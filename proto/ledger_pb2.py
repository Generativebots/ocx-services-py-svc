"""
Hand-written Python stub matching pb/ledger.proto.

Mirrors the proto messages exactly:
  - LedgerEntry: turn_id, agent_id, binary_hash, plan_id, status, intent_hash,
                 actual_hash, actions_taken, timestamp
  - AuditFilter: agent_id
  - LedgerResponse: acknowledged, entry_id

Replace with real protoc output when proto toolchain is available.
"""

from datetime import datetime
import logging
logger = logging.getLogger(__name__)


class LedgerEntry:
    """Mirrors pb/ledger.proto LedgerEntry."""

    # Status enum values matching proto
    COMMITTED = 0
    COMPENSATED = 1
    ABORTED_BY_HUMAN = 2
    SECURITY_VIOLATION = 3

    def __init__(
        self,
        turn_id: str = "",
        agent_id: str = "",
        binary_hash: str = "",
        plan_id: str = "",
        status: int = 0,
        intent_hash: str = "",
        actual_hash: str = "",
        actions_taken: list = None,
        timestamp=None,
    ):
        self.turn_id = turn_id
        self.agent_id = agent_id
        self.binary_hash = binary_hash
        self.plan_id = plan_id
        self.status = status
        self.intent_hash = intent_hash
        self.actual_hash = actual_hash
        self.actions_taken = actions_taken or []
        self.timestamp = timestamp or datetime.utcnow()

    def SerializeToString(self) -> bytes:
        import json
        return json.dumps({
            "turn_id": self.turn_id,
            "agent_id": self.agent_id,
            "binary_hash": self.binary_hash,
            "plan_id": self.plan_id,
            "status": self.status,
            "intent_hash": self.intent_hash,
            "actual_hash": self.actual_hash,
            "actions_taken": self.actions_taken,
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else str(self.timestamp),
        }).encode("utf-8")

    @classmethod
    def FromString(cls, data: bytes) -> "LedgerEntry":
        import json
        d = json.loads(data.decode("utf-8"))
        return cls(**{k: v for k, v in d.items() if k != "timestamp"})


class AuditFilter:
    """Mirrors pb/ledger.proto AuditFilter."""

    def __init__(self, agent_id: str = "") -> None:
        self.agent_id = agent_id

    def SerializeToString(self) -> bytes:
        import json
        return json.dumps({"agent_id": self.agent_id}).encode("utf-8")

    @classmethod
    def FromString(cls, data: bytes) -> "AuditFilter":
        import json
        d = json.loads(data.decode("utf-8"))
        return cls(agent_id=d.get("agent_id", ""))


class LedgerResponse:
    """Mirrors pb/ledger.proto LedgerResponse."""

    def __init__(self, acknowledged: bool = False, entry_id: str = "") -> None:
        self.acknowledged = acknowledged
        self.entry_id = entry_id

    def SerializeToString(self) -> bytes:
        import json
        return json.dumps({
            "acknowledged": self.acknowledged,
            "entry_id": self.entry_id,
        }).encode("utf-8")

    @classmethod
    def FromString(cls, data: bytes) -> "LedgerResponse":
        import json

        d = json.loads(data.decode("utf-8"))
        return cls(
            acknowledged=d.get("acknowledged", False),
            entry_id=d.get("entry_id", ""),
        )
