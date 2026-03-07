"""
Hand-written gRPC service stub matching pb/traffic_assessment.proto.

Provides:
  - TrafficAssessorServicer: Base class for server implementation
  - TrafficAssessorStub: Client stub
  - add_TrafficAssessorServicer_to_server: Registration function

Replace with real protoc output when proto toolchain is available.
"""

import grpc
import logging
logger = logging.getLogger(__name__)


class TrafficAssessorServicer:
    """Base class for TrafficAssessor gRPC service implementation.

    Server should inherit this and override:
      - InspectTraffic(request_iterator, context) -> iterator of AssessmentResponse
      - SubmitPlan(request, context) -> Verdict
    """

    def InspectTraffic(self, request_iterator, context) -> None:
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def SubmitPlan(self, request, context) -> None:
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")


def add_TrafficAssessorServicer_to_server(servicer, server) -> None:
    """Register TrafficAssessorServicer with a gRPC server."""
    from proto import traffic_assessment_pb2

    rpc_method_handlers = {
        "InspectTraffic": grpc.stream_stream_rpc_method_handler(
            servicer.InspectTraffic,
            request_deserializer=traffic_assessment_pb2.AssessmentRequest.FromString,
            response_serializer=lambda resp: resp.SerializeToString(),
        ),
        "SubmitPlan": grpc.unary_unary_rpc_method_handler(
            servicer.SubmitPlan,
            request_deserializer=traffic_assessment_pb2.ExecutionPlan.FromString,
            response_serializer=lambda resp: resp.SerializeToString(),
        ),
    }
    generic_handler = grpc.method_service_handler(
        "governance.v1.TrafficAssessor", rpc_method_handlers
    )
    server.add_generic_rpc_handlers((generic_handler,))


class TrafficAssessorStub:
    """Client stub for calling TrafficAssessor service."""

    def __init__(self, channel) -> None:
        from proto import traffic_assessment_pb2


        self.InspectTraffic = channel.stream_stream(
            "/governance.v1.TrafficAssessor/InspectTraffic",
            request_serializer=lambda req: req.SerializeToString(),
            response_deserializer=traffic_assessment_pb2.AssessmentResponse.FromString,
        )
        self.SubmitPlan = channel.unary_unary(
            "/governance.v1.TrafficAssessor/SubmitPlan",
            request_serializer=lambda req: req.SerializeToString(),
            response_deserializer=traffic_assessment_pb2.Verdict.FromString,
        )
