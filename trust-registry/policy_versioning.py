"""
Policy Versioning System
Tracks policy changes, enables rollback, and provides version comparison
"""

import time
import json
import hashlib
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class PolicyVersion:
    """Represents a specific version of a policy"""
    policy_id: str
    version: int
    logic: Dict[str, Any]
    action: Dict[str, Any]
    tier: str
    confidence: float
    source_name: str
    created_at: float
    created_by: str
    change_summary: str
    content_hash: str
    is_active: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "logic": self.logic,
            "action": self.action,
            "tier": self.tier,
            "confidence": self.confidence,
            "source_name": self.source_name,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "change_summary": self.change_summary,
            "content_hash": self.content_hash,
            "is_active": self.is_active
        }


class PolicyVersionManager:
    """
    Manages policy versions with rollback capability
    
    Features:
    - Track all policy changes
    - Compare versions
    - Rollback to previous version
    - Audit trail of changes
    """
    
    def __init__(self):
        self.versions: Dict[str, List[PolicyVersion]] = {}  # policy_id -> versions
    
    def create_policy(
        self,
        policy_id: str,
        logic: Dict[str, Any],
        action: Dict[str, Any],
        tier: str,
        confidence: float,
        source_name: str,
        created_by: str,
        change_summary: str = "Initial version"
    ) -> PolicyVersion:
        """
        Create new policy (version 1)
        
        Returns:
            PolicyVersion object
        """
        content_hash = self._calculate_hash(logic, action)
        
        version = PolicyVersion(
            policy_id=policy_id,
            version=1,
            logic=logic,
            action=action,
            tier=tier,
            confidence=confidence,
            source_name=source_name,
            created_at=time.time(),
            created_by=created_by,
            change_summary=change_summary,
            content_hash=content_hash,
            is_active=True
        )
        
        self.versions[policy_id] = [version]
        return version
    
    def update_policy(
        self,
        policy_id: str,
        logic: Optional[Dict[str, Any]] = None,
        action: Optional[Dict[str, Any]] = None,
        tier: Optional[str] = None,
        confidence: Optional[float] = None,
        created_by: str = "system",
        change_summary: str = "Updated policy"
    ) -> Optional[PolicyVersion]:
        """
        Update existing policy (creates new version)
        
        Returns:
            New PolicyVersion, or None if policy doesn't exist
        """
        if policy_id not in self.versions:
            return None
        
        # Get current version
        current = self.get_active_version(policy_id)
        if not current:
            return None
        
        # Create new version with changes
        new_logic = logic if logic is not None else current.logic
        new_action = action if action is not None else current.action
        new_tier = tier if tier is not None else current.tier
        new_confidence = confidence if confidence is not None else current.confidence
        
        content_hash = self._calculate_hash(new_logic, new_action)
        
        # Check if content actually changed
        if content_hash == current.content_hash:
            print(f"⚠️  No changes detected for policy {policy_id}")
            return current
        
        new_version_num = current.version + 1
        
        new_version = PolicyVersion(
            policy_id=policy_id,
            version=new_version_num,
            logic=new_logic,
            action=new_action,
            tier=new_tier,
            confidence=new_confidence,
            source_name=current.source_name,
            created_at=time.time(),
            created_by=created_by,
            change_summary=change_summary,
            content_hash=content_hash,
            is_active=True
        )
        
        # Deactivate current version
        current.is_active = False
        
        # Add new version
        self.versions[policy_id].append(new_version)
        
        return new_version
    
    def rollback(
        self,
        policy_id: str,
        target_version: int,
        created_by: str = "system"
    ) -> Optional[PolicyVersion]:
        """
        Rollback policy to previous version
        
        Returns:
            New PolicyVersion (copy of target version), or None if not found
        """
        if policy_id not in self.versions:
            return None
        
        # Find target version
        target = None
        for version in self.versions[policy_id]:
            if version.version == target_version:
                target = version
                break
        
        if not target:
            print(f"❌ Version {target_version} not found for policy {policy_id}")
            return None
        
        # Create new version as copy of target
        current = self.get_active_version(policy_id)
        new_version_num = current.version + 1 if current else 1
        
        rollback_version = PolicyVersion(
            policy_id=policy_id,
            version=new_version_num,
            logic=target.logic,
            action=target.action,
            tier=target.tier,
            confidence=target.confidence,
            source_name=target.source_name,
            created_at=time.time(),
            created_by=created_by,
            change_summary=f"Rollback to version {target_version}",
            content_hash=target.content_hash,
            is_active=True
        )
        
        # Deactivate current version
        if current:
            current.is_active = False
        
        # Add rollback version
        self.versions[policy_id].append(rollback_version)
        
        return rollback_version
    
    def get_active_version(self, policy_id: str) -> Optional[PolicyVersion]:
        """Get currently active version"""
        if policy_id not in self.versions:
            return None
        
        for version in reversed(self.versions[policy_id]):
            if version.is_active:
                return version
        
        return None
    
    def get_version(self, policy_id: str, version_num: int) -> Optional[PolicyVersion]:
        """Get specific version"""
        if policy_id not in self.versions:
            return None
        
        for version in self.versions[policy_id]:
            if version.version == version_num:
                return version
        
        return None
    
    def get_version_history(self, policy_id: str) -> List[PolicyVersion]:
        """Get all versions of a policy"""
        return self.versions.get(policy_id, [])
    
    def compare_versions(
        self,
        policy_id: str,
        version_a: int,
        version_b: int
    ) -> Optional[Dict[str, Any]]:
        """
        Compare two versions of a policy
        
        Returns:
            Dict with differences, or None if versions not found
        """
        ver_a = self.get_version(policy_id, version_a)
        ver_b = self.get_version(policy_id, version_b)
        
        if not ver_a or not ver_b:
            return None
        
        diff = {
            "policy_id": policy_id,
            "version_a": version_a,
            "version_b": version_b,
            "changes": {}
        }
        
        # Compare fields
        if ver_a.logic != ver_b.logic:
            diff["changes"]["logic"] = {
                "from": ver_a.logic,
                "to": ver_b.logic
            }
        
        if ver_a.action != ver_b.action:
            diff["changes"]["action"] = {
                "from": ver_a.action,
                "to": ver_b.action
            }
        
        if ver_a.tier != ver_b.tier:
            diff["changes"]["tier"] = {
                "from": ver_a.tier,
                "to": ver_b.tier
            }
        
        if ver_a.confidence != ver_b.confidence:
            diff["changes"]["confidence"] = {
                "from": ver_a.confidence,
                "to": ver_b.confidence
            }
        
        return diff
    
    def _calculate_hash(self, logic: Dict[str, Any], action: Dict[str, Any]) -> str:
        """Calculate content hash for version comparison"""
        content = json.dumps({"logic": logic, "action": action}, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()


# Example usage
if __name__ == "__main__":
    manager = PolicyVersionManager()
    
    # Create policy
    v1 = manager.create_policy(
        policy_id="PURCHASE_001",
        logic={">": [{"var": "amount"}, 500]},
        action={"on_fail": "BLOCK", "on_pass": "ALLOW"},
        tier="CONTEXTUAL",
        confidence=0.95,
        source_name="Procurement SOP",
        created_by="ape_engine",
        change_summary="Initial extraction from SOP"
    )
    print(f"Created version {v1.version}")
    
    # Update policy (increase threshold)
    v2 = manager.update_policy(
        policy_id="PURCHASE_001",
        logic={">": [{"var": "amount"}, 1000]},
        created_by="admin",
        change_summary="Increased threshold to $1000"
    )
    print(f"Updated to version {v2.version}")
    
    # Update again (add required signal)
    v3 = manager.update_policy(
        policy_id="PURCHASE_001",
        action={
            "on_fail": "INTERCEPT_AND_ESCALATE",
            "on_pass": "ALLOW",
            "required_signals": ["CTO_SIGNATURE"]
        },
        created_by="admin",
        change_summary="Added CTO signature requirement"
    )
    print(f"Updated to version {v3.version}")
    
    # Compare versions
    diff = manager.compare_versions("PURCHASE_001", 1, 3)
    print(f"Changes from v1 to v3: {json.dumps(diff, indent=2)}")
    
    # Rollback to v2
    v4 = manager.rollback("PURCHASE_001", 2, created_by="admin")
    print(f"Rolled back to v2, created new version {v4.version}")
    
    # Get version history
    history = manager.get_version_history("PURCHASE_001")
    print(f"\nVersion history ({len(history)} versions):")
    for ver in history:
        active = "✅" if ver.is_active else "  "
        print(f"  {active} v{ver.version}: {ver.change_summary} (by {ver.created_by})")
