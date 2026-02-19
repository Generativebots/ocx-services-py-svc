"""
Conformance Checker — validates execution traces against expected workflows.

Compares actual agent execution traces against discovered or defined
process models to detect deviations and policy violations.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from .miner import DiscoveredProcess, Trace

logger = logging.getLogger("conformance-checker")


@dataclass
class ConformanceResult:
    """Result of checking a trace against a process model."""
    trace_id: str
    process_id: str
    conformant: bool
    fitness_score: float  # 0.0 to 1.0 — how well the trace fits
    deviations: List[Dict[str, Any]] = field(default_factory=list)
    missing_activities: List[str] = field(default_factory=list)
    unexpected_activities: List[str] = field(default_factory=list)
    out_of_order: List[Dict[str, str]] = field(default_factory=list)


class ConformanceChecker:
    """
    Checks execution traces against expected process models.

    Deviation types detected:
    1. Missing activities — expected steps were skipped
    2. Unexpected activities — steps not in the model were executed
    3. Out-of-order — correct activities but wrong sequence
    """

    def __init__(self):
        self.models: Dict[str, DiscoveredProcess] = {}

    def register_model(self, model: DiscoveredProcess) -> None:
        """Register a process model for conformance checking."""
        self.models[model.process_id] = model
        logger.info(
            f"Registered process model {model.process_id}: "
            f"{len(model.activities)} activities"
        )

    def check_trace(
        self, trace: Trace, process_id: str
    ) -> Optional[ConformanceResult]:
        """Check a single trace against a registered process model."""
        model = self.models.get(process_id)
        if not model:
            logger.warning(f"Process model {process_id} not found")
            return None

        trace_activities = trace.activity_names
        model_activities = model.activities
        deviations = []

        # 1. Missing activities
        missing = list(model_activities - set(trace_activities))

        # 2. Unexpected activities
        unexpected = [a for a in trace_activities if a not in model_activities]

        # 3. Out-of-order transitions
        out_of_order = []
        for i in range(len(trace_activities) - 1):
            current = trace_activities[i]
            next_act = trace_activities[i + 1]
            if current in model.transitions:
                if next_act not in model.transitions[current]:
                    out_of_order.append(
                        {"from": current, "to": next_act, "position": i}
                    )
                    deviations.append(
                        {
                            "type": "out_of_order",
                            "from": current,
                            "to": next_act,
                            "position": i,
                        }
                    )

        for act in missing:
            deviations.append({"type": "missing", "activity": act})
        for act in unexpected:
            deviations.append({"type": "unexpected", "activity": act})

        # Calculate fitness score
        total_expected = len(model_activities)
        total_actual = len(set(trace_activities))
        matched = len(model_activities & set(trace_activities))

        if total_expected == 0:
            fitness = 1.0
        else:
            # Fitness = (matched - penalties) / expected
            penalty = len(out_of_order) * 0.1 + len(unexpected) * 0.05
            fitness = max(0.0, min(1.0, (matched - penalty) / total_expected))

        conformant = fitness >= 0.8 and len(out_of_order) == 0

        return ConformanceResult(
            trace_id=trace.trace_id,
            process_id=process_id,
            conformant=conformant,
            fitness_score=round(fitness, 3),
            deviations=deviations,
            missing_activities=missing,
            unexpected_activities=unexpected,
            out_of_order=out_of_order,
        )

    def check_batch(
        self, traces: List[Trace], process_id: str
    ) -> List[ConformanceResult]:
        """Check multiple traces against a process model."""
        results = []
        for trace in traces:
            result = self.check_trace(trace, process_id)
            if result:
                results.append(result)

        conformant_count = sum(1 for r in results if r.conformant)
        logger.info(
            f"Batch conformance check: {conformant_count}/{len(results)} conformant "
            f"({conformant_count/len(results)*100:.1f}%)" if results else ""
        )

        return results
