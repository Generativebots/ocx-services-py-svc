"""
Immutable Governance Ledger - Additive Compliance Layer

This service provides cryptographic audit trails for OCX enforcement decisions.
It does NOT modify core OCX behavior - it only observes and records.

Core OCX components (SOP, PID Mapper, APE Engine) remain unchanged.

Backend: Supabase (PostgreSQL)
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
    - Multi-tenant isolation (per-tenant hash chains)
    - No modification to core OCX enforcement
    
    Backend: Supabase via SupabaseLedgerClient
    """
    
    def __init__(self, supabase_client=None) -> None:
        """
        Initialize ledger with optional Supabase client.
        
        Args:
            supabase_client: SupabaseLedgerClient instance (optional for testing)
        """
        self.db_client = supabase_client
        # Per-tenant genesis hashes and chain caches
        self._previous_hashes: Dict[str, str] = {}  # tenant_id -> last hash
        self._chain_caches: Dict[str, List[Dict]] = {}  # tenant_id -> entries
        
        logger.info("Immutable Governance Ledger initialized (multi-tenant, additive layer)")
    
    def _get_previous_hash(self, tenant_id: str) -> str:
        """Get the last hash for a tenant's chain (genesis if new)."""
        return self._previous_hashes.get(tenant_id, "0" * 64)
    
    def _get_chain_cache(self, tenant_id: str) -> List[Dict]:
        """Get or create the in-memory chain for a tenant."""
        if tenant_id not in self._chain_caches:
            self._chain_caches[tenant_id] = []
        return self._chain_caches[tenant_id]
    
    def record_event(self, event: Dict) -> str:
        """
        Record a governance event with cryptographic hash.
        
        This is called AFTER core OCX enforcement decisions are made.
        It does not influence the decision - only records it.
        
        Args:
            event: Governance event data
                {
                    'tenant_id': str,       # Required — multi-tenant isolation
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
        
        Raises:
            ValueError: If tenant_id is missing
        """
        tenant_id = event.get('tenant_id')
        if not tenant_id:
            raise ValueError("tenant_id is required for ledger entries")
        
        # Create ledger entry (tenant_id is part of the hash chain)
        entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'tenant_id': tenant_id,
            'transaction_id': event.get('transaction_id'),
            'agent_id': event.get('agent_id'),
            'action': event.get('action'),
            'policy_version': event.get('policy_version'),
            'jury_verdict': event.get('jury_verdict'),
            'entropy_score': event.get('entropy_score'),
            'sop_decision': event.get('sop_decision'),
            'pid_verified': event.get('pid_verified', False),
            'previous_hash': self._get_previous_hash(tenant_id)
        }
        
        # Calculate cryptographic hash
        entry_hash = self.calculate_hash(entry)
        entry['hash'] = entry_hash
        
        # Store in database (if available)
        if self.db_client:
            self.db_client.store_entry(entry)
        else:
            # In-memory storage — per-tenant chain
            self._get_chain_cache(tenant_id).append(entry)
        
        # Update previous hash for this tenant's chain
        self._previous_hashes[tenant_id] = entry_hash
        
        logger.info(
            f"Recorded governance event: tenant={tenant_id} "
            f"tx={event.get('transaction_id')} -> {entry_hash[:16]}..."
        )
        
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
    
    def verify_chain(self, tenant_id: str) -> bool:
        """
        Verify integrity of a tenant's ledger chain.
        
        Args:
            tenant_id: Tenant whose chain to verify
        
        Returns:
            bool: True if chain is valid, False if tampered
        """
        if self.db_client:
            entries = self.db_client.query_by_tenant(tenant_id)
        else:
            entries = self._get_chain_cache(tenant_id)
        
        if not entries:
            return True  # Empty chain is valid
        
        prev_hash = "0" * 64
        for entry in entries:
            # Verify tenant isolation — entry must belong to this tenant
            if entry.get('tenant_id') != tenant_id:
                logger.error(f"Tenant mismatch in chain: expected {tenant_id}, got {entry.get('tenant_id')}")
                return False
            
            # Verify hash matches content
            expected_hash = self.calculate_hash(entry)
            if entry.get('hash', entry.get('block_hash')) != expected_hash:
                logger.error(f"Hash mismatch: {entry.get('transaction_id')}")
                return False
            
            # Verify chain linking
            if entry.get('previous_hash') != prev_hash:
                logger.error(f"Chain break: {entry.get('transaction_id')}")
                return False
            
            prev_hash = entry.get('hash', entry.get('block_hash'))
        
        logger.info(f"Chain verification passed: tenant={tenant_id}, {len(entries)} entries")
        return True
    
    def get_event(self, tenant_id: str, transaction_id: str) -> Optional[Dict]:
        """
        Retrieve a specific governance event within a tenant's chain.
        
        Args:
            tenant_id: Tenant ID for isolation
            transaction_id: Transaction ID to lookup
        
        Returns:
            Dict: Ledger entry or None
        """
        if self.db_client:
            return self.db_client.query_by_transaction_id(tenant_id, transaction_id)
        else:
            for entry in self._get_chain_cache(tenant_id):
                if entry['transaction_id'] == transaction_id:
                    return entry
        return None
    
    def get_agent_trail(
        self,
        tenant_id: str,
        agent_id: str,
        start_date: str = None,
        end_date: str = None,
    ) -> List[Dict]:
        """
        Get audit trail for a specific agent within a tenant.
        
        Args:
            tenant_id: Tenant ID for isolation
            agent_id: Agent ID
            start_date: Optional start date (ISO format)
            end_date: Optional end date (ISO format)
        
        Returns:
            List[Dict]: List of governance events
        """
        if self.db_client:
            return self.db_client.query_by_agent(tenant_id, agent_id, start_date, end_date)
        else:
            results = [
                e for e in self._get_chain_cache(tenant_id)
                if e['agent_id'] == agent_id
            ]
            
            # Filter by date if provided
            if start_date:
                results = [e for e in results if e['timestamp'] >= start_date]
            if end_date:
                results = [e for e in results if e['timestamp'] <= end_date]
            
            return results


# Standalone test (does not modify core OCX)
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Initialize ledger (in-memory mode for standalone test)
    ledger = ImmutableGovernanceLedger()
    
    TENANT = "acme-corp"
    
    # Record a governance event (called AFTER OCX enforcement)
    event = {
        'tenant_id': TENANT,
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
    logger.info(f"Event recorded: {hash1}")
    
    # Verify chain (tenant-scoped)
    is_valid = ledger.verify_chain(TENANT)
    logger.info(f"Chain valid: {is_valid}")
    
    # Retrieve event (tenant-scoped)
    retrieved = ledger.get_event(TENANT, 'tx-12345')
    logger.info(f"Retrieved: {retrieved['hash']}")
