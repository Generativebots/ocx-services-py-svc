"""
Multi-Model Support for APE Engine
Supports GPT-5, Gemini 2.0, Claude 4, and vLLM with automatic fallback
"""

import os
from typing import Dict, List, Any, Optional
from enum import Enum
from dataclasses import dataclass
import requests
import json


class ModelProvider(str, Enum):
    """Supported model providers"""
    VLLM = "vllm"
    OPENAI = "openai"  # GPT-5
    GOOGLE = "google"  # Gemini 2.0
    ANTHROPIC = "anthropic"  # Claude 4


@dataclass
class ModelConfig:
    """Configuration for a model"""
    provider: ModelProvider
    model_name: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.1
    max_tokens: int = 2048
    priority: int = 1  # Lower = higher priority for fallback


class MultiModelClient:
    """
    Multi-model client with automatic fallback
    
    Priority order (configurable):
    1. vLLM (local, fastest, cheapest)
    2. GPT-5 (OpenAI)
    3. Gemini 2.0 (Google)
    4. Claude 4 (Anthropic)
    """
    
    def __init__(self, models: List[ModelConfig]):
        self.models = sorted(models, key=lambda m: m.priority)
        self.current_model_index = 0
    
    def extract_policies(
        self,
        document_text: str,
        source_name: str
    ) -> List[Dict[str, Any]]:
        """
        Extract policies using available models with fallback
        
        Returns:
            List of extracted policies
        """
        last_error = None
        
        for i, model_config in enumerate(self.models):
            try:
                print(f"🔄 Attempting extraction with {model_config.provider.value}/{model_config.model_name}")
                
                if model_config.provider == ModelProvider.VLLM:
                    return self._extract_vllm(document_text, source_name, model_config)
                elif model_config.provider == ModelProvider.OPENAI:
                    return self._extract_openai(document_text, source_name, model_config)
                elif model_config.provider == ModelProvider.GOOGLE:
                    return self._extract_google(document_text, source_name, model_config)
                elif model_config.provider == ModelProvider.ANTHROPIC:
                    return self._extract_anthropic(document_text, source_name, model_config)
                
            except Exception as e:
                print(f"⚠️  {model_config.provider.value} failed: {e}")
                last_error = e
                continue
        
        # All models failed
        raise Exception(f"All models failed. Last error: {last_error}")
    
    def _extract_vllm(
        self,
        document_text: str,
        source_name: str,
        config: ModelConfig
    ) -> List[Dict[str, Any]]:
        """Extract using vLLM"""
        from vllm_client import VLLMClient, VLLMConfig
        
        vllm_config = VLLMConfig(
            base_url=config.base_url or "http://localhost:8000",
            model_name=config.model_name,
            temperature=config.temperature,
            max_tokens=config.max_tokens
        )
        
        client = VLLMClient(vllm_config)
        return client.extract_policies(document_text, source_name)
    
    def _extract_openai(
        self,
        document_text: str,
        source_name: str,
        config: ModelConfig
    ) -> List[Dict[str, Any]]:
        """Extract using OpenAI GPT-5"""
        import openai
        
        openai.api_key = config.api_key or os.getenv("OPENAI_API_KEY")
        
        system_prompt = """You are the Agentic Policy Extractor (APE).
Convert SOPs into machine-executable JSON-Logic.
Output format: JSON array of policy objects."""
        
        response = openai.ChatCompletion.create(
            model=config.model_name,  # e.g., "gpt-5-turbo"
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Extract policies from:\n\n{document_text}"}
            ],
            temperature=config.temperature,
            max_tokens=config.max_tokens
        )
        
        content = response.choices[0].message.content
        return json.loads(content)
    
    def _extract_google(
        self,
        document_text: str,
        source_name: str,
        config: ModelConfig
    ) -> List[Dict[str, Any]]:
        """Extract using Google Gemini 2.0"""
        import google.generativeai as genai
        
        genai.configure(api_key=config.api_key or os.getenv("GOOGLE_API_KEY"))
        
        model = genai.GenerativeModel(config.model_name)  # e.g., "gemini-2.0-pro"
        
        prompt = f"""Extract machine-executable policies from this SOP.
Output as JSON array.

SOP:
{document_text}"""
        
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=config.temperature,
                max_output_tokens=config.max_tokens
            )
        )
        
        return json.loads(response.text)
    
    def _extract_anthropic(
        self,
        document_text: str,
        source_name: str,
        config: ModelConfig
    ) -> List[Dict[str, Any]]:
        """Extract using Anthropic Claude 4"""
        import anthropic
        
        client = anthropic.Anthropic(
            api_key=config.api_key or os.getenv("ANTHROPIC_API_KEY")
        )
        
        message = client.messages.create(
            model=config.model_name,  # e.g., "claude-4-opus"
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            messages=[{
                "role": "user",
                "content": f"Extract policies as JSON from:\n\n{document_text}"
            }]
        )
        
        return json.loads(message.content[0].text)


# Factory function
def create_multi_model_client() -> MultiModelClient:
    """Create multi-model client from environment variables"""
    models = []
    
    # vLLM (priority 1)
    if os.getenv("VLLM_ENABLED", "true") == "true":
        models.append(ModelConfig(
            provider=ModelProvider.VLLM,
            model_name=os.getenv("VLLM_MODEL", "mistralai/Mistral-7B-Instruct-v0.2"),
            base_url=os.getenv("VLLM_BASE_URL", "http://localhost:8000"),
            priority=1
        ))
    
    # OpenAI GPT-5 (priority 2)
    if os.getenv("OPENAI_API_KEY"):
        models.append(ModelConfig(
            provider=ModelProvider.OPENAI,
            model_name=os.getenv("OPENAI_MODEL", "gpt-5-turbo"),
            api_key=os.getenv("OPENAI_API_KEY"),
            priority=2
        ))
    
    # Google Gemini 2.0 (priority 3)
    if os.getenv("GOOGLE_API_KEY"):
        models.append(ModelConfig(
            provider=ModelProvider.GOOGLE,
            model_name=os.getenv("GOOGLE_MODEL", "gemini-2.0-pro"),
            api_key=os.getenv("GOOGLE_API_KEY"),
            priority=3
        ))
    
    # Anthropic Claude 4 (priority 4)
    if os.getenv("ANTHROPIC_API_KEY"):
        models.append(ModelConfig(
            provider=ModelProvider.ANTHROPIC,
            model_name=os.getenv("ANTHROPIC_MODEL", "claude-4-opus"),
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            priority=4
        ))
    
    if not models:
        raise ValueError("No models configured. Set at least one API key or enable vLLM.")
    
    return MultiModelClient(models)


# Example usage
if __name__ == "__main__":
    # Configure models
    models = [
        ModelConfig(
            provider=ModelProvider.VLLM,
            model_name="mistralai/Mistral-7B-Instruct-v0.2",
            base_url="http://localhost:8000",
            priority=1
        ),
        # Add more models as fallback
    ]
    
    client = MultiModelClient(models)
    
    # Test extraction
    sop = "All purchases over $500 require CTO approval."
    policies = client.extract_policies(sop, "Test SOP")
    
    print(f"Extracted {len(policies)} policies")
