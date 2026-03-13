"""Tests for registry.py — Registry class with mocked Supabase + Redis"""
import sys, os, json, unittest
from unittest.mock import MagicMock, patch

# Mock external deps
sys.modules.setdefault("supabase", MagicMock())
sys.modules.setdefault("redis", MagicMock())
sys.modules.setdefault("redis.commands", MagicMock())
sys.modules.setdefault("redis.commands.bf", MagicMock())

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestRegistryInit(unittest.TestCase):
    @patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_SERVICE_KEY": ""})
    @patch("registry.redis")
    def test_init_no_supabase(self, mock_redis):
        from registry import Registry
        reg = Registry()
        self.assertIsNone(reg.supabase)

    @patch.dict(os.environ, {"SUPABASE_URL": "https://x.supabase.co", "SUPABASE_SERVICE_KEY": "key"})
    @patch("registry.redis")
    @patch("registry.create_client")
    def test_init_with_supabase(self, mock_create, mock_redis):
        from registry import Registry
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_create.return_value = mock_supabase
        reg = Registry()
        self.assertIsNotNone(reg.supabase)


class TestRegisterAgent(unittest.TestCase):
    @patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_SERVICE_KEY": ""})
    @patch("registry.redis")
    def test_register_without_supabase(self, mock_redis):
        from registry import Registry
        reg = Registry()
        result = reg.register_agent({"agent_id": "a1", "metadata": {"name": "A"}}, "t1")
        self.assertEqual(result, "mock-id")

    @patch.dict(os.environ, {"SUPABASE_URL": "url", "SUPABASE_SERVICE_KEY": "key"})
    @patch("registry.redis")
    @patch("registry.create_client")
    def test_register_with_supabase(self, mock_create, mock_redis):
        from registry import Registry
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_supabase.table.return_value.upsert.return_value.execute.return_value = (MagicMock(), 1)
        mock_create.return_value = mock_supabase

        reg = Registry()
        agent_json = {
            "agent_id": "a1",
            "metadata": {"name": "TestAgent", "provider": "OpenAI"},
            "security_handshake": {"auth_tier": "Premium", "public_key": "pk"},
            "capabilities": [{"tool_name": "search"}, {"tool_name": "execute"}],
            "status": "Active"
        }
        result = reg.register_agent(agent_json, "tenant-1")
        self.assertEqual(result, "a1")


class TestAddRule(unittest.TestCase):
    @patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_SERVICE_KEY": ""})
    @patch("registry.redis")
    def test_add_rule_no_supabase(self, mock_redis):
        from registry import Registry
        reg = Registry()
        rule_id = reg.add_rule("rule text", {"logic": True}, "t1")
        self.assertIsInstance(rule_id, str)
        self.assertEqual(len(rule_id), 36)  # UUID


class TestGetAgentProfile(unittest.TestCase):
    @patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_SERVICE_KEY": ""})
    @patch("registry.redis")
    def test_no_supabase(self, mock_redis):
        from registry import Registry
        reg = Registry()
        self.assertIsNone(reg.get_agent_profile("a1", "t1"))

    @patch.dict(os.environ, {"SUPABASE_URL": "url", "SUPABASE_SERVICE_KEY": "key"})
    @patch("registry.redis")
    @patch("registry.create_client")
    def test_with_profile_found(self, mock_create, mock_redis):
        from registry import Registry
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_create.return_value = mock_supabase

        reg = Registry()

        # Override the response for get_agent_profile call
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"full_schema_json": {"name": "A", "system_prompt": "existing"}}]
        )

        profile = reg.get_agent_profile("a1", "t1")
        self.assertIsNotNone(profile)
        self.assertIn("OCX", profile["system_prompt"])

    @patch.dict(os.environ, {"SUPABASE_URL": "url", "SUPABASE_SERVICE_KEY": "key"})
    @patch("registry.redis")
    @patch("registry.create_client")
    def test_no_profile_found(self, mock_create, mock_redis):
        from registry import Registry
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_create.return_value = mock_supabase

        reg = Registry()
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        self.assertIsNone(reg.get_agent_profile("unknown", "t1"))


class TestCheckRuleExistence(unittest.TestCase):
    @patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_SERVICE_KEY": ""})
    @patch("registry.redis")
    def test_bloom_filter_check(self, mock_redis):
        from registry import Registry
        mock_r = MagicMock()
        mock_redis.Redis.return_value = mock_r
        mock_r.bf.return_value.exists.return_value = 1

        reg = Registry()
        self.assertTrue(reg.check_rule_existence("r1", "t1"))


class TestEjectAgent(unittest.TestCase):
    @patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_SERVICE_KEY": ""})
    @patch("registry.redis")
    def test_eject_publishes(self, mock_redis):
        from registry import Registry
        mock_r = MagicMock()
        mock_redis.Redis.return_value = mock_r
        reg = Registry()
        result = reg.eject_agent("a1", "t1")
        self.assertTrue(result)
        mock_r.publish.assert_called()
        mock_r.setex.assert_called()


class TestGetActiveRules(unittest.TestCase):
    @patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_SERVICE_KEY": ""})
    @patch("registry.redis")
    def test_no_supabase(self, mock_redis):
        from registry import Registry
        reg = Registry()
        self.assertEqual(reg.get_active_rules("t1"), [])

    @patch.dict(os.environ, {"SUPABASE_URL": "url", "SUPABASE_SERVICE_KEY": "key"})
    @patch("registry.redis")
    @patch("registry.create_client")
    def test_with_tenant_filter(self, mock_create, mock_redis):
        from registry import Registry
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_create.return_value = mock_supabase

        reg = Registry()
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"rule_id": "r1", "status": "Active"}]
        )
        rules = reg.get_active_rules("t1")
        self.assertEqual(len(rules), 1)


class TestListAgents(unittest.TestCase):
    @patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_SERVICE_KEY": ""})
    @patch("registry.redis")
    def test_no_supabase(self, mock_redis):
        from registry import Registry
        reg = Registry()
        self.assertEqual(reg.list_agents("t1"), [])

    @patch.dict(os.environ, {"SUPABASE_URL": "url", "SUPABASE_SERVICE_KEY": "key"})
    @patch("registry.redis")
    @patch("registry.create_client")
    def test_list_agents_exception(self, mock_create, mock_redis):
        from registry import Registry
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_create.return_value = mock_supabase

        reg = Registry()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = Exception("db error")
        self.assertEqual(reg.list_agents("t1"), [])


class TestHydrateCache(unittest.TestCase):
    @patch.dict(os.environ, {"SUPABASE_URL": "url", "SUPABASE_SERVICE_KEY": "key"})
    @patch("registry.redis")
    @patch("registry.create_client")
    def test_hydrate_cache_success(self, mock_create, mock_redis):
        from registry import Registry
        mock_supabase = MagicMock()
        # __init__ calls hydrate_cache -> supabase.table("rules").select(...).eq(...).execute()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"rule_id": "r1", "tenant_id": "t1"}, {"rule_id": "r2", "tenant_id": "t2"}]
        )
        mock_create.return_value = mock_supabase
        mock_r = MagicMock()
        mock_redis.Redis.return_value = mock_r

        reg = Registry()
        # Verify bloom filter additions occurred (2 rules)
        self.assertEqual(mock_r.bf.return_value.add.call_count, 2)

    @patch.dict(os.environ, {"SUPABASE_URL": "url", "SUPABASE_SERVICE_KEY": "key"})
    @patch("registry.redis")
    @patch("registry.create_client")
    def test_hydrate_cache_error_handled(self, mock_create, mock_redis):
        from registry import Registry
        mock_supabase = MagicMock()
        # Make the select().eq().execute() raise to test error handling
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = Exception("DB down")
        mock_create.return_value = mock_supabase

        # Should NOT raise — error is logged and swallowed
        reg = Registry()
        self.assertIsNotNone(reg.supabase)

    @patch.dict(os.environ, {"SUPABASE_URL": "url", "SUPABASE_SERVICE_KEY": "key"})
    @patch("registry.redis")
    @patch("registry.create_client")
    def test_hydrate_cache_bloom_filter_already_exists(self, mock_create, mock_redis):
        """When bloom filter already exists, bf().reserve() raises ResponseError — should be caught.
        Since redis module is mocked, we create a real exception hierarchy."""
        from registry import Registry

        # Create a real ResponseError class for the mock to use
        class FakeResponseError(Exception):
            pass

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"rule_id": "r1", "tenant_id": "t1"}]
        )
        mock_create.return_value = mock_supabase
        mock_r = MagicMock()
        mock_redis.Redis.return_value = mock_r
        # Assign our real exception class to the mocked module path
        mock_redis.exceptions.ResponseError = FakeResponseError
        # Simulate bloom filter already existing
        mock_r.bf.return_value.reserve.side_effect = FakeResponseError("already exists")

        reg = Registry()
        # Should still add items despite reserve error
        mock_r.bf.return_value.add.assert_called()


class TestAddRuleWithSupabase(unittest.TestCase):
    @patch.dict(os.environ, {"SUPABASE_URL": "url", "SUPABASE_SERVICE_KEY": "key"})
    @patch("registry.redis")
    @patch("registry.create_client")
    def test_add_rule_with_supabase(self, mock_create, mock_redis):
        from registry import Registry
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_create.return_value = mock_supabase
        mock_r = MagicMock()
        mock_redis.Redis.return_value = mock_r

        reg = Registry()
        rule_id = reg.add_rule("test rule", {"condition": "amount > 100"}, "t1", priority=5)
        self.assertIsInstance(rule_id, str)
        # Verify Supabase insert was called
        mock_supabase.table.return_value.insert.assert_called()
        # Verify Redis pubsub and bloom filter
        mock_r.publish.assert_called()
        mock_r.bf.return_value.add.assert_called()


class TestGetAgentProfileNoSystemPrompt(unittest.TestCase):
    @patch.dict(os.environ, {"SUPABASE_URL": "url", "SUPABASE_SERVICE_KEY": "key"})
    @patch("registry.redis")
    @patch("registry.create_client")
    def test_profile_without_system_prompt(self, mock_create, mock_redis):
        """Agent profile without system_prompt gets one injected."""
        from registry import Registry
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_create.return_value = mock_supabase

        reg = Registry()
        # Override for get_agent_profile: profile without system_prompt
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"full_schema_json": {"name": "Agent-NoPrompt"}}]
        )
        profile = reg.get_agent_profile("a2", "t1")
        self.assertIn("OCX", profile["system_prompt"])
        self.assertNotIn("\n\n", profile["system_prompt"][:10])  # No double prefix


class TestGetActiveRulesError(unittest.TestCase):
    @patch.dict(os.environ, {"SUPABASE_URL": "url", "SUPABASE_SERVICE_KEY": "key"})
    @patch("registry.redis")
    @patch("registry.create_client")
    def test_get_active_rules_error(self, mock_create, mock_redis):
        from registry import Registry
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_create.return_value = mock_supabase

        reg = Registry()
        # Make the query chain raise
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.side_effect = Exception("timeout")
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = Exception("timeout")
        result = reg.get_active_rules("t1")
        self.assertEqual(result, [])


class TestListAgentsSuccess(unittest.TestCase):
    @patch.dict(os.environ, {"SUPABASE_URL": "url", "SUPABASE_SERVICE_KEY": "key"})
    @patch("registry.redis")
    @patch("registry.create_client")
    def test_list_agents_success(self, mock_create, mock_redis):
        from registry import Registry
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_create.return_value = mock_supabase

        reg = Registry()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"agent_id": "a1", "name": "A", "provider": "P", "tier": "Standard", "status": "Active"}]
        )
        agents = reg.list_agents("t1")
        self.assertEqual(len(agents), 1)
        self.assertEqual(agents[0]["agent_id"], "a1")


class TestEjectAgentWithSupabase(unittest.TestCase):
    @patch.dict(os.environ, {"SUPABASE_URL": "url", "SUPABASE_SERVICE_KEY": "key"})
    @patch("registry.redis")
    @patch("registry.create_client")
    def test_eject_with_supabase(self, mock_create, mock_redis):
        from registry import Registry
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_create.return_value = mock_supabase
        mock_r = MagicMock()
        mock_redis.Redis.return_value = mock_r

        reg = Registry()
        result = reg.eject_agent("a1", "t1")
        self.assertTrue(result)
        # Verify Supabase update was called
        mock_supabase.table.return_value.update.assert_called()
        mock_r.publish.assert_called()
        mock_r.setex.assert_called()


if __name__ == "__main__":
    unittest.main()


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


