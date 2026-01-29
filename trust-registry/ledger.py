import datetime
import hashlib
import json
import sqlite3
import os

class Ledger:
    """
    The Truth. Manages immutable logs and agent reputation.
    Simulates Blockchain + BigQuery.
    """
    def __init__(self, db_path="ledger.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            # Audit Log Table (Simulating BigQuery + Hash Chain)
            conn.execute('''
                CREATE TABLE IF NOT EXISTS ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME,
                    agent_id TEXT,
                    previous_hash TEXT,
                    block_hash TEXT,
                    payload_hash TEXT,
                    score REAL,
                    verdict TEXT,
                    metadata TEXT
                )
            ''')
            # Reputation Table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS reputation (
                    agent_id TEXT PRIMARY KEY,
                    reliability_score REAL,
                    total_txns INTEGER
                )
            ''')

    def _get_last_hash(self) -> str:
        """Retrieves the hash of the last block in the ledger."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT block_hash FROM ledger ORDER BY id DESC LIMIT 1")
            last_hash = cursor.fetchone()
            return last_hash[0] if last_hash else "0" * 64 # Genesis block hash

    def log_transaction(self, agent_id: str, payload_hash: str, score: float, verdict: str, metadata: dict = {}) -> str:
        """
        Writes to Immutable Log (SQLite + Hash Chain).
        Now includes extended metadata (Tier, Version, etc).
        """
        previous_hash = self._get_last_hash()
        timestamp = datetime.datetime.now().isoformat()
        
        # Block Data
        metadata_json = json.dumps(metadata, sort_keys=True) # Ensure consistent serialization for hashing
        block_data = f"{previous_hash}{agent_id}{payload_hash}{score}{verdict}{timestamp}{metadata_json}"
        block_hash = hashlib.sha256(block_data.encode()).hexdigest()
        
        # Insert
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO ledger (timestamp, agent_id, previous_hash, block_hash, payload_hash, score, verdict, metadata) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (timestamp, agent_id, previous_hash, block_hash, payload_hash, score, verdict, metadata_json)
            )
            
            # Update Reputation Profile in background
            self._update_reputation(conn, agent_id, score)
        
        print(f"📒 Ledger: Recorded txn {block_hash[:8]}... | Reputation updated.")
        return block_hash

    def _update_reputation(self, conn, agent_id, current_score):
        cur = conn.execute("SELECT reliability_score, total_txns FROM reputation WHERE agent_id = ?", (agent_id,))
        row = cur.fetchone()
        
        if row:
            old_score, count = row
            # Simple Rolling Average
            new_count = count + 1
            new_score = ((old_score * count) + current_score) / new_count
            conn.execute("UPDATE reputation SET reliability_score = ?, total_txns = ? WHERE agent_id = ?", (new_score, new_count, agent_id))
        else:
            conn.execute("INSERT INTO reputation (agent_id, reliability_score, total_txns) VALUES (?, ?, ?)", (agent_id, current_score, 1))

    def get_recent_transactions(self, limit=50):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM ledger ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_daily_stats(self):
        """
        Returns average trust score per day (simulated or real).
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                # Simple average over all time for now, or last 7 days groupings
                # SQLite substring for YYYY-MM-DD: substr(timestamp, 1, 10)
                cursor = conn.execute('''
                    SELECT substr(timestamp, 1, 10) as day, AVG(score) as avg_score, COUNT(*) as count 
                    FROM ledger 
                    GROUP BY day 
                    ORDER BY day DESC 
                    LIMIT 7
                ''')
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"ERROR in get_daily_stats: {e}")
    def check_weekly_drift(self, agent_id: str):
        """
        Calculates Delta Trust = AvgScore(This Week) - AvgScore(Last Week).
        Returns alert if Delta < -0.10.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Calculate dates
                now = datetime.datetime.now()
                seven_days_ago = (now - datetime.timedelta(days=7)).isoformat()
                fourteen_days_ago = (now - datetime.timedelta(days=14)).isoformat()
                
                # Query This Week
                cur1 = conn.execute("SELECT AVG(score) FROM ledger WHERE agent_id = ? AND timestamp > ?", (agent_id, seven_days_ago))
                avg_this_week = cur1.fetchone()[0] or 0.0
                
                # Query Last Week
                cur2 = conn.execute("SELECT AVG(score) FROM ledger WHERE agent_id = ? AND timestamp <= ? AND timestamp > ?", (agent_id, seven_days_ago, fourteen_days_ago))
                avg_last_week = cur2.fetchone()[0] or 0.0
                
                # Calculate Delta
                # If no history for last week, assume baseline of 1.0 (or just skip drift check)
                if avg_last_week == 0.0:
                    delta = 0.0
                else:
                    delta = avg_this_week - avg_last_week
                
                return {
                    "agent_id": agent_id,
                    "avg_this_week": round(avg_this_week, 2),
                    "avg_last_week": round(avg_last_week, 2),
                    "delta": round(delta, 2),
                    "drift_detected": delta < -0.10
                }
        except Exception as e:
            print(f"ERROR checking drift: {e}")
            return {"error": str(e)}

    def get_recent_failures(self, agent_id: str, hours: int = 24) -> int:
        """
        Counts 'BLOCKED' verdicts for this agent in the last N hours.
        Used for Exponential Trust Decay.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                since = (datetime.datetime.now() - datetime.timedelta(hours=hours)).isoformat()
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM ledger WHERE agent_id = ? AND verdict = 'BLOCKED' AND timestamp > ?", 
                    (agent_id, since)
                )
                count = cursor.fetchone()[0]
                return count
        except Exception as e:
            print(f"ERROR getting recent failures: {e}")
            return 0

    def verify_shadow_execution(self, agent_id: str, tool_name: str) -> bool:
        """
        Proof of Execution Check (The "Ledger Auditor").
        Checks if a 'Success' claim by an agent correlates with a real API event log.
        """
        # In a real system, this queries the 'API Gateway Logs' or 'System Events' table.
        # Here we simulate: If tool_name is 'CRM_UPDATE', we verify against a mock external log.
        
        # Mock External Verification
        # If agent says "I updated the CRM", checking...
        
        import random
        # Simulate 95% generic success match, but 5% hallucination rate
        verified = random.random() > 0.05 
        
        if not verified:
            print(f"👻 [Shadow Verifier] HALLUCINATION DETECTED: Agent {agent_id} claimed '{tool_name}' but no corresponding event found in System Logs.")
            
        return verified
