"""Tests for shadow-sop/api.py — FastAPI endpoints.

We mock `shadow_executor` and `rlhc` before importing api.py
so the module-level instantiation of ShadowExecutor() and ShadowSOPRLHC() works.
"""

import sys
import os
import importlib.util
import json

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import unittest.mock as mock

# --- Save originals so we can restore after api.py import ---
_MOCKED_KEYS = [
    "config", "config.governance_config",
    "psycopg2", "psycopg2.pool", "psycopg2.extras",
    "shadow_executor", "rlhc",
]
_saved_modules = {k: sys.modules.get(k) for k in _MOCKED_KEYS}

# --- Mock heavyweight dependencies ---
_fake_gov_mod = mock.MagicMock()
_fake_gov_mod.get_tenant_governance_config = mock.MagicMock(return_value={})
sys.modules.setdefault("config", mock.MagicMock())
sys.modules["config.governance_config"] = _fake_gov_mod
sys.modules.setdefault("psycopg2", mock.MagicMock())
sys.modules.setdefault("psycopg2.pool", mock.MagicMock())
sys.modules.setdefault("psycopg2.extras", mock.MagicMock())

# --- Mock shadow_executor module ---
_fake_shadow_executor_mod = mock.MagicMock()
_fake_shadow_executor_mod.ShadowExecutor = mock.MagicMock(return_value=mock.MagicMock())
_fake_shadow_executor_mod.ShadowVerdict = mock.MagicMock()
sys.modules["shadow_executor"] = _fake_shadow_executor_mod

# Import real rlhc module (it has ShadowSOPRLHC and CorrectionType)
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_rlhc_path = os.path.join(_ROOT, "shadow-sop", "rlhc.py")
_rlhc_spec = importlib.util.spec_from_file_location("rlhc", _rlhc_path)
rlhc_mod = importlib.util.module_from_spec(_rlhc_spec)
sys.modules["rlhc"] = rlhc_mod
_rlhc_spec.loader.exec_module(rlhc_mod)

# Now import the actual api module
_api_path = os.path.join(_ROOT, "shadow-sop", "api.py")
_api_spec = importlib.util.spec_from_file_location("shadow_sop_api", _api_path)
api_mod = importlib.util.module_from_spec(_api_spec)
sys.modules["shadow_sop_api"] = api_mod
_api_spec.loader.exec_module(api_mod)

# --- Restore original modules so subsequent test files get real imports ---
for _k, _v in _saved_modules.items():
    if _v is None:
        sys.modules.pop(_k, None)
    else:
        sys.modules[_k] = _v

from fastapi.testclient import TestClient
import pytest

app = api_mod.app
client = TestClient(app)


class TestHealthEndpoint:
    def test_health(self):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "healthy"
        assert data["service"] == "shadow-sop-process-mining"


class TestShadowMetricsEndpoint:
    def test_get_all_shadow_metrics(self):
        r = client.get("/shadow/metrics", headers={"X-Tenant-ID": "t1"})
        assert r.status_code == 200


class TestRLHCStatsEndpoint:
    def test_get_stats(self):
        r = client.get("/rlhc/stats", headers={"X-Tenant-ID": "t1"})
        assert r.status_code == 200
        data = r.json()
        assert "total_corrections" in data


class TestRLHCPatternsEndpoint:
    def test_get_patterns(self):
        r = client.get("/rlhc/patterns", headers={"X-Tenant-ID": "t1"})
        assert r.status_code == 200


class TestRLHCProposalsEndpoint:
    def test_get_proposals(self):
        r = client.get("/rlhc/proposals", headers={"X-Tenant-ID": "t1"})
        assert r.status_code == 200


class TestRecordCorrection:
    def test_record_correction(self):
        payload = {
            "agent_id": "agent-1",
            "action_type": "tool_execution",
            "correction_type": "BLOCK_OVERRIDE",
            "original_action": {"action": "ALLOW"},
            "corrected_action": {"action": "BLOCK"},
            "reviewer_id": "human-1",
            "reason": "Payment amount too high",
        }
        r = client.post(
            "/rlhc/corrections",
            json=payload,
            headers={"X-Tenant-ID": "t1"},
        )
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Coverage Boost: Shadow Metrics by SOP ID
# ---------------------------------------------------------------------------

class TestShadowMetricsBySop:
    def test_metrics_found(self):
        # Mock get_metrics to return a metrics object
        mock_metrics = mock.MagicMock()
        mock_metrics.sop_id = "sop-1"
        mock_metrics.tenant_id = "t1"
        mock_metrics.total_executions = 100
        mock_metrics.divergence_rate = 0.05
        mock_metrics.confidence_score = 0.95
        api_mod.shadow_executor.get_metrics = mock.MagicMock(return_value=mock_metrics)
        api_mod.shadow_executor.should_promote = mock.MagicMock(return_value=True)
        r = client.get("/shadow/metrics/sop-1", headers={"X-Tenant-ID": "t1"})
        assert r.status_code == 200
        data = r.json()
        assert data["sop_id"] == "sop-1"
        assert data["promotable"] is True

    def test_metrics_not_found(self):
        api_mod.shadow_executor.get_metrics = mock.MagicMock(return_value=None)
        r = client.get("/shadow/metrics/nonexistent", headers={"X-Tenant-ID": "t1"})
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Coverage Boost: Shadow Results
# ---------------------------------------------------------------------------

class TestShadowResults:
    def test_get_results(self):
        mock_result = mock.MagicMock()
        mock_result.execution_id = "exec-1"
        mock_result.verdict = mock.MagicMock(value="IDENTICAL")
        mock_result.latency_prod_ms = 23.45
        mock_result.latency_shadow_ms = 25.12
        mock_result.timestamp = "2026-01-01T00:00:00Z"
        api_mod.shadow_executor.get_results = mock.MagicMock(return_value=[mock_result])
        r = client.get("/shadow/results/sop-1", headers={"X-Tenant-ID": "t1"})
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 1
        assert data["results"][0]["verdict"] == "IDENTICAL"


# ---------------------------------------------------------------------------
# Coverage Boost: Shadow Promote
# ---------------------------------------------------------------------------

class TestShadowPromote:
    def test_promote_check(self):
        mock_metrics = mock.MagicMock()
        mock_metrics.confidence_score = 0.97
        mock_metrics.total_executions = 200
        api_mod.shadow_executor.get_metrics = mock.MagicMock(return_value=mock_metrics)
        api_mod.shadow_executor.should_promote = mock.MagicMock(return_value=True)
        r = client.post("/shadow/promote/sop-1", headers={"X-Tenant-ID": "t1"})
        assert r.status_code == 200
        data = r.json()
        assert data["promotable"] is True

    def test_promote_no_metrics(self):
        api_mod.shadow_executor.get_metrics = mock.MagicMock(return_value=None)
        api_mod.shadow_executor.should_promote = mock.MagicMock(return_value=False)
        r = client.post("/shadow/promote/sop-no", headers={"X-Tenant-ID": "t1"})
        assert r.status_code == 200
        data = r.json()
        assert data["promotable"] is False
        assert data["confidence"] == 0


# ---------------------------------------------------------------------------
# Coverage Boost: Tenant Config Header
# ---------------------------------------------------------------------------

class TestTenantConfig:
    def test_valid_tenant_config_json(self):
        cfg = json.dumps({"rlhc_min_corrections_for_pattern": 5})
        payload = {
            "agent_id": "agent-1",
            "action_type": "exec",
            "correction_type": "ALLOW_OVERRIDE",
            "original_action": {"action": "BLOCK"},
            "corrected_action": {"action": "ALLOW"},
            "reviewer_id": "admin",
            "reason": "False positive",
        }
        r = client.post(
            "/rlhc/corrections",
            json=payload,
            headers={"X-Tenant-ID": "t1", "X-Tenant-Config": cfg},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["config"]["min_corrections_for_pattern"] == 5

    def test_invalid_tenant_config_json(self):
        payload = {
            "agent_id": "agent-1",
            "action_type": "exec",
            "correction_type": "ALLOW_OVERRIDE",
            "original_action": {"action": "BLOCK"},
            "corrected_action": {"action": "ALLOW"},
            "reviewer_id": "admin",
            "reason": "ok",
        }
        r = client.post(
            "/rlhc/corrections",
            json=payload,
            headers={"X-Tenant-ID": "t1", "X-Tenant-Config": "NOT-JSON"},
        )
        # Should still succeed — falls back to defaults
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Coverage Boost: Invalid Correction Type
# ---------------------------------------------------------------------------

class TestInvalidCorrectionType:
    def test_bad_correction_type_returns_400(self):
        payload = {
            "agent_id": "agent-1",
            "action_type": "exec",
            "correction_type": "INVALID_TYPE",
            "original_action": {},
            "corrected_action": {},
            "reviewer_id": "admin",
            "reason": "test",
        }
        r = client.post(
            "/rlhc/corrections",
            json=payload,
            headers={"X-Tenant-ID": "t1"},
        )
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Coverage Boost: Traces (with no SUPABASE_URL configured)
# ---------------------------------------------------------------------------

class TestTracesNoSupabase:
    def test_list_traces_no_supabase(self):
        # SUPABASE_URL should be "" by default in test env
        r = client.get("/traces", headers={"X-Tenant-ID": "t1"})
        assert r.status_code == 200
        data = r.json()
        assert data["traces"] == []
        assert "not configured" in data.get("message", "")

    def test_create_trace_no_supabase(self):
        payload = {
            "process_id": "proc-1",
            "agent_id": "agent-1",
            "step_name": "step-1",
        }
        r = client.post("/traces", json=payload, headers={"X-Tenant-ID": "t1"})
        assert r.status_code == 503

    def test_get_trace_no_supabase(self):
        r = client.get("/traces/trace-1", headers={"X-Tenant-ID": "t1"})
        assert r.status_code == 503


# ---------------------------------------------------------------------------
# Coverage Boost: Trace CRUD with SUPABASE_URL set (httpx mocked)
# ---------------------------------------------------------------------------

class TestTracesWithSupabase:
    def test_list_traces_success(self):
        api_mod.SUPABASE_URL = "https://fake.supabase.co"
        api_mod.SUPABASE_KEY = "fake-key"
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"trace_id": "t1", "process_id": "p1"}]
        with mock.patch("httpx.AsyncClient") as MockClient:
            instance = mock.AsyncMock()
            instance.get.return_value = mock_resp
            MockClient.return_value.__aenter__ = mock.AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = mock.AsyncMock(return_value=False)
            r = client.get("/traces", headers={"X-Tenant-ID": "t1"})
        assert r.status_code == 200
        assert len(r.json()["traces"]) == 1
        api_mod.SUPABASE_URL = ""
        api_mod.SUPABASE_KEY = ""

    def test_list_traces_error(self):
        api_mod.SUPABASE_URL = "https://fake.supabase.co"
        api_mod.SUPABASE_KEY = "fake-key"
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal error"
        with mock.patch("httpx.AsyncClient") as MockClient:
            instance = mock.AsyncMock()
            instance.get.return_value = mock_resp
            MockClient.return_value.__aenter__ = mock.AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = mock.AsyncMock(return_value=False)
            r = client.get("/traces", headers={"X-Tenant-ID": "t1"})
        assert r.status_code == 500
        api_mod.SUPABASE_URL = ""
        api_mod.SUPABASE_KEY = ""

    def test_create_trace_success(self):
        api_mod.SUPABASE_URL = "https://fake.supabase.co"
        api_mod.SUPABASE_KEY = "fake-key"
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = [{"trace_id": "new-1"}]
        with mock.patch("httpx.AsyncClient") as MockClient:
            instance = mock.AsyncMock()
            instance.post.return_value = mock_resp
            MockClient.return_value.__aenter__ = mock.AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = mock.AsyncMock(return_value=False)
            r = client.post(
                "/traces",
                json={"process_id": "p1", "agent_id": "a1", "step_name": "s1"},
                headers={"X-Tenant-ID": "t1"},
            )
        assert r.status_code == 200
        api_mod.SUPABASE_URL = ""
        api_mod.SUPABASE_KEY = ""

    def test_create_trace_error(self):
        api_mod.SUPABASE_URL = "https://fake.supabase.co"
        api_mod.SUPABASE_KEY = "fake-key"
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Bad request"
        with mock.patch("httpx.AsyncClient") as MockClient:
            instance = mock.AsyncMock()
            instance.post.return_value = mock_resp
            MockClient.return_value.__aenter__ = mock.AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = mock.AsyncMock(return_value=False)
            r = client.post(
                "/traces",
                json={"process_id": "p1", "agent_id": "a1", "step_name": "s1"},
                headers={"X-Tenant-ID": "t1"},
            )
        assert r.status_code == 400
        api_mod.SUPABASE_URL = ""
        api_mod.SUPABASE_KEY = ""

    def test_get_trace_found(self):
        api_mod.SUPABASE_URL = "https://fake.supabase.co"
        api_mod.SUPABASE_KEY = "fake-key"
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"trace_id": "tr-1", "process_id": "p1"}]
        with mock.patch("httpx.AsyncClient") as MockClient:
            instance = mock.AsyncMock()
            instance.get.return_value = mock_resp
            MockClient.return_value.__aenter__ = mock.AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = mock.AsyncMock(return_value=False)
            r = client.get("/traces/tr-1", headers={"X-Tenant-ID": "t1"})
        assert r.status_code == 200
        assert r.json()["trace_id"] == "tr-1"
        api_mod.SUPABASE_URL = ""
        api_mod.SUPABASE_KEY = ""

    def test_get_trace_not_found(self):
        api_mod.SUPABASE_URL = "https://fake.supabase.co"
        api_mod.SUPABASE_KEY = "fake-key"
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        with mock.patch("httpx.AsyncClient") as MockClient:
            instance = mock.AsyncMock()
            instance.get.return_value = mock_resp
            MockClient.return_value.__aenter__ = mock.AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = mock.AsyncMock(return_value=False)
            r = client.get("/traces/missing", headers={"X-Tenant-ID": "t1"})
        assert r.status_code == 404
        api_mod.SUPABASE_URL = ""
        api_mod.SUPABASE_KEY = ""


# ---------------------------------------------------------------------------
# Coverage Boost: _supabase_headers helper
# ---------------------------------------------------------------------------

class TestSupabaseHeaders:
    def test_headers_returned(self):
        api_mod.SUPABASE_KEY = "test-key"
        headers = api_mod._supabase_headers()
        assert headers["apikey"] == "test-key"
        assert "Bearer test-key" in headers["Authorization"]
        assert headers["Content-Type"] == "application/json"
        api_mod.SUPABASE_KEY = ""


# ---------------------------------------------------------------------------
# Coverage Boost: Shadow results empty + GET all metrics with data
# ---------------------------------------------------------------------------

class TestShadowResultsEmpty:
    def test_get_results_empty(self):
        api_mod.shadow_executor.get_results = mock.MagicMock(return_value=[])
        r = client.get("/shadow/results/sop-empty", headers={"X-Tenant-ID": "t1"})
        assert r.status_code == 200
        assert r.json()["count"] == 0
        assert r.json()["results"] == []

class TestGetAllMetricsWithData:
    def test_all_metrics_with_data(self):
        m1 = mock.MagicMock()
        m1.sop_id = "sop-1"
        m1.total_executions = 50
        m1.identical_count = 40
        m1.equivalent_count = 5
        m1.divergent_count = 3
        m1.shadow_better_count = 1
        m1.shadow_worse_count = 1
        m1.shadow_error_count = 0
        m1.avg_latency_delta_ms = 2.345
        m1.divergence_rate = 0.06
        m1.confidence_score = 0.94
        m1.started_at = "2026-01-01T00:00:00Z"
        m1.last_execution_at = "2026-01-02T00:00:00Z"
        api_mod.shadow_executor.get_all_metrics = mock.MagicMock(return_value={"sop-1": m1})
        r = client.get("/shadow/metrics", headers={"X-Tenant-ID": "t1"})
        assert r.status_code == 200
        data = r.json()
        assert len(data["experiments"]) == 1
        assert data["experiments"][0]["total_executions"] == 50

