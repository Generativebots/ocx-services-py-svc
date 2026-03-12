"""Tests for proto/escrow_service_impl.py — ReputationServiceImpl._load_tier_thresholds."""
import sys, os, unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))


class TestReputationServiceTierThresholds(unittest.TestCase):
    """Cover _load_tier_thresholds (lines 123-134)."""

    def test_thresholds_returns_all_keys(self):
        from proto.escrow_service_impl import ReputationServiceImpl
        svc = ReputationServiceImpl()
        t = svc._load_tier_thresholds("any")
        assert isinstance(t, dict)
        assert "sovereign" in t and "trusted" in t and "probation" in t

    def test_sovereign_gt_trusted_gt_probation(self):
        from proto.escrow_service_impl import ReputationServiceImpl
        svc = ReputationServiceImpl()
        t = svc._load_tier_thresholds("t1")
        assert t["sovereign"] > t["trusted"] > t["probation"]

    @patch("proto.escrow_service_impl.ReputationServiceImpl._load_tier_thresholds")
    def test_thresholds_called_during_get_trust(self, mock_load):
        """Ensure _load_tier_thresholds is called by GetTrustScore."""
        mock_load.return_value = {"sovereign": 0.85, "trusted": 0.65, "probation": 0.40}

        from proto.escrow_service_impl import ReputationServiceImpl
        from proto.escrow_pb2 import TrustRequest

        svc = ReputationServiceImpl()
        ctx = MagicMock()
        req = TrustRequest(tenant_id="acme", agent_id="agent-1")
        svc.GetTrustScore(req, ctx)
        mock_load.assert_called()

    def test_fallback_when_config_raises(self):
        """When governance_config import fails, fallback defaults are used."""
        from proto.escrow_service_impl import ReputationServiceImpl
        svc = ReputationServiceImpl()

        with patch.dict("sys.modules", {"config.governance_config": None}):
            t = svc._load_tier_thresholds("bad-tenant")
        # Should return valid thresholds regardless
        assert isinstance(t, dict)
        assert len(t) == 3


if __name__ == "__main__":
    unittest.main()
