"""
Immutable Governance Ledger - Additive Compliance Layer

This service provides cryptographic audit trails for OCX enforcement decisions.
It does NOT modify core OCX behavior - it only observes and records.

Core OCX components (SOP, PID Mapper, APE Engine) remain unchanged.
"""

import hashlib
import json
from datetime import datetime
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class ImmutableGovernanceLedger:
    """
    Blockchain-style immutable ledger for governance events.
    
    Features:
    - SHA-256 cryptographic hashing
    - Previous hash linking (Merkle tree)
    - Tamper-proof chain verification
    - No modification to core OCX enforcement
    """
    
    def __init__(self, spanner_client=None):
        """
        Initialize ledger with optional Cloud Spanner client.
        
        Args:
            spanner_client: Cloud Spanner client (optional for testing)
        """
        self.spanner = spanner_client
        self.previous_hash = "0" * 64  # Genesis hash
        self.chain_cache = []  # In-memory cache for testing
        
        logger.info("Immutable Governance Ledger initialized (additive layer)")
    
    def record_event(self, event: Dict) -> str:
        """
        Record a governance event with cryptographic hash.
        
        This is called AFTER core OCX enforcement decisions are made.
        It does not influence the decision - only records it.
        
        Args:
            event: Governance event data
                {
                    'transaction_id': str,
                    'agent_id': str,
                    'action': str,
                    'policy_version': str,
                    'jury_verdict': str,
                    'entropy_score': float,
                    'sop_decision': str,  # SEQUESTERED, REPLAYED, SHREDDED
                    'pid_verified': bool
                }
        
        Returns:
            str: Cryptographic hash of the event
        """
        # Create ledger entry
        entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'transaction_id': event.get('transaction_id'),
            'agent_id': event.get('agent_id'),
            'action': event.get('action'),
            'policy_version': event.get('policy_version'),
            'jury_verdict': event.get('jury_verdict'),
            'entropy_score': event.get('entropy_score'),
            'sop_decision': event.get('sop_decision'),
            'pid_verified': event.get('pid_verified', False),
            'previous_hash': self.previous_hash
        }
        
        # Calculate cryptographic hash
        entry_hash = self.calculate_hash(entry)
        entry['hash'] = entry_hash
        
        # Store in database (if available)
        if self.spanner:
            self._store_in_spanner(entry)
        else:
            # In-memory storage for testing
            self.chain_cache.append(entry)
        
        # Update previous hash for next entry
        self.previous_hash = entry_hash
        
        logger.info(f"Recorded governance event: {event.get('transaction_id')} -> {entry_hash[:16]}...")
        
        return entry_hash
    
    def calculate_hash(self, entry: Dict) -> str:
        """
        Calculate SHA-256 hash of ledger entry.
        
        Args:
            entry: Ledger entry (without hash field)
        
        Returns:
            str: 64-character hex hash
        """
        # Create deterministic JSON string
        entry_copy = {k: v for k, v in entry.items() if k != 'hash'}
        data = json.dumps(entry_copy, sort_keys=True)
        
        # SHA-256 hash
        return hashlib.sha256(data.encode()).hexdigest()
    
    def verify_chain(self) -> bool:
        """
        Verify integrity of entire ledger chain.
        
        Returns:
            bool: True if chain is valid, False if tampered
        """
        if self.spanner:
            entries = self._query_all_from_spanner()
        else:
            entries = self.chain_cache
        
        if not entries:
            return True  # Empty chain is valid
        
        prev_hash = "0" * 64
        for entry in entries:
            # Verify hash matches content
            expected_hash = self.calculate_hash(entry)
            if entry['hash'] != expected_hash:
                logger.error(f"Hash mismatch: {entry['transaction_id']}")
                return False
            
            # Verify chain linking
            if entry['previous_hash'] != prev_hash:
                logger.error(f"Chain break: {entry['transaction_id']}")
                return False
            
            prev_hash = entry['hash']
        
        logger.info(f"Chain verification passed: {len(entries)} entries")
        return True
    
    def get_event(self, transaction_id: str) -> Optional[Dict]:
        """
        Retrieve a specific governance event.
        
        Args:
            transaction_id: Transaction ID to lookup
        
        Returns:
            Dict: Ledger entry or None
        """
        if self.spanner:
            return self._query_by_tx_id(transaction_id)
        else:
            for entry in self.chain_cache:
                if entry['transaction_id'] == transaction_id:
                    return entry
        return None
    
    def get_agent_trail(self, agent_id: str, start_date: str = None, end_date: str = None) -> List[Dict]:
        """
        Get audit trail for a specific agent.
        
        Args:
            agent_id: Agent ID
            start_date: Optional start date (ISO format)
            end_date: Optional end date (ISO format)
        
        Returns:
            List[Dict]: List of governance events
        """
        if self.spanner:
            return self._query_by_agent(agent_id, start_date, end_date)
        else:
            results = [e for e in self.chain_cache if e['agent_id'] == agent_id]
            
            # Filter by date if provided
            if start_date:
                results = [e for e in results if e['timestamp'] >= start_date]
            if end_date:
                results = [e for e in results if e['timestamp'] <= end_date]
            
            return results
    
    # Cloud Spanner integration (optional)
    
    def _store_in_spanner(self, entry: Dict):
        """Store entry in Cloud Spanner governance_ledger table."""
        # TODO: Implement Cloud Spanner insert
        # This is a placeholder for production deployment
        pass
    
    def _query_all_from_spanner(self) -> List[Dict]:
        """Query all entries from Cloud Spanner."""
        # TODO: Implement Cloud Spanner query
        return []
    
    def _query_by_tx_id(self, transaction_id: str) -> Optional[Dict]:
        """Query entry by transaction ID from Cloud Spanner."""
        # TODO: Implement Cloud Spanner query
        return None
    
    def _query_by_agent(self, agent_id: str, start_date: str = None, end_date: str = None) -> List[Dict]:
        """Query entries by agent ID from Cloud Spanner."""
        # TODO: Implement Cloud Spanner query
        return []


# Example usage (does not modify core OCX)
if __name__ == "__main__":
    # Initialize ledger
    ledger = ImmutableGovernanceLedger()
    
    # Record a governance event (called AFTER OCX enforcement)
    event = {
        'transaction_id': 'tx-12345',
        'agent_id': 'PROCUREMENT_BOT',
        'action': 'execute_payment(amount=1500)',
        'policy_version': 'v1.2.3',
        'jury_verdict': 'PASS',
        'entropy_score': 2.3,
        'sop_decision': 'REPLAYED',
        'pid_verified': True
    }
    
    hash1 = ledger.record_event(event)
    print(f"Event recorded: {hash1}")
    
    # Verify chain
    is_valid = ledger.verify_chain()
    print(f"Chain valid: {is_valid}")
    
    # Retrieve event
    retrieved = ledger.get_event('tx-12345')
    print(f"Retrieved: {retrieved['hash']}")
