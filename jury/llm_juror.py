"""
AOCS LLM Juror — Multi-Tenant Multi-Model Inference for Cognitive Auditing

Replaces simulated jury votes with real LLM calls to GPT-4, Claude, and Gemini.
Keys are loaded per-tenant from governance config (Supabase), with fallback
to environment variables, then to rule-based deterministic voting.

All API keys come from:
    1. tenant_governance_config (Supabase) via get_tenant_governance_config(tenant_id)
    2. Environment variables as fallback: OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY
    3. Rule-based deterministic fallback if no key is available
"""

import os
import json
import asyncio
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

# ============================================================================
# PROMPT TEMPLATES
# ============================================================================

JURY_SYSTEM_PROMPT = """You are an AI governance juror in the AOCS (Autonomous Operational Control System).
You evaluate agent tool-call requests against security policies.

Your role: {role}

You must respond with a JSON object:
{{
    "vote": "APPROVE" | "REJECT" | "ABSTAIN",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation"
}}

Rules:
- APPROVE: Action is safe, within policy, and beneficial
- REJECT: Action violates policy, is risky, or harmful
- ABSTAIN: Insufficient information to decide"""

JURY_USER_PROMPT = """Evaluate this agent tool-call:

Agent ID: {agent_id}
Tool: {tool_id}
Intent: {intent_action} on {intent_resource}
Operation: {operation_type}
Risk Category: {risk_category}
Confidence: {confidence}

Policy Violations Found: {violation_count}
Violations: {violations}

Entities: {entities}

Respond with JSON only."""

INTENT_EXTRACTION_PROMPT = """Extract the semantic intent from this AI agent request payload.

Payload:
{payload}

Tool ID: {tool_id}

Respond with JSON:
{{
    "primary_action": "verb_noun describing action",
    "target_resource": "what resource is being acted on",
    "operation_type": "CREATE|READ|UPDATE|DELETE|EXECUTE",
    "risk_category": "FINANCIAL|DATA|INFRASTRUCTURE|COMMUNICATION|UNKNOWN",
    "confidence": 0.0-1.0,
    "reasoning": "why you classified it this way"
}}"""


# ============================================================================
# JUROR VOTE RESULT
# ============================================================================

@dataclass
class LLMJurorVote:
    """Vote from an LLM juror."""
    juror_id: str
    model_name: str
    vote: str  # APPROVE, REJECT, ABSTAIN
    confidence: float
    reasoning: str
    latency_ms: float
    is_fallback: bool  # True if rule-based fallback was used


# ============================================================================
# LLM JUROR CLIENT
# ============================================================================

class LLMJurorClient:
    """Calls a real LLM endpoint to get a governance verdict."""

    def __init__(
        self,
        juror_id: str,
        role: str,
        model_name: str,
        api_key: str,
        api_key_env: str,
        endpoint: str,
        model_field: str = "model",
        timeout_seconds: float = 10.0,
        weight_boost: float = 1.0,
    ):
        self.juror_id = juror_id
        self.role = role
        self.model_name = model_name
        # Multi-tenant key priority: explicit key → env var → empty
        self.api_key = api_key or os.environ.get(api_key_env, "")
        self.endpoint = endpoint
        self.model_field = model_field
        self.timeout = timeout_seconds
        self.weight_boost = weight_boost  # 1.5x for default_juror_priority
        self._headers = {}

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def _build_headers(self) -> Dict[str, str]:
        """Build API-specific auth headers."""
        raise NotImplementedError

    def _build_body(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """Build API-specific request body."""
        raise NotImplementedError

    def _parse_response(self, response_json: Dict) -> str:
        """Extract content text from API-specific response shape."""
        raise NotImplementedError

    async def evaluate(
        self,
        agent_id: str,
        tool_id: str,
        intent: Any,
        violations: List,
    ) -> LLMJurorVote:
        """Call the LLM and return a governance verdict."""
        import time
        start = time.monotonic()

        if not self.available:
            return self._fallback_vote(intent, violations, "API key not configured")

        system_prompt = JURY_SYSTEM_PROMPT.format(role=self.role)
        user_prompt = JURY_USER_PROMPT.format(
            agent_id=agent_id,
            tool_id=tool_id,
            intent_action=intent.primary_action,
            intent_resource=intent.target_resource,
            operation_type=intent.operation_type,
            risk_category=intent.risk_category,
            confidence=intent.confidence,
            violation_count=len(violations),
            violations=json.dumps([v.rule_name for v in violations]) if violations else "None",
            entities=json.dumps(intent.extracted_entities),
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    self.endpoint,
                    headers=self._build_headers(),
                    json=self._build_body(system_prompt, user_prompt),
                )
                resp.raise_for_status()
                content = self._parse_response(resp.json())

                # Parse the LLM's JSON response
                result = json.loads(content)
                elapsed = (time.monotonic() - start) * 1000

                return LLMJurorVote(
                    juror_id=self.juror_id,
                    model_name=self.model_name,
                    vote=result.get("vote", "ABSTAIN").upper(),
                    confidence=float(result.get("confidence", 0.5)),
                    reasoning=result.get("reasoning", "No reasoning provided"),
                    latency_ms=elapsed,
                    is_fallback=False,
                )

        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            logger.warning(f"LLM juror {self.juror_id} ({self.model_name}) failed: {e}")
            return self._fallback_vote(intent, violations, str(e))

    def _fallback_vote(self, intent: Any, violations: List, reason: str) -> LLMJurorVote:
        """Rule-based deterministic fallback when LLM is unavailable."""
        if violations:
            vote = "REJECT"
            confidence = 0.95
            reasoning = f"[FALLBACK:{reason}] Policy violations: {[v.rule_name for v in violations]}"
        elif intent.risk_category in ("FINANCIAL", "INFRASTRUCTURE"):
            vote = "ABSTAIN"
            confidence = 0.6
            reasoning = f"[FALLBACK:{reason}] High-risk category requires LLM review"
        else:
            vote = "APPROVE"
            confidence = 0.8
            reasoning = f"[FALLBACK:{reason}] No violations, standard risk"

        return LLMJurorVote(
            juror_id=self.juror_id,
            model_name=f"{self.model_name}:fallback",
            vote=vote,
            confidence=confidence,
            reasoning=reasoning,
            latency_ms=0.0,
            is_fallback=True,
        )


# ============================================================================
# PROVIDER-SPECIFIC IMPLEMENTATIONS
# ============================================================================

class OpenAIJuror(LLMJurorClient):
    """GPT-4o-mini via OpenAI Chat Completions API."""

    def __init__(self, api_key: str = "", weight_boost: float = 1.0):
        super().__init__(
            juror_id="juror-compliance",
            role="Compliance Expert — focus on regulatory and policy adherence",
            model_name="gpt-4o-mini",
            api_key=api_key,
            api_key_env="OPENAI_API_KEY",
            endpoint="https://api.openai.com/v1/chat/completions",
            weight_boost=weight_boost,
        )

    def _build_headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _build_body(self, system_prompt, user_prompt):
        return {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
            "max_tokens": 256,
        }

    def _parse_response(self, resp):
        return resp["choices"][0]["message"]["content"]


class AnthropicJuror(LLMJurorClient):
    """Claude via Anthropic Messages API."""

    def __init__(self, api_key: str = "", weight_boost: float = 1.0):
        super().__init__(
            juror_id="juror-security",
            role="Security Analyst — focus on attack vectors, data exfiltration, privilege escalation",
            model_name="claude-3-5-haiku-latest",
            api_key=api_key,
            api_key_env="ANTHROPIC_API_KEY",
            endpoint="https://api.anthropic.com/v1/messages",
            weight_boost=weight_boost,
        )

    def _build_headers(self):
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    def _build_body(self, system_prompt, user_prompt):
        return {
            "model": self.model_name,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "max_tokens": 256,
            "temperature": 0.1,
        }

    def _parse_response(self, resp):
        return resp["content"][0]["text"]


class GeminiJuror(LLMJurorClient):
    """Gemini via Google AI API."""

    def __init__(self, api_key: str = "", weight_boost: float = 1.0):
        super().__init__(
            juror_id="juror-business",
            role="Business Logic Validator — focus on business impact, cost, and operational risk",
            model_name="gemini-2.0-flash",
            api_key=api_key,
            api_key_env="GEMINI_API_KEY",
            endpoint="",  # Set dynamically with API key
            weight_boost=weight_boost,
        )

    @property
    def _gemini_url(self):
        return f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"

    def _build_headers(self):
        return {"Content-Type": "application/json"}

    def _build_body(self, system_prompt, user_prompt):
        return {
            "contents": [
                {"parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}
            ],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 256,
                "responseMimeType": "application/json",
            },
        }

    def _parse_response(self, resp):
        return resp["candidates"][0]["content"]["parts"][0]["text"]

    async def evaluate(self, agent_id, tool_id, intent, violations):
        """Override to use dynamic URL with API key."""
        self.endpoint = self._gemini_url
        return await super().evaluate(agent_id, tool_id, intent, violations)


# ============================================================================
# JURY COORDINATOR
# ============================================================================

class MultiModelJury:
    """Coordinates N LLM jurors via JuryPoolManager for multi-agent consensus voting.
    
    Loads model registry and API keys per-tenant from governance config (Supabase).
    Supports dynamic pool sizing based on risk level, pool rotation for anti-collusion,
    and optional VRF-based juror selection for high-security tenants.
    Falls back to env vars, then to rule-based deterministic voting.
    """

    def __init__(self, tenant_id: str = ""):
        self.tenant_id = tenant_id
        
        # Initialize pool manager for dynamic juror selection
        from jury_pool_manager import JuryPoolManager
        self.pool_manager = JuryPoolManager(tenant_id)
        
        # Maintain backward-compatible jurors property (default pool)
        self._default_jurors = self.pool_manager.select_jurors(risk_level="MEDIUM")
        
        available = sum(1 for j in self._default_jurors if j.available)
        logger.info(
            f"MultiModelJury initialized: {available}/{len(self._default_jurors)} "
            f"LLM jurors available, tenant={tenant_id or 'platform'}, "
            f"pool_size={len(self._default_jurors)}, "
            f"vrf={self.pool_manager.pool_config.vrf_enabled}"
        )
    
    @property
    def jurors(self) -> List[LLMJurorClient]:
        """Backward-compatible access to current default juror pool."""
        return self._default_jurors
    
    @property
    def pool_status(self) -> Dict[str, Any]:
        """Current pool state for API/UI display."""
        return self.pool_manager.get_pool_status()
    
    @staticmethod
    def _load_tenant_config(tenant_id: str) -> Dict[str, Any]:
        """Load tenant governance config. Returns defaults if tenant_id is empty."""
        if not tenant_id:
            return {}
        try:
            from config.governance_config import get_tenant_governance_config
            return get_tenant_governance_config(tenant_id)
        except Exception as e:
            logger.warning(f"Failed to load tenant config for {tenant_id}: {e}")
            return {}

    async def get_votes(
        self,
        agent_id: str,
        tool_id: str,
        intent: Any,
        violations: List,
        risk_level: str = "MEDIUM",
    ) -> List[LLMJurorVote]:
        """Get votes from N jurors in parallel, pool sized by risk level.
        
        Args:
            agent_id: The agent being evaluated
            tool_id: The tool/action being requested
            intent: Extracted semantic intent
            violations: List of policy violations found
            risk_level: Risk level for dynamic pool sizing (LOW/MEDIUM/HIGH/CRITICAL)
        """
        # Select jurors dynamically based on risk level
        jurors = self.pool_manager.select_jurors(risk_level)
        
        tasks = [
            juror.evaluate(agent_id, tool_id, intent, violations)
            for juror in jurors
        ]
        votes = await asyncio.gather(*tasks, return_exceptions=True)

        results = []
        for i, vote in enumerate(votes):
            if isinstance(vote, Exception):
                logger.warning(f"Juror {jurors[i].juror_id} raised exception: {vote}")
                # Create fallback vote for exception cases
                results.append(LLMJurorVote(
                    juror_id=jurors[i].juror_id,
                    model_name=f"{jurors[i].model_name}:error",
                    vote="ABSTAIN",
                    confidence=0.0,
                    reasoning=f"Exception: {vote}",
                    latency_ms=0.0,
                    is_fallback=True,
                ))
            else:
                results.append(vote)

        # Log the jury results
        for v in results:
            logger.info(
                f"Jury vote: {v.juror_id} ({v.model_name}) → {v.vote} "
                f"(confidence={v.confidence:.2f}, fallback={v.is_fallback}, "
                f"latency={v.latency_ms:.0f}ms)"
            )

        return results


# ============================================================================
# LLM-BASED INTENT EXTRACTION (optional)
# ============================================================================

async def extract_intent_via_llm(
    payload: Dict[str, Any],
    tool_id: str,
    tenant_id: str = "",
) -> Optional[Dict[str, Any]]:
    """
    Use an LLM to extract semantic intent from a raw payload.
    Controlled by tenant config 'llm_intent_extraction' or env OCX_INTENT_LLM.
    Returns None if LLM is unavailable (falls back to dictionary-based).
    """
    # Check tenant config first, then env var
    enabled = False
    api_key = ""
    if tenant_id:
        try:
            from config.governance_config import get_tenant_governance_config
            cfg = get_tenant_governance_config(tenant_id)
            enabled = cfg.get("llm_intent_extraction", False)
            api_key = cfg.get("openai_api_key", "")
        except Exception:
            pass
    
    if not enabled:
        enabled = os.environ.get("OCX_INTENT_LLM", "false").lower() == "true"
    if not enabled:
        return None

    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return None

    prompt = INTENT_EXTRACTION_PROMPT.format(
        payload=json.dumps(payload, default=str)[:2000],
        tool_id=tool_id,
    )

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.0,
                    "max_tokens": 256,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return json.loads(content)
    except Exception as e:
        logger.warning(f"LLM intent extraction failed (using dictionary fallback): {e}")
        return None
