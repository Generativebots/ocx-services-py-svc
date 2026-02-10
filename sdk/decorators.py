"""
OCX Governance Decorators and Framework Wrappers.

Usage:

1. Decorator (any Python function):
    @ocx.governed(client)
    def execute_payment(amount, currency="USD") -> None:
        stripe.charge(amount, currency)

2. LangChain Tool:
    from ocx_sdk.decorators import govern_langchain_tool
    governed_tool = govern_langchain_tool(client, my_langchain_tool)

3. OpenAI function calling:
    from ocx_sdk.decorators import govern_openai_call
    response = govern_openai_call(client, openai_client, messages, tools)

4. CrewAI:
    from ocx_sdk.decorators import govern_crewai_tool
    governed = govern_crewai_tool(client, my_tool)
"""

import functools
import inspect
from typing import Any, Callable, Dict, List
import logging
logger = logging.getLogger(__name__)


def governed(client, tool_name: str = None) -> None:
    """
    Decorator that wraps any function through OCX governance.
    
    The function will only execute if the governance verdict is ALLOW.
    
    Usage:
        @governed(ocx_client)
        def send_email(to, subject, body) -> None:
            smtp.send(to, subject, body)
        
        # Or with explicit tool name:
        @governed(ocx_client, tool_name="send_external_email")
        def send(to, subject, body) -> None:
            smtp.send(to, subject, body)
    """
    def decorator(func) -> None:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Derive tool name from function name if not provided
            name = tool_name or func.__name__
            
            # Build arguments dict from function signature
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            arguments = dict(bound.arguments)
            
            # Send through OCX governance
            result = client.execute_tool(name, arguments, protocol="python-decorator")
            
            if result.verdict == "ALLOW":
                return func(*args, **kwargs)
            elif result.verdict == "BLOCK":
                raise ToolBlockedError(name, result.reason, result.transaction_id)
            elif result.verdict == "ESCROW":
                raise ToolEscrowedError(name, result.escrow_id, result.transaction_id)
            else:
                raise ToolEscalatedError(name, result.reason, result.transaction_id)
        
        wrapper._ocx_governed = True
        wrapper._ocx_tool_name = tool_name or func.__name__
        return wrapper
    return decorator


class ToolBlockedError(Exception):
    """Raised when OCX governance blocks a tool call."""
    def __init__(self, tool_name: str, reason: str, transaction_id: str) -> None:
        self.tool_name = tool_name
        self.reason = reason
        self.transaction_id = transaction_id
        super().__init__(f"OCX blocked '{tool_name}': {reason} (tx={transaction_id})")


class ToolEscrowedError(Exception):
    """Raised when OCX governance holds a tool call in escrow."""
    def __init__(self, tool_name: str, escrow_id: str, transaction_id: str) -> None:
        self.tool_name = tool_name
        self.escrow_id = escrow_id
        self.transaction_id = transaction_id
        super().__init__(f"OCX escrowed '{tool_name}': escrow_id={escrow_id} (tx={transaction_id})")


class ToolEscalatedError(Exception):
    """Raised when OCX governance escalates a tool call."""
    def __init__(self, tool_name: str, reason: str, transaction_id: str) -> None:
        self.tool_name = tool_name
        self.reason = reason
        self.transaction_id = transaction_id
        super().__init__(f"OCX escalated '{tool_name}': {reason} (tx={transaction_id})")


# =========================================================================
# Framework-Specific Wrappers
# =========================================================================

def govern_langchain_tool(client, tool) -> None:
    """
    Wrap a LangChain Tool through OCX governance.
    
    Usage:
        from langchain.tools import Tool
        my_tool = Tool(name="search", func=search_fn, description="Search")
        governed_tool = govern_langchain_tool(ocx_client, my_tool)
    """
    original_run = tool._run
    
    @functools.wraps(original_run)
    def governed_run(*args, **kwargs) -> Any:
        arguments = {"args": args, "kwargs": kwargs}
        result = client.execute_tool(tool.name, arguments, protocol="langchain")
        
        if result.verdict == "ALLOW":
            return original_run(*args, **kwargs)
        elif result.verdict == "BLOCK":
            return f"[OCX BLOCKED] {result.reason}"
        else:
            return f"[OCX ESCROWED] Held for review: {result.escrow_id}"
    
    tool._run = governed_run
    return tool


def govern_openai_call(
    client,
    openai_client,
    messages: List[Dict],
    tools: List[Dict] = None,
    model: str = "gpt-4",
    **kwargs,
) -> Any:
    """
    Govern OpenAI function calling / tool use.
    
    Intercepts the response and checks tool_calls through OCX before
    allowing execution.
    
    Usage:
        response = govern_openai_call(
            ocx_client, openai_client,
            messages=[{"role": "user", "content": "Pay $100"}],
            tools=[...],
            model="gpt-4",
        )
    """
    # Make the OpenAI call
    response = openai_client.chat.completions.create(
        model=model, messages=messages, tools=tools, **kwargs
    )
    
    # Check if the model wants to call tools
    if response.choices[0].message.tool_calls:
        governed_tool_calls = []
        for tc in response.choices[0].message.tool_calls:
            import json

            args = json.loads(tc.function.arguments)
            
            # Route through OCX governance
            result = client.execute_tool(
                tc.function.name, args,
                model=model, protocol="openai",
            )
            
            if result.verdict == "ALLOW":
                governed_tool_calls.append(tc)
            elif result.verdict == "BLOCK":
                print(f"⛔ OCX blocked tool call: {tc.function.name} — {result.reason}")
            elif result.verdict == "ESCROW":
                print(f"⏳ OCX escrowed tool call: {tc.function.name} — {result.escrow_id}")
        
        # Replace tool_calls with only the allowed ones
        response.choices[0].message.tool_calls = governed_tool_calls
    
    return response


def govern_crewai_tool(client, tool) -> None:
    """
    Wrap a CrewAI Tool through OCX governance.
    
    Usage:
        from crewai_tools import tool as crewai_tool
        
        @crewai_tool("Search")
        def search(query: str) -> str:
            return google.search(query)
        
        governed_search = govern_crewai_tool(ocx_client, search)
    """
    original_func = tool.func if hasattr(tool, 'func') else tool._run
    
    @functools.wraps(original_func)
    def governed_func(*args, **kwargs) -> Any:
        tool_name = getattr(tool, 'name', original_func.__name__)
        arguments = {"args": args, "kwargs": kwargs}
        
        result = client.execute_tool(tool_name, arguments, protocol="crewai")
        
        if result.verdict == "ALLOW":
            return original_func(*args, **kwargs)
        elif result.verdict == "BLOCK":
            return f"[OCX BLOCKED] {result.reason}"
        else:
            return f"[OCX ESCROWED] Held for review: {result.escrow_id}"
    
    if hasattr(tool, 'func'):
        tool.func = governed_func
    else:
        tool._run = governed_func
    return tool
