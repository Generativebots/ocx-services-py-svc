"""
AOCS Semantic DLP Scanner — Data Loss Prevention for Agent Payloads

Provides three detection layers:
  1. PII Detection — emails, phone numbers, SSNs, credit cards, IP addresses
     All detected PII is MD5 hashed before logging/returning for privacy compliance.
  2. Code Detection — source code, SQL queries, API keys, secrets, credentials
  3. Sensitive Data Classification — classifies payload as PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED

Architecture:
  - This module is called by the eBPF gateway's payload inspection pipeline
  - Results feed into the Tri-Factor Gate's Signal validation (entropy + DLP)
  - When enterprise DLP tools are configured via the integration endpoint,
    results are also forwarded to those tools via webhook

Human Browser Monitoring:
  > WARNING: This DLP scanner only monitors AGENT PROCESSES whose PIDs are
  > registered in the eBPF tenant_map. Human browser traffic (Chrome, Firefox,
  > Safari) is NOT monitored by default. To extend coverage to human browsers,
  > add browser PIDs to the tenant_map via the /api/v1/dlp/monitor-pid endpoint.
  > This is a deployment choice, not a code limitation.
"""

import re
import hashlib
import logging
import json
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================================
# CLASSIFICATION LEVELS
# ============================================================================

class DataClassification(str, Enum):
    """Data sensitivity classification per enterprise DLP standards."""
    PUBLIC = "PUBLIC"           # No restrictions
    INTERNAL = "INTERNAL"       # Internal use only
    CONFIDENTIAL = "CONFIDENTIAL"  # Access controlled
    RESTRICTED = "RESTRICTED"     # Highest sensitivity — PII, financial, health


# ============================================================================
# DETECTION RESULTS
# ============================================================================

@dataclass
class PIIMatch:
    """A single PII detection with the original value MD5 hashed."""
    pii_type: str       # "email", "phone", "ssn", "credit_card", "ip_address", etc.
    md5_hash: str       # MD5 hash of the original value
    position: int       # Character offset in the payload
    context: str        # Surrounding text (redacted)
    confidence: float   # 0.0–1.0


@dataclass
class CodeMatch:
    """A detected code/secret pattern."""
    code_type: str      # "source_code", "sql_query", "api_key", "aws_key", "password", etc.
    snippet_hash: str   # MD5 hash of the matched snippet
    language: str       # Detected language/framework
    confidence: float


@dataclass
class DLPScanResult:
    """Complete DLP scan result."""
    classification: DataClassification
    pii_matches: List[PIIMatch] = field(default_factory=list)
    code_matches: List[CodeMatch] = field(default_factory=list)
    total_pii_count: int = 0
    total_code_count: int = 0
    risk_score: float = 0.0  # 0.0–1.0
    should_block: bool = False
    reasoning: str = ""
    human_browser_monitored: bool = False  # Always False — logged for awareness


# ============================================================================
# PII DETECTION PATTERNS
# ============================================================================

PII_PATTERNS: List[Dict[str, Any]] = [
    # Email addresses
    {
        "type": "email",
        "pattern": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "confidence": 0.95,
    },
    # US Phone numbers
    {
        "type": "phone_us",
        "pattern": r"(?:\+1[-.\s]?)?\(?[2-9]\d{2}\)?[-.\s]?\d{3}[-.\s]?\d{4}",
        "confidence": 0.85,
    },
    # International phone numbers
    {
        "type": "phone_intl",
        "pattern": r"\+[1-9]\d{1,2}[-.\s]?\d{2,4}[-.\s]?\d{3,4}[-.\s]?\d{3,4}",
        "confidence": 0.80,
    },
    # US Social Security Numbers
    {
        "type": "ssn",
        "pattern": r"\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b",
        "confidence": 0.90,
    },
    # Credit card numbers (Visa, Mastercard, Amex, Discover)
    {
        "type": "credit_card",
        "pattern": r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b",
        "confidence": 0.92,
    },
    # IPv4 addresses
    {
        "type": "ip_address",
        "pattern": r"\b(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b",
        "confidence": 0.75,
    },
    # Passport numbers (generic)
    {
        "type": "passport",
        "pattern": r"\b[A-Z]{1,2}\d{6,9}\b",
        "confidence": 0.60,
    },
    # Date of birth patterns
    {
        "type": "date_of_birth",
        "pattern": r"\b(?:DOB|date\s+of\s+birth|born\s+on?)[\s:]*\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}\b",
        "confidence": 0.85,
    },
    # IBAN
    {
        "type": "iban",
        "pattern": r"\b[A-Z]{2}\d{2}\s?[\dA-Z]{4}\s?[\dA-Z]{4}\s?[\dA-Z]{4}(?:\s?[\dA-Z]{0,4}){0,4}\b",
        "confidence": 0.88,
    },
]


# ============================================================================
# CODE & SECRET DETECTION PATTERNS
# ============================================================================

CODE_PATTERNS: List[Dict[str, Any]] = [
    # AWS Access Keys
    {
        "type": "aws_access_key",
        "pattern": r"(?:AKIA|ASIA)[A-Z0-9]{16}",
        "language": "aws",
        "confidence": 0.98,
    },
    # AWS Secret Keys
    {
        "type": "aws_secret_key",
        "pattern": r"(?:aws.?secret.?(?:access)?.?key).{0,20}['\"][A-Za-z0-9/+=]{40}['\"]",
        "language": "aws",
        "confidence": 0.95,
    },
    # Generic API keys
    {
        "type": "api_key",
        "pattern": r"(?:api[_-]?key|apikey|token|secret|password)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}['\"]?",
        "language": "generic",
        "confidence": 0.85,
    },
    # OpenAI API keys
    {
        "type": "openai_key",
        "pattern": r"sk-[A-Za-z0-9]{48,}",
        "language": "openai",
        "confidence": 0.98,
    },
    # GitHub tokens
    {
        "type": "github_token",
        "pattern": r"gh[pousr]_[A-Za-z0-9_]{36,}",
        "language": "github",
        "confidence": 0.98,
    },
    # Private keys (PEM)
    {
        "type": "private_key",
        "pattern": r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----",
        "language": "pem",
        "confidence": 0.99,
    },
    # SQL queries
    {
        "type": "sql_query",
        "pattern": r"(?:SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE)\s+(?:INTO|FROM|TABLE|DATABASE|INDEX)\s+[\w.`\"]+",
        "language": "sql",
        "confidence": 0.80,
    },
    # Connection strings
    {
        "type": "connection_string",
        "pattern": r"(?:postgres|mysql|mongodb|redis|amqp)://[^\s]+:[^\s]+@[^\s]+",
        "language": "connection",
        "confidence": 0.95,
    },
    # Source code blocks (Python/Go/JS function definitions)
    {
        "type": "source_code",
        "pattern": r"(?:def\s+\w+\s*\(|func\s+\w+\s*\(|function\s+\w+\s*\(|class\s+\w+\s*[({:])",
        "language": "multi",
        "confidence": 0.70,
    },
    # JWT tokens
    {
        "type": "jwt_token",
        "pattern": r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
        "language": "jwt",
        "confidence": 0.95,
    },
]


# ============================================================================
# MD5 HASHING UTILITY
# ============================================================================

def md5_hash(value: str) -> str:
    """MD5 hash a PII value for safe logging. Never log the original."""
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def redact_context(text: str, match_start: int, match_end: int, window: int = 30) -> str:
    """Extract surrounding context with the match itself redacted."""
    ctx_start = max(0, match_start - window)
    ctx_end = min(len(text), match_end + window)
    before = text[ctx_start:match_start]
    after = text[match_end:ctx_end]
    return f"{before}[REDACTED]{after}"


# ============================================================================
# SEMANTIC DLP SCANNER
# ============================================================================

class SemanticDLPScanner:
    """
    Multi-layer DLP scanner for agent payloads.

    Usage:
        scanner = SemanticDLPScanner(tenant_id="tenant-123")
        result = scanner.scan(payload_text)
        if result.should_block:
            # Block the payload
    """

    def __init__(self, tenant_id: str = ""):
        self.tenant_id = tenant_id
        self._blocked_classifications: Set[DataClassification] = {
            DataClassification.RESTRICTED,
        }
        self._load_tenant_config(tenant_id)

    def _load_tenant_config(self, tenant_id: str) -> None:
        """Load tenant-specific DLP config from governance config."""
        if not tenant_id:
            return
        try:
            from config.governance_config import get_tenant_governance_config
            cfg = get_tenant_governance_config(tenant_id)
            # Tenants can configure which classifications to block
            block_levels = cfg.get("dlp_block_levels", ["RESTRICTED"])
            self._blocked_classifications = {
                DataClassification(level) for level in block_levels
                if level in DataClassification.__members__
            }
        except Exception as e:
            logger.debug(f"Tenant DLP config unavailable: {e}")

    def scan(self, text: str) -> DLPScanResult:
        """
        Scan text for PII, code, and sensitive data.
        All detected PII values are MD5 hashed — originals are NEVER stored.
        """
        if not text:
            return DLPScanResult(
                classification=DataClassification.PUBLIC,
                human_browser_monitored=False,
            )

        # --- Layer 1: PII Detection ---
        pii_matches = self._detect_pii(text)

        # --- Layer 2: Code/Secret Detection ---
        code_matches = self._detect_code(text)

        # --- Layer 3: Classification ---
        classification = self._classify(pii_matches, code_matches, text)

        # --- Risk scoring ---
        risk_score = self._calculate_risk(pii_matches, code_matches, classification)

        # --- Block decision ---
        should_block = classification in self._blocked_classifications

        reasoning = self._build_reasoning(pii_matches, code_matches, classification)

        # --- Log human browser warning ---
        logger.info(
            f"[DLP] Scan complete: tenant={self.tenant_id}, "
            f"classification={classification.value}, "
            f"pii_count={len(pii_matches)}, code_count={len(code_matches)}, "
            f"risk={risk_score:.2f}, block={should_block}. "
            f"NOTE: Human browser traffic is NOT monitored — "
            f"eBPF hooks are attached to agent processes only."
        )

        return DLPScanResult(
            classification=classification,
            pii_matches=pii_matches,
            code_matches=code_matches,
            total_pii_count=len(pii_matches),
            total_code_count=len(code_matches),
            risk_score=risk_score,
            should_block=should_block,
            reasoning=reasoning,
            human_browser_monitored=False,
        )

    def _detect_pii(self, text: str) -> List[PIIMatch]:
        """Detect PII patterns and MD5 hash all matched values."""
        matches = []
        seen_hashes: Set[str] = set()

        for pii_def in PII_PATTERNS:
            for m in re.finditer(pii_def["pattern"], text, re.IGNORECASE):
                value = m.group(0)
                hashed = md5_hash(value)

                # Deduplicate
                if hashed in seen_hashes:
                    continue
                seen_hashes.add(hashed)

                matches.append(PIIMatch(
                    pii_type=pii_def["type"],
                    md5_hash=hashed,
                    position=m.start(),
                    context=redact_context(text, m.start(), m.end()),
                    confidence=pii_def["confidence"],
                ))

        return matches

    def _detect_code(self, text: str) -> List[CodeMatch]:
        """Detect source code, API keys, secrets, and credentials."""
        matches = []
        seen_hashes: Set[str] = set()

        for code_def in CODE_PATTERNS:
            for m in re.finditer(code_def["pattern"], text, re.IGNORECASE):
                snippet = m.group(0)
                hashed = md5_hash(snippet)

                if hashed in seen_hashes:
                    continue
                seen_hashes.add(hashed)

                matches.append(CodeMatch(
                    code_type=code_def["type"],
                    snippet_hash=hashed,
                    language=code_def["language"],
                    confidence=code_def["confidence"],
                ))

        return matches

    def _classify(
        self,
        pii_matches: List[PIIMatch],
        code_matches: List[CodeMatch],
        text: str,
    ) -> DataClassification:
        """Classify the payload based on detected content."""
        # RESTRICTED: contains SSN, credit card, private keys, or connection strings
        restricted_pii = {"ssn", "credit_card", "iban"}
        restricted_code = {"private_key", "aws_secret_key", "connection_string"}

        for m in pii_matches:
            if m.pii_type in restricted_pii:
                return DataClassification.RESTRICTED

        for m in code_matches:
            if m.code_type in restricted_code:
                return DataClassification.RESTRICTED

        # CONFIDENTIAL: contains emails, API keys, tokens
        confidential_pii = {"email", "phone_us", "phone_intl", "passport", "date_of_birth"}
        confidential_code = {"api_key", "openai_key", "github_token", "jwt_token", "aws_access_key"}

        for m in pii_matches:
            if m.pii_type in confidential_pii:
                return DataClassification.CONFIDENTIAL

        for m in code_matches:
            if m.code_type in confidential_code:
                return DataClassification.CONFIDENTIAL

        # INTERNAL: contains source code or SQL
        internal_code = {"source_code", "sql_query"}

        for m in code_matches:
            if m.code_type in internal_code:
                return DataClassification.INTERNAL

        # PUBLIC: nothing sensitive detected
        return DataClassification.PUBLIC

    def _calculate_risk(
        self,
        pii_matches: List[PIIMatch],
        code_matches: List[CodeMatch],
        classification: DataClassification,
    ) -> float:
        """Calculate a 0–1 risk score."""
        base_scores = {
            DataClassification.PUBLIC: 0.0,
            DataClassification.INTERNAL: 0.3,
            DataClassification.CONFIDENTIAL: 0.6,
            DataClassification.RESTRICTED: 0.9,
        }
        score = base_scores[classification]

        # Add per-match penalties
        for m in pii_matches:
            score = min(1.0, score + 0.05 * m.confidence)
        for m in code_matches:
            score = min(1.0, score + 0.03 * m.confidence)

        return round(score, 3)

    def _build_reasoning(
        self,
        pii_matches: List[PIIMatch],
        code_matches: List[CodeMatch],
        classification: DataClassification,
    ) -> str:
        """Build human-readable reasoning string."""
        parts = [f"Classification: {classification.value}"]

        if pii_matches:
            types = sorted(set(m.pii_type for m in pii_matches))
            parts.append(f"PII detected: {', '.join(types)} ({len(pii_matches)} total, all MD5 hashed)")

        if code_matches:
            types = sorted(set(m.code_type for m in code_matches))
            parts.append(f"Code/secrets detected: {', '.join(types)} ({len(code_matches)} total)")

        if not pii_matches and not code_matches:
            parts.append("No sensitive content detected")

        return " | ".join(parts)
