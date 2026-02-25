-- =============================================================================
-- Migration: Add Execution Context (process_id, run_id, step_id) to all
-- governance tables. Every patent feature that fires during a process run
-- creates a record traceable back to the specific execution.
--
-- OCX doesn't call agents. Agents call OCX. OCX enforces the entire patent
-- stack. Every enforcement record carries the execution context.
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- PART A: Add execution context columns to existing tables
-- ─────────────────────────────────────────────────────────────────────────────

-- Tri-Factor Gate verdicts (Patent Claim 2/5)
ALTER TABLE verdicts ADD COLUMN IF NOT EXISTS process_id UUID;
ALTER TABLE verdicts ADD COLUMN IF NOT EXISTS run_id UUID;
ALTER TABLE verdicts ADD COLUMN IF NOT EXISTS step_id UUID;
CREATE INDEX IF NOT EXISTS idx_verdicts_run ON verdicts(run_id);
CREATE INDEX IF NOT EXISTS idx_verdicts_process ON verdicts(process_id);

-- Evidence Vault records (Patent Claim 6)
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS process_id UUID;
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS run_id UUID;
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS step_id UUID;
CREATE INDEX IF NOT EXISTS idx_evidence_run ON evidence(run_id);
CREATE INDEX IF NOT EXISTS idx_evidence_process ON evidence(process_id);

-- Session Audit Log (Security Forensics)
ALTER TABLE session_audit_log ADD COLUMN IF NOT EXISTS process_id UUID;
ALTER TABLE session_audit_log ADD COLUMN IF NOT EXISTS run_id UUID;
ALTER TABLE session_audit_log ADD COLUMN IF NOT EXISTS step_id UUID;
CREATE INDEX IF NOT EXISTS idx_sal_run ON session_audit_log(run_id);
CREATE INDEX IF NOT EXISTS idx_sal_process ON session_audit_log(process_id);

-- Governance Ledger / Hash Chain (Patent Claim 6)
ALTER TABLE governance_ledger ADD COLUMN IF NOT EXISTS process_id UUID;
ALTER TABLE governance_ledger ADD COLUMN IF NOT EXISTS run_id UUID;
ALTER TABLE governance_ledger ADD COLUMN IF NOT EXISTS step_id UUID;
CREATE INDEX IF NOT EXISTS idx_governance_ledger_run ON governance_ledger(run_id);

-- Billing Transactions (Trust Tax)
ALTER TABLE billing_transactions ADD COLUMN IF NOT EXISTS process_id UUID;
ALTER TABLE billing_transactions ADD COLUMN IF NOT EXISTS run_id UUID;
ALTER TABLE billing_transactions ADD COLUMN IF NOT EXISTS step_id UUID;
CREATE INDEX IF NOT EXISTS idx_billing_run ON billing_transactions(run_id);

-- Sandbox Executions (Patent Claim 1 — Speculative Execution)
ALTER TABLE sandbox_executions ADD COLUMN IF NOT EXISTS process_id UUID;
ALTER TABLE sandbox_executions ADD COLUMN IF NOT EXISTS run_id UUID;
ALTER TABLE sandbox_executions ADD COLUMN IF NOT EXISTS step_id UUID;
CREATE INDEX IF NOT EXISTS idx_sandbox_exec_run ON sandbox_executions(run_id);

-- JIT Entitlements (Patent §4.3)
ALTER TABLE jit_entitlements ADD COLUMN IF NOT EXISTS process_id UUID;
ALTER TABLE jit_entitlements ADD COLUMN IF NOT EXISTS run_id UUID;
ALTER TABLE jit_entitlements ADD COLUMN IF NOT EXISTS step_id UUID;
CREATE INDEX IF NOT EXISTS idx_jit_ent_run ON jit_entitlements(run_id);

-- Quarantine Records (Escrow)
ALTER TABLE quarantine_records ADD COLUMN IF NOT EXISTS process_id UUID;
ALTER TABLE quarantine_records ADD COLUMN IF NOT EXISTS run_id UUID;
CREATE INDEX IF NOT EXISTS idx_quarantine_run ON quarantine_records(run_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- PART B: Create new tables for patent features that had no DB persistence
-- ─────────────────────────────────────────────────────────────────────────────

-- eBPF Classification Events (Patent Claim 1 — Class A/B Triage)
CREATE TABLE IF NOT EXISTS classification_events (
    event_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     UUID NOT NULL REFERENCES tenants(tenant_id),
    agent_id      UUID REFERENCES agents(agent_id),
    process_id    UUID,
    run_id        UUID,
    step_id       UUID,
    transaction_id TEXT,
    tool_name     TEXT NOT NULL,
    action_class  TEXT NOT NULL,
    CHECK (action_class IN ('CLASS_A', 'CLASS_B')),
    trust_score   FLOAT,
    entitlements  JSONB DEFAULT '[]',
    final_verdict TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_class_evt_tenant ON classification_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_class_evt_agent ON classification_events(agent_id);
CREATE INDEX IF NOT EXISTS idx_class_evt_run ON classification_events(run_id);
CREATE INDEX IF NOT EXISTS idx_class_evt_process ON classification_events(process_id);
CREATE INDEX IF NOT EXISTS idx_class_evt_created ON classification_events(created_at DESC);

ALTER TABLE classification_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role has full access to classification_events"
    ON classification_events FOR ALL USING (auth.role() = 'service_role');


-- Shannon Entropy Events (Patent Claim 3 — Signal Analysis)
CREATE TABLE IF NOT EXISTS entropy_events (
    event_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(tenant_id),
    agent_id        UUID REFERENCES agents(agent_id),
    process_id      UUID,
    run_id          UUID,
    step_id         UUID,
    transaction_id  TEXT,
    entropy_score   FLOAT,
    jitter_ms       FLOAT,
    anomaly_detected BOOLEAN DEFAULT FALSE,
    analysis_type   TEXT DEFAULT 'SIGNAL',
    CHECK (analysis_type IN ('SIGNAL', 'TEMPORAL', 'COMPRESSION', 'SEMANTIC')),
    details         JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_entropy_evt_tenant ON entropy_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_entropy_evt_agent ON entropy_events(agent_id);
CREATE INDEX IF NOT EXISTS idx_entropy_evt_run ON entropy_events(run_id);
CREATE INDEX IF NOT EXISTS idx_entropy_evt_created ON entropy_events(created_at DESC);

ALTER TABLE entropy_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role has full access to entropy_events"
    ON entropy_events FOR ALL USING (auth.role() = 'service_role');


-- Ghost State Simulation Events (Patent Claim 9 — Speculative State)
CREATE TABLE IF NOT EXISTS ghost_state_events (
    event_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(tenant_id),
    agent_id        UUID REFERENCES agents(agent_id),
    process_id      UUID,
    run_id          UUID,
    step_id         UUID,
    transaction_id  TEXT NOT NULL,
    tool_name       TEXT,
    state_hash      TEXT,
    policy_passed   BOOLEAN,
    violations      JSONB DEFAULT '[]',
    side_effect_count INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ghost_evt_tenant ON ghost_state_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_ghost_evt_run ON ghost_state_events(run_id);
CREATE INDEX IF NOT EXISTS idx_ghost_evt_created ON ghost_state_events(created_at DESC);

ALTER TABLE ghost_state_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role has full access to ghost_state_events"
    ON ghost_state_events FOR ALL USING (auth.role() = 'service_role');


-- SOP Drift Detection Events (Patent Claim 13)
CREATE TABLE IF NOT EXISTS sop_drift_events (
    event_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             UUID NOT NULL REFERENCES tenants(tenant_id),
    agent_id              UUID REFERENCES agents(agent_id),
    process_id            UUID,
    run_id                UUID,
    step_id               UUID,
    transaction_id        TEXT,
    graph_id              TEXT,
    path_edit_distance    FLOAT,
    normalized_distance   FLOAT,
    policy_violation_count INTEGER DEFAULT 0,
    governance_tax_adj    FLOAT DEFAULT 1.0,
    missing_steps         JSONB DEFAULT '[]',
    extra_steps           JSONB DEFAULT '[]',
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sop_drift_evt_tenant ON sop_drift_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_sop_drift_evt_run ON sop_drift_events(run_id);
CREATE INDEX IF NOT EXISTS idx_sop_drift_evt_created ON sop_drift_events(created_at DESC);

ALTER TABLE sop_drift_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role has full access to sop_drift_events"
    ON sop_drift_events FOR ALL USING (auth.role() = 'service_role');


-- CAE Continuous Assessment Events (Patent Claim 8)
CREATE TABLE IF NOT EXISTS cae_events (
    event_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     UUID NOT NULL REFERENCES tenants(tenant_id),
    agent_id      UUID REFERENCES agents(agent_id),
    process_id    UUID,
    run_id        UUID,
    step_id       UUID,
    token_id      TEXT,
    trust_score   FLOAT,
    drift_score   FLOAT,
    action_taken  TEXT DEFAULT 'MONITOR',
    CHECK (action_taken IN ('MONITOR', 'WARNING', 'REVOKE', 'BLOCK')),
    details       JSONB DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cae_evt_tenant ON cae_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_cae_evt_agent ON cae_events(agent_id);
CREATE INDEX IF NOT EXISTS idx_cae_evt_run ON cae_events(run_id);
CREATE INDEX IF NOT EXISTS idx_cae_evt_created ON cae_events(created_at DESC);

ALTER TABLE cae_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role has full access to cae_events"
    ON cae_events FOR ALL USING (auth.role() = 'service_role');


-- JIT Token Broker Events (Patent Claim 7)
CREATE TABLE IF NOT EXISTS token_events (
    event_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     UUID NOT NULL REFERENCES tenants(tenant_id),
    agent_id      UUID REFERENCES agents(agent_id),
    process_id    UUID,
    run_id        UUID,
    step_id       UUID,
    token_id      TEXT NOT NULL,
    permission    TEXT,
    trust_score   FLOAT,
    attribution   TEXT,
    expires_at    TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_token_evt_tenant ON token_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_token_evt_agent ON token_events(agent_id);
CREATE INDEX IF NOT EXISTS idx_token_evt_run ON token_events(run_id);
CREATE INDEX IF NOT EXISTS idx_token_evt_created ON token_events(created_at DESC);

ALTER TABLE token_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role has full access to token_events"
    ON token_events FOR ALL USING (auth.role() = 'service_role');
