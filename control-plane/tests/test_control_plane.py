"""Tests for control-plane/aocs_control.py — synchronous only"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from aocs_control import (
    ActionVerdict,
    ActionClass,
    EscrowEvent,
    TriFactorGateResult,
    ToolRegistryEntry,
    IdentityValidator,
    SignalAnalyzer,
    CognitiveValidator,
    AOCSControlPlane,
)


# ─── Helper ────────────────────────────────────────────────────────────────

def _make_event(**overrides) -> EscrowEvent:
    defaults = dict(
        pid=1000, tid=1000, cgroup_id=0, timestamp=123456789,
        tool_id_hash=99999, action_class=1, tenant_id=1,
        binary_hash=12345678, trust_level=65, reversibility_index=5,
        required_entitlements=0, present_entitlements=0x1F,
        entitlement_valid=1, data_size=1024, verdict=0,
    )
    defaults.update(overrides)
    return EscrowEvent(**defaults)


def _run(coro):
    """Helper to run async and return result."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─── Enums ─────────────────────────────────────────────────────────────────

class TestEnums:
    def test_action_verdict_values(self):
        assert ActionVerdict.ALLOW == 0
        assert ActionVerdict.BLOCK == 1
        assert ActionVerdict.HOLD == 2

    def test_action_class_values(self):
        assert ActionClass.CLASS_A == 0
        assert ActionClass.CLASS_B == 1


# ─── IdentityValidator ─────────────────────────────────────────────────────

class TestIdentityValidator:
    def test_high_trust_passes(self):
        v = IdentityValidator()
        result = _run(v.verify(pid=1, binary_hash=123, tenant_id=1,
                                trust_level=80, entitlements=0x01))
        assert result["passed"] is True

    def test_low_trust_fails(self):
        v = IdentityValidator()
        result = _run(v.verify(pid=1, binary_hash=123, tenant_id=1,
                                trust_level=30, entitlements=0x01))
        assert result["passed"] is False

    def test_zero_binary_hash_fails(self):
        v = IdentityValidator()
        result = _run(v.verify(pid=1, binary_hash=0, tenant_id=1,
                                trust_level=80, entitlements=0x01))
        assert result["spiffe_verified"] is False

    def test_zero_entitlements_fails(self):
        v = IdentityValidator()
        result = _run(v.verify(pid=1, binary_hash=123, tenant_id=1,
                                trust_level=80, entitlements=0))
        assert result["entitlement_valid"] is False


# ─── AOCSControlPlane Basic ────────────────────────────────────────────────

class TestAOCSControlPlane:
    def test_register_tool(self):
        cp = AOCSControlPlane()
        entry = ToolRegistryEntry(
            tool_id="payment-tool", tool_id_hash=12345, action_class=1,
            reversibility_index=5, min_reputation_score=50,
            governance_tax_mult=100, required_entitlements=0x1F, hitl_required=1,
        )
        cp.register_tool(entry)
        assert 12345 in cp.tool_registry
        assert cp.tool_registry[12345].tool_id == "payment-tool"

    def test_add_event_handler(self):
        cp = AOCSControlPlane()
        handler = AsyncMock()
        cp.add_event_handler(handler)
        assert handler in cp._event_handlers

    def test_get_tool_id_known(self):
        cp = AOCSControlPlane()
        entry = ToolRegistryEntry(
            tool_id="my-tool", tool_id_hash=111, action_class=0,
            reversibility_index=100, min_reputation_score=0,
            governance_tax_mult=100, required_entitlements=0, hitl_required=0,
        )
        cp.register_tool(entry)
        assert cp._get_tool_id(111) == "my-tool"

    def test_get_tool_id_unknown(self):
        cp = AOCSControlPlane()
        assert cp._get_tool_id(999).startswith("unknown-")

    def test_entitlements_to_list(self):
        cp = AOCSControlPlane()
        ents = cp._entitlements_to_list(0x03)  # data:read + data:write
        assert "data:read" in ents
        assert "data:write" in ents
        assert "data:delete" not in ents

    def test_entitlements_full_bitmask(self):
        cp = AOCSControlPlane()
        ents = cp._entitlements_to_list(0x7F)  # all 7 bits
        assert len(ents) == 7

    def test_entitlements_zero(self):
        cp = AOCSControlPlane()
        assert cp._entitlements_to_list(0) == []

    def test_start_stop(self):
        cp = AOCSControlPlane()
        _run(cp.start())
        assert cp._running is True
        _run(cp.stop())
        assert cp._running is False

    def test_process_escrow_event_all_pass(self):
        identity = AsyncMock()
        identity.verify = AsyncMock(return_value={"passed": True, "mfaa_verified": True,
                                                    "spiffe_verified": True, "reputation_score": 0.8,
                                                    "entitlement_valid": True, "reason": "ok"})
        signal = AsyncMock()
        signal.analyze = AsyncMock(return_value={"passed": True, "entropy_verdict": "CLEAN",
                                                   "jitter_verdict": "NORMAL", "risk_factors": [],
                                                   "reason": "ok"})
        cognitive = AsyncMock()
        cognitive.audit = AsyncMock(return_value={"passed": True, "verdict": "ALLOW",
                                                    "trust_level": 0.9, "violations": 0,
                                                    "anomaly_detected": False, "reason": "clean"})

        cp = AOCSControlPlane(identity, signal, cognitive)
        result = _run(cp.process_escrow_event(_make_event()))
        assert result.all_passed is True
        assert result.final_verdict == ActionVerdict.ALLOW

    def test_process_escrow_event_identity_fails(self):
        identity = AsyncMock()
        identity.verify = AsyncMock(return_value={"passed": False, "reason": "bad identity"})
        signal = AsyncMock()
        signal.analyze = AsyncMock(return_value={"passed": True, "reason": "ok"})
        cognitive = AsyncMock()
        cognitive.audit = AsyncMock(return_value={"passed": True, "verdict": "ALLOW",
                                                    "trust_level": 0.8, "reason": "ok"})

        cp = AOCSControlPlane(identity, signal, cognitive)
        result = _run(cp.process_escrow_event(_make_event()))
        assert result.final_verdict == ActionVerdict.BLOCK
        assert result.identity_passed is False

    def test_process_escrow_event_cognitive_hold(self):
        identity = AsyncMock()
        identity.verify = AsyncMock(return_value={"passed": True, "reason": "ok"})
        signal = AsyncMock()
        signal.analyze = AsyncMock(return_value={"passed": True, "reason": "ok"})
        cognitive = AsyncMock()
        cognitive.audit = AsyncMock(return_value={"passed": False, "verdict": "HOLD",
                                                    "trust_level": 0.5, "reason": "needs review"})

        cp = AOCSControlPlane(identity, signal, cognitive)
        result = _run(cp.process_escrow_event(_make_event()))
        assert result.final_verdict == ActionVerdict.HOLD

    def test_process_escrow_event_cognitive_block(self):
        identity = AsyncMock()
        identity.verify = AsyncMock(return_value={"passed": True, "reason": "ok"})
        signal = AsyncMock()
        signal.analyze = AsyncMock(return_value={"passed": True, "reason": "ok"})
        cognitive = AsyncMock()
        cognitive.audit = AsyncMock(return_value={"passed": False, "verdict": "BLOCK",
                                                    "trust_level": 0.3, "reason": "blocked"})

        cp = AOCSControlPlane(identity, signal, cognitive)
        result = _run(cp.process_escrow_event(_make_event()))
        assert result.final_verdict == ActionVerdict.BLOCK
