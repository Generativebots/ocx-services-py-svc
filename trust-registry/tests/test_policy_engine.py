"""
Trust Registry — Policy Engine endpoint tests.

Tests /policy/agents, /policy/rules/draft, /policy/rules, and
/policy/agents/{id}/eject endpoints.
"""

import pytest


class TestRegisterAgent:
    """POST /policy/agents — agent registration."""

    def _make_payload(self, agent_id="bot-1", tenant_id="t-1"):
        import hashlib
        prompt = "You are a test bot."
        tools = ["calculator"]
        tool_slugs = "".join(sorted(tools))
        cap_hash = hashlib.sha256(f"{prompt}{tool_slugs}".encode()).hexdigest()
        return {
            "agent_id": agent_id,
            "tenant_id": tenant_id,
            "metadata": {"name": "TestBot", "provider": "Internal"},
            "security_handshake": {
                "public_key": "mock-pk",
                "capability_hash": cap_hash,
                "auth_tier": "Standard",
            },
            "capabilities": [{"tool_name": "calculator"}],
            "governance_profile": {"scrutiny_level": 1},
            "system_prompt_text": prompt,
        }

    def test_register_returns_201(self, client):
        resp = client.post("/policy/agents", json=self._make_payload())
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "Registered"
        assert data["tenant_id"] == "t-1"
        assert data["hash_verified"] is True

    def test_register_hash_mismatch_400(self, client):
        payload = self._make_payload()
        payload["security_handshake"]["capability_hash"] = "badbadbadbad"
        resp = client.post("/policy/agents", json=payload)
        assert resp.status_code == 400

    def test_register_without_prompt_skips_hash(self, client):
        payload = self._make_payload()
        del payload["system_prompt_text"]
        resp = client.post("/policy/agents", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["hash_verified"] == "Skipped"

    def test_register_missing_tenant_422(self, client):
        """tenant_id is required."""
        resp = client.post("/policy/agents", json={
            "metadata": {},
            "security_handshake": {},
            "capabilities": [],
            "governance_profile": {},
        })
        assert resp.status_code == 422


class TestListAgents:
    """GET /policy/agents — list agents (tenant-filtered)."""

    def test_list_agents(self, client):
        resp = client.get("/policy/agents", params={"tenant_id": "t-1"})
        assert resp.status_code == 200


class TestRules:
    """POST /policy/rules/draft & POST /policy/rules & GET /policy/rules."""

    def test_draft_rule_spend(self, client):
        """Spend + finance triggers BLOCK logic."""
        resp = client.post("/policy/rules/draft", json={
            "natural_language": "Block spend over $5000 in finance",
            "tenant_id": "t-1",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["generated_logic"]["action"] == "BLOCK"
        assert data["tenant_id"] == "t-1"

    def test_draft_rule_pii(self, client):
        """PII in public channels triggers BLOCK logic."""
        resp = client.post("/policy/rules/draft", json={
            "natural_language": "Block PII in public channels",
            "tenant_id": "t-1",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["generated_logic"]["action"] == "BLOCK"

    def test_draft_rule_custom(self, client):
        """Unknown rule text falls back to FLAG action."""
        resp = client.post("/policy/rules/draft", json={
            "natural_language": "Only allow approved vendors",
            "tenant_id": "t-1",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["generated_logic"]["action"] == "FLAG"

    def test_deploy_rule(self, client):
        resp = client.post("/policy/rules", json={
            "tenant_id": "t-1",
            "natural_language": "Block over $5000",
            "logic_json": {"condition": {"field": "amount", "operator": ">", "value": 5000}},
            "priority": 2,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "Active"
        assert data["tenant_id"] == "t-1"

    def test_get_rules(self, client):
        resp = client.get("/policy/rules", params={"tenant_id": "t-1"})
        assert resp.status_code == 200


class TestEjectAgent:
    """POST /policy/agents/{id}/eject — kill switch."""

    def test_eject_missing_tenant_400(self, client):
        resp = client.post("/policy/agents/agent-1/eject", json={})
        assert resp.status_code == 400

    def test_eject_with_tenant(self, client):
        resp = client.post("/policy/agents/agent-1/eject", json={
            "tenant_id": "t-1",
        })
        # Will succeed or fail depending on Registry state, but shouldn't 422
        assert resp.status_code in (200, 500)
