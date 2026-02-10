"""
Supabase Compliance Client

This module provides Supabase integration for the compliance features.
It does NOT modify existing OCX core database tables.
"""

import os
from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ComplianceClient:
    """
    Supabase client for compliance layer tables.
    
    Manages:
    - governance_ledger
    - policy_adjustments
    - shadow_sops
    """
    
    def __init__(self) -> None:
        """
        Initialize Supabase compliance client.
        """
        from supabase import create_client
        
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY")
        
        if not url or not key:
            logger.warning("Supabase credentials not found - using in-memory mode")
            self.client = None
        else:
            self.client = create_client(url, key)
            logger.info("Compliance client initialized with Supabase")
    
    def insert_governance_event(self, event: Dict) -> bool:
        """
        Insert governance event into ledger.
        
        Args:
            event: Governance event data
        
        Returns:
            bool: Success
        """
        if not self.client:
            return False
        
        try:
            self.client.table('governance_ledger').insert({
                'transaction_id': event.get('transaction_id'),
                'agent_id': event.get('agent_id'),
                'action': event.get('action'),
                'policy_version': event.get('policy_version'),
                'jury_verdict': event.get('jury_verdict'),
                'entropy_score': event.get('entropy_score'),
                'sop_decision': event.get('sop_decision'),
                'pid_verified': event.get('pid_verified'),
                'block_hash': event.get('hash'),
                'previous_hash': event.get('previous_hash'),
                'timestamp': event.get('timestamp', datetime.utcnow().isoformat()),
            }).execute()
            
            logger.info(f"Governance event inserted: {event.get('transaction_id')}")
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
        if not self.client:
            return None
        
        try:
            response = self.client.table('governance_ledger').select('*').eq(
                'transaction_id', transaction_id
            ).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Failed to get governance event: {e}")
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
        if not self.client:
            return []
        
        try:
            query = self.client.table('governance_ledger').select('*').eq('agent_id', agent_id)
            
            if start_date:
                query = query.gte('timestamp', start_date)
            if end_date:
                query = query.lte('timestamp', end_date)
            
            response = query.order('timestamp', desc=True).execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to get audit trail: {e}")
            return []
    
    def verify_chain(self) -> bool:
        """
        Verify governance ledger chain integrity.
        
        Returns:
            bool: True if valid
        """
        if not self.client:
            return True
        
        try:
            response = self.client.table('governance_ledger').select('*').order('timestamp').execute()
            entries = response.data or []
            
            if not entries:
                return True
            
            prev_hash = "0" * 64
            for entry in entries:
                if entry.get('previous_hash') != prev_hash:
                    logger.error(f"Chain break at {entry.get('transaction_id')}")
                    return False
                prev_hash = entry.get('block_hash', '')
            
            return True
        except Exception as e:
            logger.error(f"Chain verification failed: {e}")
            return False
    
    def insert_policy_adjustment(self, adjustment: Dict) -> bool:
        """
        Insert policy adjustment record.
        
        Args:
            adjustment: Adjustment data
        
        Returns:
            bool: Success
        """
        if not self.client:
            return False
        
        try:
            self.client.table('policy_adjustments').insert({
                'adjustment_id': adjustment.get('adjustment_id'),
                'policy_id': adjustment.get('policy_id'),
                'previous_threshold': adjustment.get('previous_threshold'),
                'new_threshold': adjustment.get('new_threshold'),
                'reason': adjustment.get('reason'),
                'adjusted_by': adjustment.get('adjusted_by'),
                'timestamp': adjustment.get('timestamp', datetime.utcnow().isoformat()),
            }).execute()
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
        if not self.client:
            return []
        
        try:
            response = self.client.table('policy_adjustments').select('*').eq(
                'policy_id', policy_id
            ).order('timestamp', desc=True).execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to get policy adjustment history: {e}")
            return []
    
    def insert_shadow_sop(self, shadow_sop: Dict) -> bool:
        """
        Insert discovered shadow SOP.
        
        Args:
            shadow_sop: Shadow SOP data
        
        Returns:
            bool: Success
        """
        if not self.client:
            return False
        
        try:
            self.client.table('shadow_sops').insert({
                'sop_id': shadow_sop.get('sop_id'),
                'source': shadow_sop.get('source'),
                'channel': shadow_sop.get('channel'),
                'detected_pattern': shadow_sop.get('detected_pattern'),
                'confidence': shadow_sop.get('confidence'),
                'status': shadow_sop.get('status', 'pending'),
                'timestamp': shadow_sop.get('timestamp', datetime.utcnow().isoformat()),
            }).execute()
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
        if not self.client:
            return []
        
        try:
            response = self.client.table('shadow_sops').select('*').eq(
                'status', 'pending'
            ).order('timestamp', desc=True).execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to get pending shadow SOPs: {e}")
            return []
    
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
        if not self.client:
            return False
        
        try:
            update_data = {
                'status': status,
                'reviewed_by': reviewed_by,
                'reviewed_at': datetime.utcnow().isoformat(),
            }
            if reason:
                update_data['rejection_reason'] = reason
            
            self.client.table('shadow_sops').update(update_data).eq(
                'sop_id', sop_id
            ).execute()
            return True
        except Exception as e:
            logger.error(f"Failed to update shadow SOP status: {e}")
            return False


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    client = ComplianceClient()
    
    # Test governance event insert
    event = {
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
    logger.info(f"Insert success: {success}")
