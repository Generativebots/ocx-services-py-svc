"""
3-Tier Policy Hierarchy System
Implements GLOBAL → CONTEXTUAL → DYNAMIC precedence
"""

from enum import Enum
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
import logging
logger = logging.getLogger(__name__)


class PolicyTier(str, Enum):
    """Policy tier levels with precedence"""
    GLOBAL = "GLOBAL"          # Priority 1: Hard constraints (e.g., "No data leaves VPC")
    CONTEXTUAL = "CONTEXTUAL"  # Priority 2: Role-based guardrails
    DYNAMIC = "DYNAMIC"        # Priority 3: Temporary project-specific rules


@dataclass
class Policy:
    """Policy object with tier, logic, and metadata"""
    policy_id: str
    tier: PolicyTier
    trigger_intent: str
    logic: Dict[str, Any]
    action: Dict[str, Any]
    confidence: float
    source_name: str
    
    # Optional fields
    roles: List[str] = field(default_factory=list)  # For CONTEXTUAL tier
    expires_at: Optional[datetime] = None  # For DYNAMIC tier
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    is_active: bool = True
    
    def is_expired(self) -> bool:
        """Check if policy has expired (for DYNAMIC tier)"""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at
    
    def applies_to_role(self, role: str) -> bool:
        """Check if policy applies to given role (for CONTEXTUAL tier)"""
        if self.tier != PolicyTier.CONTEXTUAL:
            return True  # GLOBAL and DYNAMIC apply to all roles
        return role in self.roles if self.roles else True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            "policy_id": self.policy_id,
            "tier": self.tier.value,
            "trigger_intent": self.trigger_intent,
            "logic": self.logic,
            "action": self.action,
            "confidence": self.confidence,
            "source_name": self.source_name,
            "roles": self.roles,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "is_active": self.is_active
        }


class PolicyHierarchy:
    """Manages 3-tier policy hierarchy with precedence"""
    
    def __init__(self) -> None:
        self.policies: Dict[str, Policy] = {}
    
    def add_policy(self, policy: Policy) -> None:
        """Add policy to hierarchy"""
        self.policies[policy.policy_id] = policy
    
    def get_applicable_policies(
        self,
        trigger_intent: str,
        role: Optional[str] = None
    ) -> List[Policy]:
        """
        Get policies applicable to trigger intent and role
        Returns policies in tier precedence order: GLOBAL → CONTEXTUAL → DYNAMIC
        """
        applicable = []
        
        for policy in self.policies.values():
            # Skip inactive policies
            if not policy.is_active:
                continue
            
            # Skip expired policies
            if policy.is_expired():
                continue
            
            # Check trigger intent match
            if policy.trigger_intent != trigger_intent and policy.trigger_intent != "*":
                continue
            
            # Check role applicability
            if role and not policy.applies_to_role(role):
                continue
            
            applicable.append(policy)
        
        # Sort by tier precedence
        tier_order = {
            PolicyTier.GLOBAL: 0,
            PolicyTier.CONTEXTUAL: 1,
            PolicyTier.DYNAMIC: 2
        }
        applicable.sort(key=lambda p: tier_order[p.tier])
        
        return applicable
    
    def evaluate_with_precedence(
        self,
        trigger_intent: str,
        data: Dict[str, Any],
        role: Optional[str] = None,
        logic_engine: Any = None
    ) -> tuple[bool, Optional[Policy], Optional[str]]:
        """
        Evaluate policies with tier precedence
        
        Returns:
            (is_allowed, violated_policy, action)
            
        Precedence Rules:
        1. GLOBAL policies are evaluated first (fail-fast)
        2. If GLOBAL passes, check CONTEXTUAL
        3. If CONTEXTUAL passes, check DYNAMIC
        4. First violation in tier order blocks action
        """
        from json_logic_engine import JSONLogicEngine

        
        if logic_engine is None:
            logic_engine = JSONLogicEngine()
        
        applicable_policies = self.get_applicable_policies(trigger_intent, role)
        
        for policy in applicable_policies:
            # Evaluate JSON-Logic
            violates = logic_engine.evaluate(policy.logic, data)
            
            if violates:
                # Policy violation detected
                action = policy.action.get("on_fail", "BLOCK")
                return False, policy, action
        
        # All policies passed
        return True, None, "ALLOW"
    
    def cleanup_expired(self) -> int:
        """Remove expired DYNAMIC policies"""
        expired_count = 0
        to_remove = []
        
        for policy_id, policy in self.policies.items():
            if policy.tier == PolicyTier.DYNAMIC and policy.is_expired():
                to_remove.append(policy_id)
                expired_count += 1
        
        for policy_id in to_remove:
            del self.policies[policy_id]
        
        return expired_count
    
    def get_stats(self) -> Dict[str, int]:
        """Get policy statistics by tier"""
        stats = {
            "GLOBAL": 0,
            "CONTEXTUAL": 0,
            "DYNAMIC": 0,
            "total": len(self.policies),
            "active": sum(1 for p in self.policies.values() if p.is_active),
            "expired": sum(1 for p in self.policies.values() if p.is_expired())
        }
        
        for policy in self.policies.values():
            stats[policy.tier.value] += 1
        
        return stats


# Example usage
if __name__ == "__main__":
    hierarchy = PolicyHierarchy()
    
    # GLOBAL: No data exfiltration
    global_policy = Policy(
        policy_id="GLOBAL_001",
        tier=PolicyTier.GLOBAL,
        trigger_intent="mcp.call_tool('send_external_request')",
        logic={"==": [{"var": "destination_type"}, "external"]},
        action={"on_fail": "BLOCK", "on_pass": "ALLOW"},
        confidence=0.99,
        source_name="Security Policy v1.0"
    )
    hierarchy.add_policy(global_policy)
    
    # CONTEXTUAL: Procurement agent limits
    contextual_policy = Policy(
        policy_id="CONTEXTUAL_001",
        tier=PolicyTier.CONTEXTUAL,
        trigger_intent="mcp.call_tool('execute_payment')",
        logic={">": [{"var": "amount"}, 500]},
        action={"on_fail": "INTERCEPT_AND_ESCALATE", "on_pass": "ALLOW"},
        confidence=0.95,
        source_name="Procurement SOP",
        roles=["procurement_agent"]
    )
    hierarchy.add_policy(contextual_policy)
    
    # DYNAMIC: Project-specific rule (expires in 7 days)
    dynamic_policy = Policy(
        policy_id="DYNAMIC_001",
        tier=PolicyTier.DYNAMIC,
        trigger_intent="mcp.call_tool('send_message')",
        logic={"in": ["urgent", {"var": "content"}]},
        action={"on_fail": "FLAG", "on_pass": "ALLOW"},
        confidence=0.8,
        source_name="Project Alpha Brief",
        expires_at=datetime.utcnow() + timedelta(days=7)
    )
    hierarchy.add_policy(dynamic_policy)
    
    # Test evaluation
    print("Stats:", hierarchy.get_stats())
    
    # Test 1: External request (GLOBAL violation)
    data1 = {"destination_type": "external", "destination": "https://evil.com"}
    allowed, policy, action = hierarchy.evaluate_with_precedence(
        "mcp.call_tool('send_external_request')",
        data1
    )
    print(f"Test 1: allowed={allowed}, policy={policy.policy_id if policy else None}, action={action}")
    
    # Test 2: Payment by procurement agent (CONTEXTUAL violation)
    data2 = {"amount": 1000}
    allowed, policy, action = hierarchy.evaluate_with_precedence(
        "mcp.call_tool('execute_payment')",
        data2,
        role="procurement_agent"
    )
    print(f"Test 2: allowed={allowed}, policy={policy.policy_id if policy else None}, action={action}")
