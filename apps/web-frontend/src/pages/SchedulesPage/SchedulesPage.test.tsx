/**
 * Unit tests for SchedulesPage (N-76).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import SchedulesPage from './SchedulesPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const SCHEDULE_1 = {
  id: 'sched-001',
  flow_id: 'flow-abc',
  cron_expr: '0 9 * * 1-5',
  name: 'Daily Morning Run',
  enabled: true,
  next_run: '2024-01-16T09:00:00Z',
  last_run: null,
  created_at: '2024-01-15T00:00:00Z',
  run_count: 0,
};

const SCHEDULE_2 = {
  id: 'sched-002',
  flow_id: 'flow-xyz',
  cron_expr: '*/15 * * * *',
  name: 'Every 15 minutes',
  enabled: false,
  next_run: null,
  last_run: '2024-01-15T10:45:00Z',
  created_at: '2024-01-14T00:00:00Z',
  run_count: 10,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <SchedulesPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SchedulesPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => [] } as Response);
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
  });

  it('shows empty state when no schedules', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => [] } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('empty-state')).toBeInTheDocument());
  });

  it('renders schedules list', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => [SCHEDULE_1, SCHEDULE_2],
    } as Response);

    renderPage();
    await waitFor(() => expect(screen.getAllByTestId('schedule-row')).toHaveLength(2));
    expect(screen.getByText('Daily Morning Run')).toBeInTheDocument();
    expect(screen.getByText('Every 15 minutes')).toBeInTheDocument();
  });

  it('shows enabled/disabled badges', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => [SCHEDULE_1, SCHEDULE_2],
    } as Response);

    renderPage();
    await waitFor(() => expect(screen.getAllByTestId('enabled-badge')).toHaveLength(2));
    expect(screen.getByText('enabled')).toBeInTheDocument();
    expect(screen.getByText('disabled')).toBeInTheDocument();
  });

  it('shows schedules-error on load failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 500 } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('schedules-error')).toBeInTheDocument());
  });

  it('opens create form on new-schedule-btn click', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => [] } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('new-schedule-btn')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('new-schedule-btn'));
    expect(screen.getByTestId('create-form')).toBeInTheDocument();
  });

  it('create-submit-btn disabled when required fields empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => [] } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('new-schedule-btn'));
    fireEvent.click(screen.getByTestId('new-schedule-btn'));
    expect(screen.getByTestId('create-submit-btn')).toBeDisabled();
  });

  it('creates a schedule successfully', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => [] } as Response)   // initial load
      .mockResolvedValueOnce({ ok: true, json: async () => SCHEDULE_1 } as Response); // create

    renderPage();
    await waitFor(() => screen.getByTestId('new-schedule-btn'));
    fireEvent.click(screen.getByTestId('new-schedule-btn'));

    fireEvent.change(screen.getByTestId('new-flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.change(screen.getByTestId('new-cron-input'), { target: { value: '0 9 * * 1-5' } });
    fireEvent.submit(screen.getByTestId('create-form'));

    await waitFor(() => expect(screen.getByText('Daily Morning Run')).toBeInTheDocument());
  });

  it('shows error on create failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => [] } as Response)
      .mockResolvedValueOnce({ ok: false, status: 404, text: async () => '' } as Response);

    renderPage();
    await waitFor(() => screen.getByTestId('new-schedule-btn'));
    fireEvent.click(screen.getByTestId('new-schedule-btn'));
    fireEvent.change(screen.getByTestId('new-flow-id-input'), { target: { value: 'bad-flow' } });
    fireEvent.change(screen.getByTestId('new-cron-input'), { target: { value: '0 9 * * *' } });
    fireEvent.submit(screen.getByTestId('create-form'));

    await waitFor(() => expect(screen.getByTestId('schedules-error')).toBeInTheDocument());
  });

  it('cancel-create-btn hides form', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => [] } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('new-schedule-btn'));
    fireEvent.click(screen.getByTestId('new-schedule-btn'));
    expect(screen.getByTestId('create-form')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('cancel-create-btn'));
    expect(screen.queryByTestId('create-form')).not.toBeInTheDocument();
  });

  it('opens edit form on edit-btn click', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => [SCHEDULE_1] } as Response);
    renderPage();
    await waitFor(() => screen.getAllByTestId('edit-btn'));
    fireEvent.click(screen.getAllByTestId('edit-btn')[0]);
    expect(screen.getByTestId('edit-form')).toBeInTheDocument();
    expect(screen.getByTestId('edit-cron-input')).toHaveValue('0 9 * * 1-5');
  });

  it('saves edit successfully', async () => {
    const updated = { ...SCHEDULE_1, name: 'Updated Name' };
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => [SCHEDULE_1] } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => updated } as Response);

    renderPage();
    await waitFor(() => screen.getAllByTestId('edit-btn'));
    fireEvent.click(screen.getAllByTestId('edit-btn')[0]);
    fireEvent.change(screen.getByTestId('edit-name-input'), { target: { value: 'Updated Name' } });
    fireEvent.click(screen.getByTestId('save-edit-btn'));

    await waitFor(() => expect(screen.getByText('Updated Name')).toBeInTheDocument());
  });

  it('shows delete confirmation buttons', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => [SCHEDULE_1] } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('delete-btn'));
    fireEvent.click(screen.getByTestId('delete-btn'));
    expect(screen.getByTestId('confirm-delete-btn')).toBeInTheDocument();
    expect(screen.getByTestId('cancel-delete-btn')).toBeInTheDocument();
  });

  it('deletes schedule on confirm', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => [SCHEDULE_1] } as Response)
      .mockResolvedValueOnce({ ok: true } as Response);

    renderPage();
    await waitFor(() => screen.getByTestId('delete-btn'));
    fireEvent.click(screen.getByTestId('delete-btn'));
    fireEvent.click(screen.getByTestId('confirm-delete-btn'));

    await waitFor(() => expect(screen.getByTestId('empty-state')).toBeInTheDocument());
  });

  it('toggles schedule enabled state', async () => {
    const disabled = { ...SCHEDULE_1, enabled: false };
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => [SCHEDULE_1] } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => disabled } as Response);

    renderPage();
    await waitFor(() => screen.getByTestId('toggle-btn'));
    fireEvent.click(screen.getByTestId('toggle-btn'));

    await waitFor(() => expect(screen.getByText('disabled')).toBeInTheDocument());
  });
});
