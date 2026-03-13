"""
Trust Registry — Orchestrator + Jury unit tests.

Tests the governance orchestration pipeline and Jury scoring.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestJury:
    """Jury consensus scoring tests."""

    def test_jury_score_structure(self):
        from jury import Jury

        j = Jury()
        result = j.score(
            payload={"proposed_action": "SEND_EMAIL"},
            agent_metadata={"agent_id": "agent-1", "tenant_id": "t-1"},
            rules_context="Standard rules apply.",
        )
        assert "trust_score" in result
        assert "breakdown" in result
        assert "reasoning" in result
        assert "status" in result

    def test_jury_deterministic_score(self):
        """Jury scoring is computed from payload/metadata, not hardcoded."""
        from jury import Jury

        j = Jury()
        # Low-risk action with no context → compliance=0.85, factuality=0.50, strategic=0.70
        result = j.score(
            payload={"proposed_action": "read_data"},
            agent_metadata={"agent_id": "x", "tenant_id": "t-1"},
            rules_context="",
        )
        assert result["trust_score"] > 0.5
        assert result["status"] == "APPROVED"

        # High-risk action → compliance drops to 0.40
        result_risky = j.score(
            payload={"proposed_action": "delete_all_records"},
            agent_metadata={"agent_id": "x", "tenant_id": "t-1"},
            rules_context="",
        )
        assert result_risky["trust_score"] < result["trust_score"]

    def test_jury_breakdown_keys(self):
        from jury import Jury

        j = Jury()
        result = j.score(
            payload={"proposed_action": "X"},
            agent_metadata={"agent_id": "x", "tenant_id": "t-1"},
            rules_context="",
        )
        bd = result["breakdown"]
        assert "compliance" in bd
        assert "factuality" in bd
        assert "strategic_alignment" in bd
        # All scores should be valid floats between 0 and 1
        for key in ["compliance", "factuality", "strategic_alignment"]:
            assert 0.0 <= bd[key] <= 1.0


class TestOrchestrator:
    """Orchestrator pipeline tests."""

    def test_orchestrator_approved(self):
        from orchestrator import ocx_governance_orchestrator
        from jury import Jury
        from ledger import Ledger

        result = ocx_governance_orchestrator(
            payload={"proposed_action": "SEND_EMAIL", "context": {"to": "a", "subject": "b", "body": "c"}},
            agent_metadata={"agent_id": "agent-1", "tenant_id": "t-1"},
            business_rules="Allow all.",
            components={"jury": Jury(), "ledger": Ledger()},
        )
        assert result["status"] == "APPROVED"
        assert 0.0 < result["trust_score"] <= 1.0

    def test_orchestrator_kill_switch_blocks(self):
        """If jury returns score < 0.3, orchestrator blocks."""
        from orchestrator import ocx_governance_orchestrator
        from ledger import Ledger

        # Create a mock jury that returns a very low score
        class LowScoreJury:
            def score(self, **kwargs):
                return {
                    "trust_score": 0.1,
                    "breakdown": {"compliance": 0.1, "factuality": 0.1, "strategic_alignment": 0.1},
                    "reasoning": "Very low trust",
                    "status": "BLOCKED",
                }

        result = ocx_governance_orchestrator(
            payload={"proposed_action": "HACK_SYSTEM"},
            agent_metadata={"agent_id": "bad-agent", "tenant_id": "t-1"},
            business_rules="Strict mode.",
            components={"jury": LowScoreJury(), "ledger": Ledger()},
        )
        assert result["status"] == "BLOCKED"
        assert "KILL-SWITCH" in result["reasoning"]

    def test_orchestrator_records_to_ledger(self):
        """Orchestrator writes to ledger."""
        from orchestrator import ocx_governance_orchestrator
        from jury import Jury
        from ledger import Ledger

        ledger = Ledger()
        ocx_governance_orchestrator(
            payload={"proposed_action": "READ"},
            agent_metadata={"agent_id": "a-1", "tenant_id": "t-1"},
            business_rules="Ok.",
            components={"jury": Jury(), "ledger": ledger},
        )
        recent = ledger.get_recent_transactions("t-1")
        assert len(recent) == 1
        assert recent[0]["agent_id"] == "a-1"

    def test_orchestrator_no_ledger(self):
        """Orchestrator works without ledger (ledger=None)."""
        from orchestrator import ocx_governance_orchestrator
        from jury import Jury

        result = ocx_governance_orchestrator(
            payload={"proposed_action": "WRITE", "context": {"table": "logs", "action": "insert", "scope": "tenant"}},
            agent_metadata={"agent_id": "a-2", "tenant_id": "t-2"},
            business_rules="Ok.",
            components={"jury": Jury(), "ledger": None},
        )
        assert result["status"] == "APPROVED"


class TestLedgerUnit:
    """Ledger direct unit tests."""

    def test_record_returns_tx_id(self):
        from ledger import Ledger

        ledger = Ledger()
        tx_id = ledger.record({"tenant_id": "t-1", "agent_id": "a-1", "status": "APPROVED"})
        assert tx_id.startswith("tx_")

    def test_tenant_isolation(self):
        """Different tenants see different entries."""
        from ledger import Ledger

        ledger = Ledger()
        ledger.record({"tenant_id": "t-1", "status": "APPROVED"})
        ledger.record({"tenant_id": "t-2", "status": "BLOCKED"})

        t1 = ledger.get_recent_transactions("t-1")
        t2 = ledger.get_recent_transactions("t-2")
        assert len(t1) == 1
        assert len(t2) == 1

    def test_daily_stats(self):
        from ledger import Ledger

        ledger = Ledger()
        ledger.record({"tenant_id": "t-1", "status": "APPROVED"})
        ledger.record({"tenant_id": "t-1", "status": "BLOCKED"})
        ledger.record({"tenant_id": "t-1", "status": "APPROVED_WITH_WARNING"})

        stats = ledger.get_daily_stats("t-1")
        assert stats["total_evaluations"] == 3
        assert stats["approved"] == 1
        assert stats["blocked"] == 1
        assert stats["warnings"] == 1

    def test_weekly_drift_insufficient_data(self):
        from ledger import Ledger

        ledger = Ledger()
        drift = ledger.check_weekly_drift("a-1", "t-1")
        assert drift["status"] == "INSUFFICIENT_DATA"

    def test_weekly_drift_stable(self):
        from ledger import Ledger

        ledger = Ledger()
        ledger.record({"tenant_id": "t-1", "agent_id": "a-1", "trust_score": 0.8})
        ledger.record({"tenant_id": "t-1", "agent_id": "a-1", "trust_score": 0.82})

        drift = ledger.check_weekly_drift("a-1", "t-1")
        assert drift["status"] == "STABLE"
        assert drift["drift"] == pytest.approx(0.02, abs=0.001)

    def test_weekly_drift_alert(self):
        from ledger import Ledger

        ledger = Ledger()
        ledger.record({"tenant_id": "t-1", "agent_id": "a-1", "trust_score": 0.8})
        ledger.record({"tenant_id": "t-1", "agent_id": "a-1", "trust_score": 0.5})

        drift = ledger.check_weekly_drift("a-1", "t-1")
        assert drift["status"] == "ALERT"
        assert drift["drift"] < -0.15
