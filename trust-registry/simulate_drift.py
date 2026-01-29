import sqlite3
import datetime
import requests
import time

DB_PATH = "ledger.db"
AGENT_ID = "drift-agent-01"

def insert_txn(timestamp, score):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO ledger (timestamp, agent_id, block_hash, score, verdict, metadata) VALUES (?, ?, 'mockhash', ?, 'ALLOWED', '{}')",
            (timestamp, AGENT_ID, score)
        )

def verify_drift():
    # 1. Clear old data for this agent
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM ledger WHERE agent_id = ?", (AGENT_ID,))
    
    # 2. Insert "Last Week" Data (High Scores - Avg 0.95)
    # 10 days ago
    t_last = (datetime.datetime.now() - datetime.timedelta(days=10)).isoformat()
    insert_txn(t_last, 0.95)
    insert_txn(t_last, 0.96)
    
    # 3. Insert "This Week" Data (Low Scores - Avg 0.70)
    # 2 days ago
    t_now = (datetime.datetime.now() - datetime.timedelta(days=2)).isoformat()
    insert_txn(t_now, 0.70)
    insert_txn(t_now, 0.71)
    
    print("✅ Drift Data Inserted.")
    
    # 4. Call API
    response = requests.get(f"http://localhost:8000/ledger/health/{AGENT_ID}")
    data = response.json()
    
    print("🔍 API Response:", data)
    
    if data["drift_detected"] == True and data["delta"] < -0.10:
        print("✅ SUCCESS: Drift Detected!")
    else:
        print("❌ FAILURE: Drift NOT Detected.")

if __name__ == "__main__":
    verify_drift()
