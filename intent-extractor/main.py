"""
JARVIS Intent Extractor — Gemini AI Pipeline

Extracts business intents from tenant documents using Google Gemini
with LangChain structured output. Writes results to intent_mappings
and resource_relationships tables.

Architecture:
  - LLM API key: tenant-provided (tenants.settings.llm_api_key),
    falls back to system-level GOOGLE_API_KEY env var.
  - All data is tenant-isolated via tenant_id.
  - Pipeline: Document → Gemini Extraction → intent_mappings + resource_relationships
"""

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

logger = logging.getLogger("jarvis.intent_extractor")

# ─── Config ───────────────────────────────────────────────────────────────────

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
SYSTEM_GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

app = FastAPI(title="JARVIS Intent Extractor", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Supabase Helpers ─────────────────────────────────────────────────────────


def _headers() -> Dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _supa_get(table: str, params: Optional[Dict[str, str]] = None) -> List[Dict]:
    if not SUPABASE_URL:
        return []
    try:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=_headers(),
            params=params or {},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Supabase GET {table} failed: {e}")
        return []


def _supa_insert(table: str, row: Dict) -> Optional[Dict]:
    if not SUPABASE_URL:
        return None
    try:
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=_headers(),
            json=row,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return data[0] if isinstance(data, list) and data else data
    except Exception as e:
        logger.error(f"Supabase INSERT {table} failed: {e}")
        return None


def _supa_patch(table: str, match_params: Dict[str, str], updates: Dict) -> bool:
    if not SUPABASE_URL:
        return False
    try:
        resp = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=_headers(),
            params=match_params,
            json=updates,
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Supabase PATCH {table} failed: {e}")
        return False


# ─── Tenant LLM Key Resolution ───────────────────────────────────────────────


def _resolve_llm_key(tenant_id: str) -> str:
    """
    Resolve the LLM API key for a tenant.
    Priority: tenant settings → system env var.
    """
    rows = _supa_get("tenants", {"tenant_id": f"eq.{tenant_id}", "select": "settings"})
    if rows:
        settings = rows[0].get("settings", {}) or {}
        tenant_key = settings.get("llm_api_key", "")
        if tenant_key:
            logger.info(f"Using tenant-provided LLM key for {tenant_id}")
            return tenant_key

    if SYSTEM_GOOGLE_API_KEY:
        logger.info(f"Using system-level LLM key for {tenant_id}")
        return SYSTEM_GOOGLE_API_KEY

    raise ValueError("No LLM API key available (tenant or system)")


def _resolve_model(tenant_id: str) -> str:
    """Resolve which Gemini model to use. Tenant can override."""
    rows = _supa_get("tenants", {"tenant_id": f"eq.{tenant_id}", "select": "settings"})
    if rows:
        settings = rows[0].get("settings", {}) or {}
        model = settings.get("llm_model", "")
        if model:
            return model
    return DEFAULT_MODEL


# ─── Pydantic Schemas (Gemini Structured Output) ─────────────────────────────


class BusinessIntent(BaseModel):
    """A single business intent extracted by Gemini."""
    intent_name: str = Field(description="Unique intent key (e.g., 'verify_sop_compliance')")
    source_resource: str = Field(description="Source document or section name")
    trigger_condition: str = Field(description="What triggers this intent")
    action_steps: List[str] = Field(description="Sequential steps the agent must take")
    risk_level: str = Field(
        default="AMBER",
        description="Risk classification: GREEN (low), AMBER (medium), RED (high)",
    )
    compliance_frameworks: List[str] = Field(
        default_factory=list,
        description="Applicable frameworks (e.g., HIPAA, SOC2, PCI-DSS)",
    )
    hitl_checkpoint: Optional[str] = Field(
        default=None,
        description="Human approval step description, if required",
    )


class IntentMap(BaseModel):
    """Collection of intents extracted from a document."""
    intents: List[BusinessIntent]


# ─── Gemini Extraction Engine ─────────────────────────────────────────────────


def _extract_intents_with_gemini(
    text: str, api_key: str, model_name: str
) -> IntentMap:
    """
    Call Gemini via LangChain with structured output to extract intents.
    Uses the massive context window for feeding in full documents.
    """
    from langchain_google_genai import ChatGoogleGenerativeAI

    llm = ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=api_key,
        temperature=0,
        max_retries=2,
    )

    structured_llm = llm.with_structured_output(IntentMap)

    prompt = (
        "You are an AI agent intent extractor for a governance platform. "
        "Analyze the following document and extract ALL agentic business intents. "
        "For each intent, identify:\n"
        "- A clear intent_name (snake_case, unique)\n"
        "- The source_resource (section or document name)\n"
        "- The trigger_condition (what event starts this intent)\n"
        "- Ordered action_steps the AI agent must execute\n"
        "- risk_level: GREEN (routine), AMBER (needs monitoring), RED (critical/requires approval)\n"
        "- compliance_frameworks that apply (e.g., HIPAA, SOC2, PCI-DSS, AML, GDPR)\n"
        "- hitl_checkpoint: describe any human approval step, or null if fully automated\n\n"
        f"DOCUMENT:\n{text}"
    )

    result = structured_llm.invoke(prompt)
    return result


# ─── Request / Response Models ────────────────────────────────────────────────


class ExtractRequest(BaseModel):
    document_id: str
    tenant_id: str


class ExtractTextRequest(BaseModel):
    text: str
    tenant_id: str


class ExtractResponse(BaseModel):
    document_id: Optional[str] = None
    intents_extracted: int
    intents: List[BusinessIntent]
    relationships_created: int


# ─── Endpoints ────────────────────────────────────────────────────────────────


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "JARVIS Intent Extractor"}


@app.post("/extract/text", response_model=ExtractResponse)
async def extract_from_text(req: ExtractTextRequest) -> ExtractResponse:
    """
    Stateless extraction: accept raw text, return structured intents.
    No DB writes — useful for previewing before committing.
    """
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text is empty")

    try:
        api_key = _resolve_llm_key(req.tenant_id)
        model = _resolve_model(req.tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        result = _extract_intents_with_gemini(req.text, api_key, model)
    except Exception as e:
        logger.error(f"Gemini extraction failed: {e}")
        raise HTTPException(status_code=502, detail=f"LLM extraction failed: {e}")

    return ExtractResponse(
        intents_extracted=len(result.intents),
        intents=result.intents,
        relationships_created=0,
    )


@app.post("/extract", response_model=ExtractResponse)
async def extract_from_document(req: ExtractRequest) -> ExtractResponse:
    """
    Full pipeline: fetch document → extract intents → write to DB.
    Updates parse_status: PENDING → PROCESSING → PARSED | FAILED
    """
    tenant_id = req.tenant_id
    document_id = req.document_id

    # 1. Resolve LLM key (tenant → system fallback)
    try:
        api_key = _resolve_llm_key(tenant_id)
        model = _resolve_model(tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 2. Fetch document record
    docs = _supa_get(
        "tenant_documents",
        {"document_id": f"eq.{document_id}", "tenant_id": f"eq.{tenant_id}"},
    )
    if not docs:
        raise HTTPException(status_code=404, detail="Document not found")

    doc = docs[0]

    # 3. Update status → PROCESSING
    _supa_patch(
        "tenant_documents",
        {"document_id": f"eq.{document_id}"},
        {"parse_status": "PROCESSING", "ai_model_used": model, "updated_at": _now()},
    )

    # 4. Get document text
    # For now, use the document content stored in DB or a placeholder
    # In production, this would fetch from Supabase Storage and parse PDF/DOCX
    doc_text = doc.get("content", "") or doc.get("raw_text", "")
    if not doc_text:
        doc_text = (
            f"Document: {doc.get('file_name', 'Unknown')}\n"
            f"Type: {doc.get('file_type', 'Unknown')}\n"
            f"This document is associated with import source: {doc.get('source_id', 'N/A')}"
        )
        logger.warning(
            f"No text content for document {document_id}, using metadata-based extraction"
        )

    # 5. Extract intents via Gemini
    try:
        result = _extract_intents_with_gemini(doc_text, api_key, model)
    except Exception as e:
        logger.error(f"Gemini extraction failed for {document_id}: {e}")
        _supa_patch(
            "tenant_documents",
            {"document_id": f"eq.{document_id}"},
            {"parse_status": "FAILED", "updated_at": _now()},
        )
        raise HTTPException(status_code=502, detail=f"LLM extraction failed: {e}")

    # 6. Write intents to intent_mappings + create edges
    relationships_created = 0
    for intent in result.intents:
        intent_id = str(uuid.uuid4())

        # Write intent
        _supa_insert("intent_mappings", {
            "intent_id": intent_id,
            "tenant_id": tenant_id,
            "intent_key": intent.intent_name,
            "description": f"{intent.trigger_condition} → {', '.join(intent.action_steps[:2])}",
            "source_type": "DOCUMENT",
            "source_id": document_id,
            "extracted_by": model,
            "confidence": 0.85 if intent.risk_level == "GREEN" else 0.70,
            "risk_level": intent.risk_level,
            "status": "PENDING_REVIEW" if intent.hitl_checkpoint else "ACTIVE",
            "compliance_frameworks": intent.compliance_frameworks,
            "hitl_checkpoint": intent.hitl_checkpoint,
            "action_steps": intent.action_steps,
            "created_at": _now(),
            "updated_at": _now(),
        })

        # Create EXTRACTS_FROM edge (intent → document)
        _supa_insert("resource_relationships", {
            "relationship_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "source_type": "INTENT",
            "source_id": intent_id,
            "target_type": "DOCUMENT",
            "target_id": document_id,
            "relationship_type": "EXTRACTS_FROM",
            "weight": 0.85 if intent.risk_level == "GREEN" else 0.70,
            "created_at": _now(),
        })
        relationships_created += 1

    # 7. Update document status → PARSED
    _supa_patch(
        "tenant_documents",
        {"document_id": f"eq.{document_id}"},
        {
            "parse_status": "PARSED",
            "extracted_intents": len(result.intents),
            "updated_at": _now(),
        },
    )

    logger.info(
        f"Extracted {len(result.intents)} intents from document {document_id} "
        f"for tenant {tenant_id} using {model}"
    )

    return ExtractResponse(
        document_id=document_id,
        intents_extracted=len(result.intents),
        intents=result.intents,
        relationships_created=relationships_created,
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Entrypoint ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
