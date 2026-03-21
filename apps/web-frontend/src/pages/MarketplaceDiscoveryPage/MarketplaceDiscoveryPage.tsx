/**
 * MarketplaceDiscoveryPage — Featured listings, autocomplete, and issue reporting (N-117).
 *
 * Covers:
 *   GET  /api/v1/marketplace/featured                → admin-curated featured listings
 *   GET  /api/v1/marketplace/autocomplete?q=&limit=  → autocomplete suggestions
 *   POST /api/v1/marketplace/{listing_id}/report     → report an issue with a listing
 *
 * Route: /marketplace-discovery (ProtectedRoute)
 */
import React, { useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface FeaturedListing {
  id: string;
  name: string;
  description?: string;
  blurb?: string;
  featured_at?: string;
  featured_by?: string;
  is_featured: boolean;
}

interface AutocompleteSuggestion {
  id: string;
  name: string;
  type?: string;
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

function jsonHeaders(): Record<string, string> {
  return { ...authHeaders(), 'Content-Type': 'application/json' };
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const MarketplaceDiscoveryPage: React.FC = () => {
  const [tab, setTab] = useState<'featured' | 'autocomplete' | 'report'>('featured');

  // Featured listings
  const [featured, setFeatured] = useState<FeaturedListing[]>([]);
  const [featuredLimit, setFeaturedLimit] = useState('0');
  const [featuredLoading, setFeaturedLoading] = useState(false);
  const [featuredError, setFeaturedError] = useState<string | null>(null);

  // Autocomplete
  const [acQuery, setAcQuery] = useState('');
  const [acLimit, setAcLimit] = useState('8');
  const [suggestions, setSuggestions] = useState<AutocompleteSuggestion[]>([]);
  const [acLoading, setAcLoading] = useState(false);
  const [acError, setAcError] = useState<string | null>(null);

  // Report issue
  const [reportListingId, setReportListingId] = useState('');
  const [reportType, setReportType] = useState('spam');
  const [reportDescription, setReportDescription] = useState('');
  const [reportLoading, setReportLoading] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);
  const [reportResult, setReportResult] = useState<Record<string, unknown> | null>(null);

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  async function loadFeatured() {
    setFeaturedLoading(true);
    setFeaturedError(null);
    try {
      const params = `?limit=${encodeURIComponent(featuredLimit || '0')}`;
      const resp = await fetch(`${getBaseUrl()}/api/v1/marketplace/featured${params}`, {
        headers: authHeaders(),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setFeaturedError(data.detail ?? `Error ${resp.status}`);
        return;
      }
      const raw = data.items ?? data;
      setFeatured(Array.isArray(raw) ? raw : []);
    } catch {
      setFeaturedError('Network error');
    } finally {
      setFeaturedLoading(false);
    }
  }

  async function runAutocomplete() {
    setAcLoading(true);
    setAcError(null);
    setSuggestions([]);
    try {
      const params = new URLSearchParams({ q: acQuery, limit: acLimit || '8' });
      const resp = await fetch(`${getBaseUrl()}/api/v1/marketplace/autocomplete?${params}`, {
        headers: authHeaders(),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setAcError(data.detail ?? `Error ${resp.status}`);
        return;
      }
      const raw = data.suggestions ?? data;
      setSuggestions(Array.isArray(raw) ? raw : []);
    } catch {
      setAcError('Network error');
    } finally {
      setAcLoading(false);
    }
  }

  async function handleReport(e: React.FormEvent) {
    e.preventDefault();
    if (!reportListingId.trim()) return;
    setReportLoading(true);
    setReportError(null);
    setReportResult(null);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/api/v1/marketplace/${encodeURIComponent(reportListingId.trim())}/report`,
        {
          method: 'POST',
          headers: jsonHeaders(),
          body: JSON.stringify({ type: reportType, description: reportDescription }),
        },
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setReportError(data.detail ?? `Error ${resp.status}`);
        return;
      }
      setReportResult(data as Record<string, unknown>);
    } catch {
      setReportError('Network error');
    } finally {
      setReportLoading(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <MainLayout title="Marketplace Discovery">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
          Marketplace Discovery
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Featured listings, search autocomplete, and issue reporting.
        </p>
      </div>

      {/* Tabs */}
      <div className="mb-6 flex gap-2" data-testid="tabs">
        {(['featured', 'autocomplete', 'report'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded px-4 py-1.5 text-sm font-medium ${
              tab === t
                ? 'bg-indigo-600 text-white'
                : 'bg-slate-800 text-slate-400 hover:text-slate-200'
            }`}
            data-testid={`tab-${t}`}
          >
            {t === 'featured' ? 'Featured' : t === 'autocomplete' ? 'Autocomplete' : 'Report Issue'}
          </button>
        ))}
      </div>

      {/* ---- Featured tab ---- */}
      {tab === 'featured' && (
        <section data-testid="featured-section">
          <div className="mb-4 flex items-center gap-3">
            <label className="text-sm text-slate-400">Limit:</label>
            <input
              type="number"
              min="0"
              className="w-24 rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200"
              value={featuredLimit}
              onChange={(e) => setFeaturedLimit(e.target.value)}
              data-testid="featured-limit-input"
            />
            <button
              onClick={loadFeatured}
              className="rounded bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-500"
              data-testid="load-featured-btn"
            >
              Load Featured
            </button>
          </div>

          {featuredError && (
            <p className="mb-3 text-sm text-red-400" data-testid="featured-error">
              {featuredError}
            </p>
          )}
          {featuredLoading && (
            <p className="text-sm text-slate-500" data-testid="featured-loading">Loading…</p>
          )}
          {!featuredLoading && featured.length === 0 && !featuredError && (
            <p className="text-sm text-slate-500" data-testid="no-featured">
              No featured listings. Click Load Featured.
            </p>
          )}
          {featured.length > 0 && (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2" data-testid="featured-grid">
              {featured.map((item) => (
                <div
                  key={item.id}
                  className="rounded border border-indigo-700/40 bg-indigo-900/10 p-4"
                  data-testid="featured-card"
                >
                  <div className="flex items-start justify-between">
                    <h3 className="text-sm font-semibold text-slate-200" data-testid="featured-name">
                      {item.name}
                    </h3>
                    <span className="rounded bg-indigo-600/20 px-2 py-0.5 text-xs text-indigo-400">
                      Featured
                    </span>
                  </div>
                  {item.blurb && (
                    <p className="mt-1 text-xs text-slate-400" data-testid="featured-blurb">
                      {item.blurb}
                    </p>
                  )}
                  {item.featured_at && (
                    <p className="mt-2 text-xs text-slate-500">
                      Featured at: {item.featured_at}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* ---- Autocomplete tab ---- */}
      {tab === 'autocomplete' && (
        <section data-testid="autocomplete-section">
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <input
              className="flex-1 rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500"
              placeholder="Search prefix…"
              value={acQuery}
              onChange={(e) => setAcQuery(e.target.value)}
              data-testid="ac-query-input"
            />
            <input
              type="number"
              min="1"
              max="50"
              className="w-20 rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200"
              value={acLimit}
              onChange={(e) => setAcLimit(e.target.value)}
              data-testid="ac-limit-input"
            />
            <button
              onClick={runAutocomplete}
              className="rounded bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-500"
              data-testid="ac-search-btn"
            >
              Search
            </button>
          </div>

          {acError && (
            <p className="mb-3 text-sm text-red-400" data-testid="ac-error">{acError}</p>
          )}
          {acLoading && (
            <p className="text-sm text-slate-500" data-testid="ac-loading">Loading…</p>
          )}
          {!acLoading && suggestions.length === 0 && !acError && (
            <p className="text-sm text-slate-500" data-testid="no-suggestions">
              No suggestions yet. Type and click Search.
            </p>
          )}
          {suggestions.length > 0 && (
            <ul className="space-y-1" data-testid="suggestions-list">
              {suggestions.map((s, i) => (
                <li
                  key={`${s.id}-${i}`}
                  className="flex items-center gap-3 rounded border border-slate-700/40 bg-slate-800/30 px-3 py-2 text-sm"
                  data-testid="suggestion-item"
                >
                  <span className="font-medium text-slate-200" data-testid="suggestion-name">
                    {s.name}
                  </span>
                  {s.type && (
                    <span className="text-xs text-slate-500">{s.type}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {/* ---- Report Issue tab ---- */}
      {tab === 'report' && (
        <section data-testid="report-section">
          <form onSubmit={handleReport} className="max-w-md space-y-4" data-testid="report-form">
            <div>
              <label className="mb-1 block text-xs text-slate-400">Listing ID</label>
              <input
                className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500"
                placeholder="listing-id"
                value={reportListingId}
                onChange={(e) => setReportListingId(e.target.value)}
                required
                data-testid="report-listing-id-input"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-400">Issue Type</label>
              <select
                className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200"
                value={reportType}
                onChange={(e) => setReportType(e.target.value)}
                data-testid="report-type-select"
              >
                <option value="spam">spam</option>
                <option value="malware">malware</option>
                <option value="copyright">copyright</option>
                <option value="other">other</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-400">Description</label>
              <textarea
                className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200"
                rows={4}
                placeholder="Describe the issue…"
                value={reportDescription}
                onChange={(e) => setReportDescription(e.target.value)}
                data-testid="report-description-input"
              />
            </div>
            <button
              type="submit"
              disabled={reportLoading || !reportListingId.trim()}
              className="rounded bg-red-700 px-4 py-1.5 text-sm text-white hover:bg-red-600 disabled:opacity-50"
              data-testid="report-submit-btn"
            >
              {reportLoading ? 'Submitting…' : 'Submit Report'}
            </button>
          </form>

          {reportError && (
            <p className="mt-3 text-sm text-red-400" data-testid="report-error">{reportError}</p>
          )}
          {reportResult && (
            <div
              className="mt-4 rounded border border-emerald-700/40 bg-emerald-900/10 p-3"
              data-testid="report-result"
            >
              <p className="text-sm text-emerald-300">Report submitted successfully.</p>
              <p className="mt-1 font-mono text-xs text-slate-400">
                Issue ID: <span data-testid="report-issue-id">{String(reportResult.issue_id ?? reportResult.id ?? '—')}</span>
              </p>
            </div>
          )}
        </section>
      )}
    </MainLayout>
  );
};

export default MarketplaceDiscoveryPage;
