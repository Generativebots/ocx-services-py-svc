"""
Ledger gRPC Service — Records and streams audit trail entries.

C1+C2 FIX: Service now inherits from LedgerServiceServicer and registers
with gRPC server. Returns proper LedgerResponse proto objects.
Previously this entire file was commented-out stubs.
"""

import grpc
from concurrent import futures
import sys
import os
import logging
import uuid

# C1+C2 FIX: Import generated protobuf stubs (no longer mocked)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from proto import ledger_pb2
from proto import ledger_pb2_grpc

logger = logging.getLogger(__name__)


class LedgerServicer(ledger_pb2_grpc.LedgerServiceServicer):
    """
    gRPC Ledger service for recording and streaming audit entries.

    C1+C2 FIX: Now inherits from LedgerServiceServicer and implements
    real RecordEntry and StreamAuditLog methods.
    """

    def __init__(self) -> None:
        self.entries = []  # In-memory store; production → Supabase/Spanner
        self.logger = logging.getLogger(__name__)
        self.logger.info("LedgerServicer initialized")

    def RecordEntry(self, request, context) -> Any:
        """
        Record a completed or reverted transaction to the audit ledger.

        C1+C2 FIX: Returns proper LedgerResponse proto instead of `pass`.
        """
        turn_id = getattr(request, 'turn_id', 'unknown')
        agent_id = getattr(request, 'agent_id', 'unknown')
        status = getattr(request, 'status', 0)

        self.logger.info(
            f"[AUDIT] Received Turn {turn_id} for Agent {agent_id}"
        )

        # Detect compensated / reverted turns
        if status == ledger_pb2.LedgerEntry.COMPENSATED:
            intent_hash = getattr(request, 'intent_hash', '')
            actual_hash = getattr(request, 'actual_hash', '')
            self.logger.warning(
                f"⚠️ REVERT LOGGED: Hash Mismatch. "
                f"Intent: {intent_hash[:8]}... Actual: {actual_hash[:8]}..."
            )
        elif status == ledger_pb2.LedgerEntry.SECURITY_VIOLATION:
            self.logger.critical(
                f"🚨 SECURITY VIOLATION logged for Agent {agent_id}"
            )

        # Store entry
        entry_id = f"audit_{uuid.uuid4().hex[:12]}"
        self.entries.append({
            'entry_id': entry_id,
            'turn_id': turn_id,
            'agent_id': agent_id,
            'status': status,
        })

        # C1+C2 FIX: Return proper proto response
        return ledger_pb2.LedgerResponse(
            acknowledged=True,
            entry_id=entry_id,
        )

    def StreamAuditLog(self, request, context) -> None:
        """
        Stream audit log entries filtered by agent_id.
        """
        agent_filter = getattr(request, 'agent_id', '')

        for entry_data in self.entries:
            if not agent_filter or entry_data.get('agent_id') == agent_filter:
                yield ledger_pb2.LedgerEntry(
                    turn_id=entry_data['turn_id'],
                    agent_id=entry_data['agent_id'],
                    status=entry_data.get('status', 0),
                )


def serve(port: int = None) -> None:
    """
    Start Ledger gRPC server.

    C1+C2 FIX: Server now actually starts (previously commented-out).
    """
    if port is None:
        port = int(os.getenv("LEDGER_PORT", "50052"))

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    # C1+C2 FIX: Service registration is no longer commented out
    ledger_pb2_grpc.add_LedgerServiceServicer_to_server(
        LedgerServicer(), server
    )

    server.add_insecure_port(f'[::]:{port}')
    server.start()

    logger.info(f"📒 OCX Ledger Service Active: Listening on port {port}")

    server.wait_for_termination()


if __name__ == '__main__':
    serve()
