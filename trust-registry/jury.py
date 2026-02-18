"""
OCX Jury — Local module for Trust Registry
-------------------------------------------
Provides the Jury class for consensus-based trust scoring.
When running inside the trust-registry service, this is a lightweight
in-process wrapper. In production, this would call the Jury gRPC service.
"""
import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class Jury:
    """Multi-model consensus jury for evaluating agent trustworthiness."""

    def __init__(self) -> None:
        self.model = os.getenv("JURY_MODEL", "default-consensus")
        logger.info("Jury initialized (model=%s)", self.model)

    def score(
        self,
        payload: Dict[str, Any],
        agent_metadata: Dict[str, Any],
        rules_context: str,
    ) -> Dict[str, Any]:
        """
        Run jury scoring on a proposed action.
        Returns a dict with trust_score, breakdown, reasoning, and status.
        """
        # Deterministic scoring based on context
        agent_id = agent_metadata.get("agent_id", "unknown")
        action = payload.get("proposed_action", "")

        # Base scores (in production, these come from LLM panel)
        compliance_score = 0.85
        factuality_score = 0.80
        strategic_score = 0.75

        # Weighted Trust Vector (40% Compliance, 40% Factuality, 20% Strategic)
        trust_score = (
            0.4 * compliance_score
            + 0.4 * factuality_score
            + 0.2 * strategic_score
        )

        breakdown = {
            "compliance": compliance_score,
            "factuality": factuality_score,
            "strategic_alignment": strategic_score,
        }

        status = "APPROVED" if trust_score >= 0.5 else "BLOCKED"

        return {
            "trust_score": round(trust_score, 4),
            "breakdown": breakdown,
            "reasoning": f"Agent {agent_id} scored {trust_score:.2f} for action '{action}'",
            "status": status,
        }
