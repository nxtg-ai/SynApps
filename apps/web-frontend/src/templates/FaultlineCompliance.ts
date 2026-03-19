/**
 * AI Content Compliance Pipeline template
 * Powered by the Faultline Platform API.
 *
 * Receive text via webhook, scan with Faultline for a trust score,
 * route flagged content (score < 70) to a Slack alert and compliant
 * content (score >= 70) to a compliance report + email notification.
 *
 * Pipeline:
 *   webhook → scan → extract → route
 *                                ├─ [flagged] → alert → end
 *                                └─ [compliant] → report → email → end
 */
import { FlowTemplate } from '../types';
import { generateId } from '../utils/flowUtils';

export const faultlineComplianceTemplate: FlowTemplate = {
  id: 'ai-content-compliance-pipeline',
  name: 'AI Content Compliance Pipeline',
  description:
    'Receive text via webhook, scan with Faultline Platform for trust score, route flagged content to Slack and compliant content to a compliance report + email. Powered by the Faultline Platform API.',
  tags: ['compliance', 'faultline', 'content-moderation', 'webhook', 'slack', 'monitoring'],
  flow: {
    id: generateId(),
    name: 'AI Content Compliance Pipeline',
    nodes: [
      {
        id: 'webhook',
        type: 'webhook_trigger',
        position: { x: 100, y: 300 },
        data: {
          label: 'Content Submission Webhook',
          input_schema: {
            text: { type: 'string', required: true },
            content_type: { type: 'string', required: false },
            user_id: { type: 'string', required: false },
          },
        },
      },
      {
        id: 'scan',
        type: 'http_request',
        position: { x: 300, y: 300 },
        data: {
          label: 'Faultline: Content Scan',
          method: 'POST',
          url: '{{var.FAULTLINE_API_URL}}/scan',
          headers: {
            'Content-Type': 'application/json',
            Authorization: 'Bearer {{var.FAULTLINE_API_KEY}}',
          },
          auth_type: 'bearer',
          auth_token: '{{var.FAULTLINE_API_KEY}}',
          body: JSON.stringify({
            text: '{{input.text}}',
            content_type: '{{input.content_type}}',
            user_id: '{{input.user_id}}',
          }),
          timeout_seconds: 30,
          verify_ssl: true,
          max_retries: 1,
          allow_redirects: true,
        },
      },
      {
        id: 'extract',
        type: 'code',
        position: { x: 500, y: 300 },
        data: {
          label: 'Extract Trust Score',
          language: 'python',
          timeout_seconds: 10,
          memory_limit_mb: 256,
          code:
            '# data = HTTP response body from Faultline scan (dict)\n' +
            '# context["input"] = original webhook payload\n' +
            'raw_input = context.get("input", {})\n' +
            'if isinstance(raw_input, dict):\n' +
            '    original_text = raw_input.get("text", "")\n' +
            'else:\n' +
            '    original_text = str(raw_input)\n' +
            '\n' +
            'scan_response = data if isinstance(data, dict) else {}\n' +
            '\n' +
            'trust_score = scan_response.get("trust_score", 0)\n' +
            'try:\n' +
            '    trust_score = float(trust_score)\n' +
            'except (TypeError, ValueError):\n' +
            '    trust_score = 0.0\n' +
            '\n' +
            'compliant = "yes" if trust_score >= 70 else "no"\n' +
            'label = "PASS" if compliant == "yes" else "FLAGGED"\n' +
            'scan_id = scan_response.get("scan_id", "")\n' +
            'text_preview = original_text[:100]\n' +
            '\n' +
            'result = {\n' +
            '    "trust_score": trust_score,\n' +
            '    "compliant": compliant,\n' +
            '    "label": label,\n' +
            '    "scan_id": scan_id,\n' +
            '    "text_preview": text_preview,\n' +
            '}\n',
        },
      },
      {
        id: 'route',
        type: 'if_else',
        position: { x: 700, y: 300 },
        data: {
          label: 'Route by Trust Score',
          source: '{{data.compliant}}',
          operation: 'equals',
          value: 'no',
          case_sensitive: false,
          negate: false,
          true_target: 'alert',
          false_target: 'report',
        },
      },
      {
        id: 'alert',
        type: 'http_request',
        position: { x: 600, y: 500 },
        data: {
          label: 'Slack: Compliance Alert',
          method: 'POST',
          url: '{{var.SLACK_WEBHOOK_URL}}',
          headers: { 'Content-Type': 'application/json' },
          auth_type: 'none',
          body: JSON.stringify({
            text: '\u26a0\ufe0f Content flagged (trust score: {{data.trust_score}}): {{data.text_preview}}',
          }),
          timeout_seconds: 15,
          verify_ssl: true,
          max_retries: 1,
          allow_redirects: true,
        },
      },
      {
        id: 'report',
        type: 'http_request',
        position: { x: 900, y: 500 },
        data: {
          label: 'Generate Compliance Report',
          method: 'POST',
          url: '{{var.FAULTLINE_API_URL}}/scan/report',
          headers: {
            'Content-Type': 'application/json',
            Authorization: 'Bearer {{var.FAULTLINE_API_KEY}}',
          },
          auth_type: 'bearer',
          auth_token: '{{var.FAULTLINE_API_KEY}}',
          body: JSON.stringify({
            scan_id: '{{data.scan_id}}',
            format: 'json',
            recipient: '{{var.REPORT_EMAIL}}',
          }),
          timeout_seconds: 30,
          verify_ssl: true,
          max_retries: 1,
          allow_redirects: true,
        },
      },
      {
        id: 'email',
        type: 'http_request',
        position: { x: 900, y: 650 },
        data: {
          label: 'Email Compliance Report',
          method: 'POST',
          url: '{{var.EMAIL_WEBHOOK_URL}}',
          headers: { 'Content-Type': 'application/json' },
          auth_type: 'none',
          body: JSON.stringify({
            to: '{{var.REPORT_EMAIL}}',
            subject: 'Compliance Report \u2014 Content Passed Review',
            body: '{{data.report_url}}',
          }),
          timeout_seconds: 15,
          verify_ssl: true,
          max_retries: 1,
          allow_redirects: true,
        },
      },
      {
        id: 'end',
        type: 'end',
        position: { x: 1100, y: 550 },
        data: { label: 'Done' },
      },
    ],
    edges: [
      {
        id: 'webhook-scan',
        source: 'webhook',
        target: 'scan',
        animated: false,
      },
      {
        id: 'scan-extract',
        source: 'scan',
        target: 'extract',
        animated: false,
      },
      {
        id: 'extract-route',
        source: 'extract',
        target: 'route',
        animated: false,
      },
      {
        id: 'route-alert',
        source: 'route',
        target: 'alert',
        sourceHandle: 'true',
        animated: false,
      },
      {
        id: 'route-report',
        source: 'route',
        target: 'report',
        sourceHandle: 'false',
        animated: false,
      },
      {
        id: 'alert-end',
        source: 'alert',
        target: 'end',
        animated: false,
      },
      {
        id: 'report-email',
        source: 'report',
        target: 'email',
        animated: false,
      },
      {
        id: 'email-end',
        source: 'email',
        target: 'end',
        animated: false,
      },
    ],
  },
};
