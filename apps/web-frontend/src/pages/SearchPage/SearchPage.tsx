/**
 * SearchPage -- Standalone full-screen marketplace search experience.
 *
 * Route: /search
 * Supports URL search params sync: /search?q=llm&category=automation
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface MarketplaceListing {
  id: string;
  name: string;
  description: string;
  category: string;
  tags: string[];
  author: string;
  nodes: Array<{ id: string; type?: string }>;
  edges: unknown[];
  install_count: number;
  featured: boolean;
  is_featured?: boolean;
  published_at: number;
  avg_rating?: number;
  rating_count?: number;
  _score?: number;
}

interface SearchResponse {
  items: MarketplaceListing[];
  total: number;
  page: number;
  per_page: number;
  query: string;
  filters_applied: Record<string, unknown>;
}

interface AutocompleteResponse {
  suggestions: string[];
}

type ServerSortOption = 'relevance' | 'installs' | 'rating' | 'newest';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PER_PAGE = 12;

const KNOWN_CATEGORIES = [
  'notification',
  'data-sync',
  'monitoring',
  'content',
  'devops',
  'ai',
  'automation',
  'data',
  'integration',
];

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

function renderStars(rating: number): string {
  const full = Math.floor(rating);
  const half = rating - full >= 0.5 ? 1 : 0;
  const empty = 5 - full - half;
  return '\u2605'.repeat(full) + (half ? '\u00bd' : '') + '\u2606'.repeat(empty);
}

function formatInstallCount(count: number): string {
  if (count >= 1000) return `${(count / 1000).toFixed(1)}k`;
  return String(count);
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

const SearchPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState(searchParams.get('q') || '');
  const [debouncedQuery, setDebouncedQuery] = useState(query);
  const [category, setCategory] = useState(searchParams.get('category') || '');
  const [minRating, setMinRating] = useState<number>(Number(searchParams.get('min_rating') || 0));
  const [minInstalls, setMinInstalls] = useState<number>(
    Number(searchParams.get('min_installs') || 0),
  );
  const [sortBy, setSortBy] = useState<ServerSortOption>(
    (searchParams.get('sort_by') as ServerSortOption) || 'relevance',
  );
  const [results, setResults] = useState<MarketplaceListing[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [autocompleteSuggestions, setAutocompleteSuggestions] = useState<string[]>([]);
  const [showAutocomplete, setShowAutocomplete] = useState(false);
  const autocompleteRef = useRef<HTMLDivElement>(null);

  // Debounce search query
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQuery(query);
    }, 400);
    return () => clearTimeout(timer);
  }, [query]);

  // Autocomplete
  useEffect(() => {
    if (!query.trim()) {
      setAutocompleteSuggestions([]);
      setShowAutocomplete(false);
      return;
    }
    const timer = setTimeout(() => {
      apiFetch<AutocompleteResponse>(
        `/api/v1/marketplace/autocomplete?q=${encodeURIComponent(query.trim())}&limit=8`,
      )
        .then((data) => {
          setAutocompleteSuggestions(data.suggestions);
          setShowAutocomplete(data.suggestions.length > 0);
        })
        .catch(() => {
          setAutocompleteSuggestions([]);
          setShowAutocomplete(false);
        });
    }, 200);
    return () => clearTimeout(timer);
  }, [query]);

  // Close autocomplete on click outside
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (autocompleteRef.current && !autocompleteRef.current.contains(e.target as Node)) {
        setShowAutocomplete(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  // Sync URL params
  useEffect(() => {
    const params: Record<string, string> = {};
    if (debouncedQuery) params.q = debouncedQuery;
    if (category) params.category = category;
    if (minRating > 0) params.min_rating = String(minRating);
    if (minInstalls > 0) params.min_installs = String(minInstalls);
    if (sortBy !== 'relevance') params.sort_by = sortBy;
    setSearchParams(params, { replace: true });
  }, [debouncedQuery, category, minRating, minInstalls, sortBy, setSearchParams]);

  // Reset page when filters change
  useEffect(() => {
    setPage(1);
  }, [debouncedQuery, category, minRating, minInstalls, sortBy]);

  const fetchResults = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams({
        page: String(page),
        per_page: String(PER_PAGE),
      });
      if (debouncedQuery) params.set('q', debouncedQuery);
      if (category) params.set('category', category);
      if (minRating > 0) params.set('min_rating', String(minRating));
      if (minInstalls > 0) params.set('min_installs', String(minInstalls));
      if (sortBy !== 'relevance') params.set('sort_by', sortBy);

      const data = await apiFetch<SearchResponse>(
        `/api/v1/marketplace/search?${params.toString()}`,
      );

      setResults(data.items);
      setTotal(data.total);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Search failed';
      setError(message);
      setResults([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [debouncedQuery, category, minRating, minInstalls, sortBy, page]);

  useEffect(() => {
    fetchResults();
  }, [fetchResults]);

  const handleAutocompletePick = (suggestion: string) => {
    setQuery(suggestion);
    setShowAutocomplete(false);
  };

  return (
    <MainLayout title="Search Marketplace">
      <div data-testid="search-page" style={{ maxWidth: '1200px', margin: '0 auto', padding: '24px' }}>
        {/* Search bar */}
        <div
          ref={autocompleteRef}
          style={{ position: 'relative', marginBottom: '24px' }}
        >
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={() => {
              if (autocompleteSuggestions.length > 0) setShowAutocomplete(true);
            }}
            placeholder="Search marketplace..."
            aria-label="Search marketplace"
            data-testid="search-input"
            style={{
              width: '100%',
              padding: '14px 20px',
              fontSize: '18px',
              background: '#1e293b',
              border: '2px solid #334155',
              borderRadius: '12px',
              color: '#f1f5f9',
              outline: 'none',
            }}
          />
          {showAutocomplete && autocompleteSuggestions.length > 0 && (
            <div
              data-testid="autocomplete-dropdown"
              style={{
                position: 'absolute',
                top: '100%',
                left: 0,
                right: 0,
                zIndex: 50,
                background: '#1e293b',
                border: '1px solid #334155',
                borderRadius: '0 0 8px 8px',
                maxHeight: '240px',
                overflowY: 'auto',
              }}
            >
              {autocompleteSuggestions.map((suggestion, idx) => (
                <button
                  key={`${suggestion}-${idx}`}
                  data-testid={`autocomplete-item-${idx}`}
                  style={{
                    display: 'block',
                    width: '100%',
                    padding: '10px 20px',
                    textAlign: 'left',
                    background: 'transparent',
                    border: 'none',
                    color: '#cbd5e1',
                    cursor: 'pointer',
                    fontSize: '15px',
                  }}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => handleAutocompletePick(suggestion)}
                >
                  {suggestion}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Results count */}
        <div data-testid="results-count" style={{ marginBottom: '16px', color: '#94a3b8' }}>
          {debouncedQuery
            ? `${total} result${total !== 1 ? 's' : ''} for "${debouncedQuery}"`
            : `${total} workflow${total !== 1 ? 's' : ''} available`}
        </div>

        <div style={{ display: 'flex', gap: '24px' }}>
          {/* Filter sidebar */}
          <aside style={{ width: '220px', flexShrink: 0 }}>
            <div style={{ marginBottom: '20px' }}>
              <h3 style={{ color: '#e2e8f0', marginBottom: '8px', fontSize: '14px', fontWeight: 600 }}>
                Category
              </h3>
              <select
                data-testid="category-filter"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                aria-label="Filter by category"
                style={{
                  width: '100%',
                  padding: '8px',
                  background: '#1e293b',
                  border: '1px solid #334155',
                  borderRadius: '6px',
                  color: '#cbd5e1',
                }}
              >
                <option value="">All categories</option>
                {KNOWN_CATEGORIES.map((cat) => (
                  <option key={cat} value={cat}>
                    {cat}
                  </option>
                ))}
              </select>
            </div>

            <div style={{ marginBottom: '20px' }}>
              <h3 style={{ color: '#e2e8f0', marginBottom: '8px', fontSize: '14px', fontWeight: 600 }}>
                Min Rating
              </h3>
              <select
                data-testid="min-rating-filter"
                value={minRating}
                onChange={(e) => setMinRating(Number(e.target.value))}
                aria-label="Minimum rating"
                style={{
                  width: '100%',
                  padding: '8px',
                  background: '#1e293b',
                  border: '1px solid #334155',
                  borderRadius: '6px',
                  color: '#cbd5e1',
                }}
              >
                <option value={0}>Any</option>
                <option value={3}>3+ stars</option>
                <option value={4}>4+ stars</option>
                <option value={4.5}>4.5+ stars</option>
              </select>
            </div>

            <div style={{ marginBottom: '20px' }}>
              <h3 style={{ color: '#e2e8f0', marginBottom: '8px', fontSize: '14px', fontWeight: 600 }}>
                Min Installs
              </h3>
              <select
                data-testid="min-installs-filter"
                value={minInstalls}
                onChange={(e) => setMinInstalls(Number(e.target.value))}
                aria-label="Minimum installs"
                style={{
                  width: '100%',
                  padding: '8px',
                  background: '#1e293b',
                  border: '1px solid #334155',
                  borderRadius: '6px',
                  color: '#cbd5e1',
                }}
              >
                <option value={0}>Any</option>
                <option value={10}>10+</option>
                <option value={100}>100+</option>
                <option value={1000}>1000+</option>
              </select>
            </div>

            <div style={{ marginBottom: '20px' }}>
              <h3 style={{ color: '#e2e8f0', marginBottom: '8px', fontSize: '14px', fontWeight: 600 }}>
                Sort By
              </h3>
              <select
                data-testid="sort-by-filter"
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as ServerSortOption)}
                aria-label="Sort order"
                style={{
                  width: '100%',
                  padding: '8px',
                  background: '#1e293b',
                  border: '1px solid #334155',
                  borderRadius: '6px',
                  color: '#cbd5e1',
                }}
              >
                <option value="relevance">Relevance</option>
                <option value="installs">Most Installed</option>
                <option value="rating">Highest Rated</option>
                <option value="newest">Newest</option>
              </select>
            </div>
          </aside>

          {/* Results grid */}
          <div style={{ flex: 1 }}>
            {error && (
              <div data-testid="search-error" style={{ color: '#f87171', marginBottom: '16px' }}>
                {error}
              </div>
            )}

            {loading ? (
              <div style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>
                Searching...
              </div>
            ) : results.length === 0 ? (
              <div
                data-testid="empty-state"
                style={{ textAlign: 'center', padding: '60px', color: '#64748b' }}
              >
                <p style={{ fontSize: '18px', marginBottom: '8px' }}>No results found</p>
                <p>Try adjusting your search or filters.</p>
              </div>
            ) : (
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                  gap: '16px',
                }}
              >
                {results.map((listing) => (
                  <article
                    key={listing.id}
                    style={{
                      background: '#1e293b',
                      border: '1px solid #334155',
                      borderRadius: '12px',
                      padding: '16px',
                    }}
                  >
                    <h3
                      style={{
                        color: '#f1f5f9',
                        fontSize: '16px',
                        marginBottom: '8px',
                        fontWeight: 600,
                      }}
                    >
                      {listing.name}
                    </h3>
                    <p style={{ color: '#94a3b8', fontSize: '13px', marginBottom: '12px' }}>
                      {listing.description}
                    </p>
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        fontSize: '12px',
                        color: '#64748b',
                      }}
                    >
                      <span>{listing.category}</span>
                      <span title={`Rating: ${listing.avg_rating?.toFixed(1) ?? 'N/A'}`}>
                        {renderStars(listing.avg_rating ?? 0)}
                      </span>
                      <span>{formatInstallCount(listing.install_count)} installs</span>
                    </div>
                    {listing.tags.length > 0 && (
                      <div style={{ marginTop: '8px', display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                        {listing.tags.slice(0, 3).map((tag) => (
                          <span
                            key={tag}
                            style={{
                              padding: '2px 8px',
                              background: '#334155',
                              borderRadius: '4px',
                              fontSize: '11px',
                              color: '#94a3b8',
                            }}
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    )}
                  </article>
                ))}
              </div>
            )}

            {/* Pagination */}
            {total > PER_PAGE && results.length > 0 && (
              <div style={{ display: 'flex', justifyContent: 'center', gap: '8px', marginTop: '24px' }}>
                <button
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  style={{
                    padding: '8px 16px',
                    background: '#334155',
                    border: 'none',
                    borderRadius: '6px',
                    color: '#cbd5e1',
                    cursor: page <= 1 ? 'not-allowed' : 'pointer',
                    opacity: page <= 1 ? 0.5 : 1,
                  }}
                >
                  Previous
                </button>
                <span style={{ padding: '8px 12px', color: '#94a3b8' }}>
                  Page {page} of {Math.ceil(total / PER_PAGE)}
                </span>
                <button
                  disabled={page >= Math.ceil(total / PER_PAGE)}
                  onClick={() => setPage((p) => p + 1)}
                  style={{
                    padding: '8px 16px',
                    background: '#334155',
                    border: 'none',
                    borderRadius: '6px',
                    color: '#cbd5e1',
                    cursor: page >= Math.ceil(total / PER_PAGE) ? 'not-allowed' : 'pointer',
                    opacity: page >= Math.ceil(total / PER_PAGE) ? 0.5 : 1,
                  }}
                >
                  Next
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </MainLayout>
  );
};

export default SearchPage;
