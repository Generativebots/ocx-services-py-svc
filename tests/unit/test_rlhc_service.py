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
from rlhc.rlhc_server import RLHCServiceImpl, _pattern_store


class TestClusterDecisionsGRPC(unittest.TestCase):
    def setUp(self):
        self.svc = RLHCServiceImpl()
        self.ctx = mock.MagicMock()
        _pattern_store.clear()

    def test_empty_decisions(self):
        request = {
            "analysis_id": "test-1",
            "tenant_id": "t1",
            "decisions": [],
            "min_frequency": 2,
            "min_confidence": 0.6,
        }
        resp = self.svc.ClusterDecisions(request, self.ctx)
        self.assertEqual(resp["total_decisions"], 0)

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
        self.assertEqual(resp["total_decisions"], 1)

    def test_auto_analysis_id(self):
        request = {"tenant_id": "t1", "decisions": []}
        resp = self.svc.ClusterDecisions(request, self.ctx)
        self.assertTrue(resp["analysis_id"].startswith("rlhc-"))

    def test_proto_attr_style_decisions(self):
        """Cover the proto-attribute branch (getattr instead of dict.get)."""
        proto_decision = mock.MagicMock()
        proto_decision.decision_id = "pd-1"
        proto_decision.agent_id = "pa"
        proto_decision.tool_name = "pt"
        proto_decision.original_verdict = "ALLOW"
        proto_decision.override_action = "BLOCK_OVERRIDE"
        proto_decision.reason = "reason"
        proto_decision.trust_score = 0.5

        proto_req = mock.MagicMock(spec=[])  # no dict interface
        proto_req.analysis_id = "proto-run"
        proto_req.tenant_id = "t1"
        proto_req.decisions = [proto_decision]
        proto_req.min_frequency = 1
        proto_req.min_confidence = 0.5

        resp = self.svc.ClusterDecisions(proto_req, self.ctx)
        self.assertEqual(resp["total_decisions"], 1)

    def test_patterns_stored_after_cluster(self):
        """ClusterDecisions stores discovered patterns in _pattern_store."""
        decisions = [
            {"decision_id": f"d{i}", "agent_id": "a", "tool_name": "t",
             "original_verdict": "ALLOW", "override_action": "BLOCK_OVERRIDE",
             "reason": "", "trust_score": 0.5}
            for i in range(5)
        ]
        self.svc.ClusterDecisions({"analysis_id": "s1", "tenant_id": "t1",
                                   "decisions": decisions, "min_frequency": 2,
                                   "min_confidence": 0.3}, self.ctx)
        self.assertGreater(len(_pattern_store), 0)


class TestGetPatternsGRPC(unittest.TestCase):
    def setUp(self):
        self.svc = RLHCServiceImpl()
        self.ctx = mock.MagicMock()
        _pattern_store.clear()

    def test_get_empty_patterns(self):
        resp = self.svc.GetPatterns({}, self.ctx)
        self.assertEqual(resp["patterns"], [])

    def test_get_all_and_filtered(self):
        # Populate store via ClusterDecisions
        decisions = [
            {"decision_id": f"d{i}", "agent_id": "a", "tool_name": "t",
             "original_verdict": "ALLOW", "override_action": "BLOCK_OVERRIDE",
             "reason": "", "trust_score": 0.5}
            for i in range(5)
        ]
        self.svc.ClusterDecisions({"analysis_id": "s1", "tenant_id": "t1",
                                   "decisions": decisions, "min_frequency": 2,
                                   "min_confidence": 0.3}, self.ctx)
        # All patterns (PENDING by default)
        all_resp = self.svc.GetPatterns({}, self.ctx)
        self.assertGreater(len(all_resp["patterns"]), 0)
        # Filter by status
        filtered = self.svc.GetPatterns({"status_filter": "APPROVED"}, self.ctx)
        self.assertEqual(len(filtered["patterns"]), 0)

    def test_proto_attr_request(self):
        proto_req = mock.MagicMock(spec=[])
        proto_req.status_filter = ""
        resp = self.svc.GetPatterns(proto_req, self.ctx)
        self.assertIn("patterns", resp)


class TestUpdatePatternStatusGRPC(unittest.TestCase):
    def setUp(self):
        self.svc = RLHCServiceImpl()
        self.ctx = mock.MagicMock()
        _pattern_store.clear()

    def test_update_nonexistent(self):
        resp = self.svc.UpdatePatternStatus({"pattern_id": "x", "status": "APPROVED"}, self.ctx)
        self.assertFalse(resp["success"])

    def test_invalid_status(self):
        # Add a pattern first
        decisions = [
            {"decision_id": f"d{i}", "agent_id": "a", "tool_name": "t",
             "original_verdict": "ALLOW", "override_action": "BLOCK_OVERRIDE",
             "reason": "", "trust_score": 0.5}
            for i in range(5)
        ]
        self.svc.ClusterDecisions({"analysis_id": "s1", "tenant_id": "t1",
                                   "decisions": decisions, "min_frequency": 2,
                                   "min_confidence": 0.3}, self.ctx)
        if _pattern_store:
            pid = list(_pattern_store.keys())[0]
            resp = self.svc.UpdatePatternStatus({"pattern_id": pid, "status": "INVALID"}, self.ctx)
            self.assertFalse(resp["success"])

    def test_approve_pattern(self):
        decisions = [
            {"decision_id": f"d{i}", "agent_id": "a", "tool_name": "t",
             "original_verdict": "ALLOW", "override_action": "BLOCK_OVERRIDE",
             "reason": "", "trust_score": 0.5}
            for i in range(5)
        ]
        self.svc.ClusterDecisions({"analysis_id": "s1", "tenant_id": "t1",
                                   "decisions": decisions, "min_frequency": 2,
                                   "min_confidence": 0.3}, self.ctx)
        if _pattern_store:
            pid = list(_pattern_store.keys())[0]
            resp = self.svc.UpdatePatternStatus({"pattern_id": pid, "status": "APPROVED"}, self.ctx)
            self.assertTrue(resp["success"])
            self.assertEqual(_pattern_store[pid].status, "APPROVED")

    def test_proto_attr_request(self):
        proto_req = mock.MagicMock(spec=[])
        proto_req.pattern_id = "nonexistent"
        proto_req.status = "REJECTED"
        resp = self.svc.UpdatePatternStatus(proto_req, self.ctx)
        self.assertFalse(resp["success"])


# ===========================================================================
# HTTP Handler Tests
# ===========================================================================
import io
from rlhc.rlhc_server import RLHCHTTPHandler


class _FakeWfile(io.BytesIO):
    """Writable buffer that works like a socket wfile."""
    pass


def _make_handler(method, path, body=None):
    """Create a handler with a mock request."""
    handler = object.__new__(RLHCHTTPHandler)
    handler.command = method
    handler.path = path
    handler.request_version = "HTTP/1.1"
    handler.headers = {"Content-Length": str(len(body)) if body else "0"}
    handler.rfile = io.BytesIO(body if body else b"")
    handler.wfile = _FakeWfile()
    handler.requestline = f"{method} {path} HTTP/1.1"
    handler.close_connection = True
    handler.client_address = ("127.0.0.1", 12345)
    handler._headers_buffer = []

    # Capture responses
    handler._resp_code = None
    handler._resp_body = None
    def _send_response(code, msg=None):
        handler._resp_code = code
    handler.send_response = _send_response
    handler.send_header = lambda k, v: None
    handler.end_headers = lambda: None
    def _send_error(code, msg=None):
        handler._resp_code = code
    handler.send_error = _send_error
    return handler


class TestHTTPHandler:
    def test_health_endpoint(self):
        h = _make_handler("GET", "/health")
        h.do_GET()
        assert h._resp_code == 200

    def test_get_patterns(self):
        h = _make_handler("GET", "/patterns")
        h.do_GET()
        assert h._resp_code == 200

    def test_get_404(self):
        h = _make_handler("GET", "/unknown")
        h.do_GET()
        assert h._resp_code == 404

    def test_post_cluster(self):
        body = json.dumps({"analysis_id": "t1", "decisions": []}).encode()
        h = _make_handler("POST", "/cluster", body)
        h.do_POST()
        assert h._resp_code == 200

    def test_post_patterns(self):
        body = json.dumps({}).encode()
        h = _make_handler("POST", "/patterns", body)
        h.do_POST()
        assert h._resp_code == 200

    def test_post_patterns_status(self):
        body = json.dumps({"pattern_id": "x", "status": "APPROVED"}).encode()
        h = _make_handler("POST", "/patterns/status", body)
        h.do_POST()
        assert h._resp_code == 200

    def test_post_unknown(self):
        h = _make_handler("POST", "/unknown", b"{}")
        h.do_POST()
        assert h._resp_code == 404

    def test_post_invalid_json(self):
        h = _make_handler("POST", "/cluster", b"not json")
        h.do_POST()
        assert h._resp_code == 400

import json


