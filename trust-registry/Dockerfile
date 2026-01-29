FROM python:3.9-slim

WORKDIR /app

RUN pip install --no-cache-dir grpcio grpcio-tools protobuf

COPY . .

# Mock entrypoint since the python file might renamed or specific
CMD ["python", "grpc_handshake.py"] 
# Assuming grpc_handshake.py or similar is the main entry. 
# Re-checking implementation plan... "HandshakeClient: Python Orchestrator... services/trust-registry/grpc_handshake.py"
