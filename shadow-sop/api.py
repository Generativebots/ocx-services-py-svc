"""
Process Mining / Shadow-SOP HTTP Service
Patent: Shadow execution for SOP validation + RLHC corrections

Exposes REST endpoints for:
- Shadow execution management (run, metrics, results, promote)
- RLHC correction recording and policy proposal
- Process mining trace CRUD (process_mining_traces table)

All endpoints are tenant-scoped via X-Tenant-ID header.
Default port: 8006
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from datetime import datetime
import logging
import os
import json
import uuid

from shadow_executor import ShadowExecutor, ShadowVerdict
from rlhc import ShadowSOPRLHC, CorrectionType

logger = logging.getLogger("shadow-sop-api")
logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="OCX Process Mining & Shadow-SOP Service",
    description="Patent-backed shadow execution engine and RLHC correction loop",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Singletons ────────────────────────────────────────────────────────────────
shadow_executor = ShadowExecutor()
rlhc_engine = ShadowSOPRLHC()

# ── Supabase DB client (optional, for process_mining_traces CRUD) ─────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

def _get_tenant(request: Request) -> str:
    return request.headers.get("X-Tenant-ID", os.getenv("OCX_DEFAULT_TENANT", "default"))

def _get_tenant_config(request: Request) -> dict:
    """Read tenant-specific config from X-Tenant-Config header (JSON).
    Injected by Go backend when proxying to Python services.
    Falls back to empty dict if not present (constructor defaults apply)."""
    raw = request.headers.get("X-Tenant-Config", "")
    if raw:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Invalid X-Tenant-Config header, ignoring")
    return {}

def _supabase_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

# ── Request/Response Models ───────────────────────────────────────────────────

class ShadowRunRequest(BaseModel):
    sop_id: str
    request_payload: Dict[str, Any] = Field(default_factory=dict)

class CorrectionRequest(BaseModel):
    agent_id: str
    action_type: str
    correction_type: str  # ALLOW_OVERRIDE, BLOCK_OVERRIDE, etc.
    original_action: Dict[str, Any] = Field(default_factory=dict)
    corrected_action: Dict[str, Any] = Field(default_factory=dict)
    reviewer_id: str = "system"  # Human reviewer identifier
    reason: str = ""
    context: Dict[str, Any] = Field(default_factory=dict)

class TraceCreateRequest(BaseModel):
    trace_id: Optional[str] = None
    process_id: str
    agent_id: str
    step_name: str
    status: str = "RUNNING"
    metadata: Dict[str, Any] = Field(default_factory=dict)

# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "shadow-sop-process-mining"}

# ── Shadow Execution (Patent: Shadow SOP Validation) ─────────────────────────

@app.get("/shadow/metrics")
async def get_all_shadow_metrics(request: Request):
    """Get aggregate shadow execution metrics for all SOPs (tenant-scoped)."""
    tenant_id = _get_tenant(request)
    metrics = shadow_executor.get_all_metrics(tenant_id)
    return {
        "tenant_id": tenant_id,
        "experiments": [
            {
                "sop_id": m.sop_id,
                "total_executions": m.total_executions,
                "identical_count": m.identical_count,
                "equivalent_count": m.equivalent_count,
                "divergent_count": m.divergent_count,
                "shadow_better_count": m.shadow_better_count,
                "shadow_worse_count": m.shadow_worse_count,
                "shadow_error_count": m.shadow_error_count,
                "avg_latency_delta_ms": round(m.avg_latency_delta_ms, 2),
                "divergence_rate": round(m.divergence_rate, 4),
                "confidence_score": round(m.confidence_score, 4),
                "started_at": m.started_at,
                "last_execution_at": m.last_execution_at,
            }
            for k, m in metrics.items()
        ],
    }

@app.get("/shadow/metrics/{sop_id}")
async def get_shadow_metrics(sop_id: str, request: Request):
    """Get shadow metrics for a specific SOP."""
    tenant_id = _get_tenant(request)
    m = shadow_executor.get_metrics(sop_id, tenant_id)
    if not m:
        raise HTTPException(404, f"No shadow experiment for SOP {sop_id}")
    return {
        "sop_id": m.sop_id,
        "tenant_id": m.tenant_id,
        "total_executions": m.total_executions,
        "divergence_rate": round(m.divergence_rate, 4),
        "confidence_score": round(m.confidence_score, 4),
        "promotable": shadow_executor.should_promote(f"{tenant_id}:{sop_id}"),
    }

@app.get("/shadow/results/{sop_id}")
async def get_shadow_results(sop_id: str, request: Request, limit: int = 50):
    """Get recent shadow execution results for an SOP."""
    tenant_id = _get_tenant(request)
    results = shadow_executor.get_results(sop_id, tenant_id, limit)
    return {
        "sop_id": sop_id,
        "count": len(results),
        "results": [
            {
                "execution_id": r.execution_id,
                "verdict": r.verdict.value,
                "latency_prod_ms": round(r.latency_prod_ms, 2),
                "latency_shadow_ms": round(r.latency_shadow_ms, 2),
                "timestamp": r.timestamp,
            }
            for r in results
        ],
    }

@app.post("/shadow/promote/{sop_id}")
async def promote_shadow(sop_id: str, request: Request):
    """Check if a shadow SOP is ready for production promotion."""
    tenant_id = _get_tenant(request)
    tc = _get_tenant_config(request)
    min_confidence = tc.get("shadow_min_confidence", 0.95)
    min_executions = tc.get("shadow_min_executions", 100)
    key = f"{tenant_id}:{sop_id}"
    promotable = shadow_executor.should_promote(key, min_executions=min_executions, min_confidence=min_confidence)
    m = shadow_executor.get_metrics(sop_id, tenant_id)
    return {
        "sop_id": sop_id,
        "promotable": promotable,
        "confidence": round(m.confidence_score, 4) if m else 0,
        "total_executions": m.total_executions if m else 0,
        "config": {"min_confidence": min_confidence, "min_executions": min_executions},
    }

# ── RLHC Corrections (Patent: Reinforcement Learning from Human Corrections)

@app.post("/rlhc/corrections")
async def record_correction(req: CorrectionRequest, request: Request):
    """Record a human correction for RLHC policy learning."""
    tenant_id = _get_tenant(request)
    tc = _get_tenant_config(request)

    # Thread-safe: read tenant config per-request without mutating shared singleton.
    # These values are used only within this request scope.
    pattern_similarity = float(tc.get("rlhc_pattern_similarity_threshold", 0.7))
    policy_approval = float(tc.get("rlhc_policy_approval_threshold", 0.8))
    min_corrections = int(tc.get("rlhc_min_corrections_for_pattern", 3))

    try:
        corr_type = CorrectionType(req.correction_type)
    except ValueError:
        valid = [ct.value for ct in CorrectionType]
        raise HTTPException(400, f"Invalid correction_type. Must be one of: {valid}")

    correction = await rlhc_engine.record_correction(
        tenant_id=tenant_id,
        agent_id=req.agent_id,
        correction_type=corr_type,
        original_action=req.original_action.get("action", req.action_type),
        corrected_action=req.corrected_action.get("action", ""),
        tool_id=req.original_action.get("tool_id", ""),
        transaction_id=req.original_action.get("transaction_id", ""),
        reviewer_id=req.reviewer_id,
        reasoning=req.reason,
        context=req.context,
        # Pass tenant-specific thresholds per-request (no singleton mutation)
        pattern_similarity_threshold=pattern_similarity,
        min_corrections_for_pattern=min_corrections,
        policy_approval_threshold=policy_approval,
    )
    return {
        "status": "recorded",
        "correction_id": correction.correction_id,
        "tenant_id": tenant_id,
        "config": {
            "pattern_similarity_threshold": pattern_similarity,
            "policy_approval_threshold": policy_approval,
            "min_corrections_for_pattern": min_corrections,
        },
    }

@app.get("/rlhc/patterns")
async def get_correction_patterns(request: Request):
    """Get correction patterns extracted by the RLHC engine."""
    # Patterns are stored internally in the engine
    patterns = []
    for p_id, p in rlhc_engine.patterns.items():
        patterns.append({
            "pattern_id": p.pattern_id,
            "pattern_type": p.pattern_type,
            "action_pattern": p.action_pattern,
            "observation_count": p.observation_count,
            "accuracy": round(p.accuracy, 4),
            "confidence": round(p.confidence, 4),
            "first_observed": p.first_observed.isoformat(),
            "last_observed": p.last_observed.isoformat(),
        })
    return {"patterns": patterns}

@app.get("/rlhc/proposals")
async def get_policy_proposals(request: Request):
    """Get proposed policy changes from RLHC learning."""
    pending = rlhc_engine.get_pending_policies()
    return {
        "proposals": [
            {
                "policy_id": p.policy_id,
                "name": p.name,
                "description": p.description,
                "status": p.status.value,
                "policy_type": p.policy_type,
                "conditions": p.conditions,
                "action": p.action,
                "proposed_at": p.proposed_at.isoformat(),
                "effectiveness_score": round(p.effectiveness_score, 4),
            }
            for p in pending
        ]
    }

@app.get("/rlhc/stats")
async def get_rlhc_stats(request: Request):
    """Get overall RLHC statistics."""
    return rlhc_engine.get_stats()

# ── Process Mining Traces (CRUD for process_mining_traces table) ──────────────

@app.get("/traces")
async def list_traces(request: Request, limit: int = 100):
    """List process mining traces (reads from process_mining_traces table)."""
    tenant_id = _get_tenant(request)
    if not SUPABASE_URL:
        return {"traces": [], "message": "SUPABASE_URL not configured"}

    import httpx
    url = f"{SUPABASE_URL}/rest/v1/process_mining_traces"
    params = {
        "tenant_id": f"eq.{tenant_id}",
        "order": "created_at.desc",
        "limit": str(limit),
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=_supabase_headers(), params=params)
    if resp.status_code != 200:
        raise HTTPException(resp.status_code, resp.text)
    return {"traces": resp.json()}

@app.post("/traces")
async def create_trace(trace: TraceCreateRequest, request: Request):
    """Create a new process mining trace."""
    tenant_id = _get_tenant(request)
    if not SUPABASE_URL:
        raise HTTPException(503, "SUPABASE_URL not configured")

    row = {
        "trace_id": trace.trace_id or str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "process_id": trace.process_id,
        "agent_id": trace.agent_id,
        "step_name": trace.step_name,
        "status": trace.status,
        "metadata": json.dumps(trace.metadata),
    }
    import httpx
    url = f"{SUPABASE_URL}/rest/v1/process_mining_traces"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=_supabase_headers(), json=row)
    if resp.status_code not in (200, 201):
        raise HTTPException(resp.status_code, resp.text)
    return resp.json()

@app.get("/traces/{trace_id}")
async def get_trace(trace_id: str, request: Request):
    """Get a specific process mining trace."""
    tenant_id = _get_tenant(request)
    if not SUPABASE_URL:
        raise HTTPException(503, "SUPABASE_URL not configured")

    import httpx
    url = f"{SUPABASE_URL}/rest/v1/process_mining_traces"
    params = {"trace_id": f"eq.{trace_id}", "tenant_id": f"eq.{tenant_id}"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=_supabase_headers(), params=params)
    rows = resp.json()
    if not rows:
        raise HTTPException(404, f"Trace {trace_id} not found")
    return rows[0]

# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8006"))
    uvicorn.run(app, host="0.0.0.0", port=port)
