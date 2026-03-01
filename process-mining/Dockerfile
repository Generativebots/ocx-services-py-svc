# Process Mining — FastAPI service for Cloud Run
FROM python:3.11-slim

# Set working directory
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
ENV LOG_LEVEL="INFO"

EXPOSE 8080

CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT}
