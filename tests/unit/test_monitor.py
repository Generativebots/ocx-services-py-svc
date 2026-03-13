"""
Monitor Service — comprehensive tests covering background loop, entropy calc,
Redis integration, FastAPI endpoints, ingest_sops_to_ape, and startup.
"""

import sys
import os
import types
import math
import time
import threading
from unittest.mock import MagicMock, patch
from collections import Counter

import pytest

# Stub redis
_fake_redis = types.ModuleType("redis")
_fake_redis.from_url = MagicMock(return_value=MagicMock())
_fake_redis.Redis = type("Redis", (), {})  # type annotation used by other modules
sys.modules.setdefault("redis", _fake_redis)

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "monitor"))

from fastapi.testclient import TestClient
import main as monitor_main

client = TestClient(monitor_main.app)


class TestHealthEndpoint:
    def test_health_returns_ok(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert resp.json()["service"] == "Monitor"

    def test_health_includes_state(self):
        resp = client.get("/health")
        assert "state" in resp.json()


class TestStatusEndpoint:
    def test_status_returns_current_state(self):
        original = monitor_main.monitor_state.copy()
        monitor_main.monitor_state["status"] = "running"
        monitor_main.monitor_state["entropy_score"] = 3.14
        monitor_main.monitor_state["last_check"] = "2026-01-01T00:00:00Z"
        monitor_main.monitor_state["redis_connected"] = True
        resp = client.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert data["entropy_score"] == 3.14
        monitor_main.monitor_state.update(original)


class TestShannonEntropy:
    def test_empty_returns_zero(self):
        assert monitor_main.calculate_shannon_entropy([]) == 0

    def test_uniform_data_high_entropy(self):
        data = list(range(100))
        e = monitor_main.calculate_shannon_entropy(data)
        assert e > 5

    def test_constant_data_zero_entropy(self):
        e = monitor_main.calculate_shannon_entropy([1.0, 1.0, 1.0, 1.0])
        assert e == 0.0

    def test_two_values_entropy(self):
        # 50/50 split → 1 bit
        data = [1.0, 2.0, 1.0, 2.0]
        e = monitor_main.calculate_shannon_entropy(data)
        assert abs(e - 1.0) < 0.01


class TestRedisConnection:
    def test_success(self):
        mock_r = MagicMock()
        mock_r.ping.return_value = True
        with patch("main.redis") as mock_redis_mod:
            mock_redis_mod.from_url.return_value = mock_r
            r = monitor_main.get_redis_connection()
            assert r is mock_r

    def test_failure(self):
        with patch("main.redis") as mock_redis_mod:
            mock_redis_mod.from_url.side_effect = Exception("refused")
            r = monitor_main.get_redis_connection()
            assert r is None


class TestIngestSopsToApe:
    def test_ingest_with_redis(self):
        mock_r = MagicMock()
        monitor_main.ingest_sops_to_ape(mock_r)
        mock_r.hset.assert_called_once()

    def test_ingest_no_redis(self):
        monitor_main.ingest_sops_to_ape(None)  # Should not raise

    def test_ingest_redis_error(self):
        mock_r = MagicMock()
        mock_r.hset.side_effect = Exception("write error")
        monitor_main.ingest_sops_to_ape(mock_r)  # Should not raise


class TestMonitorAgentSignals:
    def test_one_iteration(self):
        """Run monitor_agent_signals for one iteration by patching time.sleep to raise."""
        mock_r = MagicMock()
        mock_r.lrange.return_value = ["0.12", "0.15", "0.11"]

        call_count = 0
        def fake_sleep(secs):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                raise KeyboardInterrupt()

        with patch("main.time.sleep", side_effect=fake_sleep):
            try:
                monitor_main.monitor_agent_signals(mock_r)
            except KeyboardInterrupt:
                pass

        assert monitor_main.monitor_state["entropy_score"] is not None

    def test_no_redis(self):
        call_count = 0
        def fake_sleep(secs):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                raise KeyboardInterrupt()

        with patch("main.time.sleep", side_effect=fake_sleep):
            try:
                monitor_main.monitor_agent_signals(None)
            except KeyboardInterrupt:
                pass

        assert monitor_main.monitor_state["status"] in ("HEALTHY", "LOCKDOWN")

    def test_redis_read_failure(self):
        mock_r = MagicMock()
        mock_r.lrange.side_effect = Exception("read fail")

        call_count = 0
        def fake_sleep(secs):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                raise KeyboardInterrupt()

        with patch("main.time.sleep", side_effect=fake_sleep):
            try:
                monitor_main.monitor_agent_signals(mock_r)
            except KeyboardInterrupt:
                pass

    def test_redis_set_failure(self):
        mock_r = MagicMock()
        mock_r.lrange.return_value = ["0.1", "0.2"]
        mock_r.set.side_effect = Exception("write fail")

        call_count = 0
        def fake_sleep(secs):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                raise KeyboardInterrupt()

        with patch("main.time.sleep", side_effect=fake_sleep):
            try:
                monitor_main.monitor_agent_signals(mock_r)
            except KeyboardInterrupt:
                pass

    def test_lockdown_on_low_entropy(self):
        mock_r = MagicMock()
        # constant values → 0 entropy → below threshold
        mock_r.lrange.return_value = ["0.12"] * 20

        call_count = 0
        def fake_sleep(secs):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                raise KeyboardInterrupt()

        with patch("main.time.sleep", side_effect=fake_sleep):
            try:
                monitor_main.monitor_agent_signals(mock_r)
            except KeyboardInterrupt:
                pass

        assert monitor_main.monitor_state["status"] == "LOCKDOWN"


class TestStartBackgroundMonitor:
    def test_start_creates_thread(self):
        with patch("main.threading.Thread") as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread
            monitor_main.start_background_monitor()
            mock_thread.start.assert_called_once()

    def test_run_with_redis_success(self):
        """Exercise the inner _run() function: Redis connects, ingest runs,
        then monitor_agent_signals is called (covers lines 162-174)."""
        mock_r = MagicMock()
        call_count = 0

        def fake_get_redis(*a, **kw):
            return mock_r

        def fake_monitor(r):
            # Exit immediately
            raise KeyboardInterrupt()

        with patch("main.get_redis_connection", side_effect=fake_get_redis):
            with patch("main.ingest_sops_to_ape") as mock_ingest:
                with patch("main.monitor_agent_signals", side_effect=fake_monitor):
                    with patch("main.threading.Thread") as mock_thread_cls:
                        # Capture the _run target
                        def capture_and_run(**kwargs):
                            target = kwargs.get("target")
                            if target:
                                try:
                                    target()
                                except KeyboardInterrupt:
                                    pass
                            mock_t = MagicMock()
                            mock_t.start = MagicMock()
                            return mock_t

                        mock_thread_cls.side_effect = capture_and_run
                        monitor_main.start_background_monitor()
                        mock_ingest.assert_called_once_with(mock_r)

    def test_run_no_redis(self):
        """_run() when Redis never connects — should still call monitor_agent_signals."""
        def fake_get_redis(*a, **kw):
            return None

        def fake_monitor(r):
            raise KeyboardInterrupt()

        def fake_sleep(s):
            pass

        with patch("main.get_redis_connection", side_effect=fake_get_redis):
            with patch("main.monitor_agent_signals", side_effect=fake_monitor):
                with patch("main.time.sleep", side_effect=fake_sleep):
                    with patch("main.threading.Thread") as mock_thread_cls:
                        def capture_and_run(**kwargs):
                            target = kwargs.get("target")
                            if target:
                                try:
                                    target()
                                except KeyboardInterrupt:
                                    pass
                            mock_t = MagicMock()
                            mock_t.start = MagicMock()
                            return mock_t

                        mock_thread_cls.side_effect = capture_and_run
                        monitor_main.start_background_monitor()

