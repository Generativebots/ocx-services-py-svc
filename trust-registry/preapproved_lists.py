"""
Pre-Approved Lists Management
Supports whitelist/blacklist for vendors, endpoints, etc.
Stored in Redis for <1ms lookup
"""

import redis
import json
from typing import List, Optional, Dict, Any
from enum import Enum


class ListType(str, Enum):
    """Types of pre-approved lists"""
    WHITELIST = "whitelist"
    BLACKLIST = "blacklist"


class PreApprovedListManager:
    """
    Manages pre-approved lists (whitelist/blacklist)
    Stored in Redis for fast lookup in JSON-Logic evaluation
    """
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
    
    def create_list(
        self,
        list_name: str,
        list_type: ListType,
        items: List[str],
        description: Optional[str] = None
    ) -> bool:
        """
        Create a new pre-approved list
        
        Args:
            list_name: Unique identifier (e.g., "PRE_APPROVED_SECURITY_VENDORS")
            list_type: WHITELIST or BLACKLIST
            items: List of approved/blocked items
            description: Human-readable description
            
        Returns:
            True if created successfully
        """
        key = f"list:{list_name}"
        
        # Store list metadata
        metadata = {
            "name": list_name,
            "type": list_type.value,
            "description": description or "",
            "item_count": len(items)
        }
        
        try:
            # Store metadata as hash
            self.redis.hset(f"{key}:meta", mapping=metadata)
            
            # Store items as set for O(1) membership check
            if items:
                self.redis.sadd(key, *items)
            
            # Add to list registry
            self.redis.sadd("lists:registry", list_name)
            
            return True
        except Exception as e:
            print(f"❌ Failed to create list {list_name}: {e}")
            return False
    
    def add_items(self, list_name: str, items: List[str]) -> int:
        """
        Add items to existing list
        
        Returns:
            Number of items added
        """
        key = f"list:{list_name}"
        
        try:
            added = self.redis.sadd(key, *items)
            
            # Update item count
            self.redis.hincrby(f"{key}:meta", "item_count", added)
            
            return added
        except Exception as e:
            print(f"❌ Failed to add items to {list_name}: {e}")
            return 0
    
    def remove_items(self, list_name: str, items: List[str]) -> int:
        """
        Remove items from list
        
        Returns:
            Number of items removed
        """
        key = f"list:{list_name}"
        
        try:
            removed = self.redis.srem(key, *items)
            
            # Update item count
            self.redis.hincrby(f"{key}:meta", "item_count", -removed)
            
            return removed
        except Exception as e:
            print(f"❌ Failed to remove items from {list_name}: {e}")
            return 0
    
    def check_membership(self, list_name: str, item: str) -> bool:
        """
        Check if item is in list (O(1) lookup)
        
        Returns:
            True if item is in list
        """
        key = f"list:{list_name}"
        return self.redis.sismember(key, item)
    
    def get_list(self, list_name: str) -> Optional[Dict[str, Any]]:
        """
        Get list metadata and items
        
        Returns:
            Dict with metadata and items, or None if not found
        """
        key = f"list:{list_name}"
        
        try:
            # Get metadata
            metadata = self.redis.hgetall(f"{key}:meta")
            if not metadata:
                return None
            
            # Get items
            items = list(self.redis.smembers(key))
            
            return {
                "name": metadata.get("name", "").decode(),
                "type": metadata.get("type", "").decode(),
                "description": metadata.get("description", "").decode(),
                "items": [item.decode() if isinstance(item, bytes) else item for item in items],
                "item_count": len(items)
            }
        except Exception as e:
            print(f"❌ Failed to get list {list_name}: {e}")
            return None
    
    def list_all(self) -> List[str]:
        """Get all list names"""
        try:
            lists = self.redis.smembers("lists:registry")
            return [lst.decode() if isinstance(lst, bytes) else lst for lst in lists]
        except Exception as e:
            print(f"❌ Failed to list all lists: {e}")
            return []
    
    def delete_list(self, list_name: str) -> bool:
        """Delete a list"""
        key = f"list:{list_name}"
        
        try:
            # Delete items
            self.redis.delete(key)
            
            # Delete metadata
            self.redis.delete(f"{key}:meta")
            
            # Remove from registry
            self.redis.srem("lists:registry", list_name)
            
            return True
        except Exception as e:
            print(f"❌ Failed to delete list {list_name}: {e}")
            return False


# Common pre-approved lists
COMMON_LISTS = {
    "PRE_APPROVED_SECURITY_VENDORS": [
        "VENDOR_CROWDSTRIKE",
        "VENDOR_OKTA",
        "VENDOR_DATADOG",
        "VENDOR_PAGERDUTY"
    ],
    "APPROVED_EXTERNAL_ENDPOINTS": [
        "https://api.stripe.com",
        "https://api.github.com",
        "https://api.slack.com"
    ],
    "BLOCKED_COUNTRIES": [
        "OFAC_SANCTIONED_COUNTRY_1",
        "OFAC_SANCTIONED_COUNTRY_2"
    ],
    "APPROVED_DATA_DESTINATIONS": [
        "s3://company-data-vpc",
        "gs://company-data-vpc"
    ]
}


def initialize_common_lists(manager: PreApprovedListManager):
    """Initialize common pre-approved lists"""
    for list_name, items in COMMON_LISTS.items():
        list_type = ListType.BLACKLIST if "BLOCKED" in list_name else ListType.WHITELIST
        manager.create_list(
            list_name=list_name,
            list_type=list_type,
            items=items,
            description=f"Auto-generated {list_type.value} for {list_name}"
        )


# Example usage
if __name__ == "__main__":
    # Connect to Redis
    r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=False)
    
    # Create manager
    manager = PreApprovedListManager(r)
    
    # Initialize common lists
    initialize_common_lists(manager)
    
    # Test membership
    is_approved = manager.check_membership(
        "PRE_APPROVED_SECURITY_VENDORS",
        "VENDOR_CROWDSTRIKE"
    )
    print(f"CrowdStrike approved: {is_approved}")
    
    # List all lists
    all_lists = manager.list_all()
    print(f"All lists: {all_lists}")
    
    # Get list details
    security_vendors = manager.get_list("PRE_APPROVED_SECURITY_VENDORS")
    print(f"Security vendors: {security_vendors}")
