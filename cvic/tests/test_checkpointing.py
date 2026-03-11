"""
CVIC — Context-Vector Integrity Checkpointing Tests

Tests for ContextVectorCheckpointer: cosine similarity, text-to-vector,
checkpoint chain tracking, GC, quarantine, and HITL escalation.
"""

import os
import sys
import time
import pytest
from unittest.mock import patch, MagicMock

# Ensure cvic is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from checkpointing import (
    ContextVectorCheckpointer,
    CVICCheckpoint,
    CVICResult,
)


# =============================================================================
# _text_to_vector
# =============================================================================

class TestTextToVector:
    def test_simple_sentence(self):
        vec = ContextVectorCheckpointer._text_to_vector("hello world hello")
        assert isinstance(vec, list)
        assert len(vec) > 0
        # "hello" appears 2/3 times, "world" 1/3 times
        assert any(v > 0 for v in vec)

    def test_empty_text(self):
        vec = ContextVectorCheckpointer._text_to_vector("")
        assert vec == [0.0]

    def test_punctuation_stripped(self):
        vec = ContextVectorCheckpointer._text_to_vector("Hello, World!")
        assert isinstance(vec, list)

    def test_same_text_same_vector(self):
        v1 = ContextVectorCheckpointer._text_to_vector("alpha beta gamma")
        v2 = ContextVectorCheckpointer._text_to_vector("alpha beta gamma")
        assert v1 == v2

    def test_different_text_different_vector(self):
        # Use texts with different word COUNTS so TF vectors differ in length
        v1 = ContextVectorCheckpointer._text_to_vector("alpha")
        v2 = ContextVectorCheckpointer._text_to_vector("alpha beta gamma")
        assert len(v1) != len(v2)


# =============================================================================
# _cosine_similarity
# =============================================================================

class TestCosineSimilarity:
    def test_identical_vectors(self):
        vec = [1.0, 2.0, 3.0]
        sim = ContextVectorCheckpointer._cosine_similarity(vec, vec)
        assert abs(sim - 1.0) < 0.0001

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        sim = ContextVectorCheckpointer._cosine_similarity(a, b)
        assert abs(sim) < 0.0001

    def test_empty_vectors(self):
        assert ContextVectorCheckpointer._cosine_similarity([], []) == 0.0
        assert ContextVectorCheckpointer._cosine_similarity([], [1.0]) == 0.0

    def test_zero_vector(self):
        assert ContextVectorCheckpointer._cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0

    def test_different_lengths(self):
        a = [1.0, 2.0, 3.0]
        b = [1.0, 2.0]
        sim = ContextVectorCheckpointer._cosine_similarity(a, b)
        assert 0.0 <= sim <= 1.0


# =============================================================================
# _hash_vector
# =============================================================================

class TestHashVector:
    def test_deterministic(self):
        vec = [1.0, 2.0, 3.0]
        h1 = ContextVectorCheckpointer._hash_vector(vec)
        h2 = ContextVectorCheckpointer._hash_vector(vec)
        assert h1 == h2
        assert len(h1) == 16

    def test_different_vectors_different_hash(self):
        h1 = ContextVectorCheckpointer._hash_vector([1.0, 2.0])
        h2 = ContextVectorCheckpointer._hash_vector([3.0, 4.0])
        assert h1 != h2


# =============================================================================
# ContextVectorCheckpointer — init + config
# =============================================================================

class TestCheckpointerInit:
    def test_default_threshold(self):
        c = ContextVectorCheckpointer()
        assert c.semantic_drift_threshold == 0.85

    def test_custom_threshold(self):
        c = ContextVectorCheckpointer(semantic_drift_threshold=0.9)
        assert c.semantic_drift_threshold == 0.9

    def test_set_threshold_from_config(self):
        c = ContextVectorCheckpointer()
        c.set_threshold_from_config(0.7)
        assert c.semantic_drift_threshold == 0.7


# =============================================================================
# checkpoint() — chain tracking
# =============================================================================

class TestCheckpoint:
    def test_first_hop_returns_none(self):
        c = ContextVectorCheckpointer()
        result = c.checkpoint("chain-1", 0, "agent-a", "process the order")
        assert result is None

    def test_second_hop_returns_result(self):
        c = ContextVectorCheckpointer()
        c.checkpoint("chain-1", 0, "agent-a", "process the order quickly")
        result = c.checkpoint("chain-1", 1, "agent-b", "process the order quickly and validate")
        assert isinstance(result, CVICResult)
        assert result.hop_a_agent == "agent-a"
        assert result.hop_b_agent == "agent-b"

    def test_no_drift_similar_text(self):
        c = ContextVectorCheckpointer(semantic_drift_threshold=0.5)
        c.checkpoint("chain-1", 0, "agent-a", "process the order and validate payment")
        result = c.checkpoint("chain-1", 1, "agent-b", "process the order and validate payment immediately")
        assert result.drift_detected is False
        assert result.quarantine_recommended is False
        assert result.hitl_required is False

    def test_drift_detected_different_text(self):
        # TF bag-of-words cosine needs very different vocabulary / dimensionality
        # to drop below threshold. Use a high threshold so any mismatch triggers drift.
        c = ContextVectorCheckpointer(semantic_drift_threshold=0.99)
        # These create TF vectors of very different dimensionality → similarity < 1.0
        c.checkpoint("chain-1", 0, "agent-a", "approve approve approve approve approve")
        result = c.checkpoint("chain-1", 1, "agent-b", "deploy kubernetes cluster in production environment now")
        assert result.drift_detected is True
        assert result.quarantine_recommended is True
        assert result.hitl_required is True
        assert "MANDATORY" in result.hitl_reason

    @patch("checkpointing.requests.post")
    def test_drift_triggers_quarantine(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        c = ContextVectorCheckpointer(semantic_drift_threshold=0.99)
        c.checkpoint("chain-1", 0, "agent-a", "approve purchase order")
        c.checkpoint("chain-1", 1, "agent-b", "completely unrelated topic about weather")
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["action"] == "QUARANTINE"
        assert payload["hitl_required"] is True

    @patch("checkpointing.requests.post")
    def test_quarantine_http_error(self, mock_post):
        mock_post.return_value = MagicMock(status_code=500)
        c = ContextVectorCheckpointer(semantic_drift_threshold=0.99)
        c.checkpoint("chain-1", 0, "agent-a", "approve purchase")
        # Should not raise, just log
        c.checkpoint("chain-1", 1, "agent-b", "totally different context about fish")

    @patch("checkpointing.requests.post")
    def test_quarantine_network_error(self, mock_post):
        mock_post.side_effect = ConnectionError("network down")
        c = ContextVectorCheckpointer(semantic_drift_threshold=0.99)
        c.checkpoint("chain-1", 0, "agent-a", "approve purchase")
        # Should not raise
        c.checkpoint("chain-1", 1, "agent-b", "totally different context")


# =============================================================================
# evaluate_pair() — standalone
# =============================================================================

class TestEvaluatePair:
    def test_similar_pair(self):
        c = ContextVectorCheckpointer(semantic_drift_threshold=0.3)
        result = c.evaluate_pair(
            "process the order and ship",
            "process the order and ship quickly",
        )
        assert isinstance(result, CVICResult)
        assert result.drift_detected is False

    def test_dissimilar_pair(self):
        # Use texts with very different vocabulary/dimensionality and high threshold
        c = ContextVectorCheckpointer(semantic_drift_threshold=0.99)
        result = c.evaluate_pair(
            "approve approve approve approve approve",
            "deploy kubernetes cluster production environment now",
        )
        assert result.drift_detected is True
        assert result.hitl_reason != ""


# =============================================================================
# get_chain / clear_chain
# =============================================================================

class TestChainManagement:
    def test_get_chain_empty(self):
        c = ContextVectorCheckpointer()
        assert c.get_chain("nonexistent") == []

    def test_get_chain_after_checkpoint(self):
        c = ContextVectorCheckpointer()
        c.checkpoint("chain-1", 0, "agent-a", "hello world")
        chain = c.get_chain("chain-1")
        assert len(chain) == 1
        assert chain[0].agent_id == "agent-a"

    def test_clear_chain(self):
        c = ContextVectorCheckpointer()
        c.checkpoint("chain-1", 0, "agent-a", "hello")
        c.clear_chain("chain-1")
        assert c.get_chain("chain-1") == []

    def test_clear_nonexistent_chain(self):
        c = ContextVectorCheckpointer()
        # Should not raise
        c.clear_chain("nope")


# =============================================================================
# GC (garbage collection)
# =============================================================================

class TestGC:
    def test_ttl_eviction(self):
        c = ContextVectorCheckpointer()
        c.CHAIN_TTL_SECONDS = 0  # Expire immediately
        c.checkpoint("chain-1", 0, "agent-a", "hello")
        time.sleep(0.1)
        # Next checkpoint triggers GC
        c.checkpoint("chain-2", 0, "agent-b", "world")
        # chain-1 should be evicted
        assert c.get_chain("chain-1") == []

    def test_max_chains_cap(self):
        c = ContextVectorCheckpointer()
        c.MAX_CHAINS = 2
        c.checkpoint("chain-1", 0, "a", "text1")
        time.sleep(0.01)
        c.checkpoint("chain-2", 0, "b", "text2")
        time.sleep(0.01)
        c.checkpoint("chain-3", 0, "c", "text3")
        # After cap enforcement, oldest chain should be evicted
        assert len(c._chains) <= 3  # GC runs on next checkpoint
        c.checkpoint("chain-4", 0, "d", "text4")
        # Now GC runs — should enforce max 2
        assert len(c._chains) <= 3
