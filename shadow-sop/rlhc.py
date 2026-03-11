"""
Shadow-SOP RLHC (Reinforcement Learning from Human Corrections)

This module implements the learning loop that:
1. Observes human corrections to agent behavior
2. Extracts patterns from corrections
3. Proposes new policies based on corrections
4. Tracks effectiveness of learned policies

The RLHC system is ADDITIVE - it only proposes new policies for human review,
it never modifies core enforcement without human approval.
"""

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
import logging
import hashlib
import json
import asyncio
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CorrectionType(str, Enum):
    """Types of human corrections"""
    ALLOW_OVERRIDE = "ALLOW_OVERRIDE"  # Human allowed a blocked action
    BLOCK_OVERRIDE = "BLOCK_OVERRIDE"  # Human blocked an allowed action
    MODIFY_OUTPUT = "MODIFY_OUTPUT"    # Human modified agent output
    REJECT_ACTION = "REJECT_ACTION"    # Human rejected an executed action
    ADD_CONTEXT = "ADD_CONTEXT"        # Human added missing context
    CORRECT_DATA = "CORRECT_DATA"      # Human corrected data error


class PolicyStatus(str, Enum):
    """Status of proposed policies"""
    PROPOSED = "PROPOSED"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    RETIRED = "RETIRED"


@dataclass
class HumanCorrection:
    """Record of a human correction to agent behavior"""
    correction_id: str
    timestamp: datetime
    tenant_id: str
    agent_id: str
    
    # What was corrected
    correction_type: CorrectionType
    original_action: str
    original_output: Optional[str]
    corrected_action: str
    corrected_output: Optional[str]
    
    # Context
    tool_id: str
    transaction_id: str
    context: Dict[str, Any]
    
    # Human reviewer
    reviewer_id: str
    reviewer_trust_score: float
    reasoning: str
    
    # Learning signals
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    recurrence_count: int = 0
    similar_corrections: List[str] = field(default_factory=list)


@dataclass
class LearnedPattern:
    """Pattern extracted from multiple corrections"""
    pattern_id: str
    pattern_type: str  # CONDITIONAL, CONTEXTUAL, TEMPORAL, DOMAIN
    
    # Pattern definition
    trigger_conditions: Dict[str, Any]
    action_pattern: str
    expected_correction: str
    
    # Statistics
    observation_count: int
    accuracy: float  # How often this pattern predicts next correction
    confidence: float
    
    # Corrections that informed this pattern
    source_corrections: List[str]
    
    # Timestamps
    first_observed: datetime
    last_observed: datetime


@dataclass
class ProposedPolicy:
    """Policy proposed based on learned patterns"""
    policy_id: str
    status: PolicyStatus
    
    # Policy definition
    name: str
    description: str
    policy_type: str  # BLOCK, ALLOW, WARN, REQUIRE_REVIEW
    
    # Conditions
    conditions: Dict[str, Any]
    # {
    #     "tool_id": ["execute_payment"],
    #     "context.amount": {"gt": 5000},
    #     "agent.trust_score": {"lt": 0.7},
    # }
    
    # Actions
    action: str
    action_params: Dict[str, Any]
    
    # Provenance
    source_patterns: List[str]
    source_corrections_count: int
    
    # Review
    proposed_at: datetime
    proposed_by: str  # System or human
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    review_notes: Optional[str] = None
    
    # Effectiveness tracking (post-approval)
    times_triggered: int = 0
    overridden_count: int = 0
    effectiveness_score: float = 0.0


class ShadowSOPRLHC:
    """
    Reinforcement Learning from Human Corrections for Shadow-SOP.
    
    This system:
    1. Ingests human corrections to agent behavior
    2. Clusters similar corrections to find patterns
    3. Proposes new policies based on patterns
    4. Tracks policy effectiveness post-approval
    5. Retires ineffective policies
    """
    
    def __init__(
        self,
        min_corrections_for_pattern: int = 3,
        min_patterns_for_policy: int = 2,
        pattern_similarity_threshold: float = 0.7,
        policy_approval_threshold: float = 0.8,
    ) -> None:
        self.min_corrections_for_pattern = min_corrections_for_pattern
        self.min_patterns_for_policy = min_patterns_for_policy
        self.pattern_similarity_threshold = pattern_similarity_threshold
        self.policy_approval_threshold = policy_approval_threshold
        
        # Storage
        self.corrections: Dict[str, HumanCorrection] = {}
        self.patterns: Dict[str, LearnedPattern] = {}
        self.policies: Dict[str, ProposedPolicy] = {}
        
        # Indexes
        self.corrections_by_tool: Dict[str, List[str]] = defaultdict(list)
        self.corrections_by_agent: Dict[str, List[str]] = defaultdict(list)
        self.corrections_by_type: Dict[CorrectionType, List[str]] = defaultdict(list)
        
        # Stats
        self.total_corrections = 0
        self.patterns_generated = 0
        self.policies_proposed = 0
        self.policies_approved = 0
    
    # NOTE: set_tenant_config() removed — was a thread-safety hazard.
    # Tenant-specific thresholds are now passed as parameters per-request.

    async def record_correction(
        self,
        tenant_id: str,
        agent_id: str,
        correction_type: CorrectionType,
        original_action: str,
        corrected_action: str,
        tool_id: str,
        transaction_id: str,
        reviewer_id: str,
        reasoning: str,
        original_output: Optional[str] = None,
        corrected_output: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        reviewer_trust_score: float = 1.0,
        severity: str = "MEDIUM",
        # Per-request tenant overrides (thread-safe, no shared state mutation)
        pattern_similarity_threshold: Optional[float] = None,
        min_corrections_for_pattern: Optional[int] = None,
        policy_approval_threshold: Optional[float] = None,
    ) -> HumanCorrection:
        """Record a human correction to agent behavior.
        Tenant-specific thresholds are passed per-request to avoid
        mutating shared singleton state (thread-safety fix)."""

        # Use per-request overrides if provided, fall back to constructor defaults
        similarity_thresh = pattern_similarity_threshold if pattern_similarity_threshold is not None else self.pattern_similarity_threshold
        min_corr = min_corrections_for_pattern if min_corrections_for_pattern is not None else self.min_corrections_for_pattern
        approval_thresh = policy_approval_threshold if policy_approval_threshold is not None else self.policy_approval_threshold
        
        correction_id = self._generate_id("corr", transaction_id, correction_type.value)
        
        correction = HumanCorrection(
            correction_id=correction_id,
            timestamp=datetime.now(timezone.utc),
            tenant_id=tenant_id,
            agent_id=agent_id,
            correction_type=correction_type,
            original_action=original_action,
            original_output=original_output,
            corrected_action=corrected_action,
            corrected_output=corrected_output,
            tool_id=tool_id,
            transaction_id=transaction_id,
            context=context or {},
            reviewer_id=reviewer_id,
            reviewer_trust_score=reviewer_trust_score,
            reasoning=reasoning,
            severity=severity,
        )
        
        # Store and index
        self.corrections[correction_id] = correction
        self.corrections_by_tool[tool_id].append(correction_id)
        self.corrections_by_agent[agent_id].append(correction_id)
        self.corrections_by_type[correction_type].append(correction_id)
        
        self.total_corrections += 1
        
        # Find similar corrections (using per-request threshold)
        similar = await self._find_similar_corrections(correction, similarity_thresh)
        correction.similar_corrections = similar
        correction.recurrence_count = len(similar)
        
        logger.info(
            f"Recorded correction: {correction_id} "
            f"(type={correction_type}, tool={tool_id}, similar={len(similar)})"
        )
        
        # Check if we should generate a pattern (using per-request threshold)
        if len(similar) >= min_corr - 1:
            await self._generate_pattern_from_corrections(
                [correction_id] + similar, approval_thresh, min_corr
            )
        
        return correction
    
    async def _find_similar_corrections(
        self,
        correction: HumanCorrection,
        similarity_threshold: Optional[float] = None,
    ) -> List[str]:
        thresh = similarity_threshold if similarity_threshold is not None else self.pattern_similarity_threshold
        """Find similar corrections based on tool, action, and context."""
        similar = []
        
        # Get corrections for the same tool
        tool_corrections = self.corrections_by_tool.get(correction.tool_id, [])
        
        for corr_id in tool_corrections:
            if corr_id == correction.correction_id:
                continue
            
            other = self.corrections.get(corr_id)
            if not other:
                continue
            
            # Calculate similarity
            similarity = self._calculate_similarity(correction, other)
            if similarity >= thresh:
                similar.append(corr_id)
        
        return similar
    
    def _calculate_similarity(
        self,
        c1: HumanCorrection,
        c2: HumanCorrection,
    ) -> float:
        """Calculate similarity between two corrections."""
        score = 0.0
        
        # Same correction type (most important)
        if c1.correction_type == c2.correction_type:
            score += 0.4
        
        # Same tool
        if c1.tool_id == c2.tool_id:
            score += 0.2
        
        # Similar action
        if c1.original_action == c2.original_action:
            score += 0.2
        
        # Similar corrected action
        if c1.corrected_action == c2.corrected_action:
            score += 0.1
        
        # Same severity
        if c1.severity == c2.severity:
            score += 0.1
        
        return score
    
    async def _generate_pattern_from_corrections(
        self,
        correction_ids: List[str],
        approval_threshold: Optional[float] = None,
        min_corrections: Optional[int] = None,
    ) -> Optional[LearnedPattern]:
        min_corr = min_corrections if min_corrections is not None else self.min_corrections_for_pattern
        approval_thresh = approval_threshold if approval_threshold is not None else self.policy_approval_threshold
        """Generate a pattern from a cluster of similar corrections."""
        corrections = [self.corrections[cid] for cid in correction_ids if cid in self.corrections]
        
        if len(corrections) < min_corr:
            return None
        
        # Find common elements
        common_tool = corrections[0].tool_id if all(c.tool_id == corrections[0].tool_id for c in corrections) else "*"
        common_type = corrections[0].correction_type if all(c.correction_type == corrections[0].correction_type for c in corrections) else None
        
        if not common_type:
            return None  # Need consistent correction type
        
        pattern_id = self._generate_id("pat", common_tool, common_type.value)
        
        # Build trigger conditions
        trigger_conditions = {
            "tool_id": common_tool,
            "correction_type": common_type.value,
        }
        
        # Look for common context patterns
        context_patterns = self._extract_context_patterns(corrections)
        if context_patterns:
            trigger_conditions["context"] = context_patterns
        
        pattern = LearnedPattern(
            pattern_id=pattern_id,
            pattern_type="CONDITIONAL",
            trigger_conditions=trigger_conditions,
            action_pattern=corrections[0].original_action,
            expected_correction=corrections[0].corrected_action,
            observation_count=len(corrections),
            accuracy=0.8,  # Initial estimate
            confidence=min(len(corrections) / 10.0, 1.0),  # More corrections = more confidence
            source_corrections=correction_ids,
            first_observed=min(c.timestamp for c in corrections),
            last_observed=max(c.timestamp for c in corrections),
        )
        
        self.patterns[pattern_id] = pattern
        self.patterns_generated += 1
        
        logger.info(
            f"Generated pattern: {pattern_id} "
            f"(observations={len(corrections)}, confidence={pattern.confidence:.2f})"
        )
        
        # Check if we should propose a policy
        if pattern.confidence >= approval_thresh:
            await self._propose_policy_from_pattern(pattern)
        
        return pattern
    
    def _extract_context_patterns(
        self,
        corrections: List[HumanCorrection],
    ) -> Dict[str, Any]:
        """Extract common context patterns from corrections."""
        if not corrections or not all(c.context for c in corrections):
            return {}
        
        patterns = {}
        
        # Find common keys
        common_keys = set(corrections[0].context.keys())
        for c in corrections[1:]:
            common_keys &= set(c.context.keys())
        
        # Check for common values or ranges
        for key in common_keys:
            values = [c.context.get(key) for c in corrections]
            
            if all(isinstance(v, (int, float)) for v in values):
                # Numeric - find range
                min_val = min(values)
                max_val = max(values)
                patterns[key] = {"min": min_val, "max": max_val}
            elif all(isinstance(v, str) for v in values):
                # String - check if all same
                if len(set(values)) == 1:
                    patterns[key] = values[0]
                else:
                    patterns[key] = {"one_of": list(set(values))}
        
        return patterns
    
    async def _propose_policy_from_pattern(
        self,
        pattern: LearnedPattern,
    ) -> Optional[ProposedPolicy]:
        """Propose a new policy based on a learned pattern."""
        policy_id = self._generate_id("pol", pattern.pattern_id)
        
        # Determine policy action based on correction type
        correction_type = pattern.trigger_conditions.get("correction_type")
        
        if correction_type == CorrectionType.BLOCK_OVERRIDE.value:
            policy_type = "BLOCK"
            action = "block"
        elif correction_type == CorrectionType.ALLOW_OVERRIDE.value:
            policy_type = "WARN"  # Don't auto-allow, just warn
            action = "warn"
        else:
            policy_type = "REQUIRE_REVIEW"
            action = "require_review"
        
        # Build conditions
        conditions = {}
        if pattern.trigger_conditions.get("tool_id") != "*":
            conditions["tool_id"] = pattern.trigger_conditions.get("tool_id")
        if "context" in pattern.trigger_conditions:
            conditions["context"] = pattern.trigger_conditions["context"]
        
        policy = ProposedPolicy(
            policy_id=policy_id,
            status=PolicyStatus.PENDING_REVIEW,
            name=f"RLHC-{pattern.pattern_id[:8]}",
            description=(
                f"Learned policy from {pattern.observation_count} human corrections. "
                f"Pattern: {pattern.action_pattern} -> {pattern.expected_correction}"
            ),
            policy_type=policy_type,
            conditions=conditions,
            action=action,
            action_params={},
            source_patterns=[pattern.pattern_id],
            source_corrections_count=pattern.observation_count,
            proposed_at=datetime.now(timezone.utc),
            proposed_by="RLHC_SYSTEM",
        )
        
        self.policies[policy_id] = policy
        self.policies_proposed += 1
        
        logger.info(
            f"Proposed policy: {policy_id} "
            f"(type={policy_type}, corrections={pattern.observation_count})"
        )
        
        return policy
    
    def get_pending_policies(self) -> List[ProposedPolicy]:
        """Get all policies pending human review."""
        return [
            p for p in self.policies.values()
            if p.status == PolicyStatus.PENDING_REVIEW
        ]
    
    def approve_policy(
        self,
        policy_id: str,
        reviewer_id: str,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Approve a proposed policy (human action)."""
        policy = self.policies.get(policy_id)
        if not policy:
            return {"success": False, "error": "Policy not found"}
        
        if policy.status != PolicyStatus.PENDING_REVIEW:
            return {"success": False, "error": f"Policy status is {policy.status}"}
        
        policy.status = PolicyStatus.APPROVED
        policy.reviewed_at = datetime.now(timezone.utc)
        policy.reviewed_by = reviewer_id
        policy.review_notes = notes
        
        self.policies_approved += 1
        
        logger.info(f"Approved policy: {policy_id} by {reviewer_id}")
        
        return {
            "success": True,
            "policy_id": policy_id,
            "message": f"Policy {policy.name} approved and now active",
        }
    
    def reject_policy(
        self,
        policy_id: str,
        reviewer_id: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Reject a proposed policy (human action)."""
        policy = self.policies.get(policy_id)
        if not policy:
            return {"success": False, "error": "Policy not found"}
        
        if policy.status not in [PolicyStatus.PENDING_REVIEW, PolicyStatus.PROPOSED]:
            return {"success": False, "error": f"Policy status is {policy.status}"}
        
        policy.status = PolicyStatus.REJECTED
        policy.reviewed_at = datetime.now(timezone.utc)
        policy.reviewed_by = reviewer_id
        policy.review_notes = reason
        
        logger.info(f"Rejected policy: {policy_id} by {reviewer_id} - {reason}")
        
        return {
            "success": True,
            "policy_id": policy_id,
            "message": f"Policy {policy.name} rejected",
        }
    
    def record_policy_trigger(
        self,
        policy_id: str,
        was_overridden: bool = False,
    ) -> None:
        """Record that an approved policy was triggered."""
        policy = self.policies.get(policy_id)
        if not policy or policy.status != PolicyStatus.APPROVED:
            return
        
        policy.times_triggered += 1
        if was_overridden:
            policy.overridden_count += 1
        
        # Update effectiveness score
        if policy.times_triggered > 0:
            policy.effectiveness_score = 1.0 - (policy.overridden_count / policy.times_triggered)
    
    def retire_ineffective_policies(
        self,
        min_triggers: int = 10,
        effectiveness_threshold: float = 0.5,
    ) -> List[str]:
        """Retire policies that are frequently overridden."""
        retired = []
        
        for policy_id, policy in self.policies.items():
            if policy.status != PolicyStatus.APPROVED:
                continue
            
            if policy.times_triggered >= min_triggers:
                if policy.effectiveness_score < effectiveness_threshold:
                    policy.status = PolicyStatus.RETIRED
                    retired.append(policy_id)
                    logger.info(
                        f"Retired ineffective policy: {policy_id} "
                        f"(triggers={policy.times_triggered}, "
                        f"effectiveness={policy.effectiveness_score:.2f})"
                    )
        
        return retired
    
    def get_approved_policies(self) -> List[ProposedPolicy]:
        """Get all approved and active policies."""
        return [p for p in self.policies.values() if p.status == PolicyStatus.APPROVED]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get RLHC statistics."""
        return {
            "total_corrections": self.total_corrections,
            "patterns_generated": self.patterns_generated,
            "policies_proposed": self.policies_proposed,
            "policies_approved": self.policies_approved,
            "policies_pending": len(self.get_pending_policies()),
            "policies_active": len(self.get_approved_policies()),
            "corrections_by_type": {
                ct.value: len(ids) for ct, ids in self.corrections_by_type.items()
            },
        }
    
    def _generate_id(self, prefix: str, *parts: str) -> str:
        """Generate a unique ID."""
        content = "-".join(str(p) for p in parts) + str(datetime.now(timezone.utc).timestamp())
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"{prefix}-{hash_val}"


# ============================================================================
# FASTAPI ROUTER (PostgreSQL-backed)
# ============================================================================

import os
import psycopg2
import psycopg2.pool
from psycopg2.extras import RealDictCursor
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel

router = APIRouter()


# --- Database Connection Pool (Enterprise: avoids TCP+auth per-request) ---

_db_pool = None


def _get_pool():
    """Lazily initialize a ThreadedConnectionPool.
    Enterprise pattern: reuses existing TCP connections instead of
    creating a new psycopg2.connect() per request (saves 5-50ms/call)."""
    global _db_pool
    if _db_pool is None:
        _db_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=int(os.getenv('DB_POOL_MAX', '20')),
            host=os.getenv('DB_HOST', 'localhost'),
            port=os.getenv('DB_PORT', '5432'),
            database=os.getenv('DB_NAME', 'ocx'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD', 'postgres'),
        )
    return _db_pool


def get_db():
    """Yield a pooled connection. Returns to pool on completion."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)


class RecordCorrectionRequest(BaseModel):
    tenant_id: str
    agent_id: str
    correction_type: str
    original_action: str
    corrected_action: str
    tool_id: str
    transaction_id: str
    reviewer_id: str
    reasoning: str
    severity: str = "MEDIUM"
    context: Optional[Dict[str, Any]] = None


class PolicyApprovalRequest(BaseModel):
    reviewer_id: str
    notes: Optional[str] = None


class PolicyRejectionRequest(BaseModel):
    reviewer_id: str
    reason: str


@router.post("/corrections")
async def record_correction(
    req: RecordCorrectionRequest,
    x_department: Optional[str] = Header(None),
    conn=Depends(get_db),
) -> dict:
    """Record a human correction to agent behavior (DB-backed, tenant-scoped)."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Insert into hitl_decisions table
        cursor.execute("""
            INSERT INTO hitl_decisions (
                tenant_id, reviewer_id, transaction_id, agent_id,
                decision_type, original_verdict, modified_payload, reason
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            req.tenant_id,
            req.reviewer_id,
            req.transaction_id,
            req.agent_id,
            req.correction_type,
            req.original_action,
            json.dumps({
                "corrected_action": req.corrected_action,
                "tool_id": req.tool_id,
                "severity": req.severity,
                "context": req.context or {},
            }),
            req.reasoning,
        ))

        result = cursor.fetchone()

        # Check for similar corrections (pattern detection)
        cursor.execute("""
            SELECT COUNT(*) as similar_count
            FROM hitl_decisions
            WHERE tenant_id = %s
              AND decision_type = %s
              AND agent_id = %s
              AND created_at > NOW() - INTERVAL '30 days'
        """, (req.tenant_id, req.correction_type, req.agent_id))

        similar = cursor.fetchone()["similar_count"]

        # Read tenant-specific min_corrections threshold from governance config
        cursor.execute("""
            SELECT COALESCE(
                (SELECT (config_data->>'rlhc_min_corrections_for_pattern')::int
                 FROM platform_config
                 WHERE tenant_id = %s AND config_key = 'governance'),
                3
            ) AS min_corr
        """, (req.tenant_id,))
        min_corrections_row = cursor.fetchone()
        min_corrections = min_corrections_row["min_corr"] if min_corrections_row else 3

        # If pattern detected (tenant-configurable threshold), create cluster
        if similar >= min_corrections:
            pattern_type = "ALLOW_PATTERN" if "ALLOW" in req.correction_type else (
                "BLOCK_PATTERN" if "BLOCK" in req.correction_type else "MODIFY_PATTERN"
            )
            cursor.execute("""
                INSERT INTO rlhc_correction_clusters (
                    tenant_id, cluster_name, pattern_type,
                    trigger_conditions, correction_count,
                    confidence_score, status, department
                ) VALUES (%s, %s, %s, %s, %s, %s, 'DETECTED', %s)
            """, (
                req.tenant_id,
                f"RLHC-{req.correction_type[:12]}-{req.agent_id[:8]}",
                pattern_type,
                json.dumps({
                    "correction_type": req.correction_type,
                    "agent_id": req.agent_id,
                    "tool_id": req.tool_id,
                }),
                similar,
                min(similar / 10.0, 1.0),
                x_department,
            ))

        conn.commit()

        return {
            "correction_id": str(result["id"]),
            "tenant_id": req.tenant_id,
            "similar_count": similar,
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/policies/pending")
async def get_pending_policies(
    tenant_id: str,
    department: Optional[str] = None,
    x_department: Optional[str] = Header(None),
    conn=Depends(get_db),
) -> list:
    """Get RLHC-detected patterns pending human review (DB-backed)."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    dept = department or x_department

    if dept:
        cursor.execute("""
            SELECT * FROM rlhc_correction_clusters
            WHERE tenant_id = %s AND status IN ('DETECTED', 'REVIEWED')
              AND (department = %s OR department IS NULL)
            ORDER BY last_seen DESC
            LIMIT 200
        """, (tenant_id, dept))
    else:
        cursor.execute("""
            SELECT * FROM rlhc_correction_clusters
            WHERE tenant_id = %s AND status IN ('DETECTED', 'REVIEWED')
            ORDER BY last_seen DESC
            LIMIT 200
        """, (tenant_id,))

    rows = cursor.fetchall()
    return [
        {
            "policy_id": str(row["id"]),
            "name": row["cluster_name"],
            "description": f"Detected from {row['correction_count']} human corrections",
            "policy_type": row["pattern_type"],
            "conditions": row["trigger_conditions"] if isinstance(row["trigger_conditions"], dict) else json.loads(row["trigger_conditions"]),
            "source_corrections_count": row["correction_count"],
            "proposed_at": row["first_seen"].isoformat() if row["first_seen"] else None,
            "confidence": row["confidence_score"],
            "tenant_id": tenant_id,
        }
        for row in rows
    ]


@router.post("/policies/{policy_id}/approve")
async def approve_policy(
    policy_id: str,
    req: PolicyApprovalRequest,
    tenant_id: str,
    conn=Depends(get_db),
) -> Any:
    """Approve a detected RLHC pattern (DB-backed)."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        UPDATE rlhc_correction_clusters
        SET status = 'PROMOTED', last_seen = NOW()
        WHERE id = %s AND tenant_id = %s AND status IN ('DETECTED', 'REVIEWED')
        RETURNING *
    """, (policy_id, tenant_id))

    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=400, detail="Pattern not found or already processed")

    conn.commit()
    return {
        "success": True,
        "policy_id": str(row["id"]),
        "tenant_id": tenant_id,
        "message": f"Pattern {row['cluster_name']} promoted to policy",
    }


@router.post("/policies/{policy_id}/reject")
async def reject_policy(
    policy_id: str,
    req: PolicyRejectionRequest,
    tenant_id: str,
    conn=Depends(get_db),
) -> Any:
    """Reject a detected RLHC pattern (DB-backed)."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        UPDATE rlhc_correction_clusters
        SET status = 'REJECTED', last_seen = NOW()
        WHERE id = %s AND tenant_id = %s AND status IN ('DETECTED', 'REVIEWED')
        RETURNING *
    """, (policy_id, tenant_id))

    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=400, detail="Pattern not found or already processed")

    conn.commit()
    return {
        "success": True,
        "policy_id": str(row["id"]),
        "tenant_id": tenant_id,
        "message": f"Pattern {row['cluster_name']} rejected",
    }


@router.get("/stats")
async def get_stats(
    tenant_id: str,
    conn=Depends(get_db),
) -> Any:
    """Get RLHC statistics from DB (tenant-scoped)."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Correction stats
    cursor.execute("""
        SELECT
            COUNT(*) as total_corrections,
            COUNT(*) FILTER (WHERE decision_type = 'ALLOW_OVERRIDE') as allow_overrides,
            COUNT(*) FILTER (WHERE decision_type = 'BLOCK_OVERRIDE') as block_overrides,
            COUNT(*) FILTER (WHERE decision_type = 'MODIFY_OUTPUT') as modify_outputs
        FROM hitl_decisions
        WHERE tenant_id = %s
    """, (tenant_id,))
    correction_stats = cursor.fetchone()

    # Cluster/pattern stats
    cursor.execute("""
        SELECT
            COUNT(*) as total_patterns,
            COUNT(*) FILTER (WHERE status = 'DETECTED') as pending,
            COUNT(*) FILTER (WHERE status = 'PROMOTED') as promoted,
            COUNT(*) FILTER (WHERE status = 'REJECTED') as rejected
        FROM rlhc_correction_clusters
        WHERE tenant_id = %s
    """, (tenant_id,))
    pattern_stats = cursor.fetchone()

    return {
        "tenant_id": tenant_id,
        "total_corrections": correction_stats["total_corrections"],
        "corrections_by_type": {
            "ALLOW_OVERRIDE": correction_stats["allow_overrides"],
            "BLOCK_OVERRIDE": correction_stats["block_overrides"],
            "MODIFY_OUTPUT": correction_stats["modify_outputs"],
        },
        "patterns_generated": pattern_stats["total_patterns"],
        "policies_pending": pattern_stats["pending"],
        "policies_approved": pattern_stats["promoted"],
        "policies_rejected": pattern_stats["rejected"],
    }

