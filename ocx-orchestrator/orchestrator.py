"""
OCX Orchestrator - Multi-Tenant Integration Layer
Coordinates all OCX components with tenant-specific feature flags
"""

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import requests
import asyncio
from enum import Enum

app = FastAPI(title="OCX Orchestrator", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Service URLs
PROCESS_MINING_URL = os.getenv('PROCESS_MINING_URL', 'http://localhost:8001')
ACTIVITY_REGISTRY_URL = os.getenv('ACTIVITY_REGISTRY_URL', 'http://localhost:8002')
EVIDENCE_VAULT_URL = os.getenv('EVIDENCE_VAULT_URL', 'http://localhost:8003')

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

# ============================================================================
# TENANT MANAGEMENT
# ============================================================================

class SubscriptionTier(str, Enum):
    FREE = "FREE"
    STARTER = "STARTER"
    PROFESSIONAL = "PROFESSIONAL"
    ENTERPRISE = "ENTERPRISE"

class TenantStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    TRIAL = "TRIAL"
    CANCELLED = "CANCELLED"

class TenantCreate(BaseModel):
    tenant_id: str
    tenant_name: str
    organization_name: str
    subscription_tier: SubscriptionTier
    admin_email: str
    admin_name: Optional[str] = None

class TenantResponse(BaseModel):
    tenant_id: str
    tenant_name: str
    organization_name: str
    subscription_tier: SubscriptionTier
    status: TenantStatus
    created_at: datetime
    max_agents: int
    max_activities: int
    max_evidence_per_month: int

# Dependency to get tenant from header
async def get_tenant_id(x_tenant_id: str = Header(...)) -> str:
    """Extract tenant ID from header"""
    return x_tenant_id

async def verify_tenant(tenant_id: str = Depends(get_tenant_id), conn = Depends(get_db)) -> Dict:
    """Verify tenant exists and is active"""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT * FROM tenants WHERE tenant_id = %s AND status = 'ACTIVE'
    """, (tenant_id,))
    
    tenant = cursor.fetchone()
    if not tenant:
        raise HTTPException(status_code=403, detail="Tenant not found or inactive")
    
    return tenant

async def check_feature(
    feature_name: str,
    tenant_id: str = Depends(get_tenant_id),
    conn = Depends(get_db)
) -> bool:
    """Check if feature is enabled for tenant"""
    cursor = conn.cursor()
    cursor.execute("SELECT is_feature_enabled(%s, %s)", (tenant_id, feature_name))
    result = cursor.fetchone()
    
    if not result or not result[0]:
        raise HTTPException(
            status_code=403,
            detail=f"Feature '{feature_name}' not enabled for tenant"
        )
    
    return True

# ============================================================================
# TENANT CRUD
# ============================================================================

@app.post("/api/v1/tenants", response_model=TenantResponse)
async def create_tenant(tenant: TenantCreate, conn = Depends(get_db)):
    """Create new tenant"""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Set limits based on tier
    limits = {
        "FREE": (5, 50, 10000),
        "STARTER": (10, 100, 50000),
        "PROFESSIONAL": (50, 500, 500000),
        "ENTERPRISE": (1000, 10000, 10000000)
    }
    
    max_agents, max_activities, max_evidence = limits[tenant.subscription_tier]
    
    cursor.execute("""
        INSERT INTO tenants (
            tenant_id, tenant_name, organization_name, subscription_tier,
            admin_email, admin_name, max_agents, max_activities, max_evidence_per_month
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
    """, (
        tenant.tenant_id,
        tenant.tenant_name,
        tenant.organization_name,
        tenant.subscription_tier,
        tenant.admin_email,
        tenant.admin_name,
        max_agents,
        max_activities,
        max_evidence
    ))
    
    result = cursor.fetchone()
    conn.commit()
    
    # Enable default features based on tier
    cursor.execute("""
        INSERT INTO tenant_features (tenant_id, feature_name, enabled, enabled_at)
        SELECT %s, feature_name, TRUE, NOW()
        FROM features
        WHERE (subscription_tier = 'FREE' AND available_in_free = TRUE)
           OR (subscription_tier = 'STARTER' AND available_in_starter = TRUE)
           OR (subscription_tier = 'PROFESSIONAL' AND available_in_professional = TRUE)
           OR (subscription_tier = 'ENTERPRISE' AND available_in_enterprise = TRUE)
    """, (tenant.tenant_id,))
    conn.commit()
    
    return TenantResponse(**result)

@app.get("/api/v1/tenants/{tenant_id}", response_model=TenantResponse)
async def get_tenant(tenant_id: str, conn = Depends(get_db)):
    """Get tenant by ID"""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM tenants WHERE tenant_id = %s", (tenant_id,))
    
    result = cursor.fetchone()
    if not result:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    return TenantResponse(**result)

@app.get("/api/v1/tenants/{tenant_id}/features")
async def get_tenant_features(tenant_id: str, conn = Depends(get_db)):
    """Get enabled features for tenant"""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("""
        SELECT 
            f.feature_name,
            f.display_name,
            f.description,
            f.category,
            tf.enabled,
            tf.config
        FROM features f
        LEFT JOIN tenant_features tf ON f.feature_name = tf.feature_name AND tf.tenant_id = %s
        ORDER BY f.category, f.display_name
    """, (tenant_id,))
    
    return cursor.fetchall()

@app.post("/api/v1/tenants/{tenant_id}/features/{feature_name}/enable")
async def enable_feature(
    tenant_id: str,
    feature_name: str,
    conn = Depends(get_db)
):
    """Enable feature for tenant"""
    cursor = conn.cursor()
    
    # Check if feature exists
    cursor.execute("SELECT 1 FROM features WHERE feature_name = %s", (feature_name,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Feature not found")
    
    # Enable feature
    cursor.execute("SELECT enable_feature(%s, %s, %s)", (tenant_id, feature_name, "admin"))
    conn.commit()
    
    return {"status": "enabled", "feature": feature_name}

# ============================================================================
# UNIFIED ACTIVITY EXECUTION
# Orchestrates all components based on tenant features
# ============================================================================

class ActivityExecutionRequest(BaseModel):
    activity_id: str
    input_data: Dict[str, Any]
    agent_id: str

@app.post("/api/v1/execute")
async def execute_activity(
    request: ActivityExecutionRequest,
    tenant: Dict = Depends(verify_tenant),
    conn = Depends(get_db)
):
    """
    Unified activity execution endpoint
    Orchestrates all OCX components based on tenant features
    """
    tenant_id = tenant['tenant_id']
    execution_id = f"exec-{datetime.utcnow().timestamp()}"
    
    # 1. Check if activity execution is enabled
    await check_feature("activity_execution", tenant_id, conn)
    
    # 2. Get activity from registry
    try:
        activity_response = requests.get(
            f"{ACTIVITY_REGISTRY_URL}/api/v1/activities/{request.activity_id}"
        )
        activity_response.raise_for_status()
        activity = activity_response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch activity: {str(e)}")
    
    # 3. Socket Interception (if enabled)
    cursor = conn.cursor()
    cursor.execute("SELECT is_feature_enabled(%s, %s)", (tenant_id, "socket_interception"))
    if cursor.fetchone()[0]:
        # Apply socket interception rules
        # (In production, this would be handled by the socket interceptor service)
        pass
    
    # 4. Execute activity (simplified - in production use EBCL executor)
    execution_result = {
        "execution_id": execution_id,
        "activity_id": request.activity_id,
        "status": "SUCCESS",
        "outcome": "AutoApprove",  # Simplified
        "timestamp": datetime.utcnow().isoformat()
    }
    
    # 5. Submit evidence (if enabled)
    cursor.execute("SELECT is_feature_enabled(%s, %s)", (tenant_id, "evidence_collection"))
    if cursor.fetchone()[0]:
        try:
            evidence_response = requests.post(
                f"{EVIDENCE_VAULT_URL}/api/v1/evidence",
                json={
                    "activity_id": request.activity_id,
                    "activity_name": activity['name'],
                    "activity_version": activity['version'],
                    "execution_id": execution_id,
                    "agent_id": request.agent_id,
                    "agent_type": "SYSTEM",
                    "tenant_id": tenant_id,
                    "environment": "PROD",
                    "event_type": "ACT",
                    "event_data": request.input_data,
                    "decision": "Executed successfully",
                    "outcome": execution_result['outcome'],
                    "policy_reference": activity['authority']
                }
            )
            evidence_response.raise_for_status()
            execution_result['evidence_id'] = evidence_response.json()['evidence_id']
        except Exception as e:
            print(f"Failed to submit evidence: {e}")
    
    # 6. Trigger parallel auditing (if enabled)
    cursor.execute("SELECT is_feature_enabled(%s, %s)", (tenant_id, "continuous_auditing"))
    if cursor.fetchone()[0] and 'evidence_id' in execution_result:
        # Trigger async auditing
        asyncio.create_task(trigger_parallel_audit(execution_result['evidence_id']))
    
    # 7. Update usage metrics
    update_tenant_usage(tenant_id, conn)
    
    return execution_result

async def trigger_parallel_audit(evidence_id: str):
    """Trigger parallel auditing (async)"""
    # In production, this would call the parallel auditing service
    pass

def update_tenant_usage(tenant_id: str, conn):
    """Update tenant usage metrics"""
    cursor = conn.cursor()
    
    # Get current period
    period_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    period_end = (period_start.replace(month=period_start.month + 1) if period_start.month < 12 
                  else period_start.replace(year=period_start.year + 1, month=1))
    
    cursor.execute("""
        INSERT INTO tenant_usage (tenant_id, period_start, period_end, activities_executed)
        VALUES (%s, %s, %s, 1)
        ON CONFLICT (tenant_id, period_start)
        DO UPDATE SET activities_executed = tenant_usage.activities_executed + 1
    """, (tenant_id, period_start, period_end))
    
    conn.commit()

# Continued in next file...
# ============================================================================
# UNIFIED API GATEWAY ENDPOINTS
# Proxy to underlying services with tenant context
# ============================================================================

@app.post("/api/v1/process-mining/parse")
async def parse_document(
    file_data: Dict[str, Any],
    tenant: Dict = Depends(verify_tenant),
    conn = Depends(get_db)
):
    """Parse document (requires process_mining feature)"""
    await check_feature("process_mining", tenant['tenant_id'], conn)
    
    response = requests.post(
        f"{PROCESS_MINING_URL}/api/v1/parse",
        json=file_data,
        headers={"X-Tenant-ID": tenant['tenant_id']}
    )
    response.raise_for_status()
    
    # Update usage
    update_document_usage(tenant['tenant_id'], conn)
    
    return response.json()

@app.post("/api/v1/activities")
async def create_activity(
    activity_data: Dict[str, Any],
    tenant: Dict = Depends(verify_tenant),
    conn = Depends(get_db)
):
    """Create activity (requires activity_versioning feature)"""
    await check_feature("activity_versioning", tenant['tenant_id'], conn)
    
    # Add tenant context
    activity_data['tenant_id'] = tenant['tenant_id']
    
    response = requests.post(
        f"{ACTIVITY_REGISTRY_URL}/api/v1/activities",
        json=activity_data
    )
    response.raise_for_status()
    
    return response.json()

@app.get("/api/v1/evidence")
async def list_evidence(
    tenant: Dict = Depends(verify_tenant),
    conn = Depends(get_db)
):
    """List evidence for tenant"""
    await check_feature("evidence_collection", tenant['tenant_id'], conn)
    
    response = requests.get(
        f"{EVIDENCE_VAULT_URL}/api/v1/evidence",
        params={"tenant_id": tenant['tenant_id']}
    )
    response.raise_for_status()
    
    return response.json()

def update_document_usage(tenant_id: str, conn):
    """Update document processing usage"""
    cursor = conn.cursor()
    
    period_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    period_end = (period_start.replace(month=period_start.month + 1) if period_start.month < 12 
                  else period_start.replace(year=period_start.year + 1, month=1))
    
    cursor.execute("""
        INSERT INTO tenant_usage (tenant_id, period_start, period_end, documents_processed)
        VALUES (%s, %s, %s, 1)
        ON CONFLICT (tenant_id, period_start)
        DO UPDATE SET documents_processed = tenant_usage.documents_processed + 1
    """, (tenant_id, period_start, period_end))
    
    conn.commit()

# ============================================================================
# USAGE & ANALYTICS
# ============================================================================

@app.get("/api/v1/tenants/{tenant_id}/usage")
async def get_tenant_usage(tenant_id: str, conn = Depends(get_db)):
    """Get tenant usage statistics"""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("""
        SELECT * FROM tenant_usage_summary WHERE tenant_id = %s
    """, (tenant_id,))
    
    return cursor.fetchone()

@app.get("/api/v1/tenants/{tenant_id}/limits")
async def check_tenant_limits(tenant_id: str, conn = Depends(get_db)):
    """Check tenant limits"""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get tenant limits
    cursor.execute("""
        SELECT max_agents, max_activities, max_evidence_per_month
        FROM tenants WHERE tenant_id = %s
    """, (tenant_id,))
    
    limits = cursor.fetchone()
    
    # Get current usage
    cursor.execute("""
        SELECT 
            COUNT(DISTINCT agent_id) as current_agents,
            COUNT(DISTINCT activity_id) as current_activities
        FROM tenant_agents ta
        JOIN activities a ON a.tenant_id = ta.tenant_id
        WHERE ta.tenant_id = %s
    """, (tenant_id,))
    
    usage = cursor.fetchone()
    
    # Get current month evidence count
    period_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    cursor.execute("""
        SELECT COALESCE(SUM(evidence_collected), 0) as current_evidence
        FROM tenant_usage
        WHERE tenant_id = %s AND period_start = %s
    """, (tenant_id, period_start))
    
    evidence_usage = cursor.fetchone()
    
    return {
        "limits": limits,
        "usage": {
            "agents": usage['current_agents'],
            "activities": usage['current_activities'],
            "evidence": evidence_usage['current_evidence']
        },
        "available": {
            "agents": limits['max_agents'] - usage['current_agents'],
            "activities": limits['max_activities'] - usage['current_activities'],
            "evidence": limits['max_evidence_per_month'] - evidence_usage['current_evidence']
        }
    }

# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/health")
async def health(conn = Depends(get_db)):
    """Health check for orchestrator and all services"""
    health_status = {
        "orchestrator": "healthy",
        "database": "unknown",
        "services": {}
    }
    
    # Check database
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        health_status["database"] = "healthy"
    except:
        health_status["database"] = "unhealthy"
    
    # Check services
    services = {
        "process_mining": PROCESS_MINING_URL,
        "activity_registry": ACTIVITY_REGISTRY_URL,
        "evidence_vault": EVIDENCE_VAULT_URL
    }
    
    for service_name, service_url in services.items():
        try:
            response = requests.get(f"{service_url}/health", timeout=2)
            health_status["services"][service_name] = "healthy" if response.ok else "unhealthy"
        except:
            health_status["services"][service_name] = "unreachable"
    
    # Overall status
    all_healthy = (
        health_status["database"] == "healthy" and
        all(s == "healthy" for s in health_status["services"].values())
    )
    
    health_status["status"] = "healthy" if all_healthy else "degraded"
    
    return health_status

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
