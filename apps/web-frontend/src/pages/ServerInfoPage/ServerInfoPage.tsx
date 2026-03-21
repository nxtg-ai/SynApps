/**
 * ServerInfoPage — Server Version, Config & Metrics (N-98).
 *
 * Covers:
 *   GET /api/v1/version  → API version, supported versions, deprecated endpoints
 *   GET /api/v1/config   → server config (secrets redacted)
 *   GET /api/v1/metrics  → in-memory request metrics
 *
 * Route: /server-info (ProtectedRoute)
 */
import React, { useCallback, useEffect, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

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

type Tab = 'version' | 'config' | 'metrics';

const ServerInfoPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<Tab>('version');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<Record<string, unknown> | null>(null);

  const fetchTab = useCallback(async (tab: Tab) => {
    setLoading(true);
    setError(null);
    setData(null);
    const path = tab === 'version' ? '/version' : tab === 'config' ? '/config' : '/metrics';
    try {
      const resp = await fetch(`${getBaseUrl()}${path}`, { headers: authHeaders() });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        setError(err.detail ?? `Error ${resp.status}`);
        return;
      }
      setData(await resp.json());
    } catch {
      setError(`Network error loading ${tab}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTab(activeTab);
  }, [activeTab, fetchTab]);

  const handleTabChange = (tab: Tab) => {
    setActiveTab(tab);
  };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <MainLayout title="Server Info">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
            Server Info
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            API version, configuration, and runtime metrics.
          </p>
        </div>
        <button
          onClick={() => fetchTab(activeTab)}
          disabled={loading}
          className="rounded bg-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-600 disabled:opacity-50"
          data-testid="refresh-btn"
        >
          Refresh
        </button>
      </div>

      {/* Tabs */}
      <div className="mb-6 flex gap-2 border-b border-slate-700 pb-2" data-testid="info-tabs">
        {(['version', 'config', 'metrics'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => handleTabChange(tab)}
            className={`px-4 py-1.5 text-xs font-medium capitalize transition-colors ${
              activeTab === tab
                ? 'border-b-2 border-indigo-500 text-indigo-400'
                : 'text-slate-400 hover:text-slate-200'
            }`}
            data-testid={`tab-${tab}`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Content */}
      {loading && (
        <p className="text-xs text-slate-500" data-testid="info-loading">
          Loading…
        </p>
      )}
      {error && (
        <p className="text-sm text-red-400" data-testid="info-error">
          {error}
        </p>
      )}

      {/* Version tab */}
      {activeTab === 'version' && !loading && !error && data && (
        <div data-testid="version-panel">
          <dl className="space-y-3">
            <div className="rounded border border-slate-700 bg-slate-800/30 p-4">
              <dt className="mb-1 text-xs font-semibold text-slate-400">API Version</dt>
              <dd className="font-mono text-sm text-slate-100" data-testid="api-version">
                {String(data.api_version ?? '—')}
              </dd>
            </div>
            <div className="rounded border border-slate-700 bg-slate-800/30 p-4">
              <dt className="mb-1 text-xs font-semibold text-slate-400">App Version</dt>
              <dd className="font-mono text-sm text-slate-100" data-testid="app-version">
                {String(data.app_version ?? '—')}
              </dd>
            </div>
            <div className="rounded border border-slate-700 bg-slate-800/30 p-4">
              <dt className="mb-1 text-xs font-semibold text-slate-400">Supported Versions</dt>
              <dd className="text-sm text-slate-300" data-testid="supported-versions">
                {Array.isArray(data.supported_versions)
                  ? (data.supported_versions as string[]).join(', ')
                  : String(data.supported_versions ?? '—')}
              </dd>
            </div>
            <div className="rounded border border-slate-700 bg-slate-800/30 p-4">
              <dt className="mb-1 text-xs font-semibold text-slate-400">Sunset Grace Days</dt>
              <dd className="text-sm text-slate-300" data-testid="sunset-grace-days">
                {String(data.sunset_grace_days ?? '—')}
              </dd>
            </div>
            {Array.isArray(data.deprecated_endpoints) && data.deprecated_endpoints.length > 0 && (
              <div className="rounded border border-yellow-700/50 bg-yellow-900/20 p-4">
                <dt className="mb-2 text-xs font-semibold text-yellow-400">
                  Deprecated Endpoints ({(data.deprecated_endpoints as unknown[]).length})
                </dt>
                <dd data-testid="deprecated-list">
                  {(data.deprecated_endpoints as Record<string, unknown>[]).map((ep, i) => (
                    <div
                      key={i}
                      className="mb-1 text-xs text-slate-400"
                      data-testid="deprecated-item"
                    >
                      <span className="font-mono">
                        {String(ep.path ?? ep.endpoint ?? JSON.stringify(ep))}
                      </span>
                      {ep.sunset_date && (
                        <span className="ml-2 text-yellow-500">
                          sunset: {String(ep.sunset_date)}
                        </span>
                      )}
                    </div>
                  ))}
                </dd>
              </div>
            )}
          </dl>
        </div>
      )}

      {/* Config tab */}
      {activeTab === 'config' && !loading && !error && data && (
        <div data-testid="config-panel">
          {data._validation_errors &&
            Array.isArray(data._validation_errors) &&
            (data._validation_errors as unknown[]).length > 0 && (
              <div className="mb-4 rounded border border-red-700/50 bg-red-900/20 p-3">
                <p className="mb-1 text-xs font-semibold text-red-400">Validation Errors</p>
                {(data._validation_errors as string[]).map((err, i) => (
                  <p key={i} className="text-xs text-red-300" data-testid="config-validation-error">
                    {err}
                  </p>
                ))}
              </div>
            )}
          {data._env_file_loaded && (
            <p className="mb-4 text-xs text-slate-500" data-testid="env-file-loaded">
              Env file:{' '}
              <span className="font-mono">{String(data._env_file_loaded)}</span>
            </p>
          )}
          <div
            className="rounded border border-slate-700 bg-slate-900 p-4"
            data-testid="config-json"
          >
            <pre className="overflow-auto text-xs text-slate-300">
              {JSON.stringify(data, null, 2)}
            </pre>
          </div>
        </div>
      )}

      {/* Metrics tab */}
      {activeTab === 'metrics' && !loading && !error && data && (
        <div data-testid="metrics-panel">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {Object.entries(data).map(([key, val]) => (
              <div
                key={key}
                className="rounded border border-slate-700 bg-slate-800/30 p-3"
                data-testid="metric-card"
              >
                <p className="mb-1 text-xs text-slate-500">{key}</p>
                <p
                  className="font-mono text-sm font-semibold text-slate-100"
                  data-testid="metric-value"
                >
                  {typeof val === 'object' ? JSON.stringify(val) : String(val)}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </MainLayout>
  );
};

export default ServerInfoPage;
