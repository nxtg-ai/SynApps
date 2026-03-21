/**
 * PortfolioDashboardPage — System status, portfolio health, and user profile (N-105).
 *
 * Covers:
 *   GET /dashboard/portfolio  → templates + providers + health summary
 *   GET /health/detailed      → database, providers, last template run, uptime
 *   GET /auth/me              → authenticated user profile
 *
 * Route: /portfolio (ProtectedRoute)
 */
import React, { useCallback, useEffect, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PortfolioData {
  templates: Array<{ name: string; last_run?: unknown; [key: string]: unknown }>;
  template_count: number;
  providers: Array<{ name: string; configured: boolean; model_count: number; reason?: string }>;
  provider_count: number;
  health: { status: string; database: string; uptime_seconds: number; version?: string };
  [key: string]: unknown;
}

interface DetailedHealth {
  status: string;
  database: string;
  uptime_seconds: number;
  providers?: Array<{ name: string; configured: boolean; [key: string]: unknown }>;
  last_template_run?: unknown;
  [key: string]: unknown;
}

interface UserProfile {
  id: string;
  email: string;
  is_active: boolean;
  created_at?: string | number;
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

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

type TabId = 'portfolio' | 'health' | 'profile';

const PortfolioDashboardPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabId>('portfolio');

  // Portfolio
  const [loadingPortfolio, setLoadingPortfolio] = useState(false);
  const [portfolioError, setPortfolioError] = useState<string | null>(null);
  const [portfolio, setPortfolio] = useState<PortfolioData | null>(null);

  // Detailed health
  const [loadingHealth, setLoadingHealth] = useState(false);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [health, setHealth] = useState<DetailedHealth | null>(null);

  // User profile
  const [loadingProfile, setLoadingProfile] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);

  // ---------------------------------------------------------------------------
  // Fetchers
  // ---------------------------------------------------------------------------

  const loadPortfolio = useCallback(async () => {
    setLoadingPortfolio(true);
    setPortfolioError(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/dashboard/portfolio`, {
        headers: authHeaders(),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        setPortfolioError(err.detail ?? `Error ${resp.status}`);
        return;
      }
      setPortfolio(await resp.json());
    } catch {
      setPortfolioError('Network error loading portfolio');
    } finally {
      setLoadingPortfolio(false);
    }
  }, []);

  const loadHealth = useCallback(async () => {
    setLoadingHealth(true);
    setHealthError(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/health/detailed`, {
        headers: authHeaders(),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        setHealthError(err.detail ?? `Error ${resp.status}`);
        return;
      }
      setHealth(await resp.json());
    } catch {
      setHealthError('Network error loading health');
    } finally {
      setLoadingHealth(false);
    }
  }, []);

  const loadProfile = useCallback(async () => {
    setLoadingProfile(true);
    setProfileError(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/auth/me`, {
        headers: authHeaders(),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        setProfileError(err.detail ?? `Error ${resp.status}`);
        return;
      }
      setProfile(await resp.json());
    } catch {
      setProfileError('Network error loading profile');
    } finally {
      setLoadingProfile(false);
    }
  }, []);

  // Load all on mount
  useEffect(() => {
    loadPortfolio();
    loadHealth();
    loadProfile();
  }, [loadPortfolio, loadHealth, loadProfile]);

  // ---------------------------------------------------------------------------
  // Render helpers
  // ---------------------------------------------------------------------------

  const statusBadge = (status: string) => {
    const color =
      status === 'healthy' || status === 'reachable' || status === 'ok'
        ? 'text-emerald-400'
        : 'text-red-400';
    return <span className={`font-semibold ${color}`}>{status}</span>;
  };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <MainLayout title="Portfolio Dashboard">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
            Portfolio Dashboard
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            System health, template statuses, provider registry, and user profile.
          </p>
        </div>
        <button
          onClick={() => { loadPortfolio(); loadHealth(); loadProfile(); }}
          disabled={loadingPortfolio || loadingHealth || loadingProfile}
          className="rounded bg-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-600 disabled:opacity-50"
          data-testid="refresh-btn"
        >
          Refresh All
        </button>
      </div>

      {/* Tabs */}
      <div className="mb-6 flex gap-1 border-b border-slate-700" data-testid="tabs">
        {(['portfolio', 'health', 'profile'] as TabId[]).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm capitalize ${activeTab === tab ? 'border-b-2 border-indigo-500 text-indigo-400' : 'text-slate-500 hover:text-slate-300'}`}
            data-testid={`tab-${tab}`}
          >
            {tab === 'portfolio' ? 'Portfolio' : tab === 'health' ? 'Health' : 'Profile'}
          </button>
        ))}
      </div>

      {/* ---- Portfolio tab ---- */}
      {activeTab === 'portfolio' && (
        <div data-testid="tab-panel-portfolio">
          {portfolioError && (
            <p className="mb-4 text-sm text-red-400" data-testid="portfolio-error">
              {portfolioError}
            </p>
          )}
          {loadingPortfolio && !portfolio && (
            <p className="text-xs text-slate-500" data-testid="portfolio-loading">Loading…</p>
          )}
          {portfolio && (
            <>
              {/* Health summary */}
              <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4" data-testid="health-summary">
                <div className="rounded border border-slate-700 bg-slate-800/30 p-3 text-xs">
                  <p className="text-slate-500">Status</p>
                  <p className="mt-1" data-testid="portfolio-status">
                    {statusBadge(portfolio.health.status)}
                  </p>
                </div>
                <div className="rounded border border-slate-700 bg-slate-800/30 p-3 text-xs">
                  <p className="text-slate-500">Database</p>
                  <p className="mt-1" data-testid="portfolio-db">
                    {statusBadge(portfolio.health.database)}
                  </p>
                </div>
                <div className="rounded border border-slate-700 bg-slate-800/30 p-3 text-xs">
                  <p className="text-slate-500">Uptime</p>
                  <p className="mt-1 font-semibold text-slate-300" data-testid="portfolio-uptime">
                    {formatUptime(portfolio.health.uptime_seconds)}
                  </p>
                </div>
                <div className="rounded border border-slate-700 bg-slate-800/30 p-3 text-xs">
                  <p className="text-slate-500">Templates</p>
                  <p className="mt-1 font-semibold text-slate-300" data-testid="portfolio-template-count">
                    {portfolio.template_count}
                  </p>
                </div>
              </div>

              {/* Providers */}
              <section className="mb-6" data-testid="providers-section">
                <h2 className="mb-2 text-sm font-semibold text-slate-300">
                  Providers ({portfolio.provider_count})
                </h2>
                <div className="flex flex-wrap gap-2">
                  {portfolio.providers.map((p) => (
                    <div
                      key={p.name}
                      className={`rounded border px-3 py-1.5 text-xs ${p.configured ? 'border-emerald-700/40 bg-emerald-900/10 text-emerald-300' : 'border-slate-700 bg-slate-900/40 text-slate-500'}`}
                      data-testid="provider-badge"
                    >
                      {p.name}
                      {p.configured && (
                        <span className="ml-1 text-slate-400">({p.model_count} models)</span>
                      )}
                    </div>
                  ))}
                </div>
              </section>

              {/* Templates */}
              <section data-testid="templates-section">
                <h2 className="mb-2 text-sm font-semibold text-slate-300">Templates</h2>
                {portfolio.templates.length === 0 ? (
                  <p className="text-xs text-slate-500" data-testid="no-templates">
                    No templates found.
                  </p>
                ) : (
                  <div className="overflow-x-auto" data-testid="templates-table">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b border-slate-700 text-left text-slate-500">
                          <th className="pb-2 pr-4 font-medium">Name</th>
                          <th className="pb-2 font-medium">Last Run</th>
                        </tr>
                      </thead>
                      <tbody>
                        {portfolio.templates.map((t, i) => (
                          <tr key={i} className="border-b border-slate-700/40" data-testid="template-row">
                            <td className="py-2 pr-4 text-slate-300">{t.name}</td>
                            <td className="py-2 text-slate-500">
                              {t.last_run ? String(t.last_run) : 'never'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            </>
          )}
        </div>
      )}

      {/* ---- Health tab ---- */}
      {activeTab === 'health' && (
        <div data-testid="tab-panel-health">
          {healthError && (
            <p className="mb-4 text-sm text-red-400" data-testid="health-error">
              {healthError}
            </p>
          )}
          {loadingHealth && !health && (
            <p className="text-xs text-slate-500" data-testid="health-loading">Loading…</p>
          )}
          {health && (
            <div className="space-y-4" data-testid="health-detail">
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                <div className="rounded border border-slate-700 bg-slate-800/30 p-3 text-xs">
                  <p className="text-slate-500">Status</p>
                  <p className="mt-1" data-testid="health-status">
                    {statusBadge(health.status)}
                  </p>
                </div>
                <div className="rounded border border-slate-700 bg-slate-800/30 p-3 text-xs">
                  <p className="text-slate-500">Database</p>
                  <p className="mt-1" data-testid="health-db">
                    {statusBadge(health.database)}
                  </p>
                </div>
                <div className="rounded border border-slate-700 bg-slate-800/30 p-3 text-xs">
                  <p className="text-slate-500">Uptime</p>
                  <p className="mt-1 font-semibold text-slate-300" data-testid="health-uptime">
                    {formatUptime(health.uptime_seconds)}
                  </p>
                </div>
              </div>
              {Array.isArray(health.providers) && health.providers.length > 0 && (
                <div data-testid="health-providers">
                  <p className="mb-2 text-xs font-semibold text-slate-400">Provider Health</p>
                  <div className="flex flex-wrap gap-2">
                    {health.providers.map((p) => (
                      <span
                        key={p.name}
                        className={`rounded px-2 py-0.5 text-xs ${p.configured ? 'bg-emerald-900/30 text-emerald-300' : 'bg-slate-800 text-slate-500'}`}
                        data-testid="health-provider-item"
                      >
                        {p.name}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ---- Profile tab ---- */}
      {activeTab === 'profile' && (
        <div data-testid="tab-panel-profile">
          {profileError && (
            <p className="mb-4 text-sm text-red-400" data-testid="profile-error">
              {profileError}
            </p>
          )}
          {loadingProfile && !profile && (
            <p className="text-xs text-slate-500" data-testid="profile-loading">Loading…</p>
          )}
          {profile && (
            <div
              className="rounded border border-slate-700 bg-slate-800/30 p-4 text-sm"
              data-testid="profile-card"
            >
              <div className="space-y-3">
                <div>
                  <p className="text-xs text-slate-500">Email</p>
                  <p className="mt-0.5 font-medium text-slate-200" data-testid="profile-email">
                    {profile.email}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-slate-500">User ID</p>
                  <p className="mt-0.5 font-mono text-xs text-slate-400" data-testid="profile-id">
                    {profile.id}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-slate-500">Status</p>
                  <p className="mt-0.5" data-testid="profile-active">
                    {profile.is_active ? (
                      <span className="text-emerald-400">Active</span>
                    ) : (
                      <span className="text-red-400">Inactive</span>
                    )}
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </MainLayout>
  );
};

export default PortfolioDashboardPage;
