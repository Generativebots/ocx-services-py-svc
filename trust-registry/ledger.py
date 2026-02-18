"""
OCX Governance Ledger — Local module for Trust Registry
-------------------------------------------------------
Provides the Ledger class for immutable governance audit logging.
When running inside the trust-registry service, this is a lightweight
in-process wrapper. In production, this would call the Ledger service.
"""
import os
import time
import uuid
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class Ledger:
    """Immutable governance ledger for audit trail."""

    def __init__(self) -> None:
        self._entries: List[Dict[str, Any]] = []
        logger.info("Ledger initialized (in-memory mode)")

    def record(self, entry: Dict[str, Any]) -> str:
        """Record a governance transaction and return its ID."""
        tx_id = f"tx_{uuid.uuid4().hex[:12]}"
        record = {
            "id": tx_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            **entry,
        }
        self._entries.append(record)
        logger.debug("Ledger entry recorded: %s", tx_id)
        return tx_id

    def get_recent_transactions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return the most recent ledger entries."""
        return list(reversed(self._entries[-limit:]))

    def get_daily_stats(self) -> Dict[str, Any]:
        """Return aggregate stats for the current day."""
        total = len(self._entries)
        approved = sum(1 for e in self._entries if e.get("status") == "APPROVED")
        blocked = sum(1 for e in self._entries if e.get("status") == "BLOCKED")
        warned = sum(
            1
            for e in self._entries
            if e.get("status") == "APPROVED_WITH_WARNING"
        )

        return {
            "total_evaluations": total,
            "approved": approved,
            "blocked": blocked,
            "warnings": warned,
            "date": time.strftime("%Y-%m-%d", time.gmtime()),
        }

    def check_weekly_drift(self, agent_id: str) -> Dict[str, Any]:
        """Check trust score drift for an agent over the week."""
        agent_entries = [
            e for e in self._entries if e.get("agent_id") == agent_id
        ]

        if len(agent_entries) < 2:
            return {
                "agent_id": agent_id,
                "drift": 0.0,
                "status": "INSUFFICIENT_DATA",
                "entries_count": len(agent_entries),
            }

        scores = [e.get("trust_score", 0.0) for e in agent_entries if "trust_score" in e]
        if len(scores) >= 2:
            delta = scores[-1] - scores[0]
        else:
            delta = 0.0

        return {
            "agent_id": agent_id,
            "drift": round(delta, 4),
            "status": "ALERT" if delta < -0.15 else "STABLE",
            "entries_count": len(agent_entries),
        }
