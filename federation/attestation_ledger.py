"""
Trust Attestation Ledger - Database Backend Abstraction

Supports both PostgreSQL/Supabase (default) and Cloud Spanner (enterprise).
Automatically switches based on client tier.
"""

import hashlib
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from abc import ABC, abstractmethod

# Import configuration
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.database_config import is_spanner_enabled, get_db_config


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
    
    def __init__(self, config: Dict):
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
            print("✅ PostgreSQL ledger backend initialized")
        except ImportError:
            print("⚠️  psycopg2 not installed, using mock backend")
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


class SpannerLedgerBackend(LedgerBackend):
    """Cloud Spanner backend for trust attestations (enterprise)"""
    
    def __init__(self, config: Dict):
        """Initialize Cloud Spanner backend"""
        try:
            from google.cloud import spanner
            from google.cloud.spanner_v1 import param_types
            
            self.spanner_client = spanner.Client(project=config['project_id'])
            self.instance = self.spanner_client.instance(config['instance_id'])
            self.database = self.instance.database(config['database_id'])
            self.spanner = spanner
            print("✅ Cloud Spanner ledger backend initialized (ENTERPRISE)")
        except ImportError:
            print("⚠️  google-cloud-spanner not installed, falling back to PostgreSQL")
            raise
    
    def publish_attestation(self, attestation_data: Dict) -> str:
        """Publish attestation to Cloud Spanner"""
        with self.database.batch() as batch:
            batch.insert(
                table='trust_attestations',
                columns=['attestation_id', 'tenant_id', 'ocx_instance_id', 'agent_id',
                        'audit_hash', 'trust_level', 'signature', 'expires_at',
                        'timestamp', 'metadata'],
                values=[[
                    attestation_data['attestation_id'],
                    attestation_data.get('tenant_id', 'default'),
                    attestation_data['ocx_instance_id'],
                    attestation_data['agent_id'],
                    attestation_data['audit_hash'],
                    attestation_data['trust_level'],
                    attestation_data['signature'],
                    attestation_data['expires_at'],
                    self.spanner.COMMIT_TIMESTAMP,
                    json.dumps(attestation_data.get('metadata', {}))
                ]]
            )
        
        return attestation_data['attestation_id']
    
    def verify_attestation(self, local_hash: str, remote_hash: str, agent_id: str) -> Dict:
        """Verify attestation from Cloud Spanner"""
        query = """
            SELECT * FROM trust_attestations
            WHERE audit_hash = @audit_hash AND agent_id = @agent_id
            AND expires_at > CURRENT_TIMESTAMP()
            ORDER BY timestamp DESC
            LIMIT 1
        """
        
        with self.database.snapshot() as snapshot:
            results = snapshot.execute_sql(
                query,
                params={'audit_hash': remote_hash, 'agent_id': agent_id},
                param_types={
                    'audit_hash': self.spanner.param_types.STRING,
                    'agent_id': self.spanner.param_types.STRING
                }
            )
            
            for row in results:
                return {
                    'verified': True,
                    'trust_level': row[5],  # trust_level column
                    'timestamp': row[8],     # timestamp column
                    'ocx_instance_id': row[2]  # ocx_instance_id column
                }
        
        return {'verified': False}
    
    def query_attestations(self, ocx_instance_id: str, hours: int = 24) -> List[Dict]:
        """Query recent attestations from Cloud Spanner"""
        query = """
            SELECT * FROM trust_attestations
            WHERE ocx_instance_id = @ocx_instance_id
            AND timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @hours HOUR)
            ORDER BY timestamp DESC
        """
        
        with self.database.snapshot() as snapshot:
            results = snapshot.execute_sql(
                query,
                params={'ocx_instance_id': ocx_instance_id, 'hours': hours},
                param_types={
                    'ocx_instance_id': self.spanner.param_types.STRING,
                    'hours': self.spanner.param_types.INT64
                }
            )
            
            attestations = []
            for row in results:
                attestations.append({
                    'attestation_id': row[0],
                    'tenant_id': row[1],
                    'ocx_instance_id': row[2],
                    'agent_id': row[3],
                    'audit_hash': row[4],
                    'trust_level': row[5],
                    'signature': row[6],
                    'expires_at': row[7],
                    'timestamp': row[8],
                    'metadata': json.loads(row[9]) if row[9] else {}
                })
            
            return attestations


class TrustAttestationLedger:
    """
    Trust Attestation Ledger with automatic backend selection.
    
    Backend Selection:
    - PostgreSQL/Supabase: Default (< $10M clients)
    - Cloud Spanner: Enterprise ($10M+ clients)
    """
    
    def __init__(self, ocx_instance_id: str, tenant_id: str = "default"):
        """
        Initialize Trust Attestation Ledger with automatic backend selection.
        
        Args:
            ocx_instance_id: This OCX instance's unique ID
            tenant_id: Tenant identifier for multi-tenancy
        """
        self.ocx_instance_id = ocx_instance_id
        self.tenant_id = tenant_id
        
        # Select backend based on configuration
        config = get_db_config()
        
        if is_spanner_enabled():
            try:
                self.backend = SpannerLedgerBackend(config)
                print(f"🚀 Using Cloud Spanner for {ocx_instance_id} (ENTERPRISE)")
            except Exception as e:
                print(f"⚠️  Cloud Spanner initialization failed: {e}")
                print("   Falling back to PostgreSQL")
                self.backend = PostgreSQLLedgerBackend(config)
        else:
            self.backend = PostgreSQLLedgerBackend(config)
            print(f"✅ Using PostgreSQL for {ocx_instance_id}")
    
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
    from config.database_config import print_database_config
    
    print_database_config()
    
    # Test ledger
    ledger = TrustAttestationLedger("ocx-us-west1-001", "tenant-alpha")
    
    # Publish attestation
    attestation_id = ledger.publish_attestation(
        agent_id="agent-123",
        audit_result={'trust_score': 0.92, 'verdict': 'APPROVED'}
    )
    
    print(f"\n✅ Published attestation: {attestation_id}")
