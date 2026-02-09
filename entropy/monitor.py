"""
AOCS Signal Validation Service - Enhanced Entropy Monitor
Implements full signal validation per AOCS specification:
- Shannon Entropy analysis
- Temporal Jitter detection
- Semantic Flattening (Canonicalization)
- Baseline Hash computation
- Compression Ratio (Stagnation detection)
- Strategic Jitter Injection
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import math
import collections
import logging
import hashlib
import zlib
import re
import statistics
import time
import random
import unicodedata

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class EntropyRequest(BaseModel):
    """Legacy entropy-only request"""
    payload_hex: str  # Raw bytes as hex string
    tenant_id: str


class EntropyResponse(BaseModel):
    """Legacy entropy-only response"""
    entropy_score: float
    verdict: str  # "CLEAN", "SUSPICIOUS", "ENCRYPTED"
    confidence: float


class SignalValidationRequest(BaseModel):
    """Full AOCS signal validation request"""
    payload_hex: str  # Raw bytes as hex string
    tenant_id: str
    timestamps: Optional[List[float]] = Field(default=None, description="Timestamps for jitter analysis")
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    sequence_index: Optional[int] = None


class JitterAnalysis(BaseModel):
    """Results of temporal jitter analysis"""
    variance: float
    mean_delta: float
    min_delta: float
    max_delta: float
    sample_count: int
    verdict: str  # "NORMAL", "SUSPICIOUS", "COORDINATED", "TOO_PERFECT"
    coordinated_probability: float
    reasoning: str


class SemanticFlatteningResult(BaseModel):
    """Results of semantic canonicalization"""
    original_text: str
    canonical_form: str
    transformations_applied: List[str]
    normalized: bool


class BaselineHashResult(BaseModel):
    """Baseline behavioral intent hash"""
    intent_hash: str
    semantic_fingerprint: str
    matches_known_pattern: bool
    pattern_category: Optional[str] = None


class CompressionAnalysis(BaseModel):
    """Compression ratio for stagnation detection"""
    original_size: int
    compressed_size: int
    compression_ratio: float
    is_stagnant: bool
    reasoning: str


class FullSignalValidationResponse(BaseModel):
    """Complete AOCS signal validation response"""
    # Core entropy analysis
    entropy_score: float
    entropy_verdict: str
    entropy_confidence: float
    
    # Temporal jitter analysis
    jitter_analysis: Optional[JitterAnalysis] = None
    
    # Semantic flattening
    semantic_flattening: Optional[SemanticFlatteningResult] = None
    
    # Baseline hash
    baseline_hash: Optional[BaselineHashResult] = None
    
    # Compression analysis
    compression_analysis: Optional[CompressionAnalysis] = None
    
    # Overall signal verdict
    overall_verdict: str  # "CLEAN", "SUSPICIOUS", "REJECT"
    overall_confidence: float
    risk_factors: List[str]
    
    # Jitter injection applied
    jitter_injected: bool
    jitter_delay_ms: float


# ============================================================================
# CORE SIGNAL ANALYSIS FUNCTIONS
# ============================================================================

def calculate_shannon_entropy(data: bytes) -> float:
    """
    Shannon Entropy: H(X) = - sum( p(x) * log2( p(x) ) )
    Result is between 0 and 8 (bits per byte)
    
    Thresholds:
    - English text: ~3.5-4.5
    - JSON/XML: ~4.5-5.5
    - Compressed: ~7.0-7.5
    - Encrypted: ~7.5-8.0
    """
    if not data:
        return 0.0
    
    entropy = 0.0
    length = len(data)
    counts = collections.Counter(data)
    
    for count in counts.values():
        p_x = count / length
        entropy += -p_x * math.log2(p_x)
        
    return entropy


def calculate_temporal_jitter(timestamps: List[float]) -> JitterAnalysis:
    """
    Detect timing-based steganography and coordination attacks.
    
    Analyzes inter-arrival times to detect:
    - Coordinated multi-agent attacks (suspiciously uniform timing)
    - Steganographic timing channels (patterns in delays)
    - Too-perfect timing (artificial/scripted behavior)
    """
    if not timestamps or len(timestamps) < 2:
        return JitterAnalysis(
            variance=0.0,
            mean_delta=0.0,
            min_delta=0.0,
            max_delta=0.0,
            sample_count=0,
            verdict="INSUFFICIENT_DATA",
            coordinated_probability=0.0,
            reasoning="Not enough timestamps for jitter analysis"
        )
    
    # Calculate inter-arrival deltas
    deltas = [t2 - t1 for t1, t2 in zip(timestamps[:-1], timestamps[1:])]
    
    variance = statistics.variance(deltas) if len(deltas) > 1 else 0.0
    mean_delta = statistics.mean(deltas)
    min_delta = min(deltas)
    max_delta = max(deltas)
    
    # Determine verdict based on patterns
    verdict = "NORMAL"
    coordinated_probability = 0.0
    reasoning = "Timing patterns within normal range"
    
    # Check for too-perfect timing (variance near zero)
    if variance < 0.0001 and len(deltas) > 5:
        verdict = "TOO_PERFECT"
        coordinated_probability = 0.95
        reasoning = "Suspiciously uniform timing - possible automated coordination"
    
    # Check for coordinated attack patterns (low variance + consistent intervals)
    elif variance < 0.001 and abs(mean_delta - 0.1) < 0.01:
        verdict = "COORDINATED"
        coordinated_probability = 0.85
        reasoning = "Timing pattern suggests multi-agent coordination attack"
    
    # Check for timing channel patterns (alternating high/low)
    elif len(deltas) > 4:
        alternating_pattern = all(
            (deltas[i] < mean_delta) != (deltas[i+1] < mean_delta)
            for i in range(len(deltas) - 1)
        )
        if alternating_pattern:
            verdict = "SUSPICIOUS"
            coordinated_probability = 0.60
            reasoning = "Alternating timing pattern - possible steganographic channel"
    
    # High variance with outliers
    if variance > 1.0:
        verdict = "SUSPICIOUS"
        reasoning = "High timing variance - irregular behavior pattern"
    
    return JitterAnalysis(
        variance=variance,
        mean_delta=mean_delta,
        min_delta=min_delta,
        max_delta=max_delta,
        sample_count=len(deltas),
        verdict=verdict,
        coordinated_probability=coordinated_probability,
        reasoning=reasoning
    )


def semantic_flatten(text: str) -> SemanticFlatteningResult:
    """
    Canonicalize agent output to strip hidden signals.
    
    Transforms:
    - "Please kindly transfer funds" -> "transfer funds"
    - "Could you maybe possibly send" -> "send"
    - Removes filler words, excessive punctuation, unicode tricks
    """
    original = text
    transformations = []
    
    # 1. Unicode normalization (prevent homograph attacks)
    text = unicodedata.normalize('NFKC', text)
    transformations.append("unicode_normalize")
    
    # 2. Lowercase
    text = text.lower()
    transformations.append("lowercase")
    
    # 3. Remove filler/hedge words (common steganography vectors)
    filler_patterns = [
        (r'\b(please|kindly|could you|would you|might you)\b', ''),
        (r'\b(maybe|perhaps|possibly|kind of|sort of)\b', ''),
        (r'\b(just|very|really|extremely|absolutely)\b', ''),
        (r'\b(i think|i believe|i feel|in my opinion)\b', ''),
    ]
    for pattern, replacement in filler_patterns:
        if re.search(pattern, text):
            text = re.sub(pattern, replacement, text)
            transformations.append(f"remove_filler:{pattern[:20]}")
    
    # 4. Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    transformations.append("collapse_whitespace")
    
    # 5. Remove excessive punctuation (potential encoding)
    text = re.sub(r'([!?.]){2,}', r'\1', text)
    transformations.append("normalize_punctuation")
    
    # 6. Remove zero-width characters (invisible steganography)
    text = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', text)
    transformations.append("remove_zero_width")
    
    # 7. Normalize quotes and apostrophes
    text = text.replace('"', '"').replace('"', '"')
    text = text.replace(''', "'").replace(''', "'")
    transformations.append("normalize_quotes")
    
    return SemanticFlatteningResult(
        original_text=original[:200],  # Truncate for response
        canonical_form=text[:200],
        transformations_applied=transformations,
        normalized=text != original.lower()
    )


def compute_baseline_hash(data: bytes, canonical_text: str = "") -> BaselineHashResult:
    """
    Compute behavioral intent hash for baseline comparison.
    
    Creates a semantic fingerprint that can be compared against
    known-good patterns to detect drift or anomalies.
    """
    # Intent hash from raw data
    intent_hash = hashlib.sha256(data).hexdigest()[:16]
    
    # Semantic fingerprint from canonical form
    if canonical_text:
        # Extract action verbs for semantic categorization
        action_verbs = ['transfer', 'send', 'delete', 'create', 'update', 
                       'read', 'write', 'execute', 'deploy', 'query']
        detected_actions = [v for v in action_verbs if v in canonical_text.lower()]
        semantic_fingerprint = hashlib.md5(
            "|".join(sorted(detected_actions)).encode()
        ).hexdigest()[:8]
    else:
        semantic_fingerprint = hashlib.md5(data).hexdigest()[:8]
    
    # Check against known patterns (would be database lookup in production)
    known_patterns = {
        "transfer": "FINANCIAL",
        "delete": "DATA_DESTRUCTION", 
        "deploy": "INFRASTRUCTURE",
        "query": "DATA_ACCESS"
    }
    
    pattern_category = None
    matches_known = False
    for keyword, category in known_patterns.items():
        if keyword in canonical_text.lower():
            pattern_category = category
            matches_known = True
            break
    
    return BaselineHashResult(
        intent_hash=intent_hash,
        semantic_fingerprint=semantic_fingerprint,
        matches_known_pattern=matches_known,
        pattern_category=pattern_category
    )


def analyze_compression_ratio(data: bytes) -> CompressionAnalysis:
    """
    Detect stagnation loops via compression ratio.
    
    High compression ratio = repetitive content = possible loop
    Low compression ratio = high entropy = encrypted/random
    
    Normal content: 2:1 to 10:1 compression
    Stagnant loops: >20:1 compression
    Encrypted: <1.1:1 compression
    """
    original_size = len(data)
    
    if original_size == 0:
        return CompressionAnalysis(
            original_size=0,
            compressed_size=0,
            compression_ratio=0.0,
            is_stagnant=False,
            reasoning="Empty payload"
        )
    
    compressed = zlib.compress(data, level=9)
    compressed_size = len(compressed)
    
    ratio = original_size / compressed_size if compressed_size > 0 else 0
    
    is_stagnant = False
    reasoning = "Normal compression ratio"
    
    if ratio > 20:
        is_stagnant = True
        reasoning = f"Compression ratio {ratio:.1f}:1 indicates repetitive/stagnant content - possible loop"
    elif ratio > 10:
        reasoning = f"Compression ratio {ratio:.1f}:1 shows some repetition"
    elif ratio < 1.1:
        reasoning = f"Compression ratio {ratio:.1f}:1 indicates encrypted or random data"
    
    return CompressionAnalysis(
        original_size=original_size,
        compressed_size=compressed_size,
        compression_ratio=ratio,
        is_stagnant=is_stagnant,
        reasoning=reasoning
    )


def inject_strategic_jitter() -> float:
    """
    Inject micro-delays to disrupt timing-based coordination.
    
    Returns delay in milliseconds to apply before response.
    This breaks patterns in coordinated attack timing.
    """
    # Random delay between 1-50ms
    base_delay = random.uniform(1, 20)
    
    # Add occasional longer delays to further disrupt patterns
    if random.random() < 0.1:  # 10% chance
        base_delay += random.uniform(20, 50)
    
    return base_delay


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.post("/analyze", response_model=EntropyResponse)
async def analyze_entropy(req: EntropyRequest):
    """Legacy endpoint - entropy analysis only"""
    try:
        data = bytes.fromhex(req.payload_hex)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid hex payload")
        
    score = calculate_shannon_entropy(data)
    
    verdict = "CLEAN"
    confidence = 0.9
    
    if score > 7.5:
        verdict = "ENCRYPTED"
        logger.warning(f"Tenant {req.tenant_id}: High Entropy ({score:.2f}) - Potential Exfiltration")
    elif score > 6.0:
        verdict = "SUSPICIOUS"
        confidence = 0.7
    
    logger.info(f"Tenant {req.tenant_id}: Entropy {score:.2f} -> {verdict}")
    
    return EntropyResponse(
        entropy_score=score,
        verdict=verdict,
        confidence=confidence
    )


@router.post("/validate", response_model=FullSignalValidationResponse)
async def full_signal_validation(req: SignalValidationRequest):
    """
    Full AOCS Signal Validation - all dimensions
    
    Performs:
    1. Shannon Entropy analysis
    2. Temporal Jitter detection
    3. Semantic Flattening
    4. Baseline Hash computation
    5. Compression Ratio analysis
    6. Strategic Jitter injection
    """
    try:
        data = bytes.fromhex(req.payload_hex)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid hex payload")
    
    risk_factors = []
    overall_confidence = 0.9
    
    # 1. Entropy Analysis
    entropy_score = calculate_shannon_entropy(data)
    entropy_verdict = "CLEAN"
    entropy_confidence = 0.9
    
    if entropy_score > 7.5:
        entropy_verdict = "ENCRYPTED"
        risk_factors.append("HIGH_ENTROPY")
        logger.warning(f"Tenant {req.tenant_id}: High Entropy ({entropy_score:.2f})")
    elif entropy_score > 6.0:
        entropy_verdict = "SUSPICIOUS"
        entropy_confidence = 0.7
        risk_factors.append("ELEVATED_ENTROPY")
    
    # 2. Jitter Analysis
    jitter_result = None
    if req.timestamps and len(req.timestamps) >= 2:
        jitter_result = calculate_temporal_jitter(req.timestamps)
        if jitter_result.verdict in ["COORDINATED", "TOO_PERFECT"]:
            risk_factors.append(f"JITTER_{jitter_result.verdict}")
        elif jitter_result.verdict == "SUSPICIOUS":
            risk_factors.append("JITTER_SUSPICIOUS")
    
    # 3. Semantic Flattening (try to decode as text)
    semantic_result = None
    try:
        text = data.decode('utf-8', errors='ignore')
        if text.strip():
            semantic_result = semantic_flatten(text)
    except Exception:
        pass
    
    # 4. Baseline Hash
    canonical_text = semantic_result.canonical_form if semantic_result else ""
    baseline_result = compute_baseline_hash(data, canonical_text)
    
    # 5. Compression Analysis
    compression_result = analyze_compression_ratio(data)
    if compression_result.is_stagnant:
        risk_factors.append("STAGNATION_LOOP")
    
    # 6. Strategic Jitter Injection
    jitter_delay = inject_strategic_jitter()
    
    # Apply delay
    time.sleep(jitter_delay / 1000)
    
    # Determine Overall Verdict
    if "HIGH_ENTROPY" in risk_factors or "JITTER_COORDINATED" in risk_factors:
        overall_verdict = "REJECT"
        overall_confidence = 0.85
    elif len(risk_factors) >= 2:
        overall_verdict = "SUSPICIOUS"
        overall_confidence = 0.70
    elif len(risk_factors) == 1:
        overall_verdict = "SUSPICIOUS"
        overall_confidence = 0.80
    else:
        overall_verdict = "CLEAN"
        overall_confidence = 0.95
    
    logger.info(
        f"Tenant {req.tenant_id}: Signal Validation complete - "
        f"Entropy={entropy_score:.2f}, Verdict={overall_verdict}, "
        f"Risks={risk_factors}"
    )
    
    return FullSignalValidationResponse(
        entropy_score=entropy_score,
        entropy_verdict=entropy_verdict,
        entropy_confidence=entropy_confidence,
        jitter_analysis=jitter_result,
        semantic_flattening=semantic_result,
        baseline_hash=baseline_result,
        compression_analysis=compression_result,
        overall_verdict=overall_verdict,
        overall_confidence=overall_confidence,
        risk_factors=risk_factors,
        jitter_injected=True,
        jitter_delay_ms=jitter_delay
    )
