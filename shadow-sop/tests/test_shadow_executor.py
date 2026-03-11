"""
Shadow Executor — Patent Claim 13 (SOP Drift Detection).
Tests: ShadowExecutor, compare_results, metrics, should_promote.
"""

import pytest
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shadow_executor import (
    ShadowExecutor, ShadowVerdict, ShadowResult, ShadowMetrics,
)


# -------------------------------------------------------------------
# ShadowVerdict enum
# -------------------------------------------------------------------
class TestShadowVerdict:
    def test_all_variants(self):
        assert ShadowVerdict.IDENTICAL.value == "IDENTICAL"
        assert ShadowVerdict.EQUIVALENT.value == "EQUIVALENT"
        assert ShadowVerdict.DIVERGENT.value == "DIVERGENT"
        assert ShadowVerdict.SHADOW_BETTER.value == "SHADOW_BETTER"
        assert ShadowVerdict.SHADOW_WORSE.value == "SHADOW_WORSE"
        assert ShadowVerdict.SHADOW_ERROR.value == "SHADOW_ERROR"


# -------------------------------------------------------------------
# ShadowMetrics.update
# -------------------------------------------------------------------
class TestShadowMetrics:
    def _make_result(self, verdict=ShadowVerdict.IDENTICAL, prod_ms=10.0, shadow_ms=12.0):
        return ShadowResult(
            execution_id="ex-1", sop_id="SOP-A", tenant_id="t1",
            timestamp="2026-01-01T00:00:00Z",
            production_output={"result": "ok"},
            shadow_output={"result": "ok"},
            verdict=verdict,
            latency_prod_ms=prod_ms, latency_shadow_ms=shadow_ms,
        )

    def test_update_identical(self):
        m = ShadowMetrics(sop_id="SOP-A")
        m.update(self._make_result(ShadowVerdict.IDENTICAL))
        assert m.total_executions == 1
        assert m.identical_count == 1
        assert m.divergence_rate == 0.0

    def test_update_divergent(self):
        m = ShadowMetrics(sop_id="SOP-A")
        m.update(self._make_result(ShadowVerdict.DIVERGENT))
        assert m.divergent_count == 1
        assert m.divergence_rate == 1.0

    def test_confidence_calculation(self):
        m = ShadowMetrics(sop_id="SOP-A")
        for _ in range(9):
            m.update(self._make_result(ShadowVerdict.IDENTICAL))
        m.update(self._make_result(ShadowVerdict.DIVERGENT))
        assert m.confidence_score == 0.9
        assert m.divergence_rate == 0.1


# -------------------------------------------------------------------
# ShadowExecutor.compare_results
# -------------------------------------------------------------------
class TestCompareResults:
    def _executor(self):
        return ShadowExecutor()

    def test_both_none_identical(self):
        assert self._executor().compare_results(None, None) == ShadowVerdict.IDENTICAL

    def test_identical_dicts(self):
        prod = {"status": "ok", "amount": 100}
        shadow = {"status": "ok", "amount": 100}
        assert self._executor().compare_results(prod, shadow) == ShadowVerdict.IDENTICAL

    def test_equivalent_dicts(self):
        """Same keys, minor value differences → EQUIVALENT."""
        prod = {f"k{i}": i for i in range(20)}
        shadow = {f"k{i}": i for i in range(20)}
        shadow["k0"] = 999  # 1 out of 20 keys differ = 5% < 10%
        assert self._executor().compare_results(prod, shadow) == ShadowVerdict.EQUIVALENT

    def test_divergent_dicts(self):
        prod = {"a": 1, "b": 2, "c": 3}
        shadow = {"a": 99, "b": 99, "c": 99}
        assert self._executor().compare_results(prod, shadow) == ShadowVerdict.DIVERGENT

    def test_different_keys_divergent(self):
        prod = {"a": 1, "b": 2}
        shadow = {"x": 1, "y": 2}
        assert self._executor().compare_results(prod, shadow) == ShadowVerdict.DIVERGENT


# -------------------------------------------------------------------
# ShadowExecutor.execute_shadow (async)
# -------------------------------------------------------------------
class TestExecuteShadow:
    def test_execute_shadow_identical(self):
        executor = ShadowExecutor()

        async def prod_handler(payload):
            return {"result": "approved", "amount": payload["amount"]}

        async def shadow_handler(payload):
            return {"result": "approved", "amount": payload["amount"]}

        async def _run():
            return await executor.execute_shadow(
                sop_id="SOP-A", tenant_id="t1",
                request_payload={"amount": 500},
                prod_handler=prod_handler,
                shadow_handler=shadow_handler,
            )

        result = asyncio.get_event_loop().run_until_complete(_run())
        assert result.verdict == ShadowVerdict.IDENTICAL
        assert result.latency_prod_ms > 0

    def test_execute_shadow_error(self):
        executor = ShadowExecutor()

        async def prod_handler(payload):
            return {"result": "ok"}

        async def shadow_handler(payload):
            raise RuntimeError("Shadow pipeline crashed")

        async def _run():
            return await executor.execute_shadow(
                sop_id="SOP-B", tenant_id="t1",
                request_payload={},
                prod_handler=prod_handler,
                shadow_handler=shadow_handler,
            )

        result = asyncio.get_event_loop().run_until_complete(_run())
        assert result.verdict == ShadowVerdict.SHADOW_ERROR


# -------------------------------------------------------------------
# ShadowExecutor.should_promote
# -------------------------------------------------------------------
class TestShouldPromote:
    def test_no_metrics_returns_false(self):
        assert ShadowExecutor().should_promote("SOP-A") is False

    def test_insufficient_executions(self):
        executor = ShadowExecutor()
        executor.metrics["SOP-A"] = ShadowMetrics(
            sop_id="SOP-A", total_executions=10,
            confidence_score=1.0, shadow_error_count=0
        )
        assert executor.should_promote("SOP-A") is False

    def test_promote_ready(self):
        executor = ShadowExecutor()
        executor.metrics["SOP-A"] = ShadowMetrics(
            sop_id="SOP-A", total_executions=200,
            identical_count=190, equivalent_count=10,
            confidence_score=1.0, shadow_error_count=0
        )
        assert executor.should_promote("SOP-A") is True

    def test_errors_block_promotion(self):
        executor = ShadowExecutor()
        executor.metrics["SOP-A"] = ShadowMetrics(
            sop_id="SOP-A", total_executions=200,
            confidence_score=0.98, shadow_error_count=1
        )
        assert executor.should_promote("SOP-A") is False
