"""
FinStream API Gateway - Main Application

REST API + WebSocket endpoints for real-time data streaming.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncIterator, List, Optional

import uvicorn
import asyncpg
import redis.asyncio as redis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from pydantic import BaseModel, Field

from finstream_common.config import get_settings
from finstream_common.logging import setup_logging, get_logger
from finstream_common.metrics import setup_metrics, get_metrics
from finstream_common.tracing import setup_tracing

# Initialize
settings = get_settings()
setup_logging(service_name="api-gateway", settings=settings)
setup_tracing(service_name="api-gateway", settings=settings)
metrics = setup_metrics(service_name="api-gateway", settings=settings)
logger = get_logger(__name__)


# ============================================================================
# Pydantic Models for API Documentation
# ============================================================================

class HealthResponse(BaseModel):
    status: str = Field(example="healthy")
    service: str = Field(example="api-gateway")
    timestamp: str = Field(example="2026-02-14T00:00:00")


class QuoteResponse(BaseModel):
    timestamp: datetime
    symbol: str = Field(example="AAPL")
    bid_price: float = Field(example=150.25)
    bid_size: int = Field(example=100)
    ask_price: float = Field(example=150.30)
    ask_size: int = Field(example=200)
    exchange: str = Field(example="NASDAQ")


class Trade(BaseModel):
    timestamp: datetime
    trade_id: str
    symbol: str = Field(example="AAPL")
    price: float = Field(example=150.27)
    quantity: int = Field(example=50)
    side: str = Field(example="BUY")
    exchange: str = Field(example="NASDAQ")


class TradesResponse(BaseModel):
    trades: List[Trade]


class Candle(BaseModel):
    timestamp: datetime
    symbol: str = Field(example="AAPL")
    interval: str = Field(example="1m")
    open: float = Field(example=150.00)
    high: float = Field(example=151.00)
    low: float = Field(example=149.50)
    close: float = Field(example=150.75)
    volume: int = Field(example=10000)
    trade_count: int = Field(example=250)
    vwap: Optional[float] = Field(example=150.50)


class CandlesResponse(BaseModel):
    candles: List[Candle]


class Alert(BaseModel):
    timestamp: datetime
    alert_id: str
    symbol: str
    alert_type: str = Field(example="PRICE_SPIKE")
    severity: str = Field(example="WARNING")
    message: str
    metadata: Optional[dict] = None


class AlertsResponse(BaseModel):
    alerts: List[Alert]


class MarketSummaryItem(BaseModel):
    symbol: str = Field(example="AAPL")
    price: float = Field(example=150.75)
    timestamp: datetime


class MarketSummaryResponse(BaseModel):
    summary: List[MarketSummaryItem]


class SymbolsResponse(BaseModel):
    symbols: List[str] = Field(example=["AAPL", "GOOGL", "MSFT"])


class ConnectionManager:
    """Manage WebSocket connections."""
    
    def __init__(self):
        self.active_connections: dict[str, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, channel: str):
        await websocket.accept()
        if channel not in self.active_connections:
            self.active_connections[channel] = []
        self.active_connections[channel].append(websocket)
        logger.info("ws_connected", channel=channel)
    
    def disconnect(self, websocket: WebSocket, channel: str):
        if channel in self.active_connections:
            self.active_connections[channel].remove(websocket)
        logger.info("ws_disconnected", channel=channel)
    
    async def broadcast(self, channel: str, message: str):
        if channel in self.active_connections:
            for connection in self.active_connections[channel]:
                try:
                    await connection.send_text(message)
                except Exception:
                    pass


manager = ConnectionManager()


class APIGateway:
    """Main API Gateway service."""
    
    def __init__(self):
        self.db_pool: asyncpg.Pool | None = None
        self.redis_client: redis.Redis | None = None
        self._running = False
        self._tasks: list[asyncio.Task] = []
    
    async def start(self):
        logger.info("starting_api_gateway")
        
        # Connect to TimescaleDB
        self.db_pool = await asyncpg.create_pool(
            dsn=settings.timescale_url,
            min_size=5,
            max_size=settings.timescale_pool_size,
        )
        
        # Connect to Redis
        self.redis_client = redis.from_url(settings.redis_url)
        
        self._running = True
        
        # Start Redis subscriber for real-time updates
        self._tasks = [
            asyncio.create_task(self._redis_subscriber()),
        ]
        
        logger.info("api_gateway_started")
    
    async def stop(self):
        logger.info("stopping_api_gateway")
        self._running = False
        
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        
        if self.db_pool:
            await self.db_pool.close()
        if self.redis_client:
            await self.redis_client.close()
        
        logger.info("api_gateway_stopped")
    
    async def _redis_subscriber(self):
        """Subscribe to Redis channels and broadcast to WebSocket clients."""
        pubsub = self.redis_client.pubsub()
        await pubsub.psubscribe("quotes:*", "trades:*", "alerts:*")
        
        while self._running:
            try:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
                if message:
                    channel = message["channel"].decode() if isinstance(message["channel"], bytes) else message["channel"]
                    data = message["data"].decode() if isinstance(message["data"], bytes) else message["data"]
                    await manager.broadcast(channel, data)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("redis_subscriber_error", error=str(e))
                await asyncio.sleep(1)
        
        await pubsub.unsubscribe()


gateway = APIGateway()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await gateway.start()
    yield
    await gateway.stop()


app = FastAPI(
    title="FinStream API Gateway",
    description="""
## Real-Time Market Data API

FinStream provides REST API and WebSocket endpoints for accessing real-time and historical market data.

### Features
- **Real-time Quotes**: Get live bid/ask prices via REST or WebSocket
- **Trade Feed**: Access recent trades and subscribe to live trade streams
- **OHLCV Candles**: Query historical candlestick data with multiple intervals
- **Market Alerts**: Receive notifications for price spikes and anomalies

### Authentication
Most endpoints are public. Portfolio and trading endpoints require JWT authentication.

### Rate Limits
- REST API: 100 requests/minute per IP
- WebSocket: 10 connections per IP

### WebSocket Channels
- `/ws/quotes/{symbol}` - Real-time quote updates
- `/ws/trades/{symbol}` - Real-time trade feed
- `/ws/alerts` - Market alert notifications
    """,
    version="1.0.0",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "Health", "description": "Service health and readiness checks"},
        {"name": "Market Data", "description": "Real-time and historical market data"},
        {"name": "Alerts", "description": "Market alerts and notifications"},
        {"name": "WebSocket", "description": "Real-time streaming endpoints"},
    ],
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Health & Metrics Endpoints
# ============================================================================

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health():
    """Check service health status."""
    return {"status": "healthy", "service": "api-gateway", "timestamp": datetime.utcnow().isoformat()}


@app.get("/ready", tags=["Health"])
async def ready():
    """Check if service is ready to accept traffic."""
    is_ready = gateway.db_pool is not None and gateway._running
    return {"status": "ready" if is_ready else "not_ready"}


@app.get("/metrics", tags=["Health"], include_in_schema=False)
async def prometheus_metrics():
    """Prometheus metrics endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ============================================================================
# REST API Endpoints
# ============================================================================

@app.get("/api/v1/symbols", response_model=SymbolsResponse, tags=["Market Data"])
async def get_symbols():
    """
    Get list of all available trading symbols.
    
    Returns a list of stock ticker symbols that have trading data available.
    """
    query = "SELECT DISTINCT symbol FROM trades ORDER BY symbol"
    async with gateway.db_pool.acquire() as conn:
        rows = await conn.fetch(query)
    return {"symbols": [row["symbol"] for row in rows]}


@app.get("/api/v1/quotes/{symbol}", response_model=QuoteResponse, tags=["Market Data"])
async def get_quote(symbol: str):
    """
    Get the latest quote for a specific symbol.
    
    - **symbol**: Stock ticker symbol (e.g., AAPL, GOOGL)
    
    Returns the most recent bid/ask prices and sizes.
    """
    query = """
        SELECT timestamp, symbol, bid_price, bid_size, ask_price, ask_size, exchange
        FROM quotes WHERE symbol = $1 ORDER BY timestamp DESC LIMIT 1
    """
    async with gateway.db_pool.acquire() as conn:
        row = await conn.fetchrow(query, symbol.upper())
    if not row:
        raise HTTPException(status_code=404, detail="Symbol not found")
    return dict(row)


@app.get("/api/v1/trades/{symbol}", response_model=TradesResponse, tags=["Market Data"])
async def get_trades(
    symbol: str,
    limit: int = Query(default=100, le=1000, description="Maximum number of trades to return")
):
    """
    Get recent trades for a specific symbol.
    
    - **symbol**: Stock ticker symbol
    - **limit**: Maximum number of trades (1-1000)
    
    Returns trades in reverse chronological order.
    """
    query = """
        SELECT timestamp, trade_id, symbol, price, quantity, side, exchange
        FROM trades WHERE symbol = $1 ORDER BY timestamp DESC LIMIT $2
    """
    async with gateway.db_pool.acquire() as conn:
        rows = await conn.fetch(query, symbol.upper(), limit)
    return {"trades": [dict(row) for row in rows]}


@app.get("/api/v1/candles/{symbol}", response_model=CandlesResponse, tags=["Market Data"])
async def get_candles(
    symbol: str,
    interval: str = Query(default="1m", regex="^(1m|5m|15m|1h|4h|1d)$", description="Candle interval"),
    limit: int = Query(default=100, le=500, description="Maximum candles to return"),
):
    """
    Get OHLCV candlestick data for a symbol.
    
    - **symbol**: Stock ticker symbol
    - **interval**: Candle time interval (1m, 5m, 15m, 1h, 4h, 1d)
    - **limit**: Maximum number of candles (1-500)
    
    Returns candles with open, high, low, close, volume, and VWAP.
    """
    query = """
        SELECT timestamp, symbol, interval, open, high, low, close, volume, trade_count, vwap
        FROM candles WHERE symbol = $1 AND interval = $2 ORDER BY timestamp DESC LIMIT $3
    """
    async with gateway.db_pool.acquire() as conn:
        rows = await conn.fetch(query, symbol.upper(), interval, limit)
    return {"candles": [dict(row) for row in rows]}


@app.get("/api/v1/alerts", response_model=AlertsResponse, tags=["Alerts"])
async def get_alerts(
    symbol: Optional[str] = Query(default=None, description="Filter by symbol"),
    severity: Optional[str] = Query(default=None, description="Filter by severity (INFO, WARNING, CRITICAL)"),
    limit: int = Query(default=50, le=200, description="Maximum alerts to return"),
):
    """
    Get recent market alerts.
    
    - **symbol**: Optional filter by stock symbol
    - **severity**: Optional filter by alert severity
    - **limit**: Maximum number of alerts (1-200)
    
    Alert types include PRICE_SPIKE, VOLUME_ANOMALY, and PRICE_DROP.
    """
    query = "SELECT * FROM alerts WHERE 1=1"
    params = []
    
    if symbol:
        params.append(symbol.upper())
        query += f" AND symbol = ${len(params)}"
    if severity:
        params.append(severity)
        query += f" AND severity = ${len(params)}"
    
    params.append(limit)
    query += f" ORDER BY timestamp DESC LIMIT ${len(params)}"
    
    async with gateway.db_pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return {"alerts": [dict(row) for row in rows]}


@app.get("/api/v1/market-summary", response_model=MarketSummaryResponse, tags=["Market Data"])
async def get_market_summary():
    """
    Get market summary with latest prices for all tracked symbols.
    
    Returns the most recent closing price from 1-minute candles for each symbol.
    Useful for displaying a market overview dashboard.
    """
    query = """
        SELECT DISTINCT ON (symbol) symbol, close as price, timestamp
        FROM candles WHERE interval = '1m'
        ORDER BY symbol, timestamp DESC
    """
    async with gateway.db_pool.acquire() as conn:
        rows = await conn.fetch(query)
    return {"summary": [dict(row) for row in rows]}


# ============================================================================
# WebSocket Endpoints
# ============================================================================

@app.websocket("/ws/quotes/{symbol}")
async def ws_quotes(websocket: WebSocket, symbol: str):
    """
    WebSocket endpoint for real-time quote updates.
    
    Connect to receive live bid/ask updates for a specific symbol.
    Messages are JSON-formatted quote objects.
    """
    channel = f"quotes:{symbol.upper()}"
    await manager.connect(websocket, channel)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)


@app.websocket("/ws/trades/{symbol}")
async def ws_trades(websocket: WebSocket, symbol: str):
    """
    WebSocket endpoint for real-time trade feed.
    
    Connect to receive live trade executions for a specific symbol.
    Messages are JSON-formatted trade objects.
    """
    channel = f"trades:{symbol.upper()}"
    await manager.connect(websocket, channel)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)


@app.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket, symbol: Optional[str] = None):
    """
    WebSocket endpoint for real-time market alerts.
    
    Connect to receive live alerts for price spikes, volume anomalies, etc.
    Optionally filter by symbol.
    """
    channel = f"alerts:{symbol.upper()}" if symbol else "alerts:all"
    await manager.connect(websocket, channel)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)


def main():
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, log_level="info", reload=settings.is_development)


if __name__ == "__main__":
    main()
