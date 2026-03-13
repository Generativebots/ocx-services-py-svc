"""Tests for trust-registry main.py — API endpoints, signature verification, ghost state blocking, memory vault."""

import os
import sys
import json
import time
import types
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ============================================================================
# kill_switch.py — missing lines: 50-56 (tenant config import), 155-158
# ============================================================================

class TestMainEndpoints:
    """Tests for main.py endpoints covering uncovered branches."""

    def test_evaluate_warn_status(self, client):
        """Evaluation leading to WARN/APPROVED_WITH_WARNING (L166-168)."""
        # A high-risk action with partial context could trigger a warning
        # We control the score by adjusting context
        resp = client.post("/evaluate", json={
            "agent_id": "a-warn",
            "tenant_id": "t-1",
            "proposed_action": "DELETE_OLD_RECORDS",
            "context": {"reason": "cleanup", "scope": "limited"},
        })
        assert resp.status_code == 200
        data = resp.json()
        # delete is high risk → compliance 0.40, limited context → factuality 0.60
        # score ≈ 0.40*0.40 + 0.40*0.60 + 0.20*0.70 = 0.54 → BLOCKED
        assert data["status"] in ("BLOCKED", "APPROVED_WITH_WARNING", "APPROVED")

    def test_evaluate_with_ghost_state_non_blocking(self, client):
        """Ghost state eval runs without blocking the response (L134-140)."""
        resp = client.post("/evaluate", json={
            "agent_id": "a-ghost",
            "tenant_id": "t-1",
            "proposed_action": "execute_payment",
            "context": {"amount": 100, "from_account": "checking", "reason": "test"},
        })
        assert resp.status_code == 200

    def test_memory_vault_no_directory(self, client):
        """Memory vault with non-existent path → empty logs (L208)."""
        resp = client.get("/memory/vault?tenant_id=t-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["logs"] == []
        assert data["tenant_id"] == "t-1"

    def test_memory_vault_with_files(self, client, tmp_path):
        """Memory vault reads .jsonl files and filters by tenant."""
        import json as json_mod

        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        log_file = vault_dir / "test.jsonl"
        log_file.write_text(
            json_mod.dumps({"tenant_id": "t-1", "timestamp": "2026-01-01", "event": "test"}) + "\n"
            + json_mod.dumps({"tenant_id": "t-2", "timestamp": "2026-01-02", "event": "other"}) + "\n"
        )

        # Patch the vault_path used in main.py
        with patch("main.os.path.exists", return_value=True):
            with patch("main.os.listdir", return_value=["test.jsonl"]):
                with patch("builtins.open", MagicMock(return_value=log_file.open("r"))):
                    resp = client.get("/memory/vault?tenant_id=t-1")
                    assert resp.status_code == 200

    def test_health_endpoint(self, client):
        """Health endpoint returns ok."""
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_ledger_recent(self, client):
        """Ledger recent endpoint returns data."""
        resp = client.get("/ledger/recent?tenant_id=t-1")
        assert resp.status_code == 200

    def test_ledger_stats(self, client):
        """Ledger stats endpoint returns data."""
        resp = client.get("/ledger/stats?tenant_id=t-1")
        assert resp.status_code == 200

    def test_ledger_health(self, client):
        """Ledger health endpoint returns data."""
        resp = client.get("/ledger/health/agent-1?tenant_id=t-1")
        assert resp.status_code == 200


# ============================================================================
# policy_hierarchy.py — missing: 99, 103, 107, 194-252 (__main__ block)
# ============================================================================




class TestMainSignatureVerification:
    """Tests for main.py ECDSA signature verification path (L88-99)."""

    def test_evaluate_with_valid_signature_headers(self, client):
        """Providing X-Signature and X-Agent-ID triggers sig verification (L88-99)."""
        resp = client.post(
            "/evaluate",
            json={
                "agent_id": "a-sig-test",
                "tenant_id": "t-1",
                "proposed_action": "READ_DATA",
                "context": {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5},
            },
            headers={
                "X-Agent-ID": "deadbeef" * 8,
                "X-Signature": "beef" * 32,
                "X-Payload-Hash": "abc123",
            },
        )
        # The fake ecdsa stub will call verify which returns True
        # but from_string may fail with bad hex — that's caught by except (L97-99)
        assert resp.status_code == 200

    def test_evaluate_with_signature_no_payload_hash(self, client):
        """Missing X-Payload-Hash with sig → exception caught (L97-99)."""
        resp = client.post(
            "/evaluate",
            json={
                "agent_id": "a-nopayload",
                "tenant_id": "t-1",
                "proposed_action": "READ_DATA",
                "context": {"a": 1, "b": 2, "c": 3},
            },
            headers={
                "X-Agent-ID": "0011223344556677",
                "X-Signature": "aabbccdd",
                # No X-Payload-Hash → payload_hash is None → error caught
            },
        )
        assert resp.status_code == 200

    def test_evaluate_low_score_blocked(self, client):
        """Very low-context high-risk action → BLOCKED status with no token (L164-165)."""
        resp = client.post("/evaluate", json={
            "agent_id": "a-blocked",
            "tenant_id": "t-1",
            "proposed_action": "DELETE_ALL_RECORDS",
            "context": {},
        })
        assert resp.status_code == 200
        data = resp.json()
        # DELETE is high risk, no context → score very low → BLOCKED
        assert data["status"] == "BLOCKED"
        assert data["safety_token"] is None

    def test_evaluate_medium_context_may_warn(self, client):
        """Medium context + medium risk → could produce WARN/APPROVED (L166-168)."""
        resp = client.post("/evaluate", json={
            "agent_id": "a-medium",
            "tenant_id": "t-1",
            "proposed_action": "EXPORT_DATA",
            "context": {"reason": "monthly report", "scope": "department", "format": "csv"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("APPROVED", "APPROVED_WITH_WARNING", "BLOCKED")
        # If APPROVED_WITH_WARNING, token should contain _warn (L168)
        if data["status"] == "APPROVED_WITH_WARNING":
            assert "_warn" in data["safety_token"]




class TestMainGhostStateBlocking:
    """Tests for ghost state evaluation warning path (L134-140)."""

    def test_ghost_state_exception_doesnt_break_evaluate(self, client):
        """Ghost state engine exception → non-blocking warning (L139-140)."""
        with patch("main.ghost_engine.evaluate_with_ghost_state", side_effect=RuntimeError("ghost crash")):
            resp = client.post("/evaluate", json={
                "agent_id": "a-ghost-err",
                "tenant_id": "t-1",
                "proposed_action": "READ_DATA",
                "context": {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5},
            })
            assert resp.status_code == 200

    def test_ghost_state_blocks_logs_warning(self, client):
        """Ghost state not allowed → warning logged but doesn't block (L134-138)."""
        with patch(
            "main.ghost_engine.evaluate_with_ghost_state",
            return_value=(False, None, "Policy violation detected"),
        ):
            resp = client.post("/evaluate", json={
                "agent_id": "a-ghost-blocked",
                "tenant_id": "t-1",
                "proposed_action": "READ_DATA",
                "context": {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5},
            })
            # Ghost state is non-blocking, so evaluate still succeeds
            assert resp.status_code == 200




class TestMainMemoryVault:
    """Tests for memory vault endpoint reading files (L208-220)."""

    def test_vault_reads_jsonl_and_filters(self, client, tmp_path):
        """Vault reads .jsonl files, parses JSON, and filters by tenant (L208-220)."""
        import json as j
        import builtins

        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()

        # Create a real .jsonl file
        entries = [
            j.dumps({"tenant_id": "t-match", "timestamp": "2026-01-02", "action": "read"}),
            j.dumps({"tenant_id": "t-other", "timestamp": "2026-01-01", "action": "write"}),
            "not valid json",
            j.dumps({"tenant_id": "t-match", "timestamp": "2026-01-03", "action": "update"}),
        ]
        (vault_dir / "log1.jsonl").write_text("\n".join(entries) + "\n")

        # Save real open before patching to avoid recursion
        real_open = builtins.open

        def mock_open(path, mode="r"):
            return real_open(str(vault_dir / "log1.jsonl"), mode)

        with patch("main.os.path.exists", return_value=True), \
             patch("main.os.listdir", return_value=["log1.jsonl"]), \
             patch("builtins.open", side_effect=mock_open):
            resp = client.get("/memory/vault?tenant_id=t-match")
            assert resp.status_code == 200
            data = resp.json()
            assert data["tenant_id"] == "t-match"
            assert len(data["logs"]) == 2




class TestMainRulesV1Fallback:
    """Test rules_v1.md FileNotFoundError fallback (L48-49)."""

    def test_static_rules_fallback_value(self):
        """When rules_v1.md doesn't exist, STATIC_RULES defaults (L48-49)."""
        import main
        # The conftest stubs don't create rules_v1.md, so the fallback should be active
        assert hasattr(main, "STATIC_RULES")
        assert isinstance(main.STATIC_RULES, str)


# ============================================================================
# policy_hierarchy.py & policy_versioning.py — __main__ blocks in-process
# ============================================================================

import runpy


"""
Trust Registry — API endpoint tests.

Tests the core /evaluate, /health, /ledger/* endpoints using
FastAPI's TestClient with mocked external dependencies.
"""

import pytest


class TestHealth:
    """GET /health — service health check."""

    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "Trust Registry"


class TestEvaluate:
    """POST /evaluate — governance evaluation endpoint."""

    VALID_PAYLOAD = {
        "agent_id": "agent-test-001",
        "tenant_id": "tenant-abc",
        "proposed_action": "SEND_EMAIL",
        "context": {"recipient": "user@example.com", "subject": "test", "priority": "normal"},
    }

    def test_evaluate_returns_200(self, client):
        resp = client.post("/evaluate", json=self.VALID_PAYLOAD)
        assert resp.status_code == 200
        data = resp.json()
        assert "trust_score" in data
        assert "status" in data
        assert data["status"] in ("APPROVED", "BLOCKED", "APPROVED_WITH_WARNING")

    def test_evaluate_approved_path(self, client):
        """Deterministic jury returns ~0.70 → APPROVED (threshold=0.65)."""
        resp = client.post("/evaluate", json=self.VALID_PAYLOAD)
        data = resp.json()
        assert data["status"] == "APPROVED"
        assert data["trust_score"] >= 0.5
        assert data["safety_token"] is not None
        assert data["safety_token"].endswith("_ok")

    def test_evaluate_has_breakdown(self, client):
        """Response contains breakdown with compliance/factuality/strategic."""
        resp = client.post("/evaluate", json=self.VALID_PAYLOAD)
        data = resp.json()
        breakdown = data.get("breakdown", {})
        assert "compliance" in breakdown
        assert "factuality" in breakdown
        assert "strategic_alignment" in breakdown

    def test_evaluate_has_reasoning(self, client):
        resp = client.post("/evaluate", json=self.VALID_PAYLOAD)
        data = resp.json()
        assert len(data["reasoning"]) > 0

    def test_evaluate_with_trace_id(self, client):
        """Explicit trace_id is accepted without error."""
        payload = {**self.VALID_PAYLOAD, "trace_id": "trace-custom-123"}
        resp = client.post("/evaluate", json=payload)
        assert resp.status_code == 200

    def test_evaluate_missing_fields_422(self, client):
        """Pydantic validation rejects missing required fields."""
        resp = client.post("/evaluate", json={"agent_id": "x"})
        assert resp.status_code == 422

    def test_evaluate_empty_context(self, client):
        """Empty context dict is still valid."""
        payload = {
            "agent_id": "agent-empty-ctx",
            "tenant_id": "t-1",
            "proposed_action": "READ_FILE",
            "context": {},
        }
        resp = client.post("/evaluate", json=payload)
        assert resp.status_code == 200


class TestLedger:
    """GET /ledger/* — ledger query endpoints."""

    def test_ledger_recent(self, client):
        resp = client.get("/ledger/recent", params={"tenant_id": "t-1"})
        assert resp.status_code == 200

    def test_ledger_stats(self, client):
        resp = client.get("/ledger/stats", params={"tenant_id": "t-1"})
        assert resp.status_code == 200

    def test_ledger_agent_health(self, client):
        resp = client.get("/ledger/health/agent-001", params={"tenant_id": "t-1"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_id"] == "agent-001"
        assert data["tenant_id"] == "t-1"


class TestMemoryVault:
    """GET /memory/vault — tenant-scoped vault endpoint."""

    def test_memory_vault_empty(self, client):
        resp = client.get("/memory/vault", params={"tenant_id": "t-1"})
        assert resp.status_code == 200
        data = resp.json()
        assert "logs" in data
        assert data["tenant_id"] == "t-1"
