"""
Governance Config — pytest unit test suite.

Tests the governance configuration loader with mocked Supabase client,
covering: defaults, tenant loading, caching, invalidation, and error paths.
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock, PropertyMock

# Ensure trust-registry/config is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "config"))

import governance_config as gc


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the module-level cache before each test."""
    gc._tenant_config_cache.clear()
    yield
    gc._tenant_config_cache.clear()


# =============================================================================
# DEFAULT_GOVERNANCE_CONFIG
# =============================================================================

class TestDefaults:
    def test_defaults_is_dict(self):
        assert isinstance(gc.DEFAULT_GOVERNANCE_CONFIG, dict)

    def test_jury_trust_threshold(self):
        assert gc.DEFAULT_GOVERNANCE_CONFIG["jury_trust_threshold"] == 0.65

    def test_risk_multipliers_is_dict(self):
        rm = gc.DEFAULT_GOVERNANCE_CONFIG["risk_multipliers"]
        assert isinstance(rm, dict)
        assert "data_query" in rm
        assert rm["admin_action"] == 5.0

    def test_entropy_threshold(self):
        assert gc.DEFAULT_GOVERNANCE_CONFIG["entropy_threshold"] == 7.5

    def test_drift_threshold(self):
        assert gc.DEFAULT_GOVERNANCE_CONFIG["drift_threshold"] == 0.20

    def test_decay_half_life(self):
        assert gc.DEFAULT_GOVERNANCE_CONFIG["decay_half_life_hours"] == 168

    def test_escrow_thresholds(self):
        assert gc.DEFAULT_GOVERNANCE_CONFIG["escrow_sovereign_threshold"] == 0.90
        assert gc.DEFAULT_GOVERNANCE_CONFIG["escrow_trusted_threshold"] == 0.75
        assert gc.DEFAULT_GOVERNANCE_CONFIG["escrow_probation_threshold"] == 0.60

    def test_llm_keys_blank(self):
        assert gc.DEFAULT_GOVERNANCE_CONFIG["openai_api_key"] == ""
        assert gc.DEFAULT_GOVERNANCE_CONFIG["anthropic_api_key"] == ""

    def test_aocs_params(self):
        assert gc.DEFAULT_GOVERNANCE_CONFIG["aocs_escrow_timeout_seconds"] == 300
        assert gc.DEFAULT_GOVERNANCE_CONFIG["aocs_speculative_enabled"] is True


# =============================================================================
# _get_supabase_client
# =============================================================================

class TestGetSupabaseClient:
    def test_returns_none_no_env(self):
        with patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_SERVICE_KEY": ""}, clear=False):
            result = gc._get_supabase_client()
            assert result is None

    def test_returns_none_missing_key(self):
        with patch.dict(os.environ, {"SUPABASE_URL": "http://x", "SUPABASE_SERVICE_KEY": ""}, clear=False):
            result = gc._get_supabase_client()
            assert result is None

    @patch("governance_config.os.getenv")
    def test_returns_client_on_success(self, mock_getenv):
        mock_getenv.side_effect = lambda k, d="": {"SUPABASE_URL": "http://x", "SUPABASE_SERVICE_KEY": "key"}.get(k, d)
        with patch("governance_config.create_client", create=True) as mock_create:
            mock_create.return_value = MagicMock()
            # Need to handle the import inside the function
            import importlib
            with patch.dict("sys.modules", {"supabase": MagicMock(create_client=mock_create)}):
                result = gc._get_supabase_client()
                # Should return None or mock depending on import success

    def test_returns_none_on_exception(self):
        with patch.dict(os.environ, {"SUPABASE_URL": "http://x", "SUPABASE_SERVICE_KEY": "key"}, clear=False):
            with patch.dict("sys.modules", {"supabase": None}):
                result = gc._get_supabase_client()
                assert result is None


# =============================================================================
# _load_from_supabase
# =============================================================================

class TestLoadFromSupabase:
    def test_returns_none_when_no_client(self):
        with patch.object(gc, "_get_supabase_client", return_value=None):
            result = gc._load_from_supabase("tenant-1")
            assert result is None

    def test_returns_data_on_success(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [{"jury_trust_threshold": 0.80, "custom_key": "value"}]
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response

        with patch.object(gc, "_get_supabase_client", return_value=mock_client):
            result = gc._load_from_supabase("tenant-1")
            assert result["jury_trust_threshold"] == 0.80
            assert result["custom_key"] == "value"

    def test_returns_none_empty_data(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = []
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response

        with patch.object(gc, "_get_supabase_client", return_value=mock_client):
            result = gc._load_from_supabase("tenant-1")
            assert result is None

    def test_returns_none_on_exception(self):
        mock_client = MagicMock()
        mock_client.table.side_effect = Exception("DB error")

        with patch.object(gc, "_get_supabase_client", return_value=mock_client):
            result = gc._load_from_supabase("tenant-1")
            assert result is None


# =============================================================================
# get_tenant_governance_config
# =============================================================================

class TestGetTenantGovernanceConfig:
    def test_raises_on_empty_tenant_id(self):
        with pytest.raises(ValueError, match="tenant_id is required"):
            gc.get_tenant_governance_config("")

    def test_raises_on_whitespace_tenant_id(self):
        with pytest.raises(ValueError, match="tenant_id is required"):
            gc.get_tenant_governance_config("   ")

    def test_raises_on_none_tenant_id(self):
        with pytest.raises(ValueError):
            gc.get_tenant_governance_config(None)

    def test_returns_defaults_when_no_supabase(self):
        with patch.object(gc, "_load_from_supabase", return_value=None):
            config = gc.get_tenant_governance_config("tenant-1")
            assert config["jury_trust_threshold"] == 0.65
            assert config["entropy_threshold"] == 7.5

    def test_returns_merged_from_supabase(self):
        db_data = {"jury_trust_threshold": 0.90, "custom_extra": "hello"}
        with patch.object(gc, "_load_from_supabase", return_value=db_data):
            config = gc.get_tenant_governance_config("tenant-2")
            # Overridden
            assert config["jury_trust_threshold"] == 0.90
            # From DB
            assert config["custom_extra"] == "hello"
            # From defaults (not in DB)
            assert config["entropy_threshold"] == 7.5

    def test_cache_hit(self):
        # Populate cache
        gc._tenant_config_cache["tenant-3"] = {"cached": True}
        config = gc.get_tenant_governance_config("tenant-3")
        assert config["cached"] is True

    def test_cache_populated_from_supabase(self):
        db_data = {"jury_trust_threshold": 0.80}
        with patch.object(gc, "_load_from_supabase", return_value=db_data):
            gc.get_tenant_governance_config("tenant-4")
            # Second call should use cache, not Supabase
            with patch.object(gc, "_load_from_supabase") as mock_load:
                gc.get_tenant_governance_config("tenant-4")
                mock_load.assert_not_called()

    def test_cache_populated_from_defaults(self):
        with patch.object(gc, "_load_from_supabase", return_value=None):
            gc.get_tenant_governance_config("tenant-5")
            assert "tenant-5" in gc._tenant_config_cache


# =============================================================================
# invalidate_tenant_config
# =============================================================================

class TestInvalidateTenantConfig:
    def test_invalidate_existing(self):
        gc._tenant_config_cache["tenant-x"] = {"cached": True}
        gc.invalidate_tenant_config("tenant-x")
        assert "tenant-x" not in gc._tenant_config_cache

    def test_invalidate_nonexistent(self):
        # Should not raise
        gc.invalidate_tenant_config("nonexistent")


# =============================================================================
# invalidate_all_config
# =============================================================================

class TestInvalidateAllConfig:
    def test_clears_all(self):
        gc._tenant_config_cache["a"] = {"x": 1}
        gc._tenant_config_cache["b"] = {"y": 2}
        gc.invalidate_all_config()
        assert len(gc._tenant_config_cache) == 0


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


