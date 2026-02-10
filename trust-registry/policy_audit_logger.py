"""
Supabase Audit Logger for Policy Evaluations
Logs all policy evaluations for compliance and debugging
"""

import uuid
import json
import os
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class PolicyAuditLogger:
    """Logs policy evaluations to Supabase"""
    
    def __init__(self) -> None:
        from supabase import create_client
        
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY")
        
        if not url or not key:
            logger.warning("Supabase credentials not configured. Audit logging disabled.")
            self.client = None
        else:
            self.client = create_client(url, key)
            logger.info("Policy Audit Logger initialized with Supabase")
    
    def log_evaluation(
        self,
        policy_id: str,
        agent_id: Optional[str],
        trigger_intent: str,
        tier: str,
        violated: bool,
        action: str,
        data_payload: Dict[str, Any],
        evaluation_time_ms: float
    ) -> str:
        """
        Log a single policy evaluation
        
        Returns:
            audit_id
        """
        audit_id = str(uuid.uuid4())
        
        if not self.client:
            return audit_id
        
        try:
            self.client.table("policy_audits").insert({
                "audit_id": audit_id,
                "policy_id": policy_id,
                "agent_id": agent_id,
                "trigger_intent": trigger_intent,
                "tier": tier,
                "violated": violated,
                "action": action,
                "data_payload": json.dumps(data_payload),
                "evaluation_time_ms": evaluation_time_ms,
                "timestamp": datetime.utcnow().isoformat(),
            }).execute()
        except Exception as e:
            logger.error(f"Failed to log policy evaluation: {e}")
        
        return audit_id
    
    def log_extraction(
        self,
        source_name: str,
        document_hash: str,
        policies_extracted: int,
        avg_confidence: float,
        model_used: str,
        extraction_time_ms: float
    ) -> str:
        """
        Log a policy extraction from APE Engine
        
        Returns:
            extraction_id
        """
        extraction_id = str(uuid.uuid4())
        
        if not self.client:
            return extraction_id
        
        try:
            self.client.table("policy_extractions").insert({
                "extraction_id": extraction_id,
                "source_name": source_name,
                "document_hash": document_hash,
                "policies_extracted": policies_extracted,
                "avg_confidence": avg_confidence,
                "model_used": model_used,
                "extraction_time_ms": extraction_time_ms,
                "extracted_at": datetime.utcnow().isoformat(),
            }).execute()
        except Exception as e:
            logger.error(f"Failed to log policy extraction: {e}")
        
        return extraction_id
    
    def get_violations_by_policy(
        self,
        policy_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get recent violations for a specific policy"""
        if not self.client:
            return []
        
        try:
            response = self.client.table("policy_audits").select("*").eq(
                "policy_id", policy_id
            ).eq("violated", True).order(
                "timestamp", desc=True
            ).limit(limit).execute()
            
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to get violations by policy: {e}")
            return []
    
    def get_violations_by_agent(
        self,
        agent_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get recent violations for a specific agent"""
        if not self.client:
            return []
        
        try:
            response = self.client.table("policy_audits").select("*").eq(
                "agent_id", agent_id
            ).eq("violated", True).order(
                "timestamp", desc=True
            ).limit(limit).execute()
            
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to get violations by agent: {e}")
            return []
    
    def generate_compliance_report(
        self,
        start_time: datetime,
        end_time: datetime,
        report_type: str = "DAILY"
    ) -> str:
        """
        Generate compliance report for a time period
        
        Returns:
            report_id
        """
        report_id = str(uuid.uuid4())
        
        if not self.client:
            return report_id
        
        try:
            # Query all evaluations in time range
            response = self.client.table("policy_audits").select("*").gte(
                "timestamp", start_time.isoformat()
            ).lt("timestamp", end_time.isoformat()).execute()
            
            all_evals = response.data or []
            total_evaluations = len(all_evals)
            violations = [e for e in all_evals if e.get("violated")]
            total_violations = len(violations)
            
            # Top violated policies
            policy_counts: Dict[str, int] = {}
            agent_counts: Dict[str, int] = {}
            for v in violations:
                pid = v.get("policy_id", "unknown")
                policy_counts[pid] = policy_counts.get(pid, 0) + 1
                aid = v.get("agent_id")
                if aid:
                    agent_counts[aid] = agent_counts.get(aid, 0) + 1
            
            top_policies = sorted(policy_counts, key=policy_counts.get, reverse=True)[:10]
            top_agents = sorted(agent_counts, key=agent_counts.get, reverse=True)[:10]
            
            violation_rate = (total_violations / total_evaluations * 100) if total_evaluations > 0 else 0.0
            
            # Insert report
            self.client.table("compliance_reports").insert({
                "report_id": report_id,
                "report_type": report_type,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "total_evaluations": total_evaluations,
                "total_violations": total_violations,
                "violation_rate": violation_rate,
                "top_violated_policies": json.dumps(top_policies),
                "top_violating_agents": json.dumps(top_agents),
                "generated_at": datetime.utcnow().isoformat(),
            }).execute()
        except Exception as e:
            logger.error(f"Failed to generate compliance report: {e}")
        
        return report_id
    
    def close(self) -> None:
        """Close client"""
        self.client = None


# Singleton instance
_audit_logger: Optional[PolicyAuditLogger] = None


def get_audit_logger() -> Optional[PolicyAuditLogger]:
    """Get or create singleton audit logger"""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = PolicyAuditLogger()
    return _audit_logger
