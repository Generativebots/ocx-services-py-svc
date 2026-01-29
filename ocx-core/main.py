import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
import httpx
import json
import uuid

app = FastAPI(title="OCX Gateway")

# Configuration
CRM_SERVER_URL = "http://localhost:8001"
TRUST_REGISTRY_URL = "http://localhost:8000" # Or internal import if same process

# Logic moved to Trust Registry Call


@app.post("/messages")
async def handle_mcp_message(request: Request):
    """
    Intercepts JSON-RPC messages destined for the CRM Server.
    """
    try:
        body = await request.json()
    except:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Only intercept tool calls
    if body.get("method") == "notifications/tools/call" or body.get("method") == "tools/call":
        params = body.get("params", {})
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        print(f"🛑 OCX Intercepting Call: {tool_name} with args {arguments}")

        # 1. THE WATCHER (Trace Injection)
        trace_id = f"ocx-{uuid.uuid4()}"
        
        # 1b. The Heart Check (Optimization: Call API, don't import logic directly to decouple)
        # We assume the 'agent_id' comes from a header or context. Mocking it here.
        agent_id = "agent-gateway-user" 
        
        payload_eval = {
            "agent_id": agent_id,
            "proposed_action": f"Tool: {tool_name}",
            "context": arguments,
            "trace_id": trace_id
        }
        
        try:
            async with httpx.AsyncClient() as eval_client:
                # Call The Heart
                res = await eval_client.post(f"{TRUST_REGISTRY_URL}/evaluate", json=payload_eval)
                data = res.json()
        except Exception as e:
            # Fail closed
            print(f"❌ Heart connection failed: {e}")
            return JSONResponse(content={"error": "Governance Unavailable"}, status_code=503)

        score = data.get("trust_score", 0.0)
        status = data.get("status", "BLOCKED")
        reason = data.get("reasoning", "Unknown")
        
        print(f"⚖️  Verdict: {status} (Score {score}) | {reason}")

        if status == "BLOCKED":
            # BLOCKED
            return JSONResponse(content={
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "error": {
                    "code": -32000, # Application error
                    "message": f"OCX BLOCKED: {reason} (Score: {score})"
                }
            })
            
        # Add Trace Header for downstream (if supported)
        # request.headers["OCX-Trace-ID"] = trace_id 


    # 2. Forward to CRM Server if Safe (or if not a tool call)
    async with httpx.AsyncClient() as client:
        try:
            # Forward the query params (sessionId is critical for SSE)
            response = await client.post(
                f"{CRM_SERVER_URL}/messages", 
                params=request.query_params,
                json=body,
                timeout=30.0,
                follow_redirects=True
            )
            return JSONResponse(content=response.json(), status_code=response.status_code)
        except Exception as e:
            return JSONResponse(content={"error": str(e)}, status_code=502)

@app.get("/sse")
async def proxy_sse(request: Request):
    """
    Proxies the SSE connection to the CRM server.
    """
    client = httpx.AsyncClient()
    # We need to keep the client open for the stream? 
    # Proper proxying of SSE is tricky with httpx inside a generator.
    # We will just stream the response content.
    
    req = client.build_request("GET", f"{CRM_SERVER_URL}/sse", timeout=None)
    r = await client.send(req, stream=True)

    async def event_generator():
        async for chunk in r.aiter_bytes():
            yield chunk
        await r.aclose()
        await client.aclose()
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
