/**
 * Unit tests for MarketplaceReviewsPage (N-101).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import MarketplaceReviewsPage from './MarketplaceReviewsPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const LISTING_ID = 'listing-abc-123';

const REVIEWS_LIST = [
  {
    review_id: 'rev-001',
    listing_id: LISTING_ID,
    user_id: 'user-1',
    text: 'Great workflow tool!',
    stars: 5,
    reply: {
      reply_id: 'rpl-001',
      review_id: 'rev-001',
      publisher_id: 'pub-1',
      text: 'Thank you for the kind words!',
    },
  },
  {
    review_id: 'rev-002',
    listing_id: LISTING_ID,
    user_id: 'user-2',
    text: 'Needs improvement.',
    stars: 2,
    reply: null,
  },
];

function renderPage() {
  return render(
    <MemoryRouter>
      <MarketplaceReviewsPage />
    </MemoryRouter>,
  );
}

function makeOk(body: unknown) {
  return { ok: true, json: async () => body } as Response;
}
function makeErr(status: number, detail: string) {
  return { ok: false, status, json: async () => ({ detail }) } as unknown as Response;
}

function setListingId(value: string) {
  fireEvent.change(screen.getByTestId('listing-id-input'), { target: { value } });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('MarketplaceReviewsPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title and listing id input', () => {
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
    expect(screen.getByTestId('listing-id-input')).toBeInTheDocument();
  });

  it('rate-btn disabled when listing id is empty', () => {
    renderPage();
    expect(screen.getByTestId('rate-btn')).toBeDisabled();
  });

  it('review-btn disabled when listing id or text is empty', () => {
    renderPage();
    expect(screen.getByTestId('review-btn')).toBeDisabled();
  });

  it('submits rating and shows result', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      makeOk({ listing_id: LISTING_ID, average: 4.2, count: 10 }),
    );
    renderPage();
    setListingId(LISTING_ID);
    fireEvent.change(screen.getByTestId('rate-stars-input'), { target: { value: '4' } });
    fireEvent.submit(screen.getByTestId('rate-form'));
    await waitFor(() => expect(screen.getByTestId('rate-result')).toBeInTheDocument());
    expect(screen.getByTestId('rate-average').textContent).toContain('4.2');
  });

  it('shows rate-error on failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(404, 'Listing not found'));
    renderPage();
    setListingId(LISTING_ID);
    fireEvent.submit(screen.getByTestId('rate-form'));
    await waitFor(() => expect(screen.getByTestId('rate-error')).toBeInTheDocument());
    expect(screen.getByTestId('rate-error').textContent).toContain('Listing not found');
  });

  it('submits review and shows review-result with id', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      makeOk({
        review_id: 'rev-new-999',
        listing_id: LISTING_ID,
        user_id: 'user-1',
        text: 'Awesome!',
        stars: 5,
      }),
    );
    renderPage();
    setListingId(LISTING_ID);
    fireEvent.change(screen.getByTestId('review-text-input'), {
      target: { value: 'Awesome!' },
    });
    fireEvent.submit(screen.getByTestId('review-form'));
    await waitFor(() => expect(screen.getByTestId('review-result')).toBeInTheDocument());
    expect(screen.getByTestId('review-id').textContent).toContain('rev-new-999');
  });

  it('shows review-error on failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(422, 'Text too short'));
    renderPage();
    setListingId(LISTING_ID);
    fireEvent.change(screen.getByTestId('review-text-input'), { target: { value: 'ok' } });
    fireEvent.submit(screen.getByTestId('review-form'));
    await waitFor(() => expect(screen.getByTestId('review-error')).toBeInTheDocument());
    expect(screen.getByTestId('review-error').textContent).toContain('Text too short');
  });

  it('loads reviews and shows list with replies', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      makeOk({ listing_id: LISTING_ID, items: REVIEWS_LIST, total: 2 }),
    );
    renderPage();
    setListingId(LISTING_ID);
    fireEvent.click(screen.getByTestId('load-reviews-btn'));
    await waitFor(() => expect(screen.getByTestId('reviews-list')).toBeInTheDocument());
    const items = screen.getAllByTestId('review-item');
    expect(items).toHaveLength(2);
    expect(items[0].textContent).toContain('Great workflow tool!');
    expect(screen.getAllByTestId('review-reply')).toHaveLength(1);
    expect(screen.getByTestId('reviews-total').textContent).toBe('2');
  });

  it('shows no-reviews when list is empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      makeOk({ listing_id: LISTING_ID, items: [], total: 0 }),
    );
    renderPage();
    setListingId(LISTING_ID);
    fireEvent.click(screen.getByTestId('load-reviews-btn'));
    await waitFor(() => expect(screen.getByTestId('no-reviews')).toBeInTheDocument());
  });

  it('handles array response shape for reviews', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(REVIEWS_LIST));
    renderPage();
    setListingId(LISTING_ID);
    fireEvent.click(screen.getByTestId('load-reviews-btn'));
    await waitFor(() => {
      const items = screen.getAllByTestId('review-item');
      expect(items).toHaveLength(2);
    });
  });

  it('shows reviews-error on failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(404, 'Listing not found'));
    renderPage();
    setListingId(LISTING_ID);
    fireEvent.click(screen.getByTestId('load-reviews-btn'));
    await waitFor(() => expect(screen.getByTestId('reviews-error')).toBeInTheDocument());
    expect(screen.getByTestId('reviews-error').textContent).toContain('Listing not found');
  });

  it('submits reply and shows reply-result with id', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      makeOk({ reply_id: 'rpl-new-111', review_id: 'rev-001', publisher_id: 'pub-1', text: 'Thanks!' }),
    );
    renderPage();
    fireEvent.change(screen.getByTestId('reply-review-id-input'), {
      target: { value: 'rev-001' },
    });
    fireEvent.change(screen.getByTestId('reply-text-input'), { target: { value: 'Thanks!' } });
    fireEvent.submit(screen.getByTestId('reply-form'));
    await waitFor(() => expect(screen.getByTestId('reply-result')).toBeInTheDocument());
    expect(screen.getByTestId('reply-id').textContent).toContain('rpl-new-111');
  });

  it('shows reply-error on failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(404, 'Review not found'));
    renderPage();
    fireEvent.change(screen.getByTestId('reply-review-id-input'), {
      target: { value: 'rev-999' },
    });
    fireEvent.change(screen.getByTestId('reply-text-input'), { target: { value: 'Hi' } });
    fireEvent.submit(screen.getByTestId('reply-form'));
    await waitFor(() => expect(screen.getByTestId('reply-error')).toBeInTheDocument());
    expect(screen.getByTestId('reply-error').textContent).toContain('Review not found');
  });

  it('report-btn disabled when listing id or description empty', () => {
    renderPage();
    expect(screen.getByTestId('report-btn')).toBeDisabled();
  });

  it('submits report and shows report-result', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      makeOk({ issue_id: 'issue-xyz-888', listing_id: LISTING_ID, type: 'broken' }),
    );
    renderPage();
    setListingId(LISTING_ID);
    fireEvent.change(screen.getByTestId('report-type-select'), { target: { value: 'broken' } });
    fireEvent.change(screen.getByTestId('report-description-input'), {
      target: { value: 'The workflow crashes on run.' },
    });
    fireEvent.submit(screen.getByTestId('report-form'));
    await waitFor(() => expect(screen.getByTestId('report-result')).toBeInTheDocument());
    expect(screen.getByTestId('report-id').textContent).toContain('issue-xyz-888');
  });

  it('shows report-error on failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(404, 'Listing not found'));
    renderPage();
    setListingId(LISTING_ID);
    fireEvent.change(screen.getByTestId('report-description-input'), {
      target: { value: 'broken' },
    });
    fireEvent.submit(screen.getByTestId('report-form'));
    await waitFor(() => expect(screen.getByTestId('report-error')).toBeInTheDocument());
    expect(screen.getByTestId('report-error').textContent).toContain('Listing not found');
  });

  it('review stars are optional — omit stars field when input is empty', async () => {
    let capturedBody: Record<string, unknown> = {};
    vi.mocked(fetch).mockImplementationOnce(async (_url, opts) => {
      capturedBody = JSON.parse((opts?.body as string) ?? '{}');
      return makeOk({ review_id: 'rev-ns', listing_id: LISTING_ID, user_id: 'u', text: 'nice' });
    });
    renderPage();
    setListingId(LISTING_ID);
    fireEvent.change(screen.getByTestId('review-text-input'), { target: { value: 'nice' } });
    // leave stars empty
    fireEvent.submit(screen.getByTestId('review-form'));
    await waitFor(() => expect(screen.getByTestId('review-result')).toBeInTheDocument());
    expect(capturedBody.stars).toBeUndefined();
  });
});
