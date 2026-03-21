/**
 * MarketplaceReviewsPage — Marketplace community engagement (N-101).
 *
 * Covers:
 *   POST /marketplace/{listing_id}/rate              → submit/update star rating
 *   POST /marketplace/{listing_id}/review            → submit text review (+ optional stars)
 *   GET  /marketplace/{listing_id}/reviews           → list reviews with embedded replies
 *   POST /marketplace/reviews/{review_id}/reply      → publisher reply to review
 *   POST /marketplace/{listing_id}/report            → report issue
 *
 * Route: /marketplace-reviews (ProtectedRoute)
 */
import React, { useCallback, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Reply {
  reply_id: string;
  review_id: string;
  publisher_id: string;
  text: string;
  created_at?: string | number;
  [key: string]: unknown;
}

interface Review {
  review_id: string;
  listing_id: string;
  user_id: string;
  text: string;
  stars?: number | null;
  created_at?: string | number;
  reply?: Reply | null;
  [key: string]: unknown;
}

interface RatingStats {
  listing_id: string;
  average?: number | null;
  count?: number;
  [key: string]: unknown;
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

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const REPORT_TYPES = ['broken', 'malware', 'spam', 'outdated', 'other'] as const;

const MarketplaceReviewsPage: React.FC = () => {
  const [listingId, setListingId] = useState('');

  // Rate
  const [rateStars, setRateStars] = useState('5');
  const [rating, setRating] = useState(false);
  const [rateError, setRateError] = useState<string | null>(null);
  const [rateResult, setRateResult] = useState<RatingStats | null>(null);

  // Review
  const [reviewText, setReviewText] = useState('');
  const [reviewStars, setReviewStars] = useState('');
  const [submittingReview, setSubmittingReview] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [reviewResult, setReviewResult] = useState<Review | null>(null);

  // List reviews
  const [loadingReviews, setLoadingReviews] = useState(false);
  const [reviewsError, setReviewsError] = useState<string | null>(null);
  const [reviews, setReviews] = useState<Review[] | null>(null);
  const [reviewsTotal, setReviewsTotal] = useState<number | null>(null);

  // Reply
  const [replyReviewId, setReplyReviewId] = useState('');
  const [replyText, setReplyText] = useState('');
  const [submittingReply, setSubmittingReply] = useState(false);
  const [replyError, setReplyError] = useState<string | null>(null);
  const [replyResult, setReplyResult] = useState<Reply | null>(null);

  // Report
  const [reportType, setReportType] = useState<string>('broken');
  const [reportDescription, setReportDescription] = useState('');
  const [submittingReport, setSubmittingReport] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);
  const [reportResult, setReportResult] = useState<Record<string, unknown> | null>(null);

  // ---------------------------------------------------------------------------
  // Rate
  // ---------------------------------------------------------------------------

  const handleRate = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!listingId.trim()) return;
      setRating(true);
      setRateError(null);
      setRateResult(null);
      try {
        const resp = await fetch(
          `${getBaseUrl()}/marketplace/${encodeURIComponent(listingId.trim())}/rate`,
          {
            method: 'POST',
            headers: { ...authHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify({ stars: Number(rateStars) }),
          },
        );
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          setRateError(err.detail ?? `Error ${resp.status}`);
          return;
        }
        setRateResult(await resp.json());
      } catch {
        setRateError('Network error submitting rating');
      } finally {
        setRating(false);
      }
    },
    [listingId, rateStars],
  );

  // ---------------------------------------------------------------------------
  // Submit review
  // ---------------------------------------------------------------------------

  const handleReview = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!listingId.trim() || !reviewText.trim()) return;
      setSubmittingReview(true);
      setReviewError(null);
      setReviewResult(null);
      try {
        const body: Record<string, unknown> = { text: reviewText.trim() };
        if (reviewStars.trim()) body.stars = Number(reviewStars);
        const resp = await fetch(
          `${getBaseUrl()}/marketplace/${encodeURIComponent(listingId.trim())}/review`,
          {
            method: 'POST',
            headers: { ...authHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          },
        );
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          setReviewError(err.detail ?? `Error ${resp.status}`);
          return;
        }
        const created: Review = await resp.json();
        setReviewResult(created);
        setReviewText('');
        setReviewStars('');
      } catch {
        setReviewError('Network error submitting review');
      } finally {
        setSubmittingReview(false);
      }
    },
    [listingId, reviewText, reviewStars],
  );

  // ---------------------------------------------------------------------------
  // List reviews
  // ---------------------------------------------------------------------------

  const handleLoadReviews = useCallback(async () => {
    if (!listingId.trim()) return;
    setLoadingReviews(true);
    setReviewsError(null);
    setReviews(null);
    setReviewsTotal(null);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/marketplace/${encodeURIComponent(listingId.trim())}/reviews`,
      );
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        setReviewsError(err.detail ?? `Error ${resp.status}`);
        return;
      }
      const data = await resp.json();
      const items: Review[] = Array.isArray(data) ? data : Array.isArray(data.items) ? data.items : [];
      setReviews(items);
      setReviewsTotal(typeof data.total === 'number' ? data.total : items.length);
    } catch {
      setReviewsError('Network error loading reviews');
    } finally {
      setLoadingReviews(false);
    }
  }, [listingId]);

  // ---------------------------------------------------------------------------
  // Reply
  // ---------------------------------------------------------------------------

  const handleReply = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!replyReviewId.trim() || !replyText.trim()) return;
      setSubmittingReply(true);
      setReplyError(null);
      setReplyResult(null);
      try {
        const resp = await fetch(
          `${getBaseUrl()}/marketplace/reviews/${encodeURIComponent(replyReviewId.trim())}/reply`,
          {
            method: 'POST',
            headers: { ...authHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: replyText.trim() }),
          },
        );
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          setReplyError(err.detail ?? `Error ${resp.status}`);
          return;
        }
        setReplyResult(await resp.json());
        setReplyText('');
      } catch {
        setReplyError('Network error submitting reply');
      } finally {
        setSubmittingReply(false);
      }
    },
    [replyReviewId, replyText],
  );

  // ---------------------------------------------------------------------------
  // Report
  // ---------------------------------------------------------------------------

  const handleReport = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!listingId.trim() || !reportDescription.trim()) return;
      setSubmittingReport(true);
      setReportError(null);
      setReportResult(null);
      try {
        const resp = await fetch(
          `${getBaseUrl()}/marketplace/${encodeURIComponent(listingId.trim())}/report`,
          {
            method: 'POST',
            headers: { ...authHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify({ type: reportType, description: reportDescription.trim() }),
          },
        );
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          setReportError(err.detail ?? `Error ${resp.status}`);
          return;
        }
        setReportResult(await resp.json());
        setReportDescription('');
      } catch {
        setReportError('Network error submitting report');
      } finally {
        setSubmittingReport(false);
      }
    },
    [listingId, reportType, reportDescription],
  );

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <MainLayout title="Marketplace Reviews">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
          Marketplace Reviews & Ratings
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Rate listings, submit reviews, reply to feedback, and report issues.
        </p>
      </div>

      {/* Shared listing ID input */}
      <div className="mb-6">
        <label className="block mb-1 text-xs text-slate-500">Listing ID</label>
        <input
          type="text"
          value={listingId}
          onChange={(e) => setListingId(e.target.value)}
          placeholder="marketplace listing ID"
          className="w-72 rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
          data-testid="listing-id-input"
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* ---- Rate ---- */}
        <section
          className="rounded border border-slate-700 bg-slate-800/30 p-4"
          data-testid="rate-section"
        >
          <h2 className="mb-3 text-sm font-semibold text-slate-300">Submit Rating</h2>
          <form onSubmit={handleRate} className="space-y-3" data-testid="rate-form">
            <div className="flex items-center gap-3">
              <label className="text-xs text-slate-500">Stars (1–5)</label>
              <input
                type="number"
                min={1}
                max={5}
                value={rateStars}
                onChange={(e) => setRateStars(e.target.value)}
                className="w-16 rounded border border-slate-600 bg-slate-900 px-2 py-1 text-sm text-slate-200 focus:outline-none"
                data-testid="rate-stars-input"
              />
            </div>
            <button
              type="submit"
              disabled={rating || !listingId.trim()}
              className="rounded bg-indigo-700 px-4 py-1.5 text-sm text-white hover:bg-indigo-600 disabled:opacity-50"
              data-testid="rate-btn"
            >
              {rating ? 'Submitting…' : 'Submit Rating'}
            </button>
          </form>
          {rateError && (
            <p className="mt-2 text-sm text-red-400" data-testid="rate-error">
              {rateError}
            </p>
          )}
          {rateResult && (
            <div
              className="mt-3 rounded border border-emerald-700/50 bg-emerald-900/20 p-3 text-xs"
              data-testid="rate-result"
            >
              <p className="font-semibold text-emerald-400">Rating submitted!</p>
              {rateResult.average != null && (
                <p className="mt-1 text-slate-300">
                  Average: <span data-testid="rate-average">{String(rateResult.average)}</span>
                  {' '}({rateResult.count} ratings)
                </p>
              )}
            </div>
          )}
        </section>

        {/* ---- Review ---- */}
        <section
          className="rounded border border-slate-700 bg-slate-800/30 p-4"
          data-testid="review-section"
        >
          <h2 className="mb-3 text-sm font-semibold text-slate-300">Submit Review</h2>
          <form onSubmit={handleReview} className="space-y-3" data-testid="review-form">
            <textarea
              value={reviewText}
              onChange={(e) => setReviewText(e.target.value)}
              placeholder="Write your review…"
              rows={3}
              className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:outline-none"
              data-testid="review-text-input"
            />
            <input
              type="number"
              min={1}
              max={5}
              value={reviewStars}
              onChange={(e) => setReviewStars(e.target.value)}
              placeholder="Stars (optional)"
              className="w-32 rounded border border-slate-600 bg-slate-900 px-2 py-1 text-sm text-slate-200 focus:outline-none"
              data-testid="review-stars-input"
            />
            <button
              type="submit"
              disabled={submittingReview || !listingId.trim() || !reviewText.trim()}
              className="rounded bg-indigo-700 px-4 py-1.5 text-sm text-white hover:bg-indigo-600 disabled:opacity-50"
              data-testid="review-btn"
            >
              {submittingReview ? 'Submitting…' : 'Submit Review'}
            </button>
          </form>
          {reviewError && (
            <p className="mt-2 text-sm text-red-400" data-testid="review-error">
              {reviewError}
            </p>
          )}
          {reviewResult && (
            <div
              className="mt-3 rounded border border-emerald-700/50 bg-emerald-900/20 p-3 text-xs"
              data-testid="review-result"
            >
              <p className="font-semibold text-emerald-400">Review submitted!</p>
              <p className="mt-1 text-slate-300">
                ID:{' '}
                <span className="font-mono" data-testid="review-id">
                  {reviewResult.review_id}
                </span>
              </p>
            </div>
          )}
        </section>

        {/* ---- List Reviews ---- */}
        <section
          className="rounded border border-slate-700 bg-slate-800/30 p-4 lg:col-span-2"
          data-testid="reviews-section"
        >
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-300">Reviews</h2>
            <button
              onClick={handleLoadReviews}
              disabled={loadingReviews || !listingId.trim()}
              className="rounded bg-slate-700 px-3 py-1 text-xs text-slate-300 hover:bg-slate-600 disabled:opacity-50"
              data-testid="load-reviews-btn"
            >
              {loadingReviews ? 'Loading…' : 'Load Reviews'}
            </button>
          </div>
          {reviewsError && (
            <p className="text-sm text-red-400" data-testid="reviews-error">
              {reviewsError}
            </p>
          )}
          {loadingReviews && !reviews && (
            <p className="text-xs text-slate-500" data-testid="reviews-loading">Loading…</p>
          )}
          {reviews !== null && reviews.length === 0 && (
            <p className="text-xs text-slate-500" data-testid="no-reviews">No reviews yet.</p>
          )}
          {reviews !== null && reviews.length > 0 && (
            <div data-testid="reviews-list">
              <p className="mb-2 text-xs text-slate-500">
                Total: <span data-testid="reviews-total">{reviewsTotal}</span>
              </p>
              {reviews.map((r) => (
                <div
                  key={r.review_id}
                  className="mb-3 rounded border border-slate-700/50 bg-slate-900/40 p-3 text-xs"
                  data-testid="review-item"
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="font-mono text-slate-500">{r.review_id}</span>
                    {r.stars != null && (
                      <span className="text-yellow-400" data-testid="review-stars">
                        {'★'.repeat(r.stars)}
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-slate-300" data-testid="review-text">{r.text}</p>
                  {r.reply && (
                    <div
                      className="mt-2 rounded border border-slate-600/40 bg-slate-800/60 p-2"
                      data-testid="review-reply"
                    >
                      <p className="text-xs font-semibold text-indigo-400">Publisher reply:</p>
                      <p className="mt-0.5 text-slate-300">{r.reply.text}</p>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>

        {/* ---- Reply to review ---- */}
        <section
          className="rounded border border-slate-700 bg-slate-800/30 p-4"
          data-testid="reply-section"
        >
          <h2 className="mb-3 text-sm font-semibold text-slate-300">Reply to Review</h2>
          <form onSubmit={handleReply} className="space-y-3" data-testid="reply-form">
            <input
              type="text"
              value={replyReviewId}
              onChange={(e) => setReplyReviewId(e.target.value)}
              placeholder="Review ID"
              className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
              data-testid="reply-review-id-input"
            />
            <textarea
              value={replyText}
              onChange={(e) => setReplyText(e.target.value)}
              placeholder="Your reply…"
              rows={3}
              className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:outline-none"
              data-testid="reply-text-input"
            />
            <button
              type="submit"
              disabled={submittingReply || !replyReviewId.trim() || !replyText.trim()}
              className="rounded bg-indigo-700 px-4 py-1.5 text-sm text-white hover:bg-indigo-600 disabled:opacity-50"
              data-testid="reply-btn"
            >
              {submittingReply ? 'Submitting…' : 'Submit Reply'}
            </button>
          </form>
          {replyError && (
            <p className="mt-2 text-sm text-red-400" data-testid="reply-error">
              {replyError}
            </p>
          )}
          {replyResult && (
            <div
              className="mt-3 rounded border border-emerald-700/50 bg-emerald-900/20 p-3 text-xs"
              data-testid="reply-result"
            >
              <p className="font-semibold text-emerald-400">Reply submitted!</p>
              <p className="mt-1 font-mono text-slate-300" data-testid="reply-id">
                {replyResult.reply_id}
              </p>
            </div>
          )}
        </section>

        {/* ---- Report ---- */}
        <section
          className="rounded border border-slate-700 bg-slate-800/30 p-4"
          data-testid="report-section"
        >
          <h2 className="mb-3 text-sm font-semibold text-slate-300">Report Issue</h2>
          <form onSubmit={handleReport} className="space-y-3" data-testid="report-form">
            <select
              value={reportType}
              onChange={(e) => setReportType(e.target.value)}
              className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
              data-testid="report-type-select"
            >
              {REPORT_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <textarea
              value={reportDescription}
              onChange={(e) => setReportDescription(e.target.value)}
              placeholder="Describe the issue…"
              rows={3}
              className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:outline-none"
              data-testid="report-description-input"
            />
            <button
              type="submit"
              disabled={submittingReport || !listingId.trim() || !reportDescription.trim()}
              className="rounded bg-red-900/60 px-4 py-1.5 text-sm text-red-300 hover:bg-red-900 disabled:opacity-50"
              data-testid="report-btn"
            >
              {submittingReport ? 'Submitting…' : 'Submit Report'}
            </button>
          </form>
          {reportError && (
            <p className="mt-2 text-sm text-red-400" data-testid="report-error">
              {reportError}
            </p>
          )}
          {reportResult && (
            <div
              className="mt-3 rounded border border-emerald-700/50 bg-emerald-900/20 p-3 text-xs"
              data-testid="report-result"
            >
              <p className="font-semibold text-emerald-400">Report submitted!</p>
              {reportResult.issue_id != null && (
                <p className="mt-1 font-mono text-slate-300" data-testid="report-id">
                  {String(reportResult.issue_id)}
                </p>
              )}
            </div>
          )}
        </section>
      </div>
    </MainLayout>
  );
};

export default MarketplaceReviewsPage;
