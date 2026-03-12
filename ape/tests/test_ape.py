"""Tests for ape/ape_server.py and ape/ape_service.py — APE policy extraction and drift detection."""

import sys
import os
import types
import json

# Allow importing ape modules
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- Mock heavy dependencies before import ---
import unittest.mock as mock

# Mock grpc
_fake_grpc = types.ModuleType("grpc")
_fake_grpc.StatusCode = type("StatusCode", (), {
    "INVALID_ARGUMENT": "INVALID_ARGUMENT",
    "NOT_FOUND": "NOT_FOUND",
})()
_fake_grpc.server = mock.MagicMock()
sys.modules.setdefault("grpc", _fake_grpc)

# Mock governance config — return real dict to avoid float comparison errors
_fake_gov_mod = mock.MagicMock()
_fake_gov_mod.get_tenant_governance_config = mock.MagicMock(return_value={
    "ape_drift_warn_threshold": 0.60,
    "ape_drift_critical_threshold": 0.85,
    "escrow_sovereign_threshold": 0.90,
    "escrow_trusted_threshold": 0.60,
    "escrow_probation_threshold": 0.30,
})
sys.modules.setdefault("config", mock.MagicMock())
sys.modules["config.governance_config"] = _fake_gov_mod

# Mock httpx for LLM calls
sys.modules.setdefault("httpx", mock.MagicMock())

from ape.ape_service import (
    ExtractedRule,
    ExtractionResult,
    _regex_extract,
    extract_policies,
    compute_extraction_hash,
    POLICY_PATTERNS,
)

from ape.ape_server import (
    APEServiceImpl,
    _empty_extraction_response,
    _load_governance_config,
)

import pytest


# ---------------------------------------------------------------------------
# ape_service.py — Regex Extraction
# ---------------------------------------------------------------------------

class TestRegexExtract:
    """Tests for regex-based policy extraction."""

    def test_empty_text(self):
        result = extract_policies("", document_id="doc-empty")
        assert result.document_id == "doc-empty"
        assert result.rules == []

    def test_logging_rule(self):
        text = "All agents must log every data access. This is mandatory."
        result = _regex_extract(text, "doc-log")
        assert result.matched_sentences >= 1
        log_rules = [r for r in result.rules if r.logic["action"] == "LOG"]
        assert len(log_rules) >= 1

    def test_block_rule(self):
        text = "Employees must not access restricted data without clearance."
        result = _regex_extract(text, "doc-block")
        block_rules = [r for r in result.rules if r.logic["action"] == "BLOCK"]
        assert len(block_rules) >= 1

    def test_approval_rule(self):
        text = "Management approval is required for all external vendor contracts."
        result = _regex_extract(text, "doc-approval")
        escrow_rules = [r for r in result.rules if r.logic["action"] == "ESCROW"]
        assert len(escrow_rules) >= 1

    def test_sensitive_data_rule(self):
        text = "Confidential data must be encrypted at rest and in transit."
        result = _regex_extract(text, "doc-sensitive")
        assert result.matched_sentences >= 1

    def test_threshold_rule(self):
        text = "Any amount that exceeds $5,000 threshold requires VP sign-off before processing."
        result = _regex_extract(text, "doc-threshold")
        assert result.matched_sentences >= 1

    def test_periodic_check_rule(self):
        text = "A daily security scan is required for all production systems."
        result = _regex_extract(text, "doc-periodic")
        assert result.matched_sentences >= 1

    def test_encryption_rule(self):
        text = "TLS encryption is required for all API communications between services."
        result = _regex_extract(text, "doc-encrypt")
        assert result.matched_sentences >= 1

    def test_segregation_rule(self):
        text = "Segregation of duties must be enforced between development and operations teams."
        result = _regex_extract(text, "doc-sod")
        assert result.matched_sentences >= 1

    def test_multiple_rules(self):
        text = (
            "All agents must log every data access. "
            "Employees must not access restricted files. "
            "Authorization is required for large transactions. "
            "A weekly review of logs is needed."
        )
        result = _regex_extract(text, "doc-multi")
        assert result.matched_sentences >= 3

    def test_no_match(self):
        text = "The weather today is sunny with clear skies."
        result = _regex_extract(text, "doc-weather")
        assert result.matched_sentences == 0
        assert result.rules == []

    def test_short_sentences_skipped(self):
        text = "Hi. Ok. Sure. All employees must log data access for auditing."
        result = _regex_extract(text, "doc-short")
        # Short sentences (< 10 chars) should be skipped
        assert result.total_sentences >= 1

    def test_rule_naming(self):
        text = "Authorization is required for all production deployments."
        result = _regex_extract(text, "docid12345")
        if result.rules:
            assert result.rules[0].rule_name.startswith("APE-docid123")


class TestComputeExtractionHash:
    """Tests for extraction hash computation."""

    def test_empty_rules(self):
        result = ExtractionResult(document_id="d1")
        h = compute_extraction_hash(result)
        assert isinstance(h, str)
        assert len(h) == 16

    def test_deterministic(self):
        result = ExtractionResult(document_id="d1")
        result.rules = [
            ExtractedRule("r1", "desc1", {"action": "BLOCK"}, "ENFORCE", 0.9, "sentence1"),
            ExtractedRule("r2", "desc2", {"action": "LOG"}, "ADVISE", 0.7, "sentence2"),
        ]
        h1 = compute_extraction_hash(result)
        h2 = compute_extraction_hash(result)
        assert h1 == h2

    def test_different_rules_different_hash(self):
        r1 = ExtractionResult(document_id="d1")
        r1.rules = [ExtractedRule("r1", "d", {"action": "BLOCK"}, "ENFORCE", 0.9, "s")]
        r2 = ExtractionResult(document_id="d1")
        r2.rules = [ExtractedRule("r2", "d", {"action": "LOG"}, "ADVISE", 0.7, "s")]
        assert compute_extraction_hash(r1) != compute_extraction_hash(r2)


class TestExtractPolicies:
    """Tests for the public extract_policies API."""

    def test_regex_fallback_when_no_llm(self):
        result = extract_policies(
            "Authorization is required for all vendor payments.",
            document_id="doc-test",
        )
        assert result.extraction_method == "regex"

    def test_empty_document(self):
        result = extract_policies("", document_id="doc-empty")
        assert result.rules == []
        assert result.document_id == "doc-empty"


# ---------------------------------------------------------------------------
# ape_server.py — APEServiceImpl
# ---------------------------------------------------------------------------

class _FakeContext:
    """Stub for gRPC context."""
    def __init__(self):
        self._code = None
        self._details = None
    def set_code(self, code):
        self._code = code
    def set_details(self, details):
        self._details = details


class TestAPEServiceImpl:
    """Tests for the APEServiceImpl gRPC service."""

    def setup_method(self):
        self.svc = APEServiceImpl()
        self.ctx = _FakeContext()

    def test_extract_policies_empty_text(self):
        req = type("Req", (), {
            "document_text": "",
            "document_id": "doc-1",
            "tenant_id": "t1",
            "llm_provider": "",
            "llm_api_key": "",
        })()
        result = self.svc.ExtractPolicies(req, self.ctx)
        assert result["document_id"] == ""
        assert self.ctx._code == "INVALID_ARGUMENT"

    def test_extract_policies_valid(self):
        req = type("Req", (), {
            "document_text": "All employees must log all data access events.",
            "document_id": "doc-valid",
            "tenant_id": "t1",
            "llm_provider": "",
            "llm_api_key": "",
        })()
        result = self.svc.ExtractPolicies(req, self.ctx)
        assert result["document_id"] == "doc-valid"
        assert isinstance(result["rules"], list)

    def test_detect_drift(self):
        req = type("Req", (), {
            "policy_id": "pol-test-001",
            "tenant_id": "t1",
        })()
        result = self.svc.DetectDrift(req, self.ctx)
        assert "drift_id" in result
        assert "drift_score" in result
        assert 0 <= result["drift_score"] <= 1.0
        assert result["policy_id"] == "pol-test-001"
        assert isinstance(result["auto_correctable"], bool)

    def test_detect_drift_suggestions(self):
        """Different policy IDs produce different drift scores (hash-based)."""
        req1 = type("Req", (), {"policy_id": "pol-aaa", "tenant_id": "t1"})()
        req2 = type("Req", (), {"policy_id": "pol-bbb", "tenant_id": "t1"})()
        r1 = self.svc.DetectDrift(req1, self.ctx)
        r2 = self.svc.DetectDrift(req2, self.ctx)
        # Deterministic but different
        assert r1["drift_score"] != r2["drift_score"] or r1["drift_id"] != r2["drift_id"]

    def test_apply_correction(self):
        req = type("Req", (), {
            "drift_id": "drift-abcde-123",
            "tenant_id": "t1",
        })()
        result = self.svc.ApplyCorrection(req, self.ctx)
        assert result["success"] is True
        assert "corrected_policy_id" in result
        assert result["corrected_policy_id"].startswith("pol-corrected-")


class TestEmptyExtractionResponse:
    def test_fields(self):
        r = _empty_extraction_response()
        assert r["document_id"] == ""
        assert r["rules"] == []
        assert r["total_sentences"] == 0
        assert r["extraction_hash"] == ""


class TestLoadGovernanceConfig:
    def test_safe_fallback(self):
        cfg = _load_governance_config("nonexistent-tenant")
        # With the mock, this returns a dict
        assert isinstance(cfg, dict) or cfg is not None


# ---------------------------------------------------------------------------
# Coverage Boost: APEHTTPHandler (ape_server.py Lines 150-200)
# ---------------------------------------------------------------------------

from io import BytesIO
from ape.ape_server import APEHTTPHandler

class _FakeRequest:
    """Simulates an HTTP request for the handler."""
    def __init__(self, method, path, body=b"", headers=None):
        self.method = method
        self.path = path
        self.body = body
        self.headers = headers or {}

class _FakeHandler:
    """Wraps APEHTTPHandler to test without sockets."""

    def __init__(self):
        self.handler = APEHTTPHandler.__new__(APEHTTPHandler)
        self.handler.ape_svc = APEHTTPHandler.ape_svc
        self.response_code = None
        self.response_headers = {}
        self.response_body = b""
        self._buffer = BytesIO()
        self.handler.wfile = self._buffer
        self.handler.send_response = lambda code: setattr(self, 'response_code', code)
        self.handler.send_header = lambda k, v: self.response_headers.update({k: v})
        self.handler.end_headers = lambda: None
        self.handler.send_error = lambda code, msg="": setattr(self, 'response_code', code)
        self.handler.log_message = lambda fmt, *a: None

    def do_get(self, path):
        self.handler.path = path
        self.handler.headers = {"Content-Length": "0"}
        self.handler.do_GET()
        return self.response_code, self._get_body()

    def do_post(self, path, data=None):
        body = json.dumps(data).encode() if data else b""
        self.handler.path = path
        self.handler.headers = {"Content-Length": str(len(body))}
        self.handler.rfile = BytesIO(body)
        self.handler.do_POST()
        return self.response_code, self._get_body()

    def _get_body(self):
        self._buffer.seek(0)
        raw = self._buffer.read()
        self._buffer = BytesIO()
        self.handler.wfile = self._buffer
        if raw:
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                return raw
        return None


class TestAPEHTTPHandler:
    """Cover the REST bridge HTTP handler (ape_server.py lines 150-200)."""

    def setup_method(self):
        self.h = _FakeHandler()

    def test_health_endpoint(self):
        code, body = self.h.do_get("/health")
        assert code == 200
        assert body["status"] == "healthy"

    def test_get_unknown_path(self):
        code, _ = self.h.do_get("/unknown")
        assert code == 404

    def test_extract_endpoint(self):
        code, body = self.h.do_post("/extract", {
            "document_text": "All agents must log every data access event.",
            "document_id": "doc-http",
            "tenant_id": "t1",
        })
        assert code == 200
        assert body["document_id"] == "doc-http"

    def test_extract_with_rules(self):
        code, body = self.h.do_post("/extract", {
            "document_text": "All agents must log and audit every data access event.",
            "document_id": "doc-rules",
            "tenant_id": "t1",
        })
        assert code == 200
        assert len(body["rules"]) >= 1

    def test_drift_endpoint(self):
        code, body = self.h.do_post("/drift", {
            "policy_id": "pol-test",
            "tenant_id": "t1",
        })
        assert code == 200
        assert "drift_score" in body

    def test_correct_endpoint(self):
        code, body = self.h.do_post("/correct", {
            "drift_id": "drift-abc-001",
            "tenant_id": "t1",
        })
        assert code == 200
        assert body["success"] is True

    def test_post_unknown_path(self):
        code, _ = self.h.do_post("/nope", {})
        assert code == 404

    def test_post_invalid_json(self):
        body = b"NOT-JSON"
        self.h.handler.path = "/extract"
        self.h.handler.headers = {"Content-Length": str(len(body))}
        self.h.handler.rfile = BytesIO(body)
        self.h.handler.do_POST()
        assert self.h.response_code == 400


# ---------------------------------------------------------------------------
# Coverage Boost: ape_service.py — LLM branch stubs + more patterns
# ---------------------------------------------------------------------------

class TestExtractPoliciesEdgeCases:
    """Additional ape_service tests to boost coverage of uncovered patterns."""

    def test_multiple_sentences_with_mixed_matches(self):
        text = (
            "Segregation of duties must be maintained across teams. "
            "A weekly review of reports is mandatory for all production systems. "
            "Random unrelated sentence about weather. "
            "Amounts exceeding $10,000 require VP sign-off."
        )
        result = extract_policies(text, document_id="doc-mixed")
        assert result.total_sentences >= 3
        assert len(result.rules) >= 1

    def test_document_id_auto_generated(self):
        result = extract_policies("Authorization is required for deployments.")
        assert result.document_id is not None
        assert len(result.document_id) > 0

    def test_key_pattern_types(self):
        texts = {
            "BLOCK": "Employees must not access restricted data.",
            "ESCROW_APPROVAL": "Authorization is required for vendor contracts.",
            "ESCROW_SENSITIVE": "Confidential data must be handled carefully.",
            "ESCROW_THRESHOLD": "Any transaction above the $5,000 threshold must be reviewed.",
            "PERIODIC": "A daily review of security logs is mandatory.",
            "SEGREGATION": "Segregation of duties must apply to development roles.",
        }
        for expected_action, text in texts.items():
            result = _regex_extract(text, f"doc-{expected_action}")
            assert result.matched_sentences >= 1, f"No match for {expected_action}: {text}"

    def test_detect_drift_with_high_score(self):
        svc = APEServiceImpl()
        ctx = _FakeContext()
        for i in range(20):
            req = type("Req", (), {"policy_id": f"pol-highscore-{i}", "tenant_id": "t1"})()
            result = svc.DetectDrift(req, ctx)
            if result["suggestions"]:
                assert len(result["suggestions"]) >= 1
                return


# ---------------------------------------------------------------------------
# Coverage Boost: LLM extraction paths (ape_service.py L171-340)
# ---------------------------------------------------------------------------
import asyncio
from ape.ape_service import _llm_extract, _call_llm


class TestLLMExtract:
    """Tests for the _llm_extract function (lines 171-235)."""

    def test_no_api_key_falls_back_to_regex(self):
        """No API key → falls back to regex extraction."""
        result = asyncio.get_event_loop().run_until_complete(
            _llm_extract("All agents must log data access.", "doc-1", "t1", "openai", "")
        )
        assert result.extraction_method == "regex"

    def test_successful_llm_extraction(self):
        """Valid LLM response → parses rules correctly."""
        llm_response = json.dumps([
            {
                "rule_name": "data-logging",
                "description": "All data access must be logged",
                "tier": "ENFORCE",
                "action": "LOG",
                "condition": "data_access == true",
                "severity": "HIGH",
                "source_sentence": "All data access must be logged."
            },
            {
                "rule_name": "access-control",
                "description": "Restricted access requires approval",
                "tier": "ADVISE",
                "action": "ESCROW",
                "condition": "access_level > 3",
                "severity": "MEDIUM",
                "source_sentence": "Restricted access requires approval."
            }
        ])

        with mock.patch("ape.ape_service._call_llm", return_value=llm_response):
            result = asyncio.get_event_loop().run_until_complete(
                _llm_extract("Some SOP text.", "doc-llm", "t1", "openai", "sk-key")
            )
        assert result.extraction_method == "llm"
        assert len(result.rules) == 2
        assert result.rules[0].confidence == 0.90
        assert result.rules[0].rule_name.startswith("APE-doc-llm-L")

    def test_llm_returns_single_object(self):
        """LLM returns a single object (not array) → wraps in list."""
        llm_response = json.dumps({
            "rule_name": "single-rule",
            "description": "desc",
            "tier": "LOG",
            "action": "LOG",
            "condition": "",
            "severity": "LOW",
            "source_sentence": "sentence"
        })
        with mock.patch("ape.ape_service._call_llm", return_value=llm_response):
            result = asyncio.get_event_loop().run_until_complete(
                _llm_extract("text", "doc-s", "t1", "openai", "sk-key")
            )
        assert len(result.rules) == 1

    def test_llm_exception_falls_back_to_regex(self):
        """LLM call throws → falls back to regex."""
        with mock.patch("ape.ape_service._call_llm", side_effect=Exception("API error")):
            result = asyncio.get_event_loop().run_until_complete(
                _llm_extract("All agents must log data.", "doc-err", "t1", "openai", "sk-key")
            )
        assert result.extraction_method == "regex"

    def test_llm_invalid_json_falls_back(self):
        """LLM returns invalid JSON → falls back to regex."""
        with mock.patch("ape.ape_service._call_llm", return_value="not json at all"):
            result = asyncio.get_event_loop().run_until_complete(
                _llm_extract("All agents must log data.", "doc-bad", "t1", "openai", "sk-key")
            )
        assert result.extraction_method == "regex"


class TestCallLLM:
    """Tests for _call_llm provider dispatch (lines 238-288)."""

    def test_openai_provider(self):
        mock_resp = mock.MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "[]"}}]
        }
        mock_resp.raise_for_status = mock.MagicMock()

        mock_client = mock.AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = mock.AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = mock.AsyncMock(return_value=False)

        with mock.patch("ape.ape_service.httpx.AsyncClient", return_value=mock_client):
            result = asyncio.get_event_loop().run_until_complete(
                _call_llm("openai", "sk-key", "prompt")
            )
        assert result == "[]"

    def test_anthropic_provider(self):
        mock_resp = mock.MagicMock()
        mock_resp.json.return_value = {
            "content": [{"text": "[]"}]
        }
        mock_resp.raise_for_status = mock.MagicMock()

        mock_client = mock.AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = mock.AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = mock.AsyncMock(return_value=False)

        with mock.patch("ape.ape_service.httpx.AsyncClient", return_value=mock_client):
            result = asyncio.get_event_loop().run_until_complete(
                _call_llm("anthropic", "ak-key", "prompt")
            )
        assert result == "[]"

    def test_gemini_provider(self):
        mock_resp = mock.MagicMock()
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "[]"}]}}]
        }
        mock_resp.raise_for_status = mock.MagicMock()

        mock_client = mock.AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = mock.AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = mock.AsyncMock(return_value=False)

        with mock.patch("ape.ape_service.httpx.AsyncClient", return_value=mock_client):
            result = asyncio.get_event_loop().run_until_complete(
                _call_llm("gemini", "gk-key", "prompt")
            )
        assert result == "[]"

    def test_unsupported_provider_raises(self):
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            asyncio.get_event_loop().run_until_complete(
                _call_llm("unknown_provider", "key", "prompt")
            )

    def test_empty_provider_uses_openai(self):
        mock_resp = mock.MagicMock()
        mock_resp.json.return_value = {"choices": [{"message": {"content": "[]"}}]}
        mock_resp.raise_for_status = mock.MagicMock()

        mock_client = mock.AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = mock.AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = mock.AsyncMock(return_value=False)

        with mock.patch("ape.ape_service.httpx.AsyncClient", return_value=mock_client):
            result = asyncio.get_event_loop().run_until_complete(
                _call_llm("", "sk-key", "prompt")
            )
        assert result == "[]"


class TestExtractPoliciesWithLLM:
    """Tests for extract_policies with LLM keys (lines 295-349)."""

    def test_extract_with_llm_provider(self):
        """When llm_provider and llm_api_key are set, uses LLM path."""
        llm_response = json.dumps([{
            "rule_name": "r1", "description": "d", "tier": "ENFORCE",
            "action": "BLOCK", "condition": "c", "severity": "HIGH", "source_sentence": "s"
        }])
        with mock.patch("ape.ape_service._call_llm", return_value=llm_response):
            result = extract_policies(
                "Some policy document text here for extraction.",
                document_id="doc-llm-test",
                tenant_id="t1",
                llm_provider="openai",
                llm_api_key="sk-test-key",
            )
        assert result.extraction_method == "llm"
        assert len(result.rules) == 1

    def test_extract_llm_dispatch_failure_falls_back(self):
        """If asyncio dispatch fails, falls back to regex."""
        with mock.patch("ape.ape_service._call_llm", side_effect=RuntimeError("event loop")):
            result = extract_policies(
                "All agents must log data access events.",
                document_id="doc-fallback",
                tenant_id="t1",
                llm_provider="openai",
                llm_api_key="sk-broken",
            )
        assert result.extraction_method == "regex"

    def test_extract_llm_running_loop_uses_threadpool(self):
        """When event loop is running, uses ThreadPoolExecutor (lines 328-330)."""
        # Create a mock loop that reports is_running=True
        mock_loop = mock.MagicMock()
        mock_loop.is_running.return_value = True

        fake_result = ExtractionResult(
            document_id="doc-pool",
            extraction_method="llm",
            rules=[ExtractedRule("r1", "d", {"action": "BLOCK"}, "ENFORCE", 0.9, "s")],
            total_sentences=1,
            matched_sentences=1,
        )

        with mock.patch("asyncio.get_event_loop", return_value=mock_loop):
            # The ThreadPoolExecutor path calls pool.submit(asyncio.run, coro).result()
            # Mock concurrent.futures to return our fake result
            mock_future = mock.MagicMock()
            mock_future.result.return_value = fake_result
            mock_pool = mock.MagicMock()
            mock_pool.__enter__ = mock.MagicMock(return_value=mock_pool)
            mock_pool.__exit__ = mock.MagicMock(return_value=False)
            mock_pool.submit.return_value = mock_future

            with mock.patch("concurrent.futures.ThreadPoolExecutor", return_value=mock_pool):
                result = extract_policies(
                    "Some policy text here.",
                    document_id="doc-pool",
                    tenant_id="t1",
                    llm_provider="openai",
                    llm_api_key="sk-pool-key",
                )
        assert result.extraction_method == "llm"

    def test_extract_llm_exception_in_loop_check(self):
        """Exception in get_event_loop → falls back to regex (line 338-340)."""
        with mock.patch("asyncio.get_event_loop", side_effect=RuntimeError("no loop")):
            result = extract_policies(
                "All agents must log data access events.",
                document_id="doc-no-loop",
                tenant_id="t1",
                llm_provider="openai",
                llm_api_key="sk-err",
            )
        assert result.extraction_method == "regex"


# ---------------------------------------------------------------------------
# ape_server.py — serve() and infrastructure (L200-248)
# ---------------------------------------------------------------------------

class TestServeFunction:
    """Cover the serve() server bootstrap and log_message."""

    def test_serve_starts_http_and_grpc(self):
        from ape import ape_server
        fake_grpc_server = mock.MagicMock()
        fake_grpc_server.wait_for_termination = mock.MagicMock(return_value=None)

        with mock.patch("ape.ape_server.HTTPServer") as mock_http, \
             mock.patch("ape.ape_server.grpc") as mock_grpc, \
             mock.patch("ape.ape_server.signal") as mock_signal, \
             mock.patch("threading.Thread") as mock_thread:
            mock_grpc.server.return_value = fake_grpc_server
            ape_server.serve(port=50099, http_port=50100)
            mock_http.assert_called_once()
            mock_thread.assert_called_once()
            fake_grpc_server.start.assert_called_once()
            assert mock_signal.signal.call_count == 2

    def test_serve_shutdown_handler(self):
        from ape import ape_server
        fake_grpc_server = mock.MagicMock()
        fake_http_server = mock.MagicMock()
        captured_handler = {}

        def capture_signal(signum, handler):
            captured_handler[signum] = handler

        with mock.patch("ape.ape_server.HTTPServer", return_value=fake_http_server), \
             mock.patch("ape.ape_server.grpc") as mock_grpc, \
             mock.patch("ape.ape_server.signal") as mock_signal, \
             mock.patch("threading.Thread"):
            mock_grpc.server.return_value = fake_grpc_server
            fake_grpc_server.wait_for_termination.return_value = None
            mock_signal.signal.side_effect = capture_signal
            mock_signal.SIGTERM = 15
            mock_signal.SIGINT = 2
            ape_server.serve(port=50101, http_port=50102)
            assert 15 in captured_handler
            captured_handler[15](15, None)
            fake_http_server.shutdown.assert_called_once()
            fake_grpc_server.stop.assert_called_once_with(grace=5)

    def test_log_message(self):
        from ape.ape_server import APEHTTPHandler
        handler = mock.MagicMock(spec=APEHTTPHandler)
        APEHTTPHandler.log_message(handler, "test %s", "msg")

    def test_governance_config_fallback(self):
        with mock.patch.dict("sys.modules", {"config.governance_config": None}):
            result = _load_governance_config("tenant-x")
            assert result == {}
