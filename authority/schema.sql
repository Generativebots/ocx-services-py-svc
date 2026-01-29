-- Authority Discovery Database Schema

-- Authority gaps detected by scanner
CREATE TABLE authority_gaps (
    gap_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL,
    document_source TEXT NOT NULL,
    gap_type VARCHAR(50) NOT NULL, -- 'Authority Fragmented', 'Accountability Ambiguous', 'Execution Decoupled'
    severity VARCHAR(20) NOT NULL, -- 'HIGH', 'MEDIUM', 'LOW'
    decision_point TEXT NOT NULL,
    current_authority_holder TEXT,
    execution_system TEXT,
    accountability_gap TEXT,
    override_frequency INT,
    time_sensitivity VARCHAR(20), -- 'seconds', 'minutes', 'hours', 'days'
    a2a_candidacy_score FLOAT, -- 0.0 - 1.0
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'PENDING' -- 'PENDING', 'REVIEWED', 'CONVERTED', 'DISMISSED'
);

CREATE INDEX idx_authority_gaps_company ON authority_gaps(company_id);
CREATE INDEX idx_authority_gaps_status ON authority_gaps(status);
CREATE INDEX idx_authority_gaps_severity ON authority_gaps(severity);

-- Parsed documents
CREATE TABLE parsed_documents (
    doc_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL,
    doc_type VARCHAR(50) NOT NULL, -- 'BPMN', 'SOP', 'RACI', 'INCIDENT_LOG', 'APPROVAL_WORKFLOW', 'AUDIT'
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_size BIGINT NOT NULL,
    parsed_entities JSONB NOT NULL,
    gaps_found INT DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_parsed_documents_company ON parsed_documents(company_id);
CREATE INDEX idx_parsed_documents_type ON parsed_documents(doc_type);

-- A2A use cases
CREATE TABLE a2a_use_cases (
    use_case_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL,
    gap_id UUID REFERENCES authority_gaps(gap_id),
    pattern_type VARCHAR(50) NOT NULL, -- 'Arbitration', 'Escalation', 'Verification', 'Enforcement', 'Recovery'
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    agents_involved JSONB NOT NULL, -- [{name, role, type}]
    current_problem TEXT NOT NULL,
    ocx_proposal TEXT NOT NULL,
    authority_contract_id UUID,
    estimated_impact JSONB, -- {cost_reduction, risk_reduction, time_saved}
    status VARCHAR(20) DEFAULT 'PROPOSED', -- 'PROPOSED', 'SIMULATED', 'APPROVED', 'DEPLOYED', 'REJECTED'
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_a2a_use_cases_company ON a2a_use_cases(company_id);
CREATE INDEX idx_a2a_use_cases_pattern ON a2a_use_cases(pattern_type);
CREATE INDEX idx_a2a_use_cases_status ON a2a_use_cases(status);

-- Authority contracts
CREATE TABLE authority_contracts (
    contract_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    use_case_id UUID REFERENCES a2a_use_cases(use_case_id),
    company_id UUID NOT NULL,
    contract_yaml TEXT NOT NULL,
    contract_version VARCHAR(10) NOT NULL DEFAULT '1.0',
    agents JSONB NOT NULL, -- [{agent_id, role, spiffe_id}]
    decision_point JSONB NOT NULL,
    authority_rules JSONB NOT NULL,
    enforcement JSONB NOT NULL,
    audit_config JSONB NOT NULL,
    status VARCHAR(20) DEFAULT 'DRAFT', -- 'DRAFT', 'VALIDATED', 'ACTIVE', 'SUSPENDED', 'ARCHIVED'
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    deployed_at TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_authority_contracts_company ON authority_contracts(company_id);
CREATE INDEX idx_authority_contracts_status ON authority_contracts(status);
CREATE INDEX idx_authority_contracts_use_case ON authority_contracts(use_case_id);

-- Simulation results
CREATE TABLE simulation_results (
    simulation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    use_case_id UUID REFERENCES a2a_use_cases(use_case_id),
    contract_id UUID REFERENCES authority_contracts(contract_id),
    company_id UUID NOT NULL,
    scenario JSONB NOT NULL, -- {agent_actions: [...]}
    verdict VARCHAR(20) NOT NULL, -- 'APPROVED', 'REJECTED', 'ESCALATED'
    authority_flow JSONB NOT NULL, -- [step1, step2, ...]
    final_decision TEXT NOT NULL,
    execution_time_ms INT NOT NULL,
    jury_verdict JSONB,
    entropy_score FLOAT,
    compliance_passed BOOLEAN,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_simulation_results_use_case ON simulation_results(use_case_id);
CREATE INDEX idx_simulation_results_company ON simulation_results(company_id);

-- Business impact estimates
CREATE TABLE business_impact_estimates (
    estimate_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    use_case_id UUID REFERENCES a2a_use_cases(use_case_id),
    company_id UUID NOT NULL,
    current_monthly_cost NUMERIC(12, 2) NOT NULL,
    a2a_monthly_savings NUMERIC(12, 2) NOT NULL,
    net_monthly_savings NUMERIC(12, 2) NOT NULL,
    annual_roi FLOAT NOT NULL,
    payback_period_months FLOAT NOT NULL,
    assumptions JSONB NOT NULL, -- {hourly_rate, error_cost, etc.}
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_business_impact_use_case ON business_impact_estimates(use_case_id);
