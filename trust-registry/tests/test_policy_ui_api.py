"""
Policy UI API — pytest unit test suite.

Tests FastAPI endpoints with mocked psycopg2 DB connection.
"""

import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

# Ensure trust-registry is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from policy_ui_api import router
from fastapi import FastAPI
from fastapi.testclient import TestClient


# --- Test app setup ---

app = FastAPI()
app.include_router(router)

# --- Mock DB ---

@pytest.fixture
def mock_db():
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    return mock_conn, mock_cursor


@pytest.fixture
def client(mock_db):
    mock_conn, _ = mock_db

    def override_get_db():
        try:
            yield mock_conn
        finally:
            pass

    from policy_ui_api import get_db
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


# =============================================================================
# GET /policies
# =============================================================================

class TestListPolicies:
    def test_list_empty(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchall.return_value = []
        resp = client.get("/policies", headers={"X-Tenant-ID": "t-1"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["policies"] == []

    def test_list_with_tier_filter(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchall.return_value = []
        resp = client.get("/policies?tier=GLOBAL", headers={"X-Tenant-ID": "t-1"})
        assert resp.status_code == 200

    def test_list_with_department(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchall.return_value = []
        resp = client.get(
            "/policies?department=Finance",
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 200

    def test_list_with_department_header(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchall.return_value = []
        resp = client.get(
            "/policies",
            headers={"X-Tenant-ID": "t-1", "X-Department": "HR"},
        )
        assert resp.status_code == 200

    def test_list_with_results(self, client, mock_db):
        _, cursor = mock_db
        now = datetime.now(timezone.utc)
        cursor.fetchall.return_value = [{
            "policy_id": "p-1",
            "version": 1,
            "tier": "GLOBAL",
            "trigger_intent": "approve_po",
            "logic": {"condition": "amount > 100"},
            "action": {"on_fail": "reject"},
            "confidence": 0.9,
            "source_name": "GPT-4",
            "roles": ["admin"],
            "is_active": True,
            "department": None,
            "created_at": now,
        }]
        resp = client.get("/policies", headers={"X-Tenant-ID": "t-1"})
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_missing_tenant_header(self, client):
        resp = client.get("/policies")
        assert resp.status_code == 422


# =============================================================================
# POST /policies
# =============================================================================

class TestCreatePolicy:
    def test_create_success(self, client, mock_db):
        _, cursor = mock_db
        now = datetime.now(timezone.utc)
        cursor.fetchone.return_value = {
            "policy_id": "p-new",
            "version": 1,
            "tier": "GLOBAL",
            "trigger_intent": "approve_po",
            "logic": {"condition": "amount > 0"},
            "action": {"on_fail": "reject"},
            "confidence": 0.8,
            "source_name": "GPT-4",
            "is_active": True,
            "created_at": now,
        }
        resp = client.post(
            "/policies",
            json={
                "policy_id": "p-new",
                "tier": "GLOBAL",
                "trigger_intent": "approve_po",
                "logic": {"condition": "amount > 0"},
                "action": {"on_fail": "reject"},
                "confidence": 0.8,
                "source_name": "GPT-4",
            },
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 200
        assert resp.json()["policy_id"] == "p-new"


# =============================================================================
# PUT /policies/{policy_id}
# =============================================================================

class TestUpdatePolicy:
    def test_not_found(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchone.return_value = None
        resp = client.put(
            "/policies/p-missing",
            json={"logic": {"new": "logic"}},
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 404

    def test_max_versions(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchone.return_value = {
            "version": 18,
            "tier": "GLOBAL",
            "trigger_intent": "approve_po",
            "logic": {"old": True},
            "action": {"on_fail": "reject"},
            "confidence": 0.8,
            "source_name": "GPT-4",
        }
        resp = client.put(
            "/policies/p-1",
            json={"logic": {"new": "logic"}},
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 400
        assert "maximum" in resp.json()["detail"].lower()


# =============================================================================
# GET /policies/{policy_id}/versions
# =============================================================================

class TestVersionHistory:
    def test_not_found(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchall.return_value = []
        resp = client.get(
            "/policies/p-missing/versions",
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 404

    def test_versions_found(self, client, mock_db):
        _, cursor = mock_db
        now = datetime.now(timezone.utc)
        cursor.fetchall.return_value = [
            {
                "version": 2,
                "tier": "GLOBAL",
                "logic": {"v": 2},
                "action": {"on_fail": "reject"},
                "confidence": 0.9,
                "is_active": True,
                "created_at": now,
            },
            {
                "version": 1,
                "tier": "GLOBAL",
                "logic": {"v": 1},
                "action": {"on_fail": "reject"},
                "confidence": 0.8,
                "is_active": False,
                "created_at": now,
            },
        ]
        resp = client.get(
            "/policies/p-1/versions",
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 200
        assert resp.json()["total_versions"] == 2


# =============================================================================
# POST /policies/{policy_id}/rollback
# =============================================================================

class TestRollback:
    def test_rollback_not_found(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchone.return_value = None
        resp = client.post(
            "/policies/p-1/rollback?target_version=1",
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 404


# =============================================================================
# GET /conflicts
# =============================================================================

class TestConflicts:
    def test_no_conflicts(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchall.return_value = []
        resp = client.get("/conflicts", headers={"X-Tenant-ID": "t-1"})
        assert resp.status_code == 200
        assert resp.json()["total_conflicts"] == 0

    def test_conflicts_detected(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchall.return_value = [
            {
                "policy_id": "p-1",
                "trigger_intent": "approve_po",
                "tier": "GLOBAL",
                "action": json.dumps({"on_fail": "reject"}),
            },
            {
                "policy_id": "p-2",
                "trigger_intent": "approve_po",
                "tier": "GLOBAL",
                "action": json.dumps({"on_fail": "escalate"}),
            },
        ]
        resp = client.get("/conflicts", headers={"X-Tenant-ID": "t-1"})
        assert resp.status_code == 200
        assert resp.json()["total_conflicts"] == 1


# =============================================================================
# GET /stats
# =============================================================================

class TestStats:
    def test_stats(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchone.return_value = {
            "total": 10,
            "active": 5,
            "expired": 2,
            "global_count": 3,
            "contextual_count": 1,
            "dynamic_count": 1,
        }
        resp = client.get("/stats", headers={"X-Tenant-ID": "t-1"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 10
        assert data["active"] == 5


# =============================================================================
# DELETE /policies/{policy_id}
# =============================================================================

class TestDeletePolicy:
    def test_delete_not_found(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchall.return_value = []
        resp = client.delete(
            "/policies/p-missing",
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 404

    def test_delete_success(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchall.return_value = [
            {"policy_id": "p-1", "tier": "GLOBAL"},
        ]
        resp = client.delete(
            "/policies/p-1",
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "deactivated"


# =============================================================================
# GET /policies/{policy_id}/compare
# =============================================================================

class TestCompareVersions:
    def test_compare_missing_versions(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchall.return_value = [{"version": 1}]  # Only 1, need 2
        resp = client.get(
            "/policies/p-1/compare?version_a=1&version_b=2",
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 404

    def test_compare_success(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchall.return_value = [
            {
                "version": 1, "tier": "GLOBAL", "trigger_intent": "approve_po",
                "logic": json.dumps({"condition": "amount > 0"}),
                "action": json.dumps({"on_fail": "reject"}),
                "confidence": 0.8, "is_active": False,
            },
            {
                "version": 2, "tier": "GLOBAL", "trigger_intent": "approve_po",
                "logic": json.dumps({"condition": "amount > 100"}),
                "action": json.dumps({"on_fail": "escalate"}),
                "confidence": 0.9, "is_active": True,
            },
        ]
        resp = client.get(
            "/policies/p-1/compare?version_a=1&version_b=2",
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["policy_id"] == "p-1"
        assert "differences" in data


# =============================================================================
# Additional coverage: UpdatePolicy success path (L232-270)
# =============================================================================

class TestUpdatePolicySuccess:
    def test_update_success(self, client, mock_db):
        _, cursor = mock_db
        # First fetchone: get latest version
        # Second fetchone: INSERT RETURNING version
        cursor.fetchone.side_effect = [
            {
                "version": 2,
                "tier": "GLOBAL",
                "trigger_intent": "approve_po",
                "logic": {"condition": "amount > 0"},
                "action": {"on_fail": "reject"},
                "confidence": 0.8,
                "source_name": "GPT-4",
                "roles": ["admin"],
                "expires_at": None,
            },
            {"version": 3},
        ]
        resp = client.put(
            "/policies/p-1",
            json={"logic": {"condition": "amount > 100"}, "confidence": 0.95},
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == 3

    def test_update_error_rollback(self, client, mock_db):
        mock_conn, cursor = mock_db
        cursor.fetchone.return_value = {
            "version": 1, "tier": "GLOBAL",
            "trigger_intent": "approve_po",
            "logic": {"old": True},
            "action": {"on_fail": "reject"},
            "confidence": 0.8,
            "source_name": "GPT-4",
            "roles": [], "expires_at": None,
        }
        # Make the INSERT fail
        call_count = [0]
        original_execute = cursor.execute
        def _fail_on_insert(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] >= 3:  # UPDATE ok, INSERT fails
                raise Exception("DB error")
        cursor.execute.side_effect = _fail_on_insert
        resp = client.put(
            "/policies/p-1",
            json={"logic": {"new": True}},
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 500


# =============================================================================
# Additional coverage: Rollback success (L333-382)
# =============================================================================

class TestRollbackSuccess:
    def test_rollback_success(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchone.side_effect = [
            # First: target version exists
            {
                "tier": "GLOBAL",
                "trigger_intent": "approve_po",
                "logic": {"old": True},
                "action": {"on_fail": "reject"},
                "confidence": 0.8,
                "source_name": "GPT-4",
                "roles": ["admin"],
                "expires_at": None,
            },
            # Second: MAX(version) query
            {"max_v": 3},
            # Third: INSERT RETURNING version
            {"version": 4},
        ]
        resp = client.post(
            "/policies/p-1/rollback?target_version=1",
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["new_version"] == 4
        assert data["rolled_back_to"] == 1

    def test_rollback_exceeds_max_versions(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchone.side_effect = [
            {"tier": "GLOBAL", "trigger_intent": "approve_po",
             "logic": {}, "action": {}, "confidence": 0.5,
             "source_name": "X", "roles": [], "expires_at": None},
            {"max_v": 20},  # 20+1 > MAX
        ]
        resp = client.post(
            "/policies/p-1/rollback?target_version=1",
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 400
        assert "maximum" in resp.json()["detail"].lower()

    def test_rollback_db_error(self, client, mock_db):
        mock_conn, cursor = mock_db
        cursor.fetchone.side_effect = [
            {"tier": "GLOBAL", "trigger_intent": "approve_po",
             "logic": {}, "action": {}, "confidence": 0.5,
             "source_name": "X", "roles": [], "expires_at": None},
            {"max_v": 2},
        ]
        call_count = [0]
        def _fail_on_deactivate(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] >= 3:
                raise Exception("DB crashed")
        cursor.execute.side_effect = _fail_on_deactivate
        resp = client.post(
            "/policies/p-1/rollback?target_version=1",
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 500


# =============================================================================
# Additional coverage: CreatePolicy error paths (L194-201)
# =============================================================================

class TestCreatePolicyErrors:
    def test_integrity_error_duplicate(self, client, mock_db):
        mock_conn, cursor = mock_db
        import psycopg2
        cursor.execute.side_effect = psycopg2.IntegrityError("duplicate key value violates unique constraint")
        resp = client.post(
            "/policies",
            json={
                "policy_id": "p-dup",
                "tier": "GLOBAL",
                "trigger_intent": "approve_po",
                "logic": {"c": "d"},
                "action": {"on_fail": "reject"},
                "confidence": 0.8,
                "source_name": "GPT-4",
            },
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 400

    def test_general_error(self, client, mock_db):
        mock_conn, cursor = mock_db
        cursor.execute.side_effect = Exception("Something unexpected")
        resp = client.post(
            "/policies",
            json={
                "policy_id": "p-err",
                "tier": "GLOBAL",
                "trigger_intent": "approve_po",
                "logic": {"c": "d"},
                "action": {"on_fail": "reject"},
                "confidence": 0.8,
                "source_name": "GPT-4",
            },
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 500


class TestPolicyUIAPI:
    """Tests using FastAPI TestClient for policy_ui_api endpoints"""

    @pytest.fixture(autouse=True)
    def setup_app(self):
        """Create a test app with mocked DB dependency."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from policy_ui_api import router, get_db

        app = FastAPI()
        app.include_router(router)

        # Mock DB connection
        self.mock_conn = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_conn.cursor.return_value = self.mock_cursor

        def mock_get_db():
            yield self.mock_conn

        app.dependency_overrides[get_db] = mock_get_db
        self.client = TestClient(app)

    def _make_policy_row(self, **overrides):
        """Helper to create a mock DB row dict."""
        from datetime import datetime
        row = {
            "policy_id": "test-policy-1",
            "version": 1,
            "tier": "GLOBAL",
            "trigger_intent": "mcp.call_tool('execute_payment')",
            "logic": {"==": [1, 1]},
            "action": {"on_fail": "BLOCK", "on_pass": "ALLOW"},
            "confidence": 0.9,
            "source_name": "Test SOP",
            "roles": [],
            "is_active": True,
            "department": None,
            "created_at": datetime(2025, 1, 1),
            "expires_at": None,
        }
        row.update(overrides)
        return row

    def test_list_policies_empty(self):
        self.mock_cursor.fetchall.return_value = []
        resp = self.client.get("/policies", headers={"x-tenant-id": "t1"})
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_list_policies_with_results(self):
        self.mock_cursor.fetchall.return_value = [self._make_policy_row()]
        resp = self.client.get("/policies", headers={"x-tenant-id": "t1"})
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_list_policies_with_tier_filter(self):
        self.mock_cursor.fetchall.return_value = [self._make_policy_row(tier="CONTEXTUAL")]
        resp = self.client.get("/policies?tier=CONTEXTUAL", headers={"x-tenant-id": "t1"})
        assert resp.status_code == 200

    def test_list_policies_with_department(self):
        self.mock_cursor.fetchall.return_value = []
        resp = self.client.get(
            "/policies?department=SALES",
            headers={"x-tenant-id": "t1", "x-department": "FINANCE"}
        )
        assert resp.status_code == 200

    def test_create_policy_success(self):
        row = self._make_policy_row()
        self.mock_cursor.fetchone.return_value = row
        resp = self.client.post("/policies", json={
            "policy_id": "test-policy-1",
            "tier": "GLOBAL",
            "trigger_intent": "mcp.call_tool('execute_payment')",
            "logic": {"==": [1, 1]},
            "action": {"on_fail": "BLOCK", "on_pass": "ALLOW"},
            "confidence": 0.9,
            "source_name": "Test SOP"
        }, headers={"x-tenant-id": "t1"})
        assert resp.status_code == 200
        assert resp.json()["policy_id"] == "test-policy-1"

    def test_create_policy_duplicate(self):
        import psycopg2
        self.mock_cursor.execute.side_effect = psycopg2.IntegrityError("unique constraint")
        resp = self.client.post("/policies", json={
            "policy_id": "dup",
            "tier": "GLOBAL",
            "trigger_intent": "t",
            "logic": {},
            "action": {},
            "confidence": 0.5,
            "source_name": "s"
        }, headers={"x-tenant-id": "t1"})
        assert resp.status_code == 400

    def test_update_policy_success(self):
        latest = self._make_policy_row(version=1)
        self.mock_cursor.fetchone.side_effect = [latest, {"version": 2}]
        resp = self.client.put("/policies/test-policy-1", json={
            "logic": {"==": [2, 2]},
            "confidence": 0.95
        }, headers={"x-tenant-id": "t1"})
        assert resp.status_code == 200

    def test_update_policy_not_found(self):
        self.mock_cursor.fetchone.return_value = None
        resp = self.client.put("/policies/missing", json={
            "confidence": 0.5
        }, headers={"x-tenant-id": "t1"})
        assert resp.status_code == 404

    def test_get_version_history(self):
        rows = [self._make_policy_row(version=2), self._make_policy_row(version=1)]
        self.mock_cursor.fetchall.return_value = rows
        resp = self.client.get("/policies/test-policy-1/versions", headers={"x-tenant-id": "t1"})
        assert resp.status_code == 200
        assert resp.json()["total_versions"] == 2

    def test_get_version_history_not_found(self):
        self.mock_cursor.fetchall.return_value = []
        resp = self.client.get("/policies/missing/versions", headers={"x-tenant-id": "t1"})
        assert resp.status_code == 404

    def test_rollback_policy(self):
        target = self._make_policy_row(version=1)
        self.mock_cursor.fetchone.side_effect = [target, {"max_v": 2}, {"version": 3}]
        resp = self.client.post(
            "/policies/test-policy-1/rollback?target_version=1",
            headers={"x-tenant-id": "t1"}
        )
        assert resp.status_code == 200
        assert resp.json()["rolled_back_to"] == 1

    def test_rollback_version_not_found(self):
        self.mock_cursor.fetchone.return_value = None
        resp = self.client.post(
            "/policies/test-policy-1/rollback?target_version=99",
            headers={"x-tenant-id": "t1"}
        )
        assert resp.status_code == 404

    def test_compare_versions(self):
        rows = [
            self._make_policy_row(version=1),
            self._make_policy_row(version=2, tier="CONTEXTUAL")
        ]
        self.mock_cursor.fetchall.return_value = rows
        resp = self.client.get(
            "/policies/test-policy-1/compare?version_a=1&version_b=2",
            headers={"x-tenant-id": "t1"}
        )
        assert resp.status_code == 200
        diffs = resp.json()["differences"]
        assert diffs["tier_changed"] is True

    def test_compare_versions_missing(self):
        self.mock_cursor.fetchall.return_value = [self._make_policy_row()]
        resp = self.client.get(
            "/policies/test-policy-1/compare?version_a=1&version_b=99",
            headers={"x-tenant-id": "t1"}
        )
        assert resp.status_code == 404

    def test_detect_conflicts_none(self):
        self.mock_cursor.fetchall.return_value = []
        resp = self.client.get("/conflicts", headers={"x-tenant-id": "t1"})
        assert resp.status_code == 200
        assert resp.json()["total_conflicts"] == 0

    def test_detect_conflicts_found(self):
        rows = [
            self._make_policy_row(policy_id="p1", action={"on_fail": "BLOCK"}),
            self._make_policy_row(policy_id="p2", action={"on_fail": "ALLOW"}),
        ]
        self.mock_cursor.fetchall.return_value = rows
        resp = self.client.get("/conflicts", headers={"x-tenant-id": "t1"})
        assert resp.status_code == 200
        assert resp.json()["total_conflicts"] >= 1

    def test_get_stats(self):
        self.mock_cursor.fetchone.return_value = {
            "total": 10, "active": 8, "expired": 2,
            "global_count": 3, "contextual_count": 4, "dynamic_count": 1
        }
        resp = self.client.get("/stats", headers={"x-tenant-id": "t1"})
        assert resp.status_code == 200
        assert resp.json()["total"] == 10

    def test_delete_policy(self):
        self.mock_cursor.fetchall.return_value = [{"policy_id": "p1", "tier": "GLOBAL"}]
        resp = self.client.delete("/policies/p1", headers={"x-tenant-id": "t1"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "deactivated"

    def test_delete_policy_not_found(self):
        self.mock_cursor.fetchall.return_value = []
        resp = self.client.delete("/policies/missing", headers={"x-tenant-id": "t1"})
        assert resp.status_code == 404

