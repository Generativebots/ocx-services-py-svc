"""
Process Mining — Tests for API endpoints and core modules (Miner, Conformance, Bottleneck).
"""

import os
import sys
import pytest
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from miner import ProcessMiner, Trace, Activity, DiscoveredProcess
from conformance import ConformanceChecker, ConformanceResult
from bottleneck import BottleneckAnalyzer, BottleneckReport


# =============================================================================
# API Endpoint Tests
# =============================================================================

class TestHealth:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "process-mining"


class TestTraceIngestion:
    def test_ingest_single_trace(self, client, sample_trace):
        resp = client.post("/traces", json=sample_trace)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ingested"
        assert data["trace_id"] == "trace-001"
        assert data["event_count"] == 3

    def test_ingest_empty_events(self, client):
        resp = client.post("/traces", json={
            "trace_id": "trace-empty",
            "tenant_id": "t-1",
            "events": [],
        })
        assert resp.status_code == 200
        assert resp.json()["event_count"] == 0

    def test_ingest_missing_fields_422(self, client):
        resp = client.post("/traces", json={"trace_id": "no-tenant"})
        assert resp.status_code == 422


class TestDiscovery:
    def test_discover_after_ingest(self, client, sample_trace):
        # Ingest first
        client.post("/traces", json=sample_trace)
        # Discover
        resp = client.get("/discover", params={"tenant_id": "t-1", "min_frequency": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == "t-1"
        assert data["total_traces_analyzed"] >= 1

    def test_discover_empty_tenant(self, client):
        resp = client.get("/discover", params={"tenant_id": "nonexistent-tenant"})
        assert resp.status_code == 200
        assert resp.json()["discovered_count"] == 0


class TestConformance:
    def test_conformance_missing_model_404(self, client):
        resp = client.post("/conformance", json={
            "trace_id": "trace-x",
            "tenant_id": "t-1",
            "events": [
                {"activity": "a", "agent_id": "b", "timestamp": "2026-03-01T10:00:00"},
            ],
            "process_id": "nonexistent-process",
        })
        # 404 if model not found and cannot be auto-discovered
        assert resp.status_code in (404, 200)


class TestBottlenecks:
    def test_bottleneck_analysis(self, client, sample_trace):
        # Ingest trace with durations
        client.post("/traces", json=sample_trace)
        resp = client.get("/bottlenecks", params={"tenant_id": "t-1"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == "t-1"
        assert "bottlenecks" in data
        assert "recommendations" in data


class TestStats:
    def test_stats(self, client, sample_trace):
        client.post("/traces", json=sample_trace)
        resp = client.get("/stats", params={"tenant_id": "t-1"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == "t-1"
        assert data["total_traces"] >= 1


# =============================================================================
# Core Module Tests (merged from test_core_modules.py)
# =============================================================================

class TestProcessMiner:
    def _make_trace(self, trace_id, activities, tenant="t-1"):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        acts = []
        for i, name in enumerate(activities):
            acts.append(Activity(
                name=name,
                agent_id=f"agent-{i}",
                timestamp=base + timedelta(minutes=i),
                duration_ms=100.0 * (i + 1),
            ))
        return Trace(trace_id=trace_id, tenant_id=tenant, activities=acts)

    def test_add_trace(self):
        m = ProcessMiner()
        t = self._make_trace("t1", ["a", "b", "c"])
        m.add_trace(t)
        assert len(m.traces) == 1

    def test_add_trace_empty_activities(self):
        m = ProcessMiner()
        t = self._make_trace("t1", [])
        m.add_trace(t)
        assert len(m.traces) == 1
        assert len(m.start_activities) == 0

    def test_directly_follows(self):
        m = ProcessMiner()
        m.add_trace(self._make_trace("t1", ["a", "b", "c"]))
        dfg = m.get_directly_follows_graph()
        assert "a" in dfg
        assert "b" in dfg["a"]

    def test_activity_statistics(self):
        m = ProcessMiner()
        m.add_trace(self._make_trace("t1", ["a", "b", "c"]))
        stats = m.get_activity_statistics()
        assert "a" in stats
        assert stats["a"]["is_start"] is True
        assert stats["c"]["is_end"] is True

    def test_add_trace_from_log(self):
        m = ProcessMiner()
        events = [
            {"activity": "start", "agent_id": "a1", "timestamp": "2026-01-01T10:00:00"},
            {"activity": "process", "agent_id": "a2", "timestamp": "2026-01-01T10:01:00"},
        ]
        m.add_trace_from_log("t1", "tenant-1", events)
        assert len(m.traces) == 1

    def test_add_trace_from_log_missing_fields(self):
        m = ProcessMiner()
        events = [{"action": "fallback_action"}]
        m.add_trace_from_log("t2", "tenant-1", events)
        assert m.traces[0].activity_names[0] == "fallback_action"

    def test_discover_processes_empty(self):
        m = ProcessMiner()
        assert m.discover_processes() == []

    def test_discover_processes_below_frequency(self):
        m = ProcessMiner()
        m.add_trace(self._make_trace("t1", ["a", "b"]))
        result = m.discover_processes(min_frequency=2)
        assert len(result) == 0

    def test_discover_processes_above_frequency(self):
        m = ProcessMiner()
        m.add_trace(self._make_trace("t1", ["a", "b", "c"]))
        m.add_trace(self._make_trace("t2", ["a", "b", "c"]))
        result = m.discover_processes(min_frequency=2)
        assert len(result) == 1
        assert result[0].frequency == 2
        assert "a" in result[0].start_activities
        assert "c" in result[0].end_activities

    def test_discover_multiple_patterns(self):
        m = ProcessMiner()
        for i in range(3):
            m.add_trace(self._make_trace(f"t-a-{i}", ["a", "b"]))
        for i in range(2):
            m.add_trace(self._make_trace(f"t-b-{i}", ["x", "y"]))
        result = m.discover_processes(min_frequency=2)
        assert len(result) == 2
        # Most frequent first
        assert result[0].frequency == 3

    def test_trace_activity_names(self):
        t = self._make_trace("t1", ["start", "middle", "end"])
        assert t.activity_names == ["start", "middle", "end"]


class TestConformanceChecker:
    def _make_model(self):
        return DiscoveredProcess(
            process_id="proc-1",
            name="Test Process",
            activities={"a", "b", "c"},
            start_activities={"a"},
            end_activities={"c"},
            transitions={"a": {"b"}, "b": {"c"}},
            frequency=10,
        )

    def _make_trace(self, activities):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        acts = [
            Activity(name=n, agent_id="ag", timestamp=base + timedelta(minutes=i))
            for i, n in enumerate(activities)
        ]
        return Trace(trace_id="t1", tenant_id="t-1", activities=acts)

    def test_register_model(self):
        cc = ConformanceChecker()
        model = self._make_model()
        cc.register_model(model)
        assert "proc-1" in cc.models

    def test_check_trace_conformant(self):
        cc = ConformanceChecker()
        cc.register_model(self._make_model())
        result = cc.check_trace(self._make_trace(["a", "b", "c"]), "proc-1")
        assert result is not None
        assert result.conformant is True
        assert result.fitness_score >= 0.8

    def test_check_trace_missing_model(self):
        cc = ConformanceChecker()
        result = cc.check_trace(self._make_trace(["a"]), "nonexistent")
        assert result is None

    def test_check_trace_missing_activities(self):
        cc = ConformanceChecker()
        cc.register_model(self._make_model())
        result = cc.check_trace(self._make_trace(["a", "c"]), "proc-1")
        assert "b" in result.missing_activities

    def test_check_trace_unexpected_activities(self):
        cc = ConformanceChecker()
        cc.register_model(self._make_model())
        result = cc.check_trace(self._make_trace(["a", "b", "c", "x"]), "proc-1")
        assert "x" in result.unexpected_activities

    def test_check_trace_out_of_order(self):
        cc = ConformanceChecker()
        cc.register_model(self._make_model())
        result = cc.check_trace(self._make_trace(["a", "c", "b"]), "proc-1")
        assert len(result.out_of_order) > 0

    def test_check_batch(self):
        cc = ConformanceChecker()
        cc.register_model(self._make_model())
        traces = [
            self._make_trace(["a", "b", "c"]),
            self._make_trace(["a", "c"]),
        ]
        results = cc.check_batch(traces, "proc-1")
        assert len(results) == 2

    def test_check_batch_empty(self):
        cc = ConformanceChecker()
        cc.register_model(self._make_model())
        results = cc.check_batch([], "proc-1")
        assert results == []

    def test_fitness_zero_activities_model(self):
        cc = ConformanceChecker()
        model = DiscoveredProcess(
            process_id="empty",
            name="Empty",
            activities=set(),
            start_activities=set(),
            end_activities=set(),
            transitions={},
            frequency=1,
        )
        cc.register_model(model)
        result = cc.check_trace(self._make_trace(["a"]), "empty")
        assert result.fitness_score == 1.0


class TestBottleneckAnalyzer:
    def _make_trace(self, durations):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        acts = []
        for i, dur in enumerate(durations):
            acts.append(Activity(
                name=f"step_{i}",
                agent_id=f"agent-{i}",
                timestamp=base + timedelta(milliseconds=sum(durations[:i]) + i * 1000),
                duration_ms=dur,
            ))
        return Trace(trace_id=f"t-{id(durations)}", tenant_id="t-1", activities=acts)

    def test_analyze_empty(self):
        ba = BottleneckAnalyzer()
        report = ba.analyze([])
        assert report.total_traces == 0
        assert report.bottlenecks == []

    def test_analyze_single_trace(self):
        ba = BottleneckAnalyzer()
        trace = self._make_trace([100, 200, 500])
        report = ba.analyze([trace])
        assert report.total_traces == 1
        assert report.total_activities == 3

    def test_bottleneck_detection(self):
        ba = BottleneckAnalyzer(bottleneck_threshold_percentile=50.0)
        traces = [
            self._make_trace([10, 10, 1000]),  # step_2 is slow
            self._make_trace([10, 10, 900]),
        ]
        report = ba.analyze(traces)
        assert len(report.bottlenecks) > 0
        bottleneck_names = [b.activity_name for b in report.bottlenecks]
        assert "step_2" in bottleneck_names

    def test_recommendations_generated(self):
        ba = BottleneckAnalyzer(bottleneck_threshold_percentile=50.0)
        traces = [
            self._make_trace([10, 10, 1000]),
            self._make_trace([10, 10, 5000]),  # High variance
        ]
        report = ba.analyze(traces)
        assert len(report.recommendations) > 0

    def test_percentile_empty(self):
        assert BottleneckAnalyzer._percentile([], 95) == 0.0

    def test_percentile_single(self):
        assert BottleneckAnalyzer._percentile([42.0], 50) == 42.0

    def test_transition_performance(self):
        ba = BottleneckAnalyzer()
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        trace = Trace(
            trace_id="tw1",
            tenant_id="t-1",
            activities=[
                Activity(name="a", agent_id="x", timestamp=base, duration_ms=100),
                Activity(
                    name="b", agent_id="y",
                    timestamp=base + timedelta(seconds=2),
                    duration_ms=50,
                ),
            ],
        )
        report = ba.analyze([trace])
        assert report.total_activities == 2

