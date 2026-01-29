-- Cloud Spanner Schema: Trust Attestation Ledger
-- Multi-region, globally distributed trust verification

CREATE TABLE trust_attestations (
    attestation_id STRING(36) NOT NULL,
    ocx_instance_id STRING(255) NOT NULL,
    agent_id STRING(255) NOT NULL,
    audit_hash STRING(64) NOT NULL,  -- SHA-256 of audit result
    timestamp TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
    trust_level FLOAT64 NOT NULL,
    signature STRING(512) NOT NULL,  -- SPIFFE signature
    expires_at TIMESTAMP NOT NULL,
) PRIMARY KEY (attestation_id);

-- Global secondary index for fast agent lookup
CREATE INDEX idx_trust_agent_id ON trust_attestations(agent_id, timestamp DESC);

-- Index for OCX instance queries
CREATE INDEX idx_trust_instance ON trust_attestations(ocx_instance_id, timestamp DESC);

-- Index for cleanup of expired attestations
CREATE INDEX idx_trust_expires ON trust_attestations(expires_at);

-- Federation nodes table
CREATE TABLE federation_nodes (
    node_id STRING(36) NOT NULL,
    instance_id STRING(255) NOT NULL,
    organization STRING(255) NOT NULL,
    region STRING(50) NOT NULL,
    trust_domain STRING(255) NOT NULL,
    subscription_tier STRING(50) NOT NULL,  -- 'regional', 'global', 'authority'
    created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
    last_heartbeat TIMESTAMP NOT NULL,
    status STRING(20) NOT NULL,  -- 'active', 'inactive', 'suspended'
) PRIMARY KEY (node_id);

-- Index for organization queries
CREATE INDEX idx_federation_org ON federation_nodes(organization, status);

-- Trust tax transactions table
CREATE TABLE trust_tax_transactions (
    transaction_id STRING(36) NOT NULL,
    local_ocx STRING(255) NOT NULL,
    remote_ocx STRING(255) NOT NULL,
    agent_id STRING(255) NOT NULL,
    trust_level FLOAT64 NOT NULL,
    base_fee_usd FLOAT64 NOT NULL,
    dynamic_fee_usd FLOAT64 NOT NULL,  -- base_fee * (1.0 / trust_level)
    timestamp TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
    billing_month STRING(7) NOT NULL,  -- 'YYYY-MM' for aggregation
) PRIMARY KEY (transaction_id);

-- Index for billing aggregation
CREATE INDEX idx_trust_tax_billing ON trust_tax_transactions(local_ocx, billing_month);

-- Index for analytics
CREATE INDEX idx_trust_tax_agent ON trust_tax_transactions(agent_id, timestamp DESC);

-- Monthly billing aggregates (materialized view)
CREATE TABLE trust_tax_monthly_bills (
    bill_id STRING(36) NOT NULL,
    ocx_instance_id STRING(255) NOT NULL,
    billing_month STRING(7) NOT NULL,
    total_transactions INT64 NOT NULL,
    total_fee_usd FLOAT64 NOT NULL,
    avg_trust_level FLOAT64 NOT NULL,
    created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
    paid BOOL NOT NULL DEFAULT (false),
    paid_at TIMESTAMP,
) PRIMARY KEY (bill_id);

-- Unique constraint on instance + month
CREATE UNIQUE INDEX idx_monthly_bill_unique ON trust_tax_monthly_bills(ocx_instance_id, billing_month);
