"""
OCX Python Services — Top-Level Test Configuration
===================================================
Shared pytest fixtures and configuration used across all test types.

Test Structure:
    tests/
    ├── conftest.py          # This file — shared fixtures
    ├── fixtures/            # Shared test data (JSON, seed data)
    ├── unit/                # Fast unit tests (no external deps)
    ├── integration/         # Tests requiring DB/network
    ├── regression/          # Bug-fix regression tests
    ├── performance/         # Load/benchmark tests
    └── dataflow/            # End-to-end pipeline tests

Run Examples:
    pytest tests/unit/ -v              # Unit tests only
    pytest tests/ -m integration       # Integration tests
    pytest tests/ -m "not integration" # Everything except integration
"""
import os
import sys
import pytest

# ---------------------------------------------------------------------------
# Ensure all service packages are importable from tests
# ---------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tenant_id():
    """Standard test tenant ID."""
    return "test-tenant-001"


@pytest.fixture
def mock_env(monkeypatch):
    """Set common environment variables for testing."""
    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("ENVIRONMENT", "test")


@pytest.fixture
def sample_agent():
    """Sample agent data for testing."""
    return {
        "id": "agent-001",
        "name": "Test Agent",
        "tenant_id": "test-tenant-001",
        "status": "ACTIVE",
        "capabilities": ["read", "write"],
    }


@pytest.fixture
def sample_policy():
    """Sample policy data for testing."""
    return {
        "id": "policy-001",
        "name": "Test Policy",
        "version": "1.0.0",
        "rules": [{"action": "allow", "resource": "*"}],
    }
