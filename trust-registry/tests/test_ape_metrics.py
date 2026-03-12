"""Tests for ape_metrics.py — Prometheus metric decorators"""
import sys, os, unittest, time, types, pytest
from unittest.mock import MagicMock, patch

# Mock prometheus_client before import
mock_prometheus = MagicMock()
sys.modules["prometheus_client"] = mock_prometheus

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import ape_metrics
from ape_metrics import track_extraction, track_evaluation, track_ghost_state


class TestTrackExtraction(unittest.TestCase):
    def test_success_tracks_metrics(self):
        @track_extraction("Test SOP", "mistral-7b")
        def extract():
            return [{"confidence": 0.95}, {"confidence": 0.85}]

        result = extract()
        self.assertEqual(len(result), 2)

    def test_exception_tracks_error(self):
        @track_extraction("Test SOP", "mistral-7b")
        def extract_fail():
            raise ValueError("fail")

        with self.assertRaises(ValueError):
            extract_fail()

    def test_empty_result(self):
        @track_extraction("Empty", "model")
        def extract_empty():
            return []

        result = extract_empty()
        self.assertEqual(result, [])

    def test_non_list_result(self):
        @track_extraction("Other", "model")
        def extract_str():
            return "plain"

        result = extract_str()
        self.assertEqual(result, "plain")


class TestTrackEvaluation(unittest.TestCase):
    def test_allowed_result(self):
        @track_evaluation("P1", "CONTEXTUAL")
        def evaluate():
            return True

        result = evaluate()
        self.assertTrue(result)

    def test_blocked_tuple(self):
        @track_evaluation("P1", "GLOBAL")
        def evaluate():
            return (False, "BLOCK")

        result = evaluate()
        self.assertFalse(result[0])

    def test_allowed_tuple(self):
        @track_evaluation("P1", "DYNAMIC")
        def evaluate():
            return (True, "ALLOW")

        result = evaluate()
        self.assertTrue(result[0])


class TestTrackGhostState(unittest.TestCase):
    def test_allowed(self):
        @track_ghost_state("execute_payment")
        def simulate():
            return (True, "safe")

        result = simulate()
        self.assertTrue(result[0])

    def test_blocked(self):
        @track_ghost_state("send_email")
        def simulate():
            return (False, "blocked")

        result = simulate()
        self.assertFalse(result[0])

    def test_bool_result(self):
        @track_ghost_state("read_file")
        def simulate():
            return True

        result = simulate()
        self.assertTrue(result)


class TestMetricConstants(unittest.TestCase):
    """Verify metric objects exist"""
    def test_counters_exist(self):
        self.assertIsNotNone(ape_metrics.policy_extractions_total)
        self.assertIsNotNone(ape_metrics.policy_evaluations_total)
        self.assertIsNotNone(ape_metrics.policy_violations)
        self.assertIsNotNone(ape_metrics.ghost_state_simulations)
        self.assertIsNotNone(ape_metrics.required_signals_collected)
        self.assertIsNotNone(ape_metrics.model_errors)

    def test_histograms_exist(self):
        self.assertIsNotNone(ape_metrics.policy_extraction_duration)
        self.assertIsNotNone(ape_metrics.policies_extracted)
        self.assertIsNotNone(ape_metrics.extraction_confidence)
        self.assertIsNotNone(ape_metrics.policy_evaluation_duration)
        self.assertIsNotNone(ape_metrics.ghost_state_duration)
        self.assertIsNotNone(ape_metrics.signal_verification_duration)
        self.assertIsNotNone(ape_metrics.model_inference_duration)

    def test_gauges_exist(self):
        self.assertIsNotNone(ape_metrics.active_policies)
        self.assertIsNotNone(ape_metrics.policy_versions)
        self.assertIsNotNone(ape_metrics.policy_conflicts)


if __name__ == "__main__":
    unittest.main()


class TestApeMetricsTrackExtraction:
    """Tests for track_extraction decorator"""

    def test_track_extraction_success_with_list(self):
        am = ape_metrics
        @am.track_extraction("src", "model")
        def fn():
            return [{"confidence": 0.9}, {"confidence": 0.8}]
        result = fn()
        assert len(result) == 2

    def test_track_extraction_success_empty_list(self):
        am = ape_metrics
        @am.track_extraction("src", "model")
        def fn():
            return []
        assert fn() == []

    def test_track_extraction_non_list_result(self):
        am = ape_metrics
        @am.track_extraction("src", "model")
        def fn():
            return "scalar"
        assert fn() == "scalar"

    def test_track_extraction_error_branch(self):
        am = ape_metrics
        @am.track_extraction("src", "model")
        def fn():
            raise ValueError("boom")
        with pytest.raises(ValueError):
            fn()




class TestApeMetricsTrackEvaluation:
    """Tests for track_evaluation decorator"""

    def test_track_evaluation_allowed_tuple(self):
        am = ape_metrics
        @am.track_evaluation("P1", "GLOBAL")
        def fn():
            return (True, "ALLOW")
        assert fn() == (True, "ALLOW")

    def test_track_evaluation_blocked_tuple(self):
        am = ape_metrics
        @am.track_evaluation("P1", "GLOBAL")
        def fn():
            return (False, "BLOCK")
        assert fn() == (False, "BLOCK")

    def test_track_evaluation_bool_result(self):
        am = ape_metrics
        @am.track_evaluation("P1", "GLOBAL")
        def fn():
            return True
        assert fn() is True

    def test_track_evaluation_blocked_bool(self):
        am = ape_metrics
        @am.track_evaluation("P1", "GLOBAL")
        def fn():
            return False
        assert fn() is False




class TestApeMetricsTrackGhostState:
    """Tests for track_ghost_state decorator"""

    def test_ghost_state_allowed(self):
        am = ape_metrics
        @am.track_ghost_state("tool_x")
        def fn():
            return (True,)
        assert fn() == (True,)

    def test_ghost_state_blocked(self):
        am = ape_metrics
        @am.track_ghost_state("tool_x")
        def fn():
            return (False, "blocked")
        r = fn()
        assert r[0] is False

    def test_ghost_state_bool(self):
        am = ape_metrics
        @am.track_ghost_state("tool_x")
        def fn():
            return False
        assert fn() is False




class TestApeMetricsMainBlock:
    def test_main_executes(self):
        src = open(os.path.join(os.path.dirname(__file__), "..", "ape_metrics.py")).read()
        # Patch the real threading and time modules so exec doesn't block
        import threading as _threading
        original_event = _threading.Event
        original_sleep = time.sleep
        # Replace Event().wait with a no-op and time.sleep with a no-op
        mock_evt = MagicMock()
        mock_evt.wait = MagicMock(side_effect=KeyboardInterrupt)
        _threading.Event = MagicMock(return_value=mock_evt)
        time.sleep = MagicMock()
        try:
            with patch("prometheus_client.start_http_server"):
                try:
                    exec(compile(src, "ape_metrics.py", "exec"), {"__name__": "__main__"})
                except KeyboardInterrupt:
                    pass
        finally:
            _threading.Event = original_event
            time.sleep = original_sleep


# ──────────────────────── config/settings.py ──────────────────────────────


