/** N-112 — Workflow Test Runner */
import React, { useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getBaseUrl(): string {
  return (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');
}
function authHeaders(): Record<string, string> {
  const tok = localStorage.getItem('access_token') ?? '';
  return { Authorization: `Bearer ${tok}` };
}
function jsonHeaders(): Record<string, string> {
  return { ...authHeaders(), 'Content-Type': 'application/json' };
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AssertionResult {
  assertion: string;
  passed: boolean;
}

interface TestResult {
  id: string;
  workflow_id: string;
  run_id: string;
  suite_name?: string;
  passed: boolean;
  assertion_count: number;
  pass_count: number;
  fail_count: number;
  assertion_results: AssertionResult[];
  run_status: string;
  timestamp: number;
}

interface HistoryItem {
  id: string;
  run_id: string;
  passed: boolean;
  suite_name?: string;
}

interface HistoryResponse {
  workflow_id: string;
  total: number;
  history: HistoryItem[];
}

interface SuiteRecord {
  suite_id: string;
  name: string;
  workflow_id?: string;
}

interface SuitesResponse {
  workflow_id: string;
  total: number;
  suites: SuiteRecord[];
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

type Tab = 'run' | 'history' | 'suites';

const WorkflowTestRunnerPage: React.FC = () => {
  const [flowId, setFlowId] = useState('');
  const [activeTab, setActiveTab] = useState<Tab>('run');

  // --- Tab 1: Run Test ---
  const [inputJson, setInputJson] = useState('{}');
  const [assertionsText, setAssertionsText] = useState('');
  const [suiteName, setSuiteName] = useState('');
  const [saveResult, setSaveResult] = useState(false);
  const [runLoading, setRunLoading] = useState(false);
  const [runResult, setRunResult] = useState<TestResult | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  // --- Tab 2: Test History ---
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyData, setHistoryData] = useState<HistoryResponse | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);

  // --- Tab 3: Test Suites — Save ---
  const [saveSuiteName, setSaveSuiteName] = useState('');
  const [saveSuiteJson, setSaveSuiteJson] = useState('{}');
  const [saveSuiteLoading, setSaveSuiteLoading] = useState(false);
  const [savedSuite, setSavedSuite] = useState<SuiteRecord | null>(null);
  const [saveSuiteError, setSaveSuiteError] = useState<string | null>(null);

  // --- Tab 3: Test Suites — List ---
  const [suitesLoading, setSuitesLoading] = useState(false);
  const [suitesData, setSuitesData] = useState<SuitesResponse | null>(null);
  const [suitesError, setSuitesError] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  const handleRunTest = async () => {
    setRunError(null);
    setRunResult(null);

    let parsedInput: unknown;
    try {
      parsedInput = JSON.parse(inputJson);
    } catch {
      setRunError('Invalid input JSON — please enter valid JSON.');
      return;
    }

    const assertions = assertionsText
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean);

    setRunLoading(true);
    try {
      const resp = await fetch(`${getBaseUrl()}/api/v1/workflows/${flowId}/test`, {
        method: 'POST',
        headers: jsonHeaders(),
        body: JSON.stringify({
          input: parsedInput,
          assertions,
          suite_name: suiteName || undefined,
          save_result: saveResult,
        }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }));
        setRunError(body.detail ?? `Request failed (${resp.status})`);
        return;
      }
      const data: TestResult = await resp.json();
      setRunResult(data);
    } catch {
      setRunError('Network error running test.');
    } finally {
      setRunLoading(false);
    }
  };

  const handleLoadHistory = async () => {
    setHistoryError(null);
    setHistoryData(null);
    setHistoryLoading(true);
    try {
      const resp = await fetch(`${getBaseUrl()}/api/v1/workflows/${flowId}/test-history`, {
        headers: authHeaders(),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }));
        setHistoryError(body.detail ?? `Request failed (${resp.status})`);
        return;
      }
      const data: HistoryResponse = await resp.json();
      setHistoryData(data);
    } catch {
      setHistoryError('Network error loading history.');
    } finally {
      setHistoryLoading(false);
    }
  };

  const handleSaveSuite = async () => {
    setSaveSuiteError(null);
    setSavedSuite(null);

    let parsedExtra: Record<string, unknown>;
    try {
      const raw = JSON.parse(saveSuiteJson);
      if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
        setSaveSuiteError('Invalid JSON in suite fields — must be a JSON object.');
        return;
      }
      parsedExtra = raw as Record<string, unknown>;
    } catch {
      setSaveSuiteError('Invalid JSON in suite fields — please enter valid JSON.');
      return;
    }

    setSaveSuiteLoading(true);
    try {
      const resp = await fetch(`${getBaseUrl()}/api/v1/workflows/${flowId}/test-suites`, {
        method: 'POST',
        headers: jsonHeaders(),
        body: JSON.stringify({ name: saveSuiteName, ...parsedExtra }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }));
        setSaveSuiteError(body.detail ?? `Request failed (${resp.status})`);
        return;
      }
      const data: SuiteRecord = await resp.json();
      setSavedSuite(data);
    } catch {
      setSaveSuiteError('Network error saving suite.');
    } finally {
      setSaveSuiteLoading(false);
    }
  };

  const handleLoadSuites = async () => {
    setSuitesError(null);
    setSuitesData(null);
    setSuitesLoading(true);
    try {
      const resp = await fetch(`${getBaseUrl()}/api/v1/workflows/${flowId}/test-suites`, {
        headers: authHeaders(),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }));
        setSuitesError(body.detail ?? `Request failed (${resp.status})`);
        return;
      }
      const data: SuitesResponse = await resp.json();
      setSuitesData(data);
    } catch {
      setSuitesError('Network error loading suites.');
    } finally {
      setSuitesLoading(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Tab classes
  // ---------------------------------------------------------------------------

  const tabClass = (tab: Tab) =>
    `px-4 py-2 text-sm font-medium rounded-t border-b-2 transition-colors ${
      activeTab === tab
        ? 'border-blue-500 text-blue-400 bg-slate-800/60'
        : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800/30'
    }`;

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <MainLayout title="Workflow Test Runner">
      <h1 className="mb-2 text-2xl font-bold text-slate-100" data-testid="page-title">
        Workflow Test Runner
      </h1>
      <p className="mb-6 text-sm text-slate-400">
        Run tests against a workflow with mock inputs and assertions, browse history, and manage
        saved test suites.
      </p>

      {/* Shared flow ID input */}
      <div className="mb-6">
        <label className="mb-1 block text-xs text-slate-400">Workflow ID</label>
        <input
          type="text"
          value={flowId}
          onChange={(e) => setFlowId(e.target.value)}
          placeholder="flow-abc123"
          className="w-full max-w-sm rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
          data-testid="flow-id-input"
        />
      </div>

      {/* Tab bar */}
      <div className="mb-0 flex gap-1 border-b border-slate-700">
        <button
          className={tabClass('run')}
          onClick={() => setActiveTab('run')}
          data-testid="tab-run"
        >
          Run Test
        </button>
        <button
          className={tabClass('history')}
          onClick={() => setActiveTab('history')}
          data-testid="tab-history"
        >
          Test History
        </button>
        <button
          className={tabClass('suites')}
          onClick={() => setActiveTab('suites')}
          data-testid="tab-suites"
        >
          Test Suites
        </button>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Tab 1 — Run Test                                                    */}
      {/* ------------------------------------------------------------------ */}
      {activeTab === 'run' && (
        <div
          className="rounded-b rounded-tr border border-slate-700 bg-slate-800/30 p-5"
          data-testid="tab-panel-run"
        >
          <div className="mb-4">
            <label className="mb-1 block text-xs text-slate-400">Input JSON</label>
            <textarea
              rows={5}
              value={inputJson}
              onChange={(e) => setInputJson(e.target.value)}
              placeholder="{}"
              className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 font-mono text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
              data-testid="run-test-input-json"
            />
          </div>

          <div className="mb-4">
            <label className="mb-1 block text-xs text-slate-400">
              Assertions{' '}
              <span className="text-slate-500">(one per line, e.g. status == success)</span>
            </label>
            <textarea
              rows={4}
              value={assertionsText}
              onChange={(e) => setAssertionsText(e.target.value)}
              placeholder="status == success"
              className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 font-mono text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
              data-testid="assertions-input"
            />
          </div>

          <div className="mb-4 flex flex-wrap gap-4">
            <div className="flex-1">
              <label className="mb-1 block text-xs text-slate-400">Suite name (optional)</label>
              <input
                type="text"
                value={suiteName}
                onChange={(e) => setSuiteName(e.target.value)}
                placeholder="smoke"
                className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
                data-testid="suite-name-input"
              />
            </div>

            <div className="flex items-end gap-2 pb-1">
              <input
                type="checkbox"
                id="save-result-check"
                checked={saveResult}
                onChange={(e) => setSaveResult(e.target.checked)}
                className="h-4 w-4 rounded border-slate-600 bg-slate-800 text-blue-500"
                data-testid="save-result-check"
              />
              <label htmlFor="save-result-check" className="text-xs text-slate-400">
                Save result
              </label>
            </div>
          </div>

          <button
            onClick={handleRunTest}
            disabled={runLoading || !flowId.trim()}
            className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
            data-testid="run-test-btn"
          >
            {runLoading ? 'Running…' : 'Run Test'}
          </button>

          {/* Error */}
          {runError && (
            <div
              className="mt-4 rounded border border-red-700 bg-red-900/40 px-4 py-2 text-sm text-red-300"
              data-testid="run-test-error"
            >
              {runError}
            </div>
          )}

          {/* Result */}
          {runResult && (
            <div
              className="mt-4 rounded border border-slate-700 bg-slate-800/60 p-4"
              data-testid="run-test-result"
            >
              <div className="mb-3 flex flex-wrap items-center gap-4">
                <span
                  className={`inline-flex items-center rounded px-2 py-0.5 text-sm font-bold ${
                    runResult.passed
                      ? 'bg-emerald-900/50 text-emerald-300'
                      : 'bg-red-900/50 text-red-300'
                  }`}
                  data-testid="result-passed"
                >
                  {runResult.passed ? 'PASSED' : 'FAILED'}
                </span>
                <span className="text-xs text-slate-400">
                  Run ID:{' '}
                  <span className="font-mono text-slate-200" data-testid="result-run-id">
                    {runResult.run_id}
                  </span>
                </span>
                <span className="text-xs text-slate-400">
                  Pass:{' '}
                  <span className="font-semibold text-emerald-300" data-testid="result-pass-count">
                    {runResult.pass_count}
                  </span>
                </span>
                <span className="text-xs text-slate-400">
                  Fail:{' '}
                  <span className="font-semibold text-red-300" data-testid="result-fail-count">
                    {runResult.fail_count}
                  </span>
                </span>
              </div>

              {runResult.assertion_results.length > 0 && (
                <div className="space-y-1" data-testid="result-assertions">
                  {runResult.assertion_results.map((ar, i) => (
                    <div
                      key={i}
                      className={`flex items-center gap-2 rounded border px-3 py-1.5 text-xs ${
                        ar.passed
                          ? 'border-emerald-800 bg-emerald-900/20 text-emerald-200'
                          : 'border-red-800 bg-red-900/20 text-red-200'
                      }`}
                      data-testid="assertion-row"
                    >
                      <span
                        className="font-bold"
                        data-testid="assertion-status"
                      >
                        {ar.passed ? '✓' : '✗'}
                      </span>
                      <span className="font-mono">{ar.assertion}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Tab 2 — Test History                                                */}
      {/* ------------------------------------------------------------------ */}
      {activeTab === 'history' && (
        <div
          className="rounded-b rounded-tr border border-slate-700 bg-slate-800/30 p-5"
          data-testid="tab-panel-history"
        >
          <button
            onClick={handleLoadHistory}
            disabled={historyLoading || !flowId.trim()}
            className="mb-4 rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
            data-testid="load-history-btn"
          >
            {historyLoading ? 'Loading…' : 'Load History'}
          </button>

          {historyLoading && (
            <p className="text-sm text-slate-400" data-testid="history-loading">
              Loading history…
            </p>
          )}

          {historyError && (
            <div
              className="rounded border border-red-700 bg-red-900/40 px-4 py-2 text-sm text-red-300"
              data-testid="history-error"
            >
              {historyError}
            </div>
          )}

          {historyData && !historyLoading && (
            <>
              {historyData.history.length === 0 ? (
                <p className="text-sm text-slate-500" data-testid="no-history">
                  No test runs recorded for this workflow yet.
                </p>
              ) : (
                <div className="space-y-1" data-testid="history-list">
                  {historyData.history.map((item) => (
                    <div
                      key={item.id}
                      className={`flex items-center gap-3 rounded border px-3 py-2 text-sm ${
                        item.passed
                          ? 'border-emerald-800 bg-emerald-900/20 text-emerald-200'
                          : 'border-red-800 bg-red-900/20 text-red-200'
                      }`}
                      data-testid="history-item"
                    >
                      <span className="font-bold" data-testid="history-item-passed">
                        {item.passed ? 'PASSED' : 'FAILED'}
                      </span>
                      <span className="font-mono text-xs text-slate-400" data-testid="history-item-run-id">
                        {item.run_id}
                      </span>
                      {item.suite_name && (
                        <span className="text-xs text-slate-500">{item.suite_name}</span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Tab 3 — Test Suites                                                 */}
      {/* ------------------------------------------------------------------ */}
      {activeTab === 'suites' && (
        <div
          className="rounded-b rounded-tr border border-slate-700 bg-slate-800/30 p-5"
          data-testid="tab-panel-suites"
        >
          {/* Save Suite sub-section */}
          <div className="mb-8">
            <h2 className="mb-3 text-sm font-semibold text-slate-300">Save Test Suite</h2>

            <div className="mb-3">
              <label className="mb-1 block text-xs text-slate-400">Suite Name</label>
              <input
                type="text"
                value={saveSuiteName}
                onChange={(e) => setSaveSuiteName(e.target.value)}
                placeholder="My Suite"
                className="w-full max-w-sm rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
                data-testid="save-suite-name-input"
              />
            </div>

            <div className="mb-3">
              <label className="mb-1 block text-xs text-slate-400">
                Extra Suite Fields (JSON)
              </label>
              <textarea
                rows={4}
                value={saveSuiteJson}
                onChange={(e) => setSaveSuiteJson(e.target.value)}
                placeholder="{}"
                className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 font-mono text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
                data-testid="save-suite-json"
              />
            </div>

            <button
              onClick={handleSaveSuite}
              disabled={saveSuiteLoading || !flowId.trim()}
              className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
              data-testid="save-suite-btn"
            >
              {saveSuiteLoading ? 'Saving…' : 'Save Suite'}
            </button>

            {saveSuiteError && (
              <div
                className="mt-3 rounded border border-red-700 bg-red-900/40 px-4 py-2 text-sm text-red-300"
                data-testid="save-suite-error"
              >
                {saveSuiteError}
              </div>
            )}

            {savedSuite && (
              <div
                className="mt-3 rounded border border-emerald-800 bg-emerald-900/20 px-4 py-2 text-sm text-emerald-200"
                data-testid="save-suite-result"
              >
                Suite saved. ID:{' '}
                <span className="font-mono" data-testid="saved-suite-id">
                  {savedSuite.suite_id}
                </span>
              </div>
            )}
          </div>

          {/* List Suites sub-section */}
          <div>
            <h2 className="mb-3 text-sm font-semibold text-slate-300">Test Suites</h2>

            <button
              onClick={handleLoadSuites}
              disabled={suitesLoading || !flowId.trim()}
              className="mb-4 rounded bg-slate-700 px-4 py-2 text-sm text-slate-200 hover:bg-slate-600 disabled:opacity-50"
              data-testid="load-suites-btn"
            >
              {suitesLoading ? 'Loading…' : 'Load Suites'}
            </button>

            {suitesLoading && (
              <p className="text-sm text-slate-400" data-testid="suites-loading">
                Loading suites…
              </p>
            )}

            {suitesError && (
              <div
                className="rounded border border-red-700 bg-red-900/40 px-4 py-2 text-sm text-red-300"
                data-testid="suites-error"
              >
                {suitesError}
              </div>
            )}

            {suitesData && !suitesLoading && (
              <>
                {suitesData.suites.length === 0 ? (
                  <p className="text-sm text-slate-500" data-testid="no-suites">
                    No test suites saved for this workflow yet.
                  </p>
                ) : (
                  <div className="space-y-1" data-testid="suites-list">
                    {suitesData.suites.map((suite) => (
                      <div
                        key={suite.suite_id}
                        className="flex items-center gap-3 rounded border border-slate-700 bg-slate-800/40 px-3 py-2 text-sm text-slate-200"
                        data-testid="suite-item"
                      >
                        <span data-testid="suite-item-name">{suite.name}</span>
                        <span className="font-mono text-xs text-slate-500">{suite.suite_id}</span>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </MainLayout>
  );
};

export default WorkflowTestRunnerPage;
