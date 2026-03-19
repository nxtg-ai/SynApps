# AI Content Compliance Pipeline

A SynApps workflow template that automatically scans submitted text content
against the [Faultline Platform](https://faultline.ai) API, computes a trust
score, and routes the result: flagged content triggers a Slack alert while
compliant content generates a formal compliance report and email notification.

---

## Overview

| Property | Value |
|----------|-------|
| Template ID | `ai-content-compliance-pipeline` |
| Template file | `src/templates/FaultlineCompliance.ts` |
| YAML definition | `src/templates/faultline_compliance.yaml` |
| Trigger | Webhook (HTTP POST) |
| External services | Faultline Platform API, Slack Incoming Webhooks, Email relay |

The pipeline executes in two logical branches after the trust score is
computed:

- **Trust score < 70** (flagged): posts a Slack alert with the score and a
  preview of the submitted text, then terminates.
- **Trust score >= 70** (compliant): calls the Faultline report endpoint to
  generate a compliance report, sends the report URL by email, then terminates.

---

## Prerequisites

Before importing this template you need:

1. **Faultline Platform account** — obtain a base API URL and an API key from
   your Faultline dashboard.
2. **Slack incoming webhook** — create one at
   `https://api.slack.com/apps` under "Incoming Webhooks". The URL looks like
   `https://hooks.slack.com/services/T.../B.../...`.
3. **Email relay endpoint** — an HTTP endpoint that accepts a JSON POST and
   sends an email (e.g. a SendGrid, Mailgun, or Resend webhook relay). The
   endpoint must accept `{ "to", "subject", "body" }`.
4. **SynApps** v0.5.x or later with the HTTP Request, Code, If/Else, and
   Webhook Trigger node types available.

---

## Step-by-Step Setup

### Step 1 — Import the template

1. Open SynApps and navigate to **Template Gallery**.
2. Locate **AI Content Compliance Pipeline** and click **Use Template**.
3. A new workflow is created in your workspace with all eight nodes
   pre-configured.

### Step 2 — Set workflow variables

In the workflow settings panel, provide values for all five required variables:

| Variable | Example value |
|----------|---------------|
| `FAULTLINE_API_URL` | `https://api.faultline.ai` |
| `FAULTLINE_API_KEY` | `flt_live_xxxxxxxxxxxxxxxx` |
| `SLACK_WEBHOOK_URL` | `https://hooks.slack.com/services/...` |
| `REPORT_EMAIL` | `compliance@yourcompany.com` |
| `EMAIL_WEBHOOK_URL` | `https://api.sendgrid.com/v3/mail/relay` |

Variables are referenced throughout the nodes as `{{var.VARIABLE_NAME}}`. You
do not need to edit individual nodes once the variables are set.

### Step 3 — Register the webhook trigger

1. Select the **Content Submission Webhook** node on the canvas.
2. Click **Register Webhook** in the node settings panel.
3. Copy the generated webhook URL (format:
   `/api/v1/webhooks/trigger/{trigger_id}`).
4. Configure your content submission system to POST to this URL.

### Step 4 — Test with a sample payload

Send a test request using curl or any HTTP client:

```bash
curl -X POST https://your-synapps-instance/api/v1/webhooks/trigger/{trigger_id} \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Sample content to scan",
    "content_type": "user_post",
    "user_id": "user_123"
  }'
```

Check the **Run History** page to verify:
- The scan node returned a response from Faultline.
- The extract node correctly parsed `trust_score`, `compliant`, and `label`.
- The correct branch (alert or report) was taken.

### Step 5 — Monitor ongoing compliance

- **Slack channel**: flagged items appear immediately with score and preview.
- **Email inbox**: compliant items generate a report link sent to
  `REPORT_EMAIL`.
- **SynApps Run History**: full execution trace with per-node inputs and
  outputs for audit purposes.

---

## Workflow Diagram

```
[Webhook]
    |
    v
[Faultline Scan]  POST /scan
    |
    v
[Extract Trust Score]  (Python code node)
    |
    v
[If/Else: compliant == "no"?]
    |                    |
    | true (flagged)     | false (compliant)
    v                    v
[Slack Alert]    [Generate Report]  POST /scan/report
    |                    |
    v                    v
 [Done]          [Email Report]
                         |
                         v
                      [Done]
```

---

## Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `FAULTLINE_API_URL` | Yes | Base URL of the Faultline Platform API, without trailing slash. Example: `https://api.faultline.ai` |
| `FAULTLINE_API_KEY` | Yes | Bearer token for Faultline API authentication. Sent as `Authorization: Bearer <key>` on all Faultline requests. |
| `SLACK_WEBHOOK_URL` | Yes | Slack incoming webhook URL. Receives a message when content is flagged (trust score < 70). |
| `REPORT_EMAIL` | Yes | Email address that receives the compliance report link when content passes review. Also sent as the `recipient` parameter to the Faultline report endpoint. |
| `EMAIL_WEBHOOK_URL` | Yes | HTTP POST endpoint that sends email. Must accept JSON body `{ "to", "subject", "body" }`. |

---

## Sample Webhook Payload

```json
{
  "text": "Sample content to scan",
  "content_type": "user_post",
  "user_id": "user_123"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | string | Yes | The content to be scanned for compliance. |
| `content_type` | string | No | A label for the type of content (e.g. `user_post`, `comment`, `bio`). Passed to Faultline for context. |
| `user_id` | string | No | Identifier of the user who submitted the content. Passed to Faultline for audit trail purposes. |

---

## Trust Score Explanation

The Faultline Platform returns a `trust_score` field in its scan response on a
scale from **0 to 100**:

| Score range | Meaning | Workflow action |
|-------------|---------|-----------------|
| 0 – 69 | Flagged — content does not meet compliance threshold | Slack alert posted; execution ends |
| 70 – 100 | Compliant — content passes compliance review | Compliance report generated; report URL emailed |

The threshold (70) is applied in the **Extract Trust Score** code node:

```python
compliant = "yes" if trust_score >= 70 else "no"
```

---

## Customization Tips

### Adjusting the compliance threshold

Open the **Extract Trust Score** node and edit the code directly on the canvas.
Change `70` to any value between 0 and 100:

```python
# Raise to 85 for stricter compliance requirements
compliant = "yes" if trust_score >= 85 else "no"
```

Save the node; the change takes effect on the next execution.

### Adding more alert channels

To send flagged-content alerts to additional destinations (e.g. PagerDuty,
Teams, a logging endpoint):

1. Add a new **HTTP Request** node after the **Slack: Compliance Alert** node.
2. Configure it with the target URL and body template. Use
   `{{data.trust_score}}` and `{{data.text_preview}}` to include scan details.
3. Connect the Slack node's output edge to the new node, and connect the new
   node to **Done**.

### Storing flagged content for review

Insert a **Memory** node between **Slack: Compliance Alert** and **Done**.
Set `operation: store`, `key: flagged-content`, and `namespace: compliance`.
This accumulates flagged items for later retrieval via the Memory Read node.

### Enriching the scan request

The Faultline `/scan` endpoint body is defined in the **Faultline: Content
Scan** HTTP Request node. Add extra fields supported by your Faultline plan
(e.g. `locale`, `categories`, `sensitivity`) directly in the node's body
template.
