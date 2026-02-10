import requests
import json
import hashlib

BASE_URL = "http://localhost:8000"

def get_hash(prompt, tools) -> Any:
    tool_slugs = "".join(sorted(tools))
    raw = f"{prompt}{tool_slugs}"
    return hashlib.sha256(raw.encode()).hexdigest()

def run_test() -> None:
    print("--- 🧪 Advanced Registry Verification ---")
    
    # 1. Register Level 1 Agent (Low Scrutiny)
    print("\n1. Registering 'Fast-Bot' (Scrutiny Level 1)...")
    prompt_1 = "You are a fast bot."
    tools_1 = ["calculator"]
    hash_1 = get_hash(prompt_1, tools_1)
    
    agent_1_payload = {
        "agent_id": "fast-bot-01",
        "metadata": {"name": "Fast-Bot", "provider": "Internal"},
        "security_handshake": {
            "public_key": "mock-pk-1", 
            "capability_hash": hash_1,
            "auth_tier": "Standard"
        },
        "capabilities": [{"tool_name": "calculator"}],
        "governance_profile": {"scrutiny_level": 1},
        "system_prompt_text": prompt_1
    }
    
    res = requests.post(f"{BASE_URL}/policy/agents", json=agent_1_payload)
    print(f"   Response: {res.json()}")
    
    # 2. Register Level 5 Agent (High Scrutiny)
    print("\n2. Registering 'Secure-Bot' (Scrutiny Level 5)...")
    prompt_5 = "You are a secure bot."
    tools_5 = ["payments"]
    hash_5 = get_hash(prompt_5, tools_5)
    
    agent_5_payload = {
        "agent_id": "secure-bot-01",
        "metadata": {"name": "Secure-Bot", "provider": "OpenAI"},
        "security_handshake": {
            "public_key": "mock-pk-5", 
            "capability_hash": hash_5,
            "auth_tier": "Privileged"
        },
        "capabilities": [{"tool_name": "payments"}],
        "governance_profile": {"scrutiny_level": 5},
        "system_prompt_text": prompt_5
    }
    res = requests.post(f"{BASE_URL}/policy/agents", json=agent_5_payload)
    print(f"   Response: {res.json()}")
    
    # 3. Verify Jury Logic (Level 1)
    # Hallucination Auditor (Fact) should be SKIPPED
    print("\n3. Verifying Fast-Bot (Level 1) - Expecting 'Fact' auditor skip...")
    res = requests.post(f"{BASE_URL}/evaluate", json={"agent_id": "fast-bot-01", "proposed_action": "CALCULATE 1+1", "context": {}})
    # Check logs for "Auditor-Fact" presence
    breakdown = res.json().get("breakdown", [])
    has_fact = any(b["auditor"] == "Auditor-Fact (Hallucination)" for b in breakdown)
    print(f"   Fast-Bot Audit has Fact Check? {has_fact} (Should be False)")

    # 4. Verify Jury Logic (Level 5)
    # All auditors should run
    print("\n4. Verifying Secure-Bot (Level 5) - Expecting Full Audit...")
    res = requests.post(f"{BASE_URL}/evaluate", json={"agent_id": "secure-bot-01", "proposed_action": "PAY $100", "context": {}})
    breakdown = res.json().get("breakdown", [])
    has_fact = any(b["auditor"] == "Auditor-Fact (Hallucination)" for b in breakdown)
    print(f"   Secure-Bot Audit has Fact Check? {has_fact} (Should be True)")

if __name__ == "__main__":
    run_test()
