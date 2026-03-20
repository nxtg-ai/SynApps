/**
 * AdminFeaturedPage — Admin interface for managing featured marketplace listings.
 *
 * Allows admins to feature/unfeature listings with an optional curator blurb.
 * The hero section on the gallery page shows the top 3 featured listings.
 */
import React, { useState, useEffect, useCallback } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface MarketplaceListing {
  id: string;
  name: string;
  description: string;
  category: string;
  is_featured?: boolean;
}

interface FeaturedEntry {
  listing_id: string;
  featured_at: number;
  featured_by: string;
  blurb: string;
}

interface SearchResponse {
  items: MarketplaceListing[];
  total: number;
}

interface FeaturedResponse {
  items: (MarketplaceListing & FeaturedEntry)[];
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
  if (res.status === 204) return undefined as unknown as T;
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const AdminFeaturedPage: React.FC = () => {
  const [allListings, setAllListings] = useState<MarketplaceListing[]>([]);
  const [featuredIds, setFeaturedIds] = useState<Set<string>>(new Set());
  const [featuredCount, setFeaturedCount] = useState(0);
  const [blurbInputs, setBlurbInputs] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionInProgress, setActionInProgress] = useState<Set<string>>(new Set());

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [searchData, featuredData] = await Promise.all([
        apiFetch<SearchResponse>('/api/v1/marketplace/search?per_page=100'),
        apiFetch<FeaturedResponse>('/api/v1/marketplace/featured'),
      ]);

      setAllListings(searchData.items);
      const ids = new Set(featuredData.items.map((item) => item.listing_id ?? item.id));
      setFeaturedIds(ids);
      setFeaturedCount(featuredData.total);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load data';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleFeature = async (listingId: string) => {
    setActionInProgress((prev) => new Set(prev).add(listingId));
    try {
      const blurb = blurbInputs[listingId] ?? '';
      await apiFetch(`/api/v1/marketplace/${listingId}/feature`, {
        method: 'POST',
        body: JSON.stringify({ blurb }),
      });
      setFeaturedIds((prev) => new Set(prev).add(listingId));
      setFeaturedCount((prev) => prev + 1);
    } catch {
      // Feature action failed — user sees the button remain in unfeatured state
    } finally {
      setActionInProgress((prev) => {
        const next = new Set(prev);
        next.delete(listingId);
        return next;
      });
    }
  };

  const handleUnfeature = async (listingId: string) => {
    setActionInProgress((prev) => new Set(prev).add(listingId));
    try {
      await apiFetch(`/api/v1/marketplace/${listingId}/feature`, {
        method: 'DELETE',
      });
      setFeaturedIds((prev) => {
        const next = new Set(prev);
        next.delete(listingId);
        return next;
      });
      setFeaturedCount((prev) => Math.max(0, prev - 1));
    } catch {
      // Unfeature action failed — user sees the button remain in featured state
    } finally {
      setActionInProgress((prev) => {
        const next = new Set(prev);
        next.delete(listingId);
        return next;
      });
    }
  };

  const handleBlurbChange = (listingId: string, value: string) => {
    setBlurbInputs((prev) => ({ ...prev, [listingId]: value }));
  };

  return (
    <MainLayout title="Featured Listings">
      <div data-testid="admin-featured-page" style={{ padding: '1.5rem' }}>
        <div style={{ marginBottom: '1.5rem' }}>
          <p data-testid="featured-count">
            Currently featured: <strong>{featuredCount}</strong> listing{featuredCount !== 1 ? 's' : ''}
          </p>
          <p style={{ color: '#94a3b8', fontSize: '0.875rem' }}>
            The hero section on the Gallery page will show the top 3 featured listings.
          </p>
        </div>

        {loading && <p data-testid="loading-indicator">Loading listings...</p>}

        {error && (
          <p data-testid="error-message" style={{ color: '#ef4444' }}>
            {error}
          </p>
        )}

        {!loading && !error && allListings.length === 0 && (
          <p data-testid="empty-state">No marketplace listings available.</p>
        )}

        {!loading && !error && allListings.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {allListings.map((listing) => {
              const isFeatured = featuredIds.has(listing.id);
              const isProcessing = actionInProgress.has(listing.id);

              return (
                <div
                  key={listing.id}
                  data-testid="listing-row"
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '1rem',
                    padding: '1rem',
                    borderRadius: '0.5rem',
                    border: isFeatured ? '1px solid #eab308' : '1px solid #334155',
                    backgroundColor: isFeatured ? '#1e1b0f' : '#0f172a',
                  }}
                >
                  <div style={{ flex: 1 }}>
                    <strong>{listing.name}</strong>
                    <p style={{ color: '#94a3b8', fontSize: '0.875rem', margin: 0 }}>
                      {listing.description}
                    </p>
                  </div>

                  {!isFeatured && (
                    <input
                      type="text"
                      placeholder="Curator blurb (optional)"
                      value={blurbInputs[listing.id] ?? ''}
                      onChange={(e) => handleBlurbChange(listing.id, e.target.value)}
                      maxLength={200}
                      aria-label={`Blurb for ${listing.name}`}
                      data-testid="blurb-input"
                      style={{
                        padding: '0.375rem 0.75rem',
                        borderRadius: '0.375rem',
                        border: '1px solid #334155',
                        backgroundColor: '#1e293b',
                        color: '#e2e8f0',
                        width: '200px',
                      }}
                    />
                  )}

                  {isFeatured ? (
                    <button
                      onClick={() => handleUnfeature(listing.id)}
                      disabled={isProcessing}
                      data-testid="unfeature-btn"
                      style={{
                        padding: '0.375rem 1rem',
                        borderRadius: '0.375rem',
                        border: '1px solid #ef4444',
                        backgroundColor: 'transparent',
                        color: '#ef4444',
                        cursor: isProcessing ? 'not-allowed' : 'pointer',
                      }}
                    >
                      Unfeature
                    </button>
                  ) : (
                    <button
                      onClick={() => handleFeature(listing.id)}
                      disabled={isProcessing}
                      data-testid="feature-btn"
                      style={{
                        padding: '0.375rem 1rem',
                        borderRadius: '0.375rem',
                        border: '1px solid #eab308',
                        backgroundColor: 'transparent',
                        color: '#eab308',
                        cursor: isProcessing ? 'not-allowed' : 'pointer',
                      }}
                    >
                      Feature
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </MainLayout>
  );
};

export default AdminFeaturedPage;
