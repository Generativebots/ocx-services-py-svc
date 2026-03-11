"""
RLHC — Reinforcement Learning from Human Corrections (Patent Phase 4)
Clusters HITL decisions into patterns and suggests new policies.
Called by Go backend via gRPC: ClusterDecisions(decisions[]) -> PatternSuggestions[]
"""

import logging
import hashlib
import os
import sys
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from collections import Counter

# Allow importing trust-registry config regardless of cwd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "trust-registry"))

logger = logging.getLogger("rlhc")


def _load_governance_config(tenant_id: str = "") -> dict:
    """Load tenant governance config with safe fallback."""
    try:
        from config.governance_config import get_tenant_governance_config
        return get_tenant_governance_config(tenant_id)
    except Exception:
        return {}


@dataclass
class HITLDecision:
    """A single HITL correction record."""
    decision_id: str
    agent_id: str
    tool_name: str
    original_verdict: str  # ALLOW, BLOCK, HOLD
    override_action: str   # ALLOW_OVERRIDE, BLOCK_OVERRIDE, MODIFY_OUTPUT
    reason: str = ""
    trust_score: float = 0.0


@dataclass
class PatternSuggestion:
    """A clustered pattern suggesting a new policy."""
    pattern_id: str
    description: str
    frequency: int
    confidence: float
    suggested_rule: Dict[str, Any]
    source_decisions: List[str]  # decision IDs
    status: str = "PENDING"  # PENDING, APPROVED, REJECTED


@dataclass
class AnalysisResult:
    """Result of RLHC clustering analysis."""
    analysis_id: str
    patterns: List[PatternSuggestion] = field(default_factory=list)
    total_decisions: int = 0
    clusters_found: int = 0


def cluster_decisions(
    decisions: List[HITLDecision],
    analysis_id: str = "rlhc-auto",
    min_frequency: int = 2,
    min_confidence: float = 0.6,
    tenant_id: str = "",
) -> AnalysisResult:
    """
    Cluster HITL decisions into patterns suggesting new policies.

    Groups decisions by:
    1. (override_action, original_verdict) — what humans consistently change
    2. (agent_id, tool_name) — agent+tool combinations that get overridden
    3. Trust score ranges — low-trust overrides

    Args:
        decisions: List of HITL decision records
        analysis_id: ID for this analysis run
        min_frequency: Minimum pattern occurrences to report
        min_confidence: Minimum confidence threshold

    Returns:
        AnalysisResult with pattern suggestions
    """
    # Load thresholds from tenant governance config
    cfg = _load_governance_config(tenant_id)
    low_trust_cutoff = cfg.get("escrow_probation_threshold", 0.60)
    auto_apply_threshold = cfg.get("escrow_sovereign_threshold", 0.90)

    result = AnalysisResult(analysis_id=analysis_id, total_decisions=len(decisions))

    if not decisions:
        return result

    # --- Cluster 1: Override patterns (what humans consistently change) ---
    override_groups: Dict[str, List[HITLDecision]] = {}
    for d in decisions:
        key = f"{d.original_verdict}→{d.override_action}"
        override_groups.setdefault(key, []).append(d)

    for key, group in override_groups.items():
        if len(group) < min_frequency:
            continue
        orig, override = key.split("→")
        confidence = len(group) / len(decisions)
        if confidence < min_confidence:
            continue

        pattern = PatternSuggestion(
            pattern_id=f"pat-override-{hashlib.md5(key.encode()).hexdigest()[:6]}",
            description=f"Decisions consistently changed from {orig} to {override} ({len(group)} times)",
            frequency=len(group),
            confidence=round(confidence, 3),
            suggested_rule={
                "condition": f"original_verdict == '{orig}'",
                "action": override.replace("_OVERRIDE", "").replace("_OUTPUT", ""),
                "auto_apply": confidence > auto_apply_threshold,
            },
            source_decisions=[d.decision_id for d in group],
        )
        result.patterns.append(pattern)

    # --- Cluster 2: Low trust overrides ---
    low_trust_overrides = [d for d in decisions if d.trust_score < low_trust_cutoff and "BLOCK" in d.override_action]
    if len(low_trust_overrides) >= min_frequency:
        confidence = len(low_trust_overrides) / len(decisions)
        if confidence >= min_confidence:
            result.patterns.append(PatternSuggestion(
                pattern_id="pat-low-trust-block",
                description=f"Agents with trust < {low_trust_cutoff} frequently blocked ({len(low_trust_overrides)} times)",
                frequency=len(low_trust_overrides),
                confidence=round(confidence, 3),
                suggested_rule={
                    "condition": f"trust_score < {low_trust_cutoff}",
                    "action": "BLOCK",
                    "auto_apply": False,
                },
                source_decisions=[d.decision_id for d in low_trust_overrides],
            ))

    # --- Cluster 3: Tool-specific patterns ---
    tool_overrides: Dict[str, List[HITLDecision]] = {}
    for d in decisions:
        if d.tool_name:
            tool_overrides.setdefault(d.tool_name, []).append(d)

    for tool, group in tool_overrides.items():
        if len(group) < min_frequency:
            continue
        # Check if same override is applied consistently
        action_counts = Counter(d.override_action for d in group)
        most_common_action, count = action_counts.most_common(1)[0]
        confidence = count / len(group)
        if confidence < min_confidence:
            continue

        result.patterns.append(PatternSuggestion(
            pattern_id=f"pat-tool-{hashlib.md5(tool.encode()).hexdigest()[:6]}",
            description=f"Tool '{tool}' consistently overridden to {most_common_action} ({count}/{len(group)} times)",
            frequency=count,
            confidence=round(confidence, 3),
            suggested_rule={
                "condition": f"tool_name == '{tool}'",
                "action": most_common_action.replace("_OVERRIDE", "").replace("_OUTPUT", ""),
                "auto_apply": False,
            },
            source_decisions=[d.decision_id for d in group[:10]],
        ))

    result.clusters_found = len(result.patterns)

    logger.info(
        "RLHC analysis complete: id=%s decisions=%d patterns=%d",
        analysis_id, len(decisions), len(result.patterns),
    )
    return result
