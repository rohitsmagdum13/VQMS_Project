"""Verify Neon PostgreSQL connection, schemas, and tables.

Run with: uv run python scripts/test_postgres.py
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()


async def main() -> None:
    print("=" * 60)
    print("VQMS — PostgreSQL (Neon) Connection Verification")
    print("=" * 60)

    host = os.getenv("POSTGRES_HOST", "NOT SET")
    db = os.getenv("POSTGRES_DB", "NOT SET")
    user = os.getenv("POSTGRES_USER", "NOT SET")
    print(f"\nHost: {host}")
    print(f"Database: {db}")
    print(f"User: {user}")
    print("-" * 60)

    import asyncpg

    passed = 0
    failed = 0
    conn = None

    # ---- Test 1: Connection ----
    print("\n[TEST 1] Connecting to Neon PostgreSQL...")
    try:
        # Neon requires SSL
        conn = await asyncpg.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            database=os.getenv("POSTGRES_DB", "vqms"),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", ""),
            ssl="require",
        )
        version = await conn.fetchval("SELECT version()")
        print(f"  PASSED — Connected successfully.")
        print(f"    PostgreSQL version: {version[:60]}...")
        passed += 1
    except Exception as e:
        print(f"  FAILED — {e}")
        print("\n  Troubleshooting:")
        print("  - Check POSTGRES_HOST, POSTGRES_USER, POSTGRES_PASSWORD in .env")
        print("  - Neon requires SSL — make sure your host ends with .neon.tech")
        print("  - Check that the database 'vqms' exists in Neon dashboard")
        failed += 1
        return

    # ---- Test 2: Check pgvector extension ----
    print("\n[TEST 2] Checking pgvector extension...")
    try:
        result = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')"
        )
        if result:
            print("  PASSED — pgvector extension is enabled.")
            passed += 1
        else:
            print("  WARNING — pgvector not enabled. Run in Neon SQL Editor:")
            print("    CREATE EXTENSION IF NOT EXISTS vector;")
            failed += 1
    except Exception as e:
        print(f"  FAILED — {e}")
        failed += 1

    # ---- Test 3: Check schemas ----
    print("\n[TEST 3] Checking database schemas...")
    expected_schemas = ["intake", "workflow", "memory", "audit", "reporting"]
    try:
        rows = await conn.fetch(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name = ANY($1::text[])",
            expected_schemas,
        )
        found_schemas = [row["schema_name"] for row in rows]
        missing = [s for s in expected_schemas if s not in found_schemas]

        if not missing:
            print(f"  PASSED — All 5 schemas exist: {', '.join(found_schemas)}")
            passed += 1
        else:
            print(f"  FAILED — Missing schemas: {', '.join(missing)}")
            print(f"    Found: {', '.join(found_schemas) if found_schemas else 'none'}")
            print("    Run the migration SQL files in Neon SQL Editor:")
            for s in missing:
                migration_num = expected_schemas.index(s) + 1
                print(f"      src/db/migrations/{migration_num:03d}_*_schema.sql")
            failed += 1
    except Exception as e:
        print(f"  FAILED — {e}")
        failed += 1

    # ---- Test 4: Check tables ----
    print("\n[TEST 4] Checking database tables...")
    expected_tables = {
        "intake": ["email_messages", "email_attachments"],
        "workflow": ["case_execution", "ticket_link", "routing_decision"],
        "memory": ["vendor_profile_cache", "episodic_memory", "embedding_index"],
        "audit": ["action_log", "validation_results"],
        "reporting": ["sla_metrics"],
    }
    try:
        all_found = True
        for schema, tables in expected_tables.items():
            rows = await conn.fetch(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = $1",
                schema,
            )
            found = [row["table_name"] for row in rows]
            missing = [t for t in tables if t not in found]
            if missing:
                print(f"  MISSING in {schema}: {', '.join(missing)}")
                all_found = False
            else:
                print(f"  {schema}: {', '.join(found)} — OK")

        if all_found:
            print(f"\n  PASSED — All 11 tables exist across 5 schemas.")
            passed += 1
        else:
            print(f"\n  FAILED — Some tables are missing. Run migration files.")
            failed += 1
    except Exception as e:
        print(f"  FAILED — {e}")
        failed += 1

    # ---- Test 5: Test INSERT/SELECT on intake.email_messages ----
    print("\n[TEST 5] Testing INSERT/SELECT on intake.email_messages...")
    try:
        # Insert a test row
        await conn.execute(
            """
            INSERT INTO intake.email_messages
                (message_id, correlation_id, sender_email, subject, received_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (message_id) DO NOTHING
            """,
            "test-msg-verification-001",
            "corr-test-001",
            "test@example.com",
            "VQMS Connection Test",
        )

        # Read it back
        row = await conn.fetchrow(
            "SELECT message_id, sender_email, subject "
            "FROM intake.email_messages WHERE message_id = $1",
            "test-msg-verification-001",
        )

        if row and row["sender_email"] == "test@example.com":
            print("  PASSED — INSERT and SELECT work correctly.")
            passed += 1
        else:
            print("  FAILED — Row not found after INSERT.")
            failed += 1

        # Clean up test data
        await conn.execute(
            "DELETE FROM intake.email_messages WHERE message_id = $1",
            "test-msg-verification-001",
        )
    except Exception as e:
        print(f"  FAILED — {e}")
        failed += 1

    # ---- Test 6: Test DatabasePool wrapper ----
    print("\n[TEST 6] Testing DatabasePool wrapper class...")
    try:
        from src.db.connection import DatabasePool

        pool = DatabasePool()
        # Patch connect to use SSL for Neon
        pool._pool = await asyncpg.create_pool(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            database=os.getenv("POSTGRES_DB", "vqms"),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", ""),
            min_size=2,
            max_size=5,
            ssl="require",
        )
        row = await pool.fetchrow("SELECT 1 AS test_value")
        assert row["test_value"] == 1
        await pool.close()
        print("  PASSED — DatabasePool wrapper works.")
        passed += 1
    except Exception as e:
        print(f"  FAILED — {e}")
        failed += 1

    if conn:
        await conn.close()

    # ---- Summary ----
    print(f"\n{'=' * 60}")
    if failed == 0:
        print(f"ALL {passed} TESTS PASSED — PostgreSQL is correctly configured!")
    else:
        print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
