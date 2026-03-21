/** N-113 — OAuth Inspector & Monitoring Detail */
import React, { useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Tab = 'introspect' | 'authorize' | 'token' | 'monitoring';

interface IntrospectResult {
  active: boolean;
  sub?: string;
  client_id?: string;
  scope?: string;
  exp?: number;
  [key: string]: unknown;
}

interface AuthorizeResult {
  code?: string;
  state?: string;
  [key: string]: unknown;
}

interface TokenResult {
  access_token?: string;
  token_type?: string;
  expires_in?: number;
  scope?: string;
  [key: string]: unknown;
}

interface MonitoringWorkflow {
  flow_id: string;
  status: string;
  total_runs: number;
  success_rate: number;
  [key: string]: unknown;
}

interface MonitoringResult {
  workflow: MonitoringWorkflow;
  window_hours: number;
  [key: string]: unknown;
}

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

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const OAuthInspectorPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<Tab>('introspect');

  // --- Introspect state ---
  const [token, setToken] = useState('');
  const [introspectResult, setIntrospectResult] = useState<IntrospectResult | null>(null);
  const [introspectError, setIntrospectError] = useState<string | null>(null);
  const [introspectLoading, setIntrospectLoading] = useState(false);

  // --- Authorize state ---
  const [authClientId, setAuthClientId] = useState('');
  const [authRedirectUri, setAuthRedirectUri] = useState('http://localhost:3000/callback');
  const [authResponseType] = useState('code');
  const [authScope, setAuthScope] = useState('read');
  const [authState, setAuthState] = useState('');
  const [authorizeResult, setAuthorizeResult] = useState<AuthorizeResult | null>(null);
  const [authorizeError, setAuthorizeError] = useState<string | null>(null);
  const [authorizeLoading, setAuthorizeLoading] = useState(false);

  // --- Token state ---
  const [tokenGrantType, setTokenGrantType] = useState('authorization_code');
  const [tokenClientId, setTokenClientId] = useState('');
  const [tokenClientSecret, setTokenClientSecret] = useState('');
  const [tokenCode, setTokenCode] = useState('');
  const [tokenRedirectUri, setTokenRedirectUri] = useState('');
  const [tokenScope, setTokenScope] = useState('');
  const [tokenResult, setTokenResult] = useState<TokenResult | null>(null);
  const [tokenError, setTokenError] = useState<string | null>(null);
  const [tokenLoading, setTokenLoading] = useState(false);

  // --- Monitoring state ---
  const [monitoringFlowId, setMonitoringFlowId] = useState('');
  const [monitoringWindow, setMonitoringWindow] = useState(24);
  const [monitoringResult, setMonitoringResult] = useState<MonitoringResult | null>(null);
  const [monitoringError, setMonitoringError] = useState<string | null>(null);
  const [monitoringLoading, setMonitoringLoading] = useState(false);

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  const handleIntrospect = async () => {
    if (!token.trim()) return;
    setIntrospectLoading(true);
    setIntrospectError(null);
    setIntrospectResult(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/api/v1/oauth/introspect`, {
        method: 'POST',
        headers: {
          ...authHeaders(),
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: new URLSearchParams({ token }),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        setIntrospectError((data as { detail?: string }).detail ?? `Error ${resp.status}`);
        return;
      }
      const data: IntrospectResult = await resp.json();
      setIntrospectResult(data);
    } catch {
      setIntrospectError('Network error during introspection');
    } finally {
      setIntrospectLoading(false);
    }
  };

  const handleAuthorize = async () => {
    setAuthorizeLoading(true);
    setAuthorizeError(null);
    setAuthorizeResult(null);
    try {
      const params = new URLSearchParams({
        client_id: authClientId,
        redirect_uri: authRedirectUri,
        response_type: authResponseType,
        scope: authScope,
      });
      if (authState) params.set('state', authState);
      const resp = await fetch(`${getBaseUrl()}/api/v1/oauth/authorize?${params.toString()}`, {
        headers: authHeaders(),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        setAuthorizeError((data as { detail?: string }).detail ?? `Error ${resp.status}`);
        return;
      }
      const data: AuthorizeResult = await resp.json();
      setAuthorizeResult(data);
    } catch {
      setAuthorizeError('Network error during authorization');
    } finally {
      setAuthorizeLoading(false);
    }
  };

  const handleGetToken = async () => {
    setTokenLoading(true);
    setTokenError(null);
    setTokenResult(null);
    try {
      const body = new URLSearchParams({
        grant_type: tokenGrantType,
        client_id: tokenClientId,
        client_secret: tokenClientSecret,
        code: tokenCode,
        redirect_uri: tokenRedirectUri,
        scope: tokenScope,
      });
      const resp = await fetch(`${getBaseUrl()}/api/v1/oauth/token`, {
        method: 'POST',
        headers: {
          ...authHeaders(),
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body,
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        setTokenError((data as { detail?: string }).detail ?? `Error ${resp.status}`);
        return;
      }
      const data: TokenResult = await resp.json();
      setTokenResult(data);
    } catch {
      setTokenError('Network error fetching token');
    } finally {
      setTokenLoading(false);
    }
  };

  const handleLoadMonitoring = async () => {
    if (!monitoringFlowId.trim()) return;
    setMonitoringLoading(true);
    setMonitoringError(null);
    setMonitoringResult(null);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/api/v1/monitoring/workflows/${encodeURIComponent(monitoringFlowId)}?window_hours=${monitoringWindow}`,
        { headers: authHeaders() },
      );
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        if (resp.status === 404) {
          setMonitoringError(
            (data as { detail?: string }).detail ?? 'Workflow not found',
          );
        } else {
          setMonitoringError(
            (data as { detail?: string }).detail ?? `Error ${resp.status}`,
          );
        }
        return;
      }
      const data: MonitoringResult = await resp.json();
      setMonitoringResult(data);
    } catch {
      setMonitoringError('Network error loading monitoring detail');
    } finally {
      setMonitoringLoading(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Tab definitions
  // ---------------------------------------------------------------------------

  const tabs: { id: Tab; label: string }[] = [
    { id: 'introspect', label: 'Introspect' },
    { id: 'authorize', label: 'Authorize' },
    { id: 'token', label: 'Token' },
    { id: 'monitoring', label: 'Monitoring' },
  ];

  const tabTestId: Record<Tab, string> = {
    introspect: 'tab-introspect',
    authorize: 'tab-authorize',
    token: 'tab-token',
    monitoring: 'tab-monitoring',
  };

  const panelTestId: Record<Tab, string> = {
    introspect: 'tab-panel-introspect',
    authorize: 'tab-panel-authorize',
    token: 'tab-panel-token',
    monitoring: 'tab-panel-monitoring',
  };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <MainLayout title="OAuth Inspector">
      {/* Page header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
          OAuth Inspector
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Inspect tokens, drive the OAuth2 authorization flow, and view per-workflow monitoring
          detail.
        </p>
      </div>

      {/* Tab bar */}
      <div className="mb-6 flex gap-1 border-b border-slate-700">
        {tabs.map((t) => (
          <button
            key={t.id}
            data-testid={tabTestId[t.id]}
            onClick={() => setActiveTab(t.id)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === t.id
                ? 'border-b-2 border-indigo-500 text-indigo-400'
                : 'text-slate-400 hover:text-slate-300'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Tab 1 — Introspect                                                  */}
      {/* ------------------------------------------------------------------ */}
      {activeTab === 'introspect' && (
        <div data-testid={panelTestId.introspect} className="space-y-4">
          <h2 className="text-sm font-semibold text-slate-300">Token Introspection</h2>

          <textarea
            data-testid="token-input"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="Paste a token here…"
            rows={4}
            className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-2 font-mono text-sm text-slate-200 focus:outline-none"
          />

          <button
            data-testid="introspect-btn"
            onClick={handleIntrospect}
            disabled={introspectLoading || !token.trim()}
            className="rounded bg-indigo-700 px-4 py-1.5 text-sm text-white hover:bg-indigo-600 disabled:opacity-50"
          >
            {introspectLoading ? 'Introspecting…' : 'Introspect'}
          </button>

          {introspectError && (
            <p className="text-sm text-red-400" data-testid="introspect-error">
              {introspectError}
            </p>
          )}

          {introspectResult && (
            <div
              data-testid="introspect-result"
              className="rounded border border-slate-700 bg-slate-800/40 p-4 space-y-2 text-sm"
            >
              <p>
                <span className="text-slate-400">Status: </span>
                <span
                  data-testid="introspect-active"
                  className={introspectResult.active ? 'text-emerald-400' : 'text-red-400'}
                >
                  {introspectResult.active ? 'active' : 'inactive'}
                </span>
              </p>

              {introspectResult.active && (
                <>
                  <p>
                    <span className="text-slate-400">Subject: </span>
                    <span data-testid="introspect-sub" className="font-mono text-slate-200">
                      {introspectResult.sub}
                    </span>
                  </p>
                  <p>
                    <span className="text-slate-400">Client ID: </span>
                    <span data-testid="introspect-client-id" className="font-mono text-slate-200">
                      {introspectResult.client_id}
                    </span>
                  </p>
                  <p>
                    <span className="text-slate-400">Scope: </span>
                    <span data-testid="introspect-scope" className="font-mono text-slate-200">
                      {introspectResult.scope}
                    </span>
                  </p>
                </>
              )}

              <pre
                data-testid="introspect-json"
                className="mt-3 overflow-auto rounded bg-slate-900 p-3 text-xs text-slate-300"
              >
                {JSON.stringify(introspectResult, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Tab 2 — Authorize                                                   */}
      {/* ------------------------------------------------------------------ */}
      {activeTab === 'authorize' && (
        <div data-testid={panelTestId.authorize} className="space-y-4">
          <h2 className="text-sm font-semibold text-slate-300">Authorization Code Request</h2>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">Client ID</span>
              <input
                type="text"
                data-testid="auth-client-id"
                value={authClientId}
                onChange={(e) => setAuthClientId(e.target.value)}
                className="rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">Redirect URI</span>
              <input
                type="text"
                data-testid="auth-redirect-uri"
                value={authRedirectUri}
                onChange={(e) => setAuthRedirectUri(e.target.value)}
                className="rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">Response Type</span>
              <input
                type="text"
                data-testid="auth-response-type"
                value={authResponseType}
                readOnly
                className="rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-400 focus:outline-none"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">Scope</span>
              <input
                type="text"
                data-testid="auth-scope"
                value={authScope}
                onChange={(e) => setAuthScope(e.target.value)}
                className="rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">State (optional)</span>
              <input
                type="text"
                data-testid="auth-state"
                value={authState}
                onChange={(e) => setAuthState(e.target.value)}
                className="rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
              />
            </label>
          </div>

          <button
            data-testid="authorize-btn"
            onClick={handleAuthorize}
            disabled={authorizeLoading}
            className="rounded bg-indigo-700 px-4 py-1.5 text-sm text-white hover:bg-indigo-600 disabled:opacity-50"
          >
            {authorizeLoading ? 'Authorizing…' : 'Get Auth Code'}
          </button>

          {authorizeError && (
            <p className="text-sm text-red-400" data-testid="authorize-error">
              {authorizeError}
            </p>
          )}

          {authorizeResult && (
            <div
              data-testid="authorize-result"
              className="rounded border border-slate-700 bg-slate-800/40 p-4 space-y-2 text-sm"
            >
              <p>
                <span className="text-slate-400">Auth Code: </span>
                <span data-testid="auth-code" className="font-mono text-emerald-400">
                  {authorizeResult.code}
                </span>
              </p>
            </div>
          )}
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Tab 3 — Token                                                       */}
      {/* ------------------------------------------------------------------ */}
      {activeTab === 'token' && (
        <div data-testid={panelTestId.token} className="space-y-4">
          <h2 className="text-sm font-semibold text-slate-300">Token Exchange</h2>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">Grant Type</span>
              <select
                data-testid="token-grant-type"
                value={tokenGrantType}
                onChange={(e) => setTokenGrantType(e.target.value)}
                className="rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
              >
                <option value="authorization_code">authorization_code</option>
                <option value="client_credentials">client_credentials</option>
              </select>
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">Client ID</span>
              <input
                type="text"
                data-testid="token-client-id"
                value={tokenClientId}
                onChange={(e) => setTokenClientId(e.target.value)}
                className="rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">Client Secret</span>
              <input
                type="password"
                data-testid="token-client-secret"
                value={tokenClientSecret}
                onChange={(e) => setTokenClientSecret(e.target.value)}
                className="rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
              />
            </label>

            {tokenGrantType === 'authorization_code' && (
              <>
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-slate-400">Authorization Code</span>
                  <input
                    type="text"
                    data-testid="token-code"
                    value={tokenCode}
                    onChange={(e) => setTokenCode(e.target.value)}
                    className="rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
                  />
                </label>

                <label className="flex flex-col gap-1">
                  <span className="text-xs text-slate-400">Redirect URI</span>
                  <input
                    type="text"
                    data-testid="token-redirect-uri"
                    value={tokenRedirectUri}
                    onChange={(e) => setTokenRedirectUri(e.target.value)}
                    className="rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
                  />
                </label>
              </>
            )}

            {tokenGrantType === 'client_credentials' && (
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Scope</span>
                <input
                  type="text"
                  data-testid="token-scope"
                  value={tokenScope}
                  onChange={(e) => setTokenScope(e.target.value)}
                  className="rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
                />
              </label>
            )}
          </div>

          <button
            data-testid="get-token-btn"
            onClick={handleGetToken}
            disabled={tokenLoading}
            className="rounded bg-indigo-700 px-4 py-1.5 text-sm text-white hover:bg-indigo-600 disabled:opacity-50"
          >
            {tokenLoading ? 'Fetching…' : 'Get Token'}
          </button>

          {tokenError && (
            <p className="text-sm text-red-400" data-testid="token-error">
              {tokenError}
            </p>
          )}

          {tokenResult && (
            <div
              data-testid="token-result"
              className="rounded border border-slate-700 bg-slate-800/40 p-4 space-y-2 text-sm"
            >
              <p>
                <span className="text-slate-400">Access Token: </span>
                <span data-testid="token-access-token" className="font-mono text-emerald-400 break-all">
                  {tokenResult.access_token}
                </span>
              </p>
              <p>
                <span className="text-slate-400">Token Type: </span>
                <span data-testid="token-type" className="font-mono text-slate-200">
                  {tokenResult.token_type}
                </span>
              </p>
              <p>
                <span className="text-slate-400">Expires In: </span>
                <span data-testid="token-expires-in" className="font-mono text-slate-200">
                  {tokenResult.expires_in}
                </span>
              </p>
              <p>
                <span className="text-slate-400">Scope: </span>
                <span data-testid="token-scope-result" className="font-mono text-slate-200">
                  {tokenResult.scope}
                </span>
              </p>
            </div>
          )}
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Tab 4 — Monitoring                                                  */}
      {/* ------------------------------------------------------------------ */}
      {activeTab === 'monitoring' && (
        <div data-testid={panelTestId.monitoring} className="space-y-4">
          <h2 className="text-sm font-semibold text-slate-300">Workflow Monitoring Detail</h2>

          <div className="flex flex-wrap gap-3 items-end">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">Flow ID</span>
              <input
                type="text"
                data-testid="monitoring-flow-id"
                value={monitoringFlowId}
                onChange={(e) => setMonitoringFlowId(e.target.value)}
                placeholder="e.g. flow-abc"
                className="rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">Window (hours)</span>
              <input
                type="number"
                data-testid="monitoring-window"
                value={monitoringWindow}
                onChange={(e) => setMonitoringWindow(Number(e.target.value))}
                min={1}
                className="w-24 rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
              />
            </label>

            <button
              data-testid="load-monitoring-btn"
              onClick={handleLoadMonitoring}
              disabled={monitoringLoading || !monitoringFlowId.trim()}
              className="rounded bg-indigo-700 px-4 py-1.5 text-sm text-white hover:bg-indigo-600 disabled:opacity-50"
            >
              {monitoringLoading ? 'Loading…' : 'Load'}
            </button>
          </div>

          {monitoringLoading && (
            <p className="text-xs text-slate-500" data-testid="monitoring-loading">
              Loading…
            </p>
          )}

          {monitoringError && (
            <p className="text-sm text-red-400" data-testid="monitoring-error">
              {monitoringError}
            </p>
          )}

          {monitoringResult && (
            <div
              data-testid="monitoring-result"
              className="rounded border border-slate-700 bg-slate-800/40 p-4 space-y-2 text-sm"
            >
              <p>
                <span className="text-slate-400">Flow ID: </span>
                <span data-testid="monitoring-flow-id-result" className="font-mono text-slate-200">
                  {monitoringResult.workflow.flow_id}
                </span>
              </p>
              <p>
                <span className="text-slate-400">Status: </span>
                <span
                  data-testid="monitoring-status"
                  className={
                    monitoringResult.workflow.status === 'healthy'
                      ? 'text-emerald-400'
                      : monitoringResult.workflow.status === 'degraded'
                        ? 'text-yellow-400'
                        : 'text-red-400'
                  }
                >
                  {monitoringResult.workflow.status}
                </span>
              </p>
              <p>
                <span className="text-slate-400">Total Runs: </span>
                <span data-testid="monitoring-total-runs" className="font-mono text-slate-200">
                  {monitoringResult.workflow.total_runs}
                </span>
              </p>
              <p>
                <span className="text-slate-400">Success Rate: </span>
                <span data-testid="monitoring-success-rate" className="font-mono text-slate-200">
                  {monitoringResult.workflow.success_rate}
                </span>
              </p>

              <pre
                data-testid="monitoring-json"
                className="mt-3 overflow-auto rounded bg-slate-900 p-3 text-xs text-slate-300"
              >
                {JSON.stringify(monitoringResult, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </MainLayout>
  );
};

export default OAuthInspectorPage;
