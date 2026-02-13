"""
Sandbox Client — HTTP bridge to Go backend gVisor sandbox subsystem.

Provides:
  - get_sandbox_status() → GET /api/v1/sandbox/status
  - trigger_speculative_execution() → POST /api/v1/govern
  - Health check with retry logic
"""

import os
import time
import logging
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

# Default to the Go API gateway address
DEFAULT_BACKEND_URL = os.environ.get("OCX_BACKEND_URL", "http://localhost:8080")


class SandboxClient:
    """HTTP client for the Go backend's sandbox and governance endpoints."""

    def __init__(self, backend_url: Optional[str] = None, timeout: int = 10):
        self.backend_url = (backend_url or DEFAULT_BACKEND_URL).rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "X-OCX-Source": "trust-registry-python",
        })

    # -----------------------------------------------------------------
    # Sandbox status
    # -----------------------------------------------------------------
    def get_sandbox_status(self) -> Dict[str, Any]:
        """Fetch gVisor / GhostPool / StateCloner runtime status."""
        url = f"{self.backend_url}/api/v1/sandbox/status"
        try:
            resp = self._session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.warning("Sandbox status request failed: %s", exc)
            return {
                "gvisor_available": False,
                "demo_mode": True,
                "error": str(exc),
            }

    # -----------------------------------------------------------------
    # Speculative execution trigger
    # -----------------------------------------------------------------
    def trigger_speculative_execution(
        self,
        tool_name: str,
        agent_id: str,
        tenant_id: str,
        arguments: Optional[Dict[str, Any]] = None,
        transaction_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Ask the Go governance endpoint to run speculative gVisor execution.

        This bridges the Python ghost-state engine to the Go sandbox runtime.
        """
        url = f"{self.backend_url}/api/v1/govern"
        payload = {
            "tool_name": tool_name,
            "agent_id": agent_id,
            "tenant_id": tenant_id,
            "arguments": arguments or {},
            "protocol": "ghost-state",  # Signals Go backend this came from ghost engine
        }
        headers = {}
        if transaction_id:
            headers["X-Transaction-ID"] = transaction_id

        try:
            resp = self._session.post(
                url, json=payload, headers=headers, timeout=self.timeout
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.error("Speculative execution trigger failed: %s", exc)
            return {
                "verdict": "ERROR",
                "reason": str(exc),
                "speculative_hash": "",
            }

    # -----------------------------------------------------------------
    # Health check with retry
    # -----------------------------------------------------------------
    def health_check(self, retries: int = 3, backoff: float = 1.0) -> bool:
        """Check if the Go backend sandbox subsystem is reachable."""
        for attempt in range(1, retries + 1):
            status = self.get_sandbox_status()
            if "error" not in status:
                logger.info(
                    "Sandbox health check passed (gvisor_available=%s)",
                    status.get("gvisor_available"),
                )
                return True
            logger.warning(
                "Sandbox health check attempt %d/%d failed: %s",
                attempt,
                retries,
                status.get("error"),
            )
            if attempt < retries:
                time.sleep(backoff * attempt)
        return False
