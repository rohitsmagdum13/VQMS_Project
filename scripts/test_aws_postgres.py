"""Verify AWS RDS PostgreSQL connection.

Uses the existing POSTGRES_* variables from your .env file:

    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB,
    POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_SSLMODE

Run with: uv run python scripts/test_aws_postgres.py
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()


def get_env_or_exit(key: str) -> str:
    """Read an environment variable or exit with a helpful message."""
    value = os.getenv(key)
    if not value or value.startswith("<"):
        print(f"  ERROR: {key} is not set in .env")
        print(f"  Add it to your .env file and try again.")
        sys.exit(1)
    return value


async def main() -> None:
    print("=" * 60)
    print("VQMS — AWS RDS PostgreSQL Connection Verification")
    print("=" * 60)

    # Read connection details from .env (same variable names as Neon setup)
    host = get_env_or_exit("POSTGRES_HOST")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    db = get_env_or_exit("POSTGRES_DB")
    user = get_env_or_exit("POSTGRES_USER")
    password = get_env_or_exit("POSTGRES_PASSWORD")
    ssl_mode = os.getenv("POSTGRES_SSLMODE", "require")

    print(f"\nHost:     {host}")
    print(f"Port:     {port}")
    print(f"Database: {db}")
    print(f"User:     {user}")
    print(f"SSL:      {ssl_mode}")
    print("-" * 60)

    import asyncpg

    passed = 0
    failed = 0
    conn = None

    # ---- Test 1: Basic Connection ----
    print("\n[TEST 1] Connecting to AWS RDS PostgreSQL...")
    try:
        ssl_arg = ssl_mode if ssl_mode in ("require", "prefer", "verify-full") else None
        conn = await asyncpg.connect(
            host=host,
            port=port,
            database=db,
            user=user,
            password=password,
            ssl=ssl_arg,
            timeout=15,
        )
        version = await conn.fetchval("SELECT version()")
        print(f"  PASSED — Connected successfully.")
        print(f"    Server: {version[:80]}...")
        passed += 1
    except Exception as e:
        print(f"  FAILED — {e}")
        print("\n  Troubleshooting:")
        print("  - Verify POSTGRES_* variables in .env are correct")
        print("  - Check RDS security group allows inbound on port 5432 from your IP")
        print("  - Check RDS instance is publicly accessible (or you're in the same VPC)")
        print("  - Try setting AWS_POSTGRES_SSL=prefer if SSL handshake fails")
        failed += 1
        print(f"\n{'=' * 60}")
        print(f"Results: {passed} passed, {failed} failed")
        print("=" * 60)
        return

    # ---- Test 2: Check server info ----
    print("\n[TEST 2] Checking server details...")
    try:
        db_size = await conn.fetchval(
            "SELECT pg_size_pretty(pg_database_size(current_database()))"
        )
        current_db = await conn.fetchval("SELECT current_database()")
        current_user = await conn.fetchval("SELECT current_user")
        max_conns = await conn.fetchval("SHOW max_connections")
        print(f"  PASSED — Server info retrieved.")
        print(f"    Database:        {current_db}")
        print(f"    Connected as:    {current_user}")
        print(f"    Database size:   {db_size}")
        print(f"    Max connections: {max_conns}")
        passed += 1
    except Exception as e:
        print(f"  FAILED — {e}")
        failed += 1

    # ---- Test 3: Check pgvector extension ----
    print("\n[TEST 3] Checking pgvector extension...")
    try:
        has_vector = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')"
        )
        if has_vector:
            print("  PASSED — pgvector extension is enabled.")
            passed += 1
        else:
            print("  INFO — pgvector not enabled. To enable, run:")
            print("    CREATE EXTENSION IF NOT EXISTS vector;")
            print("  (Requires RDS instance with pgvector support)")
            failed += 1
    except Exception as e:
        print(f"  FAILED — {e}")
        failed += 1

    # ---- Test 4: Check existing schemas ----
    print("\n[TEST 4] Checking VQMS schemas...")
    expected_schemas = ["intake", "workflow", "memory", "audit", "reporting"]
    try:
        rows = await conn.fetch(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name = ANY($1::text[])",
            expected_schemas,
        )
        found = [row["schema_name"] for row in rows]
        missing = [s for s in expected_schemas if s not in found]

        if not missing:
            print(f"  PASSED — All 5 schemas exist: {', '.join(found)}")
            passed += 1
        else:
            print(f"  INFO — Missing schemas: {', '.join(missing)}")
            print(f"    Found: {', '.join(found) if found else 'none'}")
            print("    This is expected if migrations haven't been run yet.")
            failed += 1
    except Exception as e:
        print(f"  FAILED — {e}")
        failed += 1

    # ---- Test 5: Check existing tables ----
    print("\n[TEST 5] Checking VQMS tables...")
    expected_tables = {
        "intake": ["email_messages", "email_attachments"],
        "workflow": ["case_execution", "ticket_link", "routing_decision"],
        "memory": ["vendor_profile_cache", "episodic_memory", "embedding_index"],
        "audit": ["action_log", "validation_results"],
        "reporting": ["sla_metrics"],
    }
    try:
        total_found = 0
        total_expected = 0
        for schema, tables in expected_tables.items():
            total_expected += len(tables)
            rows = await conn.fetch(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = $1",
                schema,
            )
            found = [row["table_name"] for row in rows]
            present = [t for t in tables if t in found]
            missing = [t for t in tables if t not in found]
            total_found += len(present)

            if missing:
                print(f"  {schema}: missing {', '.join(missing)}")
            else:
                print(f"  {schema}: {', '.join(found)} — OK")

        if total_found == total_expected:
            print(f"\n  PASSED — All {total_expected} tables exist.")
            passed += 1
        else:
            print(f"\n  INFO — {total_found}/{total_expected} tables found.")
            print("    Run migration files to create missing tables.")
            failed += 1
    except Exception as e:
        print(f"  FAILED — {e}")
        failed += 1

    # ---- Test 6: Write/Read test ----
    print("\n[TEST 6] Testing write/read capability...")
    try:
        # Create a temporary test table
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS public._vqms_conn_test "
            "(id SERIAL PRIMARY KEY, value TEXT, created_at TIMESTAMPTZ DEFAULT NOW())"
        )
        # Insert a test row
        await conn.execute(
            "INSERT INTO public._vqms_conn_test (value) VALUES ($1)",
            "connection-test",
        )
        # Read it back
        row = await conn.fetchrow(
            "SELECT value FROM public._vqms_conn_test WHERE value = $1",
            "connection-test",
        )
        if row and row["value"] == "connection-test":
            print("  PASSED — Write and read work correctly.")
            passed += 1
        else:
            print("  FAILED — Could not read back written row.")
            failed += 1
        # Clean up
        await conn.execute("DROP TABLE IF EXISTS public._vqms_conn_test")
    except Exception as e:
        print(f"  FAILED — {e}")
        # Try cleanup even on failure
        try:
            await conn.execute("DROP TABLE IF EXISTS public._vqms_conn_test")
        except Exception:
            pass
        failed += 1

    # ---- Test 7: Check permissions ----
    print("\n[TEST 7] Checking user permissions...")
    try:
        can_create = await conn.fetchval(
            "SELECT has_database_privilege(current_user, current_database(), 'CREATE')"
        )
        can_connect = await conn.fetchval(
            "SELECT has_database_privilege(current_user, current_database(), 'CONNECT')"
        )
        print(f"  CREATE privilege: {'YES' if can_create else 'NO'}")
        print(f"  CONNECT privilege: {'YES' if can_connect else 'NO'}")
        if can_create and can_connect:
            print("  PASSED — User has required permissions.")
            passed += 1
        else:
            print("  WARNING — Missing some permissions. Schema creation may fail.")
            failed += 1
    except Exception as e:
        print(f"  FAILED — {e}")
        failed += 1

    if conn:
        await conn.close()

    # ---- Summary ----
    total = passed + failed
    print(f"\n{'=' * 60}")
    if failed == 0:
        print(f"ALL {passed} TESTS PASSED — AWS RDS PostgreSQL is ready!")
    else:
        print(f"Results: {passed}/{total} passed, {failed}/{total} failed")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
