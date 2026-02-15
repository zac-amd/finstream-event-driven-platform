FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY services/portfolio-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY services/portfolio-service/app ./app

ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
