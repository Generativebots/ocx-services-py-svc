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

# Governance config loader — tenant-specific overrides
try:
    from config.governance_config import get_tenant_governance_config
    _HAS_GOV_CONFIG = True
except ImportError:
    _HAS_GOV_CONFIG = False


class Jury:
    """Multi-model consensus jury for evaluating agent trustworthiness."""

    # Risk keywords for compliance scoring
    RISK_KEYWORDS = {
        "high": ["delete", "drop", "external", "transfer", "eject", "override", "bypass"],
        "medium": ["update", "modify", "send", "payment", "execute", "write"],
        "low": ["read", "list", "get", "query", "view", "check"],
    }

    def __init__(self, llm_client=None, tenant_id: str = None) -> None:
        self.model = os.getenv("JURY_MODEL", "default-consensus")
        self.llm_client = llm_client
        self.tenant_id = tenant_id

        # Load tenant-specific thresholds (fall back to defaults)
        if tenant_id and _HAS_GOV_CONFIG:
            cfg = get_tenant_governance_config(tenant_id)
            self.trust_threshold = cfg.get("jury_trust_threshold", 0.65)
            self.kill_switch_threshold = cfg.get("kill_switch_threshold", 0.30)
        else:
            self.trust_threshold = 0.65
            self.kill_switch_threshold = 0.30

        logger.info(
            "Jury initialized (model=%s, trust_threshold=%.2f, kill_switch=%.2f)",
            self.model, self.trust_threshold, self.kill_switch_threshold,
        )

    def _compute_compliance_score(self, action: str, rules_context: str) -> float:
        """Compute compliance score based on action risk and rules context."""
        action_lower = action.lower()
        # Check risk level of action
        for keyword in self.RISK_KEYWORDS["high"]:
            if keyword in action_lower:
                return 0.40
        for keyword in self.RISK_KEYWORDS["medium"]:
            if keyword in action_lower:
                return 0.65
        # Check if action matches any rule violation keywords
        if rules_context:
            rules_lower = rules_context.lower()
            if "block" in rules_lower and action_lower in rules_lower:
                return 0.30
        return 0.85

    def _compute_factuality_score(self, payload: Dict[str, Any]) -> float:
        """Compute factuality score based on payload completeness."""
        context = payload.get("context", {})
        # Score based on how much context is provided
        if not context:
            return 0.50
        field_count = len(context)
        if field_count >= 5:
            return 0.90
        elif field_count >= 3:
            return 0.75
        return 0.60

    def _compute_strategic_score(
        self, agent_metadata: Dict[str, Any], action: str
    ) -> float:
        """Compute strategic alignment based on agent tier and action."""
        tier = agent_metadata.get("tier", "Standard")
        if tier == "Critical" and "read" in action.lower():
            return 0.90
        if tier == "Standard":
            return 0.70
        return 0.75

    def score(
        self,
        payload: Dict[str, Any],
        agent_metadata: Dict[str, Any],
        rules_context: str,
    ) -> Dict[str, Any]:
        """
        Run jury scoring on a proposed action.
        Returns a dict with trust_score, breakdown, reasoning, and status.

        Scoring is computed from payload, agent metadata, and rules context.
        Falls back to deterministic defaults only in test mode
        (JURY_MODEL=default-consensus).
        """
        agent_id = agent_metadata.get("agent_id", "unknown")
        tenant_id = agent_metadata.get("tenant_id", "unknown")
        action = payload.get("proposed_action", "")

        if self.model == "default-consensus":
            # Test/fallback mode: compute from payload content
            compliance_score = self._compute_compliance_score(action, rules_context)
            factuality_score = self._compute_factuality_score(payload)
            strategic_score = self._compute_strategic_score(agent_metadata, action)
        elif self.llm_client:
            # Production mode: call LLM panel
            try:
                llm_result = self.llm_client.evaluate(
                    payload=payload,
                    agent_metadata=agent_metadata,
                    rules_context=rules_context,
                )
                compliance_score = llm_result.get("compliance", 0.5)
                factuality_score = llm_result.get("factuality", 0.5)
                strategic_score = llm_result.get("strategic_alignment", 0.5)
            except Exception as e:
                logger.error(
                    "LLM jury evaluation failed for agent=%s tenant=%s: %s",
                    agent_id, tenant_id, e,
                )
                # Degrade gracefully: compute from payload
                compliance_score = self._compute_compliance_score(action, rules_context)
                factuality_score = self._compute_factuality_score(payload)
                strategic_score = self._compute_strategic_score(agent_metadata, action)
        else:
            # No LLM client: compute from payload content
            compliance_score = self._compute_compliance_score(action, rules_context)
            factuality_score = self._compute_factuality_score(payload)
            strategic_score = self._compute_strategic_score(agent_metadata, action)

        # Weighted Trust Vector (40% Compliance, 40% Factuality, 20% Strategic)
        trust_score = (
            0.4 * compliance_score
            + 0.4 * factuality_score
            + 0.2 * strategic_score
        )

        breakdown = {
            "compliance": round(compliance_score, 4),
            "factuality": round(factuality_score, 4),
            "strategic_alignment": round(strategic_score, 4),
        }

        # Resolve threshold — prefer tenant-specific config loaded at init,
        # but if tenant_id wasn't known at init, load now.
        threshold = self.trust_threshold
        if tenant_id and tenant_id != "unknown" and _HAS_GOV_CONFIG and not self.tenant_id:
            cfg = get_tenant_governance_config(tenant_id)
            threshold = cfg.get("jury_trust_threshold", 0.65)

        status = "APPROVED" if trust_score >= threshold else "BLOCKED"

        reasoning = (
            f"Agent {agent_id} (tenant={tenant_id}) scored {trust_score:.2f} "
            f"(threshold={threshold:.2f}) for action '{action}'"
        )

        logger.info(
            "Jury verdict: agent=%s tenant=%s score=%.4f threshold=%.2f status=%s",
            agent_id, tenant_id, trust_score, threshold, status,
        )

        return {
            "trust_score": round(trust_score, 4),
            "breakdown": breakdown,
            "reasoning": reasoning,
            "status": status,
        }
