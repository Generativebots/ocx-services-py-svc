"""
Jury Auditor gRPC Server - Real-Time Cognitive Audit

C1+C2 FIX: Service now inherits from generated JuryAuditorServicer and
registers with gRPC server. Returns proper AuditResponse proto objects.

C3 FIX: _execute_llm_audit() now makes real HTTP calls to vLLM/OpenAI
endpoint instead of returning hardcoded PASS verdicts.
"""

import grpc
from concurrent import futures
import json
import logging
import os
import time
from typing import Dict

# Import generated protobuf code (C1+C2 FIX: no longer commented out)
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from proto import jury_pb2
from proto import jury_pb2_grpc

logger = logging.getLogger(__name__)


class JuryAuditorService(jury_pb2_grpc.JuryAuditorServicer):
    """
    gRPC service for real-time cognitive auditing.

    C1+C2 FIX: Now inherits from JuryAuditorServicer so gRPC dispatches
    AuditIntent and StreamAudit calls to this service.

    Integrates with:
    - APE Engine (policy loading)
    - vLLM (cognitive reasoning)
    - Escrow Gate (verdict delivery)
    """

    def __init__(self, policy_file: str = None, llm_endpoint: str = None) -> None:
        """
        Initialize Jury Auditor.

        Args:
            policy_file: Path to APE-extracted policies (JSON).
                         If None or file missing, uses empty default.
            llm_endpoint: vLLM/OpenAI endpoint for cognitive reasoning.
                          Falls back to VLLM_BASE_URL env var.
        """
        if llm_endpoint is None:
            llm_endpoint = os.getenv("VLLM_BASE_URL", "http://localhost:8000")
        self.llm_endpoint = llm_endpoint

        # Load policies from APE Engine
        if policy_file is None:
            policy_file = os.getenv("APE_POLICY_FILE", "ape_policies.json")

        try:
            with open(policy_file, 'r') as f:
                self.active_policies = json.load(f)
            logger.info(f"Jury Auditor: loaded {len(self.active_policies)} policies from {policy_file}")
        except FileNotFoundError:
            logger.warning(f"Policy file '{policy_file}' not found — using empty default policies")
            self.active_policies = {"default": {
                "name": "Default Policy",
                "allowed_actions": ["*"],
                "max_transaction_value": 100000,
                "require_attestation": False,
            }}

        # Track whether LLM endpoint is reachable
        self._llm_available = None

        logger.info(f"Jury Auditor initialized (LLM endpoint: {self.llm_endpoint})")

    def AuditIntent(self, request, context) -> None:
        """
        gRPC method: Audit agent intent against policy.

        C1+C2 FIX: Now receives proper AuditRequest proto and returns
        AuditResponse proto instead of a dict.

        Args:
            request: AuditRequest protobuf
            context: gRPC ServicerContext

        Returns:
            AuditResponse protobuf
        """
        start_time = time.time()

        # Handle both proto objects and dict-like objects
        tx_id = getattr(request, 'transaction_id', '')
        agent_id = getattr(request, 'agent_id', '')
        tool_name = getattr(request, 'tool_name', '')
        parameters = getattr(request, 'parameters', {})
        req_context = getattr(request, 'context', {})

        logger.info(f"Auditing transaction: {tx_id} (agent: {agent_id}, tool: {tool_name})")

        # 1. Retrieve relevant policy
        relevant_policy = self._get_relevant_policy(tool_name)

        # 2. Construct cognitive audit prompt
        prompt = self._construct_audit_prompt(
            tx_id, agent_id, tool_name,
            dict(parameters) if hasattr(parameters, 'items') else parameters,
            dict(req_context) if hasattr(req_context, 'items') else req_context,
            relevant_policy,
        )

        # 3. Execute LLM audit (C3 FIX: real HTTP call)
        verdict_data = self._execute_llm_audit(prompt)

        # 4. Parse verdict
        verdict = verdict_data.get('verdict', 'FAIL')
        confidence = verdict_data.get('confidence', 0.0)
        reason = verdict_data.get('reason', 'Unknown')

        audit_time = time.time() - start_time

        logger.info(
            f"Audit complete: {tx_id} -> {verdict} "
            f"(confidence: {confidence:.2f}, took {audit_time:.3f}s)"
        )

        # C1+C2 FIX: Return proper proto response
        return jury_pb2.AuditResponse(
            transaction_id=tx_id,
            verdict=verdict,
            confidence=confidence,
            reason=reason,
            audit_time=audit_time,
        )

    def _get_relevant_policy(self, tool_name: str) -> Dict:
        """Retrieve policy for the detected tool."""
        return self.active_policies.get(
            tool_name, self.active_policies.get('default', {})
        )

    def _construct_audit_prompt(
        self, tx_id: str, agent_id: str, tool_name: str,
        parameters: dict, req_context: dict, policy: Dict
    ) -> str:
        """Construct cognitive audit prompt for LLM."""
        prompt = f"""SYSTEM: You are the OCX Jury. Your task is to audit Agent Intent against Enterprise Policy.

POLICY:
{json.dumps(policy, indent=2)}

AGENT INTENT:
- Transaction ID: {tx_id}
- Agent ID: {agent_id}
- Tool: {tool_name}
- Parameters: {json.dumps(parameters)}
- Context: {json.dumps(req_context)}

VERDICT RULE: Respond ONLY with a JSON object:
{{
    "verdict": "PASS" or "FAIL",
    "confidence": 0.0 to 1.0,
    "reason": "brief explanation"
}}

ANALYSIS:
"""
        return prompt

    def _execute_llm_audit(self, prompt: str) -> Dict:
        """
        Execute LLM audit via vLLM or OpenAI-compatible endpoint.

        C3 FIX: Makes real HTTP call instead of returning hardcoded PASS.
        Falls back to rule-based evaluation if LLM is unavailable.
        """
        import requests

        try:
            response = requests.post(
                f"{self.llm_endpoint}/v1/completions",
                json={
                    "prompt": prompt,
                    "temperature": 0,
                    "max_tokens": 256,
                    "stop": ["}"],
                },
                timeout=10,
            )
            response.raise_for_status()

            result = response.json()
            text = result.get("choices", [{}])[0].get("text", "")
            # The model should return JSON; append the closing brace we stopped at
            text = text.strip() + "}"

            verdict_data = json.loads(text)
            self._llm_available = True
            logger.debug(f"LLM verdict received: {verdict_data}")
            return verdict_data

        except requests.exceptions.ConnectionError:
            if self._llm_available is not False:
                logger.warning(
                    f"LLM endpoint {self.llm_endpoint} unreachable — "
                    "falling back to rule-based audit"
                )
                self._llm_available = False
            return self._rule_based_fallback(prompt)

        except (requests.exceptions.RequestException, json.JSONDecodeError, KeyError) as e:
            logger.warning(f"LLM audit error: {e} — falling back to rule-based audit")
            return self._rule_based_fallback(prompt)

    def _rule_based_fallback(self, prompt: str) -> Dict:
        """
        Rule-based fallback when LLM is unavailable.
        Returns a conservative verdict based on prompt content analysis.

        This ensures the Jury never auto-approves blindly — it applies
        basic heuristics until the LLM endpoint is available.
        """
        # Extract tool name from prompt
        prompt_lower = prompt.lower()

        # High-risk patterns → FAIL
        high_risk_keywords = [
            "delete", "drop", "truncate", "rm -rf", "shutdown",
            "sudo", "admin", "root", "credential", "secret",
            "transfer_funds", "withdraw", "escalate_privilege",
        ]
        for keyword in high_risk_keywords:
            if keyword in prompt_lower:
                return {
                    "verdict": "FAIL",
                    "confidence": 0.70,
                    "reason": f"Rule-based: high-risk keyword '{keyword}' detected (LLM unavailable)",
                }

        # Medium-risk: unknown tools → HOLD-like verdict (FAIL with low confidence)
        if "tool: unknown" in prompt_lower or "tool: " not in prompt_lower:
            return {
                "verdict": "FAIL",
                "confidence": 0.40,
                "reason": "Rule-based: unknown tool — cannot verify intent (LLM unavailable)",
            }

        # Low-risk patterns → PASS with reduced confidence
        return {
            "verdict": "PASS",
            "confidence": 0.60,
            "reason": "Rule-based: no high-risk patterns detected (LLM unavailable — reduced confidence)",
        }

    def StreamAudit(self, request_iterator, context) -> None:
        """
        gRPC streaming method: Audit multiple transactions in parallel.

        C1+C2 FIX: Now returns proper AuditResponse proto objects.
        """
        for request in request_iterator:
            yield self.AuditIntent(request, context)


def serve(port: int = 50051, health_port: int = None) -> None:
    """
    Start gRPC server for Jury Auditor.

    C1+C2 FIX: Server now registers JuryAuditorService with the gRPC server.
    L2 FIX: Added gRPC health checking + HTTP health sidecar for container orchestrators.
    """
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    # C1+C2 FIX: Service is now registered (previously commented out)
    service = JuryAuditorService()
    jury_pb2_grpc.add_JuryAuditorServicer_to_server(service, server)

    # L2 FIX: Register gRPC health checking service
    try:
        from grpc_health.v1 import health as grpc_health
        from grpc_health.v1 import health_pb2 as health_pb2
        from grpc_health.v1 import health_pb2_grpc as health_pb2_grpc

        health_servicer = grpc_health.HealthServicer()
        health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
        # Mark the service as SERVING
        health_servicer.set(
            "jury.JuryAuditor",
            health_pb2.HealthCheckResponse.SERVING,
        )
        health_servicer.set(
            "",  # overall server health
            health_pb2.HealthCheckResponse.SERVING,
        )
        logger.info("✅ gRPC health checking service registered")
    except ImportError:
        logger.warning("⚠️  grpcio-health-checking not installed, gRPC health checks unavailable")

    # L2 FIX: Start HTTP health sidecar on a separate port
    if health_port is None:
        health_port = port + 1  # e.g., 50052 if gRPC is on 50051
    _start_http_health_sidecar(health_port)

    server.add_insecure_port(f'[::]:{port}')
    server.start()

    logger.info(f"OCX Jury Auditor Active: Listening on port {port}")
    logger.info(f"HTTP health check available at http://localhost:{health_port}/health")
    logger.info("Auditing in Parallel with gVisor Execution...")

    server.wait_for_termination()


def _start_http_health_sidecar(port: int) -> None:
    """Start a lightweight HTTP server for health checks (runs in background thread)."""
    import threading
    from http.server import HTTPServer, BaseHTTPRequestHandler

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/health":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                import json
                self.wfile.write(json.dumps({
                    "status": "ok",
                    "service": "jury",
                    "type": "grpc",
                }).encode())
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args) -> None:
            pass  # Suppress HTTP access logs

    def run_server() -> None:
        httpd = HTTPServer(("0.0.0.0", port), HealthHandler)
        httpd.serve_forever()

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    logger.info(f"🏥 HTTP health sidecar started on port {port}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    serve()
