"""Tests for proto/ledger_service_impl.py — LedgerServiceImpl"""
import sys, os, unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from proto.ledger_service_impl import LedgerServiceImpl
from proto.ledger_pb2 import LedgerEntry, AuditFilter


class TestRecordEntry(unittest.TestCase):
    def setUp(self):
        self.svc = LedgerServiceImpl()
        self.ctx = MagicMock()

    def test_records_entry(self):
        entry = LedgerEntry(
            turn_id="t1", agent_id="a1", binary_hash="bh1",
            plan_id="p1", status=1, intent_hash="ih1", actual_hash="ah1"
        )
        resp = self.svc.RecordEntry(entry, self.ctx)
        self.assertTrue(resp.acknowledged)
        self.assertIsNotNone(resp.entry_id)

    def test_chain_continuity(self):
        entry1 = LedgerEntry(turn_id="t1", agent_id="a1", binary_hash="bh1",
                             plan_id="p1", status=1, intent_hash="", actual_hash="")
        entry2 = LedgerEntry(turn_id="t2", agent_id="a1", binary_hash="bh2",
                             plan_id="p2", status=2, intent_hash="", actual_hash="")
        self.svc.RecordEntry(entry1, self.ctx)
        self.svc.RecordEntry(entry2, self.ctx)
        chain = self.svc._chains["a1"]
        self.assertEqual(len(chain), 2)
        self.assertEqual(chain[0]["previous_hash"], "GENESIS")
        self.assertEqual(chain[1]["previous_hash"], chain[0]["block_hash"])

    def test_different_agents_independent_chains(self):
        entry_a = LedgerEntry(turn_id="t1", agent_id="a1", binary_hash="bh1",
                              plan_id="p1", status=1, intent_hash="", actual_hash="")
        entry_b = LedgerEntry(turn_id="t2", agent_id="b1", binary_hash="bh2",
                              plan_id="p2", status=1, intent_hash="", actual_hash="")
        self.svc.RecordEntry(entry_a, self.ctx)
        self.svc.RecordEntry(entry_b, self.ctx)
        self.assertEqual(len(self.svc._chains["a1"]), 1)
        self.assertEqual(len(self.svc._chains["b1"]), 1)


class TestStreamAuditLog(unittest.TestCase):
    def setUp(self):
        self.svc = LedgerServiceImpl()
        self.ctx = MagicMock()

    def test_stream_returns_entries(self):
        for i in range(3):
            entry = LedgerEntry(turn_id=f"t{i}", agent_id="a1", binary_hash=f"bh{i}",
                                plan_id=f"p{i}", status=i, intent_hash="", actual_hash="")
            self.svc.RecordEntry(entry, self.ctx)

        audit_filter = AuditFilter(agent_id="a1")
        entries = list(self.svc.StreamAuditLog(audit_filter, self.ctx))
        self.assertEqual(len(entries), 3)

    def test_stream_empty_for_unknown_agent(self):
        audit_filter = AuditFilter(agent_id="unknown")
        entries = list(self.svc.StreamAuditLog(audit_filter, self.ctx))
        self.assertEqual(len(entries), 0)


class TestComputeHash(unittest.TestCase):
    def setUp(self):
        self.svc = LedgerServiceImpl()

    def test_deterministic(self):
        entry = LedgerEntry(turn_id="t1", agent_id="a1", binary_hash="bh1",
                            plan_id="p1", status=1, intent_hash="ih1", actual_hash="ah1")
        h1 = self.svc._compute_hash(entry, "GENESIS")
        h2 = self.svc._compute_hash(entry, "GENESIS")
        self.assertEqual(h1, h2)

    def test_different_prev_hash(self):
        entry = LedgerEntry(turn_id="t1", agent_id="a1", binary_hash="bh1",
                            plan_id="p1", status=1, intent_hash="ih1", actual_hash="ah1")
        h1 = self.svc._compute_hash(entry, "GENESIS")
        h2 = self.svc._compute_hash(entry, "OTHER")
        self.assertNotEqual(h1, h2)


class TestVerifyChainIntegrity(unittest.TestCase):
    """Tests for LedgerServiceImpl.verify_chain_integrity (lines 117-140)."""

    def setUp(self):
        self.svc = LedgerServiceImpl()
        self.ctx = MagicMock()

    def test_empty_chain_is_valid(self):
        self.assertTrue(self.svc.verify_chain_integrity("no-such-agent"))

    def test_valid_chain_passes(self):
        for i in range(3):
            entry = LedgerEntry(
                turn_id=f"t{i}", agent_id="a1", binary_hash=f"bh{i}",
                plan_id=f"p{i}", status=i, intent_hash="", actual_hash=""
            )
            self.svc.RecordEntry(entry, self.ctx)
        self.assertTrue(self.svc.verify_chain_integrity("a1"))

    def test_tampered_chain_fails(self):
        for i in range(3):
            entry = LedgerEntry(
                turn_id=f"t{i}", agent_id="a1", binary_hash=f"bh{i}",
                plan_id=f"p{i}", status=i, intent_hash="", actual_hash=""
            )
            self.svc.RecordEntry(entry, self.ctx)
        # Tamper with the middle block's hash
        self.svc._chains["a1"][1]["block_hash"] = "TAMPERED"
        self.assertFalse(self.svc.verify_chain_integrity("a1"))


if __name__ == "__main__":
    unittest.main()
