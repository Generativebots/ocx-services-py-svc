"""Tests for shadow-sop/shadow_executor.py — ShadowExecutor"""
import sys, os, unittest, asyncio, json
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shadow_executor import ShadowExecutor, ShadowVerdict, ShadowResult, ShadowMetrics


class TestShadowVerdict(unittest.TestCase):
    def test_values(self):
        self.assertEqual(ShadowVerdict.IDENTICAL.value, "IDENTICAL")
        self.assertEqual(ShadowVerdict.DIVERGENT.value, "DIVERGENT")
        self.assertEqual(ShadowVerdict.SHADOW_ERROR.value, "SHADOW_ERROR")


class TestShadowResult(unittest.TestCase):
    def test_creation(self):
        r = ShadowResult(
            execution_id="e1", sop_id="sop1", tenant_id="t1",
            timestamp=datetime.now(timezone.utc).isoformat(),
            production_output={"result": "ok"},
            shadow_output={"result": "ok"},
            verdict=ShadowVerdict.IDENTICAL,
            latency_prod_ms=50.0, latency_shadow_ms=52.0,
        )
        self.assertEqual(r.verdict, ShadowVerdict.IDENTICAL)
        self.assertEqual(r.sop_id, "sop1")


class TestShadowMetrics(unittest.TestCase):
    def test_defaults(self):
        m = ShadowMetrics(sop_id="sop1")
        self.assertEqual(m.total_executions, 0)
        self.assertEqual(m.identical_count, 0)

    def test_update_identical(self):
        m = ShadowMetrics(sop_id="sop1")
        r = ShadowResult(
            execution_id="e1", sop_id="sop1", tenant_id="t1",
            timestamp="2026-01-01T00:00:00Z",
            production_output={}, shadow_output={},
            verdict=ShadowVerdict.IDENTICAL,
            latency_prod_ms=50.0, latency_shadow_ms=55.0,
        )
        m.update(r)
        self.assertEqual(m.total_executions, 1)
        self.assertEqual(m.identical_count, 1)
        self.assertAlmostEqual(m.confidence_score, 1.0)

    def test_update_divergent(self):
        m = ShadowMetrics(sop_id="sop1")
        r = ShadowResult(
            execution_id="e1", sop_id="sop1", tenant_id="t1",
            timestamp="2026-01-01T00:00:00Z",
            production_output={}, shadow_output={},
            verdict=ShadowVerdict.DIVERGENT,
            latency_prod_ms=50.0, latency_shadow_ms=55.0,
        )
        m.update(r)
        self.assertEqual(m.divergent_count, 1)
        self.assertAlmostEqual(m.divergence_rate, 1.0)


class TestShadowExecutorInit(unittest.TestCase):
    def test_init(self):
        ex = ShadowExecutor()
        self.assertIsInstance(ex.results, dict)
        self.assertIsInstance(ex.metrics, dict)


class TestCompareResults(unittest.TestCase):
    def setUp(self):
        self.executor = ShadowExecutor()

    def test_identical(self):
        v = self.executor.compare_results({"a": 1}, {"a": 1})
        self.assertEqual(v, ShadowVerdict.IDENTICAL)

    def test_both_none(self):
        v = self.executor.compare_results(None, None)
        self.assertEqual(v, ShadowVerdict.IDENTICAL)

    def test_divergent(self):
        v = self.executor.compare_results({"a": 1}, {"a": 2, "b": 3})
        self.assertEqual(v, ShadowVerdict.DIVERGENT)

    def test_equivalent_small_diff(self):
        # Same keys, only 1 out of 20 values differs → ≤10% → EQUIVALENT
        prod = {f"k{i}": i for i in range(20)}
        shadow = {f"k{i}": i for i in range(20)}
        shadow["k0"] = 999  # 1 diff out of 20 = 5%
        v = self.executor.compare_results(prod, shadow)
        self.assertEqual(v, ShadowVerdict.EQUIVALENT)


class TestGetMetrics(unittest.TestCase):
    def test_none_for_unknown(self):
        ex = ShadowExecutor()
        self.assertIsNone(ex.get_metrics("nonexistent"))


class TestShouldPromote(unittest.TestCase):
    def test_not_enough_executions(self):
        ex = ShadowExecutor()
        self.assertFalse(ex.should_promote("sop1"))

    def test_high_confidence_promotes(self):
        ex = ShadowExecutor()
        m = ShadowMetrics(sop_id="sop1")
        m.total_executions = 200
        m.identical_count = 198
        m.equivalent_count = 2
        m.confidence_score = 1.0
        ex.metrics["sop1"] = m
        self.assertTrue(ex.should_promote("sop1"))


class TestExecuteShadow(unittest.TestCase):
    def test_async_execution(self):
        ex = ShadowExecutor()

        async def prod_handler(payload):
            return {"result": "prod"}

        async def shadow_handler(payload):
            return {"result": "prod"}

        async def _run():
            return await ex.execute_shadow(
                sop_id="sop1", tenant_id="t1",
                request_payload={"input": "test"},
                prod_handler=prod_handler,
                shadow_handler=shadow_handler,
            )

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertIsInstance(result, ShadowResult)
        self.assertEqual(result.sop_id, "sop1")
        self.assertEqual(result.verdict, ShadowVerdict.IDENTICAL)

    def test_shadow_error_caught(self):
        ex = ShadowExecutor()

        async def prod_handler(payload):
            return {"result": "ok"}

        async def shadow_handler(payload):
            raise RuntimeError("shadow crashed")

        async def _run():
            return await ex.execute_shadow(
                sop_id="sop1", tenant_id="t1",
                request_payload={},
                prod_handler=prod_handler,
                shadow_handler=shadow_handler,
            )

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(result.verdict, ShadowVerdict.SHADOW_ERROR)


if __name__ == "__main__":
    unittest.main()
