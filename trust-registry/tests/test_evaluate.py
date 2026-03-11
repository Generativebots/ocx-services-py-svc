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
