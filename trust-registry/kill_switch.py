import json
import datetime

class KillSwitch:
    """
    Circuit Breaker and Enforcement Arm.
    """
    THRESHOLD = 0.3
    
    def check_and_enforce(self, agent_id: str, score: float, verdict: str):
        """
        Checks if the score is below threshold.
        If so, triggers the Kill-switch (mock).
        """
        if score < self.THRESHOLD:
            print(f"🚫 Kill-Switch Triggered for Agent {agent_id}!")
    
            # 1. Pub/Sub Trigger (Eventarc)
            # Payload: {"block_agent": "Procure-Bot-12", "duration": "300s"}
            event_payload = {
                "block_agent": agent_id,
                "duration": "300s",
                "reason": "Trust Score Dropped below Threshold",
                "timestamp": datetime.datetime.now().isoformat()
            }
            
            # Simulate API Call to Eventarc
            print(f"🔥 Eventarc Event Dispatched: {json.dumps(event_payload)}")
            print("   -> 403 Forbidden forced.")
            return True # Triggered
        
        return False # Safe
