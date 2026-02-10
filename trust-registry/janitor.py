import time
import requests
import sqlite3
import threading

# The Janitor Agent
# Runs in the background (or as a separate process)
# Monitors Trust Scores and Auto-Regulates the Nervous System (Go)

import os
import logging
logger = logging.getLogger(__name__)


GO_ADMIN_URL = os.getenv("GO_ADMIN_URL", "http://localhost:8080/admin/policy")
DB_PATH = "ledger.db"

def monitor_ledger_loop() -> None:
    print("🧹 [Janitor] Starting Autonomous Reputation Monitor...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    while True:
        try:
            # 1. Check for "Problematic Agents" (Avg Score < 40 in last 5 txns)
            cursor.execute("""
                SELECT agent_id, AVG(score) as avg_score 
                FROM (
                    SELECT agent_id, score 
                    FROM ledger 
                    ORDER BY timestamp DESC 
                    LIMIT 20
                ) 
                GROUP BY agent_id 
                HAVING avg_score < 0.40
            """)
            
            bad_actors = cursor.fetchall()
            for agent_id, avg_score in bad_actors:
                print(f"🧹 [Janitor] DETECTED POOR PERFORMANCE: {agent_id} (Avg: {avg_score:.1f})")
                print(f"   -> Initiating AUTONOMOUS THROTTLE...")
                
                # Active Measure: Call Go Backend to Revoke Permissions
                try:
                    resp = requests.post(GO_ADMIN_URL, json={
                        "agent_id": agent_id,
                        "action": "THROTTLE"
                    })
                    if resp.status_code == 200:
                        print(f"   -> ✅ SUCCESS: {agent_id} has been throttled at the Gateway.")
                except Exception as e:
                    print(f"   -> ❌ FAILED to contact Nervous System: {e}")

            # 2. Check for "Redemption" (Avg Score > 90) - To restore
            # ... (Logic for Restore would be similar) ...

            time.sleep(10) # Run every 10 seconds
            
        except Exception as e:
            print(f"🧹 [Janitor] Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    monitor_ledger_loop()
