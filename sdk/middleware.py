"""
OCX Universal Middleware Connector.

Drop-in middleware for ANY Python web framework. Intercepts incoming
requests, detects AI tool calls, and routes them through OCX governance
before allowing execution.

Supported Frameworks:
    - FastAPI / Starlette (ASGI)
    - Flask / Quart (WSGI + ASGI)
    - Django (WSGI)
    - AIOHTTP (async)
    - Tornado
    - Generic WSGI / ASGI
    - Any framework via the ProtocolBridge adapter

Usage:

    # FastAPI
    from sdk.middleware import OCXFastAPIMiddleware
    app.add_middleware(OCXFastAPIMiddleware, client=ocx_client)

    # Flask
    from sdk.middleware import OCXFlaskMiddleware
    app.wsgi_app = OCXFlaskMiddleware(app.wsgi_app, client=ocx_client)

    # Django (settings.py)
    MIDDLEWARE = ["sdk.middleware.OCXDjangoMiddleware", ...]
    OCX_CLIENT = OCXClient(...)

    # Generic — wrap any callable
    from sdk.middleware import OCXProtocolBridge
    bridge = OCXProtocolBridge(ocx_client)
    result = bridge.govern("execute_payment", {"amount": 100})
"""

import json
import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("ocx.middleware")


# =========================================================================
# Protocol Bridge — the core connector for ANY integration
# =========================================================================

class OCXProtocolBridge:
    """
    Universal protocol bridge that connects any AI system to OCX governance.
    
    This is the lowest-level connector. All framework middlewares use this.
    You can also use it directly for custom integrations.
    
    Usage:
        bridge = OCXProtocolBridge(ocx_client)
        
        # Before executing any AI tool call:
        result = bridge.govern("execute_payment", {"amount": 100})
        if result["verdict"] == "ALLOW":
            execute_payment(100)
    """
    
    def __init__(self, client, fail_open: bool = False) -> None:
        """
        Args:
            client: OCXClient instance
            fail_open: If True, allow tool calls when OCX is unreachable.
                       If False (default), block on failure (fail-secure).
        """
        import os
        from .client import OCXClient
        self.client: OCXClient = client
        self.fail_open = fail_open
        
        # T6 fix: Warn loudly in production when fail_open is enabled
        if fail_open:
            env = os.getenv("OCX_ENV", "development").lower()
            if env in ("production", "prod", "staging"):
                logger.warning(
                    "⚠️  OCX SDK initialized with fail_open=True in %s environment. "
                    "Tool calls will be ALLOWED without governance when the Go backend "
                    "is unreachable. Set fail_open=False for fail-secure behavior.",
                    env
                )
            else:
                logger.info("OCX SDK initialized with fail_open=True (dev/test mode)")
    
    def govern(
        self,
        tool_name: str,
        arguments: Dict[str, Any] = None,
        agent_id: str = None,
        tenant_id: str = None,
        model: str = "",
        protocol: str = "bridge",
        session_id: str = "",
    ) -> Dict[str, Any]:
        """
        Send a tool call through OCX governance and return the verdict.
        
        Returns:
            dict with keys: verdict, action_class, reason, trust_score,
            governance_tax, escrow_id, entitlement_id, evidence_hash
        """
        result = self.client.execute_tool(
            tool_name=tool_name,
            arguments=arguments or {},
            model=model,
            session_id=session_id,
            protocol=protocol,
        )
        return {
            "verdict": result.verdict,
            "action_class": result.action_class,
            "reason": result.reason,
            "trust_score": result.trust_score,
            "governance_tax": result.governance_tax,
            "escrow_id": result.escrow_id,
            "entitlement_id": result.entitlement_id,
            "evidence_hash": result.evidence_hash,
            "transaction_id": result.transaction_id,
        }
    
    def is_tool_call(self, body: bytes) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Detect if a request body contains an AI tool call.
        Checks for MCP, OpenAI, A2A, LangChain, and generic patterns.
        
        Returns:
            (is_tool_call, tool_name, arguments)
        """
        try:
            data = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return False, None, None
        
        # MCP: JSON-RPC tools/call
        if data.get("jsonrpc") == "2.0" and data.get("method") == "tools/call":
            params = data.get("params", {})
            return True, params.get("name", "unknown"), params.get("arguments", {})
        
        # OpenAI: tool_calls in response
        choices = data.get("choices", [])
        if choices and isinstance(choices, list):
            msg = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                tc = tool_calls[0]
                func = tc.get("function", {})
                args = {}
                try:
                    args = json.loads(func.get("arguments", "{}"))
                except json.JSONDecodeError:
                    pass
                return True, func.get("name", "unknown"), args
        
        # A2A: tasks/send
        if data.get("jsonrpc") == "2.0" and str(data.get("method", "")).startswith("tasks/"):
            return True, "a2a_task", data.get("params", {})
        
        # Generic: look for common AI tool call fields
        for field in ["tool_name", "function_name", "tool", "action"]:
            if field in data:
                return True, data[field], data.get("arguments", data.get("params", {}))
        
        return False, None, None


# =========================================================================
# FastAPI / Starlette (ASGI) Middleware
# =========================================================================

class OCXFastAPIMiddleware:
    """
    FastAPI / Starlette ASGI middleware.
    
    Usage:
        from sdk.middleware import OCXFastAPIMiddleware
        
        app = FastAPI()
        app.add_middleware(OCXFastAPIMiddleware, client=ocx_client)
    """
    
    def __init__(self, app, client=None, fail_open: bool = False, exclude_paths: list = None) -> None:
        self.app = app
        self.bridge = OCXProtocolBridge(client, fail_open=fail_open)
        self.exclude_paths = set(exclude_paths or ["/health", "/docs", "/openapi.json"])
    
    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        path = scope.get("path", "")
        if path in self.exclude_paths:
            await self.app(scope, receive, send)
            return
        
        # Collect request body
        body = b""
        async def receive_wrapper() -> Any:
            nonlocal body
            message = await receive()
            if message.get("type") == "http.request":
                body = message.get("body", b"")
            return message
        
        # Check for AI tool calls
        message = await receive_wrapper()
        is_tool, tool_name, args = self.bridge.is_tool_call(body)
        
        if is_tool and tool_name:
            result = self.bridge.govern(tool_name, args, protocol="fastapi")
            
            if result["verdict"] == "BLOCK":
                response_body = json.dumps({
                    "error": "Blocked by OCX governance",
                    "verdict": "BLOCK",
                    "reason": result["reason"],
                    "transaction_id": result["transaction_id"],
                }).encode()
                
                await send({"type": "http.response.start", "status": 403, "headers": [
                    [b"content-type", b"application/json"],
                    [b"x-ocx-verdict", b"BLOCK"],
                    [b"x-ocx-tx", result["transaction_id"].encode()],
                ]})
                await send({"type": "http.response.body", "body": response_body})
                return
            
            elif result["verdict"] == "ESCROW":
                response_body = json.dumps({
                    "status": "held_for_review",
                    "verdict": "ESCROW",
                    "escrow_id": result["escrow_id"],
                    "transaction_id": result["transaction_id"],
                }).encode()
                
                await send({"type": "http.response.start", "status": 202, "headers": [
                    [b"content-type", b"application/json"],
                    [b"x-ocx-verdict", b"ESCROW"],
                ]})
                await send({"type": "http.response.body", "body": response_body})
                return
        
        # ALLOW — pass through to actual handler
        async def patched_receive() -> dict:
            return {"type": "http.request", "body": body}
        
        await self.app(scope, patched_receive, send)


# =========================================================================
# Flask (WSGI) Middleware
# =========================================================================

class OCXFlaskMiddleware:
    """
    Flask WSGI middleware.
    
    Usage:
        from sdk.middleware import OCXFlaskMiddleware
        
        app = Flask(__name__)
        app.wsgi_app = OCXFlaskMiddleware(app.wsgi_app, client=ocx_client)
    """
    
    def __init__(self, app, client=None, fail_open: bool = False, exclude_paths: list = None) -> None:
        self.app = app
        self.bridge = OCXProtocolBridge(client, fail_open=fail_open)
        self.exclude_paths = set(exclude_paths or ["/health"])
    
    def __call__(self, environ, start_response) -> Any:
        path = environ.get("PATH_INFO", "")
        if path in self.exclude_paths:
            return self.app(environ, start_response)
        
        # Read request body
        try:
            content_length = int(environ.get("CONTENT_LENGTH", 0))
        except (ValueError, TypeError):
            content_length = 0
        
        body = environ["wsgi.input"].read(content_length) if content_length > 0 else b""
        
        is_tool, tool_name, args = self.bridge.is_tool_call(body)
        
        if is_tool and tool_name:
            result = self.bridge.govern(tool_name, args, protocol="flask")
            
            if result["verdict"] == "BLOCK":
                response = json.dumps({
                    "error": "Blocked by OCX governance",
                    "reason": result["reason"],
                    "transaction_id": result["transaction_id"],
                }).encode()
                start_response("403 Forbidden", [
                    ("Content-Type", "application/json"),
                    ("X-OCX-Verdict", "BLOCK"),
                ])
                return [response]
            
            elif result["verdict"] == "ESCROW":
                response = json.dumps({
                    "status": "held_for_review",
                    "escrow_id": result["escrow_id"],
                    "transaction_id": result["transaction_id"],
                }).encode()
                start_response("202 Accepted", [
                    ("Content-Type", "application/json"),
                    ("X-OCX-Verdict", "ESCROW"),
                ])
                return [response]
        
        # Rewind body for downstream handler
        from io import BytesIO
        environ["wsgi.input"] = BytesIO(body)
        environ["CONTENT_LENGTH"] = str(len(body))
        
        return self.app(environ, start_response)


# =========================================================================
# Django Middleware
# =========================================================================

class OCXDjangoMiddleware:
    """
    Django middleware.
    
    Usage (settings.py):
        from sdk import OCXClient
        OCX_CLIENT = OCXClient(gateway_url="...", tenant_id="...")
        
        MIDDLEWARE = [
            "sdk.middleware.OCXDjangoMiddleware",
            ...
        ]
    """
    
    def __init__(self, get_response) -> None:
        self.get_response = get_response
        self._bridge = None
    
    @property
    def bridge(self) -> Any:
        if self._bridge is None:
            from django.conf import settings
            client = getattr(settings, "OCX_CLIENT", None)
            if client is None:
                from .client import OCXClient
                client = OCXClient()
            self._bridge = OCXProtocolBridge(client)
        return self._bridge
    
    def __call__(self, request) -> Any:
        body = request.body
        is_tool, tool_name, args = self.bridge.is_tool_call(body)
        
        if is_tool and tool_name:
            result = self.bridge.govern(tool_name, args, protocol="django")
            
            if result["verdict"] == "BLOCK":
                from django.http import JsonResponse
                return JsonResponse({
                    "error": "Blocked by OCX governance",
                    "reason": result["reason"],
                    "transaction_id": result["transaction_id"],
                }, status=403)
            
            elif result["verdict"] == "ESCROW":
                from django.http import JsonResponse
                return JsonResponse({
                    "status": "held_for_review",
                    "escrow_id": result["escrow_id"],
                    "transaction_id": result["transaction_id"],
                }, status=202)
        
        return self.get_response(request)


# =========================================================================
# AIOHTTP Middleware
# =========================================================================

def ocx_aiohttp_middleware(client, fail_open: bool = False) -> None:
    """
    AIOHTTP middleware factory.
    
    Usage:
        from sdk.middleware import ocx_aiohttp_middleware
        
        app = web.Application(middlewares=[
            ocx_aiohttp_middleware(ocx_client),
        ])
    """
    bridge = OCXProtocolBridge(client, fail_open=fail_open)
    
    async def middleware(app, handler) -> None:
        async def ocx_handler(request) -> Any:
            body = await request.read()
            is_tool, tool_name, args = bridge.is_tool_call(body)
            
            if is_tool and tool_name:
                result = bridge.govern(tool_name, args, protocol="aiohttp")
                
                if result["verdict"] == "BLOCK":
                    from aiohttp import web
                    return web.json_response({
                        "error": "Blocked by OCX governance",
                        "reason": result["reason"],
                    }, status=403)
                
                elif result["verdict"] == "ESCROW":
                    from aiohttp import web
                    return web.json_response({
                        "status": "held_for_review",
                        "escrow_id": result["escrow_id"],
                    }, status=202)
            
            return await handler(request)
        return ocx_handler
    return middleware


# =========================================================================
# MCP Server Middleware (wraps any MCP server)
# =========================================================================

class OCXMCPServerMiddleware:
    """
    Middleware for MCP (Model Context Protocol) tool servers.
    
    Wraps an MCP server's tool handler so all tool calls go through
    OCX governance before execution.
    
    Usage:
        from mcp.server import Server
        from sdk.middleware import OCXMCPServerMiddleware
        
        server = Server("my-server")
        ocx_mcp = OCXMCPServerMiddleware(ocx_client)
        
        @server.call_tool()
        @ocx_mcp.govern_tool
        async def handle_tool(name, arguments) -> None:
            ...
    """
    
    def __init__(self, client) -> None:
        self.bridge = OCXProtocolBridge(client)
    
    def govern_tool(self, func) -> None:
        """Decorator for MCP server tool handlers."""
        import functools
        
        @functools.wraps(func)
        async def wrapper(name, arguments=None, **kwargs) -> list:
            result = self.bridge.govern(
                name, arguments or {},
                protocol="mcp-server",
            )
            
            if result["verdict"] == "BLOCK":
                return [{
                    "type": "text",
                    "text": f"⛔ Blocked by OCX governance: {result['reason']}",
                }]
            
            elif result["verdict"] == "ESCROW":
                return [{
                    "type": "text",
                    "text": f"⏳ Held for review (escrow_id={result['escrow_id']})",
                }]
            
            return await func(name, arguments, **kwargs)
        
        return wrapper


# =========================================================================
# A2A Agent Middleware (wraps any A2A agent)
# =========================================================================

class OCXA2AMiddleware:
    """
    Middleware for A2A (Agent-to-Agent) protocol agents.
    
    Usage:
        from sdk.middleware import OCXA2AMiddleware
        
        a2a_mw = OCXA2AMiddleware(ocx_client)
        
        # Wrap your task handler
        @a2a_mw.govern_task
        async def handle_task(task) -> None:
            ...
    """
    
    def __init__(self, client) -> None:
        self.bridge = OCXProtocolBridge(client)
    
    def govern_task(self, func) -> None:
        """Decorator for A2A task handlers."""
        import functools
        
        @functools.wraps(func)
        async def wrapper(task, **kwargs) -> dict:
            # Extract skill/action from task
            skill_id = getattr(task, "skill_id", "a2a_task")
            message_text = ""
            if hasattr(task, "message") and hasattr(task.message, "parts"):
                for part in task.message.parts:
                    if hasattr(part, "text"):
                        message_text = part.text
                        break
            
            result = self.bridge.govern(
                skill_id,
                {"message": message_text},
                protocol="a2a-agent",
            )
            
            if result["verdict"] == "BLOCK":
                return {"status": "blocked", "reason": result["reason"]}
            elif result["verdict"] == "ESCROW":
                return {"status": "pending_review", "escrow_id": result["escrow_id"]}
            
            return await func(task, **kwargs)
        
        return wrapper
