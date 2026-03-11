"""
Monitor — API endpoint and entropy tests.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestHealth:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "Monitor"

    def test_status(self, client):
        resp = client.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "entropy_score" in data
        assert "redis_connected" in data


class TestShannonEntropy:
    """Direct unit tests on calculate_shannon_entropy."""

    def test_uniform_values_zero_entropy(self):
        from main import calculate_shannon_entropy

        # All same values → 0 entropy
        result = calculate_shannon_entropy([0.12, 0.12, 0.12, 0.12])
        assert result == 0.0

    def test_empty_list_zero(self):
        from main import calculate_shannon_entropy

        result = calculate_shannon_entropy([])
        assert result == 0

    def test_diverse_values_high_entropy(self):
        from main import calculate_shannon_entropy

        # All different values → higher entropy
        result = calculate_shannon_entropy([0.10, 0.20, 0.30, 0.40, 0.50])
        assert result > 1.0  # Should be ~2.32 bits for 5 unique values

    def test_two_distinct_values(self):
        from main import calculate_shannon_entropy

        result = calculate_shannon_entropy([0.10, 0.20, 0.10, 0.20])
        assert result == pytest.approx(1.0, abs=0.01)  # 1 bit for 50/50 split

    def test_single_value_zero(self):
        from main import calculate_shannon_entropy

        result = calculate_shannon_entropy([0.5])
        assert result == 0.0
