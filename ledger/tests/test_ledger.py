"""Tests for ledger service — avoids qrcode dependency"""
import pytest
from unittest.mock import patch, MagicMock

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# Mock qrcode before importing modules that depend on it
sys.modules['qrcode'] = MagicMock()

from immutable_ledger import ImmutableGovernanceLedger


class TestImmutableGovernanceLedger:
    def test_init_no_client(self):
        ledger = ImmutableGovernanceLedger()
        assert ledger is not None

    def test_init_with_client(self):
        ledger = ImmutableGovernanceLedger(supabase_client=MagicMock())
        assert ledger is not None

    def test_record_event(self):
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        mock_client.table.return_value.insert.return_value.execute.return_value.data = [{"id": "1"}]
        ledger = ImmutableGovernanceLedger(supabase_client=mock_client)
        event = {
            "transaction_id": "tx-1",
            "tenant_id": "acme",
            "agent_id": "agent-1",
            "action": "payment",
            "verdict": "ALLOW",
        }
        result = ledger.record_event(event)
        assert result is not None

    def test_calculate_hash(self):
        ledger = ImmutableGovernanceLedger()
        entry = {"transaction_id": "tx-1", "data": "test"}
        hash_val = ledger.calculate_hash(entry)
        assert isinstance(hash_val, str)
        assert len(hash_val) > 0

    def test_calculate_hash_deterministic(self):
        ledger = ImmutableGovernanceLedger()
        entry = {"key": "value"}
        h1 = ledger.calculate_hash(entry)
        h2 = ledger.calculate_hash(entry)
        assert h1 == h2

    def test_calculate_hash_different_entries(self):
        ledger = ImmutableGovernanceLedger()
        h1 = ledger.calculate_hash({"a": 1})
        h2 = ledger.calculate_hash({"b": 2})
        assert h1 != h2

    def test_has_verify_chain(self):
        ledger = ImmutableGovernanceLedger()
        assert hasattr(ledger, "verify_chain")

    def test_has_get_event(self):
        ledger = ImmutableGovernanceLedger()
        assert hasattr(ledger, "get_event")

    def test_has_get_agent_trail(self):
        ledger = ImmutableGovernanceLedger()
        assert hasattr(ledger, "get_agent_trail")
