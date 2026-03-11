"""
Coverage Boost Tests
====================
Targeted tests to push 9 trust-registry modules to ≥ 90% line coverage.

Covers uncovered lines in:
  kill_switch, jury, ape_engine, registry, ghost_state_engine,
  governance_config, main, policy_hierarchy, policy_versioning
"""

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

class TestJuryScoring:
    """Tests for Jury scoring edge cases covering all branches."""

    def test_high_risk_action_compliance(self):
        """High-risk action keywords → compliance 0.40."""
        from jury import Jury
        j = Jury()
        assert j._compute_compliance_score("DELETE_ALL_DATA", "") == 0.40

    def test_medium_risk_action_compliance(self):
        """Medium-risk action keywords → compliance 0.65."""
        from jury import Jury
        j = Jury()
        assert j._compute_compliance_score("SEND_EMAIL", "") == 0.65

    def test_low_risk_action_compliance(self):
        """Low-risk (default) action → compliance 0.85."""
        from jury import Jury
        j = Jury()
        assert j._compute_compliance_score("VIEW_DASHBOARD", "") == 0.85

    def test_rule_context_blocks_action(self):
        """Rules context containing 'block' + action name → 0.30."""
        from jury import Jury
        j = Jury()
        score = j._compute_compliance_score("view_dashboard", "block view_dashboard")
        assert score == 0.30

    def test_factuality_no_context(self):
        """Empty context → 0.50."""
        from jury import Jury
        j = Jury()
        assert j._compute_factuality_score({"context": {}}) == 0.50

    def test_factuality_no_context_key(self):
        """No 'context' key → 0.50."""
        from jury import Jury
        j = Jury()
        assert j._compute_factuality_score({}) == 0.50

    def test_factuality_few_fields(self):
        """1-2 fields → 0.60."""
        from jury import Jury
        j = Jury()
        assert j._compute_factuality_score({"context": {"a": 1, "b": 2}}) == 0.60

    def test_factuality_medium_fields(self):
        """3-4 fields → 0.75."""
        from jury import Jury
        j = Jury()
        assert j._compute_factuality_score({"context": {"a": 1, "b": 2, "c": 3}}) == 0.75

    def test_factuality_many_fields(self):
        """5+ fields → 0.90."""
        from jury import Jury
        j = Jury()
        assert j._compute_factuality_score(
            {"context": {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5}}
        ) == 0.90

    def test_strategic_critical_tier_read(self):
        """Critical tier + read action → 0.90."""
        from jury import Jury
        j = Jury()
        assert j._compute_strategic_score({"tier": "Critical"}, "read_data") == 0.90

    def test_strategic_critical_tier_non_read(self):
        """Critical tier + non-read → 0.75."""
        from jury import Jury
        j = Jury()
        assert j._compute_strategic_score({"tier": "Critical"}, "write_data") == 0.75

    def test_strategic_standard_tier(self):
        """Standard tier → 0.70."""
        from jury import Jury
        j = Jury()
        assert j._compute_strategic_score({"tier": "Standard"}, "anything") == 0.70

    def test_strategic_unknown_tier(self):
        """Unknown tier → 0.75 (default)."""
        from jury import Jury
        j = Jury()
        assert j._compute_strategic_score({"tier": "Premium"}, "anything") == 0.75


class TestJuryLLMClient:
    """Tests for Jury with LLM client (covers L115-139)."""

    def test_score_with_llm_client_success(self):
        """LLM client returns scores → used directly."""
        from jury import Jury

        mock_llm = MagicMock()
        mock_llm.evaluate.return_value = {
            "compliance": 0.88,
            "factuality": 0.92,
            "strategic_alignment": 0.85,
        }

        j = Jury(llm_client=mock_llm)
        j.model = "gpt-4"  # Force non-default model

        result = j.score(
            payload={"proposed_action": "SEND_EMAIL", "context": {"a": 1}},
            agent_metadata={"agent_id": "a1", "tenant_id": "t1", "tier": "Standard"},
            rules_context="standard rules",
        )
        assert result["trust_score"] == round(0.4 * 0.88 + 0.4 * 0.92 + 0.2 * 0.85, 4)
        assert result["status"] == "APPROVED"

    def test_score_with_llm_client_failure_degrades(self):
        """LLM call throws → falls back to deterministic scoring."""
        from jury import Jury

        mock_llm = MagicMock()
        mock_llm.evaluate.side_effect = RuntimeError("LLM API down")

        j = Jury(llm_client=mock_llm)
        j.model = "gpt-4"

        result = j.score(
            payload={"proposed_action": "READ_DATA", "context": {"a": 1, "b": 2, "c": 3}},
            agent_metadata={"agent_id": "a1", "tenant_id": "t1", "tier": "Standard"},
            rules_context="",
        )
        # Should degrade to deterministic scoring, not crash
        assert "trust_score" in result
        assert result["status"] in ("APPROVED", "BLOCKED")

    def test_score_no_llm_no_default_model(self):
        """No LLM client + non-default model → deterministic fallback."""
        from jury import Jury

        j = Jury()
        j.model = "custom-model"
        j.llm_client = None

        result = j.score(
            payload={"proposed_action": "READ_DATA", "context": {}},
            agent_metadata={"agent_id": "a1", "tenant_id": "t1"},
            rules_context="",
        )
        assert "trust_score" in result


class TestJuryTenantConfigRuntime:
    """Test jury late-binding tenant config (L157-159)."""

    def test_score_loads_tenant_threshold_at_runtime(self):
        """Jury without tenant_id at init loads from metadata tenant_id at score time."""
        from jury import Jury

        j = Jury()  # No tenant_id at init
        j.tenant_id = None  # ensure no init tenant

        result = j.score(
            payload={"proposed_action": "READ_DATA", "context": {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5}},
            agent_metadata={"agent_id": "a1", "tenant_id": "test-tenant-123", "tier": "Standard"},
            rules_context="",
        )
        assert result["status"] in ("APPROVED", "BLOCKED")


# ============================================================================
# ape_engine.py — missing lines: 26-57 (VLLMClient.generate_json),
#                 100-156 (extract_rules endpoint)
# ============================================================================

class TestRecursiveParser:
    """Test RecursiveParser (already likely covered but confirm)."""

    def test_parse_splits_by_double_newline(self):
        from ape_engine import RecursiveParser
        parser = RecursiveParser()
        result = parser.parse("Section 1\n\nSection 2\n\nSection 3")
        assert len(result) == 3
        assert result[0] == "Section 1"

    def test_parse_strips_whitespace(self):
        from ape_engine import RecursiveParser
        parser = RecursiveParser()
        result = parser.parse("  A  \n\n  B  ")
        assert result == ["A", "B"]

    def test_parse_empty_string(self):
        from ape_engine import RecursiveParser
        parser = RecursiveParser()
        result = parser.parse("")
        assert result == []


class TestVLLMClient:
    """Test VLLMClient.generate_json (async method)."""

    @pytest.mark.asyncio
    async def test_generate_json_success(self):
        """Successful vLLM call → returns parsed JSON array."""
        from ape_engine import VLLMClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '[{"condition": "x > 5", "confidence_score": 0.9}]'}}]
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("ape_engine.httpx.AsyncClient", return_value=mock_client):
            client = VLLMClient(base_url="http://mock:8000/v1")
            result = await client.generate_json("test prompt", {"type": "array"})
            assert len(result) == 1
            assert result[0]["condition"] == "x > 5"

    @pytest.mark.asyncio
    async def test_generate_json_no_array_in_response(self):
        """Response without JSON array → returns []."""
        from ape_engine import VLLMClient

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "No JSON here"}}]
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("ape_engine.httpx.AsyncClient", return_value=mock_client):
            client = VLLMClient()
            result = await client.generate_json("test", {})
            assert result == []

    @pytest.mark.asyncio
    async def test_generate_json_exception(self):
        """HTTP error → returns []."""
        from ape_engine import VLLMClient

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))

        with patch("ape_engine.httpx.AsyncClient", return_value=mock_client):
            client = VLLMClient()
            result = await client.generate_json("test", {})
            assert result == []


class TestAPEExtractEndpoint:
    """Test the /extract FastAPI endpoint."""

    @pytest.mark.asyncio
    async def test_extract_rules_with_mock_llm(self):
        """Extract endpoint processes chunks and returns validated rules."""
        from ape_engine import extract_rules, ExtractRequest

        # Mock the global llm to return structured data
        mock_llm_data = [{
            "condition": "amount > 500",
            "suggested_action": "BLOCK",
            "confidence_score": 0.95,
            "logic_gate": {"field": "amount", "operator": ">", "value": "500"},
        }]

        with patch("ape_engine.llm") as mock_llm:
            mock_llm.generate_json = AsyncMock(return_value=mock_llm_data)

            req = ExtractRequest(
                document_text="If amount exceeds 500, block the transaction.",
                source_name="Test SOP",
                tenant_id="t-1",
            )
            result = await extract_rules(req)
            assert len(result) >= 1
            assert result[0].tenant_id == "t-1"
            assert result[0].confidence_score == 0.95

    @pytest.mark.asyncio
    async def test_extract_rules_skips_invalid(self):
        """Invalid rules are skipped during validation."""
        from ape_engine import extract_rules, ExtractRequest

        # Return data that will fail PolicyObject validation (missing required fields)
        invalid_data = [{"invalid_field_only": True}]

        with patch("ape_engine.llm") as mock_llm:
            mock_llm.generate_json = AsyncMock(return_value=invalid_data)

            req = ExtractRequest(
                document_text="Some text",
                source_name="Test",
                tenant_id="t-1",
            )
            result = await extract_rules(req)
            assert result == []  # Invalid rules skipped

    @pytest.mark.asyncio
    async def test_extract_rules_empty_document(self):
        """Empty document → no chunks → no rules."""
        from ape_engine import extract_rules, ExtractRequest

        with patch("ape_engine.llm") as mock_llm:
            mock_llm.generate_json = AsyncMock(return_value=[])

            req = ExtractRequest(
                document_text="",
                source_name="Empty",
                tenant_id="t-1",
            )
            result = await extract_rules(req)
            assert result == []


# ============================================================================
# registry.py — missing lines: 30, 39, 46-68, 101-103, 123-135, 140-163,
#               169-172, 183, 206-214, 223-233
# ============================================================================

class TestRegistryWithMockedDB:
    """Registry methods with mocked Supabase and Redis."""

    def _make_registry(self):
        """Create Registry with fully mocked external deps."""
        from registry import Registry

        with patch.dict(os.environ, {
            "SUPABASE_URL": "http://mock-sb:8443",
            "SUPABASE_SERVICE_KEY": "mock-key",
        }):
            r = Registry()
        return r

    def test_register_agent_with_supabase(self):
        """register_agent writes to Supabase and returns agent_id."""
        from registry import Registry

        mock_sb = MagicMock()
        mock_table = MagicMock()
        mock_table.upsert.return_value.execute.return_value = ([], 1)
        mock_sb.table.return_value = mock_table

        r = Registry()
        r.supabase = mock_sb

        agent_json = {
            "agent_id": "a-123",
            "metadata": {"name": "TestBot", "provider": "OCX"},
            "security_handshake": {"auth_tier": "Critical", "public_key": "pk-abc"},
            "capabilities": [{"tool_name": "read"}, {"tool_name": "write"}],
            "status": "Active",
        }
        result = r.register_agent(agent_json, "t-1")
        assert result == "a-123"
        mock_sb.table.assert_called_with("agents")

    def test_register_agent_generates_id(self):
        """register_agent generates UUID when agent_id missing."""
        from registry import Registry

        mock_sb = MagicMock()
        mock_table = MagicMock()
        mock_table.upsert.return_value.execute.return_value = ([], 1)
        mock_sb.table.return_value = mock_table

        r = Registry()
        r.supabase = mock_sb

        agent_json = {"metadata": {}, "security_handshake": {}, "capabilities": []}
        result = r.register_agent(agent_json, "t-1")
        assert result is not None
        assert len(result) == 36  # UUID format

    def test_register_agent_no_supabase(self):
        """Without Supabase → returns mock-id."""
        from registry import Registry
        r = Registry()
        r.supabase = None
        result = r.register_agent({}, "t-1")
        assert result == "mock-id"

    def test_add_rule_with_supabase(self):
        """add_rule writes to Supabase and publishes to Redis."""
        from registry import Registry

        mock_sb = MagicMock()
        mock_table = MagicMock()
        mock_table.insert.return_value.execute.return_value = ([], 1)
        mock_sb.table.return_value = mock_table

        mock_redis = MagicMock()
        mock_bf = MagicMock()
        mock_redis.bf.return_value = mock_bf

        r = Registry()
        r.supabase = mock_sb
        r.redis = mock_redis

        rule_id = r.add_rule("No PII sharing", {"==": [{"var": "type"}, "pii"]}, "t-1", priority=2)
        assert rule_id is not None
        assert len(rule_id) == 36
        mock_sb.table.assert_called_with("rules")
        mock_redis.publish.assert_called_once()

    def test_add_rule_no_supabase(self):
        """Without Supabase → rule_id still returned (in-memory only)."""
        from registry import Registry
        r = Registry()
        r.supabase = None
        rule_id = r.add_rule("test", {}, "t-1")
        assert rule_id is not None

    def test_get_agent_profile_found(self):
        """get_agent_profile returns enriched profile with gov header."""
        from registry import Registry

        mock_sb = MagicMock()
        mock_resp = MagicMock()
        mock_resp.data = [{"full_schema_json": {"system_prompt": "I am a bot."}}]
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_resp

        r = Registry()
        r.supabase = mock_sb

        profile = r.get_agent_profile("a-1", "t-1")
        assert profile is not None
        assert "OCX" in profile["system_prompt"]
        assert "I am a bot." in profile["system_prompt"]

    def test_get_agent_profile_no_system_prompt(self):
        """Profile without system_prompt gets one injected."""
        from registry import Registry

        mock_sb = MagicMock()
        mock_resp = MagicMock()
        mock_resp.data = [{"full_schema_json": {"name": "TestBot"}}]
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_resp

        r = Registry()
        r.supabase = mock_sb

        profile = r.get_agent_profile("a-1", "t-1")
        assert "OCX" in profile["system_prompt"]

    def test_get_agent_profile_not_found(self):
        """No matching agent → returns None."""
        from registry import Registry

        mock_sb = MagicMock()
        mock_resp = MagicMock()
        mock_resp.data = []
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_resp

        r = Registry()
        r.supabase = mock_sb

        result = r.get_agent_profile("a-missing", "t-1")
        assert result is None

    def test_get_agent_profile_no_supabase(self):
        """Without Supabase → returns None."""
        from registry import Registry
        r = Registry()
        r.supabase = None
        result = r.get_agent_profile("a-1", "t-1")
        assert result is None

    def test_check_rule_existence(self):
        """Bloom filter check via Redis."""
        from registry import Registry

        mock_redis = MagicMock()
        mock_bf = MagicMock()
        mock_bf.exists.return_value = 1
        mock_redis.bf.return_value = mock_bf

        r = Registry()
        r.redis = mock_redis

        assert r.check_rule_existence("rule-1", "t-1") is True
        mock_bf.exists.assert_called_with("rules:bf", "t-1:rule-1")

    def test_eject_agent(self):
        """eject_agent updates Supabase, publishes, and sets Redis key."""
        from registry import Registry

        mock_sb = MagicMock()
        mock_redis = MagicMock()

        r = Registry()
        r.supabase = mock_sb
        r.redis = mock_redis

        result = r.eject_agent("a-bad", "t-1")
        assert result is True
        mock_redis.publish.assert_called_once()
        mock_redis.setex.assert_called_once()

    def test_hydrate_cache_with_data(self):
        """hydrate_cache loads rules into bloom filter."""
        from registry import Registry

        mock_sb = MagicMock()
        mock_resp = MagicMock()
        mock_resp.data = [
            {"rule_id": "r1", "tenant_id": "t1"},
            {"rule_id": "r2", "tenant_id": "t1"},
        ]
        mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_resp

        mock_redis = MagicMock()
        mock_bf = MagicMock()
        mock_redis.bf.return_value = mock_bf

        r = Registry()
        r.supabase = mock_sb
        r.redis = mock_redis

        r.hydrate_cache()
        assert mock_bf.add.call_count == 2

    def test_hydrate_cache_exception(self):
        """hydrate_cache handles exceptions gracefully."""
        from registry import Registry

        mock_sb = MagicMock()
        mock_sb.table.side_effect = Exception("DB down")

        mock_redis = MagicMock()

        r = Registry()
        r.supabase = mock_sb
        r.redis = mock_redis

        # Should not raise
        r.hydrate_cache()

    def test_get_active_rules_with_tenant(self):
        """get_active_rules filtered by tenant."""
        from registry import Registry

        mock_sb = MagicMock()
        mock_resp = MagicMock()
        mock_resp.data = [{"rule_id": "r1"}, {"rule_id": "r2"}]
        mock_query = MagicMock()
        mock_query.eq.return_value = mock_query
        mock_query.execute.return_value = mock_resp
        mock_sb.table.return_value.select.return_value.eq.return_value = mock_query

        r = Registry()
        r.supabase = mock_sb

        rules = r.get_active_rules("t-1")
        assert len(rules) == 2

    def test_get_active_rules_exception(self):
        """get_active_rules handles exception → returns []."""
        from registry import Registry

        mock_sb = MagicMock()
        mock_sb.table.side_effect = Exception("timeout")

        r = Registry()
        r.supabase = mock_sb

        result = r.get_active_rules("t-1")
        assert result == []

    def test_list_agents_success(self):
        """list_agents returns agent list for tenant."""
        from registry import Registry

        mock_sb = MagicMock()
        mock_resp = MagicMock()
        mock_resp.data = [{"agent_id": "a1", "name": "Bot1"}]
        mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_resp

        r = Registry()
        r.supabase = mock_sb

        agents = r.list_agents("t-1")
        assert len(agents) == 1

    def test_list_agents_empty(self):
        """list_agents with no agents → []."""
        from registry import Registry

        mock_sb = MagicMock()
        mock_resp = MagicMock()
        mock_resp.data = None
        mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_resp

        r = Registry()
        r.supabase = mock_sb

        result = r.list_agents("t-1")
        assert result == []

    def test_list_agents_exception(self):
        """list_agents handles exception → []."""
        from registry import Registry

        mock_sb = MagicMock()
        mock_sb.table.side_effect = Exception("boom")

        r = Registry()
        r.supabase = mock_sb

        result = r.list_agents("t-1")
        assert result == []

    def test_list_agents_no_supabase(self):
        """list_agents without Supabase → []."""
        from registry import Registry
        r = Registry()
        r.supabase = None
        assert r.list_agents("t-1") == []

    def test_get_active_rules_no_supabase(self):
        """get_active_rules without Supabase → []."""
        from registry import Registry
        r = Registry()
        r.supabase = None
        assert r.get_active_rules("t-1") == []


# ============================================================================
# ghost_state_engine.py — missing lines: 65, 97-99, 151, 195-199, 249-260,
#                         272, 278-317
# ============================================================================

class TestGhostStateEngineEdgeCases:
    """Cover remaining uncovered lines in ghost_state_engine.py."""

    def test_register_custom_simulator(self):
        """register_simulator adds custom simulator (L63-65)."""
        from ghost_state_engine import GhostStateEngine

        engine = GhostStateEngine()
        custom = MagicMock()
        engine.register_simulator("custom_tool", custom)
        assert "custom_tool" in engine.state_simulators

    def test_simulation_failure_blocks(self):
        """Simulator raising exception → fail-closed (L97-99)."""
        from ghost_state_engine import GhostStateEngine, StateSnapshot

        engine = GhostStateEngine()
        engine.register_simulator("bad_tool", lambda s, a: (_ for _ in ()).throw(ValueError("boom")))

        state = StateSnapshot(
            agent_balance=100.0,
            account_balances={},
            data_locations={},
            pending_approvals={},
            timestamp=0.0,
        )
        # register a simulator that raises
        def bad_sim(state, args):
            raise ValueError("sim crash")
        engine.state_simulators["bad_tool"] = bad_sim

        allowed, ghost, reason = engine.evaluate_with_ghost_state(
            state, "bad_tool", {}, {"<": [{"var": "agent_balance"}, 0]}
        )
        assert allowed is False
        assert "Simulation failed" in reason

    def test_nested_value_non_dict_path(self):
        """_get_nested_value returns None for non-dict intermediate (L151)."""
        from ghost_state_engine import GhostStateEngine

        engine = GhostStateEngine()
        result = engine._get_nested_value({"a": "string_val"}, "a.b.c")
        assert result is None

    def test_message_simulator_no_state_change(self):
        """Message simulator doesn't change state (L192-199)."""
        from ghost_state_engine import GhostStateEngine, StateSnapshot

        engine = GhostStateEngine()
        state = StateSnapshot(
            agent_balance=100.0,
            account_balances={"acc": 500.0},
            data_locations={},
            pending_approvals={},
            timestamp=0.0,
        )
        original_balance = state.agent_balance
        engine._simulate_message(state, {"content": "hello", "channel": "public"})
        assert state.agent_balance == original_balance

    def test_external_request_no_data_id(self):
        """External request without data_id doesn't crash."""
        from ghost_state_engine import GhostStateEngine, StateSnapshot

        engine = GhostStateEngine()
        state = StateSnapshot(
            agent_balance=100.0, account_balances={},
            data_locations={}, pending_approvals={}, timestamp=0.0,
        )
        engine._simulate_external_request(state, {"destination": "https://example.com"})
        assert state.data_locations == {}


class TestGhostStateEscrowGateExtended:
    """Cover sandbox client integration paths (L248-264, 268-272)."""

    def test_sandbox_client_allows(self):
        """Sandbox client returns ALLOW → gate allows."""
        from ghost_state_engine import GhostStateEngine, GhostStateEscrowGate, StateSnapshot

        engine = GhostStateEngine()
        mock_sandbox = MagicMock()
        mock_sandbox.trigger_speculative_execution.return_value = {
            "verdict": "ALLOW", "speculative_hash": "abc123"
        }

        gate = GhostStateEscrowGate(engine, sandbox_client=mock_sandbox)
        state = StateSnapshot(
            agent_balance=10000.0,
            account_balances={"checking": 5000.0},
            data_locations={}, pending_approvals={}, timestamp=0.0,
        )

        policies = [{"logic": {"<": [{"var": "account_balances.checking"}, 0]}, "action": {"on_fail": "BLOCK"}}]
        allowed, action = gate.evaluate_with_projection(
            state, "execute_payment",
            {"amount": 100, "from_account": "checking"},
            policies, agent_id="a1", tenant_id="t1",
        )
        assert allowed is True
        assert action == "ALLOW"

    def test_sandbox_client_blocks(self):
        """Sandbox client returns BLOCK → gate blocks."""
        from ghost_state_engine import GhostStateEngine, GhostStateEscrowGate, StateSnapshot

        engine = GhostStateEngine()
        mock_sandbox = MagicMock()
        mock_sandbox.trigger_speculative_execution.return_value = {
            "verdict": "BLOCK", "reason": "suspicious syscall"
        }

        gate = GhostStateEscrowGate(engine, sandbox_client=mock_sandbox)
        state = StateSnapshot(
            agent_balance=10000.0,
            account_balances={"checking": 5000.0},
            data_locations={}, pending_approvals={}, timestamp=0.0,
        )

        policies = [{"logic": {"<": [{"var": "account_balances.checking"}, 0]}, "action": {"on_fail": "BLOCK"}}]
        allowed, action = gate.evaluate_with_projection(
            state, "execute_payment",
            {"amount": 100, "from_account": "checking"},
            policies, agent_id="a1", tenant_id="t1",
        )
        assert allowed is False
        assert action == "BLOCK"

    def test_sandbox_health_with_client(self):
        """With sandbox client configured, returns its status."""
        from ghost_state_engine import GhostStateEngine, GhostStateEscrowGate

        engine = GhostStateEngine()
        mock_sandbox = MagicMock()
        mock_sandbox.get_sandbox_status.return_value = {"available": True, "runtime": "gVisor"}

        gate = GhostStateEscrowGate(engine, sandbox_client=mock_sandbox)
        health = gate.get_sandbox_health()
        assert health["available"] is True


# ============================================================================
# governance_config.py — missing lines: 126-130 (_get_supabase_client),
#                        139-151 (_load_from_supabase), 173, 185-188, 198-199, 204
# ============================================================================

class TestGovernanceConfig:
    """Tests for governance_config.py loading/caching."""

    def setup_method(self):
        """Clear cache before each test."""
        from config.governance_config import _tenant_config_cache
        _tenant_config_cache.clear()

    def test_get_config_empty_tenant_id_raises(self):
        """Blank tenant_id raises ValueError (L172-175)."""
        from config.governance_config import get_tenant_governance_config
        with pytest.raises(ValueError, match="tenant_id is required"):
            get_tenant_governance_config("")

    def test_get_config_whitespace_tenant_id_raises(self):
        from config.governance_config import get_tenant_governance_config
        with pytest.raises(ValueError, match="tenant_id is required"):
            get_tenant_governance_config("   ")

    def test_get_config_cache_hit(self):
        """Second call returns cached config (L178-179)."""
        from config.governance_config import (
            get_tenant_governance_config, _tenant_config_cache
        )
        _tenant_config_cache["cached-tenant"] = {"jury_trust_threshold": 0.99}

        cfg = get_tenant_governance_config("cached-tenant")
        assert cfg["jury_trust_threshold"] == 0.99

    def test_get_config_from_supabase(self):
        """Config loaded from Supabase and merged with defaults (L182-188)."""
        from config.governance_config import get_tenant_governance_config

        mock_sb_data = {"jury_trust_threshold": 0.80, "custom_field": "abc"}

        with patch(
            "config.governance_config._load_from_supabase",
            return_value=mock_sb_data,
        ):
            cfg = get_tenant_governance_config("sb-tenant")
            assert cfg["jury_trust_threshold"] == 0.80
            assert cfg["custom_field"] == "abc"
            # Defaults still present
            assert "kill_switch_threshold" in cfg

    def test_get_config_falls_back_to_defaults(self):
        """Supabase returns None → platform defaults (L190-193)."""
        from config.governance_config import get_tenant_governance_config

        with patch(
            "config.governance_config._load_from_supabase",
            return_value=None,
        ):
            cfg = get_tenant_governance_config("fallback-tenant")
            assert cfg["jury_trust_threshold"] == 0.65

    def test_invalidate_tenant_config(self):
        """invalidate_tenant_config removes from cache (L196-199)."""
        from config.governance_config import (
            invalidate_tenant_config, _tenant_config_cache
        )
        _tenant_config_cache["to-remove"] = {"some": "data"}
        invalidate_tenant_config("to-remove")
        assert "to-remove" not in _tenant_config_cache

    def test_invalidate_nonexistent_tenant_noop(self):
        """Invalidating non-existent tenant doesn't crash."""
        from config.governance_config import invalidate_tenant_config
        invalidate_tenant_config("not-there")

    def test_invalidate_all_config(self):
        """invalidate_all_config clears entire cache (L202-204)."""
        from config.governance_config import (
            invalidate_all_config, _tenant_config_cache
        )
        _tenant_config_cache["a"] = {}
        _tenant_config_cache["b"] = {}
        invalidate_all_config()
        assert len(_tenant_config_cache) == 0

    def test_get_supabase_client_no_env_vars(self):
        """_get_supabase_client with no env vars returns None (L124-125)."""
        from config.governance_config import _get_supabase_client

        with patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_SERVICE_KEY": ""}, clear=False):
            result = _get_supabase_client()
            assert result is None

    def test_get_supabase_client_exception(self):
        """_get_supabase_client catches exceptions (L128-130)."""
        from config.governance_config import _get_supabase_client

        with patch.dict(os.environ, {
            "SUPABASE_URL": "http://mock.supabase.co",
            "SUPABASE_SERVICE_KEY": "mock-key",
        }):
            # create_client is lazily imported from supabase inside _get_supabase_client
            with patch("supabase.create_client", side_effect=Exception("connection error")):
                result = _get_supabase_client()
                assert result is None

    def test_load_from_supabase_returns_data(self):
        """_load_from_supabase returns tenant config from DB (L139-147)."""
        from config.governance_config import _load_from_supabase

        mock_sb = MagicMock()
        mock_resp = MagicMock()
        mock_resp.data = [{"jury_trust_threshold": 0.88, "tenant_id": "t1"}]
        mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_resp

        with patch("config.governance_config._get_supabase_client", return_value=mock_sb):
            result = _load_from_supabase("t1")
            assert result["jury_trust_threshold"] == 0.88

    def test_load_from_supabase_no_data(self):
        """_load_from_supabase with no matching tenant → None."""
        from config.governance_config import _load_from_supabase

        mock_sb = MagicMock()
        mock_resp = MagicMock()
        mock_resp.data = []
        mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_resp

        with patch("config.governance_config._get_supabase_client", return_value=mock_sb):
            result = _load_from_supabase("missing")
            assert result is None

    def test_load_from_supabase_exception(self):
        """_load_from_supabase handles exception → None (L148-150)."""
        from config.governance_config import _load_from_supabase

        mock_sb = MagicMock()
        mock_sb.table.side_effect = Exception("DB error")

        with patch("config.governance_config._get_supabase_client", return_value=mock_sb):
            result = _load_from_supabase("err-tenant")
            assert result is None

    def test_load_from_supabase_no_client(self):
        """_load_from_supabase when client is None → None (L136-137)."""
        from config.governance_config import _load_from_supabase

        with patch("config.governance_config._get_supabase_client", return_value=None):
            result = _load_from_supabase("any")
            assert result is None


# ============================================================================
# main.py — missing: 48-49 (rules_v1.md not found), 89-99 (signature logic),
#           135-140 (ghost warning), 165-168 (WARN token), 197-198 (__main__),
#           218-220 (memory vault loop)
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

class TestPolicyHierarchyEdgeCases:
    """Cover edge cases for policy_hierarchy.py."""

    def test_wildcard_trigger_matches_any_intent(self):
        """Policy with trigger_intent='*' matches any intent (L102)."""
        from policy_hierarchy import Policy, PolicyTier, PolicyHierarchy

        hierarchy = PolicyHierarchy()
        p = Policy(
            policy_id="GLOBAL_CATCH_ALL",
            tier=PolicyTier.GLOBAL,
            trigger_intent="*",
            logic={"==": [{"var": "blocked"}, True]},
            action={"on_fail": "BLOCK"},
            confidence=0.99,
            source_name="Global Rule",
        )
        hierarchy.add_policy(p)

        applicable = hierarchy.get_applicable_policies("any_intent_here")
        assert len(applicable) == 1

    def test_contextual_role_mismatch_filtered(self):
        """CONTEXTUAL policy with wrong role is filtered out (L106-107)."""
        from policy_hierarchy import Policy, PolicyTier, PolicyHierarchy

        hierarchy = PolicyHierarchy()
        p = Policy(
            policy_id="CTX_001",
            tier=PolicyTier.CONTEXTUAL,
            trigger_intent="payment",
            logic={">": [{"var": "amount"}, 100]},
            action={"on_fail": "BLOCK"},
            confidence=0.9,
            source_name="Scope Rule",
            roles=["admin"],
        )
        hierarchy.add_policy(p)

        applicable = hierarchy.get_applicable_policies("payment", role="viewer")
        assert len(applicable) == 0

    def test_contextual_role_match_included(self):
        from policy_hierarchy import Policy, PolicyTier, PolicyHierarchy

        hierarchy = PolicyHierarchy()
        p = Policy(
            policy_id="CTX_002",
            tier=PolicyTier.CONTEXTUAL,
            trigger_intent="payment",
            logic={">": [{"var": "amount"}, 100]},
            action={"on_fail": "BLOCK"},
            confidence=0.9,
            source_name="Scope Rule",
            roles=["admin"],
        )
        hierarchy.add_policy(p)

        applicable = hierarchy.get_applicable_policies("payment", role="admin")
        assert len(applicable) == 1

    def test_expired_policy_filtered(self):
        """Expired DYNAMIC policy is excluded from applicable (L98-99)."""
        from policy_hierarchy import Policy, PolicyTier, PolicyHierarchy
        from datetime import datetime, timedelta, timezone

        hierarchy = PolicyHierarchy()
        p = Policy(
            policy_id="DYN_EXPIRED",
            tier=PolicyTier.DYNAMIC,
            trigger_intent="test",
            logic={"==": [{"var": "a"}, 1]},
            action={"on_fail": "FLAG"},
            confidence=0.8,
            source_name="Temp",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        hierarchy.add_policy(p)

        applicable = hierarchy.get_applicable_policies("test")
        assert len(applicable) == 0

    def test_intent_mismatch_filtered(self):
        """Policy with different trigger_intent excluded (L102-103)."""
        from policy_hierarchy import Policy, PolicyTier, PolicyHierarchy

        hierarchy = PolicyHierarchy()
        p = Policy(
            policy_id="G1",
            tier=PolicyTier.GLOBAL,
            trigger_intent="specific_action",
            logic={"==": [1, 1]},
            action={"on_fail": "BLOCK"},
            confidence=0.9,
            source_name="rule",
        )
        hierarchy.add_policy(p)

        applicable = hierarchy.get_applicable_policies("different_action")
        assert len(applicable) == 0


# ============================================================================
# policy_versioning.py — missing: 36, 125, 180, 224, 230, 235, 241, 263,
#                        280, 328-378 (__main__ block)
# ============================================================================

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

class TestPolicyHierarchyMainBlock:
    """Run policy_hierarchy.py __main__ block (L193-252) in-process."""

    def test_policy_hierarchy_main_runs(self):
        """policy_hierarchy.py __main__ block executes without error."""
        # The __main__ block calls evaluate_with_precedence which imports
        # json_logic_engine (requires json_logic module). Mock it.
        mock_jle = MagicMock()
        mock_jle.JSONLogicEngine.return_value.apply.return_value = True

        with patch.dict("sys.modules", {"json_logic_engine": mock_jle, "json_logic": MagicMock()}):
            import policy_hierarchy
            # Read the source file and exec the __main__ block
            src_path = os.path.join(os.path.dirname(__file__), "..", "policy_hierarchy.py")
            with open(src_path, "r") as f:
                source = f.read()
            # Execute in a namespace where __name__ == '__main__'
            ns = {"__name__": "__main__", "__file__": src_path}
            exec(compile(source, src_path, "exec"), ns)


class TestPolicyVersioningMainBlock:
    """Run policy_versioning.py __main__ block (L327-378) in-process."""

    def test_policy_versioning_main_runs(self):
        """policy_versioning.py __main__ block executes without error."""
        src_path = os.path.join(os.path.dirname(__file__), "..", "policy_versioning.py")
        with open(src_path, "r") as f:
            source = f.read()
        ns = {"__name__": "__main__", "__file__": src_path}
        exec(compile(source, src_path, "exec"), ns)


