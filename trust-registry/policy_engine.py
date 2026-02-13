from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from registry import Registry
import json
import datetime

router = APIRouter()
registry = Registry()

# -- Models --

import hashlib
import logging
logger = logging.getLogger(__name__)


# -- Models --

# We now accept the full Flexible JSON Schema
class RegisterAgentRequest(BaseModel):
    tenant_id: str # Required for multi-tenancy
    agent_id: Optional[str] = None
    metadata: Dict[str, Any]
    security_handshake: Dict[str, Any]
    capabilities: List[Dict[str, Any]]
    governance_profile: Dict[str, Any]
    status: Optional[str] = "Active"
    
    # Extra fields for verification simulation
    system_prompt_text: Optional[str] = None 

class DraftRuleRequest(BaseModel):
    natural_language: str
    tenant_id: str

class DeployRuleRequest(BaseModel):
    tenant_id: str
    natural_language: str
    logic_json: Dict[str, Any]
    priority: int = 1

# -- Endpoints --

@router.post("/agents", status_code=201)
def register_agent(req: RegisterAgentRequest) -> dict:
    # 1. Capability Hash Verification
    provided_hash = req.security_handshake.get("capability_hash")
    
    if req.system_prompt_text and provided_hash:
        tool_slugs = "".join(sorted([t["tool_name"] for t in req.capabilities]))
        hash_input = f"{req.system_prompt_text}{tool_slugs}"
        calculated = hashlib.sha256(hash_input.encode()).hexdigest()
        
        if calculated != provided_hash:
             raise HTTPException(status_code=400, detail=f"Security Handshake Failed: Capability Hash mismatch. (Calculated: {calculated})")
    
    # 2. Register
    payload = req.dict(exclude={"system_prompt_text", "tenant_id"}) 
    agent_id = registry.register_agent(payload, req.tenant_id)
    
    return {"agent_id": agent_id, "status": "Registered", "tenant_id": req.tenant_id, "hash_verified": True if req.system_prompt_text else "Skipped"}


@router.get("/agents")
def list_agents(tenant_id: str) -> Any:
    """List agents filtered by tenant_id for multi-tenant isolation."""
    all_agents = registry.list_agents(tenant_id)
    # Double-check tenant filtering in case registry returns unfiltered results
    if isinstance(all_agents, list):
        return [a for a in all_agents if a.get("tenant_id") == tenant_id or not a.get("tenant_id")]
    return all_agents

@router.post("/rules/draft")
def draft_rule(req: DraftRuleRequest) -> dict:
    """
    Simulates Gemini 2.0 translating Natural Language to JSON Rule Logic.
    """
    nl = req.natural_language.lower()
    
    # Mock LLM Logic
    rule_logic = {}
    
    if "spend" in nl and "finance" in nl:
        limit = 5000 
        rule_logic = {
            "condition": {
                "field": "amount",
                "operator": ">",
                "value": limit
            },
            "exception": {
                "role": "Finance-Controller"
            },
            "action": "BLOCK",
            "reason": f"Spending limit of ${limit} exceeded."
        }
    elif "pii" in nl or "public" in nl:
         rule_logic = {
            "condition": {
                "contains": ["email", "ssn", "@"],
                "channel": "public"
            },
            "action": "BLOCK",
            "reason": "PII detected in public channel."
         }
    else:
        rule_logic = {
            "condition": "custom_eval",
            "prompt": f"Does this action violate: {req.natural_language}?",
            "action": "FLAG"
        }
        
    return {"natural_language": req.natural_language, "generated_logic": rule_logic, "tenant_id": req.tenant_id}

@router.post("/rules")
def deploy_rule(req: DeployRuleRequest) -> dict:
    # Correctly pass tenant_id as 3rd arg
    rule_id = registry.add_rule(req.natural_language, req.logic_json, req.tenant_id, req.priority)
    return {"rule_id": rule_id, "status": "Active", "tenant_id": req.tenant_id}

@router.get("/rules")
def get_rules(tenant_id: str = "") -> Any:
    """List active rules, filtered by tenant if specified."""
    rules = registry.get_active_rules()
    if tenant_id and isinstance(rules, list):
        return [r for r in rules if r.get("tenant_id") == tenant_id or not r.get("tenant_id")]
    return rules

@router.post("/agents/{agent_id}/eject")
def eject_agent_endpoint(agent_id: str, req: dict) -> dict:
    """
    Emergency Kill Switch endpoint.
    Requires tenant_id in body for verification.
    """
    tenant_id = req.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id required")
        
    success = registry.eject_agent(agent_id, tenant_id)
    if success:
        return {"status": "EJECTED", "agent_id": agent_id, "timestamp": datetime.datetime.now().isoformat()}
    else:
        raise HTTPException(status_code=500, detail="Failed to eject agent")
