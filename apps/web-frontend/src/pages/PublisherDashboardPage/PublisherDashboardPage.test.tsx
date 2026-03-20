/**
 * Tests for PublisherDashboardPage — N-45.
 *
 * Covers: loading state, empty state, error state, and rendered listing data.
 */
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, afterEach } from 'vitest';
import PublisherDashboardPage from './PublisherDashboardPage';

// ---------------------------------------------------------------------------
// Mock MainLayout so the page renders in isolation
// ---------------------------------------------------------------------------

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="main-layout">{children}</div>
  ),
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeListing(overrides: Partial<{
  id: string;
  name: string;
  description: string;
  category: string;
  tags: string[];
  install_count: number;
  avg_rating: number;
  rating_count: number;
  trending_score: number;
  recent_reviews: Array<{ review_id: string; listing_id: string; user_id: string; text: string; stars: number | null; created_at: number }>;
  published_at: number;
}> = {}) {
  return {
    id: 'listing-1',
    name: 'Test Listing',
    description: 'A test listing description',
    category: 'notification',
    tags: ['test'],
    install_count: 42,
    avg_rating: 4.5,
    rating_count: 10,
    trending_score: 85,
    recent_reviews: [],
    published_at: Date.now() / 1000,
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <PublisherDashboardPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('PublisherDashboardPage', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders loading state initially', () => {
    // Make fetch never resolve so we stay in loading
    vi.spyOn(global, 'fetch').mockReturnValue(new Promise(() => {}));

    renderPage();

    expect(screen.getByLabelText('Loading publisher dashboard')).toBeInTheDocument();
  });

  it('shows "no listings" message when empty', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ listings: [], total: 0 }), { status: 200 }),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/haven't published any templates yet/i)).toBeInTheDocument();
    });
  });

  it('shows listing card with name', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(
        JSON.stringify({ listings: [makeListing({ name: 'Awesome Workflow' })], total: 1 }),
        { status: 200 },
      ),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Awesome Workflow')).toBeInTheDocument();
    });
  });

  it('shows install count', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(
        JSON.stringify({ listings: [makeListing({ install_count: 99 })], total: 1 }),
        { status: 200 },
      ),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/99 installs/i)).toBeInTheDocument();
    });
  });

  it('shows avg_rating', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(
        JSON.stringify({ listings: [makeListing({ avg_rating: 3.5, rating_count: 7 })], total: 1 }),
        { status: 200 },
      ),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/3\.5 \/ 5/i)).toBeInTheDocument();
    });
  });

  it('shows recent reviews', async () => {
    const listing = makeListing({
      recent_reviews: [
        {
          review_id: 'r1',
          listing_id: 'listing-1',
          user_id: 'user-1',
          text: 'A fantastic workflow',
          stars: 5,
          created_at: Date.now() / 1000,
        },
      ],
    });
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ listings: [listing], total: 1 }), { status: 200 }),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/A fantastic workflow/i)).toBeInTheDocument();
    });
  });

  it('shows error state when API fails', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response('Internal Server Error', { status: 500 }),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.getByRole('alert').textContent).toMatch(/error/i);
    });
  });

  it('shows multiple listings', async () => {
    const listings = [
      makeListing({ id: 'l1', name: 'First Listing' }),
      makeListing({ id: 'l2', name: 'Second Listing' }),
      makeListing({ id: 'l3', name: 'Third Listing' }),
    ];
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ listings, total: 3 }), { status: 200 }),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('First Listing')).toBeInTheDocument();
      expect(screen.getByText('Second Listing')).toBeInTheDocument();
      expect(screen.getByText('Third Listing')).toBeInTheDocument();
    });
  });
});
