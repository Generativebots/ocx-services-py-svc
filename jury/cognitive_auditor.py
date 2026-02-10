"""
AOCS Cognitive Auditor - Multi-Agent Semantic Intent Validation
Implements the Cognitive Logic layer of the Tri-Factor Gate per AOCS specification.

Key Functions:
- Semantic intent extraction from agent requests
- APE rule matching (intent vs machine-enforceable policies)
- Behavioral baseline comparison for anomaly detection
- Multi-agent unanimous jury verdict
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging
import hashlib
import json
import asyncio
from datetime import datetime, timedelta
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CognitiveVerdict(str, Enum):
    """Verdict from cognitive auditor"""
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    HOLD = "HOLD"  # Requires human review
    ESCALATE = "ESCALATE"  # Requires senior review


class AnomalyType(str, Enum):
    """Types of behavioral anomalies"""
    NONE = "NONE"
    VELOCITY = "VELOCITY"  # Too many requests in short time
    DRIFT = "DRIFT"  # Deviation from historical behavior
    PATTERN = "PATTERN"  # Suspicious request patterns
    SCOPE = "SCOPE"  # Operating outside normal scope


@dataclass
class SemanticIntent:
    """Extracted semantic intent from agent request"""
    primary_action: str  # e.g., "transfer_funds", "delete_record"
    target_resource: str  # e.g., "bank_account", "user_data"
    operation_type: str  # CREATE, READ, UPDATE, DELETE, EXECUTE
    risk_category: str  # FINANCIAL, DATA, INFRASTRUCTURE, COMMUNICATION
    confidence: float  # 0.0 to 1.0
    extracted_entities: Dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""


@dataclass
class APERuleMatch:
    """Result of matching intent against APE rules"""
    rule_id: str
    rule_name: str
    matches: bool
    violation: bool
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    explanation: str
    required_conditions: List[str] = field(default_factory=list)
    met_conditions: List[str] = field(default_factory=list)
    unmet_conditions: List[str] = field(default_factory=list)


@dataclass
class BehavioralBaseline:
    """Agent's historical behavioral baseline"""
    agent_id: str
    avg_requests_per_hour: float
    typical_actions: List[str]
    typical_resources: List[str]
    typical_time_windows: List[str]  # e.g., "09:00-17:00"
    trust_score_history: List[float]
    last_updated: datetime


@dataclass
class JurorVote:
    """Vote from a single juror agent"""
    juror_id: str
    trust_score: float
    vote: str  # APPROVE, REJECT, ABSTAIN
    confidence: float
    reasoning: str
    weight: float  # trust_score * base_weight


@dataclass
class CognitiveAuditResult:
    """Complete result of cognitive audit"""
    transaction_id: str
    tenant_id: str
    agent_id: str
    
    # Intent extraction
    intent: SemanticIntent
    
    # APE rule matching
    rules_checked: int
    rule_matches: List[APERuleMatch]
    violations: List[APERuleMatch]
    
    # Behavioral analysis
    baseline: Optional[BehavioralBaseline]
    anomaly_detected: bool
    anomaly_type: AnomalyType
    anomaly_score: float  # 0.0 to 1.0
    
    # Jury verdict
    jury_votes: List[JurorVote]
    unanimous: bool
    weighted_consensus: float
    
    # Final verdict
    verdict: CognitiveVerdict
    trust_level: float
    reasoning: str
    
    # Timing
    audit_duration_ms: int


class CognitiveAuditor:
    """
    Multi-Agent Cognitive Auditor for AOCS Tri-Factor Gate.
    
    Evaluates agent requests against:
    1. Semantic intent (what the agent is trying to do)
    2. APE rules (organizational policies)
    3. Behavioral baseline (is this normal for this agent?)
    4. Multi-juror consensus (multiple AI judges agree)
    """
    
    def __init__(
        self,
        ape_service_url: str = None,
        jury_service_url: str = None,
        trust_threshold: float = 0.65,
        unanimous_required: bool = False,
        quorum_threshold: float = 0.66,
    ) -> None:
        import os
        self.ape_service_url = ape_service_url or os.getenv("APE_SERVICE_URL", "http://localhost:8000/ape")
        self.jury_service_url = jury_service_url or os.getenv("JURY_SERVICE_URL", "http://localhost:8000/jury")
        self.trust_threshold = trust_threshold
        self.unanimous_required = unanimous_required
        self.quorum_threshold = quorum_threshold
        
        # In-memory baseline cache (production: use Supabase/Redis)
        self.baselines: Dict[str, BehavioralBaseline] = {}
        
        # Request history for velocity tracking
        self.request_history: Dict[str, List[datetime]] = {}
        
    async def audit(
        self,
        transaction_id: str,
        tenant_id: str,
        agent_id: str,
        request_payload: Dict[str, Any],
        tool_id: str,
        entitlements: List[str],
    ) -> CognitiveAuditResult:
        """
        Perform full cognitive audit on an agent request.
        
        This is called by the Tri-Factor Gate for CLASS_B actions.
        """
        start_time = datetime.now()
        
        # Step 1: Extract semantic intent
        intent = await self._extract_intent(request_payload, tool_id)
        
        # Step 2: Match against APE rules
        rule_matches = await self._match_ape_rules(
            intent, tenant_id, entitlements
        )
        violations = [r for r in rule_matches if r.violation]
        
        # Step 3: Compare against behavioral baseline
        baseline = self._get_baseline(agent_id)
        anomaly_detected, anomaly_type, anomaly_score = self._detect_anomaly(
            agent_id, intent, baseline
        )
        
        # Step 4: Get jury votes
        jury_votes = await self._get_jury_votes(
            transaction_id, tenant_id, agent_id, intent, violations
        )
        unanimous, weighted_consensus = self._calculate_consensus(jury_votes)
        
        # Step 5: Determine final verdict
        verdict, trust_level, reasoning = self._determine_verdict(
            intent, violations, anomaly_detected, anomaly_score,
            unanimous, weighted_consensus
        )
        
        # Calculate duration
        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        
        result = CognitiveAuditResult(
            transaction_id=transaction_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            intent=intent,
            rules_checked=len(rule_matches),
            rule_matches=rule_matches,
            violations=violations,
            baseline=baseline,
            anomaly_detected=anomaly_detected,
            anomaly_type=anomaly_type,
            anomaly_score=anomaly_score,
            jury_votes=jury_votes,
            unanimous=unanimous,
            weighted_consensus=weighted_consensus,
            verdict=verdict,
            trust_level=trust_level,
            reasoning=reasoning,
            audit_duration_ms=duration_ms,
        )
        
        logger.info(
            f"Cognitive audit complete: tx={transaction_id}, "
            f"verdict={verdict}, trust={trust_level:.2f}, "
            f"violations={len(violations)}, anomaly={anomaly_detected}"
        )
        
        return result
    
    async def _extract_intent(
        self,
        payload: Dict[str, Any],
        tool_id: str,
    ) -> SemanticIntent:
        """
        Extract semantic intent from agent request.
        
        In production, this would call an LLM to parse the request.
        """
        # Action classification based on tool_id
        action_map = {
            "execute_payment": ("transfer_funds", "financial_account", "EXECUTE", "FINANCIAL"),
            "delete_data": ("delete_record", "database_table", "DELETE", "DATA"),
            "send_external_email": ("send_communication", "email_system", "EXECUTE", "COMMUNICATION"),
            "deploy_infrastructure": ("deploy_resources", "cloud_infra", "EXECUTE", "INFRASTRUCTURE"),
            "read_database": ("query_data", "database_table", "READ", "DATA"),
            "draft_document": ("create_content", "document_store", "CREATE", "DATA"),
        }
        
        if tool_id in action_map:
            action, resource, op_type, risk = action_map[tool_id]
        else:
            action = tool_id
            resource = "unknown"
            op_type = "EXECUTE"
            risk = "UNKNOWN"
        
        # Extract entities from payload
        entities = {}
        if "amount" in payload:
            entities["amount"] = payload["amount"]
        if "recipient" in payload:
            entities["recipient"] = payload["recipient"]
        if "resource_id" in payload:
            entities["resource_id"] = payload["resource_id"]
        
        return SemanticIntent(
            primary_action=action,
            target_resource=resource,
            operation_type=op_type,
            risk_category=risk,
            confidence=0.85,
            extracted_entities=entities,
            reasoning=f"Extracted from tool_id={tool_id}",
        )
    
    async def _match_ape_rules(
        self,
        intent: SemanticIntent,
        tenant_id: str,
        entitlements: List[str],
    ) -> List[APERuleMatch]:
        """
        Match extracted intent against APE-generated policy rules.
        
        In production, this would query the APE engine for tenant's rules.
        """
        # Simulated APE rules (production: fetch from APE service)
        rules = [
            {
                "id": "fin-001",
                "name": "Financial Transfer Limit",
                "applies_to": "transfer_funds",
                "conditions": ["amount <= 10000", "entitlement:finance:write"],
            },
            {
                "id": "data-001",
                "name": "Data Deletion Approval",
                "applies_to": "delete_record",
                "conditions": ["entitlement:data:delete", "entitlement:admin:write"],
            },
            {
                "id": "com-001",
                "name": "External Communication Policy",
                "applies_to": "send_communication",
                "conditions": ["entitlement:email:send", "entitlement:external:access"],
            },
        ]
        
        matches = []
        for rule in rules:
            if rule["applies_to"] == intent.primary_action:
                # Check conditions
                met = []
                unmet = []
                
                for cond in rule["conditions"]:
                    if cond.startswith("entitlement:"):
                        ent = cond.replace("entitlement:", "")
                        if ent in entitlements:
                            met.append(cond)
                        else:
                            unmet.append(cond)
                    elif cond.startswith("amount"):
                        # Check amount condition
                        amount = intent.extracted_entities.get("amount", 0)
                        if "amount <= 10000" in cond and amount <= 10000:
                            met.append(cond)
                        else:
                            unmet.append(cond)
                    else:
                        met.append(cond)  # Default to met
                
                violation = len(unmet) > 0
                
                matches.append(APERuleMatch(
                    rule_id=rule["id"],
                    rule_name=rule["name"],
                    matches=True,
                    violation=violation,
                    severity="HIGH" if violation else "NONE",
                    explanation=f"Rule {rule['name']} {'violated' if violation else 'satisfied'}",
                    required_conditions=rule["conditions"],
                    met_conditions=met,
                    unmet_conditions=unmet,
                ))
        
        return matches
    
    def _get_baseline(self, agent_id: str) -> Optional[BehavioralBaseline]:
        """Get or create behavioral baseline for agent."""
        if agent_id not in self.baselines:
            # Create default baseline for new agents
            self.baselines[agent_id] = BehavioralBaseline(
                agent_id=agent_id,
                avg_requests_per_hour=10.0,
                typical_actions=["read_database", "draft_document", "search_records"],
                typical_resources=["database_table", "document_store"],
                typical_time_windows=["09:00-17:00"],
                trust_score_history=[0.75, 0.78, 0.80],
                last_updated=datetime.now(),
            )
        return self.baselines.get(agent_id)
    
    def _detect_anomaly(
        self,
        agent_id: str,
        intent: SemanticIntent,
        baseline: Optional[BehavioralBaseline],
    ) -> Tuple[bool, AnomalyType, float]:
        """
        Detect behavioral anomalies against baseline.
        
        Returns: (anomaly_detected, anomaly_type, anomaly_score)
        """
        if not baseline:
            return False, AnomalyType.NONE, 0.0
        
        # Track request velocity
        now = datetime.now()
        if agent_id not in self.request_history:
            self.request_history[agent_id] = []
        
        # Clean old entries (last hour)
        cutoff = now - timedelta(hours=1)
        self.request_history[agent_id] = [
            ts for ts in self.request_history[agent_id] if ts > cutoff
        ]
        self.request_history[agent_id].append(now)
        
        # Check velocity anomaly
        requests_last_hour = len(self.request_history[agent_id])
        if requests_last_hour > baseline.avg_requests_per_hour * 3:
            return True, AnomalyType.VELOCITY, 0.8
        
        # Check action drift
        if intent.primary_action not in baseline.typical_actions:
            # High-risk action not in typical behavior
            if intent.risk_category in ["FINANCIAL", "INFRASTRUCTURE"]:
                return True, AnomalyType.DRIFT, 0.7
        
        # Check scope anomaly
        if intent.target_resource not in baseline.typical_resources:
            if intent.operation_type in ["DELETE", "EXECUTE"]:
                return True, AnomalyType.SCOPE, 0.6
        
        return False, AnomalyType.NONE, 0.0
    
    async def _get_jury_votes(
        self,
        transaction_id: str,
        tenant_id: str,
        agent_id: str,
        intent: SemanticIntent,
        violations: List[APERuleMatch],
    ) -> List[JurorVote]:
        """
        Get votes from multiple juror agents.
        
        In production, this would call the actual Jury service.
        """
        # Simulate 3 jurors with different trust scores
        jurors = [
            ("juror-compliance", 0.90, "Compliance Expert"),
            ("juror-security", 0.85, "Security Analyst"),
            ("juror-business", 0.80, "Business Logic Validator"),
        ]
        
        votes = []
        for juror_id, trust_score, role in jurors:
            # Determine vote based on violations and intent
            if violations:
                vote = "REJECT"
                confidence = 0.95
                reasoning = f"Policy violations detected: {[v.rule_name for v in violations]}"
            elif intent.risk_category == "FINANCIAL" and intent.extracted_entities.get("amount", 0) > 5000:
                vote = "APPROVE" if trust_score > 0.85 else "ABSTAIN"
                confidence = 0.7
                reasoning = f"High-value transaction requires elevated trust"
            else:
                vote = "APPROVE"
                confidence = 0.9
                reasoning = f"No policy violations, action within normal parameters"
            
            votes.append(JurorVote(
                juror_id=juror_id,
                trust_score=trust_score,
                vote=vote,
                confidence=confidence,
                reasoning=reasoning,
                weight=trust_score * confidence,
            ))
        
        return votes
    
    def _calculate_consensus(
        self,
        votes: List[JurorVote],
    ) -> Tuple[bool, float]:
        """
        Calculate weighted consensus from jury votes.
        
        Returns: (unanimous, weighted_consensus_ratio)
        """
        if not votes:
            return False, 0.0
        
        total_weight = sum(v.weight for v in votes)
        approve_weight = sum(v.weight for v in votes if v.vote == "APPROVE")
        
        if total_weight == 0:
            return False, 0.0
        
        consensus = approve_weight / total_weight
        unanimous = all(v.vote == votes[0].vote for v in votes)
        
        return unanimous, consensus
    
    def _determine_verdict(
        self,
        intent: SemanticIntent,
        violations: List[APERuleMatch],
        anomaly_detected: bool,
        anomaly_score: float,
        unanimous: bool,
        weighted_consensus: float,
    ) -> Tuple[CognitiveVerdict, float, str]:
        """
        Determine final cognitive verdict.
        
        Returns: (verdict, trust_level, reasoning)
        """
        reasons = []
        
        # Critical violations = immediate BLOCK
        critical_violations = [v for v in violations if v.severity == "CRITICAL"]
        if critical_violations:
            return (
                CognitiveVerdict.BLOCK,
                0.0,
                f"Critical policy violations: {[v.rule_name for v in critical_violations]}",
            )
        
        # Any violations with high anomaly = BLOCK
        if violations and anomaly_detected and anomaly_score > 0.7:
            return (
                CognitiveVerdict.BLOCK,
                0.2,
                f"Policy violations combined with anomalous behavior (score={anomaly_score:.2f})",
            )
        
        # Violations without anomaly = HOLD for human review
        if violations:
            reasons.append(f"{len(violations)} policy violations")
            return (
                CognitiveVerdict.HOLD,
                0.4,
                f"Requires human review: {', '.join(reasons)}",
            )
        
        # High anomaly score = HOLD
        if anomaly_detected and anomaly_score > 0.6:
            return (
                CognitiveVerdict.HOLD,
                0.5,
                f"Behavioral anomaly detected (score={anomaly_score:.2f})",
            )
        
        # Check consensus
        if self.unanimous_required and not unanimous:
            return (
                CognitiveVerdict.HOLD,
                weighted_consensus,
                "Jury not unanimous - requires review",
            )
        
        if weighted_consensus < self.quorum_threshold:
            return (
                CognitiveVerdict.HOLD,
                weighted_consensus,
                f"Jury consensus {weighted_consensus:.2f} below threshold {self.quorum_threshold}",
            )
        
        # Calculate final trust level
        trust_level = weighted_consensus * intent.confidence
        if anomaly_detected:
            trust_level *= (1 - anomaly_score * 0.5)
        
        if trust_level < self.trust_threshold:
            return (
                CognitiveVerdict.HOLD,
                trust_level,
                f"Trust level {trust_level:.2f} below threshold {self.trust_threshold}",
            )
        
        # All checks passed
        return (
            CognitiveVerdict.ALLOW,
            trust_level,
            f"Cognitive audit passed: consensus={weighted_consensus:.2f}, trust={trust_level:.2f}",
        )
    
    def update_baseline(
        self,
        agent_id: str,
        action: str,
        resource: str,
        trust_score: float,
    ) -> None:
        """Update agent's behavioral baseline after successful action."""
        baseline = self._get_baseline(agent_id)
        if baseline:
            # Add action to typical actions if not present
            if action not in baseline.typical_actions:
                baseline.typical_actions.append(action)
                # Keep only last 10 typical actions
                baseline.typical_actions = baseline.typical_actions[-10:]
            
            # Update trust score history
            baseline.trust_score_history.append(trust_score)
            baseline.trust_score_history = baseline.trust_score_history[-20:]
            
            baseline.last_updated = datetime.now()


# FastAPI Router for Cognitive Auditor
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# Global auditor instance
_auditor = CognitiveAuditor()


class CognitiveAuditRequest(BaseModel):
    transaction_id: str
    tenant_id: str
    agent_id: str
    tool_id: str
    payload: Dict[str, Any]
    entitlements: List[str]


class CognitiveAuditResponse(BaseModel):
    transaction_id: str
    verdict: str
    trust_level: float
    reasoning: str
    violations_count: int
    anomaly_detected: bool
    anomaly_type: str
    unanimous: bool
    weighted_consensus: float
    audit_duration_ms: int


@router.post("/audit", response_model=CognitiveAuditResponse)
async def cognitive_audit(req: CognitiveAuditRequest) -> Any:
    """Perform cognitive audit on agent request."""
    try:
        result = await _auditor.audit(
            transaction_id=req.transaction_id,
            tenant_id=req.tenant_id,
            agent_id=req.agent_id,
            request_payload=req.payload,
            tool_id=req.tool_id,
            entitlements=req.entitlements,
        )
        
        return CognitiveAuditResponse(
            transaction_id=result.transaction_id,
            verdict=result.verdict.value,
            trust_level=result.trust_level,
            reasoning=result.reasoning,
            violations_count=len(result.violations),
            anomaly_detected=result.anomaly_detected,
            anomaly_type=result.anomaly_type.value,
            unanimous=result.unanimous,
            weighted_consensus=result.weighted_consensus,
            audit_duration_ms=result.audit_duration_ms,
        )
    except Exception as e:
        logger.error(f"Cognitive audit failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
