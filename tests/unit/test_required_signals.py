"""Tests for required_signals.py"""
import sys, os, time, unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from required_signals import (
    Signal, SignalType, SignalCollector, CTOSignatureVerifier,
    JuryEntropyChecker, enforce_with_signals
)


class TestSignal(unittest.TestCase):
    def test_not_expired_no_expiry(self):
        s = Signal(signal_type=SignalType.CTO_SIGNATURE, value="sig", timestamp=time.time())
        self.assertFalse(s.is_expired())
        self.assertTrue(s.is_valid())

    def test_expired(self):
        s = Signal(signal_type=SignalType.CTO_SIGNATURE, value="sig",
                   timestamp=time.time() - 100, expires_at=time.time() - 1)
        self.assertTrue(s.is_expired())
        self.assertFalse(s.is_valid())

    def test_not_yet_expired(self):
        s = Signal(signal_type=SignalType.CTO_SIGNATURE, value="sig",
                   timestamp=time.time(), expires_at=time.time() + 3600)
        self.assertFalse(s.is_expired())
        self.assertTrue(s.is_valid())


class TestSignalCollector(unittest.TestCase):
    def setUp(self):
        self.collector = SignalCollector()

    def test_add_signal(self):
        self.assertTrue(self.collector.add_signal("tx1", SignalType.CTO_SIGNATURE, "sig"))
        self.assertEqual(len(self.collector.get_signals("tx1")), 1)

    def test_add_signal_with_ttl(self):
        self.collector.add_signal("tx2", SignalType.HUMAN_APPROVAL, "yes", ttl_seconds=60)
        sigs = self.collector.get_signals("tx2")
        self.assertIsNotNone(sigs[0].expires_at)

    def test_verify_all_present(self):
        self.collector.add_signal("tx3", SignalType.CTO_SIGNATURE, "sig")
        self.collector.add_signal("tx3", SignalType.JURY_ENTROPY_CHECK, "pass")
        valid, missing = self.collector.verify_signals("tx3", ["CTO_SIGNATURE", "JURY_ENTROPY_CHECK"])
        self.assertTrue(valid)
        self.assertEqual(missing, [])

    def test_verify_missing_signal(self):
        self.collector.add_signal("tx4", SignalType.CTO_SIGNATURE, "sig")
        valid, missing = self.collector.verify_signals("tx4", ["CTO_SIGNATURE", "JURY_ENTROPY_CHECK"])
        self.assertFalse(valid)
        self.assertIn("JURY_ENTROPY_CHECK", missing)

    def test_verify_unknown_transaction(self):
        valid, missing = self.collector.verify_signals("unknown", ["CTO_SIGNATURE"])
        self.assertFalse(valid)
        self.assertEqual(missing, ["CTO_SIGNATURE"])

    def test_get_signals_empty(self):
        self.assertEqual(self.collector.get_signals("nope"), [])

    def test_cleanup_expired(self):
        self.collector.add_signal("tx5", SignalType.CTO_SIGNATURE, "sig", ttl_seconds=-1)
        # Give a moment for the time to pass
        removed = self.collector.cleanup_expired()
        self.assertGreaterEqual(removed, 1)
        self.assertEqual(self.collector.get_signals("tx5"), [])

    def test_cleanup_keeps_valid(self):
        self.collector.add_signal("tx6", SignalType.CTO_SIGNATURE, "sig", ttl_seconds=3600)
        removed = self.collector.cleanup_expired()
        self.assertEqual(removed, 0)
        self.assertEqual(len(self.collector.get_signals("tx6")), 1)


class TestCTOSignatureVerifier(unittest.TestCase):
    def setUp(self):
        self.verifier = CTOSignatureVerifier("test_pk_123")

    def test_create_and_verify_signature(self):
        data = {"amount": 10000, "vendor": "ACME"}
        sig = self.verifier.create_signature(data)
        self.assertTrue(self.verifier.verify_signature(data, sig))

    def test_invalid_signature(self):
        data = {"amount": 10000, "vendor": "ACME"}
        self.assertFalse(self.verifier.verify_signature(data, "invalid_sig"))

    def test_different_data_different_sig(self):
        d1 = {"amount": 100}
        d2 = {"amount": 200}
        s1 = self.verifier.create_signature(d1)
        s2 = self.verifier.create_signature(d2)
        self.assertNotEqual(s1, s2)


class TestJuryEntropyChecker(unittest.TestCase):
    def test_both_pass(self):
        jury = MagicMock()
        entropy = MagicMock()
        jury.EvaluateAction.return_value = (True, None)
        entropy.CheckEntropy.return_value = (True, None)
        checker = JuryEntropyChecker(jury, entropy)
        passed, details = checker.check_jury_entropy("agent1", "action", {"key": "val"})
        self.assertTrue(passed)
        self.assertTrue(details["jury_passed"])
        self.assertTrue(details["entropy_passed"])

    def test_jury_fails(self):
        jury = MagicMock()
        entropy = MagicMock()
        jury.EvaluateAction.return_value = (False, "low score")
        entropy.CheckEntropy.return_value = (True, None)
        checker = JuryEntropyChecker(jury, entropy)
        passed, details = checker.check_jury_entropy("agent1", "action", {})
        self.assertFalse(passed)

    def test_entropy_fails(self):
        jury = MagicMock()
        entropy = MagicMock()
        jury.EvaluateAction.return_value = (True, None)
        entropy.CheckEntropy.return_value = (False, "high entropy")
        checker = JuryEntropyChecker(jury, entropy)
        passed, details = checker.check_jury_entropy("agent1", "action", {})
        self.assertFalse(passed)


class TestEnforceWithSignals(unittest.TestCase):
    def test_allowed(self):
        c = SignalCollector()
        c.add_signal("tx", SignalType.CTO_SIGNATURE, "s")
        allowed, action = enforce_with_signals("tx", ["CTO_SIGNATURE"], c)
        self.assertTrue(allowed)
        self.assertEqual(action, "ALLOW")

    def test_blocked(self):
        c = SignalCollector()
        allowed, action = enforce_with_signals("tx", ["CTO_SIGNATURE"], c)
        self.assertFalse(allowed)
        self.assertIn("BLOCK", action)


if __name__ == "__main__":
    unittest.main()


class TestRequiredSignals:

    def test_signal_not_expired(self):
        from required_signals import Signal, SignalType
        s = Signal(SignalType.CTO_SIGNATURE, "val", time.time(), expires_at=time.time() + 1000)
        assert s.is_expired() is False
        assert s.is_valid() is True

    def test_signal_expired(self):
        from required_signals import Signal, SignalType
        s = Signal(SignalType.CTO_SIGNATURE, "val", time.time(), expires_at=time.time() - 10)
        assert s.is_expired() is True
        assert s.is_valid() is False

    def test_signal_no_expiry(self):
        from required_signals import Signal, SignalType
        s = Signal(SignalType.HUMAN_APPROVAL, "val", time.time())
        assert s.is_expired() is False

    def test_add_signal(self):
        from required_signals import SignalCollector, SignalType
        c = SignalCollector()
        assert c.add_signal("tx1", SignalType.CTO_SIGNATURE, "sig") is True
        assert len(c.get_signals("tx1")) == 1

    def test_add_signal_with_ttl(self):
        from required_signals import SignalCollector, SignalType
        c = SignalCollector()
        c.add_signal("tx1", SignalType.CTO_SIGNATURE, "sig", ttl_seconds=300)
        sig = c.get_signals("tx1")[0]
        assert sig.expires_at is not None

    def test_verify_signals_all_present(self):
        from required_signals import SignalCollector, SignalType
        c = SignalCollector()
        c.add_signal("tx1", SignalType.CTO_SIGNATURE, "sig")
        c.add_signal("tx1", SignalType.JURY_ENTROPY_CHECK, "ent")
        ok, missing = c.verify_signals("tx1", ["CTO_SIGNATURE", "JURY_ENTROPY_CHECK"])
        assert ok is True
        assert missing == []

    def test_verify_signals_missing(self):
        from required_signals import SignalCollector, SignalType
        c = SignalCollector()
        c.add_signal("tx1", SignalType.CTO_SIGNATURE, "sig")
        ok, missing = c.verify_signals("tx1", ["CTO_SIGNATURE", "JURY_ENTROPY_CHECK"])
        assert ok is False
        assert "JURY_ENTROPY_CHECK" in missing

    def test_verify_signals_unknown_tx(self):
        from required_signals import SignalCollector
        c = SignalCollector()
        ok, missing = c.verify_signals("unknown", ["CTO_SIGNATURE"])
        assert ok is False

    def test_cleanup_expired(self):
        from required_signals import SignalCollector, SignalType
        c = SignalCollector()
        c.add_signal("tx1", SignalType.CTO_SIGNATURE, "sig", ttl_seconds=-1)
        removed = c.cleanup_expired()
        assert removed >= 1
        assert c.get_signals("tx1") == []

    def test_cleanup_keeps_valid(self):
        from required_signals import SignalCollector, SignalType
        c = SignalCollector()
        c.add_signal("tx1", SignalType.CTO_SIGNATURE, "sig", ttl_seconds=9999)
        removed = c.cleanup_expired()
        assert removed == 0
        assert len(c.get_signals("tx1")) == 1

    def test_cto_signature_verify(self):
        from required_signals import CTOSignatureVerifier
        v = CTOSignatureVerifier("pubkey")
        data = {"amount": 100}
        sig = v.create_signature(data)
        assert v.verify_signature(data, sig) is True

    def test_cto_signature_verify_bad(self):
        from required_signals import CTOSignatureVerifier
        v = CTOSignatureVerifier("pubkey")
        assert v.verify_signature({"a": 1}, "bad_sig") is False

    def test_jury_entropy_checker(self):
        from required_signals import JuryEntropyChecker
        jury_client = MagicMock()
        jury_client.EvaluateAction.return_value = (True, None)
        entropy_monitor = MagicMock()
        entropy_monitor.CheckEntropy.return_value = (True, None)
        checker = JuryEntropyChecker(jury_client, entropy_monitor)
        passed, details = checker.check_jury_entropy("a1", "act", {"k": "v"})
        assert passed is True
        assert details["jury_passed"] is True

    def test_jury_entropy_checker_fails(self):
        from required_signals import JuryEntropyChecker
        jury_client = MagicMock()
        jury_client.EvaluateAction.return_value = (False, "err")
        entropy_monitor = MagicMock()
        entropy_monitor.CheckEntropy.return_value = (True, None)
        checker = JuryEntropyChecker(jury_client, entropy_monitor)
        passed, details = checker.check_jury_entropy("a1", "act", {})
        assert passed is False

    def test_enforce_with_signals(self):
        from required_signals import enforce_with_signals, SignalCollector, SignalType
        c = SignalCollector()
        c.add_signal("tx1", SignalType.CTO_SIGNATURE, "sig")
        ok, action = enforce_with_signals("tx1", ["CTO_SIGNATURE"], c)
        assert ok is True
        assert action == "ALLOW"

    def test_enforce_with_signals_block(self):
        from required_signals import enforce_with_signals, SignalCollector
        c = SignalCollector()
        ok, action = enforce_with_signals("tx1", ["CTO_SIGNATURE"], c)
        assert ok is False
        assert "BLOCK" in action


# ────────────────────── preapproved_lists.py ──────────────────────────────


