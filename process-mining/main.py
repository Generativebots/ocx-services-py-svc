"""
Process Mining Service — FastAPI entry point.

Exposes process mining capabilities via REST API:
- POST /traces — ingest execution traces
- GET /discover — run process discovery
- POST /conformance — check trace conformance
- GET /bottlenecks — analyze performance bottlenecks
"""

import logging
import os
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from miner import ProcessMiner, Trace, Activity
from conformance import ConformanceChecker
from bottleneck import BottleneckAnalyzer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("process-mining-api")

app = FastAPI(
    title="OCX Process Mining Engine",
    description="Patent: Extract workflows from agent logs for conformance checking",
    version="1.0.0",
)

# Global instances
miner = ProcessMiner()
conformance_checker = ConformanceChecker()
bottleneck_analyzer = BottleneckAnalyzer()


# ===== Request/Response Models =====

class ActivityEvent(BaseModel):
    activity: str
    agent_id: str
    timestamp: str
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = {}


class TraceInput(BaseModel):
    trace_id: str
    tenant_id: str
    events: List[ActivityEvent]


class ConformanceRequest(BaseModel):
    trace_id: str
    tenant_id: str
    events: List[ActivityEvent]
    process_id: str


# ===== API Endpoints =====

@app.post("/traces")
async def ingest_trace(trace_input: TraceInput):
    """Ingest an execution trace for analysis."""
    events = [
        {
            "activity": e.activity,
            "agent_id": e.agent_id,
            "timestamp": e.timestamp,
            "duration_ms": e.duration_ms,
            "metadata": e.metadata,
        }
        for e in trace_input.events
    ]
    miner.add_trace_from_log(trace_input.trace_id, trace_input.tenant_id, events)

    return {
        "status": "ingested",
        "trace_id": trace_input.trace_id,
        "event_count": len(events),
        "total_traces": len(miner.traces),
    }


@app.get("/discover")
async def discover_processes(tenant_id: str, min_frequency: int = 2):
    """Run process discovery on ingested traces (tenant-scoped)."""
    # Filter traces by tenant
    traces = [t for t in miner.traces if t.tenant_id == tenant_id]

    processes = miner.discover_processes(min_frequency=min_frequency, traces=traces)

    return {
        "tenant_id": tenant_id,
        "discovered_count": len(processes),
        "total_traces_analyzed": len(traces),
        "processes": [
            {
                "process_id": p.process_id,
                "name": p.name,
                "activities": list(p.activities),
                "start_activities": list(p.start_activities),
                "end_activities": list(p.end_activities),
                "transitions": {k: list(v) for k, v in p.transitions.items()},
                "frequency": p.frequency,
                "avg_duration_ms": p.avg_duration_ms,
            }
            for p in processes
        ],
    }


@app.post("/conformance")
async def check_conformance(request: ConformanceRequest):
    """Check a trace against a registered process model."""
    # Auto-discover and register models if needed
    if request.process_id not in conformance_checker.models:
        processes = miner.discover_processes(min_frequency=1)
        for p in processes:
            conformance_checker.register_model(p)

    if request.process_id not in conformance_checker.models:
        raise HTTPException(
            status_code=404,
            detail=f"Process model {request.process_id} not found",
        )

    # Build trace
    from datetime import datetime
    trace = Trace(
        trace_id=request.trace_id,
        tenant_id=request.tenant_id,
        activities=[
            Activity(
                name=e.activity,
                agent_id=e.agent_id,
                timestamp=datetime.fromisoformat(e.timestamp),
                duration_ms=e.duration_ms,
            )
            for e in request.events
        ],
    )

    result = conformance_checker.check_trace(trace, request.process_id)
    if not result:
        raise HTTPException(status_code=500, detail="Conformance check failed")

    return {
        "trace_id": result.trace_id,
        "process_id": result.process_id,
        "conformant": result.conformant,
        "fitness_score": result.fitness_score,
        "deviations": result.deviations,
        "missing_activities": result.missing_activities,
        "unexpected_activities": result.unexpected_activities,
    }


@app.get("/bottlenecks")
async def analyze_bottlenecks(tenant_id: str):
    """Analyze performance bottlenecks in ingested traces (tenant-scoped)."""
    traces = [t for t in miner.traces if t.tenant_id == tenant_id]

    report = bottleneck_analyzer.analyze(traces)

    return {
        "tenant_id": tenant_id,
        "total_traces": report.total_traces,
        "total_activities": report.total_activities,
        "avg_trace_duration_ms": report.avg_trace_duration_ms,
        "bottleneck_count": len(report.bottlenecks),
        "bottlenecks": [
            {
                "activity": b.activity_name,
                "avg_duration_ms": b.avg_duration_ms,
                "p95_duration_ms": b.p95_duration_ms,
                "execution_count": b.execution_count,
                "reason": b.bottleneck_reason,
            }
            for b in report.bottlenecks
        ],
        "recommendations": report.recommendations,
        "activities": [
            {
                "name": a.activity_name,
                "count": a.execution_count,
                "avg_ms": round(a.avg_duration_ms, 1),
                "p95_ms": round(a.p95_duration_ms, 1),
                "max_ms": round(a.max_duration_ms, 1),
            }
            for a in report.activities[:10]
        ],
    }


@app.get("/stats")
async def get_stats(tenant_id: str):
    """Get current mining statistics (tenant-scoped)."""
    tenant_traces = [t for t in miner.traces if t.tenant_id == tenant_id]
    return {
        "tenant_id": tenant_id,
        "total_traces": len(tenant_traces),
        "activity_statistics": miner.get_activity_statistics(),
        "directly_follows_graph": {
            k: dict(v) for k, v in miner.get_directly_follows_graph().items()
        },
        "registered_models": len(conformance_checker.models),
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "process-mining"}


def main():
    """Entry point for the process mining service."""
    port = int(os.environ.get("PORT", "8080"))
    logger.info(f"Starting Process Mining Engine on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
