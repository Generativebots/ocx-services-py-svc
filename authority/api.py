"""
Authority Discovery API - FastAPI service
Provides REST endpoints for authority gap scanning
"""

import os
import uuid
import json
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from scanner import AuthorityGapScanner
from mock_scanner import MockScanner
from use_case_generator import A2AUseCaseGenerator
from impact_estimator import BusinessImpactEstimator
import logging
logger = logging.getLogger(__name__)

app = FastAPI(title="Authority Discovery API", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize scanner (use mock for demos)
USE_MOCK = os.getenv('USE_MOCK_SCANNER', 'true').lower() == 'true'
db_url = os.getenv('DATABASE_URL', 'postgresql://localhost/ocx')

if USE_MOCK:
    import psycopg2
    db_conn = psycopg2.connect(db_url)
    scanner = MockScanner(db_conn)
    use_case_generator = A2AUseCaseGenerator(db_conn)
    impact_estimator = BusinessImpactEstimator(db_conn)
    print("✅ Using Mock Scanner for demo")
else:
    import psycopg2
    db_conn = psycopg2.connect(db_url)
    scanner = AuthorityGapScanner(
        db_url=db_url,
        anthropic_api_key=os.getenv('ANTHROPIC_API_KEY')
    )
    use_case_generator = A2AUseCaseGenerator(db_conn)
    impact_estimator = BusinessImpactEstimator(db_conn)
    print("✅ Using Real Scanner with Claude AI")

# Models
class ScanRequest(BaseModel):
    tenant_id: str
    doc_type: str  # BPMN, SOP, RACI, INCIDENT_LOG, APPROVAL_WORKFLOW, AUDIT

class ScanResponse(BaseModel):
    scan_id: str
    doc_id: str
    gaps_found: int
    gap_ids: List[str]

class AuthorityGap(BaseModel):
    gap_id: str
    gap_type: str
    severity: str
    decision_point: str
    current_authority_holder: Optional[str]
    execution_system: Optional[str]
    accountability_gap: Optional[str]
    override_frequency: int
    time_sensitivity: str
    a2a_candidacy_score: float
    status: str

class GapListResponse(BaseModel):
    gaps: List[AuthorityGap]
    total: int

# A2A Models
class GenerateUseCaseRequest(BaseModel):
    gap_id: str
    tenant_id: str

class Agent(BaseModel):
    name: str
    role: str
    type: str

class UseCase(BaseModel):
    use_case_id: str
    gap_id: str
    pattern_type: str
    title: str
    description: str
    agents_involved: List[Agent]
    current_problem: str
    ocx_proposal: str
    authority_contract: Optional[str] = None
    status: str

class UseCaseListResponse(BaseModel):
    use_cases: List[UseCase]
    total: int

class SimulationStep(BaseModel):
    step_number: int
    agent: str
    action: str
    timestamp: str
    status: str

class SimulateRequest(BaseModel):
    use_case_id: str
    scenario: Dict[str, Any]
    agent_action_1: Optional[str] = "propose_payment"
    agent_action_2: Optional[str] = "validate_compliance"

class SimulationResult(BaseModel):
    simulation_id: str
    use_case_id: str
    verdict: str
    steps: List[SimulationStep]
    final_decision: str
    execution_time_ms: int

class ImpactEstimateRequest(BaseModel):
    use_case_id: str
    assumptions: Dict[str, Any]

class ImpactEstimate(BaseModel):
    estimate_id: str
    use_case_id: str
    current_monthly_cost: float
    a2a_monthly_savings: float
    net_monthly_savings: float
    annual_roi: float
    payback_period_months: float
    assumptions: Dict[str, Any]

# Endpoints
@app.post("/api/v1/authority/scan", response_model=ScanResponse)
async def scan_document(
    tenant_id: str,
    doc_type: str,
    file: UploadFile = File(...)
) -> Any:
    """
    Upload and scan a document for authority gaps
    
    Args:
        tenant_id: Company identifier
        doc_type: Type of document (BPMN, SOP, RACI, etc.)
        file: Document file to scan
    
    Returns:
        Scan results with detected gaps
    """
    # Read file content
    content = await file.read()
    content_str = content.decode('utf-8')
    
    # Scan document
    result = scanner.scan_document(
        tenant_id=tenant_id,
        doc_type=doc_type,
        file_path=file.filename,
        file_content=content_str
    )
    
    return ScanResponse(
        scan_id=str(uuid.uuid4()),
        doc_id=result['doc_id'],
        gaps_found=result['gaps_found'],
        gap_ids=result['gap_ids']
    )

@app.get("/api/v1/authority/gaps", response_model=GapListResponse)
async def get_gaps(
    tenant_id: str,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 100
) -> Any:
    """
    Get all authority gaps for a company
    
    Args:
        tenant_id: Company identifier
        status: Filter by status (PENDING, REVIEWED, CONVERTED, DISMISSED)
        severity: Filter by severity (HIGH, MEDIUM, LOW)
        limit: Maximum number of gaps to return
    
    Returns:
        List of authority gaps
    """
    gaps = scanner.get_gaps(tenant_id=tenant_id, status=status)
    
    # Filter by severity if provided
    if severity:
        gaps = [g for g in gaps if g['severity'] == severity]
    
    # Limit results
    gaps = gaps[:limit]
    
    return GapListResponse(
        gaps=[AuthorityGap(**g) for g in gaps],
        total=len(gaps)
    )

@app.get("/api/v1/authority/gaps/{gap_id}", response_model=AuthorityGap)
async def get_gap(gap_id: str) -> Any:
    """Get a specific authority gap by ID"""
    gap = scanner.get_gap_by_id(gap_id)
    if not gap:
        raise HTTPException(status_code=404, detail=f"Gap {gap_id} not found")
    return AuthorityGap(**gap)

@app.put("/api/v1/authority/gaps/{gap_id}/status")
async def update_gap_status(gap_id: str, status: str) -> dict:
    """Update the status of an authority gap"""
    updated = scanner.update_gap_status(gap_id, status)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Gap {gap_id} not found")
    return {"gap_id": gap_id, "status": status, "message": "Status updated"}

# ============================================================================
# A2A USE CASES ENDPOINTS
# ============================================================================

@app.post("/api/v1/a2a/use-cases/generate", response_model=UseCase)
async def generate_use_case(request: GenerateUseCaseRequest) -> Any:
    """
    Generate an A2A use case from an authority gap
    
    Args:
        request: Contains gap_id and tenant_id
    
    Returns:
        Generated A2A use case
    """
    try:
        # Get the gap details first
        gaps = scanner.get_gaps(tenant_id=request.tenant_id)
        gap = next((g for g in gaps if g['gap_id'] == request.gap_id), None)
        
        if not gap:
            raise HTTPException(status_code=404, detail=f"Gap {request.gap_id} not found")
        
        # Create canvas from gap data
        canvas = {
            'decisionPoint': {'description': gap['decision_point'], 'reversible': True},
            'currentAuthorityHolder': {'name': gap.get('current_authority_holder', 'Unknown')},
            'executionSystem': gap.get('execution_system', 'Manual'),
            'accountabilityGap': {'blamedParty': gap.get('accountability_gap', 'Unknown'), 'isAuthorityHolder': False},
            'overrideFrequency': gap.get('override_frequency', 0),
            'timeSensitivity': gap.get('time_sensitivity', 'hours')
        }
        
        # Generate use case
        use_case = use_case_generator.generate_use_case(request.gap_id, canvas)
        
        return UseCase(**use_case)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate use case: {str(e)}")

@app.get("/api/v1/a2a/use-cases", response_model=UseCaseListResponse)
async def get_use_cases(
    tenant_id: str = "00000000-0000-0000-0000-000000000001",
    pattern_type: Optional[str] = None
) -> Any:
    """
    Get all A2A use cases for a company
    
    Args:
        tenant_id: Company identifier
        pattern_type: Optional filter by pattern (Arbitration, Escalation, etc.)
    
    Returns:
        List of A2A use cases
    """
    try:
        use_cases = use_case_generator.get_use_cases(tenant_id, pattern_type)
        
        # Convert to response format
        formatted_cases = []
        for uc in use_cases:
            formatted_cases.append(UseCase(
                use_case_id=uc['use_case_id'],
                gap_id=uc['gap_id'],
                pattern_type=uc['pattern_type'],
                title=uc['title'],
                description=uc['description'],
                agents_involved=[Agent(**agent) for agent in uc['agents_involved']],
                current_problem=uc['current_problem'],
                ocx_proposal=uc['ocx_proposal'],
                authority_contract=uc.get('authority_contract'),
                status=uc['status']
            ))
        
        return UseCaseListResponse(use_cases=formatted_cases, total=len(formatted_cases))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch use cases: {str(e)}")

@app.get("/api/v1/a2a/use-cases/{use_case_id}", response_model=UseCase)
async def get_use_case(use_case_id: str, tenant_id: str = "00000000-0000-0000-0000-000000000001") -> Any:
    """Get a specific A2A use case by ID"""
    try:
        use_cases = use_case_generator.get_use_cases(tenant_id)
        use_case = next((uc for uc in use_cases if uc['use_case_id'] == use_case_id), None)
        
        if not use_case:
            raise HTTPException(status_code=404, detail=f"Use case {use_case_id} not found")
        
        return UseCase(
            use_case_id=use_case['use_case_id'],
            gap_id=use_case['gap_id'],
            pattern_type=use_case['pattern_type'],
            title=use_case['title'],
            description=use_case['description'],
            agents_involved=[Agent(**agent) for agent in use_case['agents_involved']],
            current_problem=use_case['current_problem'],
            ocx_proposal=use_case['ocx_proposal'],
            authority_contract=use_case.get('authority_contract'),
            status=use_case['status']
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch use case: {str(e)}")

# ============================================================================
# SIMULATOR ENDPOINTS
# ============================================================================

@app.post("/api/v1/a2a/simulator/run", response_model=SimulationResult)
async def run_simulation(request: SimulateRequest) -> None:
    """
    Run a what-if simulation for an A2A use case
    
    Args:
        request: Contains use_case_id, scenario, and agent actions
    
    Returns:
        Simulation results with verdict and authority flow
    """
    try:
        import time
        import random

        
        simulation_id = str(uuid.uuid4())
        start_time = time.time()
        
        # Simulate authority flow (in production, this would use the actual EBCL runtime)
        steps = [
            SimulationStep(
                step_number=1,
                agent="Agent-1",
                action=f"Proposes action: {request.agent_action_1}",
                timestamp="0ms",
                status="completed"
            ),
            SimulationStep(
                step_number=2,
                agent="OCX-Jury",
                action="Evaluates against authority contract rules",
                timestamp="47ms",
                status="completed"
            ),
            SimulationStep(
                step_number=3,
                agent="Agent-2",
                action=f"Validates: {request.agent_action_2}",
                timestamp="123ms",
                status="completed"
            ),
            SimulationStep(
                step_number=4,
                agent="OCX-Jury",
                action="Final decision based on agent consensus and policy rules",
                timestamp="247ms",
                status="completed"
            )
        ]
        
        # Determine verdict (80% approval rate for demo)
        verdict = "APPROVED" if random.random() > 0.2 else "REJECTED"
        final_decision = (
            "Action approved with compliance verification. All authority contract rules satisfied."
            if verdict == "APPROVED"
            else "Action rejected due to policy violation. Escalation required."
        )
        
        execution_time = int((time.time() - start_time) * 1000) + 247  # Add simulated time
        
        # Store simulation result
        cursor = db_conn.cursor()
        cursor.execute("""
            INSERT INTO simulation_results 
            (simulation_id, use_case_id, tenant_id, scenario, verdict,
             authority_flow, final_decision, execution_time_ms)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            simulation_id,
            request.use_case_id,
            '00000000-0000-0000-0000-000000000001',
            json.dumps(request.scenario),
            verdict,
            json.dumps([step.dict() for step in steps]),
            final_decision,
            execution_time
        ))
        db_conn.commit()
        cursor.close()
        
        return SimulationResult(
            simulation_id=simulation_id,
            use_case_id=request.use_case_id,
            verdict=verdict,
            steps=steps,
            final_decision=final_decision,
            execution_time_ms=execution_time
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Simulation failed: {str(e)}")

@app.get("/api/v1/a2a/simulator/results/{simulation_id}", response_model=SimulationResult)
async def get_simulation_result(simulation_id: str) -> Any:
    """Get simulation results by ID"""
    try:
        cursor = db_conn.cursor()
        cursor.execute("""
            SELECT simulation_id, use_case_id, verdict, authority_flow,
                   final_decision, execution_time_ms
            FROM simulation_results
            WHERE simulation_id = %s
        """, (simulation_id,))
        
        row = cursor.fetchone()
        cursor.close()
        
        if not row:
            raise HTTPException(status_code=404, detail=f"Simulation {simulation_id} not found")
        
        steps = [SimulationStep(**step) for step in json.loads(row[3])]
        
        return SimulationResult(
            simulation_id=str(row[0]),
            use_case_id=str(row[1]),
            verdict=row[2],
            steps=steps,
            final_decision=row[4],
            execution_time_ms=row[5]
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch simulation: {str(e)}")

# ============================================================================
# IMPACT ESTIMATION ENDPOINTS
# ============================================================================

@app.post("/api/v1/a2a/impact/estimate", response_model=ImpactEstimate)
async def estimate_impact(request: ImpactEstimateRequest) -> Any:
    """
    Calculate business impact and ROI for an A2A use case
    
    Args:
        request: Contains use_case_id and assumptions
    
    Returns:
        Impact estimate with cost savings and ROI
    """
    try:
        impact = impact_estimator.calculate_impact(request.use_case_id, request.assumptions)
        return ImpactEstimate(**impact)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to estimate impact: {str(e)}")

@app.get("/api/v1/a2a/impact/{use_case_id}", response_model=ImpactEstimate)
async def get_impact_estimate(use_case_id: str) -> Any:
    """Get the most recent impact estimate for a use case"""
    try:
        cursor = db_conn.cursor()
        cursor.execute("""
            SELECT estimate_id, use_case_id, current_monthly_cost,
                   a2a_monthly_savings, net_monthly_savings, annual_roi,
                   payback_period_months, assumptions
            FROM business_impact_estimates
            WHERE use_case_id = %s
            ORDER BY created_at DESC
            LIMIT 1
        """, (use_case_id,))
        
        row = cursor.fetchone()
        cursor.close()
        
        if not row:
            # Generate default estimate if none exists
            default_assumptions = {
                'override_frequency': 10,
                'avg_time_per_override': 2,
                'hourly_rate': 50,
                'error_rate': 5,
                'error_cost': 1000,
                'delayed_transactions': 20,
                'opportunity_cost': 100,
                'ocx_monthly_cost': 5000
            }
            impact = impact_estimator.calculate_impact(use_case_id, default_assumptions)
            return ImpactEstimate(**impact)
        
        return ImpactEstimate(
            estimate_id=str(row[0]),
            use_case_id=str(row[1]),
            current_monthly_cost=float(row[2]),
            a2a_monthly_savings=float(row[3]),
            net_monthly_savings=float(row[4]),
            annual_roi=float(row[5]),
            payback_period_months=float(row[6]),
            assumptions=row[7]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch impact estimate: {str(e)}")

@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint"""
    return {"status": "healthy", "service": "authority-discovery"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
