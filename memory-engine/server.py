# mcp_server/memory_extension.py
# Note: For this demo environment, we are simulating the FastMCP dependency
# if it is not installed, but the code structure is accurate.

import json
import datetime
import os
import logging
logger = logging.getLogger(__name__)


# Ensure vault is relative to THIS file, not the CWD
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VAULT_DIR = os.path.join(BASE_DIR, "vault")
os.makedirs(VAULT_DIR, exist_ok=True)

def record_agent_memory(agent_id: str, insight: str, outcome: str, tags: list[str] = None) -> str:
    """
    Records a key outcome or learning into the agent's memory.
    Use this to store 'Lessons Learned' or 'Repeated Errors'.
    """
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "agent_id": agent_id,
        "insight": insight,
        "outcome": outcome, # e.g., "SUCCESS", "BLOCKED", "HALLUCINATION"
        "tags": tags or []
    }

    # Write to local JSONL vault
    file_path = os.path.join(VAULT_DIR, f"{agent_id}_memory.jsonl")
    with open(file_path, "a") as f:
        f.write(json.dumps(entry) + "\n")

    return f"Memory successfully committed to episodic storage for {agent_id}."

if __name__ == "__main__":
    # Test Run
    print(record_agent_memory("test-agent", "Always verify API version", "BLOCKED"))
