/**
 * PublisherDashboardPage — Marketplace publisher analytics dashboard.
 *
 * Shows the authenticated user's own published listings with:
 *   - Install count
 *   - Avg rating and rating count
 *   - Trending score
 *   - Last 3 reviews (truncated)
 *
 * Route: /publisher/dashboard (ProtectedRoute)
 */
import React, { useEffect, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ReviewItem {
  review_id: string;
  listing_id: string;
  user_id: string;
  text: string;
  stars: number | null;
  created_at: number;
}

interface PublisherListing {
  id: string;
  name: string;
  description: string;
  category: string;
  tags: string[];
  install_count: number;
  avg_rating: number;
  rating_count: number;
  trending_score: number;
  recent_reviews: ReviewItem[];
  published_at: number;
}

interface DashboardResponse {
  listings: PublisherListing[];
  total: number;
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

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getAuthToken();
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options?.headers ?? {}),
  };
  const res = await fetch(`${getBaseUrl()}${path}`, { ...options, headers });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

function truncate(text: string, maxLen: number): string {
  return text.length > maxLen ? `${text.slice(0, maxLen)}…` : text;
}

function renderStars(avg: number): string {
  const full = Math.floor(avg);
  const half = avg - full >= 0.5 ? 1 : 0;
  const empty = 5 - full - half;
  return '★'.repeat(full) + (half ? '½' : '') + '☆'.repeat(empty);
}

function trendingBadgeColor(score: number): string {
  if (score >= 50) return 'bg-orange-500/20 text-orange-300 border-orange-500/40';
  if (score >= 10) return 'bg-yellow-500/20 text-yellow-300 border-yellow-500/40';
  return 'bg-slate-700/40 text-slate-400 border-slate-600/40';
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface ReviewPreviewProps {
  reviews: ReviewItem[];
}

const ReviewPreview: React.FC<ReviewPreviewProps> = ({ reviews }) => {
  if (reviews.length === 0) {
    return <p className="text-xs text-slate-500 italic">No reviews yet.</p>;
  }

  const shown = reviews.slice(0, 3);
  return (
    <ul className="space-y-1">
      {shown.map((r) => (
        <li key={r.review_id} className="text-xs text-slate-400 border-l-2 border-slate-700 pl-2">
          {r.stars != null && (
            <span className="text-yellow-400 mr-1">{renderStars(r.stars)}</span>
          )}
          <span>{truncate(r.text, 100)}</span>
        </li>
      ))}
    </ul>
  );
};

interface ListingCardProps {
  listing: PublisherListing;
}

const ListingCard: React.FC<ListingCardProps> = ({ listing }) => {
  const badgeColor = trendingBadgeColor(listing.trending_score);

  return (
    <article className="bg-slate-800 border border-slate-700 rounded-xl p-5 flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <h2 className="text-base font-semibold text-slate-100 truncate" title={listing.name}>
            {listing.name}
          </h2>
          <p className="text-sm text-slate-400 mt-0.5 line-clamp-2">{listing.description}</p>
        </div>
        <span className="shrink-0 text-xs font-medium px-2 py-0.5 rounded border bg-slate-700/60 text-slate-300 border-slate-600/40 capitalize">
          {listing.category}
        </span>
      </div>

      {/* Stats row */}
      <div className="flex flex-wrap items-center gap-3 text-sm">
        {/* Install count */}
        <span className="flex items-center gap-1 text-slate-300">
          <span aria-hidden="true">📦</span>
          <span>{listing.install_count} installs</span>
        </span>

        {/* Star rating */}
        <span className="flex items-center gap-1 text-slate-300">
          <span className="text-yellow-400" aria-hidden="true">
            {renderStars(listing.avg_rating)}
          </span>
          <span>
            {listing.avg_rating.toFixed(1)} / 5
          </span>
          <span className="text-slate-500">
            ({listing.rating_count} {listing.rating_count === 1 ? 'rating' : 'ratings'})
          </span>
        </span>

        {/* Trending score */}
        <span
          className={`text-xs font-medium px-2 py-0.5 rounded border ${badgeColor}`}
          title="Trending score = recent installs × 10 + all-time installs"
        >
          Trending: {listing.trending_score.toFixed(0)}
        </span>
      </div>

      {/* Recent reviews */}
      <div>
        <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">
          Recent Reviews
        </p>
        <ReviewPreview reviews={listing.recent_reviews} />
      </div>
    </article>
  );
};

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

const PublisherDashboardPage: React.FC = () => {
  const [listings, setListings] = useState<PublisherListing[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    apiFetch<DashboardResponse>('/api/v1/marketplace/publisher/dashboard')
      .then((data) => {
        if (!cancelled) {
          setListings(data.listings);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load dashboard');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <MainLayout title="Publisher Dashboard">
      <div className="max-w-4xl mx-auto px-4 py-6 space-y-6">
        {/* Page header */}
        <div>
          <h1 className="text-xl font-bold text-slate-100">Your Published Templates</h1>
          <p className="text-sm text-slate-400 mt-1">
            Analytics for all workflows you have published to the marketplace.
          </p>
        </div>

        {/* Loading state */}
        {loading && (
          <div
            className="flex items-center justify-center h-48 text-slate-400"
            aria-label="Loading publisher dashboard"
          >
            <svg
              className="animate-spin h-6 w-6 mr-2 text-slate-400"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8v8H4z"
              />
            </svg>
            Loading dashboard...
          </div>
        )}

        {/* Error state */}
        {!loading && error != null && (
          <div
            className="bg-red-900/30 border border-red-700/40 rounded-lg p-4 text-red-300 text-sm"
            role="alert"
          >
            <strong>Error:</strong> {error}
          </div>
        )}

        {/* Empty state */}
        {!loading && error == null && listings.length === 0 && (
          <div className="flex flex-col items-center justify-center h-64 text-center gap-3">
            <span className="text-4xl" aria-hidden="true">📭</span>
            <p className="text-slate-300 font-medium">
              You haven&apos;t published any templates yet.
            </p>
            <p className="text-slate-500 text-sm">
              Go to the Gallery to publish your workflows.
            </p>
          </div>
        )}

        {/* Listings grid */}
        {!loading && error == null && listings.length > 0 && (
          <div className="grid gap-4 sm:grid-cols-1 md:grid-cols-2">
            {listings.map((listing) => (
              <ListingCard key={listing.id} listing={listing} />
            ))}
          </div>
        )}
      </div>
    </MainLayout>
  );
};

export default PublisherDashboardPage;
