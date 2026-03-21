/**
 * Unit tests for WebhookTriggersPage (N-89).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import WebhookTriggersPage from './WebhookTriggersPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const TRIGGERS_LIST = [
  { id: 'trig-001', flow_id: 'flow-a', created_at: '2024-01-10T09:00:00Z' },
  { id: 'trig-002', flow_id: 'flow-b', created_at: '2024-01-11T10:00:00Z' },
];

const NEW_TRIGGER = { id: 'trig-new-123', flow_id: 'flow-c' };

function renderPage() {
  return render(
    <MemoryRouter>
      <WebhookTriggersPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('WebhookTriggersPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ triggers: [] }),
    } as Response);
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
  });

  it('shows trigger rows in table', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ triggers: TRIGGERS_LIST }),
    } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('triggers-table')).toBeInTheDocument());
    const rows = screen.getAllByTestId('trigger-row');
    expect(rows).toHaveLength(2);
    expect(screen.getByText('trig-001')).toBeInTheDocument();
    expect(screen.getByText('trig-002')).toBeInTheDocument();
  });

  it('shows no-triggers when empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ triggers: [] }),
    } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('no-triggers')).toBeInTheDocument());
  });

  it('shows triggers-error on fetch failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 500 } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('triggers-error')).toBeInTheDocument());
  });

  it('create btn disabled when flow-id empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ triggers: [] }),
    } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('create-form'));
    expect(screen.getByTestId('create-btn')).toBeDisabled();
  });

  it('registering a trigger shows create-success and new row', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ triggers: [] }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => NEW_TRIGGER } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('create-form'));
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-c' } });
    fireEvent.click(screen.getByTestId('create-btn'));
    await waitFor(() => expect(screen.getByTestId('create-success')).toBeInTheDocument());
    expect(screen.getByTestId('new-trigger-id').textContent).toContain('trig-new-123');
    expect(screen.getByTestId('triggers-table')).toBeInTheDocument();
    expect(screen.getAllByTestId('trigger-row')).toHaveLength(1);
  });

  it('shows create-error on registration failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ triggers: [] }) } as Response)
      .mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: async () => ({ detail: "Flow 'bad-id' not found" }),
      } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('create-form'));
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'bad-id' } });
    fireEvent.click(screen.getByTestId('create-btn'));
    await waitFor(() => expect(screen.getByTestId('create-error')).toBeInTheDocument());
    expect(screen.getByTestId('create-error').textContent).toContain("not found");
  });

  it('handles array response shape from backend', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => TRIGGERS_LIST,
    } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('triggers-table')).toBeInTheDocument());
    expect(screen.getAllByTestId('trigger-row')).toHaveLength(2);
  });

  it('deleting a trigger removes its row', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ triggers: TRIGGERS_LIST }),
      } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({}) } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('triggers-table'));
    fireEvent.click(screen.getAllByTestId('delete-btn')[0]);
    await waitFor(() => expect(screen.getAllByTestId('trigger-row')).toHaveLength(1));
  });

  it('shows delete-error on delete failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ triggers: TRIGGERS_LIST }),
      } as Response)
      .mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: async () => ({ detail: 'Trigger not found' }),
      } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('triggers-table'));
    fireEvent.click(screen.getAllByTestId('delete-btn')[0]);
    await waitFor(() => expect(screen.getByTestId('delete-error')).toBeInTheDocument());
    expect(screen.getByTestId('delete-error').textContent).toContain('Trigger not found');
  });

  it('refresh-btn reloads trigger list', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ triggers: TRIGGERS_LIST }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ triggers: TRIGGERS_LIST }),
      } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('refresh-btn')).not.toBeDisabled());
    fireEvent.click(screen.getByTestId('refresh-btn'));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.length).toBeGreaterThanOrEqual(2));
  });
});
