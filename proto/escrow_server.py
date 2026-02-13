"""
Escrow gRPC Server Bootstrap.

Starts the Escrow + Reputation gRPC server on the configured port.
This is the entry point for the Python escrow service container.

Usage:
    python -m proto.escrow_server          # default port 50052
    OCX_ESCROW_PORT=50052 python -m proto.escrow_server
"""

import grpc
import logging
import os
import signal
import sys
from concurrent import futures

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from proto.escrow_pb2_grpc import (
    add_EscrowServiceServicer_to_server,
    add_ReputationServiceServicer_to_server,
)
from proto.escrow_service_impl import EscrowServiceImpl, ReputationServiceImpl

logger = logging.getLogger(__name__)

_DEFAULT_PORT = 50052
_MAX_WORKERS = 10


def serve(port: int = None) -> None:
    """Start the Escrow + Reputation gRPC server."""
    if port is None:
        port = int(os.environ.get("OCX_ESCROW_PORT", _DEFAULT_PORT))

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=_MAX_WORKERS))

    # Register service implementations
    escrow_svc = EscrowServiceImpl()
    reputation_svc = ReputationServiceImpl()

    add_EscrowServiceServicer_to_server(escrow_svc, server)
    add_ReputationServiceServicer_to_server(reputation_svc, server)

    listen_addr = f"[::]:{port}"
    server.add_insecure_port(listen_addr)
    server.start()

    logger.info(f"Escrow gRPC server started on {listen_addr}")
    logger.info(f"  EscrowService    → SubmitPrediction, Release")
    logger.info(f"  ReputationService → GetTrustScore, LevyTax")

    # Graceful shutdown on SIGTERM/SIGINT
    def _shutdown(signum, frame):
        logger.info("Shutting down escrow gRPC server...")
        server.stop(grace=5)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    server.wait_for_termination()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    serve()
