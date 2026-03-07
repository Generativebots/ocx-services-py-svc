"""
Traffic Assessment gRPC Service Implementation.

Implements TrafficAssessorServicer from proto/traffic_assessment_pb2_grpc.py:
  - InspectTraffic: Bidirectional stream analyzing network traffic for anomalies
  - SubmitPlan: Validate an execution plan against governance rules

Works with the eBPF interceptor (Layer 1) and the Shannon Entropy Monitor
(Layer 3) to classify outbound traffic from agent processes.
"""

import hashlib
import logging
import time
from typing import Dict, List

import grpc

from proto.traffic_assessment_pb2_grpc import TrafficAssessorServicer
from proto.traffic_assessment_pb2 import (
    AssessmentRequest,
    AssessmentResponse,
    ExecutionPlan,
    Verdict,
    VerdictAction,
    ProtocolType,
)

logger = logging.getLogger(__name__)

# Known-safe destinations that are always allowed
_SAFE_DESTINATIONS = {
    "127.0.0.1",
    "localhost",
    "0.0.0.0",
    "::1",
}

# High-risk ports that trigger enhanced scrutiny
_HIGH_RISK_PORTS = {22, 23, 25, 445, 3389, 5900}


class TrafficAssessorImpl(TrafficAssessorServicer):
    """Production implementation of the Traffic Assessor gRPC service.

    Analyzes intercepted network traffic from eBPF and execution plans
    from the Python Orchestrator. Uses heuristics for initial assessment
    with hooks for ML-based classification in production.
    """

    def __init__(self) -> None:
        # Registered execution plans (agent_id → plan)
        self._plans: Dict[str, ExecutionPlan] = {}
        # Seen traffic patterns for anomaly detection
        self._history: Dict[str, List[float]] = {}

    def InspectTraffic(self, request_iterator, context):
        """
        Bidirectional stream: receives captured traffic metadata from the
        eBPF interceptor and yields assessment verdicts in real time.

        Assessment logic:
        1. Known-safe destination → ALLOW
        2. High-risk port with no registered plan → BLOCK
        3. DNS traffic → OBSERVE (log for forensics)
        4. Traffic matching a registered plan's allowed_calls → ALLOW
        5. Unknown pattern → MITIGATE (hold for Tri-Factor Gate)
        """
        for request in request_iterator:
            verdict = self._assess_single(request)
            yield verdict

    def SubmitPlan(self, request: ExecutionPlan, context) -> Verdict:
        """
        Validate and register an execution plan.

        Checks:
        1. Plan has a valid agent_id and plan_id
        2. allowed_calls list is non-empty
        3. If manual_review_required, always returns MITIGATE
        4. Otherwise, registers and returns ALLOW
        """
        if not request.agent_id or not request.plan_id:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("agent_id and plan_id are required")
            return Verdict(action=VerdictAction.ACTION_BLOCK)

        if not request.allowed_calls:
            logger.warning(
                "[TrafficAssessor] Plan with empty allowed_calls: plan=%s agent=%s",
                request.plan_id,
                request.agent_id,
            )
            return Verdict(action=VerdictAction.ACTION_BLOCK)

        # Register the plan
        self._plans[request.agent_id] = request

        if request.manual_review_required:
            logger.info(
                "[TrafficAssessor] Plan requires manual review: plan=%s",
                request.plan_id,
            )
            return Verdict(action=VerdictAction.ACTION_MITIGATE)

        logger.info(
            "[TrafficAssessor] Plan registered: plan=%s agent=%s calls=%s",
            request.plan_id,
            request.agent_id,
            request.allowed_calls,
        )
        return Verdict(action=VerdictAction.ACTION_ALLOW)

    def _assess_single(self, request: AssessmentRequest) -> AssessmentResponse:
        """Assess a single traffic capture."""
        meta = request.metadata
        dest = meta.destination_address
        port = meta.destination_port

        # Rule 1: Known-safe destinations
        if dest in _SAFE_DESTINATIONS:
            return AssessmentResponse(
                request_id=request.request_id,
                verdict=Verdict(action=VerdictAction.ACTION_ALLOW),
                confidence_score=1.0,
                reasoning="Known-safe destination",
            )

        # Rule 2: High-risk ports with no plan
        if port in _HIGH_RISK_PORTS:
            plan = self._plans.get(meta.comm, None)
            if plan is None:
                logger.warning(
                    "[TrafficAssessor] High-risk port with no plan: pid=%d dest=%s:%d",
                    meta.pid,
                    dest,
                    port,
                )
                return AssessmentResponse(
                    request_id=request.request_id,
                    verdict=Verdict(action=VerdictAction.ACTION_BLOCK),
                    confidence_score=0.95,
                    reasoning=f"High-risk port {port} with no registered plan",
                )

        # Rule 3: DNS traffic → observe
        if request.protocol == ProtocolType.PROTOCOL_TYPE_DNS:
            return AssessmentResponse(
                request_id=request.request_id,
                verdict=Verdict(action=VerdictAction.ACTION_OBSERVE),
                confidence_score=0.8,
                reasoning="DNS traffic logged for forensics",
            )

        # Rule 4: Check against registered plan
        # Look up by comm (process name) since eBPF provides that
        plan = self._plans.get(meta.comm, None)
        if plan and dest in plan.allowed_calls:
            return AssessmentResponse(
                request_id=request.request_id,
                verdict=Verdict(action=VerdictAction.ACTION_ALLOW),
                confidence_score=0.9,
                reasoning=f"Destination matches plan {plan.plan_id}",
            )

        # Rule 5: Unknown → mitigate (hold for Tri-Factor)
        logger.info(
            "[TrafficAssessor] Unknown traffic pattern: pid=%d dest=%s:%d",
            meta.pid,
            dest,
            port,
        )
        return AssessmentResponse(
            request_id=request.request_id,
            verdict=Verdict(action=VerdictAction.ACTION_MITIGATE),
            confidence_score=0.6,
            reasoning="Unknown traffic pattern — held for Tri-Factor Gate review",
            metadata={
                "pid": meta.pid,
                "comm": meta.comm,
                "destination": f"{dest}:{port}",
            },
        )
