# Ledger — FastAPI Regulator API for Cloud Run
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Cloud Run injects PORT env var; default to 8000
ENV PORT=8000
ENV PYTHONUNBUFFERED=1

# Run the Regulator API (FastAPI) via uvicorn
CMD exec uvicorn regulator_api:app --host 0.0.0.0 --port ${PORT}
