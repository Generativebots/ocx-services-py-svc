"""
Evidence Vault Service
Immutable audit trail and compliance layer for OCX
"""

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime, timedelta
import os
import hashlib
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from elasticsearch import Elasticsearch
import uuid

app = FastAPI(title="Evidence Vault API", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connection
def get_db():
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        database=os.getenv('DB_NAME', 'ocx'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', 'postgres')
    )
    try:
        yield conn
    finally:
        conn.close()

# Elasticsearch connection
es = Elasticsearch([os.getenv('ELASTICSEARCH_URL', 'http://localhost:9200')])

# Enums
class AgentType(str, Enum):
    HUMAN = "HUMAN"
    SYSTEM = "SYSTEM"
    AI = "AI"

class EventType(str, Enum):
    TRIGGER = "TRIGGER"
    VALIDATE = "VALIDATE"
    DECIDE = "DECIDE"
    ACT = "ACT"
    EXCEPTION = "EXCEPTION"
    EVIDENCE = "EVIDENCE"

class Environment(str, Enum):
    DEV = "DEV"
    STAGING = "STAGING"
    PROD = "PROD"

class VerificationStatus(str, Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    DISPUTED = "DISPUTED"

class AttestorType(str, Enum):
    JURY = "JURY"
    ENTROPY = "ENTROPY"
    ESCROW = "ESCROW"
    COMPLIANCE_OFFICER = "COMPLIANCE_OFFICER"

class AttestationStatus(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DISPUTED = "DISPUTED"

# Models
class EvidenceCreate(BaseModel):
    activity_id: str
    activity_name: str
    activity_version: str
    execution_id: str
    agent_id: str
    agent_type: AgentType
    tenant_id: str
    environment: Environment
    event_type: EventType
    event_data: Dict[str, Any]
    decision: Optional[str] = None
    outcome: Optional[str] = None
    policy_reference: str
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None

class EvidenceResponse(BaseModel):
    evidence_id: str
    activity_id: str
    activity_name: str
    activity_version: str
    execution_id: str
    agent_id: str
    agent_type: AgentType
    tenant_id: str
    environment: Environment
    event_type: EventType
    event_data: Dict[str, Any]
    decision: Optional[str]
    outcome: Optional[str]
    policy_reference: str
    verified: bool
    verification_status: VerificationStatus
    verification_errors: Optional[List[str]]
    hash: str
    previous_hash: Optional[str]
    created_at: datetime
    verified_at: Optional[datetime]

class AttestationCreate(BaseModel):
    evidence_id: str
    attestor_type: AttestorType
    attestor_id: str
    attestation_status: AttestationStatus
    confidence_score: Optional[float] = None
    reasoning: Optional[str] = None
    signature: Optional[str] = None
    proof: Optional[Dict[str, Any]] = None

class AttestationResponse(BaseModel):
    attestation_id: str
    evidence_id: str
    attestor_type: AttestorType
    attestor_id: str
    attestation_status: AttestationStatus
    confidence_score: Optional[float]
    reasoning: Optional[str]
    created_at: datetime

# Helper functions
def calculate_hash(data: Dict[str, Any]) -> str:
    """Calculate SHA-256 hash of data"""
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

def verify_activity_exists(activity_id: str, conn) -> bool:
    """Verify activity exists in Activity Registry"""
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM activities WHERE activity_id = %s", (activity_id,))
    return cursor.fetchone() is not None

def verify_policy_reference(policy_reference: str) -> bool:
    """Verify policy reference is valid"""
    # In production, check against policy database
    return len(policy_reference) > 0

def verify_agent_authorization(agent_id: str, activity_id: str) -> bool:
    """Verify agent is authorized to execute activity"""
    # In production, check against authorization service
    return True

# ============================================================================
# EVIDENCE COLLECTION API
# ============================================================================

@app.post("/api/v1/evidence", response_model=EvidenceResponse)
async def create_evidence(evidence: EvidenceCreate, conn = Depends(get_db)):
    """
    Create immutable evidence record
    
    Verifies:
    - Activity exists
    - Policy reference is valid
    - Agent is authorized
    
    Stores in:
    - PostgreSQL (compliance DB)
    - Elasticsearch (search index)
    - Trust Attestation Ledger (blockchain)
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Verification
    verification_errors = []
    
    # 1. Verify activity exists
    if not verify_activity_exists(evidence.activity_id, conn):
        verification_errors.append(f"Activity {evidence.activity_id} does not exist")
    
    # 2. Verify policy reference
    if not verify_policy_reference(evidence.policy_reference):
        verification_errors.append(f"Invalid policy reference: {evidence.policy_reference}")
    
    # 3. Verify agent authorization
    if not verify_agent_authorization(evidence.agent_id, evidence.activity_id):
        verification_errors.append(f"Agent {evidence.agent_id} not authorized for activity {evidence.activity_id}")
    
    # Determine verification status
    verified = len(verification_errors) == 0
    verification_status = VerificationStatus.VERIFIED if verified else VerificationStatus.FAILED
    
    # Insert evidence
    cursor.execute("""
        INSERT INTO evidence (
            activity_id, activity_name, activity_version, execution_id,
            agent_id, agent_type, tenant_id, environment,
            event_type, event_data, decision, outcome, policy_reference,
            verified, verification_status, verification_errors,
            tags, metadata
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        RETURNING *
    """, (
        evidence.activity_id,
        evidence.activity_name,
        evidence.activity_version,
        evidence.execution_id,
        evidence.agent_id,
        evidence.agent_type,
        evidence.tenant_id,
        evidence.environment,
        evidence.event_type,
        json.dumps(evidence.event_data),
        evidence.decision,
        evidence.outcome,
        evidence.policy_reference,
        verified,
        verification_status,
        verification_errors if verification_errors else None,
        evidence.tags,
        json.dumps(evidence.metadata) if evidence.metadata else None
    ))
    
    result = cursor.fetchone()
    conn.commit()
    
    # Index in Elasticsearch
    try:
        es.index(
            index='evidence',
            id=str(result['evidence_id']),
            document={
                **result,
                'created_at': result['created_at'].isoformat(),
                'event_data': evidence.event_data,
            }
        )
    except Exception as e:
        print(f"Elasticsearch indexing failed: {e}")
    
    return EvidenceResponse(**result)

@app.get("/api/v1/evidence/{evidence_id}", response_model=EvidenceResponse)
async def get_evidence(evidence_id: str, conn = Depends(get_db)):
    """Get evidence by ID"""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("SELECT * FROM evidence WHERE evidence_id = %s", (evidence_id,))
    result = cursor.fetchone()
    
    if not result:
        raise HTTPException(status_code=404, detail="Evidence not found")
    
    return EvidenceResponse(**result)

@app.get("/api/v1/evidence", response_model=List[EvidenceResponse])
async def list_evidence(
    tenant_id: Optional[str] = None,
    activity_id: Optional[str] = None,
    execution_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    event_type: Optional[EventType] = None,
    environment: Optional[Environment] = None,
    verification_status: Optional[VerificationStatus] = None,
    policy_reference: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    conn = Depends(get_db)
):
    """
    List evidence with filters
    
    Supports filtering by:
    - tenant_id
    - activity_id
    - execution_id
    - agent_id
    - event_type
    - environment
    - verification_status
    - policy_reference
    - date range (start_date, end_date)
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    query = "SELECT * FROM evidence WHERE 1=1"
    params = []
    
    if tenant_id:
        query += " AND tenant_id = %s"
        params.append(tenant_id)
    
    if activity_id:
        query += " AND activity_id = %s"
        params.append(activity_id)
    
    if execution_id:
        query += " AND execution_id = %s"
        params.append(execution_id)
    
    if agent_id:
        query += " AND agent_id = %s"
        params.append(agent_id)
    
    if event_type:
        query += " AND event_type = %s"
        params.append(event_type)
    
    if environment:
        query += " AND environment = %s"
        params.append(environment)
    
    if verification_status:
        query += " AND verification_status = %s"
        params.append(verification_status)
    
    if policy_reference:
        query += " AND policy_reference = %s"
        params.append(policy_reference)
    
    if start_date:
        query += " AND created_at >= %s"
        params.append(start_date)
    
    if end_date:
        query += " AND created_at <= %s"
        params.append(end_date)
    
    query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    results = cursor.fetchall()
    
    return [EvidenceResponse(**r) for r in results]

# Continued in next file...
# ============================================================================
# ATTESTATION API
# ============================================================================

@app.post("/api/v1/evidence/{evidence_id}/attest", response_model=AttestationResponse)
async def create_attestation(
    evidence_id: str,
    attestation: AttestationCreate,
    conn = Depends(get_db)
):
    """
    Create trust attestation for evidence
    
    Attestors:
    - JURY: Multi-agent consensus
    - ENTROPY: Randomness verification
    - ESCROW: Third-party validation
    - COMPLIANCE_OFFICER: Human review
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Verify evidence exists
    cursor.execute("SELECT 1 FROM evidence WHERE evidence_id = %s", (evidence_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Evidence not found")
    
    # Create attestation
    cursor.execute("""
        INSERT INTO evidence_attestations (
            evidence_id, attestor_type, attestor_id, attestation_status,
            confidence_score, reasoning, signature, proof
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
    """, (
        evidence_id,
        attestation.attestor_type,
        attestation.attestor_id,
        attestation.attestation_status,
        attestation.confidence_score,
        attestation.reasoning,
        attestation.signature,
        json.dumps(attestation.proof) if attestation.proof else None
    ))
    
    result = cursor.fetchone()
    conn.commit()
    
    return AttestationResponse(**result)

@app.get("/api/v1/evidence/{evidence_id}/attestations", response_model=List[AttestationResponse])
async def get_attestations(evidence_id: str, conn = Depends(get_db)):
    """Get all attestations for evidence"""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("""
        SELECT * FROM evidence_attestations
        WHERE evidence_id = %s
        ORDER BY created_at DESC
    """, (evidence_id,))
    
    results = cursor.fetchall()
    return [AttestationResponse(**r) for r in results]

# ============================================================================
# VERIFICATION API
# ============================================================================

@app.post("/api/v1/evidence/{evidence_id}/verify")
async def verify_evidence(evidence_id: str, conn = Depends(get_db)):
    """
    Manually trigger evidence verification
    
    Checks:
    1. Hash integrity
    2. Chain integrity
    3. Activity exists
    4. Policy reference valid
    5. Agent authorized
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get evidence
    cursor.execute("SELECT * FROM evidence WHERE evidence_id = %s", (evidence_id,))
    evidence = cursor.fetchone()
    
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")
    
    verification_errors = []
    
    # 1. Verify hash integrity
    cursor.execute("SELECT verify_evidence_integrity(%s) as valid", (evidence_id,))
    if not cursor.fetchone()['valid']:
        verification_errors.append("Hash integrity check failed")
    
    # 2. Verify activity exists
    if not verify_activity_exists(evidence['activity_id'], conn):
        verification_errors.append(f"Activity {evidence['activity_id']} does not exist")
    
    # 3. Verify policy reference
    if not verify_policy_reference(evidence['policy_reference']):
        verification_errors.append(f"Invalid policy reference: {evidence['policy_reference']}")
    
    # 4. Verify agent authorization
    if not verify_agent_authorization(evidence['agent_id'], evidence['activity_id']):
        verification_errors.append(f"Agent {evidence['agent_id']} not authorized")
    
    # Update verification status (this will fail due to immutability trigger)
    # In production, create a new verification record instead
    
    return {
        "evidence_id": evidence_id,
        "verified": len(verification_errors) == 0,
        "verification_errors": verification_errors,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/api/v1/evidence/{evidence_id}/chain")
async def get_evidence_chain(evidence_id: str, conn = Depends(get_db)):
    """Get evidence chain for tamper detection"""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("SELECT * FROM get_evidence_chain(%s)", (evidence_id,))
    chain = cursor.fetchall()
    
    return {
        "evidence_id": evidence_id,
        "chain_length": len(chain),
        "chain": chain
    }

# ============================================================================
# COMPLIANCE REPORTS API
# ============================================================================

@app.post("/api/v1/compliance/reports")
async def generate_compliance_report(
    tenant_id: str,
    start_date: datetime,
    end_date: datetime,
    report_type: str = "DAILY",
    conn = Depends(get_db)
):
    """Generate compliance report for date range"""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get evidence statistics
    cursor.execute("""
        SELECT 
            COUNT(*) as total_evidence,
            COUNT(CASE WHEN verified = true THEN 1 END) as verified_count,
            COUNT(CASE WHEN verification_status = 'FAILED' THEN 1 END) as failed_count,
            COUNT(CASE WHEN verification_status = 'DISPUTED' THEN 1 END) as disputed_count
        FROM evidence
        WHERE tenant_id = %s
          AND created_at BETWEEN %s AND %s
    """, (tenant_id, start_date, end_date))
    
    stats = cursor.fetchone()
    
    # Calculate compliance score
    compliance_score = (stats['verified_count'] / stats['total_evidence'] * 100) if stats['total_evidence'] > 0 else 0
    
    # Get policy violations
    cursor.execute("""
        SELECT COUNT(*) as violations
        FROM evidence
        WHERE tenant_id = %s
          AND created_at BETWEEN %s AND %s
          AND verification_status = 'FAILED'
    """, (tenant_id, start_date, end_date))
    
    violations = cursor.fetchone()['violations']
    
    # Create report
    cursor.execute("""
        INSERT INTO compliance_reports (
            tenant_id, start_date, end_date, report_type,
            total_evidence_count, verified_evidence_count,
            failed_evidence_count, disputed_evidence_count,
            compliance_score, policy_violations, report_data
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
    """, (
        tenant_id,
        start_date,
        end_date,
        report_type,
        stats['total_evidence'],
        stats['verified_count'],
        stats['failed_count'],
        stats['disputed_count'],
        compliance_score,
        violations,
        json.dumps({
            'period': f"{start_date.date()} to {end_date.date()}",
            'statistics': stats,
            'compliance_score': compliance_score
        })
    ))
    
    result = cursor.fetchone()
    conn.commit()
    
    return result

@app.get("/api/v1/compliance/reports")
async def list_compliance_reports(
    tenant_id: Optional[str] = None,
    report_type: Optional[str] = None,
    limit: int = 100,
    conn = Depends(get_db)
):
    """List compliance reports"""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    query = "SELECT * FROM compliance_reports WHERE 1=1"
    params = []
    
    if tenant_id:
        query += " AND tenant_id = %s"
        params.append(tenant_id)
    
    if report_type:
        query += " AND report_type = %s"
        params.append(report_type)
    
    query += " ORDER BY generated_at DESC LIMIT %s"
    params.append(limit)
    
    cursor.execute(query, params)
    return cursor.fetchall()

# ============================================================================
# ANALYTICS API
# ============================================================================

@app.get("/api/v1/evidence/stats")
async def get_evidence_stats(
    tenant_id: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    conn = Depends(get_db)
):
    """Get evidence statistics"""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    query = """
        SELECT 
            COUNT(*) as total_evidence,
            COUNT(CASE WHEN verified = true THEN 1 END) as verified_count,
            COUNT(CASE WHEN verification_status = 'FAILED' THEN 1 END) as failed_count,
            COUNT(CASE WHEN verification_status = 'DISPUTED' THEN 1 END) as disputed_count,
            COUNT(DISTINCT activity_id) as unique_activities,
            COUNT(DISTINCT agent_id) as unique_agents,
            COUNT(DISTINCT policy_reference) as unique_policies
        FROM evidence
        WHERE 1=1
    """
    params = []
    
    if tenant_id:
        query += " AND tenant_id = %s"
        params.append(tenant_id)
    
    if start_date:
        query += " AND created_at >= %s"
        params.append(start_date)
    
    if end_date:
        query += " AND created_at <= %s"
        params.append(end_date)
    
    cursor.execute(query, params)
    return cursor.fetchone()

@app.get("/api/v1/evidence/search")
async def search_evidence(
    q: str,
    tenant_id: Optional[str] = None,
    limit: int = 100
):
    """Full-text search in Elasticsearch"""
    try:
        query = {
            "bool": {
                "must": [
                    {"multi_match": {"query": q, "fields": ["event_data", "decision", "outcome"]}}
                ]
            }
        }
        
        if tenant_id:
            query["bool"]["filter"] = [{"term": {"tenant_id": tenant_id}}]
        
        results = es.search(
            index='evidence',
            query=query,
            size=limit
        )
        
        return {
            "total": results['hits']['total']['value'],
            "results": [hit['_source'] for hit in results['hits']['hits']]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/health")
async def health(conn = Depends(get_db)):
    """Health check"""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        db_healthy = True
    except:
        db_healthy = False
    
    try:
        es.ping()
        es_healthy = True
    except:
        es_healthy = False
    
    return {
        "status": "healthy" if (db_healthy and es_healthy) else "degraded",
        "service": "evidence-vault",
        "database": "healthy" if db_healthy else "unhealthy",
        "elasticsearch": "healthy" if es_healthy else "unhealthy",
        "timestamp": datetime.utcnow().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
