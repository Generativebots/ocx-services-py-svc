"""Tests for rlhc/rlhc_server.py — RLHCServiceImpl gRPC"""
import sys, os, unittest, uuid
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from rlhc.rlhc_server import RLHCServiceImpl


class TestClusterDecisions(unittest.TestCase):
    def setUp(self):
        self.svc = RLHCServiceImpl()
        self.ctx = MagicMock()

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


class TestGetPatterns(unittest.TestCase):
    def setUp(self):
        self.svc = RLHCServiceImpl()
        self.ctx = MagicMock()

    def test_get_empty_patterns(self):
        if hasattr(self.svc, "GetPatterns"):
            request = {"tenant_id": "t1"}
            resp = self.svc.GetPatterns(request, self.ctx)
            self.assertIsNotNone(resp)


class TestUpdatePatternStatus(unittest.TestCase):
    def setUp(self):
        self.svc = RLHCServiceImpl()
        self.ctx = MagicMock()

    def test_update_nonexistent(self):
        if hasattr(self.svc, "UpdatePatternStatus"):
            request = {"pattern_id": "nonexistent", "status": "APPROVED"}
            resp = self.svc.UpdatePatternStatus(request, self.ctx)
            self.assertIsNotNone(resp)


if __name__ == "__main__":
    unittest.main()
