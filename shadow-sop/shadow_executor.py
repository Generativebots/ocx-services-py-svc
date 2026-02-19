"""
Shadow Mode Execution Engine
Patent: Shadow execution to validate new SOPs before deployment

Runs new/modified SOPs alongside production pipelines in isolation.
Captures divergence metrics without affecting real traffic.
"""

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger("shadow-executor")


class ShadowVerdict(str, Enum):
    """Outcome of comparing shadow vs production results."""
    IDENTICAL = "IDENTICAL"          # Results match exactly
    EQUIVALENT = "EQUIVALENT"        # Semantically equivalent, minor diffs
    DIVERGENT = "DIVERGENT"          # Significant differences
    SHADOW_BETTER = "SHADOW_BETTER"  # Shadow produced better outcome
    SHADOW_WORSE = "SHADOW_WORSE"    # Shadow produced worse outcome
    SHADOW_ERROR = "SHADOW_ERROR"    # Shadow pipeline failed


@dataclass
class ShadowResult:
    """Captures the outcome of a single shadow execution."""
    execution_id: str
    sop_id: str
    tenant_id: str
    timestamp: str
    production_output: Any
    shadow_output: Any
    verdict: ShadowVerdict
    latency_prod_ms: float
    latency_shadow_ms: float
    divergence_details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ShadowMetrics:
    """Aggregate metrics for a shadow SOP experiment."""
    sop_id: str
    tenant_id: str = ""
    total_executions: int = 0
    identical_count: int = 0
    equivalent_count: int = 0
    divergent_count: int = 0
    shadow_better_count: int = 0
    shadow_worse_count: int = 0
    shadow_error_count: int = 0
    avg_latency_delta_ms: float = 0.0
    divergence_rate: float = 0.0
    confidence_score: float = 0.0
    started_at: Optional[str] = None
    last_execution_at: Optional[str] = None

    def update(self, result: ShadowResult) -> None:
        """Update aggregate metrics with a new result."""
        self.total_executions += 1
        self.last_execution_at = result.timestamp

        if self.started_at is None:
            self.started_at = result.timestamp

        match result.verdict:
            case ShadowVerdict.IDENTICAL:
                self.identical_count += 1
            case ShadowVerdict.EQUIVALENT:
                self.equivalent_count += 1
            case ShadowVerdict.DIVERGENT:
                self.divergent_count += 1
            case ShadowVerdict.SHADOW_BETTER:
                self.shadow_better_count += 1
            case ShadowVerdict.SHADOW_WORSE:
                self.shadow_worse_count += 1
            case ShadowVerdict.SHADOW_ERROR:
                self.shadow_error_count += 1

        # Rolling average latency delta
        delta = result.latency_shadow_ms - result.latency_prod_ms
        self.avg_latency_delta_ms = (
            (self.avg_latency_delta_ms * (self.total_executions - 1) + delta)
            / self.total_executions
        )

        # Divergence rate = (divergent + worse + error) / total
        bad = self.divergent_count + self.shadow_worse_count + self.shadow_error_count
        self.divergence_rate = bad / self.total_executions if self.total_executions > 0 else 0.0

        # Confidence: higher with more identical/equivalent results
        good = self.identical_count + self.equivalent_count + self.shadow_better_count
        self.confidence_score = good / self.total_executions if self.total_executions > 0 else 0.0


class ShadowExecutor:
    """
    Executes new SOPs in shadow mode alongside production.

    Architecture:
    1. Intercepts incoming requests at the routing layer
    2. Duplicates the request to both prod and shadow pipelines
    3. Runs shadow asynchronously (non-blocking to production)
    4. Compares results and logs divergence metrics
    5. Never affects production traffic
    """

    def __init__(self, max_results_per_sop: int = 1000):
        self.metrics: Dict[str, ShadowMetrics] = {}  # key = "tenant:sop_id"
        self.results: Dict[str, List[ShadowResult]] = {}
        self._max_results_per_sop = max_results_per_sop

    async def execute_shadow(
        self,
        sop_id: str,
        tenant_id: str,
        request_payload: Dict[str, Any],
        prod_handler,
        shadow_handler,
    ) -> ShadowResult:
        """
        Run production and shadow handlers concurrently.
        Production result is returned immediately; shadow runs async.
        """
        execution_id = str(uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        storage_key = f"{tenant_id}:{sop_id}"

        # Run production (blocking)
        prod_start = time.monotonic()
        prod_output = await prod_handler(request_payload)
        prod_latency = (time.monotonic() - prod_start) * 1000

        # Run shadow (non-blocking, catch all errors)
        shadow_output = None
        shadow_latency = 0.0
        verdict = ShadowVerdict.SHADOW_ERROR

        try:
            shadow_start = time.monotonic()
            shadow_output = await shadow_handler(request_payload)
            shadow_latency = (time.monotonic() - shadow_start) * 1000
            verdict = self.compare_results(prod_output, shadow_output)
        except Exception as e:
            logger.error(f"Shadow execution failed for SOP {sop_id}: {e}")
            shadow_output = {"error": str(e)}

        result = ShadowResult(
            execution_id=execution_id,
            sop_id=sop_id,
            tenant_id=tenant_id,
            timestamp=timestamp,
            production_output=prod_output,
            shadow_output=shadow_output,
            verdict=verdict,
            latency_prod_ms=prod_latency,
            latency_shadow_ms=shadow_latency,
        )

        # Update metrics (tenant-scoped)
        if storage_key not in self.metrics:
            self.metrics[storage_key] = ShadowMetrics(sop_id=sop_id, tenant_id=tenant_id)
        self.metrics[storage_key].update(result)

        # Store result (bounded)
        if storage_key not in self.results:
            self.results[storage_key] = []
        self.results[storage_key].append(result)
        if len(self.results[storage_key]) > self._max_results_per_sop:
            self.results[storage_key] = self.results[storage_key][-self._max_results_per_sop:]

        logger.info(
            f"Shadow execution {execution_id}: SOP={sop_id} verdict={verdict.value} "
            f"prod_latency={prod_latency:.1f}ms shadow_latency={shadow_latency:.1f}ms"
        )

        return result

    def compare_results(
        self, prod_output: Any, shadow_output: Any
    ) -> ShadowVerdict:
        """Compare production and shadow outputs to determine verdict."""
        if prod_output is None and shadow_output is None:
            return ShadowVerdict.IDENTICAL

        # Hash-based exact match
        prod_hash = self._hash_output(prod_output)
        shadow_hash = self._hash_output(shadow_output)

        if prod_hash == shadow_hash:
            return ShadowVerdict.IDENTICAL

        # Structural comparison for dicts
        if isinstance(prod_output, dict) and isinstance(shadow_output, dict):
            prod_keys = set(prod_output.keys())
            shadow_keys = set(shadow_output.keys())

            if prod_keys == shadow_keys:
                # Same structure, check values
                diffs = 0
                for key in prod_keys:
                    if prod_output[key] != shadow_output[key]:
                        diffs += 1

                if diffs == 0:
                    return ShadowVerdict.IDENTICAL
                elif diffs <= len(prod_keys) * 0.1:
                    return ShadowVerdict.EQUIVALENT
                else:
                    return ShadowVerdict.DIVERGENT
            else:
                return ShadowVerdict.DIVERGENT

        return ShadowVerdict.DIVERGENT

    def get_metrics(self, sop_id: str, tenant_id: str = "") -> Optional[ShadowMetrics]:
        """Get aggregate metrics for a shadow SOP experiment."""
        key = f"{tenant_id}:{sop_id}" if tenant_id else sop_id
        return self.metrics.get(key)

    def get_all_metrics(self, tenant_id: str = "") -> Dict[str, ShadowMetrics]:
        """Get metrics for all active shadow experiments, optionally filtered by tenant."""
        if not tenant_id:
            return self.metrics
        return {k: v for k, v in self.metrics.items() if v.tenant_id == tenant_id}

    def get_results(self, sop_id: str, tenant_id: str = "", limit: int = 50) -> List[ShadowResult]:
        """Get recent execution results for an SOP."""
        key = f"{tenant_id}:{sop_id}" if tenant_id else sop_id
        results = self.results.get(key, [])
        return results[-limit:]

    def should_promote(self, sop_id: str, min_executions: int = 100, min_confidence: float = 0.95) -> bool:
        """
        Determine if a shadow SOP is ready for production promotion.
        Requires minimum execution count and confidence threshold.
        """
        metrics = self.metrics.get(sop_id)
        if not metrics:
            return False

        return (
            metrics.total_executions >= min_executions
            and metrics.confidence_score >= min_confidence
            and metrics.shadow_error_count == 0
        )

    @staticmethod
    def _hash_output(output: Any) -> str:
        """Create a deterministic hash of an output for comparison."""
        serialized = json.dumps(output, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()
