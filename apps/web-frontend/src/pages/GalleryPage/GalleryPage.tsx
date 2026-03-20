/**
 * GalleryPage — Workflow Gallery
 *
 * Displays marketplace listings with search, category filtering, and one-click
 * install. Pulls data from GET /api/v1/marketplace/search and
 * POST /api/v1/marketplace/install/{listing_id}.
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import MainLayout from '../../components/Layout/MainLayout';
import './GalleryPage.css';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface MarketplaceNode {
  id: string;
  type?: string;
  data?: Record<string, unknown>;
}

interface MarketplaceListing {
  id: string;
  name: string;
  description: string;
  category: string;
  tags: string[];
  author: string;
  nodes: MarketplaceNode[];
  edges: unknown[];
  install_count: number;
  featured: boolean;
  published_at: number;
}

interface SearchResponse {
  items: MarketplaceListing[];
  total: number;
  page: number;
  per_page: number;
}

interface TrendingResponse {
  items: MarketplaceListing[];
  total: number;
}

type SortOption = 'popular' | 'newest' | 'most_installed' | 'alphabetical';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PER_PAGE = 12;

const SORT_OPTIONS: { value: SortOption; label: string }[] = [
  { value: 'popular', label: 'Most Popular' },
  { value: 'newest', label: 'Newest' },
  { value: 'most_installed', label: 'Most Installed' },
  { value: 'alphabetical', label: 'Alphabetical' },
];

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

const NODE_TYPE_COLORS: Record<string, string> = {
  llm: '#a855f7',
  gpt: '#a855f7',
  openai: '#a855f7',
  anthropic: '#a855f7',
  http: '#3b82f6',
  api: '#3b82f6',
  webhook: '#3b82f6',
  code: '#eab308',
  script: '#eab308',
  transform: '#14b8a6',
  map: '#14b8a6',
  filter: '#14b8a6',
  memory: '#22c55e',
  store: '#22c55e',
  database: '#22c55e',
  image: '#f97316',
  imagegen: '#f97316',
  art: '#f97316',
  input: '#6b7280',
  output: '#6b7280',
  start: '#6b7280',
  end: '#6b7280',
};

const CATEGORY_COLORS: Record<string, string> = {
  notification: '#f97316',
  'data-sync': '#3b82f6',
  monitoring: '#eab308',
  content: '#a855f7',
  devops: '#14b8a6',
  ai: '#8b5cf6',
  automation: '#06b6d4',
  data: '#10b981',
  integration: '#f43f5e',
};

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

function deriveStarRating(installCount: number): string {
  // Map install count to a 3.5–5.0 rating, in 0.5 steps
  const raw = 3.5 + Math.min(installCount / 40, 1.5);
  const rounded = Math.round(raw * 2) / 2;
  return rounded.toFixed(1);
}

function renderStars(rating: string): string {
  const val = parseFloat(rating);
  const full = Math.floor(val);
  const half = val - full >= 0.5 ? 1 : 0;
  const empty = 5 - full - half;
  return '★'.repeat(full) + (half ? '½' : '') + '☆'.repeat(empty);
}

function getNodeColor(nodeType: string | undefined): string {
  if (!nodeType) return '#6b7280';
  const lower = nodeType.toLowerCase();
  for (const [key, color] of Object.entries(NODE_TYPE_COLORS)) {
    if (lower.includes(key)) return color;
  }
  return '#6b7280';
}

function getCategoryColor(category: string): string {
  const lower = category.toLowerCase();
  return CATEGORY_COLORS[lower] ?? '#6b7280';
}

function formatInstallCount(count: number): string {
  if (count >= 1000) return `${(count / 1000).toFixed(1)}k`;
  return String(count);
}

function sortListings(items: MarketplaceListing[], sort: SortOption): MarketplaceListing[] {
  const copy = [...items];
  switch (sort) {
    case 'popular':
    case 'most_installed':
      return copy.sort((a, b) => b.install_count - a.install_count);
    case 'newest':
      return copy.sort((a, b) => b.published_at - a.published_at);
    case 'alphabetical':
      return copy.sort((a, b) => a.name.localeCompare(b.name));
    default:
      return copy;
  }
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface NodePreviewProps {
  nodes: MarketplaceNode[];
}

const NodePreview: React.FC<NodePreviewProps> = ({ nodes }) => {
  if (nodes.length === 0) {
    return (
      <div className="gallery-card-preview gallery-card-preview--empty">
        <span className="gallery-card-preview-label">No preview</span>
      </div>
    );
  }

  // Show up to 6 nodes in the preview strip
  const visible = nodes.slice(0, 6);
  const remaining = nodes.length - visible.length;

  return (
    <div className="gallery-card-preview">
      <div className="gallery-card-preview-strip">
        {visible.map((node, idx) => {
          const color = getNodeColor(node.type);
          return (
            <React.Fragment key={node.id}>
              {idx > 0 && <div className="gallery-card-preview-connector" />}
              <div
                className="gallery-card-preview-node"
                style={{ backgroundColor: color }}
                title={node.type ?? 'node'}
              >
                <span className="gallery-card-preview-node-label">
                  {(node.type ?? 'node').slice(0, 3).toUpperCase()}
                </span>
              </div>
            </React.Fragment>
          );
        })}
        {remaining > 0 && (
          <>
            <div className="gallery-card-preview-connector" />
            <div className="gallery-card-preview-node gallery-card-preview-node--more">
              +{remaining}
            </div>
          </>
        )}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Toast
// ---------------------------------------------------------------------------

interface ToastMessage {
  id: number;
  text: string;
  type: 'success' | 'error';
}

interface ToastProps {
  messages: ToastMessage[];
  onDismiss: (id: number) => void;
}

const Toast: React.FC<ToastProps> = ({ messages, onDismiss }) => {
  return (
    <div className="gallery-toast-container">
      {messages.map((msg) => (
        <div key={msg.id} className={`gallery-toast gallery-toast--${msg.type}`}>
          <span>{msg.text}</span>
          <button className="gallery-toast-close" onClick={() => onDismiss(msg.id)}>
            x
          </button>
        </div>
      ))}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

const TRENDING_RANK_BADGES: Record<number, string> = {
  0: '🥇',
  1: '🥈',
  2: '🥉',
};

const GalleryPage: React.FC = () => {
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [selectedCategories, setSelectedCategories] = useState<Set<string>>(new Set());
  const [sort, setSort] = useState<SortOption>('popular');
  const [allItems, setAllItems] = useState<MarketplaceListing[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [installedIds, setInstalledIds] = useState<Set<string>>(new Set());
  const [installingIds, setInstallingIds] = useState<Set<string>>(new Set());
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const toastCounter = useRef(0);
  const [trendingItems, setTrendingItems] = useState<MarketplaceListing[]>([]);

  // Debounce search query
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQuery(query);
    }, 400);
    return () => clearTimeout(timer);
  }, [query]);

  // Reset to page 1 when search/category changes
  useEffect(() => {
    setPage(1);
    setAllItems([]);
  }, [debouncedQuery, selectedCategories]);

  const addToast = useCallback((text: string, type: 'success' | 'error') => {
    const id = ++toastCounter.current;
    setToasts((prev) => [...prev, { id, text, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  }, []);

  const dismissToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const fetchListings = useCallback(
    async (pageNum: number, append: boolean) => {
      if (append) {
        setLoadingMore(true);
      } else {
        setLoading(true);
      }

      try {
        const params = new URLSearchParams({
          page: String(pageNum),
          per_page: String(PER_PAGE),
        });
        if (debouncedQuery) params.set('q', debouncedQuery);
        if (selectedCategories.size === 1) {
          const [cat] = selectedCategories;
          params.set('category', cat);
        }

        const data = await apiFetch<SearchResponse>(
          `/api/v1/marketplace/search?${params.toString()}`,
        );

        setTotal(data.total);
        setAllItems((prev) => (append ? [...prev, ...data.items] : data.items));
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to load gallery';
        addToast(message, 'error');
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [debouncedQuery, selectedCategories, addToast],
  );

  // Initial load and re-fetch on filter change
  useEffect(() => {
    fetchListings(1, false);
  }, [fetchListings]);

  // Fetch trending listings once on mount
  useEffect(() => {
    let cancelled = false;
    apiFetch<TrendingResponse>('/api/v1/marketplace/trending?limit=3')
      .then((data) => {
        if (!cancelled) setTrendingItems(data.items);
      })
      .catch(() => {
        // Trending section is non-critical; silently skip on error
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleLoadMore = () => {
    const nextPage = page + 1;
    setPage(nextPage);
    fetchListings(nextPage, true);
  };

  const handleInstall = async (listing: MarketplaceListing) => {
    if (installedIds.has(listing.id) || installingIds.has(listing.id)) return;

    setInstallingIds((prev) => new Set(prev).add(listing.id));

    try {
      await apiFetch(`/api/v1/marketplace/install/${listing.id}`, {
        method: 'POST',
        body: JSON.stringify({}),
      });

      setInstalledIds((prev) => new Set(prev).add(listing.id));
      addToast(`"${listing.name}" installed successfully!`, 'success');

      // Optimistically update install_count in local state
      setAllItems((prev) =>
        prev.map((item) =>
          item.id === listing.id
            ? { ...item, install_count: item.install_count + 1 }
            : item,
        ),
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Installation failed';
      addToast(message, 'error');
    } finally {
      setInstallingIds((prev) => {
        const next = new Set(prev);
        next.delete(listing.id);
        return next;
      });
    }
  };

  const toggleCategory = (cat: string) => {
    setSelectedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) {
        next.delete(cat);
      } else {
        next.add(cat);
      }
      return next;
    });
  };

  const clearFilters = () => {
    setSelectedCategories(new Set());
    setSort('popular');
    setQuery('');
  };

  // Client-side filtering by multiple categories (server supports only one)
  const visibleItems = selectedCategories.size > 1
    ? sortListings(
        allItems.filter((item) => selectedCategories.has(item.category.toLowerCase())),
        sort,
      )
    : sortListings(allItems, sort);

  // Derive category counts from current results for the sidebar
  const categoryCounts = visibleItems.reduce<Record<string, number>>((acc, item) => {
    const cat = item.category.toLowerCase();
    acc[cat] = (acc[cat] ?? 0) + 1;
    return acc;
  }, {});

  const hasMore = allItems.length < total && selectedCategories.size <= 1;

  // Stats: compute unique categories and total installs from all loaded items
  const uniqueCategories = new Set(allItems.map((i) => i.category)).size;
  const totalInstalls = allItems.reduce((sum, i) => sum + i.install_count, 0);

  return (
    <MainLayout title="Workflow Gallery">
      <Toast messages={toasts} onDismiss={dismissToast} />

      {/* Hero */}
      <section className="gallery-hero">
        <div className="gallery-hero-text">
          <h2 className="gallery-hero-title">Discover & Install Workflows</h2>
          <p className="gallery-hero-subtitle">
            Browse community-built AI workflows. One click to install into your workspace.
          </p>
        </div>

        <div className="gallery-search-bar">
          <span className="gallery-search-icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
          </span>
          <input
            className="gallery-search-input"
            type="search"
            placeholder="Search workflows by name, description, or tag..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search workflows"
          />
          {query && (
            <button
              className="gallery-search-clear"
              onClick={() => setQuery('')}
              aria-label="Clear search"
            >
              x
            </button>
          )}
        </div>

        <div className="gallery-stats-bar">
          <span>{total} templates</span>
          <span className="gallery-stats-dot" />
          <span>{uniqueCategories} categories</span>
          <span className="gallery-stats-dot" />
          <span>{formatInstallCount(totalInstalls)} installs</span>
        </div>
      </section>

      {/* Trending This Week */}
      {trendingItems.length > 0 && (
        <section className="gallery-trending" aria-label="Trending this week">
          <h2 className="gallery-trending-title">🔥 Trending This Week</h2>
          <div className="gallery-trending-row">
            {trendingItems.map((listing, idx) => {
              const isInstalled = installedIds.has(listing.id);
              const isInstalling = installingIds.has(listing.id);
              const rankBadge = TRENDING_RANK_BADGES[idx] ?? `#${idx + 1}`;

              return (
                <article key={listing.id} className="gallery-card gallery-card--compact">
                  <div className="gallery-trending-rank">{rankBadge}</div>
                  <div className="gallery-card-body">
                    <div className="gallery-card-top">
                      <h3 className="gallery-card-title gallery-card-title--sm" title={listing.name}>
                        {listing.name}
                      </h3>
                      <p className="gallery-card-description gallery-card-description--sm">
                        {listing.description}
                      </p>
                    </div>

                    <div className="gallery-card-meta">
                      <span
                        className="gallery-category-badge"
                        style={{
                          backgroundColor: `${getCategoryColor(listing.category)}22`,
                          color: getCategoryColor(listing.category),
                          borderColor: `${getCategoryColor(listing.category)}44`,
                        }}
                      >
                        {listing.category}
                      </span>
                    </div>

                    <div className="gallery-card-footer">
                      <span className="gallery-installs">
                        <svg
                          width="12"
                          height="12"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          aria-hidden="true"
                        >
                          <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                          <polyline points="7 10 12 15 17 10" />
                          <line x1="12" y1="15" x2="12" y2="3" />
                        </svg>
                        {formatInstallCount(listing.install_count)}
                      </span>

                      <button
                        className={`gallery-install-btn ${isInstalled ? 'gallery-install-btn--installed' : ''} ${isInstalling ? 'gallery-install-btn--installing' : ''}`}
                        onClick={() => handleInstall(listing)}
                        disabled={isInstalled || isInstalling}
                        aria-label={isInstalled ? 'Installed' : `Install ${listing.name}`}
                      >
                        {isInstalling ? (
                          <span className="gallery-btn-spinner" />
                        ) : isInstalled ? (
                          'Installed'
                        ) : (
                          'Install'
                        )}
                      </button>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        </section>
      )}

      {/* Body: sidebar + grid */}
      <div className="gallery-body">
        {/* Filter sidebar */}
        <aside className="gallery-sidebar">
          <div className="gallery-sidebar-section">
            <div className="gallery-sidebar-header">
              <h3 className="gallery-sidebar-title">Categories</h3>
              {(selectedCategories.size > 0 || sort !== 'popular') && (
                <button className="gallery-clear-btn" onClick={clearFilters}>
                  Clear filters
                </button>
              )}
            </div>

            <div className="gallery-category-list">
              {KNOWN_CATEGORIES.map((cat) => {
                const count = categoryCounts[cat] ?? 0;
                const active = selectedCategories.has(cat);
                return (
                  <button
                    key={cat}
                    className={`gallery-category-pill ${active ? 'gallery-category-pill--active' : ''}`}
                    onClick={() => toggleCategory(cat)}
                    aria-pressed={active}
                  >
                    <span
                      className="gallery-category-dot"
                      style={{ backgroundColor: getCategoryColor(cat) }}
                    />
                    <span className="gallery-category-label">{cat}</span>
                    {count > 0 && <span className="gallery-category-count">{count}</span>}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="gallery-sidebar-section">
            <h3 className="gallery-sidebar-title">Sort By</h3>
            <select
              className="gallery-sort-select"
              value={sort}
              onChange={(e) => setSort(e.target.value as SortOption)}
              aria-label="Sort listings"
            >
              {SORT_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
        </aside>

        {/* Main grid */}
        <div className="gallery-main">
          {loading ? (
            <div className="gallery-loading">
              <div className="gallery-spinner" />
              <p>Loading workflows...</p>
            </div>
          ) : visibleItems.length === 0 ? (
            <div className="gallery-empty">
              <div className="gallery-empty-icon">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="2" y="3" width="20" height="14" rx="2" />
                  <line x1="8" y1="21" x2="16" y2="21" />
                  <line x1="12" y1="17" x2="12" y2="21" />
                </svg>
              </div>
              <h3 className="gallery-empty-title">No workflows found</h3>
              <p className="gallery-empty-sub">
                Try adjusting your search or clearing the filters.
              </p>
              <button className="gallery-clear-btn gallery-clear-btn--cta" onClick={clearFilters}>
                Clear filters
              </button>
            </div>
          ) : (
            <>
              <div className="gallery-grid">
                {visibleItems.map((listing) => {
                  const isInstalled = installedIds.has(listing.id);
                  const isInstalling = installingIds.has(listing.id);
                  const rating = deriveStarRating(listing.install_count);
                  const visibleTags = listing.tags.slice(0, 3);
                  const extraTags = listing.tags.length - visibleTags.length;

                  return (
                    <article key={listing.id} className="gallery-card">
                      <NodePreview nodes={listing.nodes} />

                      <div className="gallery-card-body">
                        <div className="gallery-card-top">
                          <h3 className="gallery-card-title" title={listing.name}>
                            {listing.name}
                          </h3>
                          <p className="gallery-card-description">{listing.description}</p>
                        </div>

                        <div className="gallery-card-meta">
                          <span
                            className="gallery-category-badge"
                            style={{ backgroundColor: `${getCategoryColor(listing.category)}22`, color: getCategoryColor(listing.category), borderColor: `${getCategoryColor(listing.category)}44` }}
                          >
                            {listing.category}
                          </span>

                          <div className="gallery-tags">
                            {visibleTags.map((tag) => (
                              <span key={tag} className="gallery-tag">
                                {tag}
                              </span>
                            ))}
                            {extraTags > 0 && (
                              <span className="gallery-tag gallery-tag--more">+{extraTags}</span>
                            )}
                          </div>
                        </div>

                        <div className="gallery-card-footer">
                          <div className="gallery-card-stats">
                            <span className="gallery-rating" title={`Rating: ${rating}`}>
                              <span className="gallery-stars">{renderStars(rating)}</span>
                              <span className="gallery-rating-value">{rating}</span>
                            </span>
                            <span className="gallery-installs">
                              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                                <polyline points="7 10 12 15 17 10" />
                                <line x1="12" y1="15" x2="12" y2="3" />
                              </svg>
                              {formatInstallCount(listing.install_count)}
                            </span>
                          </div>

                          <button
                            className={`gallery-install-btn ${isInstalled ? 'gallery-install-btn--installed' : ''} ${isInstalling ? 'gallery-install-btn--installing' : ''}`}
                            onClick={() => handleInstall(listing)}
                            disabled={isInstalled || isInstalling}
                            aria-label={isInstalled ? 'Installed' : `Install ${listing.name}`}
                          >
                            {isInstalling ? (
                              <span className="gallery-btn-spinner" />
                            ) : isInstalled ? (
                              'Installed'
                            ) : (
                              'Install'
                            )}
                          </button>
                        </div>
                      </div>
                    </article>
                  );
                })}
              </div>

              {hasMore && (
                <div className="gallery-load-more">
                  <button
                    className="gallery-load-more-btn"
                    onClick={handleLoadMore}
                    disabled={loadingMore}
                  >
                    {loadingMore ? (
                      <>
                        <span className="gallery-btn-spinner" />
                        Loading...
                      </>
                    ) : (
                      `Load More (${total - allItems.length} remaining)`
                    )}
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </MainLayout>
  );
};

export default GalleryPage;
