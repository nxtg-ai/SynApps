/**
 * TemplateToolsPage — Advanced template operations (N-103).
 *
 * Covers:
 *   POST /templates/validate              → dry-run validation
 *   GET  /templates/{id}/by-semver        → fetch template by semver version
 *   PUT  /templates/{id}/rollback         → rollback template to a semver
 *   POST /templates/{id}/run-async        → async template execution
 *   GET  /tasks/{task_id}                 → poll async task status/result
 *
 * Route: /template-tools (ProtectedRoute)
 */
import React, { useCallback, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ValidationResult {
  valid: boolean;
  errors?: string[];
  warnings?: string[];
  [key: string]: unknown;
}

interface TemplateEntry {
  id: string;
  name?: string;
  semver?: string;
  version?: number;
  nodes?: unknown[];
  edges?: unknown[];
  [key: string]: unknown;
}

interface TaskStatus {
  task_id: string;
  status: string;
  result?: unknown;
  error?: string | null;
  [key: string]: unknown;
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

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const TemplateToolsPage: React.FC = () => {
  // Validate
  const [validateJson, setValidateJson] = useState('');
  const [validating, setValidating] = useState(false);
  const [validateError, setValidateError] = useState<string | null>(null);
  const [validateResult, setValidateResult] = useState<ValidationResult | null>(null);

  // By semver
  const [semverTemplateId, setSemverTemplateId] = useState('');
  const [semverVersion, setSemverVersion] = useState('');
  const [fetchingSemver, setFetchingSemver] = useState(false);
  const [semverError, setSemverError] = useState<string | null>(null);
  const [semverResult, setSemverResult] = useState<TemplateEntry | null>(null);

  // Rollback
  const [rollbackTemplateId, setRollbackTemplateId] = useState('');
  const [rollbackVersion, setRollbackVersion] = useState('');
  const [rollingBack, setRollingBack] = useState(false);
  const [rollbackError, setRollbackError] = useState<string | null>(null);
  const [rollbackResult, setRollbackResult] = useState<TemplateEntry | null>(null);

  // Run async
  const [runTemplateId, setRunTemplateId] = useState('');
  const [runInputJson, setRunInputJson] = useState('{}');
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState<TaskStatus | null>(null);
  const [polling, setPolling] = useState(false);
  const [pollError, setPollError] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // Validate
  // ---------------------------------------------------------------------------

  const handleValidate = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setValidating(true);
      setValidateError(null);
      setValidateResult(null);
      try {
        let body: Record<string, unknown> = {};
        try {
          body = JSON.parse(validateJson || '{}');
        } catch {
          setValidateError('Invalid JSON');
          return;
        }
        const resp = await fetch(`${getBaseUrl()}/templates/validate`, {
          method: 'POST',
          headers: { ...authHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          setValidateError(err.detail ?? `Error ${resp.status}`);
          return;
        }
        setValidateResult(await resp.json());
      } catch {
        setValidateError('Network error during validation');
      } finally {
        setValidating(false);
      }
    },
    [validateJson],
  );

  // ---------------------------------------------------------------------------
  // By semver
  // ---------------------------------------------------------------------------

  const handleFetchBySemver = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!semverTemplateId.trim()) return;
      setFetchingSemver(true);
      setSemverError(null);
      setSemverResult(null);
      try {
        const params = semverVersion.trim()
          ? `?version=${encodeURIComponent(semverVersion.trim())}`
          : '';
        const resp = await fetch(
          `${getBaseUrl()}/templates/${encodeURIComponent(semverTemplateId.trim())}/by-semver${params}`,
          { headers: authHeaders() },
        );
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          setSemverError(err.detail ?? `Error ${resp.status}`);
          return;
        }
        setSemverResult(await resp.json());
      } catch {
        setSemverError('Network error fetching template');
      } finally {
        setFetchingSemver(false);
      }
    },
    [semverTemplateId, semverVersion],
  );

  // ---------------------------------------------------------------------------
  // Rollback
  // ---------------------------------------------------------------------------

  const handleRollback = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!rollbackTemplateId.trim() || !rollbackVersion.trim()) return;
      setRollingBack(true);
      setRollbackError(null);
      setRollbackResult(null);
      try {
        const resp = await fetch(
          `${getBaseUrl()}/templates/${encodeURIComponent(rollbackTemplateId.trim())}/rollback?version=${encodeURIComponent(rollbackVersion.trim())}`,
          { method: 'PUT', headers: authHeaders() },
        );
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          setRollbackError(err.detail ?? `Error ${resp.status}`);
          return;
        }
        setRollbackResult(await resp.json());
      } catch {
        setRollbackError('Network error during rollback');
      } finally {
        setRollingBack(false);
      }
    },
    [rollbackTemplateId, rollbackVersion],
  );

  // ---------------------------------------------------------------------------
  // Run async
  // ---------------------------------------------------------------------------

  const handleRunAsync = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!runTemplateId.trim()) return;
      setRunning(true);
      setRunError(null);
      setTaskId(null);
      setTaskStatus(null);
      try {
        let input: Record<string, unknown> = {};
        try {
          input = JSON.parse(runInputJson || '{}');
        } catch {
          setRunError('Invalid JSON for input');
          return;
        }
        const resp = await fetch(
          `${getBaseUrl()}/templates/${encodeURIComponent(runTemplateId.trim())}/run-async`,
          {
            method: 'POST',
            headers: { ...authHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify({ input }),
          },
        );
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          setRunError(err.detail ?? `Error ${resp.status}`);
          return;
        }
        const data = await resp.json();
        setTaskId(data.task_id ?? null);
      } catch {
        setRunError('Network error starting async run');
      } finally {
        setRunning(false);
      }
    },
    [runTemplateId, runInputJson],
  );

  const handlePollTask = useCallback(async () => {
    if (!taskId) return;
    setPolling(true);
    setPollError(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/tasks/${encodeURIComponent(taskId)}`, {
        headers: authHeaders(),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        setPollError(err.detail ?? `Error ${resp.status}`);
        return;
      }
      setTaskStatus(await resp.json());
    } catch {
      setPollError('Network error polling task');
    } finally {
      setPolling(false);
    }
  }, [taskId]);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <MainLayout title="Template Tools">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
          Template Tools
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Validate, version-query, rollback, and async-run templates.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* ---- Validate ---- */}
        <section
          className="rounded border border-slate-700 bg-slate-800/30 p-4"
          data-testid="validate-section"
        >
          <h2 className="mb-3 text-sm font-semibold text-slate-300">Validate Template</h2>
          <form onSubmit={handleValidate} className="space-y-3" data-testid="validate-form">
            <textarea
              value={validateJson}
              onChange={(e) => setValidateJson(e.target.value)}
              placeholder='{"name":"My Template","nodes":[],"edges":[]}'
              rows={4}
              className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-2 font-mono text-xs text-slate-200 focus:outline-none"
              data-testid="validate-json-input"
            />
            <button
              type="submit"
              disabled={validating}
              className="rounded bg-indigo-700 px-4 py-1.5 text-sm text-white hover:bg-indigo-600 disabled:opacity-50"
              data-testid="validate-btn"
            >
              {validating ? 'Validating…' : 'Validate'}
            </button>
          </form>
          {validateError && (
            <p className="mt-2 text-sm text-red-400" data-testid="validate-error">
              {validateError}
            </p>
          )}
          {validateResult && (
            <div
              className={`mt-3 rounded border p-3 text-xs ${validateResult.valid ? 'border-emerald-700/50 bg-emerald-900/20' : 'border-red-700/50 bg-red-900/20'}`}
              data-testid="validate-result"
            >
              <p
                className={`font-semibold ${validateResult.valid ? 'text-emerald-400' : 'text-red-400'}`}
                data-testid="validate-valid"
              >
                {validateResult.valid ? 'Valid ✓' : 'Invalid ✗'}
              </p>
              {Array.isArray(validateResult.errors) && validateResult.errors.length > 0 && (
                <ul className="mt-1 space-y-0.5 text-red-300" data-testid="validate-errors">
                  {validateResult.errors.map((err, i) => (
                    <li key={i}>{err}</li>
                  ))}
                </ul>
              )}
              {Array.isArray(validateResult.warnings) && validateResult.warnings.length > 0 && (
                <ul className="mt-1 space-y-0.5 text-yellow-300" data-testid="validate-warnings">
                  {validateResult.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </section>

        {/* ---- By semver ---- */}
        <section
          className="rounded border border-slate-700 bg-slate-800/30 p-4"
          data-testid="semver-section"
        >
          <h2 className="mb-3 text-sm font-semibold text-slate-300">Fetch by Semver</h2>
          <form onSubmit={handleFetchBySemver} className="space-y-3" data-testid="semver-form">
            <input
              type="text"
              value={semverTemplateId}
              onChange={(e) => setSemverTemplateId(e.target.value)}
              placeholder="Template ID"
              className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
              data-testid="semver-template-id-input"
            />
            <input
              type="text"
              value={semverVersion}
              onChange={(e) => setSemverVersion(e.target.value)}
              placeholder="Version (e.g. 1.2.3) — leave blank for latest"
              className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
              data-testid="semver-version-input"
            />
            <button
              type="submit"
              disabled={fetchingSemver || !semverTemplateId.trim()}
              className="rounded bg-indigo-700 px-4 py-1.5 text-sm text-white hover:bg-indigo-600 disabled:opacity-50"
              data-testid="semver-btn"
            >
              {fetchingSemver ? 'Fetching…' : 'Fetch'}
            </button>
          </form>
          {semverError && (
            <p className="mt-2 text-sm text-red-400" data-testid="semver-error">
              {semverError}
            </p>
          )}
          {semverResult && (
            <div
              className="mt-3 rounded border border-slate-700/50 bg-slate-900/40 p-3 text-xs"
              data-testid="semver-result"
            >
              <p className="font-semibold text-slate-300">
                <span data-testid="semver-result-name">{semverResult.name ?? semverResult.id}</span>
              </p>
              <p className="mt-0.5 text-slate-500">
                semver: <span data-testid="semver-result-semver">{semverResult.semver}</span>
                {' | '}v<span data-testid="semver-result-version">{semverResult.version}</span>
              </p>
            </div>
          )}
        </section>

        {/* ---- Rollback ---- */}
        <section
          className="rounded border border-slate-700 bg-slate-800/30 p-4"
          data-testid="rollback-section"
        >
          <h2 className="mb-3 text-sm font-semibold text-slate-300">Rollback Template</h2>
          <form onSubmit={handleRollback} className="space-y-3" data-testid="rollback-form">
            <input
              type="text"
              value={rollbackTemplateId}
              onChange={(e) => setRollbackTemplateId(e.target.value)}
              placeholder="Template ID"
              className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
              data-testid="rollback-template-id-input"
            />
            <input
              type="text"
              value={rollbackVersion}
              onChange={(e) => setRollbackVersion(e.target.value)}
              placeholder="Target semver (e.g. 1.0.0)"
              className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
              data-testid="rollback-version-input"
            />
            <button
              type="submit"
              disabled={rollingBack || !rollbackTemplateId.trim() || !rollbackVersion.trim()}
              className="rounded bg-amber-700 px-4 py-1.5 text-sm text-white hover:bg-amber-600 disabled:opacity-50"
              data-testid="rollback-btn"
            >
              {rollingBack ? 'Rolling back…' : 'Rollback'}
            </button>
          </form>
          {rollbackError && (
            <p className="mt-2 text-sm text-red-400" data-testid="rollback-error">
              {rollbackError}
            </p>
          )}
          {rollbackResult && (
            <div
              className="mt-3 rounded border border-emerald-700/50 bg-emerald-900/20 p-3 text-xs"
              data-testid="rollback-result"
            >
              <p className="font-semibold text-emerald-400">Rollback complete!</p>
              <p className="mt-1 text-slate-300">
                New semver:{' '}
                <span className="font-mono" data-testid="rollback-new-semver">
                  {rollbackResult.semver}
                </span>
              </p>
            </div>
          )}
        </section>

        {/* ---- Run async ---- */}
        <section
          className="rounded border border-slate-700 bg-slate-800/30 p-4"
          data-testid="run-async-section"
        >
          <h2 className="mb-3 text-sm font-semibold text-slate-300">Run Template (Async)</h2>
          <form onSubmit={handleRunAsync} className="space-y-3" data-testid="run-async-form">
            <input
              type="text"
              value={runTemplateId}
              onChange={(e) => setRunTemplateId(e.target.value)}
              placeholder="Template ID"
              className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
              data-testid="run-template-id-input"
            />
            <textarea
              value={runInputJson}
              onChange={(e) => setRunInputJson(e.target.value)}
              placeholder='{"key":"value"}'
              rows={3}
              className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-2 font-mono text-xs text-slate-200 focus:outline-none"
              data-testid="run-input-json"
            />
            <button
              type="submit"
              disabled={running || !runTemplateId.trim()}
              className="rounded bg-indigo-700 px-4 py-1.5 text-sm text-white hover:bg-indigo-600 disabled:opacity-50"
              data-testid="run-async-btn"
            >
              {running ? 'Starting…' : 'Run Async'}
            </button>
          </form>
          {runError && (
            <p className="mt-2 text-sm text-red-400" data-testid="run-error">
              {runError}
            </p>
          )}
          {taskId && (
            <div
              className="mt-3 rounded border border-slate-700/50 bg-slate-900/40 p-3 text-xs"
              data-testid="task-created"
            >
              <p className="font-semibold text-emerald-400">Task started!</p>
              <p className="mt-1 text-slate-300">
                Task ID:{' '}
                <span className="font-mono" data-testid="task-id">
                  {taskId}
                </span>
              </p>
              <button
                onClick={handlePollTask}
                disabled={polling}
                className="mt-2 rounded bg-slate-700 px-3 py-1 text-xs text-slate-300 hover:bg-slate-600 disabled:opacity-50"
                data-testid="poll-btn"
              >
                {polling ? 'Polling…' : 'Poll Status'}
              </button>
              {pollError && (
                <p className="mt-1 text-red-400" data-testid="poll-error">
                  {pollError}
                </p>
              )}
              {taskStatus && (
                <div className="mt-2" data-testid="task-status">
                  <p className="text-slate-300">
                    Status:{' '}
                    <span className="font-mono text-yellow-300" data-testid="task-status-value">
                      {taskStatus.status}
                    </span>
                  </p>
                </div>
              )}
            </div>
          )}
        </section>
      </div>
    </MainLayout>
  );
};

export default TemplateToolsPage;
