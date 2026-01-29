import httpx
import os
import json
import time
import hashlib
from ecdsa import SigningKey, NIST256p

# Configuration
TRUST_REGISTRY_URL = os.getenv("TRUST_REGISTRY_URL", "http://localhost:8000")
OCX_GATEWAY_URL = os.getenv("OCX_GATEWAY_URL", "http://localhost:8002")

class SecurityError(Exception):
    """Raised when trust evaluation fails."""
    pass

class BaseOCXTool:
    """
    Base class for all OCX-governed tools.
    Enforces a handshake with the Trust Registry before execution.
    Now supports Protocol Hashing (Phase 8).
    """
    name: str = "unknown_tool"
    description: str = "No description provided."
    
    def __init__(self):
        # Demo: Generate a fresh key pair for this agent instance
        # In production, this would be loaded from a secure vault
        self._sk = SigningKey.generate(curve=NIST256p)
        self._vk = self._sk.verifying_key
        # We'll share the VK in hex as the Agent ID for this demo verification
        self.agent_id = self._vk.to_string().hex()
        
    def run_impl(self, **kwargs):
        """
        Implementation of the tool logic. 
        MUST be overridden by subclasses.
        """
        raise NotImplementedError("Tool must implement run_impl")

    def evaluate_trust(self, context: dict) -> bool:
        """
        Calls the Trust Registry (via Gateway) to evaluate the intent.
        Returns True if allowed, False if blocked.
        """
        try:
            # Construct the evaluation payload
            payload = {
                "agent_id": self.agent_id, # Use Public Key Hex as ID for verification
                "proposed_action": self.name,
                "context": context
            }
            
            payload_json = json.dumps(payload, sort_keys=True)
            timestamp = str(time.time())
            nonce = os.urandom(8).hex()
            
            # 1. Hashing: SHA-256(Body + Timestamp + Nonce)
            msg = f"{payload_json}{timestamp}{nonce}"
            payload_hash = hashlib.sha256(msg.encode()).hexdigest()
            
            # 2. Signing: ECDSA Sign(Hash)
            signature = self._sk.sign(payload_hash.encode()).hex()
            
            headers = {
                "X-Agent-ID": self.agent_id,
                "X-Timestamp": timestamp,
                "X-Nonce": nonce,
                "X-Payload-Hash": payload_hash,
                "X-Signature": signature,
                "X-Version": "Gemini-2.0-Flash-Exp",
                "X-Governance-Tier": "Tier-1 (High Risk)",
                "X-Auth-Scope": "bigquery.read, crm.write"
            }
            
            # Call Gateway (Watcher) which forwards to Trust Registry
            # Phase 8: We call the Gateway, which verifies, then calls Trust Registry
            # To simulate this flow without changing the entire architecture:
            # We call the Trust Registry endpoint, but we imagine the Gateway intercepts it.
            # OR we call the Gateway directly if it exposes an evaluate endpoint? 
            # The Gateway exposes /messages for MCP. 
            # For this SDK, let's assume we are calling the Trust Registry directly 
            # BUT we enforce the headers that the Gateway WOULD verify.
            # Wait, the Gateway (OCX Core) intercepts /messages. 
            # The SDK usually runs IN the agent. The agent talks to the Gateway.
            # So the SDK should target the Gateway. 
            # However, BaseOCXTool currently calls TRUST_REGISTRY_URL directly in `evaluate_trust`.
            # Let's update it to hit the Gateway if we want "In-line" governance.
            # BUT, the Gateway `ocx-core` logic we built handles `tools/call` interception.
            # BaseOCXTool is a proactive check.
            # Let's keep calling Trust Registry but with the Headers so the "Watcher" (if it were a sidecar) could see them.
            # Or better: The Gateway `ocx-core` should verify these headers.
            # For this implementation, we will perform the HTTP call to the Registry with these headers.
            # And we will update the Registry (or a middleware in it) to verify them? 
            # The Requirement says: "The Watcher (Apigee) validates... before passing to The Jury".
            # So ideally: SDK -> Gateway -> Jury.
            # Currently: SDK -> Jury.
            # We will simulate the "Watcher" verification inside the Jury Service entry point (or a middleware there)
            # OR logic in the Gateway if the SDK calls the Gateway.
            
            with httpx.Client() as client:
                res = client.post(
                    f"{TRUST_REGISTRY_URL}/evaluate", 
                    json=payload, 
                    headers=headers,
                    timeout=5.0
                )
                
                if res.status_code != 200:
                    print(f"⚠️ Trust Registry Error: {res.status_code} {res.text}")
                    return False
                
                data = res.json()
                
                # Log the verdict
                status = data.get("status", "BLOCKED")
                score = data.get("trust_score", 0.0)
                reason = data.get("reasoning", "No reason provided")
                
                print(f"⚖️  OCX Verdict for '{self.name}': {status} (Score: {score:.2f})")
                print(f"    Reason: {reason}")
                
                return status != "BLOCKED"

        except Exception as e:
            print(f"❌ Trust Check Failed (Exception): {e}")
            return False

    def run(self, **kwargs):
        """
        The main entry point. Enforces governance handshake.
        """
        print(f"🔒 OCX Governance: Verifying intent for '{self.name}'...")
        
        if not self.evaluate_trust(kwargs):
            raise SecurityError(f"OCX Blocked Action: {self.name}. See Trust Registry logs for details.")
            
        print(f"✅ Access Granted. Executing '{self.name}'...")
        return self.run_impl(**kwargs)
