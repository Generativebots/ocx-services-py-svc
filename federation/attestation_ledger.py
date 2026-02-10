"""
Trust Attestation Ledger - Database Backend (Supabase/PostgreSQL)

All tiers use Supabase/PostgreSQL as the backend.
"""

import hashlib
import json
import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from abc import ABC, abstractmethod

# Import configuration
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.database_config import get_db_config

logger = logging.getLogger(__name__)


class LedgerBackend(ABC):
    """Abstract base class for ledger backends"""
    
    @abstractmethod
    def publish_attestation(self, attestation_data: Dict) -> str:
        """Publish attestation to ledger"""
        pass
    
    @abstractmethod
    def verify_attestation(self, local_hash: str, remote_hash: str, agent_id: str) -> Dict:
        """Verify attestation from ledger"""
        pass
    
    @abstractmethod
    def query_attestations(self, ocx_instance_id: str, hours: int = 24) -> List[Dict]:
        """Query recent attestations"""
        pass


class PostgreSQLLedgerBackend(LedgerBackend):
    """PostgreSQL/Supabase backend for trust attestations"""
    
    def __init__(self, config: Dict) -> None:
        """Initialize PostgreSQL backend"""
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            
            self.conn = psycopg2.connect(
                host=config['host'],
                port=config['port'],
                database=config['database'],
                user=config['user'],
                password=config['password']
            )
            self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)
            logger.info("PostgreSQL ledger backend initialized")
        except ImportError:
            logger.warning("psycopg2 not installed, using mock backend")
            self.conn = None
            self.cursor = None
    
    def publish_attestation(self, attestation_data: Dict) -> str:
        """Publish attestation to PostgreSQL"""
        if not self.conn:
            return attestation_data['attestation_id']
        
        query = """
            INSERT INTO trust_attestations (
                attestation_id, tenant_id, ocx_instance_id, agent_id,
                audit_hash, trust_level, signature, expires_at, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING attestation_id
        """
        
        self.cursor.execute(query, (
            attestation_data['attestation_id'],
            attestation_data.get('tenant_id', 'default'),
            attestation_data['ocx_instance_id'],
            attestation_data['agent_id'],
            attestation_data['audit_hash'],
            attestation_data['trust_level'],
            attestation_data['signature'],
            attestation_data['expires_at'],
            json.dumps(attestation_data.get('metadata', {}))
        ))
        
        self.conn.commit()
        return attestation_data['attestation_id']
    
    def verify_attestation(self, local_hash: str, remote_hash: str, agent_id: str) -> Dict:
        """Verify attestation from PostgreSQL"""
        if not self.conn:
            # Mock verification
            return {
                'verified': True,
                'trust_level': 0.85,
                'timestamp': datetime.utcnow()
            }
        
        query = """
            SELECT * FROM trust_attestations
            WHERE audit_hash = %s AND agent_id = %s
            AND expires_at > NOW()
            ORDER BY timestamp DESC
            LIMIT 1
        """
        
        self.cursor.execute(query, (remote_hash, agent_id))
        result = self.cursor.fetchone()
        
        if result:
            return {
                'verified': True,
                'trust_level': result['trust_level'],
                'timestamp': result['timestamp'],
                'ocx_instance_id': result['ocx_instance_id']
            }
        
        return {'verified': False}
    
    def query_attestations(self, ocx_instance_id: str, hours: int = 24) -> List[Dict]:
        """Query recent attestations from PostgreSQL"""
        if not self.conn:
            return []
        
        query = """
            SELECT * FROM trust_attestations
            WHERE ocx_instance_id = %s
            AND timestamp > NOW() - INTERVAL '%s hours'
            ORDER BY timestamp DESC
        """
        
        self.cursor.execute(query, (ocx_instance_id, hours))
        return [dict(row) for row in self.cursor.fetchall()]


class TrustAttestationLedger:
    """
    Trust Attestation Ledger with Supabase/PostgreSQL backend.
    """
    
    def __init__(self, ocx_instance_id: str, tenant_id: str = "default") -> None:
        """
        Initialize Trust Attestation Ledger.
        
        Args:
            ocx_instance_id: This OCX instance's unique ID
            tenant_id: Tenant identifier for multi-tenancy
        """
        self.ocx_instance_id = ocx_instance_id
        self.tenant_id = tenant_id
        
        # Use PostgreSQL/Supabase backend
        config = get_db_config()
        self.backend = PostgreSQLLedgerBackend(config)
        logger.info(f"Trust Attestation Ledger initialized for {ocx_instance_id}")
    
    def publish_attestation(self, agent_id: str, audit_result: Dict) -> str:
        """
        Publish a trust attestation to the ledger.
        
        Args:
            agent_id: Agent identifier
            audit_result: Audit result containing trust_score, verdict, etc.
        
        Returns:
            Attestation ID
        """
        attestation_id = str(uuid.uuid4())
        
        # Create audit hash (zero-knowledge proof)
        audit_data = {
            'agent_id': agent_id,
            'trust_score': audit_result.get('trust_score', 0.0),
            'verdict': audit_result.get('verdict', 'UNKNOWN'),
            'timestamp': datetime.utcnow().isoformat()
        }
        audit_hash = hashlib.sha256(json.dumps(audit_data, sort_keys=True).encode()).hexdigest()
        
        # Create attestation
        attestation_data = {
            'attestation_id': attestation_id,
            'tenant_id': self.tenant_id,
            'ocx_instance_id': self.ocx_instance_id,
            'agent_id': agent_id,
            'audit_hash': audit_hash,
            'trust_level': audit_result.get('trust_score', 0.0),
            'signature': '',  # Would be SPIFFE signature in production
            'expires_at': datetime.utcnow() + timedelta(hours=24),
            'metadata': {
                'verdict': audit_result.get('verdict', 'UNKNOWN'),
                'published_at': datetime.utcnow().isoformat()
            }
        }
        
        return self.backend.publish_attestation(attestation_data)
    
    def verify_attestation(self, local_audit_hash: str, remote_audit_hash: str, agent_id: str) -> Dict:
        """
        Verify a trust attestation from another OCX instance.
        
        Args:
            local_audit_hash: Our computed audit hash
            remote_audit_hash: Remote OCX's published audit hash
            agent_id: Agent identifier
        
        Returns:
            Verification result with trust level
        """
        return self.backend.verify_attestation(local_audit_hash, remote_audit_hash, agent_id)
    
    def query_recent_attestations(self, hours: int = 24) -> List[Dict]:
        """
        Query recent attestations for this OCX instance.
        
        Args:
            hours: Number of hours to look back
        
        Returns:
            List of attestations
        """
        return self.backend.query_attestations(self.ocx_instance_id, hours)


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test ledger
    ledger = TrustAttestationLedger("ocx-us-west1-001", "tenant-alpha")
    
    # Publish attestation
    attestation_id = ledger.publish_attestation(
        agent_id="agent-123",
        audit_result={'trust_score': 0.92, 'verdict': 'APPROVED'}
    )
    
    logger.info(f"Published attestation: {attestation_id}")
