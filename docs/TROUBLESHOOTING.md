# FinStream Troubleshooting Guide

> **Common Issues and Solutions for Developers**

This guide covers common issues you may encounter while developing or running FinStream, along with their solutions.

---

## Table of Contents

1. [Quick Diagnostics](#quick-diagnostics)
2. [Startup Issues](#startup-issues)
3. [Service-Specific Issues](#service-specific-issues)
4. [Database Issues](#database-issues)
5. [Network & Proxy Issues](#network--proxy-issues)
6. [Authentication Issues](#authentication-issues)
7. [Performance Issues](#performance-issues)
8. [Observability Stack Issues](#observability-stack-issues)
9. [Development Environment Issues](#development-environment-issues)
10. [Useful Commands Reference](#useful-commands-reference)

---

## Quick Diagnostics

### Check All Services Status

```bash
cd ~/finstream
docker compose ps
```

**Expected output:**
```
NAME                        STATUS    PORTS
finstream-api-gateway       running   0.0.0.0:8000->8080/tcp
finstream-dashboard         running   0.0.0.0:3000->80/tcp
finstream-portfolio         running   0.0.0.0:8003->8003/tcp
finstream-market-data       running   0.0.0.0:8002->8002/tcp
finstream-redpanda          healthy   ...
finstream-redis             healthy   ...
finstream-timescaledb       healthy   ...
```

### Check Service Logs

```bash
# All logs
docker compose logs -f

# Specific service
docker compose logs -f api-gateway

# Last 100 lines
docker compose logs --tail=100 portfolio-service
```

### Verify Service Health

```bash
# API Gateway
curl http://localhost:8000/health

# Portfolio Service
curl http://localhost:8003/health

# Market Data Service
curl http://localhost:8002/health
```

---

## Startup Issues

### Issue: "Port already in use"

**Symptoms:**
```
Error: listen tcp :8000: bind: address already in use
```

**Solution:**
```bash
# Find process using the port
lsof -i :8000

# Kill the process
kill -9 <PID>

# Or use different port in docker-compose.yml
```

**Alternative - Stop all containers:**
```bash
docker compose down
docker stop $(docker ps -q)
```

---

### Issue: Container fails to start - "host not found in upstream"

**Symptoms:**
```
nginx: [emerg] host not found in upstream "portfolio-service" in /etc/nginx/conf.d/default.conf:13
```

**Solution:**
This occurs when nginx starts before backend services are ready.

1. Update `nginx.conf` with dynamic DNS resolution:
```nginx
resolver 127.0.0.11 valid=30s ipv6=off;

location /api/v1/auth/ {
    set $upstream http://portfolio-service:8003;
    proxy_pass $upstream/api/v1/auth/;
}
```

2. Rebuild dashboard:
```bash
docker compose build dashboard
docker compose up -d dashboard
```

---

### Issue: Database connection failed

**Symptoms:**
```
asyncpg.exceptions.CannotConnectNowError: cannot connect to server
```

**Solution:**

1. Check if TimescaleDB is running:
```bash
docker compose ps timescaledb
```

2. Wait for health check:
```bash
docker compose logs -f timescaledb
# Look for: "database system is ready to accept connections"
```

3. Restart dependent services:
```bash
docker compose restart api-gateway portfolio-service
```

---

### Issue: Redpanda/Kafka not ready

**Symptoms:**
```
KafkaException: Failed to create consumer
```

**Solution:**

1. Check Redpanda health:
```bash
docker exec finstream-redpanda rpk cluster health
```

2. Wait for Redpanda to be healthy:
```bash
docker compose logs -f redpanda
# Look for: "Successfully started Redpanda!"
```

3. Create topics manually if needed:
```bash
docker exec finstream-redpanda rpk topic create trades quotes alerts
```

---

## Service-Specific Issues

### API Gateway Issues

#### Issue: Market summary returns empty

**Symptoms:**
```json
{"summary": []}
```

**Cause:** No data in TimescaleDB candles table.

**Solution:**
1. Start the market simulator:
```bash
docker compose --profile simulator up -d market-simulator
```

2. Or manually insert test data:
```bash
docker exec finstream-timescaledb psql -U finstream -d finstream -c "
INSERT INTO candles (timestamp, symbol, interval, open, high, low, close, volume)
VALUES (NOW(), 'AAPL', '1m', 150, 151, 149, 150.5, 10000);
"
```

---

### Portfolio Service Issues

#### Issue: "Could not get price for SYMBOL"

**Symptoms:**
```json
{"detail": "Could not get price for AAPL"}
```

**Cause:** Market data service is down or Yahoo Finance is unreachable.

**Solution:**
1. Check market-data-service:
```bash
docker compose logs market-data-service
curl http://localhost:8002/api/v1/yahoo/quote/AAPL
```

2. Restart market-data-service:
```bash
docker compose restart market-data-service
```

---

#### Issue: "Insufficient funds" when buying

**Symptoms:**
```json
{"detail": "Insufficient funds for this purchase"}
```

**Solution:**
Check your portfolio cash balance. You cannot buy more than you have.

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
     http://localhost:8003/api/v1/portfolios/YOUR_PORTFOLIO_ID/summary
```

---

### Dashboard Issues

#### Issue: Dashboard shows "No market data available"

**Causes & Solutions:**

| Cause | Solution |
|-------|----------|
| Nginx not routing correctly | Check nginx.conf routes |
| API gateway down | `docker compose up -d api-gateway` |
| No data in database | Start market simulator |
| Browser cache | Hard refresh (Ctrl+Shift+R) |

**Debug steps:**
```bash
# Test from dashboard nginx
curl http://localhost:3000/api/v1/market-summary

# Test directly from API gateway
curl http://localhost:8000/api/v1/market-summary
```

---

#### Issue: Login not working

**Symptoms:** Login button does nothing, or always returns error.

**Solutions:**

1. Check portfolio-service logs:
```bash
docker compose logs portfolio-service | grep -i error
```

2. Test auth endpoint directly:
```bash
curl -X POST http://localhost:8003/api/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email": "test@example.com", "password": "password123"}'
```

3. Check if users table exists:
```bash
docker exec finstream-timescaledb psql -U finstream -d finstream -c "\dt users"
```

---

## Database Issues

### Issue: Tables don't exist

**Symptoms:**
```
relation "users" does not exist
```

**Solution:**
Re-initialize the database:
```bash
docker compose down -v
docker volume rm finstream-timescaledb-data
docker compose up -d timescaledb
# Wait for init.sql to run
docker compose up -d
```

---

### Issue: Can't connect to database from host

**Solution:**
```bash
# Connect via Docker
docker exec -it finstream-timescaledb psql -U finstream -d finstream

# Or use port 5432
psql -h localhost -U finstream -d finstream
```

---

### Issue: Database migrations needed

If schema changes are required:
```bash
# Connect to database
docker exec -it finstream-timescaledb psql -U finstream -d finstream

# Run SQL commands manually
\i /path/to/migration.sql
```

---

## Network & Proxy Issues

### Issue: CORS errors in browser

**Symptoms:**
```
Access to fetch at 'http://localhost:8000' from origin 'http://localhost:3000' 
has been blocked by CORS policy
```

**Solution:**
CORS is configured in FastAPI services. Check that middleware is present:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

### Issue: WebSocket connection fails

**Symptoms:**
```
WebSocket connection to 'ws://localhost:3000/ws/...' failed
```

**Solutions:**

1. Check nginx WebSocket configuration:
```nginx
location /ws/ {
    proxy_pass http://api-gateway:8080/ws/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

2. Rebuild dashboard after changes:
```bash
docker compose build dashboard
docker compose up -d dashboard
```

---

## Authentication Issues

### Issue: "Invalid token" error

**Causes:**

| Cause | Solution |
|-------|----------|
| Token expired | Login again (tokens last 30 min) |
| Wrong token type | Use access_token, not refresh_token |
| JWT secret mismatch | Check JWT_SECRET env var |

---

### Issue: Token not being sent

**Check browser DevTools:**
1. Network tab → Request Headers
2. Should see: `Authorization: Bearer <token>`

**If missing:**
Check frontend authStore.ts is setting header correctly.

---

## Performance Issues

### Issue: Slow API responses

**Diagnostics:**
1. Check database queries:
```sql
-- Enable slow query log
ALTER SYSTEM SET log_min_duration_statement = 100;
SELECT pg_reload_conf();
```

2. Check connection pool:
```bash
docker exec finstream-timescaledb psql -U finstream -d finstream -c "
SELECT count(*) FROM pg_stat_activity WHERE datname = 'finstream';
"
```

**Solutions:**
- Increase pool size in service config
- Add database indexes
- Check for N+1 queries

---

### Issue: High memory usage

**Check container stats:**
```bash
docker stats
```

**Solutions:**
```yaml
# In docker-compose.yml, add memory limits:
services:
  api-gateway:
    deploy:
      resources:
        limits:
          memory: 512M
```

---

## Observability Stack Issues

### Issue: Grafana won't start

**Check logs:**
```bash
docker compose logs grafana
```

**Common fix - permissions:**
```bash
sudo chown -R 472:472 observability/grafana/
```

---

### Issue: No metrics in Prometheus

1. Check targets: http://localhost:9090/targets
2. Verify services expose /metrics endpoint
3. Check prometheus.yml scrape configs

---

### Issue: Loki returns 404

**Expected:** Loki has no web UI at root path.

**Valid endpoints:**
- `http://localhost:3100/ready`
- `http://localhost:3100/loki/api/v1/labels`

---

## Docker-Specific Issues

### Issue: "ERROR: 1 error(s) decoding docker-compose.yml"

**Symptoms:**
```
yaml: line 45: did not find expected key
```

**Solution:**
```bash
# Validate YAML syntax
docker compose config

# Check for tab characters (use spaces only)
cat -A docker-compose.yml | grep -n $'\t'

# Use 2-space indentation consistently
```

---

### Issue: Container exits immediately (Exit Code 1)

**Diagnostics:**
```bash
# Check exit code
docker compose ps -a

# View last logs before exit
docker compose logs --tail=50 api-gateway
```

**Common causes:**

| Exit Code | Meaning | Solution |
|-----------|---------|----------|
| 0 | Normal exit | Check if CMD is correct |
| 1 | Application error | Check logs for exception |
| 137 | OOM killed | Increase memory limit |
| 139 | Segmentation fault | Check native dependencies |
| 143 | SIGTERM received | Container was stopped |

---

### Issue: "no matching manifest" or platform mismatch

**Symptoms (Apple Silicon/ARM):**
```
no matching manifest for linux/arm64/v8
```

**Solution:**
```bash
# Force AMD64 platform
docker compose build --build-arg TARGETPLATFORM=linux/amd64

# Or in docker-compose.yml:
services:
  api-gateway:
    platform: linux/amd64
```

---

### Issue: Volume mount permissions

**Symptoms:**
```
PermissionError: [Errno 13] Permission denied: '/app/data'
```

**Solution (Linux):**
```bash
# Fix ownership
sudo chown -R $USER:$USER ./data

# Or run container as current user
services:
  api-gateway:
    user: "${UID}:${GID}"
```

**Solution (SELinux):**
```bash
# Add :z or :Z to volume mount
volumes:
  - ./data:/app/data:z
```

---

### Issue: Docker network connectivity between containers

**Diagnostics:**
```bash
# List networks
docker network ls

# Inspect network
docker network inspect finstream_default

# Test connectivity from inside container
docker exec finstream-api-gateway ping timescaledb
docker exec finstream-api-gateway nslookup timescaledb
```

**Solution if DNS not working:**
```bash
# Recreate network
docker compose down
docker network prune -f
docker compose up -d
```

---

### Issue: "Cannot connect to the Docker daemon"

**Symptoms:**
```
Cannot connect to the Docker daemon at unix:///var/run/docker.sock
```

**Solution:**
```bash
# Linux - Start Docker service
sudo systemctl start docker
sudo systemctl enable docker

# Add user to docker group (logout required)
sudo usermod -aG docker $USER

# macOS/Windows - Start Docker Desktop application
```

---

### Issue: Docker build fails with "COPY failed"

**Symptoms:**
```
COPY failed: file not found in build context
```

**Solutions:**

1. Check `.dockerignore` isn't excluding needed files:
```bash
cat .dockerignore
```

2. Verify file exists:
```bash
ls -la path/to/file
```

3. Ensure build context is correct:
```bash
# Build from correct directory
docker build -f services/api-gateway/Dockerfile -t api-gateway .
```

---

### Issue: Image won't rebuild with changes

**Solution:**
```bash
# Force rebuild without cache
docker compose build --no-cache api-gateway

# Remove dangling images
docker image prune -f

# Full rebuild
docker compose down
docker compose build --no-cache
docker compose up -d
```

---

### Issue: "Bind for 0.0.0.0:3000 failed: port is already allocated"

**Solution:**
```bash
# Find what's using the port
# Linux/macOS:
lsof -i :3000
netstat -tulpn | grep 3000

# Windows:
netstat -ano | findstr :3000

# Kill the process or change port in docker-compose.yml
```

---

### Issue: Container can't reach external network

**Symptoms:**
```
Could not resolve host: api.example.com
```

**Solution:**
```bash
# Check DNS configuration
docker exec finstream-api-gateway cat /etc/resolv.conf

# Test external connectivity
docker exec finstream-api-gateway curl -v https://google.com

# Fix by adding DNS to docker-compose.yml:
services:
  api-gateway:
    dns:
      - 8.8.8.8
      - 8.8.4.4
```

---

### Issue: Slow Docker performance (macOS/Windows)

**Solutions:**

1. **Use delegated/cached mounts:**
```yaml
volumes:
  - ./app:/app:delegated
```

2. **Exclude node_modules from mounts:**
```yaml
volumes:
  - ./dashboard:/app
  - /app/node_modules  # Anonymous volume
```

3. **Increase Docker Desktop resources:**
   - Open Docker Desktop → Settings → Resources
   - Increase CPU, Memory, Disk

---

### Issue: "no space left on device"

**Solution:**
```bash
# Check Docker disk usage
docker system df

# Clean up everything unused
docker system prune -af --volumes

# Remove specific resources
docker image prune -af      # Remove unused images
docker volume prune -f      # Remove unused volumes
docker container prune -f   # Remove stopped containers
docker builder prune -af    # Remove build cache
```

---

### Issue: Health check keeps failing

**Diagnostics:**
```bash
# Check health status
docker inspect --format='{{.State.Health}}' finstream-timescaledb

# View health check logs
docker inspect --format='{{range .State.Health.Log}}{{.Output}}{{end}}' finstream-timescaledb
```

**Solution:**
Adjust health check timing in docker-compose.yml:
```yaml
healthcheck:
  test: ["CMD", "pg_isready", "-U", "finstream"]
  interval: 10s
  timeout: 5s
  retries: 10
  start_period: 30s  # Give more time to start
```

---

### Issue: Container stuck in "Restarting" loop

**Diagnostics:**
```bash
# Check logs
docker compose logs api-gateway

# Check restart policy
docker inspect --format='{{.HostConfig.RestartPolicy}}' finstream-api-gateway
```

**Solution:**
```bash
# Stop the loop
docker compose stop api-gateway

# Fix the underlying issue (check logs)

# Start again
docker compose up -d api-gateway
```

---

### Docker Compose Best Practices

**1. Use explicit service dependencies:**
```yaml
services:
  api-gateway:
    depends_on:
      timescaledb:
        condition: service_healthy
      redis:
        condition: service_healthy
```

**2. Set resource limits:**
```yaml
services:
  api-gateway:
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 512M
        reservations:
          memory: 256M
```

**3. Use .env file for configuration:**
```bash
# .env
POSTGRES_PASSWORD=secret
JWT_SECRET=your-secret-key

# docker-compose.yml
environment:
  - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
```

**4. Named volumes for persistence:**
```yaml
volumes:
  timescaledb-data:
    name: finstream-timescaledb-data
```

---

## Development Environment Issues

### Issue: node_modules missing

```bash
cd dashboard
npm install
```

---

### Issue: Python dependencies missing

```bash
pip install -r requirements.txt
```

---

### Issue: Can't build Docker images

**Check Docker daemon:**
```bash
docker info
```

**Clear build cache:**
```bash
docker builder prune -f
docker compose build --no-cache
```

---

## Useful Commands Reference

### Container Management

```bash
# Start all services
docker compose up -d

# Stop all services
docker compose down

# Restart specific service
docker compose restart api-gateway

# Rebuild and restart
docker compose up -d --build api-gateway

# View logs
docker compose logs -f --tail=100 api-gateway
```

### Database Commands

```bash
# Connect to PostgreSQL
docker exec -it finstream-timescaledb psql -U finstream -d finstream

# List tables
\dt

# Describe table
\d users

# Run query
SELECT * FROM users LIMIT 5;
```

### Redpanda/Kafka Commands

```bash
# List topics
docker exec finstream-redpanda rpk topic list

# Consume messages
docker exec finstream-redpanda rpk topic consume trades --num 10

# Create topic
docker exec finstream-redpanda rpk topic create my-topic
```

### Cleanup Commands

```bash
# Remove all containers and volumes
docker compose down -v

# Remove all Docker resources
docker system prune -af

# Remove specific volume
docker volume rm finstream-timescaledb-data
```

---

## Getting Help

If your issue isn't covered here:

1. **Check service logs** for error details
2. **Search GitHub Issues** for similar problems
3. **Check Swagger docs** at `/docs` endpoint
4. **Open a GitHub Issue** with:
   - Error message
   - Steps to reproduce
   - Docker compose logs
   - Environment details

---

# JWT
```bash
# 1. Register a new user
curl -X POST http://localhost:8003/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","username":"trader1","password":"password123"}'

# 2. Login to get JWT token
curl -X POST http://localhost:8003/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password123"}'
# Save the access_token from response

# 3. Get your portfolios
curl http://localhost:8003/api/v1/portfolios \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

# 4. Buy 10 shares of AAPL
curl -X POST http://localhost:8003/api/v1/portfolios/PORTFOLIO_ID/buy \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"symbol":"AAPL","quantity":10}'

# 5. Get portfolio summary with P&L
curl http://localhost:8003/api/v1/portfolios/PORTFOLIO_ID/summary \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

# API Endpoints
# Get quote for any symbol
curl http://localhost:8002/api/v1/yahoo/quote/TSLA

# See tracked symbols
curl http://localhost:8002/api/v1/yahoo/symbols

# Add AMD to watchlist
curl -X POST http://localhost:8002/api/v1/yahoo/symbols/AMD

# Cached prices
curl http://localhost:8002/api/v1/yahoo/prices

# 1. Check service status
docker ps --format "table {{.Names}}\t{{.Status}}"

# 2. Check market-simulator logs
docker logs finstream-market-simulator --tail 50

# 3. Check stream-processor logs  
docker logs finstream-stream-processor --tail 50

# 4. Test API directly
curl http://localhost:8000/api/v1/market-summary


```

# Make
```bash
cd ~/finstream
make down
make build
make up
```

*Last updated: February 2026*
