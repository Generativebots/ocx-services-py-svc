"""
Supabase Client for Ledger Service
===================================

Provides database operations for the Immutable Governance Ledger.
Uses Supabase instead of Cloud Spanner.
"""

import os
from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class SupabaseLedgerClient:
    """
    Supabase client for ledger operations.
    
    Tables used:
    - governance_ledger: Immutable audit entries
    """
    
    def __init__(self):
        """Initialize Supabase client."""
        from supabase import create_client
        
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY")
        
        if not url or not key:
            logger.warning("Supabase credentials not found - using in-memory mode")
            self.client = None
        else:
            self.client = create_client(url, key)
            logger.info("Supabase ledger client initialized")
    
    def store_entry(self, entry: Dict) -> bool:
        """Store ledger entry in Supabase."""
        if not self.client:
            return False
            
        try:
            self.client.table("governance_ledger").insert({
                "transaction_id": entry.get("transaction_id"),
                "agent_id": entry.get("agent_id"),
                "action": entry.get("action"),
                "policy_version": entry.get("policy_version"),
                "jury_verdict": entry.get("jury_verdict"),
                "entropy_score": entry.get("entropy_score"),
                "sop_decision": entry.get("sop_decision"),
                "pid_verified": entry.get("pid_verified"),
                "previous_hash": entry.get("previous_hash"),
                "block_hash": entry.get("hash"),
                "timestamp": entry.get("timestamp")
            }).execute()
            return True
        except Exception as e:
            logger.error(f"Failed to store ledger entry: {e}")
            return False
    
    def query_all(self) -> List[Dict]:
        """Query all ledger entries."""
        if not self.client:
            return []
            
        try:
            response = self.client.table("governance_ledger").select("*").order("timestamp").execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to query ledger: {e}")
            return []
    
    def query_by_transaction_id(self, transaction_id: str) -> Optional[Dict]:
        """Query entry by transaction ID."""
        if not self.client:
            return None
            
        try:
            response = self.client.table("governance_ledger").select("*").eq("transaction_id", transaction_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Failed to query by tx_id: {e}")
            return None
    
    def query_by_agent(self, agent_id: str, start_date: str = None, end_date: str = None) -> List[Dict]:
        """Query entries by agent ID with optional date filter."""
        if not self.client:
            return []
            
        try:
            query = self.client.table("governance_ledger").select("*").eq("agent_id", agent_id)
            
            if start_date:
                query = query.gte("timestamp", start_date)
            if end_date:
                query = query.lte("timestamp", end_date)
            
            response = query.order("timestamp", desc=True).execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to query by agent: {e}")
            return []
    
    def get_recent_entries(self, limit: int = 50) -> List[Dict]:
        """Get most recent ledger entries."""
        if not self.client:
            return []
            
        try:
            response = self.client.table("governance_ledger").select("*").order("timestamp", desc=True).limit(limit).execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to get recent entries: {e}")
            return []


# Create singleton instance
_client = None

def get_ledger_client() -> SupabaseLedgerClient:
    """Get singleton ledger client instance."""
    global _client
    if _client is None:
        _client = SupabaseLedgerClient()
    return _client
