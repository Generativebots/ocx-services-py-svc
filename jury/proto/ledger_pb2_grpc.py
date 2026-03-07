"""
Hand-written gRPC service stub matching pb/ledger.proto.

Provides:
  - LedgerServiceServicer: Base class for server implementation
  - LedgerServiceStub: Client stub
  - add_LedgerServiceServicer_to_server: Registration function

Replace with real protoc output when proto toolchain is available.
"""

import grpc
import logging
logger = logging.getLogger(__name__)


class LedgerServiceServicer:
    """Base class for LedgerService gRPC service implementation.

    Server should inherit this and override:
      - RecordEntry(request, context) -> LedgerResponse
      - StreamAuditLog(request, context) -> iterator of LedgerEntry
    """

    def RecordEntry(self, request, context) -> None:
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def StreamAuditLog(self, request, context) -> None:
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")


def add_LedgerServiceServicer_to_server(servicer, server) -> None:
    """Register LedgerServiceServicer with a gRPC server."""
    from proto import ledger_pb2

    rpc_method_handlers = {
        "RecordEntry": grpc.unary_unary_rpc_method_handler(
            servicer.RecordEntry,
            request_deserializer=ledger_pb2.LedgerEntry.FromString,
            response_serializer=lambda resp: resp.SerializeToString(),
        ),
        "StreamAuditLog": grpc.unary_stream_rpc_method_handler(
            servicer.StreamAuditLog,
            request_deserializer=ledger_pb2.AuditFilter.FromString,
            response_serializer=lambda resp: resp.SerializeToString(),
        ),
    }
    generic_handler = grpc.method_service_handler(
        "ocx.ledger.v1.LedgerService", rpc_method_handlers
    )
    server.add_generic_rpc_handlers((generic_handler,))


class LedgerServiceStub:
    """Client stub for calling LedgerService."""

    def __init__(self, channel) -> None:
        from proto import ledger_pb2


        self.RecordEntry = channel.unary_unary(
            "/ocx.ledger.v1.LedgerService/RecordEntry",
            request_serializer=lambda req: req.SerializeToString(),
            response_deserializer=ledger_pb2.LedgerResponse.FromString,
        )
        self.StreamAuditLog = channel.unary_stream(
            "/ocx.ledger.v1.LedgerService/StreamAuditLog",
            request_serializer=lambda req: req.SerializeToString(),
            response_deserializer=ledger_pb2.LedgerEntry.FromString,
        )
