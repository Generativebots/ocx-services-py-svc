"""Tests for recursive_parser.py — RecursiveSemanticParser"""
import sys, os, unittest
from unittest.mock import MagicMock, patch

# Mock vllm_client and json_logic_engine before import
sys.modules["vllm_client"] = MagicMock()
_mock_jle = MagicMock()
sys.modules["json_logic"] = MagicMock()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from recursive_parser import RecursiveSemanticParser, DocumentChunk


class TestDocumentChunk(unittest.TestCase):
    def test_init_defaults(self):
        c = DocumentChunk(level=0, title="Root", content="text")
        self.assertEqual(c.level, 0)
        self.assertEqual(c.children, [])
        self.assertIsNone(c.parent)

    def test_post_init_creates_list(self):
        c = DocumentChunk(level=1, title="S1", content="txt")
        self.assertIsInstance(c.children, list)


class TestSplitByHeaders(unittest.TestCase):
    def setUp(self):
        self.parser = RecursiveSemanticParser(MagicMock())

    def test_markdown_headers(self):
        text = "# Section 1\nContent 1\n## Subsection\nContent 2"
        sections = self.parser._split_by_headers(text)
        self.assertEqual(len(sections), 2)
        self.assertEqual(sections[0][0], "Section 1")
        self.assertEqual(sections[1][0], "Subsection")

    def test_no_headers(self):
        text = "Just plain text\nwith some lines"
        sections = self.parser._split_by_headers(text)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0][0], "Untitled")

    def test_single_header(self):
        text = "# Only Header\nSome content here."
        sections = self.parser._split_by_headers(text)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0][0], "Only Header")


class TestSplitByParagraphs(unittest.TestCase):
    def setUp(self):
        self.parser = RecursiveSemanticParser(MagicMock())

    def test_double_newline(self):
        paras = self.parser._split_by_paragraphs("Para 1\n\nPara 2\n\nPara 3")
        self.assertEqual(len(paras), 3)

    def test_empty_text(self):
        self.assertEqual(self.parser._split_by_paragraphs(""), [])


class TestSplitBySentences(unittest.TestCase):
    def setUp(self):
        self.parser = RecursiveSemanticParser(MagicMock())

    def test_multiple_sentences(self):
        sentences = self.parser._split_by_sentences("First sentence. Second sentence. Third!")
        self.assertEqual(len(sentences), 3)

    def test_single_sentence(self):
        self.assertEqual(len(self.parser._split_by_sentences("Hello world")), 1)


class TestParseDocument(unittest.TestCase):
    def setUp(self):
        self.parser = RecursiveSemanticParser(MagicMock())

    def test_full_parse(self):
        text = "# Procurement\n\nAll purchases over $500 need approval.\n\n## Payment\n\nPayments in 48h."
        root = self.parser.parse_document(text)
        self.assertEqual(root.level, 0)
        self.assertEqual(len(root.children), 2)  # Two headers
        for section in root.children:
            self.assertEqual(section.level, 1)
            self.assertGreater(len(section.children), 0)


class TestExtractPoliciesRecursive(unittest.TestCase):
    def setUp(self):
        self.mock_vllm = MagicMock()
        self.parser = RecursiveSemanticParser(self.mock_vllm)

    def test_skips_short_chunks(self):
        chunk = DocumentChunk(level=2, title=None, content="Hi")
        result = self.parser._extract_from_chunk(chunk, "src")
        self.assertEqual(result, [])

    def test_calls_vllm_for_long_chunk(self):
        self.mock_vllm.extract_policies.return_value = [{"policy_id": "P1"}]
        chunk = DocumentChunk(level=2, title="Para", content="A" * 50)
        result = self.parser._extract_from_chunk(chunk, "src")
        self.assertEqual(len(result), 1)

    def test_merge_policies_deduplicates_by_trigger(self):
        policies = [
            {"trigger_intent": "buy", "confidence": 0.8},
            {"trigger_intent": "buy", "confidence": 0.95},
            {"trigger_intent": "sell", "confidence": 0.7},
        ]
        merged = self.parser._merge_policies(policies)
        self.assertEqual(len(merged), 2)
        buy = [p for p in merged if p["trigger_intent"] == "buy"][0]
        self.assertEqual(buy["confidence"], 0.95)


class TestValidateConsistency(unittest.TestCase):
    def setUp(self):
        self.parser = RecursiveSemanticParser(MagicMock())

    def test_filters_duplicate_ids(self):
        """json_logic_engine is imported inside _validate_consistency, so we mock it there"""
        mock_engine = MagicMock()
        mock_engine.validate_logic.return_value = (True, None)
        
        with patch.dict("sys.modules", {"json_logic_engine": MagicMock()}):
            # Import inside patch context so we get fresh module
            import importlib
            import recursive_parser as rp
            importlib.reload(rp)
            
            parser = rp.RecursiveSemanticParser(MagicMock())
            # The _validate_consistency imports JSONLogicEngine inside the function
            # We need to mock it at the module level it imports from
            with patch("json_logic_engine.JSONLogicEngine", return_value=mock_engine):
                policies = [
                    {"policy_id": "P1", "logic": {}},
                    {"policy_id": "P1", "logic": {}},
                ]
                result = parser._validate_consistency(policies)
                self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
