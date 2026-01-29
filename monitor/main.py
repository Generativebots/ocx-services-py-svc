import os
import time
import math
import redis
import requests
from collections import Counter

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
VLLM_URL = os.getenv("vLLM_URL", "http://localhost:8000/v1")
ENTROPY_THRESHOLD = 1.5

# Connect to Redis
# r = redis.from_url(REDIS_URL, decode_responses=True)

def get_redis_connection():
    try:
        r = redis.from_url(REDIS_URL, decode_responses=True)
        r.ping()
        return r
    except Exception as e:
        print(f"Waiting for Redis at {REDIS_URL}... ({e})")
        return None

def calculate_shannon_entropy(data_points):
    if not data_points: return 0
    counts = Counter([round(x, 2) for x in data_points])
    total = len(data_points)
    return -sum((c/total) * math.log2(c/total) for c in counts.values())

def ingest_sops_to_ape(r):
    """
    Simulates sending local Markdown SOPs to vLLM 
    and hot-loading results into Redis.
    """
    print("🚀 APE Engine: Initializing recursive semantic parsing...")
    # In a real scenario, you'd iterate over /app/sops/*.md
    # For now, we simulate a successful extraction loop
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

def monitor_agent_signals(r):
    """
    Monitors the 'pulse' of agent handshakes stored in a Redis stream
    to detect low-entropy collusion patterns.
    """
    print("📊 Pulse Monitor: Starting Shannon Entropy calculation...")
    while True:
        # Simulate fetching recent handshake intervals from a Redis list/stream
        # In production, use r.lrange("agent:handshakes", 0, 50)
        sample_intervals = [0.12, 0.15, 0.11, 0.13, 0.12] # Mock deterministic data
        
        entropy = calculate_shannon_entropy(sample_intervals)
        
        if entropy < ENTROPY_THRESHOLD:
            print(f"⚠️ ALERT: Low Entropy Detected ({entropy:.2f} bits). Possible Collusion.")
            if r:
                try:
                    r.set("system:status", "LOCKDOWN")
                except:
                    pass
        else:
            if r:
                try:
                    r.set("system:status", "HEALTHY")
                except:
                    pass
            
        time.sleep(10)

if __name__ == "__main__":
    r_conn = None
    # Retry loop for Redis
    while r_conn is None:
        r_conn = get_redis_connection()
        if r_conn is None:
            time.sleep(2)
            
    ingest_sops_to_ape(r_conn)
    monitor_agent_signals(r_conn)
