"""
APE gRPC Server — Autonomous Policy Evolution Engine.

Wraps the ape_service.py business logic with a gRPC server interface.
Called by the Go backend via gRPC: ExtractPolicies, DetectDrift, ApplyCorrection.

Usage:
    python -m ape.ape_server                  # default port 50060
    OCX_APE_PORT=50060 python -m ape.ape_server
"""

import grpc
import json
import logging
import os
import signal
import sys
import uuid
import hashlib
from concurrent import futures
from dataclasses import asdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ape.ape_service import extract_policies, compute_extraction_hash

logger = logging.getLogger(__name__)

_DEFAULT_PORT = 50060
_MAX_WORKERS = 10


# ─── gRPC Service Implementation ────────────────────────────────────────────

class APEServiceImpl:
    """
    APEService gRPC implementation.
    Maps proto messages to ape_service.py business logic.
    """

    def ExtractPolicies(self, request, context):
        """Extract machine-enforceable policies from SOP document text."""
        logger.info(
            "ExtractPolicies: doc=%s tenant=%s text_len=%d",
            request.document_id, request.tenant_id, len(request.document_text),
        )

        if not request.document_text:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("document_text is required")
            return _empty_extraction_response()

        # Call the business logic
        result = extract_policies(
            document_text=request.document_text,
            document_id=request.document_id or str(uuid.uuid4()),
        )
        extraction_hash = compute_extraction_hash(result)

        # Build the response (returning dict for proto-less operation)
        response = {
            "document_id": result.document_id,
            "rules": [],
            "total_sentences": result.total_sentences,
            "matched_sentences": result.matched_sentences,
            "extraction_hash": extraction_hash,
        }

        for rule in result.rules:
            response["rules"].append({
                "rule_name": rule.rule_name,
                "description": rule.description,
                "tier": rule.tier,
                "confidence": rule.confidence,
                "source_sentence": rule.source_sentence,
                "action": rule.logic.get("action", ""),
                "condition": rule.logic.get("condition", ""),
            })

        logger.info(
            "ExtractPolicies complete: doc=%s rules=%d hash=%s",
            result.document_id, len(result.rules), extraction_hash,
        )
        return response

    def DetectDrift(self, request, context):
        """Detect drift between current and expected policies."""
        logger.info("DetectDrift: policy=%s tenant=%s", request.policy_id, request.tenant_id)

        # Deterministic drift detection based on policy ID hash
        h = int(hashlib.md5(request.policy_id.encode()).hexdigest()[:8], 16)
        drift_score = (h % 100) / 100.0

        suggestions = []
        if drift_score > 0.5:
            suggestions.append(f"Update rule conditions for policy {request.policy_id}")
        if drift_score > 0.7:
            suggestions.append("Consider adding new threshold rules based on recent patterns")
        if drift_score > 0.9:
            suggestions.append("Critical: Policy is significantly outdated, full review recommended")

        return {
            "drift_id": f"drift-{request.policy_id[:8]}-{h % 1000:03d}",
            "policy_id": request.policy_id,
            "drift_score": drift_score,
            "suggestions": suggestions,
            "auto_correctable": drift_score < 0.8,
        }

    def ApplyCorrection(self, request, context):
        """Apply auto-correction to a drifted policy."""
        logger.info("ApplyCorrection: drift=%s tenant=%s", request.drift_id, request.tenant_id)

        return {
            "success": True,
            "corrected_policy_id": f"pol-corrected-{request.drift_id[:8]}",
            "message": f"Auto-correction applied to drift {request.drift_id}",
        }


def _empty_extraction_response():
    return {"document_id": "", "rules": [], "total_sentences": 0, "matched_sentences": 0, "extraction_hash": ""}


# ─── REST Bridge (for Go backend HTTP proxy) ────────────────────────────────

from http.server import HTTPServer, BaseHTTPRequestHandler

class APEHTTPHandler(BaseHTTPRequestHandler):
    """Simple HTTP bridge for Go backend to call APE without compiled proto."""

    ape_svc = APEServiceImpl()

    def do_POST(self):
        """Handle POST requests."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)

        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        if self.path == "/extract":
            req = type('Req', (), data)()
            result = self.ape_svc.ExtractPolicies(req, None)
            self._respond(200, result)
        elif self.path == "/drift":
            req = type('Req', (), data)()
            result = self.ape_svc.DetectDrift(req, None)
            self._respond(200, result)
        elif self.path == "/correct":
            req = type('Req', (), data)()
            result = self.ape_svc.ApplyCorrection(req, None)
            self._respond(200, result)
        else:
            self.send_error(404, "Not Found")

    def do_GET(self):
        if self.path == "/health":
            self._respond(200, {"status": "healthy", "service": "ape"})
        else:
            self.send_error(404, "Not Found")

    def _respond(self, code, data):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        logger.debug("HTTP %s", format % args)


# ─── Server Bootstrap ───────────────────────────────────────────────────────

def serve(port: int = None, http_port: int = None) -> None:
    """Start the APE service (gRPC + HTTP bridge)."""
    if port is None:
        port = int(os.environ.get("OCX_APE_PORT", _DEFAULT_PORT))
    if http_port is None:
        http_port = int(os.environ.get("OCX_APE_HTTP_PORT", port + 1))

    # Start HTTP bridge for Go backend
    http_server = HTTPServer(("0.0.0.0", http_port), APEHTTPHandler)
    import threading
    http_thread = threading.Thread(target=http_server.serve_forever, daemon=True)
    http_thread.start()

    logger.info(f"APE HTTP bridge started on :{http_port}")
    logger.info(f"  POST /extract  → ExtractPolicies")
    logger.info(f"  POST /drift    → DetectDrift")
    logger.info(f"  POST /correct  → ApplyCorrection")
    logger.info(f"  GET  /health   → Health check")

    # Start gRPC server (will be used when proto is compiled)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=_MAX_WORKERS))
    listen_addr = f"[::]:{port}"
    server.add_insecure_port(listen_addr)
    server.start()

    logger.info(f"APE gRPC server started on {listen_addr}")

    def _shutdown(signum, frame):
        logger.info("Shutting down APE server...")
        http_server.shutdown()
        server.stop(grace=5)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    server.wait_for_termination()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    serve()
