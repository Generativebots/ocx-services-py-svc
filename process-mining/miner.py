"""
Process Miner — Extracts workflow patterns from agent execution logs.

Uses the Alpha Algorithm variant to discover process models from event logs.
Each trace is a sequence of activities performed by agents.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("process-miner")


@dataclass
class Activity:
    """A single activity/step in a workflow trace."""
    name: str
    agent_id: str
    timestamp: datetime
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Trace:
    """A complete execution trace — ordered sequence of activities."""
    trace_id: str
    tenant_id: str
    activities: List[Activity] = field(default_factory=list)

    @property
    def activity_names(self) -> List[str]:
        return [a.name for a in self.activities]


@dataclass
class DiscoveredProcess:
    """A workflow model discovered from traces."""
    process_id: str
    name: str
    activities: Set[str]
    start_activities: Set[str]
    end_activities: Set[str]
    transitions: Dict[str, Set[str]]  # activity → set of successors
    frequency: int  # how many traces follow this pattern
    avg_duration_ms: float = 0.0


class ProcessMiner:
    """
    Discovers workflow patterns from agent evidence logs.

    Algorithm:
    1. Ingest execution traces (from evidence vault or audit logs)
    2. Build directly-follows graph
    3. Identify start/end activities
    4. Discover parallel and sequential patterns
    5. Output discovered process models
    """

    def __init__(self):
        self.traces: List[Trace] = []
        self.directly_follows: Dict[str, Dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        self.activity_freq: Dict[str, int] = defaultdict(int)
        self.start_activities: Dict[str, int] = defaultdict(int)
        self.end_activities: Dict[str, int] = defaultdict(int)

    def add_trace(self, trace: Trace) -> None:
        """Add an execution trace to the miner."""
        self.traces.append(trace)

        activities = trace.activity_names
        if not activities:
            return

        # Track start/end activities
        self.start_activities[activities[0]] += 1
        self.end_activities[activities[-1]] += 1

        # Build directly-follows relations
        for i, act in enumerate(activities):
            self.activity_freq[act] += 1
            if i < len(activities) - 1:
                self.directly_follows[act][activities[i + 1]] += 1

    def add_trace_from_log(
        self, trace_id: str, tenant_id: str, events: List[Dict[str, Any]]
    ) -> None:
        """Build a trace from raw log events."""
        activities = []
        for event in sorted(events, key=lambda e: e.get("timestamp", "")):
            activities.append(
                Activity(
                    name=event.get("activity", event.get("action", "unknown")),
                    agent_id=event.get("agent_id", ""),
                    timestamp=datetime.fromisoformat(
                        event.get("timestamp", datetime.now().isoformat())
                    ),
                    duration_ms=event.get("duration_ms", 0.0),
                    metadata=event.get("metadata", {}),
                )
            )
        self.add_trace(
            Trace(trace_id=trace_id, tenant_id=tenant_id, activities=activities)
        )

    def discover_processes(
        self, min_frequency: int = 2, traces: Optional[List["Trace"]] = None
    ) -> List[DiscoveredProcess]:
        """
        Run Alpha-miner-style discovery to extract process models.

        Returns a list of DiscoveredProcess objects representing
        the most common workflow patterns.
        """
        source_traces = traces if traces is not None else self.traces
        if not source_traces:
            return []

        # Group traces by their activity sequence pattern
        pattern_groups: Dict[str, List[Trace]] = defaultdict(list)
        for trace in source_traces:
            pattern_key = "→".join(trace.activity_names)
            pattern_groups[pattern_key].append(trace)

        discovered = []
        for pattern_key, group_traces in pattern_groups.items():
            if len(group_traces) < min_frequency:
                continue

            activities = set()
            starts = set()
            ends = set()
            transitions: Dict[str, Set[str]] = defaultdict(set)
            total_duration = 0.0

            for trace in group_traces:
                names = trace.activity_names
                activities.update(names)
                if names:
                    starts.add(names[0])
                    ends.add(names[-1])
                for i in range(len(names) - 1):
                    transitions[names[i]].add(names[i + 1])
                total_duration += sum(
                    a.duration_ms for a in trace.activities
                )

            discovered.append(
                DiscoveredProcess(
                    process_id=f"proc-{len(discovered)+1}",
                    name=f"Process {len(discovered)+1}",
                    activities=activities,
                    start_activities=starts,
                    end_activities=ends,
                    transitions=dict(transitions),
                    frequency=len(group_traces),
                    avg_duration_ms=(
                        total_duration / len(group_traces) if group_traces else 0
                    ),
                )
            )

        # Sort by frequency, most common first
        discovered.sort(key=lambda p: p.frequency, reverse=True)
        logger.info(f"Discovered {len(discovered)} process models from {len(source_traces)} traces")

        return discovered

    def get_directly_follows_graph(self) -> Dict[str, Dict[str, int]]:
        """Return the directly-follows graph with frequencies."""
        return dict(self.directly_follows)

    def get_activity_statistics(self) -> Dict[str, Dict[str, Any]]:
        """Get frequency and connection stats for each activity."""
        stats = {}
        for activity, freq in self.activity_freq.items():
            successors = self.directly_follows.get(activity, {})
            predecessors = {
                a: counts.get(activity, 0)
                for a, counts in self.directly_follows.items()
                if activity in counts
            }
            stats[activity] = {
                "frequency": freq,
                "successor_count": len(successors),
                "predecessor_count": len(predecessors),
                "is_start": activity in self.start_activities,
                "is_end": activity in self.end_activities,
            }
        return stats
