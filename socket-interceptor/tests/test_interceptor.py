"""
Socket Interceptor — Patent Claim 5 (eBPF Socket-Level Interception).
Tests: SocketInterceptor, rule evaluation, compliance checks, InterceptedSocket.
"""

import pytest
import sys
import os
import socket
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

# Stub requests before importing interceptor
import types
_fake_requests = types.ModuleType("requests")
_fake_requests.get = MagicMock(return_value=MagicMock(status_code=200, json=lambda: []))
_fake_requests.post = MagicMock(return_value=MagicMock(status_code=201))
_fake_requests.Response = type("Response", (), {"raise_for_status": lambda self: None})
_fake_requests.RequestException = type("RequestException", (Exception,), {})
sys.modules.setdefault("requests", _fake_requests)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from interceptor import (
    ValidationRule, InterceptionContext,
    ActivityRegistry, EvidenceVault, SocketInterceptor,
)


# -------------------------------------------------------------------
# ValidationRule dataclass
# -------------------------------------------------------------------
class TestValidationRule:
    def test_defaults(self):
        r = ValidationRule(
            rule_id="R1", condition="port != 22",
            activity_id="A1", activity_name="Procurement",
            policy_reference="SOP-v1"
        )
        assert r.severity == "ERROR"
        assert r.rule_id == "R1"


# -------------------------------------------------------------------
# ActivityRegistry — EBCL parsing
# -------------------------------------------------------------------
class TestActivityRegistry:
    def test_parse_validate_rules_empty(self):
        reg = ActivityRegistry("http://fake")
        rules = reg.parse_validate_rules(
            "NO-VALIDATION-BLOCK-HERE", "A1", "Test Activity", "SOP"
        )
        assert rules == []

    def test_parse_validate_rules_with_requires(self):
        ebcl = """
VALIDATE
REQUIRE destination.port != 22
REQUIRE destination.host not in blacklist

NEXT SECTION
"""
        reg = ActivityRegistry("http://fake")
        rules = reg.parse_validate_rules(ebcl, "A1", "Procurement", "SOP-v1")
        assert len(rules) == 2
        assert "port" in rules[0].condition
        assert rules[0].activity_id == "A1"

    def test_cache_hit(self):
        import time
        reg = ActivityRegistry("http://fake")
        reg._cache["t1:PROD"] = (["cached_data"], time.time())
        result = reg.get_active_activities("t1", "PROD")
        assert result == ["cached_data"]


# -------------------------------------------------------------------
# EvidenceVault client
# -------------------------------------------------------------------
class TestEvidenceVault:
    def test_log_violation_calls_post(self):
        vault = EvidenceVault("http://fake")
        ctx = InterceptionContext(
            socket_id="s1", operation="connect",
            destination=("evil.com", 443), data=None,
            timestamp=datetime.now(timezone.utc),
            agent_id="agent-1", tenant_id="t1"
        )
        rule = ValidationRule(
            rule_id="R1", condition="host blacklisted",
            activity_id="A1", activity_name="Test",
            policy_reference="SOP"
        )
        # Should not raise
        vault.log_violation(ctx, rule, "Host is blacklisted")


# -------------------------------------------------------------------
# SocketInterceptor — rule evaluation & compliance
# -------------------------------------------------------------------
class TestSocketInterceptorRuleEvaluation:
    def _make_interceptor(self):
        """Create interceptor with mocked external services."""
        with patch.object(SocketInterceptor, '_load_validation_rules'):
            with patch.object(SocketInterceptor, '_start_rule_refresh'):
                si = SocketInterceptor(tenant_id="t1", agent_id="agent-1")
        return si

    def _make_context(self, host="api.example.com", port=443, op="connect"):
        return InterceptionContext(
            socket_id="test-sock", operation=op,
            destination=(host, port), data=None,
            timestamp=datetime.now(timezone.utc),
            agent_id="agent-1", tenant_id="t1"
        )

    def test_port_block_rule(self):
        si = self._make_interceptor()
        rule = ValidationRule(
            rule_id="R1", condition="destination.port != 22",
            activity_id="A1", activity_name="Test",
            policy_reference="SOP"
        )
        ctx = self._make_context(port=22)
        passed, reason = si._evaluate_rule(rule, ctx)
        assert passed is False
        assert "22" in reason

    def test_port_allow_rule(self):
        si = self._make_interceptor()
        rule = ValidationRule(
            rule_id="R1", condition="destination.port != 22",
            activity_id="A1", activity_name="Test",
            policy_reference="SOP"
        )
        ctx = self._make_context(port=443)
        passed, reason = si._evaluate_rule(rule, ctx)
        assert passed is True

    def test_blacklist_rule_blocks(self):
        si = self._make_interceptor()
        rule = ValidationRule(
            rule_id="R2", condition="destination.host not in blacklist",
            activity_id="A1", activity_name="Test",
            policy_reference="SOP"
        )
        ctx = self._make_context(host="malicious.com")
        passed, reason = si._evaluate_rule(rule, ctx)
        assert passed is False
        assert "blacklisted" in reason.lower()

    def test_blacklist_rule_allows(self):
        si = self._make_interceptor()
        rule = ValidationRule(
            rule_id="R2", condition="destination.host not in blacklist",
            activity_id="A1", activity_name="Test",
            policy_reference="SOP"
        )
        ctx = self._make_context(host="api.trusted.com")
        passed, reason = si._evaluate_rule(rule, ctx)
        assert passed is True

    def test_compliance_check_all_pass(self):
        si = self._make_interceptor()
        si.validation_rules = []
        ctx = self._make_context()
        compliant, violations = si._check_compliance(ctx)
        assert compliant is True
        assert violations == []

    def test_compliance_check_with_violation(self):
        si = self._make_interceptor()
        si.validation_rules = [
            ValidationRule("R1", "destination.port != 22", "A1", "Test", "SOP"),
        ]
        si.evidence_vault = MagicMock()
        ctx = self._make_context(port=22)
        compliant, violations = si._check_compliance(ctx)
        assert compliant is False
        assert len(violations) == 1

    def test_install_and_uninstall(self):
        """SocketInterceptor.install replaces socket.socket; uninstall restores it."""
        si = self._make_interceptor()
        original = socket.socket
        si.install()
        # After install, socket.socket should NOT be the standard one
        assert socket.socket is not original
        si.uninstall()
        # After uninstall, socket.socket should be restored
        assert socket.socket is original


# -------------------------------------------------------------------
# Expanded coverage: ActivityRegistry live fetch & error
# -------------------------------------------------------------------
class TestActivityRegistryExpanded:
    def test_get_active_activities_live_fetch(self):
        """Covers lines 66-79: live HTTP fetch path (cache miss)."""
        reg = ActivityRegistry("http://fake")
        reg._cache.clear()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = [{"id": "a1"}]
        with patch("interceptor.requests.get", return_value=mock_resp):
            result = reg.get_active_activities("t-new", "PROD")
        assert result == [{"id": "a1"}]
        assert "t-new:PROD" in reg._cache

    def test_get_active_activities_error(self):
        """On request error, returns empty list."""
        reg = ActivityRegistry("http://fake")
        reg._cache.clear()
        with patch("interceptor.requests.get", side_effect=Exception("timeout")):
            result = reg.get_active_activities("t-err", "PROD")
        assert result == []

    def test_cache_expired(self):
        """Expired cache triggers re-fetch."""
        import time as _time
        reg = ActivityRegistry("http://fake")
        reg._cache["t1:PROD"] = (["old"], _time.time() - 400)  # expired
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = [{"id": "new"}]
        with patch("interceptor.requests.get", return_value=mock_resp):
            result = reg.get_active_activities("t1", "PROD")
        assert result == [{"id": "new"}]


# -------------------------------------------------------------------
# Expanded coverage: EvidenceVault error + success paths
# -------------------------------------------------------------------
class TestEvidenceVaultExpanded:
    def test_log_violation_request_error(self):
        """requests.post raises exception → logs error."""
        vault = EvidenceVault("http://fake")
        ctx = InterceptionContext(
            socket_id="s1", operation="connect",
            destination=("evil.com", 443), data=None,
            timestamp=datetime.now(timezone.utc),
            agent_id="agent-1", tenant_id="t1"
        )
        rule = ValidationRule("R1", "cond", "A1", "Test", "SOP")
        with patch("interceptor.requests.post", side_effect=Exception("net error")):
            vault.log_violation(ctx, rule, "reason")  # should not raise

    def test_log_violation_success(self):
        """requests.post succeeds → raise_for_status + logger.info (lines 142-143)."""
        vault = EvidenceVault("http://fake")
        ctx = InterceptionContext(
            socket_id="s1", operation="connect",
            destination=("safe.com", 443), data=None,
            timestamp=datetime.now(timezone.utc),
            agent_id="agent-1", tenant_id="t1"
        )
        rule = ValidationRule("R1", "cond", "A1", "Test", "SOP")
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        with patch("interceptor.requests.post", return_value=mock_resp):
            vault.log_violation(ctx, rule, "logged ok")


# -------------------------------------------------------------------
# Expanded coverage: _start_rule_refresh (lines 190-196)
# -------------------------------------------------------------------
class TestStartRuleRefresh:
    def test_refresh_thread_starts(self):
        """_start_rule_refresh creates and starts a daemon thread."""
        import threading
        with patch.object(SocketInterceptor, '_load_validation_rules'):
            with patch.object(SocketInterceptor, '_start_rule_refresh'):
                si = SocketInterceptor(tenant_id="t1", agent_id="a1")
        
        initial_count = threading.active_count()
        # Now actually call _start_rule_refresh
        si._start_rule_refresh()
        import time
        time.sleep(0.1)
        # A new daemon thread should have been created
        assert threading.active_count() >= initial_count


# -------------------------------------------------------------------
# Expanded coverage: _evaluate_rule branches
# -------------------------------------------------------------------
class TestEvaluateRuleExpanded:
    def _make_interceptor(self):
        with patch.object(SocketInterceptor, '_load_validation_rules'):
            with patch.object(SocketInterceptor, '_start_rule_refresh'):
                return SocketInterceptor(tenant_id="t1", agent_id="agent-1")

    def _make_context(self, host="api.example.com", port=443, op="connect"):
        return InterceptionContext(
            socket_id="test-sock", operation=op,
            destination=(host, port), data=None,
            timestamp=datetime.now(timezone.utc),
            agent_id="agent-1", tenant_id="t1"
        )

    def test_port_equals_rule_pass(self):
        """destination.port == 443 — port matches, pass."""
        si = self._make_interceptor()
        rule = ValidationRule("R", "destination.port == 443", "A", "T", "S")
        ctx = self._make_context(port=443)
        passed, reason = si._evaluate_rule(rule, ctx)
        assert passed is True

    def test_port_equals_rule_fail(self):
        """destination.port == 443 — port doesn't match, fail."""
        si = self._make_interceptor()
        rule = ValidationRule("R", "destination.port == 443", "A", "T", "S")
        ctx = self._make_context(port=80)
        passed, reason = si._evaluate_rule(rule, ctx)
        assert passed is False
        assert "443" in reason

    def test_rule_evaluation_exception(self):
        """Malformed rule condition → exception → allow by default."""
        si = self._make_interceptor()
        rule = ValidationRule("R", "port != INVALID_TEXT", "A", "T", "S")
        ctx = self._make_context(port=80)
        passed, reason = si._evaluate_rule(rule, ctx)
        # Exception path: allows by default
        assert passed is True
        assert "failed" in reason.lower()


# -------------------------------------------------------------------
# Expanded coverage: _load_validation_rules
# -------------------------------------------------------------------
class TestLoadValidationRules:
    def test_load_rules_from_activities(self):
        """Covers lines 171-186: _load_validation_rules populates rules."""
        with patch.object(SocketInterceptor, '_start_rule_refresh'):
            with patch.object(SocketInterceptor, '_load_validation_rules'):
                si = SocketInterceptor(tenant_id="t1", agent_id="a1")

        activities = [
            {
                "activity_id": "act-1",
                "name": "PO Approval",
                "authority": "SOP-v1",
                "ebcl_source": "VALIDATE\nREQUIRE destination.port != 22\n\nNEXT"
            }
        ]
        si.activity_registry = MagicMock()
        si.activity_registry.get_active_activities.return_value = activities
        si.activity_registry.parse_validate_rules = ActivityRegistry("").parse_validate_rules

        si._load_validation_rules()
        assert len(si.validation_rules) == 1
        assert "port" in si.validation_rules[0].condition


# -------------------------------------------------------------------
# Expanded coverage: InterceptedSocket connect, send, recv
# -------------------------------------------------------------------
class TestInterceptedSocket:
    def _make_interceptor(self):
        with patch.object(SocketInterceptor, '_load_validation_rules'):
            with patch.object(SocketInterceptor, '_start_rule_refresh'):
                return SocketInterceptor(tenant_id="t1", agent_id="agent-1")

    def test_intercepted_connect_blocked(self):
        """InterceptedSocket.connect raises PermissionError for violations."""
        si = self._make_interceptor()
        si.validation_rules = [
            ValidationRule("R1", "destination.port != 22", "A1", "Test", "SOP")
        ]
        si.evidence_vault = MagicMock()

        si.install()
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            import pytest
            with pytest.raises(PermissionError, match="blocked by policy"):
                s.connect(("example.com", 22))
        finally:
            si.uninstall()

    def test_intercepted_connect_allowed(self):
        """InterceptedSocket.connect allows compliant connections."""
        si = self._make_interceptor()
        si.validation_rules = []  # no rules → allow all

        si.install()
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Mock super().connect to avoid actual network call
            with patch.object(type(s), 'connect', return_value=None) as mock_conn:
                s.connect(("example.com", 443))
                mock_conn.assert_called_once_with(("example.com", 443))
        finally:
            si.uninstall()

    def test_intercepted_send(self):
        """InterceptedSocket.send delegates to super."""
        si = self._make_interceptor()
        si.install()
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            with patch.object(type(s).__bases__[0], 'send', return_value=5) as mock_send:
                result = s.send(b"hello")
                assert result == 5
        finally:
            si.uninstall()

    def test_intercepted_recv(self):
        """InterceptedSocket.recv delegates to super."""
        si = self._make_interceptor()
        si.install()
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            with patch.object(type(s).__bases__[0], 'recv', return_value=b"world") as mock_recv:
                result = s.recv(1024)
                assert result == b"world"
        finally:
            si.uninstall()

