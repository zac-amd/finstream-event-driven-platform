FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy shared library first
COPY shared/python-lib /shared/python-lib
RUN pip install --no-cache-dir /shared/python-lib

# Copy service requirements and install
COPY services/market-data-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY services/market-data-service/app ./app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8002/health')" || exit 1

EXPOSE 8002

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002", "--reload"]
