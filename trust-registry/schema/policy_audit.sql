-- Cloud Spanner DDL: Policy Audit Logging Schema
-- Tracks all policy evaluations for compliance and debugging

-- Main table for policy audit logs
CREATE TABLE PolicyAudits (
    AuditID STRING(36) NOT NULL,
    PolicyID STRING(36) NOT NULL,
    AgentID STRING(36),
    TriggerIntent STRING(255) NOT NULL,
    Tier STRING(20) NOT NULL,  -- GLOBAL, CONTEXTUAL, DYNAMIC
    Violated BOOL NOT NULL,
    Action STRING(50) NOT NULL,  -- BLOCK, ALLOW, INTERCEPT_AND_ESCALATE, etc.
    DataPayload JSON,  -- The data that was evaluated
    EvaluationTimeMs FLOAT64,  -- Time taken to evaluate (milliseconds)
    Timestamp TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
) PRIMARY KEY (AuditID);

-- Index for querying by policy
CREATE INDEX IndexAuditsByPolicy ON PolicyAudits(PolicyID, Timestamp DESC);

-- Index for querying by agent
CREATE INDEX IndexAuditsByAgent ON PolicyAudits(AgentID, Timestamp DESC);

-- Index for querying violations
CREATE INDEX IndexAuditsByViolation ON PolicyAudits(Violated, Timestamp DESC) WHERE Violated = TRUE;

-- Index for querying by tier
CREATE INDEX IndexAuditsByTier ON PolicyAudits(Tier, Timestamp DESC);

-- Table for policy metadata and versioning
CREATE TABLE Policies (
    PolicyID STRING(36) NOT NULL,
    Version INT64 NOT NULL,
    Tier STRING(20) NOT NULL,
    TriggerIntent STRING(255) NOT NULL,
    Logic JSON NOT NULL,
    Action JSON NOT NULL,
    Confidence FLOAT64 NOT NULL,
    SourceName STRING(255) NOT NULL,
    Roles ARRAY<STRING(MAX)>,  -- For CONTEXTUAL tier
    ExpiresAt TIMESTAMP,  -- For DYNAMIC tier
    IsActive BOOL NOT NULL DEFAULT TRUE,
    CreatedAt TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
    UpdatedAt TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
) PRIMARY KEY (PolicyID, Version);

-- Index for active policies
CREATE INDEX IndexActivePolicies ON Policies(IsActive, Tier, TriggerIntent) WHERE IsActive = TRUE;

-- Index for expiring policies
CREATE INDEX IndexExpiringPolicies ON Policies(ExpiresAt) WHERE ExpiresAt IS NOT NULL;

-- Table for policy extraction history (from APE Engine)
CREATE TABLE PolicyExtractions (
    ExtractionID STRING(36) NOT NULL,
    SourceName STRING(255) NOT NULL,
    DocumentHash STRING(64) NOT NULL,  -- SHA-256 of source document
    PoliciesExtracted INT64 NOT NULL,
    AvgConfidence FLOAT64,
    ModelUsed STRING(100) NOT NULL,  -- e.g., "mistralai/Mistral-7B-Instruct-v0.2"
    ExtractionTimeMs FLOAT64,
    ExtractedAt TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
) PRIMARY KEY (ExtractionID);

-- Index for querying by source
CREATE INDEX IndexExtractionsBySource ON PolicyExtractions(SourceName, ExtractedAt DESC);

-- Table for compliance reporting
CREATE TABLE ComplianceReports (
    ReportID STRING(36) NOT NULL,
    ReportType STRING(50) NOT NULL,  -- DAILY, WEEKLY, MONTHLY, AUDIT
    StartTime TIMESTAMP NOT NULL,
    EndTime TIMESTAMP NOT NULL,
    TotalEvaluations INT64 NOT NULL,
    TotalViolations INT64 NOT NULL,
    ViolationRate FLOAT64 NOT NULL,
    TopViolatedPolicies ARRAY<STRING(36)>,
    TopViolatingAgents ARRAY<STRING(36)>,
    GeneratedAt TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
) PRIMARY KEY (ReportID);

-- Index for querying reports by type
CREATE INDEX IndexReportsByType ON ComplianceReports(ReportType, GeneratedAt DESC);
