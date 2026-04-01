-- Migration 003: Memory Schema
-- Creates the memory schema for vendor profiles, episodic history,
-- and semantic embeddings (pgvector).
--
-- Three tables:
--   vendor_profile_cache — cached vendor data from Salesforce
--   episodic_memory      — timeline of events per vendor/case
--   embedding_index      — 1536-dim vectors for RAG similarity search
--
-- The pgvector extension must be available in the PostgreSQL instance.
-- We use HNSW indexing for fast approximate nearest neighbor search.

-- Enable pgvector extension — required for the embedding_index table
CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS memory;

-- ============================================================
-- Table: vendor_profile_cache
-- Caches vendor data from Salesforce to avoid repeated API calls.
-- Also stored in Redis with a 1-hour TTL for hot lookups.
-- This PostgreSQL table is the persistent backing store.
-- ============================================================
CREATE TABLE IF NOT EXISTS memory.vendor_profile_cache (
    id                          BIGSERIAL       PRIMARY KEY,
    vendor_id                   VARCHAR(255)    UNIQUE NOT NULL, -- Salesforce Account ID
    vendor_name                 VARCHAR(500),
    tier                        VARCHAR(50),                    -- platinum | gold | silver | standard
    sla_hours                   INT,                            -- SLA target in hours for this tier
    risk_flags                  JSONB,                          -- Array of risk flags from Salesforce
    last_seen                   TIMESTAMP,                      -- Last email received from vendor
    last_ticket_id              VARCHAR(255),                   -- Most recent ServiceNow ticket
    interaction_count           INT             DEFAULT 0,      -- Total emails from vendor
    avg_resolution_time_hours   NUMERIC(8,2),                   -- Average resolution time
    cached_at                   TIMESTAMP       DEFAULT CURRENT_TIMESTAMP
);

-- Index: query vendors by tier for SLA reporting
CREATE INDEX IF NOT EXISTS idx_vendor_profile_cache_tier ON memory.vendor_profile_cache (tier);


-- ============================================================
-- Table: episodic_memory
-- Immutable timeline of events during case processing.
-- Agents read this to understand a vendor's history and make
-- better decisions about routing, urgency, and response tone.
-- ============================================================
CREATE TABLE IF NOT EXISTS memory.episodic_memory (
    id              BIGSERIAL       PRIMARY KEY,
    correlation_id  VARCHAR(64)     NOT NULL,           -- Links to case_execution
    vendor_id       VARCHAR(255),                       -- Salesforce Account ID
    event_type      VARCHAR(50),                        -- email_received | ticket_created | sla_warning | etc
    event_data      JSONB,                              -- Full event payload (varies by type)
    timestamp       TIMESTAMP       NOT NULL,           -- When the event occurred
    created_at      TIMESTAMP       DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for episodic_memory:
-- correlation_id: get all events for a specific case
-- vendor_id:      get all events for a specific vendor (history)
-- timestamp:      time-range queries for context windows
CREATE INDEX IF NOT EXISTS idx_episodic_memory_correlation_id ON memory.episodic_memory (correlation_id);
CREATE INDEX IF NOT EXISTS idx_episodic_memory_vendor_id      ON memory.episodic_memory (vendor_id);
CREATE INDEX IF NOT EXISTS idx_episodic_memory_timestamp      ON memory.episodic_memory (timestamp);


-- ============================================================
-- Table: embedding_index
-- Stores 1536-dimensional vectors from Amazon Bedrock for
-- semantic similarity search (RAG). Text chunks from emails,
-- tickets, and knowledge base docs are embedded and indexed here.
--
-- Uses HNSW indexing for fast approximate nearest neighbor search.
-- HNSW parameters: m=16, ef_construction=64 (from .env config).
-- ============================================================
CREATE TABLE IF NOT EXISTS memory.embedding_index (
    id              BIGSERIAL       PRIMARY KEY,
    correlation_id  VARCHAR(64),                        -- Links to source case (null for knowledge base)
    vendor_id       VARCHAR(255),                       -- Associated vendor (null for knowledge base)
    text_chunk      TEXT,                               -- The original text that was embedded
    embedding       vector(1536),                       -- 1536-dim vector from Bedrock
    created_at      TIMESTAMP       DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for embedding_index:
-- correlation_id: find embeddings for a specific case
-- HNSW index:     fast cosine similarity search across all embeddings
CREATE INDEX IF NOT EXISTS idx_embedding_index_correlation_id ON memory.embedding_index (correlation_id);
CREATE INDEX IF NOT EXISTS idx_embedding_index_hnsw
    ON memory.embedding_index
    USING hnsw (embedding vector_cosine_ops);
