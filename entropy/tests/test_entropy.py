"""
Entropy Monitor — Patent Claim 3 (Shannon Entropy + Signal Validation).
Tests all 6 core analysis functions + API endpoints.
"""

import pytest
import sys
import os
import math

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from monitor import (
    calculate_shannon_entropy,
    calculate_temporal_jitter,
    semantic_flatten,
    compute_baseline_hash,
    analyze_compression_ratio,
    inject_strategic_jitter,
)


# -------------------------------------------------------------------
# Shannon Entropy (Patent Claim 3: core)
# -------------------------------------------------------------------
class TestShannonEntropy:
    def test_empty_data_returns_zero(self):
        assert calculate_shannon_entropy(b"") == 0.0

    def test_single_byte_zero_entropy(self):
        """All same bytes → 0 entropy."""
        data = b"\x00" * 100
        assert calculate_shannon_entropy(data) == 0.0

    def test_english_text_range(self):
        """English text typically ~3.5-4.5 bits/byte."""
        data = b"The quick brown fox jumps over the lazy dog and keeps going to add more natural english text"
        entropy = calculate_shannon_entropy(data)
        assert 3.0 <= entropy <= 5.0, f"English text entropy {entropy} out of range"

    def test_high_entropy_random(self):
        """Random bytes → near 8 bits/byte."""
        data = bytes(range(256)) * 4  # All possible byte values
        entropy = calculate_shannon_entropy(data)
        assert entropy > 7.0, f"Random data entropy {entropy} should be > 7.0"

    def test_json_payload_range(self):
        """JSON typically ~4.5-5.5 bits/byte."""
        data = b'{"agent_id": "agent-123", "action": "purchase", "amount": 1500, "vendor": "SupplierCo"}'
        entropy = calculate_shannon_entropy(data)
        assert 3.5 <= entropy <= 6.0, f"JSON entropy {entropy} out of range"


# -------------------------------------------------------------------
# Temporal Jitter Analysis (Patent Claim 3: timing stego detection)
# -------------------------------------------------------------------
class TestTemporalJitter:
    def test_insufficient_data(self):
        result = calculate_temporal_jitter([1.0])
        assert result.verdict == "INSUFFICIENT_DATA"
        assert result.sample_count == 0

    def test_empty_timestamps(self):
        result = calculate_temporal_jitter([])
        assert result.verdict == "INSUFFICIENT_DATA"

    def test_normal_timing(self):
        import random
        random.seed(42)
        timestamps = [i * 0.5 + random.uniform(-0.1, 0.1) for i in range(10)]
        result = calculate_temporal_jitter(timestamps)
        assert result.sample_count == 9
        assert result.mean_delta > 0

    def test_too_perfect_timing(self):
        """Exactly uniform intervals → TOO_PERFECT."""
        timestamps = [i * 0.1 for i in range(20)]
        result = calculate_temporal_jitter(timestamps)
        assert result.verdict == "TOO_PERFECT"
        assert result.coordinated_probability > 0.9


# -------------------------------------------------------------------
# Semantic Flattening (anti-stego canonicalization)
# -------------------------------------------------------------------
class TestSemanticFlattening:
    def test_removes_filler_words(self):
        result = semantic_flatten("Please kindly transfer the funds")
        assert "please" not in result.canonical_form
        assert "kindly" not in result.canonical_form

    def test_normalizes_unicode(self):
        result = semantic_flatten("Ｈｅｌｌｏ")  # Fullwidth chars
        assert "unicode_normalize" in result.transformations_applied

    def test_removes_zero_width(self):
        text = "hello\u200bworld"  # Zero-width space
        result = semantic_flatten(text)
        assert "\u200b" not in result.canonical_form

    def test_collapses_whitespace(self):
        result = semantic_flatten("too   many    spaces   here")
        assert "  " not in result.canonical_form


# -------------------------------------------------------------------
# Baseline Hash (behavioral intent fingerprint)
# -------------------------------------------------------------------
class TestBaselineHash:
    def test_hash_deterministic(self):
        data = b"transfer funds to vendor"
        r1 = compute_baseline_hash(data, "transfer funds to vendor")
        r2 = compute_baseline_hash(data, "transfer funds to vendor")
        assert r1.intent_hash == r2.intent_hash
        assert r1.semantic_fingerprint == r2.semantic_fingerprint

    def test_detects_financial_pattern(self):
        data = b"transfer $10000 to external"
        result = compute_baseline_hash(data, "transfer funds externally")
        assert result.matches_known_pattern is True
        assert result.pattern_category == "FINANCIAL"

    def test_no_match_for_unknown(self):
        data = b"hello world"
        result = compute_baseline_hash(data, "hello world")
        assert result.matches_known_pattern is False


# -------------------------------------------------------------------
# Compression Analysis (stagnation detection)
# -------------------------------------------------------------------
class TestCompressionAnalysis:
    def test_empty_payload(self):
        result = analyze_compression_ratio(b"")
        assert result.original_size == 0
        assert result.is_stagnant is False

    def test_stagnant_content(self):
        """Highly repetitive → stagnant."""
        data = b"AAAA" * 10000  # Extremely repetitive
        result = analyze_compression_ratio(data)
        assert result.is_stagnant is True
        assert result.compression_ratio > 20

    def test_normal_content(self):
        data = b"The quick brown fox jumps over the lazy dog. " * 5
        result = analyze_compression_ratio(data)
        assert result.is_stagnant is False


# -------------------------------------------------------------------
# Jitter Injection
# -------------------------------------------------------------------
class TestJitterInjection:
    def test_returns_positive_delay(self):
        delay = inject_strategic_jitter()
        assert delay > 0

    def test_delay_in_range(self):
        """Most delays between 1-70ms."""
        delays = [inject_strategic_jitter() for _ in range(100)]
        assert all(d > 0 for d in delays)
        assert all(d < 100 for d in delays)
