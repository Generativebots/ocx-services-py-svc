"""
Activity Registry — pytest unit test suite.

Tests helper functions + FastAPI endpoints with mocked DB.
Replaces the old live-HTTP test script.
"""

import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

# Ensure activity-registry is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api import (
    app,
    calculate_hash,
    parse_version,
    increment_version,
    ActivityStatus,
    VersionType,
    Environment,
    ApprovalType,
    ApprovalStatus,
)
from fastapi.testclient import TestClient


# =============================================================================
# Helper Functions
# =============================================================================

class TestHelpers:
    def test_calculate_hash(self):
        h = calculate_hash("hello")
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256

    def test_calculate_hash_deterministic(self):
        h1 = calculate_hash("test")
        h2 = calculate_hash("test")
        assert h1 == h2

    def test_parse_version_valid(self):
        assert parse_version("1.2.3") == (1, 2, 3)
        assert parse_version("0.0.1") == (0, 0, 1)

    def test_parse_version_invalid(self):
        with pytest.raises(ValueError):
            parse_version("1.2")
        with pytest.raises(ValueError):
            parse_version("abc")

    def test_increment_version_major(self):
        assert increment_version("1.2.3", VersionType.MAJOR) == "2.0.0"

    def test_increment_version_minor(self):
        assert increment_version("1.2.3", VersionType.MINOR) == "1.3.0"

    def test_increment_version_patch(self):
        assert increment_version("1.2.3", VersionType.PATCH) == "1.2.4"

    def test_increment_from_zero(self):
        assert increment_version("0.0.0", VersionType.PATCH) == "0.0.1"


# =============================================================================
# Enum Tests
# =============================================================================

class TestEnums:
    def test_activity_status_values(self):
        assert ActivityStatus.DRAFT == "DRAFT"
        assert ActivityStatus.DEPLOYED == "DEPLOYED"
        assert ActivityStatus.SUSPENDED == "SUSPENDED"

    def test_environment_values(self):
        assert Environment.DEV == "DEV"
        assert Environment.PROD == "PROD"

    def test_approval_type_values(self):
        assert ApprovalType.COMPLIANCE == "COMPLIANCE"
        assert ApprovalType.SECURITY == "SECURITY"

    def test_version_type_values(self):
        assert VersionType.MAJOR == "MAJOR"
        assert VersionType.MINOR == "MINOR"
        assert VersionType.PATCH == "PATCH"


# =============================================================================
# FastAPI Endpoints (mocked DB)
# =============================================================================

@pytest.fixture
def mock_db():
    """Mock psycopg2 connection for dependency override."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    return mock_conn, mock_cursor


@pytest.fixture
def client(mock_db):
    """FastAPI TestClient with mocked DB."""
    mock_conn, _ = mock_db

    def override_get_db():
        try:
            yield mock_conn
        finally:
            pass

    from api import get_db
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestHealthEndpoint:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200


class TestCreateActivity:
    def test_missing_tenant_header(self, client):
        resp = client.post("/api/v1/activities", json={
            "name": "Test",
            "version": "1.0.0",
            "ebcl_source": "activity test",
            "owner": "System",
            "authority": "Policy v1",
            "created_by": "admin",
        })
        assert resp.status_code == 401

    def test_create_success(self, client, mock_db):
        _, mock_cursor = mock_db
        now = datetime.now(timezone.utc)
        mock_cursor.fetchone.return_value = {
            "activity_id": "act-1",
            "name": "Test",
            "version": "1.0.0",
            "status": "DRAFT",
            "ebcl_source": "activity test",
            "owner": "System",
            "authority": "Policy v1",
            "created_by": "admin",
            "created_at": now,
            "approved_by": None,
            "approved_at": None,
            "deployed_by": None,
            "deployed_at": None,
            "hash": "abc123",
            "description": None,
            "tags": None,
            "category": None,
            "tenant_id": "t-1",
        }
        resp = client.post(
            "/api/v1/activities",
            json={
                "name": "Test",
                "version": "1.0.0",
                "ebcl_source": "activity test",
                "owner": "System",
                "authority": "Policy v1",
                "created_by": "admin",
            },
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 200
        assert resp.json()["activity_id"] == "act-1"


class TestGetActivity:
    def test_missing_tenant(self, client):
        resp = client.get("/api/v1/activities/act-1")
        assert resp.status_code == 401

    def test_not_found(self, client, mock_db):
        _, mock_cursor = mock_db
        mock_cursor.fetchone.return_value = None
        resp = client.get(
            "/api/v1/activities/act-1",
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 404


class TestListActivities:
    def test_missing_tenant(self, client):
        resp = client.get("/api/v1/activities")
        assert resp.status_code == 401

    def test_list_empty(self, client, mock_db):
        _, mock_cursor = mock_db
        mock_cursor.fetchall.return_value = []
        resp = client.get(
            "/api/v1/activities",
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 200
        assert resp.json() == []


class TestUpdateActivity:
    def test_no_fields(self, client, mock_db):
        resp = client.patch(
            "/api/v1/activities/act-1",
            json={},
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 400

    def test_missing_tenant(self, client):
        resp = client.patch(
            "/api/v1/activities/act-1",
            json={"description": "new"},
        )
        assert resp.status_code == 401

    def test_update_success(self, client, mock_db):
        _, mock_cursor = mock_db
        now = datetime.now(timezone.utc)
        mock_cursor.fetchone.return_value = {
            "activity_id": "act-1",
            "name": "Test",
            "version": "1.0.0",
            "status": "DRAFT",
            "ebcl_source": "source",
            "owner": "System",
            "authority": "Policy v1",
            "created_by": "admin",
            "created_at": now,
            "approved_by": None,
            "approved_at": None,
            "deployed_by": None,
            "deployed_at": None,
            "hash": "abc",
            "description": "updated desc",
            "tags": ["tag1"],
            "category": "cat",
            "tenant_id": "t-1",
        }
        resp = client.patch(
            "/api/v1/activities/act-1",
            json={"description": "updated desc"},
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 200

    def test_update_not_found(self, client, mock_db):
        _, mock_cursor = mock_db
        mock_cursor.fetchone.return_value = None
        resp = client.patch(
            "/api/v1/activities/act-1",
            json={"description": "x"},
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 404


# =============================================================================
# Approval Workflow
# =============================================================================

class TestRequestApproval:
    def test_missing_tenant(self, client):
        resp = client.post(
            "/api/v1/activities/act-1/request-approval",
            json={"approver_id": "u1", "approver_role": "admin", "approval_type": "COMPLIANCE"},
        )
        assert resp.status_code == 401

    def test_not_found(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchone.return_value = None
        resp = client.post(
            "/api/v1/activities/act-1/request-approval",
            json={"approver_id": "u1", "approver_role": "admin", "approval_type": "COMPLIANCE"},
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 404

    def test_wrong_status(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchone.return_value = {"status": "DEPLOYED"}
        resp = client.post(
            "/api/v1/activities/act-1/request-approval",
            json={"approver_id": "u1", "approver_role": "admin", "approval_type": "COMPLIANCE"},
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 400

    def test_success(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchone.side_effect = [
            {"status": "DRAFT"},  # status check
            {"approval_id": "appr-1"},  # insert result
        ]
        resp = client.post(
            "/api/v1/activities/act-1/request-approval",
            json={"approver_id": "u1", "approver_role": "admin", "approval_type": "COMPLIANCE"},
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "PENDING"


class TestApproveActivity:
    def test_missing_tenant(self, client):
        resp = client.post(
            "/api/v1/activities/act-1/approve?approval_id=appr-1",
            json={"approval_status": "APPROVED"},
        )
        assert resp.status_code == 401

    def test_activity_not_found(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchone.return_value = None
        resp = client.post(
            "/api/v1/activities/act-1/approve?approval_id=appr-1",
            json={"approval_status": "APPROVED"},
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 404

    def test_approval_not_found(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchone.side_effect = [
            {"activity_id": "act-1"},  # tenant check
            None,  # approval not found
        ]
        resp = client.post(
            "/api/v1/activities/act-1/approve?approval_id=appr-1",
            json={"approval_status": "APPROVED"},
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 404

    def test_approve_success(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchone.side_effect = [
            {"activity_id": "act-1"},  # tenant check
            {"approval_id": "appr-1", "approver_id": "u1"},  # approval
            {"pending": 0},  # no pending
        ]
        resp = client.post(
            "/api/v1/activities/act-1/approve?approval_id=appr-1",
            json={"approval_status": "APPROVED"},
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    def test_reject_activity(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchone.side_effect = [
            {"activity_id": "act-1"},  # tenant check
            {"approval_id": "appr-1", "approver_id": "u1"},  # approval
            {"pending": 0},  # count
        ]
        resp = client.post(
            "/api/v1/activities/act-1/approve?approval_id=appr-1",
            json={"approval_status": "REJECTED"},
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 200


# =============================================================================
# Deployment
# =============================================================================

class TestListDeployments:
    def test_missing_tenant(self, client):
        resp = client.get("/api/v1/activities/act-1/deployments")
        assert resp.status_code == 401

    def test_activity_not_found(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchone.return_value = None
        resp = client.get(
            "/api/v1/activities/act-1/deployments",
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 404

    def test_list_deployments_empty(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchone.return_value = {"activity_id": "act-1"}
        cursor.fetchall.return_value = []
        resp = client.get(
            "/api/v1/activities/act-1/deployments",
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 200
        assert resp.json() == []


# =============================================================================
# Suspend
# =============================================================================

class TestSuspendActivity:
    def test_missing_tenant(self, client):
        resp = client.post(
            "/api/v1/activities/act-1/suspend?reason=test&suspended_by=admin",
        )
        assert resp.status_code == 401

    def test_not_found(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchone.return_value = None
        resp = client.post(
            "/api/v1/activities/act-1/suspend?reason=test&suspended_by=admin",
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 404

    def test_suspend_success(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchone.return_value = {"activity_id": "act-1"}
        resp = client.post(
            "/api/v1/activities/act-1/suspend?reason=emergency&suspended_by=admin",
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "suspended"


# =============================================================================
# Version Management
# =============================================================================

class TestCreateNewVersion:
    def test_not_found(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchone.return_value = None
        resp = client.post(
            "/api/v1/activities/act-1/new-version?version_type=MINOR&change_summary=test&created_by=admin",
        )
        assert resp.status_code == 404

    def test_success(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchone.side_effect = [
            {
                "activity_id": "act-1",
                "name": "Test",
                "version": "1.0.0",
                "ebcl_source": "src",
                "owner": "System",
                "authority": "Policy v1",
                "description": None,
                "tags": None,
                "category": None,
                "tenant_id": "t-1",
            },
            {"activity_id": "act-2"},  # new activity
        ]
        resp = client.post(
            "/api/v1/activities/act-1/new-version?version_type=MINOR&change_summary=test&created_by=admin",
        )
        assert resp.status_code == 200
        assert resp.json()["new_version"] == "1.1.0"


class TestVersionHistory:
    def test_missing_tenant(self, client):
        resp = client.get("/api/v1/activities/act-1/versions")
        assert resp.status_code == 401

    def test_not_found(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchone.return_value = None
        resp = client.get(
            "/api/v1/activities/act-1/versions",
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 404


# =============================================================================
# Analytics
# =============================================================================

class TestExecutions:
    def test_missing_tenant(self, client):
        resp = client.get("/api/v1/activities/act-1/executions")
        assert resp.status_code == 401

    def test_not_found(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchone.return_value = None
        resp = client.get(
            "/api/v1/activities/act-1/executions",
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 404

    def test_success(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchone.return_value = {"activity_id": "act-1"}
        cursor.fetchall.return_value = []
        resp = client.get(
            "/api/v1/activities/act-1/executions",
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 200


class TestActivityStats:
    def test_missing_tenant(self, client):
        resp = client.get("/api/v1/activities/act-1/stats")
        assert resp.status_code == 401

    def test_not_found(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchone.return_value = None
        resp = client.get(
            "/api/v1/activities/act-1/stats",
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 404

    def test_no_stats(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchone.side_effect = [
            {"activity_id": "act-1"},  # activity exists
            None,  # no stats
        ]
        resp = client.get(
            "/api/v1/activities/act-1/stats",
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 200
        assert resp.json()["total_executions"] == 0

    def test_with_stats(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchone.side_effect = [
            {"activity_id": "act-1"},  # activity exists
            {
                "activity_id": "act-1",
                "total_executions": 50,
                "successful_executions": 45,
                "failed_executions": 5,
                "avg_duration_ms": 120,
                "last_execution_at": "2026-03-01T10:00:00",
            },
        ]
        resp = client.get(
            "/api/v1/activities/act-1/stats",
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 200
        assert resp.json()["total_executions"] == 50


class TestPendingApprovals:
    def test_missing_tenant(self, client):
        resp = client.get("/api/v1/approvals/pending")
        assert resp.status_code == 401

    def test_empty(self, client, mock_db):
        _, cursor = mock_db
        cursor.fetchall.return_value = []
        resp = client.get(
            "/api/v1/approvals/pending",
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 200
        assert resp.json() == []


# =============================================================================
# Create Activity — error paths
# =============================================================================

class TestCreateActivityErrors:
    def test_invalid_version(self, client, mock_db):
        resp = client.post(
            "/api/v1/activities",
            json={
                "name": "Test",
                "version": "bad",
                "ebcl_source": "source",
                "owner": "System",
                "authority": "Policy v1",
                "created_by": "admin",
            },
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 500

    def test_integrity_error(self, client, mock_db):
        import psycopg2
        _, cursor = mock_db
        cursor.execute.side_effect = psycopg2.IntegrityError("unique constraint violated")
        resp = client.post(
            "/api/v1/activities",
            json={
                "name": "Test",
                "version": "1.0.0",
                "ebcl_source": "source",
                "owner": "System",
                "authority": "Policy v1",
                "created_by": "admin",
            },
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 400


# =============================================================================
# Get Activity — found
# =============================================================================

class TestGetActivityFound:
    def test_found(self, client, mock_db):
        _, cursor = mock_db
        now = datetime.now(timezone.utc)
        cursor.fetchone.return_value = {
            "activity_id": "act-1",
            "name": "MyActivity",
            "version": "1.0.0",
            "status": "DRAFT",
            "ebcl_source": "source",
            "owner": "System",
            "authority": "Policy v1",
            "created_by": "admin",
            "created_at": now,
            "approved_by": None,
            "approved_at": None,
            "deployed_by": None,
            "deployed_at": None,
            "hash": "abc",
            "description": None,
            "tags": None,
            "category": None,
            "tenant_id": "t-1",
        }
        resp = client.get(
            "/api/v1/activities/act-1",
            headers={"X-Tenant-ID": "t-1"},
        )
        assert resp.status_code == 200
        assert resp.json()["activity_id"] == "act-1"
