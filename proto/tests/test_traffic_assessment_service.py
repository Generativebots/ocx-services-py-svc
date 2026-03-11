"""Tests for proto/traffic_assessment_service_impl.py — TrafficAssessorImpl"""
import sys, os, unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from proto.traffic_assessment_service_impl import TrafficAssessorImpl
from proto.traffic_assessment_pb2 import (
    AssessmentRequest, TrafficMetadata, ExecutionPlan, VerdictAction, ProtocolType
)


def _make_request(dest="127.0.0.1", port=80, protocol=ProtocolType.PROTOCOL_TYPE_TCP,
                  comm="", pid=0, request_id="r1"):
    meta = TrafficMetadata(destination_address=dest, destination_port=port, comm=comm, pid=pid)
    return AssessmentRequest(request_id=request_id, metadata=meta, protocol=protocol)


class TestSubmitPlan(unittest.TestCase):
    def setUp(self):
        self.svc = TrafficAssessorImpl()
        self.ctx = MagicMock()

    def test_valid_plan(self):
        plan = ExecutionPlan(agent_id="a1", plan_id="p1", allowed_calls=["GET /api/data"])
        verdict = self.svc.SubmitPlan(plan, self.ctx)
        self.assertEqual(verdict.action, VerdictAction.ACTION_ALLOW)

    def test_empty_plan_id(self):
        plan = ExecutionPlan(agent_id="a1", plan_id="", allowed_calls=["GET /x"])
        verdict = self.svc.SubmitPlan(plan, self.ctx)
        self.assertEqual(verdict.action, VerdictAction.ACTION_BLOCK)
        self.ctx.set_code.assert_called()

    def test_empty_allowed_calls(self):
        plan = ExecutionPlan(agent_id="a1", plan_id="p1", allowed_calls=[])
        verdict = self.svc.SubmitPlan(plan, self.ctx)
        self.assertEqual(verdict.action, VerdictAction.ACTION_BLOCK)

    def test_manual_review_required(self):
        plan = ExecutionPlan(agent_id="a1", plan_id="p1",
                             allowed_calls=["GET /x"], manual_review_required=True)
        verdict = self.svc.SubmitPlan(plan, self.ctx)
        self.assertEqual(verdict.action, VerdictAction.ACTION_MITIGATE)

    def test_plan_registers_in_memory(self):
        plan = ExecutionPlan(agent_id="a1", plan_id="p1", allowed_calls=["GET /x"])
        self.svc.SubmitPlan(plan, self.ctx)
        self.assertIn("a1", self.svc._plans)


class TestAssessSingle(unittest.TestCase):
    def setUp(self):
        self.svc = TrafficAssessorImpl()

    def test_safe_destination_allowed(self):
        req = _make_request(dest="127.0.0.1", port=8080)
        resp = self.svc._assess_single(req)
        self.assertEqual(resp.verdict.action, VerdictAction.ACTION_ALLOW)

    def test_localhost_allowed(self):
        req = _make_request(dest="localhost", port=443)
        resp = self.svc._assess_single(req)
        self.assertEqual(resp.verdict.action, VerdictAction.ACTION_ALLOW)

    def test_high_risk_port_blocked(self):
        req = _make_request(dest="evil.com", port=22)
        resp = self.svc._assess_single(req)
        self.assertEqual(resp.verdict.action, VerdictAction.ACTION_BLOCK)

    def test_dns_observed(self):
        req = _make_request(dest="dns.example.com", port=53,
                            protocol=ProtocolType.PROTOCOL_TYPE_DNS)
        resp = self.svc._assess_single(req)
        self.assertEqual(resp.verdict.action, VerdictAction.ACTION_OBSERVE)

    def test_unknown_mitigated(self):
        req = _make_request(dest="unknown.com", port=8443)
        resp = self.svc._assess_single(req)
        self.assertEqual(resp.verdict.action, VerdictAction.ACTION_MITIGATE)

    def test_planned_traffic_allowed(self):
        # Plan lookup uses meta.comm (process name)
        plan = ExecutionPlan(agent_id="a1", plan_id="p1",
                             allowed_calls=["api.trusted.com"])
        ctx = MagicMock()
        # Register plan under agent_id "a1"
        self.svc.SubmitPlan(plan, ctx)
        # But _assess_single looks up plan by meta.comm
        # So manually register under the comm name too
        self.svc._plans["myapp"] = plan

        req = _make_request(dest="api.trusted.com", port=443, comm="myapp")
        resp = self.svc._assess_single(req)
        self.assertEqual(resp.verdict.action, VerdictAction.ACTION_ALLOW)


class TestInspectTraffic(unittest.TestCase):
    def setUp(self):
        self.svc = TrafficAssessorImpl()

    def test_stream_processing(self):
        requests = [
            _make_request(dest="127.0.0.1", port=80),
            _make_request(dest="evil.com", port=22),
        ]
        ctx = MagicMock()
        responses = list(self.svc.InspectTraffic(iter(requests), ctx))
        self.assertEqual(len(responses), 2)
        self.assertEqual(responses[0].verdict.action, VerdictAction.ACTION_ALLOW)
        self.assertEqual(responses[1].verdict.action, VerdictAction.ACTION_BLOCK)


if __name__ == "__main__":
    unittest.main()
