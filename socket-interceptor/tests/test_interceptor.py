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
