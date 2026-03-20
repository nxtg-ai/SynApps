/**
 * Tests for CreditsPage -- N-47 marketplace revenue.
 *
 * Covers: loading state, balance display, ledger entries, empty ledger,
 * payout modal, payout success, error state, per-listing section.
 */
import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, afterEach } from 'vitest';
import CreditsPage from './CreditsPage';

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

function makeSummary(overrides: Partial<{ balance: number; total_earned: number; total_paid_out: number; entry_count: number }> = {}) {
  return {
    balance: 100,
    total_earned: 150,
    total_paid_out: 50,
    entry_count: 5,
    ...overrides,
  };
}

function makeLedger(entries: Array<Partial<{
  entry_id: string;
  publisher_id: string;
  type: string;
  amount: number;
  listing_id: string | null;
  listing_name: string | null;
  note: string;
  created_at: number;
}>> = []) {
  return {
    entries: entries.map((e, i) => ({
      entry_id: `e-${i}`,
      publisher_id: 'pub1',
      type: 'credit',
      amount: 10,
      listing_id: 'list-1',
      listing_name: 'Template A',
      note: '',
      created_at: Date.now() / 1000,
      ...e,
    })),
    balance: 100,
  };
}

function makeReport(perListing: Array<Partial<{
  listing_id: string;
  listing_name: string;
  installs: number;
  credits_earned: number;
}>> = []) {
  return {
    balance: 100,
    total_earned: 150,
    total_paid_out: 50,
    entry_count: 5,
    per_listing: perListing.map((p, i) => ({
      listing_id: `list-${i}`,
      listing_name: `Template ${i}`,
      installs: 5,
      credits_earned: 50,
      ...p,
    })),
  };
}

function mockAllFetches(
  summary = makeSummary(),
  ledger = makeLedger(),
  report = makeReport(),
) {
  let callIndex = 0;
  vi.spyOn(global, 'fetch').mockImplementation(() => {
    const responses = [
      new Response(JSON.stringify(summary), { status: 200 }),
      new Response(JSON.stringify(ledger), { status: 200 }),
      new Response(JSON.stringify(report), { status: 200 }),
    ];
    const resp = responses[callIndex] ?? responses[0];
    callIndex++;
    return Promise.resolve(resp);
  });
}

function renderPage() {
  return render(
    <MemoryRouter>
      <CreditsPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('CreditsPage', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders loading state initially', () => {
    // Make fetch never resolve so we stay in loading
    vi.spyOn(global, 'fetch').mockReturnValue(new Promise(() => {}));

    renderPage();

    expect(screen.getByLabelText('Loading credits')).toBeInTheDocument();
  });

  it('shows balance value', async () => {
    mockAllFetches(makeSummary({ balance: 250 }));

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('balance-value')).toHaveTextContent('250');
    });
  });

  it('shows ledger entries', async () => {
    mockAllFetches(
      makeSummary(),
      makeLedger([
        { listing_name: 'My Workflow', amount: 10, type: 'credit' },
        { listing_name: 'Other Flow', amount: 20, type: 'credit' },
      ]),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('My Workflow')).toBeInTheDocument();
      expect(screen.getByText('Other Flow')).toBeInTheDocument();
    });
  });

  it('shows empty ledger message', async () => {
    mockAllFetches(makeSummary(), makeLedger([]), makeReport());

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/No transactions yet/i)).toBeInTheDocument();
    });
  });

  it('opens payout modal on button click', async () => {
    mockAllFetches();

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Request Payout')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Request Payout'));

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
      expect(screen.getByLabelText('Payout amount')).toBeInTheDocument();
    });
  });

  it('handles successful payout', async () => {
    mockAllFetches();

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Request Payout')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Request Payout'));

    await waitFor(() => {
      expect(screen.getByLabelText('Payout amount')).toBeInTheDocument();
    });

    // Mock the payout POST + subsequent reload fetches
    vi.spyOn(global, 'fetch').mockImplementation(() => {
      return Promise.resolve(
        new Response(JSON.stringify({ balance: 70 }), { status: 200 }),
      );
    });

    fireEvent.change(screen.getByLabelText('Payout amount'), { target: { value: '30' } });
    fireEvent.click(screen.getByText('Submit Payout'));

    await waitFor(() => {
      // Modal should close after success
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });

  it('shows error state when API fails', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response('Internal Server Error', { status: 500 }),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.getByRole('alert').textContent).toMatch(/error/i);
    });
  });

  it('shows per-listing section', async () => {
    mockAllFetches(
      makeSummary(),
      makeLedger(),
      makeReport([
        { listing_name: 'Slack Bot', installs: 12, credits_earned: 120 },
        { listing_name: 'Email Flow', installs: 3, credits_earned: 30 },
      ]),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Per-Listing Breakdown')).toBeInTheDocument();
      expect(screen.getByText('Slack Bot')).toBeInTheDocument();
      expect(screen.getByText('Email Flow')).toBeInTheDocument();
    });
  });
});
