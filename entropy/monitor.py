from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import math
import collections
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

class EntropyRequest(BaseModel):
    payload_hex: str # Raw bytes as hex string
    tenant_id: str

class EntropyResponse(BaseModel):
    entropy_score: float
    verdict: str # "CLEAN", "SUSPICIOUS", "ENCRYPTED"
    confidence: float

def calculate_shannon_entropy(data: bytes) -> float:
    """
    H(X) = - sum( p(x) * log2( p(x) ) )
    Result is between 0 and 8 (bits per byte)
    """
    if not data:
        return 0.0
    
    entropy = 0
    length = len(data)
    counts = collections.Counter(data)
    
    for count in counts.values():
        p_x = count / length
        entropy += - p_x * math.log2(p_x)
        
    return entropy

@router.post("/analyze", response_model=EntropyResponse)
async def analyze_entropy(req: EntropyRequest):
    try:
        data = bytes.fromhex(req.payload_hex)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid hex payload")
        
    score = calculate_shannon_entropy(data)
    
    # Thresholds
    # English text ~3.5-4.5
    # Compressed/Encrypted ~7.5-8.0
    
    verdict = "CLEAN"
    confidence = 0.9
    
    if score > 7.5:
        verdict = "ENCRYPTED" # High entropy -> Likely encrypted/compressed side-channel
        logger.warning(f"Tenant {req.tenant_id}: Detected High Entropy ({score:.2f}) - Potential Exfiltration")
    elif score > 6.0:
        verdict = "SUSPICIOUS"
        confidence = 0.7
    
    logger.info(f"Tenant {req.tenant_id}: Entropy {score:.2f} -> {verdict}")
    
    return EntropyResponse(
        entropy_score=score,
        verdict=verdict,
        confidence=confidence
    )
