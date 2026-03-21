/**
 * Unit tests for QuotaManagerPage (N-87).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import QuotaManagerPage from './QuotaManagerPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const QUOTAS_LIST = [
  { key_id: 'key-abc', requests_this_month: 450, monthly_limit: 1000, pct_consumed: 45 },
  { key_id: 'key-xyz', requests_this_month: 920, monthly_limit: 1000, pct_consumed: 92 },
  { key_id: 'key-unlimited', requests_this_month: 10 },
];

const QUOTAS_EMPTY: never[] = [];

const QUOTA_OBJ_RESPONSE = {
  'key-abc': { requests_this_month: 450, monthly_limit: 1000, pct_consumed: 45 },
};

function renderPage() {
  return render(
    <MemoryRouter>
      <QuotaManagerPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('QuotaManagerPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => QUOTAS_EMPTY } as Response);
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
  });

  it('shows quota rows in table', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => QUOTAS_LIST } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('quotas-table')).toBeInTheDocument());
    const rows = screen.getAllByTestId('quota-row');
    expect(rows).toHaveLength(3);
    expect(screen.getByText('key-abc')).toBeInTheDocument();
    expect(screen.getByText('key-xyz')).toBeInTheDocument();
  });

  it('shows no-quotas when empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => QUOTAS_EMPTY } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('no-quotas')).toBeInTheDocument());
  });

  it('shows error on fetch failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 500 } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('quotas-error')).toBeInTheDocument());
  });

  it('handles object response shape from backend', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => QUOTA_OBJ_RESPONSE,
    } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('quotas-table')).toBeInTheDocument());
    expect(screen.getByText('key-abc')).toBeInTheDocument();
  });

  it('shows usage bars for entries with pct_consumed', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => QUOTAS_LIST } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('quotas-table'));
    const bars = screen.getAllByTestId('usage-bar');
    expect(bars.length).toBeGreaterThanOrEqual(2);
  });

  it('red bar for >=90% usage', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => QUOTAS_LIST } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('quotas-table'));
    const bars = screen.getAllByTestId('usage-bar');
    // key-xyz has pct_consumed=92 → red
    const redBar = bars.find((b) => b.className.includes('bg-red-600'));
    expect(redBar).toBeTruthy();
  });

  it('clicking Set Limit shows inline input with current value', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => QUOTAS_LIST } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('quotas-table'));
    fireEvent.click(screen.getAllByTestId('edit-btn')[0]);
    expect(screen.getByTestId('limit-input')).toBeInTheDocument();
    expect((screen.getByTestId('limit-input') as HTMLInputElement).value).toBe('1000');
  });

  it('cancel returns to edit-btn state', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => QUOTAS_LIST } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('quotas-table'));
    fireEvent.click(screen.getAllByTestId('edit-btn')[0]);
    expect(screen.getByTestId('limit-input')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('cancel-btn'));
    expect(screen.queryByTestId('limit-input')).not.toBeInTheDocument();
  });

  it('save updates the row monthly_limit', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => QUOTAS_LIST } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({}) } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('quotas-table'));
    fireEvent.click(screen.getAllByTestId('edit-btn')[0]);
    fireEvent.change(screen.getByTestId('limit-input'), { target: { value: '2000' } });
    fireEvent.click(screen.getByTestId('save-btn'));
    await waitFor(() => expect(screen.queryByTestId('limit-input')).not.toBeInTheDocument());
    expect(screen.getByText('2,000')).toBeInTheDocument();
  });

  it('save with empty value sets unlimited', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => QUOTAS_LIST } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({}) } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('quotas-table'));
    fireEvent.click(screen.getAllByTestId('edit-btn')[0]);
    fireEvent.change(screen.getByTestId('limit-input'), { target: { value: '' } });
    fireEvent.click(screen.getByTestId('save-btn'));
    await waitFor(() => expect(screen.queryByTestId('limit-input')).not.toBeInTheDocument());
  });

  it('shows save-error on invalid limit value', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => QUOTAS_LIST } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('quotas-table'));
    fireEvent.click(screen.getAllByTestId('edit-btn')[0]);
    fireEvent.change(screen.getByTestId('limit-input'), { target: { value: '-5' } });
    fireEvent.click(screen.getByTestId('save-btn'));
    await waitFor(() => expect(screen.getByTestId('save-error')).toBeInTheDocument());
  });

  it('shows save-error on PUT failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => QUOTAS_LIST } as Response)
      .mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => ({ detail: 'Bad request' }),
      } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('quotas-table'));
    fireEvent.click(screen.getAllByTestId('edit-btn')[0]);
    fireEvent.change(screen.getByTestId('limit-input'), { target: { value: '500' } });
    fireEvent.click(screen.getByTestId('save-btn'));
    await waitFor(() => expect(screen.getByTestId('save-error')).toBeInTheDocument());
    expect(screen.getByTestId('save-error').textContent).toContain('Bad request');
  });

  it('refresh-btn reloads quotas', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => QUOTAS_LIST } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => QUOTAS_LIST } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('refresh-btn')).not.toBeDisabled());
    fireEvent.click(screen.getByTestId('refresh-btn'));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.length).toBeGreaterThanOrEqual(2));
  });
});
