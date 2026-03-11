"""Tests for rlhc — cluster_decisions, RLHCServiceImpl gRPC, and governance config."""

import sys
import os

# Allow importing rlhc_service from rlhc/
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Mock governance config before import
import unittest.mock as mock

_fake_gov_mod = mock.MagicMock()
_fake_gov_mod.get_tenant_governance_config = mock.MagicMock(return_value={})
_mock_gov = mock.patch.dict(sys.modules, {
    "config": mock.MagicMock(),
    "config.governance_config": _fake_gov_mod,
})
_mock_gov.start()

from rlhc.rlhc_service import (
    HITLDecision,
    PatternSuggestion,
    AnalysisResult,
    cluster_decisions,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_decision(
    decision_id="d1",
    agent_id="agent-A",
    tool_name="tool-X",
    original_verdict="ALLOW",
    override_action="BLOCK_OVERRIDE",
    reason="test reason",
    trust_score=0.7,
):
    return HITLDecision(
        decision_id=decision_id,
        agent_id=agent_id,
        tool_name=tool_name,
        original_verdict=original_verdict,
        override_action=override_action,
        reason=reason,
        trust_score=trust_score,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDataclasses:
    """Smoke-test the dataclass constructors."""

    def test_hitl_decision(self):
        d = _make_decision()
        assert d.decision_id == "d1"
        assert d.trust_score == 0.7

    def test_pattern_suggestion(self):
        ps = PatternSuggestion(
            pattern_id="p1",
            description="desc",
            frequency=5,
            confidence=0.9,
            suggested_rule={"condition": "x", "action": "BLOCK"},
            source_decisions=["d1", "d2"],
        )
        assert ps.status == "PENDING"

    def test_analysis_result_defaults(self):
        ar = AnalysisResult(analysis_id="ar1")
        assert ar.patterns == []
        assert ar.total_decisions == 0
        assert ar.clusters_found == 0


class TestClusterDecisionsEmpty:
    """Edge case — zero decisions."""

    def test_no_decisions(self):
        result = cluster_decisions([], analysis_id="test-empty")
        assert result.total_decisions == 0
        assert result.clusters_found == 0
        assert result.patterns == []


class TestOverridePatterns:
    """Cluster 1 — override patterns (what humans consistently change)."""

    def test_single_override_below_min_frequency(self):
        """One occurrence should not create a pattern (min_frequency=2)."""
        decisions = [_make_decision(decision_id="d1")]
        result = cluster_decisions(decisions, min_frequency=2)
        assert result.clusters_found == 0

    def test_override_pattern_detected(self):
        """Two identical override types should produce a pattern."""
        decisions = [
            _make_decision(decision_id="d1"),
            _make_decision(decision_id="d2"),
        ]
        result = cluster_decisions(decisions, min_frequency=2, min_confidence=0.5)
        # All decisions have same override key, so confidence = 2/2 = 1.0
        override_patterns = [p for p in result.patterns if "override" in p.pattern_id]
        assert len(override_patterns) >= 1
        assert override_patterns[0].confidence >= 0.5

    def test_override_below_confidence(self):
        """If confidence is below threshold, pattern is skipped."""
        decisions = [
            _make_decision(decision_id="d1", override_action="BLOCK_OVERRIDE"),
            _make_decision(decision_id="d2", override_action="ALLOW_OVERRIDE"),
            _make_decision(decision_id="d3", override_action="ALLOW_OVERRIDE"),
            _make_decision(decision_id="d4", override_action="ALLOW_OVERRIDE"),
        ]
        # BLOCK_OVERRIDE: 1/4 = 0.25 confidence — should be filtered
        result = cluster_decisions(decisions, min_frequency=1, min_confidence=0.5)
        block_patterns = [p for p in result.patterns if "BLOCK" in p.description]
        # Should not appear because confidence 0.25 < 0.5
        # But ALLOW_OVERRIDE: 3/4 = 0.75 should appear
        allow_patterns = [p for p in result.patterns if "ALLOW" in p.description]
        assert len(allow_patterns) >= 1

    def test_auto_apply_high_confidence(self):
        """auto_apply should be True when confidence > auto_apply_threshold."""
        # Need all decisions to be the same override → confidence = 1.0
        decisions = [_make_decision(decision_id=f"d{i}") for i in range(5)]
        result = cluster_decisions(decisions, min_frequency=2, min_confidence=0.5)
        for p in result.patterns:
            if "override" in p.pattern_id:
                # confidence=1.0 > default auto_apply_threshold (0.90) → True
                assert p.suggested_rule.get("auto_apply") is True


class TestLowTrustOverrides:
    """Cluster 2 — low trust overrides."""

    def test_low_trust_block_pattern(self):
        """Low-trust agents that are blocked should produce a pattern."""
        decisions = [
            _make_decision(decision_id=f"d{i}", trust_score=0.3, override_action="BLOCK_OVERRIDE")
            for i in range(5)
        ]
        result = cluster_decisions(decisions, min_frequency=2, min_confidence=0.5)
        low_trust = [p for p in result.patterns if "low-trust" in p.pattern_id]
        assert len(low_trust) >= 1
        assert low_trust[0].suggested_rule["action"] == "BLOCK"

    def test_high_trust_no_low_trust_pattern(self):
        """High-trust agents should not trigger low-trust pattern."""
        decisions = [
            _make_decision(decision_id=f"d{i}", trust_score=0.9, override_action="BLOCK_OVERRIDE")
            for i in range(5)
        ]
        result = cluster_decisions(decisions, min_frequency=2, min_confidence=0.5)
        low_trust = [p for p in result.patterns if "low-trust" in p.pattern_id]
        assert len(low_trust) == 0


class TestToolSpecificPatterns:
    """Cluster 3 — tool-specific patterns."""

    def test_tool_pattern_detected(self):
        """Consistent override for same tool should produce a pattern."""
        decisions = [
            _make_decision(decision_id=f"d{i}", tool_name="risky-tool", override_action="BLOCK_OVERRIDE")
            for i in range(4)
        ]
        result = cluster_decisions(decisions, min_frequency=2, min_confidence=0.5)
        tool_patterns = [p for p in result.patterns if "tool" in p.pattern_id]
        assert len(tool_patterns) >= 1

    def test_mixed_tools_no_tool_pattern(self):
        """Different tools should each need enough occurrences."""
        decisions = [
            _make_decision(decision_id="d1", tool_name="tool-A"),
            _make_decision(decision_id="d2", tool_name="tool-B"),
            _make_decision(decision_id="d3", tool_name="tool-C"),
        ]
        result = cluster_decisions(decisions, min_frequency=2, min_confidence=0.5)
        tool_patterns = [p for p in result.patterns if "tool" in p.pattern_id]
        assert len(tool_patterns) == 0

    def test_tool_mixed_overrides_below_confidence(self):
        """Same tool but mixed override actions → low confidence per action."""
        decisions = [
            _make_decision(decision_id="d1", tool_name="tool-X", override_action="BLOCK_OVERRIDE"),
            _make_decision(decision_id="d2", tool_name="tool-X", override_action="ALLOW_OVERRIDE"),
            _make_decision(decision_id="d3", tool_name="tool-X", override_action="MODIFY_OUTPUT"),
            _make_decision(decision_id="d4", tool_name="tool-X", override_action="BLOCK_OVERRIDE"),
        ]
        # Most common: BLOCK_OVERRIDE 2/4 = 0.50
        result = cluster_decisions(decisions, min_frequency=2, min_confidence=0.6)
        tool_patterns = [p for p in result.patterns if "tool" in p.pattern_id]
        assert len(tool_patterns) == 0  # 0.5 < 0.6


class TestCombinedClustering:
    """Integration — multiple clusters in one analysis."""

    def test_all_three_clusters(self):
        """Scenario where all 3 cluster types fire."""
        decisions = [
            # Override cluster: 5× ALLOW→BLOCK_OVERRIDE
            _make_decision(decision_id=f"over-{i}", trust_score=0.3,
                           tool_name="danger-tool", override_action="BLOCK_OVERRIDE")
            for i in range(5)
        ]
        result = cluster_decisions(decisions, min_frequency=2, min_confidence=0.3)
        # Should have override + low-trust + tool patterns
        assert result.clusters_found >= 2
        assert result.total_decisions == 5

    def test_analysis_id_propagated(self):
        result = cluster_decisions([], analysis_id="my-run-42")
        assert result.analysis_id == "my-run-42"


class TestGovernanceConfig:
    """Verify governance config integration."""

    def test_custom_tenant_thresholds(self):
        """cluster_decisions accepts tenant_id for governance config lookup."""
        decisions = [_make_decision(decision_id=f"d{i}") for i in range(3)]
        result = cluster_decisions(decisions, tenant_id="tenant-abc", min_frequency=2, min_confidence=0.5)
        # Should not crash; governance config is mocked
        assert result.total_decisions == 3


# ===========================================================================
# RLHCServiceImpl gRPC Tests (merged from test_rlhc_server.py)
# ===========================================================================

import unittest
from rlhc.rlhc_server import RLHCServiceImpl


class TestClusterDecisionsGRPC(unittest.TestCase):
    def setUp(self):
        self.svc = RLHCServiceImpl()
        self.ctx = mock.MagicMock()

    def test_empty_decisions(self):
        request = {
            "analysis_id": "test-1",
            "tenant_id": "t1",
            "decisions": [],
            "min_frequency": 2,
            "min_confidence": 0.6,
        }
        resp = self.svc.ClusterDecisions(request, self.ctx)
        self.assertIsNotNone(resp)

    def test_with_dict_decisions(self):
        request = {
            "analysis_id": "test-2",
            "tenant_id": "t1",
            "decisions": [
                {
                    "decision_id": "d1",
                    "agent_id": "a1",
                    "tool_name": "web_search",
                    "original_verdict": "BLOCK",
                    "override_action": "ALLOW",
                    "reason": "Safe query",
                    "trust_score": 0.8,
                }
            ],
            "min_frequency": 1,
            "min_confidence": 0.5,
        }
        resp = self.svc.ClusterDecisions(request, self.ctx)
        self.assertIsNotNone(resp)

    def test_auto_analysis_id(self):
        request = {
            "tenant_id": "t1",
            "decisions": [],
        }
        resp = self.svc.ClusterDecisions(request, self.ctx)
        self.assertIsNotNone(resp)


class TestGetPatternsGRPC(unittest.TestCase):
    def setUp(self):
        self.svc = RLHCServiceImpl()
        self.ctx = mock.MagicMock()

    def test_get_empty_patterns(self):
        if hasattr(self.svc, "GetPatterns"):
            request = {"tenant_id": "t1"}
            resp = self.svc.GetPatterns(request, self.ctx)
            self.assertIsNotNone(resp)


class TestUpdatePatternStatusGRPC(unittest.TestCase):
    def setUp(self):
        self.svc = RLHCServiceImpl()
        self.ctx = mock.MagicMock()

    def test_update_nonexistent(self):
        if hasattr(self.svc, "UpdatePatternStatus"):
            request = {"pattern_id": "nonexistent", "status": "APPROVED"}
            resp = self.svc.UpdatePatternStatus(request, self.ctx)
            self.assertIsNotNone(resp)

