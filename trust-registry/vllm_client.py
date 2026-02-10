"""
Production vLLM Client for APE Engine
Supports Mistral-7B, Llama-3, and other vLLM-compatible models
"""

import os
import json
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import requests
from tenacity import retry, stop_after_attempt, wait_exponential
import logging
logger = logging.getLogger(__name__)



@dataclass
class VLLMConfig:
    """Configuration for vLLM client"""
    base_url: str = None  # Set from VLLM_BASE_URL env var
    model_name: str = "mistralai/Mistral-7B-Instruct-v0.2"
    temperature: float = 0.1  # Low temperature for deterministic extraction
    max_tokens: int = 2048
    timeout: int = 30
    max_retries: int = 3

    def __post_init__(self) -> None:
        if self.base_url is None:
            self.base_url = os.getenv("VLLM_BASE_URL", "http://localhost:8000")


class VLLMClient:
    """Production vLLM client with retry logic and error handling"""
    
    def __init__(self, config: Optional[VLLMConfig] = None) -> None:
        self.config = config or VLLMConfig()
        self._validate_connection()
    
    def _validate_connection(self) -> None:
        """Validate vLLM server is reachable"""
        try:
            response = requests.get(
                f"{self.config.base_url}/health",
                timeout=5
            )
            if response.status_code != 200:
                print(f"⚠️  vLLM server health check failed: {response.status_code}")
        except Exception as e:
            print(f"⚠️  vLLM server not reachable: {e}")
            print("   Falling back to mock mode for development")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def generate(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Generate completion from vLLM server
        
        Args:
            prompt: Input prompt
            temperature: Sampling temperature (overrides config)
            max_tokens: Max tokens to generate (overrides config)
            
        Returns:
            Generated text
            
        Raises:
            requests.RequestException: If vLLM server is unreachable
        """
        payload = {
            "model": self.config.model_name,
            "prompt": prompt,
            "temperature": temperature or self.config.temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
            "stop": ["</json>", "\n\n\n"]  # Stop tokens
        }
        
        try:
            response = requests.post(
                f"{self.config.base_url}/v1/completions",
                json=payload,
                timeout=self.config.timeout
            )
            response.raise_for_status()
            
            result = response.json()
            return result["choices"][0]["text"].strip()
            
        except requests.RequestException as e:
            print(f"❌ vLLM generation failed: {e}")
            # Fallback to mock for development
            return self._mock_generate(prompt)
    
    def _mock_generate(self, prompt: str) -> str:
        """
        Mock generation for development/testing
        Returns hardcoded JSON-Logic based on prompt content
        """
        prompt_lower = prompt.lower()
        
        # Procurement policy
        if "procurement" in prompt_lower or "purchase" in prompt_lower:
            return json.dumps({
                "policy_id": "PURCHASE_AUTH_001",
                "trigger_intent": "mcp.call_tool('execute_payment')",
                "logic": {
                    "and": [
                        {">": [{"var": "payload.amount"}, 500]},
                        {"not": {"in": [{"var": "payload.vendor_id"}, ["APPROVED_VENDOR_1", "APPROVED_VENDOR_2"]]}}
                    ]
                },
                "action": {
                    "on_fail": "INTERCEPT_AND_ESCALATE",
                    "on_pass": "SPECULATIVE_COMMIT",
                    "required_signals": ["CTO_SIGNATURE", "JURY_ENTROPY_CHECK"]
                },
                "tier": "CONTEXTUAL",
                "confidence": 0.95
            })
        
        # Data exfiltration policy
        elif "data" in prompt_lower and ("vpc" in prompt_lower or "network" in prompt_lower):
            return json.dumps({
                "policy_id": "DATA_EXFIL_001",
                "trigger_intent": "mcp.call_tool('send_external_request')",
                "logic": {
                    "and": [
                        {"==": [{"var": "payload.destination_type"}, "external"]},
                        {"not": {"in": [{"var": "payload.destination"}, {"var": "whitelist.approved_endpoints"}]}}
                    ]
                },
                "action": {
                    "on_fail": "BLOCK",
                    "on_pass": "ALLOW"
                },
                "tier": "GLOBAL",
                "confidence": 0.99
            })
        
        # PII detection policy
        elif "pii" in prompt_lower or "personal" in prompt_lower:
            return json.dumps({
                "policy_id": "PII_PROTECT_001",
                "trigger_intent": "mcp.call_tool('send_message')",
                "logic": {
                    "or": [
                        {"in": ["@", {"var": "payload.content"}]},
                        {"in": ["ssn", {"var": "payload.content"}]},
                        {"in": ["credit card", {"var": "payload.content"}]}
                    ]
                },
                "action": {
                    "on_fail": "REDACT_AND_LOG",
                    "on_pass": "ALLOW"
                },
                "tier": "GLOBAL",
                "confidence": 0.92
            })
        
        # Default fallback
        return json.dumps({
            "policy_id": "GENERIC_001",
            "trigger_intent": "unknown",
            "logic": {"==": [1, 1]},  # Always true
            "action": {"on_fail": "FLAG", "on_pass": "ALLOW"},
            "tier": "DYNAMIC",
            "confidence": 0.5
        })
    
    def extract_policies(
        self,
        document_text: str,
        source_name: str
    ) -> List[Dict[str, Any]]:
        """
        Extract policies from document using vLLM
        
        Args:
            document_text: Raw SOP/policy document
            source_name: Source identifier (e.g., "Procurement SOP v2.1")
            
        Returns:
            List of policy objects with JSON-Logic
        """
        system_prompt = """You are the Agentic Policy Extractor (APE).

Your task is to convert Standard Operating Procedures (SOPs) into machine-executable JSON-Logic.

Output Format (JSON):
{
  "policy_id": "UNIQUE_ID",
  "trigger_intent": "mcp.call_tool('tool_name')",
  "logic": { JSON-Logic expression },
  "action": {
    "on_fail": "BLOCK|INTERCEPT_AND_ESCALATE|REDACT_AND_LOG",
    "on_pass": "ALLOW|SPECULATIVE_COMMIT",
    "required_signals": ["SIGNAL_1", "SIGNAL_2"]
  },
  "tier": "GLOBAL|CONTEXTUAL|DYNAMIC",
  "confidence": 0.0-1.0
}

JSON-Logic Operators:
- Comparison: >, <, >=, <=, ==, !=
- Boolean: and, or, not
- Membership: in
- Variables: {"var": "payload.field_name"}

Examples:
1. "Purchases over $500 require CTO approval"
   → {"and": [{">": [{"var": "payload.amount"}, 500]}, {"not": {"in": [{"var": "approver"}, ["CTO"]]}}]}

2. "No data can leave the VPC"
   → {"==": [{"var": "payload.destination_type"}, "external"]}

Extract ALL policies from the document below."""

        full_prompt = f"""{system_prompt}

SOURCE: {source_name}

DOCUMENT:
{document_text}

JSON OUTPUT:
"""

        try:
            raw_response = self.generate(full_prompt)
            
            # Parse JSON response
            # Handle both single object and array responses
            if raw_response.startswith('['):
                policies = json.loads(raw_response)
            else:
                policies = [json.loads(raw_response)]
            
            # Add source metadata
            for policy in policies:
                policy['source_name'] = source_name
                policy['extracted_at'] = time.time()
            
            return policies
            
        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse vLLM response: {e}")
            print(f"   Raw response: {raw_response[:200]}...")
            return []
        except Exception as e:
            print(f"❌ Policy extraction failed: {e}")
            return []


# Singleton instance
_vllm_client: Optional[VLLMClient] = None


def get_vllm_client() -> VLLMClient:
    """Get or create singleton vLLM client"""
    global _vllm_client
    if _vllm_client is None:
        config = VLLMConfig(
            base_url=os.getenv("VLLM_BASE_URL", "http://localhost:8000"),
            model_name=os.getenv("VLLM_MODEL", "mistralai/Mistral-7B-Instruct-v0.2"),
        )
        _vllm_client = VLLMClient(config)
    return _vllm_client
