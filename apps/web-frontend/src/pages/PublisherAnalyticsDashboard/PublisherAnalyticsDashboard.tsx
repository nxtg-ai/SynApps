/**
 * PublisherAnalyticsDashboard -- Shows a publisher's template performance.
 *
 * Displays: KPI cards, top templates, growth trend bar chart, per-listing table.
 * Route: /publisher/analytics (ProtectedRoute)
 */
import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AnalyticsSummary {
  total_installs: number;
  total_listings: number;
  avg_rating: number;
  total_credits_earned: number;
  credit_balance: number;
  total_reviews: number;
  featured_count: number;
}

interface PerListingEntry {
  listing_id: string;
  name: string;
  install_count: number;
  avg_rating: number;
  rating_count: number;
  review_count: number;
  credits_earned: number;
  trending_score: number;
  is_featured: boolean;
  published_at: number;
}

interface TrendEntry {
  date: string;
  installs: number;
}

interface AnalyticsResponse {
  summary: AnalyticsSummary;
  per_listing: PerListingEntry[];
  growth_trend: TrendEntry[];
  top_templates: PerListingEntry[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getBaseUrl(): string {
  return (
    (import.meta as unknown as { env?: { VITE_API_URL?: string; REACT_APP_API_URL?: string } }).env
      ?.VITE_API_URL ||
    (import.meta as unknown as { env?: { REACT_APP_API_URL?: string } }).env?.REACT_APP_API_URL ||
    'http://localhost:8000'
  );
}

function getAuthToken(): string | null {
  return typeof window !== 'undefined' ? window.localStorage.getItem('access_token') : null;
}

async function apiFetch<T>(path: string): Promise<T> {
  const token = getAuthToken();
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
  const res = await fetch(`${getBaseUrl()}${path}`, { headers });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface KpiCardProps {
  label: string;
  value: string | number;
  color: string;
  testId: string;
}

const KpiCard: React.FC<KpiCardProps> = ({ label, value, color, testId }) => (
  <div className={`rounded-lg p-4 ${color} shadow-md`} data-testid={testId}>
    <div className="text-sm font-medium text-slate-300">{label}</div>
    <div className="mt-1 text-2xl font-bold text-white">{value}</div>
  </div>
);

interface GrowthChartProps {
  data: TrendEntry[];
}

const GrowthChart: React.FC<GrowthChartProps> = ({ data }) => {
  if (data.length === 0) return null;

  const maxInstalls = Math.max(...data.map((d) => d.installs), 1);
  const chartHeight = 120;
  const barWidth = Math.max(4, Math.floor(600 / data.length) - 2);
  const chartWidth = data.length * (barWidth + 2);

  return (
    <div data-testid="growth-chart" className="overflow-x-auto">
      <svg
        width={chartWidth}
        height={chartHeight + 20}
        viewBox={`0 0 ${chartWidth} ${chartHeight + 20}`}
        aria-label="Growth trend chart"
      >
        {data.map((entry, i) => {
          const barHeight = maxInstalls > 0 ? (entry.installs / maxInstalls) * chartHeight : 0;
          const x = i * (barWidth + 2);
          const y = chartHeight - barHeight;
          return (
            <g key={entry.date}>
              <rect x={x} y={y} width={barWidth} height={barHeight} fill="#6366f1" rx={1}>
                <title>{`${entry.date}: ${entry.installs} installs`}</title>
              </rect>
            </g>
          );
        })}
      </svg>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Days selector options
// ---------------------------------------------------------------------------

const DAYS_OPTIONS = [
  { label: '7d', value: 7 },
  { label: '30d', value: 30 },
  { label: '90d', value: 90 },
] as const;

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

const PublisherAnalyticsDashboard: React.FC = () => {
  const navigate = useNavigate();
  const [data, setData] = useState<AnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [days, setDays] = useState(30);

  const fetchData = useCallback(async (daysParam: number) => {
    setLoading(true);
    setError(null);
    try {
      const result = await apiFetch<AnalyticsResponse>(
        `/api/v1/marketplace/publisher/analytics?days=${daysParam}`,
      );
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load analytics');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData(days);
  }, [days, fetchData]);

  const handleDaysChange = (newDays: number) => {
    setDays(newDays);
  };

  if (loading) {
    return (
      <MainLayout title="Publisher Analytics">
        <div
          className="flex min-h-[40vh] items-center justify-center text-slate-300"
          aria-label="Loading analytics"
          data-testid="analytics-dashboard"
        >
          Loading analytics...
        </div>
      </MainLayout>
    );
  }

  if (error) {
    return (
      <MainLayout title="Publisher Analytics">
        <div
          className="flex min-h-[40vh] items-center justify-center text-red-400"
          role="alert"
          data-testid="analytics-dashboard"
        >
          {error}
        </div>
      </MainLayout>
    );
  }

  if (!data) return null;

  const { summary, per_listing, growth_trend, top_templates } = data;
  const isEmpty = summary.total_listings === 0;

  return (
    <MainLayout title="Publisher Analytics">
      <div className="space-y-6" data-testid="analytics-dashboard">
        {/* Days selector */}
        <div className="flex items-center gap-2" data-testid="days-selector">
          {DAYS_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => handleDaysChange(opt.value)}
              className={`rounded px-3 py-1 text-sm font-medium ${
                days === opt.value
                  ? 'bg-indigo-600 text-white'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {isEmpty ? (
          <div className="text-center text-slate-400 py-12" data-testid="empty-state">
            No templates published yet. Publish a template to see analytics.
          </div>
        ) : (
          <>
            {/* KPI Cards */}
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
              <KpiCard
                label="Total Installs"
                value={summary.total_installs}
                color="bg-indigo-900/60"
                testId="kpi-total-installs"
              />
              <KpiCard
                label="Total Templates"
                value={summary.total_listings}
                color="bg-emerald-900/60"
                testId="kpi-total-templates"
              />
              <KpiCard
                label="Avg Rating"
                value={`${summary.avg_rating.toFixed(1)} \u2605`}
                color="bg-amber-900/60"
                testId="kpi-avg-rating"
              />
              <KpiCard
                label="Credits Earned"
                value={summary.total_credits_earned}
                color="bg-purple-900/60"
                testId="kpi-credits-earned"
              />
              <KpiCard
                label="Credit Balance"
                value={summary.credit_balance}
                color="bg-cyan-900/60"
                testId="kpi-credit-balance"
              />
              <KpiCard
                label="Total Reviews"
                value={summary.total_reviews}
                color="bg-rose-900/60"
                testId="kpi-total-reviews"
              />
            </div>

            {/* Top Templates */}
            <section data-testid="top-templates-section">
              <h2 className="mb-3 text-lg font-semibold text-white">Top Templates</h2>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
                {top_templates.map((t) => (
                  <div key={t.listing_id} className="rounded-lg bg-slate-800 p-4 shadow">
                    <div className="font-medium text-white">{t.name}</div>
                    <div className="mt-1 text-sm text-slate-400">
                      {t.install_count} installs &middot; {t.avg_rating.toFixed(1)} &#9733;
                    </div>
                    <div className="mt-1 text-xs text-slate-500">
                      Trending: {t.trending_score.toFixed(0)}
                    </div>
                    {t.is_featured && (
                      <span className="mt-1 inline-block rounded bg-amber-600/30 px-2 py-0.5 text-xs text-amber-300">
                        Featured
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </section>

            {/* Growth Trend */}
            <section>
              <h2 className="mb-3 text-lg font-semibold text-white">Install Trend ({days}d)</h2>
              <div className="rounded-lg bg-slate-800 p-4">
                <GrowthChart data={growth_trend} />
              </div>
            </section>

            {/* Per-Listing Table */}
            <section>
              <h2 className="mb-3 text-lg font-semibold text-white">All Templates</h2>
              <div className="overflow-x-auto rounded-lg bg-slate-800">
                <table className="w-full text-left text-sm" data-testid="per-listing-table">
                  <thead className="border-b border-slate-700 text-slate-400">
                    <tr>
                      <th className="px-4 py-3">Name</th>
                      <th className="px-4 py-3">Installs</th>
                      <th className="px-4 py-3">Avg Rating</th>
                      <th className="px-4 py-3">Reviews</th>
                      <th className="px-4 py-3">Credits</th>
                      <th className="px-4 py-3">Trending</th>
                      <th className="px-4 py-3">Featured</th>
                      <th className="px-4 py-3">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="text-slate-300">
                    {per_listing.map((entry) => (
                      <tr
                        key={entry.listing_id}
                        className="border-b border-slate-700/50 hover:bg-slate-700/30 cursor-pointer"
                        onClick={() => navigate(`/publisher/analytics/${entry.listing_id}`)}
                      >
                        <td className="px-4 py-3 font-medium text-white">{entry.name}</td>
                        <td className="px-4 py-3">{entry.install_count}</td>
                        <td className="px-4 py-3">{entry.avg_rating.toFixed(1)} &#9733;</td>
                        <td className="px-4 py-3">{entry.review_count}</td>
                        <td className="px-4 py-3">{entry.credits_earned}</td>
                        <td className="px-4 py-3">{entry.trending_score.toFixed(0)}</td>
                        <td className="px-4 py-3">
                          {entry.is_featured ? (
                            <span className="text-amber-400">&#9733;</span>
                          ) : (
                            <span className="text-slate-600">-</span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <button
                            className="text-indigo-400 hover:text-indigo-300 text-xs"
                            onClick={(e) => {
                              e.stopPropagation();
                              navigate(`/publisher/analytics/${entry.listing_id}`);
                            }}
                          >
                            View Details
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
      </div>
    </MainLayout>
  );
};

export default PublisherAnalyticsDashboard;
