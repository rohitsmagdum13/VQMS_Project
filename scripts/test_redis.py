"""Verify Redis Cloud connection and key operations.

Run with: uv run python scripts/test_redis.py
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()


async def main() -> None:
    print("=" * 60)
    print("VQMS — Redis Connection Verification")
    print("=" * 60)

    host = os.getenv("REDIS_HOST", "NOT SET")
    port = os.getenv("REDIS_PORT", "NOT SET")
    print(f"\nHost: {host}")
    print(f"Port: {port}")
    print("-" * 60)

    import redis.asyncio as redis_lib

    passed = 0
    failed = 0

    # ---- Test 1: Connection ----
    print("\n[TEST 1] Connecting to Redis...")
    try:
        client = redis_lib.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            password=os.getenv("REDIS_PASSWORD"),
            db=int(os.getenv("REDIS_DB", "0")),
            ssl=os.getenv("REDIS_SSL", "false").lower() == "true",
            decode_responses=True,
        )
        pong = await client.ping()
        print(f"  PASSED — PING returned: {pong}")
        passed += 1
    except Exception as e:
        print(f"  FAILED — {e}")
        print("\n  Troubleshooting:")
        print("  - Check REDIS_HOST, REDIS_PORT, REDIS_PASSWORD in .env")
        print("  - Try setting REDIS_SSL=true if using Redis Cloud")
        failed += 1
        return

    # ---- Test 2: SET/GET/DELETE ----
    print("\n[TEST 2] Testing SET/GET/DELETE...")
    try:
        test_key = "vqms:test:connection_check"
        await client.setex(test_key, 60, "hello_vqms")
        value = await client.get(test_key)
        assert value == "hello_vqms", f"Expected 'hello_vqms', got '{value}'"
        await client.delete(test_key)
        deleted_value = await client.get(test_key)
        assert deleted_value is None, "Key should be deleted"
        print("  PASSED — SET, GET, DELETE all work correctly.")
        passed += 1
    except Exception as e:
        print(f"  FAILED — {e}")
        failed += 1

    # ---- Test 3: JSON serialization (like RedisClient uses) ----
    print("\n[TEST 3] Testing JSON key operations (simulating VQMS key families)...")
    try:
        import orjson

        test_data = {
            "message_id": "test-msg-001",
            "processed_at": "2026-03-30T10:00:00Z",
            "status": "processed",
        }

        # Test idempotency key family
        key = "vqms:idempotency:test-msg-001"
        serialized = orjson.dumps(test_data).decode("utf-8")
        await client.setex(key, 60, serialized)
        raw = await client.get(key)
        result = orjson.loads(raw)
        assert result["message_id"] == "test-msg-001"
        await client.delete(key)

        print("  PASSED — JSON serialization with orjson works.")
        passed += 1
    except Exception as e:
        print(f"  FAILED — {e}")
        failed += 1

    # ---- Test 4: RedisClient wrapper ----
    print("\n[TEST 4] Testing RedisClient wrapper class...")
    try:
        from src.cache.redis_client import RedisClient

        rc = RedisClient(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            password=os.getenv("REDIS_PASSWORD"),
            db=int(os.getenv("REDIS_DB", "0")),
            ssl=os.getenv("REDIS_SSL", "false").lower() == "true",
        )
        await rc.connect()

        # Test idempotency family
        await rc.set_idempotency("test-001", {"status": "ok"})
        data = await rc.get_idempotency("test-001")
        assert data is not None and data["status"] == "ok"
        await rc.delete_idempotency("test-001")

        await rc.close()
        print("  PASSED — RedisClient wrapper works end-to-end.")
        passed += 1
    except Exception as e:
        print(f"  FAILED — {e}")
        failed += 1

    await client.aclose()

    # ---- Summary ----
    print(f"\n{'=' * 60}")
    if failed == 0:
        print(f"ALL {passed} TESTS PASSED — Redis is correctly configured!")
    else:
        print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
