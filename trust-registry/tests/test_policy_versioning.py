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
