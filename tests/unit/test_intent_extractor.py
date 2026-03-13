"""
Intent Extractor — comprehensive tests covering all endpoints, Supabase helpers,
LLM key resolution, model resolution, extraction pipeline, and edge cases.
"""

import sys
import os
import types
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

import pytest

# Stub LangChain before import
_fake_lc = types.ModuleType("langchain_google_genai")
_fake_lc.ChatGoogleGenerativeAI = MagicMock
sys.modules.setdefault("langchain_google_genai", _fake_lc)

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "intent-extractor"))

from fastapi.testclient import TestClient
import main as ie_main

client = TestClient(ie_main.app)


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

class TestHeaders:
    def test_headers(self):
        h = ie_main._headers()
        assert "apikey" in h
        assert "Content-Type" in h


class TestSupaGet:
    def test_no_url(self):
        with patch.object(ie_main, "SUPABASE_URL", ""):
            assert ie_main._supa_get("table") == []

    def test_success(self):
        with patch.object(ie_main, "SUPABASE_URL", "http://supa"):
            with patch("main.requests.get") as mock_get:
                mock_get.return_value.json.return_value = [{"id": 1}]
                mock_get.return_value.raise_for_status = MagicMock()
                result = ie_main._supa_get("table")
                assert result == [{"id": 1}]

    def test_failure(self):
        with patch.object(ie_main, "SUPABASE_URL", "http://supa"):
            with patch("main.requests.get", side_effect=Exception("timeout")):
                assert ie_main._supa_get("table") == []


class TestSupaInsert:
    def test_no_url(self):
        with patch.object(ie_main, "SUPABASE_URL", ""):
            assert ie_main._supa_insert("table", {}) is None

    def test_success_list(self):
        with patch.object(ie_main, "SUPABASE_URL", "http://supa"):
            with patch("main.requests.post") as mock_post:
                mock_post.return_value.json.return_value = [{"id": "new"}]
                mock_post.return_value.raise_for_status = MagicMock()
                result = ie_main._supa_insert("table", {"a": 1})
                assert result == {"id": "new"}

    def test_success_dict(self):
        with patch.object(ie_main, "SUPABASE_URL", "http://supa"):
            with patch("main.requests.post") as mock_post:
                mock_post.return_value.json.return_value = {"id": "new"}
                mock_post.return_value.raise_for_status = MagicMock()
                result = ie_main._supa_insert("table", {"a": 1})
                assert result == {"id": "new"}

    def test_failure(self):
        with patch.object(ie_main, "SUPABASE_URL", "http://supa"):
            with patch("main.requests.post", side_effect=Exception("err")):
                assert ie_main._supa_insert("t", {}) is None


class TestSupaPatch:
    def test_no_url(self):
        with patch.object(ie_main, "SUPABASE_URL", ""):
            assert ie_main._supa_patch("t", {}, {}) is False

    def test_success(self):
        with patch.object(ie_main, "SUPABASE_URL", "http://supa"):
            with patch("main.requests.patch") as mock_patch:
                mock_patch.return_value.raise_for_status = MagicMock()
                assert ie_main._supa_patch("t", {"k": "v"}, {"x": 1}) is True

    def test_failure(self):
        with patch.object(ie_main, "SUPABASE_URL", "http://supa"):
            with patch("main.requests.patch", side_effect=Exception("err")):
                assert ie_main._supa_patch("t", {}, {}) is False


# ═══════════════════════════════════════════════════════════════════════════════
# LLM KEY / MODEL RESOLUTION
# ═══════════════════════════════════════════════════════════════════════════════

class TestResolveLLMKey:
    def test_tenant_key(self):
        with patch.object(ie_main, "_supa_get", return_value=[{"settings": {"llm_api_key": "tk-123"}}]):
            assert ie_main._resolve_llm_key("t1") == "tk-123"

    def test_system_key_fallback(self):
        with patch.object(ie_main, "_supa_get", return_value=[{"settings": {}}]):
            with patch.object(ie_main, "SYSTEM_GOOGLE_API_KEY", "sys-key"):
                assert ie_main._resolve_llm_key("t1") == "sys-key"

    def test_no_key_raises(self):
        with patch.object(ie_main, "_supa_get", return_value=[]):
            with patch.object(ie_main, "SYSTEM_GOOGLE_API_KEY", ""):
                with pytest.raises(ValueError):
                    ie_main._resolve_llm_key("t1")

    def test_tenant_settings_none(self):
        with patch.object(ie_main, "_supa_get", return_value=[{"settings": None}]):
            with patch.object(ie_main, "SYSTEM_GOOGLE_API_KEY", "sys"):
                assert ie_main._resolve_llm_key("t1") == "sys"


class TestResolveModel:
    def test_tenant_model(self):
        with patch.object(ie_main, "_supa_get", return_value=[{"settings": {"llm_model": "gemini-pro"}}]):
            assert ie_main._resolve_model("t1") == "gemini-pro"

    def test_default_model(self):
        with patch.object(ie_main, "_supa_get", return_value=[]):
            assert ie_main._resolve_model("t1") == ie_main.DEFAULT_MODEL


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestHealthEndpoint:
    def test_health(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["service"] == "JARVIS Intent Extractor"


class TestExtractText:
    def test_empty_text(self):
        resp = client.post("/extract/text", json={"text": "", "tenant_id": "t1"})
        assert resp.status_code == 400

    def test_whitespace_text(self):
        resp = client.post("/extract/text", json={"text": "   ", "tenant_id": "t1"})
        assert resp.status_code == 400

    def test_no_llm_key(self):
        with patch.object(ie_main, "_resolve_llm_key", side_effect=ValueError("no key")):
            resp = client.post("/extract/text", json={"text": "test doc", "tenant_id": "t1"})
            assert resp.status_code == 400

    def test_llm_failure(self):
        with patch.object(ie_main, "_resolve_llm_key", return_value="key"):
            with patch.object(ie_main, "_resolve_model", return_value="gemini"):
                with patch.object(ie_main, "_extract_intents_with_gemini", side_effect=Exception("LLM err")):
                    resp = client.post("/extract/text", json={"text": "test doc", "tenant_id": "t1"})
                    assert resp.status_code == 502

    def test_success(self):
        mock_result = MagicMock()
        mock_result.intents = [
            ie_main.BusinessIntent(
                intent_name="verify_sop",
                source_resource="doc1",
                trigger_condition="daily",
                action_steps=["check", "report"],
            )
        ]
        with patch.object(ie_main, "_resolve_llm_key", return_value="key"):
            with patch.object(ie_main, "_resolve_model", return_value="gemini"):
                with patch.object(ie_main, "_extract_intents_with_gemini", return_value=mock_result):
                    resp = client.post("/extract/text", json={"text": "test doc", "tenant_id": "t1"})
                    assert resp.status_code == 200
                    assert resp.json()["intents_extracted"] == 1


class TestExtractDocument:
    def test_no_llm_key(self):
        with patch.object(ie_main, "_resolve_llm_key", side_effect=ValueError("no key")):
            resp = client.post("/extract", json={"document_id": "d1", "tenant_id": "t1"})
            assert resp.status_code == 400

    def test_doc_not_found(self):
        with patch.object(ie_main, "_resolve_llm_key", return_value="key"):
            with patch.object(ie_main, "_resolve_model", return_value="gemini"):
                with patch.object(ie_main, "_supa_get", return_value=[]):
                    resp = client.post("/extract", json={"document_id": "d1", "tenant_id": "t1"})
                    assert resp.status_code == 404

    def test_llm_failure_marks_failed(self):
        with patch.object(ie_main, "_resolve_llm_key", return_value="key"):
            with patch.object(ie_main, "_resolve_model", return_value="gemini"):
                with patch.object(ie_main, "_supa_get", return_value=[{"content": "text", "file_name": "f"}]):
                    with patch.object(ie_main, "_supa_patch") as mock_patch:
                        with patch.object(ie_main, "_extract_intents_with_gemini", side_effect=Exception("err")):
                            resp = client.post("/extract", json={"document_id": "d1", "tenant_id": "t1"})
                            assert resp.status_code == 502
                            # Should have patched status to FAILED
                            calls = mock_patch.call_args_list
                            assert any("FAILED" in str(c) for c in calls)

    def test_success_pipeline(self):
        mock_result = MagicMock()
        mock_result.intents = [
            ie_main.BusinessIntent(
                intent_name="test_intent", source_resource="doc",
                trigger_condition="t", action_steps=["a"],
                risk_level="GREEN",
            )
        ]
        with patch.object(ie_main, "_resolve_llm_key", return_value="key"):
            with patch.object(ie_main, "_resolve_model", return_value="gemini"):
                with patch.object(ie_main, "_supa_get", return_value=[{"content": "text", "file_name": "f"}]):
                    with patch.object(ie_main, "_supa_patch"):
                        with patch.object(ie_main, "_supa_insert"):
                            with patch.object(ie_main, "_extract_intents_with_gemini", return_value=mock_result):
                                resp = client.post("/extract", json={"document_id": "d1", "tenant_id": "t1"})
                                assert resp.status_code == 200
                                assert resp.json()["intents_extracted"] == 1
                                assert resp.json()["relationships_created"] == 1

    def test_no_content_fallback(self):
        mock_result = MagicMock()
        mock_result.intents = []
        with patch.object(ie_main, "_resolve_llm_key", return_value="key"):
            with patch.object(ie_main, "_resolve_model", return_value="gemini"):
                with patch.object(ie_main, "_supa_get", return_value=[{"file_name": "f.pdf"}]):
                    with patch.object(ie_main, "_supa_patch"):
                        with patch.object(ie_main, "_extract_intents_with_gemini", return_value=mock_result):
                            resp = client.post("/extract", json={"document_id": "d1", "tenant_id": "t1"})
                            assert resp.status_code == 200


class TestNow:
    def test_returns_iso(self):
        s = ie_main._now()
        assert "T" in s


class TestModels:
    def test_business_intent(self):
        bi = ie_main.BusinessIntent(
            intent_name="x", source_resource="s", trigger_condition="t",
            action_steps=["a"], risk_level="RED",
            compliance_frameworks=["HIPAA"], hitl_checkpoint="approve"
        )
        assert bi.risk_level == "RED"
        assert bi.hitl_checkpoint == "approve"

    def test_extract_request(self):
        r = ie_main.ExtractRequest(document_id="d1", tenant_id="t1")
        assert r.document_id == "d1"

    def test_extract_text_request(self):
        r = ie_main.ExtractTextRequest(text="hello", tenant_id="t1")
        assert r.text == "hello"


# ═══════════════════════════════════════════════════════════════════════════════
# COVERAGE GAP: _extract_intents_with_gemini (L183-209)
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtractIntentsWithGemini:
    """Cover lines 183-209: LangChain + Gemini extraction function."""

    def test_successful_extraction(self):
        mock_intent_map = ie_main.IntentMap(intents=[
            ie_main.BusinessIntent(
                intent_name="verify_sop",
                source_resource="doc1",
                trigger_condition="daily",
                action_steps=["check", "report"],
                risk_level="GREEN",
            )
        ])

        mock_structured = MagicMock()
        mock_structured.invoke.return_value = mock_intent_map

        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_structured

        with patch("langchain_google_genai.ChatGoogleGenerativeAI", return_value=mock_llm):
            result = ie_main._extract_intents_with_gemini(
                "Some SOP document text", "test-api-key", "gemini-2.0-flash"
            )
        assert len(result.intents) == 1
        assert result.intents[0].intent_name == "verify_sop"
        mock_llm.with_structured_output.assert_called_once_with(ie_main.IntentMap)
        mock_structured.invoke.assert_called_once()

    def test_extraction_with_all_fields(self):
        mock_intent_map = ie_main.IntentMap(intents=[
            ie_main.BusinessIntent(
                intent_name="transfer_funds",
                source_resource="banking_sop",
                trigger_condition="amount > 10000",
                action_steps=["validate", "approve", "execute"],
                risk_level="RED",
                compliance_frameworks=["AML", "SOC2"],
                hitl_checkpoint="VP approval required",
            )
        ])

        mock_structured = MagicMock()
        mock_structured.invoke.return_value = mock_intent_map

        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_structured

        with patch("langchain_google_genai.ChatGoogleGenerativeAI", return_value=mock_llm):
            result = ie_main._extract_intents_with_gemini(
                "Some banking SOP", "test-key", "gemini-2.0-flash"
            )
        assert result.intents[0].risk_level == "RED"
        assert result.intents[0].hitl_checkpoint == "VP approval required"

