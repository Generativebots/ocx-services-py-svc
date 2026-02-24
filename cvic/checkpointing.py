"""
Context-Vector Integrity Checkpointing (CVIC) — Patent §0023-0024

Measures semantic drift across sequential agent hops using cosine similarity.
If the vector distance between the originating intent (A) and downstream
context (B) exceeds the Semantic Drift Threshold (loaded from DB), the escrow
controller quarantines the packet.

HITL is ALWAYS notified when semantic drift is detected.

Formula: S_C(A,B) = (A · B) / (||A|| * ||B||)
"""

import hashlib
import logging
import math
import re
import os
from collections import Counter
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

import requests

logger = logging.getLogger(__name__)

# ─── Configuration (loaded from DB via config service) ───────────────────────

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
ESCROW_CONTROLLER_URL = os.getenv("ESCROW_CONTROLLER_URL", "http://localhost:8080")

# ─── Default loaded from DB; code-level fallback is EMERGENCY ONLY ───────────
DEFAULT_SEMANTIC_DRIFT_THRESHOLD = float(
    os.getenv("OCX_SEMANTIC_DRIFT_THRESHOLD", "0.85")
)


@dataclass
class CVICCheckpoint:
    """A single checkpoint in a multi-agent chain."""
    hop_index: int
    agent_id: str
    context_text: str
    vector: List[float] = field(default_factory=list)
    vector_hash: str = ""
    timestamp: str = ""


@dataclass
class CVICResult:
    """Result of a CVIC integrity check."""
    cosine_similarity: float
    drift_detected: bool
    threshold_used: float
    hop_a_agent: str
    hop_b_agent: str
    quarantine_recommended: bool
    hitl_required: bool
    hitl_reason: str = ""


class ContextVectorCheckpointer:
    """
    Implements Context-Vector Integrity Checkpointing (CVIC).

    At each transport-layer hop, the CVIC extracts the agent's contextual
    prompt history and generates a dimensional vector. Cosine similarity
    is calculated between sequential hops to detect hallucination drift.

    All thresholds are loaded from the tenant's DB configuration.
    HITL is ALWAYS required when drift is detected.

    Memory safety: chains are auto-purged after CHAIN_TTL_SECONDS and
    capped at MAX_CHAINS to prevent unbounded growth.
    """

    CHAIN_TTL_SECONDS = 1800  # 30 minutes
    MAX_CHAINS = 5000

    def __init__(self, semantic_drift_threshold: Optional[float] = None) -> None:
        """
        Args:
            semantic_drift_threshold: Override from DB config.
                If None, uses the environment/default fallback.
        """
        self.semantic_drift_threshold = (
            semantic_drift_threshold
            if semantic_drift_threshold is not None
            else DEFAULT_SEMANTIC_DRIFT_THRESHOLD
        )
        # Checkpoint history per transaction chain
        self._chains: Dict[str, List[CVICCheckpoint]] = {}
        # Track when chains were created for TTL eviction
        self._chain_created: Dict[str, float] = {}

    def set_threshold_from_config(self, threshold: float) -> None:
        """Update threshold from tenant governance config (loaded from DB)."""
        self.semantic_drift_threshold = threshold
        logger.info(
            f"CVIC threshold updated from DB config: {threshold}"
        )

    # ─── Core API ─────────────────────────────────────────────────────────

    def checkpoint(
        self,
        chain_id: str,
        hop_index: int,
        agent_id: str,
        context_text: str,
    ) -> Optional[CVICResult]:
        """
        Record a checkpoint and compare against the PREVIOUS hop.

        Args:
            chain_id: Unique identifier for the multi-agent chain.
            hop_index: The sequential hop number (0, 1, 2, ...).
            agent_id: The agent producing this context.
            context_text: The agent's full contextual prompt/output.

        Returns:
            CVICResult if hop_index > 0 (comparison available), else None.
        """
        # Build the term-frequency vector for this checkpoint
        vector = self._text_to_vector(context_text)
        vector_hash = self._hash_vector(vector)

        cp = CVICCheckpoint(
            hop_index=hop_index,
            agent_id=agent_id,
            context_text=context_text,
            vector=vector,
            vector_hash=vector_hash,
            timestamp=datetime.utcnow().isoformat(),
        )

        # Periodic GC before storing
        self._gc()

        # Store in chain
        if chain_id not in self._chains:
            self._chains[chain_id] = []
            self._chain_created[chain_id] = datetime.utcnow().timestamp()
        self._chains[chain_id].append(cp)

        # If this is the first hop, nothing to compare
        if hop_index == 0 or len(self._chains[chain_id]) < 2:
            logger.info(
                f"[CVIC] Checkpoint recorded for chain={chain_id} "
                f"hop={hop_index} agent={agent_id} (origin — no comparison)"
            )
            return None

        # Compare against the ORIGINATING intent (hop 0) — NOT just the
        # previous hop. This catches compound drift across the full chain.
        origin = self._chains[chain_id][0]
        similarity = self._cosine_similarity(origin.vector, cp.vector)

        drift_detected = similarity < self.semantic_drift_threshold

        result = CVICResult(
            cosine_similarity=round(similarity, 6),
            drift_detected=drift_detected,
            threshold_used=self.semantic_drift_threshold,
            hop_a_agent=origin.agent_id,
            hop_b_agent=agent_id,
            quarantine_recommended=drift_detected,
            hitl_required=drift_detected,  # HITL is ALWAYS required on drift
            hitl_reason=(
                f"Semantic drift detected: cosine similarity {similarity:.4f} "
                f"< threshold {self.semantic_drift_threshold}. "
                f"Origin agent '{origin.agent_id}' → current agent '{agent_id}' "
                f"(hop {hop_index}). Context contamination risk — "
                f"human review is MANDATORY."
                if drift_detected
                else ""
            ),
        )

        if drift_detected:
            logger.warning(
                f"[CVIC] SEMANTIC DRIFT DETECTED chain={chain_id} "
                f"hop={hop_index} similarity={similarity:.4f} "
                f"threshold={self.semantic_drift_threshold} "
                f"— QUARANTINE + HITL ESCALATION"
            )
            self._trigger_quarantine(chain_id, result)
        else:
            logger.info(
                f"[CVIC] Checkpoint OK chain={chain_id} hop={hop_index} "
                f"similarity={similarity:.4f}"
            )

        return result

    def evaluate_pair(
        self,
        context_a: str,
        context_b: str,
        agent_a: str = "hop_0",
        agent_b: str = "hop_n",
    ) -> CVICResult:
        """
        Standalone pairwise evaluation (e.g., called from the cognitive auditor).

        Args:
            context_a: The originating intent text.
            context_b: The downstream context text.

        Returns:
            CVICResult with cosine similarity and drift assessment.
        """
        vec_a = self._text_to_vector(context_a)
        vec_b = self._text_to_vector(context_b)
        similarity = self._cosine_similarity(vec_a, vec_b)
        drift_detected = similarity < self.semantic_drift_threshold

        return CVICResult(
            cosine_similarity=round(similarity, 6),
            drift_detected=drift_detected,
            threshold_used=self.semantic_drift_threshold,
            hop_a_agent=agent_a,
            hop_b_agent=agent_b,
            quarantine_recommended=drift_detected,
            hitl_required=drift_detected,
            hitl_reason=(
                f"Semantic drift detected: cosine similarity {similarity:.4f} "
                f"< threshold {self.semantic_drift_threshold}. "
                f"Human review is MANDATORY."
                if drift_detected
                else ""
            ),
        )

    def get_chain(self, chain_id: str) -> List[CVICCheckpoint]:
        """Return all checkpoints for a given chain."""
        return self._chains.get(chain_id, [])

    def clear_chain(self, chain_id: str) -> None:
        """Remove a completed chain from memory."""
        self._chains.pop(chain_id, None)
        self._chain_created.pop(chain_id, None)

    def _gc(self) -> None:
        """Evict chains older than CHAIN_TTL_SECONDS and enforce MAX_CHAINS."""
        import time as _time
        now = _time.time()

        # TTL eviction
        expired = [
            cid for cid, created in self._chain_created.items()
            if now - created > self.CHAIN_TTL_SECONDS
        ]
        for cid in expired:
            self._chains.pop(cid, None)
            self._chain_created.pop(cid, None)

        # Hard cap: if we exceed MAX_CHAINS, evict oldest
        if len(self._chains) > self.MAX_CHAINS:
            sorted_chains = sorted(
                self._chain_created.items(), key=lambda x: x[1]
            )
            excess = len(self._chains) - self.MAX_CHAINS
            for cid, _ in sorted_chains[:excess]:
                self._chains.pop(cid, None)
                self._chain_created.pop(cid, None)

        if expired:
            logger.info(
                f"[CVIC] GC: evicted {len(expired)} expired chains, "
                f"{len(self._chains)} remaining"
            )

    # ─── Mathematical Core ────────────────────────────────────────────────

    @staticmethod
    def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
        """
        Calculate cosine similarity: S_C(A,B) = (A · B) / (||A|| * ||B||)

        Patent §0023: "The system calculates semantic drift across the
        agent chain using cosine similarity."
        """
        if not vec_a or not vec_b:
            return 0.0

        # Build a unified dimension space
        all_keys = set(range(max(len(vec_a), len(vec_b))))

        # Pad shorter vector with zeros
        a = vec_a + [0.0] * max(0, len(vec_b) - len(vec_a))
        b = vec_b + [0.0] * max(0, len(vec_a) - len(vec_b))

        # Dot product: A · B
        dot_product = sum(a_i * b_i for a_i, b_i in zip(a, b))

        # Magnitudes: ||A|| and ||B||
        magnitude_a = math.sqrt(sum(a_i ** 2 for a_i in a))
        magnitude_b = math.sqrt(sum(b_i ** 2 for b_i in b))

        if magnitude_a == 0 or magnitude_b == 0:
            return 0.0

        return dot_product / (magnitude_a * magnitude_b)

    @staticmethod
    def _text_to_vector(text: str) -> List[float]:
        """
        Convert text to a term-frequency vector for cosine similarity.

        Uses a lightweight bag-of-words approach (no external ML dependencies)
        to keep the service fast and dependency-light for the demo.
        """
        # Normalize: lowercase, strip punctuation, split into tokens
        tokens = re.findall(r'\b[a-z0-9]+\b', text.lower())

        if not tokens:
            return [0.0]

        # Build term frequency counter
        counts = Counter(tokens)

        # Sort terms for deterministic vector ordering
        sorted_terms = sorted(counts.keys())

        # Return normalized term-frequency vector
        total = len(tokens)
        return [counts[term] / total for term in sorted_terms]

    @staticmethod
    def _hash_vector(vector: List[float]) -> str:
        """Generate a SHA-256 hash of the dimensional vector."""
        data = ",".join(f"{v:.6f}" for v in vector)
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    # ─── HITL & Quarantine ────────────────────────────────────────────────

    def _trigger_quarantine(self, chain_id: str, result: CVICResult) -> None:
        """
        Notify the escrow controller to quarantine the packet and
        ALWAYS escalate to HITL.
        """
        try:
            payload = {
                "chain_id": chain_id,
                "cosine_similarity": result.cosine_similarity,
                "threshold": result.threshold_used,
                "hop_a_agent": result.hop_a_agent,
                "hop_b_agent": result.hop_b_agent,
                "action": "QUARANTINE",
                "hitl_required": True,
                "hitl_reason": result.hitl_reason,
            }
            response = requests.post(
                f"{ESCROW_CONTROLLER_URL}/api/v1/escrow/quarantine",
                json=payload,
                timeout=5,
            )
            if response.status_code == 200:
                logger.info(f"[CVIC] Quarantine command sent for chain={chain_id}")
            else:
                logger.error(
                    f"[CVIC] Quarantine command failed: {response.status_code}"
                )
        except Exception as e:
            logger.error(f"[CVIC] Failed to send quarantine command: {e}")
