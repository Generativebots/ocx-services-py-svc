"""Tests for trust-registry jury module — scoring, LLM integration, tenant config."""

import os
import sys
import json
import time
import types
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ============================================================================
# kill_switch.py — missing lines: 50-56 (tenant config import), 155-158
# ============================================================================

class TestJuryScoring:
    """Tests for Jury scoring edge cases covering all branches."""

    def test_high_risk_action_compliance(self):
        """High-risk action keywords → compliance 0.40."""
        from jury import Jury
        j = Jury()
        assert j._compute_compliance_score("DELETE_ALL_DATA", "") == 0.40

    def test_medium_risk_action_compliance(self):
        """Medium-risk action keywords → compliance 0.65."""
        from jury import Jury
        j = Jury()
        assert j._compute_compliance_score("SEND_EMAIL", "") == 0.65

    def test_low_risk_action_compliance(self):
        """Low-risk (default) action → compliance 0.85."""
        from jury import Jury
        j = Jury()
        assert j._compute_compliance_score("VIEW_DASHBOARD", "") == 0.85

    def test_rule_context_blocks_action(self):
        """Rules context containing 'block' + action name → 0.30."""
        from jury import Jury
        j = Jury()
        score = j._compute_compliance_score("view_dashboard", "block view_dashboard")
        assert score == 0.30

    def test_factuality_no_context(self):
        """Empty context → 0.50."""
        from jury import Jury
        j = Jury()
        assert j._compute_factuality_score({"context": {}}) == 0.50

    def test_factuality_no_context_key(self):
        """No 'context' key → 0.50."""
        from jury import Jury
        j = Jury()
        assert j._compute_factuality_score({}) == 0.50

    def test_factuality_few_fields(self):
        """1-2 fields → 0.60."""
        from jury import Jury
        j = Jury()
        assert j._compute_factuality_score({"context": {"a": 1, "b": 2}}) == 0.60

    def test_factuality_medium_fields(self):
        """3-4 fields → 0.75."""
        from jury import Jury
        j = Jury()
        assert j._compute_factuality_score({"context": {"a": 1, "b": 2, "c": 3}}) == 0.75

    def test_factuality_many_fields(self):
        """5+ fields → 0.90."""
        from jury import Jury
        j = Jury()
        assert j._compute_factuality_score(
            {"context": {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5}}
        ) == 0.90

    def test_strategic_critical_tier_read(self):
        """Critical tier + read action → 0.90."""
        from jury import Jury
        j = Jury()
        assert j._compute_strategic_score({"tier": "Critical"}, "read_data") == 0.90

    def test_strategic_critical_tier_non_read(self):
        """Critical tier + non-read → 0.75."""
        from jury import Jury
        j = Jury()
        assert j._compute_strategic_score({"tier": "Critical"}, "write_data") == 0.75

    def test_strategic_standard_tier(self):
        """Standard tier → 0.70."""
        from jury import Jury
        j = Jury()
        assert j._compute_strategic_score({"tier": "Standard"}, "anything") == 0.70

    def test_strategic_unknown_tier(self):
        """Unknown tier → 0.75 (default)."""
        from jury import Jury
        j = Jury()
        assert j._compute_strategic_score({"tier": "Premium"}, "anything") == 0.75




class TestJuryLLMClient:
    """Tests for Jury with LLM client (covers L115-139)."""

    def test_score_with_llm_client_success(self):
        """LLM client returns scores → used directly."""
        from jury import Jury

        mock_llm = MagicMock()
        mock_llm.evaluate.return_value = {
            "compliance": 0.88,
            "factuality": 0.92,
            "strategic_alignment": 0.85,
        }

        j = Jury(llm_client=mock_llm)
        j.model = "gpt-4"  # Force non-default model

        result = j.score(
            payload={"proposed_action": "SEND_EMAIL", "context": {"a": 1}},
            agent_metadata={"agent_id": "a1", "tenant_id": "t1", "tier": "Standard"},
            rules_context="standard rules",
        )
        assert result["trust_score"] == round(0.4 * 0.88 + 0.4 * 0.92 + 0.2 * 0.85, 4)
        assert result["status"] == "APPROVED"

    def test_score_with_llm_client_failure_degrades(self):
        """LLM call throws → falls back to deterministic scoring."""
        from jury import Jury

        mock_llm = MagicMock()
        mock_llm.evaluate.side_effect = RuntimeError("LLM API down")

        j = Jury(llm_client=mock_llm)
        j.model = "gpt-4"

        result = j.score(
            payload={"proposed_action": "READ_DATA", "context": {"a": 1, "b": 2, "c": 3}},
            agent_metadata={"agent_id": "a1", "tenant_id": "t1", "tier": "Standard"},
            rules_context="",
        )
        # Should degrade to deterministic scoring, not crash
        assert "trust_score" in result
        assert result["status"] in ("APPROVED", "BLOCKED")

    def test_score_no_llm_no_default_model(self):
        """No LLM client + non-default model → deterministic fallback."""
        from jury import Jury

        j = Jury()
        j.model = "custom-model"
        j.llm_client = None

        result = j.score(
            payload={"proposed_action": "READ_DATA", "context": {}},
            agent_metadata={"agent_id": "a1", "tenant_id": "t1"},
            rules_context="",
        )
        assert "trust_score" in result




class TestJuryTenantConfigRuntime:
    """Test jury late-binding tenant config (L157-159)."""

    def test_score_loads_tenant_threshold_at_runtime(self):
        """Jury without tenant_id at init loads from metadata tenant_id at score time."""
        from jury import Jury

        j = Jury()  # No tenant_id at init
        j.tenant_id = None  # ensure no init tenant

        result = j.score(
            payload={"proposed_action": "READ_DATA", "context": {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5}},
            agent_metadata={"agent_id": "a1", "tenant_id": "test-tenant-123", "tier": "Standard"},
            rules_context="",
        )
        assert result["status"] in ("APPROVED", "BLOCKED")


# ============================================================================
# ape_engine.py — missing lines: 26-57 (VLLMClient.generate_json),
#                 100-156 (extract_rules endpoint)
# ============================================================================


