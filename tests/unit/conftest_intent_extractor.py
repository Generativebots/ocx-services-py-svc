"""
Intent Extractor — pytest configuration & shared fixtures.

Stubs external dependencies (Supabase, Google Gemini) for isolated testing.
"""

import os
import sys
import types
import pytest

sys.path.insert(0, os.path.dirname(__file__))

# Stub httpx for Supabase HTTP calls
# The intent-extractor uses direct httpx for Supabase REST API

from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    """FastAPI TestClient with mocked Supabase and Gemini."""
    # Mock environment variables
    monkeypatch.setenv("SUPABASE_URL", "http://mock-supabase:8000")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "mock-key")
    monkeypatch.setenv("GOOGLE_API_KEY", "mock-gemini-key")

    from main import app
    return TestClient(app)
