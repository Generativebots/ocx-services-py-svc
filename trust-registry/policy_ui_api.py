"""
Policy Management UI API
FastAPI endpoints for policy management interface

All endpoints are tenant-scoped and backed by PostgreSQL.
Policies persist across restarts via the `policies` table.
"""

import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Maximum number of versions per policy
MAX_POLICY_VERSIONS = 18


# --- Database ---

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


# --- Models ---

class PolicyCreateRequest(BaseModel):
    policy_id: str
    tier: str
    trigger_intent: str
    logic: Dict[str, Any]
    action: Dict[str, Any]
    confidence: float
    source_name: str
    roles: Optional[List[str]] = None
    expires_at: Optional[str] = None


class PolicyUpdateRequest(BaseModel):
    logic: Optional[Dict[str, Any]] = None
    action: Optional[Dict[str, Any]] = None
    tier: Optional[str] = None
    confidence: Optional[float] = None


class PolicyResponse(BaseModel):
    policy_id: str
    version: int
    tier: str
    trigger_intent: str
    logic: Dict[str, Any]
    action: Dict[str, Any]
    confidence: float
    source_name: str
    is_active: bool
    created_at: str
    created_by: str


# --- Endpoints (all tenant-scoped, PostgreSQL-backed) ---

@router.get("/policies")
def list_policies(
    x_tenant_id: str = Header(...),
    x_department: Optional[str] = Header(None),
    tier: Optional[str] = None,
    department: Optional[str] = None,
    conn=Depends(get_db),
) -> dict:
    """List all active policies for tenant from DB.
    If department is provided (via query param or X-Department header),
    returns GLOBAL policies (department IS NULL) + department-specific ones.
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    dept = department or x_department  # query param takes precedence

    conditions = ["tenant_id = %s", "is_active = TRUE", "(expires_at IS NULL OR expires_at > NOW())"]
    params: list = [x_tenant_id]

    if tier:
        conditions.append("tier = %s")
        params.append(tier)

    if dept:
        conditions.append("(department = %s OR department IS NULL)")
        params.append(dept)

    sql = f"SELECT * FROM policies WHERE {' AND '.join(conditions)} ORDER BY created_at DESC"
    cursor.execute(sql, params)

    rows = cursor.fetchall()
    policies = []
    for row in rows:
        policies.append({
            "policy_id": str(row["policy_id"]),
            "version": row["version"],
            "tier": row["tier"],
            "trigger_intent": row["trigger_intent"],
            "logic": row["logic"] if isinstance(row["logic"], dict) else json.loads(row["logic"]),
            "action": row["action"] if isinstance(row["action"], dict) else json.loads(row["action"]),
            "confidence": row["confidence"],
            "source_name": row["source_name"],
            "roles": row.get("roles", []),
            "is_active": row["is_active"],
            "department": row.get("department"),
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        })

    return {"tenant_id": x_tenant_id, "department": dept, "policies": policies, "count": len(policies)}


@router.post("/policies", response_model=PolicyResponse)
def create_policy(
    req: PolicyCreateRequest,
    x_tenant_id: str = Header(...),
    x_user_id: str = Header("system"),
    x_department: Optional[str] = Header(None),
    conn=Depends(get_db),
) -> Any:
    """Create new policy in DB."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cursor.execute("""
            INSERT INTO policies (
                policy_id, tenant_id, version, tier, trigger_intent,
                logic, action, confidence, source_name, roles, expires_at,
                department, is_active, created_at, updated_at
            ) VALUES (
                %s, %s, 1, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, TRUE, NOW(), NOW()
            )
            RETURNING *
        """, (
            req.policy_id,
            x_tenant_id,
            req.tier,
            req.trigger_intent,
            json.dumps(req.logic),
            json.dumps(req.action),
            req.confidence,
            req.source_name,
            req.roles or [],
            datetime.fromisoformat(req.expires_at) if req.expires_at else None,
            x_department,
        ))

        row = cursor.fetchone()
        conn.commit()

        # Log audit
        cursor.execute("""
            INSERT INTO policy_audits (
                tenant_id, policy_id, trigger_intent, tier,
                violated, action, data_payload
            ) VALUES (%s, %s, %s, %s, FALSE, 'CREATE', %s)
        """, (x_tenant_id, req.policy_id, req.trigger_intent, req.tier,
              json.dumps({"created_by": x_user_id})))
        conn.commit()

        return PolicyResponse(
            policy_id=str(row["policy_id"]),
            version=row["version"],
            tier=row["tier"],
            trigger_intent=row["trigger_intent"],
            logic=row["logic"] if isinstance(row["logic"], dict) else json.loads(row["logic"]),
            action=row["action"] if isinstance(row["action"], dict) else json.loads(row["action"]),
            confidence=row["confidence"],
            source_name=row["source_name"],
            is_active=row["is_active"],
            created_at=row["created_at"].isoformat(),
            created_by=x_user_id
        )

    except psycopg2.IntegrityError as e:
        conn.rollback()
        if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
            raise HTTPException(status_code=400, detail=f"Policy {req.policy_id} version 1 already exists")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/policies/{policy_id}")
def update_policy(
    policy_id: str,
    req: PolicyUpdateRequest,
    x_tenant_id: str = Header(...),
    x_user_id: str = Header("system"),
    conn=Depends(get_db),
) -> dict:
    """Update policy by creating a new version in DB."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Get latest version
    cursor.execute("""
        SELECT * FROM policies
        WHERE policy_id = %s AND tenant_id = %s
        ORDER BY version DESC LIMIT 1
    """, (policy_id, x_tenant_id))

    latest = cursor.fetchone()
    if not latest:
        raise HTTPException(status_code=404, detail="Policy not found")

    new_version = latest["version"] + 1
    if new_version > MAX_POLICY_VERSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Policy {policy_id} has reached the maximum of {MAX_POLICY_VERSIONS} versions"
        )
    new_logic = json.dumps(req.logic) if req.logic else (
        json.dumps(latest["logic"]) if isinstance(latest["logic"], dict) else latest["logic"]
    )
    new_action = json.dumps(req.action) if req.action else (
        json.dumps(latest["action"]) if isinstance(latest["action"], dict) else latest["action"]
    )
    new_tier = req.tier or latest["tier"]
    new_confidence = req.confidence if req.confidence is not None else latest["confidence"]

    try:
        # Deactivate old version
        cursor.execute("""
            UPDATE policies SET is_active = FALSE, updated_at = NOW()
            WHERE policy_id = %s AND tenant_id = %s AND version = %s
        """, (policy_id, x_tenant_id, latest["version"]))

        # Insert new version
        cursor.execute("""
            INSERT INTO policies (
                policy_id, tenant_id, version, tier, trigger_intent,
                logic, action, confidence, source_name, roles, expires_at,
                is_active, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, NOW(), NOW())
            RETURNING version
        """, (
            policy_id, x_tenant_id, new_version, new_tier,
            latest["trigger_intent"], new_logic, new_action,
            new_confidence, latest["source_name"],
            latest.get("roles", []), latest.get("expires_at"),
        ))

        result = cursor.fetchone()
        conn.commit()

        return {"version": result["version"], "policy_id": policy_id, "tenant_id": x_tenant_id}

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/policies/{policy_id}/versions")
def get_version_history(
    policy_id: str,
    x_tenant_id: str = Header(...),
    conn=Depends(get_db),
) -> dict:
    """Get version history for policy from DB."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT * FROM policies
        WHERE policy_id = %s AND tenant_id = %s
        ORDER BY version DESC
    """, (policy_id, x_tenant_id))

    rows = cursor.fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="Policy not found")

    versions = []
    for row in rows:
        versions.append({
            "version": row["version"],
            "tier": row["tier"],
            "logic": row["logic"] if isinstance(row["logic"], dict) else json.loads(row["logic"]),
            "action": row["action"] if isinstance(row["action"], dict) else json.loads(row["action"]),
            "confidence": row["confidence"],
            "is_active": row["is_active"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        })

    return {
        "policy_id": policy_id,
        "tenant_id": x_tenant_id,
        "versions": versions,
        "total_versions": len(versions)
    }


@router.post("/policies/{policy_id}/rollback")
def rollback_policy(
    policy_id: str,
    target_version: int,
    x_tenant_id: str = Header(...),
    x_user_id: str = Header("system"),
    conn=Depends(get_db),
) -> dict:
    """Rollback policy to previous version by creating new version from old."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Get target version
    cursor.execute("""
        SELECT * FROM policies
        WHERE policy_id = %s AND tenant_id = %s AND version = %s
    """, (policy_id, x_tenant_id, target_version))

    target = cursor.fetchone()
    if not target:
        raise HTTPException(status_code=404, detail="Target version not found")

    # Get current max version
    cursor.execute("""
        SELECT MAX(version) as max_v FROM policies
        WHERE policy_id = %s AND tenant_id = %s
    """, (policy_id, x_tenant_id))
    max_v = cursor.fetchone()["max_v"]

    if max_v + 1 > MAX_POLICY_VERSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Policy {policy_id} has reached the maximum of {MAX_POLICY_VERSIONS} versions"
        )

    try:
        # Deactivate all versions
        cursor.execute("""
            UPDATE policies SET is_active = FALSE, updated_at = NOW()
            WHERE policy_id = %s AND tenant_id = %s
        """, (policy_id, x_tenant_id))

        # Insert rollback as new version
        new_version = max_v + 1
        cursor.execute("""
            INSERT INTO policies (
                policy_id, tenant_id, version, tier, trigger_intent,
                logic, action, confidence, source_name, roles, expires_at,
                is_active, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, NOW(), NOW())
            RETURNING version
        """, (
            policy_id, x_tenant_id, new_version, target["tier"],
            target["trigger_intent"],
            json.dumps(target["logic"]) if isinstance(target["logic"], dict) else target["logic"],
            json.dumps(target["action"]) if isinstance(target["action"], dict) else target["action"],
            target["confidence"], target["source_name"],
            target.get("roles", []), target.get("expires_at"),
        ))

        result = cursor.fetchone()
        conn.commit()

        return {
            "policy_id": policy_id,
            "tenant_id": x_tenant_id,
            "new_version": result["version"],
            "rolled_back_to": target_version
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/policies/{policy_id}/compare")
def compare_versions(
    policy_id: str,
    version_a: int,
    version_b: int,
    x_tenant_id: str = Header(...),
    conn=Depends(get_db),
) -> Any:
    """Compare two versions of a policy from DB."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT * FROM policies
        WHERE policy_id = %s AND tenant_id = %s AND version IN (%s, %s)
        ORDER BY version
    """, (policy_id, x_tenant_id, version_a, version_b))

    rows = cursor.fetchall()
    if len(rows) < 2:
        raise HTTPException(status_code=404, detail="One or both versions not found")

    a, b = rows[0], rows[1]
    logic_a = a["logic"] if isinstance(a["logic"], dict) else json.loads(a["logic"])
    logic_b = b["logic"] if isinstance(b["logic"], dict) else json.loads(b["logic"])
    action_a = a["action"] if isinstance(a["action"], dict) else json.loads(a["action"])
    action_b = b["action"] if isinstance(b["action"], dict) else json.loads(b["action"])

    return {
        "policy_id": policy_id,
        "version_a": version_a,
        "version_b": version_b,
        "differences": {
            "logic_changed": logic_a != logic_b,
            "action_changed": action_a != action_b,
            "tier_changed": a["tier"] != b["tier"],
            "confidence_changed": a["confidence"] != b["confidence"],
        },
        "version_a_data": {"logic": logic_a, "action": action_a, "tier": a["tier"], "confidence": a["confidence"]},
        "version_b_data": {"logic": logic_b, "action": action_b, "tier": b["tier"], "confidence": b["confidence"]},
    }


@router.get("/conflicts")
def detect_conflicts(
    x_tenant_id: str = Header(...),
    conn=Depends(get_db),
) -> dict:
    """Detect conflicts in tenant's active policies from DB."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT * FROM policies
        WHERE tenant_id = %s AND is_active = TRUE
          AND (expires_at IS NULL OR expires_at > NOW())
        ORDER BY tier, trigger_intent
    """, (x_tenant_id,))

    rows = cursor.fetchall()
    conflicts = []

    # Detect same-intent conflicts across tiers
    by_intent: Dict[str, list] = {}
    for row in rows:
        intent = row["trigger_intent"]
        if intent not in by_intent:
            by_intent[intent] = []
        by_intent[intent].append(row)

    for intent, policies in by_intent.items():
        if len(policies) > 1:
            for i in range(len(policies)):
                for j in range(i + 1, len(policies)):
                    a, b = policies[i], policies[j]
                    action_a = a["action"] if isinstance(a["action"], dict) else json.loads(a["action"])
                    action_b = b["action"] if isinstance(b["action"], dict) else json.loads(b["action"])
                    if action_a.get("on_fail") != action_b.get("on_fail"):
                        conflicts.append({
                            "type": "ACTION_CONFLICT",
                            "policy_a": str(a["policy_id"]),
                            "policy_b": str(b["policy_id"]),
                            "description": f"Same intent '{intent}' has different actions: {action_a.get('on_fail')} vs {action_b.get('on_fail')}",
                            "severity": "HIGH" if a["tier"] == b["tier"] else "MEDIUM",
                            "resolution": "Higher tier policy takes precedence",
                        })

    return {
        "tenant_id": x_tenant_id,
        "conflicts": conflicts,
        "total_conflicts": len(conflicts),
    }


@router.get("/stats")
def get_stats(
    x_tenant_id: str = Header(...),
    conn=Depends(get_db),
) -> Any:
    """Get policy statistics for tenant from DB."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE is_active = TRUE) as active,
            COUNT(*) FILTER (WHERE expires_at IS NOT NULL AND expires_at < NOW()) as expired,
            COUNT(*) FILTER (WHERE tier = 'GLOBAL' AND is_active = TRUE) as global_count,
            COUNT(*) FILTER (WHERE tier = 'CONTEXTUAL' AND is_active = TRUE) as contextual_count,
            COUNT(*) FILTER (WHERE tier = 'DYNAMIC' AND is_active = TRUE) as dynamic_count
        FROM policies
        WHERE tenant_id = %s
    """, (x_tenant_id,))

    row = cursor.fetchone()
    return {
        "tenant_id": x_tenant_id,
        "total": row["total"],
        "active": row["active"],
        "expired": row["expired"],
        "GLOBAL": row["global_count"],
        "CONTEXTUAL": row["contextual_count"],
        "DYNAMIC": row["dynamic_count"],
    }


@router.delete("/policies/{policy_id}")
def delete_policy(
    policy_id: str,
    x_tenant_id: str = Header(...),
    conn=Depends(get_db),
) -> dict:
    """Deactivate policy in DB (soft delete)."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        UPDATE policies SET is_active = FALSE, updated_at = NOW()
        WHERE policy_id = %s AND tenant_id = %s AND is_active = TRUE
        RETURNING policy_id, tier
    """, (policy_id, x_tenant_id))

    rows = cursor.fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="Policy not found or already deactivated")

    conn.commit()
    return {"policy_id": policy_id, "tenant_id": x_tenant_id, "status": "deactivated"}
