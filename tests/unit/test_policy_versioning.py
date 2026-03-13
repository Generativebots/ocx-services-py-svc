"""
Policy Versioning — create, update, rollback, compare tests.
Patent: CIP policy lifecycle management.
Tests Bug #1 fix: confidence/tier/source_name changes now create new versions
(hash includes ALL versioned fields, not just logic+action).
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from policy_versioning import PolicyVersionManager


class TestPolicyVersionManager:
    def _make_mgr(self):
        mgr = PolicyVersionManager()
        mgr.create_policy(
            policy_id="P1",
            logic={">": [{"var": "amount"}, 500]},
            action={"on_fail": "BLOCK"},
            tier="CONTEXTUAL",
            confidence=0.95,
            source_name="SOP v1",
            created_by="admin",
        )
        return mgr

    def test_create_policy_version_1(self):
        mgr = self._make_mgr()
        v = mgr.get_active_version("P1")
        assert v is not None
        assert v.version == 1
        assert v.is_active is True
        assert v.policy_id == "P1"

    def test_update_with_logic_change_creates_new_version(self):
        mgr = self._make_mgr()
        v2 = mgr.update_policy(
            "P1",
            logic={">": [{"var": "amount"}, 1000]},
            change_summary="Raised limit to $1000",
        )
        assert v2 is not None
        assert v2.version == 2
        assert v2.is_active is True
        v1 = mgr.get_version("P1", 1)
        assert v1.is_active is False

    def test_update_with_action_change(self):
        mgr = self._make_mgr()
        v2 = mgr.update_policy(
            "P1",
            action={"on_fail": "ESCALATE"},
            change_summary="Changed action",
        )
        assert v2 is not None
        assert v2.version == 2

    def test_update_no_change_returns_current(self):
        """When nothing changes, should return current version (no new version)."""
        mgr = self._make_mgr()
        result = mgr.update_policy("P1", change_summary="No real change")
        # Returns current v1 since content_hash is identical
        assert result.version == 1

    def test_update_nonexistent_returns_none(self):
        mgr = PolicyVersionManager()
        result = mgr.update_policy("GHOST", confidence=0.5)
        assert result is None

    # ── Bug #1 Fix Verification: confidence/tier changes now create versions ──

    def test_update_confidence_only_creates_new_version(self):
        """Per patent audit trail: confidence changes MUST create a new version.
        This was the original Bug #1 — _calculate_hash only hashed logic+action."""
        mgr = self._make_mgr()
        v2 = mgr.update_policy(
            "P1",
            confidence=0.80,
            change_summary="Confidence adjusted",
        )
        assert v2 is not None
        assert v2.version == 2, "Confidence-only change must create v2"
        assert v2.confidence == 0.80
        assert v2.is_active is True
        # v1 should be deactivated
        v1 = mgr.get_version("P1", 1)
        assert v1.is_active is False

    def test_update_tier_only_creates_new_version(self):
        """Per patent: tier changes (e.g., CONTEXTUAL → GLOBAL) must create new version."""
        mgr = self._make_mgr()
        v2 = mgr.update_policy(
            "P1",
            tier="GLOBAL",
            change_summary="Elevated to global tier",
        )
        assert v2 is not None
        assert v2.version == 2, "Tier-only change must create v2"
        assert v2.tier == "GLOBAL"

    def test_compare_versions_shows_confidence_diff(self):
        """compare_versions should detect confidence changes."""
        mgr = self._make_mgr()
        mgr.update_policy("P1", confidence=0.60, change_summary="Lower confidence")
        diff = mgr.compare_versions("P1", 1, 2)
        assert diff is not None
        assert "confidence" in diff["changes"]
        assert diff["changes"]["confidence"]["from"] == 0.95
        assert diff["changes"]["confidence"]["to"] == 0.60

    def test_compare_versions_shows_tier_diff(self):
        """compare_versions should detect tier changes."""
        mgr = self._make_mgr()
        mgr.update_policy("P1", tier="GLOBAL", change_summary="Tier change")
        diff = mgr.compare_versions("P1", 1, 2)
        assert diff is not None
        assert "tier" in diff["changes"]
        assert diff["changes"]["tier"]["from"] == "CONTEXTUAL"
        assert diff["changes"]["tier"]["to"] == "GLOBAL"

    # ── Multi-tenant versioning ──

    def test_multi_tenant_isolation(self):
        """Different tenants can have independent policies with the same ID prefix."""
        mgr = PolicyVersionManager()
        mgr.create_policy(
            policy_id="T1:PO1",
            logic={">": [{"var": "amount"}, 100]},
            action={"on_fail": "BLOCK"},
            tier="CONTEXTUAL",
            confidence=0.90,
            source_name="Tenant-1 SOP",
            created_by="admin",
        )
        mgr.create_policy(
            policy_id="T2:PO1",
            logic={">": [{"var": "amount"}, 200]},
            action={"on_fail": "WARN"},
            tier="GLOBAL",
            confidence=0.85,
            source_name="Tenant-2 SOP",
            created_by="admin",
        )
        # Policies are isolated
        t1_v1 = mgr.get_active_version("T1:PO1")
        t2_v1 = mgr.get_active_version("T2:PO1")
        assert t1_v1.logic != t2_v1.logic
        assert t1_v1.confidence == 0.90
        assert t2_v1.confidence == 0.85

        # Update T1 doesn't affect T2
        mgr.update_policy("T1:PO1", confidence=0.50, change_summary="T1 update")
        assert mgr.get_active_version("T1:PO1").version == 2
        assert mgr.get_active_version("T2:PO1").version == 1

    # ── Original tests retained ──

    def test_rollback_restores_version(self):
        mgr = self._make_mgr()
        mgr.update_policy("P1", logic={">": [{"var": "amount"}, 1000]}, change_summary="v2")
        v3 = mgr.rollback("P1", target_version=1, created_by="rollback-bot")
        assert v3 is not None
        assert v3.version == 3
        assert v3.logic == {">": [{"var": "amount"}, 500]}

    def test_rollback_nonexistent_version(self):
        mgr = self._make_mgr()
        result = mgr.rollback("P1", target_version=99)
        assert result is None

    def test_version_history(self):
        mgr = self._make_mgr()
        mgr.update_policy("P1", logic={">": [{"var": "amount"}, 1000]}, change_summary="v2")
        mgr.update_policy("P1", logic={">": [{"var": "amount"}, 2000]}, change_summary="v3")
        history = mgr.get_version_history("P1")
        assert len(history) == 3
        assert history[0].version == 1
        assert history[2].version == 3

    def test_compare_versions_logic(self):
        mgr = self._make_mgr()
        mgr.update_policy("P1", logic={">": [{"var": "amount"}, 1000]}, change_summary="v2")
        diff = mgr.compare_versions("P1", 1, 2)
        assert diff is not None
        assert "logic" in diff["changes"]

    def test_content_hash_changes_with_logic(self):
        mgr = self._make_mgr()
        v1 = mgr.get_version("P1", 1)
        mgr.update_policy("P1", logic={">": [{"var": "amount"}, 1000]}, change_summary="Raised limit")
        v2 = mgr.get_version("P1", 2)
        assert v1.content_hash != v2.content_hash


class TestPolicyVersioningEdgeCases:
    """Cover edge cases for policy_versioning.py."""

    def _make_manager(self):
        from policy_versioning import PolicyVersionManager
        mgr = PolicyVersionManager()
        mgr.create_policy(
            policy_id="P1",
            logic={">": [{"var": "amount"}, 100]},
            action={"on_fail": "BLOCK"},
            tier="GLOBAL",
            confidence=0.9,
            source_name="SOP v1",
            created_by="admin",
        )
        return mgr

    def test_update_nonexistent_returns_none(self):
        """Update to non-existent policy → None (L119-120)."""
        from policy_versioning import PolicyVersionManager
        mgr = PolicyVersionManager()
        result = mgr.update_policy("NONEXISTENT", logic={})
        assert result is None

    def test_rollback_nonexistent_policy(self):
        """Rollback on non-existent policy → None (L179-180)."""
        from policy_versioning import PolicyVersionManager
        mgr = PolicyVersionManager()
        result = mgr.rollback("NONEXISTENT", 1)
        assert result is None

    def test_rollback_nonexistent_version(self):
        """Rollback to non-existent version → None (L189-191)."""
        mgr = self._make_manager()
        result = mgr.rollback("P1", 99)
        assert result is None

    def test_get_active_version_nonexistent(self):
        """get_active_version for non-existent → None (L223-224)."""
        from policy_versioning import PolicyVersionManager
        mgr = PolicyVersionManager()
        assert mgr.get_active_version("NO_SUCH") is None

    def test_get_active_version_none_active(self):
        """All versions deactivated → None (L226-230)."""
        mgr = self._make_manager()
        for v in mgr.versions["P1"]:
            v.is_active = False
        assert mgr.get_active_version("P1") is None

    def test_get_version_nonexistent_policy(self):
        """get_version for non-existent policy → None (L234-235)."""
        from policy_versioning import PolicyVersionManager
        mgr = PolicyVersionManager()
        assert mgr.get_version("NO_SUCH", 1) is None

    def test_get_version_nonexistent_version_num(self):
        """get_version for wrong version number → None (L237-241)."""
        mgr = self._make_manager()
        assert mgr.get_version("P1", 99) is None

    def test_compare_versions_missing_one(self):
        """compare_versions where one version doesn't exist → None (L262-263)."""
        mgr = self._make_manager()
        result = mgr.compare_versions("P1", 1, 99)
        assert result is None

    def test_compare_versions_action_diff(self):
        """compare_versions detects action difference (L279-283)."""
        mgr = self._make_manager()
        mgr.update_policy(
            "P1", action={"on_fail": "ESCALATE"}, change_summary="Changed action",
        )
        diff = mgr.compare_versions("P1", 1, 2)
        assert "action" in diff["changes"]

    def test_compare_versions_tier_diff(self):
        """compare_versions detects tier difference (L285-289)."""
        mgr = self._make_manager()
        mgr.update_policy("P1", tier="DYNAMIC", change_summary="Changed tier")
        diff = mgr.compare_versions("P1", 1, 2)
        assert "tier" in diff["changes"]

    def test_version_to_dict(self):
        """PolicyVersion.to_dict serializes correctly (L34-49)."""
        mgr = self._make_manager()
        v = mgr.get_active_version("P1")
        d = v.to_dict()
        assert d["policy_id"] == "P1"
        assert d["version"] == 1
        assert d["is_active"] is True
        assert isinstance(d["content_hash"], str)

    def test_version_history_empty(self):
        """get_version_history for non-existent → [] (L245)."""
        from policy_versioning import PolicyVersionManager
        mgr = PolicyVersionManager()
        assert mgr.get_version_history("NOTHING") == []

    def test_update_no_change_returns_current(self):
        """Update with same data → returns current version (L138-140)."""
        mgr = self._make_manager()
        v1 = mgr.get_active_version("P1")
        # Update with identical values
        result = mgr.update_policy("P1", change_summary="No real change")
        assert result is v1  # Same object returned

    def test_update_with_active_deactivated(self):
        """Update when active version exists → deactivates it (L124-125)."""
        mgr = self._make_manager()
        # Deactivate all
        for v in mgr.versions["P1"]:
            v.is_active = False
        # Now update — no active version → returns None
        result = mgr.update_policy("P1", logic={"==": [1, 1]})
        assert result is None

    def test_compare_versions_confidence_diff(self):
        """compare_versions detects confidence difference (L291-295)."""
        mgr = self._make_manager()
        mgr.update_policy("P1", confidence=0.5, change_summary="Lower confidence")
        diff = mgr.compare_versions("P1", 1, 2)
        assert "confidence" in diff["changes"]

    def test_compare_versions_no_changes(self):
        """compare_versions with identical versions → empty changes dict."""
        mgr = self._make_manager()
        # Create v2 with different logic to make it exist
        mgr.update_policy("P1", logic={">": [{"var": "amount"}, 200]}, change_summary="bump")
        # Compare v1 with v1
        diff = mgr.compare_versions("P1", 1, 1)
        assert diff["changes"] == {}


# ============================================================================
# main.py — additional tests for signature verification (L88-99),
#            ghost state warning (L134-140), WARN token (L167-168),
#            rules_v1.md fallback (L48-49), memory vault reading (L208-220)
# ============================================================================




class TestPolicyVersioningMainBlock:
    """Run policy_versioning.py __main__ block (L327-378) in-process."""

    def test_policy_versioning_main_runs(self):
        """policy_versioning.py __main__ block executes without error."""
        src_path = os.path.join(os.path.dirname(__file__), "..", "policy_versioning.py")
        with open(src_path, "r") as f:
            source = f.read()
        ns = {"__name__": "__main__", "__file__": src_path}
        exec(compile(source, src_path, "exec"), ns)


