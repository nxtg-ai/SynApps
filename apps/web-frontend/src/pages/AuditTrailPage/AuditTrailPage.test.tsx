/**
 * Unit tests for AuditTrailPage (N-75).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import AuditTrailPage from './AuditTrailPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const ENTRY_1 = {
  id: 'audit-001',
  timestamp: '2024-01-15T10:30:00Z',
  actor: 'alice@example.com',
  action: 'workflow_created',
  resource_type: 'flow',
  resource_id: 'flow-abc',
  detail: 'Created workflow "My Flow"',
};

const ENTRY_2 = {
  id: 'audit-002',
  timestamp: '2024-01-15T11:00:00Z',
  actor: 'bob@example.com',
  action: 'run_started',
  resource_type: 'run',
  resource_id: 'run-xyz',
  detail: 'Started run',
};

const RESULT_TWO = { count: 2, entries: [ENTRY_1, ENTRY_2] };
const RESULT_EMPTY = { count: 0, entries: [] };

function renderPage() {
  return render(
    <MemoryRouter>
      <AuditTrailPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('AuditTrailPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title and filter form', () => {
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
    expect(screen.getByTestId('filter-form')).toBeInTheDocument();
  });

  it('renders all filter inputs', () => {
    renderPage();
    expect(screen.getByTestId('actor-input')).toBeInTheDocument();
    expect(screen.getByTestId('action-input')).toBeInTheDocument();
    expect(screen.getByTestId('resource-type-input')).toBeInTheDocument();
    expect(screen.getByTestId('resource-id-input')).toBeInTheDocument();
    expect(screen.getByTestId('since-input')).toBeInTheDocument();
    expect(screen.getByTestId('until-input')).toBeInTheDocument();
    expect(screen.getByTestId('limit-select')).toBeInTheDocument();
  });

  it('shows audit entries after search', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => RESULT_TWO,
    } as Response);

    renderPage();
    fireEvent.submit(screen.getByTestId('filter-form'));

    await waitFor(() => expect(screen.getByTestId('results-panel')).toBeInTheDocument());
    expect(screen.getByTestId('result-count')).toHaveTextContent('2 entries returned');
    expect(screen.getAllByTestId('audit-row')).toHaveLength(2);
    expect(screen.getByText('alice@example.com')).toBeInTheDocument();
    expect(screen.getByText('bob@example.com')).toBeInTheDocument();
  });

  it('shows action badges for each entry', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => RESULT_TWO } as Response);

    renderPage();
    fireEvent.submit(screen.getByTestId('filter-form'));

    await waitFor(() => expect(screen.getAllByTestId('action-badge')).toHaveLength(2));
    expect(screen.getByText('workflow_created')).toBeInTheDocument();
    expect(screen.getByText('run_started')).toBeInTheDocument();
  });

  it('shows no-results when entries array is empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => RESULT_EMPTY } as Response);

    renderPage();
    fireEvent.submit(screen.getByTestId('filter-form'));

    await waitFor(() => expect(screen.getByTestId('no-results')).toBeInTheDocument());
    expect(screen.getByTestId('result-count')).toHaveTextContent('0 entries returned');
  });

  it('shows audit-error on fetch failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 500 } as Response);

    renderPage();
    fireEvent.submit(screen.getByTestId('filter-form'));

    await waitFor(() => expect(screen.getByTestId('audit-error')).toBeInTheDocument());
  });

  it('shows loading state on search button during fetch', async () => {
    vi.mocked(fetch).mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve({ ok: true, json: async () => RESULT_EMPTY } as unknown as Response), 100)),
    );

    renderPage();
    fireEvent.submit(screen.getByTestId('filter-form'));

    expect(screen.getByTestId('search-btn')).toHaveTextContent('Loading…');
    expect(screen.getByTestId('search-btn')).toBeDisabled();
    await waitFor(() => expect(screen.getByTestId('results-panel')).toBeInTheDocument());
  });

  it('includes actor filter in query string', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => RESULT_EMPTY } as Response);

    renderPage();
    fireEvent.change(screen.getByTestId('actor-input'), { target: { value: 'alice@example.com' } });
    fireEvent.submit(screen.getByTestId('filter-form'));

    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledOnce());
    const url = vi.mocked(fetch).mock.calls[0][0] as string;
    expect(url).toContain('actor=alice%40example.com');
  });

  it('includes action filter in query string', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => RESULT_EMPTY } as Response);

    renderPage();
    fireEvent.change(screen.getByTestId('action-input'), { target: { value: 'workflow_created' } });
    fireEvent.submit(screen.getByTestId('filter-form'));

    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledOnce());
    const url = vi.mocked(fetch).mock.calls[0][0] as string;
    expect(url).toContain('action=workflow_created');
  });

  it('clear-btn resets all fields and clears results', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => RESULT_TWO } as Response);

    renderPage();
    fireEvent.change(screen.getByTestId('actor-input'), { target: { value: 'alice@example.com' } });
    fireEvent.submit(screen.getByTestId('filter-form'));

    await waitFor(() => expect(screen.getByTestId('results-panel')).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('clear-btn'));

    expect(screen.getByTestId('actor-input')).toHaveValue('');
    expect(screen.queryByTestId('results-panel')).not.toBeInTheDocument();
  });

  it('shows singular "entry" for count of 1', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ count: 1, entries: [ENTRY_1] }),
    } as Response);

    renderPage();
    fireEvent.submit(screen.getByTestId('filter-form'));

    await waitFor(() => expect(screen.getByTestId('result-count')).toHaveTextContent('1 entry returned'));
  });
});
