"""
RLHC gRPC Server — Reinforcement Learning from Human Corrections.

Wraps the rlhc_service.py business logic with a gRPC server interface.
Called by the Go backend via gRPC: ClusterDecisions, GetPatterns, UpdatePatternStatus.

Usage:
    python -m rlhc.rlhc_server                  # default port 50062
    OCX_RLHC_PORT=50062 python -m rlhc.rlhc_server
"""

import grpc
import json
import logging
import os
import signal
import sys
import uuid
from concurrent import futures

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rlhc.rlhc_service import cluster_decisions, HITLDecision

logger = logging.getLogger(__name__)

_DEFAULT_PORT = 50062
_MAX_WORKERS = int(os.getenv("RLHC_MAX_WORKERS", str(max(4, (os.cpu_count() or 2) * 2))))

# In-memory pattern store (upgraded to DB in production)
_pattern_store: dict = {}


# ─── gRPC Service Implementation ────────────────────────────────────────────

class RLHCServiceImpl:
    """
    RLHCService gRPC implementation.
    Maps proto messages to rlhc_service.py business logic.
    """

    def ClusterDecisions(self, request, context):
        """Cluster HITL decisions into patterns suggesting new policies."""
        logger.info(
            "ClusterDecisions: analysis=%s tenant=%s decisions=%d",
            request.get("analysis_id", "auto") if isinstance(request, dict) else getattr(request, "analysis_id", "auto"),
            request.get("tenant_id", "") if isinstance(request, dict) else getattr(request, "tenant_id", ""),
            len(request.get("decisions", [])) if isinstance(request, dict) else len(getattr(request, "decisions", [])),
        )

        # Convert proto/dict decisions to business objects
        raw_decisions = request.get("decisions", []) if isinstance(request, dict) else getattr(request, "decisions", [])
        decisions = []
        for d in raw_decisions:
            if isinstance(d, dict):
                decisions.append(HITLDecision(**d))
            else:
                decisions.append(HITLDecision(
                    decision_id=d.decision_id,
                    agent_id=d.agent_id,
                    tool_name=d.tool_name,
                    original_verdict=d.original_verdict,
                    override_action=d.override_action,
                    reason=d.reason,
                    trust_score=d.trust_score,
                ))

        analysis_id = (
            request.get("analysis_id") if isinstance(request, dict)
            else getattr(request, "analysis_id", None)
        ) or f"rlhc-{uuid.uuid4().hex[:8]}"

        min_freq = (
            request.get("min_frequency", 2) if isinstance(request, dict)
            else getattr(request, "min_frequency", 2)
        )
        min_conf = (
            request.get("min_confidence", 0.6) if isinstance(request, dict)
            else getattr(request, "min_confidence", 0.6)
        )

        # Call business logic
        result = cluster_decisions(
            decisions=decisions,
            analysis_id=analysis_id,
            min_frequency=max(1, min_freq),
            min_confidence=min_conf,
        )

        # Store patterns
        for p in result.patterns:
            _pattern_store[p.pattern_id] = p

        # Build response
        response = {
            "analysis_id": result.analysis_id,
            "patterns": [],
            "total_decisions": result.total_decisions,
            "clusters_found": result.clusters_found,
        }

        for pat in result.patterns:
            response["patterns"].append({
                "pattern_id": pat.pattern_id,
                "description": pat.description,
                "frequency": pat.frequency,
                "confidence": pat.confidence,
                "condition": pat.suggested_rule.get("condition", ""),
                "action": pat.suggested_rule.get("action", ""),
                "auto_apply": pat.suggested_rule.get("auto_apply", False),
                "source_decision_ids": pat.source_decisions[:10],
                "status": pat.status,
            })

        logger.info(
            "ClusterDecisions complete: analysis=%s patterns=%d",
            result.analysis_id, len(result.patterns),
        )
        return response

    def GetPatterns(self, request, context):
        """Get existing pattern suggestions."""
        status_filter = (
            request.get("status_filter", "") if isinstance(request, dict)
            else getattr(request, "status_filter", "")
        )

        patterns = []
        for pat in _pattern_store.values():
            if status_filter and pat.status != status_filter:
                continue
            patterns.append({
                "pattern_id": pat.pattern_id,
                "description": pat.description,
                "frequency": pat.frequency,
                "confidence": pat.confidence,
                "condition": pat.suggested_rule.get("condition", ""),
                "action": pat.suggested_rule.get("action", ""),
                "auto_apply": pat.suggested_rule.get("auto_apply", False),
                "source_decision_ids": pat.source_decisions[:10],
                "status": pat.status,
            })

        return {"patterns": patterns}

    def UpdatePatternStatus(self, request, context):
        """Approve or reject a pattern suggestion."""
        pattern_id = request.get("pattern_id") if isinstance(request, dict) else getattr(request, "pattern_id", "")
        new_status = request.get("status") if isinstance(request, dict) else getattr(request, "status", "")

        if pattern_id not in _pattern_store:
            return {"success": False, "message": f"Pattern {pattern_id} not found"}

        if new_status not in ("APPROVED", "REJECTED"):
            return {"success": False, "message": f"Invalid status: {new_status}"}

        _pattern_store[pattern_id].status = new_status
        logger.info("Pattern %s status updated to %s", pattern_id, new_status)

        return {"success": True, "message": f"Pattern {pattern_id} → {new_status}"}


# ─── REST Bridge (for Go backend HTTP proxy) ────────────────────────────────

from http.server import HTTPServer, BaseHTTPRequestHandler


class RLHCHTTPHandler(BaseHTTPRequestHandler):
    """Simple HTTP bridge for Go backend to call RLHC without compiled proto."""

    rlhc_svc = RLHCServiceImpl()

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)

        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        if self.path == "/cluster":
            result = self.rlhc_svc.ClusterDecisions(data, None)
            self._respond(200, result)
        elif self.path == "/patterns":
            result = self.rlhc_svc.GetPatterns(data, None)
            self._respond(200, result)
        elif self.path == "/patterns/status":
            result = self.rlhc_svc.UpdatePatternStatus(data, None)
            self._respond(200, result)
        else:
            self.send_error(404, "Not Found")

    def do_GET(self):
        if self.path == "/health":
            self._respond(200, {"status": "healthy", "service": "rlhc"})
        elif self.path.startswith("/patterns"):
            result = self.rlhc_svc.GetPatterns({}, None)
            self._respond(200, result)
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
    """Start the RLHC service (gRPC + HTTP bridge)."""
    if port is None:
        port = int(os.environ.get("OCX_RLHC_PORT", _DEFAULT_PORT))
    if http_port is None:
        http_port = int(os.environ.get("OCX_RLHC_HTTP_PORT", port + 1))

    # Start HTTP bridge
    http_server = HTTPServer(("0.0.0.0", http_port), RLHCHTTPHandler)
    import threading
    http_thread = threading.Thread(target=http_server.serve_forever, daemon=True)
    http_thread.start()

    logger.info(f"RLHC HTTP bridge started on :{http_port}")
    logger.info(f"  POST /cluster          → ClusterDecisions")
    logger.info(f"  GET  /patterns         → GetPatterns")
    logger.info(f"  POST /patterns/status  → UpdatePatternStatus")
    logger.info(f"  GET  /health           → Health check")

    # gRPC server
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=_MAX_WORKERS))
    listen_addr = f"[::]:{port}"
    server.add_insecure_port(listen_addr)
    server.start()

    logger.info(f"RLHC gRPC server started on {listen_addr}")

    def _shutdown(signum, frame):
        logger.info("Shutting down RLHC server...")
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
