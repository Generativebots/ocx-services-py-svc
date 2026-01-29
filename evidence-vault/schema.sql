-- Evidence Vault Database Schema
-- OCX Control Plane - Week 7-8

-- ============================================================================
-- EVIDENCE TABLE
-- Immutable audit trail for all activity executions
-- ============================================================================

CREATE TABLE evidence (
    -- Identity
    evidence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Activity context
    activity_id UUID NOT NULL,
    activity_name TEXT NOT NULL,
    activity_version TEXT NOT NULL,
    execution_id UUID NOT NULL,
    
    -- Agent context
    agent_id TEXT NOT NULL,
    agent_type TEXT NOT NULL, -- HUMAN, SYSTEM, AI
    
    -- Tenant context
    tenant_id TEXT NOT NULL,
    environment TEXT NOT NULL,
    CHECK (environment IN ('DEV', 'STAGING', 'PROD')),
    
    -- Evidence payload
    event_type TEXT NOT NULL, -- TRIGGER, VALIDATE, DECIDE, ACT, EXCEPTION
    event_data JSONB NOT NULL,
    
    -- Decision tracking
    decision TEXT,
    outcome TEXT,
    policy_reference TEXT NOT NULL,
    
    -- Verification
    verified BOOLEAN DEFAULT FALSE,
    verification_status TEXT DEFAULT 'PENDING',
    CHECK (verification_status IN ('PENDING', 'VERIFIED', 'FAILED', 'DISPUTED')),
    verification_errors TEXT[],
    
    -- Cryptographic integrity
    hash TEXT NOT NULL, -- SHA-256 of evidence payload
    previous_hash TEXT, -- Chain to previous evidence
    signature TEXT, -- Digital signature
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    verified_at TIMESTAMP,
    
    -- Metadata
    tags TEXT[],
    metadata JSONB,
    
    -- Immutability constraint
    CONSTRAINT evidence_immutable CHECK (created_at <= NOW())
);

-- Indexes for performance
CREATE INDEX idx_evidence_activity ON evidence(activity_id);
CREATE INDEX idx_evidence_execution ON evidence(execution_id);
CREATE INDEX idx_evidence_agent ON evidence(agent_id);
CREATE INDEX idx_evidence_tenant ON evidence(tenant_id);
CREATE INDEX idx_evidence_created_at ON evidence(created_at DESC);
CREATE INDEX idx_evidence_event_type ON evidence(event_type);
CREATE INDEX idx_evidence_verification ON evidence(verification_status);
CREATE INDEX idx_evidence_policy ON evidence(policy_reference);

-- Full-text search on event_data
CREATE INDEX idx_evidence_event_data_gin ON evidence USING gin(event_data);

-- ============================================================================
-- EVIDENCE_CHAIN TABLE
-- Blockchain-style chain for tamper detection
-- ============================================================================

CREATE TABLE evidence_chain (
    chain_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evidence_id UUID NOT NULL REFERENCES evidence(evidence_id),
    
    -- Chain metadata
    block_number BIGSERIAL,
    previous_block_hash TEXT,
    merkle_root TEXT,
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    UNIQUE(block_number)
);

CREATE INDEX idx_chain_evidence ON evidence_chain(evidence_id);
CREATE INDEX idx_chain_block ON evidence_chain(block_number DESC);

-- ============================================================================
-- EVIDENCE_ATTESTATIONS TABLE
-- Trust attestations from multiple verifiers (Jury, Entropy, Escrow)
-- ============================================================================

CREATE TABLE evidence_attestations (
    attestation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evidence_id UUID NOT NULL REFERENCES evidence(evidence_id),
    
    -- Attestation source
    attestor_type TEXT NOT NULL, -- JURY, ENTROPY, ESCROW, COMPLIANCE_OFFICER
    attestor_id TEXT NOT NULL,
    
    -- Attestation result
    attestation_status TEXT NOT NULL,
    CHECK (attestation_status IN ('APPROVED', 'REJECTED', 'DISPUTED')),
    
    -- Reasoning
    confidence_score DECIMAL(3,2), -- 0.00 to 1.00
    reasoning TEXT,
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Cryptographic proof
    signature TEXT,
    proof JSONB
);

CREATE INDEX idx_attestations_evidence ON evidence_attestations(evidence_id);
CREATE INDEX idx_attestations_type ON evidence_attestations(attestor_type);
CREATE INDEX idx_attestations_status ON evidence_attestations(attestation_status);

-- ============================================================================
-- COMPLIANCE_REPORTS TABLE
-- Aggregated compliance reports for auditors
-- ============================================================================

CREATE TABLE compliance_reports (
    report_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Report scope
    tenant_id TEXT NOT NULL,
    start_date TIMESTAMP NOT NULL,
    end_date TIMESTAMP NOT NULL,
    
    -- Report type
    report_type TEXT NOT NULL, -- DAILY, WEEKLY, MONTHLY, ANNUAL, AUDIT
    
    -- Statistics
    total_evidence_count INTEGER,
    verified_evidence_count INTEGER,
    failed_evidence_count INTEGER,
    disputed_evidence_count INTEGER,
    
    -- Compliance metrics
    compliance_score DECIMAL(5,2), -- 0.00 to 100.00
    policy_violations INTEGER,
    
    -- Report data
    report_data JSONB NOT NULL,
    
    -- Timestamps
    generated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Status
    status TEXT DEFAULT 'DRAFT',
    CHECK (status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED'))
);

CREATE INDEX idx_reports_tenant ON compliance_reports(tenant_id);
CREATE INDEX idx_reports_generated ON compliance_reports(generated_at DESC);
CREATE INDEX idx_reports_type ON compliance_reports(report_type);

-- ============================================================================
-- VIEWS
-- ============================================================================

-- Evidence verification summary
CREATE VIEW evidence_verification_summary AS
SELECT 
    tenant_id,
    environment,
    COUNT(*) as total_evidence,
    COUNT(CASE WHEN verified = true THEN 1 END) as verified_count,
    COUNT(CASE WHEN verification_status = 'FAILED' THEN 1 END) as failed_count,
    COUNT(CASE WHEN verification_status = 'DISPUTED' THEN 1 END) as disputed_count,
    ROUND(
        COUNT(CASE WHEN verified = true THEN 1 END)::DECIMAL / 
        NULLIF(COUNT(*), 0) * 100, 
        2
    ) as verification_rate
FROM evidence
GROUP BY tenant_id, environment;

-- Activity execution evidence
CREATE VIEW activity_execution_evidence AS
SELECT 
    e.evidence_id,
    e.activity_name,
    e.activity_version,
    e.execution_id,
    e.agent_id,
    e.event_type,
    e.decision,
    e.outcome,
    e.policy_reference,
    e.verified,
    e.created_at,
    COUNT(a.attestation_id) as attestation_count,
    AVG(a.confidence_score) as avg_confidence
FROM evidence e
LEFT JOIN evidence_attestations a ON e.evidence_id = a.evidence_id
GROUP BY e.evidence_id;

-- Policy compliance tracking
CREATE VIEW policy_compliance_tracking AS
SELECT 
    policy_reference,
    tenant_id,
    COUNT(*) as total_executions,
    COUNT(CASE WHEN verified = true THEN 1 END) as compliant_executions,
    COUNT(CASE WHEN verification_status = 'FAILED' THEN 1 END) as violations,
    ROUND(
        COUNT(CASE WHEN verified = true THEN 1 END)::DECIMAL / 
        NULLIF(COUNT(*), 0) * 100, 
        2
    ) as compliance_rate
FROM evidence
GROUP BY policy_reference, tenant_id;

-- ============================================================================
-- FUNCTIONS
-- ============================================================================

-- Function to verify evidence integrity
CREATE OR REPLACE FUNCTION verify_evidence_integrity(p_evidence_id UUID)
RETURNS BOOLEAN AS $$
DECLARE
    v_evidence RECORD;
    v_calculated_hash TEXT;
BEGIN
    -- Get evidence
    SELECT * INTO v_evidence
    FROM evidence
    WHERE evidence_id = p_evidence_id;
    
    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;
    
    -- Calculate hash of event_data
    v_calculated_hash := encode(
        digest(v_evidence.event_data::TEXT, 'sha256'), 
        'hex'
    );
    
    -- Compare with stored hash
    RETURN v_calculated_hash = v_evidence.hash;
END;
$$ LANGUAGE plpgsql;

-- Function to get evidence chain
CREATE OR REPLACE FUNCTION get_evidence_chain(p_evidence_id UUID)
RETURNS TABLE (
    evidence_id UUID,
    block_number BIGINT,
    hash TEXT,
    previous_hash TEXT,
    created_at TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        e.evidence_id,
        ec.block_number,
        e.hash,
        e.previous_hash,
        e.created_at
    FROM evidence e
    JOIN evidence_chain ec ON e.evidence_id = ec.evidence_id
    WHERE e.evidence_id = p_evidence_id
    ORDER BY ec.block_number DESC;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- TRIGGERS
-- ============================================================================

-- Trigger to calculate hash on insert
CREATE OR REPLACE FUNCTION calculate_evidence_hash()
RETURNS TRIGGER AS $$
BEGIN
    NEW.hash = encode(digest(NEW.event_data::TEXT, 'sha256'), 'hex');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_calculate_evidence_hash
BEFORE INSERT ON evidence
FOR EACH ROW
EXECUTE FUNCTION calculate_evidence_hash();

-- Trigger to prevent evidence modification
CREATE OR REPLACE FUNCTION prevent_evidence_modification()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Evidence is immutable and cannot be modified';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_prevent_evidence_modification
BEFORE UPDATE ON evidence
FOR EACH ROW
EXECUTE FUNCTION prevent_evidence_modification();

-- Trigger to add to evidence chain
CREATE OR REPLACE FUNCTION add_to_evidence_chain()
RETURNS TRIGGER AS $$
DECLARE
    v_last_block_hash TEXT;
BEGIN
    -- Get last block hash
    SELECT hash INTO v_last_block_hash
    FROM evidence e
    JOIN evidence_chain ec ON e.evidence_id = ec.evidence_id
    ORDER BY ec.block_number DESC
    LIMIT 1;
    
    -- Set previous_hash
    NEW.previous_hash = v_last_block_hash;
    
    -- Add to chain
    INSERT INTO evidence_chain (evidence_id, previous_block_hash)
    VALUES (NEW.evidence_id, v_last_block_hash);
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_add_to_evidence_chain
AFTER INSERT ON evidence
FOR EACH ROW
EXECUTE FUNCTION add_to_evidence_chain();

-- ============================================================================
-- SAMPLE DATA (for testing)
-- ============================================================================

-- Insert sample evidence
INSERT INTO evidence (
    activity_id,
    activity_name,
    activity_version,
    execution_id,
    agent_id,
    agent_type,
    tenant_id,
    environment,
    event_type,
    event_data,
    decision,
    outcome,
    policy_reference
) VALUES (
    gen_random_uuid(),
    'PO_Approval',
    '1.0.0',
    gen_random_uuid(),
    'agent-001',
    'SYSTEM',
    'acme-corp',
    'PROD',
    'DECIDE',
    '{"amount": 75000, "vendor": "Acme Corp", "decision": "ManagerApproval"}',
    'Amount > $50K requires manager approval',
    'ManagerApproval',
    'Procurement Policy v3.2'
);

-- Grant permissions
-- GRANT SELECT, INSERT ON evidence TO ocx_app;
-- GRANT SELECT ON ALL TABLES IN SCHEMA public TO ocx_readonly;
