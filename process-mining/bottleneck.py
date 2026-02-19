"""
Bottleneck Analyzer — identifies slow steps and throughput issues.

Analyzes execution traces to find performance bottlenecks,
resource contention, and throughput limitations.
"""

import logging
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .miner import Trace

logger = logging.getLogger("bottleneck-analyzer")


@dataclass
class ActivityPerformance:
    """Performance statistics for a single activity."""
    activity_name: str
    execution_count: int = 0
    total_duration_ms: float = 0.0
    avg_duration_ms: float = 0.0
    median_duration_ms: float = 0.0
    p95_duration_ms: float = 0.0
    p99_duration_ms: float = 0.0
    min_duration_ms: float = float("inf")
    max_duration_ms: float = 0.0
    is_bottleneck: bool = False
    bottleneck_reason: str = ""


@dataclass
class TransitionPerformance:
    """Performance of transitions between activities (wait times)."""
    from_activity: str
    to_activity: str
    avg_wait_ms: float = 0.0
    max_wait_ms: float = 0.0
    count: int = 0


@dataclass
class BottleneckReport:
    """Complete bottleneck analysis report."""
    total_traces: int
    total_activities: int
    avg_trace_duration_ms: float
    activities: List[ActivityPerformance]
    transitions: List[TransitionPerformance]
    bottlenecks: List[ActivityPerformance]
    recommendations: List[str] = field(default_factory=list)


class BottleneckAnalyzer:
    """
    Identifies performance bottlenecks in agent workflows.

    Analysis dimensions:
    1. Activity duration — which steps take the longest
    2. Wait times — delays between consecutive activities
    3. Frequency × duration — total time consumed
    4. Variability — high stddev indicates inconsistent performance
    """

    def __init__(self, bottleneck_threshold_percentile: float = 90.0):
        self.threshold_percentile = bottleneck_threshold_percentile

    def analyze(self, traces: List[Trace]) -> BottleneckReport:
        """Perform full bottleneck analysis on a set of traces."""
        if not traces:
            return BottleneckReport(
                total_traces=0,
                total_activities=0,
                avg_trace_duration_ms=0,
                activities=[],
                transitions=[],
                bottlenecks=[],
            )

        # Collect durations per activity
        activity_durations: Dict[str, List[float]] = defaultdict(list)
        transition_waits: Dict[str, List[float]] = defaultdict(list)
        trace_durations: List[float] = []

        for trace in traces:
            trace_total = sum(a.duration_ms for a in trace.activities)
            trace_durations.append(trace_total)

            for i, activity in enumerate(trace.activities):
                activity_durations[activity.name].append(activity.duration_ms)

                # Compute wait time between activities
                if i < len(trace.activities) - 1:
                    next_act = trace.activities[i + 1]
                    wait = (
                        next_act.timestamp - activity.timestamp
                    ).total_seconds() * 1000 - activity.duration_ms
                    if wait > 0:
                        key = f"{activity.name}→{next_act.name}"
                        transition_waits[key].append(wait)

        # Build activity performance stats
        activity_perfs: List[ActivityPerformance] = []
        for name, durations in activity_durations.items():
            sorted_d = sorted(durations)
            perf = ActivityPerformance(
                activity_name=name,
                execution_count=len(durations),
                total_duration_ms=sum(durations),
                avg_duration_ms=statistics.mean(durations),
                median_duration_ms=statistics.median(durations),
                p95_duration_ms=self._percentile(sorted_d, 95),
                p99_duration_ms=self._percentile(sorted_d, 99),
                min_duration_ms=min(durations),
                max_duration_ms=max(durations),
            )
            activity_perfs.append(perf)

        # Identify bottlenecks (activities above threshold)
        all_avgs = [p.avg_duration_ms for p in activity_perfs]
        threshold = self._percentile(sorted(all_avgs), self.threshold_percentile)

        bottlenecks = []
        for perf in activity_perfs:
            if perf.avg_duration_ms >= threshold:
                perf.is_bottleneck = True
                perf.bottleneck_reason = (
                    f"avg duration {perf.avg_duration_ms:.1f}ms exceeds "
                    f"P{self.threshold_percentile:.0f} threshold of {threshold:.1f}ms"
                )
                bottlenecks.append(perf)

        # Build transition stats
        transition_perfs = []
        for key, waits in transition_waits.items():
            parts = key.split("→")
            transition_perfs.append(
                TransitionPerformance(
                    from_activity=parts[0],
                    to_activity=parts[1],
                    avg_wait_ms=statistics.mean(waits),
                    max_wait_ms=max(waits),
                    count=len(waits),
                )
            )

        # Generate recommendations
        recommendations = self._generate_recommendations(
            bottlenecks, transition_perfs, trace_durations
        )

        avg_trace_dur = statistics.mean(trace_durations) if trace_durations else 0

        report = BottleneckReport(
            total_traces=len(traces),
            total_activities=sum(p.execution_count for p in activity_perfs),
            avg_trace_duration_ms=avg_trace_dur,
            activities=sorted(
                activity_perfs, key=lambda p: p.avg_duration_ms, reverse=True
            ),
            transitions=sorted(
                transition_perfs, key=lambda t: t.avg_wait_ms, reverse=True
            ),
            bottlenecks=bottlenecks,
            recommendations=recommendations,
        )

        logger.info(
            f"Bottleneck analysis: {len(traces)} traces, "
            f"{len(bottlenecks)} bottlenecks found"
        )

        return report

    def _generate_recommendations(
        self,
        bottlenecks: List[ActivityPerformance],
        transitions: List[TransitionPerformance],
        trace_durations: List[float],
    ) -> List[str]:
        """Generate actionable recommendations."""
        recs = []

        for b in bottlenecks:
            recs.append(
                f"Activity '{b.activity_name}' is a bottleneck "
                f"(avg {b.avg_duration_ms:.0f}ms, P99 {b.p99_duration_ms:.0f}ms). "
                f"Consider caching, parallelization, or SOP optimization."
            )

        # Check for high-variance activities
        for b in bottlenecks:
            if b.max_duration_ms > b.avg_duration_ms * 5:
                recs.append(
                    f"Activity '{b.activity_name}' shows high variance "
                    f"(max={b.max_duration_ms:.0f}ms vs avg={b.avg_duration_ms:.0f}ms). "
                    f"Investigate intermittent slowdowns."
                )

        # Check for slow transitions
        for t in transitions[:3]:  # Top 3 slowest transitions
            if t.avg_wait_ms > 500:
                recs.append(
                    f"Transition '{t.from_activity}' → '{t.to_activity}' "
                    f"has high wait time (avg {t.avg_wait_ms:.0f}ms). "
                    f"Consider pre-fetching or pipeline optimization."
                )

        return recs

    @staticmethod
    def _percentile(sorted_values: List[float], pct: float) -> float:
        """Compute percentile from a sorted list."""
        if not sorted_values:
            return 0.0
        idx = int(len(sorted_values) * pct / 100)
        idx = min(idx, len(sorted_values) - 1)
        return sorted_values[idx]
