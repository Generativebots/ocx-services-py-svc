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

# Cloud Run injects PORT=8080
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

# Run via run.py (reads PORT from env, starts uvicorn internally)
CMD ["python", "run.py"]
