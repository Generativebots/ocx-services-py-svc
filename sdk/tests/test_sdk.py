"""Tests for sdk/client.py, sdk/decorators.py, sdk/middleware.py"""
import pytest
from unittest.mock import patch, MagicMock

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from client import OCXClient, GovernanceResult, JITTokenInfo


class TestGovernanceResult:
    def test_creation_defaults(self):
        r = GovernanceResult()
        assert r.verdict == "ALLOW"
        assert r.trust_score == 0.0
        assert r.escrow_id == ""

    def test_creation_custom(self):
        r = GovernanceResult(verdict="BLOCK", reason="Policy violation", trust_score=0.2)
        assert r.verdict == "BLOCK"
        assert r.reason == "Policy violation"

    def test_escrow_result(self):
        r = GovernanceResult(verdict="ESCROW", escrow_id="esc-123")
        assert r.escrow_id == "esc-123"

    def test_jit_token_field(self):
        r = GovernanceResult()
        assert r.jit_token is None

    def test_sop_drift_field(self):
        r = GovernanceResult()
        assert r.sop_drift is None

    def test_speculative_hash_default(self):
        r = GovernanceResult()
        assert r.speculative_hash == ""


class TestOCXClient:
    def test_init(self):
        client = OCXClient(
            gateway_url="https://gateway.example.com",
            tenant_id="acme",
            api_key="test-key",
        )
        assert client.gateway_url == "https://gateway.example.com"
        assert client.tenant_id == "acme"

    def test_init_sets_session(self):
        client = OCXClient("https://gw.test", "acme", "key")
        assert hasattr(client, '_session') or hasattr(client, 'session') or hasattr(client, 'api_key')


class TestDecorators:
    def test_governed_decorator_import(self):
        from decorators import governed
        assert callable(governed)

    def test_tool_blocked_error(self):
        from decorators import ToolBlockedError
        err = ToolBlockedError("payment", "Policy violation", "tx-123")
        assert err.tool_name == "payment"
        assert err.reason == "Policy violation"
        assert err.transaction_id == "tx-123"

    def test_tool_escrowed_error(self):
        from decorators import ToolEscrowedError
        err = ToolEscrowedError("transfer", "esc-1", "tx-456")
        assert err.tool_name == "transfer"
        assert err.escrow_id == "esc-1"

    def test_tool_escalated_error(self):
        from decorators import ToolEscalatedError
        err = ToolEscalatedError("admin-action", "Needs approval", "tx-789")
        assert err.tool_name == "admin-action"

    def test_blocked_inherits_exception(self):
        from decorators import ToolBlockedError
        assert issubclass(ToolBlockedError, Exception)

    def test_escrowed_inherits_exception(self):
        from decorators import ToolEscrowedError
        assert issubclass(ToolEscrowedError, Exception)


class TestMiddleware:
    def test_protocol_bridge_import(self):
        from middleware import OCXProtocolBridge
        assert OCXProtocolBridge is not None

    def test_fastapi_middleware_import(self):
        from middleware import OCXFastAPIMiddleware
        assert OCXFastAPIMiddleware is not None

    def test_flask_middleware_import(self):
        from middleware import OCXFlaskMiddleware
        assert OCXFlaskMiddleware is not None

    def test_django_middleware_import(self):
        from middleware import OCXDjangoMiddleware
        assert OCXDjangoMiddleware is not None

    def test_mcp_middleware_import(self):
        from middleware import OCXMCPServerMiddleware
        assert OCXMCPServerMiddleware is not None

    def test_a2a_middleware_import(self):
        from middleware import OCXA2AMiddleware
        assert OCXA2AMiddleware is not None
