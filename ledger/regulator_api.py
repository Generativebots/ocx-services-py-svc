"""
Regulator API - Additive Compliance Layer

Provides external API for regulators to access governance audit trails.
Does NOT modify core OCX enforcement - only provides read-only access.
"""

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional, List, Any
import secrets
import logging
import os

logger = logging.getLogger(__name__)

app = FastAPI(title="OCX Regulator API", version="1.0.0")

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory API key storage (replace with database in production)
REGULATOR_API_KEYS = {}


# Response models
class AuditTrailPeriod(BaseModel):
    start: str
    end: str

class AuditTrailStatistics(BaseModel):
    total_actions: int
    blocked_actions: int
    sequestered_actions: int
    pass_rate: float

class AuditTrailResponse(BaseModel):
    agent_id: str
    period: AuditTrailPeriod
    statistics: AuditTrailStatistics
    entries: List[Any]

class ChainVerifyResponse(BaseModel):
    chain_valid: bool
    verified_at: str
    verified_by: str

class ApiKeyRegulatorInfo(BaseModel):
    name: str
    organization: str
    created_at: str

class ApiKeyResponse(BaseModel):
    api_key: str
    regulator: ApiKeyRegulatorInfo
    usage: str

class HealthResponse(BaseModel):
    status: str
    service: str


def verify_api_key(x_api_key: str = Header(...)) -> dict:
    """
    Verify regulator API key.
    
    Args:
        x_api_key: API key from request header
    
    Raises:
        HTTPException: If API key is invalid
    """
    if x_api_key not in REGULATOR_API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return REGULATOR_API_KEYS[x_api_key]


@app.get("/api/regulator/certificate/{transaction_id}")
def get_compliance_certificate(
    transaction_id: str,
    regulator: dict = Depends(verify_api_key)
) -> Any:
    """
    Get compliance certificate PDF for a specific transaction.
    
    This is a READ-ONLY endpoint - it does not modify OCX behavior.
    
    Args:
        transaction_id: Transaction ID
        regulator: Verified regulator info (from API key)
    
    Returns:
        PDF file
    """
    from certificate_generator import ComplianceCertificateGenerator
    from immutable_ledger import ImmutableGovernanceLedger
    
    # Initialize services
    ledger = ImmutableGovernanceLedger()
    generator = ComplianceCertificateGenerator(ledger)
    
    # Generate certificate
    pdf_bytes = generator.generate_certificate_by_tx_id(transaction_id)
    
    if not pdf_bytes:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    logger.info(f"Regulator {regulator['name']} accessed certificate for {transaction_id}")
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=compliance_{transaction_id}.pdf"
        }
    )


@app.get("/api/regulator/audit-trail/{agent_id}", response_model=AuditTrailResponse)
def get_audit_trail(
    agent_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    regulator: dict = Depends(verify_api_key)
) -> Any:
    """
    Get audit trail for a specific agent.
    
    This is a READ-ONLY endpoint - it does not modify OCX behavior.
    
    Args:
        agent_id: Agent ID
        start_date: Optional start date (ISO format)
        end_date: Optional end date (ISO format)
        regulator: Verified regulator info
    
    Returns:
        JSON: List of governance events
    """
    from immutable_ledger import ImmutableGovernanceLedger
    
    ledger = ImmutableGovernanceLedger()
    entries = ledger.get_agent_trail(agent_id, start_date, end_date)
    
    # Calculate statistics
    total_actions = len(entries)
    blocked_actions = sum(1 for e in entries if e.get('jury_verdict') == 'FAILURE')
    sequestered_actions = sum(1 for e in entries if e.get('sop_decision') == 'SEQUESTERED')
    
    logger.info(f"Regulator {regulator['name']} accessed audit trail for {agent_id}")
    
    return AuditTrailResponse(
        agent_id=agent_id,
        period=AuditTrailPeriod(
            start=start_date or 'beginning',
            end=end_date or 'now'
        ),
        statistics=AuditTrailStatistics(
            total_actions=total_actions,
            blocked_actions=blocked_actions,
            sequestered_actions=sequestered_actions,
            pass_rate=(total_actions - blocked_actions) / total_actions if total_actions > 0 else 0
        ),
        entries=entries
    )


@app.get("/api/regulator/verify-chain", response_model=ChainVerifyResponse)
def verify_chain(regulator: dict = Depends(verify_api_key)) -> ChainVerifyResponse:
    """
    Verify integrity of entire governance ledger chain.
    
    This is a READ-ONLY endpoint - it does not modify OCX behavior.
    
    Args:
        regulator: Verified regulator info
    
    Returns:
        JSON: Verification status
    """
    from immutable_ledger import ImmutableGovernanceLedger
    
    ledger = ImmutableGovernanceLedger()
    is_valid = ledger.verify_chain()
    
    logger.info(f"Regulator {regulator['name']} verified chain: {is_valid}")
    
    return ChainVerifyResponse(
        chain_valid=is_valid,
        verified_at=__import__('datetime').datetime.utcnow().isoformat(),
        verified_by=regulator['name']
    )


@app.post("/api/regulator/api-key", response_model=ApiKeyResponse)
def generate_api_key(
    regulator_name: str,
    regulator_org: str,
    admin_secret: str
) -> Any:
    """
    Generate API key for a regulator (admin only).
    
    Args:
        regulator_name: Regulator name
        regulator_org: Regulator organization
        admin_secret: Admin secret key
    
    Returns:
        JSON: API key
    """
    # Verify admin secret from environment (never hardcoded)
    expected_secret = os.environ.get("REGULATOR_ADMIN_SECRET")
    if not expected_secret:
        raise HTTPException(status_code=500, detail="Admin secret not configured")
    if admin_secret != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    
    # Generate API key
    api_key = secrets.token_urlsafe(32)
    
    # Store regulator info
    REGULATOR_API_KEYS[api_key] = {
        'name': regulator_name,
        'organization': regulator_org,
        'created_at': __import__('datetime').datetime.utcnow().isoformat()
    }
    
    logger.info(f"Generated API key for regulator: {regulator_name} ({regulator_org})")
    
    return ApiKeyResponse(
        api_key=api_key,
        regulator=ApiKeyRegulatorInfo(**REGULATOR_API_KEYS[api_key]),
        usage=f'Include in request header as: X-API-Key: {api_key}'
    )


@app.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="healthy", service="OCX Regulator API")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
