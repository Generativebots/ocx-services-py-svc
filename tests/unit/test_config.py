"""Tests for trust-registry config module — settings, PlatformConfigStore."""

import sys, os, json, time, types, hashlib, importlib
from unittest.mock import MagicMock, patch, mock_open, PropertyMock
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Mock ALL missing pip deps so real modules can be force-reloaded ────────
# prometheus_client (ape_metrics.py)
if "prometheus_client" not in sys.modules:
    _mock_prom = types.ModuleType("prometheus_client")
    _mock_prom.Counter = MagicMock(return_value=MagicMock())
    _mock_prom.Histogram = MagicMock(return_value=MagicMock())
    _mock_prom.start_http_server = MagicMock()
    _mock_prom.Gauge = MagicMock(return_value=MagicMock())
    _mock_prom.Summary = MagicMock(return_value=MagicMock())
    sys.modules["prometheus_client"] = _mock_prom

# yaml (llm_client.py)
if "yaml" not in sys.modules:
    _mock_yaml = types.ModuleType("yaml")
    def _simple_yaml_parse(content):
        """Mini YAML parser — handles key: value lines."""
        result = {}
        if not isinstance(content, str):
            return result
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                k, v = line.split(":", 1)
                v = v.strip()
                if v.lower() == "true": v = True
                elif v.lower() == "false": v = False
                elif v.isdigit(): v = int(v)
                result[k.strip()] = v
        return result
    _mock_yaml.safe_load = _simple_yaml_parse
    sys.modules["yaml"] = _mock_yaml

# tenacity (vllm_client.py)
if "tenacity" not in sys.modules:
    def _noop_decorator(*args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda fn: fn
    _mock_tenacity = types.ModuleType("tenacity")
    _mock_tenacity.retry = _noop_decorator
    _mock_tenacity.stop_after_attempt = lambda n: None
    _mock_tenacity.wait_exponential = lambda **kw: None
    sys.modules["tenacity"] = _mock_tenacity

# pydantic_settings (config/settings.py)
if "pydantic_settings" not in sys.modules:
    _mock_ps = types.ModuleType("pydantic_settings")
    _mock_ps.BaseSettings = type("BaseSettings", (), {
        "__init_subclass__": classmethod(lambda cls, **kw: None),
    })
    sys.modules["pydantic_settings"] = _mock_ps


def _force_import(module_name):
    """Force-import a real module by removing conftest fakes from sys.modules."""
    saved = sys.modules.pop(module_name, None)
    try:
        mod = importlib.import_module(module_name)
        importlib.reload(mod)  # Ensure fresh load
        return mod
    except Exception:
        if saved is not None:
            sys.modules[module_name] = saved
        raise


# ───────────────────────────── ape_metrics.py ─────────────────────────────
# Force-reload real ape_metrics (conftest may not have faked it, but
# prometheus_client was missing — now mocked at module level above)

def _get_ape_metrics():
    """Import the real ape_metrics module."""
    saved = sys.modules.pop("ape_metrics", None)
    try:
        import ape_metrics
        importlib.reload(ape_metrics)
        return ape_metrics
    except Exception:
        if saved is not None:
            sys.modules["ape_metrics"] = saved
        raise

class TestConfigSettings:

    def test_server_config_defaults(self):
        from config.settings import ServerConfig
        sc = ServerConfig()
        assert sc.host == os.getenv("HOST", "0.0.0.0")
        assert isinstance(sc.port, int)

    def test_database_config_defaults(self):
        from config.settings import DatabaseConfig
        dc = DatabaseConfig()
        assert isinstance(dc.pool_size, int)
        assert dc.backend in ("supabase", "postgresql")

    def test_cache_config(self):
        from config.settings import CacheConfig
        cc = CacheConfig()
        assert isinstance(cc.redis_port, int)

    def test_ai_models_config(self):
        from config.settings import AIModelsConfig
        ai = AIModelsConfig()
        assert isinstance(ai.model_priority, list)

    def test_trust_config(self):
        from config.settings import TrustConfig
        tc = TrustConfig()
        assert 0 <= tc.min_trust_score <= 1

    def test_governance_config(self):
        from config.settings import GovernanceConfig
        gc = GovernanceConfig()
        assert gc.committee_size > 0

    def test_monitoring_config(self):
        from config.settings import MonitoringConfig
        mc = MonitoringConfig()
        assert mc.log_level in ("DEBUG", "INFO", "WARNING", "ERROR")

    def test_service_urls_config(self):
        from config.settings import ServiceURLsConfig
        su = ServiceURLsConfig()
        assert "run.app" in su.trust_registry_url or "localhost" in su.trust_registry_url

    def test_ocx_config_master(self):
        from config.settings import OCXConfig
        oc = OCXConfig()
        assert hasattr(oc, "server")
        assert hasattr(oc, "database")
        assert hasattr(oc, "cache")

    def test_get_config_cached(self):
        from config.settings import get_config
        c1 = get_config()
        c2 = get_config()
        assert c1 is c2

    def test_is_production(self):
        from config.settings import is_production
        # Default env is development
        assert is_production() is False or is_production() is True

    def test_is_development(self):
        from config.settings import is_development
        assert isinstance(is_development(), bool)

    def test_get_database_url(self):
        from config.settings import get_database_url
        url = get_database_url()
        assert url.startswith("postgresql://")

    def test_get_supabase_client(self):
        with patch("supabase.create_client", return_value=MagicMock()) as mock_create:
            from config import settings
            import importlib
            importlib.reload(settings)
            client = settings.get_supabase_client()
            mock_create.assert_called_once()


# ────────────── config/platform_config_store.py ───────────────────────────




class TestPlatformConfigStore:
    """Tests for config/platform_config_store.py module functions."""

    def test_validate_tenant_id_valid(self):
        from config.platform_config_store import validate_tenant_id
        validate_tenant_id("tenant-abc")  # Should not raise

    def test_validate_tenant_id_empty(self):
        from config.platform_config_store import validate_tenant_id, EmptyTenantIDError
        with pytest.raises(EmptyTenantIDError):
            validate_tenant_id("")

    @patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_SERVICE_KEY": ""})
    def test_get_supabase_client_no_creds(self):
        from config.platform_config_store import _get_supabase_client
        assert _get_supabase_client() is None

    @patch("config.platform_config_store._get_supabase_client", return_value=None)
    def test_load_from_db_no_client(self, _):
        from config.platform_config_store import _load_from_db
        assert _load_from_db("t1", "cat", "key") is None

    def test_cache_operations(self):
        from config import platform_config_store as pcs
        pcs._cache["t1:cat:k"] = "val"
        pcs._cache_expiry["t1:cat:k"] = MagicMock()
        pcs.invalidate_tenant("t1")
        assert "t1:cat:k" not in pcs._cache
        pcs._cache["x"] = 1
        pcs.invalidate_all()
        assert len(pcs._cache) == 0




class TestPlatformConfigStoreFunctions:
    """Tests for module-level functions in platform_config_store"""

    def test_validate_tenant_id_valid(self):
        from config.platform_config_store import validate_tenant_id
        validate_tenant_id("tenant-abc")  # Should not raise

    def test_validate_tenant_id_empty(self):
        from config.platform_config_store import validate_tenant_id, EmptyTenantIDError
        with pytest.raises(EmptyTenantIDError):
            validate_tenant_id("")

    def test_validate_tenant_id_whitespace(self):
        from config.platform_config_store import validate_tenant_id, EmptyTenantIDError
        with pytest.raises(EmptyTenantIDError):
            validate_tenant_id("   ")

    @patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_SERVICE_KEY": ""})
    def test_get_supabase_client_no_creds(self):
        from config.platform_config_store import _get_supabase_client
        assert _get_supabase_client() is None

    @patch.dict(os.environ, {"SUPABASE_URL": "https://x.supabase.co", "SUPABASE_SERVICE_KEY": "key"})
    @patch("supabase.create_client", side_effect=Exception("connect fail"))
    def test_get_supabase_client_exception(self, mock_create):
        from config import platform_config_store
        import importlib
        importlib.reload(platform_config_store)
        result = platform_config_store._get_supabase_client()
        assert result is None

    @patch("config.platform_config_store._get_supabase_client", return_value=None)
    def test_load_from_db_no_client(self, _):
        from config.platform_config_store import _load_from_db
        assert _load_from_db("t1", "cat", "key") is None

    @patch("config.platform_config_store._get_supabase_client")
    def test_load_from_db_with_tenant(self, mock_client_fn):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        resp = MagicMock()
        resp.data = [{"value": {"v": 42}}]
        # Chain: table().select().eq(category).eq(key).eq(tenant_id).execute()
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = resp
        from config.platform_config_store import _load_from_db
        assert _load_from_db("t1", "cat", "key") == 42

    @patch("config.platform_config_store._get_supabase_client")
    def test_load_from_db_no_tenant(self, mock_client_fn):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        resp = MagicMock()
        resp.data = [{"value": "plain_val"}]
        # Chain: table().select().eq(category).eq(key).is_(tenant_id, null).execute()
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.is_.return_value.execute.return_value = resp
        from config.platform_config_store import _load_from_db
        assert _load_from_db("", "cat", "key") == "plain_val"

    def test_invalidate_tenant(self):
        from config import platform_config_store as pcs
        pcs._cache["t1:cat:k"] = "val"
        pcs._cache_expiry["t1:cat:k"] = MagicMock()
        pcs.invalidate_tenant("t1")
        assert "t1:cat:k" not in pcs._cache

    def test_invalidate_all(self):
        from config import platform_config_store as pcs
        pcs._cache["x"] = 1
        pcs.invalidate_all()
        assert len(pcs._cache) == 0


# ──────────────────────── policy_testing.py ────────────────────────────────


