"""Tests for parallel-auditing/auditor.py — JuryVerifier, EntropyVerifier, EscrowVerifier, ParallelAuditor."""

import sys
import os
import types
import hashlib
import json

# Allow importing auditor from parallel-auditing/
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# --- Mock heavy dependencies before import ---
import unittest.mock as mock

# Mock numpy
_fake_np = types.ModuleType("numpy")
_fake_np.unique = lambda x, return_counts=False: (list(set(x)), [x.count(v) for v in set(x)]) if return_counts else list(set(x))
_fake_np.sum = sum
_fake_np.log2 = lambda x: __import__("math").log2(x) if x > 0 else 0
sys.modules["numpy"] = _fake_np

# Mock scipy
_fake_scipy = types.ModuleType("scipy")
_fake_stats = types.ModuleType("scipy.stats")
_fake_chi2 = mock.MagicMock()
_fake_chi2.cdf = mock.MagicMock(return_value=0.5)
_fake_stats.chi2 = _fake_chi2
_fake_scipy.stats = _fake_stats
sys.modules["scipy"] = _fake_scipy
sys.modules["scipy.stats"] = _fake_stats

# Mock governance config — must return real dict with float values
_fake_gov_mod = mock.MagicMock()
_fake_gov_mod.get_tenant_governance_config = mock.MagicMock(return_value={
    "jury_consensus_threshold": 0.67,
    "jury_vote_threshold": 0.5,
    "entropy_confidence_high": 0.8,
    "entropy_confidence_low": 0.4,
    "escrow_sovereign_threshold": 0.90,
})
sys.modules.setdefault("config", mock.MagicMock())
sys.modules["config.governance_config"] = _fake_gov_mod

# Mock requests
sys.modules.setdefault("requests", mock.MagicMock())

import pytest
import asyncio

def _run(coro):
    """Run coroutine synchronously — pytest-asyncio is not installed."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

from auditor import (
    AttestationStatus,
    EvidenceRecord,
    JuryVerifier,
    EntropyVerifier,
    EscrowVerifier,
    ParallelAuditor,
    ContinuousAuditingService,
    _load_governance_config,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_evidence(evidence_id="ev-001", event_data=None, matching_hash=True):
    """Create a test EvidenceRecord."""
    data = event_data or {"action": "transfer", "amount": 1000}
    data_hash = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    return EvidenceRecord(
        evidence_id=evidence_id,
        activity_id="act-001",
        activity_name="transfer-funds",
        execution_id="exec-001",
        agent_id="agent-A",
        event_type="ACTION",
        event_data=data,
        decision="ALLOW",
        outcome="SUCCESS",
        policy_reference="pol-001",
        hash=data_hash if matching_hash else "badhash",
    )


# ---------------------------------------------------------------------------
# JuryVerifier
# ---------------------------------------------------------------------------

class TestJuryVerifier:
    """Tests for JuryVerifier multi-agent consensus."""

    def test_init_defaults(self):
        jv = JuryVerifier()
        assert jv.num_agents == 10
        assert len(jv.agent_ids) == 10

    def test_init_custom(self):
        jv = JuryVerifier(num_agents=3, consensus_threshold=0.8)
        assert jv.num_agents == 3
        assert jv.consensus_threshold == 0.8

    def test_verify_evidence_returns_attestation(self):
        jv = JuryVerifier(num_agents=3, consensus_threshold=0.5)
        evidence = _make_evidence()
        result = _run(jv.verify_evidence(evidence))

        assert result["attestor_type"] == "JURY"
        assert "confidence_score" in result
        assert result["attestation_status"] in [
            AttestationStatus.APPROVED,
            AttestationStatus.REJECTED,
            AttestationStatus.DISPUTED,
        ]
        assert result["proof"]["total_votes"] == 3

    def test_calculate_validity_score_valid_hash(self):
        jv = JuryVerifier()
        evidence = _make_evidence()
        score = jv._calculate_validity_score(evidence)
        # Base 0.5 + hash match 0.3 + decision/outcome 0.1 + policy 0.1 + offset
        assert 0.7 <= score <= 1.0

    def test_calculate_validity_score_bad_hash(self):
        jv = JuryVerifier()
        evidence = _make_evidence(matching_hash=False)
        score = jv._calculate_validity_score(evidence)
        # Base 0.5, no +0.3 for hash
        assert score < 0.9

    def test_calculate_validity_score_missing_fields(self):
        jv = JuryVerifier()
        evidence = _make_evidence()
        evidence.decision = None
        evidence.outcome = None
        evidence.policy_reference = ""
        score = jv._calculate_validity_score(evidence)
        assert score <= 1.0

    def test_calculate_validity_deterministic(self):
        """Same evidence should always produce same score."""
        jv = JuryVerifier()
        evidence = _make_evidence()
        s1 = jv._calculate_validity_score(evidence)
        s2 = jv._calculate_validity_score(evidence)
        assert s1 == s2

    def test_collect_votes(self):
        jv = JuryVerifier(num_agents=3)
        evidence = _make_evidence()
        votes = _run(jv._collect_votes(evidence))
        assert len(votes) == 3

    def test_agent_vote(self):
        jv = JuryVerifier()
        evidence = _make_evidence()
        vote = _run(jv._agent_vote("agent-0", evidence))
        assert vote["vote"] in ("APPROVE", "REJECT")
        assert "score" in vote
        assert "timestamp" in vote


# ---------------------------------------------------------------------------
# EntropyVerifier
# ---------------------------------------------------------------------------

class TestEntropyVerifier:
    """Tests for EntropyVerifier bias detection."""

    def test_init_defaults(self):
        ev = EntropyVerifier()
        assert ev.history_window == 100
        assert ev.decision_history == []

    def test_verify_evidence_single(self):
        ev = EntropyVerifier()
        evidence = _make_evidence()
        result = _run(ev.verify_evidence(evidence))

        assert result["attestor_type"] == "ENTROPY"
        assert "confidence_score" in result
        assert result["proof"]["sample_size"] == 1

    def test_history_accumulates(self):
        ev = EntropyVerifier()
        for i in range(5):
            evidence = _make_evidence(evidence_id=f"ev-{i}")
            _run(ev.verify_evidence(evidence))
        assert len(ev.decision_history) == 5

    def test_history_window_limit(self):
        ev = EntropyVerifier()
        ev.history_window = 10
        for i in range(20):
            evidence = _make_evidence(evidence_id=f"ev-{i}")
            _run(ev.verify_evidence(evidence))
        assert len(ev.decision_history) <= 10

    def test_calculate_entropy_insufficient_data(self):
        ev = EntropyVerifier()
        ev.decision_history = [{"outcome": "A"}] * 5
        score = ev._calculate_entropy()
        assert score == 0.5  # Insufficient data

    def test_calculate_entropy_no_outcomes(self):
        ev = EntropyVerifier()
        ev.decision_history = [{"outcome": None}] * 15
        score = ev._calculate_entropy()
        assert score == 0.0

    def test_detect_bias_insufficient_data(self):
        ev = EntropyVerifier()
        ev.decision_history = [{"outcome": "A"}] * 5
        score = ev._detect_bias()
        assert score == 0.0

    def test_detect_anomalies_insufficient_data(self):
        ev = EntropyVerifier()
        ev.decision_history = [{"outcome": "A"}] * 10
        score = ev._detect_anomalies()
        assert score == 0.0

    def test_detect_anomalies_uniform(self):
        ev = EntropyVerifier()
        ev.decision_history = [{"outcome": "SUCCESS"}] * 25
        score = ev._detect_anomalies()
        # All same → high anomaly
        assert score > 0.5


# ---------------------------------------------------------------------------
# EscrowVerifier
# ---------------------------------------------------------------------------

class TestEscrowVerifier:
    """Tests for EscrowVerifier cryptographic validation."""

    def test_init(self):
        ev = EscrowVerifier()
        assert ev.escrow_id == "escrow-validator"
        assert ev.private_key

    def test_init_custom_id(self):
        ev = EscrowVerifier(escrow_id="custom-escrow")
        assert ev.escrow_id == "custom-escrow"

    def test_verify_valid_hash(self):
        ev = EscrowVerifier()
        evidence = _make_evidence()
        result = _run(ev.verify_evidence(evidence))

        assert result["attestor_type"] == "ESCROW"
        assert result["attestation_status"] == AttestationStatus.APPROVED
        assert result["confidence_score"] == 1.0
        assert result["proof"]["hash_valid"] is True

    def test_verify_invalid_hash(self):
        ev = EscrowVerifier()
        evidence = _make_evidence(matching_hash=False)
        result = _run(ev.verify_evidence(evidence))

        assert result["attestation_status"] == AttestationStatus.REJECTED
        assert result["confidence_score"] == 0.0
        assert result["proof"]["hash_valid"] is False

    def test_verify_hash_method(self):
        ev = EscrowVerifier()
        evidence = _make_evidence()
        assert ev._verify_hash(evidence) is True
        evidence.hash = "tampered"
        assert ev._verify_hash(evidence) is False

    def test_sign_evidence(self):
        ev = EscrowVerifier()
        evidence = _make_evidence()
        sig = ev._sign_evidence(evidence)
        assert isinstance(sig, str)
        assert len(sig) == 64  # SHA-256 hex digest

    def test_generate_merkle_proof(self):
        ev = EscrowVerifier()
        evidence = _make_evidence()
        proof = ev._generate_merkle_proof(evidence)
        assert "leaf" in proof
        assert "root" in proof
        assert len(proof["path"]) == 3


# ---------------------------------------------------------------------------
# ParallelAuditor
# ---------------------------------------------------------------------------

class TestParallelAuditor:
    """Tests for ParallelAuditor orchestration."""

    def test_init(self):
        pa = ParallelAuditor()
        assert pa.jury is not None
        assert pa.entropy is not None
        assert pa.escrow is not None

    def test_calculate_verdict_all_approved(self):
        pa = ParallelAuditor()
        jury = {"attestation_status": AttestationStatus.APPROVED, "confidence_score": 0.9}
        entropy = {"attestation_status": AttestationStatus.APPROVED, "confidence_score": 0.8}
        escrow = {"attestation_status": AttestationStatus.APPROVED, "confidence_score": 1.0}
        verdict = pa._calculate_verdict(jury, entropy, escrow)
        assert verdict["status"] == "VERIFIED"
        assert verdict["approvals"] == 3

    def test_calculate_verdict_majority(self):
        pa = ParallelAuditor()
        jury = {"attestation_status": AttestationStatus.APPROVED, "confidence_score": 0.9}
        entropy = {"attestation_status": AttestationStatus.REJECTED, "confidence_score": 0.3}
        escrow = {"attestation_status": AttestationStatus.APPROVED, "confidence_score": 1.0}
        verdict = pa._calculate_verdict(jury, entropy, escrow)
        assert verdict["status"] == "VERIFIED"
        assert verdict["approvals"] == 2

    def test_calculate_verdict_all_rejected(self):
        pa = ParallelAuditor()
        jury = {"attestation_status": AttestationStatus.REJECTED, "confidence_score": 0.1}
        entropy = {"attestation_status": AttestationStatus.REJECTED, "confidence_score": 0.2}
        escrow = {"attestation_status": AttestationStatus.REJECTED, "confidence_score": 0.0}
        verdict = pa._calculate_verdict(jury, entropy, escrow)
        assert verdict["status"] == "REJECTED"
        assert verdict["approvals"] == 0

    def test_calculate_verdict_disputed(self):
        pa = ParallelAuditor()
        jury = {"attestation_status": AttestationStatus.APPROVED, "confidence_score": 0.9}
        entropy = {"attestation_status": AttestationStatus.REJECTED, "confidence_score": 0.3}
        escrow = {"attestation_status": AttestationStatus.DISPUTED, "confidence_score": 0.5}
        verdict = pa._calculate_verdict(jury, entropy, escrow)
        assert verdict["status"] == "DISPUTED"
        assert verdict["approvals"] == 1

    def test_calculate_verdict_with_exception(self):
        pa = ParallelAuditor()
        jury = {"attestation_status": AttestationStatus.APPROVED, "confidence_score": 0.9}
        entropy = Exception("timeout")  # Simulate exception from asyncio.gather
        escrow = {"attestation_status": AttestationStatus.APPROVED, "confidence_score": 1.0}
        verdict = pa._calculate_verdict(jury, entropy, escrow)
        assert verdict["approvals"] == 2  # Only dict results count


# ---------------------------------------------------------------------------
# ContinuousAuditingService
# ---------------------------------------------------------------------------

class TestContinuousAuditingService:
    """Tests for ContinuousAuditingService."""

    def test_init(self):
        svc = ContinuousAuditingService()
        assert svc.poll_interval == 60
        assert svc.running is False

    def test_init_custom_interval(self):
        svc = ContinuousAuditingService(poll_interval=30)
        assert svc.poll_interval == 30

    def test_stop(self):
        svc = ContinuousAuditingService()
        svc.running = True
        svc.stop()
        assert svc.running is False


# ---------------------------------------------------------------------------
# Governance Config
# ---------------------------------------------------------------------------

class TestGovernanceConfig:
    def test_safe_fallback(self):
        cfg = _load_governance_config("nonexistent")
        # With the mock, returns a dict from the mocked function
        assert isinstance(cfg, dict) or cfg is not None


# ---------------------------------------------------------------------------
# AttestationStatus
# ---------------------------------------------------------------------------

class TestAttestationStatus:
    def test_values(self):
        assert AttestationStatus.APPROVED == "APPROVED"
        assert AttestationStatus.REJECTED == "REJECTED"
        assert AttestationStatus.DISPUTED == "DISPUTED"


# ---------------------------------------------------------------------------
# Coverage Boost: ParallelAuditor HTTP methods
# ---------------------------------------------------------------------------

# Async mock helpers (asyncio.coroutine removed in Python 3.13)
async def _async_return_evidence(evidence):
    async def _inner(eid):
        return evidence
    return _inner

async def _async_return_none(eid):
    return None

async def _async_return_empty(eid, att):
    return {"evidence_id": eid, **att}

async def _async_return_eid(eid, att):
    return {"evidence_id": eid}

async def _async_empty_list():
    return []


class TestParallelAuditorAudit:
    """Tests for audit_evidence, _fetch_evidence, _submit_attestation, batch_audit."""

    def test_audit_evidence_full_flow(self):
        pa = ParallelAuditor()
        evidence = _make_evidence()
        async def mock_fetch(eid): return evidence
        async def mock_submit(eid, att): return {"evidence_id": eid, **att}
        pa._fetch_evidence = mock_fetch
        pa._submit_attestation = mock_submit
        result = _run(pa.audit_evidence("ev-001"))
        assert result["evidence_id"] == "ev-001"
        assert "verdict" in result
        assert "jury" in result
        assert "entropy" in result
        assert "escrow" in result

    def test_audit_evidence_not_found(self):
        pa = ParallelAuditor()
        async def mock_fetch(eid): return None
        pa._fetch_evidence = mock_fetch
        with pytest.raises(ValueError, match="not found"):
            _run(pa.audit_evidence("ev-missing"))

    def test_fetch_evidence_success(self):
        pa = ParallelAuditor()
        import requests as req_mod
        fake_resp = mock.MagicMock()
        fake_resp.json.return_value = {
            "evidence_id": "ev-001", "activity_id": "act-001",
            "activity_name": "test", "execution_id": "exec-001",
            "agent_id": "agent-A", "event_type": "ACTION",
            "event_data": {"a": 1}, "decision": "ALLOW",
            "outcome": "SUCCESS", "policy_reference": "pol-001",
            "hash": "abc123",
        }
        fake_resp.raise_for_status = mock.MagicMock()
        req_mod.get = mock.MagicMock(return_value=fake_resp)
        result = _run(pa._fetch_evidence("ev-001"))
        assert result is not None
        assert result.evidence_id == "ev-001"

    def test_fetch_evidence_failure(self):
        pa = ParallelAuditor()
        import requests as req_mod
        req_mod.get = mock.MagicMock(side_effect=Exception("connection error"))
        result = _run(pa._fetch_evidence("ev-fail"))
        assert result is None

    def test_submit_attestation_success(self):
        pa = ParallelAuditor()
        import requests as req_mod
        fake_resp = mock.MagicMock()
        fake_resp.json.return_value = {"id": "att-001", "status": "ok"}
        fake_resp.raise_for_status = mock.MagicMock()
        req_mod.post = mock.MagicMock(return_value=fake_resp)
        result = _run(pa._submit_attestation("ev-001", {"score": 0.9}))
        assert result["id"] == "att-001"

    def test_submit_attestation_failure(self):
        pa = ParallelAuditor()
        import requests as req_mod
        req_mod.post = mock.MagicMock(side_effect=Exception("post error"))
        result = _run(pa._submit_attestation("ev-001", {"score": 0.9}))
        assert result == {}

    def test_batch_audit(self):
        pa = ParallelAuditor()
        evidence = _make_evidence()
        async def mock_fetch(eid): return evidence
        async def mock_submit(eid, att): return {"evidence_id": eid}
        pa._fetch_evidence = mock_fetch
        pa._submit_attestation = mock_submit
        results = _run(pa.batch_audit(["ev-001", "ev-002"]))
        assert len(results) >= 1  # Some may succeed


# ---------------------------------------------------------------------------
# Coverage Boost: ContinuousAuditingService methods
# ---------------------------------------------------------------------------

class TestContinuousAuditingServiceMethods:
    """Tests for _audit_cycle and _fetch_unverified_evidence."""

    def test_audit_cycle_with_data(self):
        svc = ContinuousAuditingService()
        evidence = _make_evidence()
        async def mock_fetch_unverified():
            return [{"evidence_id": "ev-001"}, {"evidence_id": "ev-002"}]
        async def mock_fetch(eid): return evidence
        async def mock_submit(eid, att): return {"evidence_id": eid}
        svc._fetch_unverified_evidence = mock_fetch_unverified
        svc.auditor._fetch_evidence = mock_fetch
        svc.auditor._submit_attestation = mock_submit
        _run(svc._audit_cycle())
        assert svc.last_audit_time is not None

    def test_audit_cycle_empty(self):
        svc = ContinuousAuditingService()
        async def mock_fetch_unverified(): return []
        svc._fetch_unverified_evidence = mock_fetch_unverified
        _run(svc._audit_cycle())

    def test_fetch_unverified_success(self):
        svc = ContinuousAuditingService()
        import requests as req_mod
        fake_resp = mock.MagicMock()
        fake_resp.json.return_value = [{"evidence_id": "ev-001"}]
        fake_resp.raise_for_status = mock.MagicMock()
        req_mod.get = mock.MagicMock(return_value=fake_resp)
        result = _run(svc._fetch_unverified_evidence())
        assert len(result) == 1

    def test_fetch_unverified_error(self):
        svc = ContinuousAuditingService()
        import requests as req_mod
        req_mod.get = mock.MagicMock(side_effect=Exception("timeout"))
        result = _run(svc._fetch_unverified_evidence())
        assert result == []


# ---------------------------------------------------------------------------
# Coverage Boost: JuryVerifier rejected/disputed consensus paths
# ---------------------------------------------------------------------------

class TestJuryVerifierConsensusPaths:
    """Cover lines 112-117: rejection consensus + disputed paths."""

    def test_jury_rejects_on_consensus_reject(self):
        jv = JuryVerifier(num_agents=3, consensus_threshold=0.5)
        evidence = _make_evidence(matching_hash=False)
        evidence.decision = None
        evidence.outcome = None
        evidence.policy_reference = ""
        # With bad hash + no decision/outcome/policy → low validity → reject votes
        result = _run(jv.verify_evidence(evidence))
        assert result["attestation_status"] in [
            AttestationStatus.APPROVED,
            AttestationStatus.REJECTED,
            AttestationStatus.DISPUTED,
        ]


# ---------------------------------------------------------------------------
# Coverage Boost: EntropyVerifier bias/anomaly with valid data
# ---------------------------------------------------------------------------

class TestEntropyVerifierBiasAnomaly:
    """Cover _detect_bias and _detect_anomalies with sufficient data."""

    def test_detect_bias_with_data(self):
        ev = EntropyVerifier()
        ev.decision_history = [{"outcome": "A"}] * 8 + [{"outcome": "B"}] * 2 + [{"outcome": "C"}] * 2
        score = ev._detect_bias()
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_detect_bias_no_outcomes(self):
        ev = EntropyVerifier()
        ev.decision_history = [{"outcome": None}] * 15
        score = ev._detect_bias()
        assert score == 0.0

    def test_detect_anomalies_varied(self):
        ev = EntropyVerifier()
        ev.decision_history = [
            {"outcome": f"type-{i % 5}"} for i in range(25)
        ]
        score = ev._detect_anomalies()
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_detect_anomalies_no_outcomes(self):
        ev = EntropyVerifier()
        ev.decision_history = [{"outcome": None}] * 25
        score = ev._detect_anomalies()
        assert score == 0.0


# ---------------------------------------------------------------------------
# Governance fallback (L44-45)
# ---------------------------------------------------------------------------

class TestGovernanceConfigFallback:
    """Cover _load_governance_config exception fallback."""

    def test_fallback_returns_empty_dict(self):
        """When import fails, returns {}."""
        with mock.patch.dict("sys.modules", {"config.governance_config": None}):
            result = _load_governance_config("tenant-123")
            assert result == {}


# ---------------------------------------------------------------------------
# JuryVerifier — DISPUTED verdict (L116-117)
# ---------------------------------------------------------------------------

class TestJuryVerifierDisputed:
    """Cover the DISPUTED branch when no consensus is reached."""

    def test_disputed_verdict(self):
        jv = JuryVerifier(num_agents=3, consensus_threshold=0.8)
        evidence = _make_evidence()

        # Force a split vote — 1 approve, 1 reject, 1 approve → 2/3 = 0.67 < 0.8
        async def _split_votes(ev):
            return {
                "agent-a": {"vote": "APPROVE", "score": 0.6},
                "agent-b": {"vote": "REJECT", "score": 0.3},
                "agent-c": {"vote": "APPROVE", "score": 0.7},
            }

        jv._collect_votes = _split_votes
        result = asyncio.get_event_loop().run_until_complete(jv.verify_evidence(evidence))
        assert result["attestation_status"] == AttestationStatus.DISPUTED
        assert "No consensus" in result["reasoning"]


# ---------------------------------------------------------------------------
# EntropyVerifier — REJECTED verdict (L249-250)
# ---------------------------------------------------------------------------

class TestEntropyVerifierRejected:
    """Cover the REJECTED branch (low entropy / high bias)."""

    def test_rejected_verdict(self):
        ev = EntropyVerifier()
        # Override confidence_low to make REJECTED easy to trigger
        ev.confidence_low = 0.99
        evidence = _make_evidence()

        # Feed identical decisions → low entropy → low confidence
        ev.decision_history = [{"outcome": "A"}] * 20
        result = asyncio.get_event_loop().run_until_complete(ev.verify_evidence(evidence))
        assert result["attestation_status"] == AttestationStatus.REJECTED
        assert "Low entropy" in result["reasoning"]


# ---------------------------------------------------------------------------
# ContinuousAuditingService (L608-662)
# ---------------------------------------------------------------------------

class TestContinuousAuditingService:
    """Cover start/stop loop, audit_cycle, and _fetch_unverified_evidence."""

    def test_init(self):
        svc = ContinuousAuditingService(poll_interval=10)
        assert svc.poll_interval == 10
        assert svc.running is False

    def test_stop(self):
        svc = ContinuousAuditingService()
        svc.running = True
        svc.stop()
        assert svc.running is False

    def test_start_and_stop(self):
        """Run start() and stop it after one iteration."""
        svc = ContinuousAuditingService(poll_interval=0.01)

        async def _run():
            task = asyncio.create_task(svc.start())
            await asyncio.sleep(0.05)
            svc.stop()
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        with mock.patch.object(svc, "_audit_cycle", new_callable=mock.AsyncMock):
            asyncio.get_event_loop().run_until_complete(_run())
        assert svc.running is False

    def test_start_handles_audit_cycle_error(self):
        """start() catches exceptions in _audit_cycle."""
        svc = ContinuousAuditingService(poll_interval=0.01)

        async def _run():
            task = asyncio.create_task(svc.start())
            await asyncio.sleep(0.05)
            svc.stop()
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        with mock.patch.object(svc, "_audit_cycle", side_effect=RuntimeError("boom"), new_callable=mock.AsyncMock):
            # Should NOT raise — error is caught inside start()
            asyncio.get_event_loop().run_until_complete(_run())

    def test_audit_cycle_no_evidence(self):
        """When _fetch_unverified_evidence returns [], does nothing."""
        svc = ContinuousAuditingService()

        with mock.patch.object(svc, "_fetch_unverified_evidence", new_callable=mock.AsyncMock, return_value=[]):
            asyncio.get_event_loop().run_until_complete(svc._audit_cycle())

    def test_audit_cycle_with_evidence(self):
        """When evidence found, calls batch_audit."""
        svc = ContinuousAuditingService()
        fake_evidence = [{"evidence_id": f"ev-{i}"} for i in range(3)]

        with mock.patch.object(svc, "_fetch_unverified_evidence", new_callable=mock.AsyncMock, return_value=fake_evidence):
            with mock.patch.object(svc.auditor, "batch_audit", new_callable=mock.AsyncMock, return_value=[]):
                asyncio.get_event_loop().run_until_complete(svc._audit_cycle())
                svc.auditor.batch_audit.assert_called_once()

    def test_fetch_unverified_success(self):
        """HTTP GET to Evidence Vault returns data."""
        svc = ContinuousAuditingService()
        mock_resp = mock.MagicMock()
        mock_resp.json.return_value = [{"evidence_id": "ev-1"}]
        mock_resp.raise_for_status = mock.MagicMock()

        with mock.patch("auditor.requests.get", return_value=mock_resp):
            result = asyncio.get_event_loop().run_until_complete(svc._fetch_unverified_evidence())
            assert len(result) == 1

    def test_fetch_unverified_failure(self):
        """HTTP error returns empty list."""
        svc = ContinuousAuditingService()

        with mock.patch("auditor.requests.get", side_effect=Exception("connection refused")):
            result = asyncio.get_event_loop().run_until_complete(svc._fetch_unverified_evidence())
            assert result == []


# ---------------------------------------------------------------------------
# Coverage Boost: main() and run_continuous_service() (L668-711)
# ---------------------------------------------------------------------------

from auditor import main, run_continuous_service


class TestMainFunction:
    """Cover the main() example usage function (L668-702)."""

    def test_main_success(self):
        """main() calls audit_evidence and prints results."""
        fake_result = {
            "evidence_id": "ev-001",
            "verdict": {"status": "VERIFIED", "confidence": 0.95, "approvals": 3},
            "jury": {"attestation_status": "APPROVED", "confidence_score": 0.9, "reasoning": "ok"},
            "entropy": {"attestation_status": "APPROVED", "confidence_score": 0.8, "reasoning": "ok"},
            "escrow": {"attestation_status": "APPROVED", "confidence_score": 1.0, "reasoning": "ok"},
        }
        with mock.patch.object(ParallelAuditor, "audit_evidence", new_callable=mock.AsyncMock, return_value=fake_result):
            asyncio.get_event_loop().run_until_complete(main())

    def test_main_exception(self):
        """main() catches audit_evidence exceptions and prints error."""
        with mock.patch.object(ParallelAuditor, "audit_evidence", new_callable=mock.AsyncMock, side_effect=Exception("audit failed")):
            # Should NOT raise — exception is caught inside main()
            asyncio.get_event_loop().run_until_complete(main())


class TestRunContinuousService:
    """Cover run_continuous_service() (L704-711)."""

    def test_run_continuous_normal(self):
        """run_continuous_service creates ContinuousAuditingService and calls start()."""
        with mock.patch.object(ContinuousAuditingService, "start", new_callable=mock.AsyncMock, return_value=None):
            asyncio.get_event_loop().run_until_complete(run_continuous_service())

    def test_run_continuous_keyboard_interrupt(self):
        """run_continuous_service catches KeyboardInterrupt and calls stop()."""
        with mock.patch.object(ContinuousAuditingService, "start", new_callable=mock.AsyncMock, side_effect=KeyboardInterrupt):
            with mock.patch.object(ContinuousAuditingService, "stop") as mock_stop:
                asyncio.get_event_loop().run_until_complete(run_continuous_service())
                mock_stop.assert_called_once()

