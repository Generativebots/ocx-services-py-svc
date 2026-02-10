"""
Hand-written gRPC service stub matching pb/escrow.proto.

Provides:
  - EscrowServiceServicer, ReputationServiceServicer: Base classes
  - add_*_to_server: Registration functions
  - Client stubs

Replace with real protoc output when proto toolchain is available.
"""

import grpc
import logging
logger = logging.getLogger(__name__)


class EscrowServiceServicer:
    """Base class for EscrowService."""

    def SubmitPrediction(self, request, context) -> None:
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        raise NotImplementedError("Method not implemented!")

    def Release(self, request, context) -> None:
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        raise NotImplementedError("Method not implemented!")


class ReputationServiceServicer:
    """Base class for ReputationService."""

    def GetTrustScore(self, request, context) -> None:
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        raise NotImplementedError("Method not implemented!")

    def LevyTax(self, request, context) -> None:
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        raise NotImplementedError("Method not implemented!")


def add_EscrowServiceServicer_to_server(servicer, server) -> None:
    """Register EscrowServiceServicer with a gRPC server."""
    from proto import escrow_pb2

    rpc_method_handlers = {
        "SubmitPrediction": grpc.unary_unary_rpc_method_handler(
            servicer.SubmitPrediction,
            request_deserializer=escrow_pb2.EscrowItem.FromString,
            response_serializer=lambda resp: resp.SerializeToString(),
        ),
        "Release": grpc.unary_unary_rpc_method_handler(
            servicer.Release,
            request_deserializer=escrow_pb2.ReleaseSignal.FromString,
            response_serializer=lambda resp: resp.SerializeToString(),
        ),
    }
    generic_handler = grpc.method_service_handler(
        "escrow.v1.EscrowService", rpc_method_handlers
    )
    server.add_generic_rpc_handlers((generic_handler,))


def add_ReputationServiceServicer_to_server(servicer, server) -> None:
    """Register ReputationServiceServicer with a gRPC server."""
    from proto import escrow_pb2


    rpc_method_handlers = {
        "GetTrustScore": grpc.unary_unary_rpc_method_handler(
            servicer.GetTrustScore,
            request_deserializer=escrow_pb2.TrustRequest.FromString,
            response_serializer=lambda resp: resp.SerializeToString(),
        ),
        "LevyTax": grpc.unary_unary_rpc_method_handler(
            servicer.LevyTax,
            request_deserializer=escrow_pb2.TaxLevy.FromString,
            response_serializer=lambda resp: resp.SerializeToString(),
        ),
    }
    generic_handler = grpc.method_service_handler(
        "escrow.v1.ReputationService", rpc_method_handlers
    )
    server.add_generic_rpc_handlers((generic_handler,))
