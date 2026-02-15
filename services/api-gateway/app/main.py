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
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

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
    description="REST API and WebSocket endpoints for real-time market data",
    version="0.1.0",
    lifespan=lifespan,
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

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "api-gateway", "timestamp": datetime.utcnow().isoformat()}

@app.get("/ready")
async def ready():
    is_ready = gateway.db_pool is not None and gateway._running
    return {"status": "ready" if is_ready else "not_ready"}

@app.get("/metrics")
async def prometheus_metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ============================================================================
# REST API Endpoints
# ============================================================================

@app.get("/api/v1/symbols")
async def get_symbols():
    """Get list of available symbols."""
    query = "SELECT DISTINCT symbol FROM trades ORDER BY symbol"
    async with gateway.db_pool.acquire() as conn:
        rows = await conn.fetch(query)
    return {"symbols": [row["symbol"] for row in rows]}


@app.get("/api/v1/quotes/{symbol}")
async def get_quote(symbol: str):
    """Get latest quote for a symbol."""
    query = """
        SELECT timestamp, symbol, bid_price, bid_size, ask_price, ask_size, exchange
        FROM quotes WHERE symbol = $1 ORDER BY timestamp DESC LIMIT 1
    """
    async with gateway.db_pool.acquire() as conn:
        row = await conn.fetchrow(query, symbol.upper())
    if not row:
        raise HTTPException(status_code=404, detail="Symbol not found")
    return dict(row)


@app.get("/api/v1/trades/{symbol}")
async def get_trades(symbol: str, limit: int = Query(default=100, le=1000)):
    """Get recent trades for a symbol."""
    query = """
        SELECT timestamp, trade_id, symbol, price, quantity, side, exchange
        FROM trades WHERE symbol = $1 ORDER BY timestamp DESC LIMIT $2
    """
    async with gateway.db_pool.acquire() as conn:
        rows = await conn.fetch(query, symbol.upper(), limit)
    return {"trades": [dict(row) for row in rows]}


@app.get("/api/v1/candles/{symbol}")
async def get_candles(
    symbol: str,
    interval: str = Query(default="1m", regex="^(1m|5m|15m|1h|4h|1d)$"),
    limit: int = Query(default=100, le=500),
):
    """Get OHLCV candles for a symbol."""
    query = """
        SELECT timestamp, symbol, interval, open, high, low, close, volume, trade_count, vwap
        FROM candles WHERE symbol = $1 AND interval = $2 ORDER BY timestamp DESC LIMIT $3
    """
    async with gateway.db_pool.acquire() as conn:
        rows = await conn.fetch(query, symbol.upper(), interval, limit)
    return {"candles": [dict(row) for row in rows]}


@app.get("/api/v1/alerts")
async def get_alerts(
    symbol: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = Query(default=50, le=200),
):
    """Get recent alerts."""
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


@app.get("/api/v1/market-summary")
async def get_market_summary():
    """Get market summary with latest prices for all symbols."""
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
    """WebSocket for real-time quotes."""
    channel = f"quotes:{symbol.upper()}"
    await manager.connect(websocket, channel)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)


@app.websocket("/ws/trades/{symbol}")
async def ws_trades(websocket: WebSocket, symbol: str):
    """WebSocket for real-time trades."""
    channel = f"trades:{symbol.upper()}"
    await manager.connect(websocket, channel)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)


@app.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket, symbol: Optional[str] = None):
    """WebSocket for real-time alerts."""
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
