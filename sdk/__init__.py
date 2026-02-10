"""
OCX Governance SDK for Python

This is the 'code drop' for Python AI agents. Install it with:
    pip install ocx-sdk  (or copy this module into your project)

Three integration patterns:

1. Direct:
    client = OCXClient(gateway_url="https://ocx.example.com", tenant_id="acme")
    result = client.execute_tool("execute_payment", {"amount": 100})

2. Decorator:
    @ocx.governed(client)
    def execute_payment(amount, currency):
        ...

3. Framework wrappers:
    from ocx_sdk.langchain import OCXToolWrapper
    from ocx_sdk.openai_wrapper import governed_chat_completion
    from ocx_sdk.crewai import OCXCrewAITool
"""

from .client import OCXClient
from .decorators import governed

__all__ = ["OCXClient", "governed"]
__version__ = "0.1.0"
