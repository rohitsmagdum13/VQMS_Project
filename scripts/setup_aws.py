"""Provision all AWS resources needed for VQMS.

Creates S3 buckets, SQS queues (with DLQ), and EventBridge bus.
Idempotent — skips resources that already exist.

Run with: uv run python scripts/setup_aws.py
"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()

import boto3
from botocore.exceptions import ClientError

REGION = os.getenv("AWS_REGION", "us-east-1")


def create_s3_buckets() -> tuple[int, int]:
    """Create the 4 VQMS S3 buckets. Returns (passed, failed)."""
    print("\n[S3] Creating buckets...")
    s3 = boto3.client("s3", region_name=REGION)

    buckets = [
        os.getenv("S3_BUCKET_EMAIL_RAW", "vqms-email-raw-dev"),
        os.getenv("S3_BUCKET_ATTACHMENTS", "vqms-email-attachments-dev"),
        os.getenv("S3_BUCKET_AUDIT_ARTIFACTS", "vqms-audit-artifacts-dev"),
        os.getenv("S3_BUCKET_KNOWLEDGE", "vqms-knowledge-artifacts-dev"),
    ]

    passed = 0
    failed = 0

    for bucket in buckets:
        try:
            s3.head_bucket(Bucket=bucket)
            print(f"  {bucket} -- ALREADY EXISTS (skipped)")
            passed += 1
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code in ("404", "NoSuchBucket"):
                # Bucket doesn't exist — create it
                try:
                    # us-east-1 doesn't use LocationConstraint
                    if REGION == "us-east-1":
                        s3.create_bucket(Bucket=bucket)
                    else:
                        s3.create_bucket(
                            Bucket=bucket,
                            CreateBucketConfiguration={
                                "LocationConstraint": REGION
                            },
                        )

                    # Block all public access
                    s3.put_public_access_block(
                        Bucket=bucket,
                        PublicAccessBlockConfiguration={
                            "BlockPublicAcls": True,
                            "IgnorePublicAcls": True,
                            "BlockPublicPolicy": True,
                            "RestrictPublicBuckets": True,
                        },
                    )
                    print(f"  {bucket} -- CREATED")
                    passed += 1
                except ClientError as create_err:
                    print(f"  {bucket} -- FAILED: {create_err}")
                    failed += 1
            else:
                print(f"  {bucket} -- FAILED: {e}")
                failed += 1

    return passed, failed


def create_sqs_queues() -> tuple[int, int]:
    """Create 11 SQS queues (DLQ first, then 10 main queues). Returns (passed, failed)."""
    print("\n[SQS] Creating queues...")
    sqs = boto3.client("sqs", region_name=REGION)

    passed = 0
    failed = 0

    # Step 1: Create the Dead Letter Queue first
    dlq_name = "vqms-dlq"
    dlq_arn = None

    try:
        response = sqs.get_queue_url(QueueName=dlq_name)
        print(f"  {dlq_name} -- ALREADY EXISTS (skipped)")
        # Get the ARN for linking to other queues
        dlq_url = response["QueueUrl"]
        attrs = sqs.get_queue_attributes(
            QueueUrl=dlq_url, AttributeNames=["QueueArn"]
        )
        dlq_arn = attrs["Attributes"]["QueueArn"]
        passed += 1
    except ClientError as e:
        if "NonExistentQueue" in str(e):
            try:
                response = sqs.create_queue(
                    QueueName=dlq_name,
                    Attributes={
                        "VisibilityTimeout": "300",
                        "MessageRetentionPeriod": "1209600",  # 14 days
                        "ReceiveMessageWaitTimeSeconds": "20",
                    },
                )
                dlq_url = response["QueueUrl"]
                attrs = sqs.get_queue_attributes(
                    QueueUrl=dlq_url, AttributeNames=["QueueArn"]
                )
                dlq_arn = attrs["Attributes"]["QueueArn"]
                print(f"  {dlq_name} -- CREATED")
                passed += 1
            except ClientError as create_err:
                print(f"  {dlq_name} -- FAILED: {create_err}")
                failed += 1
        else:
            print(f"  {dlq_name} -- FAILED: {e}")
            failed += 1

    if dlq_arn is None:
        print("  ERROR: Cannot create main queues without DLQ ARN.")
        return passed, failed + 10

    # Step 2: Create the 10 main queues with DLQ redrive policy
    import json

    redrive_policy = json.dumps({
        "deadLetterTargetArn": dlq_arn,
        "maxReceiveCount": "3",
    })

    queue_names = [
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

    for queue_name in queue_names:
        try:
            sqs.get_queue_url(QueueName=queue_name)
            print(f"  {queue_name} -- ALREADY EXISTS (skipped)")
            passed += 1
        except ClientError as e:
            if "NonExistentQueue" in str(e):
                try:
                    sqs.create_queue(
                        QueueName=queue_name,
                        Attributes={
                            "VisibilityTimeout": "300",
                            "MessageRetentionPeriod": "345600",  # 4 days
                            "ReceiveMessageWaitTimeSeconds": "20",
                            "RedrivePolicy": redrive_policy,
                        },
                    )
                    print(f"  {queue_name} -- CREATED")
                    passed += 1
                except ClientError as create_err:
                    print(f"  {queue_name} -- FAILED: {create_err}")
                    failed += 1
            else:
                print(f"  {queue_name} -- FAILED: {e}")
                failed += 1

    return passed, failed


def create_eventbridge_bus() -> tuple[int, int]:
    """Create the VQMS EventBridge bus. Returns (passed, failed)."""
    print("\n[EventBridge] Creating event bus...")
    events = boto3.client("events", region_name=REGION)

    bus_name = os.getenv("EVENTBRIDGE_BUS_NAME", "vqms-event-bus")

    try:
        events.describe_event_bus(Name=bus_name)
        print(f"  {bus_name} -- ALREADY EXISTS (skipped)")
        return 1, 0
    except ClientError as e:
        if "ResourceNotFoundException" in str(e):
            try:
                events.create_event_bus(Name=bus_name)
                print(f"  {bus_name} -- CREATED")
                return 1, 0
            except ClientError as create_err:
                print(f"  {bus_name} -- FAILED: {create_err}")
                return 0, 1
        else:
            print(f"  {bus_name} -- FAILED: {e}")
            return 0, 1


def main() -> None:
    print("=" * 60)
    print("VQMS -- AWS Resource Provisioning")
    print("=" * 60)
    print(f"Region: {REGION}")

    total_passed = 0
    total_failed = 0

    # S3
    p, f = create_s3_buckets()
    total_passed += p
    total_failed += f

    # SQS
    p, f = create_sqs_queues()
    total_passed += p
    total_failed += f

    # EventBridge
    p, f = create_eventbridge_bus()
    total_passed += p
    total_failed += f

    # Summary
    print(f"\n{'=' * 60}")
    if total_failed == 0:
        print(f"ALL {total_passed} RESOURCES READY!")
    else:
        print(f"Results: {total_passed} ready, {total_failed} failed")
    print("=" * 60)


if __name__ == "__main__":
    main()
