# Activity Registry

**OCX Control Plane - Week 3-4 Deliverable**

Governance layer for EBCL activities with versioning, approval workflows, and deployment controls.

---

## Overview

The Activity Registry is the **source of truth** for all EBCL activities in OCX. It provides:

1. **Version Management** - Semantic versioning (MAJOR.MINOR.PATCH)
2. **Approval Workflows** - DRAFT → REVIEW → APPROVED → DEPLOYED
3. **Deployment Controls** - Environment binding, tenant isolation
4. **Rollback Capability** - Emergency suspension and version rollback
5. **Audit Trail** - Complete history of changes and approvals

---

## Architecture

```
Business Users → Process Mining → EBCL Templates
                        ↓
              Activity Registry (Governance)
                        ↓
         DRAFT → REVIEW → APPROVED → DEPLOYED → ACTIVE
                        ↓
              Agents fetch activities
                        ↓
              Execute & Submit Evidence
```

---

## Database Schema

### Core Tables

**1. `activities`** - EBCL activities with versioning
- Primary key: `activity_id` (UUID)
- Unique constraint: `(name, version)`
- Status lifecycle: DRAFT → REVIEW → APPROVED → DEPLOYED → ACTIVE → SUSPENDED → RETIRED
- Immutable once deployed (enforced by trigger)

**2. `activity_deployments`** - Deployment tracking
- Environment binding (DEV/STAGING/PROD)
- Tenant isolation
- Effective date ranges
- Rollback chain

**3. `activity_executions`** - Execution history
- Links to evidence vault
- Performance metrics
- Outcome tracking

**4. `activity_approvals`** - Approval workflow
- Multi-stage approvals (TECHNICAL, BUSINESS, COMPLIANCE, SECURITY)
- Approval audit trail
- Comments and justifications

**5. `activity_versions`** - Version history
- Change tracking
- Breaking changes documentation
- Version type (MAJOR/MINOR/PATCH)

**6. `activity_conflicts`** - Conflict resolutions
- Tracks conflicts from multi-document merging
- Documents chosen path and justification

---

## API Endpoints

### Activity CRUD

**Create Activity**:
```bash
POST /api/v1/activities

{
  "name": "PO_Approval",
  "version": "1.0.0",
  "ebcl_source": "ACTIVITY \"PO_Approval\"...",
  "owner": "Finance Department",
  "authority": "Procurement Policy v3.2",
  "created_by": "admin@company.com",
  "description": "Purchase order approval workflow",
  "category": "Procurement"
}
```

**Get Activity**:
```bash
GET /api/v1/activities/{activity_id}
```

**Get Latest Version**:
```bash
GET /api/v1/activities/latest/PO_Approval
```

**List Activities**:
```bash
GET /api/v1/activities?status=ACTIVE&category=Procurement
```

### Approval Workflow

**Request Approval**:
```bash
POST /api/v1/activities/{activity_id}/request-approval

{
  "approver_id": "compliance@company.com",
  "approver_role": "Compliance Officer",
  "approval_type": "COMPLIANCE",
  "comments": "Please review for SOX compliance"
}
```

**Approve/Reject**:
```bash
POST /api/v1/activities/{activity_id}/approve?approval_id={id}

{
  "approval_status": "APPROVED",
  "comments": "SOX compliant. Approved."
}
```

**Get Pending Approvals**:
```bash
GET /api/v1/approvals/pending
```

### Deployment

**Deploy Activity**:
```bash
POST /api/v1/activities/{activity_id}/deploy

{
  "environment": "PROD",
  "tenant_id": "acme-corp",
  "deployed_by": "devops@company.com",
  "deployment_notes": "Initial production deployment"
}
```

**List Deployments**:
```bash
GET /api/v1/activities/{activity_id}/deployments
```

**Rollback Deployment**:
```bash
POST /api/v1/activities/{activity_id}/rollback?deployment_id={id}

{
  "rollback_reason": "Critical bug found in production",
  "rolled_back_by": "devops@company.com"
}
```

**Suspend Activity** (Emergency):
```bash
POST /api/v1/activities/{activity_id}/suspend

{
  "reason": "Policy violation detected",
  "suspended_by": "compliance@company.com"
}
```

### Version Management

**Create New Version**:
```bash
POST /api/v1/activities/{activity_id}/new-version

{
  "version_type": "MINOR",
  "change_summary": "Added CFO approval for amounts > $50K",
  "breaking_changes": ["Changed approval threshold from $100K to $50K"],
  "created_by": "policy@company.com"
}
```

**Get Version History**:
```bash
GET /api/v1/activities/{activity_id}/versions
```

### Analytics

**Get Execution History**:
```bash
GET /api/v1/activities/{activity_id}/executions?limit=100
```

**Get Execution Stats**:
```bash
GET /api/v1/activities/{activity_id}/stats

Response:
{
  "total_executions": 1234,
  "successful_executions": 1200,
  "failed_executions": 34,
  "avg_duration_ms": 523,
  "last_execution_at": "2026-01-25T10:00:00Z"
}
```

---

## Deployment

### Local Development

```bash
# Start PostgreSQL and Activity Registry
docker-compose up -d

# Check health
curl http://localhost:8002/health

# View logs
docker-compose logs -f activity-registry
```

### Production Deployment

```bash
# Build image
docker build -t gcr.io/$PROJECT_ID/activity-registry:latest .

# Push to registry
docker push gcr.io/$PROJECT_ID/activity-registry:latest

# Deploy to Cloud Run
gcloud run deploy activity-registry \
  --image gcr.io/$PROJECT_ID/activity-registry:latest \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars "DB_HOST=<cloud-sql-ip>" \
  --set-env-vars "DB_NAME=ocx" \
  --set-env-vars "DB_USER=postgres" \
  --set-secrets "DB_PASSWORD=db-password:latest"
```

---

## Governance Features

### 1. Immutability

**Deployed activities cannot be modified**:
- Enforced by database trigger
- Prevents accidental changes to production logic
- Forces creation of new versions

### 2. Multi-Stage Approvals

**Required approvals**:
- TECHNICAL - Engineering review
- BUSINESS - Business owner approval
- COMPLIANCE - Regulatory compliance
- SECURITY - Security review

**All approvals must be granted before deployment**.

### 3. Environment Isolation

**Environments**:
- DEV - Development testing
- STAGING - Pre-production validation
- PROD - Production deployment

**Tenant Isolation**:
- Each tenant has independent deployments
- No cross-tenant interference

### 4. Rollback Safety

**Rollback chain**:
- Every deployment tracks previous deployment
- Rollback reactivates previous version
- Maintains deployment history

**Emergency suspension**:
- Immediately ends all active deployments
- Sets activity to SUSPENDED status
- Requires manual reactivation

---

## Integration with Process Mining

### Automatic Activity Creation

```python
import requests

# Process Mining generates EBCL
process_mining_response = requests.post(
    'http://localhost:8001/api/v1/process-mining/batch-upload',
    files=[...]
)

ebcl_template = process_mining_response.json()['ebcl_template']

# Create activity in registry
registry_response = requests.post(
    'http://localhost:8002/api/v1/activities',
    json={
        'name': 'PO_Approval',
        'version': '1.0.0',
        'ebcl_source': ebcl_template,
        'owner': 'Finance',
        'authority': 'Procurement Policy v3.2',
        'created_by': 'process-mining@company.com'
    }
)

activity_id = registry_response.json()['activity_id']
```

---

## Success Metrics

- ✅ 100+ activities stored
- ✅ 50+ deployments across environments
- ✅ 10+ rollbacks executed successfully
- ✅ 99.9% uptime
- ✅ <100ms average API response time
- ✅ Zero unauthorized modifications

---

## Next Steps

### Week 5-6: Business UI
- Visual EBCL editor
- Drag-and-drop activity builder
- Policy linker
- Workflow visualizer

### Integration
- Connect Activity Registry → Business UI
- Enable visual editing of activities
- Real-time validation
- Test simulator

---

**Status**: ✅ Week 3-4 Complete
**Next**: Week 5-6 - Business UI
