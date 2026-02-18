"""
OCX Governance Orchestrator — Trust Registry
---------------------------------------------
Central orchestration function that coordinates Jury scoring,
Ledger recording, and Kill-Switch evaluation.
"""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def ocx_governance_orchestrator(
    payload: Dict[str, Any],
    agent_metadata: Dict[str, Any],
    business_rules: str,
    components: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Orchestrate the governance evaluation pipeline.

    Args:
        payload: The proposed action and context
        agent_metadata: Agent ID, tenant ID, tier
        business_rules: Combined static + dynamic rules text
        components: Dict containing 'jury' and 'ledger' instances

    Returns:
        Dict with trust_score, status, auditor_breakdown, reasoning
    """
    jury = components.get("jury")
    ledger = components.get("ledger")

    agent_id = agent_metadata.get("agent_id", "unknown")
    action = payload.get("proposed_action", "")

    # Step 1: Jury Scoring
    jury_result = jury.score(
        payload=payload,
        agent_metadata=agent_metadata,
        rules_context=business_rules,
    )

    trust_score = jury_result["trust_score"]
    breakdown = jury_result["breakdown"]
    status = jury_result["status"]
    reasoning = jury_result["reasoning"]

    # Step 2: Kill-Switch Check (score below 0.3 = block)
    if trust_score < 0.3:
        status = "BLOCKED"
        reasoning += " | KILL-SWITCH TRIGGERED: Score below safety threshold."
        logger.warning(
            "🛑 Kill-switch triggered for agent %s (score=%.2f)",
            agent_id,
            trust_score,
        )

    # Step 3: Record to Ledger
    if ledger:
        ledger.record({
            "agent_id": agent_id,
            "action": action,
            "trust_score": trust_score,
            "status": status,
            "breakdown": breakdown,
        })

    logger.info(
        "Orchestrator result: agent=%s score=%.2f status=%s",
        agent_id,
        trust_score,
        status,
    )

    return {
        "trust_score": trust_score,
        "status": status,
        "auditor_breakdown": breakdown,
        "reasoning": reasoning,
    }
