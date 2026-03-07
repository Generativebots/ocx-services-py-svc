import logging
logger = logging.getLogger(__name__)
"""
Hand-written Python stub matching pb/traffic_assessment.proto.

Mirrors the proto messages:
  - ExecutionPlan, TrafficMetadata, AssessmentRequest, AssessmentResponse
  - Verdict (with Action enum), ProtocolType enum

Replace with real protoc output when proto toolchain is available.
"""


class ProtocolType:
    """Enum matching proto ProtocolType."""
    PROTOCOL_TYPE_UNSPECIFIED = 0
    PROTOCOL_TYPE_TCP = 1
    PROTOCOL_TYPE_HTTP = 2
    PROTOCOL_TYPE_TLS = 3
    PROTOCOL_TYPE_DNS = 4


class VerdictAction:
    """Enum matching proto Verdict.Action."""
    ACTION_ALLOW = 0
    ACTION_BLOCK = 1
    ACTION_MITIGATE = 2
    ACTION_OBSERVE = 3


class Verdict:
    """Mirrors pb/traffic_assessment.proto Verdict."""

    def __init__(self, action: int = 0) -> None:
        self.action = action

    def SerializeToString(self) -> bytes:
        import json
        return json.dumps({"action": self.action}).encode("utf-8")

    @classmethod
    def FromString(cls, data: bytes) -> "Verdict":
        import json
        d = json.loads(data.decode("utf-8"))
        return cls(action=d.get("action", 0))


class ExecutionPlan:
    """Mirrors pb/traffic_assessment.proto ExecutionPlan."""

    def __init__(
        self,
        plan_id: str = "",
        agent_id: str = "",
        allowed_calls: list = None,
        expected_outcome_hash: str = "",
        manual_review_required: bool = False,
    ):
        self.plan_id = plan_id
        self.agent_id = agent_id
        self.allowed_calls = allowed_calls or []
        self.expected_outcome_hash = expected_outcome_hash
        self.manual_review_required = manual_review_required

    def SerializeToString(self) -> bytes:
        import json
        return json.dumps({
            "plan_id": self.plan_id,
            "agent_id": self.agent_id,
            "allowed_calls": self.allowed_calls,
            "expected_outcome_hash": self.expected_outcome_hash,
            "manual_review_required": self.manual_review_required,
        }).encode("utf-8")

    @classmethod
    def FromString(cls, data: bytes) -> "ExecutionPlan":
        import json
        d = json.loads(data.decode("utf-8"))
        return cls(**d)


class TrafficMetadata:
    """Mirrors pb/traffic_assessment.proto TrafficMetadata."""

    def __init__(
        self,
        pid: int = 0,
        comm: str = "",
        file_descriptor: int = 0,
        source_address: str = "",
        source_port: int = 0,
        destination_address: str = "",
        destination_port: int = 0,
        binary_path: str = "",
        binary_sha256: str = "",
        container_id: str = "",
    ):
        self.pid = pid
        self.comm = comm
        self.file_descriptor = file_descriptor
        self.source_address = source_address
        self.source_port = source_port
        self.destination_address = destination_address
        self.destination_port = destination_port
        self.binary_path = binary_path
        self.binary_sha256 = binary_sha256
        self.container_id = container_id


class AssessmentRequest:
    """Mirrors pb/traffic_assessment.proto AssessmentRequest."""

    def __init__(
        self,
        request_id: str = "",
        sequence_number: int = 0,
        timeout=None,
        captured_at=None,
        metadata: TrafficMetadata = None,
        raw_payload: bytes = b"",
        protocol: int = 0,
    ):
        self.request_id = request_id
        self.sequence_number = sequence_number
        self.timeout = timeout
        self.captured_at = captured_at
        self.metadata = metadata or TrafficMetadata()
        self.raw_payload = raw_payload
        self.protocol = protocol

    def SerializeToString(self) -> bytes:
        import json
        return json.dumps({
            "request_id": self.request_id,
            "sequence_number": self.sequence_number,
            "raw_payload": self.raw_payload.hex() if self.raw_payload else "",
            "protocol": self.protocol,
        }).encode("utf-8")

    @classmethod
    def FromString(cls, data: bytes) -> "AssessmentRequest":
        import json
        d = json.loads(data.decode("utf-8"))
        return cls(
            request_id=d.get("request_id", ""),
            sequence_number=d.get("sequence_number", 0),
            protocol=d.get("protocol", 0),
        )


class AssessmentResponse:
    """Mirrors pb/traffic_assessment.proto AssessmentResponse."""

    def __init__(
        self,
        request_id: str = "",
        verdict: Verdict = None,
        confidence_score: float = 0.0,
        reasoning: str = "",
        metadata: dict = None,
    ):
        self.request_id = request_id
        self.verdict = verdict or Verdict()
        self.confidence_score = confidence_score
        self.reasoning = reasoning
        self.metadata = metadata or {}

    def SerializeToString(self) -> bytes:
        import json
        return json.dumps({
            "request_id": self.request_id,
            "verdict": {"action": self.verdict.action},
            "confidence_score": self.confidence_score,
            "reasoning": self.reasoning,
            "metadata": self.metadata,
        }).encode("utf-8")

    @classmethod
    def FromString(cls, data: bytes) -> "AssessmentResponse":
        import json

        d = json.loads(data.decode("utf-8"))
        v = d.get("verdict", {})
        return cls(
            request_id=d.get("request_id", ""),
            verdict=Verdict(action=v.get("action", 0)),
            confidence_score=d.get("confidence_score", 0.0),
            reasoning=d.get("reasoning", ""),
            metadata=d.get("metadata", {}),
        )
