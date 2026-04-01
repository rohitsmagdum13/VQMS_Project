-- Migration 001: Intake Schema
-- Creates the intake schema for storing raw email data.
--
-- Two tables:
--   email_messages    — metadata for each incoming vendor email
--   email_attachments — files attached to emails, stored in S3
--
-- This is the entry point for all data in VQMS. Every email
-- that arrives via Exchange Online gets a row in email_messages.

CREATE SCHEMA IF NOT EXISTS intake;

-- ============================================================
-- Table: email_messages
-- Stores metadata about each incoming vendor email.
-- The raw .eml file is stored in S3; this table holds
-- the parsed fields needed for pipeline processing.
-- ============================================================
CREATE TABLE IF NOT EXISTS intake.email_messages (
    id              BIGSERIAL       PRIMARY KEY,
    message_id      VARCHAR(255)    UNIQUE NOT NULL,    -- Exchange Online message ID
    correlation_id  VARCHAR(64)     NOT NULL,           -- Trace ID across the entire pipeline
    sender_email    VARCHAR(255)    NOT NULL,           -- Who sent the email
    sender_name     VARCHAR(255),                       -- Display name (may be null)
    to_address      VARCHAR(255),                       -- Primary recipient email address
    cc_addresses    TEXT,                               -- CC recipients (semicolon-separated)
    subject         VARCHAR(500)    NOT NULL,           -- Email subject line
    body_plain      TEXT,                               -- Plain text body (HTML stripped)
    received_at     TIMESTAMP       NOT NULL,           -- When Exchange Online received it
    parsed_at       TIMESTAMP,                          -- When our parser processed it
    s3_raw_path     VARCHAR(512),                       -- Path in vqms-email-raw-dev bucket
    has_attachments BOOLEAN         DEFAULT FALSE,      -- True if email has attachments
    attachment_count INTEGER        DEFAULT 0,          -- Number of attachments
    thread_id       VARCHAR(255),                       -- Graph API conversationId (groups related emails)
    is_reply        BOOLEAN         DEFAULT FALSE,      -- True if this is a reply
    is_auto_reply   BOOLEAN         DEFAULT FALSE,      -- True if auto-reply (OOO, delivery receipt)
    language        VARCHAR(10)     DEFAULT 'en',       -- ISO 639-1 language code
    status          VARCHAR(50)     DEFAULT 'INGESTED', -- Pipeline status: INGESTED → ANALYZED → ROUTED → RESOLVED
    vendor_id       VARCHAR(255),                       -- Salesforce Account ID (set after vendor resolution)
    is_duplicate    BOOLEAN         DEFAULT FALSE,      -- True if message_id was already seen
    created_at      TIMESTAMP       DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata'),
    updated_at      TIMESTAMP       DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata')
);

-- Indexes for email_messages:
-- correlation_id: trace any email through the pipeline
-- sender_email:   find all emails from a specific sender
-- received_at:    time-range queries for monitoring and reporting
CREATE INDEX IF NOT EXISTS idx_email_messages_correlation_id ON intake.email_messages (correlation_id);
CREATE INDEX IF NOT EXISTS idx_email_messages_sender_email   ON intake.email_messages (sender_email);
CREATE INDEX IF NOT EXISTS idx_email_messages_received_at    ON intake.email_messages (received_at);
CREATE INDEX IF NOT EXISTS idx_email_messages_thread_id      ON intake.email_messages (thread_id);


-- ============================================================
-- Table: email_attachments
-- Stores metadata about files attached to emails.
-- The actual files are stored in S3 (vqms-email-attachments-prod);
-- this table holds the reference and metadata.
-- ============================================================
CREATE TABLE IF NOT EXISTS intake.email_attachments (
    id              BIGSERIAL       PRIMARY KEY,
    message_id      BIGINT          NOT NULL REFERENCES intake.email_messages(id),
    filename        VARCHAR(500)    NOT NULL,           -- Original filename from email
    file_size_bytes BIGINT,                             -- Size in bytes
    mime_type       VARCHAR(100),                       -- MIME type (e.g., 'application/pdf')
    s3_path         VARCHAR(512),                       -- Path in vqms-email-attachments-prod
    created_at      TIMESTAMP       DEFAULT CURRENT_TIMESTAMP
);

-- Index: look up all attachments for a given email
CREATE INDEX IF NOT EXISTS idx_email_attachments_message_id ON intake.email_attachments (message_id);
