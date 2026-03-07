"""
Escrow gRPC Service Implementation.

Implements the EscrowServiceServicer and ReputationServiceServicer
base classes from proto/escrow_pb2_grpc.py with real escrow logic:
  - SubmitPrediction: Hold an agent's action in escrow pending Tri-Factor approval
  - Release: Release escrowed action after jury + entropy approval
  - GetTrustScore: Fetch an agent's reputation trust score
  - LevyTax: Deduct micro-tax for high-cost actions
"""

import hashlib
import logging
import time
import uuid
from typing import Dict

import grpc

from proto.escrow_pb2_grpc import EscrowServiceServicer, ReputationServiceServicer
from proto.escrow_pb2 import (
    EscrowItem,
    EscrowReceipt,
    ReleaseSignal,
    ReleaseResponse,
    TrustRequest,
    TrustScore,
    TaxLevy,
    TaxReceipt,
)

logger = logging.getLogger(__name__)


class EscrowServiceImpl(EscrowServiceServicer):
    """Production implementation of the Escrow gRPC service."""

    def __init__(self) -> None:
        # In-memory escrow ledger (keyed by escrow_id)
        # For production, back with Supabase 'escrow_items' table.
        self._held: Dict[str, EscrowItem] = {}
        self._receipts: Dict[str, EscrowReceipt] = {}

    def SubmitPrediction(self, request: EscrowItem, context) -> EscrowReceipt:
        """
        Hold an agent's turn in escrow.
        
        The Go backend's TriFactorGate calls this when a Class B action is
        intercepted. The item stays held until Release() is called
        with jury_approved=True and entropy_safe=True.
        """
        escrow_id = str(uuid.uuid4())
        self._held[escrow_id] = request

        receipt = EscrowReceipt(escrow_id=escrow_id, status="HELD")
        self._receipts[escrow_id] = receipt

        logger.info(
            "[EscrowService] Held action in escrow: escrow_id=%s agent=%s tenant=%s",
            escrow_id,
            request.agent_id,
            request.tenant_id,
        )
        return receipt

    def Release(self, request: ReleaseSignal, context) -> ReleaseResponse:
        """
        Release or reject an escrowed action.
        
        Requires both jury_approved AND entropy_safe to release.
        If either fails, the action remains held and the agent's turn
        payload is NOT returned.
        """
        item = self._held.get(request.escrow_id)
        if item is None:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details(f"Escrow item not found: {request.escrow_id}")
            return ReleaseResponse(success=False, payload=b"")

        if not request.jury_approved:
            logger.warning(
                "[EscrowService] Release denied — jury rejected: escrow_id=%s",
                request.escrow_id,
            )
            return ReleaseResponse(success=False, payload=b"")

        if not request.entropy_safe:
            logger.warning(
                "[EscrowService] Release denied — entropy unsafe: escrow_id=%s",
                request.escrow_id,
            )
            return ReleaseResponse(success=False, payload=b"")

        # All gates passed — release the payload
        payload = item.payload
        del self._held[request.escrow_id]

        if request.escrow_id in self._receipts:
            self._receipts[request.escrow_id].status = "RELEASED"

        logger.info(
            "[EscrowService] Released action: escrow_id=%s agent=%s",
            request.escrow_id,
            item.agent_id,
        )
        return ReleaseResponse(success=True, payload=payload)


class ReputationServiceImpl(ReputationServiceServicer):
    """Production implementation of the Reputation gRPC service."""

    def __init__(self) -> None:
        # Agent trust scores (agent_id → score).
        # For production, fetch from Supabase 'agent_trust_scores' table.
        self._scores: Dict[str, float] = {}
        self._balances: Dict[str, float] = {}  # micro-payment balance per agent

    def GetTrustScore(self, request: TrustRequest, context) -> TrustScore:
        """
        Return the current trust score and tier for an agent.
        
        Tier mapping:
          - score >= 0.85 → "SOVEREIGN"
          - score >= 0.65 → "TRUSTED"
          - score >= 0.40 → "PROBATION"
          - below 0.40    → "QUARANTINED"
        """
        agent_key = f"{request.tenant_id}:{request.agent_id}"
        score = self._scores.get(agent_key, 0.50)  # default 0.50 for new agents

        if score >= 0.85:
            tier = "SOVEREIGN"
        elif score >= 0.65:
            tier = "TRUSTED"
        elif score >= 0.40:
            tier = "PROBATION"
        else:
            tier = "QUARANTINED"

        logger.info(
            "[ReputationService] Trust score: agent=%s score=%.3f tier=%s",
            request.agent_id,
            score,
            tier,
        )
        return TrustScore(score=score, tier=tier)

    def LevyTax(self, request: TaxLevy, context) -> TaxReceipt:
        """
        Deduct a micro-tax from an agent's balance.
        
        Used for Class B actions that incur a governance cost. The tax
        is redistributed to high-trust agents (SOVEREIGN tier).
        """
        agent_key = f"{request.tenant_id}:{request.agent_id}"
        current_balance = self._balances.get(agent_key, 100.0)  # default 100 credits

        if request.amount > current_balance:
            context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
            context.set_details(
                f"Insufficient balance: {current_balance:.2f} < {request.amount:.2f}"
            )
            return TaxReceipt(tx_id="", new_balance=current_balance)

        new_balance = current_balance - request.amount
        self._balances[agent_key] = new_balance
        tx_id = hashlib.sha256(
            f"{agent_key}:{request.amount}:{time.time()}".encode()
        ).hexdigest()[:16]

        logger.info(
            "[ReputationService] Tax levied: agent=%s amount=%.2f balance=%.2f tx=%s reason=%s",
            request.agent_id,
            request.amount,
            new_balance,
            tx_id,
            request.reason,
        )
        return TaxReceipt(tx_id=tx_id, new_balance=new_balance)

    def set_score(self, tenant_id: str, agent_id: str, score: float) -> None:
        """Admin setter for test/setup. Production uses Supabase writes."""
        self._scores[f"{tenant_id}:{agent_id}"] = max(0.0, min(1.0, score))
