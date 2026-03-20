/**
 * Tests for PublisherAnalyticsDashboard -- N-50 publisher analytics.
 *
 * Covers: loading state, KPI cards, top templates, growth chart,
 * per-listing table, days selector, empty state, error state.
 *
 * Total: 10 tests.
 */
import React from 'react';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, afterEach } from 'vitest';
import PublisherAnalyticsDashboard from './PublisherAnalyticsDashboard';

// ---------------------------------------------------------------------------
// Mock MainLayout
// ---------------------------------------------------------------------------

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="main-layout">{children}</div>
  ),
}));

// ---------------------------------------------------------------------------
// Mock navigate
// ---------------------------------------------------------------------------

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// ---------------------------------------------------------------------------
// Factories
// ---------------------------------------------------------------------------

function makeAnalyticsResponse(
  overrides: Partial<{
    summary: Record<string, unknown>;
    per_listing: Array<Record<string, unknown>>;
    growth_trend: Array<Record<string, unknown>>;
    top_templates: Array<Record<string, unknown>>;
  }> = {},
) {
  return {
    summary: {
      total_installs: 150,
      total_listings: 5,
      avg_rating: 4.2,
      total_credits_earned: 300,
      credit_balance: 200,
      total_reviews: 12,
      featured_count: 1,
      ...(overrides.summary ?? {}),
    },
    per_listing: overrides.per_listing ?? [
      {
        listing_id: 'lst-1',
        name: 'AI Writer',
        install_count: 80,
        avg_rating: 4.5,
        rating_count: 6,
        review_count: 4,
        credits_earned: 160,
        trending_score: 90,
        is_featured: true,
        published_at: Date.now() / 1000,
      },
      {
        listing_id: 'lst-2',
        name: 'Data Pipeline',
        install_count: 70,
        avg_rating: 3.9,
        rating_count: 4,
        review_count: 8,
        credits_earned: 140,
        trending_score: 70,
        is_featured: false,
        published_at: Date.now() / 1000,
      },
    ],
    growth_trend: overrides.growth_trend ?? [
      { date: '2026-03-18', installs: 3 },
      { date: '2026-03-19', installs: 5 },
      { date: '2026-03-20', installs: 2 },
    ],
    top_templates: overrides.top_templates ?? [
      {
        listing_id: 'lst-1',
        name: 'AI Writer',
        install_count: 80,
        avg_rating: 4.5,
        rating_count: 6,
        review_count: 4,
        credits_earned: 160,
        trending_score: 90,
        is_featured: true,
        published_at: Date.now() / 1000,
      },
    ],
  };
}

function mockFetch(data: ReturnType<typeof makeAnalyticsResponse>) {
  vi.spyOn(global, 'fetch').mockResolvedValue(new Response(JSON.stringify(data), { status: 200 }));
}

function renderPage() {
  return render(
    <MemoryRouter>
      <PublisherAnalyticsDashboard />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('PublisherAnalyticsDashboard', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    mockNavigate.mockReset();
  });

  it('shows loading state', () => {
    vi.spyOn(global, 'fetch').mockReturnValue(new Promise(() => {}));

    renderPage();

    expect(screen.getByLabelText('Loading analytics')).toBeInTheDocument();
  });

  it('renders KPI cards with correct values', async () => {
    mockFetch(makeAnalyticsResponse());

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('kpi-total-installs')).toHaveTextContent('150');
      expect(screen.getByTestId('kpi-total-templates')).toHaveTextContent('5');
      expect(screen.getByTestId('kpi-credits-earned')).toHaveTextContent('300');
      expect(screen.getByTestId('kpi-credit-balance')).toHaveTextContent('200');
      expect(screen.getByTestId('kpi-total-reviews')).toHaveTextContent('12');
    });
  });

  it('shows total installs KPI', async () => {
    mockFetch(makeAnalyticsResponse({ summary: { total_installs: 42 } }));

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('kpi-total-installs')).toHaveTextContent('42');
    });
  });

  it('shows avg rating KPI', async () => {
    mockFetch(makeAnalyticsResponse({ summary: { avg_rating: 4.8 } }));

    renderPage();

    await waitFor(() => {
      const el = screen.getByTestId('kpi-avg-rating');
      expect(el).toHaveTextContent('4.8');
    });
  });

  it('renders top templates section', async () => {
    mockFetch(makeAnalyticsResponse());

    renderPage();

    await waitFor(() => {
      const section = screen.getByTestId('top-templates-section');
      expect(section).toBeInTheDocument();
      expect(within(section).getByText('AI Writer')).toBeInTheDocument();
    });
  });

  it('renders growth chart', async () => {
    mockFetch(makeAnalyticsResponse());

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('growth-chart')).toBeInTheDocument();
    });
  });

  it('renders per-listing table', async () => {
    mockFetch(makeAnalyticsResponse());

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('per-listing-table')).toBeInTheDocument();
      expect(screen.getByText('Data Pipeline')).toBeInTheDocument();
    });
  });

  it('days selector triggers re-fetch', async () => {
    const responseData = makeAnalyticsResponse();
    const fetchSpy = vi
      .spyOn(global, 'fetch')
      .mockImplementation(() =>
        Promise.resolve(new Response(JSON.stringify(responseData), { status: 200 })),
      );

    renderPage();

    // Wait for KPI cards to confirm data loaded
    await waitFor(() => {
      expect(screen.getByTestId('kpi-total-installs')).toBeInTheDocument();
    });

    // Initial fetch with days=30
    expect(fetchSpy).toHaveBeenCalledWith(expect.stringContaining('days=30'), expect.any(Object));

    // Click 7d button
    const daysSelector = screen.getByTestId('days-selector');
    fireEvent.click(within(daysSelector).getByText('7d'));

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(expect.stringContaining('days=7'), expect.any(Object));
    });
  });

  it('shows empty state when no listings', async () => {
    mockFetch(
      makeAnalyticsResponse({
        summary: {
          total_installs: 0,
          total_listings: 0,
          avg_rating: 0,
          total_credits_earned: 0,
          credit_balance: 0,
          total_reviews: 0,
          featured_count: 0,
        },
        per_listing: [],
        growth_trend: [],
        top_templates: [],
      }),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
      expect(screen.getByText(/No templates published yet/)).toBeInTheDocument();
    });
  });

  it('shows error state', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response('Internal Server Error', { status: 500 }),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
  });
});
