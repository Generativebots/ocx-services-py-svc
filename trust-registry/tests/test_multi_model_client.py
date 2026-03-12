"""Tests for multi_model_client.py — MultiModelClient with mocked providers"""
import sys, os, json, unittest
from unittest.mock import MagicMock, patch

# Mock provider deps
for mod in ["openai", "google", "google.generativeai", "anthropic", "tenacity"]:
    sys.modules.setdefault(mod, MagicMock())

# Mock tenacity decorators
mock_tenacity = sys.modules["tenacity"]
mock_tenacity.retry = lambda **kwargs: lambda f: f
mock_tenacity.stop_after_attempt = MagicMock()
mock_tenacity.wait_exponential = MagicMock()

# Mock vllm_client module
mock_vllm_mod = MagicMock()
sys.modules["vllm_client"] = mock_vllm_mod

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from multi_model_client import (
    MultiModelClient, ModelConfig, ModelProvider, create_multi_model_client
)


class TestModelConfig(unittest.TestCase):
    def test_defaults(self):
        cfg = ModelConfig(provider=ModelProvider.VLLM, model_name="mistral-7b")
        self.assertEqual(cfg.temperature, 0.1)
        self.assertEqual(cfg.priority, 1)

    def test_custom(self):
        cfg = ModelConfig(
            provider=ModelProvider.OPENAI, model_name="gpt-5",
            api_key="key", priority=2
        )
        self.assertEqual(cfg.api_key, "key")


class TestMultiModelClient(unittest.TestCase):
    def test_sorts_by_priority(self):
        m1 = ModelConfig(provider=ModelProvider.OPENAI, model_name="gpt", priority=2)
        m2 = ModelConfig(provider=ModelProvider.VLLM, model_name="mistral", priority=1)
        client = MultiModelClient([m1, m2])
        self.assertEqual(client.models[0].provider, ModelProvider.VLLM)

    def test_fallback_on_failure(self):
        m1 = ModelConfig(provider=ModelProvider.VLLM, model_name="m1", priority=1)
        m2 = ModelConfig(provider=ModelProvider.OPENAI, model_name="m2", priority=2)
        client = MultiModelClient([m1, m2])
        client._extract_vllm = MagicMock(side_effect=Exception("fail"))
        client._extract_openai = MagicMock(return_value=[{"policy": "P1"}])

        result = client.extract_policies("text", "src")
        self.assertEqual(len(result), 1)
        client._extract_openai.assert_called_once()

    def test_all_fail_raises(self):
        m1 = ModelConfig(provider=ModelProvider.VLLM, model_name="m1", priority=1)
        client = MultiModelClient([m1])
        client._extract_vllm = MagicMock(side_effect=Exception("fail"))

        with self.assertRaises(Exception) as ctx:
            client.extract_policies("text", "src")
        self.assertIn("All models failed", str(ctx.exception))

    def test_vllm_calls_vllm_client(self):
        # Re-set mock to override any conftest interference
        sys.modules["vllm_client"] = mock_vllm_mod
        mock_vllm_cls = MagicMock()
        mock_vllm_cls.return_value.extract_policies.return_value = [{"id": "P1"}]
        mock_vllm_mod.VLLMClient = mock_vllm_cls
        mock_vllm_mod.VLLMConfig = MagicMock()

        client = MultiModelClient([])
        cfg = ModelConfig(provider=ModelProvider.VLLM, model_name="mistral", base_url="http://localhost:8000")
        result = client._extract_vllm("text", "src", cfg)
        self.assertEqual(len(result), 1)


class TestCreateMultiModelClient(unittest.TestCase):
    @patch.dict(os.environ, {"VLLM_ENABLED": "true"}, clear=False)
    def test_creates_with_vllm(self):
        client = create_multi_model_client()
        self.assertIsInstance(client, MultiModelClient)
        self.assertGreaterEqual(len(client.models), 1)

    @patch.dict(os.environ, {"VLLM_ENABLED": "false"}, clear=False)
    def test_raises_with_no_models(self):
        # Remove all API keys
        env = {k: v for k, v in os.environ.items() 
               if k not in ("OPENAI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY")}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValueError):
                create_multi_model_client()


class TestModelProvider(unittest.TestCase):
    def test_values(self):
        self.assertEqual(ModelProvider.VLLM.value, "vllm")
        self.assertEqual(ModelProvider.OPENAI.value, "openai")
        self.assertEqual(ModelProvider.GOOGLE.value, "google")
        self.assertEqual(ModelProvider.ANTHROPIC.value, "anthropic")


if __name__ == "__main__":
    unittest.main()
import pytest

class TestMultiModelClientBoost:
    """Additional coverage tests for MultiModelClient, using module-level imports."""

    def test_init(self):
        models = [
            ModelConfig(provider=ModelProvider.VLLM, model_name="m1", priority=2),
            ModelConfig(provider=ModelProvider.OPENAI, model_name="m2", priority=1),
        ]
        client = MultiModelClient(models)
        assert client.models[0].priority == 1  # sorted

    def test_extract_vllm_fallback(self):
        models = [ModelConfig(provider=ModelProvider.VLLM, model_name="m", base_url="http://fake:8000", priority=1)]
        client = MultiModelClient(models)
        client._extract_vllm = MagicMock(return_value=[{"policy": "P1"}])
        result = client.extract_policies("procurement doc", "src")
        assert isinstance(result, list)
        assert len(result) == 1

    def test_all_models_fail(self):
        models = [ModelConfig(provider=ModelProvider.OPENAI, model_name="m", api_key="fake", priority=1)]
        client = MultiModelClient(models)
        with patch.object(client, "_extract_openai", side_effect=Exception("fail")):
            with pytest.raises(Exception, match="All models failed"):
                client.extract_policies("doc", "src")

    def test_fallback_chain(self):
        models = [
            ModelConfig(provider=ModelProvider.OPENAI, model_name="m1", api_key="k", priority=1),
            ModelConfig(provider=ModelProvider.VLLM, model_name="m2", base_url="http://fake:8000", priority=2),
        ]
        client = MultiModelClient(models)
        client._extract_vllm = MagicMock(return_value=[{"policy": "P2"}])
        with patch.object(client, "_extract_openai", side_effect=Exception("fail")):
            result = client.extract_policies("procurement doc", "src")
            assert isinstance(result, list)
            assert len(result) == 1

    @patch.dict(os.environ, {"VLLM_ENABLED": "true", "OPENAI_API_KEY": "", "GOOGLE_API_KEY": "", "ANTHROPIC_API_KEY": ""}, clear=False)
    def test_factory_vllm_only(self):
        client = create_multi_model_client()
        assert len(client.models) >= 1

    @patch.dict(os.environ, {"VLLM_ENABLED": "false", "OPENAI_API_KEY": "", "GOOGLE_API_KEY": "", "ANTHROPIC_API_KEY": ""}, clear=False)
    def test_factory_no_models(self):
        with pytest.raises(ValueError, match="No models configured"):
            create_multi_model_client()

    @patch.dict(os.environ, {"VLLM_ENABLED": "true", "OPENAI_API_KEY": "k1", "GOOGLE_API_KEY": "k2", "ANTHROPIC_API_KEY": "k3"})
    def test_factory_all_models(self):
        client = create_multi_model_client()
        assert len(client.models) == 4

    def test_model_provider_enum(self):
        assert ModelProvider.VLLM.value == "vllm"
        assert ModelProvider.OPENAI.value == "openai"
        assert ModelProvider.GOOGLE.value == "google"
        assert ModelProvider.ANTHROPIC.value == "anthropic"
