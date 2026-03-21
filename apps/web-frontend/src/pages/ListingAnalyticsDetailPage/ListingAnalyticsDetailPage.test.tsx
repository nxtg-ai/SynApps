import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ListingAnalyticsDetailPage from './ListingAnalyticsDetailPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children, title }: { children: React.ReactNode; title: string }) => (
    <div data-testid="layout">
      <span data-testid="layout-title">{title}</span>
      {children}
    </div>
  ),
}));

const LISTING_DETAIL = {
  listing: { id: 'lst-aaa-111', name: 'My Listing', publisher_id: 'user-1' },
  stats: {
    avg_rating: 4.3,
    rating_count: 12,
    review_count: 5,
    credits_earned: 88,
    trending_score: 9.1,
    is_featured: true,
  },
  recent_reviews: [
    {
      review_id: 'rev-001',
      reviewer_id: 'user-42',
      rating: 5,
      comment: 'Great workflow!',
      reply: { body: 'Thanks!' },
    },
    {
      review_id: 'rev-002',
      reviewer_id: 'user-99',
      rating: 3,
      comment: 'Could be better.',
      reply: null,
    },
  ],
  install_trend: Array.from({ length: 30 }, (_, i) => ({
    date: `2026-02-${String(i + 1).padStart(2, '0')}`,
    installs: i % 3,
  })),
};

function makeOk(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response;
}

function makeErr(status: number, detail: string) {
  return { ok: false, status, json: async () => ({ detail }) } as Response;
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ListingAnalyticsDetailPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn());
  window.localStorage.setItem('access_token', 'tok-test');
});

describe('ListingAnalyticsDetailPage', () => {
  // 1. Page title
  it('renders page title', () => {
    renderPage();
    expect(screen.getByTestId('page-title')).toHaveTextContent('Listing Analytics Detail');
  });

  // 2. Fetch button disabled without listing ID
  it('fetch button disabled without listing ID', () => {
    renderPage();
    expect(screen.getByTestId('fetch-btn')).toBeDisabled();
  });

  // 3. Calls GET /publisher/analytics/{listing_id}
  it('calls GET /publisher/analytics/{listing_id} on submit', async () => {
    const fetchMock = vi.fn().mockResolvedValue(makeOk(LISTING_DETAIL));
    vi.stubGlobal('fetch', fetchMock);
    renderPage();
    fireEvent.change(screen.getByTestId('listing-id-input'), {
      target: { value: 'lst-aaa-111' },
    });
    fireEvent.click(screen.getByTestId('fetch-btn'));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/marketplace/publisher/analytics/lst-aaa-111'),
        expect.any(Object),
      ),
    );
  });

  // 4. Detail panel shown on success
  it('renders detail panel after successful fetch', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(LISTING_DETAIL)));
    renderPage();
    fireEvent.change(screen.getByTestId('listing-id-input'), {
      target: { value: 'lst-aaa-111' },
    });
    fireEvent.click(screen.getByTestId('fetch-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('detail-panel')).toBeInTheDocument(),
    );
  });

  // 5. Stats section rendered
  it('displays all stat cards', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(LISTING_DETAIL)));
    renderPage();
    fireEvent.change(screen.getByTestId('listing-id-input'), {
      target: { value: 'lst-aaa-111' },
    });
    fireEvent.click(screen.getByTestId('fetch-btn'));
    await waitFor(() => expect(screen.getByTestId('stats-section')).toBeInTheDocument());
    expect(screen.getByTestId('stat-rating')).toBeInTheDocument();
    expect(screen.getByTestId('stat-credits')).toBeInTheDocument();
    expect(screen.getByTestId('stat-featured')).toBeInTheDocument();
  });

  // 6. Avg rating shown
  it('displays avg rating value', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(LISTING_DETAIL)));
    renderPage();
    fireEvent.change(screen.getByTestId('listing-id-input'), {
      target: { value: 'lst-aaa-111' },
    });
    fireEvent.click(screen.getByTestId('fetch-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('stat-rating')).toHaveTextContent('4.3'),
    );
  });

  // 7. Featured status shown
  it('shows featured status correctly', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(LISTING_DETAIL)));
    renderPage();
    fireEvent.change(screen.getByTestId('listing-id-input'), {
      target: { value: 'lst-aaa-111' },
    });
    fireEvent.click(screen.getByTestId('fetch-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('stat-featured')).toHaveTextContent('Yes'),
    );
  });

  // 8. Credits earned shown
  it('displays credits earned', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(LISTING_DETAIL)));
    renderPage();
    fireEvent.change(screen.getByTestId('listing-id-input'), {
      target: { value: 'lst-aaa-111' },
    });
    fireEvent.click(screen.getByTestId('fetch-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('stat-credits')).toHaveTextContent('88'),
    );
  });

  // 9. Install trend bars rendered
  it('renders 30 trend bars', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(LISTING_DETAIL)));
    renderPage();
    fireEvent.change(screen.getByTestId('listing-id-input'), {
      target: { value: 'lst-aaa-111' },
    });
    fireEvent.click(screen.getByTestId('fetch-btn'));
    await waitFor(() => expect(screen.getByTestId('trend-section')).toBeInTheDocument());
    const bars = screen.getAllByTestId('trend-bar');
    expect(bars.length).toBe(30);
  });

  // 10. Reviews list rendered
  it('renders review items', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(LISTING_DETAIL)));
    renderPage();
    fireEvent.change(screen.getByTestId('listing-id-input'), {
      target: { value: 'lst-aaa-111' },
    });
    fireEvent.click(screen.getByTestId('fetch-btn'));
    await waitFor(() => {
      const items = screen.getAllByTestId('review-item');
      expect(items.length).toBeGreaterThanOrEqual(1);
    });
  });

  // 11. Review comment shown
  it('displays review comment text', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(LISTING_DETAIL)));
    renderPage();
    fireEvent.change(screen.getByTestId('listing-id-input'), {
      target: { value: 'lst-aaa-111' },
    });
    fireEvent.click(screen.getByTestId('fetch-btn'));
    await waitFor(() =>
      expect(screen.getByText('Great workflow!')).toBeInTheDocument(),
    );
  });

  // 12. Publisher reply shown
  it('shows publisher reply when present', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(LISTING_DETAIL)));
    renderPage();
    fireEvent.change(screen.getByTestId('listing-id-input'), {
      target: { value: 'lst-aaa-111' },
    });
    fireEvent.click(screen.getByTestId('fetch-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('review-reply')).toBeInTheDocument(),
    );
  });

  // 13. Error shown on API failure
  it('shows error message on fetch failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeErr(403, 'Listing not owned by current user')));
    renderPage();
    fireEvent.change(screen.getByTestId('listing-id-input'), {
      target: { value: 'bad-id' },
    });
    fireEvent.click(screen.getByTestId('fetch-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('fetch-error')).toHaveTextContent('Listing not owned by current user'),
    );
  });

  // 14. Empty reviews state shown
  it('shows no-reviews message when reviews list is empty', async () => {
    const noReviews = { ...LISTING_DETAIL, recent_reviews: [] };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(noReviews)));
    renderPage();
    fireEvent.change(screen.getByTestId('listing-id-input'), {
      target: { value: 'lst-aaa-111' },
    });
    fireEvent.click(screen.getByTestId('fetch-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('no-reviews')).toBeInTheDocument(),
    );
  });
});
