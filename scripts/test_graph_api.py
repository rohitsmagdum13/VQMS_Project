"""Quick verification script for Microsoft Graph API setup.

Tests authentication, mailbox access, and email fetching
against the configured Exchange Online mailbox.

Run with: uv run python scripts/test_graph_api.py
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

# Add project root to path so we can import src/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from src.adapters.graph_api import GraphAPIAdapter, GraphAPIError


async def main() -> None:
    print("=" * 60)
    print("VQMS — Microsoft Graph API Verification")
    print("=" * 60)

    # Show config (masked for security)
    tenant = os.getenv("GRAPH_API_TENANT_ID", "NOT SET")
    client = os.getenv("GRAPH_API_CLIENT_ID", "NOT SET")
    mailbox = os.getenv("GRAPH_API_MAILBOX", "NOT SET")

    masked_tenant = f"{tenant[:8]}...{tenant[-4:]}" if len(tenant) > 12 else tenant
    masked_client = f"{client[:8]}...{client[-4:]}" if len(client) > 12 else client

    print(f"\nTenant ID:  {masked_tenant}")
    print(f"Client ID:  {masked_client}")
    print(f"Mailbox:    {mailbox}")
    print("-" * 60)

    graph = GraphAPIAdapter()
    passed = 0
    failed = 0

    # ---- Test 1: Authentication ----
    print("\n[TEST 1] Authenticating with Azure AD...")
    try:
        token = await graph._get_access_token()
        print(f"  PASSED — Token acquired (starts with: {token[:20]}...)")
        passed += 1
    except GraphAPIError as e:
        print(f"  FAILED — {e}")
        print("\n  Troubleshooting:")
        print("  - Check GRAPH_API_TENANT_ID, CLIENT_ID, CLIENT_SECRET in .env")
        print("  - Make sure the app registration exists in Azure portal")
        print("  - Make sure the client secret hasn't expired")
        failed += 1
        await graph.close()
        print(f"\n{'=' * 60}")
        print(f"Results: {passed} passed, {failed} failed")
        print("Fix authentication first, then run again.")
        return

    # ---- Test 2: Mailbox Access ----
    print("\n[TEST 2] Accessing mailbox (listing unread messages)...")
    try:
        messages = await graph.list_unread_messages(max_results=10)
        print(f"  PASSED — Mailbox accessible. Found {len(messages)} unread message(s).")
        passed += 1

        if messages:
            print("\n  Recent unread emails:")
            for i, msg in enumerate(messages[:5], 1):
                sender = (
                    msg.get("from", {})
                    .get("emailAddress", {})
                    .get("address", "unknown")
                )
                subject = msg.get("subject", "(no subject)")
                received = msg.get("receivedDateTime", "unknown")
                print(f"    {i}. From: {sender}")
                print(f"       Subject: {subject}")
                print(f"       Received: {received}")
        else:
            print("\n  No unread emails found.")
            print("  Send a test email to your mailbox and run this script again.")

    except GraphAPIError as e:
        print(f"  FAILED — {e}")
        print("\n  Troubleshooting:")
        print("  - Check GRAPH_API_MAILBOX matches your actual mailbox email")
        print("  - Make sure Mail.Read permission is granted (green checkmark)")
        print("  - Make sure admin consent was granted")
        failed += 1
        await graph.close()
        print(f"\n{'=' * 60}")
        print(f"Results: {passed} passed, {failed} failed")
        return

    # ---- Test 3: Fetch Single Message ----
    if messages:
        print("\n[TEST 3] Fetching first message in detail...")
        try:
            msg_id = messages[0]["id"]
            detail = await graph.fetch_message(msg_id)
            body_preview = detail.get("bodyPreview", "")[:100]
            has_attach = detail.get("hasAttachments", False)
            print("  PASSED — Message fetched successfully.")
            print(f"    Body preview: {body_preview}...")
            print(f"    Has attachments: {has_attach}")
            passed += 1

            # Test fetching attachments if present
            if has_attach:
                print("\n[TEST 3b] Fetching attachments...")
                attachments = await graph.fetch_attachments(msg_id)
                print(f"  PASSED — Found {len(attachments)} attachment(s).")
                for att in attachments:
                    name = att.get("name", "unnamed")
                    content_type = att.get("contentType", "unknown")
                    print(f"    - {name} ({content_type})")

        except GraphAPIError as e:
            print(f"  FAILED — {e}")
            failed += 1
    else:
        print("\n[TEST 3] Skipped — no messages to fetch.")

    # ---- Test 4: Mark as Read ----
    if messages:
        print("\n[TEST 4] Testing mark-as-read (Mail.ReadWrite permission)...")
        try:
            msg_id = messages[0]["id"]
            await graph.mark_as_read(msg_id)
            print("  PASSED — Mail.ReadWrite permission works.")
            passed += 1
        except GraphAPIError as e:
            print(f"  FAILED — {e}")
            print("  - Check Mail.ReadWrite permission is granted")
            failed += 1

    # ---- Summary ----
    print(f"\n{'=' * 60}")
    if failed == 0:
        print(f"ALL {passed} TESTS PASSED — Graph API is correctly configured!")
        print(f"{'=' * 60}")
        print(f"\nYour VQMS instance can now read emails from: {mailbox}")
        print("Next step: Run the email intake pipeline (Phase 2)")
    else:
        print(f"Results: {passed} passed, {failed} failed")
        print("Fix the issues above and run again.")

    await graph.close()


if __name__ == "__main__":
    asyncio.run(main())
