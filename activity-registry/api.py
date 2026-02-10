"""
Activity Registry Service
Governance layer for EBCL activities with versioning, approval workflows, and deployment controls
"""

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum
import os
import hashlib
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
import json
import logging
logger = logging.getLogger(__name__)

app = FastAPI(title="Activity Registry API", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connection
def get_db() -> None:
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

# Enums
class ActivityStatus(str, Enum):
    DRAFT = "DRAFT"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    DEPLOYED = "DEPLOYED"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    RETIRED = "RETIRED"

class Environment(str, Enum):
    DEV = "DEV"
    STAGING = "STAGING"
    PROD = "PROD"

class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class ApprovalType(str, Enum):
    TECHNICAL = "TECHNICAL"
    BUSINESS = "BUSINESS"
    COMPLIANCE = "COMPLIANCE"
    SECURITY = "SECURITY"

class VersionType(str, Enum):
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    PATCH = "PATCH"

# Models
class ActivityCreate(BaseModel):
    name: str = Field(..., description="Activity name (e.g., 'PO_Approval')")
    version: str = Field(..., description="Semantic version (e.g., '1.0.0')")
    ebcl_source: str = Field(..., description="EBCL source code")
    owner: str = Field(..., description="Owner (e.g., 'Finance Department')")
    authority: str = Field(..., description="Policy reference (e.g., 'Procurement Policy v3.2')")
    created_by: str = Field(..., description="Creator email/ID")
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    category: Optional[str] = None
    compiled_artifact: Optional[Dict[str, Any]] = None

class ActivityResponse(BaseModel):
    activity_id: str
    name: str
    version: str
    status: ActivityStatus
    ebcl_source: str
    owner: str
    authority: str
    created_by: str
    created_at: datetime
    approved_by: Optional[str]
    approved_at: Optional[datetime]
    deployed_by: Optional[str]
    deployed_at: Optional[datetime]
    hash: str
    description: Optional[str]
    tags: Optional[List[str]]
    category: Optional[str]
    tenant_id: str

class ActivityUpdate(BaseModel):
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    category: Optional[str] = None

class ApprovalRequest(BaseModel):
    approver_id: str
    approver_role: str
    approval_type: ApprovalType
    comments: Optional[str] = None

class ApprovalResponse(BaseModel):
    approval_status: ApprovalStatus
    comments: Optional[str] = None

class DeploymentRequest(BaseModel):
    environment: Environment
    tenant_id: str
    deployed_by: str
    deployment_notes: Optional[str] = None
    effective_from: Optional[datetime] = None

class DeploymentResponse(BaseModel):
    deployment_id: str
    activity_id: str
    environment: Environment
    tenant_id: str
    effective_from: datetime
    effective_until: Optional[datetime]
    deployed_by: str
    deployed_at: datetime

class RollbackRequest(BaseModel):
    rollback_reason: str
    rolled_back_by: str

# Helper functions
def calculate_hash(ebcl_source: str) -> str:
    """Calculate SHA-256 hash of EBCL source"""
    return hashlib.sha256(ebcl_source.encode()).hexdigest()

def parse_version(version: str) -> tuple:
    """Parse semantic version into (major, minor, patch)"""
    parts = version.split('.')
    if len(parts) != 3:
        raise ValueError("Version must be in format MAJOR.MINOR.PATCH")
    return tuple(map(int, parts))

def increment_version(current_version: str, version_type: VersionType) -> str:
    """Increment version based on type"""
    major, minor, patch = parse_version(current_version)
    
    if version_type == VersionType.MAJOR:
        return f"{major + 1}.0.0"
    elif version_type == VersionType.MINOR:
        return f"{major}.{minor + 1}.0"
    else:  # PATCH
        return f"{major}.{minor}.{patch + 1}"

# ============================================================================
# ACTIVITY CRUD ENDPOINTS
# ============================================================================

@app.post("/api/v1/activities", response_model=ActivityResponse)
async def create_activity(activity: ActivityCreate, request: Request, conn = Depends(get_db)) -> None:
    """
    Create a new activity in DRAFT status
    
    - Validates semantic versioning
    - Calculates hash of EBCL source
    - Sets status to DRAFT
    """
    tenant_id = request.headers.get("X-Tenant-ID")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Missing X-Tenant-ID header")

    try:
        # Validate version format
        parse_version(activity.version)
        
        # Calculate hash
        activity_hash = calculate_hash(activity.ebcl_source)
        
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Insert activity
        cursor.execute("""
            INSERT INTO activities (
                name, version, status, ebcl_source, compiled_artifact,
                owner, authority, created_by, hash, description, tags, category, tenant_id
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            RETURNING *
        """, (
            activity.name,
            activity.version,
            ActivityStatus.DRAFT,
            activity.ebcl_source,
            json.dumps(activity.compiled_artifact) if activity.compiled_artifact else None,
            activity.owner,
            activity.authority,
            activity.created_by,
            activity_hash,
            activity.description,
            activity.tags,
            activity.category,
            tenant_id
        ))
        
        result = cursor.fetchone()
        conn.commit()
        
        return ActivityResponse(**result)
    
    except psycopg2.IntegrityError as e:
        conn.rollback()
        if 'unique constraint' in str(e).lower():
            raise HTTPException(status_code=400, detail=f"Activity {activity.name} version {activity.version} already exists")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/activities/{activity_id}", response_model=ActivityResponse)
async def get_activity(activity_id: str, conn = Depends(get_db)) -> Any:
    """Get activity by ID"""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("SELECT * FROM activities WHERE activity_id = %s", (activity_id,))
    result = cursor.fetchone()
    
    if not result:
        raise HTTPException(status_code=404, detail="Activity not found")
    
    return ActivityResponse(**result)

@app.get("/api/v1/activities", response_model=List[ActivityResponse])
async def list_activities(
    request: Request,
    status: Optional[ActivityStatus] = None,
    owner: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    conn = Depends(get_db)
) -> list:
    """List activities with optional filters"""
    tenant_id = request.headers.get("X-Tenant-ID")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Missing X-Tenant-ID header")

    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    query = "SELECT * FROM activities WHERE tenant_id = %s"
    params = [tenant_id]
    
    if status:
        query += " AND status = %s"
        params.append(status)
    
    if owner:
        query += " AND owner = %s"
        params.append(owner)
    
    if category:
        query += " AND category = %s"
        params.append(category)
    
    query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    results = cursor.fetchall()
    
    return [ActivityResponse(**r) for r in results]

@app.get("/api/v1/activities/latest/{name}", response_model=ActivityResponse)
async def get_latest_activity(name: str, conn = Depends(get_db)) -> Any:
    """Get latest version of an activity by name"""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("SELECT * FROM get_latest_version(%s)", (name,))
    result = cursor.fetchone()
    
    if not result:
        raise HTTPException(status_code=404, detail=f"Activity {name} not found")
    
    # Get full activity details
    cursor.execute("SELECT * FROM activities WHERE activity_id = %s", (result['activity_id'],))
    activity = cursor.fetchone()
    
    return ActivityResponse(**activity)

@app.patch("/api/v1/activities/{activity_id}", response_model=ActivityResponse)
async def update_activity(activity_id: str, update: ActivityUpdate, conn = Depends(get_db)) -> Any:
    """
    Update activity metadata (description, tags, category)
    
    Note: EBCL source cannot be modified for deployed activities.
    Create a new version instead.
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Build update query
    updates = []
    params = []
    
    if update.description is not None:
        updates.append("description = %s")
        params.append(update.description)
    
    if update.tags is not None:
        updates.append("tags = %s")
        params.append(update.tags)
    
    if update.category is not None:
        updates.append("category = %s")
        params.append(update.category)
    
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    params.append(activity_id)
    query = f"UPDATE activities SET {', '.join(updates)} WHERE activity_id = %s RETURNING *"
    
    cursor.execute(query, params)
    result = cursor.fetchone()
    conn.commit()
    
    if not result:
        raise HTTPException(status_code=404, detail="Activity not found")
    
    return ActivityResponse(**result)

# ============================================================================
# APPROVAL WORKFLOW ENDPOINTS
# ============================================================================

@app.post("/api/v1/activities/{activity_id}/request-approval")
async def request_approval(activity_id: str, request: ApprovalRequest, conn = Depends(get_db)) -> dict:
    """Request approval for an activity"""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Check activity exists and is in DRAFT or REVIEW status
    cursor.execute("SELECT status FROM activities WHERE activity_id = %s", (activity_id,))
    result = cursor.fetchone()
    
    if not result:
        raise HTTPException(status_code=404, detail="Activity not found")
    
    if result['status'] not in [ActivityStatus.DRAFT, ActivityStatus.REVIEW]:
        raise HTTPException(status_code=400, detail=f"Cannot request approval for activity in {result['status']} status")
    
    # Update activity status to REVIEW
    cursor.execute(
        "UPDATE activities SET status = %s WHERE activity_id = %s",
        (ActivityStatus.REVIEW, activity_id)
    )
    
    # Create approval request
    cursor.execute("""
        INSERT INTO activity_approvals (
            activity_id, approver_id, approver_role, approval_status, approval_type, comments
        ) VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING *
    """, (
        activity_id,
        request.approver_id,
        request.approver_role,
        ApprovalStatus.PENDING,
        request.approval_type,
        request.comments
    ))
    
    approval = cursor.fetchone()
    conn.commit()
    
    return {"approval_id": str(approval['approval_id']), "status": "PENDING"}

@app.post("/api/v1/activities/{activity_id}/approve")
async def approve_activity(
    activity_id: str,
    approval_id: str,
    response: ApprovalResponse,
    conn = Depends(get_db)
) -> dict:
    """
    Approve or reject an activity
    
    If all required approvals are granted, activity moves to APPROVED status
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Update approval
    cursor.execute("""
        UPDATE activity_approvals
        SET approval_status = %s, responded_at = NOW(), comments = %s
        WHERE approval_id = %s AND activity_id = %s
        RETURNING *
    """, (response.approval_status, response.comments, approval_id, activity_id))
    
    approval = cursor.fetchone()
    
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    
    # Check if all approvals are complete
    cursor.execute("""
        SELECT COUNT(*) as pending
        FROM activity_approvals
        WHERE activity_id = %s AND approval_status = 'PENDING'
    """, (activity_id,))
    
    pending = cursor.fetchone()['pending']
    
    # If approved and no pending approvals, move to APPROVED
    if response.approval_status == ApprovalStatus.APPROVED and pending == 0:
        cursor.execute("""
            UPDATE activities
            SET status = %s, approved_by = %s, approved_at = NOW()
            WHERE activity_id = %s
        """, (ActivityStatus.APPROVED, approval['approver_id'], activity_id))
    
    # If rejected, move back to DRAFT
    elif response.approval_status == ApprovalStatus.REJECTED:
        cursor.execute("""
            UPDATE activities
            SET status = %s
            WHERE activity_id = %s
        """, (ActivityStatus.DRAFT, activity_id))
    
    conn.commit()
    
    return {"status": "success", "approval_status": response.approval_status}

# Continued in next file...
# ============================================================================
# DEPLOYMENT ENDPOINTS
# ============================================================================

@app.post("/api/v1/activities/{activity_id}/deploy", response_model=DeploymentResponse)
async def deploy_activity(
    activity_id: str,
    deployment: DeploymentRequest,
    conn = Depends(get_db)
) -> None:
    """
    Deploy an activity to an environment
    
    Requirements:
    - Activity must be in APPROVED status
    - All approvals must be granted
    - No conflicting deployments in the same environment/tenant
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Check if activity can be deployed
    cursor.execute("SELECT can_deploy_activity(%s) as can_deploy", (activity_id,))
    result = cursor.fetchone()
    
    if not result['can_deploy']:
        raise HTTPException(
            status_code=400,
            detail="Activity cannot be deployed. Check status and approvals."
        )
    
    # Check for existing active deployment
    cursor.execute("""
        SELECT deployment_id
        FROM activity_deployments
        WHERE activity_id = %s
          AND environment = %s
          AND tenant_id = %s
          AND effective_from <= NOW()
          AND (effective_until IS NULL OR effective_until > NOW())
    """, (activity_id, deployment.environment, deployment.tenant_id))
    
    existing = cursor.fetchone()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Activity already deployed to {deployment.environment}/{deployment.tenant_id}"
        )
    
    # Create deployment
    effective_from = deployment.effective_from or datetime.now()
    
    cursor.execute("""
        INSERT INTO activity_deployments (
            activity_id, environment, tenant_id, deployed_by,
            effective_from, deployment_notes
        ) VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING *
    """, (
        activity_id,
        deployment.environment,
        deployment.tenant_id,
        deployment.deployed_by,
        effective_from,
        deployment.deployment_notes
    ))
    
    deployment_result = cursor.fetchone()
    
    # Update activity status to DEPLOYED (first deployment) or ACTIVE (subsequent)
    cursor.execute("""
        SELECT COUNT(*) as deployment_count
        FROM activity_deployments
        WHERE activity_id = %s
    """, (activity_id,))
    
    count = cursor.fetchone()['deployment_count']
    new_status = ActivityStatus.ACTIVE if count > 1 else ActivityStatus.DEPLOYED
    
    cursor.execute("""
        UPDATE activities
        SET status = %s, deployed_by = %s, deployed_at = NOW()
        WHERE activity_id = %s
    """, (new_status, deployment.deployed_by, activity_id))
    
    conn.commit()
    
    return DeploymentResponse(**deployment_result)

@app.get("/api/v1/activities/{activity_id}/deployments", response_model=List[DeploymentResponse])
async def list_deployments(activity_id: str, conn = Depends(get_db)) -> list:
    """List all deployments for an activity"""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("""
        SELECT * FROM activity_deployments
        WHERE activity_id = %s
        ORDER BY deployed_at DESC
    """, (activity_id,))
    
    results = cursor.fetchall()
    return [DeploymentResponse(**r) for r in results]

@app.post("/api/v1/activities/{activity_id}/rollback")
async def rollback_deployment(
    activity_id: str,
    deployment_id: str,
    rollback: RollbackRequest,
    conn = Depends(get_db)
) -> dict:
    """
    Rollback a deployment
    
    - Marks current deployment as ended
    - Optionally activates previous deployment
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get current deployment
    cursor.execute("""
        SELECT * FROM activity_deployments
        WHERE deployment_id = %s AND activity_id = %s
    """, (deployment_id, activity_id))
    
    current = cursor.fetchone()
    if not current:
        raise HTTPException(status_code=404, detail="Deployment not found")
    
    # End current deployment
    cursor.execute("""
        UPDATE activity_deployments
        SET effective_until = NOW(), rollback_reason = %s
        WHERE deployment_id = %s
    """, (rollback.rollback_reason, deployment_id))
    
    # Get previous deployment
    cursor.execute("""
        SELECT * FROM activity_deployments
        WHERE activity_id = %s
          AND environment = %s
          AND tenant_id = %s
          AND deployed_at < %s
        ORDER BY deployed_at DESC
        LIMIT 1
    """, (activity_id, current['environment'], current['tenant_id'], current['deployed_at']))
    
    previous = cursor.fetchone()
    
    if previous:
        # Reactivate previous deployment
        cursor.execute("""
            UPDATE activity_deployments
            SET effective_until = NULL
            WHERE deployment_id = %s
        """, (previous['deployment_id'],))
    
    conn.commit()
    
    return {
        "status": "success",
        "rolled_back_to": str(previous['deployment_id']) if previous else None
    }

@app.post("/api/v1/activities/{activity_id}/suspend")
async def suspend_activity(
    activity_id: str,
    reason: str,
    suspended_by: str,
    conn = Depends(get_db)
) -> dict:
    """
    Suspend an activity (emergency stop)
    
    - Immediately ends all active deployments
    - Sets activity status to SUSPENDED
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # End all active deployments
    cursor.execute("""
        UPDATE activity_deployments
        SET effective_until = NOW(), rollback_reason = %s
        WHERE activity_id = %s
          AND effective_from <= NOW()
          AND (effective_until IS NULL OR effective_until > NOW())
    """, (f"SUSPENDED: {reason}", activity_id))
    
    # Update activity status
    cursor.execute("""
        UPDATE activities
        SET status = %s
        WHERE activity_id = %s
    """, (ActivityStatus.SUSPENDED, activity_id))
    
    conn.commit()
    
    return {"status": "suspended", "reason": reason}

# ============================================================================
# VERSION MANAGEMENT ENDPOINTS
# ============================================================================

@app.post("/api/v1/activities/{activity_id}/new-version")
async def create_new_version(
    activity_id: str,
    version_type: VersionType,
    change_summary: str,
    breaking_changes: Optional[List[str]] = None,
    created_by: str = "system",
    conn = Depends(get_db)
) -> dict:
    """
    Create a new version of an activity
    
    - Increments version based on type (MAJOR/MINOR/PATCH)
    - Copies EBCL source from current version
    - Creates new activity in DRAFT status
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get current activity
    cursor.execute("SELECT * FROM activities WHERE activity_id = %s", (activity_id,))
    current = cursor.fetchone()
    
    if not current:
        raise HTTPException(status_code=404, detail="Activity not found")
    
    # Calculate new version
    new_version = increment_version(current['version'], version_type)
    
    # Create new activity
    cursor.execute("""
        INSERT INTO activities (
            name, version, status, ebcl_source, owner, authority,
            created_by, description, tags, category
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING activity_id
    """, (
        current['name'],
        new_version,
        ActivityStatus.DRAFT,
        current['ebcl_source'],
        current['owner'],
        current['authority'],
        created_by,
        current['description'],
        current['tags'],
        current['category']
    ))
    
    new_activity = cursor.fetchone()
    
    # Record version history
    cursor.execute("""
        INSERT INTO activity_versions (
            activity_id, version, previous_version, version_type,
            change_summary, breaking_changes, created_by
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        new_activity['activity_id'],
        new_version,
        current['version'],
        version_type,
        change_summary,
        breaking_changes,
        created_by
    ))
    
    conn.commit()
    
    return {
        "new_activity_id": str(new_activity['activity_id']),
        "new_version": new_version,
        "previous_version": current['version']
    }

@app.get("/api/v1/activities/{activity_id}/versions")
async def get_version_history(activity_id: str, conn = Depends(get_db)) -> Any:
    """Get version history for an activity"""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get activity name
    cursor.execute("SELECT name FROM activities WHERE activity_id = %s", (activity_id,))
    activity = cursor.fetchone()
    
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    
    # Get all versions
    cursor.execute("""
        SELECT a.*, v.change_summary, v.breaking_changes, v.version_type
        FROM activities a
        LEFT JOIN activity_versions v ON a.activity_id = v.activity_id
        WHERE a.name = %s
        ORDER BY a.created_at DESC
    """, (activity['name'],))
    
    versions = cursor.fetchall()
    return versions

# ============================================================================
# ANALYTICS ENDPOINTS
# ============================================================================

@app.get("/api/v1/activities/{activity_id}/executions")
async def get_activity_executions(
    activity_id: str,
    limit: int = 100,
    offset: int = 0,
    conn = Depends(get_db)
) -> Any:
    """Get execution history for an activity"""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("""
        SELECT * FROM activity_executions
        WHERE activity_id = %s
        ORDER BY started_at DESC
        LIMIT %s OFFSET %s
    """, (activity_id, limit, offset))
    
    return cursor.fetchall()

@app.get("/api/v1/activities/{activity_id}/stats")
async def get_activity_stats(activity_id: str, conn = Depends(get_db)) -> dict:
    """Get execution statistics for an activity"""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("""
        SELECT * FROM activity_execution_stats
        WHERE activity_id = %s
    """, (activity_id,))
    
    stats = cursor.fetchone()
    
    if not stats:
        return {
            "activity_id": activity_id,
            "total_executions": 0,
            "successful_executions": 0,
            "failed_executions": 0,
            "avg_duration_ms": 0,
            "last_execution_at": None
        }
    
    return stats

@app.get("/api/v1/approvals/pending")
async def get_pending_approvals(conn = Depends(get_db)) -> Any:
    """Get all pending approvals"""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("SELECT * FROM pending_approvals")
    return cursor.fetchall()

# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/health")
async def health() -> dict:
    """Health check"""
    return {"status": "healthy", "service": "activity-registry"}

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002)
