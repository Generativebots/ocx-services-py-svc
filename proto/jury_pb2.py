import logging
logger = logging.getLogger(__name__)
"""
Hand-written Python stub matching pb/jury/jury.proto.

Mirrors the proto messages exactly:
  - AuditRequest: transaction_id, agent_id, tool_name, parameters, context, raw_payload
  - AuditResponse: transaction_id, verdict, confidence, reason, audit_time

Replace with real protoc output when proto toolchain is available.
"""


class AuditRequest:
    """Mirrors pb/jury/jury.proto AuditRequest."""

    def __init__(
        self,
        transaction_id: str = "",
        agent_id: str = "",
        tool_name: str = "",
        parameters: dict = None,
        context: dict = None,
        raw_payload: bytes = b"",
    ):
        self.transaction_id = transaction_id
        self.agent_id = agent_id
        self.tool_name = tool_name
        self.parameters = parameters or {}
        self.context = context or {}
        self.raw_payload = raw_payload

    def SerializeToString(self) -> bytes:
        """Serialize for gRPC transport (simplified JSON wire format)."""
        import json
        return json.dumps({
            "transaction_id": self.transaction_id,
            "agent_id": self.agent_id,
            "tool_name": self.tool_name,
            "parameters": self.parameters,
            "context": self.context,
            "raw_payload": self.raw_payload.hex() if self.raw_payload else "",
        }).encode("utf-8")

    @classmethod
    def FromString(cls, data: bytes) -> "AuditRequest":
        """Deserialize from gRPC transport."""
        import json
        d = json.loads(data.decode("utf-8"))
        return cls(
            transaction_id=d.get("transaction_id", ""),
            agent_id=d.get("agent_id", ""),
            tool_name=d.get("tool_name", ""),
            parameters=d.get("parameters", {}),
            context=d.get("context", {}),
            raw_payload=bytes.fromhex(d.get("raw_payload", "")),
        )


class AuditResponse:
    """Mirrors pb/jury/jury.proto AuditResponse."""

    def __init__(
        self,
        transaction_id: str = "",
        verdict: str = "",
        confidence: float = 0.0,
        reason: str = "",
        audit_time: float = 0.0,
    ):
        self.transaction_id = transaction_id
        self.verdict = verdict
        self.confidence = confidence
        self.reason = reason
        self.audit_time = audit_time

    def SerializeToString(self) -> bytes:
        import json
        return json.dumps({
            "transaction_id": self.transaction_id,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "reason": self.reason,
            "audit_time": self.audit_time,
        }).encode("utf-8")

    @classmethod
    def FromString(cls, data: bytes) -> "AuditResponse":
        import json

        d = json.loads(data.decode("utf-8"))
        return cls(
            transaction_id=d.get("transaction_id", ""),
            verdict=d.get("verdict", ""),
            confidence=d.get("confidence", 0.0),
            reason=d.get("reason", ""),
            audit_time=d.get("audit_time", 0.0),
        )
