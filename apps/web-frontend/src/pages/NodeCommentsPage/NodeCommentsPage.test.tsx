/**
 * Unit tests for NodeCommentsPage (N-104).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import NodeCommentsPage from './NodeCommentsPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const FLOW_ID = 'flow-abc-123';
const NODE_ID = 'node-xyz-456';

const COMMENTS_LIST = [
  {
    comment_id: 'cmt-001',
    flow_id: FLOW_ID,
    node_id: NODE_ID,
    author: 'alice@example.com',
    content: 'This node looks correct.',
    parent_id: null,
  },
  {
    comment_id: 'cmt-002',
    flow_id: FLOW_ID,
    node_id: NODE_ID,
    author: 'bob@example.com',
    content: 'Agreed, but check edge cases.',
    parent_id: 'cmt-001',
  },
];

function renderPage() {
  return render(
    <MemoryRouter>
      <NodeCommentsPage />
    </MemoryRouter>,
  );
}

function makeOk(body: unknown) {
  return { ok: true, json: async () => body } as Response;
}
function makeErr(status: number, detail: string) {
  return { ok: false, status, json: async () => ({ detail }) } as unknown as Response;
}

function setFlowAndNode() {
  fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: FLOW_ID } });
  fireEvent.change(screen.getByTestId('node-id-input'), { target: { value: NODE_ID } });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('NodeCommentsPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title, flow/node inputs, and create section', () => {
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
    expect(screen.getByTestId('flow-id-input')).toBeInTheDocument();
    expect(screen.getByTestId('node-id-input')).toBeInTheDocument();
    expect(screen.getByTestId('create-section')).toBeInTheDocument();
  });

  it('load-btn disabled when flow id or node id empty', () => {
    renderPage();
    expect(screen.getByTestId('load-btn')).toBeDisabled();
  });

  it('create-btn disabled when flow id, node id, or content empty', () => {
    renderPage();
    expect(screen.getByTestId('create-btn')).toBeDisabled();
  });

  it('loads comments and shows list', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      makeOk({ flow_id: FLOW_ID, node_id: NODE_ID, count: 2, comments: COMMENTS_LIST }),
    );
    renderPage();
    setFlowAndNode();
    fireEvent.click(screen.getByTestId('load-btn'));
    await waitFor(() => expect(screen.getByTestId('comments-list')).toBeInTheDocument());
    const items = screen.getAllByTestId('comment-item');
    expect(items).toHaveLength(2);
    expect(items[0].textContent).toContain('This node looks correct.');
    expect(items[1].textContent).toContain('Agreed, but check edge cases.');
  });

  it('handles array response shape', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(COMMENTS_LIST));
    renderPage();
    setFlowAndNode();
    fireEvent.click(screen.getByTestId('load-btn'));
    await waitFor(() => {
      const items = screen.getAllByTestId('comment-item');
      expect(items).toHaveLength(2);
    });
  });

  it('shows no-comments when list is empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      makeOk({ flow_id: FLOW_ID, node_id: NODE_ID, count: 0, comments: [] }),
    );
    renderPage();
    setFlowAndNode();
    fireEvent.click(screen.getByTestId('load-btn'));
    await waitFor(() => expect(screen.getByTestId('no-comments')).toBeInTheDocument());
  });

  it('shows list-error on fetch failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(404, 'Flow not found'));
    renderPage();
    setFlowAndNode();
    fireEvent.click(screen.getByTestId('load-btn'));
    await waitFor(() => expect(screen.getByTestId('list-error')).toBeInTheDocument());
    expect(screen.getByTestId('list-error').textContent).toContain('Flow not found');
  });

  it('shows parent thread indicator for replies', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      makeOk({ count: 2, comments: COMMENTS_LIST }),
    );
    renderPage();
    setFlowAndNode();
    fireEvent.click(screen.getByTestId('load-btn'));
    await waitFor(() => screen.getByTestId('comments-list'));
    const items = screen.getAllByTestId('comment-item');
    expect(items[1].textContent).toContain('reply to cmt-001');
  });

  it('creates comment and shows create-success with comment id', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      makeOk({
        comment_id: 'cmt-new-999',
        flow_id: FLOW_ID,
        node_id: NODE_ID,
        author: 'alice@example.com',
        content: 'New comment!',
        parent_id: null,
      }),
    );
    renderPage();
    setFlowAndNode();
    fireEvent.change(screen.getByTestId('content-input'), {
      target: { value: 'New comment!' },
    });
    fireEvent.submit(screen.getByTestId('create-form'));
    await waitFor(() => expect(screen.getByTestId('create-success')).toBeInTheDocument());
    expect(screen.getByTestId('new-comment-id').textContent).toContain('cmt-new-999');
  });

  it('shows create-error on failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(404, 'Flow not found'));
    renderPage();
    setFlowAndNode();
    fireEvent.change(screen.getByTestId('content-input'), {
      target: { value: 'Test' },
    });
    fireEvent.submit(screen.getByTestId('create-form'));
    await waitFor(() => expect(screen.getByTestId('create-error')).toBeInTheDocument());
    expect(screen.getByTestId('create-error').textContent).toContain('Flow not found');
  });

  it('includes parent_id in request when provided', async () => {
    let capturedBody: Record<string, unknown> = {};
    vi.mocked(fetch).mockImplementationOnce(async (_url, opts) => {
      capturedBody = JSON.parse((opts?.body as string) ?? '{}');
      return makeOk({
        comment_id: 'cmt-reply',
        flow_id: FLOW_ID,
        node_id: NODE_ID,
        author: 'x',
        content: 'Reply!',
        parent_id: 'cmt-001',
      });
    });
    renderPage();
    setFlowAndNode();
    fireEvent.change(screen.getByTestId('content-input'), { target: { value: 'Reply!' } });
    fireEvent.change(screen.getByTestId('parent-id-input'), {
      target: { value: 'cmt-001' },
    });
    fireEvent.submit(screen.getByTestId('create-form'));
    await waitFor(() => screen.getByTestId('create-success'));
    expect(capturedBody.parent_id).toBe('cmt-001');
    expect(capturedBody.content).toBe('Reply!');
  });

  it('new comment prepended to loaded list', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ count: 1, comments: [COMMENTS_LIST[0]] }))
      .mockResolvedValueOnce(
        makeOk({
          comment_id: 'cmt-prepend',
          flow_id: FLOW_ID,
          node_id: NODE_ID,
          author: 'c@c.com',
          content: 'Prepended comment',
          parent_id: null,
        }),
      );
    renderPage();
    setFlowAndNode();
    fireEvent.click(screen.getByTestId('load-btn'));
    await waitFor(() => screen.getByTestId('comments-list'));

    fireEvent.change(screen.getByTestId('content-input'), {
      target: { value: 'Prepended comment' },
    });
    fireEvent.submit(screen.getByTestId('create-form'));
    await waitFor(() => {
      const items = screen.getAllByTestId('comment-item');
      expect(items).toHaveLength(2);
      expect(items[0].textContent).toContain('Prepended comment');
    });
  });
});
