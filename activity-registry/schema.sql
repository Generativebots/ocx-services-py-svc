-- Activity Registry Database Schema
-- OCX Control Plane - Week 3-4

-- ============================================================================
-- ACTIVITIES TABLE
-- Stores EBCL activities with versioning and governance
-- ============================================================================

CREATE TABLE activities (
    -- Identity
    activity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    
    -- Status lifecycle: DRAFT → REVIEW → APPROVED → DEPLOYED → ACTIVE → SUSPENDED → RETIRED
    status TEXT NOT NULL DEFAULT 'DRAFT',
    CHECK (status IN ('DRAFT', 'REVIEW', 'APPROVED', 'DEPLOYED', 'ACTIVE', 'SUSPENDED', 'RETIRED')),
    
    -- EBCL content
    ebcl_source TEXT NOT NULL,
    compiled_artifact JSONB,
    
    -- Governance
    owner TEXT NOT NULL,
    authority TEXT NOT NULL, -- Policy reference (e.g., "Procurement Policy v3.2")
    
    -- Audit trail
    created_by TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    approved_by TEXT,
    approved_at TIMESTAMP,
    deployed_by TEXT,
    deployed_at TIMESTAMP,
    
    -- Integrity
    hash TEXT NOT NULL, -- SHA-256 of ebcl_source
    
    -- Metadata
    description TEXT,
    tags TEXT[],
    category TEXT, -- e.g., "Procurement", "Finance", "HR"
    
    -- Unique constraint: one version per activity name
    UNIQUE(name, version)
);

-- Indexes for performance
CREATE INDEX idx_activities_tenant ON activities(tenant_id);
CREATE INDEX idx_activities_name ON activities(name);
CREATE INDEX idx_activities_status ON activities(status);
CREATE INDEX idx_activities_owner ON activities(owner);
CREATE INDEX idx_activities_created_at ON activities(created_at DESC);
CREATE INDEX idx_activities_category ON activities(category);

-- ============================================================================
-- ACTIVITY_DEPLOYMENTS TABLE
-- Tracks where activities are deployed (environment, tenant)
-- ============================================================================

CREATE TABLE activity_deployments (
    -- Identity
    deployment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    activity_id UUID NOT NULL REFERENCES activities(activity_id) ON DELETE CASCADE,
    
    -- Deployment target
    environment TEXT NOT NULL, -- DEV, STAGING, PROD
    CHECK (environment IN ('DEV', 'STAGING', 'PROD')),
    tenant_id TEXT NOT NULL,
    
    -- Effective period
    effective_from TIMESTAMP NOT NULL DEFAULT NOW(),
    effective_until TIMESTAMP, -- NULL means active indefinitely
    
    -- Audit trail
    deployed_by TEXT NOT NULL,
    deployed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Rollback info
    previous_deployment_id UUID REFERENCES activity_deployments(deployment_id),
    rollback_reason TEXT,
    
    -- Metadata
    deployment_notes TEXT,
    
    -- Unique constraint: one active deployment per environment+tenant+activity
    UNIQUE(activity_id, environment, tenant_id, effective_from)
);

-- Indexes
CREATE INDEX idx_deployments_activity ON activity_deployments(activity_id);
CREATE INDEX idx_deployments_environment ON activity_deployments(environment);
CREATE INDEX idx_deployments_tenant ON activity_deployments(tenant_id);
CREATE INDEX idx_deployments_effective ON activity_deployments(effective_from, effective_until);

-- ============================================================================
-- ACTIVITY_EXECUTIONS TABLE
-- Tracks every execution of an activity
-- ============================================================================

CREATE TABLE activity_executions (
    -- Identity
    execution_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    activity_id UUID NOT NULL REFERENCES activities(activity_id) ON DELETE CASCADE,
    activity_version TEXT NOT NULL,
    
    -- Execution context
    tenant_id TEXT NOT NULL,
    environment TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    
    -- Execution lifecycle
    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'RUNNING',
    CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED', 'TIMEOUT')),
    
    -- Outcome
    outcome TEXT, -- e.g., "AutoApprove", "ManagerApproval"
    error_message TEXT,
    
    -- Evidence
    evidence_id UUID, -- Links to evidence vault
    
    -- Metadata
    input_data JSONB,
    output_data JSONB,
    duration_ms INTEGER,
    
    -- Audit
    triggered_by TEXT,
    trigger_event TEXT
);

-- Indexes
CREATE INDEX idx_executions_activity ON activity_executions(activity_id);
CREATE INDEX idx_executions_tenant ON activity_executions(tenant_id);
CREATE INDEX idx_executions_agent ON activity_executions(agent_id);
CREATE INDEX idx_executions_started_at ON activity_executions(started_at DESC);
CREATE INDEX idx_executions_status ON activity_executions(status);

-- ============================================================================
-- ACTIVITY_APPROVALS TABLE
-- Tracks approval workflow
-- ============================================================================

CREATE TABLE activity_approvals (
    approval_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    activity_id UUID NOT NULL REFERENCES activities(activity_id) ON DELETE CASCADE,
    
    -- Approval details
    approver_id TEXT NOT NULL,
    approver_role TEXT NOT NULL, -- e.g., "Compliance Officer", "Business Owner"
    approval_status TEXT NOT NULL,
    CHECK (approval_status IN ('PENDING', 'APPROVED', 'REJECTED')),
    
    -- Audit
    requested_at TIMESTAMP NOT NULL DEFAULT NOW(),
    responded_at TIMESTAMP,
    comments TEXT,
    
    -- Metadata
    approval_type TEXT NOT NULL, -- e.g., "TECHNICAL", "BUSINESS", "COMPLIANCE"
    CHECK (approval_type IN ('TECHNICAL', 'BUSINESS', 'COMPLIANCE', 'SECURITY'))
);

-- Indexes
CREATE INDEX idx_approvals_activity ON activity_approvals(activity_id);
CREATE INDEX idx_approvals_approver ON activity_approvals(approver_id);
CREATE INDEX idx_approvals_status ON activity_approvals(approval_status);

-- ============================================================================
-- ACTIVITY_VERSIONS TABLE
-- Tracks version history and changes
-- ============================================================================

CREATE TABLE activity_versions (
    version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    activity_id UUID NOT NULL REFERENCES activities(activity_id) ON DELETE CASCADE,
    
    -- Version info
    version TEXT NOT NULL,
    previous_version TEXT,
    version_type TEXT NOT NULL, -- MAJOR, MINOR, PATCH
    CHECK (version_type IN ('MAJOR', 'MINOR', 'PATCH')),
    
    -- Change tracking
    change_summary TEXT NOT NULL,
    breaking_changes TEXT[],
    
    -- Audit
    created_by TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    UNIQUE(activity_id, version)
);

-- Indexes
CREATE INDEX idx_versions_activity ON activity_versions(activity_id);
CREATE INDEX idx_versions_created_at ON activity_versions(created_at DESC);

-- ============================================================================
-- ACTIVITY_CONFLICTS TABLE
-- Tracks conflicts resolved during multi-document merging
-- ============================================================================

CREATE TABLE activity_conflicts (
    conflict_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    activity_id UUID NOT NULL REFERENCES activities(activity_id) ON DELETE CASCADE,
    
    -- Conflict details
    conflict_issue TEXT NOT NULL,
    conflicting_documents TEXT[] NOT NULL,
    chosen_path TEXT NOT NULL,
    justification TEXT NOT NULL,
    rule_applied TEXT NOT NULL, -- e.g., "Compliance > Policy > SOP"
    
    -- Audit
    resolved_by TEXT NOT NULL,
    resolved_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_conflicts_activity ON activity_conflicts(activity_id);

-- ============================================================================
-- VIEWS
-- ============================================================================

-- Active activities by environment
CREATE VIEW active_activities AS
SELECT 
    a.activity_id,
    a.name,
    a.version,
    a.status,
    a.owner,
    a.authority,
    d.environment,
    d.tenant_id,
    d.effective_from,
    d.effective_until
FROM activities a
JOIN activity_deployments d ON a.activity_id = d.activity_id
WHERE a.status = 'ACTIVE'
  AND d.effective_from <= NOW()
  AND (d.effective_until IS NULL OR d.effective_until > NOW());

-- Activity execution stats
CREATE VIEW activity_execution_stats AS
SELECT 
    a.activity_id,
    a.name,
    a.version,
    COUNT(e.execution_id) as total_executions,
    COUNT(CASE WHEN e.status = 'COMPLETED' THEN 1 END) as successful_executions,
    COUNT(CASE WHEN e.status = 'FAILED' THEN 1 END) as failed_executions,
    AVG(e.duration_ms) as avg_duration_ms,
    MAX(e.started_at) as last_execution_at
FROM activities a
LEFT JOIN activity_executions e ON a.activity_id = e.activity_id
GROUP BY a.activity_id, a.name, a.version;

-- Pending approvals
CREATE VIEW pending_approvals AS
SELECT 
    a.activity_id,
    a.name,
    a.version,
    a.owner,
    ap.approval_id,
    ap.approver_id,
    ap.approver_role,
    ap.approval_type,
    ap.requested_at,
    EXTRACT(EPOCH FROM (NOW() - ap.requested_at))/3600 as hours_pending
FROM activities a
JOIN activity_approvals ap ON a.activity_id = ap.activity_id
WHERE ap.approval_status = 'PENDING'
ORDER BY ap.requested_at ASC;

-- ============================================================================
-- FUNCTIONS
-- ============================================================================

-- Function to get latest version of an activity
CREATE OR REPLACE FUNCTION get_latest_version(activity_name TEXT)
RETURNS TABLE (
    activity_id UUID,
    version TEXT,
    status TEXT,
    ebcl_source TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT a.activity_id, a.version, a.status, a.ebcl_source
    FROM activities a
    WHERE a.name = activity_name
      AND a.status IN ('ACTIVE', 'DEPLOYED')
    ORDER BY 
        CASE 
            WHEN a.status = 'ACTIVE' THEN 1
            WHEN a.status = 'DEPLOYED' THEN 2
        END,
        a.created_at DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- Function to check if activity can be deployed
CREATE OR REPLACE FUNCTION can_deploy_activity(p_activity_id UUID)
RETURNS BOOLEAN AS $$
DECLARE
    activity_status TEXT;
    pending_approvals INTEGER;
BEGIN
    -- Get activity status
    SELECT status INTO activity_status
    FROM activities
    WHERE activity_id = p_activity_id;
    
    -- Check if approved
    IF activity_status != 'APPROVED' THEN
        RETURN FALSE;
    END IF;
    
    -- Check for pending approvals
    SELECT COUNT(*) INTO pending_approvals
    FROM activity_approvals
    WHERE activity_id = p_activity_id
      AND approval_status = 'PENDING';
    
    IF pending_approvals > 0 THEN
        RETURN FALSE;
    END IF;
    
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- TRIGGERS
-- ============================================================================

-- Trigger to update activity hash on insert/update
CREATE OR REPLACE FUNCTION update_activity_hash()
RETURNS TRIGGER AS $$
BEGIN
    NEW.hash = encode(digest(NEW.ebcl_source, 'sha256'), 'hex');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_activity_hash
BEFORE INSERT OR UPDATE OF ebcl_source ON activities
FOR EACH ROW
EXECUTE FUNCTION update_activity_hash();

-- Trigger to prevent modification of deployed activities
CREATE OR REPLACE FUNCTION prevent_deployed_modification()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.status IN ('DEPLOYED', 'ACTIVE') AND NEW.ebcl_source != OLD.ebcl_source THEN
        RAISE EXCEPTION 'Cannot modify deployed or active activity. Create a new version instead.';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_prevent_deployed_modification
BEFORE UPDATE ON activities
FOR EACH ROW
EXECUTE FUNCTION prevent_deployed_modification();

-- ============================================================================
-- SAMPLE DATA (for testing)
-- ============================================================================

-- Insert sample activity
INSERT INTO activities (
    name, version, status, ebcl_source, owner, authority, created_by, description, category
) VALUES (
    'PO_Approval',
    '1.0.0',
    'DRAFT',
    'ACTIVITY "PO_Approval"

OWNER Finance
VERSION 1.0
AUTHORITY "Procurement Policy v3.2"

TRIGGER
    ON Event.PurchaseRequest.Created

VALIDATE
    REQUIRE amount > 0
    REQUIRE vendor.isApproved == true

DECIDE
    IF amount <= 50000
        OUTCOME AutoApprove
    ELSE
        OUTCOME ManagerApproval

ACT
    AutoApprove:
        SYSTEM ERP.CREATE_PO
    ManagerApproval:
        HUMAN Manager.APPROVE
        SYSTEM WAIT Approval
        SYSTEM ERP.CREATE_PO

EVIDENCE
    LOG decision
    LOG policy_reference
    STORE immutable',
    'Finance Department',
    'Procurement Policy v3.2',
    'admin@company.com',
    'Purchase order approval workflow with automatic approval for amounts <= $50K',
    'Procurement'
);

-- Grant permissions (adjust as needed)
-- GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO ocx_app;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ocx_app;
