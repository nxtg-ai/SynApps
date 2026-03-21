/**
 * Unit tests for TaskMonitorPage (N-92).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import TaskMonitorPage from './TaskMonitorPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const TASKS_LIST = [
  { task_id: 'task-001', status: 'completed', created_at: '2024-01-10T09:00:00Z', completed_at: '2024-01-10T09:01:00Z', result: { run_id: 'run-abc' } },
  { task_id: 'task-002', status: 'failed', created_at: '2024-01-10T10:00:00Z', error: 'Flow not found' },
  { task_id: 'task-003', status: 'running', created_at: '2024-01-10T11:00:00Z' },
];

const TASK_DETAIL = {
  task_id: 'task-001',
  status: 'completed',
  created_at: '2024-01-10T09:00:00Z',
  completed_at: '2024-01-10T09:01:00Z',
  result: { run_id: 'run-abc' },
};

function renderPage() {
  return render(
    <MemoryRouter>
      <TaskMonitorPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('TaskMonitorPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title and filter bar', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ tasks: [] }),
    } as Response);
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
    expect(screen.getByTestId('filter-bar')).toBeInTheDocument();
    expect(screen.getByTestId('filter-all')).toBeInTheDocument();
    expect(screen.getByTestId('filter-completed')).toBeInTheDocument();
    expect(screen.getByTestId('filter-failed')).toBeInTheDocument();
  });

  it('shows task rows in table', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ tasks: TASKS_LIST }),
    } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('tasks-table')).toBeInTheDocument());
    const rows = screen.getAllByTestId('task-row');
    expect(rows).toHaveLength(3);
  });

  it('shows no-tasks when empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ tasks: [] }),
    } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('no-tasks')).toBeInTheDocument());
  });

  it('shows tasks-error on fetch failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 500 } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('tasks-error')).toBeInTheDocument());
  });

  it('shows no-task-selected initially', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ tasks: TASKS_LIST }),
    } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('tasks-table'));
    expect(screen.getByTestId('no-task-selected')).toBeInTheDocument();
  });

  it('clicking a row loads task detail', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ tasks: TASKS_LIST }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => TASK_DETAIL } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('tasks-table'));
    fireEvent.click(screen.getAllByTestId('task-row')[0]);
    await waitFor(() => expect(screen.getByTestId('task-detail')).toBeInTheDocument());
    expect(screen.getByTestId('detail-task-id').textContent).toContain('task-001');
    expect(screen.getByTestId('detail-status').textContent).toContain('completed');
  });

  it('shows result section for completed task', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ tasks: TASKS_LIST }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => TASK_DETAIL } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('tasks-table'));
    fireEvent.click(screen.getAllByTestId('task-row')[0]);
    await waitFor(() => screen.getByTestId('task-detail'));
    expect(screen.getByTestId('detail-result-section')).toBeInTheDocument();
  });

  it('shows error section for failed task', async () => {
    const failedDetail = { task_id: 'task-002', status: 'failed', error: 'Flow not found' };
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ tasks: TASKS_LIST }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => failedDetail } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('tasks-table'));
    fireEvent.click(screen.getAllByTestId('task-row')[1]);
    await waitFor(() => screen.getByTestId('task-detail'));
    expect(screen.getByTestId('detail-error-section')).toBeInTheDocument();
  });

  it('clicking filter-failed sends status param', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ tasks: TASKS_LIST }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ tasks: [TASKS_LIST[1]] }) } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('filter-failed')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('filter-failed'));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.length).toBeGreaterThanOrEqual(2));
    const secondCall = vi.mocked(fetch).mock.calls[1][0] as string;
    expect(secondCall).toContain('status=failed');
  });

  it('status badges use appropriate colors', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ tasks: TASKS_LIST }),
    } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('tasks-table'));
    const badges = screen.getAllByTestId('status-badge');
    expect(badges).toHaveLength(3);
    // completed badge should have emerald class
    expect(badges[0].className).toContain('emerald');
    // failed badge should have red class
    expect(badges[1].className).toContain('red');
  });

  it('refresh-btn reloads tasks', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ tasks: TASKS_LIST }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ tasks: TASKS_LIST }) } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('refresh-btn')).not.toBeDisabled());
    fireEvent.click(screen.getByTestId('refresh-btn'));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.length).toBeGreaterThanOrEqual(2));
  });
});
