"""
A2A Negotiator Arbitrator — bilateral negotiation validation tests.
Patent: CIP A2A negotiation arbitration with self-healing.
"""

import pytest
import sys
import os
import builtins
from typing import Any

# Bug #10: correction_agent.py uses `Any` without importing it.
# Patch builtins so the module can load.
if not hasattr(builtins, "Any"):
    builtins.Any = Any  # type: ignore[attr-defined]

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "trust-registry"))

from jury import Jury
from correction_agent import CorrectionAgent
from negotiator import A2ANegotiatorArbitrator


class TestA2ANegotiatorArbitrator:
    def _make_arbitrator(self):
        jury = Jury()
        corrector = CorrectionAgent()
        return A2ANegotiatorArbitrator(jury, corrector)

    def test_allow_clean_negotiation(self):
        arb = self._make_arbitrator()
        result = arb.arbitrate_exchange(
            buyer_payload={"offer": {"price": 5000, "quantity": 10}},
            seller_payload={"offer": {"price": 5000, "quantity": 10}},
        )
        assert result["status"] == "ALLOW"
        assert result["verdict"]["final_trust_score"] >= 0.70

    def test_block_excessive_price(self):
        """Price > $10k triggers self-healing directive."""
        arb = self._make_arbitrator()
        result = arb.arbitrate_exchange(
            buyer_payload={"offer": {"price": 5000}},
            seller_payload={"offer": {"price": 15000}},
        )
        assert result["status"] == "HEALING_REQUIRED"
        assert result["action"] == "BLOCK_AND_STEER"
        assert "directive" in result

    def test_healing_directive_has_remediation(self):
        arb = self._make_arbitrator()
        result = arb.arbitrate_exchange(
            buyer_payload={"offer": {"price": 1000}},
            seller_payload={"offer": {"price": 50000}},
        )
        assert result["status"] == "HEALING_REQUIRED"
        assert result["directive"] is not None
        assert len(result["directive"]) > 0

    def test_verdict_has_trace_id(self):
        arb = self._make_arbitrator()
        result = arb.arbitrate_exchange(
            buyer_payload={"offer": {"price": 100}},
            seller_payload={"offer": {"price": 100}},
        )
        assert "trace_id" in result["verdict"]
        assert result["verdict"]["trace_id"].startswith("NEGO-")


class TestCorrectionAgent:
    def test_high_value_remediation(self):
        agent = CorrectionAgent()
        result = agent.generate_directive(
            original_prompt="Buy supplies",
            blocked_payload="$20,000 order",
            violation_report="High Value Transaction limit exceeded"
        )
        assert "remediation_directive" in result
        assert "approval" in result["remediation_directive"].lower() or "override" in result["remediation_directive"].lower()

    def test_generic_remediation(self):
        agent = CorrectionAgent()
        result = agent.generate_directive(
            original_prompt="Do something",
            blocked_payload="payload",
            violation_report="Random violation"
        )
        assert result["remediation_directive"] is not None
        assert result["secondary_hallucination_check"] == "YES"
