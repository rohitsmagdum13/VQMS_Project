-- Migration 004: Audit Schema
-- Creates the audit schema for compliance logging and validation tracking.
--
-- Two tables:
--   action_log         — every side-effect in VQMS is logged here
--   validation_results — results from Quality Gate checks on drafts
--
-- The audit trail is a compliance requirement. Every action that
-- changes state (email stored, ticket created, draft sent, etc.)
-- must have a corresponding row in action_log.

CREATE SCHEMA IF NOT EXISTS audit;

-- ============================================================
-- Table: action_log
-- Immutable audit trail for every action in the VQMS pipeline.
-- Each row records: what happened, who did it, what resource
-- was affected, and whether it succeeded or failed.
-- ============================================================
CREATE TABLE IF NOT EXISTS audit.action_log (
    id              BIGSERIAL       PRIMARY KEY,
    correlation_id  VARCHAR(64),                        -- Trace ID (links to case_execution)
    action          VARCHAR(100),                       -- What happened: email_stored | analysis_completed | ticket_created | draft_sent | etc
    actor           VARCHAR(255),                       -- Who did it: service name or agent name
    resource_id     VARCHAR(255),                       -- What was affected: message_id, ticket_id, case_id, etc
    status          VARCHAR(50),                        -- Outcome: success | failure
    error_message   TEXT,                               -- Error details (null on success)
    metadata        JSONB,                              -- Additional context (varies by action)
    timestamp       TIMESTAMP       DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for action_log:
-- correlation_id: get the full audit trail for a case
-- actor:          find all actions by a specific service/agent
-- timestamp:      time-range queries for compliance reporting
CREATE INDEX IF NOT EXISTS idx_action_log_correlation_id ON audit.action_log (correlation_id);
CREATE INDEX IF NOT EXISTS idx_action_log_actor          ON audit.action_log (actor);
CREATE INDEX IF NOT EXISTS idx_action_log_timestamp      ON audit.action_log (timestamp);


-- ============================================================
-- Table: validation_results
-- Records the outcome of each Quality Gate check on a draft.
-- Four check types: ticket_number, sla_wording, pii_check,
-- template_check. Each gets its own row per validation run.
-- ============================================================
CREATE TABLE IF NOT EXISTS audit.validation_results (
    id                  BIGSERIAL       PRIMARY KEY,
    case_id             BIGINT          REFERENCES workflow.case_execution(id),
    validation_type     VARCHAR(50),                    -- ticket_number | sla_wording | pii_check | template_check
    is_valid            BOOLEAN,                        -- True if this check passed
    details             JSONB,                          -- Check-specific details (e.g., PII types found)
    checked_at          TIMESTAMP       DEFAULT CURRENT_TIMESTAMP
);

-- Index: find all validation results for a case
CREATE INDEX IF NOT EXISTS idx_validation_results_case_id ON audit.validation_results (case_id);
