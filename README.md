# VQMS - Vendor Query Management System

VQMS automates vendor email handling for Hexaware Technologies. When a vendor sends an email (invoice question, status request, complaint), the system picks it up from Exchange Online, figures out who sent it, creates or updates a ServiceNow ticket, drafts a response, and sends it back. Less manual triage, faster vendor responses.

The system uses AI agents (Claude 3.5 Sonnet via Amazon Bedrock) to read emails, extract intent, and draft responses. Deterministic services handle the rest: looking up vendors in Salesforce, managing tickets in ServiceNow, and tracking SLA deadlines.

This is an internal tool. There is no user-facing frontend. The value is in the backend pipeline.

## Current status

**Phases 1 and 2 are complete. Phase 3 is next.**

Phase 1 built the foundation: all data models, database schemas, Redis key helpers, config files, and utility functions. Phase 2 built the email ingestion pipeline end-to-end, from fetching an email via Microsoft Graph API through storing it in S3 and PostgreSQL, publishing events, and queuing it for analysis.

83 tests, all passing. Linting clean.

The AI agents, Salesforce/ServiceNow integrations, and the LangGraph orchestration pipeline are not built yet. Those come in Phases 3-10.

## Tech stack

| Technology | What it does here |
|---|---|
| Python 3.12+ | Everything is Python. Async throughout with `asyncio`/`await`. |
| uv | Package manager. Replaces pip. Faster, handles virtual envs. |
| FastAPI | Web framework for the API layer (stubbed, not wired up yet). |
| Pydantic v2 | Data validation. Every piece of data flowing through the pipeline has a Pydantic model. |
| Amazon Bedrock | Hosts Claude 3.5 Sonnet. All LLM calls go through a single adapter. |
| LangGraph | Will run the multi-agent orchestration. Not implemented yet. |
| PostgreSQL | Primary database. 5 schemas, 11 tables. Stores emails, cases, audit logs, SLA metrics. |
| pgvector | PostgreSQL extension for vector similarity search. Used for semantic memory (RAG). |
| Redis | Fast cache. Deduplication keys, vendor profile caching, workflow state, SLA tracking. |
| Microsoft Graph API | Fetches emails from Exchange Online. OAuth 2.0 client credentials flow via MSAL. |
| Salesforce | Vendor lookup. Match email sender to a Salesforce account. Not implemented yet. |
| ServiceNow | Ticket management. Create/update/reopen tickets. Not implemented yet. |
| boto3 | AWS SDK. Used for S3, SQS, EventBridge, and Bedrock calls. |
| S3 | Stores raw emails and attachments. 4 buckets. |
| SQS | Message queues between services. 10 queues plus a dead letter queue. |
| EventBridge | Event bus. 17 event types published as emails flow through the pipeline. |
| ruff | Linter. Configured in `.ruff.toml`. |
| pytest | Test framework. All tests in `tests/`. |
| moto | Mocks AWS services in tests so we don't hit real AWS. |
| structlog | Structured JSON logging. Every log line includes correlation IDs. |

## Project structure

```
vqms/
├── main.py                          # Entry point (stub - server setup pending)
├── pyproject.toml                   # Dependencies and project config (uv)
├── .python-version                  # 3.12
├── .env.copy                        # Environment variable template (copy to .env)
├── .ruff.toml                       # Linter config
├── .gitignore
├── CLAUDE.md                        # AI assistant rules and project reference
├── README.md                        # You are here
│
├── tasks/
│   ├── todo.md                      # Phase tracker with checkboxes
│   └── lessons.md                   # Mistakes and corrections log
│
├── docs/
│   └── references/                  # DO NOT EDIT these files
│       ├── GenAI_AgenticAI_Coding_Standards_Full_transcription.md
│       └── VQMS_Complete_Architecture_and_Flows.docx
│
├── config/
│   ├── agents_config.yaml           # Agent names, models, prompt paths, thresholds
│   ├── database_config.yaml         # PostgreSQL and Redis connection structure
│   ├── model_config.yaml            # Bedrock model IDs, token limits, temperature
│   ├── logging_config.yaml          # Structured logging format and fields
│   ├── tools_config.yaml            # Agent tool access policies and budgets
│   ├── dev_config.yaml              # Development environment overrides
│   ├── test_config.yaml             # Test environment overrides
│   └── prod_config.yaml             # Production environment settings
│
├── src/
│   ├── models/                      # Pydantic data models (20 models across 8 files)
│   │   ├── email.py                 # EmailAttachment, EmailMessage, ParsedEmailPayload
│   │   ├── vendor.py                # VendorTier, VendorMatch, VendorProfile
│   │   ├── ticket.py                # TicketRecord, TicketLink, RoutingDecision
│   │   ├── workflow.py              # WorkflowState, AnalysisResult, CaseExecution
│   │   ├── communication.py         # DraftEmailPackage, ValidationReport
│   │   ├── memory.py                # EpisodicMemory, VendorProfileCache, EmbeddingRecord
│   │   ├── messages.py              # AgentMessage, ToolCall
│   │   └── budget.py                # Budget dataclass (token and cost tracking)
│   │
│   ├── db/
│   │   ├── connection.py            # Async PostgreSQL connection pool (asyncpg)
│   │   └── migrations/
│   │       ├── 001_intake_schema.sql       # intake.email_messages, intake.email_attachments
│   │       ├── 002_workflow_schema.sql     # workflow.case_execution, ticket_link, routing_decision
│   │       ├── 003_memory_schema.sql       # memory.vendor_profile_cache, episodic_memory, embedding_index
│   │       ├── 004_audit_schema.sql        # audit.action_log, audit.validation_results
│   │       └── 005_reporting_schema.sql    # reporting.sla_metrics
│   │
│   ├── cache/
│   │   └── redis_client.py          # Redis wrapper with 6 key families and TTL management
│   │
│   ├── storage/
│   │   └── s3_client.py             # S3 upload/download for 4 buckets
│   │
│   ├── events/
│   │   └── eventbridge.py           # Publishes 17 event types to vqms-event-bus
│   │
│   ├── queues/
│   │   └── sqs.py                   # Producer/consumer for 10 SQS queues + DLQ
│   │
│   ├── adapters/
│   │   └── graph_api.py             # Microsoft Graph API client (OAuth, email fetch, attachments)
│   │
│   ├── services/
│   │   └── email_intake.py          # 10-step email ingestion pipeline (fully working)
│   │
│   ├── utils/
│   │   ├── correlation.py           # UUID4-based correlation ID generator
│   │   ├── logger.py                # Structured logging setup
│   │   ├── helpers.py               # General utility functions
│   │   ├── retry.py                 # Retry with backoff
│   │   └── validation.py            # Input validation helpers
│   │
│   ├── agents/                      # Stub - AI agents go here (Phase 4+)
│   ├── gates/                       # Stub - Quality Gate goes here (Phase 7)
│   ├── monitoring/                  # Stub - SLA alerting goes here (Phase 8)
│   ├── orchestration/               # Stub - LangGraph pipeline goes here (Phase 4)
│   ├── llm/                         # Stub - Bedrock integration goes here (Phase 5)
│   ├── memory/                      # Stub - Memory service goes here (Phase 3)
│   ├── tools/                       # Stub - Agent tools go here (Phase 5)
│   └── evaluation/                  # Stub - LLM eval framework goes here (Phase 10)
│
├── tests/
│   ├── conftest.py                  # Shared fixtures
│   ├── unit/
│   │   ├── test_models.py           # Pydantic model validation (all 20 models)
│   │   ├── test_correlation.py      # Correlation ID generation
│   │   ├── test_redis_client.py     # Redis key builders, connect, set/get
│   │   ├── test_s3_client.py        # S3 upload/download (moto mocked)
│   │   ├── test_eventbridge.py      # Event publishing (moto mocked)
│   │   ├── test_sqs.py              # Queue send/receive (moto mocked)
│   │   └── test_email_intake.py     # Full 10-step pipeline test
│   └── evals/                       # Stub - LLM quality evaluations go here
│
├── prompts/                         # Jinja2 prompt templates (empty, Phase 5+)
│   ├── email_analysis/
│   ├── communication_drafting/
│   └── orchestration/
│
├── security/                        # Security and compliance configs (empty, later phases)
│
├── data/
│   ├── knowledge_base/              # RAG source documents
│   ├── vector_store/                # Local vector DB files
│   ├── logs/                        # Execution logs
│   └── artifacts/                   # Generated output files
│
└── notebooks/                       # Jupyter notebooks for experimentation
```

## Local setup

You need Python 3.12+ and [uv](https://docs.astral.sh/uv/) installed.

```bash
# 1. Clone the repo and cd into it
cd VQMS_Project

# 2. Install all dependencies (creates .venv automatically)
uv sync --all-extras

# 3. Copy the environment template
cp .env.copy .env

# 4. Edit .env and fill in your values (see "Environment variables" below)

# 5. Verify everything works
uv run ruff check .
uv run pytest
```

You should see 83 tests passing and 0 linting errors.

### PostgreSQL and Redis

The email intake service and tests that hit the database need PostgreSQL and Redis running. For local development:

```bash
# If you have Docker
docker run -d --name vqms-postgres -p 5432:5432 -e POSTGRES_DB=vqms -e POSTGRES_PASSWORD=yourpassword postgres:16
docker run -d --name vqms-redis -p 6379:6379 redis:7

# Run the migrations in order
psql -h localhost -U postgres -d vqms -f src/db/migrations/001_intake_schema.sql
psql -h localhost -U postgres -d vqms -f src/db/migrations/002_workflow_schema.sql
psql -h localhost -U postgres -d vqms -f src/db/migrations/003_memory_schema.sql
psql -h localhost -U postgres -d vqms -f src/db/migrations/004_audit_schema.sql
psql -h localhost -U postgres -d vqms -f src/db/migrations/005_reporting_schema.sql
```

The unit tests mock all external services (AWS, Graph API, Redis, PostgreSQL) so you can run tests without any infrastructure.

## Running tests

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run a specific test file
uv run pytest tests/unit/test_email_intake.py

# Run with coverage
uv run pytest --cov=src --cov-report=term-missing
```

Tests use `moto` to mock AWS services (S3, SQS, EventBridge) and `pytest-mock` for everything else. No real AWS credentials needed for tests.

## Linting

```bash
# Check for issues
uv run ruff check .

# Auto-fix what ruff can fix
uv run ruff check . --fix
```

Ruff is configured in `.ruff.toml`. It checks for: pyflakes errors, pycodestyle warnings, import sorting, naming conventions, unnecessary complexity, and some ruff-specific rules. Line length is not enforced (handled by formatter).

## Environment variables

Copy `.env.copy` to `.env` and fill in real values. The template has about 80 variables across these sections:

| Section | What you need |
|---|---|
| APPLICATION | `APP_ENV=development`, port, log level. Safe to leave defaults. |
| AWS GENERAL | AWS credentials and region. Needed for S3, SQS, EventBridge, Bedrock. |
| AMAZON BEDROCK | Model ID, region, token limits, temperature. Used by the LLM adapter. |
| POSTGRESQL | Host, port, database name, user, password, pool sizes. |
| PGVECTOR | Embedding dimensions (1536), HNSW index params. |
| REDIS | Host, port, password, key prefix (`vqms:`). |
| MICROSOFT GRAPH API | Azure tenant/client IDs and secret. Needed for email fetching. |
| SALESFORCE | Instance URL, credentials, consumer key/secret. Phase 6. |
| SERVICENOW | Instance URL, credentials, OAuth client. Phase 6. |
| AWS S3 | 4 bucket names. |
| AWS SQS | Queue prefix, DLQ name, visibility timeout. |
| AWS EVENTBRIDGE | Bus name (`vqms-event-bus`), source prefix. |
| SLA CONFIG | Warning/escalation thresholds (70%, 85%, 95%), default SLA hours. |
| AGENT CONFIG | Confidence threshold, max hops, token budgets. |

For local development, you need at minimum: PostgreSQL connection, Redis connection, and AWS credentials (or use moto for testing). The Graph API, Salesforce, and ServiceNow credentials are only needed when you run the actual pipeline against real services.

## Data models

Every piece of data in the pipeline has a Pydantic model in `src/models/`. Here is what each one represents.

### Email models (`src/models/email.py`)

| Model | What it is |
|---|---|
| `EmailAttachment` | A file attached to an email. Has filename, MIME type, size, and S3 path after upload. |
| `EmailMessage` | A raw email from Exchange Online. Sender info, subject, plain and HTML body, timestamps, list of attachments. |
| `ParsedEmailPayload` | The cleaned-up version of an email after ingestion. This is what gets passed to the analysis queue. Includes correlation ID, sender, subject, body, S3 path, and a duplicate flag. |

### Vendor models (`src/models/vendor.py`)

| Model | What it is |
|---|---|
| `VendorTier` | Enum with four levels: `platinum`, `gold`, `silver`, `standard`. Determines SLA targets. Platinum gets the fastest response. |
| `VendorMatch` | Result of looking up a vendor in Salesforce. Has the vendor ID, name, tier, how we matched them (exact email, vendor ID in body, or fuzzy name), confidence score, and any risk flags. |
| `VendorProfile` | Cached vendor data. Includes SLA hours, interaction count, average resolution time, last ticket ID. Used for context when agents make decisions. |

### Ticket models (`src/models/ticket.py`)

| Model | What it is |
|---|---|
| `TicketRecord` | A ServiceNow ticket. ID, URL, vendor, title, description, assignee, status, priority, timestamps. |
| `TicketLink` | Links a case to a ticket. A case can have multiple tickets but only one is primary. |
| `RoutingDecision` | What the orchestration agent decided to do: auto-process, human review, update existing ticket, reopen closed ticket, or escalate. Includes confidence and reasoning. |

### Workflow models (`src/models/workflow.py`)

| Model | What it is |
|---|---|
| `WorkflowState` | Enum tracking where a case is in the pipeline: `pending`, `analyzing`, `routing`, `drafting`, `validating`, `sending`, `closed`, `reopened`. |
| `AnalysisResult` | Output from the Email Analysis Agent. Intent, extracted entities, urgency level, sentiment, confidence score, and a summary. |
| `CaseExecution` | The central tracking object. One per email. Holds the correlation ID, current workflow state, and all intermediate results (analysis, vendor match, routing decision, draft, validation report). |

### Communication models (`src/models/communication.py`)

| Model | What it is |
|---|---|
| `DraftEmailPackage` | A response email drafted by the Communication Agent. Has the ticket ID, recipient, subject, HTML and plain text body, SLA promise text, and flags for whether the ticket number and template are correct. |
| `ValidationReport` | Result of the Quality Gate checking a draft. Four boolean checks: ticket number present, ticket number valid, SLA wording correct, no PII detected. Plus an overall pass/fail. |

### Memory models (`src/models/memory.py`)

| Model | What it is |
|---|---|
| `EpisodicMemory` | An immutable record of something that happened with a vendor. Used to give agents context about past interactions ("last time this vendor wrote, it was about invoice #1234"). |
| `VendorProfileCache` | Persistent cache of vendor data in PostgreSQL. Mirrors what's in Salesforce but avoids repeated API calls. Includes interaction count and average resolution time. |
| `EmbeddingRecord` | A 1536-dimensional vector embedding of a text chunk. Stored in pgvector for semantic similarity search (RAG). |

### Inter-agent models (`src/models/messages.py`)

| Model | What it is |
|---|---|
| `ToolCall` | Record of one tool invocation by an agent. Tool name, input, output, and how long it took. |
| `AgentMessage` | How agents communicate. Has a sender, receiver, message type, payload, list of tool calls, and token/cost accounting. Every message carries a correlation ID. |

### Budget model (`src/models/budget.py`)

| Model | What it is |
|---|---|
| `Budget` | A dataclass (not Pydantic) that tracks token usage and cost per agent call. Has limits for input tokens, output tokens, and USD cost. Has methods like `is_exhausted()` and `remaining_tokens_in()`. |

## Database schema

Five schemas, eleven tables. All defined in `src/db/migrations/`.

### `intake` schema (migration 001)

| Table | What it stores |
|---|---|
| `email_messages` | One row per email. message_id (from Exchange), correlation_id, sender email/name, subject, plain and HTML body, received_at, parsed_at, S3 path to raw email, vendor_id (filled later), is_duplicate flag. Indexed on correlation_id, sender_email, received_at. |
| `email_attachments` | One row per attachment. Foreign key to email_messages. Filename, size in bytes, MIME type, S3 path. |

### `workflow` schema (migration 002)

| Table | What it stores |
|---|---|
| `case_execution` | One row per case (one case per email). correlation_id (unique), message_id FK, workflow_state, plus JSONB columns for analysis_result, vendor_match, routing_decision, draft_package, validation_report. Also: ticket_id, assigned_group, escalation_count, is_human_review flag, closed_at. |
| `ticket_link` | Links cases to ServiceNow tickets. case_id FK, ticket_id, ticket_url, linked_at. Unique constraint on (case_id, is_primary=true) so each case has exactly one primary ticket. |
| `routing_decision` | What the orchestration agent decided. case_id FK, decision_type, confidence_score (0-1), reason text, decided_at. |

### `memory` schema (migration 003)

| Table | What it stores |
|---|---|
| `vendor_profile_cache` | Cached vendor data from Salesforce. vendor_id (unique), name, tier, SLA hours, risk flags (JSONB array), last_seen, last_ticket_id, interaction_count, avg_resolution_time_hours. |
| `episodic_memory` | Event log per vendor. correlation_id, vendor_id, event_type, event_data (JSONB), timestamp. |
| `embedding_index` | Vector embeddings for semantic search. correlation_id, vendor_id, text_chunk, embedding (vector(1536) with HNSW index). Uses the pgvector extension. |

### `audit` schema (migration 004)

| Table | What it stores |
|---|---|
| `action_log` | Immutable audit trail. Every action in the pipeline gets a row: correlation_id, action name, actor (service or agent name), resource_id, status (success/failure), error_message, metadata (JSONB). This is a compliance requirement. |
| `validation_results` | Quality Gate check results. case_id FK, validation_type (ticket_number, sla_wording, pii_check, template_check), is_valid boolean, details (JSONB). |

### `reporting` schema (migration 005)

| Table | What it stores |
|---|---|
| `sla_metrics` | SLA tracking per case. case_id FK, ticket_id, vendor_id, vendor_tier, sla_hours target, created_at, first_response_at, resolved_at, time_to_first_response_minutes, time_to_resolution_minutes, sla_met boolean, escalation count. |

## Redis key families

Six key patterns, all prefixed with `vqms:`. Defined in `src/cache/redis_client.py`.

| Key pattern | TTL | What it does |
|---|---|---|
| `vqms:idempotency:{message_id}` | 7 days | Prevents processing the same email twice. Set after successful ingestion. The 7-day window covers Exchange Online's redelivery behavior during recovery. |
| `vqms:thread:{thread_id}` | 30 days | Groups related emails into a conversation thread. |
| `vqms:ticket:{ticket_id}` | 30 days | Maps a ticket ID to its case data for fast lookup. |
| `vqms:workflow:{correlation_id}` | 24 hours | Temporary state while a case is being processed. Short TTL because it's transient. |
| `vqms:vendor:{vendor_id}` | 1 hour | Hot cache of vendor profile data. Short TTL so stale Salesforce data doesn't linger. |
| `vqms:sla:{case_id}` | 7 days | Tracks SLA deadlines and escalation state for active cases. |

Currently, only the idempotency key family is wired into the pipeline (used in `email_intake.py`). The rest have builders and set/get methods ready but are waiting for their respective services.

## How an email flows through the system

This is the full pipeline as designed. Steps 1-10 are working today. The rest is planned.

```
Vendor sends email to vendorsupport@yourcompany.com
         |
         v
[1]  Graph API adapter polls Exchange Online for unread messages
[2]  Email Intake Service picks up the email
[3]  Check Redis idempotency key - skip if we already processed this message_id
[4]  Fetch full email content from Graph API
[5]  Store raw email in S3 (vqms-email-raw-prod)
[6]  Publish EmailReceived event to EventBridge
[7]  Fetch and store attachments in S3 (vqms-email-attachments-prod)
[8]  Write email metadata to PostgreSQL (intake.email_messages + email_attachments)
[9]  Set Redis idempotency key (7-day TTL)
[10] Build ParsedEmailPayload, publish EmailParsed event, send to vqms-analysis queue
         |
         v  (NOT YET BUILT - Phase 3+)
[11] Memory & Context Service loads vendor history and past threads
[12] Email Analysis Agent reads the email, extracts intent/urgency/entities
[13] Vendor Resolution Service matches sender to Salesforce account
[14] Orchestration Agent decides: auto-process, human review, update, reopen, or escalate
[15] Ticket Operations Service creates/updates ServiceNow ticket
[16] Communication Drafting Agent writes the response email
[17] Quality Gate checks: ticket number, SLA wording, PII scan, template compliance
[18] If validation passes, send the response via Graph API
[19] Log everything to audit.action_log
[20] Update SLA metrics in reporting.sla_metrics
```

## Build order and progress

The project follows a strict bottom-up build order. Do not skip phases.

| Phase | What it builds | Status |
|---|---|---|
| 1 | Project structure, Pydantic models, SQL migrations, Redis helpers, configs, utilities | Done |
| 2 | Email Ingestion Service (Graph API, S3, PostgreSQL, Redis, EventBridge, SQS) | Done |
| 3 | Thread correlation, deduplication, Memory & Context Service | Next |
| 4 | AWS Step Functions + LangGraph orchestration skeleton (stub agents) | Not started |
| 5 | Email Analysis Agent + Bedrock Integration Service | Not started |
| 6 | Salesforce (vendor resolution) + ServiceNow (ticket operations) | Not started |
| 7 | Communication Drafting Agent + Quality Gate | Not started |
| 8 | SLA monitoring and escalation | Not started |
| 9 | Closure and reopen logic | Not started |
| 10 | End-to-end testing, observability, production readiness | Not started |

## Where do I put this?

| I want to... | Put it in... |
|---|---|
| Add a new AI agent | `src/agents/` (inherit from `abc_agent.py`) |
| Add a new data model | `src/models/` (Pydantic model) |
| Add a new external API connector | `src/adapters/` (wrap the REST API) |
| Add a deterministic business service | `src/services/` |
| Add a quality/validation check | `src/gates/` |
| Add a prompt template | `prompts/<agent_name>/v<N>.jinja` |
| Add a database table | `src/db/migrations/` (new SQL file) |
| Add a utility/helper function | `src/utils/` |
| Add a custom tool for agents | `src/tools/custom_tools.py` |
| Add/update an environment variable | `.env` AND `.env.copy` |
| Add a YAML config | `config/` |
| Write a unit test | `tests/unit/test_<module_name>.py` |
| Write an LLM eval test | `tests/evals/` |
| Track a task | `tasks/todo.md` |
| Log a lesson learned | `tasks/lessons.md` |

## Contributing guidelines

### Naming

- Variables and functions: `snake_case`. Be descriptive. `vendor_match_result` not `vmr`.
- Classes: `PascalCase`. Nouns. `VendorResolutionService` not `Helper`.
- Constants: `UPPER_SNAKE_CASE`. `MAX_RETRY_ATTEMPTS = 3`.
- Booleans: should read as a yes/no question. `is_duplicate`, `has_attachments`, `vendor_found`.

### Comments

Write comments that explain why, not what. If the code says `active_vendors = [v for v in vendors if v.is_active]`, don't write `# Filter active vendors`. Do write `# Salesforce sometimes returns inactive vendor records, so we filter them out before matching`.

### Type hints

Required on all function signatures. No exceptions.

```python
async def resolve_vendor_from_email(
    sender_email: str,
    email_body: str,
    *,
    correlation_id: str | None = None,
) -> VendorMatch:
```

### Docstrings

Required on all public functions and classes. Explain what it does, the args, what it returns, and what exceptions it raises. See `src/services/email_intake.py` for examples of the expected level of detail.

### Error handling

- Define domain-specific exceptions per module (`EmailIntakeError`, `VendorResolutionError`, etc.)
- Never raise bare `Exception`
- Never use `print()` - use `logging` with structured fields
- Always include `correlation_id` in log lines

### Testing

- Write tests for everything you build
- Tests go in `tests/unit/test_<module_name>.py`
- Mock external services (AWS, Graph API, Salesforce, ServiceNow) - never hit real APIs in tests
- Run `uv run pytest` and `uv run ruff check .` before considering anything done
- Target 80%+ coverage

### Dependencies

Never use `pip install`. Always use `uv add <package>`. Dependencies live in `pyproject.toml`.

### Git

- Never commit `.env`
- Conventional commit messages: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`
