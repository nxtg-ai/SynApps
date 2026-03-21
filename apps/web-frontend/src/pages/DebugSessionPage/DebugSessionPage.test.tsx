/**
 * Unit tests for DebugSessionPage (N-107).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import DebugSessionPage from './DebugSessionPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const SESSION = {
  session_id: 'dbg-session-001',
  run_id: 'run-001',
  flow_id: 'flow-abc',
  status: 'paused',
  current_node_id: 'node-B',
  breakpoints: ['node-B', 'node-C'],
  execution_history: [
    { node_id: 'node-A', status: 'completed', skipped: false },
    { node_id: 'node-B', status: 'paused', skipped: false },
  ],
};

const SESSION_RUNNING = { ...SESSION, status: 'running', current_node_id: null };
const SESSION_COMPLETED = { ...SESSION, status: 'completed', current_node_id: null };
const SESSION_SKIPPED = { ...SESSION, status: 'running', execution_history: [
  { node_id: 'node-A', status: 'completed', skipped: false },
  { node_id: 'node-B', status: 'skipped', skipped: true },
]};

function makeOk(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response;
}
function makeNoContent() {
  return { ok: true, status: 204, json: async () => ({}) } as Response;
}
function makeErr(status: number, detail: string) {
  return { ok: false, status, json: async () => ({ detail }) } as unknown as Response;
}

function renderPage() {
  return render(
    <MemoryRouter>
      <DebugSessionPage />
    </MemoryRouter>,
  );
}

async function startSession() {
  vi.mocked(fetch).mockResolvedValueOnce(makeOk(SESSION));
  fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
  fireEvent.click(screen.getByTestId('start-btn'));
  await waitFor(() => expect(screen.getByTestId('session-panel')).toBeInTheDocument());
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('DebugSessionPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'tok');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title and start form', () => {
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
    expect(screen.getByTestId('start-section')).toBeInTheDocument();
    expect(screen.getByTestId('start-btn')).toBeInTheDocument();
  });

  it('starts debug session and shows session panel', async () => {
    renderPage();
    await startSession();
    expect(screen.getByTestId('session-id').textContent).toBe('dbg-session-001');
    expect(screen.getByTestId('session-status').textContent).toBe('paused');
    expect(screen.getByTestId('session-run-id').textContent).toBe('run-001');
  });

  it('shows start-error on invalid input JSON', async () => {
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.change(screen.getByTestId('input-json'), { target: { value: 'bad-json' } });
    fireEvent.click(screen.getByTestId('start-btn'));
    await waitFor(() => expect(screen.getByTestId('start-error')).toBeInTheDocument());
    expect(screen.getByTestId('start-error').textContent).toContain('Invalid JSON');
  });

  it('shows start-error on API failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(404, 'Flow not found'));
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.click(screen.getByTestId('start-btn'));
    await waitFor(() => expect(screen.getByTestId('start-error')).toBeInTheDocument());
    expect(screen.getByTestId('start-error').textContent).toContain('Flow not found');
  });

  it('shows current paused node', async () => {
    renderPage();
    await startSession();
    expect(screen.getByTestId('current-node').textContent).toBe('node-B');
  });

  it('shows execution history', async () => {
    renderPage();
    await startSession();
    const items = screen.getAllByTestId('history-item');
    expect(items).toHaveLength(2);
    expect(items[0].textContent).toContain('node-A');
    expect(items[0].textContent).toContain('completed');
  });

  it('shows skipped flag in history', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(SESSION_SKIPPED));
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.click(screen.getByTestId('start-btn'));
    await waitFor(() => screen.getByTestId('session-panel'));
    const items = screen.getAllByTestId('history-item');
    expect(items[1].textContent).toContain('skipped');
  });

  it('continues session and updates status', async () => {
    renderPage();
    await startSession();
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(SESSION_RUNNING));
    fireEvent.click(screen.getByTestId('continue-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('session-status').textContent).toBe('running'),
    );
  });

  it('skips node and updates session', async () => {
    renderPage();
    await startSession();
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(SESSION_SKIPPED));
    fireEvent.click(screen.getByTestId('skip-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('session-status').textContent).toBe('running'),
    );
  });

  it('refreshes session state', async () => {
    renderPage();
    await startSession();
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(SESSION_COMPLETED));
    fireEvent.click(screen.getByTestId('refresh-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('session-status').textContent).toBe('completed'),
    );
  });

  it('updates breakpoints', async () => {
    renderPage();
    await startSession();
    const updatedSession = { ...SESSION, breakpoints: ['node-X'] };
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(updatedSession));
    fireEvent.change(screen.getByTestId('new-breakpoints-input'), { target: { value: 'node-X' } });
    fireEvent.click(screen.getByTestId('update-bp-btn'));
    await waitFor(() => screen.getByTestId('session-panel'));
  });

  it('shows bp-error on breakpoints update failure', async () => {
    renderPage();
    await startSession();
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(404, 'Session gone'));
    fireEvent.click(screen.getByTestId('update-bp-btn'));
    await waitFor(() => expect(screen.getByTestId('bp-error')).toBeInTheDocument());
  });

  it('aborts session and returns to start form', async () => {
    renderPage();
    await startSession();
    vi.mocked(fetch).mockResolvedValueOnce(makeNoContent());
    fireEvent.click(screen.getByTestId('abort-btn'));
    await waitFor(() => expect(screen.getByTestId('start-section')).toBeInTheDocument());
    expect(screen.queryByTestId('session-panel')).not.toBeInTheDocument();
  });

  it('shows session-error on continue failure', async () => {
    renderPage();
    await startSession();
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(404, 'Not found'));
    fireEvent.click(screen.getByTestId('continue-btn'));
    await waitFor(() => expect(screen.getByTestId('session-error')).toBeInTheDocument());
  });

  it('breakpoints parsed from comma-separated input and sent to start', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk({ ...SESSION, breakpoints: ['node-A', 'node-B'] }));
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.change(screen.getByTestId('breakpoints-input'), { target: { value: 'node-A, node-B' } });
    fireEvent.click(screen.getByTestId('start-btn'));
    await waitFor(() => screen.getByTestId('session-panel'));
    const call = vi.mocked(fetch).mock.calls[0];
    const body = JSON.parse(call[1]?.body as string);
    expect(body.breakpoints).toEqual(['node-A', 'node-B']);
  });
});
