"""Tests for shadow-sop/rlhc.py — ShadowSOPRLHC (in-memory class)."""

import sys
import os
import importlib.util
import asyncio

# Allow importing shadow-sop modules
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# --- Mock dependencies ---
import unittest.mock as mock

_fake_gov_mod = mock.MagicMock()
_fake_gov_mod.get_tenant_governance_config = mock.MagicMock(return_value={})
sys.modules.setdefault("config", mock.MagicMock())
sys.modules["config.governance_config"] = _fake_gov_mod
sys.modules.setdefault("psycopg2", mock.MagicMock())
sys.modules.setdefault("psycopg2.pool", mock.MagicMock())
sys.modules.setdefault("psycopg2.extras", mock.MagicMock())
sys.modules.setdefault("fastapi", mock.MagicMock())

# We need fastapi stubs for import
_fake_fastapi = mock.MagicMock()
_fake_fastapi.APIRouter = mock.MagicMock(return_value=mock.MagicMock())
_fake_fastapi.HTTPException = Exception
_fake_fastapi.Depends = mock.MagicMock()
_fake_fastapi.Header = mock.MagicMock(return_value=None)
sys.modules["fastapi"] = _fake_fastapi

_fake_pydantic = mock.MagicMock()
_fake_pydantic.BaseModel = type("BaseModel", (), {})
sys.modules.setdefault("pydantic", _fake_pydantic)

_rlhc_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "rlhc.py",
)
_spec = importlib.util.spec_from_file_location("shadow_sop_rlhc", _rlhc_path)
rlhc_mod = importlib.util.module_from_spec(_spec)
sys.modules["shadow_sop_rlhc"] = rlhc_mod
_spec.loader.exec_module(rlhc_mod)

ShadowSOPRLHC = rlhc_mod.ShadowSOPRLHC
CorrectionType = rlhc_mod.CorrectionType
PolicyStatus = rlhc_mod.PolicyStatus
HumanCorrection = rlhc_mod.HumanCorrection

import pytest

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestInit:
    def test_defaults(self):
        rlhc = ShadowSOPRLHC()
        assert rlhc.total_corrections == 0
        assert rlhc.patterns_generated == 0
        assert rlhc.policies_proposed == 0
        assert rlhc.corrections == {}
        assert rlhc.patterns == {}
        assert rlhc.policies == {}

    def test_custom_thresholds(self):
        rlhc = ShadowSOPRLHC(
            min_corrections_for_pattern=5,
            min_patterns_for_policy=3,
            pattern_similarity_threshold=0.8,
            policy_approval_threshold=0.9,
        )
        assert rlhc.min_corrections_for_pattern == 5
        assert rlhc.pattern_similarity_threshold == 0.8


class TestRecordCorrection:
    def setup_method(self):
        self.rlhc = ShadowSOPRLHC(min_corrections_for_pattern=2)

    def test_single_correction(self):
        result = _run(self.rlhc.record_correction(
            tenant_id="t1",
            agent_id="agent-1",
            correction_type=CorrectionType.BLOCK_OVERRIDE,
            original_action="ALLOW",
            corrected_action="BLOCK",
            tool_id="execute_payment",
            transaction_id="txn-001",
            reviewer_id="human-1",
            reasoning="Payment too large",
            severity="HIGH",
        ))
        assert isinstance(result, HumanCorrection)
        assert result.correction_type == CorrectionType.BLOCK_OVERRIDE
        assert self.rlhc.total_corrections == 1

    def test_multiple_corrections_accumulate(self):
        for i in range(3):
            _run(self.rlhc.record_correction(
                tenant_id="t1",
                agent_id="agent-1",
                correction_type=CorrectionType.ALLOW_OVERRIDE,
                original_action="BLOCK",
                corrected_action="ALLOW",
                tool_id="read_data",
                transaction_id=f"txn-{i}",
                reviewer_id="human-1",
                reasoning="False positive",
            ))
        assert self.rlhc.total_corrections == 3

    def test_per_request_overrides(self):
        result = _run(self.rlhc.record_correction(
            tenant_id="t1",
            agent_id="agent-1",
            correction_type=CorrectionType.MODIFY_OUTPUT,
            original_action="EXECUTE",
            corrected_action="MODIFY",
            tool_id="generate_report",
            transaction_id="txn-ovr",
            reviewer_id="human-2",
            reasoning="Output needed adjustment",
            pattern_similarity_threshold=0.5,
            min_corrections_for_pattern=1,
        ))
        assert result is not None


class TestCorrectionTypes:
    def test_enum_values(self):
        assert CorrectionType.ALLOW_OVERRIDE == "ALLOW_OVERRIDE"
        assert CorrectionType.BLOCK_OVERRIDE == "BLOCK_OVERRIDE"
        assert CorrectionType.MODIFY_OUTPUT == "MODIFY_OUTPUT"
        assert CorrectionType.REJECT_ACTION == "REJECT_ACTION"
        assert CorrectionType.ADD_CONTEXT == "ADD_CONTEXT"
        assert CorrectionType.CORRECT_DATA == "CORRECT_DATA"

    def test_policy_status(self):
        assert PolicyStatus.PROPOSED == "PROPOSED"
        assert PolicyStatus.APPROVED == "APPROVED"
        assert PolicyStatus.REJECTED == "REJECTED"
        assert PolicyStatus.RETIRED == "RETIRED"


class TestSimilarity:
    def setup_method(self):
        self.rlhc = ShadowSOPRLHC()

    def test_same_tool_same_type(self):
        from datetime import datetime, timezone as tz
        c1 = HumanCorrection(
            correction_id="c1", timestamp=datetime.now(tz.utc),
            tenant_id="t1", agent_id="a1",
            correction_type=CorrectionType.BLOCK_OVERRIDE,
            original_action="ALLOW", original_output=None,
            corrected_action="BLOCK", corrected_output=None,
            tool_id="payment", transaction_id="tx1",
            context={}, reviewer_id="r1",
            reviewer_trust_score=1.0, reasoning="test",
            severity="HIGH",
        )
        c2 = HumanCorrection(
            correction_id="c2", timestamp=datetime.now(tz.utc),
            tenant_id="t1", agent_id="a1",
            correction_type=CorrectionType.BLOCK_OVERRIDE,
            original_action="ALLOW", original_output=None,
            corrected_action="BLOCK", corrected_output=None,
            tool_id="payment", transaction_id="tx2",
            context={}, reviewer_id="r1",
            reviewer_trust_score=1.0, reasoning="test",
            severity="HIGH",
        )
        sim = self.rlhc._calculate_similarity(c1, c2)
        assert sim > 0.5  # Same type + same tool + same actions


class TestGetStats:
    def test_initial_stats(self):
        rlhc = ShadowSOPRLHC()
        stats = rlhc.get_stats()
        assert stats["total_corrections"] == 0
        assert stats["patterns_generated"] == 0
        assert stats["policies_proposed"] == 0
        assert stats["policies_approved"] == 0

    def test_stats_after_correction(self):
        rlhc = ShadowSOPRLHC()
        _run(rlhc.record_correction(
            tenant_id="t1", agent_id="a1",
            correction_type=CorrectionType.ALLOW_OVERRIDE,
            original_action="BLOCK", corrected_action="ALLOW",
            tool_id="tool1", transaction_id="tx1",
            reviewer_id="r1", reasoning="ok",
        ))
        stats = rlhc.get_stats()
        assert stats["total_corrections"] == 1


class TestPolicyApproval:
    def test_approve_nonexistent(self):
        rlhc = ShadowSOPRLHC()
        result = rlhc.approve_policy("nonexistent", "admin")
        assert result is None or (isinstance(result, dict) and not result.get("success", True) is True) or result is None

    def test_reject_nonexistent(self):
        rlhc = ShadowSOPRLHC()
        result = rlhc.reject_policy("nonexistent", "admin", "bad idea")
        assert result is None or isinstance(result, (dict, type(None)))


class TestGetPendingPolicies:
    def test_empty_initially(self):
        rlhc = ShadowSOPRLHC()
        pending = rlhc.get_pending_policies()
        assert pending == []

    def test_get_approved_policies(self):
        rlhc = ShadowSOPRLHC()
        approved = rlhc.get_approved_policies()
        assert approved == []


# ---------------------------------------------------------------------------
# Coverage Boost: Pattern Generation
# ---------------------------------------------------------------------------

class TestPatternGeneration:
    """Cover _generate_pattern_from_corrections (lines 319-379)."""

    def setup_method(self):
        self.rlhc = ShadowSOPRLHC(
            min_corrections_for_pattern=2,
            policy_approval_threshold=0.9,
        )

    def _make_correction(self, cid, tool_id="payment", corr_type=CorrectionType.BLOCK_OVERRIDE,
                          orig="ALLOW", corrected="BLOCK", ctx=None):
        from datetime import datetime, timezone as tz
        c = HumanCorrection(
            correction_id=cid, timestamp=datetime.now(tz.utc),
            tenant_id="t1", agent_id="a1",
            correction_type=corr_type,
            original_action=orig, original_output=None,
            corrected_action=corrected, corrected_output=None,
            tool_id=tool_id, transaction_id=f"tx-{cid}",
            context=ctx or {}, reviewer_id="r1",
            reviewer_trust_score=1.0, reasoning="test",
            severity="HIGH",
        )
        self.rlhc.corrections[cid] = c
        return c

    def test_generate_pattern_with_enough_corrections(self):
        self._make_correction("c1")
        self._make_correction("c2")
        self._make_correction("c3")
        pattern = _run(self.rlhc._generate_pattern_from_corrections(
            ["c1", "c2", "c3"]
        ))
        assert pattern is not None
        assert pattern.observation_count == 3
        assert pattern.pattern_type == "CONDITIONAL"
        assert len(pattern.source_corrections) == 3

    def test_generate_pattern_insufficient_corrections(self):
        self._make_correction("c1")
        pattern = _run(self.rlhc._generate_pattern_from_corrections(["c1"]))
        assert pattern is None

    def test_generate_pattern_mixed_types_returns_none(self):
        self._make_correction("c1", corr_type=CorrectionType.BLOCK_OVERRIDE)
        self._make_correction("c2", corr_type=CorrectionType.ALLOW_OVERRIDE)
        pattern = _run(self.rlhc._generate_pattern_from_corrections(["c1", "c2"]))
        assert pattern is None

    def test_generate_pattern_proposes_policy_on_high_confidence(self):
        # 10 corrections = confidence 1.0 >= 0.9 threshold → policy proposed
        for i in range(10):
            self._make_correction(f"c{i}")
        pattern = _run(self.rlhc._generate_pattern_from_corrections(
            [f"c{i}" for i in range(10)]
        ))
        assert pattern is not None
        assert pattern.confidence == 1.0
        assert self.rlhc.policies_proposed >= 1

    def test_pattern_stored_in_dict(self):
        for i in range(3):
            self._make_correction(f"c{i}")
        pattern = _run(self.rlhc._generate_pattern_from_corrections(
            [f"c{i}" for i in range(3)]
        ))
        assert pattern.pattern_id in self.rlhc.patterns


# ---------------------------------------------------------------------------
# Coverage Boost: Context Pattern Extraction
# ---------------------------------------------------------------------------

class TestExtractContextPatterns:
    """Cover _extract_context_patterns (lines 381-412)."""

    def setup_method(self):
        self.rlhc = ShadowSOPRLHC()

    def _make_correction_with_ctx(self, cid, ctx):
        from datetime import datetime, timezone as tz
        return HumanCorrection(
            correction_id=cid, timestamp=datetime.now(tz.utc),
            tenant_id="t1", agent_id="a1",
            correction_type=CorrectionType.BLOCK_OVERRIDE,
            original_action="ALLOW", original_output=None,
            corrected_action="BLOCK", corrected_output=None,
            tool_id="payment", transaction_id=f"tx-{cid}",
            context=ctx, reviewer_id="r1",
            reviewer_trust_score=1.0, reasoning="test",
            severity="HIGH",
        )

    def test_numeric_context_produces_range(self):
        corrections = [
            self._make_correction_with_ctx("c1", {"amount": 1000}),
            self._make_correction_with_ctx("c2", {"amount": 5000}),
            self._make_correction_with_ctx("c3", {"amount": 3000}),
        ]
        patterns = self.rlhc._extract_context_patterns(corrections)
        assert "amount" in patterns
        assert patterns["amount"]["min"] == 1000
        assert patterns["amount"]["max"] == 5000

    def test_string_context_same_value(self):
        corrections = [
            self._make_correction_with_ctx("c1", {"region": "US"}),
            self._make_correction_with_ctx("c2", {"region": "US"}),
        ]
        patterns = self.rlhc._extract_context_patterns(corrections)
        assert patterns["region"] == "US"

    def test_string_context_different_values(self):
        corrections = [
            self._make_correction_with_ctx("c1", {"region": "US"}),
            self._make_correction_with_ctx("c2", {"region": "EU"}),
        ]
        patterns = self.rlhc._extract_context_patterns(corrections)
        assert "one_of" in patterns["region"]
        assert set(patterns["region"]["one_of"]) == {"US", "EU"}

    def test_empty_context(self):
        corrections = [
            self._make_correction_with_ctx("c1", {}),
        ]
        patterns = self.rlhc._extract_context_patterns(corrections)
        assert patterns == {}


# ---------------------------------------------------------------------------
# Coverage Boost: Policy Lifecycle (Approve/Reject/Trigger/Retire)
# ---------------------------------------------------------------------------

class TestPolicyLifecycle:
    """Cover approve_policy, reject_policy, record_policy_trigger, retire_ineffective_policies."""

    def setup_method(self):
        from datetime import datetime, timezone as tz
        self.rlhc = ShadowSOPRLHC(min_corrections_for_pattern=2)
        # Create corrections and force a pattern + policy
        for i in range(10):
            c = HumanCorrection(
                correction_id=f"c{i}", timestamp=datetime.now(tz.utc),
                tenant_id="t1", agent_id="a1",
                correction_type=CorrectionType.BLOCK_OVERRIDE,
                original_action="ALLOW", original_output=None,
                corrected_action="BLOCK", corrected_output=None,
                tool_id="payment", transaction_id=f"tx-{i}",
                context={"amount": 1000 * (i + 1)}, reviewer_id="r1",
                reviewer_trust_score=1.0, reasoning="too large",
                severity="HIGH",
            )
            self.rlhc.corrections[f"c{i}"] = c
        # Generate pattern and policy
        _run(self.rlhc._generate_pattern_from_corrections(
            [f"c{i}" for i in range(10)]
        ))

    def _get_first_policy_id(self):
        return list(self.rlhc.policies.keys())[0]

    def test_approve_policy_success(self):
        pid = self._get_first_policy_id()
        result = self.rlhc.approve_policy(pid, "admin", "Looks good")
        assert result["success"] is True
        assert self.rlhc.policies[pid].status == PolicyStatus.APPROVED

    def test_approve_already_approved(self):
        pid = self._get_first_policy_id()
        self.rlhc.approve_policy(pid, "admin")
        result = self.rlhc.approve_policy(pid, "admin2")
        assert result["success"] is False

    def test_reject_policy_success(self):
        pid = self._get_first_policy_id()
        result = self.rlhc.reject_policy(pid, "admin", "Too aggressive")
        assert result["success"] is True
        assert self.rlhc.policies[pid].status == PolicyStatus.REJECTED

    def test_record_policy_trigger(self):
        pid = self._get_first_policy_id()
        self.rlhc.approve_policy(pid, "admin")
        self.rlhc.record_policy_trigger(pid, was_overridden=False)
        assert self.rlhc.policies[pid].times_triggered == 1
        assert self.rlhc.policies[pid].effectiveness_score == 1.0

    def test_record_trigger_with_override(self):
        pid = self._get_first_policy_id()
        self.rlhc.approve_policy(pid, "admin")
        self.rlhc.record_policy_trigger(pid, was_overridden=True)
        assert self.rlhc.policies[pid].overridden_count == 1
        assert self.rlhc.policies[pid].effectiveness_score == 0.0

    def test_retire_ineffective_policies(self):
        pid = self._get_first_policy_id()
        self.rlhc.approve_policy(pid, "admin")
        # Trigger 10 times, override 8 → effectiveness 0.2 < 0.5
        for i in range(10):
            self.rlhc.record_policy_trigger(pid, was_overridden=(i < 8))
        retired = self.rlhc.retire_ineffective_policies(min_triggers=10, effectiveness_threshold=0.5)
        assert pid in retired
        assert self.rlhc.policies[pid].status == PolicyStatus.RETIRED

    def test_retire_skips_effective_policies(self):
        pid = self._get_first_policy_id()
        self.rlhc.approve_policy(pid, "admin")
        # All triggers, no overrides → effectiveness 1.0
        for _ in range(10):
            self.rlhc.record_policy_trigger(pid, was_overridden=False)
        retired = self.rlhc.retire_ineffective_policies(min_triggers=10)
        assert pid not in retired


# ---------------------------------------------------------------------------
# Coverage Boost: Policy Proposal from Pattern
# ---------------------------------------------------------------------------

class TestProposePolicyFromPattern:
    """Cover _propose_policy_from_pattern (lines 414-467)."""

    def setup_method(self):
        self.rlhc = ShadowSOPRLHC()

    def _make_pattern(self, corr_type_value, tool_id="payment"):
        from datetime import datetime, timezone as tz
        rlhc_mod_local = rlhc_mod
        return rlhc_mod_local.LearnedPattern(
            pattern_id="pat-test",
            pattern_type="CONDITIONAL",
            trigger_conditions={
                "tool_id": tool_id,
                "correction_type": corr_type_value,
                "context": {"amount": {"min": 100, "max": 500}},
            },
            action_pattern="ALLOW",
            expected_correction="BLOCK",
            observation_count=5,
            accuracy=0.8,
            confidence=0.9,
            source_corrections=["c1", "c2"],
            first_observed=datetime.now(tz.utc),
            last_observed=datetime.now(tz.utc),
        )

    def test_block_override_creates_block_policy(self):
        pattern = self._make_pattern(CorrectionType.BLOCK_OVERRIDE.value)
        policy = _run(self.rlhc._propose_policy_from_pattern(pattern))
        assert policy is not None
        assert policy.policy_type == "BLOCK"
        assert policy.action == "block"

    def test_allow_override_creates_warn_policy(self):
        pattern = self._make_pattern(CorrectionType.ALLOW_OVERRIDE.value)
        policy = _run(self.rlhc._propose_policy_from_pattern(pattern))
        assert policy is not None
        assert policy.policy_type == "WARN"
        assert policy.action == "warn"

    def test_modify_creates_require_review_policy(self):
        pattern = self._make_pattern(CorrectionType.MODIFY_OUTPUT.value)
        policy = _run(self.rlhc._propose_policy_from_pattern(pattern))
        assert policy is not None
        assert policy.policy_type == "REQUIRE_REVIEW"

    def test_wildcard_tool_excludes_tool_condition(self):
        pattern = self._make_pattern(CorrectionType.BLOCK_OVERRIDE.value, tool_id="*")
        policy = _run(self.rlhc._propose_policy_from_pattern(pattern))
        assert "tool_id" not in policy.conditions


# ---------------------------------------------------------------------------
# Coverage Boost: E2E Flow
# ---------------------------------------------------------------------------

class TestE2EFlow:
    """Test full correction → pattern → policy flow."""

    def test_many_corrections_produce_pattern_and_policy(self):
        rlhc = ShadowSOPRLHC(min_corrections_for_pattern=2, policy_approval_threshold=0.3)
        for i in range(5):
            _run(rlhc.record_correction(
                tenant_id="t1", agent_id="a1",
                correction_type=CorrectionType.BLOCK_OVERRIDE,
                original_action="ALLOW",
                corrected_action="BLOCK",
                tool_id="execute_payment",
                transaction_id=f"txn-{i}",
                reviewer_id="human-1",
                reasoning="Payment too large",
                severity="HIGH",
                context={"amount": 1000 * (i + 1)},
            ))
        assert rlhc.patterns_generated >= 1
        stats = rlhc.get_stats()
        assert stats["total_corrections"] == 5

