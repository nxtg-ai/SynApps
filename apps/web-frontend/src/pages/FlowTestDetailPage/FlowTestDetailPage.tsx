/**
 * FlowTestDetailPage — Single test-case inspector (N-118).
 *
 * Covers:
 *   GET /api/v1/flows/{flow_id}/tests/{test_id} → fetch a single test case by ID
 *
 * Route: /flow-test-detail (ProtectedRoute)
 */
import React, { useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TestCase {
  test_id: string;
  name: string;
  description?: string;
  input: unknown;
  expected_output: unknown;
  match_mode: string;
  created_by?: string;
  created_at?: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getBaseUrl(): string {
  return (
    (import.meta as unknown as { env?: { VITE_API_URL?: string } }).env?.VITE_API_URL ||
    'http://localhost:8000'
  );
}

function authHeaders(): Record<string, string> {
  const token =
    typeof window !== 'undefined' ? window.localStorage.getItem('access_token') : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function prettyJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const FlowTestDetailPage: React.FC = () => {
  const [flowId, setFlowId] = useState('');
  const [testId, setTestId] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testCase, setTestCase] = useState<TestCase | null>(null);

  // ---------------------------------------------------------------------------
  // Handler
  // ---------------------------------------------------------------------------

  async function handleFetch(e: React.FormEvent) {
    e.preventDefault();
    if (!flowId.trim() || !testId.trim()) return;
    setLoading(true);
    setError(null);
    setTestCase(null);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/api/v1/flows/${encodeURIComponent(flowId.trim())}/tests/${encodeURIComponent(testId.trim())}`,
        { headers: authHeaders() },
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setError(data.detail ?? `Error ${resp.status}`);
        return;
      }
      setTestCase(data as TestCase);
    } catch {
      setError('Network error');
    } finally {
      setLoading(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <MainLayout title="Flow Test Detail">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
          Flow Test Detail
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Inspect a single test case by flow ID and test ID.
        </p>
      </div>

      {/* Lookup form */}
      <form onSubmit={handleFetch} className="mb-6 flex flex-wrap items-end gap-3" data-testid="lookup-form">
        <div>
          <label className="mb-1 block text-xs text-slate-400">Flow ID</label>
          <input
            className="rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500"
            placeholder="flow-id"
            value={flowId}
            onChange={(e) => setFlowId(e.target.value)}
            required
            data-testid="flow-id-input"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-400">Test ID</label>
          <input
            className="rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500"
            placeholder="test-id"
            value={testId}
            onChange={(e) => setTestId(e.target.value)}
            required
            data-testid="test-id-input"
          />
        </div>
        <button
          type="submit"
          disabled={loading || !flowId.trim() || !testId.trim()}
          className="rounded bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-500 disabled:opacity-50"
          data-testid="fetch-btn"
        >
          {loading ? 'Loading…' : 'Fetch Test'}
        </button>
      </form>

      {error && (
        <p className="mb-4 text-sm text-red-400" data-testid="fetch-error">{error}</p>
      )}

      {testCase && (
        <div
          className="rounded border border-slate-700 bg-slate-800/30 p-5 space-y-4"
          data-testid="test-detail"
        >
          {/* Header */}
          <div className="flex items-start justify-between">
            <div>
              <h2 className="text-lg font-semibold text-slate-100" data-testid="test-name">
                {testCase.name}
              </h2>
              {testCase.description && (
                <p className="mt-0.5 text-sm text-slate-400" data-testid="test-description">
                  {testCase.description}
                </p>
              )}
            </div>
            <span
              className="rounded bg-slate-700 px-2 py-0.5 text-xs text-slate-400"
              data-testid="test-match-mode"
            >
              {testCase.match_mode}
            </span>
          </div>

          {/* Meta */}
          <div className="grid grid-cols-2 gap-3 text-xs text-slate-500" data-testid="test-meta">
            <div>
              <span className="text-slate-600">Test ID: </span>
              <span className="font-mono text-slate-400" data-testid="meta-test-id">
                {testCase.test_id}
              </span>
            </div>
            {testCase.created_by && (
              <div>
                <span className="text-slate-600">Created by: </span>
                <span className="text-slate-400" data-testid="meta-created-by">
                  {testCase.created_by}
                </span>
              </div>
            )}
            {testCase.created_at && (
              <div>
                <span className="text-slate-600">Created at: </span>
                <span className="text-slate-400">{testCase.created_at}</span>
              </div>
            )}
          </div>

          {/* Input */}
          <div data-testid="test-input-section">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Input
            </h3>
            <pre
              className="overflow-x-auto rounded bg-slate-900 p-3 font-mono text-xs text-slate-300"
              data-testid="test-input-json"
            >
              {prettyJson(testCase.input)}
            </pre>
          </div>

          {/* Expected output */}
          <div data-testid="test-expected-section">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Expected Output
            </h3>
            <pre
              className="overflow-x-auto rounded bg-slate-900 p-3 font-mono text-xs text-slate-300"
              data-testid="test-expected-json"
            >
              {prettyJson(testCase.expected_output)}
            </pre>
          </div>
        </div>
      )}

      {!loading && !testCase && !error && (
        <p className="text-sm text-slate-500" data-testid="empty-state">
          Enter a Flow ID and Test ID, then click Fetch Test.
        </p>
      )}
    </MainLayout>
  );
};

export default FlowTestDetailPage;
