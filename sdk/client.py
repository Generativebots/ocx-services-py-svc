"""
OCX Governance Client for Python.

Usage:
    from ocx_sdk import OCXClient

    client = OCXClient(
        gateway_url="https://ocx-gateway.example.com",
        tenant_id="acme-corp",
        api_key=os.environ["OCX_API_KEY"],
    )

    # Govern a tool call
    result = client.execute_tool("execute_payment", {
        "amount": 100.00,
        "currency": "USD",
        "to": "vendor@example.com",
    })

    if result.verdict == "ALLOW":
        # Safe to execute
        actual_payment(result.arguments)
    elif result.verdict == "BLOCK":
        print(f"Blocked: {result.reason}")
    elif result.verdict == "ESCROW":
        print(f"Held for review: {result.escrow_id}")
"""

import os
import time
import uuid
import requests
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Callable
import logging
logger = logging.getLogger(__name__)



@dataclass
class JITTokenInfo:
    """JIT Token issued by the Token Broker (Claim 7)."""
    token_id: str = ""
    token: str = ""
    attribution: str = ""
    expires_at: str = ""


@dataclass
class SOPDriftInfo:
    """SOP Drift report from Claim 13."""
    path_edit_distance: int = 0
    normalized_edit_distance: float = 0.0
    policy_violations: int = 0
    governance_tax_adjustment: float = 1.0
    missing_steps: list = field(default_factory=list)
    extra_steps: list = field(default_factory=list)


@dataclass
class GovernanceResult:
    """Result from the OCX governance pipeline."""
    transaction_id: str = ""
    verdict: str = "ALLOW"  # ALLOW, BLOCK, ESCROW, ESCALATE
    action_class: str = ""  # CLASS_A, CLASS_B
    reason: str = ""
    trust_score: float = 0.0
    governance_tax: float = 0.0
    escrow_id: str = ""
    entitlement_id: str = ""
    evidence_hash: str = ""
    speculative_hash: str = ""  # G5: speculative execution hash (Claim 1)
    processed_at: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)
    # G5: JIT token from Token Broker (Claim 7)
    jit_token: Optional[JITTokenInfo] = None
    # G5: SOP drift report (Claim 13)
    sop_drift: Optional[SOPDriftInfo] = None
    # G5: Ghost state side effects count (Claim 9)
    ghost_side_effects: int = 0


class OCXClient:
    """
    OCX Governance SDK Client.
    
    Drop this into ANY Python AI agent to route all tool calls through
    the OCX patent governance pipeline.
    """
    
    def __init__(
        self,
        gateway_url: str = None,
        tenant_id: str = None,
        api_key: str = None,
        agent_id: str = None,
        timeout: int = 30,
        on_block: Callable = None,
        on_escrow: Callable = None,
    ) -> None:
        self.gateway_url = gateway_url or os.environ.get("OCX_GATEWAY_URL", "http://localhost:8080")
        self.tenant_id = tenant_id or os.environ.get("OCX_TENANT_ID", "default")
        self.api_key = api_key or os.environ.get("OCX_API_KEY", "")
        self.agent_id = agent_id or f"py-agent-{uuid.uuid4().hex[:8]}"
        self.timeout = timeout
        self.on_block = on_block
        self.on_escrow = on_escrow
        self._session = requests.Session()
        
        # Set default headers
        self._session.headers.update({
            "Content-Type": "application/json",
            "X-Tenant-ID": self.tenant_id,
            "X-Agent-ID": self.agent_id,
        })
        if self.api_key:
            self._session.headers["Authorization"] = f"Bearer {self.api_key}"

    def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any] = None,
        model: str = "",
        session_id: str = "",
        protocol: str = "python-sdk",
    ) -> GovernanceResult:
        """
        Send a tool call through the OCX governance pipeline.
        
        Args:
            tool_name: The tool being called (e.g., "execute_payment")
            arguments: Tool call parameters
            model: LLM model making the decision (optional)
            session_id: Conversation/session ID (optional)
            protocol: Source framework identifier
            
        Returns:
            GovernanceResult with verdict (ALLOW/BLOCK/ESCROW)
        """
        payload = {
            "tool_name": tool_name,
            "agent_id": self.agent_id,
            "tenant_id": self.tenant_id,
            "arguments": arguments or {},
            "model": model,
            "session_id": session_id,
            "protocol": protocol,
            "timestamp": time.time(),
        }
        
        try:
            resp = self._session.post(
                f"{self.gateway_url}/api/v1/govern",
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            
            result = GovernanceResult(
                transaction_id=data.get("transaction_id", ""),
                verdict=data.get("verdict", "ALLOW"),
                action_class=data.get("action_class", ""),
                reason=data.get("reason", ""),
                trust_score=data.get("trust_score", 0.0),
                governance_tax=data.get("governance_tax", 0.0),
                escrow_id=data.get("escrow_id", ""),
                entitlement_id=data.get("entitlement_id", ""),
                evidence_hash=data.get("evidence_hash", ""),
                speculative_hash=data.get("speculative_hash", ""),
                processed_at=data.get("processed_at", ""),
                arguments=arguments or {},
                ghost_side_effects=data.get("ghost_side_effects", 0),
            )
            
            # Parse JIT token if present (Claim 7)
            jit_data = data.get("jit_token")
            if jit_data and isinstance(jit_data, dict):
                result.jit_token = JITTokenInfo(
                    token_id=jit_data.get("token_id", ""),
                    token=jit_data.get("token", ""),
                    attribution=jit_data.get("attribution", ""),
                    expires_at=jit_data.get("expires_at", ""),
                )
            
            # Parse SOP drift if present (Claim 13)
            drift_data = data.get("sop_drift")
            if drift_data and isinstance(drift_data, dict):
                result.sop_drift = SOPDriftInfo(
                    path_edit_distance=drift_data.get("path_edit_distance", 0),
                    normalized_edit_distance=drift_data.get("normalized_edit_distance", 0.0),
                    policy_violations=drift_data.get("policy_violations", 0),
                    governance_tax_adjustment=drift_data.get("governance_tax_adjustment", 1.0),
                    missing_steps=drift_data.get("missing_steps", []),
                    extra_steps=drift_data.get("extra_steps", []),
                )
            
            # Trigger callbacks
            if result.verdict == "BLOCK" and self.on_block:
                self.on_block(result)
            elif result.verdict == "ESCROW" and self.on_escrow:
                self.on_escrow(result)
                
            return result
            
        except requests.RequestException as e:
            # Fail-open or fail-closed based on config
            print(f"⚠️ OCX governance request failed: {e}")
            return GovernanceResult(
                verdict="ALLOW",
                reason=f"Governance unavailable: {e}",
                arguments=arguments or {},
            )

    def check_entitlement(self, tool_name: str) -> bool:
        """Check if the agent has permission to call a specific tool."""
        try:
            resp = self._session.get(
                f"{self.gateway_url}/api/v1/entitlements/active",
                params={"agent_id": self.agent_id},
                timeout=10,
            )
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def get_trust_score(self) -> tuple:
        """Get the agent's current trust score and tier."""
        try:
            resp = self._session.get(
                f"{self.gateway_url}/api/reputation/{self.agent_id}",
                timeout=10,
            )
            data = resp.json()
            return data.get("score", 0.5), data.get("tier", "BRONZE")
        except (requests.RequestException, ValueError):
            return 0.5, "BRONZE"
