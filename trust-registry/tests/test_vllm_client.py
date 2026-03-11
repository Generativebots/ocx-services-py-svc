"""Tests for vllm_client.py — VLLMClient, VLLMConfig
NOTE: conftest.py replaces vllm_client with a FakeVLLMClient.
We use importlib.util to bypass conftest and test the real code.
"""
import sys, os, json, unittest
from unittest.mock import patch, MagicMock
import importlib.util


def _get_real_vllm_module():
    """Import real vllm_client bypassing conftest fake."""
    spec = importlib.util.spec_from_file_location(
        "vllm_client_real",
        os.path.join(os.path.dirname(__file__), "..", "vllm_client.py")
    )
    mod = importlib.util.module_from_spec(spec)
    # We need tenacity available for the @retry decorator
    if "tenacity" not in sys.modules:
        mock_tenacity = MagicMock()
        mock_tenacity.retry = lambda **kwargs: lambda f: f
        mock_tenacity.stop_after_attempt = MagicMock()
        mock_tenacity.wait_exponential = MagicMock()
        sys.modules["tenacity"] = mock_tenacity
    spec.loader.exec_module(mod)
    return mod


class TestVLLMConfig(unittest.TestCase):
    def test_defaults(self):
        mod = _get_real_vllm_module()
        cfg = mod.VLLMConfig()
        self.assertIn("localhost", cfg.base_url)
        self.assertEqual(cfg.temperature, 0.1)
        self.assertEqual(cfg.max_tokens, 2048)

    def test_custom_url(self):
        mod = _get_real_vllm_module()
        cfg = mod.VLLMConfig(base_url="http://custom:9000")
        self.assertEqual(cfg.base_url, "http://custom:9000")


class TestVLLMClientInit(unittest.TestCase):
    @patch("requests.get")
    def test_init_health_check_fails_gracefully(self, mock_get):
        mock_get.side_effect = Exception("not reachable")
        mod = _get_real_vllm_module()
        client = mod.VLLMClient(mod.VLLMConfig())
        # Should not raise — falls back to mock mode
        self.assertIsNotNone(client)


class TestVLLMClientMockGenerate(unittest.TestCase):
    @patch("requests.get")
    def setUp(self, mock_get):
        mock_get.side_effect = Exception("no server")
        self.mod = _get_real_vllm_module()
        self.client = self.mod.VLLMClient(self.mod.VLLMConfig())

    def test_procurement_prompt(self):
        result = self.client._mock_generate("Check procurement policy limits")
        data = json.loads(result)
        self.assertEqual(data["policy_id"], "PURCHASE_AUTH_001")

    def test_data_vpc_prompt(self):
        result = self.client._mock_generate("Data leaving the VPC network")
        data = json.loads(result)
        self.assertEqual(data["policy_id"], "DATA_EXFIL_001")

    def test_pii_prompt(self):
        result = self.client._mock_generate("Check for PII in message")
        data = json.loads(result)
        self.assertEqual(data["policy_id"], "PII_PROTECT_001")

    def test_generic_prompt(self):
        result = self.client._mock_generate("General request")
        data = json.loads(result)
        self.assertEqual(data["policy_id"], "GENERIC_001")


class TestVLLMClientGenerate(unittest.TestCase):
    @patch("requests.get")
    @patch("requests.post")
    def test_successful_generation(self, mock_post, mock_get):
        mock_get.side_effect = Exception("no server")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"choices": [{"text": "  generated text  "}]}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        mod = _get_real_vllm_module()
        client = mod.VLLMClient(mod.VLLMConfig())
        result = client.generate("test prompt")
        self.assertEqual(result, "generated text")


class TestExtractPolicies(unittest.TestCase):
    @patch("requests.get")
    def test_extract_uses_mock(self, mock_get):
        mock_get.side_effect = Exception("no server")
        mod = _get_real_vllm_module()
        client = mod.VLLMClient(mod.VLLMConfig())
        policies = client.extract_policies(
            "Purchase things requiring approval", "Procurement SOP"
        )
        self.assertGreaterEqual(len(policies), 1)
        self.assertIn("source_name", policies[0])


if __name__ == "__main__":
    unittest.main()
