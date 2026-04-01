-- Migration 005: Reporting Schema
-- Creates the reporting schema for SLA metrics and dashboards.
--
-- One table:
--   sla_metrics — tracks SLA compliance for each case
--
-- This table is populated after a case is resolved (or during
-- active monitoring). It drives SLA compliance reports and
-- vendor performance dashboards.

CREATE SCHEMA IF NOT EXISTS reporting;

-- ============================================================
-- Table: sla_metrics
-- Tracks SLA performance for each case.
-- Populated by the SLA Alerting Service and updated when
-- a case receives its first response or is fully resolved.
-- ============================================================
CREATE TABLE IF NOT EXISTS reporting.sla_metrics (
    id                              BIGSERIAL       PRIMARY KEY,
    case_id                         BIGINT          REFERENCES workflow.case_execution(id),
    ticket_id                       VARCHAR(255),                   -- ServiceNow ticket number
    vendor_id                       VARCHAR(255),                   -- Salesforce Account ID
    vendor_tier                     VARCHAR(50),                    -- platinum | gold | silver | standard
    sla_hours                       INT,                            -- SLA target in hours for this tier
    created_at                      TIMESTAMP,                      -- When the case was created
    first_response_at               TIMESTAMP,                      -- When vendor got first response
    resolved_at                     TIMESTAMP,                      -- When the case was fully resolved
    time_to_first_response_minutes  INT,                            -- Minutes from created to first response
    time_to_resolution_minutes      INT,                            -- Minutes from created to resolution
    sla_met                         BOOLEAN,                        -- True if resolved within sla_hours
    escalations                     INT                             -- Number of escalations during this case
);

-- Indexes for sla_metrics:
-- vendor_tier: aggregate SLA compliance by tier
-- created_at:  time-range queries for reporting periods
CREATE INDEX IF NOT EXISTS idx_sla_metrics_vendor_tier ON reporting.sla_metrics (vendor_tier);
CREATE INDEX IF NOT EXISTS idx_sla_metrics_created_at  ON reporting.sla_metrics (created_at);
