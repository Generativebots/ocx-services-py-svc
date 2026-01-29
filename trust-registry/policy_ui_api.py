"""
Policy Management UI API
FastAPI endpoints for policy management interface
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime

from policy_hierarchy import PolicyHierarchy, Policy, PolicyTier
from policy_versioning import PolicyVersionManager
from conflict_detector import ConflictDetector
from policy_testing import PolicyTestGenerator, PolicySimulator
from ape_metrics import *

router = APIRouter()

# Global instances
policy_hierarchy = PolicyHierarchy()
version_manager = PolicyVersionManager()
conflict_detector = ConflictDetector()
test_generator = PolicyTestGenerator()
test_simulator = PolicySimulator()


# --- Models ---

class PolicyCreateRequest(BaseModel):
    policy_id: str
    tier: str
    trigger_intent: str
    logic: Dict[str, Any]
    action: Dict[str, Any]
    confidence: float
    source_name: str
    roles: Optional[List[str]] = None
    expires_at: Optional[str] = None


class PolicyUpdateRequest(BaseModel):
    logic: Optional[Dict[str, Any]] = None
    action: Optional[Dict[str, Any]] = None
    tier: Optional[str] = None
    confidence: Optional[float] = None


class PolicyResponse(BaseModel):
    policy_id: str
    version: int
    tier: str
    trigger_intent: str
    logic: Dict[str, Any]
    action: Dict[str, Any]
    confidence: float
    source_name: str
    is_active: bool
    created_at: str
    created_by: str


# --- Endpoints ---

@router.get("/policies")
def list_policies(tier: Optional[str] = None):
    """List all active policies"""
    policies = []
    for policy in policy_hierarchy.policies.values():
        if policy.is_active and not policy.is_expired():
            if tier and policy.tier.value != tier:
                continue
            policies.append(policy.to_dict())
    
    return {"policies": policies, "count": len(policies)}


@router.post("/policies", response_model=PolicyResponse)
def create_policy(req: PolicyCreateRequest):
    """Create new policy"""
    # Create in version manager
    version = version_manager.create_policy(
        policy_id=req.policy_id,
        logic=req.logic,
        action=req.action,
        tier=req.tier,
        confidence=req.confidence,
        source_name=req.source_name,
        created_by="ui_user",
        change_summary="Created via UI"
    )
    
    # Add to hierarchy
    policy = Policy(
        policy_id=req.policy_id,
        tier=PolicyTier(req.tier),
        trigger_intent=req.trigger_intent,
        logic=req.logic,
        action=req.action,
        confidence=req.confidence,
        source_name=req.source_name,
        roles=req.roles or [],
        expires_at=datetime.fromisoformat(req.expires_at) if req.expires_at else None
    )
    policy_hierarchy.add_policy(policy)
    
    # Update metrics
    active_policies.labels(tier=req.tier).inc()
    
    return PolicyResponse(
        policy_id=version.policy_id,
        version=version.version,
        tier=version.tier,
        trigger_intent=req.trigger_intent,
        logic=version.logic,
        action=version.action,
        confidence=version.confidence,
        source_name=version.source_name,
        is_active=version.is_active,
        created_at=datetime.fromtimestamp(version.created_at).isoformat(),
        created_by=version.created_by
    )


@router.put("/policies/{policy_id}")
def update_policy(policy_id: str, req: PolicyUpdateRequest):
    """Update existing policy (creates new version)"""
    version = version_manager.update_policy(
        policy_id=policy_id,
        logic=req.logic,
        action=req.action,
        tier=req.tier,
        confidence=req.confidence,
        created_by="ui_user",
        change_summary="Updated via UI"
    )
    
    if not version:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    return {"version": version.version, "policy_id": policy_id}


@router.get("/policies/{policy_id}/versions")
def get_version_history(policy_id: str):
    """Get version history for policy"""
    versions = version_manager.get_version_history(policy_id)
    
    if not versions:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    return {
        "policy_id": policy_id,
        "versions": [v.to_dict() for v in versions],
        "total_versions": len(versions)
    }


@router.post("/policies/{policy_id}/rollback")
def rollback_policy(policy_id: str, target_version: int):
    """Rollback policy to previous version"""
    version = version_manager.rollback(
        policy_id=policy_id,
        target_version=target_version,
        created_by="ui_user"
    )
    
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    
    return {
        "policy_id": policy_id,
        "new_version": version.version,
        "rolled_back_to": target_version
    }


@router.get("/policies/{policy_id}/compare")
def compare_versions(policy_id: str, version_a: int, version_b: int):
    """Compare two versions of a policy"""
    diff = version_manager.compare_versions(policy_id, version_a, version_b)
    
    if not diff:
        raise HTTPException(status_code=404, detail="Versions not found")
    
    return diff


@router.get("/conflicts")
def detect_conflicts():
    """Detect conflicts in all policies"""
    policies = [p.to_dict() for p in policy_hierarchy.policies.values() if p.is_active]
    conflicts = conflict_detector.detect_conflicts(policies)
    
    # Update metrics
    for conflict in conflicts:
        policy_conflicts.labels(conflict_type=conflict.conflict_type.value).set(1)
    
    return {
        "conflicts": [
            {
                "type": c.conflict_type.value,
                "policy_a": c.policy_a_id,
                "policy_b": c.policy_b_id,
                "description": c.description,
                "severity": c.severity,
                "resolution": c.resolution_strategy,
                "test_case": c.test_case
            }
            for c in conflicts
        ],
        "total_conflicts": len(conflicts)
    }


@router.get("/policies/{policy_id}/test")
def generate_tests(policy_id: str):
    """Generate test cases for policy"""
    policy = policy_hierarchy.policies.get(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    test_cases = test_generator.generate_test_cases(policy.to_dict())
    
    return {
        "policy_id": policy_id,
        "test_cases": [
            {
                "name": tc.name,
                "input_data": tc.input_data,
                "expected_result": tc.expected_result,
                "expected_action": tc.expected_action,
                "description": tc.description
            }
            for tc in test_cases
        ],
        "total_tests": len(test_cases)
    }


@router.post("/policies/{policy_id}/test/run")
def run_tests(policy_id: str):
    """Run test cases for policy"""
    policy = policy_hierarchy.policies.get(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    test_cases = test_generator.generate_test_cases(policy.to_dict())
    results = test_simulator.run_test_suite(policy.to_dict(), test_cases)
    
    passed = sum(1 for r in results if r.passed)
    
    return {
        "policy_id": policy_id,
        "total_tests": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "results": [
            {
                "test_name": r.test_case.name,
                "passed": r.passed,
                "expected": r.test_case.expected_action,
                "actual": r.actual_action,
                "error": r.error
            }
            for r in results
        ]
    }


@router.get("/stats")
def get_stats():
    """Get policy statistics"""
    return policy_hierarchy.get_stats()


@router.delete("/policies/{policy_id}")
def delete_policy(policy_id: str):
    """Delete policy (deactivate)"""
    policy = policy_hierarchy.policies.get(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    policy.is_active = False
    
    # Update metrics
    active_policies.labels(tier=policy.tier.value).dec()
    
    return {"policy_id": policy_id, "status": "deactivated"}
