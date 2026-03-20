/**
 * ReviewsPanel -- displays reviews for a marketplace listing, with reply support,
 * issue reporting, and rate-and-review form.
 *
 * Props:
 *   listingId: string -- the marketplace listing to show reviews for
 */
import React, { useState, useEffect, useCallback } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ReviewReply {
  reply_id: string;
  review_id: string;
  publisher_id: string;
  text: string;
  created_at: number;
}

interface Review {
  review_id: string;
  listing_id: string;
  user_id: string;
  text: string;
  stars: number | null;
  created_at: number;
  reply: ReviewReply | null;
}

interface ReviewsResponse {
  listing_id: string;
  items: Review[];
  total: number;
}

type IssueType = 'broken' | 'malware' | 'spam' | 'outdated' | 'other';

interface ReviewsPanelProps {
  listingId: string;
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

function renderStars(count: number): string {
  const clamped = Math.max(1, Math.min(5, count));
  return '\u2605'.repeat(clamped) + '\u2606'.repeat(5 - clamped);
}

function formatDate(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleDateString();
}

const ISSUE_TYPES: { value: IssueType; label: string }[] = [
  { value: 'broken', label: 'Broken / Not Working' },
  { value: 'malware', label: 'Malware / Security Issue' },
  { value: 'spam', label: 'Spam / Misleading' },
  { value: 'outdated', label: 'Outdated' },
  { value: 'other', label: 'Other' },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const ReviewsPanel: React.FC<ReviewsPanelProps> = ({ listingId }) => {
  const [reviews, setReviews] = useState<Review[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Report modal state
  const [reportModalOpen, setReportModalOpen] = useState(false);
  const [reportType, setReportType] = useState<IssueType>('broken');
  const [reportDescription, setReportDescription] = useState('');
  const [reportSubmitting, setReportSubmitting] = useState(false);

  // Rate & review form state
  const [reviewStars, setReviewStars] = useState(5);
  const [reviewText, setReviewText] = useState('');
  const [reviewSubmitting, setReviewSubmitting] = useState(false);

  const hasToken = getAuthToken() !== null;

  const fetchReviews = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<ReviewsResponse>(
        `/api/v1/marketplace/${listingId}/reviews`,
      );
      setReviews(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load reviews');
    } finally {
      setLoading(false);
    }
  }, [listingId]);

  useEffect(() => {
    fetchReviews();
  }, [fetchReviews]);

  const handleSubmitReport = async () => {
    setReportSubmitting(true);
    try {
      await apiFetch(`/api/v1/marketplace/${listingId}/report`, {
        method: 'POST',
        body: JSON.stringify({ type: reportType, description: reportDescription }),
      });
      setReportModalOpen(false);
      setReportDescription('');
    } catch {
      // Report error is non-critical; modal stays open for retry
    } finally {
      setReportSubmitting(false);
    }
  };

  const handleSubmitReview = async () => {
    if (!reviewText.trim()) return;
    setReviewSubmitting(true);
    try {
      // Submit rating
      await apiFetch(`/api/v1/marketplace/${listingId}/rate`, {
        method: 'POST',
        body: JSON.stringify({ stars: reviewStars }),
      });
      // Submit review text
      await apiFetch(`/api/v1/marketplace/${listingId}/review`, {
        method: 'POST',
        body: JSON.stringify({ text: reviewText, stars: reviewStars }),
      });
      setReviewText('');
      setReviewStars(5);
      await fetchReviews();
    } catch {
      // Submission error; form stays populated for retry
    } finally {
      setReviewSubmitting(false);
    }
  };

  // --- Loading state ---
  if (loading) {
    return (
      <div className="p-4" data-testid="reviews-loading">
        <p className="text-gray-500">Loading reviews...</p>
      </div>
    );
  }

  // --- Error state ---
  if (error) {
    return (
      <div className="p-4" data-testid="reviews-error">
        <p className="text-red-500">{error}</p>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-6" data-testid="reviews-panel">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-900">
          Reviews ({reviews.length})
        </h3>
        <button
          className="px-3 py-1.5 text-sm border border-red-300 text-red-600 rounded hover:bg-red-50"
          onClick={() => setReportModalOpen(true)}
          data-testid="report-issue-btn"
        >
          Report Issue
        </button>
      </div>

      {/* Reviews list */}
      {reviews.length === 0 ? (
        <p className="text-gray-400" data-testid="reviews-empty">
          No reviews yet. Be the first to review!
        </p>
      ) : (
        <div className="space-y-4" data-testid="reviews-list">
          {reviews.map((review) => (
            <div
              key={review.review_id}
              className="border border-gray-200 rounded-lg p-4"
              data-testid="review-item"
            >
              <div className="flex items-center gap-2 mb-1">
                {review.stars !== null && (
                  <span className="text-yellow-500 text-sm" data-testid="review-stars">
                    {renderStars(review.stars)}
                  </span>
                )}
                <span className="text-xs text-gray-400">
                  {formatDate(review.created_at)}
                </span>
              </div>
              <p className="text-gray-800 text-sm">{review.text}</p>
              <p className="text-xs text-gray-400 mt-1">by {review.user_id}</p>

              {review.reply && (
                <div
                  className="mt-3 ml-4 pl-3 border-l-2 border-blue-200 bg-blue-50 rounded p-2"
                  data-testid="review-reply"
                >
                  <p className="text-xs text-blue-600 font-medium mb-1">Publisher reply</p>
                  <p className="text-sm text-gray-700">{review.reply.text}</p>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Rate & Review form (only if authenticated) */}
      {hasToken && (
        <div className="border-t pt-4" data-testid="review-form">
          <h4 className="text-sm font-semibold text-gray-700 mb-2">Rate & Review</h4>
          <div className="flex items-center gap-1 mb-2">
            {[1, 2, 3, 4, 5].map((star) => (
              <button
                key={star}
                className={`text-xl ${star <= reviewStars ? 'text-yellow-500' : 'text-gray-300'}`}
                onClick={() => setReviewStars(star)}
                aria-label={`Rate ${star} star${star > 1 ? 's' : ''}`}
                data-testid={`star-${star}`}
              >
                {'\u2605'}
              </button>
            ))}
          </div>
          <textarea
            className="w-full border border-gray-300 rounded p-2 text-sm"
            rows={3}
            placeholder="Write your review..."
            value={reviewText}
            onChange={(e) => setReviewText(e.target.value)}
            data-testid="review-text-input"
          />
          <button
            className="mt-2 px-4 py-2 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 disabled:opacity-50"
            onClick={handleSubmitReview}
            disabled={reviewSubmitting || !reviewText.trim()}
            data-testid="submit-review-btn"
          >
            {reviewSubmitting ? 'Submitting...' : 'Submit Review'}
          </button>
        </div>
      )}

      {/* Report Issue Modal */}
      {reportModalOpen && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          data-testid="report-modal"
        >
          <div className="bg-white rounded-lg p-6 w-full max-w-md">
            <h4 className="text-lg font-semibold mb-4">Report Issue</h4>

            <label className="block text-sm font-medium text-gray-700 mb-1">
              Issue Type
            </label>
            <select
              className="w-full border border-gray-300 rounded p-2 text-sm mb-3"
              value={reportType}
              onChange={(e) => setReportType(e.target.value as IssueType)}
              data-testid="report-type-select"
            >
              {ISSUE_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>

            <label className="block text-sm font-medium text-gray-700 mb-1">
              Description
            </label>
            <textarea
              className="w-full border border-gray-300 rounded p-2 text-sm mb-4"
              rows={3}
              maxLength={1000}
              placeholder="Describe the issue..."
              value={reportDescription}
              onChange={(e) => setReportDescription(e.target.value)}
              data-testid="report-description-input"
            />

            <div className="flex justify-end gap-2">
              <button
                className="px-3 py-1.5 text-sm border border-gray-300 rounded hover:bg-gray-50"
                onClick={() => setReportModalOpen(false)}
              >
                Cancel
              </button>
              <button
                className="px-3 py-1.5 text-sm bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
                onClick={handleSubmitReport}
                disabled={reportSubmitting || !reportDescription.trim()}
                data-testid="submit-report-btn"
              >
                {reportSubmitting ? 'Submitting...' : 'Submit Report'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ReviewsPanel;
