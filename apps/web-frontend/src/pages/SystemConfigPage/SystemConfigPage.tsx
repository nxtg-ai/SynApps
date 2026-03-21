/**
 * SystemConfigPage — Server version, metrics snapshot, and config (N-108).
 *
 * Covers:
 *   GET /version   → API version, supported versions, deprecated endpoints
 *   GET /metrics   → In-memory request metrics snapshot
 *   GET /config    → Server config (secrets redacted)
 *
 * Route: /system-config (ProtectedRoute)
 */
import React, { useCallback, useEffect, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface VersionData {
  api_version: string;
  app_version: string;
  supported_versions?: string[];
  deprecated_endpoints?: Array<{ path: string; sunset?: string }>;
  sunset_grace_days?: number;
  [key: string]: unknown;
}

interface MetricsData {
  [key: string]: unknown;
}

interface ConfigData {
  _validation_errors?: string[];
  _env_file_loaded?: string | null;
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

type TabId = 'version' | 'metrics' | 'config';

const SystemConfigPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabId>('version');

  const [version, setVersion] = useState<VersionData | null>(null);
  const [versionError, setVersionError] = useState<string | null>(null);
  const [versionLoading, setVersionLoading] = useState(false);

  const [metrics, setMetrics] = useState<MetricsData | null>(null);
  const [metricsError, setMetricsError] = useState<string | null>(null);
  const [metricsLoading, setMetricsLoading] = useState(false);

  const [config, setConfig] = useState<ConfigData | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [configLoading, setConfigLoading] = useState(false);

  const loadVersion = useCallback(async () => {
    setVersionLoading(true);
    setVersionError(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/api/v1/version`);
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) { setVersionError(data.detail ?? `Error ${resp.status}`); return; }
      setVersion(data as VersionData);
    } catch {
      setVersionError('Network error');
    } finally {
      setVersionLoading(false);
    }
  }, []);

  const loadMetrics = useCallback(async () => {
    setMetricsLoading(true);
    setMetricsError(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/api/v1/metrics`, { headers: authHeaders() });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) { setMetricsError(data.detail ?? `Error ${resp.status}`); return; }
      setMetrics(data as MetricsData);
    } catch {
      setMetricsError('Network error');
    } finally {
      setMetricsLoading(false);
    }
  }, []);

  const loadConfig = useCallback(async () => {
    setConfigLoading(true);
    setConfigError(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/api/v1/config`, { headers: authHeaders() });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) { setConfigError(data.detail ?? `Error ${resp.status}`); return; }
      setConfig(data as ConfigData);
    } catch {
      setConfigError('Network error');
    } finally {
      setConfigLoading(false);
    }
  }, []);

  useEffect(() => {
    loadVersion();
    loadMetrics();
    loadConfig();
  }, [loadVersion, loadMetrics, loadConfig]);

  return (
    <MainLayout title="System Config">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
            System Config
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            API version, runtime metrics, and server configuration.
          </p>
        </div>
        <button
          onClick={() => { loadVersion(); loadMetrics(); loadConfig(); }}
          disabled={versionLoading || metricsLoading || configLoading}
          className="rounded bg-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-600 disabled:opacity-50"
          data-testid="refresh-btn"
        >
          Refresh All
        </button>
      </div>

      {/* Tabs */}
      <div className="mb-6 flex gap-1 border-b border-slate-700" data-testid="tabs">
        {(['version', 'metrics', 'config'] as TabId[]).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm capitalize ${activeTab === tab ? 'border-b-2 border-indigo-500 text-indigo-400' : 'text-slate-500 hover:text-slate-300'}`}
            data-testid={`tab-${tab}`}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {/* ---- Version tab ---- */}
      {activeTab === 'version' && (
        <div data-testid="tab-panel-version">
          {versionError && (
            <p className="mb-4 text-sm text-red-400" data-testid="version-error">{versionError}</p>
          )}
          {versionLoading && !version && (
            <p className="text-xs text-slate-500" data-testid="version-loading">Loading…</p>
          )}
          {version && (
            <div className="space-y-4" data-testid="version-detail">
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                <div className="rounded border border-slate-700 bg-slate-800/30 p-3 text-xs">
                  <p className="text-slate-500">API Version</p>
                  <p className="mt-1 font-semibold text-slate-200" data-testid="api-version">
                    {version.api_version}
                  </p>
                </div>
                <div className="rounded border border-slate-700 bg-slate-800/30 p-3 text-xs">
                  <p className="text-slate-500">App Version</p>
                  <p className="mt-1 font-semibold text-slate-200" data-testid="app-version">
                    {version.app_version}
                  </p>
                </div>
                {version.sunset_grace_days !== undefined && (
                  <div className="rounded border border-slate-700 bg-slate-800/30 p-3 text-xs">
                    <p className="text-slate-500">Sunset Grace Days</p>
                    <p className="mt-1 font-semibold text-slate-200" data-testid="sunset-days">
                      {version.sunset_grace_days}
                    </p>
                  </div>
                )}
              </div>
              {Array.isArray(version.supported_versions) && version.supported_versions.length > 0 && (
                <div data-testid="supported-versions">
                  <p className="mb-2 text-xs font-semibold text-slate-400">Supported Versions</p>
                  <div className="flex flex-wrap gap-2">
                    {version.supported_versions.map((v) => (
                      <span
                        key={v}
                        className="rounded bg-emerald-900/20 px-2 py-0.5 text-xs text-emerald-300"
                        data-testid="supported-version-item"
                      >
                        {v}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {Array.isArray(version.deprecated_endpoints) && version.deprecated_endpoints.length > 0 && (
                <div data-testid="deprecated-section">
                  <p className="mb-2 text-xs font-semibold text-slate-400">Deprecated Endpoints</p>
                  <ul className="space-y-1">
                    {version.deprecated_endpoints.map((ep, i) => (
                      <li key={i} className="text-xs text-slate-500" data-testid="deprecated-item">
                        <span className="font-mono text-amber-400">{ep.path}</span>
                        {ep.sunset && <span className="ml-2">→ sunset {ep.sunset}</span>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ---- Metrics tab ---- */}
      {activeTab === 'metrics' && (
        <div data-testid="tab-panel-metrics">
          {metricsError && (
            <p className="mb-4 text-sm text-red-400" data-testid="metrics-error">{metricsError}</p>
          )}
          {metricsLoading && !metrics && (
            <p className="text-xs text-slate-500" data-testid="metrics-loading">Loading…</p>
          )}
          {metrics && (
            <div data-testid="metrics-detail">
              <pre className="overflow-x-auto rounded border border-slate-700 bg-slate-900 p-4 text-xs text-slate-300" data-testid="metrics-json">
                {JSON.stringify(metrics, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}

      {/* ---- Config tab ---- */}
      {activeTab === 'config' && (
        <div data-testid="tab-panel-config">
          {configError && (
            <p className="mb-4 text-sm text-red-400" data-testid="config-error">{configError}</p>
          )}
          {configLoading && !config && (
            <p className="text-xs text-slate-500" data-testid="config-loading">Loading…</p>
          )}
          {config && (
            <div className="space-y-4" data-testid="config-detail">
              {config._env_file_loaded !== undefined && (
                <p className="text-xs text-slate-400" data-testid="env-file">
                  Env file: <span className="font-mono">{config._env_file_loaded ?? 'not found'}</span>
                </p>
              )}
              {Array.isArray(config._validation_errors) && config._validation_errors.length > 0 && (
                <div data-testid="validation-errors">
                  <p className="mb-1 text-xs font-semibold text-red-400">Validation Errors</p>
                  <ul className="space-y-1">
                    {config._validation_errors.map((e, i) => (
                      <li key={i} className="text-xs text-red-400" data-testid="validation-error-item">{e}</li>
                    ))}
                  </ul>
                </div>
              )}
              <pre className="overflow-x-auto rounded border border-slate-700 bg-slate-900 p-4 text-xs text-slate-300" data-testid="config-json">
                {JSON.stringify(config, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </MainLayout>
  );
};

export default SystemConfigPage;
