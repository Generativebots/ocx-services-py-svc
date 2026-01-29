# Process Mining Engine

**OCX Control Plane - Week 1-2 Deliverable**

Extract business workflows from documents using Google Cloud AI.

---

## Overview

The Process Mining Engine converts business documents (SOPs, policies, BRDs, FRDs) into executable EBCL activities using:

1. **Google Document AI** - OCR and document parsing
2. **Vertex AI (Gemini 1.5 Pro)** - Workflow extraction and EBCL generation
3. **Cloud Storage** - Document storage
4. **FastAPI** - REST API

---

## Architecture

```
Business Document (PDF/TXT/DOCX)
         ↓
Document AI (OCR + Parsing)
         ↓
Process Extraction Table
(Actor | Action | Input | Output | Condition | System)
         ↓
Vertex AI Gemini (Workflow Analysis)
         ↓
EBCL Template
```

---

## Features

### 1. Document Parser
- **OCR**: Extract text from PDFs and images
- **Structure**: Identify paragraphs, tables, entities
- **Metadata**: Extract document type, version, owner
- **Storage**: Upload to Cloud Storage

### 2. Process Extraction
- **Actionable Statements**: Extract only actions (ignore philosophy)
- **Actor Normalization**: Normalize role names across documents
- **Business Events**: Identify core events (Request created, Approval granted, etc.)
- **System Identification**: Detect ERP/CRM/payment systems

### 3. EBCL Generation
- **Template Generation**: Create complete EBCL activities
- **Policy Linking**: Link to source documents
- **Validation**: Pre-fill VALIDATE rules
- **Decision Logic**: Generate DECIDE blocks
- **Actions**: Specify SYSTEM/HUMAN actions

---

## API Endpoints

### 1. Parse Document
```bash
POST /api/v1/process-mining/parse
```

Upload a document for parsing.

**Request**:
```bash
curl -X POST http://localhost:8001/api/v1/process-mining/parse \
  -F 'file=@purchase_order_sop.txt' \
  -F 'company_id=demo-company'
```

**Response**:
```json
{
  "doc_id": "uuid",
  "document_type": "SOP",
  "pages": 1,
  "entities": 5,
  "paragraphs": 8,
  "tables": 0,
  "confidence": 0.95,
  "metadata": {
    "version": "2.3",
    "owner": "Finance Department",
    "gcs_uri": "gs://bucket/path"
  }
}
```

### 2. Extract Process
```bash
POST /api/v1/process-mining/extract-process
```

Extract process table from document text.

**Request**:
```json
{
  "doc_id": "uuid",
  "document_text": "...",
  "document_type": "SOP"
}
```

**Response**:
```json
{
  "process_table": [
    {
      "actor": "Finance Manager",
      "action": "Approve invoice",
      "input": "Invoice",
      "output": "Approved invoice",
      "condition": "If amount > $10,000",
      "system": "ERP"
    }
  ],
  "business_events": [
    "Request created",
    "Budget validated",
    "Manager approved"
  ]
}
```

### 3. Generate EBCL
```bash
POST /api/v1/process-mining/generate-ebcl
```

Generate EBCL template from process table.

**Request**:
```json
{
  "process_table": [...],
  "business_events": [...],
  "document_metadata": {...}
}
```

**Response**:
```json
{
  "ebcl_template": "ACTIVITY \"PO_Approval\"\n...",
  "activity_name": "PO_Approval"
}
```

### 4. Complete Workflow (One-Shot)
```bash
POST /api/v1/process-mining/complete-workflow
```

End-to-end: Parse → Extract → Generate EBCL.

**Request**:
```bash
curl -X POST http://localhost:8001/api/v1/process-mining/complete-workflow \
  -F 'file=@purchase_order_sop.txt' \
  -F 'company_id=demo-company'
```

**Response**:
```json
{
  "doc_id": "uuid",
  "process_table": [...],
  "business_events": [...],
  "ebcl_template": "ACTIVITY \"PO_Approval\"\n...",
  "metadata": {...}
}
```

---

## Setup

### Prerequisites
- Google Cloud Project
- Document AI API enabled
- Vertex AI API enabled
- Cloud Storage API enabled
- Service account with permissions

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Setup Google Cloud
```bash
chmod +x setup-gcp.sh
./setup-gcp.sh
```

This will:
- Enable required APIs
- Create Document AI processor
- Create Cloud Storage bucket
- Create service account
- Deploy to Cloud Run

### 3. Run Locally
```bash
# Set environment variables
export GOOGLE_CLOUD_PROJECT=your-project-id
export DOCUMENT_AI_PROCESSOR_ID=your-processor-id
export DOCUMENT_STORAGE_BUCKET=your-bucket-name
export GOOGLE_APPLICATION_CREDENTIALS=service-account-key.json

# Run service
python api.py
```

Service runs on `http://localhost:8001`

### 4. Deploy to Cloud Run
```bash
# Build
docker build -t gcr.io/$PROJECT_ID/process-mining:latest .

# Push
docker push gcr.io/$PROJECT_ID/process-mining:latest

# Deploy
gcloud run deploy process-mining \
  --image gcr.io/$PROJECT_ID/process-mining:latest \
  --region us-central1 \
  --allow-unauthenticated
```

---

## Example Usage

### Upload and Process Document
```python
import requests

# Upload document
with open('purchase_order_sop.txt', 'rb') as f:
    response = requests.post(
        'http://localhost:8001/api/v1/process-mining/complete-workflow',
        files={'file': f},
        data={'company_id': 'demo-company'}
    )

result = response.json()

print(f"Document Type: {result['metadata']['document_type']}")
print(f"Process Steps: {len(result['process_table'])}")
print(f"Business Events: {len(result['business_events'])}")
print(f"\nEBCL Template:\n{result['ebcl_template']}")
```

### Output
```
Document Type: SOP
Process Steps: 5
Business Events: 6

EBCL Template:
ACTIVITY "PO_Approval"

OWNER Finance
VERSION 1.0
AUTHORITY "Procurement Policy v3.2"

TRIGGER
    ON Event.PurchaseRequest.Created

VALIDATE
    REQUIRE amount > 0
    REQUIRE vendor.isApproved == true
    REQUIRE budget.available >= amount

DECIDE
    IF amount <= 50000
        OUTCOME AutoApprove
    ELSE
        OUTCOME ManagerApproval

ACT
    AutoApprove:
        SYSTEM ERP.CREATE_PO
        SYSTEM NOTIFY Requester
    ManagerApproval:
        HUMAN Manager.APPROVE
        SYSTEM WAIT Approval
        SYSTEM ERP.CREATE_PO

EVIDENCE
    LOG decision
    LOG policy_reference
    LOG timestamps
    STORE immutable
```

---

## Cost Estimate

### Google Cloud Costs (Monthly)

| Service | Usage | Cost |
|---------|-------|------|
| Document AI | 1,000 pages | $15 |
| Vertex AI (Gemini) | 1M tokens | $7 |
| Cloud Storage | 10 GB | $0.20 |
| Cloud Run | 100 hours | $5 |
| **Total** | | **$27.20** |

### Cost Optimization
- Use Cloud Run with min instances = 0 (pay per request)
- Cache parsed documents in Cloud Storage
- Batch process documents
- Use Gemini Flash for simple documents ($0.35/1M tokens)

---

## Testing

### Test with Sample Documents
```bash
# Test purchase order SOP
curl -X POST http://localhost:8001/api/v1/process-mining/complete-workflow \
  -F 'file=@../../demo-documents/purchase_order_sop.txt'

# Test patient transfer protocol
curl -X POST http://localhost:8001/api/v1/process-mining/complete-workflow \
  -F 'file=@../../demo-documents/patient_transfer_protocol.txt'

# Test loan approval workflow
curl -X POST http://localhost:8001/api/v1/process-mining/complete-workflow \
  -F 'file=@../../demo-documents/loan_approval_workflow.txt'
```

---

## Next Steps

### Week 3-4: Activity Registry
- Store EBCL activities
- Version management
- Approval workflows
- Deployment controls

### Integration
- Connect Process Mining → Activity Registry
- Auto-create activities from EBCL templates
- Link to source documents
- Track document versions

---

## Files

```
services/process-mining/
├── document_parser.py      # Google Document AI integration
├── process_extraction.py   # Vertex AI Gemini workflow extraction
├── api.py                  # FastAPI service
├── requirements.txt        # Python dependencies
├── Dockerfile              # Container image
├── setup-gcp.sh            # Google Cloud setup script
└── README.md               # This file
```

---

## Success Metrics

- ✅ Parse 10+ business documents
- ✅ Extract 20+ EBCL activities
- ✅ 90%+ accuracy on process extraction
- ✅ <5 seconds per document processing
- ✅ Deploy to Cloud Run
- ✅ Cost < $30/month

---

## Support

For issues or questions:
- Check logs: `gcloud run logs read process-mining --region us-central1`
- Test health: `curl https://your-service.run.app/health`
- Review Document AI: https://console.cloud.google.com/ai/document-ai
- Review Vertex AI: https://console.cloud.google.com/vertex-ai

---

**Status**: ✅ Week 1-2 Complete
**Next**: Week 3-4 - Activity Registry
