"""Verify AWS resources: S3 buckets, SQS queues, EventBridge bus.

Run with: uv run python scripts/test_aws.py
"""

import os
import sys

# Fix Windows console encoding for unicode characters
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

import boto3
from botocore.exceptions import ClientError


def main() -> None:
    print("=" * 60)
    print("VQMS — AWS Resources Verification")
    print("=" * 60)

    region = os.getenv("AWS_REGION", "us-east-1")
    print(f"\nRegion: {region}")
    print("-" * 60)

    passed = 0
    failed = 0

    # ---- Test 1: AWS Credentials ----
    print("\n[TEST 1] Verifying AWS credentials...")
    try:
        sts = boto3.client("sts", region_name=region)
        identity = sts.get_caller_identity()
        account_id = identity["Account"]
        arn = identity["Arn"]
        print(f"  PASSED — Authenticated as: {arn}")
        print(f"    Account ID: {account_id}")
        passed += 1
    except ClientError as e:
        print(f"  FAILED — {e}")
        print("\n  Troubleshooting:")
        print("  - Check AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in .env")
        print("  - Remove AWS_SESSION_TOKEN if not using temporary credentials")
        failed += 1
        print(f"\n{'=' * 60}")
        print(f"Results: {passed} passed, {failed} failed")
        print("Fix AWS credentials first, then run again.")
        return

    # ---- Test 2: S3 Buckets ----
    print("\n[TEST 2] Checking S3 buckets...")
    s3 = boto3.client("s3", region_name=region)
    buckets = [
        os.getenv("S3_BUCKET_EMAIL_RAW", "vqms-email-raw-dev"),
        os.getenv("S3_BUCKET_ATTACHMENTS", "vqms-email-attachments-dev"),
        os.getenv("S3_BUCKET_AUDIT_ARTIFACTS", "vqms-audit-artifacts-dev"),
        os.getenv("S3_BUCKET_KNOWLEDGE", "vqms-knowledge-artifacts-dev"),
    ]

    s3_all_ok = True
    for bucket in buckets:
        try:
            s3.head_bucket(Bucket=bucket)
            print(f"  {bucket} — EXISTS")
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "404":
                print(f"  {bucket} — NOT FOUND (create it in S3 console)")
            elif error_code == "403":
                print(f"  {bucket} — ACCESS DENIED (check IAM permissions)")
            else:
                print(f"  {bucket} — ERROR: {e}")
            s3_all_ok = False

    if s3_all_ok:
        print(f"\n  PASSED — All 4 S3 buckets exist and are accessible.")
        passed += 1
    else:
        print(f"\n  FAILED — Some buckets are missing or inaccessible.")
        failed += 1

    # ---- Test 3: S3 Upload/Download ----
    if s3_all_ok:
        print("\n[TEST 3] Testing S3 upload/download...")
        test_bucket = buckets[0]
        test_key = "_vqms_test/connection_check.txt"
        test_content = b"VQMS connection test"
        try:
            s3.put_object(Bucket=test_bucket, Key=test_key, Body=test_content)
            response = s3.get_object(Bucket=test_bucket, Key=test_key)
            downloaded = response["Body"].read()
            assert downloaded == test_content
            s3.delete_object(Bucket=test_bucket, Key=test_key)
            print(f"  PASSED — Upload, download, delete all work on {test_bucket}.")
            passed += 1
        except ClientError as e:
            print(f"  FAILED — {e}")
            failed += 1
    else:
        print("\n[TEST 3] Skipped — S3 buckets not available.")

    # ---- Test 4: SQS Queues ----
    print("\n[TEST 4] Checking SQS queues...")
    sqs = boto3.client("sqs", region_name=region)
    queue_names = [
        "vqms-dlq",
        "vqms-email-intake",
        "vqms-analysis",
        "vqms-vendor-resolution",
        "vqms-ticket-ops",
        "vqms-routing",
        "vqms-communication",
        "vqms-escalation",
        "vqms-human-review",
        "vqms-audit",
        "vqms-notification",
    ]

    sqs_all_ok = True
    for queue_name in queue_names:
        try:
            response = sqs.get_queue_url(QueueName=queue_name)
            print(f"  {queue_name} — EXISTS")
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "AWS.SimpleQueueService.NonExistentQueue":
                print(f"  {queue_name} — NOT FOUND (create it in SQS console)")
            else:
                print(f"  {queue_name} — ERROR: {e}")
            sqs_all_ok = False

    if sqs_all_ok:
        print(f"\n  PASSED — All 11 SQS queues exist.")
        passed += 1
    else:
        print(f"\n  FAILED — Some queues are missing.")
        failed += 1

    # ---- Test 5: SQS Send/Receive ----
    if sqs_all_ok:
        print("\n[TEST 5] Testing SQS send/receive...")
        try:
            queue_url = sqs.get_queue_url(QueueName="vqms-dlq")["QueueUrl"]
            sqs.send_message(
                QueueUrl=queue_url,
                MessageBody='{"test": "vqms_connection_check"}',
            )
            response = sqs.receive_message(
                QueueUrl=queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=5
            )
            messages = response.get("Messages", [])
            if messages:
                sqs.delete_message(
                    QueueUrl=queue_url,
                    ReceiptHandle=messages[0]["ReceiptHandle"],
                )
                print(f"  PASSED — Send, receive, delete all work on vqms-dlq.")
                passed += 1
            else:
                print(f"  WARNING — Message sent but not received (may need longer wait).")
                failed += 1
        except ClientError as e:
            print(f"  FAILED — {e}")
            failed += 1
    else:
        print("\n[TEST 5] Skipped — SQS queues not available.")

    # ---- Test 6: EventBridge ----
    print("\n[TEST 6] Checking EventBridge bus...")
    events = boto3.client("events", region_name=region)
    bus_name = os.getenv("EVENTBRIDGE_BUS_NAME", "vqms-event-bus")
    try:
        events.describe_event_bus(Name=bus_name)
        print(f"  PASSED — Event bus '{bus_name}' exists.")
        passed += 1
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "ResourceNotFoundException":
            print(f"  FAILED — Event bus '{bus_name}' not found.")
            print("    Create it in EventBridge console → Event buses → Create event bus")
        else:
            print(f"  FAILED — {e}")
        failed += 1

    # ---- Summary ----
    print(f"\n{'=' * 60}")
    if failed == 0:
        print(f"ALL {passed} TESTS PASSED — AWS resources are correctly configured!")
    else:
        print(f"Results: {passed} passed, {failed} failed")
        print("\nCreate missing resources, then run this script again.")
    print("=" * 60)


if __name__ == "__main__":
    main()
