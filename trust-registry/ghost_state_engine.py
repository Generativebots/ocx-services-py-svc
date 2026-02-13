"""
Ghost-State Evaluation Engine
Evaluates policies against projected state after tool execution
Integrated with Economic Barrier for speculative execution
"""

import copy
import json
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
from json_logic_engine import JSONLogicEngine
import logging
logger = logging.getLogger(__name__)



@dataclass
class StateSnapshot:
    """Represents a snapshot of system state"""
    agent_balance: float
    account_balances: Dict[str, float]
    data_locations: Dict[str, str]  # data_id -> location (vpc, external)
    pending_approvals: Dict[str, list]
    timestamp: float
    
    def clone(self) -> 'StateSnapshot':
        """Create a deep copy of the snapshot"""
        return StateSnapshot(
            agent_balance=self.agent_balance,
            account_balances=copy.deepcopy(self.account_balances),
            data_locations=copy.deepcopy(self.data_locations),
            pending_approvals=copy.deepcopy(self.pending_approvals),
            timestamp=self.timestamp
        )


class GhostStateEngine:
    """
    Evaluates policies against projected future state
    
    Flow:
    1. Capture current state snapshot
    2. Speculatively execute tool call
    3. Generate "Ghost State" (projected future)
    4. Evaluate policies against Ghost State
    5. If violation → BLOCK, else → ALLOW
    """
    
    def __init__(self) -> None:
        self.logic_engine = JSONLogicEngine()
        self.state_simulators: Dict[str, Callable] = {}
        self._register_default_simulators()
    
    def _register_default_simulators(self) -> None:
        """Register default state simulators for common tools"""
        self.state_simulators = {
            "execute_payment": self._simulate_payment,
            "send_external_request": self._simulate_external_request,
            "transfer_funds": self._simulate_transfer,
            "send_message": self._simulate_message,
        }
    
    def register_simulator(self, tool_name: str, simulator: Callable) -> None:
        """Register custom state simulator for a tool"""
        self.state_simulators[tool_name] = simulator
    
    def evaluate_with_ghost_state(
        self,
        current_state: StateSnapshot,
        tool_name: str,
        tool_args: Dict[str, Any],
        policy_logic: Dict[str, Any]
    ) -> tuple[bool, Optional[StateSnapshot], Optional[str]]:
        """
        Evaluate policy against Ghost State
        
        Args:
            current_state: Current system state
            tool_name: Tool to be executed
            tool_args: Arguments for tool
            policy_logic: JSON-Logic policy to evaluate
            
        Returns:
            (is_allowed, ghost_state, violation_reason)
        """
        # Get simulator for tool
        simulator = self.state_simulators.get(tool_name)
        if not simulator:
            # No simulator → fail-open (allow but log warning)
            print(f"⚠️  No simulator for tool: {tool_name}")
            return True, None, None
        
        # Create Ghost State
        ghost_state = current_state.clone()
        try:
            simulator(ghost_state, tool_args)
        except Exception as e:
            # Simulation failed → fail-closed (block)
            return False, None, f"Simulation failed: {e}"
        
        # Convert Ghost State to data dict for JSON-Logic
        ghost_data = self._state_to_data(ghost_state, tool_args)
        
        # Evaluate policy
        violates = self.logic_engine.evaluate(policy_logic, ghost_data)
        
        if violates:
            reason = self._generate_violation_reason(policy_logic, ghost_data)
            return False, ghost_state, reason
        
        return True, ghost_state, None
    
    def _state_to_data(
        self,
        state: StateSnapshot,
        tool_args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Convert StateSnapshot to data dict for JSON-Logic"""
        return {
            "agent_balance": state.agent_balance,
            "account_balances": state.account_balances,
            "data_locations": state.data_locations,
            "pending_approvals": state.pending_approvals,
            "payload": tool_args,  # Tool arguments
        }
    
    def _generate_violation_reason(
        self,
        logic: Dict[str, Any],
        data: Dict[str, Any]
    ) -> str:
        """Generate human-readable violation reason"""
        # Extract violated condition
        variables = self.logic_engine.extract_variables(logic)
        
        reason_parts = []
        for var in variables:
            value = self._get_nested_value(data, var)
            reason_parts.append(f"{var}={value}")
        
        return f"Policy violation: {', '.join(reason_parts)}"
    
    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """Get nested value from dict using dot notation"""
        keys = path.split('.')
        value = data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
        return value
    
    # --- State Simulators ---
    
    def _simulate_payment(self, state: StateSnapshot, args: Dict[str, Any]) -> None:
        """Simulate payment execution"""
        amount = args.get("amount", 0)
        from_account = args.get("from_account", "default")
        
        # Deduct from account
        if from_account in state.account_balances:
            state.account_balances[from_account] -= amount
        
        # Deduct from agent balance (governance tax)
        tax = amount * 0.01  # 1% tax
        state.agent_balance -= tax
    
    def _simulate_external_request(self, state: StateSnapshot, args: Dict[str, Any]) -> None:
        """Simulate external data request"""
        data_id = args.get("data_id")
        destination = args.get("destination")
        
        if data_id:
            # Mark data as moved to external
            state.data_locations[data_id] = "external"
    
    def _simulate_transfer(self, state: StateSnapshot, args: Dict[str, Any]) -> None:
        """Simulate fund transfer"""
        amount = args.get("amount", 0)
        from_account = args.get("from_account")
        to_account = args.get("to_account")
        
        if from_account in state.account_balances:
            state.account_balances[from_account] -= amount
        
        if to_account in state.account_balances:
            state.account_balances[to_account] += amount
        else:
            state.account_balances[to_account] = amount
    
    def _simulate_message(self, state: StateSnapshot, args: Dict[str, Any]) -> None:
        """Simulate message sending"""
        # Check for PII in message
        content = args.get("content", "")
        channel = args.get("channel", "private")
        
        # No state change for messages, but we can check content
        pass


# Integration with Economic Barrier
class GhostStateEscrowGate:
    """
    Extended Escrow Gate with Ghost-State evaluation
    Integrates with existing Economic Barrier and Go gVisor sandbox
    """
    
    def __init__(
        self,
        ghost_engine: GhostStateEngine,
        sandbox_client: "Optional[SandboxClient]" = None,
    ) -> None:
        self.ghost_engine = ghost_engine
        self.sandbox_client = sandbox_client  # Bridge to Go backend gVisor
    
    def evaluate_with_projection(
        self,
        current_state: StateSnapshot,
        tool_name: str,
        tool_args: Dict[str, Any],
        policies: list,
        agent_id: str = "",
        tenant_id: str = "",
    ) -> tuple[bool, Optional[str]]:
        """
        Evaluate all policies with Ghost-State projection.
        If policies pass and sandbox_client is configured, triggers real
        gVisor speculative execution in the Go backend.
        
        Returns:
            (is_allowed, action)
        """
        for policy in policies:
            is_allowed, ghost_state, reason = self.ghost_engine.evaluate_with_ghost_state(
                current_state=current_state,
                tool_name=tool_name,
                tool_args=tool_args,
                policy_logic=policy["logic"]
            )
            
            if not is_allowed:
                action = policy["action"].get("on_fail", "BLOCK")
                logger.warning("Ghost-State violation: %s", reason)
                return False, action
        
        # All policies passed — trigger real sandbox execution if available
        if self.sandbox_client is not None and agent_id:
            sandbox_result = self.sandbox_client.trigger_speculative_execution(
                tool_name=tool_name,
                agent_id=agent_id,
                tenant_id=tenant_id,
                arguments=tool_args,
            )
            verdict = sandbox_result.get("verdict", "ALLOW")
            if verdict == "BLOCK":
                reason = sandbox_result.get("reason", "Sandbox execution blocked")
                logger.warning("Sandbox execution blocked: %s", reason)
                return False, "BLOCK"
            logger.info(
                "Sandbox execution confirmed: verdict=%s hash=%s",
                verdict,
                sandbox_result.get("speculative_hash", ""),
            )
        
        return True, "ALLOW"

    def get_sandbox_health(self) -> Dict[str, Any]:
        """Query the Go backend for gVisor sandbox runtime status."""
        if self.sandbox_client is None:
            return {"available": False, "reason": "No sandbox client configured"}
        return self.sandbox_client.get_sandbox_status()


# Example usage
if __name__ == "__main__":
    # Create current state
    current_state = StateSnapshot(
        agent_balance=10000.0,
        account_balances={"checking": 5000.0, "savings": 10000.0},
        data_locations={"customer_data": "vpc"},
        pending_approvals={},
        timestamp=1234567890.0
    )
    
    # Create Ghost-State engine
    engine = GhostStateEngine()
    
    # Policy: Account balance must not drop below $1,000
    policy = {
        "logic": {"<": [{"var": "account_balances.checking"}, 1000]},
        "action": {"on_fail": "BLOCK", "on_pass": "ALLOW"}
    }
    
    # Test 1: Payment that would violate policy
    is_allowed, ghost_state, reason = engine.evaluate_with_ghost_state(
        current_state=current_state,
        tool_name="execute_payment",
        tool_args={"amount": 4500, "from_account": "checking"},
        policy_logic=policy["logic"]
    )
    
    print(f"Test 1: allowed={is_allowed}, reason={reason}")
    if ghost_state:
        print(f"  Ghost balance: ${ghost_state.account_balances['checking']}")
    
    # Test 2: Payment that would pass
    is_allowed, ghost_state, reason = engine.evaluate_with_ghost_state(
        current_state=current_state,
        tool_name="execute_payment",
        tool_args={"amount": 500, "from_account": "checking"},
        policy_logic=policy["logic"]
    )
    
    print(f"Test 2: allowed={is_allowed}, reason={reason}")
    if ghost_state:
        print(f"  Ghost balance: ${ghost_state.account_balances['checking']}")
