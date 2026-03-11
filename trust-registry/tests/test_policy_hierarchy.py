"""
Policy Hierarchy — 3-Tier precedence tests (GLOBAL → CONTEXTUAL → DYNAMIC).
Patent: Claim 8 (CAE + APE Enforcement) — tier-based policy evaluation.
"""

import pytest
import sys
import os
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from policy_hierarchy import Policy, PolicyTier, PolicyHierarchy


class TestPolicyDataclass:
    def test_global_policy_applies_to_all_roles(self):
        p = Policy(
            policy_id="G1", tier=PolicyTier.GLOBAL,
            trigger_intent="*", logic={">": [{"var": "amount"}, 500]},
            action={"on_fail": "BLOCK"}, confidence=0.99, source_name="test"
        )
        assert p.applies_to_role("any_role")

    def test_contextual_restricts_to_role(self):
        p = Policy(
            policy_id="C1", tier=PolicyTier.CONTEXTUAL,
            trigger_intent="buy", logic={}, action={}, confidence=0.9,
            source_name="test", roles=["procurement"]
        )
        assert p.applies_to_role("procurement") is True
        assert p.applies_to_role("engineer") is False

    def test_dynamic_expiry(self):
        expired = Policy(
            policy_id="D1", tier=PolicyTier.DYNAMIC,
            trigger_intent="send", logic={}, action={}, confidence=0.8,
            source_name="test", expires_at=datetime.now(timezone.utc) - timedelta(hours=1)
        )
        assert expired.is_expired() is True

        active = Policy(
            policy_id="D2", tier=PolicyTier.DYNAMIC,
            trigger_intent="send", logic={}, action={}, confidence=0.8,
            source_name="test", expires_at=datetime.now(timezone.utc) + timedelta(days=7)
        )
        assert active.is_expired() is False

    def test_to_dict_serialization(self):
        p = Policy(
            policy_id="G1", tier=PolicyTier.GLOBAL,
            trigger_intent="*", logic={">": [{"var": "a"}, 1]},
            action={"on_fail": "BLOCK"}, confidence=0.99, source_name="test"
        )
        d = p.to_dict()
        assert d["policy_id"] == "G1"
        assert d["tier"] == "GLOBAL"
        assert d["is_active"] is True


class TestPolicyHierarchy:
    def _make_hierarchy(self):
        h = PolicyHierarchy()
        h.add_policy(Policy(
            policy_id="G1", tier=PolicyTier.GLOBAL,
            trigger_intent="buy", logic={">": [{"var": "amount"}, 10000]},
            action={"on_fail": "BLOCK"}, confidence=0.99, source_name="security"
        ))
        h.add_policy(Policy(
            policy_id="C1", tier=PolicyTier.CONTEXTUAL,
            trigger_intent="buy", logic={">": [{"var": "amount"}, 500]},
            action={"on_fail": "ESCALATE"}, confidence=0.95, source_name="sop",
            roles=["procurement"]
        ))
        h.add_policy(Policy(
            policy_id="D1", tier=PolicyTier.DYNAMIC,
            trigger_intent="buy", logic={">": [{"var": "amount"}, 100]},
            action={"on_fail": "FLAG"}, confidence=0.8, source_name="project",
            expires_at=datetime.now(timezone.utc) + timedelta(days=7)
        ))
        return h

    def test_precedence_order(self):
        h = self._make_hierarchy()
        policies = h.get_applicable_policies("buy", role="procurement")
        assert [p.tier for p in policies] == [PolicyTier.GLOBAL, PolicyTier.CONTEXTUAL, PolicyTier.DYNAMIC]

    def test_global_blocks_first(self):
        h = self._make_hierarchy()
        allowed, policy, action = h.evaluate_with_precedence("buy", {"amount": 20000}, "procurement")
        assert allowed is False
        assert policy.policy_id == "G1"
        assert action == "BLOCK"

    def test_contextual_blocks_second(self):
        h = self._make_hierarchy()
        allowed, policy, action = h.evaluate_with_precedence("buy", {"amount": 1000}, "procurement")
        assert allowed is False
        assert policy.policy_id == "C1"

    def test_all_pass(self):
        h = self._make_hierarchy()
        allowed, policy, action = h.evaluate_with_precedence("buy", {"amount": 50}, "procurement")
        assert allowed is True
        assert policy is None

    def test_inactive_skipped(self):
        h = PolicyHierarchy()
        p = Policy(
            policy_id="X", tier=PolicyTier.GLOBAL, trigger_intent="*",
            logic={">": [{"var": "a"}, 0]}, action={"on_fail": "BLOCK"},
            confidence=0.99, source_name="test", is_active=False
        )
        h.add_policy(p)
        assert h.get_applicable_policies("anything") == []

    def test_cleanup_expired(self):
        h = PolicyHierarchy()
        h.add_policy(Policy(
            policy_id="EXP", tier=PolicyTier.DYNAMIC, trigger_intent="*",
            logic={}, action={}, confidence=0.5, source_name="test",
            expires_at=datetime.now(timezone.utc) - timedelta(days=1)
        ))
        removed = h.cleanup_expired()
        assert removed == 1
        assert len(h.policies) == 0

    def test_stats(self):
        h = self._make_hierarchy()
        stats = h.get_stats()
        assert stats["GLOBAL"] == 1
        assert stats["CONTEXTUAL"] == 1
        assert stats["DYNAMIC"] == 1
        assert stats["total"] == 3
