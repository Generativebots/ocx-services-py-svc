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


if __name__ == "__main__":
    unittest.main()
