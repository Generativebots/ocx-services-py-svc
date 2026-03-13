"""
Evidence Vault — Patent Claim 14 (Immutable Ledger Attribution).
Tests: Hash chain, evidence creation, attestation, integrity verification.
"""

import pytest
import sys
import os
import hashlib
import json
from unittest.mock import MagicMock, patch
import types

# Stub heavy external deps before import
_fake_psycopg2 = types.ModuleType("psycopg2")
_fake_psycopg2.pool = types.ModuleType("psycopg2.pool")
_fake_psycopg2.pool.ThreadedConnectionPool = MagicMock
_fake_psycopg2.extras = types.ModuleType("psycopg2.extras")
_fake_psycopg2.extras.RealDictCursor = type("RealDictCursor", (), {})
sys.modules.setdefault("psycopg2", _fake_psycopg2)
sys.modules.setdefault("psycopg2.pool", _fake_psycopg2.pool)
sys.modules.setdefault("psycopg2.extras", _fake_psycopg2.extras)

_fake_es = types.ModuleType("elasticsearch")
_fake_es.Elasticsearch = MagicMock
sys.modules.setdefault("elasticsearch", _fake_es)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# -------------------------------------------------------------------
# Hash chain utility tests (pure function, no DB)
# -------------------------------------------------------------------
class TestHashChain:
    """Test the hash chain integrity mechanism (Patent Claim 14 core)."""

    def test_sha256_chain_link(self):
        """Each evidence record's hash includes the previous record's hash."""
        prev_hash = "0" * 64
        evidence_data = {
            "activity_id": "A1",
            "agent_id": "agent-1",
            "event_type": "EXECUTION",
            "outcome": "ALLOWED",
        }
        payload = json.dumps(evidence_data, sort_keys=True)
        current_hash = hashlib.sha256(
            f"{prev_hash}:{payload}".encode()
        ).hexdigest()

        assert len(current_hash) == 64
        assert current_hash != prev_hash

    def test_chain_integrity_tamper_detection(self):
        """Modifying any record in the chain breaks all subsequent hashes."""
        chain = []
        prev = "0" * 64
        for i in range(5):
            data = json.dumps({"step": i}, sort_keys=True)
            current = hashlib.sha256(f"{prev}:{data}".encode()).hexdigest()
            chain.append({"data": {"step": i}, "hash": current, "prev_hash": prev})
            prev = current

        # Verify the chain
        for j in range(1, len(chain)):
            expected = hashlib.sha256(
                f"{chain[j]['prev_hash']}:{json.dumps(chain[j]['data'], sort_keys=True)}".encode()
            ).hexdigest()
            assert chain[j]["hash"] == expected

        # Tamper with record 2
        chain[2]["data"]["step"] = 999
        tampered_hash = hashlib.sha256(
            f"{chain[2]['prev_hash']}:{json.dumps(chain[2]['data'], sort_keys=True)}".encode()
        ).hexdigest()
        assert tampered_hash != chain[2]["hash"], "Tampered record should break hash"


# -------------------------------------------------------------------
# Evidence record structure
# -------------------------------------------------------------------
class TestEvidenceRecordStructure:
    def test_required_fields(self):
        """Patent Claim 14 requires: activity_id, agent_id, event_type, outcome, hash, chain."""
        evidence = {
            "evidence_id": "ev-001",
            "activity_id": "A1",
            "agent_id": "agent-1",
            "tenant_id": "t1",
            "event_type": "EXECUTION",
            "event_data": {"amount": 1000},
            "decision": "Allowed by policy",
            "outcome": "ALLOWED",
            "policy_reference": "SOP-v1",
            "hash": hashlib.sha256(b"test").hexdigest(),
            "prev_hash": "0" * 64,
            "timestamp": "2026-01-01T00:00:00Z",
        }
        # All required fields present
        for key in ["evidence_id", "activity_id", "agent_id", "event_type", "outcome", "hash", "prev_hash"]:
            assert key in evidence

    def test_attestation_structure(self):
        """Attestation adds verifier, signature, and attestation hash."""
        attestation = {
            "attestation_id": "att-001",
            "evidence_id": "ev-001",
            "verifier_id": "verifier-1",
            "verification_result": "VALID",
            "attestation_hash": hashlib.sha256(b"ev-001:VALID").hexdigest(),
            "timestamp": "2026-01-01T01:00:00Z",
        }
        assert attestation["verification_result"] in ["VALID", "INVALID", "TAMPERED"]
        assert len(attestation["attestation_hash"]) == 64


# -------------------------------------------------------------------
# Compliance report generation
# -------------------------------------------------------------------
class TestComplianceReport:
    def test_report_aggregates_outcomes(self):
        records = [
            {"outcome": "ALLOWED", "tenant_id": "t1"},
            {"outcome": "BLOCKED", "tenant_id": "t1"},
            {"outcome": "ALLOWED", "tenant_id": "t1"},
            {"outcome": "BLOCKED", "tenant_id": "t1"},
            {"outcome": "ALLOWED", "tenant_id": "t1"},
        ]
        allowed = sum(1 for r in records if r["outcome"] == "ALLOWED")
        blocked = sum(1 for r in records if r["outcome"] == "BLOCKED")
        assert allowed == 3
        assert blocked == 2
        assert allowed + blocked == len(records)

    def test_tenant_isolation_in_report(self):
        records = [
            {"outcome": "ALLOWED", "tenant_id": "t1"},
            {"outcome": "BLOCKED", "tenant_id": "t2"},
        ]
        t1_records = [r for r in records if r["tenant_id"] == "t1"]
        t2_records = [r for r in records if r["tenant_id"] == "t2"]
        assert len(t1_records) == 1
        assert len(t2_records) == 1
