/**
 * CreditsPage -- Marketplace publisher credits dashboard.
 *
 * Shows:
 *   - Balance card with big number
 *   - "Request Payout" button -> modal with amount input
 *   - Ledger table: date, type, amount, listing name, note
 *   - Per-listing breakdown: listing name, installs, credits earned
 *
 * Route: /publisher/credits (ProtectedRoute)
 */
import React, { useCallback, useEffect, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CreditsSummary {
  balance: number;
  total_earned: number;
  total_paid_out: number;
  entry_count: number;
}

interface LedgerEntry {
  entry_id: string;
  publisher_id: string;
  type: 'credit' | 'debit';
  amount: number;
  listing_id: string | null;
  listing_name: string | null;
  note: string;
  created_at: number;
}

interface LedgerResponse {
  entries: LedgerEntry[];
  balance: number;
}

interface PerListingItem {
  listing_id: string;
  listing_name: string;
  installs: number;
  credits_earned: number;
}

interface PayoutReport {
  balance: number;
  total_earned: number;
  total_paid_out: number;
  entry_count: number;
  per_listing: PerListingItem[];
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

function formatDate(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface PayoutModalProps {
  balance: number;
  onClose: () => void;
  onSubmit: (amount: number) => Promise<void>;
}

const PayoutModal: React.FC<PayoutModalProps> = ({ balance, onClose, onSubmit }) => {
  const [amount, setAmount] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async () => {
    const parsed = parseInt(amount, 10);
    if (isNaN(parsed) || parsed < 1) {
      setError('Please enter a valid amount (minimum 1)');
      return;
    }
    if (parsed > balance) {
      setError('Amount exceeds available balance');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      await onSubmit(parsed);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Payout failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" role="dialog" aria-label="Request Payout">
      <div className="w-full max-w-md rounded-lg bg-slate-800 p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-semibold text-white">Request Payout</h2>
        <p className="mb-2 text-sm text-slate-400">Available balance: {balance} credits</p>
        <input
          type="number"
          min={1}
          max={balance}
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          placeholder="Enter amount"
          aria-label="Payout amount"
          className="mb-3 w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white placeholder-slate-400 focus:border-blue-500 focus:outline-none"
        />
        {error && <p className="mb-3 text-sm text-red-400">{error}</p>}
        <div className="flex justify-end gap-3">
          <button
            onClick={onClose}
            className="rounded px-4 py-2 text-sm text-slate-300 hover:text-white"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
          >
            {submitting ? 'Processing...' : 'Submit Payout'}
          </button>
        </div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

const CreditsPage: React.FC = () => {
  const [summary, setSummary] = useState<CreditsSummary | null>(null);
  const [ledger, setLedger] = useState<LedgerEntry[]>([]);
  const [report, setReport] = useState<PayoutReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showPayoutModal, setShowPayoutModal] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [summaryData, ledgerData, reportData] = await Promise.all([
        apiFetch<CreditsSummary>('/api/v1/marketplace/publisher/credits'),
        apiFetch<LedgerResponse>('/api/v1/marketplace/publisher/credits/ledger'),
        apiFetch<PayoutReport>('/api/v1/marketplace/publisher/credits/payout-report'),
      ]);
      setSummary(summaryData);
      setLedger(ledgerData.entries);
      setReport(reportData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load credits data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handlePayout = async (amount: number) => {
    await apiFetch('/api/v1/marketplace/publisher/credits/payout', {
      method: 'POST',
      body: JSON.stringify({ amount }),
    });
    await loadData();
  };

  // Loading state
  if (loading) {
    return (
      <MainLayout title="Credits">
        <div className="flex min-h-[40vh] items-center justify-center" aria-label="Loading credits">
          <p className="text-slate-400">Loading credits...</p>
        </div>
      </MainLayout>
    );
  }

  // Error state
  if (error) {
    return (
      <MainLayout title="Credits">
        <div role="alert" className="mx-auto mt-8 max-w-lg rounded-lg border border-red-800 bg-red-900/30 p-6 text-center">
          <p className="text-red-300">Error loading credits: {error}</p>
          <button
            onClick={loadData}
            className="mt-4 rounded bg-red-700 px-4 py-2 text-sm text-white hover:bg-red-600"
          >
            Retry
          </button>
        </div>
      </MainLayout>
    );
  }

  return (
    <MainLayout title="Credits">
      <div className="mx-auto max-w-5xl space-y-6 px-4 py-6">
        {/* Balance card */}
        <div className="rounded-lg border border-slate-700 bg-slate-800 p-6">
          <p className="text-sm font-medium uppercase tracking-wider text-slate-400">Credit Balance</p>
          <p className="mt-2 text-4xl font-bold text-white" data-testid="balance-value">
            {summary?.balance ?? 0}
          </p>
          <div className="mt-4 flex gap-6 text-sm text-slate-400">
            <span>Total earned: {summary?.total_earned ?? 0}</span>
            <span>Total paid out: {summary?.total_paid_out ?? 0}</span>
          </div>
          <button
            onClick={() => setShowPayoutModal(true)}
            className="mt-4 rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500"
          >
            Request Payout
          </button>
        </div>

        {/* Per-listing breakdown */}
        {report && report.per_listing.length > 0 && (
          <div className="rounded-lg border border-slate-700 bg-slate-800 p-6">
            <h2 className="mb-4 text-lg font-semibold text-white">Per-Listing Breakdown</h2>
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-700 text-slate-400">
                  <th className="pb-2">Listing</th>
                  <th className="pb-2">Installs</th>
                  <th className="pb-2">Credits Earned</th>
                </tr>
              </thead>
              <tbody>
                {report.per_listing.map((item) => (
                  <tr key={item.listing_id} className="border-b border-slate-700/50">
                    <td className="py-2 text-white">{item.listing_name}</td>
                    <td className="py-2 text-slate-300">{item.installs}</td>
                    <td className="py-2 text-slate-300">{item.credits_earned}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Ledger table */}
        <div className="rounded-lg border border-slate-700 bg-slate-800 p-6">
          <h2 className="mb-4 text-lg font-semibold text-white">Transaction History</h2>
          {ledger.length === 0 ? (
            <p className="text-slate-400">No transactions yet.</p>
          ) : (
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-700 text-slate-400">
                  <th className="pb-2">Date</th>
                  <th className="pb-2">Type</th>
                  <th className="pb-2">Amount</th>
                  <th className="pb-2">Listing</th>
                  <th className="pb-2">Note</th>
                </tr>
              </thead>
              <tbody>
                {ledger.map((entry) => (
                  <tr key={entry.entry_id} className="border-b border-slate-700/50">
                    <td className="py-2 text-slate-300">{formatDate(entry.created_at)}</td>
                    <td className="py-2">
                      <span
                        className={
                          entry.type === 'credit'
                            ? 'rounded bg-green-900/50 px-2 py-0.5 text-green-300'
                            : 'rounded bg-red-900/50 px-2 py-0.5 text-red-300'
                        }
                      >
                        {entry.type}
                      </span>
                    </td>
                    <td className="py-2 text-white">{entry.type === 'credit' ? '+' : '-'}{entry.amount}</td>
                    <td className="py-2 text-slate-300">{entry.listing_name ?? '-'}</td>
                    <td className="py-2 text-slate-400">{entry.note || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Payout modal */}
      {showPayoutModal && summary && (
        <PayoutModal
          balance={summary.balance}
          onClose={() => setShowPayoutModal(false)}
          onSubmit={handlePayout}
        />
      )}
    </MainLayout>
  );
};

export default CreditsPage;
