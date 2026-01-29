"""
Policy Conflict Detection System
Detects contradictory rules and provides resolution strategies
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from json_logic_engine import JSONLogicEngine


class ConflictType(str, Enum):
    """Types of policy conflicts"""
    CONTRADICTION = "CONTRADICTION"  # Policies that contradict each other
    OVERLAP = "OVERLAP"  # Policies that partially overlap
    REDUNDANCY = "REDUNDANCY"  # Duplicate policies
    PRECEDENCE = "PRECEDENCE"  # Unclear tier precedence


@dataclass
class PolicyConflict:
    """Represents a detected conflict between policies"""
    conflict_type: ConflictType
    policy_a_id: str
    policy_b_id: str
    description: str
    severity: str  # HIGH, MEDIUM, LOW
    resolution_strategy: Optional[str] = None
    test_case: Optional[Dict[str, Any]] = None


class ConflictDetector:
    """
    Detects conflicts between policies
    
    Conflict Types:
    1. CONTRADICTION: Policy A blocks what Policy B allows
    2. OVERLAP: Policies apply to same trigger but different conditions
    3. REDUNDANCY: Policies are functionally identical
    4. PRECEDENCE: Same tier policies with conflicting actions
    """
    
    def __init__(self):
        self.logic_engine = JSONLogicEngine()
    
    def detect_conflicts(
        self,
        policies: List[Dict[str, Any]]
    ) -> List[PolicyConflict]:
        """
        Detect all conflicts in policy set
        
        Returns:
            List of detected conflicts
        """
        conflicts = []
        
        # Compare each pair of policies
        for i, policy_a in enumerate(policies):
            for policy_b in policies[i+1:]:
                # Skip if different triggers
                if policy_a.get("trigger_intent") != policy_b.get("trigger_intent"):
                    continue
                
                # Check for contradictions
                contradiction = self._check_contradiction(policy_a, policy_b)
                if contradiction:
                    conflicts.append(contradiction)
                
                # Check for redundancy
                redundancy = self._check_redundancy(policy_a, policy_b)
                if redundancy:
                    conflicts.append(redundancy)
                
                # Check for precedence issues
                precedence = self._check_precedence(policy_a, policy_b)
                if precedence:
                    conflicts.append(precedence)
        
        return conflicts
    
    def _check_contradiction(
        self,
        policy_a: Dict[str, Any],
        policy_b: Dict[str, Any]
    ) -> Optional[PolicyConflict]:
        """
        Check if policies contradict each other
        
        Example:
        Policy A: amount > 500 → BLOCK
        Policy B: amount > 500 → ALLOW
        """
        logic_a = policy_a.get("logic", {})
        logic_b = policy_b.get("logic", {})
        action_a = policy_a.get("action", {})
        action_b = policy_b.get("action", {})
        
        # Check if logic is similar but actions differ
        if self._logic_similar(logic_a, logic_b):
            action_a_fail = action_a.get("on_fail", "BLOCK")
            action_b_fail = action_b.get("on_fail", "BLOCK")
            
            if action_a_fail != action_b_fail:
                # Generate test case
                test_case = self._generate_test_case(logic_a)
                
                return PolicyConflict(
                    conflict_type=ConflictType.CONTRADICTION,
                    policy_a_id=policy_a.get("policy_id", "unknown"),
                    policy_b_id=policy_b.get("policy_id", "unknown"),
                    description=f"Policies have similar logic but different actions: {action_a_fail} vs {action_b_fail}",
                    severity="HIGH",
                    resolution_strategy="Use tier precedence or merge policies",
                    test_case=test_case
                )
        
        return None
    
    def _check_redundancy(
        self,
        policy_a: Dict[str, Any],
        policy_b: Dict[str, Any]
    ) -> Optional[PolicyConflict]:
        """Check if policies are redundant (duplicate)"""
        logic_a = policy_a.get("logic", {})
        logic_b = policy_b.get("logic", {})
        action_a = policy_a.get("action", {})
        action_b = policy_b.get("action", {})
        
        # Check if both logic and action are identical
        if logic_a == logic_b and action_a == action_b:
            return PolicyConflict(
                conflict_type=ConflictType.REDUNDANCY,
                policy_a_id=policy_a.get("policy_id", "unknown"),
                policy_b_id=policy_b.get("policy_id", "unknown"),
                description="Policies are functionally identical",
                severity="LOW",
                resolution_strategy="Remove one policy or merge into single policy"
            )
        
        return None
    
    def _check_precedence(
        self,
        policy_a: Dict[str, Any],
        policy_b: Dict[str, Any]
    ) -> Optional[PolicyConflict]:
        """Check for unclear precedence (same tier, different actions)"""
        tier_a = policy_a.get("tier", "DYNAMIC")
        tier_b = policy_b.get("tier", "DYNAMIC")
        
        # Only check if same tier
        if tier_a != tier_b:
            return None
        
        action_a = policy_a.get("action", {}).get("on_fail", "BLOCK")
        action_b = policy_b.get("action", {}).get("on_fail", "BLOCK")
        
        if action_a != action_b:
            return PolicyConflict(
                conflict_type=ConflictType.PRECEDENCE,
                policy_a_id=policy_a.get("policy_id", "unknown"),
                policy_b_id=policy_b.get("policy_id", "unknown"),
                description=f"Same tier ({tier_a}) but different actions: {action_a} vs {action_b}",
                severity="MEDIUM",
                resolution_strategy="Assign different tiers or merge policies"
            )
        
        return None
    
    def _logic_similar(self, logic_a: Dict[str, Any], logic_b: Dict[str, Any]) -> bool:
        """Check if two logic expressions are similar"""
        # Simple comparison for now
        # In production, would use semantic similarity
        return logic_a == logic_b
    
    def _generate_test_case(self, logic: Dict[str, Any]) -> Dict[str, Any]:
        """Generate test case that would trigger the logic"""
        variables = self.logic_engine.extract_variables(logic)
        
        test_case = {}
        for var in variables:
            # Generate sample value based on variable name
            if "amount" in var.lower():
                test_case[var] = 1000
            elif "vendor" in var.lower():
                test_case[var] = "TEST_VENDOR"
            else:
                test_case[var] = "test_value"
        
        return test_case


# Example usage
if __name__ == "__main__":
    detector = ConflictDetector()
    
    # Test policies
    policies = [
        {
            "policy_id": "PURCHASE_001",
            "trigger_intent": "mcp.call_tool('execute_payment')",
            "logic": {">": [{"var": "amount"}, 500]},
            "action": {"on_fail": "BLOCK", "on_pass": "ALLOW"},
            "tier": "CONTEXTUAL"
        },
        {
            "policy_id": "PURCHASE_002",
            "trigger_intent": "mcp.call_tool('execute_payment')",
            "logic": {">": [{"var": "amount"}, 500]},
            "action": {"on_fail": "ALLOW", "on_pass": "ALLOW"},
            "tier": "CONTEXTUAL"
        },
        {
            "policy_id": "PURCHASE_003",
            "trigger_intent": "mcp.call_tool('execute_payment')",
            "logic": {">": [{"var": "amount"}, 500]},
            "action": {"on_fail": "BLOCK", "on_pass": "ALLOW"},
            "tier": "CONTEXTUAL"
        }
    ]
    
    conflicts = detector.detect_conflicts(policies)
    
    print(f"Detected {len(conflicts)} conflicts:")
    for conflict in conflicts:
        print(f"\n{conflict.conflict_type.value} ({conflict.severity}):")
        print(f"  Policies: {conflict.policy_a_id} vs {conflict.policy_b_id}")
        print(f"  Description: {conflict.description}")
        print(f"  Resolution: {conflict.resolution_strategy}")
        if conflict.test_case:
            print(f"  Test case: {conflict.test_case}")
