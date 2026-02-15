"""
Market Data Service - Yahoo Finance Integration

Fetches real market data from Yahoo Finance and publishes to Kafka.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from typing import AsyncIterator
import concurrent.futures

import yfinance as yf
import redis.asyncio as redis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response

from finstream_common.config import get_settings
from finstream_common.logging import setup_logging, get_logger
from finstream_common.kafka import KafkaProducer
from finstream_common.models import Trade, OrderSide

settings = get_settings()
setup_logging(service_name="market-data-service", settings=settings)
logger = get_logger(__name__)

# Default watchlist
DEFAULT_SYMBOLS = ["AAPL", "GOOGL", "MSFT", "AMZN", "META", "NVDA", "TSLA", "JPM", "V", "JNJ"]


class YahooFinanceService:
    """Fetches real-time data from Yahoo Finance."""
    
    def __init__(self):
        self.symbols = DEFAULT_SYMBOLS
        self.producer: KafkaProducer | None = None
        self.redis_client: redis.Redis | None = None
        self._running = False
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self._tasks: list[asyncio.Task] = []
    
    async def start(self):
        """Start the service."""
        logger.info("starting_yahoo_finance_service", symbols=self.symbols)
        
        # Initialize Kafka producer
        self.producer = KafkaProducer()
        await self.producer.start()
        
        # Initialize Redis
        self.redis_client = redis.from_url(settings.redis_url)
        
        self._running = True
        
        # Start background data fetch loop
        self._tasks = [
            asyncio.create_task(self._fetch_loop()),
        ]
        
        logger.info("yahoo_finance_service_started")
    
    async def stop(self):
        """Stop the service."""
        logger.info("stopping_yahoo_finance_service")
        self._running = False
        
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        
        if self.producer:
            await self.producer.stop()
        if self.redis_client:
            await self.redis_client.close()
        
        self._executor.shutdown(wait=False)
        logger.info("yahoo_finance_service_stopped")
    
    def _fetch_quotes_sync(self, symbols: list[str]) -> dict:
        """Synchronous Yahoo Finance fetch (runs in thread pool)."""
        try:
            tickers = yf.Tickers(" ".join(symbols))
            data = {}
            for symbol in symbols:
                try:
                    ticker = tickers.tickers.get(symbol)
                    if ticker:
                        info = ticker.fast_info
                        data[symbol] = {
                            "price": float(info.last_price) if hasattr(info, 'last_price') else None,
                            "open": float(info.open) if hasattr(info, 'open') else None,
                            "high": float(info.day_high) if hasattr(info, 'day_high') else None,
                            "low": float(info.day_low) if hasattr(info, 'day_low') else None,
                            "volume": int(info.last_volume) if hasattr(info, 'last_volume') else 0,
                            "previous_close": float(info.previous_close) if hasattr(info, 'previous_close') else None,
                        }
                except Exception as e:
                    logger.warning("fetch_symbol_error", symbol=symbol, error=str(e))
            return data
        except Exception as e:
            logger.error("fetch_quotes_error", error=str(e))
            return {}
    
    async def _fetch_loop(self):
        """Background loop to fetch and publish market data."""
        while self._running:
            try:
                # Fetch quotes in thread pool (yfinance is sync)
                loop = asyncio.get_event_loop()
                quotes = await loop.run_in_executor(
                    self._executor,
                    self._fetch_quotes_sync,
                    self.symbols
                )
                
                # Process and publish each quote
                for symbol, data in quotes.items():
                    if data and data.get("price"):
                        # Create a "trade" from the price update
                        trade = Trade(
                            trade_id=f"YF-{symbol}-{datetime.utcnow().timestamp()}",
                            symbol=symbol,
                            price=Decimal(str(round(data["price"], 2))),
                            quantity=data.get("volume", 1000) // 100,  # Scaled volume
                            side=OrderSide.BUY,
                            exchange="YAHOO",
                            timestamp=datetime.utcnow(),
                        )
                        
                        # Publish to Kafka
                        await self.producer.send_model("trades", trade, key=symbol)
                        
                        # Cache latest price in Redis
                        await self.redis_client.setex(
                            f"price:{symbol}",
                            60,  # 60 second TTL
                            str(data["price"])
                        )
                        
                        logger.debug("published_quote", symbol=symbol, price=data["price"])
                
                # Yahoo Finance has rate limits, fetch every 5 seconds
                await asyncio.sleep(5)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("fetch_loop_error", error=str(e))
                await asyncio.sleep(10)
    
    async def get_quote(self, symbol: str) -> dict | None:
        """Get a single quote."""
        loop = asyncio.get_event_loop()
        quotes = await loop.run_in_executor(
            self._executor,
            self._fetch_quotes_sync,
            [symbol]
        )
        return quotes.get(symbol)
    
    async def get_cached_prices(self) -> dict:
        """Get all cached prices from Redis."""
        prices = {}
        for symbol in self.symbols:
            price = await self.redis_client.get(f"price:{symbol}")
            if price:
                prices[symbol] = float(price)
        return prices


service = YahooFinanceService()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await service.start()
    yield
    await service.stop()


app = FastAPI(
    title="FinStream Market Data Service",
    description="Real-time market data from Yahoo Finance",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "market-data-service"}


@app.get("/ready")
async def ready():
    return {"status": "ready" if service._running else "not_ready"}


@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/v1/yahoo/quote/{symbol}")
async def get_yahoo_quote(symbol: str):
    """Get real-time quote from Yahoo Finance."""
    quote = await service.get_quote(symbol.upper())
    if not quote:
        raise HTTPException(status_code=404, detail="Symbol not found")
    return {"symbol": symbol.upper(), **quote}


@app.get("/api/v1/yahoo/prices")
async def get_cached_prices():
    """Get all cached prices."""
    prices = await service.get_cached_prices()
    return {"prices": prices, "timestamp": datetime.utcnow().isoformat()}


@app.get("/api/v1/yahoo/symbols")
async def get_symbols():
    """Get list of tracked symbols."""
    return {"symbols": service.symbols}


@app.post("/api/v1/yahoo/symbols/{symbol}")
async def add_symbol(symbol: str):
    """Add a symbol to track."""
    symbol = symbol.upper()
    if symbol not in service.symbols:
        service.symbols.append(symbol)
    return {"symbols": service.symbols}


@app.delete("/api/v1/yahoo/symbols/{symbol}")
async def remove_symbol(symbol: str):
    """Remove a symbol from tracking."""
    symbol = symbol.upper()
    if symbol in service.symbols:
        service.symbols.remove(symbol)
    return {"symbols": service.symbols}
