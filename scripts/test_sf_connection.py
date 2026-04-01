"""Module: scripts/test_sf_connection.py

Salesforce Connection Test Script for VQMS.

Verifies that VQMS can connect to Salesforce and query
the imported vendor data. Run this AFTER importing the
CSV files into your Salesforce Developer Org.

Tests performed:
  1. Connect to Salesforce using credentials from .env
  2. Query a specific vendor (V-001) by External ID
  3. Query contacts linked to that vendor
  4. Count all vendor accounts
  5. Count all vendor contacts
  6. Count all contracts

Usage:
  uv run python scripts/test_sf_connection.py
"""

from __future__ import annotations

import os
import sys

try:
    from dotenv import load_dotenv
except ImportError:
    print("ERROR: python-dotenv is required. Install with: uv add python-dotenv")
    sys.exit(1)

try:
    from simple_salesforce import Salesforce, SalesforceAuthenticationFailed
except ImportError:
    print("ERROR: simple-salesforce is required. Install with: uv add simple-salesforce")
    sys.exit(1)


def main() -> None:
    """Connect to Salesforce and run verification queries."""
    # Load environment variables from .env file
    load_dotenv()

    # Read credentials
    instance_url = os.getenv("SALESFORCE_INSTANCE_URL", "")
    username = os.getenv("SALESFORCE_USERNAME", "")
    password = os.getenv("SALESFORCE_PASSWORD", "")
    security_token = os.getenv("SALESFORCE_SECURITY_TOKEN", "")

    # Validate that credentials are present
    missing = []
    if not username:
        missing.append("SALESFORCE_USERNAME")
    if not password:
        missing.append("SALESFORCE_PASSWORD")
    if not security_token:
        missing.append("SALESFORCE_SECURITY_TOKEN")

    if missing:
        print("ERROR: Missing required environment variables in .env:")
        for var in missing:
            print(f"  - {var}")
        print("\nUpdate your .env file with Salesforce credentials.")
        print("See STEP 6 in the Salesforce import plan for instructions.")
        sys.exit(1)

    # Connect to Salesforce
    print("=" * 60)
    print("SALESFORCE CONNECTION TEST")
    print("=" * 60)
    print(f"\n  Username: {username}")
    print(f"  Instance: {instance_url or '(auto-detect)'}")

    try:
        # For Developer Edition orgs, do NOT pass domain="test"
        # domain="test" is only for sandbox orgs
        sf = Salesforce(
            username=username,
            password=password,
            security_token=security_token,
        )
        print(f"  Connected: YES")
        print(f"  API URL:   {sf.base_url}")
    except SalesforceAuthenticationFailed as e:
        print(f"\n  ERROR: Authentication failed!")
        print(f"  Details: {e}")
        print("\n  Troubleshooting:")
        print("  1. Verify username, password, and security token in .env")
        print("  2. Password field should be just your password (not password+token)")
        print("  3. Security token is sent via email — check for 'Salesforce security token' email")
        print("  4. If you recently changed your password, you need a new security token")
        sys.exit(1)

    # --- Test 1: Query a specific vendor ---
    print("\n--- Test 1: Query vendor V-001 ---")
    try:
        result = sf.query(
            "SELECT Vendor_ID__c, Name, Vendor_Tier__c, Category__c, "
            "SLA_Response_Hours__c, BillingCity, BillingState "
            "FROM Account "
            "WHERE Vendor_ID__c = 'V-001'"
        )
        if result["totalSize"] == 1:
            record = result["records"][0]
            print(f"  PASS: Found vendor V-001")
            print(f"    Name:     {record['Name']}")
            print(f"    Tier:     {record['Vendor_Tier__c']}")
            print(f"    Category: {record['Category__c']}")
            print(f"    SLA Hrs:  {record['SLA_Response_Hours__c']}")
            print(f"    City:     {record['BillingCity']}, {record['BillingState']}")
        else:
            print(f"  FAIL: Expected 1 record, got {result['totalSize']}")
    except Exception as e:
        print(f"  ERROR: {e}")

    # --- Test 2: Query contacts for V-001 ---
    print("\n--- Test 2: Query contacts for V-001 ---")
    try:
        result = sf.query(
            "SELECT FirstName, LastName, Email, Title, Contact_Type__c "
            "FROM Contact "
            "WHERE Account.Vendor_ID__c = 'V-001'"
        )
        print(f"  PASS: Found {result['totalSize']} contacts for V-001")
        for record in result["records"]:
            print(
                f"    - {record['FirstName']} {record['LastName']} "
                f"({record['Title']}, {record['Contact_Type__c']})"
            )
    except Exception as e:
        print(f"  ERROR: {e}")

    # --- Test 3: Count all vendor accounts ---
    print("\n--- Test 3: Count all vendor accounts ---")
    try:
        result = sf.query(
            "SELECT COUNT() FROM Account WHERE Vendor_ID__c LIKE 'V-%'"
        )
        count = result["totalSize"]
        status = "PASS" if count == 25 else "WARN"
        print(f"  {status}: {count} vendor accounts (expected 25)")
    except Exception as e:
        print(f"  ERROR: {e}")

    # --- Test 4: Count all contacts ---
    print("\n--- Test 4: Count all vendor contacts ---")
    try:
        result = sf.query(
            "SELECT COUNT() FROM Contact WHERE Contact_ID__c LIKE 'VC-%'"
        )
        count = result["totalSize"]
        status = "PASS" if count == 50 else "WARN"
        print(f"  {status}: {count} contacts (expected 50)")
    except Exception as e:
        print(f"  ERROR: {e}")

    # --- Test 5: Count all contracts ---
    print("\n--- Test 5: Count all contracts ---")
    try:
        result = sf.query(
            "SELECT COUNT() FROM Contract WHERE Contract_ID__c LIKE 'CNT-%'"
        )
        count = result["totalSize"]
        status = "PASS" if count == 25 else "WARN"
        print(f"  {status}: {count} contracts (expected 25)")
    except Exception as e:
        print(f"  ERROR: {e}")

    # --- Test 6: Verify vendor tier distribution ---
    print("\n--- Test 6: Vendor tier distribution ---")
    try:
        result = sf.query(
            "SELECT Vendor_Tier__c, COUNT(Id) cnt "
            "FROM Account "
            "WHERE Vendor_ID__c LIKE 'V-%' "
            "GROUP BY Vendor_Tier__c "
            "ORDER BY Vendor_Tier__c"
        )
        for record in result["records"]:
            print(f"    {record['Vendor_Tier__c']}: {record['cnt']} vendors")
    except Exception as e:
        print(f"  ERROR: {e}")

    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
