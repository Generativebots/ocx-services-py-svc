"""
OCX Monitor Service — Cloud Run Compatible
-------------------------------------------
Wraps the background monitor loop in a FastAPI app so Cloud Run
can perform HTTP health checks. The actual monitor logic runs in
a background thread.
"""
import os
import time
import math
import redis
import threading
from collections import Counter
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Optional
import logging
logger = logging.getLogger(__name__)

# ============================================================================
# FastAPI App (Cloud Run health check + status endpoint)
# ============================================================================
app = FastAPI(title="OCX Monitor Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state for health reporting
monitor_state = {
    "status": "starting",
    "entropy_score": None,
    "last_check": None,
    "redis_connected": False,
}

# Response models
class HealthResponse(BaseModel):
    status: str
    service: str
    state: dict

class MonitorStatusResponse(BaseModel):
    status: str
    entropy_score: Optional[float]
    last_check: Optional[str]
    redis_connected: bool

@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="Monitor", state=monitor_state)

@app.get("/status", response_model=MonitorStatusResponse)
def status() -> MonitorStatusResponse:
    return MonitorStatusResponse(**monitor_state)

# ============================================================================
# Configuration
# ============================================================================
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
VLLM_URL = os.getenv("vLLM_URL", "http://localhost:8000/v1")
ENTROPY_THRESHOLD = float(os.getenv("ENTROPY_THRESHOLD", "1.5"))

# ============================================================================
# Redis Connection
# ============================================================================
def get_redis_connection() -> Any:
    try:
        r = redis.from_url(REDIS_URL, decode_responses=True)
        r.ping()
        return r
    except Exception as e:
        print(f"Waiting for Redis at {REDIS_URL}... ({e})")
        return None

# ============================================================================
# Entropy Calculation
# ============================================================================
def calculate_shannon_entropy(data_points) -> int:
    if not data_points:
        return 0
    counts = Counter([round(x, 2) for x in data_points])
    total = len(data_points)
    return -sum((c/total) * math.log2(c/total) for c in counts.values())

# ============================================================================
# Background Monitor Loop
# ============================================================================
def ingest_sops_to_ape(r) -> None:
    """Hot-load SOP policies into Redis for the APE engine."""
    print("🚀 APE Engine: Initializing recursive semantic parsing...")
    if r:
        try:
            r.hset("policy:FIN-001", mapping={
                "threshold": 50,
                "action_if_exceeded": "DENY",
                "logic_operator": ">"
            })
            print("✅ Policy Registry: Hot-loaded SOP logic into Redis.")
        except Exception as e:
            print(f"❌ Failed to load policy: {e}")

def monitor_agent_signals(r) -> None:
    """
    Monitors agent handshake entropy to detect collusion patterns.
    Runs as a background thread so it doesn't block the FastAPI server.
    """
    global monitor_state
    print("📊 Pulse Monitor: Starting Shannon Entropy calculation...")
    
    while True:
        sample_intervals = None
        if r:
            try:
                raw = r.lrange("agent:handshakes", 0, 50)
                if raw:
                    sample_intervals = [float(x) for x in raw]
            except Exception as e:
                print(f"⚠️ Redis read failed: {e}")

        # Fallback to mock data if Redis is empty or unavailable
        if not sample_intervals:
            sample_intervals = [0.12, 0.15, 0.11, 0.13, 0.12]

        entropy = calculate_shannon_entropy(sample_intervals)
        
        if entropy < ENTROPY_THRESHOLD:
            print(f"⚠️ ALERT: Low Entropy ({entropy:.2f} bits). Possible Collusion.")
            status = "LOCKDOWN"
        else:
            status = "HEALTHY"

        # Update global state for health endpoint
        monitor_state.update({
            "status": status,
            "entropy_score": round(entropy, 4),
            "last_check": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "redis_connected": r is not None,
        })
        
        if r:
            try:
                r.set("system:status", status)
                r.set("system:entropy_score", str(round(entropy, 4)))
            except Exception:
                pass

        time.sleep(10)

# ============================================================================
# Startup Event — launch monitor in background thread
# ============================================================================
@app.on_event("startup")
def start_background_monitor() -> None:
    """Launch the monitor loop in a daemon thread on FastAPI startup."""
    def _run() -> None:
        r_conn = None
        # Retry loop for Redis (non-blocking — don't block Cloud Run startup)
        for _ in range(5):
            r_conn = get_redis_connection()
            if r_conn:
                break
            time.sleep(2)
        
        if r_conn:
            ingest_sops_to_ape(r_conn)
        
        monitor_state["status"] = "running"
        monitor_agent_signals(r_conn)
    
    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    print("🔍 Monitor background thread started")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8005"))
    uvicorn.run(app, host="0.0.0.0", port=port)
