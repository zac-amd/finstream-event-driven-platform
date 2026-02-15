# FinStream API Documentation

> **Complete API Reference for Developers**

This document provides comprehensive documentation for all FinStream REST APIs and WebSocket endpoints.

---

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [API Gateway (Market Data)](#api-gateway-market-data)
4. [Portfolio Service](#portfolio-service)
5. [Market Data Service](#market-data-service)
6. [WebSocket Endpoints](#websocket-endpoints)
7. [Error Handling](#error-handling)
8. [Rate Limits](#rate-limits)

---

## Overview

### Base URLs

| Service | Local URL | Description |
|---------|-----------|-------------|
| API Gateway | `http://localhost:8000` | Market data, candles, trades |
| Portfolio Service | `http://localhost:8003` | Auth, portfolios, trading |
| Market Data Service | `http://localhost:8002` | Yahoo Finance integration |
| Dashboard (Proxy) | `http://localhost:3000/api/` | Unified access via nginx |

### Interactive Documentation (Swagger UI)

- **API Gateway**: http://localhost:8000/docs
- **Portfolio Service**: http://localhost:8003/docs
- **Market Data Service**: http://localhost:8002/docs

### Content Type

All requests and responses use JSON:
```
Content-Type: application/json
```

---

## Authentication

### Overview

FinStream uses **JWT (JSON Web Tokens)** for authentication.

**Token Types:**
| Token | Lifetime | Purpose |
|-------|----------|---------|
| Access Token | 30 minutes | API authentication |
| Refresh Token | 7 days | Obtain new access token |

### Authenticating Requests

Include the access token in the `Authorization` header:

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Register User

Create a new user account.

```http
POST /api/v1/auth/register
```

**Request Body:**
```json
{
  "email": "user@example.com",
  "username": "trader123",
  "password": "securepassword",
  "full_name": "John Doe"
}
```

**Response (201 Created):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "username": "trader123",
  "full_name": "John Doe",
  "is_verified": false,
  "created_at": "2026-02-14T12:00:00Z"
}
```

**Validation:**
| Field | Rules |
|-------|-------|
| email | Valid email format, unique |
| username | 3-30 characters, unique |
| password | Minimum 8 characters |

---

### Login

Authenticate and obtain tokens.

```http
POST /api/v1/auth/login
```

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "securepassword"
}
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

---

### Get Current User

Get the authenticated user's profile.

```http
GET /api/v1/auth/me
Authorization: Bearer <access_token>
```

**Response (200 OK):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "username": "trader123",
  "full_name": "John Doe",
  "is_verified": false,
  "created_at": "2026-02-14T12:00:00Z"
}
```

---

## API Gateway (Market Data)

### Get Market Summary

Get latest prices for all tracked symbols.

```http
GET /api/v1/market-summary
```

**Response (200 OK):**
```json
{
  "summary": [
    {
      "symbol": "AAPL",
      "price": 150.75,
      "timestamp": "2026-02-14T12:00:00Z"
    },
    {
      "symbol": "GOOGL",
      "price": 142.30,
      "timestamp": "2026-02-14T12:00:00Z"
    }
  ]
}
```

---

### Get Available Symbols

List all symbols with trading data.

```http
GET /api/v1/symbols
```

**Response (200 OK):**
```json
{
  "symbols": ["AAPL", "AMZN", "GOOGL", "META", "MSFT", "NVDA", "TSLA"]
}
```

---

### Get Quote

Get the latest quote for a specific symbol.

```http
GET /api/v1/quotes/{symbol}
```

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| symbol | string | Stock ticker (e.g., AAPL) |

**Response (200 OK):**
```json
{
  "timestamp": "2026-02-14T12:00:00Z",
  "symbol": "AAPL",
  "bid_price": 150.25,
  "bid_size": 100,
  "ask_price": 150.30,
  "ask_size": 200,
  "exchange": "NASDAQ"
}
```

**Error (404 Not Found):**
```json
{
  "detail": "Symbol not found"
}
```

---

### Get Trades

Get recent trades for a symbol.

```http
GET /api/v1/trades/{symbol}?limit=100
```

**Query Parameters:**
| Parameter | Type | Default | Max | Description |
|-----------|------|---------|-----|-------------|
| limit | integer | 100 | 1000 | Number of trades |

**Response (200 OK):**
```json
{
  "trades": [
    {
      "timestamp": "2026-02-14T12:00:00Z",
      "trade_id": "T123456",
      "symbol": "AAPL",
      "price": 150.27,
      "quantity": 50,
      "side": "BUY",
      "exchange": "NASDAQ"
    }
  ]
}
```

---

### Get Candles (OHLCV)

Get candlestick data for a symbol.

```http
GET /api/v1/candles/{symbol}?interval=1m&limit=100
```

**Query Parameters:**
| Parameter | Type | Default | Options | Description |
|-----------|------|---------|---------|-------------|
| interval | string | 1m | 1m, 5m, 15m, 1h, 4h, 1d | Candle interval |
| limit | integer | 100 | 1-500 | Number of candles |

**Response (200 OK):**
```json
{
  "candles": [
    {
      "timestamp": "2026-02-14T12:00:00Z",
      "symbol": "AAPL",
      "interval": "1m",
      "open": 150.00,
      "high": 151.00,
      "low": 149.50,
      "close": 150.75,
      "volume": 10000,
      "trade_count": 250,
      "vwap": 150.50
    }
  ]
}
```

---

### Get Alerts

Get market alerts (price spikes, anomalies).

```http
GET /api/v1/alerts?symbol=AAPL&severity=WARNING&limit=50
```

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| symbol | string | null | Filter by symbol |
| severity | string | null | INFO, WARNING, CRITICAL |
| limit | integer | 50 | Max 200 |

**Response (200 OK):**
```json
{
  "alerts": [
    {
      "timestamp": "2026-02-14T12:00:00Z",
      "alert_id": "A123456",
      "symbol": "AAPL",
      "alert_type": "PRICE_SPIKE",
      "severity": "WARNING",
      "message": "Price increased 5% in 1 minute",
      "metadata": {
        "price_change_pct": 5.2,
        "previous_price": 143.00,
        "current_price": 150.45
      }
    }
  ]
}
```

---

## Portfolio Service

### List Portfolios

Get all portfolios for the authenticated user.

```http
GET /api/v1/portfolios
Authorization: Bearer <access_token>
```

**Response (200 OK):**
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "My Portfolio",
    "description": null,
    "initial_cash": "10000.00",
    "current_cash": "8500.00",
    "is_default": true,
    "is_public": false,
    "created_at": "2026-02-14T12:00:00Z"
  }
]
```

---

### Create Portfolio

Create a new portfolio.

```http
POST /api/v1/portfolios
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "name": "Growth Portfolio",
  "description": "Long-term growth stocks",
  "initial_cash": "25000.00",
  "is_public": true
}
```

**Response (201 Created):**
```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "name": "Growth Portfolio",
  "description": "Long-term growth stocks",
  "initial_cash": "25000.00",
  "current_cash": "25000.00",
  "is_default": false,
  "is_public": true,
  "created_at": "2026-02-14T12:00:00Z"
}
```

---

### Get Portfolio Summary

Get detailed portfolio summary with real-time P&L.

```http
GET /api/v1/portfolios/{portfolio_id}/summary
Authorization: Bearer <access_token>
```

**Response (200 OK):**
```json
{
  "portfolio_id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "My Portfolio",
  "cash_balance": "8500.00",
  "holdings_value": "2150.00",
  "total_value": "10650.00",
  "total_cost_basis": "1500.00",
  "total_pnl": "650.00",
  "total_pnl_pct": "43.33",
  "holdings": [
    {
      "symbol": "AAPL",
      "quantity": "10",
      "average_cost": "150.00",
      "total_cost": "1500.00",
      "current_price": "215.00",
      "market_value": "2150.00",
      "unrealized_pnl": "650.00",
      "unrealized_pnl_pct": "43.33"
    }
  ]
}
```

---

### Buy Stock

Execute a buy order.

```http
POST /api/v1/portfolios/{portfolio_id}/buy
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "symbol": "AAPL",
  "quantity": "10",
  "notes": "Buying on dip"
}
```

**Response (200 OK):**
```json
{
  "transaction_id": "770e8400-e29b-41d4-a716-446655440002",
  "symbol": "AAPL",
  "transaction_type": "BUY",
  "quantity": "10",
  "price": "150.00",
  "total_amount": "1500.00",
  "remaining_cash": "8500.00",
  "executed_at": "2026-02-14T12:00:00Z"
}
```

**Error (400 Bad Request):**
```json
{
  "detail": "Insufficient funds for this purchase"
}
```

---

### Sell Stock

Execute a sell order.

```http
POST /api/v1/portfolios/{portfolio_id}/sell
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "symbol": "AAPL",
  "quantity": "5",
  "notes": "Taking profits"
}
```

**Response (200 OK):**
```json
{
  "transaction_id": "880e8400-e29b-41d4-a716-446655440003",
  "symbol": "AAPL",
  "transaction_type": "SELL",
  "quantity": "5",
  "price": "160.00",
  "total_amount": "800.00",
  "remaining_cash": "9300.00",
  "executed_at": "2026-02-14T12:00:00Z"
}
```

---

### Get Transaction History

Get all transactions for a portfolio.

```http
GET /api/v1/portfolios/{portfolio_id}/transactions?limit=50
Authorization: Bearer <access_token>
```

**Response (200 OK):**
```json
[
  {
    "id": "770e8400-e29b-41d4-a716-446655440002",
    "symbol": "AAPL",
    "transaction_type": "BUY",
    "quantity": "10",
    "price": "150.00",
    "total_amount": "1500.00",
    "executed_at": "2026-02-14T12:00:00Z"
  }
]
```

---

### Get Leaderboard

Get public portfolio rankings (no auth required).

```http
GET /api/v1/leaderboard?limit=10
```

**Response (200 OK):**
```json
[
  {
    "portfolio_id": "550e8400-e29b-41d4-a716-446655440000",
    "portfolio_name": "Growth Portfolio",
    "username": "trader123",
    "total_value": 15000.00,
    "initial_value": 10000.00,
    "return_pct": 50.0
  }
]
```

---

## Market Data Service

### Get Yahoo Finance Quote

Get real-time quote from Yahoo Finance.

```http
GET /api/v1/yahoo/quote/{symbol}
```

**Response (200 OK):**
```json
{
  "symbol": "AAPL",
  "price": 150.75,
  "open": 149.00,
  "high": 152.00,
  "low": 148.50,
  "volume": 50000000,
  "previous_close": 148.00
}
```

---

## WebSocket Endpoints

### Overview

WebSocket connections provide real-time streaming data.

**Base URL:** `ws://localhost:8000/ws/`

### Quotes Stream

Subscribe to real-time quote updates.

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/quotes/AAPL');

ws.onmessage = (event) => {
  const quote = JSON.parse(event.data);
  console.log('Quote:', quote);
};
```

**Message Format:**
```json
{
  "timestamp": "2026-02-14T12:00:00.123Z",
  "symbol": "AAPL",
  "bid_price": 150.25,
  "bid_size": 100,
  "ask_price": 150.30,
  "ask_size": 200
}
```

---

### Trades Stream

Subscribe to real-time trade executions.

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/trades/AAPL');

ws.onmessage = (event) => {
  const trade = JSON.parse(event.data);
  console.log('Trade:', trade);
};
```

---

### Alerts Stream

Subscribe to market alerts.

```javascript
// All alerts
const ws = new WebSocket('ws://localhost:8000/ws/alerts');

// Symbol-specific alerts
const ws = new WebSocket('ws://localhost:8000/ws/alerts?symbol=AAPL');
```

---

## Error Handling

### HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request - Invalid input |
| 401 | Unauthorized - Invalid/missing token |
| 403 | Forbidden - Access denied |
| 404 | Not Found - Resource doesn't exist |
| 422 | Validation Error |
| 500 | Internal Server Error |
| 503 | Service Unavailable |

### Error Response Format

```json
{
  "detail": "Error message describing what went wrong"
}
```

### Validation Errors (422)

```json
{
  "detail": [
    {
      "loc": ["body", "email"],
      "msg": "value is not a valid email address",
      "type": "value_error.email"
    }
  ]
}
```

---

## Rate Limits

| Endpoint Type | Limit |
|---------------|-------|
| REST API | 100 requests/minute per IP |
| WebSocket | 10 connections per IP |

**Rate Limit Headers:**
```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1707912060
```

---

## Code Examples

### Python (requests)

```python
import requests

# Login
response = requests.post(
    "http://localhost:8003/api/v1/auth/login",
    json={"email": "user@example.com", "password": "password123"}
)
tokens = response.json()
access_token = tokens["access_token"]

# Get portfolio summary
headers = {"Authorization": f"Bearer {access_token}"}
response = requests.get(
    "http://localhost:8003/api/v1/portfolios/PORTFOLIO_ID/summary",
    headers=headers
)
summary = response.json()
print(f"Total Value: ${summary['total_value']}")

# Buy stock
response = requests.post(
    "http://localhost:8003/api/v1/portfolios/PORTFOLIO_ID/buy",
    headers=headers,
    json={"symbol": "AAPL", "quantity": "10"}
)
trade = response.json()
print(f"Bought {trade['quantity']} shares at ${trade['price']}")
```

### JavaScript (fetch)

```javascript
// Login
const loginResponse = await fetch('http://localhost:8003/api/v1/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email: 'user@example.com', password: 'password123' })
});
const tokens = await loginResponse.json();

// Get market summary
const summaryResponse = await fetch('http://localhost:8000/api/v1/market-summary');
const summary = await summaryResponse.json();
console.log(summary.summary);

// Buy stock (with auth)
const buyResponse = await fetch('http://localhost:8003/api/v1/portfolios/PORTFOLIO_ID/buy', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${tokens.access_token}`
  },
  body: JSON.stringify({ symbol: 'AAPL', quantity: '10' })
});
const trade = await buyResponse.json();
```

### cURL

```bash
# Login
curl -X POST http://localhost:8003/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "password123"}'

# Get market summary
curl http://localhost:8000/api/v1/market-summary

# Buy stock
curl -X POST http://localhost:8003/api/v1/portfolios/PORTFOLIO_ID/buy \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"symbol": "AAPL", "quantity": "10"}'
```

---

## Health Check Endpoints

Each service exposes health endpoints:

```bash
# API Gateway
curl http://localhost:8000/health
curl http://localhost:8000/ready

# Portfolio Service
curl http://localhost:8003/health
curl http://localhost:8003/ready

# Market Data Service
curl http://localhost:8002/health
```

**Health Response:**
```json
{
  "status": "healthy",
  "service": "api-gateway",
  "timestamp": "2026-02-14T12:00:00Z"
}
```

---

*Last updated: February 2026*
