"""
Trust Registry — Kill Switch unit tests.

Tests the KillSwitch class enforcement logic with mocked HTTP
backend (requests library).
"""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestKillSwitch:
    """KillSwitch enforcement tests."""

    def _make_ks(self):
        from kill_switch import KillSwitch
        return KillSwitch(
            backend_url="http://mock-backend:8080",
            pubsub_topic="test-topic",
        )

    def test_no_trigger_above_threshold(self):
        """Score above threshold → no enforcement."""
        ks = self._make_ks()
        result = ks.check_and_enforce(
            agent_id="agent-1",
            score=0.8,
            verdict="APPROVED",
            tenant_id="t-1",
        )
        assert result["triggered"] is False
        assert result["score"] == 0.8

    def test_no_trigger_at_threshold(self):
        """Score exactly at threshold → no enforcement."""
        ks = self._make_ks()
        result = ks.check_and_enforce(
            agent_id="agent-1",
            score=0.3,
            verdict="APPROVED",
            tenant_id="t-1",
        )
        assert result["triggered"] is False

    @patch("kill_switch.requests.Session")
    def test_trigger_below_threshold(self, mock_session_cls):
        """Score below threshold → kill switch triggered."""
        # Mock the session's post method
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"ok": true}'
        mock_session.post.return_value = mock_resp
        mock_session_cls.return_value = mock_session

        ks = self._make_ks()
        ks._session = mock_session  # Inject mock session

        result = ks.check_and_enforce(
            agent_id="agent-low",
            score=0.1,
            verdict="BLOCKED",
            tenant_id="t-1",
        )
        assert result["triggered"] is True
        assert result["agent_id"] == "agent-low"
        assert result["score"] == 0.1
        assert result["tokens_revoked"] is True
        assert result["event_id"] is not None

    @patch("kill_switch.requests.Session")
    def test_trigger_backend_unreachable(self, mock_session_cls):
        """Backend unreachable → triggered but tokens_revoked=False."""
        import requests as real_requests

        mock_session = MagicMock()
        mock_session.post.side_effect = real_requests.exceptions.ConnectionError("Connection refused")
        mock_session_cls.return_value = mock_session

        ks = self._make_ks()
        ks._session = mock_session

        result = ks.check_and_enforce(
            agent_id="agent-down",
            score=0.05,
            verdict="BLOCKED",
            tenant_id="t-1",
        )
        assert result["triggered"] is True
        assert result["tokens_revoked"] is False

    def test_threshold_from_constructor(self):
        """Threshold is configurable."""
        ks = self._make_ks()
        assert ks.THRESHOLD == 0.3


class TestKillSwitchRevocation:
    """Tests for the private _revoke_agent_tokens method."""

    @patch("kill_switch.requests.Session")
    def test_revoke_success(self, mock_session_cls):
        from kill_switch import KillSwitch

        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_session.post.return_value = mock_resp
        mock_session_cls.return_value = mock_session

        ks = KillSwitch(backend_url="http://mock:8080")
        ks._session = mock_session

        result = ks._revoke_agent_tokens("agent-1", "t-1", 0.1)
        assert result is True

    @patch("kill_switch.requests.Session")
    def test_revoke_server_error(self, mock_session_cls):
        from kill_switch import KillSwitch

        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_session.post.return_value = mock_resp
        mock_session_cls.return_value = mock_session

        ks = KillSwitch(backend_url="http://mock:8080")
        ks._session = mock_session

        result = ks._revoke_agent_tokens("agent-1", "t-1", 0.1)
        assert result is False


class TestKillSwitchTenantConfig:
    """Tests for KillSwitch tenant-specific threshold loading."""

    @patch("kill_switch.requests.Session")
    def test_tenant_config_overrides_threshold(self, mock_sess_cls):
        """KillSwitch with tenant_id loads threshold from governance config."""
        fake_cfg = {"kill_switch_threshold": 0.50}
        with patch(
            "config.governance_config.get_tenant_governance_config",
            return_value=fake_cfg,
        ):
            from kill_switch import KillSwitch
            ks = KillSwitch(
                backend_url="http://mock:8080",
                tenant_id="tenant-abc",
            )
            assert ks.THRESHOLD == 0.50

    @patch("kill_switch.requests.Session")
    def test_tenant_config_missing_key_uses_default(self, mock_sess_cls):
        """Governance config without kill_switch_threshold uses 0.3 default."""
        with patch(
            "config.governance_config.get_tenant_governance_config",
            return_value={},
        ):
            from kill_switch import KillSwitch
            ks = KillSwitch(
                backend_url="http://mock:8080",
                tenant_id="tenant-xyz",
            )
            assert ks.THRESHOLD == 0.3




class TestKillSwitchDispatchEvent:
    """Tests for _dispatch_block_event covering L141-161."""

    @patch("kill_switch.requests.Session")
    def test_dispatch_event_success(self, mock_sess_cls):
        from kill_switch import KillSwitch

        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_session.post.return_value = mock_resp

        ks = KillSwitch(backend_url="http://mock:8080")
        ks._session = mock_session

        payload = {"block_agent": "agent-xyz-12345678", "tenant_id": "t1"}
        event_id = ks._dispatch_block_event(payload)
        assert event_id is not None
        assert event_id.startswith("ks-agent-xy")

    @patch("kill_switch.requests.Session")
    def test_dispatch_event_server_error_still_returns_id(self, mock_sess_cls):
        """Non-200 response → event_id still returned (non-critical path)."""
        from kill_switch import KillSwitch

        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_session.post.return_value = mock_resp

        ks = KillSwitch(backend_url="http://mock:8080")
        ks._session = mock_session

        payload = {"block_agent": "agent-err-12345678", "tenant_id": "t1"}
        event_id = ks._dispatch_block_event(payload)
        # Even on 500, the event_id is returned (L155-158 coverage)
        assert event_id is not None

    @patch("kill_switch.requests.Session")
    def test_dispatch_event_connection_error_returns_none(self, mock_sess_cls):
        """Request exception → returns None."""
        import requests as real_requests
        from kill_switch import KillSwitch

        mock_session = MagicMock()
        mock_session.post.side_effect = real_requests.exceptions.ConnectionError("down")

        ks = KillSwitch(backend_url="http://mock:8080")
        ks._session = mock_session

        payload = {"block_agent": "agent-down-1234", "tenant_id": "t1"}
        event_id = ks._dispatch_block_event(payload)
        assert event_id is None


# ============================================================================
# jury.py — missing lines: 18-19 (_HAS_GOV_CONFIG=False), 39-41, 65, 76, 79,
#            87, 90, 115-139 (LLM client + fallback)
# ============================================================================


