import logging
logger = logging.getLogger(__name__)
"""
Hand-written Python stub matching pb/escrow.proto.

Mirrors the proto messages:
  - EscrowItem, EscrowReceipt, ReleaseSignal, ReleaseResponse
  - TrustRequest, TrustScore, TaxLevy, TaxReceipt

Replace with real protoc output when proto toolchain is available.
"""


class EscrowItem:
    """Mirrors pb/escrow.proto EscrowItem."""

    def __init__(
        self,
        turn_id: str = "",
        tenant_id: str = "",
        agent_id: str = "",
        payload: bytes = b"",
        target_hash: str = "",
    ):
        self.turn_id = turn_id
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.payload = payload
        self.target_hash = target_hash

    def SerializeToString(self) -> bytes:
        import json
        return json.dumps({
            "turn_id": self.turn_id,
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "payload": self.payload.hex() if self.payload else "",
            "target_hash": self.target_hash,
        }).encode("utf-8")

    @classmethod
    def FromString(cls, data: bytes) -> "EscrowItem":
        import json
        d = json.loads(data.decode("utf-8"))
        return cls(
            turn_id=d.get("turn_id", ""),
            tenant_id=d.get("tenant_id", ""),
            agent_id=d.get("agent_id", ""),
            payload=bytes.fromhex(d.get("payload", "")),
            target_hash=d.get("target_hash", ""),
        )


class EscrowReceipt:
    """Mirrors pb/escrow.proto EscrowReceipt."""

    def __init__(self, escrow_id: str = "", status: str = "") -> None:
        self.escrow_id = escrow_id
        self.status = status

    def SerializeToString(self) -> bytes:
        import json
        return json.dumps({
            "escrow_id": self.escrow_id,
            "status": self.status,
        }).encode("utf-8")

    @classmethod
    def FromString(cls, data: bytes) -> "EscrowReceipt":
        import json
        d = json.loads(data.decode("utf-8"))
        return cls(**d)


class ReleaseSignal:
    """Mirrors pb/escrow.proto ReleaseSignal."""

    def __init__(
        self,
        escrow_id: str = "",
        tenant_id: str = "",
        jury_approved: bool = False,
        entropy_safe: bool = False,
    ):
        self.escrow_id = escrow_id
        self.tenant_id = tenant_id
        self.jury_approved = jury_approved
        self.entropy_safe = entropy_safe


class ReleaseResponse:
    """Mirrors pb/escrow.proto ReleaseResponse."""

    def __init__(self, success: bool = False, payload: bytes = b"") -> None:
        self.success = success
        self.payload = payload


class TrustRequest:
    """Mirrors pb/escrow.proto TrustRequest."""

    def __init__(self, agent_id: str = "", tenant_id: str = "") -> None:
        self.agent_id = agent_id
        self.tenant_id = tenant_id


class TrustScore:
    """Mirrors pb/escrow.proto TrustScore."""

    def __init__(self, score: float = 0.0, tier: str = "") -> None:
        self.score = score
        self.tier = tier

    def SerializeToString(self) -> bytes:
        import json
        return json.dumps({"score": self.score, "tier": self.tier}).encode("utf-8")


class TaxLevy:
    """Mirrors pb/escrow.proto TaxLevy."""

    def __init__(
        self,
        agent_id: str = "",
        tenant_id: str = "",
        amount: float = 0.0,
        reason: str = "",
    ):
        self.agent_id = agent_id
        self.tenant_id = tenant_id
        self.amount = amount
        self.reason = reason


class TaxReceipt:
    """Mirrors pb/escrow.proto TaxReceipt."""

    def __init__(self, tx_id: str = "", new_balance: float = 0.0) -> None:
        self.tx_id = tx_id
        self.new_balance = new_balance

    def SerializeToString(self) -> bytes:
        import json

        return json.dumps({
            "tx_id": self.tx_id,
            "new_balance": self.new_balance,
        }).encode("utf-8")
