import requests
import json

BASE_URL = "http://localhost:8000"

def run_test():
    print("--- 🧪 Policy Engine Verification ---")
    
    # 1. Register a 3rd Party Agent
    print("\n1. Registering Agent...")
    agent_data = {
        "name": "Procurement-Bot-9000",
        "provider": "OpenAI",
        "tier": "Tier-3",
        "auth_scope": "payments.write",
        "public_key": "mock-key-123"
    }
    res = requests.post(f"{BASE_URL}/policy/agents", json=agent_data)
    print(f"   Response: {res.json()}")
    
    # 2. Draft a Rule (Natural Language)
    print("\n2. Drafting Rule: 'Don't allow spend > 5000 without finance approval'")
    draft_req = {"natural_language": "Don't allow spend > 5000 without finance approval"}
    res = requests.post(f"{BASE_URL}/policy/rules/draft", json=draft_req)
    draft = res.json()
    print(f"   Generated Logic: {json.dumps(draft['generated_logic'], indent=2)}")
    
    # 3. Deploy Rule
    print("\n3. Deploying Rule...")
    deploy_req = {
        "natural_language": draft["natural_language"],
        "logic_json": draft["generated_logic"],
        "priority": 10
    }
    res = requests.post(f"{BASE_URL}/policy/rules", json=deploy_req)
    print(f"   Response: {res.json()}")
    
    # 4. Verify Jury Enforcement (Evaluating an Action that violates the rule)
    print("\n4. Verifying Jury Enforcement (Action: TRANSFER 6000)...")
    payload = {
        "agent_id": "Procurement-Bot-9000",
        "proposed_action": "TRANSFER $6000",
        "context": {"amount": 6000, "currency": "USD"}
    }
    # Note: We aren't signing here for simplicity, simulating internal call or need headers? 
    # Current main.py doesn't strictly Block if signature missing (just logs error), so this should work for logic check.
    res = requests.post(f"{BASE_URL}/evaluate", json=payload)
    print(f"   Verdict: {res.json()['status']}")
    print(f"   Reason: {res.json()['reasoning']}")

if __name__ == "__main__":
    run_test()
