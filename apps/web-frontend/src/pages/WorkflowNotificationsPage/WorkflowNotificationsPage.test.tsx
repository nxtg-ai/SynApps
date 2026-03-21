/**
 * Unit tests for WorkflowNotificationsPage (N-78).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import WorkflowNotificationsPage from './WorkflowNotificationsPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const CONFIG_EMPTY = {
  flow_id: 'flow-abc',
  config: { on_complete: [], on_failure: [] },
};

const CONFIG_WITH_HANDLERS = {
  flow_id: 'flow-abc',
  config: {
    on_complete: [{ type: 'email', to: 'ops@example.com', subject: 'Done', message: '' }],
    on_failure: [{ type: 'slack', webhook_url: 'https://hooks.slack.com/xxx', message: '' }],
  },
};

function renderPage() {
  return render(
    <MemoryRouter>
      <WorkflowNotificationsPage />
    </MemoryRouter>,
  );
}

function loadFlow(flowId = 'flow-abc') {
  fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: flowId } });
  fireEvent.submit(screen.getByTestId('flow-selector-form'));
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('WorkflowNotificationsPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title and flow selector form', () => {
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
    expect(screen.getByTestId('flow-selector-form')).toBeInTheDocument();
  });

  it('shows no-flow-state before load', () => {
    renderPage();
    expect(screen.getByTestId('no-flow-state')).toBeInTheDocument();
  });

  it('load-btn is disabled when flow ID empty', () => {
    renderPage();
    expect(screen.getByTestId('load-btn')).toBeDisabled();
  });

  it('shows config-panel after loading', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => CONFIG_EMPTY } as Response);
    renderPage();
    loadFlow();
    await waitFor(() => expect(screen.getByTestId('config-panel')).toBeInTheDocument());
    expect(screen.getByTestId('on-complete-section')).toBeInTheDocument();
    expect(screen.getByTestId('on-failure-section')).toBeInTheDocument();
  });

  it('shows no-handlers when both sections empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => CONFIG_EMPTY } as Response);
    renderPage();
    loadFlow();
    await waitFor(() => screen.getAllByTestId('no-handlers'));
    expect(screen.getAllByTestId('no-handlers')).toHaveLength(2);
  });

  it('shows notif-error on load failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 404 } as Response);
    renderPage();
    loadFlow();
    await waitFor(() => expect(screen.getByTestId('notif-error')).toBeInTheDocument());
  });

  it('shows existing handlers when config has handlers', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true, json: async () => CONFIG_WITH_HANDLERS,
    } as Response);
    renderPage();
    loadFlow();
    await waitFor(() => expect(screen.getAllByTestId('handler-row')).toHaveLength(2));
  });

  it('adds handler to on-complete section', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => CONFIG_EMPTY } as Response);
    renderPage();
    loadFlow();
    await waitFor(() => screen.getByTestId('on-complete-section'));

    const addBtns = screen.getAllByTestId('add-handler-btn');
    fireEvent.click(addBtns[0]); // first section = on_complete
    expect(screen.getAllByTestId('handler-row')).toHaveLength(1);
  });

  it('removes handler on remove click', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true, json: async () => CONFIG_WITH_HANDLERS,
    } as Response);
    renderPage();
    loadFlow();
    await waitFor(() => screen.getAllByTestId('handler-row'));
    expect(screen.getAllByTestId('handler-row')).toHaveLength(2);
    fireEvent.click(screen.getAllByTestId('remove-handler-btn')[0]);
    expect(screen.getAllByTestId('handler-row')).toHaveLength(1);
  });

  it('saves config and shows notif-success', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => CONFIG_EMPTY } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => CONFIG_EMPTY } as Response);
    renderPage();
    loadFlow();
    await waitFor(() => screen.getByTestId('save-btn'));
    fireEvent.click(screen.getByTestId('save-btn'));
    await waitFor(() => expect(screen.getByTestId('notif-success')).toBeInTheDocument());
  });

  it('shows notif-error on save failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => CONFIG_EMPTY } as Response)
      .mockResolvedValueOnce({ ok: false, status: 422 } as Response);
    renderPage();
    loadFlow();
    await waitFor(() => screen.getByTestId('save-btn'));
    fireEvent.click(screen.getByTestId('save-btn'));
    await waitFor(() => expect(screen.getByTestId('notif-error')).toBeInTheDocument());
  });

  it('changing handler type updates the form fields', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => CONFIG_EMPTY } as Response);
    renderPage();
    loadFlow();
    await waitFor(() => screen.getAllByTestId('add-handler-btn'));
    fireEvent.click(screen.getAllByTestId('add-handler-btn')[0]);
    // Default type is email — shows email-specific fields
    expect(screen.getByTestId('handler-to-input')).toBeInTheDocument();
    // Change to slack
    fireEvent.change(screen.getByTestId('handler-type-select'), { target: { value: 'slack' } });
    expect(screen.getByTestId('handler-webhook-url-input')).toBeInTheDocument();
    expect(screen.queryByTestId('handler-to-input')).not.toBeInTheDocument();
  });
});
