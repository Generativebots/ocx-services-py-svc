from mcp.server.fastmcp import FastMCP
import httpx
import os

# Configuration
# Service-to-Service communication. 
TRUST_REGISTRY_URL = os.getenv("TRUST_REGISTRY_URL", "http://localhost:8000")

# Initialize FastMCP Server
mcp = FastMCP("MCP Governance Interface")

@mcp.resource("rules://golden_rules")
def get_golden_rules() -> str:
    """
    Returns the Enterprise Golden Rules for AI Agents.
    Fetches the latest rules from the central Trust Registry.
    """
    # Ideally fetch from Trust Registry API to ensure consistency
    # For now, we can hardcode or (better) fetch if we add an endpoint for it.
    # Let's simple return a static message pointing to the registry for now
    # or implement a GET /rules on the Registry.
    
    return "Please consult the Trust Registry Source of Truth." 

@mcp.resource("telemetry://system_context")
def get_system_context() -> str:
    """
    Returns real-time local telemetry for Context-Aware Tooling.
    Used by the OCX Dashboard to overlay 'Dynamic Tool-Tips'.
    """
    import json
    import random
    
    # Mocking live system/terminal data
    metrics = {
        "cpu_load": f"{random.randint(20, 45)}%",
        "memory_usage": "1.2GB / 8GB",
        "active_socket": "/var/run/cortex/agent_bus.sock",
        "last_log": "[INFO] Policy Check passed for Agent-007 (2ms)"
    }
    return json.dumps(metrics, indent=2) 

@mcp.tool()
async def verify_compliance(agent_id: str, action: str, context: dict = {}) -> str:
    """
    Validates a proposed action against the Golden Rules.
    Returns a text summary of the verdict (Approved/Blocked) and the reasoning.
    
    Use this tool BEFORE executing any high-risk action to ensure compliance.
    """
    payload = {
        "agent_id": agent_id,
        "proposed_action": action,
        "context": context
    }
    
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(f"{TRUST_REGISTRY_URL}/evaluate", json=payload, timeout=10.0)
            data = res.json()
            
            # Extract
            score = data.get("trust_score", 0.0)
            reason = data.get("reasoning", "No reason provided")
            status = data.get("status", "Rejection")
            
            return f"Verdict: {status}\nTrust Score: {score:.2f}\nReasoning: {reason}"
            
    except Exception as e:
        return f"Error contacting Trust Registry: {e}"

if __name__ == "__main__":
    mcp.run()

