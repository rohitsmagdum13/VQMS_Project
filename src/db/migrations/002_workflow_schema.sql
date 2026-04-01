-- Migration 002: Workflow Schema
-- Creates the workflow schema for tracking case execution state.
--
-- Three tables:
--   case_execution   — the central tracking record for each email case
--   ticket_link      — links cases to ServiceNow tickets
--   routing_decision — records the orchestration agent's routing choices
--
-- Every incoming email creates one case_execution row. As the case
-- moves through the pipeline, the row accumulates results from each stage.

CREATE SCHEMA IF NOT EXISTS workflow;

-- ============================================================
-- Table: case_execution
-- Central tracking object for the entire VQMS pipeline.
-- Each incoming email creates one row. JSONB columns store
-- structured results from each pipeline stage.
-- ============================================================
CREATE TABLE IF NOT EXISTS workflow.case_execution (
    id                  BIGSERIAL       PRIMARY KEY,
    correlation_id      VARCHAR(64)     UNIQUE NOT NULL,    -- Same trace ID as email_messages
    message_id          BIGINT          REFERENCES intake.email_messages(id),
    workflow_state      VARCHAR(50),                        -- pending | analyzing | routing | drafting | validating | sending | closed | reopened
    analysis_result     JSONB,                              -- Output from Email Analysis Agent
    vendor_match        JSONB,                              -- Output from Vendor Resolution Service
    routing_decision    JSONB,                              -- Output from Orchestration Agent
    draft_package       JSONB,                              -- Output from Communication Drafting Agent
    validation_report   JSONB,                              -- Output from Quality Gate
    ticket_id           VARCHAR(255),                       -- ServiceNow ticket ID
    assigned_group      VARCHAR(255),                       -- ServiceNow assignment group
    escalation_count    INT             DEFAULT 0,          -- Number of escalations
    is_human_review     BOOLEAN         DEFAULT FALSE,      -- True if routed to human review
    closed_at           TIMESTAMP,                          -- When the case was resolved
    created_at          TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP       DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for case_execution:
-- workflow_state: find all cases in a given state (e.g., for dashboards)
-- ticket_id:     look up a case by its ServiceNow ticket
-- updated_at:    find recently updated cases for monitoring
CREATE INDEX IF NOT EXISTS idx_case_execution_workflow_state ON workflow.case_execution (workflow_state);
CREATE INDEX IF NOT EXISTS idx_case_execution_ticket_id      ON workflow.case_execution (ticket_id);
CREATE INDEX IF NOT EXISTS idx_case_execution_updated_at     ON workflow.case_execution (updated_at);


-- ============================================================
-- Table: ticket_link
-- Associates cases with ServiceNow tickets.
-- A case can have multiple tickets, but only one is primary.
-- The primary ticket is referenced in vendor communications.
-- ============================================================
CREATE TABLE IF NOT EXISTS workflow.ticket_link (
    id              BIGSERIAL       PRIMARY KEY,
    case_id         BIGINT          NOT NULL REFERENCES workflow.case_execution(id),
    ticket_id       VARCHAR(255)    NOT NULL,               -- ServiceNow ticket number
    ticket_url      VARCHAR(512),                           -- Full URL to ServiceNow ticket
    linked_at       TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    is_primary      BOOLEAN         DEFAULT TRUE            -- Only one primary per case
);

-- Indexes for ticket_link:
-- case_id:   find all tickets for a case
-- ticket_id: find which case a ticket belongs to
CREATE INDEX IF NOT EXISTS idx_ticket_link_case_id   ON workflow.ticket_link (case_id);
CREATE INDEX IF NOT EXISTS idx_ticket_link_ticket_id ON workflow.ticket_link (ticket_id);

-- Enforce: only one primary ticket per case
-- Uses a partial unique index so multiple non-primary links are allowed
CREATE UNIQUE INDEX IF NOT EXISTS idx_ticket_link_primary
    ON workflow.ticket_link (case_id)
    WHERE is_primary = TRUE;


-- ============================================================
-- Table: routing_decision
-- Records each routing decision made by the Orchestration Agent.
-- Kept as a separate table (not just JSONB in case_execution)
-- so we can query routing patterns across all cases.
-- ============================================================
CREATE TABLE IF NOT EXISTS workflow.routing_decision (
    id                  BIGSERIAL       PRIMARY KEY,
    case_id             BIGINT          NOT NULL REFERENCES workflow.case_execution(id),
    decision_type       VARCHAR(50),                        -- auto | human_review | escalate | reopen | new_ticket
    confidence_score    NUMERIC(3,2),                       -- 0.00 to 1.00
    reason              TEXT,                               -- Why this decision was made
    decided_at          TIMESTAMP       DEFAULT CURRENT_TIMESTAMP
);

-- Index: find all routing decisions for a case
CREATE INDEX IF NOT EXISTS idx_routing_decision_case_id ON workflow.routing_decision (case_id);
