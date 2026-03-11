"""
Intent Extractor — API endpoint tests.

Tests /health, /extract/text, /extract/document endpoints
with mocked Gemini and Supabase.
"""

import pytest
import sys
import os
from unittest.mock import patch, AsyncMock, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestHealth:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


class TestExtractFromText:
    """POST /extract/text — stateless intent extraction."""

    @patch("main._extract_intents_with_gemini")
    def test_extract_text_success(self, mock_gemini, client):
        """Mocked Gemini returns structured intents."""
        from main import IntentMap, BusinessIntent

        mock_gemini.return_value = IntentMap(
            intents=[
                BusinessIntent(
                    intent_name="verify_compliance",
                    source_resource="vendor_onboarding_sop",
                    trigger_condition="New vendor submitted for onboarding",
                    action_steps=["Check SOC2 cert", "Validate expiry dates"],
                    risk_level="AMBER",
                    compliance_frameworks=["SOC2"],
                ),
            ]
        )

        resp = client.post("/extract/text", json={
            "text": "All vendors must be SOC2 compliant before onboarding.",
            "tenant_id": "t-1",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["intents_extracted"] == 1
        assert data["intents"][0]["intent_name"] == "verify_compliance"
        assert data["intents"][0]["source_resource"] == "vendor_onboarding_sop"
        assert len(data["intents"][0]["action_steps"]) == 2

    def test_extract_text_missing_fields_422(self, client):
        resp = client.post("/extract/text", json={"text": "hello"})
        assert resp.status_code == 422

    @patch("main._extract_intents_with_gemini")
    def test_extract_text_empty_result(self, mock_gemini, client):
        """Gemini returns no intents → valid but empty response."""
        from main import IntentMap

        mock_gemini.return_value = IntentMap(intents=[])

        resp = client.post("/extract/text", json={
            "text": "Nothing here.",
            "tenant_id": "t-1",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["intents_extracted"] == 0

    @patch("main._extract_intents_with_gemini")
    def test_extract_text_gemini_failure(self, mock_gemini, client):
        """If Gemini raises, endpoint returns 502 (LLM upstream error)."""
        mock_gemini.side_effect = Exception("API rate limit")

        resp = client.post("/extract/text", json={
            "text": "Test document.",
            "tenant_id": "t-1",
        })
        assert resp.status_code == 502
        assert "LLM extraction failed" in resp.json()["detail"]

    @patch("main._extract_intents_with_gemini")
    def test_extract_multiple_intents(self, mock_gemini, client):
        """Multiple intents extracted from a complex document."""
        from main import IntentMap, BusinessIntent

        mock_gemini.return_value = IntentMap(
            intents=[
                BusinessIntent(
                    intent_name="verify_compliance",
                    source_resource="policy_doc",
                    trigger_condition="New vendor submitted",
                    action_steps=["Check cert"],
                    risk_level="GREEN",
                    compliance_frameworks=["SOC2"],
                ),
                BusinessIntent(
                    intent_name="approve_access",
                    source_resource="access_policy",
                    trigger_condition="Employee requests data access",
                    action_steps=["Check role", "Request approval", "Grant access"],
                    risk_level="RED",
                    compliance_frameworks=["HIPAA", "GDPR"],
                    hitl_checkpoint="Manager must approve RED risk access",
                ),
            ]
        )

        resp = client.post("/extract/text", json={
            "text": "Complex compliance document with multiple policies.",
            "tenant_id": "t-1",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["intents_extracted"] == 2
        assert data["intents"][1]["hitl_checkpoint"] is not None

    def test_extract_empty_text_400(self, client):
        """Empty text should return 400."""
        resp = client.post("/extract/text", json={
            "text": "   ",
            "tenant_id": "t-1",
        })
        assert resp.status_code == 400
