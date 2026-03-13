"""Tests for shadow-sop/slack_observer.py — SlackShadowSOPObserver."""

import sys
import os
import importlib.util

# Allow importing shadow-sop modules
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# --- Mock dependencies ---
import unittest.mock as mock

_fake_gov_mod = mock.MagicMock()
_fake_gov_mod.get_tenant_governance_config = mock.MagicMock(return_value={
    "shadow_min_confidence": 0.70,
})
sys.modules.setdefault("config", mock.MagicMock())
sys.modules["config.governance_config"] = _fake_gov_mod

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_observer_path = os.path.join(_ROOT, "shadow-sop", "slack_observer.py")
_spec = importlib.util.spec_from_file_location("slack_observer", _observer_path)
slack_observer = importlib.util.module_from_spec(_spec)
sys.modules["slack_observer"] = slack_observer
_spec.loader.exec_module(slack_observer)

SlackShadowSOPObserver = slack_observer.SlackShadowSOPObserver

import pytest


class TestInit:
    def test_defaults(self):
        obs = SlackShadowSOPObserver()
        assert obs.bot_token is None
        assert obs.app_token is None
        assert obs.llm is None
        assert obs.discovered_sops == []
        assert obs.min_confidence == 0.70

    def test_with_tokens(self):
        obs = SlackShadowSOPObserver(bot_token="xoxb-test", app_token="xapp-test")
        assert obs.bot_token == "xoxb-test"
        assert obs.app_token == "xapp-test"


class TestExtractTribalKnowledge:
    def setup_method(self):
        self.obs = SlackShadowSOPObserver()

    def test_cloud_costs(self):
        r = self.obs.extract_tribal_knowledge(
            "We always get CTO approval for cloud costs over $5k/month",
            "#eng", "alice",
        )
        assert r is not None
        assert r["rule"] == "Get CTO approval for cloud costs over $5k/month"
        assert r["confidence"] == 0.9
        assert r["channel"] == "#eng"
        assert r["author"] == "alice"
        assert r["suggested_action"] == "BLOCK"

    def test_deploy_fridays(self):
        r = self.obs.extract_tribal_knowledge(
            "Never deploy on Fridays without QA sign-off",
            "#ops", "bob",
        )
        assert r is not None
        assert r["confidence"] == 0.85
        assert r["suggested_action"] == "BLOCK"

    def test_no_match(self):
        r = self.obs.extract_tribal_knowledge("Hello world", "#gen", "x")
        assert r is None


class TestProcessMessage:
    def setup_method(self):
        self.obs = SlackShadowSOPObserver()

    def test_matching_message_stored(self):
        self.obs.process_message(
            "We always get CTO approval for cloud costs over $5k/month",
            "#eng", "alice",
        )
        assert len(self.obs.discovered_sops) >= 1

    def test_non_matching_message(self):
        self.obs.process_message("Just random chat", "#gen", "bob")
        assert len(self.obs.discovered_sops) == 0


class TestStoreAndReview:
    def setup_method(self):
        self.obs = SlackShadowSOPObserver()
        # Store a valid SOP (must have 'rule' key)
        self.obs.store_shadow_sop({
            "rule": "Always run tests before deploy",
            "confidence": 0.9,
            "source": "slack",
        })

    def test_store_sets_status(self):
        assert self.obs.discovered_sops[0]["status"] == "pending"

    def test_store_sets_discovered_at(self):
        assert "discovered_at" in self.obs.discovered_sops[0]

    def test_get_pending_reviews(self):
        pending = self.obs.get_pending_reviews()
        assert len(pending) == 1

    def test_approve(self):
        result = self.obs.approve_shadow_sop(0, reviewed_by="admin")
        assert result["success"] is True
        assert self.obs.discovered_sops[0]["status"] == "approved"
        assert self.obs.discovered_sops[0]["reviewed_by"] == "admin"

    def test_approve_not_found(self):
        result = self.obs.approve_shadow_sop(999, reviewed_by="admin")
        assert result["success"] is False

    def test_reject(self):
        result = self.obs.reject_shadow_sop(0, reviewed_by="admin", reason="Not applicable")
        assert result["success"] is True
        assert self.obs.discovered_sops[0]["status"] == "rejected"
        assert self.obs.discovered_sops[0]["rejection_reason"] == "Not applicable"

    def test_reject_not_found(self):
        result = self.obs.reject_shadow_sop(999, reviewed_by="admin", reason="n/a")
        assert result["success"] is False


class TestListenForTribalKnowledge:
    def test_processes_dummy_messages(self):
        obs = SlackShadowSOPObserver()
        obs.listen_for_tribal_knowledge()
        # Should process dummy messages and discover SOPs
        assert len(obs.discovered_sops) >= 1
