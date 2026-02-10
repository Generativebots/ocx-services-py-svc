# Jury — gRPC service for Cloud Run
FROM python:3.11-slim

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Cloud Run injects PORT env var; Jury uses it for gRPC
# Cloud Run default is 8080, but we set 8000 for consistency
ENV PORT=8000
ENV PYTHONUNBUFFERED=1

# Run the gRPC server via run.py (reads PORT from env)
CMD ["python", "run.py", "--port", "8000"]
