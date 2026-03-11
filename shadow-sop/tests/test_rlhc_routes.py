import sys
import os
import json
import importlib.util

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import unittest.mock as mock

# Import real fastapi FIRST (before any mock contamination)
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# --- Stub external dependencies before importing rlhc ---
_fake_gov_mod = mock.MagicMock()
_fake_gov_mod.get_tenant_governance_config = mock.MagicMock(return_value={})
sys.modules.setdefault("config", mock.MagicMock())
sys.modules["config.governance_config"] = _fake_gov_mod

# Stub psycopg2 properly so pool and extras resolve
_fake_pg = mock.MagicMock()
sys.modules["psycopg2"] = _fake_pg
sys.modules["psycopg2.pool"] = _fake_pg.pool
sys.modules["psycopg2.extras"] = _fake_pg.extras
_fake_pg.extras.RealDictCursor = "RealDictCursor"

# Import the module via importlib so we get fresh objects
_rlhc_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "rlhc.py",
)
_spec = importlib.util.spec_from_file_location("rlhc_routes", _rlhc_path)
rlhc_mod = importlib.util.module_from_spec(_spec)
sys.modules["rlhc_routes"] = rlhc_mod
_spec.loader.exec_module(rlhc_mod)

router = rlhc_mod.router
get_db = rlhc_mod.get_db
_get_pool = rlhc_mod._get_pool


# --- Test harness ---

def _mock_conn():
    """Create a mock DB connection with a mock cursor."""
    conn = mock.MagicMock()
    cursor = mock.MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


def _make_app(conn):
    """Mount router on a test FastAPI app with DB override."""
    app = FastAPI()
    app.include_router(router, prefix="/rlhc")
    app.dependency_overrides[get_db] = lambda: conn
    return app


# ============================================================================
# Connection Pool & get_db (L618-643)
# ============================================================================

class TestConnectionPool:

    def test_get_pool_creates_pool_once(self):
        """_get_pool lazily creates a ThreadedConnectionPool."""
        rlhc_mod._db_pool = None
        fake_pool = mock.MagicMock()
        with mock.patch.object(rlhc_mod.psycopg2.pool, "ThreadedConnectionPool", return_value=fake_pool):
            result = rlhc_mod._get_pool()
            assert result is fake_pool
            # Second call returns the cached pool
            result2 = rlhc_mod._get_pool()
            assert result2 is fake_pool
        rlhc_mod._db_pool = None  # reset

    def test_get_db_yields_and_returns_conn(self):
        """get_db yields a pooled connection and returns it."""
        fake_pool = mock.MagicMock()
        fake_conn = mock.MagicMock()
        fake_pool.getconn.return_value = fake_conn

        rlhc_mod._db_pool = fake_pool
        gen = get_db()
        conn = next(gen)
        assert conn is fake_conn
        try:
            next(gen)
        except StopIteration:
            pass
        fake_pool.putconn.assert_called_once_with(fake_conn)
        rlhc_mod._db_pool = None  # reset


# ============================================================================
# POST /corrections (L670-764)
# ============================================================================

class TestRecordCorrection:

    def test_success_no_pattern(self):
        conn, cursor = _mock_conn()
        cursor.fetchone.side_effect = [
            {"id": 42},     # INSERT RETURNING id
            {"similar_count": 1},  # similar count (below threshold)
            {"min_corr": 3},  # governance threshold
        ]
        app = _make_app(conn)
        client = TestClient(app)
        resp = client.post("/rlhc/corrections", json={
            "tenant_id": "t1",
            "agent_id": "a1",
            "correction_type": "BLOCK_OVERRIDE",
            "original_action": "ALLOW",
            "corrected_action": "BLOCK",
            "tool_id": "tool-1",
            "transaction_id": "txn-1",
            "reviewer_id": "rev-1",
            "reasoning": "Too risky",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["correction_id"] == "42"
        assert data["similar_count"] == 1
        conn.commit.assert_called_once()

    def test_success_with_pattern_creation(self):
        conn, cursor = _mock_conn()
        cursor.fetchone.side_effect = [
            {"id": 99},
            {"similar_count": 5},  # >= threshold → creates cluster
            {"min_corr": 3},
        ]
        app = _make_app(conn)
        client = TestClient(app)
        resp = client.post("/rlhc/corrections", json={
            "tenant_id": "t1",
            "agent_id": "a1",
            "correction_type": "ALLOW_OVERRIDE",
            "original_action": "BLOCK",
            "corrected_action": "ALLOW",
            "tool_id": "tool-2",
            "transaction_id": "txn-2",
            "reviewer_id": "rev-1",
            "reasoning": "False positive",
        }, headers={"X-Department": "finance"})
        assert resp.status_code == 200
        # Should have inserted correction + cluster
        assert cursor.execute.call_count >= 4

    def test_success_modify_pattern_type(self):
        """MODIFY_OUTPUT correction type produces MODIFY_PATTERN."""
        conn, cursor = _mock_conn()
        cursor.fetchone.side_effect = [
            {"id": 7},
            {"similar_count": 10},
            {"min_corr": 3},
        ]
        app = _make_app(conn)
        client = TestClient(app)
        resp = client.post("/rlhc/corrections", json={
            "tenant_id": "t1",
            "agent_id": "a1",
            "correction_type": "REFORMAT",
            "original_action": "RAW",
            "corrected_action": "FORMATTED",
            "tool_id": "tool-3",
            "transaction_id": "txn-3",
            "reviewer_id": "rev-1",
            "reasoning": "Wrong format",
        })
        assert resp.status_code == 200

    def test_db_error_returns_500(self):
        conn, cursor = _mock_conn()
        cursor.execute.side_effect = Exception("DB gone")
        app = _make_app(conn)
        client = TestClient(app)
        resp = client.post("/rlhc/corrections", json={
            "tenant_id": "t1",
            "agent_id": "a1",
            "correction_type": "BLOCK_OVERRIDE",
            "original_action": "ALLOW",
            "corrected_action": "BLOCK",
            "tool_id": "tool-1",
            "transaction_id": "txn-1",
            "reviewer_id": "rev-1",
            "reasoning": "Reason",
        })
        assert resp.status_code == 500
        conn.rollback.assert_called_once()


# ============================================================================
# GET /policies/pending (L767-808)
# ============================================================================

class TestGetPendingPolicies:

    def _make_row(self, idx):
        return {
            "id": idx,
            "cluster_name": f"RLHC-pattern-{idx}",
            "correction_count": 5,
            "pattern_type": "BLOCK_PATTERN",
            "trigger_conditions": json.dumps({"key": "val"}),
            "first_seen": mock.MagicMock(isoformat=lambda: "2026-01-01T00:00:00Z"),
            "confidence_score": 0.8,
        }

    def test_returns_pending_no_department(self):
        conn, cursor = _mock_conn()
        cursor.fetchall.return_value = [self._make_row(1)]
        app = _make_app(conn)
        client = TestClient(app)
        resp = client.get("/rlhc/policies/pending", params={"tenant_id": "t1"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["policy_id"] == "1"

    def test_returns_pending_with_department(self):
        conn, cursor = _mock_conn()
        cursor.fetchall.return_value = [self._make_row(2)]
        app = _make_app(conn)
        client = TestClient(app)
        resp = client.get("/rlhc/policies/pending", params={
            "tenant_id": "t1", "department": "finance",
        })
        assert resp.status_code == 200

    def test_returns_pending_with_header_department(self):
        conn, cursor = _mock_conn()
        cursor.fetchall.return_value = []
        app = _make_app(conn)
        client = TestClient(app)
        resp = client.get("/rlhc/policies/pending",
                          params={"tenant_id": "t1"},
                          headers={"X-Department": "ops"})
        assert resp.status_code == 200


# ============================================================================
# POST /policies/{id}/approve (L811-838)
# ============================================================================

class TestApprovePolicy:

    def test_approve_success(self):
        conn, cursor = _mock_conn()
        cursor.fetchone.return_value = {
            "id": 10,
            "cluster_name": "RLHC-test",
        }
        app = _make_app(conn)
        client = TestClient(app)
        resp = client.post("/rlhc/policies/10/approve",
                           params={"tenant_id": "t1"},
                           json={"reviewer_id": "rev-1"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        conn.commit.assert_called_once()

    def test_approve_not_found(self):
        conn, cursor = _mock_conn()
        cursor.fetchone.return_value = None
        app = _make_app(conn)
        client = TestClient(app)
        resp = client.post("/rlhc/policies/999/approve",
                           params={"tenant_id": "t1"},
                           json={"reviewer_id": "rev-1"})
        assert resp.status_code == 400


# ============================================================================
# POST /policies/{id}/reject (L841-868)
# ============================================================================

class TestRejectPolicy:

    def test_reject_success(self):
        conn, cursor = _mock_conn()
        cursor.fetchone.return_value = {
            "id": 20,
            "cluster_name": "RLHC-bad",
        }
        app = _make_app(conn)
        client = TestClient(app)
        resp = client.post("/rlhc/policies/20/reject",
                           params={"tenant_id": "t1"},
                           json={"reviewer_id": "rev-2", "reason": "Not valid"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        conn.commit.assert_called_once()

    def test_reject_not_found(self):
        conn, cursor = _mock_conn()
        cursor.fetchone.return_value = None
        app = _make_app(conn)
        client = TestClient(app)
        resp = client.post("/rlhc/policies/999/reject",
                           params={"tenant_id": "t1"},
                           json={"reviewer_id": "rev-2", "reason": "Nope"})
        assert resp.status_code == 400


# ============================================================================
# GET /stats (L871-915)
# ============================================================================

class TestGetStats:

    def test_stats_success(self):
        conn, cursor = _mock_conn()
        cursor.fetchone.side_effect = [
            {
                "total_corrections": 100,
                "allow_overrides": 40,
                "block_overrides": 50,
                "modify_outputs": 10,
            },
            {
                "total_patterns": 20,
                "pending": 5,
                "promoted": 12,
                "rejected": 3,
            },
        ]
        app = _make_app(conn)
        client = TestClient(app)
        resp = client.get("/rlhc/stats", params={"tenant_id": "t1"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_corrections"] == 100
        assert data["patterns_generated"] == 20
        assert data["policies_pending"] == 5
        assert data["policies_approved"] == 12
