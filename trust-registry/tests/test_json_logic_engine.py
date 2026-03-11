"""Tests for json_logic_engine.py — JSONLogicEngine
NOTE: conftest.py replaces json_logic with FakeJSONLogicEngine wrapper.
These tests verify the actual JSONLogicEngine class as loaded by conftest.
"""
import sys, os, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from json_logic_engine import JSONLogicEngine


class TestJSONLogicEngineEvaluate(unittest.TestCase):
    def setUp(self):
        self.engine = JSONLogicEngine()

    def test_simple_comparison_true(self):
        result = self.engine.evaluate({">": [{"var": "amount"}, 500]}, {"amount": 1000})
        self.assertTrue(result)

    def test_simple_comparison_false(self):
        result = self.engine.evaluate({">": [{"var": "amount"}, 500]}, {"amount": 100})
        self.assertFalse(result)

    def test_context_merged_into_data(self):
        logic = {"in": [{"var": "dest"}, {"var": "wl"}]}
        result = self.engine.evaluate(logic, {"dest": "a"}, context={"wl": ["a", "b"]})
        self.assertTrue(result)

    def test_less_than(self):
        result = self.engine.evaluate({"<": [{"var": "x"}, 10]}, {"x": 5})
        self.assertTrue(result)

    def test_less_than_false(self):
        result = self.engine.evaluate({"<": [{"var": "x"}, 10]}, {"x": 15})
        self.assertFalse(result)

    def test_equality(self):
        result = self.engine.evaluate({"==": [{"var": "status"}, "active"]}, {"status": "active"})
        self.assertTrue(result)

    def test_and_both_true(self):
        logic = {"and": [{">": [{"var": "a"}, 0]}, {"<": [{"var": "b"}, 10]}]}
        result = self.engine.evaluate(logic, {"a": 5, "b": 3})
        self.assertTrue(result)

    def test_and_one_false(self):
        logic = {"and": [{">": [{"var": "a"}, 0]}, {"<": [{"var": "b"}, 10]}]}
        result = self.engine.evaluate(logic, {"a": -1, "b": 3})
        self.assertFalse(result)

    def test_or_one_true(self):
        logic = {"or": [{">": [{"var": "a"}, 100]}, {"<": [{"var": "b"}, 10]}]}
        result = self.engine.evaluate(logic, {"a": 1, "b": 3})
        self.assertTrue(result)

    def test_not_operator(self):
        logic = {"not": {">": [{"var": "x"}, 100]}}
        result = self.engine.evaluate(logic, {"x": 50})
        self.assertTrue(result)

    def test_missing_variable(self):
        result = self.engine.evaluate({">": [{"var": "missing"}, 500]}, {"amount": 1000})
        self.assertFalse(result)


class TestJSONLogicEngineValidate(unittest.TestCase):
    def setUp(self):
        self.engine = JSONLogicEngine()

    def test_valid_logic(self):
        valid, err = self.engine.validate_logic({">": [1, 0]})
        self.assertTrue(valid)
        self.assertIsNone(err)

    def test_empty_logic_valid(self):
        valid, err = self.engine.validate_logic({})
        self.assertTrue(valid)


class TestExtractVariables(unittest.TestCase):
    def setUp(self):
        self.engine = JSONLogicEngine()

    def test_single_var(self):
        result = self.engine.extract_variables({">": [{"var": "amount"}, 500]})
        self.assertEqual(result, ["amount"])

    def test_nested_vars(self):
        logic = {"and": [{">": [{"var": "a"}, 1]}, {"<": [{"var": "b"}, 2]}]}
        result = self.engine.extract_variables(logic)
        self.assertIn("a", result)
        self.assertIn("b", result)

    def test_deduplicates(self):
        logic = {"and": [{">": [{"var": "x"}, 1]}, {"<": [{"var": "x"}, 10]}]}
        self.assertEqual(self.engine.extract_variables(logic), ["x"])


class TestSimplify(unittest.TestCase):
    def setUp(self):
        self.engine = JSONLogicEngine()

    def test_single_and(self):
        self.assertEqual(self.engine.simplify({"and": [{">": [1, 0]}]}), {">": [1, 0]})

    def test_single_or(self):
        self.assertEqual(self.engine.simplify({"or": [{"<": [1, 2]}]}), {"<": [1, 2]})

    def test_double_negation(self):
        self.assertEqual(self.engine.simplify({"not": {"not": {">": [1, 0]}}}), {">": [1, 0]})

    def test_identity_comparison(self):
        self.assertTrue(self.engine.simplify({"==": [{"var": "x"}, {"var": "x"}]}))

    def test_complex_no_simplification(self):
        result = self.engine.simplify({"and": [{">": [1, 0]}, {"<": [2, 3]}]})
        self.assertIn("and", result)

    def test_non_dict_passthrough(self):
        self.assertEqual(self.engine.simplify(42), 42)


if __name__ == "__main__":
    unittest.main()
