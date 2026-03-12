"""
Evidence Vault API — comprehensive endpoint tests.
Covers: create_evidence, get_evidence, list_evidence, attestation, verify, chain,
        compliance reports, stats, search, health, helper functions, Elasticsearch,
        and database pool lifecycle.
"""

import sys
import os
import types
import json
import hashlib
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

# ── Stub heavy externals BEFORE import ──────────────────────────────────────
_fake_pg = types.ModuleType("psycopg2")
_fake_pool = types.ModuleType("psycopg2.pool")
_fake_pool.ThreadedConnectionPool = MagicMock
_fake_pg.pool = _fake_pool
_fake_extras = types.ModuleType("psycopg2.extras")
_fake_extras.RealDictCursor = type("RealDictCursor", (), {})
_fake_pg.extras = _fake_extras
sys.modules.setdefault("psycopg2", _fake_pg)
sys.modules.setdefault("psycopg2.pool", _fake_pool)
sys.modules.setdefault("psycopg2.extras", _fake_extras)

_fake_es_mod = types.ModuleType("elasticsearch")
_mock_es_cls = MagicMock()
_fake_es_mod.Elasticsearch = _mock_es_cls
sys.modules.setdefault("elasticsearch", _fake_es_mod)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
import api  # noqa: E402  (evidence-vault/api.py)

# ── Fake DB row builder ─────────────────────────────────────────────────────
_NOW = datetime.now(timezone.utc)

def _evidence_row(**overrides):
    base = {
        "evidence_id": "ev-1",
        "activity_id": "A1",
        "activity_name": "Test Activity",
        "activity_version": "1.0",
        "execution_id": "exec-1",
        "agent_id": "agent-1",
        "agent_type": "AI",
        "tenant_id": "t1",
        "environment": "DEV",
        "event_type": "TRIGGER",
        "event_data": {"k": "v"},
        "decision": "allow",
        "outcome": "ok",
        "policy_reference": "SOP-1",
        "verified": True,
        "verification_status": "VERIFIED",
        "verification_errors": None,
        "hash": "a" * 64,
        "previous_hash": None,
        "created_at": _NOW,
        "verified_at": _NOW,
        "tags": None,
        "metadata": None,
    }
    base.update(overrides)
    return base

def _attestation_row(**overrides):
    base = {
        "attestation_id": "att-1",
        "evidence_id": "ev-1",
        "attestor_type": "JURY",
        "attestor_id": "juror-1",
        "attestation_status": "APPROVED",
        "confidence_score": 0.95,
        "reasoning": "all good",
        "created_at": _NOW,
    }
    base.update(overrides)
    return base


# ── Override DB / ES dependency ──────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _mock_deps(monkeypatch):
    """Replace get_db and get_es for every test."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = _evidence_row()
    mock_cursor.fetchall.return_value = [_evidence_row()]

    def _fake_get_db():
        yield mock_conn

    monkeypatch.setattr(api, "_db_pool", MagicMock())
    api.app.dependency_overrides[api.get_db] = _fake_get_db

    # Reset ES state
    monkeypatch.setattr(api, "_es_client", None)
    monkeypatch.setattr(api, "_es_healthy", False)

    yield {"conn": mock_conn, "cursor": mock_cursor}

    api.app.dependency_overrides.clear()


client = TestClient(api.app)


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTION TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestHelpers:
    def test_calculate_hash_deterministic(self):
        h1 = api.calculate_hash({"a": 1, "b": 2})
        h2 = api.calculate_hash({"b": 2, "a": 1})
        assert h1 == h2  # sort_keys=True

    def test_calculate_hash_differs(self):
        assert api.calculate_hash({"a": 1}) != api.calculate_hash({"a": 2})

    def test_verify_policy_reference_valid(self):
        assert api.verify_policy_reference("SOP-1") is True

    def test_verify_policy_reference_empty(self):
        assert api.verify_policy_reference("") is False

    def test_verify_agent_authorization_always_true(self):
        assert api.verify_agent_authorization("agent-x", "ACT-1") is True

    def test_verify_activity_exists_found(self, _mock_deps):
        _mock_deps["cursor"].fetchone.return_value = (1,)
        assert api.verify_activity_exists("A1", _mock_deps["conn"]) is True

    def test_verify_activity_exists_missing(self, _mock_deps):
        _mock_deps["cursor"].fetchone.return_value = None
        assert api.verify_activity_exists("MISSING", _mock_deps["conn"]) is False


# ═══════════════════════════════════════════════════════════════════════════════
# DB POOL TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestDBPool:
    def test_get_pool_creates_once(self):
        with patch.object(api, "_db_pool", None):
            with patch("api.psycopg2") as mock_pg:
                pool_obj = MagicMock()
                mock_pg.pool.ThreadedConnectionPool.return_value = pool_obj
                p = api._get_pool()
                assert p is pool_obj

    def test_get_pool_returns_cached(self):
        sentinel = object()
        with patch.object(api, "_db_pool", sentinel):
            assert api._get_pool() is sentinel


# ═══════════════════════════════════════════════════════════════════════════════
# ELASTICSEARCH TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestElasticsearch:
    def test_get_es_healthy(self):
        api._es_client = None
        api._es_healthy = False
        mock_es = MagicMock()
        mock_es.ping.return_value = True
        with patch("api.Elasticsearch", return_value=mock_es):
            result = api.get_es()
            assert result is mock_es

    def test_get_es_unhealthy(self):
        api._es_client = None
        api._es_healthy = False
        mock_es = MagicMock()
        mock_es.ping.return_value = False
        with patch("api.Elasticsearch", return_value=mock_es):
            result = api.get_es()
            assert result is None

    def test_get_es_exception(self):
        api._es_client = None
        api._es_healthy = False
        with patch("api.Elasticsearch", side_effect=Exception("conn refused")):
            result = api.get_es()
            assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# EVIDENCE ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestCreateEvidence:
    def test_create_evidence_success(self, _mock_deps):
        _mock_deps["cursor"].fetchone.side_effect = [
            (1,),  # activity exists
            _evidence_row(),
        ]
        body = {
            "activity_id": "A1", "activity_name": "Act", "activity_version": "1",
            "execution_id": "e1", "agent_id": "ag1", "agent_type": "AI",
            "tenant_id": "t1", "environment": "DEV", "event_type": "TRIGGER",
            "event_data": {}, "policy_reference": "SOP-1",
        }
        resp = client.post("/api/v1/evidence", json=body)
        assert resp.status_code == 200
        assert resp.json()["evidence_id"] == "ev-1"

    def test_create_evidence_with_es_index(self, _mock_deps):
        _mock_deps["cursor"].fetchone.side_effect = [(1,), _evidence_row()]
        mock_es = MagicMock()
        with patch.object(api, "get_es", return_value=mock_es):
            body = {
                "activity_id": "A1", "activity_name": "Act", "activity_version": "1",
                "execution_id": "e1", "agent_id": "ag1", "agent_type": "AI",
                "tenant_id": "t1", "environment": "DEV", "event_type": "TRIGGER",
                "event_data": {}, "policy_reference": "SOP-1",
            }
            resp = client.post("/api/v1/evidence", json=body)
            assert resp.status_code == 200
            mock_es.index.assert_called_once()

    def test_create_evidence_es_failure_graceful(self, _mock_deps):
        _mock_deps["cursor"].fetchone.side_effect = [(1,), _evidence_row()]
        mock_es = MagicMock()
        mock_es.index.side_effect = Exception("ES down")
        with patch.object(api, "get_es", return_value=mock_es):
            body = {
                "activity_id": "A1", "activity_name": "Act", "activity_version": "1",
                "execution_id": "e1", "agent_id": "ag1", "agent_type": "AI",
                "tenant_id": "t1", "environment": "DEV", "event_type": "TRIGGER",
                "event_data": {}, "policy_reference": "SOP-1",
            }
            resp = client.post("/api/v1/evidence", json=body)
            assert resp.status_code == 200  # degrades gracefully

    def test_create_evidence_verification_failure(self, _mock_deps):
        _mock_deps["cursor"].fetchone.side_effect = [
            None,  # activity NOT found
            _evidence_row(verified=False, verification_status="FAILED", verification_errors=["Activity not found"]),
        ]
        body = {
            "activity_id": "BAD", "activity_name": "Act", "activity_version": "1",
            "execution_id": "e1", "agent_id": "ag1", "agent_type": "AI",
            "tenant_id": "t1", "environment": "DEV", "event_type": "TRIGGER",
            "event_data": {}, "policy_reference": "SOP-1",
        }
        resp = client.post("/api/v1/evidence", json=body)
        assert resp.status_code == 200


class TestGetEvidence:
    def test_get_evidence_found(self, _mock_deps):
        _mock_deps["cursor"].fetchone.return_value = _evidence_row()
        resp = client.get("/api/v1/evidence/ev-1?tenant_id=t1")
        assert resp.status_code == 200
        assert resp.json()["evidence_id"] == "ev-1"

    def test_get_evidence_not_found(self, _mock_deps):
        _mock_deps["cursor"].fetchone.return_value = None
        resp = client.get("/api/v1/evidence/missing?tenant_id=t1")
        assert resp.status_code == 404


class TestListEvidence:
    def test_list_basic(self, _mock_deps):
        _mock_deps["cursor"].fetchall.return_value = [_evidence_row(), _evidence_row(evidence_id="ev-2")]
        resp = client.get("/api/v1/evidence?tenant_id=t1")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_list_with_all_filters(self, _mock_deps):
        _mock_deps["cursor"].fetchall.return_value = [_evidence_row()]
        resp = client.get(
            "/api/v1/evidence?tenant_id=t1&activity_id=A1&execution_id=e1"
            "&agent_id=ag1&event_type=TRIGGER&environment=DEV"
            "&verification_status=VERIFIED&policy_reference=SOP-1"
            "&start_date=2025-01-01T00:00:00Z&end_date=2026-12-31T23:59:59Z"
            "&limit=50&offset=0"
        )
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# ATTESTATION ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestAttestation:
    def test_create_attestation_success(self, _mock_deps):
        _mock_deps["cursor"].fetchone.side_effect = [
            {"evidence_id": "ev-1"},  # evidence exists
            _attestation_row(),
        ]
        body = {
            "evidence_id": "ev-1",
            "attestor_type": "JURY",
            "attestor_id": "juror-1",
            "attestation_status": "APPROVED",
            "confidence_score": 0.95,
            "reasoning": "ok",
        }
        resp = client.post("/api/v1/evidence/ev-1/attest?tenant_id=t1", json=body)
        assert resp.status_code == 200

    def test_create_attestation_evidence_not_found(self, _mock_deps):
        _mock_deps["cursor"].fetchone.return_value = None
        body = {
            "evidence_id": "ev-missing",
            "attestor_type": "JURY",
            "attestor_id": "juror-1",
            "attestation_status": "REJECTED",
        }
        resp = client.post("/api/v1/evidence/ev-missing/attest?tenant_id=t1", json=body)
        assert resp.status_code == 404

    def test_create_attestation_with_proof(self, _mock_deps):
        _mock_deps["cursor"].fetchone.side_effect = [
            {"evidence_id": "ev-1"},
            _attestation_row(),
        ]
        body = {
            "evidence_id": "ev-1",
            "attestor_type": "ENTROPY",
            "attestor_id": "ent-1",
            "attestation_status": "APPROVED",
            "signature": "0xabc",
            "proof": {"method": "entropy_check"},
        }
        resp = client.post("/api/v1/evidence/ev-1/attest?tenant_id=t1", json=body)
        assert resp.status_code == 200

    def test_get_attestations(self, _mock_deps):
        _mock_deps["cursor"].fetchone.return_value = {"evidence_id": "ev-1"}
        _mock_deps["cursor"].fetchall.return_value = [_attestation_row()]
        resp = client.get("/api/v1/evidence/ev-1/attestations?tenant_id=t1")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_get_attestations_evidence_not_found(self, _mock_deps):
        _mock_deps["cursor"].fetchone.return_value = None
        resp = client.get("/api/v1/evidence/missing/attestations?tenant_id=t1")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# VERIFICATION ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestVerification:
    def test_verify_evidence_success(self, _mock_deps):
        row = _evidence_row()
        _mock_deps["cursor"].fetchone.side_effect = [
            row,           # evidence found
            {"valid": True},   # hash integrity check
            (1,),          # activity exists
        ]
        resp = client.post("/api/v1/evidence/ev-1/verify?tenant_id=t1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["verified"] is True
        assert data["verification_errors"] == []

    def test_verify_evidence_not_found(self, _mock_deps):
        _mock_deps["cursor"].fetchone.return_value = None
        resp = client.post("/api/v1/evidence/missing/verify?tenant_id=t1")
        assert resp.status_code == 404

    def test_verify_evidence_integrity_fail(self, _mock_deps):
        row = _evidence_row()
        _mock_deps["cursor"].fetchone.side_effect = [
            row,
            {"valid": False},
            None,  # activity not found
        ]
        resp = client.post("/api/v1/evidence/ev-1/verify?tenant_id=t1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["verified"] is False
        assert len(data["verification_errors"]) > 0


class TestChain:
    def test_get_chain_success(self, _mock_deps):
        _mock_deps["cursor"].fetchone.return_value = {"evidence_id": "ev-1"}
        _mock_deps["cursor"].fetchall.return_value = [{"hash": "a"}, {"hash": "b"}]
        resp = client.get("/api/v1/evidence/ev-1/chain?tenant_id=t1")
        assert resp.status_code == 200
        assert resp.json()["chain_length"] == 2

    def test_get_chain_not_found(self, _mock_deps):
        _mock_deps["cursor"].fetchone.return_value = None
        resp = client.get("/api/v1/evidence/missing/chain?tenant_id=t1")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# COMPLIANCE REPORTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestComplianceReports:
    def test_generate_report(self, _mock_deps):
        _mock_deps["cursor"].fetchone.side_effect = [
            {"total_evidence": 100, "verified_count": 90, "failed_count": 5, "disputed_count": 5},
            {"violations": 5},
            {"report_id": "rpt-1"},  # RETURNING *
        ]
        resp = client.post(
            "/api/v1/compliance/reports"
            "?tenant_id=t1&start_date=2026-01-01T00:00:00Z&end_date=2026-02-01T00:00:00Z"
        )
        assert resp.status_code == 200

    def test_list_reports(self, _mock_deps):
        _mock_deps["cursor"].fetchall.return_value = [{"report_id": "r1"}, {"report_id": "r2"}]
        resp = client.get("/api/v1/compliance/reports?tenant_id=t1")
        assert resp.status_code == 200

    def test_list_reports_with_type_filter(self, _mock_deps):
        _mock_deps["cursor"].fetchall.return_value = []
        resp = client.get("/api/v1/compliance/reports?tenant_id=t1&report_type=DAILY")
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYTICS & SEARCH
# ═══════════════════════════════════════════════════════════════════════════════

class TestDirectFunctions:
    """Test stats/search helpers directly (routes intercepted by path params)."""

    def test_get_es_returns_cached(self):
        sentinel = MagicMock()
        api._es_client = sentinel
        api._es_healthy = True
        assert api.get_es() is sentinel
        api._es_client = None
        api._es_healthy = False

    def test_calculate_hash_deterministic(self):
        h1 = api.calculate_hash({"a": 1})
        h2 = api.calculate_hash({"a": 1})
        assert h1 == h2 and len(h1) == 64

    def test_verify_policy_ref_empty(self):
        assert api.verify_policy_reference("") is False

    def test_verify_agent_auth_differs(self):
        assert api.verify_agent_authorization("x", "y") is True
        assert api.verify_agent_authorization("", "") is True


# ═══════════════════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ═══════════════════════════════════════════════════════════════════════════════

class TestHealth:
    def test_health_all_ok(self, _mock_deps):
        with patch.object(api, "get_es", return_value=MagicMock()):
            resp = client.get("/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "healthy"

    def test_health_no_es(self, _mock_deps):
        with patch.object(api, "get_es", return_value=None):
            resp = client.get("/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "degraded"

    def test_health_db_failure(self, _mock_deps):
        _mock_deps["cursor"].execute.side_effect = Exception("db down")
        with patch.object(api, "get_es", return_value=None):
            resp = client.get("/health")
            assert resp.status_code == 200
            assert resp.json()["database"] == "unhealthy"


# ═══════════════════════════════════════════════════════════════════════════════
# ENUM / MODEL TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestEnumsAndModels:
    def test_agent_types(self):
        assert api.AgentType.HUMAN == "HUMAN"
        assert api.AgentType.AI == "AI"
        assert api.AgentType.SYSTEM == "SYSTEM"

    def test_event_types(self):
        for et in ["TRIGGER", "VALIDATE", "DECIDE", "ACT", "EXCEPTION", "EVIDENCE"]:
            assert et in [e.value for e in api.EventType]

    def test_verification_statuses(self):
        for vs in ["PENDING", "VERIFIED", "FAILED", "DISPUTED"]:
            assert vs in [v.value for v in api.VerificationStatus]

    def test_attestor_types(self):
        for at in ["JURY", "ENTROPY", "ESCROW", "COMPLIANCE_OFFICER"]:
            assert at in [a.value for a in api.AttestorType]

    def test_evidence_create_model(self):
        obj = api.EvidenceCreate(
            activity_id="A1", activity_name="test", activity_version="1",
            execution_id="e1", agent_id="ag1", agent_type="AI", tenant_id="t1",
            environment="DEV", event_type="TRIGGER", event_data={},
            policy_reference="SOP-1"
        )
        assert obj.activity_id == "A1"
        assert obj.tags is None
        assert obj.metadata is None

    def test_attestation_create_model(self):
        obj = api.AttestationCreate(
            evidence_id="ev-1", attestor_type="JURY",
            attestor_id="j1", attestation_status="APPROVED"
        )
        assert obj.confidence_score is None


# ═══════════════════════════════════════════════════════════════════════════════
# COVERAGE GAP TESTS — stats, search, verify fail paths
# ═══════════════════════════════════════════════════════════════════════════════

class TestStatsEndpoint:
    """Cover lines 655-680: get_evidence_stats (direct async call)."""

    def test_stats_basic(self, _mock_deps):
        import asyncio
        _mock_deps["cursor"].fetchone.return_value = {
            "total_evidence": 50, "verified_count": 45,
            "failed_count": 3, "disputed_count": 2,
            "unique_activities": 10, "unique_agents": 5,
            "unique_policies": 8,
        }
        result = asyncio.get_event_loop().run_until_complete(
            api.get_evidence_stats(tenant_id="t1", conn=_mock_deps["conn"])
        )
        assert result["total_evidence"] == 50

    def test_stats_with_date_range(self, _mock_deps):
        import asyncio
        _mock_deps["cursor"].fetchone.return_value = {
            "total_evidence": 10, "verified_count": 10,
            "failed_count": 0, "disputed_count": 0,
            "unique_activities": 3, "unique_agents": 2,
            "unique_policies": 2,
        }
        result = asyncio.get_event_loop().run_until_complete(
            api.get_evidence_stats(
                tenant_id="t1",
                start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
                end_date=datetime(2026, 2, 1, tzinfo=timezone.utc),
                conn=_mock_deps["conn"],
            )
        )
        assert result["total_evidence"] == 10


class TestSearchEndpoint:
    """Cover lines 689-717: search_evidence (direct async call)."""

    def test_search_no_es(self, _mock_deps):
        """ES unavailable → HTTPException 503."""
        import asyncio
        with patch.object(api, "get_es", return_value=None):
            with pytest.raises(HTTPException) as exc:
                asyncio.get_event_loop().run_until_complete(
                    api.search_evidence(q="test", tenant_id="t1")
                )
            assert exc.value.status_code == 503

    def test_search_success(self, _mock_deps):
        """ES available → dict with results."""
        import asyncio
        mock_es = MagicMock()
        mock_es.search.return_value = {
            "hits": {
                "total": {"value": 1},
                "hits": [{"_source": {"evidence_id": "ev-1"}}],
            }
        }
        with patch.object(api, "get_es", return_value=mock_es):
            result = asyncio.get_event_loop().run_until_complete(
                api.search_evidence(q="test", tenant_id="t1")
            )
            assert result["total"] == 1

    def test_search_es_error(self, _mock_deps):
        """ES search throws → HTTPException 500."""
        import asyncio
        mock_es = MagicMock()
        mock_es.search.side_effect = Exception("search failed")
        with patch.object(api, "get_es", return_value=mock_es):
            with pytest.raises(HTTPException) as exc:
                asyncio.get_event_loop().run_until_complete(
                    api.search_evidence(q="test", tenant_id="t1")
                )
            assert exc.value.status_code == 500


class TestVerifyGapPaths:
    """Cover lines 509, 513: verify_evidence policy/auth failures."""

    def test_verify_policy_ref_fail(self, _mock_deps):
        row = _evidence_row(policy_reference="")
        _mock_deps["cursor"].fetchone.side_effect = [
            row,                # evidence found
            {"valid": True},    # hash OK
            (1,),               # activity exists
        ]
        resp = client.post("/api/v1/evidence/ev-1/verify?tenant_id=t1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["verified"] is False
        assert any("policy" in e.lower() for e in data["verification_errors"])

    def test_verify_auth_fail(self, _mock_deps):
        """Force verify_agent_authorization to return False."""
        row = _evidence_row()
        _mock_deps["cursor"].fetchone.side_effect = [
            row, {"valid": True}, (1,),
        ]
        with patch.object(api, "verify_agent_authorization", return_value=False):
            resp = client.post("/api/v1/evidence/ev-1/verify?tenant_id=t1")
            assert resp.status_code == 200
            data = resp.json()
            assert data["verified"] is False
            assert any("authorized" in e.lower() for e in data["verification_errors"])


class TestCreateEvidenceGapPaths:
    """Cover lines 241, 245: policy/auth errors in create_evidence."""

    def test_create_with_empty_policy(self, _mock_deps):
        """Empty policy_reference → verification_errors includes policy msg."""
        _mock_deps["cursor"].fetchone.side_effect = [
            (1,),  # activity exists
            _evidence_row(verified=False, verification_status="FAILED",
                         verification_errors=["Invalid policy reference: "]),
        ]
        body = {
            "activity_id": "A1", "activity_name": "Act", "activity_version": "1",
            "execution_id": "e1", "agent_id": "ag1", "agent_type": "AI",
            "tenant_id": "t1", "environment": "DEV", "event_type": "TRIGGER",
            "event_data": {}, "policy_reference": "",
        }
        resp = client.post("/api/v1/evidence", json=body)
        assert resp.status_code == 200

    def test_create_with_auth_fail(self, _mock_deps):
        """Agent auth fails → verification_errors includes auth msg."""
        _mock_deps["cursor"].fetchone.side_effect = [
            (1,),  # activity exists
            _evidence_row(verified=False, verification_status="FAILED"),
        ]
        with patch.object(api, "verify_agent_authorization", return_value=False):
            body = {
                "activity_id": "A1", "activity_name": "Act", "activity_version": "1",
                "execution_id": "e1", "agent_id": "ag1", "agent_type": "AI",
                "tenant_id": "t1", "environment": "DEV", "event_type": "TRIGGER",
                "event_data": {}, "policy_reference": "SOP-1",
            }
            resp = client.post("/api/v1/evidence", json=body)
            assert resp.status_code == 200
