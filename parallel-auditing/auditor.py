"""
Parallel Auditing System
Multi-verifier evidence validation with Jury, Entropy, and Escrow

Implements three independent verification mechanisms:
1. JURY - Multi-agent consensus voting
2. ENTROPY - Randomness and bias detection
3. ESCROW - Third-party cryptographic validation
"""

import asyncio
import hashlib
import json
import random
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import requests
import numpy as np
from scipy import stats
import logging

import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration — from environment variables
EVIDENCE_VAULT_URL = os.getenv("EVIDENCE_VAULT_URL", "http://localhost:8003")
ACTIVITY_REGISTRY_URL = os.getenv("ACTIVITY_REGISTRY_URL", "http://localhost:8002")

class AttestationStatus(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DISPUTED = "DISPUTED"

@dataclass
class EvidenceRecord:
    """Evidence record from Evidence Vault"""
    evidence_id: str
    activity_id: str
    activity_name: str
    execution_id: str
    agent_id: str
    event_type: str
    event_data: Dict[str, Any]
    decision: Optional[str]
    outcome: Optional[str]
    policy_reference: str
    hash: str

# ============================================================================
# JURY VERIFIER - Multi-Agent Consensus
# ============================================================================

class JuryVerifier:
    """
    Jury-based verification using multi-agent consensus
    
    Multiple independent agents vote on evidence validity
    Consensus threshold determines approval
    """
    
    def __init__(self, num_agents: int = 10, consensus_threshold: float = 0.75) -> None:
        self.num_agents = num_agents
        self.consensus_threshold = consensus_threshold
        self.agent_ids = [f"jury-agent-{i}" for i in range(num_agents)]
    
    async def verify_evidence(self, evidence: EvidenceRecord) -> Dict[str, Any]:
        """
        Verify evidence using jury consensus
        
        Returns attestation with voting results
        """
        logger.info(f"Jury verification for evidence {evidence.evidence_id}")
        
        # Simulate parallel voting by agents
        votes = await self._collect_votes(evidence)
        
        # Calculate consensus
        approve_count = sum(1 for v in votes.values() if v['vote'] == 'APPROVE')
        reject_count = sum(1 for v in votes.values() if v['vote'] == 'REJECT')
        total_votes = len(votes)
        
        approval_rate = approve_count / total_votes
        
        # Determine attestation status
        if approval_rate >= self.consensus_threshold:
            status = AttestationStatus.APPROVED
            reasoning = f"Consensus achieved: {approve_count}/{total_votes} agents approved"
        elif (reject_count / total_votes) >= self.consensus_threshold:
            status = AttestationStatus.REJECTED
            reasoning = f"Consensus rejection: {reject_count}/{total_votes} agents rejected"
        else:
            status = AttestationStatus.DISPUTED
            reasoning = f"No consensus: {approve_count} approve, {reject_count} reject"
        
        return {
            "attestor_type": "JURY",
            "attestor_id": "jury-system",
            "attestation_status": status,
            "confidence_score": approval_rate,
            "reasoning": reasoning,
            "proof": {
                "votes": votes,
                "approve_count": approve_count,
                "reject_count": reject_count,
                "total_votes": total_votes,
                "consensus_threshold": self.consensus_threshold
            }
        }
    
    async def _collect_votes(self, evidence: EvidenceRecord) -> Dict[str, Dict]:
        """Collect votes from all jury agents"""
        tasks = [self._agent_vote(agent_id, evidence) for agent_id in self.agent_ids]
        results = await asyncio.gather(*tasks)
        
        return {
            agent_id: result 
            for agent_id, result in zip(self.agent_ids, results)
        }
    
    async def _agent_vote(self, agent_id: str, evidence: EvidenceRecord) -> Dict:
        """Single agent vote on evidence"""
        # Simulate agent deliberation
        await asyncio.sleep(random.uniform(0.1, 0.5))
        
        # Simple validation logic (in production, use sophisticated AI)
        score = self._calculate_validity_score(evidence)
        
        vote = "APPROVE" if score > 0.7 else "REJECT"
        
        return {
            "agent_id": agent_id,
            "vote": vote,
            "score": score,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def _calculate_validity_score(self, evidence: EvidenceRecord) -> float:
        """Calculate validity score for evidence"""
        score = 0.5  # Base score
        
        # Check hash integrity
        calculated_hash = hashlib.sha256(
            json.dumps(evidence.event_data, sort_keys=True).encode()
        ).hexdigest()
        
        if calculated_hash == evidence.hash:
            score += 0.3
        
        # Check required fields
        if evidence.decision and evidence.outcome:
            score += 0.1
        
        # Check policy reference
        if evidence.policy_reference:
            score += 0.1
        
        # T12 fix: Deterministic variance derived from evidence hash
        # Use evidence hash to produce a stable offset in [-0.1, 0.1]
        # This ensures reproducible scores while still providing variance
        hash_seed = hashlib.sha256(
            f"{evidence.evidence_id}:{evidence.hash}".encode()
        ).digest()
        # Map first 4 bytes to float in [-0.1, 0.1]
        hash_val = int.from_bytes(hash_seed[:4], "big") / 0xFFFFFFFF  # [0, 1]
        deterministic_offset = (hash_val * 0.2) - 0.1  # [-0.1, 0.1]
        score += deterministic_offset
        
        return max(0.0, min(1.0, score))


# ============================================================================
# ENTROPY VERIFIER - Randomness & Bias Detection
# ============================================================================

class EntropyVerifier:
    """
    Entropy-based verification for randomness and bias detection
    
    Analyzes decision patterns for:
    - Statistical bias
    - Anomalous patterns
    - Randomness quality
    """
    
    def __init__(self) -> None:
        self.history_window = 100  # Number of recent decisions to analyze
        self.decision_history = []
    
    async def verify_evidence(self, evidence: EvidenceRecord) -> Dict[str, Any]:
        """
        Verify evidence using entropy analysis
        
        Detects bias and anomalies in decision patterns
        """
        logger.info(f"Entropy verification for evidence {evidence.evidence_id}")
        
        # Add to history
        self.decision_history.append({
            'outcome': evidence.outcome,
            'decision': evidence.decision,
            'timestamp': datetime.utcnow()
        })
        
        # Keep only recent history
        if len(self.decision_history) > self.history_window:
            self.decision_history = self.decision_history[-self.history_window:]
        
        # Calculate entropy metrics
        entropy_score = self._calculate_entropy()
        bias_score = self._detect_bias()
        anomaly_score = self._detect_anomalies()
        
        # Overall confidence
        confidence = (entropy_score + (1 - bias_score) + (1 - anomaly_score)) / 3
        
        # Determine status
        if confidence > 0.8:
            status = AttestationStatus.APPROVED
            reasoning = f"High entropy ({entropy_score:.2f}), low bias ({bias_score:.2f})"
        elif confidence < 0.5:
            status = AttestationStatus.REJECTED
            reasoning = f"Low entropy or high bias detected"
        else:
            status = AttestationStatus.DISPUTED
            reasoning = f"Moderate confidence ({confidence:.2f})"
        
        return {
            "attestor_type": "ENTROPY",
            "attestor_id": "entropy-analyzer",
            "attestation_status": status,
            "confidence_score": confidence,
            "reasoning": reasoning,
            "proof": {
                "entropy_score": entropy_score,
                "bias_score": bias_score,
                "anomaly_score": anomaly_score,
                "sample_size": len(self.decision_history)
            }
        }
    
    def _calculate_entropy(self) -> float:
        """Calculate Shannon entropy of decision outcomes"""
        if len(self.decision_history) < 10:
            return 0.5  # Insufficient data
        
        outcomes = [d['outcome'] for d in self.decision_history if d['outcome']]
        
        if not outcomes:
            return 0.0
        
        # Count occurrences
        unique, counts = np.unique(outcomes, return_counts=True)
        probabilities = counts / len(outcomes)
        
        # Shannon entropy
        entropy = -np.sum(probabilities * np.log2(probabilities + 1e-10))
        
        # Normalize to [0, 1]
        max_entropy = np.log2(len(unique))
        normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0
        
        return normalized_entropy
    
    def _detect_bias(self) -> float:
        """Detect bias in decision patterns"""
        if len(self.decision_history) < 10:
            return 0.0
        
        outcomes = [d['outcome'] for d in self.decision_history if d['outcome']]
        
        if not outcomes:
            return 0.0
        
        # Chi-square test for uniform distribution
        unique, counts = np.unique(outcomes, return_counts=True)
        expected = len(outcomes) / len(unique)
        
        chi_square = np.sum((counts - expected) ** 2 / expected)
        p_value = 1 - stats.chi2.cdf(chi_square, len(unique) - 1)
        
        # Low p-value indicates bias
        bias_score = 1 - p_value
        
        return bias_score
    
    def _detect_anomalies(self) -> float:
        """Detect anomalous patterns"""
        if len(self.decision_history) < 20:
            return 0.0
        
        # Check for suspicious patterns (e.g., all same outcome)
        recent_outcomes = [d['outcome'] for d in self.decision_history[-20:] if d['outcome']]
        
        if not recent_outcomes:
            return 0.0
        
        # Calculate variance
        unique_count = len(set(recent_outcomes))
        
        # Anomaly if too uniform
        anomaly_score = 1.0 - (unique_count / len(recent_outcomes))
        
        return anomaly_score

# ============================================================================
# ESCROW VERIFIER - Third-Party Cryptographic Validation
# ============================================================================

class EscrowVerifier:
    """
    Escrow-based verification using cryptographic proofs
    
    Independent third-party validation with:
    - Digital signatures
    - Merkle proofs
    - Zero-knowledge proofs (simulated)
    """
    
    def __init__(self, escrow_id: str = "escrow-validator") -> None:
        self.escrow_id = escrow_id
        self.private_key = self._generate_key()
    
    def _generate_key(self) -> str:
        """Generate escrow private key (simulated)"""
        return hashlib.sha256(self.escrow_id.encode()).hexdigest()
    
    async def verify_evidence(self, evidence: EvidenceRecord) -> Dict[str, Any]:
        """
        Verify evidence using cryptographic validation
        
        Checks:
        - Hash integrity
        - Signature validity
        - Merkle proof
        """
        logger.info(f"Escrow verification for evidence {evidence.evidence_id}")
        
        # Verify hash integrity
        hash_valid = self._verify_hash(evidence)
        
        # Generate cryptographic proof
        signature = self._sign_evidence(evidence)
        merkle_proof = self._generate_merkle_proof(evidence)
        
        # Calculate confidence
        confidence = 1.0 if hash_valid else 0.0
        
        # Determine status
        if hash_valid:
            status = AttestationStatus.APPROVED
            reasoning = "Cryptographic validation passed"
        else:
            status = AttestationStatus.REJECTED
            reasoning = "Hash integrity check failed"
        
        return {
            "attestor_type": "ESCROW",
            "attestor_id": self.escrow_id,
            "attestation_status": status,
            "confidence_score": confidence,
            "reasoning": reasoning,
            "signature": signature,
            "proof": {
                "hash_valid": hash_valid,
                "merkle_proof": merkle_proof,
                "escrow_signature": signature
            }
        }
    
    def _verify_hash(self, evidence: EvidenceRecord) -> bool:
        """Verify evidence hash integrity"""
        calculated_hash = hashlib.sha256(
            json.dumps(evidence.event_data, sort_keys=True).encode()
        ).hexdigest()
        
        return calculated_hash == evidence.hash
    
    def _sign_evidence(self, evidence: EvidenceRecord) -> str:
        """Sign evidence with escrow private key"""
        message = f"{evidence.evidence_id}:{evidence.hash}"
        signature = hashlib.sha256(
            (message + self.private_key).encode()
        ).hexdigest()
        
        return signature
    
    def _generate_merkle_proof(self, evidence: EvidenceRecord) -> Dict:
        """Generate Merkle proof for evidence"""
        # Simplified Merkle proof
        leaf_hash = evidence.hash
        
        # Simulate Merkle tree path
        proof_path = []
        current_hash = leaf_hash
        
        for i in range(3):  # 3 levels
            sibling = hashlib.sha256(f"sibling-{i}".encode()).hexdigest()
            parent = hashlib.sha256((current_hash + sibling).encode()).hexdigest()
            
            proof_path.append({
                "level": i,
                "sibling": sibling,
                "parent": parent
            })
            
            current_hash = parent
        
        return {
            "leaf": leaf_hash,
            "root": current_hash,
            "path": proof_path
        }

# Continued in next file...
# ============================================================================
# PARALLEL AUDITING ORCHESTRATOR
# ============================================================================

class ParallelAuditor:
    """
    Orchestrates parallel evidence verification across multiple verifiers
    
    Coordinates:
    - Jury (multi-agent consensus)
    - Entropy (bias detection)
    - Escrow (cryptographic validation)
    """
    
    def __init__(self) -> None:
        self.jury = JuryVerifier(num_agents=10, consensus_threshold=0.75)
        self.entropy = EntropyVerifier()
        self.escrow = EscrowVerifier()
        self.evidence_vault_url = EVIDENCE_VAULT_URL
    
    async def audit_evidence(self, evidence_id: str) -> Dict[str, Any]:
        """
        Run parallel audit on evidence
        
        Returns combined attestation results
        """
        logger.info(f"Starting parallel audit for evidence {evidence_id}")
        
        # Fetch evidence from vault
        evidence = await self._fetch_evidence(evidence_id)
        
        if not evidence:
            raise ValueError(f"Evidence {evidence_id} not found")
        
        # Run verifiers in parallel
        results = await asyncio.gather(
            self.jury.verify_evidence(evidence),
            self.entropy.verify_evidence(evidence),
            self.escrow.verify_evidence(evidence),
            return_exceptions=True
        )
        
        jury_result, entropy_result, escrow_result = results
        
        # Submit attestations to Evidence Vault
        attestations = []
        for result in [jury_result, entropy_result, escrow_result]:
            if isinstance(result, dict):
                attestation = await self._submit_attestation(evidence_id, result)
                attestations.append(attestation)
        
        # Calculate overall verdict
        verdict = self._calculate_verdict(jury_result, entropy_result, escrow_result)
        
        return {
            "evidence_id": evidence_id,
            "verdict": verdict,
            "attestations": attestations,
            "jury": jury_result,
            "entropy": entropy_result,
            "escrow": escrow_result
        }
    
    async def _fetch_evidence(self, evidence_id: str) -> Optional[EvidenceRecord]:
        """Fetch evidence from Evidence Vault"""
        try:
            response = requests.get(f"{self.evidence_vault_url}/api/v1/evidence/{evidence_id}")
            response.raise_for_status()
            data = response.json()
            
            return EvidenceRecord(
                evidence_id=data['evidence_id'],
                activity_id=data['activity_id'],
                activity_name=data['activity_name'],
                execution_id=data['execution_id'],
                agent_id=data['agent_id'],
                event_type=data['event_type'],
                event_data=data['event_data'],
                decision=data.get('decision'),
                outcome=data.get('outcome'),
                policy_reference=data['policy_reference'],
                hash=data['hash']
            )
        except Exception as e:
            logger.error(f"Failed to fetch evidence: {e}")
            return None
    
    async def _submit_attestation(self, evidence_id: str, attestation: Dict) -> Dict:
        """Submit attestation to Evidence Vault"""
        try:
            response = requests.post(
                f"{self.evidence_vault_url}/api/v1/evidence/{evidence_id}/attest",
                json={
                    "evidence_id": evidence_id,
                    **attestation
                }
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to submit attestation: {e}")
            return {}
    
    def _calculate_verdict(self, jury: Dict, entropy: Dict, escrow: Dict) -> Dict:
        """Calculate overall verdict from all verifiers"""
        # Count approvals
        approvals = sum([
            1 if isinstance(r, dict) and r.get('attestation_status') == AttestationStatus.APPROVED else 0
            for r in [jury, entropy, escrow]
        ])
        
        # Calculate average confidence
        confidences = [
            r.get('confidence_score', 0)
            for r in [jury, entropy, escrow]
            if isinstance(r, dict)
        ]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0
        
        # Determine overall status
        if approvals >= 2:  # Majority approval
            status = "VERIFIED"
        elif approvals == 0:
            status = "REJECTED"
        else:
            status = "DISPUTED"
        
        return {
            "status": status,
            "approvals": approvals,
            "total_verifiers": 3,
            "confidence": avg_confidence,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def batch_audit(self, evidence_ids: List[str]) -> List[Dict]:
        """Audit multiple evidence records in parallel"""
        tasks = [self.audit_evidence(eid) for eid in evidence_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return [r for r in results if isinstance(r, dict)]

# ============================================================================
# CONTINUOUS AUDITING SERVICE
# ============================================================================

class ContinuousAuditingService:
    """
    Background service for continuous evidence auditing
    
    Monitors Evidence Vault for new evidence and triggers parallel audits
    """
    
    def __init__(self, poll_interval: int = 60) -> None:
        self.poll_interval = poll_interval
        self.auditor = ParallelAuditor()
        self.last_audit_time = datetime.utcnow()
        self.running = False
    
    async def start(self) -> None:
        """Start continuous auditing service"""
        self.running = True
        logger.info("Continuous auditing service started")
        
        while self.running:
            try:
                await self._audit_cycle()
            except Exception as e:
                logger.error(f"Audit cycle error: {e}")
            
            await asyncio.sleep(self.poll_interval)
    
    def stop(self) -> None:
        """Stop continuous auditing service"""
        self.running = False
        logger.info("Continuous auditing service stopped")
    
    async def _audit_cycle(self) -> None:
        """Single audit cycle"""
        # Fetch unverified evidence
        unverified = await self._fetch_unverified_evidence()
        
        if not unverified:
            logger.info("No unverified evidence found")
            return
        
        logger.info(f"Found {len(unverified)} unverified evidence records")
        
        # Audit in batches
        batch_size = 10
        for i in range(0, len(unverified), batch_size):
            batch = unverified[i:i+batch_size]
            evidence_ids = [e['evidence_id'] for e in batch]
            
            results = await self.auditor.batch_audit(evidence_ids)
            logger.info(f"Audited batch of {len(results)} evidence records")
        
        self.last_audit_time = datetime.utcnow()
    
    async def _fetch_unverified_evidence(self) -> List[Dict]:
        """Fetch unverified evidence from Evidence Vault"""
        try:
            response = requests.get(
                f"{EVIDENCE_VAULT_URL}/api/v1/evidence",
                params={
                    "verification_status": "PENDING",
                    "limit": 100
                }
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch unverified evidence: {e}")
            return []

# ============================================================================
# USAGE EXAMPLE
# ============================================================================

async def main() -> None:
    """Example usage of parallel auditing"""
    
    # Create auditor
    auditor = ParallelAuditor()
    
    # Audit single evidence
    evidence_id = "550e8400-e29b-41d4-a716-446655440000"
    
    try:
        result = await auditor.audit_evidence(evidence_id)
        
        print(f"\n=== Parallel Audit Results ===")
        print(f"Evidence ID: {result['evidence_id']}")
        print(f"Verdict: {result['verdict']['status']}")
        print(f"Confidence: {result['verdict']['confidence']:.2f}")
        print(f"Approvals: {result['verdict']['approvals']}/3")
        
        print(f"\n--- Jury Verification ---")
        print(f"Status: {result['jury']['attestation_status']}")
        print(f"Confidence: {result['jury']['confidence_score']:.2f}")
        print(f"Reasoning: {result['jury']['reasoning']}")
        
        print(f"\n--- Entropy Verification ---")
        print(f"Status: {result['entropy']['attestation_status']}")
        print(f"Confidence: {result['entropy']['confidence_score']:.2f}")
        print(f"Reasoning: {result['entropy']['reasoning']}")
        
        print(f"\n--- Escrow Verification ---")
        print(f"Status: {result['escrow']['attestation_status']}")
        print(f"Confidence: {result['escrow']['confidence_score']:.2f}")
        print(f"Reasoning: {result['escrow']['reasoning']}")
        
    except Exception as e:
        print(f"Audit failed: {e}")

async def run_continuous_service() -> None:
    """Run continuous auditing service"""
    service = ContinuousAuditingService(poll_interval=60)
    
    try:
        await service.start()
    except KeyboardInterrupt:
        service.stop()

if __name__ == "__main__":
    # Run single audit
    asyncio.run(main())
    
    # Or run continuous service
    # asyncio.run(run_continuous_service())
