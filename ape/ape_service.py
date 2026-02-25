"""
APE — Autonomous Policy Engine (Patent Claim 8)
Extracts machine-enforceable policies from SOP/document text using NLP.
Called by Go backend via gRPC: ExtractPolicies(document_text) -> PolicyList
"""

import re
import hashlib
import logging
from typing import List, Dict, Any
from dataclasses import dataclass, field

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


# Rule extraction patterns — keywords that indicate enforceable policies
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
]


def extract_policies(document_text: str, document_id: str = "unknown") -> ExtractionResult:
    """
    Extract machine-enforceable policies from SOP document text.

    Uses NLP pattern matching to identify sentences containing enforceable rules,
    then converts them into structured policy objects.

    Args:
        document_text: Raw text content of the SOP/policy document
        document_id: ID of the source document

    Returns:
        ExtractionResult with list of extracted rules
    """
    result = ExtractionResult(document_id=document_id)

    # Split into sentences
    sentences = re.split(r'[.!?]\s+', document_text.strip())
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
                rule_name = f"APE-{document_id[:8]}-R{rule_idx:03d}"

                # Build logic object
                logic = {
                    "condition": f"source_sentence MATCHES '{sentence[:60]}...'",
                    "action": pattern_def["action"],
                    "severity": "HIGH" if pattern_def["tier"] == "ENFORCE" else "INFO",
                    "source_pattern": pattern_def["pattern"],
                }

                rule = ExtractedRule(
                    rule_name=rule_name,
                    description=pattern_def["description_template"].format(
                        subject=sentence[:80]
                    ),
                    logic=logic,
                    tier=pattern_def["tier"],
                    confidence=0.85 if pattern_def["tier"] == "ENFORCE" else 0.65,
                    source_sentence=sentence[:200],
                )
                result.rules.append(rule)
                result.matched_sentences += 1
                break  # One rule per sentence

    logger.info(
        "APE extraction complete: doc=%s sentences=%d matched=%d rules=%d",
        document_id, result.total_sentences, result.matched_sentences, len(result.rules),
    )
    return result


def compute_extraction_hash(result: ExtractionResult) -> str:
    """SHA-256 hash of all extracted rules for integrity verification."""
    rule_data = "|".join(
        f"{r.rule_name}:{r.tier}:{r.logic.get('action', '')}"
        for r in result.rules
    )
    return hashlib.sha256(rule_data.encode()).hexdigest()[:16]
