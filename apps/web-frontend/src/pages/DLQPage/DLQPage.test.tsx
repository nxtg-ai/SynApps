/**
 * Unit tests for DLQPage (N-77).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import DLQPage from './DLQPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const ENTRY_1 = {
  id: 'dlq-001',
  run_id: 'run-abc-123456',
  flow_id: 'flow-abc',
  error: 'LLM API timeout after 30s',
  error_details: { node_id: 'llm-1', timeout: 30 },
  failed_at: '2024-01-15T10:30:00Z',
  replay_count: 0,
  input_data: { prompt: 'hello world' },
};

const ENTRY_2 = {
  id: 'dlq-002',
  run_id: 'run-xyz-654321',
  flow_id: 'flow-xyz',
  error: 'HTTP 503 from downstream API',
  error_details: null,
  failed_at: '2024-01-15T11:00:00Z',
  replay_count: 2,
  input_data: { url: 'https://api.example.com' },
};

const LIST_TWO = { items: [ENTRY_1, ENTRY_2], total: 2 };
const LIST_EMPTY = { items: [], total: 0 };

function renderPage() {
  return render(
    <MemoryRouter>
      <DLQPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('DLQPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title and filter form', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => LIST_EMPTY } as Response);
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
    expect(screen.getByTestId('filter-form')).toBeInTheDocument();
  });

  it('shows empty state when queue is empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => LIST_EMPTY } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('empty-state')).toBeInTheDocument());
    expect(screen.getByTestId('total-count')).toHaveTextContent('0 entries');
  });

  it('renders DLQ entries', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => LIST_TWO } as Response);
    renderPage();
    await waitFor(() => expect(screen.getAllByTestId('dlq-row')).toHaveLength(2));
    expect(screen.getByText('LLM API timeout after 30s')).toBeInTheDocument();
    expect(screen.getByText('HTTP 503 from downstream API')).toBeInTheDocument();
  });

  it('shows replay count for replayed entries', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => LIST_TWO } as Response);
    renderPage();
    await waitFor(() => screen.getAllByTestId('dlq-row'));
    expect(screen.getByText(/replayed 2×/)).toBeInTheDocument();
  });

  it('shows dlq-error on load failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 500 } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('dlq-error')).toBeInTheDocument());
  });

  it('expands entry details on expand-btn click', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => LIST_TWO } as Response);
    renderPage();
    await waitFor(() => screen.getAllByTestId('expand-btn'));
    fireEvent.click(screen.getAllByTestId('expand-btn')[0]);
    expect(screen.getByTestId('dlq-details')).toBeInTheDocument();
    expect(screen.getByTestId('entry-input')).toBeInTheDocument();
  });

  it('shows error-details when present', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => LIST_TWO } as Response);
    renderPage();
    await waitFor(() => screen.getAllByTestId('expand-btn'));
    fireEvent.click(screen.getAllByTestId('expand-btn')[0]);
    expect(screen.getByTestId('error-details')).toBeInTheDocument();
  });

  it('collapses entry on second expand-btn click', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => LIST_TWO } as Response);
    renderPage();
    await waitFor(() => screen.getAllByTestId('expand-btn'));
    fireEvent.click(screen.getAllByTestId('expand-btn')[0]);
    expect(screen.getByTestId('dlq-details')).toBeInTheDocument();
    fireEvent.click(screen.getAllByTestId('expand-btn')[0]);
    expect(screen.queryByTestId('dlq-details')).not.toBeInTheDocument();
  });

  it('opens replay form on replay-btn click', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => LIST_TWO } as Response);
    renderPage();
    await waitFor(() => screen.getAllByTestId('replay-btn'));
    fireEvent.click(screen.getAllByTestId('replay-btn')[0]);
    expect(screen.getByTestId('replay-form')).toBeInTheDocument();
    expect(screen.getByTestId('replay-override-input')).toBeInTheDocument();
  });

  it('dispatches replay and shows replay-result', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => LIST_TWO } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ replay_run_id: 'run-new-001' }) } as Response);

    renderPage();
    await waitFor(() => screen.getAllByTestId('replay-btn'));
    fireEvent.click(screen.getAllByTestId('replay-btn')[0]);
    fireEvent.click(screen.getByTestId('submit-replay-btn'));

    await waitFor(() => expect(screen.getByTestId('replay-result')).toBeInTheDocument());
    expect(screen.getByTestId('replay-result')).toHaveTextContent('run-new-001');
  });

  it('shows error on replay failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => LIST_TWO } as Response)
      .mockResolvedValueOnce({ ok: false, status: 500 } as Response);

    renderPage();
    await waitFor(() => screen.getAllByTestId('replay-btn'));
    fireEvent.click(screen.getAllByTestId('replay-btn')[0]);
    fireEvent.click(screen.getByTestId('submit-replay-btn'));

    await waitFor(() => expect(screen.getByTestId('dlq-error')).toBeInTheDocument());
  });

  it('shows discard confirmation buttons', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => LIST_TWO } as Response);
    renderPage();
    await waitFor(() => screen.getAllByTestId('discard-btn'));
    fireEvent.click(screen.getAllByTestId('discard-btn')[0]);
    expect(screen.getByTestId('confirm-discard-btn')).toBeInTheDocument();
    expect(screen.getByTestId('cancel-discard-btn')).toBeInTheDocument();
  });

  it('discards entry on confirm', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => { return { items: [ENTRY_1], total: 1 }; } } as Response)
      .mockResolvedValueOnce({ ok: true } as Response);

    renderPage();
    await waitFor(() => screen.getByTestId('discard-btn'));
    fireEvent.click(screen.getByTestId('discard-btn'));
    fireEvent.click(screen.getByTestId('confirm-discard-btn'));

    await waitFor(() => expect(screen.getByTestId('empty-state')).toBeInTheDocument());
  });

  it('cancel-discard-btn hides confirmation', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => LIST_TWO } as Response);
    renderPage();
    await waitFor(() => screen.getAllByTestId('discard-btn'));
    fireEvent.click(screen.getAllByTestId('discard-btn')[0]);
    expect(screen.getByTestId('confirm-discard-btn')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('cancel-discard-btn'));
    expect(screen.queryByTestId('confirm-discard-btn')).not.toBeInTheDocument();
  });

  it('shows singular "entry" for total of 1', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true, json: async () => ({ items: [ENTRY_1], total: 1 }),
    } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('total-count')).toHaveTextContent('1 entry in queue'));
  });
});
