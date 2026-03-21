/**
 * Unit tests for ExecutionLogsPage (N-79).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import ExecutionLogsPage from './ExecutionLogsPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const LOGS_RESULT = {
  run_id: 'run-abc-1234567890',
  count: 3,
  logs: [
    { event: 'node_start',   node_id: 'llm-1', started_at: 1704067200, duration_ms: undefined },
    { event: 'node_success', node_id: 'llm-1', started_at: 1704067200, duration_ms: 342.5 },
    { event: 'node_error',   node_id: 'http-1', started_at: 1704067204, duration_ms: 30.0, error: 'Timeout' },
  ],
};

const LOGS_EMPTY = { run_id: 'run-abc-1234567890', count: 0, logs: [] };

function renderPage() {
  return render(
    <MemoryRouter>
      <ExecutionLogsPage />
    </MemoryRouter>,
  );
}

function fetchLogs() {
  fireEvent.change(screen.getByTestId('run-id-input'), { target: { value: 'run-abc-123' } });
  fireEvent.submit(screen.getByTestId('search-form'));
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ExecutionLogsPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title and search form', () => {
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
    expect(screen.getByTestId('search-form')).toBeInTheDocument();
  });

  it('search-btn is disabled when run ID is empty', () => {
    renderPage();
    expect(screen.getByTestId('search-btn')).toBeDisabled();
  });

  it('shows logs-panel with entries on success', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => LOGS_RESULT } as Response);
    renderPage();
    fetchLogs();
    await waitFor(() => expect(screen.getByTestId('logs-panel')).toBeInTheDocument());
    expect(screen.getAllByTestId('log-entry')).toHaveLength(3);
  });

  it('shows event badges for each entry', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => LOGS_RESULT } as Response);
    renderPage();
    fetchLogs();
    await waitFor(() => screen.getAllByTestId('event-badge'));
    const badges = screen.getAllByTestId('event-badge');
    expect(badges).toHaveLength(3);
    expect(badges[0]).toHaveTextContent('node_start');
    expect(badges[1]).toHaveTextContent('node_success');
    expect(badges[2]).toHaveTextContent('node_error');
  });

  it('shows log-count', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => LOGS_RESULT } as Response);
    renderPage();
    fetchLogs();
    await waitFor(() => expect(screen.getByTestId('log-count')).toHaveTextContent('3 events'));
  });

  it('shows singular "event" for count of 1', async () => {
    const oneLog = { run_id: 'run-x', count: 1, logs: [LOGS_RESULT.logs[0]] };
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => oneLog } as Response);
    renderPage();
    fetchLogs();
    await waitFor(() => expect(screen.getByTestId('log-count')).toHaveTextContent('1 event'));
  });

  it('shows no-logs when logs array is empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => LOGS_EMPTY } as Response);
    renderPage();
    fetchLogs();
    await waitFor(() => expect(screen.getByTestId('no-logs')).toBeInTheDocument());
  });

  it('shows logs-error on 404', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 404 } as Response);
    renderPage();
    fetchLogs();
    await waitFor(() => expect(screen.getByTestId('logs-error')).toBeInTheDocument());
    expect(screen.getByTestId('logs-error')).toHaveTextContent('No logs found');
  });

  it('shows logs-error on server error', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 500 } as Response);
    renderPage();
    fetchLogs();
    await waitFor(() => expect(screen.getByTestId('logs-error')).toBeInTheDocument());
  });

  it('expands log entry details on toggle click', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => LOGS_RESULT } as Response);
    renderPage();
    fetchLogs();
    await waitFor(() => screen.getAllByTestId('log-entry-toggle'));
    fireEvent.click(screen.getAllByTestId('log-entry-toggle')[0]);
    expect(screen.getByTestId('log-entry-details')).toBeInTheDocument();
  });

  it('collapses log entry on second toggle click', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => LOGS_RESULT } as Response);
    renderPage();
    fetchLogs();
    await waitFor(() => screen.getAllByTestId('log-entry-toggle'));
    fireEvent.click(screen.getAllByTestId('log-entry-toggle')[0]);
    expect(screen.getByTestId('log-entry-details')).toBeInTheDocument();
    fireEvent.click(screen.getAllByTestId('log-entry-toggle')[0]);
    expect(screen.queryByTestId('log-entry-details')).not.toBeInTheDocument();
  });

  it('shows duration_ms in log entries where present', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => LOGS_RESULT } as Response);
    renderPage();
    fetchLogs();
    await waitFor(() => screen.getAllByTestId('log-entry'));
    expect(screen.getByText('342.5 ms')).toBeInTheDocument();
  });
});
