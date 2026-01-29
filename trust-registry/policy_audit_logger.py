"""
Cloud Spanner Audit Logger for Policy Evaluations
Logs all policy evaluations for compliance and debugging
"""

import uuid
import time
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from google.cloud import spanner
from google.cloud.spanner_v1 import param_types


class PolicyAuditLogger:
    """Logs policy evaluations to Cloud Spanner"""
    
    def __init__(
        self,
        project_id: str,
        instance_id: str,
        database_id: str
    ):
        self.client = spanner.Client(project=project_id)
        self.instance = self.client.instance(instance_id)
        self.database = self.instance.database(database_id)
    
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
        
        with self.database.batch() as batch:
            batch.insert(
                table="PolicyAudits",
                columns=[
                    "AuditID",
                    "PolicyID",
                    "AgentID",
                    "TriggerIntent",
                    "Tier",
                    "Violated",
                    "Action",
                    "DataPayload",
                    "EvaluationTimeMs",
                    "Timestamp"
                ],
                values=[(
                    audit_id,
                    policy_id,
                    agent_id,
                    trigger_intent,
                    tier,
                    violated,
                    action,
                    json.dumps(data_payload),
                    evaluation_time_ms,
                    spanner.COMMIT_TIMESTAMP
                )]
            )
        
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
        
        with self.database.batch() as batch:
            batch.insert(
                table="PolicyExtractions",
                columns=[
                    "ExtractionID",
                    "SourceName",
                    "DocumentHash",
                    "PoliciesExtracted",
                    "AvgConfidence",
                    "ModelUsed",
                    "ExtractionTimeMs",
                    "ExtractedAt"
                ],
                values=[(
                    extraction_id,
                    source_name,
                    document_hash,
                    policies_extracted,
                    avg_confidence,
                    model_used,
                    extraction_time_ms,
                    spanner.COMMIT_TIMESTAMP
                )]
            )
        
        return extraction_id
    
    def get_violations_by_policy(
        self,
        policy_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get recent violations for a specific policy"""
        query = """
            SELECT AuditID, AgentID, TriggerIntent, Action, DataPayload, Timestamp
            FROM PolicyAudits
            WHERE PolicyID = @policy_id AND Violated = TRUE
            ORDER BY Timestamp DESC
            LIMIT @limit
        """
        
        with self.database.snapshot() as snapshot:
            results = snapshot.execute_sql(
                query,
                params={"policy_id": policy_id, "limit": limit},
                param_types={
                    "policy_id": param_types.STRING,
                    "limit": param_types.INT64
                }
            )
            
            violations = []
            for row in results:
                violations.append({
                    "audit_id": row[0],
                    "agent_id": row[1],
                    "trigger_intent": row[2],
                    "action": row[3],
                    "data_payload": json.loads(row[4]) if row[4] else {},
                    "timestamp": row[5].isoformat()
                })
            
            return violations
    
    def get_violations_by_agent(
        self,
        agent_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get recent violations for a specific agent"""
        query = """
            SELECT AuditID, PolicyID, TriggerIntent, Tier, Action, Timestamp
            FROM PolicyAudits
            WHERE AgentID = @agent_id AND Violated = TRUE
            ORDER BY Timestamp DESC
            LIMIT @limit
        """
        
        with self.database.snapshot() as snapshot:
            results = snapshot.execute_sql(
                query,
                params={"agent_id": agent_id, "limit": limit},
                param_types={
                    "agent_id": param_types.STRING,
                    "limit": param_types.INT64
                }
            )
            
            violations = []
            for row in results:
                violations.append({
                    "audit_id": row[0],
                    "policy_id": row[1],
                    "trigger_intent": row[2],
                    "tier": row[3],
                    "action": row[4],
                    "timestamp": row[5].isoformat()
                })
            
            return violations
    
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
        # Query total evaluations
        total_query = """
            SELECT COUNT(*) as total
            FROM PolicyAudits
            WHERE Timestamp >= @start_time AND Timestamp < @end_time
        """
        
        # Query violations
        violations_query = """
            SELECT COUNT(*) as violations
            FROM PolicyAudits
            WHERE Timestamp >= @start_time AND Timestamp < @end_time AND Violated = TRUE
        """
        
        # Query top violated policies
        top_policies_query = """
            SELECT PolicyID, COUNT(*) as count
            FROM PolicyAudits
            WHERE Timestamp >= @start_time AND Timestamp < @end_time AND Violated = TRUE
            GROUP BY PolicyID
            ORDER BY count DESC
            LIMIT 10
        """
        
        # Query top violating agents
        top_agents_query = """
            SELECT AgentID, COUNT(*) as count
            FROM PolicyAudits
            WHERE Timestamp >= @start_time AND Timestamp < @end_time AND Violated = TRUE AND AgentID IS NOT NULL
            GROUP BY AgentID
            ORDER BY count DESC
            LIMIT 10
        """
        
        with self.database.snapshot() as snapshot:
            # Get total evaluations
            total_results = snapshot.execute_sql(
                total_query,
                params={"start_time": start_time, "end_time": end_time},
                param_types={
                    "start_time": param_types.TIMESTAMP,
                    "end_time": param_types.TIMESTAMP
                }
            )
            total_evaluations = list(total_results)[0][0]
            
            # Get violations
            violations_results = snapshot.execute_sql(
                violations_query,
                params={"start_time": start_time, "end_time": end_time},
                param_types={
                    "start_time": param_types.TIMESTAMP,
                    "end_time": param_types.TIMESTAMP
                }
            )
            total_violations = list(violations_results)[0][0]
            
            # Get top policies
            top_policies_results = snapshot.execute_sql(
                top_policies_query,
                params={"start_time": start_time, "end_time": end_time},
                param_types={
                    "start_time": param_types.TIMESTAMP,
                    "end_time": param_types.TIMESTAMP
                }
            )
            top_policies = [row[0] for row in top_policies_results]
            
            # Get top agents
            top_agents_results = snapshot.execute_sql(
                top_agents_query,
                params={"start_time": start_time, "end_time": end_time},
                param_types={
                    "start_time": param_types.TIMESTAMP,
                    "end_time": param_types.TIMESTAMP
                }
            )
            top_agents = [row[0] for row in top_agents_results]
        
        # Calculate violation rate
        violation_rate = (total_violations / total_evaluations * 100) if total_evaluations > 0 else 0.0
        
        # Insert report
        report_id = str(uuid.uuid4())
        with self.database.batch() as batch:
            batch.insert(
                table="ComplianceReports",
                columns=[
                    "ReportID",
                    "ReportType",
                    "StartTime",
                    "EndTime",
                    "TotalEvaluations",
                    "TotalViolations",
                    "ViolationRate",
                    "TopViolatedPolicies",
                    "TopViolatingAgents",
                    "GeneratedAt"
                ],
                values=[(
                    report_id,
                    report_type,
                    start_time,
                    end_time,
                    total_evaluations,
                    total_violations,
                    violation_rate,
                    top_policies,
                    top_agents,
                    spanner.COMMIT_TIMESTAMP
                )]
            )
        
        return report_id
    
    def close(self):
        """Close Spanner client"""
        self.client.close()


# Singleton instance
_audit_logger: Optional[PolicyAuditLogger] = None


def get_audit_logger() -> Optional[PolicyAuditLogger]:
    """Get or create singleton audit logger"""
    global _audit_logger
    if _audit_logger is None:
        import os
        project_id = os.getenv("SPANNER_PROJECT_ID")
        instance_id = os.getenv("SPANNER_INSTANCE_ID")
        database_id = os.getenv("SPANNER_DATABASE_ID")
        
        if project_id and instance_id and database_id:
            _audit_logger = PolicyAuditLogger(project_id, instance_id, database_id)
        else:
            print("⚠️  Spanner credentials not configured. Audit logging disabled.")
    
    return _audit_logger
