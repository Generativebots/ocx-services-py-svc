"""
Trust Registry — Ghost State Engine unit tests.

Tests the GhostStateEngine and GhostStateEscrowGate directly
(no HTTP, pure unit tests on the engine classes).
"""

import pytest
import sys
import os
from unittest.mock import MagicMock

# Ensure conftest stubs are loaded
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestStateSnapshot:
    """StateSnapshot dataclass tests."""

    def test_clone_is_deep_copy(self):
        from ghost_state_engine import StateSnapshot

        state = StateSnapshot(
            agent_balance=1000.0,
            account_balances={"checking": 5000.0},
            data_locations={"doc1": "vpc"},
            pending_approvals={},
            timestamp=1234567890.0,
        )
        clone = state.clone()

        # Mutating clone should not affect original
        clone.account_balances["checking"] = 0
        assert state.account_balances["checking"] == 5000.0

    def test_clone_preserves_values(self):
        from ghost_state_engine import StateSnapshot

        state = StateSnapshot(
            agent_balance=500.0,
            account_balances={"a": 100.0, "b": 200.0},
            data_locations={},
            pending_approvals={"x": ["y"]},
            timestamp=99.0,
        )
        clone = state.clone()
        assert clone.agent_balance == 500.0
        assert clone.account_balances == {"a": 100.0, "b": 200.0}
        assert clone.pending_approvals == {"x": ["y"]}


class TestGhostStateEngine:
    """GhostStateEngine speculative evaluation tests."""

    def _make_state(self, checking=5000.0, agent_balance=10000.0):
        from ghost_state_engine import StateSnapshot
        return StateSnapshot(
            agent_balance=agent_balance,
            account_balances={"checking": checking},
            data_locations={"customer_data": "vpc"},
            pending_approvals={},
            timestamp=1234567890.0,
        )

    def test_payment_within_balance(self):
        """Payment that keeps balance above policy → allowed."""
        from ghost_state_engine import GhostStateEngine

        engine = GhostStateEngine()
        state = self._make_state(checking=5000.0)

        # Policy: balance must NOT drop below 1000
        policy = {"<": [{"var": "account_balances.checking"}, 1000]}
        allowed, ghost, reason = engine.evaluate_with_ghost_state(
            current_state=state,
            tool_name="execute_payment",
            tool_args={"amount": 500, "from_account": "checking"},
            policy_logic=policy,
        )
        assert allowed is True
        assert reason is None

    def test_payment_violates_balance_policy(self):
        """Payment that drops balance below threshold → blocked."""
        from ghost_state_engine import GhostStateEngine

        engine = GhostStateEngine()
        state = self._make_state(checking=5000.0)

        policy = {"<": [{"var": "account_balances.checking"}, 1000]}
        allowed, ghost, reason = engine.evaluate_with_ghost_state(
            current_state=state,
            tool_name="execute_payment",
            tool_args={"amount": 4500, "from_account": "checking"},
            policy_logic=policy,
        )
        # checking goes to 500, which IS < 1000, so policy fires → blocked
        assert allowed is False
        assert ghost is not None
        assert ghost.account_balances["checking"] == 500.0
        assert "violation" in reason.lower()

    def test_unknown_tool_fails_open(self):
        """Tool without simulator → allowed (fail-open with warning)."""
        from ghost_state_engine import GhostStateEngine

        engine = GhostStateEngine()
        state = self._make_state()

        policy = {"<": [{"var": "account_balances.checking"}, 0]}
        allowed, ghost, reason = engine.evaluate_with_ghost_state(
            current_state=state,
            tool_name="unknown_tool_xyz",
            tool_args={},
            policy_logic=policy,
        )
        assert allowed is True
        assert ghost is None

    def test_external_request_marks_data_location(self):
        """External request simulator moves data to 'external'."""
        from ghost_state_engine import GhostStateEngine

        engine = GhostStateEngine()
        state = self._make_state()

        # Just run the simulator directly
        engine._simulate_external_request(state, {"data_id": "customer_data"})
        assert state.data_locations["customer_data"] == "external"

    def test_transfer_funds_between_accounts(self):
        """Transfer simulator moves funds correctly."""
        from ghost_state_engine import GhostStateEngine

        engine = GhostStateEngine()
        state = self._make_state(checking=5000.0)
        state.account_balances["savings"] = 10000.0

        engine._simulate_transfer(state, {
            "amount": 2000,
            "from_account": "checking",
            "to_account": "savings",
        })
        assert state.account_balances["checking"] == 3000.0
        assert state.account_balances["savings"] == 12000.0

    def test_transfer_creates_new_account(self):
        """Transfer to non-existent account creates it."""
        from ghost_state_engine import GhostStateEngine

        engine = GhostStateEngine()
        state = self._make_state(checking=5000.0)

        engine._simulate_transfer(state, {
            "amount": 1000,
            "from_account": "checking",
            "to_account": "new_account",
        })
        assert state.account_balances["new_account"] == 1000.0

    def test_payment_deducts_governance_tax(self):
        """Payment simulator charges 1% governance tax on agent balance."""
        from ghost_state_engine import GhostStateEngine

        engine = GhostStateEngine()
        state = self._make_state(checking=5000.0, agent_balance=10000.0)

        engine._simulate_payment(state, {"amount": 1000, "from_account": "checking"})
        assert state.account_balances["checking"] == 4000.0
        # 1% of 1000 = 10 governance tax
        assert state.agent_balance == 9990.0


class TestGhostStateEscrowGate:
    """GhostStateEscrowGate integration tests."""

    def _make_state(self, checking=5000.0):
        from ghost_state_engine import StateSnapshot
        return StateSnapshot(
            agent_balance=10000.0,
            account_balances={"checking": checking},
            data_locations={},
            pending_approvals={},
            timestamp=0.0,
        )

    def test_all_policies_pass(self):
        """All policies satisfied → ALLOW."""
        from ghost_state_engine import GhostStateEngine, GhostStateEscrowGate

        engine = GhostStateEngine()
        gate = GhostStateEscrowGate(engine)
        state = self._make_state(checking=5000.0)

        policies = [{
            "logic": {"<": [{"var": "account_balances.checking"}, 0]},
            "action": {"on_fail": "BLOCK"},
        }]

        allowed, action = gate.evaluate_with_projection(
            current_state=state,
            tool_name="execute_payment",
            tool_args={"amount": 100, "from_account": "checking"},
            policies=policies,
        )
        assert allowed is True
        assert action == "ALLOW"

    def test_policy_violation_blocks(self):
        """Policy violation → BLOCK."""
        from ghost_state_engine import GhostStateEngine, GhostStateEscrowGate

        engine = GhostStateEngine()
        gate = GhostStateEscrowGate(engine)
        state = self._make_state(checking=1500.0)

        policies = [{
            "logic": {"<": [{"var": "account_balances.checking"}, 1000]},
            "action": {"on_fail": "BLOCK"},
        }]

        allowed, action = gate.evaluate_with_projection(
            current_state=state,
            tool_name="execute_payment",
            tool_args={"amount": 600, "from_account": "checking"},
            policies=policies,
        )
        assert allowed is False
        assert action == "BLOCK"

    def test_sandbox_health_no_client(self):
        """Without sandbox client, health returns unavailable."""
        from ghost_state_engine import GhostStateEngine, GhostStateEscrowGate

        engine = GhostStateEngine()
        gate = GhostStateEscrowGate(engine, sandbox_client=None)

        health = gate.get_sandbox_health()
        assert health["available"] is False


class TestGhostStateEngineEdgeCases:
    """Cover remaining uncovered lines in ghost_state_engine.py."""

    def test_register_custom_simulator(self):
        """register_simulator adds custom simulator (L63-65)."""
        from ghost_state_engine import GhostStateEngine

        engine = GhostStateEngine()
        custom = MagicMock()
        engine.register_simulator("custom_tool", custom)
        assert "custom_tool" in engine.state_simulators

    def test_simulation_failure_blocks(self):
        """Simulator raising exception → fail-closed (L97-99)."""
        from ghost_state_engine import GhostStateEngine, StateSnapshot

        engine = GhostStateEngine()
        engine.register_simulator("bad_tool", lambda s, a: (_ for _ in ()).throw(ValueError("boom")))

        state = StateSnapshot(
            agent_balance=100.0,
            account_balances={},
            data_locations={},
            pending_approvals={},
            timestamp=0.0,
        )
        # register a simulator that raises
        def bad_sim(state, args):
            raise ValueError("sim crash")
        engine.state_simulators["bad_tool"] = bad_sim

        allowed, ghost, reason = engine.evaluate_with_ghost_state(
            state, "bad_tool", {}, {"<": [{"var": "agent_balance"}, 0]}
        )
        assert allowed is False
        assert "Simulation failed" in reason

    def test_nested_value_non_dict_path(self):
        """_get_nested_value returns None for non-dict intermediate (L151)."""
        from ghost_state_engine import GhostStateEngine

        engine = GhostStateEngine()
        result = engine._get_nested_value({"a": "string_val"}, "a.b.c")
        assert result is None

    def test_message_simulator_no_state_change(self):
        """Message simulator doesn't change state (L192-199)."""
        from ghost_state_engine import GhostStateEngine, StateSnapshot

        engine = GhostStateEngine()
        state = StateSnapshot(
            agent_balance=100.0,
            account_balances={"acc": 500.0},
            data_locations={},
            pending_approvals={},
            timestamp=0.0,
        )
        original_balance = state.agent_balance
        engine._simulate_message(state, {"content": "hello", "channel": "public"})
        assert state.agent_balance == original_balance

    def test_external_request_no_data_id(self):
        """External request without data_id doesn't crash."""
        from ghost_state_engine import GhostStateEngine, StateSnapshot

        engine = GhostStateEngine()
        state = StateSnapshot(
            agent_balance=100.0, account_balances={},
            data_locations={}, pending_approvals={}, timestamp=0.0,
        )
        engine._simulate_external_request(state, {"destination": "https://example.com"})
        assert state.data_locations == {}




class TestGhostStateEscrowGateExtended:
    """Cover sandbox client integration paths (L248-264, 268-272)."""

    def test_sandbox_client_allows(self):
        """Sandbox client returns ALLOW → gate allows."""
        from ghost_state_engine import GhostStateEngine, GhostStateEscrowGate, StateSnapshot

        engine = GhostStateEngine()
        mock_sandbox = MagicMock()
        mock_sandbox.trigger_speculative_execution.return_value = {
            "verdict": "ALLOW", "speculative_hash": "abc123"
        }

        gate = GhostStateEscrowGate(engine, sandbox_client=mock_sandbox)
        state = StateSnapshot(
            agent_balance=10000.0,
            account_balances={"checking": 5000.0},
            data_locations={}, pending_approvals={}, timestamp=0.0,
        )

        policies = [{"logic": {"<": [{"var": "account_balances.checking"}, 0]}, "action": {"on_fail": "BLOCK"}}]
        allowed, action = gate.evaluate_with_projection(
            state, "execute_payment",
            {"amount": 100, "from_account": "checking"},
            policies, agent_id="a1", tenant_id="t1",
        )
        assert allowed is True
        assert action == "ALLOW"

    def test_sandbox_client_blocks(self):
        """Sandbox client returns BLOCK → gate blocks."""
        from ghost_state_engine import GhostStateEngine, GhostStateEscrowGate, StateSnapshot

        engine = GhostStateEngine()
        mock_sandbox = MagicMock()
        mock_sandbox.trigger_speculative_execution.return_value = {
            "verdict": "BLOCK", "reason": "suspicious syscall"
        }

        gate = GhostStateEscrowGate(engine, sandbox_client=mock_sandbox)
        state = StateSnapshot(
            agent_balance=10000.0,
            account_balances={"checking": 5000.0},
            data_locations={}, pending_approvals={}, timestamp=0.0,
        )

        policies = [{"logic": {"<": [{"var": "account_balances.checking"}, 0]}, "action": {"on_fail": "BLOCK"}}]
        allowed, action = gate.evaluate_with_projection(
            state, "execute_payment",
            {"amount": 100, "from_account": "checking"},
            policies, agent_id="a1", tenant_id="t1",
        )
        assert allowed is False
        assert action == "BLOCK"

    def test_sandbox_health_with_client(self):
        """With sandbox client configured, returns its status."""
        from ghost_state_engine import GhostStateEngine, GhostStateEscrowGate

        engine = GhostStateEngine()
        mock_sandbox = MagicMock()
        mock_sandbox.get_sandbox_status.return_value = {"available": True, "runtime": "gVisor"}

        gate = GhostStateEscrowGate(engine, sandbox_client=mock_sandbox)
        health = gate.get_sandbox_health()
        assert health["available"] is True


# ============================================================================
# governance_config.py — missing lines: 126-130 (_get_supabase_client),
#                        139-151 (_load_from_supabase), 173, 185-188, 198-199, 204
# ============================================================================


