import os
import uuid
import json
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from ecdsa import VerifyingKey, NIST256p

from jury import Jury
from ledger import Ledger
from kill_switch import KillSwitch
from registry import Registry
from policy_engine import router as policy_router
from ape_engine import router as ape_router
from orchestrator import ocx_governance_orchestrator

app = FastAPI(title="OCX Trust Registry (The Heart)")

# Enable CORS for Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(policy_router, prefix="/policy", tags=["Policy Engine"])
app.include_router(ape_router, prefix="/ape", tags=["APE Engine"])

# Initialize Components
jury = Jury()
ledger = Ledger()
kill_switch = KillSwitch()
registry = Registry()

# Load Rules
try:
    with open("rules_v1.md", "r") as f:
        STATIC_RULES = f.read()
except FileNotFoundError:
    STATIC_RULES = "Standard Golden Rules apply."

class EvaluationRequest(BaseModel):
    agent_id: str
    tenant_id: str
    proposed_action: str
    context: Dict[str, Any]
    trace_id: Optional[str] = None # New field

class EvaluationResponse(BaseModel):
    trust_score: float
    safety_token: Optional[str]
    reasoning: str
    status: str
    breakdown: Dict[str, float] # Changed to Dict

@app.get("/health")
def health():
    return {"status": "ok", "service": "Trust Registry"}

@app.post("/evaluate", response_model=EvaluationResponse)
async def evaluate_intent(req: EvaluationRequest, request: Request = None):
    # Ensure Trace ID
    trace_id = req.trace_id or f"trace-{uuid.uuid4()}"
    
    print(f"⚖️  Processing Intent from {req.agent_id} [Trace: {trace_id}]")
    
    # 0. PROTOCOL CHECK & METADATA EXTRACTION
    metadata = {}
    if request:
        headers = request.headers
        metadata["version"] = headers.get("X-Version", "1.0")
        metadata["tier"] = headers.get("X-Governance-Tier", "Standard")
        metadata["auth_scope"] = headers.get("X-Auth-Scope", "*")
        
        agent_id_header = headers.get("X-Agent-ID")
        signature = headers.get("X-Signature")
        payload_hash = headers.get("X-Payload-Hash")
        
        if signature and agent_id_header:
            try:
                vk_hex = agent_id_header
                vk = VerifyingKey.from_string(bytes.fromhex(vk_hex), curve=NIST256p)
                if vk.verify(bytes.fromhex(signature), payload_hash.encode()):
                    print(f"🔐 Protocol Verified: Valid Signature from {agent_id_header[:8]}...")
                    metadata["verified_identity"] = True
                else:
                    raise HTTPException(status_code=401, detail="Invalid Signature")
            except Exception as e:
                print(f"❌ Protocol Error: {e}")
                pass
    
    # 1. THE JURY (Consensus)
    # Fetch Dynamic Rules
    # 1. ORCHESTRATION (The Governor)
    # Fetch Dynamic Rules
    active_rules = registry.get_active_rules()
    rules_context = STATIC_RULES + "\n\nACTIVE DYNAMIC RULES:\n" + json.dumps(active_rules, indent=2)
    
    # Prepare Agent Metadata
    agent_metadata = {
        "agent_id": req.agent_id,
        "tenant_id": req.tenant_id,
        "tier": metadata.get("tier", "Standard")
    }
    
    # Prepare Components
    components = {
        "jury": jury,
        "ledger": ledger
        # KillSwitch is internal to Orchestrator or used if Orchestrator returns block
    }
    
    # Call Orchestrator
    result = ocx_governance_orchestrator(
        payload={"proposed_action": req.proposed_action, "context": req.context},
        agent_metadata=agent_metadata,
        business_rules=rules_context,
        components=components
    )
    
    score = result['trust_score']
    status = result['status'] 
    breakdown = result['auditor_breakdown']
    reason = result['reasoning']
    
    # Handle Tokens based on Status
    token = None
    if status == "BLOCKED":
        token = None
    elif status == "WARN" or status == "APPROVED_WITH_WARNING":
        status = "APPROVED_WITH_WARNING"
        token = f"st_{uuid.uuid4().hex[:8]}_warn"
    else:
        status = "APPROVED"
        token = f"st_{uuid.uuid4().hex[:8]}_ok"

    return EvaluationResponse(
        trust_score=score,
        safety_token=token,
        reasoning=reason,
        status=status,
        breakdown=breakdown
    )


# Note: /health route is already defined above at line 57

@app.get("/ledger/recent")
def get_ledger_recent():
    return ledger.get_recent_transactions()

@app.get("/ledger/stats")
def get_ledger_stats():
    return ledger.get_daily_stats()

@app.get("/ledger/health/{agent_id}")
def check_agent_health(agent_id: str):
    return ledger.check_weekly_drift(agent_id)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
@app.get("/memory/vault")
async def get_memory_vault():
    """
    Reads the Memory Vault logs from the filesystem.
    """
    vault_path = "../memory-engine/vault"
    logs = []
    
    if os.path.exists(vault_path):
        for filename in os.listdir(vault_path):
            if filename.endswith(".jsonl"):
                with open(os.path.join(vault_path, filename), "r") as f:
                    for line in f:
                        if line.strip():
                            try:
                                logs.append(json.loads(line))
                            except:
                                pass
    
    # Sort by timestamp desc
    logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return {"logs": logs}
