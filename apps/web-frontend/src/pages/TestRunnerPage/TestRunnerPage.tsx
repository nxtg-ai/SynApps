/**
 * TestRunnerPage -- CI-compatible workflow test runner.
 *
 * Users define expected outputs, run workflows, compare results.
 * Route: /workflows/:id/tests
 */
import React, { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import MainLayout from '../../components/Layout/MainLayout';
import { apiService } from '../../services/ApiService';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TestCase {
  test_id: string;
  flow_id: string;
  name: string;
  description: string;
  input: Record<string, unknown>;
  expected_output: Record<string, unknown>;
  match_mode: 'exact' | 'contains' | 'keys_present';
  created_at: number;
  created_by: string;
}

interface TestResult {
  result_id: string;
  test_id: string;
  flow_id: string;
  run_id: string;
  status: 'pass' | 'fail' | 'error';
  actual_output: Record<string, unknown>;
  expected_output: Record<string, unknown>;
  diff: Record<string, { expected: unknown; actual: unknown }>;
  error_message: string;
  duration_ms: number;
  ran_at: number;
}

interface SuiteSummary {
  total: number;
  passed: number;
  failed: number;
  error: number;
  pass_rate_pct: number;
}

interface RunSuiteResponse {
  results: TestResult[];
  summary: SuiteSummary;
  exit_code: number;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const TestRunnerPage: React.FC = () => {
  const { id: flowId } = useParams<{ id: string }>();

  const [tests, setTests] = useState<TestCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Add form state
  const [formName, setFormName] = useState('');
  const [formDescription, setFormDescription] = useState('');
  const [formInput, setFormInput] = useState('{}');
  const [formExpected, setFormExpected] = useState('{}');
  const [formMatchMode, setFormMatchMode] = useState<'exact' | 'contains' | 'keys_present'>(
    'contains',
  );

  // Run results state
  const [runResults, setRunResults] = useState<TestResult[]>([]);
  const [summary, setSummary] = useState<SuiteSummary | null>(null);
  const [exitCode, setExitCode] = useState<number | null>(null);
  const [running, setRunning] = useState(false);

  const fetchTests = useCallback(async () => {
    if (!flowId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await apiService.getFlowTests(flowId);
      setTests(data.tests);
    } catch {
      setError('Failed to load test cases. Please try again.');
    } finally {
      setLoading(false);
    }
  }, [flowId]);

  useEffect(() => {
    fetchTests();
  }, [fetchTests]);

  const handleAddTest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!flowId) return;
    try {
      const inputParsed = JSON.parse(formInput);
      const expectedParsed = JSON.parse(formExpected);
      await apiService.addFlowTest(flowId, {
        name: formName,
        description: formDescription,
        input: inputParsed,
        expected_output: expectedParsed,
        match_mode: formMatchMode,
      });
      setFormName('');
      setFormDescription('');
      setFormInput('{}');
      setFormExpected('{}');
      setFormMatchMode('contains');
      await fetchTests();
    } catch {
      setError('Failed to add test case.');
    }
  };

  const handleDelete = async (testId: string) => {
    if (!flowId) return;
    try {
      await apiService.deleteFlowTest(flowId, testId);
      await fetchTests();
    } catch {
      setError('Failed to delete test case.');
    }
  };

  const handleRunSuite = async () => {
    if (!flowId) return;
    setRunning(true);
    setError(null);
    try {
      const data: RunSuiteResponse = await apiService.runFlowTests(flowId);
      setRunResults(data.results);
      setSummary(data.summary);
      setExitCode(data.exit_code);
    } catch {
      setError('Failed to run test suite.');
    } finally {
      setRunning(false);
    }
  };

  // --- Render helpers ---

  const matchModeBadge = (mode: string) => {
    const colors: Record<string, string> = {
      exact: 'bg-red-900/50 text-red-300',
      contains: 'bg-blue-900/50 text-blue-300',
      keys_present: 'bg-green-900/50 text-green-300',
    };
    return (
      <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${colors[mode] || 'bg-slate-700 text-slate-300'}`}>
        {mode}
      </span>
    );
  };

  const statusBadge = (status: string) => {
    if (status === 'pass')
      return <span className="rounded bg-green-900/50 px-2 py-0.5 text-xs font-bold text-green-300">PASS</span>;
    if (status === 'fail')
      return <span className="rounded bg-red-900/50 px-2 py-0.5 text-xs font-bold text-red-300">FAIL</span>;
    return <span className="rounded bg-yellow-900/50 px-2 py-0.5 text-xs font-bold text-yellow-300">ERROR</span>;
  };

  if (loading) {
    return (
      <MainLayout>
        <div data-testid="test-runner-page" className="p-6 text-slate-300" aria-label="Loading test runner">
          Loading test runner...
        </div>
      </MainLayout>
    );
  }

  if (error && tests.length === 0 && !runResults.length) {
    return (
      <MainLayout>
        <div data-testid="test-runner-page" className="p-6">
          <div data-testid="error-banner" className="rounded bg-red-900/30 p-4 text-red-300">
            {error}
          </div>
        </div>
      </MainLayout>
    );
  }

  return (
    <MainLayout>
      <div data-testid="test-runner-page" className="mx-auto max-w-5xl space-y-6 p-6 text-slate-100">
        <h1 className="text-2xl font-bold">Workflow Test Runner</h1>

        {error && (
          <div data-testid="error-banner" className="rounded bg-red-900/30 p-3 text-red-300">
            {error}
          </div>
        )}

        {/* Exit code banner */}
        {exitCode !== null && (
          <div
            data-testid="exit-code-banner"
            className={`rounded p-4 text-lg font-semibold ${exitCode === 0 ? 'bg-green-900/30 text-green-300' : 'bg-red-900/30 text-red-300'}`}
          >
            {exitCode === 0
              ? 'All tests passed'
              : `${summary ? summary.failed + summary.error : 0} test(s) failed`}
          </div>
        )}

        {/* Suite summary */}
        {summary && (
          <div data-testid="suite-summary" className="grid grid-cols-5 gap-3">
            <div className="rounded bg-slate-800 p-3 text-center">
              <div className="text-2xl font-bold">{summary.total}</div>
              <div className="text-xs text-slate-400">Total</div>
            </div>
            <div className="rounded bg-slate-800 p-3 text-center">
              <div className="text-2xl font-bold text-green-400">{summary.passed}</div>
              <div className="text-xs text-slate-400">Passed</div>
            </div>
            <div className="rounded bg-slate-800 p-3 text-center">
              <div className="text-2xl font-bold text-red-400">{summary.failed}</div>
              <div className="text-xs text-slate-400">Failed</div>
            </div>
            <div className="rounded bg-slate-800 p-3 text-center">
              <div className="text-2xl font-bold text-yellow-400">{summary.error}</div>
              <div className="text-xs text-slate-400">Error</div>
            </div>
            <div className="rounded bg-slate-800 p-3 text-center">
              <div className="text-2xl font-bold">{summary.pass_rate_pct}%</div>
              <div className="text-xs text-slate-400">Pass Rate</div>
            </div>
          </div>
        )}

        {/* Run suite button */}
        <button
          data-testid="run-suite-button"
          onClick={handleRunSuite}
          disabled={running}
          className="rounded bg-indigo-600 px-4 py-2 font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          {running ? 'Running...' : 'Run All Tests'}
        </button>

        {/* Results section */}
        {runResults.length > 0 && (
          <div className="space-y-3">
            <h2 className="text-lg font-semibold">Results</h2>
            {runResults.map((r) => (
              <div key={r.result_id} className="rounded border border-slate-700 bg-slate-800 p-4">
                <div className="flex items-center gap-3">
                  {statusBadge(r.status)}
                  <span className="font-medium">{r.test_id.slice(0, 8)}</span>
                  <span className="text-sm text-slate-400">{r.duration_ms.toFixed(0)}ms</span>
                </div>
                {r.status === 'fail' && Object.keys(r.diff).length > 0 && (
                  <div data-testid="diff-viewer" className="mt-3 space-y-1 rounded bg-slate-900 p-3 text-sm">
                    {Object.entries(r.diff).map(([key, val]) => (
                      <div key={key}>
                        <span className="font-mono text-slate-300">{key}:</span>{' '}
                        <span className="text-red-400">expected {JSON.stringify(val.expected)}</span>
                        {' -> '}
                        <span className="text-yellow-400">actual {JSON.stringify(val.actual)}</span>
                      </div>
                    ))}
                  </div>
                )}
                {r.status === 'error' && r.error_message && (
                  <div className="mt-2 text-sm text-red-400">{r.error_message}</div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Test cases list */}
        <div className="space-y-3">
          <h2 className="text-lg font-semibold">Test Cases ({tests.length})</h2>
          {tests.length === 0 && (
            <p className="text-sm text-slate-400">No test cases yet. Add one below.</p>
          )}
          {tests.map((tc) => (
            <div
              key={tc.test_id}
              data-testid={`test-case-${tc.test_id}`}
              className="flex items-start justify-between rounded border border-slate-700 bg-slate-800 p-4"
            >
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{tc.name}</span>
                  {matchModeBadge(tc.match_mode)}
                </div>
                {tc.description && (
                  <p className="text-sm text-slate-400">{tc.description}</p>
                )}
                <div className="text-xs text-slate-500">
                  Input: {JSON.stringify(tc.input).slice(0, 60)}
                  {' | '}
                  Expected: {JSON.stringify(tc.expected_output).slice(0, 60)}
                </div>
              </div>
              <button
                data-testid={`delete-test-${tc.test_id}`}
                onClick={() => handleDelete(tc.test_id)}
                className="rounded bg-red-900/30 px-3 py-1 text-sm text-red-300 hover:bg-red-900/50"
              >
                Delete
              </button>
            </div>
          ))}
        </div>

        {/* Add test form */}
        <form data-testid="add-test-form" onSubmit={handleAddTest} className="space-y-4 rounded border border-slate-700 bg-slate-800 p-4">
          <h2 className="text-lg font-semibold">Add Test Case</h2>

          <div>
            <label className="mb-1 block text-sm text-slate-300">Name</label>
            <input
              data-testid="test-name-input"
              type="text"
              value={formName}
              onChange={(e) => setFormName(e.target.value)}
              required
              className="w-full rounded bg-slate-900 px-3 py-2 text-slate-100"
              placeholder="Test case name"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm text-slate-300">Description</label>
            <input
              type="text"
              value={formDescription}
              onChange={(e) => setFormDescription(e.target.value)}
              className="w-full rounded bg-slate-900 px-3 py-2 text-slate-100"
              placeholder="Optional description"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm text-slate-300">Input (JSON)</label>
            <textarea
              data-testid="test-input-textarea"
              value={formInput}
              onChange={(e) => setFormInput(e.target.value)}
              rows={3}
              className="w-full rounded bg-slate-900 px-3 py-2 font-mono text-sm text-slate-100"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm text-slate-300">Expected Output (JSON)</label>
            <textarea
              data-testid="test-expected-textarea"
              value={formExpected}
              onChange={(e) => setFormExpected(e.target.value)}
              rows={3}
              className="w-full rounded bg-slate-900 px-3 py-2 font-mono text-sm text-slate-100"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm text-slate-300">Match Mode</label>
            <select
              data-testid="match-mode-select"
              value={formMatchMode}
              onChange={(e) => setFormMatchMode(e.target.value as 'exact' | 'contains' | 'keys_present')}
              className="rounded bg-slate-900 px-3 py-2 text-slate-100"
            >
              <option value="contains">contains</option>
              <option value="exact">exact</option>
              <option value="keys_present">keys_present</option>
            </select>
          </div>

          <button
            data-testid="submit-test-button"
            type="submit"
            className="rounded bg-emerald-600 px-4 py-2 font-medium text-white hover:bg-emerald-500"
          >
            Add Test Case
          </button>
        </form>
      </div>
    </MainLayout>
  );
};

export default TestRunnerPage;
