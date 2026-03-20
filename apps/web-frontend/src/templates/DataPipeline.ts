/**
 * Data Pipeline template
 * Scheduled data fetch, transform, and store pipeline (ETL)
 */
import { FlowTemplate } from '../types';
import { generateId } from '../utils/flowUtils';

export const dataPipelineTemplate: FlowTemplate = {
  id: 'data-pipeline',
  name: 'Data Pipeline',
  description:
    'Scheduled ETL pipeline: fetch data from an external API on a cron schedule, reshape with Transform, and persist the result in memory store.',
  tags: ['data', 'pipeline', 'etl', 'scheduled'],
  flow: {
    id: generateId(),
    name: 'Data Pipeline',
    nodes: [
      {
        id: 'scheduler',
        type: 'scheduler',
        position: { x: 300, y: 25 },
        data: {
          label: 'Hourly Trigger',
          cron: '{{CRON_SCHEDULE}}',
          description: 'Fires on the configured cron schedule (default: every hour)',
        },
      },
      {
        id: 'fetch',
        type: 'http_request',
        position: { x: 300, y: 150 },
        data: {
          label: 'Fetch Data',
          method: 'GET',
          url: '{{DATA_API_URL}}',
          headers: {
            Accept: 'application/json',
            'X-Api-Key': '{{DATA_API_KEY}}',
          },
          timeout_seconds: 30,
          auth_type: 'none',
          max_retries: 3,
          allow_redirects: true,
          verify_ssl: true,
        },
      },
      {
        id: 'reshape',
        type: 'transform',
        position: { x: 300, y: 300 },
        data: {
          label: 'Reshape Data',
          operation: 'json_path',
          json_path: '$.data',
          description: 'Extract and reshape the payload — adjust json_path for your API response',
        },
      },
      {
        id: 'store',
        type: 'memory',
        position: { x: 300, y: 450 },
        data: {
          label: 'Store Result',
          operation: 'store',
          key: 'pipeline-latest',
          namespace: 'data-pipeline',
          description: 'Persist the transformed data for downstream consumers',
        },
      },
      {
        id: 'end',
        type: 'end',
        position: { x: 300, y: 575 },
        data: { label: 'End' },
      },
    ],
    edges: [
      { id: 'scheduler-fetch', source: 'scheduler', target: 'fetch', animated: false },
      { id: 'fetch-reshape', source: 'fetch', target: 'reshape', animated: false },
      { id: 'reshape-store', source: 'reshape', target: 'store', animated: false },
      { id: 'store-end', source: 'store', target: 'end', animated: false },
    ],
  },
};
