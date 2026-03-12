"""Tests for proto/escrow_service_impl.py — EscrowServiceImpl and ReputationServiceImpl."""

import sys
import os
import types

# Allow importing proto module
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# --- Mock heavy dependencies before import ---
import unittest.mock as mock

# Mock grpc
_fake_grpc = types.ModuleType("grpc")
_fake_grpc.StatusCode = type("StatusCode", (), {
    "NOT_FOUND": "NOT_FOUND",
    "FAILED_PRECONDITION": "FAILED_PRECONDITION",
    "INVALID_ARGUMENT": "INVALID_ARGUMENT",
})()
sys.modules["grpc"] = _fake_grpc

# Mock governance config — must return real dict, not MagicMock
_fake_gov_mod = mock.MagicMock()
_fake_gov_mod.get_tenant_governance_config = mock.MagicMock(return_value={
    "escrow_sovereign_threshold": 0.90,
    "escrow_trusted_threshold": 0.60,
    "escrow_probation_threshold": 0.30,
})
sys.modules.setdefault("config", mock.MagicMock())
sys.modules["config.governance_config"] = _fake_gov_mod

# --- Mock proto pb2 + pb2_grpc with simple classes ---

_fake_pb2 = types.ModuleType("proto.escrow_pb2")


class EscrowItem:
    def __init__(self, agent_id="", tenant_id="", payload=b"", **kw):
        self.agent_id = agent_id
        self.tenant_id = tenant_id
        self.payload = payload


class EscrowReceipt:
    def __init__(self, escrow_id="", status=""):
        self.escrow_id = escrow_id
        self.status = status


class ReleaseSignal:
    def __init__(self, escrow_id="", jury_approved=False, entropy_safe=False):
        self.escrow_id = escrow_id
        self.jury_approved = jury_approved
        self.entropy_safe = entropy_safe


class ReleaseResponse:
    def __init__(self, success=False, payload=b""):
        self.success = success
        self.payload = payload


class TrustRequest:
    def __init__(self, agent_id="", tenant_id=""):
        self.agent_id = agent_id
        self.tenant_id = tenant_id


class TrustScore:
    def __init__(self, score=0.0, tier=""):
        self.score = score
        self.tier = tier


class TaxLevy:
    def __init__(self, agent_id="", tenant_id="", amount=0.0, reason=""):
        self.agent_id = agent_id
        self.tenant_id = tenant_id
        self.amount = amount
        self.reason = reason


class TaxReceipt:
    def __init__(self, tx_id="", new_balance=0.0):
        self.tx_id = tx_id
        self.new_balance = new_balance


_fake_pb2.EscrowItem = EscrowItem
_fake_pb2.EscrowReceipt = EscrowReceipt
_fake_pb2.ReleaseSignal = ReleaseSignal
_fake_pb2.ReleaseResponse = ReleaseResponse
_fake_pb2.TrustRequest = TrustRequest
_fake_pb2.TrustScore = TrustScore
_fake_pb2.TaxLevy = TaxLevy
_fake_pb2.TaxReceipt = TaxReceipt

_fake_pb2_grpc = types.ModuleType("proto.escrow_pb2_grpc")
_fake_pb2_grpc.EscrowServiceServicer = object
_fake_pb2_grpc.ReputationServiceServicer = object

sys.modules["proto.escrow_pb2"] = _fake_pb2
sys.modules["proto.escrow_pb2_grpc"] = _fake_pb2_grpc

from proto.escrow_service_impl import EscrowServiceImpl, ReputationServiceImpl

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeContext:
    """Stub for gRPC context."""
    def __init__(self):
        self._code = None
        self._details = None
    def set_code(self, code):
        self._code = code
    def set_details(self, details):
        self._details = details


# ---------------------------------------------------------------------------
# EscrowServiceImpl
# ---------------------------------------------------------------------------

class TestEscrowServiceImpl:
    """Tests for EscrowServiceImpl gRPC methods."""

    def setup_method(self):
        self.svc = EscrowServiceImpl()
        self.ctx = _FakeContext()

    def test_submit_prediction(self):
        item = EscrowItem(agent_id="agent-A", tenant_id="t1", payload=b"action-data")
        receipt = self.svc.SubmitPrediction(item, self.ctx)
        assert receipt.status == "HELD"
        assert receipt.escrow_id  # non-empty UUID

    def test_submit_prediction_stored(self):
        item = EscrowItem(agent_id="agent-A", tenant_id="t1", payload=b"data")
        receipt = self.svc.SubmitPrediction(item, self.ctx)
        assert receipt.escrow_id in self.svc._held
        assert receipt.escrow_id in self.svc._receipts

    def test_release_approved(self):
        """Full approval: jury_approved=True AND entropy_safe=True → release."""
        item = EscrowItem(agent_id="agent-A", payload=b"payload-bytes")
        receipt = self.svc.SubmitPrediction(item, self.ctx)

        signal = ReleaseSignal(
            escrow_id=receipt.escrow_id,
            jury_approved=True,
            entropy_safe=True,
        )
        response = self.svc.Release(signal, self.ctx)
        assert response.success is True
        assert response.payload == b"payload-bytes"
        # Item should be removed
        assert receipt.escrow_id not in self.svc._held

    def test_release_jury_rejected(self):
        """Jury rejects → release denied."""
        item = EscrowItem(agent_id="agent-A", payload=b"data")
        receipt = self.svc.SubmitPrediction(item, self.ctx)

        signal = ReleaseSignal(
            escrow_id=receipt.escrow_id,
            jury_approved=False,
            entropy_safe=True,
        )
        response = self.svc.Release(signal, self.ctx)
        assert response.success is False
        # Item should still be held
        assert receipt.escrow_id in self.svc._held

    def test_release_entropy_unsafe(self):
        """Entropy unsafe → release denied."""
        item = EscrowItem(agent_id="agent-A", payload=b"data")
        receipt = self.svc.SubmitPrediction(item, self.ctx)

        signal = ReleaseSignal(
            escrow_id=receipt.escrow_id,
            jury_approved=True,
            entropy_safe=False,
        )
        response = self.svc.Release(signal, self.ctx)
        assert response.success is False

    def test_release_not_found(self):
        """Release non-existent escrow → NOT_FOUND."""
        signal = ReleaseSignal(escrow_id="nonexistent-id", jury_approved=True, entropy_safe=True)
        response = self.svc.Release(signal, self.ctx)
        assert response.success is False
        assert self.ctx._code == "NOT_FOUND"

    def test_release_updates_receipt_status(self):
        item = EscrowItem(agent_id="agent-A", payload=b"data")
        receipt = self.svc.SubmitPrediction(item, self.ctx)
        eid = receipt.escrow_id

        signal = ReleaseSignal(escrow_id=eid, jury_approved=True, entropy_safe=True)
        self.svc.Release(signal, self.ctx)
        assert self.svc._receipts[eid].status == "RELEASED"


# ---------------------------------------------------------------------------
# ReputationServiceImpl
# ---------------------------------------------------------------------------

class TestReputationServiceImpl:
    """Tests for ReputationServiceImpl gRPC methods."""

    def setup_method(self):
        self.svc = ReputationServiceImpl()
        self.ctx = _FakeContext()

    def test_get_trust_score_default(self):
        """New agent should get default score 0.50."""
        req = TrustRequest(agent_id="new-agent", tenant_id="t1")
        result = self.svc.GetTrustScore(req, self.ctx)
        assert result.score == 0.50

    def test_get_trust_score_sovereign(self):
        self.svc.set_score("t1", "agent-A", 0.95)
        req = TrustRequest(agent_id="agent-A", tenant_id="t1")
        result = self.svc.GetTrustScore(req, self.ctx)
        assert result.tier == "SOVEREIGN"
        assert result.score == 0.95

    def test_get_trust_score_trusted(self):
        self.svc.set_score("t1", "agent-B", 0.70)
        req = TrustRequest(agent_id="agent-B", tenant_id="t1")
        result = self.svc.GetTrustScore(req, self.ctx)
        assert result.tier == "TRUSTED"

    def test_get_trust_score_probation(self):
        self.svc.set_score("t1", "agent-C", 0.45)
        req = TrustRequest(agent_id="agent-C", tenant_id="t1")
        result = self.svc.GetTrustScore(req, self.ctx)
        assert result.tier == "PROBATION"

    def test_get_trust_score_quarantined(self):
        self.svc.set_score("t1", "agent-D", 0.20)
        req = TrustRequest(agent_id="agent-D", tenant_id="t1")
        result = self.svc.GetTrustScore(req, self.ctx)
        assert result.tier == "QUARANTINED"

    def test_levy_tax_success(self):
        req = TaxLevy(agent_id="agent-A", tenant_id="t1", amount=10.0, reason="action-cost")
        result = self.svc.LevyTax(req, self.ctx)
        assert result.tx_id  # non-empty
        assert result.new_balance == 90.0  # 100 - 10

    def test_levy_tax_insufficient_balance(self):
        req = TaxLevy(agent_id="agent-A", tenant_id="t1", amount=200.0, reason="big-spend")
        result = self.svc.LevyTax(req, self.ctx)
        assert result.tx_id == ""
        assert self.ctx._code == "FAILED_PRECONDITION"

    def test_levy_tax_cumulative(self):
        """Multiple levies reduce balance cumulatively."""
        req1 = TaxLevy(agent_id="agent-A", tenant_id="t1", amount=30.0, reason="r1")
        r1 = self.svc.LevyTax(req1, self.ctx)
        assert r1.new_balance == 70.0

        req2 = TaxLevy(agent_id="agent-A", tenant_id="t1", amount=50.0, reason="r2")
        r2 = self.svc.LevyTax(req2, self.ctx)
        assert r2.new_balance == 20.0

    def test_set_score_clamps(self):
        """set_score should clamp to [0.0, 1.0]."""
        self.svc.set_score("t1", "agent", 1.5)
        assert self.svc._scores["t1:agent"] == 1.0

        self.svc.set_score("t1", "agent", -0.5)
        assert self.svc._scores["t1:agent"] == 0.0

    def test_load_tier_thresholds(self):
        thresholds = self.svc._load_tier_thresholds("t1")
        assert "sovereign" in thresholds
        assert "trusted" in thresholds
        assert "probation" in thresholds
