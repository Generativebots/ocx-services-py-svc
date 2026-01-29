# Use an optimized Python base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for networking and build tools
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
ENV REDIS_URL="redis://policy-registry:6379"
ENV vLLM_URL="http://ape-engine:8000/v1"
ENV LOG_LEVEL="INFO"

# Run the entrypoint script
CMD ["python", "main.py"]
