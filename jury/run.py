#!/usr/bin/env python3
"""
OCX Jury Service — Cloud Run entry point.
FastAPI wrapper exposing gRPC audit logic via REST.

Cloud Run requires an HTTP listener on $PORT (8080).

Environment variables:
    PORT: HTTP port (default: 8080, set by Cloud Run)
    VLLM_BASE_URL: vLLM endpoint for LLM inference
"""

import os
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Dict, Any, Optional
import uvicorn

app = FastAPI(title="OCX Jury Auditor")


# ---- Request / Response models ----

class AuditRequest(BaseModel):
    transaction_id: str = ""
    agent_id: str = ""
    tool_name: str = ""
    parameters: Dict[str, Any] = {}
    context: Dict[str, Any] = {}


class AuditResponse(BaseModel):
    transaction_id: str
    verdict: str
    confidence: float
    reason: str
    audit_time: float


# ---- Auditor core (inlined from grpc_server logic) ----

_active_policies: Dict[str, Any] = {"default": {
    "name": "Default Policy",
    "allowed_actions": ["*"],
    "max_transaction_value": 100000,
    "require_attestation": False,
}}

LLM_ENDPOINT = os.getenv("VLLM_BASE_URL", "http://localhost:8000")


def _rule_based_fallback(prompt: str) -> Dict[str, Any]:
    """Rule-based fallback when LLM is unavailable."""
    prompt_lower = prompt.lower()
    high_risk = ["delete", "drop", "truncate", "rm -rf", "shutdown",
                 "sudo", "admin", "root", "credential", "secret",
                 "transfer_funds", "withdraw", "escalate_privilege"]
    for kw in high_risk:
        if kw in prompt_lower:
            return {"verdict": "FAIL", "confidence": 0.70,
                    "reason": f"Rule-based: high-risk keyword '{kw}' detected (LLM unavailable)"}
    return {"verdict": "PASS", "confidence": 0.60,
            "reason": "Rule-based: no high-risk patterns detected (LLM unavailable)"}


def _execute_audit(tx_id: str, agent_id: str, tool_name: str,
                   parameters: dict, ctx: dict) -> Dict[str, Any]:
    """Run the audit pipeline."""
    import time, json
    start = time.time()

    policy = _active_policies.get(tool_name, _active_policies.get("default", {}))
    prompt = f"""SYSTEM: You are the OCX Jury. Audit Agent Intent against Enterprise Policy.
POLICY: {json.dumps(policy, indent=2)}
AGENT INTENT: tx={tx_id}, agent={agent_id}, tool={tool_name}, params={json.dumps(parameters)}
Respond with JSON: {{"verdict":"PASS/FAIL","confidence":0.0-1.0,"reason":"..."}}
"""
    # Try LLM, fallback to rules
    try:
        import requests
        resp = requests.post(f"{LLM_ENDPOINT}/v1/completions",
                             json={"prompt": prompt, "temperature": 0, "max_tokens": 256, "stop": ["}"]},
                             timeout=10)
        resp.raise_for_status()
        text = resp.json().get("choices", [{}])[0].get("text", "").strip() + "}"
        verdict_data = json.loads(text)
    except Exception:
        verdict_data = _rule_based_fallback(prompt)

    elapsed = time.time() - start
    return {
        "transaction_id": tx_id,
        "verdict": verdict_data.get("verdict", "FAIL"),
        "confidence": verdict_data.get("confidence", 0.0),
        "reason": verdict_data.get("reason", "Unknown"),
        "audit_time": round(elapsed, 4),
    }


# ---- Endpoints ----

@app.get("/health")
def health():
    return {"status": "ok", "service": "jury"}


@app.post("/audit", response_model=AuditResponse)
def audit_intent(req: AuditRequest):
    result = _execute_audit(req.transaction_id, req.agent_id, req.tool_name,
                            req.parameters, req.context)
    return AuditResponse(**result)


def main():
    port = int(os.getenv("PORT", "8080"))
    logger.info(f"⚖️  Starting OCX Jury Service on 0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
