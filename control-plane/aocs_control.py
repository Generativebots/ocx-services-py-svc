"""
AOCS Control Plane - User-Space Orchestrator for eBPF Events

This is the central control plane that:
1. Receives escrow events from eBPF kernel hooks (via ring buffer)
2. Orchestrates Tri-Factor Gate validation
3. Updates eBPF verdict cache with final decisions
4. Manages tool registry synchronization

In production, this uses BCC (BPF Compiler Collection) for eBPF interaction.
For development/testing, we provide mock implementations.
"""

import asyncio
import logging
import json
import struct
import time
from typing import Dict, Optional, Callable, Any, List
from dataclasses import dataclass, field
from enum import IntEnum
from datetime import datetime
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# CONSTANTS (Match eBPF definitions)
# ============================================================================

class ActionVerdict(IntEnum):
    """Verdict constants matching eBPF"""
    ALLOW = 0
    BLOCK = 1
    HOLD = 2


class ActionClass(IntEnum):
    """Tool classification constants"""
    CLASS_A = 0  # Reversible - Ghost-Turn
    CLASS_B = 1  # Irreversible - Atomic-Hold


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class EscrowEvent:
    """Event from eBPF escrow_events ring buffer"""
    pid: int
    tid: int
    cgroup_id: int
    timestamp: int
    tool_id_hash: int
    action_class: int
    tenant_id: int
    binary_hash: int
    trust_level: int
    reversibility_index: int
    required_entitlements: int
    present_entitlements: int
    entitlement_valid: int
    data_size: int
    verdict: int  # 0=pending


@dataclass
class TriFactorGateResult:
    """Result from Tri-Factor Gate validation"""
    transaction_id: str
    identity_passed: bool
    signal_passed: bool
    cognitive_passed: bool
    all_passed: bool
    final_verdict: ActionVerdict
    trust_level: float
    reasoning: str


@dataclass
class ToolRegistryEntry:
    """Tool metadata for eBPF synchronization"""
    tool_id: str
    tool_id_hash: int
    action_class: int
    reversibility_index: int
    min_reputation_score: int  # 0-100
    governance_tax_mult: int  # 100 = 1.0x
    required_entitlements: int  # Bitmask
    hitl_required: int


# ============================================================================
# SERVICE CLIENTS
# ============================================================================

class IdentityValidator:
    """Client for Identity validation (MFAA, SPIFFE)"""
    
    def __init__(self, base_url: str = "http://localhost:8000") -> None:
        self.base_url = base_url
    
    async def verify(
        self,
        pid: int,
        binary_hash: int,
        tenant_id: int,
        trust_level: int,
        entitlements: int,
    ) -> Dict[str, Any]:
        """Verify agent identity."""
        # In production, this would call the Identity service
        # For now, simulate validation
        
        mfaa_passed = trust_level >= 50  # Minimum trust for MFAA
        spiffe_passed = binary_hash != 0  # Has valid binary hash
        entitlement_valid = entitlements != 0  # Has some entitlements
        
        return {
            "passed": mfaa_passed and spiffe_passed and entitlement_valid,
            "mfaa_verified": mfaa_passed,
            "spiffe_verified": spiffe_passed,
            "reputation_score": trust_level / 100.0,
            "entitlement_valid": entitlement_valid,
            "reason": "Identity validation complete",
        }


class SignalAnalyzer:
    """Client for Signal validation (Entropy, Jitter)"""
    
    def __init__(self, base_url: str = "http://localhost:8000") -> None:
        self.base_url = base_url
    
    async def analyze(
        self,
        payload_hex: str,
        tenant_id: str,
        timestamps: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """Analyze signal integrity."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.base_url}/entropy/validate",
                    json={
                        "payload_hex": payload_hex,
                        "tenant_id": tenant_id,
                        "timestamps": timestamps or [],
                    },
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "passed": data.get("overall_verdict") != "REJECT",
                        "entropy_verdict": data.get("entropy_verdict"),
                        "jitter_verdict": data.get("jitter_analysis", {}).get("verdict"),
                        "risk_factors": data.get("risk_factors", []),
                        "reason": f"Signal: {data.get('overall_verdict')}",
                    }
        except Exception as e:
            logger.warning(f"Signal analysis failed: {e}")
        
        # Default: pass (fail-open for signal)
        return {
            "passed": True,
            "entropy_verdict": "CLEAN",
            "jitter_verdict": "NORMAL",
            "risk_factors": [],
            "reason": "Signal validation (mock)",
        }


class CognitiveValidator:
    """Client for Cognitive validation (Jury, APE)"""
    
    def __init__(self, base_url: str = "http://localhost:8000") -> None:
        self.base_url = base_url
    
    async def audit(
        self,
        transaction_id: str,
        tenant_id: str,
        agent_id: str,
        tool_id: str,
        payload: Dict[str, Any],
        entitlements: List[str],
    ) -> Dict[str, Any]:
        """Perform cognitive audit."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.base_url}/cognitive/audit",
                    json={
                        "transaction_id": transaction_id,
                        "tenant_id": tenant_id,
                        "agent_id": agent_id,
                        "tool_id": tool_id,
                        "payload": payload,
                        "entitlements": entitlements,
                    },
                    timeout=10.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "passed": data.get("verdict") == "ALLOW",
                        "verdict": data.get("verdict"),
                        "trust_level": data.get("trust_level"),
                        "violations": data.get("violations_count", 0),
                        "anomaly_detected": data.get("anomaly_detected"),
                        "reason": data.get("reasoning"),
                    }
        except Exception as e:
            logger.warning(f"Cognitive audit failed: {e}")
        
        # Default: fail-secure for cognitive
        return {
            "passed": False,
            "verdict": "HOLD",
            "trust_level": 0.5,
            "violations": 0,
            "anomaly_detected": False,
            "reason": "Cognitive validation unavailable - defaulting to HOLD",
        }


# ============================================================================
# AOCS CONTROL PLANE
# ============================================================================

class AOCSControlPlane:
    """
    Central control plane for AOCS governance.
    
    Responsibilities:
    1. Listen for eBPF escrow events
    2. Orchestrate Tri-Factor Gate validation
    3. Update eBPF verdict cache
    4. Manage tool registry
    """
    
    def __init__(
        self,
        identity_validator: Optional[IdentityValidator] = None,
        signal_analyzer: Optional[SignalAnalyzer] = None,
        cognitive_validator: Optional[CognitiveValidator] = None,
    ) -> None:
        self.identity = identity_validator or IdentityValidator()
        self.signal = signal_analyzer or SignalAnalyzer()
        self.cognitive = cognitive_validator or CognitiveValidator()
        
        # Tool registry (synced to eBPF)
        self.tool_registry: Dict[int, ToolRegistryEntry] = {}
        
        # Pending escrow items
        self.pending: Dict[str, EscrowEvent] = {}
        
        # Verdict cache (mirrors eBPF verdict_cache)
        self.verdict_cache: Dict[int, ActionVerdict] = {}
        
        # Event handlers
        self._event_handlers: List[Callable] = []
        
        # Running flag
        self._running = False
        
    def register_tool(self, entry: ToolRegistryEntry) -> None:
        """Register a tool in the registry."""
        self.tool_registry[entry.tool_id_hash] = entry
        logger.info(f"Registered tool: {entry.tool_id} (hash={entry.tool_id_hash})")
    
    def add_event_handler(self, handler: Callable) -> None:
        """Add handler for escrow events."""
        self._event_handlers.append(handler)
    
    async def process_escrow_event(self, event: EscrowEvent) -> TriFactorGateResult:
        """
        Process an escrow event through the Tri-Factor Gate.
        
        This is the core orchestration logic.
        """
        transaction_id = f"tx-{event.pid}-{event.timestamp}"
        logger.info(f"Processing escrow event: {transaction_id} (class={event.action_class})")
        
        # Store pending
        self.pending[transaction_id] = event
        
        try:
            # Run all three validations in parallel
            identity_task = self.identity.verify(
                pid=event.pid,
                binary_hash=event.binary_hash,
                tenant_id=event.tenant_id,
                trust_level=event.trust_level,
                entitlements=event.present_entitlements,
            )
            
            signal_task = self.signal.analyze(
                payload_hex="",  # Would be extracted from packet
                tenant_id=str(event.tenant_id),
            )
            
            # Get tool info for cognitive audit
            tool_id = self._get_tool_id(event.tool_id_hash)
            cognitive_task = self.cognitive.audit(
                transaction_id=transaction_id,
                tenant_id=str(event.tenant_id),
                agent_id=f"agent-{event.pid}",
                tool_id=tool_id,
                payload={},
                entitlements=self._entitlements_to_list(event.present_entitlements),
            )
            
            # Await all validations
            identity_result, signal_result, cognitive_result = await asyncio.gather(
                identity_task, signal_task, cognitive_task
            )
            
            # Determine final verdict
            identity_passed = identity_result.get("passed", False)
            signal_passed = signal_result.get("passed", True)  # Fail-open
            cognitive_passed = cognitive_result.get("passed", False)
            
            all_passed = identity_passed and signal_passed and cognitive_passed
            
            if all_passed:
                final_verdict = ActionVerdict.ALLOW
                reasoning = "Tri-Factor Gate: All validations passed"
            elif not identity_passed:
                final_verdict = ActionVerdict.BLOCK
                reasoning = f"Identity failed: {identity_result.get('reason')}"
            elif not cognitive_passed:
                # Cognitive failure might be recoverable with HITL
                cognitive_verdict = cognitive_result.get("verdict", "HOLD")
                if cognitive_verdict == "BLOCK":
                    final_verdict = ActionVerdict.BLOCK
                else:
                    final_verdict = ActionVerdict.HOLD
                reasoning = f"Cognitive: {cognitive_result.get('reason')}"
            else:
                final_verdict = ActionVerdict.BLOCK
                reasoning = f"Signal failed: {signal_result.get('reason')}"
            
            result = TriFactorGateResult(
                transaction_id=transaction_id,
                identity_passed=identity_passed,
                signal_passed=signal_passed,
                cognitive_passed=cognitive_passed,
                all_passed=all_passed,
                final_verdict=final_verdict,
                trust_level=cognitive_result.get("trust_level", 0.5),
                reasoning=reasoning,
            )
            
            # Update verdict cache
            self.verdict_cache[event.pid] = final_verdict
            
            # In production: update eBPF verdict_cache map
            await self._update_ebpf_verdict(event.pid, final_verdict)
            
            logger.info(
                f"Tri-Factor Gate complete: {transaction_id} -> {final_verdict.name} "
                f"(identity={identity_passed}, signal={signal_passed}, cognitive={cognitive_passed})"
            )
            
            # Notify handlers
            for handler in self._event_handlers:
                try:
                    await handler(result)
                except Exception as e:
                    logger.error(f"Event handler error: {e}")
            
            return result
            
        finally:
            # Clean up pending
            self.pending.pop(transaction_id, None)
    
    async def _update_ebpf_verdict(self, pid: int, verdict: ActionVerdict) -> None:
        """
        Update eBPF verdict_cache map.
        
        In production, this uses BCC to update the map:
        ```python
        from bcc import BPF
        bpf = BPF(src_file="interceptor.bpf.c")
        verdict_cache = bpf.get_table("verdict_cache")
        verdict_cache[c_uint(pid)] = c_uint(verdict)
        ```
        """
        # Mock implementation - log the update
        logger.info(f"[eBPF] verdict_cache[{pid}] = {verdict.name}")
    
    def _get_tool_id(self, tool_id_hash: int) -> str:
        """Get tool ID from hash."""
        entry = self.tool_registry.get(tool_id_hash)
        return entry.tool_id if entry else f"unknown-{tool_id_hash}"
    
    def _entitlements_to_list(self, bitmask: int) -> List[str]:
        """Convert entitlement bitmask to list of strings."""
        # In production, this would decode the bitmask
        entitlements = []
        if bitmask & 0x01:
            entitlements.append("data:read")
        if bitmask & 0x02:
            entitlements.append("data:write")
        if bitmask & 0x04:
            entitlements.append("data:delete")
        if bitmask & 0x08:
            entitlements.append("finance:read")
        if bitmask & 0x10:
            entitlements.append("finance:write")
        if bitmask & 0x20:
            entitlements.append("admin:read")
        if bitmask & 0x40:
            entitlements.append("admin:write")
        return entitlements
    
    async def start(self) -> None:
        """Start the control plane."""
        self._running = True
        logger.info("AOCS Control Plane started")
        
        # In production, this would:
        # 1. Load eBPF program
        # 2. Attach to LSM hooks
        # 3. Poll ring buffers for events
        
    async def stop(self) -> None:
        """Stop the control plane."""
        self._running = False
        logger.info("AOCS Control Plane stopped")


# ============================================================================
# BCC INTEGRATION (Production)
# ============================================================================

class BCCControlPlane(AOCSControlPlane):
    """
    BCC-based control plane for production use.
    
    Uses BPF Compiler Collection to:
    1. Load eBPF programs
    2. Attach to LSM hooks
    3. Read from ring buffers
    4. Update BPF maps
    """
    
    def __init__(self, ebpf_source: str = "interceptor.bpf.c") -> None:
        super().__init__()
        self.ebpf_source = ebpf_source
        self._bpf = None
    
    async def start(self) -> None:
        """Start BCC-based control plane."""
        self._running = True
        logger.info("BCC Control Plane starting...")
        
        try:
            # Import BCC (only available on Linux with BCC installed)
            from bcc import BPF
            
            # Load eBPF program
            self._bpf = BPF(src_file=self.ebpf_source)
            
            # Get ring buffer
            escrow_events = self._bpf["escrow_events"]
            
            # Set up callback
            def handle_event(cpu, data, size) -> None:
                event = self._parse_escrow_event(data)
                asyncio.create_task(self.process_escrow_event(event))
            
            escrow_events.open_ring_buffer(handle_event)
            
            logger.info("BCC Control Plane started - listening for escrow events")
            
            # Poll loop
            while self._running:
                self._bpf.ring_buffer_poll(timeout=100)
                await asyncio.sleep(0.01)
                
        except ImportError:
            logger.warning("BCC not available - using mock control plane")
            await super().start()
    
    def _parse_escrow_event(self, data: bytes) -> EscrowEvent:
        """Parse raw bytes from ring buffer into EscrowEvent."""
        # Struct format matches escrow_event in eBPF
        # u32 pid, tid; u64 cgroup_id, timestamp, tool_id_hash; ...
        fmt = "IIQQQIIQIIQQIIb"
        values = struct.unpack(fmt, data[:struct.calcsize(fmt)])
        
        return EscrowEvent(
            pid=values[0],
            tid=values[1],
            cgroup_id=values[2],
            timestamp=values[3],
            tool_id_hash=values[4],
            action_class=values[5],
            tenant_id=values[6],
            binary_hash=values[7],
            trust_level=values[8],
            reversibility_index=values[9],
            required_entitlements=values[10],
            present_entitlements=values[11],
            entitlement_valid=values[12],
            data_size=values[13],
            verdict=values[14],
        )
    
    async def _update_ebpf_verdict(self, pid: int, verdict: ActionVerdict) -> None:
        """Update eBPF verdict_cache map via BCC."""
        if self._bpf:
            from ctypes import c_uint
            verdict_cache = self._bpf.get_table("verdict_cache")
            verdict_cache[c_uint(pid)] = c_uint(verdict)
        await super()._update_ebpf_verdict(pid, verdict)


# ============================================================================
# FASTAPI ROUTER
# ============================================================================

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# Global control plane instance
_control_plane = AOCSControlPlane()


class SimulateEscrowRequest(BaseModel):
    """Request to simulate an escrow event for testing"""
    pid: int
    tool_id: str
    action_class: int = 1  # CLASS_B
    trust_level: int = 65
    entitlements: int = 0x1F


class SimulateEscrowResponse(BaseModel):
    """Response from simulated escrow event"""
    transaction_id: str
    final_verdict: str
    identity_passed: bool
    signal_passed: bool
    cognitive_passed: bool
    trust_level: float
    reasoning: str


@router.post("/simulate", response_model=SimulateEscrowResponse)
async def simulate_escrow_event(req: SimulateEscrowRequest) -> Any:
    """Simulate an escrow event for testing the Tri-Factor Gate."""
    import hashlib
    
    # Create mock event
    tool_hash = int(hashlib.sha256(req.tool_id.encode()).hexdigest()[:16], 16)
    
    event = EscrowEvent(
        pid=req.pid,
        tid=req.pid,
        cgroup_id=0,
        timestamp=int(time.time() * 1e9),
        tool_id_hash=tool_hash,
        action_class=req.action_class,
        tenant_id=1,
        binary_hash=12345678,
        trust_level=req.trust_level,
        reversibility_index=5 if req.action_class == 1 else 100,
        required_entitlements=0,
        present_entitlements=req.entitlements,
        entitlement_valid=1,
        data_size=1024,
        verdict=0,
    )
    
    result = await _control_plane.process_escrow_event(event)
    
    return SimulateEscrowResponse(
        transaction_id=result.transaction_id,
        final_verdict=result.final_verdict.name,
        identity_passed=result.identity_passed,
        signal_passed=result.signal_passed,
        cognitive_passed=result.cognitive_passed,
        trust_level=result.trust_level,
        reasoning=result.reasoning,
    )


@router.get("/status")
async def control_plane_status() -> dict:
    """Get control plane status."""
    return {
        "running": _control_plane._running,
        "pending_events": len(_control_plane.pending),
        "registered_tools": len(_control_plane.tool_registry),
        "cached_verdicts": len(_control_plane.verdict_cache),
    }
