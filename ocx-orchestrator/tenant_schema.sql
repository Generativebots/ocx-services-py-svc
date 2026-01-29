-- OCX Multi-Tenant Configuration Schema
-- Tenant-specific feature flags and configuration

-- ============================================================================
-- TENANTS TABLE
-- ============================================================================

CREATE TABLE tenants (
    tenant_id TEXT PRIMARY KEY,
    tenant_name TEXT NOT NULL,
    organization_name TEXT NOT NULL,
    
    -- Subscription
    subscription_tier TEXT NOT NULL DEFAULT 'FREE',
    CHECK (subscription_tier IN ('FREE', 'STARTER', 'PROFESSIONAL', 'ENTERPRISE')),
    
    -- Status
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    CHECK (status IN ('ACTIVE', 'SUSPENDED', 'TRIAL', 'CANCELLED')),
    
    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    trial_ends_at TIMESTAMP,
    
    -- Contact
    admin_email TEXT NOT NULL,
    admin_name TEXT,
    
    -- Limits
    max_agents INTEGER DEFAULT 5,
    max_activities INTEGER DEFAULT 50,
    max_evidence_per_month INTEGER DEFAULT 10000,
    
    -- Settings
    settings JSONB DEFAULT '{}'::jsonb
);

-- ============================================================================
-- FEATURE FLAGS TABLE
-- Tenant-specific feature enablement
-- ============================================================================

CREATE TABLE tenant_features (
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    feature_name TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    
    -- Feature configuration
    config JSONB DEFAULT '{}'::jsonb,
    
    -- Metadata
    enabled_at TIMESTAMP,
    enabled_by TEXT,
    
    PRIMARY KEY (tenant_id, feature_name)
);

-- Feature categories
CREATE TYPE feature_category AS ENUM (
    'CORE',
    'PROCESS_MINING',
    'ACTIVITY_REGISTRY',
    'EVIDENCE_VAULT',
    'SOCKET_INTERCEPTION',
    'PARALLEL_AUDITING',
    'ADVANCED'
);

-- Feature definitions
CREATE TABLE features (
    feature_name TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    description TEXT,
    category feature_category NOT NULL,
    
    -- Availability by tier
    available_in_free BOOLEAN DEFAULT FALSE,
    available_in_starter BOOLEAN DEFAULT FALSE,
    available_in_professional BOOLEAN DEFAULT TRUE,
    available_in_enterprise BOOLEAN DEFAULT TRUE,
    
    -- Default configuration
    default_config JSONB DEFAULT '{}'::jsonb,
    
    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Insert feature definitions
INSERT INTO features (feature_name, display_name, description, category, available_in_free, available_in_starter, available_in_professional, available_in_enterprise) VALUES
-- Core features
('activity_execution', 'Activity Execution', 'Execute EBCL activities', 'CORE', TRUE, TRUE, TRUE, TRUE),
('evidence_collection', 'Evidence Collection', 'Collect and store evidence', 'CORE', TRUE, TRUE, TRUE, TRUE),

-- Process Mining
('process_mining', 'Process Mining', 'AI-powered EBCL extraction from documents', 'PROCESS_MINING', FALSE, TRUE, TRUE, TRUE),
('batch_processing', 'Batch Document Processing', 'Process multiple documents in parallel', 'PROCESS_MINING', FALSE, FALSE, TRUE, TRUE),
('conflict_resolution', 'Conflict Resolution', 'Automatic conflict resolution in extracted workflows', 'PROCESS_MINING', FALSE, FALSE, TRUE, TRUE),

-- Activity Registry
('activity_versioning', 'Activity Versioning', 'Semantic versioning for activities', 'ACTIVITY_REGISTRY', FALSE, TRUE, TRUE, TRUE),
('approval_workflows', 'Approval Workflows', 'Multi-stage approval process', 'ACTIVITY_REGISTRY', FALSE, FALSE, TRUE, TRUE),
('environment_isolation', 'Environment Isolation', 'DEV/STAGING/PROD environments', 'ACTIVITY_REGISTRY', FALSE, FALSE, TRUE, TRUE),
('rollback_capability', 'Rollback Capability', 'Rollback to previous versions', 'ACTIVITY_REGISTRY', FALSE, FALSE, TRUE, TRUE),

-- Evidence Vault
('immutable_evidence', 'Immutable Evidence', 'Blockchain-style immutable audit trail', 'EVIDENCE_VAULT', TRUE, TRUE, TRUE, TRUE),
('evidence_chain', 'Evidence Chain', 'Cryptographic chain for tamper detection', 'EVIDENCE_VAULT', FALSE, TRUE, TRUE, TRUE),
('trust_attestations', 'Trust Attestations', 'Multi-party evidence verification', 'EVIDENCE_VAULT', FALSE, FALSE, TRUE, TRUE),
('compliance_reports', 'Compliance Reports', 'Automated compliance reporting', 'EVIDENCE_VAULT', FALSE, FALSE, TRUE, TRUE),
('evidence_search', 'Evidence Search', 'Full-text search across evidence', 'EVIDENCE_VAULT', FALSE, TRUE, TRUE, TRUE),

-- Socket Interception
('socket_interception', 'Socket Interception', 'Real-time network compliance enforcement', 'SOCKET_INTERCEPTION', FALSE, FALSE, TRUE, TRUE),
('validate_rules', 'VALIDATE Rules', 'Activity-aware validation rules', 'SOCKET_INTERCEPTION', FALSE, FALSE, TRUE, TRUE),
('violation_logging', 'Violation Logging', 'Log policy violations', 'SOCKET_INTERCEPTION', FALSE, TRUE, TRUE, TRUE),

-- Parallel Auditing
('jury_verification', 'Jury Verification', 'Multi-agent consensus verification', 'PARALLEL_AUDITING', FALSE, FALSE, FALSE, TRUE),
('entropy_verification', 'Entropy Verification', 'Bias detection and anomaly analysis', 'PARALLEL_AUDITING', FALSE, FALSE, FALSE, TRUE),
('escrow_verification', 'Escrow Verification', 'Cryptographic third-party validation', 'PARALLEL_AUDITING', FALSE, FALSE, FALSE, TRUE),
('continuous_auditing', 'Continuous Auditing', 'Background evidence verification', 'PARALLEL_AUDITING', FALSE, FALSE, FALSE, TRUE),

-- Advanced features
('ai_assistance', 'AI Assistance', 'AI-powered activity suggestions', 'ADVANCED', FALSE, FALSE, TRUE, TRUE),
('workflow_visualization', 'Workflow Visualization', 'BPMN-style workflow diagrams', 'ADVANCED', FALSE, TRUE, TRUE, TRUE),
('test_simulator', 'Test Simulator', 'Test activities with mock data', 'ADVANCED', FALSE, TRUE, TRUE, TRUE),
('policy_linking', 'Policy Linking', 'Link policies to EBCL blocks', 'ADVANCED', FALSE, FALSE, TRUE, TRUE),
('custom_integrations', 'Custom Integrations', 'Custom API integrations', 'ADVANCED', FALSE, FALSE, FALSE, TRUE),
('sla_monitoring', 'SLA Monitoring', 'Monitor and enforce SLAs', 'ADVANCED', FALSE, FALSE, TRUE, TRUE),
('escalation_management', 'Escalation Management', 'Automated escalation workflows', 'ADVANCED', FALSE, FALSE, TRUE, TRUE);

-- ============================================================================
-- TENANT AGENTS TABLE
-- Track agents per tenant
-- ============================================================================

CREATE TABLE tenant_agents (
    agent_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    agent_name TEXT NOT NULL,
    agent_type TEXT NOT NULL,
    CHECK (agent_type IN ('HUMAN', 'SYSTEM', 'AI')),
    
    -- Status
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    CHECK (status IN ('ACTIVE', 'INACTIVE', 'SUSPENDED')),
    
    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMP,
    
    -- Configuration
    config JSONB DEFAULT '{}'::jsonb
);

-- ============================================================================
-- TENANT USAGE TRACKING
-- Track usage for billing and limits
-- ============================================================================

CREATE TABLE tenant_usage (
    usage_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    
    -- Usage period
    period_start TIMESTAMP NOT NULL,
    period_end TIMESTAMP NOT NULL,
    
    -- Metrics
    activities_executed INTEGER DEFAULT 0,
    evidence_collected INTEGER DEFAULT 0,
    documents_processed INTEGER DEFAULT 0,
    api_calls INTEGER DEFAULT 0,
    storage_bytes BIGINT DEFAULT 0,
    
    -- Costs
    estimated_cost DECIMAL(10,2) DEFAULT 0.00,
    
    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- VIEWS
-- ============================================================================

-- Tenant feature summary
CREATE VIEW tenant_feature_summary AS
SELECT 
    t.tenant_id,
    t.tenant_name,
    t.subscription_tier,
    COUNT(tf.feature_name) as enabled_features,
    json_agg(
        json_build_object(
            'feature', tf.feature_name,
            'enabled', tf.enabled,
            'category', f.category
        )
    ) as features
FROM tenants t
LEFT JOIN tenant_features tf ON t.tenant_id = tf.tenant_id
LEFT JOIN features f ON tf.feature_name = f.feature_name
GROUP BY t.tenant_id, t.tenant_name, t.subscription_tier;

-- Tenant usage summary
CREATE VIEW tenant_usage_summary AS
SELECT 
    t.tenant_id,
    t.tenant_name,
    t.subscription_tier,
    COUNT(DISTINCT ta.agent_id) as active_agents,
    COALESCE(SUM(tu.activities_executed), 0) as total_activities,
    COALESCE(SUM(tu.evidence_collected), 0) as total_evidence,
    COALESCE(SUM(tu.documents_processed), 0) as total_documents,
    COALESCE(SUM(tu.estimated_cost), 0) as total_cost
FROM tenants t
LEFT JOIN tenant_agents ta ON t.tenant_id = ta.tenant_id AND ta.status = 'ACTIVE'
LEFT JOIN tenant_usage tu ON t.tenant_id = tu.tenant_id
GROUP BY t.tenant_id, t.tenant_name, t.subscription_tier;

-- ============================================================================
-- FUNCTIONS
-- ============================================================================

-- Check if feature is enabled for tenant
CREATE OR REPLACE FUNCTION is_feature_enabled(p_tenant_id TEXT, p_feature_name TEXT)
RETURNS BOOLEAN AS $$
DECLARE
    v_enabled BOOLEAN;
BEGIN
    SELECT enabled INTO v_enabled
    FROM tenant_features
    WHERE tenant_id = p_tenant_id AND feature_name = p_feature_name;
    
    RETURN COALESCE(v_enabled, FALSE);
END;
$$ LANGUAGE plpgsql;

-- Enable feature for tenant
CREATE OR REPLACE FUNCTION enable_feature(
    p_tenant_id TEXT,
    p_feature_name TEXT,
    p_enabled_by TEXT DEFAULT NULL
)
RETURNS VOID AS $$
BEGIN
    INSERT INTO tenant_features (tenant_id, feature_name, enabled, enabled_at, enabled_by)
    VALUES (p_tenant_id, p_feature_name, TRUE, NOW(), p_enabled_by)
    ON CONFLICT (tenant_id, feature_name)
    DO UPDATE SET enabled = TRUE, enabled_at = NOW(), enabled_by = p_enabled_by;
END;
$$ LANGUAGE plpgsql;

-- Check tenant limits
CREATE OR REPLACE FUNCTION check_tenant_limit(
    p_tenant_id TEXT,
    p_limit_type TEXT,
    p_current_count INTEGER
)
RETURNS BOOLEAN AS $$
DECLARE
    v_limit INTEGER;
BEGIN
    CASE p_limit_type
        WHEN 'agents' THEN
            SELECT max_agents INTO v_limit FROM tenants WHERE tenant_id = p_tenant_id;
        WHEN 'activities' THEN
            SELECT max_activities INTO v_limit FROM tenants WHERE tenant_id = p_tenant_id;
        WHEN 'evidence' THEN
            SELECT max_evidence_per_month INTO v_limit FROM tenants WHERE tenant_id = p_tenant_id;
        ELSE
            RETURN TRUE;
    END CASE;
    
    RETURN p_current_count < v_limit;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- SAMPLE DATA
-- ============================================================================

-- Create sample tenants
INSERT INTO tenants (tenant_id, tenant_name, organization_name, subscription_tier, admin_email, max_agents, max_activities, max_evidence_per_month) VALUES
('acme-corp', 'Acme Corporation', 'Acme Corp', 'ENTERPRISE', 'admin@acme.com', 100, 1000, 1000000),
('startup-inc', 'Startup Inc', 'Startup Inc', 'PROFESSIONAL', 'admin@startup.com', 20, 200, 100000),
('demo-tenant', 'Demo Tenant', 'Demo Organization', 'TRIAL', 'demo@example.com', 5, 50, 10000);

-- Enable features for enterprise tenant
INSERT INTO tenant_features (tenant_id, feature_name, enabled, enabled_at)
SELECT 'acme-corp', feature_name, TRUE, NOW()
FROM features
WHERE available_in_enterprise = TRUE;

-- Enable features for professional tenant
INSERT INTO tenant_features (tenant_id, feature_name, enabled, enabled_at)
SELECT 'startup-inc', feature_name, TRUE, NOW()
FROM features
WHERE available_in_professional = TRUE;

-- Grant permissions
-- GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO ocx_app;
-- GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO ocx_app;
