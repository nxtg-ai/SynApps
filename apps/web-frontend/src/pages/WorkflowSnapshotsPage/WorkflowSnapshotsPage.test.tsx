import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import WorkflowSnapshotsPage from './WorkflowSnapshotsPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children, title }: { children: React.ReactNode; title: string }) => (
    <div data-testid="layout">
      <span data-testid="layout-title">{title}</span>
      {children}
    </div>
  ),
}));

const VERSION_HISTORY = {
  flow_id: 'flow-1',
  versions: [
    { version_id: 'ver-aaa-111', label: 'before-refactor', node_count: 3 },
    { version_id: 'ver-bbb-222', label: 'post-refactor', node_count: 5 },
  ],
  total: 2,
};

const VERSION_RECORD = {
  version_id: 'ver-aaa-111',
  label: 'before-refactor',
  node_count: 3,
  snapshot: { nodes: [{ id: 'n1' }], edges: [] },
};

const DIFF_RESULT = {
  nodes_added: ['node-x'],
  nodes_removed: ['node-y'],
  nodes_changed: ['node-z'],
  edges_added: 1,
  edges_removed: 0,
  summary: '1 added, 1 removed, 1 changed',
};

const SAVE_RESULT = {
  version_id: 'ver-new-001',
  label: 'my-label',
  flow_id: 'flow-1',
  node_count: 2,
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
      <WorkflowSnapshotsPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn());
  window.localStorage.setItem('access_token', 'tok-test');
});

describe('WorkflowSnapshotsPage', () => {
  // 1. Page title
  it('renders page title', () => {
    renderPage();
    expect(screen.getByTestId('page-title')).toHaveTextContent('Workflow Snapshots');
  });

  // 2. Four tabs rendered
  it('renders all four tabs', () => {
    renderPage();
    expect(screen.getByTestId('tab-history')).toBeInTheDocument();
    expect(screen.getByTestId('tab-inspect')).toBeInTheDocument();
    expect(screen.getByTestId('tab-save')).toBeInTheDocument();
    expect(screen.getByTestId('tab-diff')).toBeInTheDocument();
  });

  // 3. History tab active by default
  it('shows history section by default', () => {
    renderPage();
    expect(screen.getByTestId('history-section')).toBeInTheDocument();
  });

  // 4. Load history — calls GET /version-history
  it('calls GET /version-history on submit', async () => {
    const fetchMock = vi.fn().mockResolvedValue(makeOk(VERSION_HISTORY));
    vi.stubGlobal('fetch', fetchMock);
    renderPage();
    fireEvent.change(screen.getByTestId('history-flow-id-input'), {
      target: { value: 'flow-1' },
    });
    fireEvent.click(screen.getByTestId('history-load-btn'));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/workflows/flow-1/version-history'),
        expect.any(Object),
      ),
    );
  });

  // 5. Version rows rendered
  it('renders version rows after history load', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(VERSION_HISTORY)));
    renderPage();
    fireEvent.change(screen.getByTestId('history-flow-id-input'), {
      target: { value: 'flow-1' },
    });
    fireEvent.click(screen.getByTestId('history-load-btn'));
    await waitFor(() => {
      const rows = screen.getAllByTestId('version-row');
      expect(rows.length).toBeGreaterThanOrEqual(1);
    });
  });

  // 6. No-versions empty state
  it('shows no-versions message when list is empty', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk({ versions: [], total: 0 })));
    renderPage();
    fireEvent.change(screen.getByTestId('history-flow-id-input'), {
      target: { value: 'flow-1' },
    });
    fireEvent.click(screen.getByTestId('history-load-btn'));
    await waitFor(() => expect(screen.getByTestId('no-versions')).toBeInTheDocument());
  });

  // 7. History error shown
  it('shows error on history load failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeErr(404, 'Not found')));
    renderPage();
    fireEvent.change(screen.getByTestId('history-flow-id-input'), {
      target: { value: 'flow-1' },
    });
    fireEvent.click(screen.getByTestId('history-load-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('history-error')).toHaveTextContent('Not found'),
    );
  });

  // 8. Inspect tab — fetch disabled without both IDs
  it('inspect button disabled without both IDs', () => {
    renderPage();
    fireEvent.click(screen.getByTestId('tab-inspect'));
    expect(screen.getByTestId('inspect-btn')).toBeDisabled();
  });

  // 9. Inspect — calls GET /versions/{id}
  it('calls GET /versions/{id} on inspect', async () => {
    const fetchMock = vi.fn().mockResolvedValue(makeOk(VERSION_RECORD));
    vi.stubGlobal('fetch', fetchMock);
    renderPage();
    fireEvent.click(screen.getByTestId('tab-inspect'));
    fireEvent.change(screen.getByTestId('inspect-flow-id-input'), {
      target: { value: 'flow-1' },
    });
    fireEvent.change(screen.getByTestId('inspect-version-id-input'), {
      target: { value: 'ver-aaa-111' },
    });
    fireEvent.click(screen.getByTestId('inspect-btn'));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/workflows/flow-1/versions/ver-aaa-111'),
        expect.any(Object),
      ),
    );
  });

  // 10. Inspect result shown
  it('displays inspect result with label and snapshot', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(VERSION_RECORD)));
    renderPage();
    fireEvent.click(screen.getByTestId('tab-inspect'));
    fireEvent.change(screen.getByTestId('inspect-flow-id-input'), {
      target: { value: 'flow-1' },
    });
    fireEvent.change(screen.getByTestId('inspect-version-id-input'), {
      target: { value: 'ver-aaa-111' },
    });
    fireEvent.click(screen.getByTestId('inspect-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('inspect-result')).toBeInTheDocument();
      expect(screen.getByTestId('inspect-label')).toHaveTextContent('before-refactor');
      expect(screen.getByTestId('inspect-snapshot')).toBeInTheDocument();
    });
  });

  // 11. Save snapshot — calls POST /versions
  it('calls POST /versions to save snapshot', async () => {
    const fetchMock = vi.fn().mockResolvedValue(makeOk(SAVE_RESULT));
    vi.stubGlobal('fetch', fetchMock);
    renderPage();
    fireEvent.click(screen.getByTestId('tab-save'));
    fireEvent.change(screen.getByTestId('save-flow-id-input'), {
      target: { value: 'flow-1' },
    });
    fireEvent.change(screen.getByTestId('save-label-input'), {
      target: { value: 'my-label' },
    });
    fireEvent.change(screen.getByTestId('save-snapshot-input'), {
      target: { value: '{"nodes":[],"edges":[]}' },
    });
    fireEvent.click(screen.getByTestId('save-btn'));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/workflows/flow-1/versions'),
        expect.objectContaining({ method: 'POST' }),
      ),
    );
  });

  // 12. Save result shown
  it('displays save result with version ID', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(SAVE_RESULT)));
    renderPage();
    fireEvent.click(screen.getByTestId('tab-save'));
    fireEvent.change(screen.getByTestId('save-flow-id-input'), {
      target: { value: 'flow-1' },
    });
    fireEvent.change(screen.getByTestId('save-snapshot-input'), {
      target: { value: '{"nodes":[],"edges":[]}' },
    });
    fireEvent.click(screen.getByTestId('save-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('save-result')).toBeInTheDocument();
      expect(screen.getByTestId('save-result-version-id')).toHaveTextContent('ver-new-001');
    });
  });

  // 13. Diff tab — calls POST /diff
  it('calls POST /diff on compute', async () => {
    const fetchMock = vi.fn().mockResolvedValue(makeOk(DIFF_RESULT));
    vi.stubGlobal('fetch', fetchMock);
    renderPage();
    fireEvent.click(screen.getByTestId('tab-diff'));
    fireEvent.change(screen.getByTestId('diff-flow-id-input'), {
      target: { value: 'flow-1' },
    });
    fireEvent.change(screen.getByTestId('diff-v1-input'), {
      target: { value: '{"nodes":[{"id":"n1"}],"edges":[]}' },
    });
    fireEvent.change(screen.getByTestId('diff-v2-input'), {
      target: { value: '{"nodes":[{"id":"n2"}],"edges":[]}' },
    });
    fireEvent.click(screen.getByTestId('diff-btn'));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/workflows/flow-1/diff'),
        expect.objectContaining({ method: 'POST' }),
      ),
    );
  });

  // 14. Diff result rendered with added/removed/changed nodes
  it('displays diff result with node changes', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(DIFF_RESULT)));
    renderPage();
    fireEvent.click(screen.getByTestId('tab-diff'));
    fireEvent.change(screen.getByTestId('diff-flow-id-input'), {
      target: { value: 'flow-1' },
    });
    fireEvent.change(screen.getByTestId('diff-v1-input'), {
      target: { value: '{"nodes":[],"edges":[]}' },
    });
    fireEvent.change(screen.getByTestId('diff-v2-input'), {
      target: { value: '{"nodes":[],"edges":[]}' },
    });
    fireEvent.click(screen.getByTestId('diff-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('diff-result')).toBeInTheDocument();
      expect(screen.getByTestId('diff-nodes-added')).toBeInTheDocument();
      expect(screen.getByTestId('diff-nodes-removed')).toBeInTheDocument();
      expect(screen.getByTestId('diff-nodes-changed')).toBeInTheDocument();
    });
  });

  // 15. Clicking a version row navigates to inspect tab with IDs pre-filled
  it('clicking version row switches to inspect tab with pre-filled IDs', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(VERSION_HISTORY)));
    renderPage();
    fireEvent.change(screen.getByTestId('history-flow-id-input'), {
      target: { value: 'flow-1' },
    });
    fireEvent.click(screen.getByTestId('history-load-btn'));
    await waitFor(() => screen.getAllByTestId('version-row'));
    fireEvent.click(screen.getAllByTestId('version-row')[0]);
    await waitFor(() => {
      expect(screen.getByTestId('inspect-section')).toBeInTheDocument();
      expect(screen.getByTestId('inspect-version-id-input')).toHaveValue('ver-aaa-111');
    });
  });
});
