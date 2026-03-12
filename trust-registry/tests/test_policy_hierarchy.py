"""
Policy Hierarchy — 3-Tier precedence tests (GLOBAL → CONTEXTUAL → DYNAMIC).
Patent: Claim 8 (CAE + APE Enforcement) — tier-based policy evaluation.
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch
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


class TestPolicyHierarchyEdgeCases:
    """Cover edge cases for policy_hierarchy.py."""

    def test_wildcard_trigger_matches_any_intent(self):
        """Policy with trigger_intent='*' matches any intent (L102)."""

        hierarchy = PolicyHierarchy()
        p = Policy(
            policy_id="GLOBAL_CATCH_ALL",
            tier=PolicyTier.GLOBAL,
            trigger_intent="*",
            logic={"==": [{"var": "blocked"}, True]},
            action={"on_fail": "BLOCK"},
            confidence=0.99,
            source_name="Global Rule",
        )
        hierarchy.add_policy(p)

        applicable = hierarchy.get_applicable_policies("any_intent_here")
        assert len(applicable) == 1

    def test_contextual_role_mismatch_filtered(self):
        """CONTEXTUAL policy with wrong role is filtered out (L106-107)."""

        hierarchy = PolicyHierarchy()
        p = Policy(
            policy_id="CTX_001",
            tier=PolicyTier.CONTEXTUAL,
            trigger_intent="payment",
            logic={">": [{"var": "amount"}, 100]},
            action={"on_fail": "BLOCK"},
            confidence=0.9,
            source_name="Scope Rule",
            roles=["admin"],
        )
        hierarchy.add_policy(p)

        applicable = hierarchy.get_applicable_policies("payment", role="viewer")
        assert len(applicable) == 0

    def test_contextual_role_match_included(self):

        hierarchy = PolicyHierarchy()
        p = Policy(
            policy_id="CTX_002",
            tier=PolicyTier.CONTEXTUAL,
            trigger_intent="payment",
            logic={">": [{"var": "amount"}, 100]},
            action={"on_fail": "BLOCK"},
            confidence=0.9,
            source_name="Scope Rule",
            roles=["admin"],
        )
        hierarchy.add_policy(p)

        applicable = hierarchy.get_applicable_policies("payment", role="admin")
        assert len(applicable) == 1

    def test_expired_policy_filtered(self):
        """Expired DYNAMIC policy is excluded from applicable (L98-99)."""

        hierarchy = PolicyHierarchy()
        p = Policy(
            policy_id="DYN_EXPIRED",
            tier=PolicyTier.DYNAMIC,
            trigger_intent="test",
            logic={"==": [{"var": "a"}, 1]},
            action={"on_fail": "FLAG"},
            confidence=0.8,
            source_name="Temp",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        hierarchy.add_policy(p)

        applicable = hierarchy.get_applicable_policies("test")
        assert len(applicable) == 0

    def test_intent_mismatch_filtered(self):
        """Policy with different trigger_intent excluded (L102-103)."""

        hierarchy = PolicyHierarchy()
        p = Policy(
            policy_id="G1",
            tier=PolicyTier.GLOBAL,
            trigger_intent="specific_action",
            logic={"==": [1, 1]},
            action={"on_fail": "BLOCK"},
            confidence=0.9,
            source_name="rule",
        )
        hierarchy.add_policy(p)

        applicable = hierarchy.get_applicable_policies("different_action")
        assert len(applicable) == 0


# ============================================================================
# policy_versioning.py — missing: 36, 125, 180, 224, 230, 235, 241, 263,
#                        280, 328-378 (__main__ block)
# ============================================================================




class TestPolicyHierarchyMainBlock:
    """Run policy_hierarchy.py __main__ block (L193-252) in-process."""

    def test_policy_hierarchy_main_runs(self):
        """policy_hierarchy.py __main__ block executes without error."""
        # The __main__ block calls evaluate_with_precedence which imports
        # json_logic_engine (requires json_logic module). Mock it.
        mock_jle = MagicMock()
        mock_jle.JSONLogicEngine.return_value.apply.return_value = True

        with patch.dict("sys.modules", {"json_logic_engine": mock_jle, "json_logic": MagicMock()}):
            import policy_hierarchy
            # Read the source file and exec the __main__ block
            src_path = os.path.join(os.path.dirname(__file__), "..", "policy_hierarchy.py")
            with open(src_path, "r") as f:
                source = f.read()
            # Execute in a namespace where __name__ == '__main__'
            ns = {"__name__": "__main__", "__file__": src_path}
            exec(compile(source, src_path, "exec"), ns)


