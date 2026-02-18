# Jury — gRPC service for Cloud Run
FROM python:3.11-slim

WORKDIR /app

# Install build dependencies for grpcio native compilation
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Cloud Run injects PORT=8080; Jury reads JURY_PORT for gRPC
ENV PORT=8080
ENV JURY_PORT=8080
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

# Run the gRPC server via run.py (reads JURY_PORT from env)
CMD ["python", "run.py"]
