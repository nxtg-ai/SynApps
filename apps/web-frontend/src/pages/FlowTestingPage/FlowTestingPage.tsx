/**
 * FlowTestingPage — Flow test-suite management (N-106).
 *
 * Covers:
 *   POST   /flows/{flow_id}/tests           → add test case
 *   GET    /flows/{flow_id}/tests           → list test cases
 *   DELETE /flows/{flow_id}/tests/{test_id} → delete test case
 *   GET    /flows/{flow_id}/tests/summary   → suite summary
 *   POST   /flows/{flow_id}/tests/run       → run test suite
 *   GET    /flows/{flow_id}/tests/results   → list results
 *
 * Route: /flow-testing (ProtectedRoute)
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
}

interface TestResult {
  result_id: string;
  test_id: string;
  status: 'pass' | 'fail' | 'error';
  actual_output: unknown;
  expected_output: unknown;
  diff?: unknown;
  error_message?: string;
  duration_ms?: number;
}

interface SuiteSummary {
  total: number;
  passed: number;
  failed: number;
  errors?: number;
  last_run?: string | null;
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

function jsonHeaders(): Record<string, string> {
  return { ...authHeaders(), 'Content-Type': 'application/json' };
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const FlowTestingPage: React.FC = () => {
  const [flowId, setFlowId] = useState('');

  // Add test case
  const [addName, setAddName] = useState('');
  const [addDesc, setAddDesc] = useState('');
  const [addInput, setAddInput] = useState('{}');
  const [addExpected, setAddExpected] = useState('{}');
  const [addMatchMode, setAddMatchMode] = useState('exact');
  const [addLoading, setAddLoading] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const [addResult, setAddResult] = useState<TestCase | null>(null);

  // List / delete tests
  const [tests, setTests] = useState<TestCase[]>([]);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Summary
  const [summary, setSummary] = useState<SuiteSummary | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  // Run suite
  const [runLoading, setRunLoading] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [runResults, setRunResults] = useState<TestResult[] | null>(null);
  const [exitCode, setExitCode] = useState<number | null>(null);

  // Results history
  const [resultsLoading, setResultsLoading] = useState(false);
  const [resultsError, setResultsError] = useState<string | null>(null);
  const [results, setResults] = useState<TestResult[] | null>(null);

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!flowId.trim()) return;
    setAddLoading(true);
    setAddError(null);
    setAddResult(null);
    try {
      let inputData: unknown;
      let expectedData: unknown;
      try { inputData = JSON.parse(addInput); } catch { setAddError('Invalid JSON in Input'); setAddLoading(false); return; }
      try { expectedData = JSON.parse(addExpected); } catch { setAddError('Invalid JSON in Expected Output'); setAddLoading(false); return; }
      const resp = await fetch(`${getBaseUrl()}/api/v1/flows/${flowId.trim()}/tests`, {
        method: 'POST',
        headers: jsonHeaders(),
        body: JSON.stringify({
          name: addName,
          description: addDesc || undefined,
          input: inputData,
          expected_output: expectedData,
          match_mode: addMatchMode,
        }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) { setAddError(data.detail ?? `Error ${resp.status}`); return; }
      setAddResult(data as TestCase);
      // Refresh list
      loadTests();
    } catch {
      setAddError('Network error');
    } finally {
      setAddLoading(false);
    }
  }

  async function loadTests() {
    if (!flowId.trim()) return;
    setListLoading(true);
    setListError(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/api/v1/flows/${flowId.trim()}/tests`, {
        headers: authHeaders(),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) { setListError(data.detail ?? `Error ${resp.status}`); return; }
      const raw = data.tests ?? data;
      setTests(Array.isArray(raw) ? raw : []);
    } catch {
      setListError('Network error');
    } finally {
      setListLoading(false);
    }
  }

  async function handleDelete(testId: string) {
    setDeleteError(null);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/api/v1/flows/${flowId.trim()}/tests/${testId}`,
        { method: 'DELETE', headers: authHeaders() },
      );
      if (!resp.ok && resp.status !== 204) {
        const data = await resp.json().catch(() => ({}));
        setDeleteError(data.detail ?? `Error ${resp.status}`);
        return;
      }
      setTests((prev) => prev.filter((t) => t.test_id !== testId));
    } catch {
      setDeleteError('Network error');
    }
  }

  async function loadSummary() {
    if (!flowId.trim()) return;
    setSummaryError(null);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/api/v1/flows/${flowId.trim()}/tests/summary`,
        { headers: authHeaders() },
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) { setSummaryError(data.detail ?? `Error ${resp.status}`); return; }
      setSummary(data as SuiteSummary);
    } catch {
      setSummaryError('Network error');
    }
  }

  async function handleRun() {
    if (!flowId.trim()) return;
    setRunLoading(true);
    setRunError(null);
    setRunResults(null);
    setExitCode(null);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/api/v1/flows/${flowId.trim()}/tests/run`,
        { method: 'POST', headers: authHeaders() },
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) { setRunError(data.detail ?? `Error ${resp.status}`); return; }
      setRunResults(data.results ?? []);
      setExitCode(data.exit_code ?? null);
      setSummary(data.summary ?? null);
    } catch {
      setRunError('Network error');
    } finally {
      setRunLoading(false);
    }
  }

  async function loadResults() {
    if (!flowId.trim()) return;
    setResultsLoading(true);
    setResultsError(null);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/api/v1/flows/${flowId.trim()}/tests/results`,
        { headers: authHeaders() },
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) { setResultsError(data.detail ?? `Error ${resp.status}`); return; }
      const raw = data.results ?? data;
      setResults(Array.isArray(raw) ? raw : []);
    } catch {
      setResultsError('Network error');
    } finally {
      setResultsLoading(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  const statusColor = (s: string) =>
    s === 'pass' ? 'text-emerald-400' : s === 'fail' ? 'text-red-400' : 'text-amber-400';

  return (
    <MainLayout title="Flow Testing">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
          Flow Testing
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Manage test cases and run test suites for flows.
        </p>
      </div>

      {/* Flow ID input */}
      <div className="mb-6 flex gap-3" data-testid="flow-id-section">
        <input
          className="flex-1 rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500"
          placeholder="Flow ID"
          value={flowId}
          onChange={(e) => setFlowId(e.target.value)}
          data-testid="flow-id-input"
        />
        <button
          onClick={loadTests}
          className="rounded bg-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-600"
          data-testid="load-tests-btn"
        >
          Load Tests
        </button>
        <button
          onClick={loadSummary}
          className="rounded bg-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-600"
          data-testid="load-summary-btn"
        >
          Summary
        </button>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">

        {/* ---- Add Test Case ---- */}
        <section className="rounded border border-slate-700 bg-slate-800/30 p-4" data-testid="add-section">
          <h2 className="mb-3 text-sm font-semibold text-slate-300">Add Test Case</h2>
          <form onSubmit={handleAdd} className="space-y-3" data-testid="add-form">
            <input
              className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500"
              placeholder="Test name"
              value={addName}
              onChange={(e) => setAddName(e.target.value)}
              required
              data-testid="add-name-input"
            />
            <input
              className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500"
              placeholder="Description (optional)"
              value={addDesc}
              onChange={(e) => setAddDesc(e.target.value)}
              data-testid="add-desc-input"
            />
            <textarea
              className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-1.5 font-mono text-xs text-slate-200"
              rows={3}
              placeholder='Input JSON (e.g. {"key":"val"})'
              value={addInput}
              onChange={(e) => setAddInput(e.target.value)}
              data-testid="add-input-json"
            />
            <textarea
              className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-1.5 font-mono text-xs text-slate-200"
              rows={3}
              placeholder='Expected output JSON'
              value={addExpected}
              onChange={(e) => setAddExpected(e.target.value)}
              data-testid="add-expected-json"
            />
            <select
              className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200"
              value={addMatchMode}
              onChange={(e) => setAddMatchMode(e.target.value)}
              data-testid="add-match-mode"
            >
              <option value="exact">exact</option>
              <option value="contains">contains</option>
              <option value="regex">regex</option>
            </select>
            <button
              type="submit"
              disabled={addLoading || !flowId.trim() || !addName.trim()}
              className="rounded bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-500 disabled:opacity-50"
              data-testid="add-btn"
            >
              {addLoading ? 'Adding…' : 'Add Test Case'}
            </button>
          </form>
          {addError && (
            <p className="mt-2 text-xs text-red-400" data-testid="add-error">{addError}</p>
          )}
          {addResult && (
            <div className="mt-3 rounded border border-emerald-700/40 bg-emerald-900/10 p-3 text-xs" data-testid="add-result">
              <p className="text-emerald-300">Test case created</p>
              <p className="mt-1 text-slate-400">ID: <span className="font-mono" data-testid="new-test-id">{addResult.test_id}</span></p>
            </div>
          )}
        </section>

        {/* ---- Summary + Run ---- */}
        <section className="rounded border border-slate-700 bg-slate-800/30 p-4" data-testid="summary-section">
          <h2 className="mb-3 text-sm font-semibold text-slate-300">Suite Summary &amp; Run</h2>
          {summaryError && (
            <p className="mb-2 text-xs text-red-400" data-testid="summary-error">{summaryError}</p>
          )}
          {summary && (
            <div className="mb-4 grid grid-cols-3 gap-3" data-testid="summary-cards">
              <div className="rounded border border-slate-700 bg-slate-800/50 p-2 text-center text-xs">
                <p className="text-slate-500">Total</p>
                <p className="mt-1 font-bold text-slate-200" data-testid="summary-total">{summary.total}</p>
              </div>
              <div className="rounded border border-slate-700 bg-slate-800/50 p-2 text-center text-xs">
                <p className="text-slate-500">Passed</p>
                <p className="mt-1 font-bold text-emerald-400" data-testid="summary-passed">{summary.passed}</p>
              </div>
              <div className="rounded border border-slate-700 bg-slate-800/50 p-2 text-center text-xs">
                <p className="text-slate-500">Failed</p>
                <p className="mt-1 font-bold text-red-400" data-testid="summary-failed">{summary.failed}</p>
              </div>
            </div>
          )}
          <button
            onClick={handleRun}
            disabled={runLoading || !flowId.trim()}
            className="rounded bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-500 disabled:opacity-50"
            data-testid="run-btn"
          >
            {runLoading ? 'Running…' : 'Run Test Suite'}
          </button>
          {runError && (
            <p className="mt-2 text-xs text-red-400" data-testid="run-error">{runError}</p>
          )}
          {runResults !== null && (
            <div className="mt-3" data-testid="run-results">
              <p className="text-xs text-slate-400">
                Exit code: <span className={`font-bold ${exitCode === 0 ? 'text-emerald-400' : 'text-red-400'}`} data-testid="exit-code">{exitCode}</span>
              </p>
              <ul className="mt-2 space-y-1">
                {runResults.map((r) => (
                  <li key={r.result_id} className="text-xs" data-testid="run-result-item">
                    <span className="text-slate-400">{r.test_id.slice(0, 8)}…</span>
                    {' '}
                    <span className={statusColor(r.status)} data-testid="run-result-status">{r.status}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>

        {/* ---- Test Cases List ---- */}
        <section className="rounded border border-slate-700 bg-slate-800/30 p-4 lg:col-span-2" data-testid="tests-section">
          <h2 className="mb-3 text-sm font-semibold text-slate-300">Test Cases</h2>
          {listError && (
            <p className="mb-2 text-xs text-red-400" data-testid="list-error">{listError}</p>
          )}
          {deleteError && (
            <p className="mb-2 text-xs text-red-400" data-testid="delete-error">{deleteError}</p>
          )}
          {listLoading && (
            <p className="text-xs text-slate-500" data-testid="list-loading">Loading…</p>
          )}
          {!listLoading && tests.length === 0 && (
            <p className="text-xs text-slate-500" data-testid="no-tests">No test cases yet.</p>
          )}
          {tests.length > 0 && (
            <div className="overflow-x-auto" data-testid="tests-table">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-700 text-left text-slate-500">
                    <th className="pb-2 pr-4 font-medium">Name</th>
                    <th className="pb-2 pr-4 font-medium">Match Mode</th>
                    <th className="pb-2 pr-4 font-medium">Created By</th>
                    <th className="pb-2 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {tests.map((t) => (
                    <tr key={t.test_id} className="border-b border-slate-700/40" data-testid="test-row">
                      <td className="py-2 pr-4 text-slate-300" data-testid="test-name">{t.name}</td>
                      <td className="py-2 pr-4 text-slate-500">{t.match_mode}</td>
                      <td className="py-2 pr-4 text-slate-500">{t.created_by ?? '—'}</td>
                      <td className="py-2">
                        <button
                          onClick={() => handleDelete(t.test_id)}
                          className="rounded bg-red-900/30 px-2 py-0.5 text-xs text-red-400 hover:bg-red-900/50"
                          data-testid="delete-btn"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* ---- Results History ---- */}
        <section className="rounded border border-slate-700 bg-slate-800/30 p-4 lg:col-span-2" data-testid="results-section">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-300">Results History</h2>
            <button
              onClick={loadResults}
              disabled={!flowId.trim()}
              className="rounded bg-slate-700 px-3 py-1 text-xs text-slate-300 hover:bg-slate-600 disabled:opacity-50"
              data-testid="load-results-btn"
            >
              Load Results
            </button>
          </div>
          {resultsError && (
            <p className="mb-2 text-xs text-red-400" data-testid="results-error">{resultsError}</p>
          )}
          {resultsLoading && (
            <p className="text-xs text-slate-500" data-testid="results-loading">Loading…</p>
          )}
          {results !== null && results.length === 0 && (
            <p className="text-xs text-slate-500" data-testid="no-results">No results yet.</p>
          )}
          {results !== null && results.length > 0 && (
            <ul className="space-y-1" data-testid="results-list">
              {results.map((r) => (
                <li key={r.result_id} className="flex items-center gap-3 text-xs" data-testid="result-item">
                  <span className="font-mono text-slate-500">{r.result_id.slice(0, 8)}</span>
                  <span className={statusColor(r.status)} data-testid="result-status">{r.status}</span>
                  {r.error_message && (
                    <span className="text-red-400">{r.error_message}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </MainLayout>
  );
};

export default FlowTestingPage;
