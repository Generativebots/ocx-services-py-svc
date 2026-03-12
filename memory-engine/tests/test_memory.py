"""Tests for memory-engine/server.py"""
import json
import os
import pytest

import sys, pathlib

# We need to set VAULT_DIR before import since it runs at module level
_mem_dir = str(pathlib.Path(__file__).resolve().parent.parent)
sys.path.insert(0, _mem_dir)

# Import after sys.path setup - the module creates VAULT_DIR at import time
from server import record_agent_memory


class TestRecordAgentMemory:
    def test_creates_memory_file(self):
        """Test that record_agent_memory writes to JSONL file."""
        result = record_agent_memory("test-agent-1", "Test insight", "SUCCESS")
        assert "test-agent-1" in result

    def test_returns_confirmation_string(self):
        result = record_agent_memory("test-agent-2", "insight", "OK")
        assert isinstance(result, str)
        assert "test-agent-2" in result or "Memory" in result

    def test_with_tags(self):
        result = record_agent_memory("test-agent-3", "Tagged insight", "BLOCKED", tags=["retry", "error"])
        assert "test-agent-3" in result

    def test_file_contains_correct_data(self):
        """Verify the actual JSONL output."""
        from server import VAULT_DIR
        agent_id = "test-verify-data"
        record_agent_memory(agent_id, "Verify data", "SUCCESS", tags=["test"])
        fpath = os.path.join(VAULT_DIR, f"{agent_id}_memory.jsonl")
        assert os.path.exists(fpath)
        with open(fpath) as f:
            lines = f.read().strip().split("\n")
        entry = json.loads(lines[-1])
        assert entry["agent_id"] == agent_id
        assert entry["insight"] == "Verify data"
        assert entry["outcome"] == "SUCCESS"
        assert entry["tags"] == ["test"]

    def test_appends_multiple_entries(self):
        from server import VAULT_DIR
        agent_id = "test-multi"
        record_agent_memory(agent_id, "First", "SUCCESS")
        record_agent_memory(agent_id, "Second", "BLOCKED")
        fpath = os.path.join(VAULT_DIR, f"{agent_id}_memory.jsonl")
        with open(fpath) as f:
            lines = f.read().strip().split("\n")
        assert len(lines) >= 2
