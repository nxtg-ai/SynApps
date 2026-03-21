/**
 * NodeConfigPage -- Demo/testing page for the SchemaForm component (N-61).
 *
 * Shows SchemaForm with a sample plugin schema, a live JSON preview,
 * and Reset / Save Config buttons.
 *
 * Route: /node-config (ProtectedRoute)
 */
import React, { useCallback, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';
import SchemaForm from '../../components/SchemaForm';

// ---------------------------------------------------------------------------
// Sample schema for demonstration
// ---------------------------------------------------------------------------

const SAMPLE_SCHEMA: Record<string, unknown> = {
  type: 'object',
  required: ['apiKey'],
  properties: {
    apiKey: { type: 'string', title: 'API Key', description: 'Your secret API key' },
    model: { type: 'string', title: 'Model', default: 'gpt-4' },
    maxTokens: { type: 'integer', title: 'Max Tokens', default: 1024 },
    temperature: { type: 'number', title: 'Temperature', default: 0.7 },
    stream: { type: 'boolean', title: 'Stream', default: false },
    stopSequences: {
      type: 'array',
      title: 'Stop Sequences',
      items: { type: 'string' },
      description: 'Comma-separated stop tokens',
    },
    advanced: {
      type: 'object',
      title: 'Advanced Settings',
      properties: {
        timeout: { type: 'number', title: 'Timeout (ms)', default: 30000 },
        retries: { type: 'integer', title: 'Retries', default: 2 },
      },
    },
  },
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const NodeConfigPage: React.FC = () => {
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const handleChange = useCallback((newValues: Record<string, unknown>) => {
    setValues(newValues);
    setSuccessMessage(null);
  }, []);

  const handleReset = useCallback(() => {
    setValues({});
    setSuccessMessage(null);
  }, []);

  const handleSave = useCallback(() => {
    setSuccessMessage('Configuration saved successfully');
  }, []);

  return (
    <MainLayout title="Node Configuration">
      <div className="mx-auto max-w-3xl px-4 py-6">
        <h1 className="mb-6 text-2xl font-bold text-slate-100">Node Configuration</h1>

        {successMessage && (
          <div
            role="status"
            className="mb-4 rounded bg-green-800/40 p-3 text-sm text-green-300"
          >
            {successMessage}
          </div>
        )}

        <div className="mb-6 rounded-lg border border-slate-700 bg-slate-800 p-4">
          <SchemaForm schema={SAMPLE_SCHEMA} value={values} onChange={handleChange} />
        </div>

        <div className="mb-6 flex gap-3">
          <button
            onClick={handleSave}
            className="rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
          >
            Save Config
          </button>
          <button
            onClick={handleReset}
            className="rounded border border-slate-600 px-4 py-2 text-sm font-medium text-slate-300 hover:bg-slate-700"
          >
            Reset
          </button>
        </div>

        <div>
          <h2 className="mb-2 text-sm font-semibold text-slate-400">Current Values (JSON)</h2>
          <pre
            data-testid="json-preview"
            className="rounded border border-slate-700 bg-slate-900 p-4 text-xs text-slate-300"
          >
            {JSON.stringify(values, null, 2)}
          </pre>
        </div>
      </div>
    </MainLayout>
  );
};

export default NodeConfigPage;
