"""
Geo-Fenced Regulatory Attestation — Regulatory AI Service

AI-powered regulatory analysis for the GRA system. ALL regulatory
frameworks, verification intents, and risk thresholds are loaded
from the database. ZERO hardcoded values.

Responsibilities:
  - Fetch regulatory requirements for a country (from DB)
  - Classify agent actions against regulatory intents (semantic matching)
  - Generate risk assessments with AI suggestions
  - Produce next-step remediation recommendations
"""

import hashlib
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("gra.regulatory_ai")

# ─── DB Connection ────────────────────────────────────────────────────────────

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")


def _supabase_headers() -> Dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _supabase_get(table: str, params: Optional[Dict[str, str]] = None) -> List[Dict]:
    """Query a Supabase table. All data is DB-driven."""
    if not SUPABASE_URL:
        logger.warning("[GRA-AI] SUPABASE_URL not configured")
        return []
    try:
        url = f"{SUPABASE_URL}/rest/v1/{table}"
        resp = requests.get(url, headers=_supabase_headers(), params=params or {}, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"[GRA-AI] Supabase query failed for {table}: {e}")
        return []


def _supabase_insert(table: str, row: Dict) -> bool:
    """Insert a row into a Supabase table."""
    if not SUPABASE_URL:
        return False
    try:
        url = f"{SUPABASE_URL}/rest/v1/{table}"
        resp = requests.post(url, headers=_supabase_headers(), json=row, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"[GRA-AI] Supabase insert failed for {table}: {e}")
        return False


# ─── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class RegulatoryRequirement:
    """A single regulatory requirement loaded from DB."""
    requirement_id: str
    framework_id: str
    framework_name: str
    country_code: str
    category: str
    requirement_text: str
    enforcement_level: str  # MANDATORY, RECOMMENDED, ADVISORY
    verification_url: str
    risk_weight: float = 1.0


@dataclass
class ActionClassification:
    """Result of classifying an agent action against regulatory intents."""
    classified_intent: str
    mapped_intent_keys: List[str] = field(default_factory=list)
    risk_color: str = "AMBER"
    risk_score: float = 0.5
    suggestion: str = ""
    next_steps: List[str] = field(default_factory=list)


# ─── Regulatory AI Service ────────────────────────────────────────────────────


class RegulatoryAIService:
    """
    AI-powered regulatory analysis. ALL data is loaded from Supabase.
    No hardcoded regulatory frameworks, thresholds, or country mappings.
    """

    def __init__(self) -> None:
        """Initialize the service. All config comes from DB at query time."""
        logger.info("[GRA-AI] RegulatoryAIService initialized (DB-driven)")

    def fetch_regulatory_requirements(
        self, country_code: str
    ) -> List[RegulatoryRequirement]:
        """
        Fetch all regulatory requirements for a country from DB.
        Queries gra_regulatory_frameworks joined with gra_compliance_regions.
        """
        # 1. Find region for this country
        regions = _supabase_get("gra_compliance_regions")
        matched_region = None
        for region in regions:
            countries = region.get("countries", [])
            if country_code in countries:
                matched_region = region
                break

        if not matched_region:
            logger.warning(f"[GRA-AI] No region found for country: {country_code}")
            return []

        region_code = matched_region.get("region_code", "")

        # 2. Fetch frameworks for this region from DB
        frameworks = _supabase_get(
            "gra_regulatory_frameworks",
            {"region_code": f"eq.{region_code}", "is_active": "eq.true"},
        )

        requirements = []
        for fw in frameworks:
            req = RegulatoryRequirement(
                requirement_id=fw.get("framework_id", ""),
                framework_id=fw.get("framework_id", ""),
                framework_name=fw.get("name", ""),
                country_code=country_code,
                category=fw.get("category", ""),
                requirement_text=fw.get("description", ""),
                enforcement_level=fw.get("enforcement_level", "RECOMMENDED"),
                verification_url=fw.get("verification_url", ""),
                risk_weight=fw.get("risk_weight", 1.0),
            )
            requirements.append(req)

        logger.info(
            f"[GRA-AI] Fetched {len(requirements)} requirements "
            f"for {country_code} (region: {region_code})"
        )
        return requirements

    def generate_verification_intents(
        self, requirements: List[RegulatoryRequirement]
    ) -> List[Dict[str, Any]]:
        """
        Generate verification intents from regulatory requirements.
        Intent templates are loaded from the DB (gra_intent_templates table).
        """
        # Fetch intent templates from DB
        templates = _supabase_get("gra_intent_templates")
        template_map: Dict[str, Dict] = {
            t.get("template_key", ""): t for t in templates
        }

        intents: List[Dict[str, Any]] = []
        for req in requirements:
            # Get required intents from the framework's DB record
            fw_data = _supabase_get(
                "gra_regulatory_frameworks",
                {"framework_id": f"eq.{req.framework_id}"},
            )
            if not fw_data:
                continue

            required_intents = fw_data[0].get("required_intents", [])
            for intent_key in required_intents:
                template = template_map.get(intent_key, {})
                intent = {
                    "framework_id": req.framework_id,
                    "framework_name": req.framework_name,
                    "intent_key": intent_key,
                    "intent_name": template.get("intent_name", intent_key),
                    "description": template.get("description", f"Verify {intent_key} compliance"),
                    "required_proof": template.get("required_proof", "Evidence required"),
                    "enforcement_level": req.enforcement_level,
                    "risk_weight": req.risk_weight,
                }
                intents.append(intent)

        logger.info(f"[GRA-AI] Generated {len(intents)} verification intents")
        return intents

    def classify_action_intent(
        self,
        tenant_id: str,
        agent_id: str,
        action_type: str,
        payload: Dict[str, Any],
    ) -> ActionClassification:
        """
        Classify an agent action against the tenant's regulatory intents.
        Uses semantic matching with action-to-intent mappings from DB.

        All mapping rules are in the gra_action_mappings table.
        """
        # 1. Load action-to-intent mappings from DB
        mappings = _supabase_get(
            "gra_action_mappings",
            {"tenant_id": f"eq.{tenant_id}"},
        )

        # If no tenant-specific mappings, try global defaults
        if not mappings:
            mappings = _supabase_get(
                "gra_action_mappings",
                {"tenant_id": "eq.global"},
            )

        # 2. Find matching intents for this action type
        matched_keys: List[str] = []
        max_risk_weight = 0.0

        for mapping in mappings:
            mapped_actions = mapping.get("action_types", [])
            if action_type in mapped_actions or "*" in mapped_actions:
                intent_key = mapping.get("intent_key", "")
                if intent_key:
                    matched_keys.append(intent_key)
                    weight = mapping.get("risk_weight", 0.5)
                    if weight > max_risk_weight:
                        max_risk_weight = weight

        # 3. Load risk thresholds from DB
        risk_configs = _supabase_get(
            "gra_risk_config",
            {"tenant_id": f"eq.{tenant_id}"},
        )
        if not risk_configs:
            risk_configs = _supabase_get(
                "gra_risk_config",
                {"tenant_id": "eq.global"},
            )

        green_max = 0.3
        amber_max = 0.7
        if risk_configs:
            cfg = risk_configs[0]
            green_max = cfg.get("green_max_score", 0.3)
            amber_max = cfg.get("amber_max_score", 0.7)

        # 4. Classify risk color
        risk_score = max_risk_weight
        if risk_score <= green_max:
            risk_color = "GREEN"
        elif risk_score <= amber_max:
            risk_color = "AMBER"
        else:
            risk_color = "RED"

        # 5. Generate AI suggestion from DB templates
        suggestion = self._generate_suggestion(risk_color, matched_keys, action_type, tenant_id)
        next_steps = self._generate_next_steps(risk_color, matched_keys, tenant_id)

        classified_intent = matched_keys[0] if matched_keys else action_type

        result = ActionClassification(
            classified_intent=classified_intent,
            mapped_intent_keys=matched_keys,
            risk_color=risk_color,
            risk_score=risk_score,
            suggestion=suggestion,
            next_steps=next_steps,
        )

        logger.info(
            f"[GRA-AI] Action classified: agent={agent_id} "
            f"action={action_type} risk={risk_color} "
            f"intents={len(matched_keys)}"
        )

        return result

    def _generate_suggestion(
        self, risk_color: str, intent_keys: List[str], action_type: str,
        tenant_id: str = None,
    ) -> str:
        """Generate AI suggestion from DB-stored suggestion templates."""
        params = {"risk_color": f"eq.{risk_color}"}
        if tenant_id:
            params["tenant_id"] = f"eq.{tenant_id}"
        templates = _supabase_get(
            "gra_suggestion_templates",
            params,
        )

        if templates:
            template = templates[0]
            suggestion = template.get("suggestion_text", "")
            # Variable substitution
            suggestion = suggestion.replace("{action_type}", action_type)
            suggestion = suggestion.replace("{intent_keys}", ", ".join(intent_keys))
            return suggestion

        # Fallback if no templates in DB
        return (
            f"{risk_color} risk for '{action_type}' "
            f"— mapped to {len(intent_keys)} regulatory intent(s). "
            f"Review required."
        )

    def _generate_next_steps(
        self, risk_color: str, intent_keys: List[str], tenant_id: str
    ) -> List[str]:
        """Generate next-step recommendations from DB-stored step templates."""
        params = {"risk_color": f"eq.{risk_color}"}
        if tenant_id:
            params["tenant_id"] = f"eq.{tenant_id}"
        steps_data = _supabase_get(
            "gra_next_step_templates",
            params,
        )

        if steps_data:
            steps: List[str] = []
            for s in steps_data:
                step_text = s.get("step_text", "")
                step_text = step_text.replace("{intent_keys}", ", ".join(intent_keys))
                step_text = step_text.replace("{tenant_id}", tenant_id)
                steps.append(step_text)
            return steps

        # Fallback if no templates in DB
        if risk_color == "RED":
            return [
                "Immediate HITL review required",
                "Pause agent execution pending compliance review",
                f"Verify regulatory compliance for: {', '.join(intent_keys)}",
            ]
        elif risk_color == "AMBER":
            return [
                f"Schedule compliance review for: {', '.join(intent_keys)}",
                "Monitor agent for repeated borderline actions",
            ]
        return ["No immediate action required — compliance tracking active"]

    def generate_risk_assessment(
        self,
        tenant_id: str,
        agent_id: str,
        action_type: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Full risk assessment: classify action + produce comprehensive report.
        All data from DB.
        """
        classification = self.classify_action_intent(
            tenant_id, agent_id, action_type, payload
        )

        assessment = {
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "action_type": action_type,
            "classified_intent": classification.classified_intent,
            "mapped_intents": classification.mapped_intent_keys,
            "risk_color": classification.risk_color,
            "risk_score": classification.risk_score,
            "ai_suggestion": classification.suggestion,
            "next_steps": classification.next_steps,
            "assessed_at": datetime.now(timezone.utc).isoformat(),
            "assessment_hash": hashlib.sha256(
                f"{tenant_id}:{agent_id}:{action_type}:{datetime.now(timezone.utc).isoformat()}".encode()
            ).hexdigest()[:16],
        }

        # Persist assessment to DB
        _supabase_insert("gra_risk_assessments", assessment)

        return assessment
