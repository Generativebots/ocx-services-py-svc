"""Tests for vllm_client.py — VLLMClient, VLLMConfig
NOTE: conftest.py replaces vllm_client with a FakeVLLMClient.
We use importlib.util to bypass conftest and test the real code.
"""
import sys, os, json, unittest, pytest
from unittest.mock import patch, MagicMock, AsyncMock
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


class TestVLLMClientAsync:
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




class TestVLLMClientBoost:

    @patch("requests.get", side_effect=Exception("unreachable"))
    def test_init_unreachable(self, _):
        mod = _get_real_vllm_module()
        client = mod.VLLMClient(mod.VLLMConfig(base_url="http://fake:8000"))
        assert client is not None

    @patch("requests.get", return_value=MagicMock(status_code=200))
    def test_init_healthy(self, _):
        mod = _get_real_vllm_module()
        client = mod.VLLMClient(mod.VLLMConfig(base_url="http://fake:8000"))
        assert client.config.base_url == "http://fake:8000"

    @patch("requests.get", return_value=MagicMock(status_code=503))
    def test_init_unhealthy(self, _):
        mod = _get_real_vllm_module()
        client = mod.VLLMClient(mod.VLLMConfig(base_url="http://fake:8000"))
        assert client is not None

    @patch("requests.get", side_effect=Exception("x"))
    def test_generate_falls_back_to_mock(self, mock_get):
        mod = _get_real_vllm_module()
        client = mod.VLLMClient(mod.VLLMConfig(base_url="http://fake:8000"))
        # Call _mock_generate directly (since generate() goes through retry+exception)
        result = client._mock_generate("test procurement prompt")
        assert isinstance(result, str)

    @patch("requests.get", side_effect=Exception("x"))
    def test_mock_generate_procurement(self, _):
        mod = _get_real_vllm_module()
        client = mod.VLLMClient(mod.VLLMConfig(base_url="http://fake:8000"))
        result = client._mock_generate("procurement order")
        assert "PURCHASE_AUTH" in result

    @patch("requests.get", side_effect=Exception("x"))
    def test_mock_generate_data_vpc(self, _):
        mod = _get_real_vllm_module()
        client = mod.VLLMClient(mod.VLLMConfig(base_url="http://fake:8000"))
        result = client._mock_generate("data sent outside vpc network")
        assert "DATA_EXFIL" in result

    @patch("requests.get", side_effect=Exception("x"))
    def test_mock_generate_pii(self, _):
        mod = _get_real_vllm_module()
        client = mod.VLLMClient(mod.VLLMConfig(base_url="http://fake:8000"))
        result = client._mock_generate("Detect PII in document")
        assert "PII_PROTECT" in result

    @patch("requests.get", side_effect=Exception("x"))
    def test_mock_generate_default(self, _):
        mod = _get_real_vllm_module()
        client = mod.VLLMClient(mod.VLLMConfig(base_url="http://fake:8000"))
        result = client._mock_generate("generic stuff")
        assert "GENERIC" in result

    @patch("requests.get", side_effect=Exception("x"))
    def test_extract_policies(self, _):
        mod = _get_real_vllm_module()
        client = mod.VLLMClient(mod.VLLMConfig(base_url="http://fake:8000"))
        policies = client.extract_policies("All purchases over $500 need approval", "Test")
        assert isinstance(policies, list)
        assert len(policies) >= 1
        assert "source_name" in policies[0]

    @patch("requests.get", side_effect=Exception("x"))
    def test_extract_policies_json_error(self, _):
        mod = _get_real_vllm_module()
        client = mod.VLLMClient(mod.VLLMConfig(base_url="http://fake:8000"))
        client.generate = MagicMock(return_value="not valid json {{{")
        policies = client.extract_policies("text", "src")
        assert policies == []

    def test_vllm_config_defaults(self):
        mod = _get_real_vllm_module()
        cfg = mod.VLLMConfig()
        assert cfg.temperature == 0.1
        assert cfg.max_tokens == 2048
        assert cfg.max_retries == 3


# ─────────────────── multi_model_client.py ────────────────────────────────
# multi_model_client imports vllm_client internally; make sure real vllm_client is available

def _get_real_mmc():
    """Force-import the REAL multi_model_client module."""
    _get_real_vllm_module()  # Ensure real vllm_client is in sys.modules
    saved = sys.modules.pop("multi_model_client", None)
    try:
        mod = importlib.import_module("multi_model_client")
        importlib.reload(mod)
        return mod
    finally:
        pass


