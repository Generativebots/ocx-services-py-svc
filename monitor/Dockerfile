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

# Cloud Run injects PORT=8080
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL="INFO"

EXPOSE 8080

# No run.py — use uvicorn directly with main:app
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT}
