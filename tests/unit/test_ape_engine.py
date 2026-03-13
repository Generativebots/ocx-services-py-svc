"""Tests for ape_engine.py — VLLMClient, RecursiveParser, extract_rules endpoint"""
import sys, os, unittest, pytest
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


class TestAPEExtractEndpoint:
    """Test the /extract FastAPI endpoint."""

    @pytest.mark.asyncio
    async def test_extract_rules_with_mock_llm(self):
        """Extract endpoint processes chunks and returns validated rules."""
        from ape_engine import extract_rules, ExtractRequest

        # Mock the global llm to return structured data
        mock_llm_data = [{
            "condition": "amount > 500",
            "suggested_action": "BLOCK",
            "confidence_score": 0.95,
            "logic_gate": {"field": "amount", "operator": ">", "value": "500"},
        }]

        with patch("ape_engine.llm") as mock_llm:
            mock_llm.generate_json = AsyncMock(return_value=mock_llm_data)

            req = ExtractRequest(
                document_text="If amount exceeds 500, block the transaction.",
                source_name="Test SOP",
                tenant_id="t-1",
            )
            result = await extract_rules(req)
            assert len(result) >= 1
            assert result[0].tenant_id == "t-1"
            assert result[0].confidence_score == 0.95

    @pytest.mark.asyncio
    async def test_extract_rules_skips_invalid(self):
        """Invalid rules are skipped during validation."""
        from ape_engine import extract_rules, ExtractRequest

        # Return data that will fail PolicyObject validation (missing required fields)
        invalid_data = [{"invalid_field_only": True}]

        with patch("ape_engine.llm") as mock_llm:
            mock_llm.generate_json = AsyncMock(return_value=invalid_data)

            req = ExtractRequest(
                document_text="Some text",
                source_name="Test",
                tenant_id="t-1",
            )
            result = await extract_rules(req)
            assert result == []  # Invalid rules skipped

    @pytest.mark.asyncio
    async def test_extract_rules_empty_document(self):
        """Empty document → no chunks → no rules."""
        from ape_engine import extract_rules, ExtractRequest

        with patch("ape_engine.llm") as mock_llm:
            mock_llm.generate_json = AsyncMock(return_value=[])

            req = ExtractRequest(
                document_text="",
                source_name="Empty",
                tenant_id="t-1",
            )
            result = await extract_rules(req)
            assert result == []


# ============================================================================
# registry.py — missing lines: 30, 39, 46-68, 101-103, 123-135, 140-163,
#               169-172, 183, 206-214, 223-233
# ============================================================================


