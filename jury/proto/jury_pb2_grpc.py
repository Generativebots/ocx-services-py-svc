"""
Hand-written gRPC service stub matching pb/jury/jury.proto.

Provides:
  - JuryAuditorServicer: Base class for server implementation
  - JuryAuditorStub: Client stub for calling the service
  - add_JuryAuditorServicer_to_server: Registration function

Replace with real protoc output when proto toolchain is available.
"""

import grpc
import logging
logger = logging.getLogger(__name__)


# ============================================================================
# Server-side: Servicer base class
# ============================================================================


class JuryAuditorServicer:
    """Base class for JuryAuditor gRPC service implementation.

    Server should inherit this and override:
      - AuditIntent(request, context) -> AuditResponse
      - StreamAudit(request_iterator, context) -> iterator of AuditResponse
    """

    def AuditIntent(self, request, context) -> None:
        """Single audit request."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def StreamAudit(self, request_iterator, context) -> None:
        """Streaming audit for batch processing."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")


# ============================================================================
# Server registration
# ============================================================================


def _audit_intent_handler(servicer, request_deserializer, response_serializer) -> None:
    """Create unary-unary handler for AuditIntent."""
    def handler(request, context) -> Any:
        return servicer.AuditIntent(request, context)
    return handler


def _stream_audit_handler(servicer, request_deserializer, response_serializer) -> None:
    """Create stream-stream handler for StreamAudit."""
    def handler(request_iterator, context) -> Any:
        return servicer.StreamAudit(request_iterator, context)
    return handler


def add_JuryAuditorServicer_to_server(servicer, server) -> None:
    """Register JuryAuditorServicer with a gRPC server.

    This wires:
      /ocx.jury.JuryAuditor/AuditIntent  -> servicer.AuditIntent
      /ocx.jury.JuryAuditor/StreamAudit  -> servicer.StreamAudit
    """
    from proto import jury_pb2

    rpc_method_handlers = {
        "AuditIntent": grpc.unary_unary_rpc_method_handler(
            servicer.AuditIntent,
            request_deserializer=jury_pb2.AuditRequest.FromString,
            response_serializer=lambda resp: resp.SerializeToString(),
        ),
        "StreamAudit": grpc.stream_stream_rpc_method_handler(
            servicer.StreamAudit,
            request_deserializer=jury_pb2.AuditRequest.FromString,
            response_serializer=lambda resp: resp.SerializeToString(),
        ),
    }
    generic_handler = grpc.method_service_handler(
        "ocx.jury.JuryAuditor", rpc_method_handlers
    )
    server.add_generic_rpc_handlers((generic_handler,))


# ============================================================================
# Client-side: Stub
# ============================================================================


class JuryAuditorStub:
    """Client stub for calling JuryAuditor service."""

    def __init__(self, channel) -> None:
        from proto import jury_pb2


        self.AuditIntent = channel.unary_unary(
            "/ocx.jury.JuryAuditor/AuditIntent",
            request_serializer=lambda req: req.SerializeToString(),
            response_deserializer=jury_pb2.AuditResponse.FromString,
        )
        self.StreamAudit = channel.stream_stream(
            "/ocx.jury.JuryAuditor/StreamAudit",
            request_serializer=lambda req: req.SerializeToString(),
            response_deserializer=jury_pb2.AuditResponse.FromString,
        )
