-- Cloud Spanner Schema for Compliance Layer
-- These tables support the additive compliance features without modifying OCX core

-- ============================================================================
-- Phase 1: Governance-as-an-Asset Ledger
-- ============================================================================

-- Immutable governance ledger with cryptographic hashing
CREATE TABLE governance_ledger (
    id STRING(36) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    transaction_id STRING(36) NOT NULL,
    agent_id STRING(255) NOT NULL,
    action STRING(1024) NOT NULL,
    policy_version STRING(36) NOT NULL,
    jury_verdict STRING(50) NOT NULL,
    entropy_score FLOAT64,
    sop_decision STRING(50),  -- SEQUESTERED, REPLAYED, SHREDDED
    pid_verified BOOL NOT NULL,
    hash STRING(64) NOT NULL,  -- SHA-256 hash of this entry
    previous_hash STRING(64) NOT NULL,  -- Hash of previous entry (blockchain-style)
) PRIMARY KEY (id);

-- Index for transaction lookup
CREATE INDEX idx_governance_ledger_tx_id ON governance_ledger(transaction_id);

-- Index for agent audit trail
CREATE INDEX idx_governance_ledger_agent_id ON governance_ledger(agent_id, timestamp DESC);

-- Index for chain verification
CREATE INDEX idx_governance_ledger_timestamp ON governance_ledger(timestamp);

-- Regulator API keys
CREATE TABLE regulator_api_keys (
    api_key STRING(64) NOT NULL,
    regulator_name STRING(255) NOT NULL,
    regulator_org STRING(255) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    last_used_at TIMESTAMP,
    is_active BOOL NOT NULL DEFAULT TRUE,
) PRIMARY KEY (api_key);

-- ============================================================================
-- Phase 2: Jury Room Decision-Support UI
-- ============================================================================

-- Policy adjustment history
CREATE TABLE policy_adjustments (
    id STRING(36) NOT NULL,
    policy_id STRING(255) NOT NULL,
    adjustment_type STRING(50) NOT NULL,  -- increase_threshold, add_exception, change_action
    old_value STRING(1024),
    new_value STRING(1024),
    reason STRING(2048),
    approved_by STRING(255) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    transaction_id STRING(36),  -- Optional: link to divergence analysis
) PRIMARY KEY (id);

-- Index for policy adjustment history
CREATE INDEX idx_policy_adjustments_policy_id ON policy_adjustments(policy_id, timestamp DESC);

-- Index for auditing who made adjustments
CREATE INDEX idx_policy_adjustments_approved_by ON policy_adjustments(approved_by, timestamp DESC);

-- Divergence analysis cache (optional - for performance)
CREATE TABLE divergence_analysis (
    transaction_id STRING(36) NOT NULL,
    analysis_data JSON NOT NULL,  -- Full divergence analysis result
    created_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP,  -- Optional TTL
) PRIMARY KEY (transaction_id);

-- ============================================================================
-- Phase 3: Shadow-SOP Discovery Engine
-- ============================================================================

-- Discovered shadow SOPs from Slack/Teams/Meetings
CREATE TABLE shadow_sops (
    id STRING(36) NOT NULL,
    rule TEXT NOT NULL,
    confidence FLOAT64 NOT NULL,
    category STRING(50),  -- procurement, security, compliance, other
    source STRING(50) NOT NULL,  -- slack, teams, meeting
    channel STRING(255),
    author STRING(255),
    original_text TEXT NOT NULL,
    suggested_logic JSON,  -- JSON-Logic representation
    suggested_action STRING(50),  -- BLOCK, WARN, ALLOW
    status STRING(50) NOT NULL,  -- pending, approved, rejected
    reviewed_by STRING(255),
    reviewed_at TIMESTAMP,
    rejection_reason TEXT,
    discovered_at TIMESTAMP NOT NULL,
) PRIMARY KEY (id);

-- Index for pending reviews
CREATE INDEX idx_shadow_sops_status ON shadow_sops(status, discovered_at DESC);

-- Index for source attribution
CREATE INDEX idx_shadow_sops_source ON shadow_sops(source, channel, discovered_at DESC);

-- Index for category filtering
CREATE INDEX idx_shadow_sops_category ON shadow_sops(category, status);

-- ============================================================================
-- Views for Reporting
-- ============================================================================

-- Governance summary view
CREATE VIEW governance_summary AS
SELECT 
    DATE(timestamp) as date,
    COUNT(*) as total_events,
    COUNTIF(jury_verdict = 'PASS') as passed_events,
    COUNTIF(jury_verdict = 'FAILURE') as failed_events,
    COUNTIF(sop_decision = 'SHREDDED') as shredded_events,
    AVG(entropy_score) as avg_entropy
FROM governance_ledger
GROUP BY DATE(timestamp);

-- Shadow SOP discovery metrics
CREATE VIEW shadow_sop_metrics AS
SELECT
    source,
    category,
    status,
    COUNT(*) as count,
    AVG(confidence) as avg_confidence
FROM shadow_sops
GROUP BY source, category, status;

-- Policy adjustment frequency
CREATE VIEW policy_adjustment_frequency AS
SELECT
    policy_id,
    adjustment_type,
    COUNT(*) as adjustment_count,
    MAX(timestamp) as last_adjusted
FROM policy_adjustments
GROUP BY policy_id, adjustment_type;

-- ============================================================================
-- Notes
-- ============================================================================

-- 1. All tables are additive - they do not modify existing OCX core tables
-- 2. Indexes are optimized for common query patterns
-- 3. JSON columns allow flexible schema evolution
-- 4. Timestamps use UTC for consistency
-- 5. Consider adding TTL policies for governance_ledger if storage is a concern
