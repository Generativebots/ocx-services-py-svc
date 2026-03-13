"""
Process Mining — pytest configuration & shared fixtures.
"""

import os
import sys
import pytest

# Ensure the process-mining package is importable
sys.path.insert(0, os.path.dirname(__file__))

from fastapi.testclient import TestClient
from main import app


@pytest.fixture
def client():
    """FastAPI TestClient for process-mining."""
    return TestClient(app)


@pytest.fixture
def sample_trace():
    """Reusable trace payload."""
    return {
        "trace_id": "trace-001",
        "tenant_id": "t-1",
        "events": [
            {
                "activity": "receive_order",
                "agent_id": "agent-a",
                "timestamp": "2026-03-01T10:00:00",
                "duration_ms": 50.0,
            },
            {
                "activity": "validate_payment",
                "agent_id": "agent-b",
                "timestamp": "2026-03-01T10:01:00",
                "duration_ms": 200.0,
            },
            {
                "activity": "ship_item",
                "agent_id": "agent-c",
                "timestamp": "2026-03-01T10:05:00",
                "duration_ms": 500.0,
            },
        ],
    }
