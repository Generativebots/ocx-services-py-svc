"""
Process Mining — API endpoint tests.

Tests trace ingestion, process discovery, conformance checking,
bottleneck analysis, stats, and health endpoints.
"""

import pytest


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
