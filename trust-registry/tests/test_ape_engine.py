"""Tests for ape_engine.py — VLLMClient, RecursiveParser, extract_rules endpoint"""
import sys, os, unittest
from unittest.mock import MagicMock, patch, AsyncMock

# Mock httpx before import
sys.modules.setdefault("httpx", MagicMock())

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestVLLMClient(unittest.TestCase):
    def setUp(self):
        from ape_engine import VLLMClient
        self.client = VLLMClient(base_url="http://localhost:8000/v1")

    def test_init_defaults(self):
        self.assertIn("localhost", self.client.base_url)


class TestRecursiveParser(unittest.TestCase):
    def test_parse_simple_text(self):
        from ape_engine import RecursiveParser
        parser = RecursiveParser()
        chunks = parser.parse("Para 1\n\nPara 2\n\nPara 3")
        self.assertEqual(len(chunks), 3)

    def test_parse_no_double_newline(self):
        from ape_engine import RecursiveParser
        parser = RecursiveParser()
        chunks = parser.parse("Just one paragraph")
        self.assertEqual(len(chunks), 1)

    def test_parse_empty(self):
        from ape_engine import RecursiveParser
        parser = RecursiveParser()
        chunks = parser.parse("")
        self.assertEqual(chunks, [])


class TestModels(unittest.TestCase):
    def test_extract_request(self):
        from ape_engine import ExtractRequest
        req = ExtractRequest(document_text="text", source_name="src", tenant_id="t1")
        self.assertEqual(req.tenant_id, "t1")

    def test_logic_gate(self):
        from ape_engine import LogicGate
        lg = LogicGate(field="amount", operator=">", value=500)
        self.assertEqual(lg.field, "amount")

    def test_policy_object(self):
        from ape_engine import PolicyObject
        po = PolicyObject(
            rule_id="r1", tenant_id="t1", source_reference="src",
            condition="cond", suggested_action="act", confidence_score=0.9
        )
        self.assertEqual(po.logic_type, "DETERMINISTIC")
        self.assertIsNone(po.logic_gate)


class TestExtractRulesEndpoint(unittest.TestCase):
    """Test the FastAPI route via import"""

    @patch("ape_engine.llm")
    def test_extract_with_mock_llm(self, mock_llm):
        from ape_engine import extract_rules, ExtractRequest
        import asyncio

        mock_llm.generate_json = AsyncMock(return_value=[
            {
                "condition": "amount > 500",
                "suggested_action": "BLOCK",
                "confidence_score": 0.95,
                "logic_gate": {"field": "amount", "operator": ">", "value": "500"}
            }
        ])

        req = ExtractRequest(
            document_text="All purchases over $500 need approval.",
            source_name="Test SOP",
            tenant_id="tenant-1"
        )

        result = asyncio.get_event_loop().run_until_complete(extract_rules(req))
        self.assertGreaterEqual(len(result), 1)
        self.assertEqual(result[0].tenant_id, "tenant-1")

    @patch("ape_engine.llm")
    def test_extract_returns_empty_on_no_results(self, mock_llm):
        from ape_engine import extract_rules, ExtractRequest
        import asyncio

        mock_llm.generate_json = AsyncMock(return_value=[])
        req = ExtractRequest(document_text="Nothing.", source_name="Empty", tenant_id="t1")
        result = asyncio.get_event_loop().run_until_complete(extract_rules(req))
        self.assertEqual(len(result), 0)

    @patch("ape_engine.llm")
    def test_extract_skips_invalid_rules(self, mock_llm):
        from ape_engine import extract_rules, ExtractRequest
        import asyncio

        mock_llm.generate_json = AsyncMock(return_value=[
            {"bad_field": True}  # Missing required fields
        ])
        req = ExtractRequest(document_text="Some text\n\nsome more", source_name="Src", tenant_id="t1")
        result = asyncio.get_event_loop().run_until_complete(extract_rules(req))
        # Should skip invalid rules gracefully
        self.assertEqual(len(result), 0)


if __name__ == "__main__":
    unittest.main()
