import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import RunsPage from './RunsPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children, title }: { children: React.ReactNode; title: string }) => (
    <div data-testid="layout">
      <span data-testid="layout-title">{title}</span>
      {children}
    </div>
  ),
}));

const RUNS_RESPONSE = {
  items: [
    { run_id: 'run-aaa-111', flow_id: 'flow-1', status: 'completed' },
    { run_id: 'run-bbb-222', flow_id: 'flow-2', status: 'failed' },
    { run_id: 'run-ccc-333', flow_id: 'flow-1', status: 'running' },
  ],
  total: 42,
  page: 1,
  page_size: 20,
};

const RUN_DETAIL = {
  run_id: 'run-aaa-111',
  flow_id: 'flow-1',
  status: 'completed',
  progress: 3,
  total_steps: 3,
  completed_applets: ['start', 'llm', 'end'],
};

function makeOk(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response;
}

function makeErr(status: number, detail: string) {
  return { ok: false, status, json: async () => ({ detail }) } as Response;
}

function renderPage() {
  return render(
    <MemoryRouter>
      <RunsPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn());
  window.localStorage.setItem('access_token', 'tok-test');
});

describe('RunsPage', () => {
  // 1. Page title
  it('renders page title', () => {
    renderPage();
    expect(screen.getByTestId('page-title')).toHaveTextContent('Workflow Runs');
  });

  // 2. Empty state before load
  it('shows empty state before loading', () => {
    renderPage();
    expect(screen.getByTestId('no-runs')).toBeInTheDocument();
  });

  // 3. Calls GET /runs on load
  it('calls GET /api/v1/runs on load', async () => {
    const fetchMock = vi.fn().mockResolvedValue(makeOk(RUNS_RESPONSE));
    vi.stubGlobal('fetch', fetchMock);
    renderPage();
    fireEvent.click(screen.getByTestId('load-runs-btn'));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/runs'),
        expect.any(Object),
      ),
    );
  });

  // 4. Run rows rendered
  it('renders run rows after load', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(RUNS_RESPONSE)));
    renderPage();
    fireEvent.click(screen.getByTestId('load-runs-btn'));
    await waitFor(() => {
      const rows = screen.getAllByTestId('run-row');
      expect(rows.length).toBeGreaterThanOrEqual(1);
    });
  });

  // 5. Status colors shown
  it('displays run status in rows', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(RUNS_RESPONSE)));
    renderPage();
    fireEvent.click(screen.getByTestId('load-runs-btn'));
    await waitFor(() => expect(screen.getByText('completed')).toBeInTheDocument());
    expect(screen.getByText('failed')).toBeInTheDocument();
  });

  // 6. Total count shown
  it('displays total run count', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(RUNS_RESPONSE)));
    renderPage();
    fireEvent.click(screen.getByTestId('load-runs-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('total-count')).toHaveTextContent('42'),
    );
  });

  // 7. List error shown
  it('shows error on list failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeErr(500, 'Server error')));
    renderPage();
    fireEvent.click(screen.getByTestId('load-runs-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('list-error')).toHaveTextContent('Server error'),
    );
  });

  // 8. Detail fetch button disabled without ID
  it('detail fetch button disabled without run ID', () => {
    renderPage();
    expect(screen.getByTestId('detail-fetch-btn')).toBeDisabled();
  });

  // 9. Detail fetch calls GET /runs/{run_id}
  it('calls GET /runs/{run_id} on fetch', async () => {
    const fetchMock = vi.fn().mockResolvedValue(makeOk(RUN_DETAIL));
    vi.stubGlobal('fetch', fetchMock);
    renderPage();
    fireEvent.change(screen.getByTestId('detail-run-id-input'), {
      target: { value: 'run-aaa-111' },
    });
    fireEvent.click(screen.getByTestId('detail-fetch-btn'));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/runs/run-aaa-111'),
        expect.any(Object),
      ),
    );
  });

  // 10. Detail status shown
  it('displays run detail status', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(RUN_DETAIL)));
    renderPage();
    fireEvent.change(screen.getByTestId('detail-run-id-input'), {
      target: { value: 'run-aaa-111' },
    });
    fireEvent.click(screen.getByTestId('detail-fetch-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('detail-status')).toHaveTextContent('completed'),
    );
  });

  // 11. Progress shown
  it('displays progress', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(RUN_DETAIL)));
    renderPage();
    fireEvent.change(screen.getByTestId('detail-run-id-input'), {
      target: { value: 'run-aaa-111' },
    });
    fireEvent.click(screen.getByTestId('detail-fetch-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('detail-progress')).toHaveTextContent('3 / 3'),
    );
  });

  // 12. Completed applets shown
  it('shows completed applets list', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(RUN_DETAIL)));
    renderPage();
    fireEvent.change(screen.getByTestId('detail-run-id-input'), {
      target: { value: 'run-aaa-111' },
    });
    fireEvent.click(screen.getByTestId('detail-fetch-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('completed-applets')).toBeInTheDocument(),
    );
  });

  // 13. Clicking row populates detail input
  it('clicking a run row populates detail input', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(makeOk(RUNS_RESPONSE))
      .mockResolvedValueOnce(makeOk(RUN_DETAIL));
    vi.stubGlobal('fetch', fetchMock);
    renderPage();
    fireEvent.click(screen.getByTestId('load-runs-btn'));
    await waitFor(() => screen.getAllByTestId('run-row'));
    const rows = screen.getAllByTestId('run-row');
    fireEvent.click(rows[0]);
    await waitFor(() =>
      expect(screen.getByTestId('detail-run-id-input')).toHaveValue('run-aaa-111'),
    );
  });

  // 14. Detail error shown
  it('shows error on detail fetch failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeErr(404, 'Run not found')));
    renderPage();
    fireEvent.change(screen.getByTestId('detail-run-id-input'), {
      target: { value: 'missing-run' },
    });
    fireEvent.click(screen.getByTestId('detail-fetch-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('detail-error')).toHaveTextContent('Run not found'),
    );
  });
});
