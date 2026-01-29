from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
import json
import httpx
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

# --- vLLM Client (Real) ---
class VLLMClient:
    def __init__(self, base_url="http://localhost:8000/v1"):
        self.base_url = base_url
        self.api_key = os.getenv("VLLM_API_KEY", "EMPTY")

    async def generate_json(self, prompt: str, schema: dict) -> list:
        """
        Calls vLLM (OpenAI-compatible) to extract structured JSON.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                payload = {
                    "model": "mistralai/Mistral-7B-Instruct-v0.2",
                    "messages": [
                        {"role": "system", "content": "You are the APE (Agentic Policy Extractor). Extract logic gates from the SOP. Return ONLY a JSON array."},
                        {"role": "user", "content": f"{prompt}\n\nSchema: {json.dumps(schema)}"}
                    ],
                    "temperature": 0.1,  # Deterministic
                    "max_tokens": 1024
                }
                
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload
                )
                resp.raise_for_status()
                
                content = resp.json()["choices"][0]["message"]["content"]
                # Attempt to parse JSON from the response
                start = content.find('[')
                end = content.rfind(']') + 1
                if start == -1 or end == 0:
                    logger.warning("No JSON array found in LLM response")
                    return []
                    
                return json.loads(content[start:end])
                
            except Exception as e:
                logger.error(f"vLLM Inference Error: {e}")
                return []

llm = VLLMClient()

# --- Recursive Semantic Parser ---
class RecursiveParser:
    def parse(self, text: str) -> List[str]:
        """
        Recursively splits text into semantic chunks (Header -> Section -> Paragraph).
        Simple implementation: Splits by double newline blocks.
        """
        # Level 1: Split by Headers (Mocked by double newlines for now)
        chunks = [c.strip() for c in text.split('\n\n') if c.strip()]
        return chunks

parser = RecursiveParser()

# --- Models ---
class ExtractRequest(BaseModel):
    document_text: str
    source_name: str
    tenant_id: str # Multi-tenancy

class LogicGate(BaseModel):
    field: str
    operator: str
    value: float | str | int | bool

class PolicyObject(BaseModel):
    rule_id: str
    tenant_id: str
    source_reference: str
    logic_type: str = "DETERMINISTIC"
    condition: str
    suggested_action: str
    confidence_score: float
    logic_gate: Optional[LogicGate] = None

@router.post("/extract", response_model=List[PolicyObject])
async def extract_rules(req: ExtractRequest):
    """
    APE Engine V2: Recursive Semantic Parsing + Real vLLM Inference.
    """
    logger.info(f"Extracting rules for Tenant: {req.tenant_id} from Source: {req.source_name}")
    
    # 1. Recursive Decomposition
    chunks = parser.parse(req.document_text)
    all_rules = []
    
    # 2. Parallel/Batch Inference (Sequential for now)
    for i, chunk in enumerate(chunks):
        prompt = f"""
        Extract business rules from this section of the SOP.
        Source: {req.source_name} (Section {i+1})
        Text: "{chunk}"
        
        Output JSON Array of objects with keys: rule_id (generate unique), condition, suggested_action, confidence_score, logic_gate.
        For logic_gate, extract field, operator, value.
        """
        
        schema = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "condition": {"type": "string"},
                    "suggested_action": {"type": "string"},
                    "confidence_score": {"type": "number"},
                    "logic_gate": {
                        "type": "object",
                        "properties": {
                            "field": {"type": "string"},
                            "operator": {"type": "string"},
                            "value": {"type": "string"} # Simplify to string for robustness
                        }
                    }
                }
            }
        }
        
        extracted_data = await llm.generate_json(prompt, schema)
        
        for rule in extracted_data:
            # Enrich with system metadata
            rule["rule_id"] = str(uuid.uuid4())
            rule["tenant_id"] = req.tenant_id
            rule["source_reference"] = f"{req.source_name}#chunk-{i}"
            rule["logic_type"] = "DETERMINISTIC"
            all_rules.append(rule)
            
    # 3. Return (Later: Persist to Supabase)
    # Using pydantic validation
    validated_rules = []
    for r in all_rules:
        try:
            validated_rules.append(PolicyObject(**r))
        except Exception as e:
            logger.warning(f"Skipping invalid rule: {e}")
            
    return validated_rules
