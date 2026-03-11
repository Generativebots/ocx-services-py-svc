"""
Conflict Detector — tests for policy contradiction, redundancy, precedence detection.
Patent: CIP conflict detection system.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from conflict_detector import ConflictDetector, ConflictType


class TestConflictDetector:
    def _make_detector(self):
        return ConflictDetector()

    def test_detect_contradiction(self):
        """Two policies with same trigger but opposite actions."""
        detector = self._make_detector()
        policies = [
            {
                "policy_id": "A",
                "trigger_intent": "buy",
                "logic": {">": [{"var": "amount"}, 500]},
                "action": {"on_fail": "BLOCK"},
                "tier": "GLOBAL",
            },
            {
                "policy_id": "B",
                "trigger_intent": "buy",
                "logic": {">": [{"var": "amount"}, 500]},
                "action": {"on_fail": "ALLOW"},
                "tier": "GLOBAL",
            },
        ]
        conflicts = detector.detect_conflicts(policies)
        assert any(c.conflict_type == ConflictType.CONTRADICTION for c in conflicts)

    def test_detect_redundancy(self):
        """Two identical policies should be flagged as redundant."""
        detector = self._make_detector()
        policies = [
            {
                "policy_id": "A",
                "trigger_intent": "buy",
                "logic": {">": [{"var": "amount"}, 500]},
                "action": {"on_fail": "BLOCK"},
                "tier": "GLOBAL",
            },
            {
                "policy_id": "B",
                "trigger_intent": "buy",
                "logic": {">": [{"var": "amount"}, 500]},
                "action": {"on_fail": "BLOCK"},
                "tier": "GLOBAL",
            },
        ]
        conflicts = detector.detect_conflicts(policies)
        assert any(c.conflict_type == ConflictType.REDUNDANCY for c in conflicts)

    def test_detect_precedence_issue(self):
        """Same tier, same trigger, different actions → precedence ambiguity."""
        detector = self._make_detector()
        policies = [
            {
                "policy_id": "A",
                "trigger_intent": "send",
                "logic": {">": [{"var": "size"}, 100]},
                "action": {"on_fail": "BLOCK"},
                "tier": "CONTEXTUAL",
            },
            {
                "policy_id": "B",
                "trigger_intent": "send",
                "logic": {">": [{"var": "size"}, 200]},
                "action": {"on_fail": "FLAG"},
                "tier": "CONTEXTUAL",
            },
        ]
        conflicts = detector.detect_conflicts(policies)
        assert any(c.conflict_type == ConflictType.PRECEDENCE for c in conflicts)

    def test_no_conflicts_for_different_triggers(self):
        """Policies with different triggers should not conflict."""
        detector = self._make_detector()
        policies = [
            {
                "policy_id": "A",
                "trigger_intent": "buy",
                "logic": {">": [{"var": "amount"}, 500]},
                "action": {"on_fail": "BLOCK"},
                "tier": "GLOBAL",
            },
            {
                "policy_id": "B",
                "trigger_intent": "sell",
                "logic": {">": [{"var": "amount"}, 500]},
                "action": {"on_fail": "BLOCK"},
                "tier": "GLOBAL",
            },
        ]
        conflicts = detector.detect_conflicts(policies)
        assert len(conflicts) == 0

    def test_empty_policy_list(self):
        detector = self._make_detector()
        conflicts = detector.detect_conflicts([])
        assert conflicts == []

    def test_single_policy_no_conflict(self):
        detector = self._make_detector()
        conflicts = detector.detect_conflicts([{
            "policy_id": "A", "trigger_intent": "buy",
            "logic": {">": [{"var": "amount"}, 500]},
            "action": {"on_fail": "BLOCK"}, "tier": "GLOBAL"
        }])
        assert conflicts == []
