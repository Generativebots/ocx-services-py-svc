"""
Cloud Spanner Integration for Compliance Layer

This module provides Cloud Spanner integration for the compliance features.
It does NOT modify existing OCX core database tables.
"""

from google.cloud import spanner
from typing import Dict, List, Optional
import logging
import os

logger = logging.getLogger(__name__)


class ComplianceSpannerClient:
    """
    Cloud Spanner client for compliance layer tables.
    
    Manages:
    - governance_ledger
    - regulator_api_keys
    - policy_adjustments
    - shadow_sops
    """
    
    def __init__(self, instance_id: str = None, database_id: str = None):
        """
        Initialize Spanner client.
        
        Args:
            instance_id: Spanner instance ID (or from env)
            database_id: Spanner database ID (or from env)
        """
        self.instance_id = instance_id or os.getenv('SPANNER_INSTANCE_ID', 'ocx-instance')
        self.database_id = database_id or os.getenv('SPANNER_DATABASE_ID', 'ocx-db')
        
        self.client = spanner.Client()
        self.instance = self.client.instance(self.instance_id)
        self.database = self.instance.database(self.database_id)
        
        logger.info(f"Compliance Spanner client initialized: {self.instance_id}/{self.database_id}")
    
    # ========================================================================
    # Governance Ledger
    # ========================================================================
    
    def insert_governance_event(self, event: Dict) -> bool:
        """
        Insert governance event into ledger.
        
        Args:
            event: Governance event data
        
        Returns:
            bool: Success
        """
        def insert_event(transaction):
            transaction.insert(
                table='governance_ledger',
                columns=[
                    'id', 'timestamp', 'transaction_id', 'agent_id', 'action',
                    'policy_version', 'jury_verdict', 'entropy_score',
                    'sop_decision', 'pid_verified', 'hash', 'previous_hash'
                ],
                values=[[
                    event['id'],
                    event['timestamp'],
                    event['transaction_id'],
                    event['agent_id'],
                    event['action'],
                    event['policy_version'],
                    event['jury_verdict'],
                    event.get('entropy_score'),
                    event.get('sop_decision'),
                    event.get('pid_verified', False),
                    event['hash'],
                    event['previous_hash']
                ]]
            )
        
        try:
            self.database.run_in_transaction(insert_event)
            logger.info(f"Inserted governance event: {event['transaction_id']}")
            return True
        except Exception as e:
            logger.error(f"Failed to insert governance event: {e}")
            return False
    
    def get_governance_event(self, transaction_id: str) -> Optional[Dict]:
        """
        Get governance event by transaction ID.
        
        Args:
            transaction_id: Transaction ID
        
        Returns:
            Dict: Event data or None
        """
        with self.database.snapshot() as snapshot:
            results = snapshot.execute_sql(
                """
                SELECT * FROM governance_ledger 
                WHERE transaction_id = @tx_id
                LIMIT 1
                """,
                params={'tx_id': transaction_id},
                param_types={'tx_id': spanner.param_types.STRING}
            )
            
            for row in results:
                return dict(row)
        
        return None
    
    def get_agent_audit_trail(self, agent_id: str, start_date: str = None, end_date: str = None) -> List[Dict]:
        """
        Get audit trail for an agent.
        
        Args:
            agent_id: Agent ID
            start_date: Optional start date (ISO format)
            end_date: Optional end date (ISO format)
        
        Returns:
            List[Dict]: Audit trail
        """
        query = """
            SELECT * FROM governance_ledger 
            WHERE agent_id = @agent_id
        """
        params = {'agent_id': agent_id}
        param_types = {'agent_id': spanner.param_types.STRING}
        
        if start_date:
            query += " AND timestamp >= @start_date"
            params['start_date'] = start_date
            param_types['start_date'] = spanner.param_types.TIMESTAMP
        
        if end_date:
            query += " AND timestamp <= @end_date"
            params['end_date'] = end_date
            param_types['end_date'] = spanner.param_types.TIMESTAMP
        
        query += " ORDER BY timestamp DESC"
        
        with self.database.snapshot() as snapshot:
            results = snapshot.execute_sql(query, params=params, param_types=param_types)
            return [dict(row) for row in results]
    
    def verify_chain(self) -> bool:
        """
        Verify governance ledger chain integrity.
        
        Returns:
            bool: True if valid
        """
        with self.database.snapshot() as snapshot:
            results = snapshot.execute_sql(
                "SELECT * FROM governance_ledger ORDER BY timestamp"
            )
            
            prev_hash = "0" * 64
            for row in results:
                if row['previous_hash'] != prev_hash:
                    logger.error(f"Chain break at {row['transaction_id']}")
                    return False
                prev_hash = row['hash']
        
        return True
    
    # ========================================================================
    # Policy Adjustments
    # ========================================================================
    
    def insert_policy_adjustment(self, adjustment: Dict) -> bool:
        """
        Insert policy adjustment record.
        
        Args:
            adjustment: Adjustment data
        
        Returns:
            bool: Success
        """
        def insert_adj(transaction):
            transaction.insert(
                table='policy_adjustments',
                columns=[
                    'id', 'policy_id', 'adjustment_type', 'old_value',
                    'new_value', 'reason', 'approved_by', 'timestamp', 'transaction_id'
                ],
                values=[[
                    adjustment['id'],
                    adjustment['policy_id'],
                    adjustment['adjustment_type'],
                    adjustment.get('old_value'),
                    adjustment.get('new_value'),
                    adjustment.get('reason'),
                    adjustment['approved_by'],
                    adjustment['timestamp'],
                    adjustment.get('transaction_id')
                ]]
            )
        
        try:
            self.database.run_in_transaction(insert_adj)
            logger.info(f"Inserted policy adjustment: {adjustment['policy_id']}")
            return True
        except Exception as e:
            logger.error(f"Failed to insert policy adjustment: {e}")
            return False
    
    def get_policy_adjustment_history(self, policy_id: str) -> List[Dict]:
        """
        Get adjustment history for a policy.
        
        Args:
            policy_id: Policy ID
        
        Returns:
            List[Dict]: Adjustment history
        """
        with self.database.snapshot() as snapshot:
            results = snapshot.execute_sql(
                """
                SELECT * FROM policy_adjustments 
                WHERE policy_id = @policy_id
                ORDER BY timestamp DESC
                """,
                params={'policy_id': policy_id},
                param_types={'policy_id': spanner.param_types.STRING}
            )
            return [dict(row) for row in results]
    
    # ========================================================================
    # Shadow SOPs
    # ========================================================================
    
    def insert_shadow_sop(self, shadow_sop: Dict) -> bool:
        """
        Insert discovered shadow SOP.
        
        Args:
            shadow_sop: Shadow SOP data
        
        Returns:
            bool: Success
        """
        def insert_sop(transaction):
            transaction.insert(
                table='shadow_sops',
                columns=[
                    'id', 'rule', 'confidence', 'category', 'source', 'channel',
                    'author', 'original_text', 'suggested_logic', 'suggested_action',
                    'status', 'discovered_at'
                ],
                values=[[
                    shadow_sop['id'],
                    shadow_sop['rule'],
                    shadow_sop['confidence'],
                    shadow_sop.get('category'),
                    shadow_sop['source'],
                    shadow_sop.get('channel'),
                    shadow_sop.get('author'),
                    shadow_sop['original_text'],
                    shadow_sop.get('suggested_logic'),
                    shadow_sop.get('suggested_action'),
                    shadow_sop['status'],
                    shadow_sop['discovered_at']
                ]]
            )
        
        try:
            self.database.run_in_transaction(insert_sop)
            logger.info(f"Inserted shadow SOP: {shadow_sop['id']}")
            return True
        except Exception as e:
            logger.error(f"Failed to insert shadow SOP: {e}")
            return False
    
    def get_pending_shadow_sops(self) -> List[Dict]:
        """
        Get shadow SOPs pending review.
        
        Returns:
            List[Dict]: Pending shadow SOPs
        """
        with self.database.snapshot() as snapshot:
            results = snapshot.execute_sql(
                """
                SELECT * FROM shadow_sops 
                WHERE status = 'pending'
                ORDER BY discovered_at DESC
                """
            )
            return [dict(row) for row in results]
    
    def update_shadow_sop_status(self, sop_id: str, status: str, reviewed_by: str, reason: str = None) -> bool:
        """
        Update shadow SOP status.
        
        Args:
            sop_id: Shadow SOP ID
            status: New status (approved, rejected)
            reviewed_by: Reviewer
            reason: Optional rejection reason
        
        Returns:
            bool: Success
        """
        def update_status(transaction):
            transaction.update(
                table='shadow_sops',
                columns=['id', 'status', 'reviewed_by', 'reviewed_at', 'rejection_reason'],
                values=[[
                    sop_id,
                    status,
                    reviewed_by,
                    spanner.COMMIT_TIMESTAMP,
                    reason
                ]]
            )
        
        try:
            self.database.run_in_transaction(update_status)
            logger.info(f"Updated shadow SOP {sop_id}: {status}")
            return True
        except Exception as e:
            logger.error(f"Failed to update shadow SOP: {e}")
            return False


# Example usage
if __name__ == "__main__":
    client = ComplianceSpannerClient()
    
    # Test governance event insert
    event = {
        'id': 'evt-001',
        'timestamp': '2026-01-21T08:00:00Z',
        'transaction_id': 'tx-001',
        'agent_id': 'PROCUREMENT_BOT',
        'action': 'execute_payment(amount=1500)',
        'policy_version': 'v1.2.3',
        'jury_verdict': 'PASS',
        'entropy_score': 2.3,
        'sop_decision': 'REPLAYED',
        'pid_verified': True,
        'hash': 'a1b2c3...',
        'previous_hash': '000000...'
    }
    
    success = client.insert_governance_event(event)
    print(f"Insert success: {success}")
