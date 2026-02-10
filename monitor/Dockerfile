# Monitor — FastAPI + background poller for Cloud Run
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for networking
RUN apt-get update && apt-get install -y \
    gcc \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Environment variables (defaults)
ENV PORT=8000
ENV PYTHONUNBUFFERED=1
ENV REDIS_URL="redis://localhost:6379"
ENV LOG_LEVEL="INFO"

# Run via uvicorn (FastAPI wraps the background monitor thread)
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT}
