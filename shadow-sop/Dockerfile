# =============================================================================
# OCX Shadow-SOP Service — Dockerfile
# =============================================================================
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Runtime configuration
ENV PORT=8080 \
    PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["python", "run.py"]
