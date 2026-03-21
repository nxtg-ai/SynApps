/**
 * ListingAnalyticsDetailPage — Per-listing publisher analytics (N-123).
 *
 * Covers:
 *   GET /api/v1/marketplace/publisher/analytics/{listing_id}
 *
 * Returns listing metadata, rating stats, credits earned, featured status,
 * recent reviews with replies, and a 30-day install trend.
 *
 * Route: /listing-analytics (ProtectedRoute)
 */
import React, { useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ListingStats {
  avg_rating: number;
  rating_count: number;
  review_count: number;
  credits_earned: number;
  trending_score: number;
  is_featured: boolean;
}

interface Review {
  review_id: string;
  reviewer_id?: string;
  rating?: number;
  comment?: string;
  created_at?: number;
  reply?: { body?: string } | null;
}

interface TrendEntry {
  date: string;
  installs: number;
}

interface ListingDetail {
  listing: Record<string, unknown>;
  stats: ListingStats;
  recent_reviews: Review[];
  install_trend: TrendEntry[];
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

function stars(n: number): string {
  const full = Math.round(n);
  return '★'.repeat(full) + '☆'.repeat(Math.max(0, 5 - full));
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const ListingAnalyticsDetailPage: React.FC = () => {
  const [listingId, setListingId] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<ListingDetail | null>(null);

  async function handleFetch(e: React.FormEvent) {
    e.preventDefault();
    if (!listingId.trim()) return;
    setLoading(true);
    setError(null);
    setDetail(null);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/api/v1/marketplace/publisher/analytics/${encodeURIComponent(listingId.trim())}`,
        { headers: authHeaders() },
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setError(data.detail ?? `Error ${resp.status}`);
        return;
      }
      setDetail(data as ListingDetail);
    } catch {
      setError('Network error');
    } finally {
      setLoading(false);
    }
  }

  const maxInstalls = detail
    ? Math.max(...detail.install_trend.map((t) => t.installs), 1)
    : 1;

  return (
    <MainLayout title="Listing Analytics">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
          Listing Analytics Detail
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Per-listing breakdown: ratings, credits, reviews, and 30-day install trend.
        </p>
      </div>

      {/* Lookup form */}
      <form onSubmit={handleFetch} className="mb-6 flex gap-2" data-testid="lookup-form">
        <input
          className="flex-1 rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500"
          placeholder="Listing ID"
          value={listingId}
          onChange={(e) => setListingId(e.target.value)}
          data-testid="listing-id-input"
        />
        <button
          type="submit"
          disabled={loading || !listingId.trim()}
          className="rounded bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-500 disabled:opacity-50"
          data-testid="fetch-btn"
        >
          {loading ? '…' : 'Fetch'}
        </button>
      </form>

      {error && (
        <p className="mb-4 text-sm text-red-400" data-testid="fetch-error">{error}</p>
      )}

      {detail && (
        <div className="space-y-6" data-testid="detail-panel">
          {/* Stats cards */}
          <section data-testid="stats-section">
            <h2 className="mb-3 text-sm font-semibold text-slate-300">Stats</h2>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
              <div className="rounded border border-slate-700 bg-slate-800/30 p-3 text-center" data-testid="stat-rating">
                <p className="text-xs text-slate-500">Avg Rating</p>
                <p className="mt-1 text-lg font-bold text-amber-300">
                  {detail.stats.avg_rating.toFixed(1)}
                </p>
                <p className="text-xs text-amber-400">{stars(detail.stats.avg_rating)}</p>
              </div>
              <div className="rounded border border-slate-700 bg-slate-800/30 p-3 text-center" data-testid="stat-rating-count">
                <p className="text-xs text-slate-500">Ratings</p>
                <p className="mt-1 text-lg font-bold text-slate-100">{detail.stats.rating_count}</p>
              </div>
              <div className="rounded border border-slate-700 bg-slate-800/30 p-3 text-center" data-testid="stat-review-count">
                <p className="text-xs text-slate-500">Reviews</p>
                <p className="mt-1 text-lg font-bold text-slate-100">{detail.stats.review_count}</p>
              </div>
              <div className="rounded border border-slate-700 bg-slate-800/30 p-3 text-center" data-testid="stat-credits">
                <p className="text-xs text-slate-500">Credits Earned</p>
                <p className="mt-1 text-lg font-bold text-emerald-300">{detail.stats.credits_earned}</p>
              </div>
              <div className="rounded border border-slate-700 bg-slate-800/30 p-3 text-center" data-testid="stat-trending">
                <p className="text-xs text-slate-500">Trending Score</p>
                <p className="mt-1 text-lg font-bold text-blue-300">{detail.stats.trending_score.toFixed(1)}</p>
              </div>
              <div className="rounded border border-slate-700 bg-slate-800/30 p-3 text-center" data-testid="stat-featured">
                <p className="text-xs text-slate-500">Featured</p>
                <p className={`mt-1 text-sm font-bold ${detail.stats.is_featured ? 'text-amber-300' : 'text-slate-500'}`}>
                  {detail.stats.is_featured ? 'Yes' : 'No'}
                </p>
              </div>
            </div>
          </section>

          {/* 30-day install trend */}
          <section data-testid="trend-section">
            <h2 className="mb-3 text-sm font-semibold text-slate-300">
              30-Day Install Trend
            </h2>
            {detail.install_trend.length === 0 ? (
              <p className="text-xs text-slate-500" data-testid="no-trend">No install data.</p>
            ) : (
              <div className="overflow-x-auto" data-testid="trend-bars">
                <div className="flex items-end gap-px" style={{ height: 60 }}>
                  {detail.install_trend.map((t) => (
                    <div
                      key={t.date}
                      title={`${t.date}: ${t.installs}`}
                      className="flex-1 bg-indigo-600 hover:bg-indigo-400 transition-colors rounded-t"
                      style={{ height: `${Math.max(2, (t.installs / maxInstalls) * 100)}%` }}
                      data-testid="trend-bar"
                    />
                  ))}
                </div>
                <div className="mt-1 flex justify-between text-xs text-slate-600">
                  <span>{detail.install_trend[0]?.date}</span>
                  <span>{detail.install_trend[detail.install_trend.length - 1]?.date}</span>
                </div>
              </div>
            )}
          </section>

          {/* Recent reviews */}
          <section data-testid="reviews-section">
            <h2 className="mb-3 text-sm font-semibold text-slate-300">
              Recent Reviews ({detail.recent_reviews.length})
            </h2>
            {detail.recent_reviews.length === 0 ? (
              <p className="text-xs text-slate-500" data-testid="no-reviews">No reviews yet.</p>
            ) : (
              <div className="space-y-3" data-testid="reviews-list">
                {detail.recent_reviews.map((r) => (
                  <div
                    key={r.review_id}
                    className="rounded border border-slate-700 bg-slate-800/20 p-3"
                    data-testid="review-item"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-xs text-slate-500">{r.reviewer_id ?? 'anonymous'}</span>
                      {r.rating != null && (
                        <span className="text-xs text-amber-400" data-testid="review-rating">
                          {stars(r.rating)}
                        </span>
                      )}
                    </div>
                    {r.comment && (
                      <p className="mt-1 text-xs text-slate-300" data-testid="review-comment">{r.comment}</p>
                    )}
                    {r.reply && r.reply.body && (
                      <div className="mt-2 rounded bg-slate-900/50 px-3 py-2" data-testid="review-reply">
                        <p className="text-xs text-slate-500">Publisher reply:</p>
                        <p className="text-xs text-slate-300">{r.reply.body}</p>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      )}
    </MainLayout>
  );
};

export default ListingAnalyticsDetailPage;
