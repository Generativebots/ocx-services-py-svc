"""
Ledger gRPC Service Implementation.

Implements LedgerServiceServicer from proto/ledger_pb2_grpc.py with
hash-chained immutable audit trail logic:
  - RecordEntry: Append a new ledger entry with hash-chain verification
  - StreamAuditLog: Stream all audit entries for a given agent

The Evidence Vault (Go) and this Ledger (Python) form the dual-layer
immutability system described in Patent Claim 6.
"""

import hashlib
import logging
import time
import uuid
from collections import defaultdict
from typing import Dict, List

import grpc

from proto.ledger_pb2_grpc import LedgerServiceServicer
from proto.ledger_pb2 import LedgerEntry, AuditFilter, LedgerResponse

logger = logging.getLogger(__name__)


class LedgerServiceImpl(LedgerServiceServicer):
    """Production implementation of the Ledger gRPC service.

    Maintains an in-memory hash-chained audit trail per agent.
    For production, back with Supabase 'governance_ledger' table.
    """

    def __init__(self) -> None:
        # agent_id → ordered list of (entry_id, LedgerEntry, block_hash)
        self._chains: Dict[str, List[dict]] = defaultdict(list)
        # last hash per agent for chain continuity
        self._last_hash: Dict[str, str] = {}

    def _compute_hash(self, entry: LedgerEntry, previous_hash: str) -> str:
        """Compute SHA-256 hash for the entry, chaining to previous hash."""
        payload = (
            f"{previous_hash}:"
            f"{entry.turn_id}:"
            f"{entry.agent_id}:"
            f"{entry.binary_hash}:"
            f"{entry.plan_id}:"
            f"{entry.status}:"
            f"{entry.intent_hash}:"
            f"{entry.actual_hash}"
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def RecordEntry(self, request: LedgerEntry, context) -> LedgerResponse:
        """
        Append a new entry to the hash-chained audit trail.

        Each entry is linked to the previous via SHA-256 hash chaining,
        creating a tamper-evident Merkle-lite structure. If someone
        modifies an older entry, all subsequent hashes become invalid.
        """
        entry_id = str(uuid.uuid4())
        agent_id = request.agent_id

        # Get or initialize chain
        previous_hash = self._last_hash.get(agent_id, "GENESIS")

        # Compute block hash
        block_hash = self._compute_hash(request, previous_hash)

        # Append to chain
        self._chains[agent_id].append({
            "entry_id": entry_id,
            "entry": request,
            "block_hash": block_hash,
            "previous_hash": previous_hash,
            "recorded_at": time.time(),
        })

        # Update last hash
        self._last_hash[agent_id] = block_hash

        logger.info(
            "[LedgerService] Recorded entry: id=%s agent=%s status=%d hash=%s…",
            entry_id,
            agent_id,
            request.status,
            block_hash[:12],
        )

        return LedgerResponse(acknowledged=True, entry_id=entry_id)

    def StreamAuditLog(self, request: AuditFilter, context):
        """
        Stream all audit entries for a given agent, oldest → newest.

        The Go backend's EvidenceVault calls this to verify chain
        integrity during periodic audits.
        """
        agent_id = request.agent_id
        chain = self._chains.get(agent_id, [])

        if not chain:
            logger.info("[LedgerService] No entries for agent: %s", agent_id)
            return

        logger.info(
            "[LedgerService] Streaming %d entries for agent: %s",
            len(chain),
            agent_id,
        )

        for record in chain:
            yield record["entry"]

    def verify_chain_integrity(self, agent_id: str) -> bool:
        """
        Verify the hash chain for an agent is intact.
        
        Returns True if all hashes verify correctly, False if any
        entry has been tampered with.
        """
        chain = self._chains.get(agent_id, [])
        if not chain:
            return True  # empty chain is valid

        expected_prev = "GENESIS"
        for record in chain:
            computed = self._compute_hash(record["entry"], expected_prev)
            if computed != record["block_hash"]:
                logger.error(
                    "[LedgerService] Chain integrity violation: agent=%s entry=%s",
                    agent_id,
                    record["entry_id"],
                )
                return False
            expected_prev = record["block_hash"]

        return True
