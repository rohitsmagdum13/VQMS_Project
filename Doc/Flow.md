# VQMS -- how an email moves through the system

A step-by-step walkthrough of every single thing that happens when a vendor
sends an email. Uses real data from our first production email (TechNova
Solutions asking about Invoice #INV-2026-0451).

Steps 1-6 have working code. Steps 7-15 are designed but not built yet.

Last updated: 2026-04-01

---


STEP 1: VENDOR SENDS EMAIL  [BUILT -- no code needed, external trigger]
═══════════════════════════════════════════════════════════════════════════

```
    Rajesh Mehta
    Accounts & Finance
    TechNova Solutions Pvt. Ltd.
     |
     |  Subject: "Payment Status Inquiry - Invoice #INV-2026-0451
     |            | TechNova Solutions Pvt. Ltd."
     |
     |  Body: "...Vendor Code: VN-30892...Invoice: INV-2026-0451
     |         ...Amount: 4,75,000.00...PO: PO-HEX-78412
     |         ...Due Date: 17th March 2026 (past due)..."
     |
     |  Attachment: Invoice_INV-2026-0451.pdf
     |    (TechNova -> Hexaware, Total: 5,60,500.00 incl. GST)
     |    Line items:
     |      AI/ML Consulting .......... 3,50,000.00
     |      Cloud Infrastructure ...... 75,000.00
     |      Data Pipeline Dev ......... 50,000.00
     |      CGST 9% ................... 42,750.00
     |      SGST 9% ................... 42,750.00
     |
     v
    RohitMagdum@VQMS13.onmicrosoft.com
    (Exchange Online shared mailbox)
```

WHAT HAPPENS: Rajesh Mehta from TechNova Solutions has an overdue invoice. He
sends an email to the company support mailbox asking what's going on with the
payment. He attaches the original invoice PDF as proof. The due date was
17th March 2026 -- it's now April, so he's been waiting two weeks. The system
picks it up from here. Rajesh doesn't know or care about any of this pipeline.
He just wants his money.

**Real data from this email:**
```
From:        rohitsmagdum13@gmail.com (Rohit Magdum)
To:          RohitMagdum@VQMS13.onmicrosoft.com
Subject:     Payment Status Inquiry – Invoice #INV-2026-0451 | TechNova Solutions Pvt. Ltd.
Received:    2026-04-01T05:47:20.000Z
Attachment:  Invoice_INV-2026-0451.pdf (PDF, ~4KB)
```

**Entities in the email body:**
```
Vendor Code:    VN-30892
Invoice Number: INV-2026-0451
Invoice Date:   15th February 2026
Amount:         4,75,000.00 (subtotal, 5,60,500 with GST)
PO Number:      PO-HEX-78412
Due Date:       17th March 2026
Contact:        Rajesh Mehta, +91 98765 43210, rajesh.mehta@technovasolutions.in
```

**Storage:** Exchange Online mailbox only. Nothing in our systems yet.


---


STEP 2: SYSTEM DETECTS THE EMAIL  [BUILT]
═══════════════════════════════════════════

```
    [Exchange Online Mailbox]
     |
     |  Two detection methods (belt and suspenders):
     |
     +---> PRIMARY: Webhook push notification
     |     (Graph API sends change notification within ~5 seconds)
     |
     +---> BACKUP: Polling every 60 seconds
           |
           v
    +=============================================+
    | poll_for_new_emails()                       |
    | src/services/email_intake.py : line 303     |
    +=============================================+
           |
           | calls
           v
    +=============================================+
    | GraphAPIAdapter.list_unread_messages()       |
    | src/adapters/graph_api.py : line 209         |
    |                                              |
    | GET https://graph.microsoft.com/v1.0/        |
    |   users/RohitMagdum@VQMS13.                  |
    |   onmicrosoft.com/messages                   |
    |   ?$filter=isRead eq false                   |
    |   &$orderby=receivedDateTime desc            |
    |   &$top=50                                   |
    +=============================================+
           |
           | OAuth token via MSAL (cached, auto-refreshes)
           | Returns: list of unread message dicts
           |
           v
    +---------------------------------------------+
    | Found 1 unread message:                      |
    |   id: "AAMkADhhNTY3YmY1LWJiYmUt..."        |
    |   subject: "Payment Status Inquiry..."       |
    |   hasAttachments: true                        |
    +---------------------------------------------+
           |
           | for each message_id:
           v
    +=============================================+
    | process_single_email(message_id, ...)        |
    | src/services/email_intake.py : line 51       |
    +=============================================+
```

WHAT HAPPENS: The system checks Exchange Online for new emails. In production,
Microsoft pushes a webhook notification the moment an email lands -- that's the
fast path. But webhooks can fail (network blip, subscription expired, whatever),
so there's a backup poller that runs every 60 seconds and asks "any unread
messages?" The poller calls `list_unread_messages()` which hits the Graph API,
gets back a list, and feeds each message ID into `process_single_email()`.

For our TechNova email, the poller finds one unread message and starts
processing it.

**Code path:**
```
poll_for_new_emails()                         src/services/email_intake.py:303
  -> GraphAPIAdapter.list_unread_messages()   src/adapters/graph_api.py:209
       -> _get_access_token()                 src/adapters/graph_api.py:87
       -> _make_request("GET", url)           src/adapters/graph_api.py:111
  -> process_single_email(message_id, ...)    src/services/email_intake.py:51
```

**Storage:** Nothing written yet. This is a read-only step.


---


STEP 3: IDEMPOTENCY CHECK -- IS THIS A DUPLICATE?  [BUILT]
════════════════════════════════════════════════════════════

```
    message_id: "AAMkADhhNTY3YmY1LWJiYmUt..."
           |
           |  Generate correlation ID (if not provided):
           |  vqms-bc1357d5-6731-4ffe-bd4a-8f2859afaefd
           |
           v
    +=============================================+
    | RedisClient.get_idempotency(message_id)     |
    | src/cache/redis_client.py : line 184         |
    |                                              |
    | GET vqms:idempotency:AAMkADhhNTY3YmY1L...   |
    +=============================================+
           |                    |
           |                    |
      key EXISTS            key MISSING
      (duplicate)           (new email)
           |                    |
           v                    v
    +--------------+    +------------------+
    | Log:         |    | Continue to      |
    | "Duplicate   |    | Step 4           |
    |  detected"   |    |                  |
    | return None  |    | This email is    |
    +--------------+    | brand new        |
                        +------------------+
```

WHAT HAPPENS: Before doing any real work, we check Redis to see if we've already
processed this email. Exchange Online can redeliver the same email multiple times
(up to 5 days later during recovery scenarios). We don't want to create duplicate
tickets or send duplicate acknowledgments.

The check is simple: look up `vqms:idempotency:{message_id}` in Redis. If the
key exists, we've seen this one before -- log it and bail. If it's missing, this
is a fresh email and we keep going.

For our TechNova email, this is the first time we're seeing it, so the key
doesn't exist. We continue to Step 4.

**Code path:**
```
process_single_email()                        src/services/email_intake.py:85
  -> generate_correlation_id()                src/utils/correlation.py:23
       returns: "vqms-bc1357d5-6731-4ffe-bd4a-8f2859afaefd"
  -> redis_client.get_idempotency(msg_id)     src/cache/redis_client.py:184
       builds key: "vqms:idempotency:AAMkADhhNTY3YmY1LWJiYmUt..."
       result: None (key does not exist)
```

**Redis key checked:**
```
Key:    vqms:idempotency:AAMkADhhNTY3YmY1LWJiYmUtNGYwYy1hZGJiLTgyZDAzNDY0MDQ5NABGAAAAAABvGz37CERNRJDLSDF4mXl2BwC6sKXNjFBNRquyL8NknMDUAAAAAAEMAAC6sKXNjFBNRquyL8NknMDUAAABFZLhAAA=
Result: nil (not found -- new email)
```

**Storage:** Read-only. No writes yet. The idempotency key gets set later
(Step 5, after we've safely stored everything) so that a crash mid-pipeline
doesn't silently drop the email.


---


STEP 4: SAVE RAW EMAIL TO S3  [BUILT]
══════════════════════════════════════

```
    message_id + correlation_id
           |
           v
    +=============================================+
    | GraphAPIAdapter.fetch_message(message_id)    |
    | src/adapters/graph_api.py : line 170         |
    |                                              |
    | GET /users/{mailbox}/messages/{message_id}   |
    +=============================================+
           |
           | Full Graph API JSON response
           | (sender, body, headers, timestamps, everything)
           |
           v
    +=============================================+
    | orjson.dumps(raw_email)                      |
    | Serialize to bytes                           |
    +=============================================+
           |
           v
    +=============================================+
    | S3Client.upload_raw_email()                  |
    | src/storage/s3_client.py : line 84           |
    |                                              |
    | boto3 put_object -> vqms-email-raw-prod      |
    +=============================================+
           |
           v
    +---------------------------------------------+
    | S3: vqms-email-raw-prod                      |
    |                                              |
    | raw-emails/                                  |
    |   2026-04-01/                                |
    |     vqms-bc1357d5-6731-4ffe-bd4a-.../        |
    |       vqms-bc1357d5-6731-4ffe-bd4a-...json   |
    +---------------------------------------------+
```

WHAT HAPPENS: We fetch the full email from Graph API and immediately dump the
raw JSON into S3 before doing anything else. This is the safety net. If our
parsing code has a bug, if our database goes down, if we somehow mangle the
data -- the original email is sitting untouched in S3 and we can reprocess it.

We use the correlation_id as the folder name (not the message_id, which is a
giant ugly Exchange string). Makes it easy to find in the S3 console.

**Code path:**
```
process_single_email()                        src/services/email_intake.py:110
  -> graph_api.fetch_message(message_id)      src/adapters/graph_api.py:170
  -> orjson.dumps(raw_email)                  inline, line 186
  -> s3_client.upload_raw_email(              src/storage/s3_client.py:84
       message_id, raw_bytes,
       correlation_id="vqms-bc1357d5-..."
     )
```

**Storage write:**
```
Bucket:       vqms-email-raw-prod
Key:          raw-emails/2026-04-01/vqms-bc1357d5-6731-4ffe-bd4a-8f2859afaefd/vqms-bc1357d5-6731-4ffe-bd4a-8f2859afaefd.json
Content-Type: application/json
Contents:     Full Graph API message JSON (body, headers, sender, timestamps)
```

After raw storage, we also fetch and store the attachment:

```
    has_attachments == true?
           |
          YES
           |
           v
    +=============================================+
    | GraphAPIAdapter.fetch_attachments()           |
    | src/adapters/graph_api.py : line 245          |
    |                                               |
    | GET /messages/{id}/attachments                |
    +=============================================+
           |
           | base64 decode each attachment
           v
    +=============================================+
    | S3Client.upload_attachment()                  |
    | src/storage/s3_client.py : line 169           |
    +=============================================+
           |
           v
    +---------------------------------------------+
    | S3: vqms-email-attachments-prod              |
    |                                              |
    | attachments/                                 |
    |   2026-04-01/                                |
    |     vqms-bc1357d5-6731-4ffe-bd4a-.../        |
    |       Invoice_INV-2026-0451.pdf              |
    +---------------------------------------------+
```

**Attachment storage:**
```
Bucket:       vqms-email-attachments-prod
Key:          attachments/2026-04-01/vqms-bc1357d5-6731-4ffe-bd4a-8f2859afaefd/Invoice_INV-2026-0451.pdf
Content-Type: application/pdf
Size:         ~4KB
```

**EmailAttachment model built:**
```python
EmailAttachment(
    filename="Invoice_INV-2026-0451.pdf",
    mime_type="application/pdf",
    file_size_bytes=4096,
    s3_path="attachments/2026-04-01/vqms-bc1357d5-.../Invoice_INV-2026-0451.pdf"
)
```


---


STEP 5: PARSE EMAIL AND STORE IN POSTGRESQL  [BUILT]
═════════════════════════════════════════════════════

```
    Raw Graph API JSON
           |
           |  Extract fields:
           |
           |  sender_email  = "rohitsmagdum13@gmail.com"
           |  sender_name   = "Rohit Magdum"
           |  to_address    = "RohitMagdum@VQMS13.onmicrosoft.com"
           |  subject       = "Payment Status Inquiry - Invoice #INV-2026-0451..."
           |  body_html     = "<html>Dear Accounts Payable Team..."
           |  body_plain    = html_to_plain_text(body_html)
           |  received_at   = 2026-04-01T05:47:20Z -> converted to IST
           |  thread_id     = "AAQkADhhNTY3YmY1LWJiYmUt..."
           |  is_reply      = false (subject doesn't start with "Re:")
           |  is_auto_reply = false (no auto-submitted header)
           |  has_attachments = true
           |
           v
    +=============================================+
    | _write_email_to_database()                   |
    | src/services/email_intake.py : line 385      |
    |                                              |
    | Uses DatabasePool.fetchrow()                 |
    | src/db/connection.py : line 142              |
    +=============================================+
           |                        |
           v                        v
    +-------------------+   +----------------------+
    | INSERT INTO       |   | INSERT INTO          |
    | intake.email_     |   | intake.email_        |
    |   messages        |   |   attachments        |
    |                   |   |                      |
    | RETURNING id      |   | (1 row for the PDF)  |
    +-------------------+   +----------------------+
           |
           |  email_db_id = 1
           v
    +=============================================+
    | RedisClient.set_idempotency(message_id, {   |
    |   correlation_id: "vqms-bc1357d5-...",      |
    |   processed_at:   "2026-04-01T11:17:33",    |
    |   email_db_id:    1                          |
    | })                                           |
    | src/cache/redis_client.py : line 177         |
    +=============================================+
           |
           | SETEX with 7-day TTL (604800 seconds)
           v
    +---------------------------------------------+
    | Redis: vqms:idempotency:AAMkADhhNTY3...     |
    | TTL: 7 days                                  |
    | Value: {"correlation_id":"vqms-bc1357d5-...",|
    |  "processed_at":"2026-04-01T11:17:33",       |
    |  "email_db_id":1}                            |
    +---------------------------------------------+
```

WHAT HAPPENS: Now we take the raw Graph API response and pull out every field
we care about. Sender, recipient, subject, body, timestamps, thread info,
reply detection. The HTML body gets converted to plain text using
`html_to_plain_text()` so downstream agents can read it without parsing HTML.

Timestamps get converted from UTC to IST (UTC+5:30) since all our timestamps
are stored in IST.

Then we write two things to PostgreSQL:
1. The email metadata goes into `intake.email_messages`
2. Each attachment gets a row in `intake.email_attachments`

After the database write succeeds, we set the Redis idempotency key. The
ordering matters here -- if we set the key first and then the DB write fails,
we'd never retry the email. By setting the key last, a failed write means no
key, which means the poller will retry it next cycle.

**Code path:**
```
process_single_email()                        src/services/email_intake.py:115-180
  -> html_to_plain_text(body_html)            src/utils/helpers.py
  -> _write_email_to_database(...)            src/services/email_intake.py:385
       -> db_pool.fetchrow(INSERT...)         src/db/connection.py:142
       -> db_pool.execute(INSERT...)          src/db/connection.py:107
  -> redis_client.set_idempotency(...)        src/cache/redis_client.py:177
```

**PostgreSQL write -- intake.email_messages:**
```sql
INSERT INTO intake.email_messages
  (message_id, correlation_id, sender_email, sender_name,
   to_address, cc_addresses, subject, body_plain,
   received_at, s3_raw_path, has_attachments, attachment_count,
   thread_id, is_reply, is_auto_reply, parsed_at)
VALUES
  ('AAMkADhhNTY3YmY1LWJiYmUt...',
   'vqms-bc1357d5-6731-4ffe-bd4a-8f2859afaefd',
   'rohitsmagdum13@gmail.com',
   'Rohit Magdum',
   'RohitMagdum@VQMS13.onmicrosoft.com',
   NULL,
   'Payment Status Inquiry – Invoice #INV-2026-0451 | TechNova Solutions Pvt. Ltd.',
   'Dear Accounts Payable Team, I hope this message finds you well...',
   '2026-04-01 11:17:20',
   'raw-emails/2026-04-01/vqms-bc1357d5-.../vqms-bc1357d5-...json',
   true, 1,
   'AAQkADhhNTY3YmY1LWJiYmUt...',
   false, false,
   CURRENT_TIMESTAMP)
RETURNING id
```

**PostgreSQL write -- intake.email_attachments:**
```sql
INSERT INTO intake.email_attachments
  (message_id, filename, file_size_bytes, mime_type, s3_path)
VALUES
  (1, 'Invoice_INV-2026-0451.pdf', 4096, 'application/pdf',
   'attachments/2026-04-01/vqms-bc1357d5-.../Invoice_INV-2026-0451.pdf')
```

**Redis write:**
```
Key:   vqms:idempotency:AAMkADhhNTY3YmY1LWJiYmUtNGYwYy1hZGJi...
TTL:   604800 seconds (7 days)
Value: {"correlation_id":"vqms-bc1357d5-6731-4ffe-bd4a-8f2859afaefd",
        "processed_at":"2026-04-01T11:17:33","email_db_id":1}
```

**The row in our database (from results1.json):**
```json
{
  "id": "1",
  "message_id": "AAMkADhhNTY3YmY1LWJiYmUtNGYwYy1hZGJiLTgyZDAzNDY0MDQ5NABGAAAAAABvGz37CERNRJDLSDF4mXl2BwC6sKXNjFBNRquyL8NknMDUAAAAAAEMAAC6sKXNjFBNRquyL8NknMDUAAABFZLhAAA=",
  "correlation_id": "vqms-bc1357d5-6731-4ffe-bd4a-8f2859afaefd",
  "sender_email": "rohitsmagdum13@gmail.com",
  "sender_name": "Rohit Magdum",
  "to_address": "RohitMagdum@VQMS13.onmicrosoft.com",
  "cc_addresses": null,
  "subject": "Payment Status Inquiry – Invoice #INV-2026-0451 | TechNova Solutions Pvt. Ltd.",
  "body_plain": "Dear Accounts Payable Team, I hope this message finds you well...",
  "received_at": "2026-04-01T05:47:20.000Z",
  "parsed_at": "2026-04-01T05:47:33.620Z",
  "s3_raw_path": "raw-emails/2026-04-01/vqms-bc1357d5-6731-4ffe-bd4a-8f2859afaefd/vqms-bc1357d5-6731-4ffe-bd4a-8f2859afaefd.json",
  "has_attachments": true,
  "attachment_count": 1,
  "thread_id": "AAQkADhhNTY3YmY1LWJiYmUtNGYwYy1hZGJiLTgyZDAzNDY0MDQ5NAAQAJQPQ6OmkO5IqgsTfIpslas=",
  "is_reply": false,
  "is_auto_reply": false,
  "language": "en",
  "status": "INGESTED",
  "is_duplicate": false
}
```


---


STEP 6: PUBLISH EVENTS AND PUSH TO QUEUE  [BUILT]
═══════════════════════════════════════════════════

```
    ParsedEmailPayload (built from all the parsed data)
           |
           +---> EventBridge
           |        |
           |        v
           |     +------------------------------------------+
           |     | EventBridgePublisher                     |
           |     |   .publish_email_received()              |
           |     | src/events/eventbridge.py : line 117     |
           |     |                                          |
           |     | Event: "EmailReceived"                   |
           |     | Bus:   vqms-event-bus                    |
           |     | Source: com.vqms                         |
           |     | Detail: {                                |
           |     |   message_id: "AAMkADhh...",            |
           |     |   sender_email: "rohitsmagdum13@...",    |
           |     |   subject: "Payment Status...",          |
           |     |   received_at: "2026-04-01T05:47:20Z",  |
           |     |   correlation_id: "vqms-bc1357d5-..."   |
           |     | }                                        |
           |     +------------------------------------------+
           |
           +---> EventBridge (again)
           |        |
           |        v
           |     +------------------------------------------+
           |     | EventBridgePublisher                     |
           |     |   .publish_email_parsed()                |
           |     | src/events/eventbridge.py : line 142     |
           |     |                                          |
           |     | Event: "EmailParsed"                     |
           |     | Detail: {                                |
           |     |   message_id: "AAMkADhh...",            |
           |     |   correlation_id: "vqms-bc1357d5-...",  |
           |     |   s3_raw_path: "raw-emails/2026-04-01/..|
           |     |   has_attachments: true,                 |
           |     |   attachment_count: 1                    |
           |     | }                                        |
           |     +------------------------------------------+
           |
           +---> SQS
           |        |
           |        v
           |     +------------------------------------------+
           |     | SQSClient.send_message(                  |
           |     |   "vqms-analysis",                       |
           |     |   parsed_payload.model_dump(mode="json"),|
           |     |   correlation_id="vqms-bc1357d5-..."     |
           |     | )                                        |
           |     | src/queues/sqs.py : line 115             |
           |     +------------------------------------------+
           |        |
           |        v
           |     +------------------------------------------+
           |     | SQS: vqms-analysis                       |
           |     | Message body: full ParsedEmailPayload    |
           |     | Message attribute: correlation_id        |
           |     +------------------------------------------+
           |
           +---> Mark as read
                    |
                    v
                 +------------------------------------------+
                 | GraphAPIAdapter.mark_as_read()            |
                 | src/adapters/graph_api.py : line 283      |
                 |                                           |
                 | PATCH /messages/{id}  {"isRead": true}    |
                 | (best-effort, non-fatal on failure)       |
                 +------------------------------------------+
```

WHAT HAPPENS: The email is now safely stored in S3, PostgreSQL, and Redis. Time
to tell the rest of the system about it.

Two EventBridge events fire: `EmailReceived` (a new email showed up) and
`EmailParsed` (we're done processing it). Any service subscribed to the event
bus can react to these -- monitoring dashboards, alerting, whatever.

Then the full `ParsedEmailPayload` gets serialized to JSON and dropped onto
the `vqms-analysis` SQS queue. The correlation_id rides along as a message
attribute so consumers can trace the message without parsing the body.

Finally, we try to mark the email as read in Exchange Online so the poller
doesn't pick it up again. If that PATCH fails, no big deal -- the Redis
idempotency key will prevent reprocessing.

**Code path:**
```
process_single_email()                        src/services/email_intake.py:248-280
  -> event_publisher.publish_email_received() src/events/eventbridge.py:117
  -> event_publisher.publish_email_parsed()   src/events/eventbridge.py:142
  -> sqs_client.send_message("vqms-analysis") src/queues/sqs.py:115
  -> graph_api.mark_as_read(message_id)       src/adapters/graph_api.py:283
```

**Storage writes:**
```
EventBridge:  vqms-event-bus <- EmailReceived event
EventBridge:  vqms-event-bus <- EmailParsed event
SQS:          vqms-analysis  <- ParsedEmailPayload as JSON
Exchange:     email marked as read (best-effort)
```

```
==========================================================
    THE PIPELINE STOPS HERE
    Steps 1-6 are built and working.
    The ParsedEmailPayload is sitting in vqms-analysis
    queue, waiting for a consumer that doesn't exist yet.
==========================================================
```

**Where our TechNova email data sits right now:**
```
S3 (raw email):     vqms-email-raw-prod
                    raw-emails/2026-04-01/vqms-bc1357d5-.../vqms-bc1357d5-...json

S3 (attachment):    vqms-email-attachments-prod
                    attachments/2026-04-01/vqms-bc1357d5-.../Invoice_INV-2026-0451.pdf

PostgreSQL:         intake.email_messages  (1 row, id=1)
                    intake.email_attachments (1 row, the PDF)

Redis:              vqms:idempotency:AAMkADhh...  (TTL: 7 days)

SQS:                vqms-analysis queue (1 message waiting)

EventBridge:        EmailReceived + EmailParsed events fired
```


---


STEP 7: ORCHESTRATOR STARTS WORKFLOW  [NOT STARTED]
════════════════════════════════════════════════════

```
    [SQS: vqms-analysis]
    (ParsedEmailPayload sitting here)
           |
           | SQS consumer picks up the message
           v
    +=============================================+
    | AWS Step Functions:                          |
    |   vqms-case-orchestrator                     |
    | src/orchestration/step_functions.py           |
    +=============================================+
           |
           | Start new execution
           v
    +=============================================+
    | LangGraph Orchestrator                       |
    | src/orchestration/graph.py                   |
    |                                              |
    | 1. Create workflow.case_execution record     |
    | 2. Load context from Memory & Context Svc    |
    | 3. Determine thread status                   |
    +=============================================+
           |               |               |
           v               v               v
    +-------------+ +-------------+ +--------------+
    | READ        | | READ        | | READ         |
    | Redis:      | | PostgreSQL: | | PostgreSQL:  |
    | vqms:thread:| | workflow.   | | memory.      |
    | AAQkADhh... | | ticket_link | | episodic_    |
    | (miss)      | | (no match)  | | memory       |
    +-------------+ +-------------+ | (no match)   |
                                    +--------------+
           |
           | All three lookups return nothing.
           | This is a brand new thread.
           v
    +---------------------------------------------+
    | Thread status: NEW                           |
    | (no existing ticket, no prior history)       |
    +---------------------------------------------+
```

WHAT HAPPENS: A consumer (which doesn't exist yet) picks up the
ParsedEmailPayload from the SQS queue and kicks off a Step Functions workflow.
Step Functions handles the durable execution -- retries, wait states, callbacks.
LangGraph handles the reasoning and decision-making.

First thing: create a record in `workflow.case_execution` so we can track this
email's journey. Then load context -- has this sender emailed before? Is there
an existing ticket? Any past interactions?

For the TechNova email, all three lookups come back empty. Nobody matching
`rohitsmagdum13@gmail.com` has emailed before, there's no thread in Redis,
and no ticket mapping in PostgreSQL. Thread status: NEW.

**Storage reads (all misses for this email):**
```
Redis:      GET vqms:thread:AAQkADhhNTY3YmY1LWJiYmUt...   -> nil
PostgreSQL: SELECT FROM workflow.ticket_link WHERE ...      -> 0 rows
PostgreSQL: SELECT FROM memory.episodic_memory WHERE ...    -> 0 rows
PostgreSQL: SELECT FROM memory.vendor_profile_cache WHERE . -> 0 rows
```

**Storage writes:**
```
PostgreSQL: INSERT INTO workflow.case_execution (
              execution_id, email_id, status='STARTED',
              correlation_id='vqms-bc1357d5-...',
              created_at=NOW()
            )

Redis:      SET vqms:workflow:vqms-bc1357d5-6731-4ffe-bd4a-8f2859afaefd
            {status: "STARTED", email_id: "AAMkADhh...", step: "CONTEXT_LOADING"}
            TTL: 24 hours
```

**Files that need to be built:**
```
src/orchestration/graph.py           LangGraph state machine
src/orchestration/step_functions.py  Step Functions integration
src/orchestration/router.py          Routing logic
src/orchestration/manager.py         Agent manager
src/services/memory_context.py       Memory & Context Service
```


---


STEP 8: THREE PARALLEL TASKS  [NOT STARTED]
════════════════════════════════════════════

```
                    ParsedEmailPayload
                           |
            +--------------+--------------+
            |              |              |
            v              v              v
    +===============+ +============+ +=============+
    | TASK A:       | | TASK B:    | | TASK C:     |
    | Email         | | Vendor     | | Ticket      |
    | Analysis      | | Resolution | | Lookup      |
    | Agent         | | Service    | |             |
    | (Bedrock      | | (Salesforce| | (PostgreSQL |
    |  Claude)      | |  CRM)     | |  + Service- |
    |               | |            | |  Now)       |
    +===============+ +============+ +=============+
            |              |              |
            v              v              v

    TASK A OUTPUT:    TASK B OUTPUT:    TASK C OUTPUT:
    AnalysisResult    VendorMatch       TicketCorrelation

    intent:           vendor_id:        ticket_exists:
     PAYMENT_QUERY     "SF-ACC-0892"     false

    entities:         vendor_name:      recommended_
     invoice:          "TechNova         action:
      INV-2026-0451    Solutions         CREATE
     vendor_code:      Pvt. Ltd."
      VN-30892                          (no existing
     po_number:       vendor_tier:       ticket found)
      PO-HEX-78412    GOLD
     amount:
      4,75,000.00    match_method:
     due_date:         EMAIL_EXACT
      17 Mar 2026    match_confidence:
                       0.95
    urgency: HIGH
    (past due)       risk_flags: []

    sentiment:
     FRUSTRATED
    (polite but
     past due)

    confidence:
     0.92

    is_reply: false
    multi_issue: false
```

WHAT HAPPENS: Three things run at the same time (Step Functions Parallel state).
No point doing them one after another when they're independent.

**Task A -- Email Analysis Agent** reads the email body through Bedrock Claude
and pulls out structured data. For our TechNova email, it figures out this is
a PAYMENT_QUERY (not a contract question, not tech support). It extracts the
invoice number, vendor code, PO, amount, and due date. Urgency is HIGH because
the due date already passed. Sentiment is FRUSTRATED -- Rajesh is polite, but
he's been waiting two weeks. Confidence score: 0.92 (the intent is pretty
clear from the subject line alone).

**Task B -- Vendor Resolution** takes the sender email and searches Salesforce.
It tries three strategies in order: exact email match, vendor ID from the body,
fuzzy name match. For our email, `rohitsmagdum13@gmail.com` matches against
TechNova Solutions in Salesforce. They're a GOLD tier vendor. Confidence: 0.95.

**Task C -- Ticket Lookup** checks if there's already a ticket for this thread.
It looks up the thread_id in `workflow.ticket_link` and queries ServiceNow.
For our TechNova email, nothing comes back -- this is the first email in the
thread. Recommended action: CREATE a new ticket.

**Storage reads:**
```
Task A:
  SQS:    consume from vqms-analysis
  S3:     load prompt template from vqms-knowledge-artifacts-prod

Task B:
  Redis:  GET vqms:vendor:SF-ACC-0892 -> nil (cache miss)
  Salesforce CRM: SOQL query by email domain

Task C:
  PostgreSQL: SELECT FROM workflow.ticket_link
              WHERE thread references match -> 0 rows
  ServiceNow: GET /incident (no match)
```

**Storage writes:**
```
Task A:
  S3:          vqms-audit-artifacts-prod  <- prompt snapshot
  PostgreSQL:  workflow.case_execution.analysis_result <- AnalysisResult JSON

Task B:
  Redis:       SET vqms:vendor:SF-ACC-0892  <- cached vendor profile (TTL: 1h)
  PostgreSQL:  memory.vendor_profile_cache <- TechNova profile

Task C:
  (no writes -- lookup only)
```

**Files that need to be built:**
```
src/agents/email_analysis.py          Email Analysis Agent
src/adapters/bedrock.py               Bedrock Integration Service
src/services/vendor_resolution.py     Vendor Resolution Service
src/adapters/salesforce.py            Salesforce CRM adapter
src/llm/factory.py                    LLM model factory
```


---


STEP 9: ORCHESTRATOR DECISION -- WHICH PATH?  [NOT STARTED]
═════════════════════════════════════════════════════════════

```
    AnalysisResult + VendorMatch + TicketCorrelation
                     |
                     v
    +=============================================+
    | Workflow Orchestration Agent                  |
    | (LangGraph decision node)                    |
    | src/orchestration/router.py                  |
    +=============================================+
                     |
                     | Evaluate decision matrix:
                     |
                     v

    confidence >= 0.85?  --------YES------+
           |                              |
          YES (0.92)                      |
           |                              |
    vendor matched?  --------YES------+   |
           |                          |   |
          YES (0.95)                  |   |
           |                          |   |
    clear single intent?  ---YES--+   |   |
           |                      |   |   |
          YES (PAYMENT_QUERY)     |   |   |
           |                      |   |   |
    risk flags?  -----NO------+  |   |   |
           |                   |  |   |   |
          NO (empty)           |  |   |   |
           |                   v  v   v   v
           |            +=======================+
           |            | PATH 1: FULL_AUTO     |
           +----------->| Create ticket,        |
                        | draft ack, send it.   |
                        | No human needed.      |
                        +=======================+


    If confidence < 0.85 OR vendor unresolved OR multi-issue:
                        +=======================+
                        | PATH 2: LOW_CONFIDENCE|
                        | Route to human review |
                        | queue. Step Functions  |
                        | pauses with callback  |
                        | token.                |
                        +=======================+


    If ticket_exists AND ticket_status in (OPEN, IN_PROGRESS):
                        +=======================+
                        | PATH 3: EXISTING_TKT  |
                        | Append to existing    |
                        | ticket. Add work      |
                        | notes in ServiceNow.  |
                        +=======================+


    If ticket_exists AND ticket_status == CLOSED:
                        +=======================+
                        | PATH 4: REOPEN        |
                        | Reopen closed ticket  |
                        | or create linked one. |
                        | Reset SLA timer.      |
                        +=======================+


    If urgency == CRITICAL OR (vendor_tier == PLATINUM AND risk_flags):
                        +=======================+
                        | PATH 5: ESCALATION    |
                        | Skip normal routing.  |
                        | Immediate escalation  |
                        | to manager.           |
                        +=======================+
```

WHAT HAPPENS: All three parallel tasks are done. The orchestrator now has the
full picture: what the email says, who sent it, and whether there's an existing
ticket. Time to decide what to do.

For our TechNova email, the decision is straightforward:
- Confidence: 0.92 (above 0.85 threshold) -- YES
- Vendor matched: TechNova Solutions, GOLD tier, confidence 0.95 -- YES
- Clear single intent: PAYMENT_QUERY, no multi-issue -- YES
- Risk flags: none -- clean
- No existing ticket -- this is new

**Result: PATH 1 -- FULL_AUTO.** Create a new ticket, draft an acknowledgment
email, validate it, send it. No human review needed.

If Rajesh had sent a vague email with no invoice number and we couldn't figure
out who he was, confidence would drop below 0.85 and we'd hit PATH 2 -- route
it to a human reviewer who'd sort out the intent and vendor manually.

**Storage writes:**
```
PostgreSQL:  INSERT INTO workflow.routing_decision (
               execution_id, intent='PAYMENT_QUERY',
               vendor_tier='GOLD', urgency='HIGH',
               resolver_group='Finance Support',
               decision_path='FULL_AUTO',
               confidence_score=0.92,
               rationale='High confidence, matched vendor, clear intent'
             )

Redis:       UPDATE vqms:workflow:vqms-bc1357d5-...
             {step: "ROUTING_COMPLETE", decision: "FULL_AUTO"}

EventBridge: AnalysisCompleted event
EventBridge: VendorResolved event
```

**Files that need to be built:**
```
src/orchestration/router.py          Routing decision logic
src/agents/orchestration.py          Workflow Orchestration Agent
```


---


STEP 10: CREATE TICKET IN SERVICENOW  [NOT STARTED]
════════════════════════════════════════════════════

```
    RoutingDecision (FULL_AUTO) + AnalysisResult + VendorMatch
           |
           | Push to vqms-ticket-ops SQS queue
           v
    +=============================================+
    | Ticket Operations Service                    |
    | src/services/ticket_ops.py                   |
    |                                              |
    | Check: does a ticket already exist           |
    |   for this correlation_id?                   |
    |   -> NO (idempotent check)                   |
    |                                              |
    | POST /api/now/table/incident                 |
    +=============================================+
           |
           v
    ServiceNow creates:
    +---------------------------------------------+
    | Ticket: INC0012345                           |
    |                                              |
    | Short Description:                           |
    |   Payment Status Inquiry - INV-2026-0451     |
    |                                              |
    | Category:       Financial                    |
    | Subcategory:    Payment Inquiry              |
    | Urgency:        2 - High                     |
    | Impact:         2 - Medium                   |
    | Assignment:     Finance Support Group        |
    | Caller:         TechNova Solutions (VN-30892)|
    | Correlation ID: vqms-bc1357d5-...            |
    |                                              |
    | Description:                                 |
    |   Vendor TechNova Solutions (GOLD tier)      |
    |   is inquiring about payment for Invoice     |
    |   INV-2026-0451 (PO-HEX-78412).             |
    |   Amount: 4,75,000.00. Due: 17 Mar 2026.    |
    |   Payment is 15 days overdue.                |
    |                                              |
    | SLA Target: 8 hours (GOLD tier, HIGH urgency)|
    +---------------------------------------------+
           |
           v
    +---------------------------------------------+
    | Storage writes:                              |
    |                                              |
    | PostgreSQL: workflow.ticket_link              |
    |   email_message_id -> ticket INC0012345      |
    |                                              |
    | Redis: vqms:ticket:INC0012345                |
    |   {status: OPEN, vendor: VN-30892,           |
    |    sla_target: 8h, assignment: Finance}      |
    |                                              |
    | EventBridge: TicketCreated event             |
    +---------------------------------------------+
```

WHAT HAPPENS: The routing decision says FULL_AUTO, so we create a ServiceNow
ticket. Before creating, we check `workflow.ticket_link` to make sure we haven't
already created one for this email (idempotency -- same pattern as the Redis
check in Step 3, but for tickets).

The ticket gets populated with everything we know: vendor name, invoice number,
amount, PO, and the fact that payment is 15 days overdue. Assignment group is
"Finance Support" based on the PAYMENT_QUERY intent. SLA target is 8 hours
because TechNova is a GOLD tier vendor with HIGH urgency.

**Files that need to be built:**
```
src/services/ticket_ops.py           Ticket Operations Service
src/adapters/servicenow.py           ServiceNow REST API adapter
```


---


STEP 11: DRAFT RESPONSE EMAIL  [NOT STARTED]
═════════════════════════════════════════════

```
    AnalysisResult + TicketRecord + VendorProfile + MemoryContext
           |
           | Push to vqms-communication SQS queue
           v
    +=============================================+
    | Communication Drafting Agent                 |
    | src/agents/communication_drafting.py         |
    |                                              |
    | Call Bedrock Claude via                       |
    | Bedrock Integration Service                  |
    | src/adapters/bedrock.py                      |
    +=============================================+
           |
           v
    DraftEmailPackage:
    +---------------------------------------------+
    | To:      rohitsmagdum13@gmail.com            |
    | Subject: RE: Payment Status Inquiry -        |
    |          Invoice #INV-2026-0451 |            |
    |          TechNova Solutions Pvt. Ltd.         |
    |                                              |
    | Body:                                        |
    | Dear Rajesh,                                 |
    |                                              |
    | Thank you for reaching out regarding         |
    | Invoice #INV-2026-0451 (PO-HEX-78412).      |
    |                                              |
    | We have logged your inquiry under ticket     |
    | INC0012345. Our Finance Support team is      |
    | reviewing the payment status for the amount  |
    | of Rs. 4,75,000.00 (due 17th March 2026).   |
    |                                              |
    | As a Gold-tier partner, your SLA target is   |
    | 8 hours. You can expect an update by         |
    | [timestamp + 8h].                            |
    |                                              |
    | If you need anything in the meantime,        |
    | reply to this email or reference ticket      |
    | INC0012345.                                  |
    |                                              |
    | Regards,                                     |
    | Hexaware Vendor Support                      |
    |                                              |
    | Headers:                                     |
    |   In-Reply-To: <original message-id>         |
    |   References:  <original message-id>         |
    +---------------------------------------------+
           |
           v
    EventBridge: DraftPrepared event
```

WHAT HAPPENS: The Communication Drafting Agent takes everything we know about
this case -- the analysis, the ticket number, the vendor profile, the SLA
target -- and feeds it to Bedrock Claude with a structured prompt template.
Claude generates a professional acknowledgment email.

The key things in the draft: ticket number (INC0012345) so Rajesh can reference
it, the specific invoice and amount so he knows we understood his question, and
the SLA commitment (8 hours) so he has an expectation. The reply headers
(`In-Reply-To`, `References`) are set so the response lands in the same email
thread on Rajesh's end.

**Files that need to be built:**
```
src/agents/communication_drafting.py  Communication Drafting Agent
src/adapters/bedrock.py               Bedrock Integration Service (shared with Step 8)
prompts/communication_drafting/v1.jinja  Prompt template
```


---


STEP 12: QUALITY GATE VALIDATES THE DRAFT  [NOT STARTED]
══════════════════════════════════════════════════════════

```
    DraftEmailPackage + TicketRecord + VendorProfile
           |
           v
    +=============================================+
    | Quality & Governance Gate                    |
    | src/gates/quality_governance.py              |
    +=============================================+
           |
           | Run 5 validation checks:
           |
           v
    CHECK 1: Ticket number correct?
        Draft says "INC0012345"
        ServiceNow has INC0012345 for this correlation_id
        -> PASS

    CHECK 2: SLA wording correct?
        Draft says "8 hours"
        Policy for GOLD + HIGH = 8 hours
        -> PASS

    CHECK 3: Template compliance?
        Has greeting, ticket ref, SLA statement,
        next steps, sign-off
        -> PASS

    CHECK 4: PII scan (Amazon Comprehend)?
        Scan draft body for leaked PII
        Found: phone number (+91 98765 43210)
        -> This is Rajesh's own phone from his
           signature, not leaked internal PII
        -> PASS (vendor's own info is OK)

    CHECK 5: Governance check?
        No restricted terms, no legal violations
        -> PASS

           |
           v
    All 5 checks passed?
           |
          YES
           |
           v
    +---------------------------------------------+
    | ValidationReport:                            |
    |   overall_status: PASS                       |
    |   checks: [PASS, PASS, PASS, PASS, PASS]    |
    |   pii_detected: false                        |
    +---------------------------------------------+
           |
           v
    EventBridge: ValidationPassed event
    S3: vqms-audit-artifacts-prod <- validation-report.json


    What if it FAILED?
    ==================

    All 5 checks passed?
           |
          NO (e.g., wrong ticket number in draft)
           |
           v
    +---------------------------------------------+
    | Route back to Communication Drafting Agent   |
    | for correction (max 2 re-drafts)             |
    |                                              |
    | If still failing after 2 re-drafts:          |
    |   -> Route to vqms-human-review-queue        |
    +---------------------------------------------+
           |
           v
    EventBridge: ValidationFailed event
    PostgreSQL: audit.validation_results <- failure details
```

WHAT HAPPENS: Before sending anything to Rajesh, the draft goes through a
five-point inspection. We check that the ticket number is real, that the SLA
promise matches our actual policy for GOLD vendors, that the email has all the
required sections, that we haven't accidentally leaked internal PII, and that
there's nothing legally problematic.

For our TechNova draft, everything checks out. The ticket number is real, the
SLA wording is correct, the template is compliant, no PII leakage, no
governance issues.

If the draft had a wrong ticket number or made a promise we couldn't keep, the
gate would fail it and send it back to the drafting agent for another try. After
two failed re-drafts, a human gets pulled in.

**Files that need to be built:**
```
src/gates/quality_governance.py    Quality & Governance Gate
```


---


STEP 13: SEND EMAIL BACK TO VENDOR  [NOT STARTED]
══════════════════════════════════════════════════

```
    Validated DraftEmailPackage
           |
           v
    +=============================================+
    | Outbound Send via Graph API                  |
    | (reuses GraphAPIAdapter)                     |
    | src/adapters/graph_api.py                    |
    |                                              |
    | POST /users/{mailbox}/sendMail               |
    | OR                                            |
    | POST /messages/{original-id}/reply           |
    +=============================================+
           |
           | Headers:
           |   In-Reply-To: <original message-id of Rajesh's email>
           |   References: <original message-id>
           |   (ensures reply lands in same thread)
           |
           v
    +---------------------------------------------+
    | Rajesh Mehta receives:                       |
    |                                              |
    | "RE: Payment Status Inquiry - Invoice        |
    |  #INV-2026-0451 | TechNova Solutions..."     |
    |                                              |
    | In his inbox, in the SAME THREAD as his      |
    | original email. Not a separate conversation. |
    +---------------------------------------------+
           |
           v
    +---------------------------------------------+
    | Storage writes:                              |
    |                                              |
    | PostgreSQL: audit.action_log                 |
    |   action: EMAIL_SENT                         |
    |   recipient: rohitsmagdum13@gmail.com        |
    |   outbound_message_id: <new id>              |
    |   correlation_id: vqms-bc1357d5-...          |
    |                                              |
    | S3: vqms-audit-artifacts-prod                |
    |   outputs/vqms-bc1357d5-.../outbound.json    |
    |                                              |
    | EventBridge: EmailSent event                 |
    |                                              |
    | PostgreSQL: workflow.case_execution           |
    |   status: COMPLETED (for ack flow)           |
    |   Set sent_flag = true to prevent            |
    |   double-send on retry                       |
    +---------------------------------------------+
```

WHAT HAPPENS: The validated draft gets sent to Rajesh through the same Graph
API we used to fetch the email. We use `/reply` instead of `/sendMail` so the
response lands in the same thread in Rajesh's inbox -- he sees it as a reply
to his original message, not a random new email.

The outbound send has a double-send guard: we set a `sent_flag` on the
`workflow.case_execution` record. If Step Functions retries this step (say, the
first attempt timed out but the email actually went through), we check the flag
before sending again.

**Files that need to be built:**
```
src/adapters/graph_api.py    Already exists, but needs a send_reply() method
```


---


STEP 14: SLA MONITORING STARTS  [NOT STARTED]
══════════════════════════════════════════════

```
    [EventBridge: TicketCreated]
    (from Step 10)
           |
           | Triggers SLA monitor
           v
    +=============================================+
    | Monitoring & SLA Alerting Service            |
    | src/monitoring/sla_alerting.py               |
    |                                              |
    | Step Functions: vqms-sla-monitor             |
    +=============================================+
           |
           | For ticket INC0012345:
           |   Vendor tier: GOLD
           |   Urgency: HIGH
           |   SLA target: 8 hours
           |   Created at: 2026-04-01 11:17:33 IST
           |   Deadline: 2026-04-01 19:17:33 IST
           |
           v

    TIME PASSES...
    ===============

    5.6 hours elapsed (70% of 8h):
    +---------------------------------------------+
    | SLAWarning70 event                           |
    |   -> Notify assigned resolver                |
    |   "Hey, ticket INC0012345 is at 70%.         |
    |    TechNova payment inquiry. 2.4h left."     |
    +---------------------------------------------+

    6.8 hours elapsed (85% of 8h):
    +---------------------------------------------+
    | SLAEscalation85 event                        |
    |   -> L1 manager escalation                   |
    |   -> Push to vqms-escalation-queue           |
    |   "INC0012345 is at 85%. GOLD vendor.        |
    |    Needs manager attention. 1.2h left."      |
    +---------------------------------------------+

    7.6 hours elapsed (95% of 8h):
    +---------------------------------------------+
    | SLAEscalation95 event                        |
    |   -> L2 senior management escalation         |
    |   "INC0012345 about to breach SLA.           |
    |    TechNova, GOLD tier. 24 minutes left."    |
    +---------------------------------------------+

    If resolved before breach:
    +---------------------------------------------+
    | SLA Monitor stops.                           |
    | reporting.sla_metrics:                       |
    |   ticket_id: INC0012345                      |
    |   sla_target_hours: 8                        |
    |   actual_hours: 6.2                          |
    |   breach: false                              |
    +---------------------------------------------+
```

WHAT HAPPENS: The moment a ticket is created, a separate Step Functions workflow
starts counting. It calculates when 70%, 85%, and 95% of the SLA window will
be reached, then uses wait states to sleep until each threshold.

For our TechNova ticket (GOLD tier, HIGH urgency = 8-hour SLA), the thresholds
are at 5.6 hours, 6.8 hours, and 7.6 hours after creation.

At each threshold, the monitor checks whether the ticket is already resolved.
If it is, the monitor stops. If it's still open, it fires an escalation event.
70% is a heads-up to the resolver. 85% pulls in a manager. 95% is a red alert
to senior management.

**Storage reads/writes:**
```
Redis:      SET vqms:sla:INC0012345
            {sla_start: "2026-04-01T11:17:33",
             sla_target_hours: 8,
             next_threshold: 70,
             elapsed_pct: 0}

PostgreSQL: INSERT INTO reporting.sla_metrics (...)

At each threshold:
  EventBridge: SLAWarning70 / SLAEscalation85 / SLAEscalation95
  SQS:         vqms-escalation (for 85% and 95%)
  PostgreSQL:  audit.action_log <- escalation action
```

**Files that need to be built:**
```
src/monitoring/sla_alerting.py    SLA Alerting Service
```


---


STEP 15: CLOSURE AND REOPEN FLOWS  [NOT STARTED]
═════════════════════════════════════════════════

```
    CLOSURE (two paths):
    =====================

    Path A: Rajesh replies "Thanks, payment received"
           |
           v
    [Email Ingestion -> Analysis Agent]
    Intent: CONFIRMATION
           |
           v
    Close ticket INC0012345 in ServiceNow
    (PATCH state: OPEN -> CLOSED)
           |
           v
    +---------------------------------------------+
    | PostgreSQL: audit.action_log <- TICKET_CLOSED|
    | PostgreSQL: memory.episodic_memory           |
    |   (store resolution summary for future ref)  |
    | EventBridge: TicketClosed event              |
    | SLA Monitor: stopped                         |
    +---------------------------------------------+


    Path B: No response from Rajesh for 5 business days
           |
           | Step Functions wait state expires
           v
    Auto-close ticket INC0012345
    (same writes as Path A)


    REOPEN:
    =======

    Two weeks later, Rajesh sends:
    "Hi, the payment still hasn't arrived..."

           |
           v
    [Email Ingestion processes normally]
    (Steps 1-6 run again for the new email)
           |
           v
    [Thread correlation]
    in-reply-to matches -> workflow.ticket_link
    -> ticket INC0012345, status = CLOSED
    -> Thread status: REPLY_TO_CLOSED
           |
           v
    [LangGraph decision node]
           |
    Same issue?  -------YES-------> REOPEN INC0012345
    ("payment still                 (CLOSED -> IN_PROGRESS)
     hasn't arrived")               Reset SLA timer
           |                        Restart vqms-sla-monitor
          NO                        TicketReopened event
    (new issue)
           |
           v
    CREATE new linked ticket INC0012400
    (parent_incident = INC0012345)
    Fresh SLA starts
    TicketCreated event
           |
           v
    Both paths re-enter the main flow
    from Step 9 (routing decision)
    with updated context
```

WHAT HAPPENS: Two ways a ticket closes. Either Rajesh confirms "yes, got the
payment, thanks" -- in which case the Analysis Agent catches the CONFIRMATION
intent and triggers closure. Or Rajesh just goes silent, and after 5 business
days, the system auto-closes the ticket.

Reopening is trickier. If Rajesh emails again about the same invoice after the
ticket is closed, the thread correlation (Step 7) catches it: "this thread
maps to ticket INC0012345, which is CLOSED." The LangGraph decision node then
figures out if this is the same issue coming back ("payment still hasn't
arrived") or a new issue ("I have a different question about a new invoice").

Same issue: reopen the existing ticket, reset the SLA, restart the monitor.
New issue: create a brand new ticket linked to the original as a parent, start
a fresh SLA.

Either way, the flow re-enters at Step 9 (routing decision) with the updated
context.

**Files that need to be built:**
```
src/services/ticket_ops.py          (reopen/close operations)
src/orchestration/router.py         (reopen decision logic)
src/services/memory_context.py      (episodic memory writes)
```


---


## Build status

Where every step stands right now:

```
Step   Description                         Status          Code Location
-----  ----------------------------------  --------------  ---------------------------------
 1     Vendor sends email                  [BUILT]         (external, no code needed)
 2     System detects email                [BUILT]         src/services/email_intake.py
                                                           src/adapters/graph_api.py
 3     Idempotency check                   [BUILT]         src/cache/redis_client.py
 4     Save raw email to S3                [BUILT]         src/storage/s3_client.py
                                                           src/adapters/graph_api.py
 5     Parse and store in PostgreSQL        [BUILT]         src/services/email_intake.py
                                                           src/db/connection.py
                                                           src/models/email.py
 6     Publish events + push to SQS        [BUILT]         src/events/eventbridge.py
                                                           src/queues/sqs.py
 7     Orchestrator starts workflow         [NOT STARTED]   src/orchestration/ (empty dir)
 8     Three parallel tasks                [NOT STARTED]   src/agents/ (empty dir)
                                                           src/adapters/bedrock.py (missing)
                                                           src/adapters/salesforce.py (missing)
 9     Orchestrator decision               [NOT STARTED]   src/orchestration/router.py (missing)
10     Create ticket in ServiceNow         [NOT STARTED]   src/services/ticket_ops.py (missing)
                                                           src/adapters/servicenow.py (missing)
11     Draft response email                [NOT STARTED]   src/agents/communication_drafting.py
12     Quality gate                        [NOT STARTED]   src/gates/quality_governance.py
13     Send email to vendor                [NOT STARTED]   src/adapters/graph_api.py (needs send)
14     SLA monitoring                      [NOT STARTED]   src/monitoring/sla_alerting.py
15     Closure and reopen                  [NOT STARTED]   (multiple files)
```

**Summary:**
```
[BUILT]         6 steps   (Steps 1-6: email in -> parsed -> stored -> queued)
[NOT STARTED]   9 steps   (Steps 7-15: orchestration -> agents -> tickets -> send -> SLA)
```

**Infrastructure built but not consumed yet:**
```
Redis key families:    thread, ticket, workflow, vendor, sla  (all ready, no callers)
EventBridge stubs:     15 event methods exist but aren't called yet
SQS queue definitions: 10 queues defined, only vqms-analysis is used
Pydantic models:       VendorMatch, TicketRecord, RoutingDecision, CaseExecution,
                       DraftEmailPackage, ValidationReport, EpisodicMemory,
                       VendorProfileCache, EmbeddingRecord  (all ready, no callers)
```


---


## What to build next

The build order from the architecture doc (Phase 3-10). Each one unlocks the
next.

**Phase 3 -- Thread correlation and memory (Steps 7 context loading)**
- `src/services/memory_context.py` -- Memory & Context Service
- `src/memory/short_term.py` -- Redis thread state
- `src/memory/long_term.py` -- pgvector semantic search
- Wire up thread_id lookup against `workflow.ticket_link`

**Phase 4 -- Orchestration skeleton (Steps 7, 9)**
- `src/orchestration/graph.py` -- LangGraph state machine
- `src/orchestration/step_functions.py` -- Step Functions integration
- `src/orchestration/router.py` -- Routing decision logic
- SQS consumer from `vqms-analysis` to trigger orchestration
- Use stub agents (hardcoded responses) to test the flow

**Phase 5 -- Email Analysis Agent (Step 8, Task A)**
- `src/adapters/bedrock.py` -- Bedrock Integration Service
- `src/agents/email_analysis.py` -- Email Analysis Agent
- `src/llm/factory.py` -- LLM model factory
- `prompts/email_analysis/v1.jinja` -- Prompt template
- Wire into orchestration graph

**Phase 6 -- External integrations (Steps 8 Tasks B/C, Step 10)**
- `src/adapters/salesforce.py` -- Salesforce CRM adapter
- `src/services/vendor_resolution.py` -- Vendor Resolution Service
- `src/adapters/servicenow.py` -- ServiceNow REST adapter
- `src/services/ticket_ops.py` -- Ticket Operations Service

**Phase 7 -- Drafting and validation (Steps 11-12)**
- `src/agents/communication_drafting.py` -- Drafting Agent
- `src/gates/quality_governance.py` -- Quality & Governance Gate
- `prompts/communication_drafting/v1.jinja` -- Prompt template

**Phase 8 -- SLA monitoring (Step 14)**
- `src/monitoring/sla_alerting.py` -- SLA Alerting Service

**Phase 9 -- Closure and reopen (Step 15)**
- Closure logic in `src/services/ticket_ops.py`
- Reopen detection in `src/orchestration/router.py`

**Phase 10 -- End-to-end testing**
- Integration tests for all 6 business flow variants
- The full journey: Rajesh emails -> system processes -> Rajesh gets ack -> ticket resolves -> closure
