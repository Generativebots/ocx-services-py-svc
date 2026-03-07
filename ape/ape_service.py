"""
APE — Autonomous Policy Engine (Patent Claim 8)
Extracts machine-enforceable policies from SOP/document text.

Two extraction layers:
  1. Regex Pattern Matching (default) — microsecond latency, 6 built-in patterns
  2. LLM Semantic Extraction (tenant keys) — uses OpenAI/Anthropic/Gemini for
     deep document understanding and nuanced rule extraction

Called by Go backend via HTTP: POST /extract
"""

import re
import os
import json
import hashlib
import logging
import httpx
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict

logger = logging.getLogger("ape")


@dataclass
class ExtractedRule:
    """A single machine-enforceable rule extracted from SOP text."""
    rule_name: str
    description: str
    logic: Dict[str, Any]
    tier: str  # ENFORCE, ADVISE, LOG
    confidence: float
    source_sentence: str


@dataclass
class ExtractionResult:
    """Result of APE policy extraction from a document."""
    document_id: str
    rules: List[ExtractedRule] = field(default_factory=list)
    total_sentences: int = 0
    matched_sentences: int = 0
    extraction_method: str = "regex"  # "regex" or "llm"


# ============================================================================
# REGEX PATTERN EXTRACTION (Layer 1 — fast default)
# ============================================================================

POLICY_PATTERNS = [
    {
        "pattern": r"\b(must|shall|required|mandatory)\b.*\b(log|audit|record|track)\b",
        "action": "LOG",
        "tier": "ENFORCE",
        "description_template": "All {subject} must be logged/audited",
    },
    {
        "pattern": r"\b(must not|shall not|prohibited|forbidden)\b.*\b(access|read|write|modify|delete)\b",
        "action": "BLOCK",
        "tier": "ENFORCE",
        "description_template": "Prohibited action: {subject}",
    },
    {
        "pattern": r"\b(approval|review|sign-off|authorization)\b.*\b(required|needed|necessary)\b",
        "action": "ESCROW",
        "tier": "ENFORCE",
        "description_template": "Approval required: {subject}",
    },
    {
        "pattern": r"\b(sensitive|confidential|restricted|classified)\b.*\b(data|information|records|files)\b",
        "action": "ESCROW",
        "tier": "ENFORCE",
        "description_template": "Sensitive data handling: {subject}",
    },
    {
        "pattern": r"\b(exceeds?|above|over|more than)\b.*\b(\$[\d,]+|threshold|limit)\b",
        "action": "ESCROW",
        "tier": "ENFORCE",
        "description_template": "Threshold exceeded: {subject}",
    },
    {
        "pattern": r"\b(daily|weekly|monthly)\b.*\b(report|review|check|scan)\b",
        "action": "LOG",
        "tier": "ADVISE",
        "description_template": "Periodic check: {subject}",
    },
    {
        "pattern": r"\b(encrypt|encryption|TLS|SSL)\b.*\b(required|must|shall)\b",
        "action": "BLOCK",
        "tier": "ENFORCE",
        "description_template": "Encryption required: {subject}",
    },
    {
        "pattern": r"\b(segregation|separation)\b.*\b(duties|roles|responsibilities)\b",
        "action": "ESCROW",
        "tier": "ENFORCE",
        "description_template": "Segregation of duties: {subject}",
    },
]


def _regex_extract(text: str, document_id: str) -> ExtractionResult:
    """Layer 1: Fast regex-based extraction."""
    result = ExtractionResult(document_id=document_id, extraction_method="regex")
    sentences = re.split(r'[.!?]\s+', text.strip())
    result.total_sentences = len(sentences)

    rule_idx = 0
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) < 10:
            continue
        for pattern_def in POLICY_PATTERNS:
            match = re.search(pattern_def["pattern"], sentence, re.IGNORECASE)
            if match:
                rule_idx += 1
                rule = ExtractedRule(
                    rule_name=f"APE-{document_id[:8]}-R{rule_idx:03d}",
                    description=pattern_def["description_template"].format(
                        subject=sentence[:80]
                    ),
                    logic={
                        "condition": f"source_sentence MATCHES '{sentence[:60]}...'",
                        "action": pattern_def["action"],
                        "severity": "HIGH" if pattern_def["tier"] == "ENFORCE" else "INFO",
                        "source_pattern": pattern_def["pattern"],
                    },
                    tier=pattern_def["tier"],
                    confidence=0.85 if pattern_def["tier"] == "ENFORCE" else 0.65,
                    source_sentence=sentence[:200],
                )
                result.rules.append(rule)
                result.matched_sentences += 1
                break
    return result


# ============================================================================
# LLM SEMANTIC EXTRACTION (Layer 2 — tenant API keys)
# ============================================================================

LLM_EXTRACTION_PROMPT = """You are an enterprise compliance policy extraction engine.
Given the following SOP/policy document text, extract ALL machine-enforceable rules.

For EACH rule found, output a JSON object with these fields:
- rule_name: A short identifier (e.g., "data-access-logging")
- description: Human-readable description of the rule
- tier: One of "ENFORCE" (must comply), "ADVISE" (recommended), or "LOG" (log only)
- action: One of "BLOCK" (prevent), "ESCROW" (hold for approval), "LOG" (record only)
- condition: The triggering condition as a machine-readable expression
- severity: "CRITICAL", "HIGH", "MEDIUM", "LOW", or "INFO"
- source_sentence: The exact sentence from the document this rule was derived from

Rules should cover:
- Access controls and restrictions
- Approval workflows and thresholds
- Data classification and handling requirements
- Audit and logging requirements
- Segregation of duties
- Encryption and security requirements
- Time-based compliance (periodic reviews, deadlines)
- Financial thresholds and limits

Output ONLY a JSON array of rule objects. No markdown, no explanation.

DOCUMENT TEXT:
{document_text}
"""


async def _llm_extract(
    text: str,
    document_id: str,
    tenant_id: str,
    llm_provider: str = "openai",
    api_key: str = "",
) -> ExtractionResult:
    """
    Layer 2: LLM-based semantic extraction using tenant's API keys.

    Supports: openai, anthropic, gemini
    Falls back to regex if LLM call fails.
    """
    result = ExtractionResult(document_id=document_id, extraction_method="llm")

    if not api_key:
        logger.warning(
            "APE LLM extraction: No API key for tenant=%s provider=%s, falling back to regex",
            tenant_id, llm_provider,
        )
        return _regex_extract(text, document_id)

    # Truncate to avoid token limits (approx 12k tokens = 48k chars)
    truncated = text[:48000]
    prompt = LLM_EXTRACTION_PROMPT.format(document_text=truncated)

    try:
        rules_json = await _call_llm(llm_provider, api_key, prompt)
        parsed_rules = json.loads(rules_json)

        if not isinstance(parsed_rules, list):
            parsed_rules = [parsed_rules]

        sentences = re.split(r'[.!?]\s+', text.strip())
        result.total_sentences = len(sentences)

        for idx, raw_rule in enumerate(parsed_rules):
            rule = ExtractedRule(
                rule_name=f"APE-{document_id[:8]}-L{idx+1:03d}",
                description=raw_rule.get("description", "LLM-extracted rule"),
                logic={
                    "condition": raw_rule.get("condition", ""),
                    "action": raw_rule.get("action", "LOG"),
                    "severity": raw_rule.get("severity", "MEDIUM"),
                },
                tier=raw_rule.get("tier", "ADVISE"),
                confidence=0.90,  # LLM extraction has higher confidence
                source_sentence=raw_rule.get("source_sentence", "")[:200],
            )
            result.rules.append(rule)
            result.matched_sentences += 1

        logger.info(
            "APE LLM extraction: tenant=%s provider=%s rules=%d",
            tenant_id, llm_provider, len(result.rules),
        )

    except Exception as e:
        logger.error(
            "APE LLM extraction failed: tenant=%s provider=%s error=%s — falling back to regex",
            tenant_id, llm_provider, str(e),
        )
        return _regex_extract(text, document_id)

    return result


async def _call_llm(provider: str, api_key: str, prompt: str) -> str:
    """Call the appropriate LLM provider and return the raw response text."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        if provider in ("openai", ""):
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 4000,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

        elif provider == "anthropic":
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "claude-3-5-haiku-latest",
                    "max_tokens": 4000,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            return resp.json()["content"][0]["text"]

        elif provider == "gemini":
            resp = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.1, "maxOutputTokens": 4000},
                },
            )
            resp.raise_for_status()
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"]

        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")


# ============================================================================
# PUBLIC API
# ============================================================================

def extract_policies(
    document_text: str,
    document_id: str = "unknown",
    tenant_id: str = "",
    llm_provider: str = "",
    llm_api_key: str = "",
) -> ExtractionResult:
    """
    Extract machine-enforceable policies from SOP document text.

    If tenant provides LLM keys → uses LLM semantic extraction.
    Otherwise → uses fast regex pattern matching.

    Args:
        document_text: Raw text content of the SOP/policy document
        document_id: ID of the source document
        tenant_id: Tenant ID for multi-tenant key lookup
        llm_provider: "openai", "anthropic", "gemini" or "" for regex-only
        llm_api_key: Tenant's API key for the LLM provider

    Returns:
        ExtractionResult with list of extracted rules
    """
    if not document_text:
        return ExtractionResult(document_id=document_id)

    # If tenant provided LLM keys, use semantic extraction
    if llm_provider and llm_api_key:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context — create a task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(
                        asyncio.run,
                        _llm_extract(document_text, document_id, tenant_id, llm_provider, llm_api_key),
                    ).result(timeout=90)
            else:
                result = loop.run_until_complete(
                    _llm_extract(document_text, document_id, tenant_id, llm_provider, llm_api_key)
                )
        except Exception as e:
            logger.error("APE LLM dispatch failed: %s — falling back to regex", e)
            result = _regex_extract(document_text, document_id)
    else:
        result = _regex_extract(document_text, document_id)

    logger.info(
        "APE extraction complete: doc=%s method=%s sentences=%d matched=%d rules=%d",
        document_id, result.extraction_method,
        result.total_sentences, result.matched_sentences, len(result.rules),
    )
    return result


def compute_extraction_hash(result: ExtractionResult) -> str:
    """SHA-256 hash of all extracted rules for integrity verification."""
    rule_data = "|".join(
        f"{r.rule_name}:{r.tier}:{r.logic.get('action', '')}"
        for r in result.rules
    )
    return hashlib.sha256(rule_data.encode()).hexdigest()[:16]
