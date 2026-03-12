"""Tests for gra/regulatory_ai.py"""
import pytest
from unittest.mock import patch, MagicMock

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from regulatory_ai import (
    RegulatoryAIService,
    RegulatoryRequirement,
    ActionClassification,
    _supabase_headers,
    _supabase_get,
    _supabase_insert,
)


class TestSupabaseHelpers:
    def test_headers_contain_auth(self):
        with patch("regulatory_ai.SUPABASE_KEY", "test-key"):
            headers = _supabase_headers()
            assert headers["apikey"] == "test-key"
            assert "Bearer test-key" in headers["Authorization"]

    @patch("regulatory_ai.SUPABASE_URL", "")
    def test_supabase_get_no_url_returns_empty(self):
        assert _supabase_get("any_table") == []

    @patch("regulatory_ai.SUPABASE_URL", "")
    def test_supabase_insert_no_url_returns_false(self):
        assert _supabase_insert("any_table", {}) is False

    @patch("regulatory_ai.SUPABASE_URL", "https://test.supabase.co")
    @patch("regulatory_ai.requests.get")
    def test_supabase_get_success(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200)
        mock_get.return_value.json.return_value = [{"id": "r1"}]
        mock_get.return_value.raise_for_status = MagicMock()
        result = _supabase_get("test_table", {"key": "eq.val"})
        assert result == [{"id": "r1"}]

    @patch("regulatory_ai.SUPABASE_URL", "https://test.supabase.co")
    @patch("regulatory_ai.requests.get")
    def test_supabase_get_error_returns_empty(self, mock_get):
        mock_get.side_effect = Exception("network error")
        assert _supabase_get("test_table") == []

    @patch("regulatory_ai.SUPABASE_URL", "https://test.supabase.co")
    @patch("regulatory_ai.requests.post")
    def test_supabase_insert_success(self, mock_post):
        mock_post.return_value = MagicMock(status_code=201)
        mock_post.return_value.raise_for_status = MagicMock()
        assert _supabase_insert("test_table", {"data": 1}) is True


class TestRegulatoryAIService:
    def setup_method(self):
        self.svc = RegulatoryAIService()

    @patch("regulatory_ai._supabase_get")
    def test_fetch_requirements_no_region_found(self, mock_get):
        mock_get.return_value = []
        result = self.svc.fetch_regulatory_requirements("XX")
        assert result == []

    @patch("regulatory_ai._supabase_get")
    def test_fetch_requirements_with_region(self, mock_get):
        def side_effect(table, params=None):
            if table == "gra_compliance_regions":
                return [{"region_code": "EU", "countries": ["DE", "FR"]}]
            if table == "gra_regulatory_frameworks":
                return [{"framework_id": "f1", "name": "GDPR", "category": "privacy",
                         "description": "Data protection", "enforcement_level": "MANDATORY",
                         "verification_url": "https://gdpr.eu", "risk_weight": 0.9}]
            return []
        mock_get.side_effect = side_effect
        reqs = self.svc.fetch_regulatory_requirements("DE")
        assert len(reqs) == 1
        assert reqs[0].framework_name == "GDPR"
        assert reqs[0].enforcement_level == "MANDATORY"

    @patch("regulatory_ai._supabase_get")
    def test_classify_action_green_risk(self, mock_get):
        def side_effect(table, params=None):
            if table == "gra_action_mappings":
                return [{"action_types": ["read"], "intent_key": "audit-log", "risk_weight": 0.1}]
            if table == "gra_risk_config":
                return [{"green_max_score": 0.3, "amber_max_score": 0.7}]
            if table == "gra_suggestion_templates":
                return []
            if table == "gra_next_step_templates":
                return []
            return []
        mock_get.side_effect = side_effect
        result = self.svc.classify_action_intent("t1", "agent-1", "read", {})
        assert result.risk_color == "GREEN"
        assert result.risk_score == 0.1

    @patch("regulatory_ai._supabase_get")
    def test_classify_action_red_risk(self, mock_get):
        def side_effect(table, params=None):
            if table == "gra_action_mappings":
                return [{"action_types": ["delete"], "intent_key": "data-delete", "risk_weight": 0.9}]
            if table == "gra_risk_config":
                return [{"green_max_score": 0.3, "amber_max_score": 0.7}]
            if table == "gra_suggestion_templates":
                return []
            if table == "gra_next_step_templates":
                return []
            return []
        mock_get.side_effect = side_effect
        result = self.svc.classify_action_intent("t1", "agent-1", "delete", {})
        assert result.risk_color == "RED"

    @patch("regulatory_ai._supabase_get")
    def test_classify_action_wildcard_match(self, mock_get):
        def side_effect(table, params=None):
            if table == "gra_action_mappings":
                return [{"action_types": ["*"], "intent_key": "catchall", "risk_weight": 0.5}]
            if table == "gra_risk_config":
                return []
            return []
        mock_get.side_effect = side_effect
        result = self.svc.classify_action_intent("t1", "a1", "anything", {})
        assert result.classified_intent == "catchall"
        assert result.risk_color == "AMBER"

    @patch("regulatory_ai._supabase_get")
    def test_classify_no_mappings_uses_action_type(self, mock_get):
        mock_get.return_value = []
        result = self.svc.classify_action_intent("t1", "a1", "custom-action", {})
        assert result.classified_intent == "custom-action"
        assert result.risk_score == 0.0

    @patch("regulatory_ai._supabase_get")
    def test_generate_suggestion_with_template(self, mock_get):
        mock_get.return_value = [{"suggestion_text": "Review {action_type} for {intent_keys}"}]
        result = self.svc._generate_suggestion("RED", ["data-delete"], "delete", "t1")
        assert "delete" in result
        assert "data-delete" in result

    @patch("regulatory_ai._supabase_get")
    def test_generate_suggestion_fallback(self, mock_get):
        mock_get.return_value = []
        result = self.svc._generate_suggestion("AMBER", ["k1"], "write")
        assert "AMBER" in result

    @patch("regulatory_ai._supabase_get")
    def test_generate_next_steps_red_fallback(self, mock_get):
        mock_get.return_value = []
        steps = self.svc._generate_next_steps("RED", ["k1"], "t1")
        assert any("HITL" in s for s in steps)

    @patch("regulatory_ai._supabase_get")
    def test_generate_next_steps_amber_fallback(self, mock_get):
        mock_get.return_value = []
        steps = self.svc._generate_next_steps("AMBER", ["k1"], "t1")
        assert any("compliance review" in s.lower() for s in steps)

    @patch("regulatory_ai._supabase_get")
    def test_generate_next_steps_green_fallback(self, mock_get):
        mock_get.return_value = []
        steps = self.svc._generate_next_steps("GREEN", [], "t1")
        assert len(steps) >= 1

    @patch("regulatory_ai._supabase_insert")
    @patch("regulatory_ai._supabase_get")
    def test_generate_risk_assessment(self, mock_get, mock_insert):
        mock_get.return_value = []
        mock_insert.return_value = True
        assessment = self.svc.generate_risk_assessment("t1", "a1", "read", {})
        assert "risk_color" in assessment
        assert "ai_suggestion" in assessment
        assert "next_steps" in assessment
        assert assessment["tenant_id"] == "t1"
        mock_insert.assert_called_once()
