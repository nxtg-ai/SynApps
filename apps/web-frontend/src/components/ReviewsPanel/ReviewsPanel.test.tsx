/**
 * ReviewsPanel unit tests
 *
 * Covers: loading state, renders reviews, shows reply if present, report button
 * opens modal, submit report calls API, rate & review form submits, empty state,
 * error state.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import ReviewsPanel from './ReviewsPanel';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockFetch = vi.fn();
(globalThis as Record<string, unknown>).fetch = mockFetch;

function makeReview(overrides: Partial<{
  review_id: string;
  listing_id: string;
  user_id: string;
  text: string;
  stars: number | null;
  created_at: number;
  reply: { reply_id: string; review_id: string; publisher_id: string; text: string; created_at: number } | null;
}> = {}) {
  return {
    review_id: overrides.review_id ?? 'rev-1',
    listing_id: overrides.listing_id ?? 'listing-1',
    user_id: overrides.user_id ?? 'user-1',
    text: overrides.text ?? 'Great workflow!',
    stars: overrides.stars ?? 4,
    created_at: overrides.created_at ?? 1700000000,
    reply: overrides.reply ?? null,
  };
}

function mockReviewsResponse(reviews: ReturnType<typeof makeReview>[]) {
  return {
    ok: true,
    status: 200,
    json: async () => ({
      listing_id: 'listing-1',
      items: reviews,
      total: reviews.length,
    }),
    text: async () => '',
  };
}

function mockErrorResponse(status = 500) {
  return {
    ok: false,
    status,
    json: async () => ({ detail: 'Server error' }),
    text: async () => 'Server error',
  };
}

function mockOkResponse(data: unknown = {}) {
  return {
    ok: true,
    status: 200,
    json: async () => data,
    text: async () => '',
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  // Clear localStorage to reset auth state
  window.localStorage.clear();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ReviewsPanel', () => {
  it('shows loading state initially', () => {
    // Never resolve fetch so component stays in loading
    mockFetch.mockReturnValue(new Promise(() => {}));
    render(<ReviewsPanel listingId="listing-1" />);
    expect(screen.getByTestId('reviews-loading')).toBeInTheDocument();
  });

  it('renders reviews after loading', async () => {
    const reviews = [
      makeReview({ review_id: 'r1', text: 'Excellent work!' }),
      makeReview({ review_id: 'r2', text: 'Needs improvement', stars: 2 }),
    ];
    mockFetch.mockResolvedValueOnce(mockReviewsResponse(reviews));

    render(<ReviewsPanel listingId="listing-1" />);

    await waitFor(() => {
      expect(screen.getByTestId('reviews-list')).toBeInTheDocument();
    });

    const items = screen.getAllByTestId('review-item');
    expect(items.length).toBe(2);
    expect(screen.getByText('Excellent work!')).toBeInTheDocument();
    expect(screen.getByText('Needs improvement')).toBeInTheDocument();
  });

  it('shows reply on review when present', async () => {
    const reviews = [
      makeReview({
        review_id: 'r1',
        text: 'Great!',
        reply: {
          reply_id: 'rp1',
          review_id: 'r1',
          publisher_id: 'pub-1',
          text: 'Thank you for your feedback!',
          created_at: 1700001000,
        },
      }),
    ];
    mockFetch.mockResolvedValueOnce(mockReviewsResponse(reviews));

    render(<ReviewsPanel listingId="listing-1" />);

    await waitFor(() => {
      expect(screen.getByTestId('review-reply')).toBeInTheDocument();
    });
    expect(screen.getByText('Thank you for your feedback!')).toBeInTheDocument();
  });

  it('report button opens modal', async () => {
    mockFetch.mockResolvedValueOnce(mockReviewsResponse([]));

    render(<ReviewsPanel listingId="listing-1" />);

    await waitFor(() => {
      expect(screen.getByTestId('report-issue-btn')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('report-issue-btn'));
    expect(screen.getByTestId('report-modal')).toBeInTheDocument();
  });

  it('submit report calls API with correct payload', async () => {
    window.localStorage.setItem('access_token', 'test-token');
    mockFetch.mockResolvedValueOnce(mockReviewsResponse([]));

    render(<ReviewsPanel listingId="listing-1" />);

    await waitFor(() => {
      expect(screen.getByTestId('report-issue-btn')).toBeInTheDocument();
    });

    // Open modal
    fireEvent.click(screen.getByTestId('report-issue-btn'));

    // Fill form
    fireEvent.change(screen.getByTestId('report-type-select'), {
      target: { value: 'spam' },
    });
    fireEvent.change(screen.getByTestId('report-description-input'), {
      target: { value: 'This is spam' },
    });

    // Submit
    mockFetch.mockResolvedValueOnce(mockOkResponse({ issue_id: 'iss-1' }));
    fireEvent.click(screen.getByTestId('submit-report-btn'));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/marketplace/listing-1/report'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ type: 'spam', description: 'This is spam' }),
        }),
      );
    });
  });

  it('rate & review form submits when authenticated', async () => {
    window.localStorage.setItem('access_token', 'test-token');
    mockFetch.mockResolvedValueOnce(mockReviewsResponse([]));

    render(<ReviewsPanel listingId="listing-1" />);

    await waitFor(() => {
      expect(screen.getByTestId('review-form')).toBeInTheDocument();
    });

    // Select 3 stars
    fireEvent.click(screen.getByTestId('star-3'));

    // Type review
    fireEvent.change(screen.getByTestId('review-text-input'), {
      target: { value: 'Pretty good workflow' },
    });

    // Mock rate + review + re-fetch
    mockFetch
      .mockResolvedValueOnce(mockOkResponse({ avg_rating: 3.0, rating_count: 1 }))
      .mockResolvedValueOnce(mockOkResponse({ review_id: 'new-rev' }))
      .mockResolvedValueOnce(mockReviewsResponse([makeReview({ text: 'Pretty good workflow' })]));

    fireEvent.click(screen.getByTestId('submit-review-btn'));

    await waitFor(() => {
      // Rate endpoint called
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/marketplace/listing-1/rate'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ stars: 3 }),
        }),
      );
    });
  });

  it('shows empty state when no reviews exist', async () => {
    mockFetch.mockResolvedValueOnce(mockReviewsResponse([]));

    render(<ReviewsPanel listingId="listing-1" />);

    await waitFor(() => {
      expect(screen.getByTestId('reviews-empty')).toBeInTheDocument();
    });
    expect(screen.getByText(/No reviews yet/)).toBeInTheDocument();
  });

  it('shows error state when fetch fails', async () => {
    mockFetch.mockResolvedValueOnce(mockErrorResponse(500));

    render(<ReviewsPanel listingId="listing-1" />);

    await waitFor(() => {
      expect(screen.getByTestId('reviews-error')).toBeInTheDocument();
    });
  });
});
