"""
Portfolio Service - User Authentication, Portfolios, and Trading

Production-ready portfolio management with JWT authentication.
"""

import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from decimal import Decimal
from typing import AsyncIterator
from uuid import UUID

import asyncpg
import httpx
import structlog
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field
from pydantic_settings import BaseSettings


# =============================================================================
# CONFIGURATION
# =============================================================================

class Settings(BaseSettings):
    database_url: str = "postgresql://finstream:finstream@timescaledb:5432/finstream"
    redis_url: str = "redis://redis:6379"
    market_data_url: str = "http://market-data-service:8002"
    jwt_secret: str = "your-super-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    
    class Config:
        env_prefix = ""


settings = Settings()
logger = structlog.get_logger()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=30)
    password: str = Field(..., min_length=8)
    full_name: str | None = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    full_name: str | None
    is_verified: bool
    created_at: datetime


class PortfolioCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    initial_cash: Decimal = Field(default=Decimal("10000.00"), ge=0)
    is_public: bool = False


class PortfolioResponse(BaseModel):
    id: str
    name: str
    description: str | None
    initial_cash: Decimal
    current_cash: Decimal
    is_default: bool
    is_public: bool
    created_at: datetime


class HoldingResponse(BaseModel):
    symbol: str
    quantity: Decimal
    average_cost: Decimal
    total_cost: Decimal
    current_price: Decimal | None = None
    market_value: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    unrealized_pnl_pct: Decimal | None = None


class TradeRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=10)
    quantity: Decimal = Field(..., gt=0)
    notes: str | None = None


class TradeResponse(BaseModel):
    transaction_id: str
    symbol: str
    transaction_type: str
    quantity: Decimal
    price: Decimal
    total_amount: Decimal
    remaining_cash: Decimal
    executed_at: datetime


class TransactionResponse(BaseModel):
    id: str
    symbol: str
    transaction_type: str
    quantity: Decimal
    price: Decimal
    total_amount: Decimal
    executed_at: datetime


class PortfolioSummary(BaseModel):
    portfolio_id: str
    name: str
    cash_balance: Decimal
    holdings_value: Decimal
    total_value: Decimal
    total_cost_basis: Decimal
    total_pnl: Decimal
    total_pnl_pct: Decimal
    holdings: list[HoldingResponse]


# =============================================================================
# DATABASE CONNECTION
# =============================================================================

pool: asyncpg.Pool | None = None


async def get_db() -> asyncpg.Pool:
    global pool
    if pool is None:
        raise HTTPException(status_code=503, detail="Database not available")
    return pool


# =============================================================================
# JWT AUTHENTICATION
# =============================================================================

def create_access_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": user_id, "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
    payload = {"sub": user_id, "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: asyncpg.Pool = Depends(get_db)
) -> dict:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = payload.get("sub")
        token_type = payload.get("type")
        
        if user_id is None or token_type != "access":
            raise HTTPException(status_code=401, detail="Invalid token")
            
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user = await db.fetchrow(
        "SELECT id, email, username, full_name, is_active, is_verified FROM users WHERE id = $1",
        UUID(user_id)
    )
    
    if user is None or not user["is_active"]:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    
    return dict(user)


# =============================================================================
# MARKET DATA CLIENT
# =============================================================================

async def get_current_price(symbol: str) -> Decimal | None:
    """Get current price from market-data-service."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.market_data_url}/api/v1/yahoo/quote/{symbol}",
                timeout=5.0
            )
            if response.status_code == 200:
                data = response.json()
                return Decimal(str(data.get("price", 0)))
    except Exception as e:
        logger.warning("failed_to_get_price", symbol=symbol, error=str(e))
    return None


# =============================================================================
# APPLICATION LIFECYCLE
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global pool
    logger.info("starting_portfolio_service")
    
    # Connect to database
    pool = await asyncpg.create_pool(
        settings.database_url,
        min_size=5,
        max_size=20
    )
    logger.info("database_connected")
    
    yield
    
    if pool:
        await pool.close()
    logger.info("portfolio_service_stopped")


app = FastAPI(
    title="FinStream Portfolio Service",
    description="""
## Portfolio Management & Paper Trading API

Manage virtual portfolios and execute paper trades with real market data.

### Features
- **User Authentication**: Register, login, and JWT token management
- **Portfolio Management**: Create and manage multiple portfolios
- **Paper Trading**: Buy and sell stocks using real-time Yahoo Finance prices
- **P&L Tracking**: Real-time profit/loss calculation for holdings
- **Leaderboard**: Public portfolio rankings

### Authentication
All portfolio and trading endpoints require JWT authentication.
1. Register or login to get an access token
2. Include the token in the `Authorization` header: `Bearer <token>`

### Paper Trading
- Start with $10,000 virtual cash
- Execute trades at real market prices
- Track your portfolio performance over time
    """,
    version="1.0.0",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "Health", "description": "Service health endpoints"},
        {"name": "Authentication", "description": "User registration and login"},
        {"name": "Portfolios", "description": "Portfolio management"},
        {"name": "Trading", "description": "Buy and sell stocks"},
        {"name": "Public", "description": "Public endpoints (no auth required)"},
    ],
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# HEALTH ENDPOINTS
# =============================================================================

@app.get("/health", tags=["Health"])
async def health():
    """Check service health status."""
    return {"status": "healthy", "service": "portfolio-service"}


@app.get("/ready", tags=["Health"])
async def ready():
    """Check if service is ready to accept traffic."""
    return {"status": "ready" if pool else "not_ready"}


# =============================================================================
# AUTH ENDPOINTS
# =============================================================================

@app.post("/api/v1/auth/register", response_model=UserResponse, status_code=201, tags=["Authentication"])
async def register(user_data: UserCreate, db: asyncpg.Pool = Depends(get_db)):
    """
    Register a new user account.
    
    Creates a new user with the provided email, username, and password.
    A default portfolio with $10,000 virtual cash is automatically created.
    """
    # Check if email or username exists
    existing = await db.fetchrow(
        "SELECT email FROM users WHERE email = $1 OR username = $2",
        user_data.email, user_data.username
    )
    if existing:
        raise HTTPException(status_code=400, detail="Email or username already registered")
    
    # Hash password and create user
    password_hash = pwd_context.hash(user_data.password)
    
    user = await db.fetchrow(
        """
        INSERT INTO users (email, username, password_hash, full_name)
        VALUES ($1, $2, $3, $4)
        RETURNING id, email, username, full_name, is_verified, created_at
        """,
        user_data.email, user_data.username, password_hash, user_data.full_name
    )
    
    # Create default portfolio
    await db.execute(
        """
        INSERT INTO portfolios (user_id, name, is_default)
        VALUES ($1, 'My Portfolio', TRUE)
        """,
        user["id"]
    )
    
    logger.info("user_registered", user_id=str(user["id"]), email=user_data.email)
    return UserResponse(id=str(user["id"]), **{k: v for k, v in dict(user).items() if k != "id"})


@app.post("/api/v1/auth/login", response_model=TokenResponse, tags=["Authentication"])
async def login(credentials: UserLogin, db: asyncpg.Pool = Depends(get_db)):
    """
    Login with email and password to obtain JWT tokens.
    
    Returns an access token (30 min) and refresh token (7 days).
    Include the access token in the Authorization header for protected endpoints.
    """
    user = await db.fetchrow(
        "SELECT id, password_hash, is_active FROM users WHERE email = $1",
        credentials.email
    )
    
    if user is None or not pwd_context.verify(credentials.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="Account is disabled")
    
    # Update last login
    await db.execute(
        "UPDATE users SET last_login_at = NOW() WHERE id = $1",
        user["id"]
    )
    
    access_token = create_access_token(str(user["id"]))
    refresh_token = create_refresh_token(str(user["id"]))
    
    logger.info("user_logged_in", user_id=str(user["id"]))
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60
    )


@app.get("/api/v1/auth/me", response_model=UserResponse, tags=["Authentication"])
async def get_me(current_user: dict = Depends(get_current_user)):
    """
    Get the current authenticated user's profile.
    
    Requires valid JWT access token in Authorization header.
    """
    return UserResponse(
        id=str(current_user["id"]),
        email=current_user["email"],
        username=current_user["username"],
        full_name=current_user["full_name"],
        is_verified=current_user["is_verified"],
        created_at=datetime.utcnow()  # Simplified
    )


# =============================================================================
# PORTFOLIO ENDPOINTS
# =============================================================================

@app.get("/api/v1/portfolios", response_model=list[PortfolioResponse], tags=["Portfolios"])
async def list_portfolios(
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db)
):
    """
    List all portfolios owned by the current user.
    
    Returns portfolio metadata including cash balances and settings.
    """
    rows = await db.fetch(
        """
        SELECT id, name, description, initial_cash, current_cash, is_default, is_public, created_at
        FROM portfolios WHERE user_id = $1 ORDER BY created_at
        """,
        current_user["id"]
    )
    return [PortfolioResponse(id=str(r["id"]), **{k: v for k, v in dict(r).items() if k != "id"}) for r in rows]


@app.post("/api/v1/portfolios", response_model=PortfolioResponse, status_code=201, tags=["Portfolios"])
async def create_portfolio(
    data: PortfolioCreate,
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db)
):
    """
    Create a new portfolio with specified initial cash.
    
    - **name**: Portfolio name (required)
    - **initial_cash**: Starting virtual cash (default: $10,000)
    - **is_public**: Whether to show on leaderboard
    """
    row = await db.fetchrow(
        """
        INSERT INTO portfolios (user_id, name, description, initial_cash, current_cash, is_public)
        VALUES ($1, $2, $3, $4, $4, $5)
        RETURNING id, name, description, initial_cash, current_cash, is_default, is_public, created_at
        """,
        current_user["id"], data.name, data.description, data.initial_cash, data.is_public
    )
    return PortfolioResponse(id=str(row["id"]), **{k: v for k, v in dict(row).items() if k != "id"})


@app.get("/api/v1/portfolios/{portfolio_id}/summary", response_model=PortfolioSummary, tags=["Portfolios"])
async def get_portfolio_summary(
    portfolio_id: str,
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db)
):
    """
    Get detailed portfolio summary with real-time P&L.
    
    Includes:
    - Cash balance
    - All holdings with current market prices
    - Unrealized P&L per holding and total
    - Portfolio total value
    """
    # Verify ownership
    portfolio = await db.fetchrow(
        "SELECT * FROM portfolios WHERE id = $1 AND user_id = $2",
        UUID(portfolio_id), current_user["id"]
    )
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    # Get holdings
    holdings = await db.fetch(
        """
        SELECT symbol, quantity, average_cost, total_cost
        FROM holdings WHERE portfolio_id = $1 AND quantity > 0
        """,
        UUID(portfolio_id)
    )
    
    # Enrich with current prices
    enriched_holdings = []
    total_market_value = Decimal("0")
    total_cost_basis = Decimal("0")
    
    for h in holdings:
        current_price = await get_current_price(h["symbol"])
        quantity = Decimal(str(h["quantity"]))
        avg_cost = Decimal(str(h["average_cost"]))
        total_cost = Decimal(str(h["total_cost"]))
        
        if current_price:
            market_value = quantity * current_price
            pnl = market_value - total_cost
            pnl_pct = (pnl / total_cost * 100) if total_cost > 0 else Decimal("0")
        else:
            market_value = total_cost
            pnl = Decimal("0")
            pnl_pct = Decimal("0")
        
        total_market_value += market_value
        total_cost_basis += total_cost
        
        enriched_holdings.append(HoldingResponse(
            symbol=h["symbol"],
            quantity=quantity,
            average_cost=avg_cost,
            total_cost=total_cost,
            current_price=current_price,
            market_value=market_value,
            unrealized_pnl=pnl,
            unrealized_pnl_pct=pnl_pct
        ))
    
    cash = Decimal(str(portfolio["current_cash"]))
    total_value = cash + total_market_value
    total_pnl = total_market_value - total_cost_basis
    total_pnl_pct = (total_pnl / total_cost_basis * 100) if total_cost_basis > 0 else Decimal("0")
    
    return PortfolioSummary(
        portfolio_id=portfolio_id,
        name=portfolio["name"],
        cash_balance=cash,
        holdings_value=total_market_value,
        total_value=total_value,
        total_cost_basis=total_cost_basis,
        total_pnl=total_pnl,
        total_pnl_pct=total_pnl_pct,
        holdings=enriched_holdings
    )


# =============================================================================
# TRADING ENDPOINTS
# =============================================================================

@app.post("/api/v1/portfolios/{portfolio_id}/buy", response_model=TradeResponse, tags=["Trading"])
async def buy_stock(
    portfolio_id: str,
    trade: TradeRequest,
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db)
):
    """
    Execute a buy order for shares of a stock.
    
    - Fetches real-time price from Yahoo Finance
    - Deducts cost from cash balance
    - Creates or updates holding position
    - Records transaction history
    
    Raises error if insufficient cash.
    """
    # Verify ownership
    portfolio = await db.fetchrow(
        "SELECT id FROM portfolios WHERE id = $1 AND user_id = $2",
        UUID(portfolio_id), current_user["id"]
    )
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    # Get current price
    price = await get_current_price(trade.symbol.upper())
    if not price:
        raise HTTPException(status_code=400, detail=f"Could not get price for {trade.symbol}")
    
    # Execute buy using database function
    try:
        result = await db.fetchrow(
            "SELECT * FROM execute_buy($1, $2, $3, $4, $5)",
            UUID(portfolio_id), trade.symbol.upper(), trade.quantity, price, trade.notes
        )
    except asyncpg.exceptions.RaiseError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    logger.info("buy_executed", 
                portfolio_id=portfolio_id, 
                symbol=trade.symbol.upper(),
                quantity=str(trade.quantity),
                price=str(price))
    
    return TradeResponse(
        transaction_id=str(result["transaction_id"]),
        symbol=trade.symbol.upper(),
        transaction_type="BUY",
        quantity=trade.quantity,
        price=price,
        total_amount=trade.quantity * price,
        remaining_cash=result["remaining_cash"],
        executed_at=datetime.utcnow()
    )


@app.post("/api/v1/portfolios/{portfolio_id}/sell", response_model=TradeResponse, tags=["Trading"])
async def sell_stock(
    portfolio_id: str,
    trade: TradeRequest,
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db)
):
    """
    Execute a sell order for shares of a stock.
    
    - Fetches real-time price from Yahoo Finance
    - Adds proceeds to cash balance
    - Reduces holding position
    - Records realized P&L
    
    Raises error if insufficient shares.
    """
    # Verify ownership
    portfolio = await db.fetchrow(
        "SELECT id FROM portfolios WHERE id = $1 AND user_id = $2",
        UUID(portfolio_id), current_user["id"]
    )
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    # Get current price
    price = await get_current_price(trade.symbol.upper())
    if not price:
        raise HTTPException(status_code=400, detail=f"Could not get price for {trade.symbol}")
    
    # Execute sell using database function
    try:
        result = await db.fetchrow(
            "SELECT * FROM execute_sell($1, $2, $3, $4, $5)",
            UUID(portfolio_id), trade.symbol.upper(), trade.quantity, price, trade.notes
        )
    except asyncpg.exceptions.RaiseError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    logger.info("sell_executed",
                portfolio_id=portfolio_id,
                symbol=trade.symbol.upper(),
                quantity=str(trade.quantity),
                price=str(price),
                realized_pnl=str(result["realized_pnl"]))
    
    return TradeResponse(
        transaction_id=str(result["transaction_id"]),
        symbol=trade.symbol.upper(),
        transaction_type="SELL",
        quantity=trade.quantity,
        price=price,
        total_amount=trade.quantity * price,
        remaining_cash=result["new_cash"],
        executed_at=datetime.utcnow()
    )


@app.get("/api/v1/portfolios/{portfolio_id}/transactions", response_model=list[TransactionResponse], tags=["Portfolios"])
async def get_transactions(
    portfolio_id: str,
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db)
):
    """
    Get transaction history for a portfolio.
    
    Returns buy/sell transactions in reverse chronological order.
    """
    # Verify ownership
    portfolio = await db.fetchrow(
        "SELECT id FROM portfolios WHERE id = $1 AND user_id = $2",
        UUID(portfolio_id), current_user["id"]
    )
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    rows = await db.fetch(
        """
        SELECT id, symbol, transaction_type, quantity, price, total_amount, executed_at
        FROM transactions WHERE portfolio_id = $1
        ORDER BY executed_at DESC LIMIT $2
        """,
        UUID(portfolio_id), limit
    )
    
    return [TransactionResponse(id=str(r["id"]), **{k: v for k, v in dict(r).items() if k != "id"}) for r in rows]


# =============================================================================
# PUBLIC PORTFOLIOS (LEADERBOARD)
# =============================================================================

@app.get("/api/v1/leaderboard", tags=["Public"])
async def get_leaderboard(
    limit: int = 10,
    db: asyncpg.Pool = Depends(get_db)
):
    """
    Get top public portfolios ranked by total value.
    
    No authentication required.
    Shows portfolio name, username, total value, and return percentage.
    """
    rows = await db.fetch(
        """
        SELECT p.id, p.name, u.username,
               p.current_cash + COALESCE(SUM(h.total_cost), 0) as total_value,
               p.initial_cash
        FROM portfolios p
        JOIN users u ON p.user_id = u.id
        LEFT JOIN holdings h ON p.id = h.portfolio_id AND h.quantity > 0
        WHERE p.is_public = TRUE
        GROUP BY p.id, p.name, u.username, p.current_cash, p.initial_cash
        ORDER BY total_value DESC
        LIMIT $1
        """,
        limit
    )
    
    return [
        {
            "portfolio_id": str(r["id"]),
            "portfolio_name": r["name"],
            "username": r["username"],
            "total_value": float(r["total_value"]),
            "initial_value": float(r["initial_cash"]),
            "return_pct": ((float(r["total_value"]) - float(r["initial_cash"])) / float(r["initial_cash"]) * 100)
                if r["initial_cash"] > 0 else 0
        }
        for r in rows
    ]
