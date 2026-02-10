"""
Complete Supabase Client for OCX Jury Service
Provides all CRUD operations for trust calculation and verdict recording.
P2 FIX #12: Uses SupabaseRetryMixin for exponential backoff on all operations.
"""

import os
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from supabase import create_client, Client
from config.supabase_retry import SupabaseRetryMixin
import logging
logger = logging.getLogger(__name__)



class SupabaseClient(SupabaseRetryMixin):
    """Enhanced Supabase client with all OCX database operations.
    P2 FIX #12: Inherits SupabaseRetryMixin for automatic retry on failures."""
    
    def __init__(self) -> None:
        """Initialize Supabase client from environment variables"""
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY")
        
        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
        
        self.client: Client = create_client(url, key)
    
    # ========================================================================
    # AGENTS OPERATIONS
    # ========================================================================
    
    def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get agent by ID"""
        response = self.client.table("agents").select("*").eq("agent_id", agent_id).execute()
        return response.data[0] if response.data else None
    
    def create_agent(self, agent_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new agent"""
        response = self.client.table("agents").insert(agent_data).execute()
        return response.data[0]
    
    def update_agent(self, agent_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update an agent"""
        response = self.client.table("agents").update(updates).eq("agent_id", agent_id).execute()
        return response.data[0] if response.data else None
    
    def list_agents(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List all agents"""
        response = self.client.table("agents").select("*").limit(limit).execute()
        return response.data
    
    # ========================================================================
    # TRUST SCORES OPERATIONS
    # ========================================================================
    
    def get_trust_scores(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get trust scores for an agent"""
        response = self.client.table("trust_scores").select("*").eq("agent_id", agent_id).execute()
        return response.data[0] if response.data else None
    
    def upsert_trust_scores(self, scores_data: Dict[str, Any]) -> Dict[str, Any]:
        """Upsert trust scores"""
        response = self.client.table("trust_scores").upsert(scores_data).execute()
        return response.data[0]
    
    def calculate_and_store_trust(
        self,
        agent_id: str,
        audit_score: float,
        reputation_score: float,
        attestation_score: float,
        history_score: float
    ) -> Dict[str, Any]:
        """Calculate and store trust scores"""
        scores_data = {
            "agent_id": agent_id,
            "audit_score": audit_score,
            "reputation_score": reputation_score,
            "attestation_score": attestation_score,
            "history_score": history_score
        }
        return self.upsert_trust_scores(scores_data)
    
    # ========================================================================
    # REPUTATION AUDIT OPERATIONS
    # ========================================================================
    
    def create_audit_entry(self, audit_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new audit log entry"""
        response = self.client.table("reputation_audit").insert(audit_data).execute()
        return response.data[0]
    
    def get_audit_history(self, agent_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get audit history for an agent"""
        response = (
            self.client.table("reputation_audit")
            .select("*")
            .eq("agent_id", agent_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data
    
    def get_success_count(self, agent_id: str, hours: int = 24) -> int:
        """Get successful transaction count for an agent"""
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        response = (
            self.client.table("reputation_audit")
            .select("audit_id", count="exact")
            .eq("agent_id", agent_id)
            .eq("verdict", "SUCCESS")
            .gte("created_at", cutoff)
            .execute()
        )
        return response.count or 0
    
    # ========================================================================
    # VERDICTS OPERATIONS
    # ========================================================================
    
    def record_verdict(self, verdict_data: Dict[str, Any]) -> Dict[str, Any]:
        """Record a trust verdict"""
        response = self.client.table("verdicts").insert(verdict_data).execute()
        return response.data[0]
    
    def get_recent_verdicts(self, agent_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent verdicts for an agent"""
        response = (
            self.client.table("verdicts")
            .select("*")
            .eq("agent_id", agent_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data
    
    def get_verdict_stats(self, agent_id: str) -> Dict[str, int]:
        """Get verdict statistics for an agent"""
        response = self.client.table("verdicts").select("action").eq("agent_id", agent_id).execute()
        
        stats = {"ALLOW": 0, "BLOCK": 0, "HOLD": 0}
        for verdict in response.data:
            action = verdict.get("action", "ALLOW")
            stats[action] = stats.get(action, 0) + 1
        
        return stats
    
    # ========================================================================
    # HANDSHAKE OPERATIONS
    # ========================================================================
    
    def create_handshake_session(self, session_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new handshake session"""
        response = self.client.table("handshake_sessions").insert(session_data).execute()
        return response.data[0]
    
    def get_handshake_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get handshake session by ID"""
        response = (
            self.client.table("handshake_sessions")
            .select("*")
            .eq("session_id", session_id)
            .execute()
        )
        return response.data[0] if response.data else None
    
    def update_handshake_session(self, session_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update handshake session"""
        response = (
            self.client.table("handshake_sessions")
            .update(updates)
            .eq("session_id", session_id)
            .execute()
        )
        return response.data[0] if response.data else None
    
    # ========================================================================
    # AGENT IDENTITY OPERATIONS
    # ========================================================================
    
    def create_agent_identity(self, identity_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create PID to AgentID mapping"""
        response = self.client.table("agent_identities").upsert(identity_data).execute()
        return response.data[0]
    
    def get_agent_identity(self, pid: int) -> Optional[Dict[str, Any]]:
        """Get agent identity by PID"""
        response = self.client.table("agent_identities").select("*").eq("pid", pid).execute()
        return response.data[0] if response.data else None
    
    # ========================================================================
    # QUARANTINE OPERATIONS
    # ========================================================================
    
    def create_quarantine_record(self, record_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a quarantine record"""
        response = self.client.table("quarantine_records").insert(record_data).execute()
        return response.data[0]
    
    def get_active_quarantines(self, agent_id: str) -> List[Dict[str, Any]]:
        """Get active quarantines for an agent"""
        response = (
            self.client.table("quarantine_records")
            .select("*")
            .eq("agent_id", agent_id)
            .eq("is_active", True)
            .execute()
        )
        return response.data
    
    def is_quarantined(self, agent_id: str) -> bool:
        """Check if agent is currently quarantined"""
        quarantines = self.get_active_quarantines(agent_id)
        return len(quarantines) > 0
    
    # ========================================================================
    # REWARD OPERATIONS
    # ========================================================================
    
    def create_reward_distribution(self, distribution_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a reward distribution record"""
        response = self.client.table("reward_distributions").insert(distribution_data).execute()
        return response.data[0]
    
    def get_reward_history(self, agent_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get reward history for an agent"""
        response = (
            self.client.table("reward_distributions")
            .select("*")
            .eq("agent_id", agent_id)
            .order("distributed_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data
    
    # ========================================================================
    # HIGH-LEVEL OPERATIONS FOR TRUST ENGINE
    # ========================================================================
    
    def get_agent_context(self, agent_id: str) -> Dict[str, Any]:
        """Get complete context for an agent (for trust calculation)"""
        agent = self.get_agent(agent_id)
        trust_scores = self.get_trust_scores(agent_id)
        recent_verdicts = self.get_recent_verdicts(agent_id, limit=10)
        verdict_stats = self.get_verdict_stats(agent_id)
        is_quarantined = self.is_quarantined(agent_id)
        
        return {
            "agent": agent,
            "trust_scores": trust_scores,
            "recent_verdicts": recent_verdicts,
            "verdict_stats": verdict_stats,
            "is_quarantined": is_quarantined
        }
    
    def record_trust_decision(
        self,
        request_id: str,
        agent_id: str,
        action: str,
        trust_level: float,
        reasoning: str,
        audit_verdict: str = "SUCCESS",
        tax_levied: int = 0
    ) -> Dict[str, Any]:
        """Record a complete trust decision (verdict + audit)"""
        # Record verdict
        verdict_data = {
            "request_id": request_id,
            "agent_id": agent_id,
            "action": action,
            "trust_level": trust_level,
            "reasoning": reasoning
        }
        verdict = self.record_verdict(verdict_data)
        
        # Record audit entry
        audit_data = {
            "agent_id": agent_id,
            "transaction_id": request_id,
            "verdict": audit_verdict,
            "tax_levied": tax_levied,
            "reasoning": reasoning
        }
        audit = self.create_audit_entry(audit_data)
        
        return {
            "verdict": verdict,
            "audit": audit
        }
    
    def apply_penalty(self, agent_id: str, amount: int, reason: str) -> Dict[str, Any]:
        """Apply penalty to an agent"""
        agent = self.get_agent(agent_id)
        if not agent:
            raise ValueError(f"Agent not found: {agent_id}")
        
        new_balance = agent["gov_tax_balance"] - amount
        new_drift = agent["behavioral_drift"] + 0.1
        
        updates = {
            "gov_tax_balance": new_balance,
            "behavioral_drift": new_drift
        }
        
        updated_agent = self.update_agent(agent_id, updates)
        
        # Record audit
        self.create_audit_entry({
            "agent_id": agent_id,
            "verdict": "FAILURE",
            "tax_levied": amount,
            "reasoning": reason
        })
        
        return updated_agent
    
    def reward_agent(self, agent_id: str, amount: int, reason: str) -> Dict[str, Any]:
        """Reward an agent"""
        agent = self.get_agent(agent_id)
        if not agent:
            raise ValueError(f"Agent not found: {agent_id}")
        
        new_balance = agent["gov_tax_balance"] + amount
        new_trust = min(1.0, agent["trust_score"] + 0.01)
        
        updates = {
            "gov_tax_balance": new_balance,
            "trust_score": new_trust
        }
        
        updated_agent = self.update_agent(agent_id, updates)
        
        # Record audit
        self.create_audit_entry({
            "agent_id": agent_id,
            "verdict": "REWARD",
            "tax_levied": -amount,  # Negative for reward
            "reasoning": reason
        })
        
        return updated_agent
    
    # ========================================================================
    # VIEWS & ANALYTICS
    # ========================================================================
    
    def get_high_trust_agents(self, min_trust: float = 0.7, limit: int = 50) -> List[Dict[str, Any]]:
        """Get high trust agents"""
        response = (
            self.client.table("agents")
            .select("*")
            .gte("trust_score", min_trust)
            .eq("is_frozen", False)
            .eq("blacklisted", False)
            .order("trust_score", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data
    
    def get_agent_statistics(self) -> Dict[str, Any]:
        """Get overall agent statistics"""
        total_response = self.client.table("agents").select("agent_id", count="exact").execute()
        frozen_response = (
            self.client.table("agents")
            .select("agent_id", count="exact")
            .eq("is_frozen", True)
            .execute()
        )
        blacklisted_response = (
            self.client.table("agents")
            .select("agent_id", count="exact")
            .eq("blacklisted", True)
            .execute()
        )
        
        return {
            "total_agents": total_response.count or 0,
            "frozen_agents": frozen_response.count or 0,
            "blacklisted_agents": blacklisted_response.count or 0,
            "active_agents": (total_response.count or 0) - (frozen_response.count or 0)
        }


# Singleton instance
_supabase_client: Optional[SupabaseClient] = None


def get_supabase_client() -> SupabaseClient:
    """Get or create Supabase client singleton"""
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = SupabaseClient()
    return _supabase_client
