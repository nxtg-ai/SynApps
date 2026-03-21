/**
 * Unit tests for WorkflowActivityPage (N-85).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import WorkflowActivityPage from './WorkflowActivityPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const COMMENTS_TWO = {
  flow_id: 'flow-abc',
  count: 2,
  comments: [
    { id: 'c1', node_id: 'node-1', author: 'alice@example.com', content: 'Looks good!', created_at: '2024-01-10T09:00:00Z' },
    { id: 'c2', node_id: 'node-2', author: 'bob@example.com', content: 'Check the timeout here.', created_at: '2024-01-10T10:00:00Z' },
  ],
};

const COMMENTS_EMPTY = { flow_id: 'flow-abc', count: 0, comments: [] };

const ACTIVITY_TWO = {
  flow_id: 'flow-abc',
  count: 2,
  events: [
    { actor: 'alice@example.com', action: 'workflow_run', detail: 'Run started', timestamp: '2024-01-10T09:30:00Z' },
    { actor: 'bob@example.com', action: 'node_commented', detail: 'Comment on node-2', timestamp: '2024-01-10T10:00:00Z' },
  ],
};

const ACTIVITY_EMPTY = { flow_id: 'flow-abc', count: 0, events: [] };

function renderPage() {
  return render(
    <MemoryRouter>
      <WorkflowActivityPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('WorkflowActivityPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title and no-flow state', () => {
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
    expect(screen.getByTestId('no-flow-state')).toBeInTheDocument();
  });

  it('load button disabled when input is empty', () => {
    renderPage();
    expect(screen.getByTestId('load-btn')).toBeDisabled();
  });

  it('shows comments and activity panels after load', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => COMMENTS_TWO } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ACTIVITY_TWO } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.click(screen.getByTestId('load-btn'));
    await waitFor(() => expect(screen.getByTestId('panels-container')).toBeInTheDocument());
    expect(screen.getByTestId('comments-panel')).toBeInTheDocument();
    expect(screen.getByTestId('activity-panel')).toBeInTheDocument();
  });

  it('shows comment rows', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => COMMENTS_TWO } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ACTIVITY_EMPTY } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.click(screen.getByTestId('load-btn'));
    await waitFor(() => screen.getByTestId('comments-list'));
    expect(screen.getAllByTestId('comment-row')).toHaveLength(2);
    expect(screen.getByText('Looks good!')).toBeInTheDocument();
  });

  it('shows no-comments when empty', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => COMMENTS_EMPTY } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ACTIVITY_EMPTY } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.click(screen.getByTestId('load-btn'));
    await waitFor(() => expect(screen.getByTestId('no-comments')).toBeInTheDocument());
  });

  it('shows activity rows with action badges', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => COMMENTS_EMPTY } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ACTIVITY_TWO } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.click(screen.getByTestId('load-btn'));
    await waitFor(() => screen.getByTestId('activity-list'));
    expect(screen.getAllByTestId('activity-row')).toHaveLength(2);
    expect(screen.getAllByTestId('action-badge')).toHaveLength(2);
  });

  it('shows no-activity when events empty', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => COMMENTS_EMPTY } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ACTIVITY_EMPTY } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.click(screen.getByTestId('load-btn'));
    await waitFor(() => expect(screen.getByTestId('no-activity')).toBeInTheDocument());
  });

  it('shows comments-error on comments fetch failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: false, status: 404 } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ACTIVITY_EMPTY } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'bad-id' } });
    fireEvent.click(screen.getByTestId('load-btn'));
    await waitFor(() => expect(screen.getByTestId('comments-error')).toBeInTheDocument());
  });

  it('shows activity-error on activity fetch failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => COMMENTS_EMPTY } as Response)
      .mockResolvedValueOnce({ ok: false, status: 500 } as Response);
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.click(screen.getByTestId('load-btn'));
    await waitFor(() => expect(screen.getByTestId('activity-error')).toBeInTheDocument());
  });
});
