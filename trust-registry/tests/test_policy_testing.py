"""Tests for policy_testing.py — PolicyTestGenerator, PolicySimulator, RegressionTester"""
import sys, os, unittest
from unittest.mock import MagicMock, patch

# Mock external deps
sys.modules["json_logic"] = MagicMock()
sys.modules["policy_hierarchy"] = MagicMock()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from policy_testing import (
    TestCase, TestResult, PolicyTestGenerator, PolicySimulator, RegressionTester
)


class TestTestCaseDataclass(unittest.TestCase):
    def test_from_init(self):
        tc = TestCase(
            name="test", policy_id="P1",
            input_data={"x": 1}, expected_result=True,
            expected_action="ALLOW", description="desc"
        )
        self.assertEqual(tc.name, "test")
        self.assertTrue(tc.expected_result)


class TestTestResultDataclass(unittest.TestCase):
    def test_passed(self):
        tc = TestCase("t", "P1", {}, True, "ALLOW", "d")
        tr = TestResult(test_case=tc, actual_result=True, actual_action="ALLOW", passed=True)
        self.assertTrue(tr.passed)

    def test_failed_with_error(self):
        tc = TestCase("t", "P1", {}, True, "ALLOW", "d")
        tr = TestResult(test_case=tc, actual_result=False, actual_action="ERROR", passed=False, error="boom")
        self.assertFalse(tr.passed)
        self.assertEqual(tr.error, "boom")


class TestPolicyTestGenerator(unittest.TestCase):
    def setUp(self):
        self.gen = PolicyTestGenerator()
        self.gen.logic_engine = MagicMock()

    def test_generate_produces_cases(self):
        self.gen.logic_engine.extract_variables.return_value = ["amount"]
        policy = {
            "policy_id": "P1",
            "logic": {">": [{"var": "amount"}, 500]},
            "action": {"on_pass": "ALLOW", "on_fail": "BLOCK"}
        }
        cases = self.gen.generate_test_cases(policy)
        # Should produce positive, negative, and edge cases
        self.assertGreaterEqual(len(cases), 2)
        names = [c.name for c in cases]
        self.assertIn("P1_positive", names)
        self.assertIn("P1_negative", names)

    def test_positive_case_low_amount(self):
        data = self.gen._generate_positive_case({}, ["amount"])
        self.assertEqual(data["amount"], 100)

    def test_negative_case_high_amount(self):
        data = self.gen._generate_negative_case({}, ["amount"])
        self.assertEqual(data["amount"], 10000)

    def test_edge_cases_boundaries(self):
        edges = self.gen._generate_edge_cases({}, ["amount"])
        self.assertEqual(len(edges), 3)  # 500, 501, 499

    def test_non_amount_variables(self):
        data = self.gen._generate_positive_case({}, ["vendor_id"])
        self.assertEqual(data["vendor_id"], "APPROVED_VENDOR")

    def test_generic_variable(self):
        data = self.gen._generate_positive_case({}, ["foo"])
        self.assertEqual(data["foo"], "safe_value")


class TestPolicySimulator(unittest.TestCase):
    def setUp(self):
        self.sim = PolicySimulator()
        self.sim.logic_engine = MagicMock()

    def test_run_test_passes(self):
        self.sim.logic_engine.evaluate.return_value = False  # no violation
        tc = TestCase("t", "P1", {"amount": 100}, True, "ALLOW", "d")
        policy = {"logic": {}, "action": {"on_pass": "ALLOW", "on_fail": "BLOCK"}}
        result = self.sim.run_test(policy, tc)
        self.assertTrue(result.passed)
        self.assertEqual(result.actual_action, "ALLOW")

    def test_run_test_fails(self):
        self.sim.logic_engine.evaluate.return_value = True  # violation
        tc = TestCase("t", "P1", {"amount": 10000}, False, "BLOCK", "d")
        policy = {"logic": {}, "action": {"on_pass": "ALLOW", "on_fail": "BLOCK"}}
        result = self.sim.run_test(policy, tc)
        self.assertTrue(result.passed)
        self.assertEqual(result.actual_action, "BLOCK")

    def test_run_test_exception(self):
        self.sim.logic_engine.evaluate.side_effect = Exception("boom")
        tc = TestCase("t", "P1", {}, True, "ALLOW", "d")
        result = self.sim.run_test({"logic": {}}, tc)
        self.assertFalse(result.passed)
        self.assertEqual(result.error, "boom")

    def test_run_test_suite(self):
        self.sim.logic_engine.evaluate.return_value = False
        tc1 = TestCase("t1", "P1", {}, True, "ALLOW", "d")
        tc2 = TestCase("t2", "P1", {}, True, "ALLOW", "d")
        policy = {"logic": {}, "action": {"on_pass": "ALLOW"}}
        results = self.sim.run_test_suite(policy, [tc1, tc2])
        self.assertEqual(len(results), 2)


class TestRegressionTester(unittest.TestCase):
    def setUp(self):
        self.tester = RegressionTester()
        self.tester.simulator.logic_engine = MagicMock()

    def test_no_regressions(self):
        self.tester.simulator.logic_engine.evaluate.return_value = False
        tc = TestCase("t", "P1", {}, True, "ALLOW", "d")
        old_p = {"policy_id": "P1", "logic": {}, "action": {"on_pass": "ALLOW"}}
        new_p = {"policy_id": "P1", "logic": {}, "action": {"on_pass": "ALLOW"}}
        report = self.tester.run_regression(old_p, new_p, [tc])
        self.assertEqual(report["regression_count"], 0)

    def test_detects_regression(self):
        # Old passes, new fails
        engine = self.tester.simulator.logic_engine
        engine.evaluate.side_effect = [False, True]  # old=no violation, new=violation
        tc = TestCase("t", "P1", {}, True, "ALLOW", "d")
        old_p = {"policy_id": "P1", "logic": {}, "action": {"on_pass": "ALLOW", "on_fail": "BLOCK"}}
        new_p = {"policy_id": "P1", "logic": {}, "action": {"on_pass": "ALLOW", "on_fail": "BLOCK"}}
        report = self.tester.run_regression(old_p, new_p, [tc])
        self.assertEqual(report["regression_count"], 1)


if __name__ == "__main__":
    unittest.main()
