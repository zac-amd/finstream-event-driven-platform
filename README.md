# FinStream - Real-Time Financial Data Pipeline

<div align="center">

![FinStream](https://img.shields.io/badge/FinStream-v1.0-blue?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.11+-green?style=for-the-badge&logo=python)
![TypeScript](https://img.shields.io/badge/TypeScript-5.0+-blue?style=for-the-badge&logo=typescript)
![Docker](https://img.shields.io/badge/Docker-Compose-blue?style=for-the-badge&logo=docker)

**A cloud-native microservices platform for real-time market data streaming, processing, and analytics.**

</div>

---

## 📋 Table of Contents

- [What is FinStream?](#-what-is-finstream)
- [Features](#-features)
- [Architecture](#-architecture)
- [Quick Start](#-quick-start)
- [Usage Guide](#-usage-guide)
- [API Reference](#-api-reference)
- [Observability](#-observability)
- [AWS Deployment](#-aws-deployment)
- [Troubleshooting](#-troubleshooting)

---

## 🎯 What is FinStream?

FinStream is a **production-grade demonstration** of a cloud-native microservices architecture for financial data processing. It simulates a real-time stock market data pipeline that:

1. **Generates** realistic market data (trades, quotes, prices)
2. **Streams** data through Kafka (Redpanda) in real-time
3. **Processes** streams to create OHLCV candles and aggregations
4. **Detects** anomalies and generates alerts
5. **Stores** time-series data in TimescaleDB
6. **Serves** data via REST API and WebSocket
7. **Visualizes** everything in a real-time dashboard

This project showcases **staff-level distributed systems expertise** including:
- Event-driven microservices architecture
- Stream processing with backpressure handling
- Time-series data management
- Real-time WebSocket broadcasting
- Full observability stack (metrics, tracing, logging)
- Infrastructure as Code (Terraform for AWS)

---

## ✨ Features

### Real-Time Market Data
- **10 Stock Symbols**: AAPL, GOOGL, MSFT, AMZN, META, NVDA, TSLA, JPM, V, JNJ
- **100 Trades/Second**: Configurable high-throughput data generation
- **Bid/Ask Quotes**: Realistic spread simulation with market microstructure
- **OHLCV Candles**: 1m, 5m, 15m, 1h, 4h, 1d aggregations

### Anomaly Detection
- **Price Spike Detection**: Alerts when price moves >5% in a minute
- **Volume Anomalies**: Detects unusual trading volume (>3σ from mean)
- **Real-time Alerts**: Instant WebSocket notifications

### Modern Tech Stack
| Component | Technology |
|-----------|------------|
| **Event Streaming** | Redpanda (Kafka-compatible) |
| **Time-Series DB** | TimescaleDB with continuous aggregates |
| **Caching** | Redis with pub/sub |
| **API** | FastAPI with async/await |
| **Frontend** | React + TypeScript + TailwindCSS |
| **Observability** | Prometheus + Grafana + Jaeger + Loki |

---

## 🏗 Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    Dashboard    │     │   API Gateway   │     │   Alert Service │
│   (React UI)    │◄────│  (FastAPI +     │────►│  (Anomaly       │
│                 │     │   WebSocket)    │     │   Detection)    │
└─────────────────┘     └────────┬────────┘     └────────┬────────┘
                                 │                       │
                        ┌────────▼────────┐              │
                        │   TimescaleDB   │              │
                        │  (Time-Series)  │              │
                        └────────▲────────┘              │
                                 │                       │
┌─────────────────┐     ┌────────┴────────┐     ┌────────▼────────┐
│ Market Simulator│────►│    Redpanda     │◄────│ Stream Processor│
│ (Data Generator)│     │    (Kafka)      │     │ (OHLCV Builder) │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

### Service Descriptions

| Service | Description |
|---------|-------------|
| **Market Simulator** | Generates realistic stock trades and quotes using geometric Brownian motion |
| **Stream Processor** | Consumes trades, builds OHLCV candles, writes to TimescaleDB |
| **Alert Service** | Monitors prices for anomalies, generates real-time alerts |
| **API Gateway** | REST endpoints + WebSocket for real-time data streaming |
| **Dashboard** | React SPA showing live market data and alerts |

---

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose v2+
- 8GB RAM minimum (for all services)
- Make (optional, for convenience commands)

### 1. Clone and Start

```bash
# Clone the repository
git clone https://github.com/your-username/finstream.git
cd finstream

# Copy environment file
cp .env.example .env

# Start all services
make up

# Or without Make:
docker compose up -d
```

### 2. Wait for Services

Services take about 30-60 seconds to fully initialize:

```bash
# Watch logs
make logs

# Or check specific service
docker logs finstream-market-simulator -f
```

### 3. Access the Application

| Service | URL | Description |
|---------|-----|-------------|
| **Dashboard** | http://localhost:3000 | Main UI - market overview & alerts |
| **API Gateway** | http://localhost:8000 | REST API endpoints |
| **Redpanda Console** | http://localhost:8080 | Kafka topic browser |
| **Grafana** | http://localhost:3001 | Metrics dashboards (admin/admin) |
| **Prometheus** | http://localhost:9090 | Metrics & alerts |
| **Jaeger** | http://localhost:16686 | Distributed tracing |

### 4. Verify Everything Works

```bash
# Check API health
curl http://localhost:8000/health

# Get market summary
curl http://localhost:8000/api/v1/market-summary

# Get available symbols
curl http://localhost:8000/api/v1/symbols
```

---

## 📖 Usage Guide

### Dashboard Overview

The dashboard at http://localhost:3000 provides:

1. **Market Overview** - Grid of all symbols with current prices and trend indicators
2. **Symbol Detail** - Click any symbol to see detailed charts and recent trades
3. **Alerts Page** - View all generated anomaly alerts

### API Usage Examples

#### Get Latest Quote
```bash
curl http://localhost:8000/api/v1/quotes/AAPL
```

#### Get Recent Trades
```bash
curl "http://localhost:8000/api/v1/trades/AAPL?limit=50"
```

#### Get OHLCV Candles
```bash
curl "http://localhost:8000/api/v1/candles/AAPL?interval=1m&limit=100"
```

#### Get Alerts
```bash
curl "http://localhost:8000/api/v1/alerts?severity=high&limit=20"
```

### WebSocket Streaming

Connect to WebSocket for real-time updates:

```javascript
// Real-time quotes for AAPL
const ws = new WebSocket('ws://localhost:8000/ws/quotes/AAPL');
ws.onmessage = (event) => console.log(JSON.parse(event.data));

// Real-time trades
const wsTrades = new WebSocket('ws://localhost:8000/ws/trades/AAPL');

// Real-time alerts
const wsAlerts = new WebSocket('ws://localhost:8000/ws/alerts');
```

### Kafka Topics

View and inspect messages in Redpanda Console at http://localhost:8080:

| Topic | Description |
|-------|-------------|
| `market.trades` | All trade events |
| `market.quotes` | Bid/ask quote updates |
| `market.candles` | Aggregated OHLCV candles |
| `alerts` | Anomaly detection alerts |

---

## 📡 API Reference

### Health Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Service health check |
| `/ready` | GET | Readiness probe |
| `/metrics` | GET | Prometheus metrics |

### Market Data Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/symbols` | GET | List all available symbols |
| `/api/v1/quotes/{symbol}` | GET | Latest quote for symbol |
| `/api/v1/trades/{symbol}` | GET | Recent trades (limit param) |
| `/api/v1/candles/{symbol}` | GET | OHLCV candles (interval, limit params) |
| `/api/v1/market-summary` | GET | All symbols with latest prices |
| `/api/v1/alerts` | GET | Recent alerts (symbol, severity, limit params) |

### WebSocket Endpoints

| Endpoint | Description |
|----------|-------------|
| `/ws/quotes/{symbol}` | Real-time quotes stream |
| `/ws/trades/{symbol}` | Real-time trades stream |
| `/ws/alerts` | Real-time alerts stream |

---

## 📊 Observability

### Grafana Dashboards

Access Grafana at http://localhost:3001 (admin/admin):

- **FinStream Overview**: Messages/sec, latency, alerts, consumer lag
- Pre-configured datasources for Prometheus, Jaeger, and Loki

### Prometheus Metrics

Each service exports metrics:
- `finstream_messages_processed_total` - Message throughput
- `finstream_processing_latency_seconds` - Processing latency histogram
- `finstream_alerts_total` - Alert counts by type
- Standard Python/FastAPI metrics

### Distributed Tracing

Jaeger at http://localhost:16686 shows:
- Request traces across services
- Latency breakdown per operation
- Error tracking

---

## ☁️ AWS Deployment

### Terraform Infrastructure

The `infrastructure/terraform/` directory contains production-ready AWS infrastructure:

```bash
cd infrastructure/terraform

# Initialize
terraform init

# Plan
terraform plan -var="environment=prod"

# Apply
terraform apply -var="environment=prod"
```

**AWS Resources Created:**
- VPC with public/private subnets
- ECS Fargate cluster
- Application Load Balancer
- Amazon MSK (Kafka)
- Amazon RDS (PostgreSQL/TimescaleDB)
- ElastiCache (Redis)
- ECR repositories

### CI/CD Pipeline

GitHub Actions workflow (`.github/workflows/ci-cd.yml`):

1. **Test** - Run unit tests
2. **Build** - Build Docker images, push to ECR
3. **Deploy** - Rolling deployment to ECS

---

## 🔧 Development

### Local Development

```bash
# Install shared library
pip install -e shared/python-lib

# Run individual service
cd services/market-simulator
python -m app.main

# Run tests
make test

# Lint code
make lint
```

### Configuration

Environment variables (see `.env.example`):

| Variable | Description | Default |
|----------|-------------|---------|
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka brokers | `redpanda:9092` |
| `REDIS_URL` | Redis connection | `redis://redis:6379` |
| `TIMESCALE_URL` | Database connection | `postgresql://...` |
| `SYMBOLS` | Symbols to simulate | `AAPL,GOOGL,...` |
| `TRADES_PER_SECOND` | Generation rate | `100` |

---

## 🔍 Troubleshooting

### Services Keep Restarting

```bash
# Check logs
docker logs finstream-market-simulator
docker logs finstream-api-gateway

# Ensure Redpanda is healthy first
docker logs finstream-redpanda
```

### No Data in Dashboard

1. Wait 30-60 seconds after startup for data generation
2. Check if API returns data: `curl http://localhost:8000/api/v1/market-summary`
3. Verify Kafka topics have messages: http://localhost:8080

### Database Connection Issues

```bash
# Check TimescaleDB
docker logs finstream-timescaledb

# Connect manually
docker exec -it finstream-timescaledb psql -U finstream -d finstream
```

### Memory Issues

The full stack requires ~6-8GB RAM. To reduce memory:

```bash
# Run only infrastructure
make infra-up

# Then selectively start services
docker compose up -d market-simulator api-gateway dashboard
```

---

## 📁 Project Structure

```
finstream/
├── services/
│   ├── market-simulator/     # Data generation service
│   ├── stream-processor/     # Kafka consumer, OHLCV builder
│   ├── alert-service/        # Anomaly detection
│   └── api-gateway/          # REST + WebSocket API
├── dashboard/                 # React frontend
├── shared/python-lib/         # Common utilities (models, config, etc.)
├── infrastructure/
│   ├── terraform/            # AWS infrastructure
│   └── db/                   # Database migrations
├── observability/
│   ├── prometheus/           # Metrics config
│   ├── grafana/              # Dashboards
│   └── loki/                 # Log aggregation
├── docker-compose.yml         # Local development
├── Makefile                   # Convenience commands
└── README.md                  # This file
```

---

## 📝 License

MIT License - feel free to use this as a portfolio project template.

---

## 🙏 Acknowledgments

Built to demonstrate cloud-native microservices architecture patterns for staff-level engineering roles.

**Technologies used:**
- [Redpanda](https://redpanda.com/) - Kafka-compatible streaming
- [TimescaleDB](https://www.timescale.com/) - Time-series database
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python API framework
- [React](https://react.dev/) - Frontend framework
- [Terraform](https://www.terraform.io/) - Infrastructure as Code
