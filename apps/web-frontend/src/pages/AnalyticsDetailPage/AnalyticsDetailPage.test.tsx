import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import AnalyticsDetailPage from './AnalyticsDetailPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children, title }: { children: React.ReactNode; title: string }) => (
    <div data-testid="layout">
      <span data-testid="layout-title">{title}</span>
      {children}
    </div>
  ),
}));

const WORKFLOW_RESPONSE = {
  workflows: [
    { flow_id: 'flow-1', run_count: 10, success_count: 8, error_count: 2, avg_duration_ms: 150 },
    { flow_id: 'flow-2', run_count: 5, success_count: 5, error_count: 0, avg_duration_ms: 200 },
  ],
  total_flows: 2,
};

const NODE_RESPONSE = {
  nodes: [
    { node_id: 'node-1', node_type: 'llm', execution_count: 20, success_count: 18, error_count: 2, avg_duration_ms: 300 },
    { node_id: 'node-2', node_type: 'code', execution_count: 10, success_count: 10, error_count: 0 },
  ],
  total_nodes: 2,
};

function makeOk(body: unknown) {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  } as Response;
}

function makeErr(status: number, detail: string) {
  return {
    ok: false,
    status,
    json: async () => ({ detail }),
  } as Response;
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AnalyticsDetailPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn());
  window.localStorage.setItem('access_token', 'tok-test');
});

describe('AnalyticsDetailPage', () => {
  // 1. Page title rendered
  it('renders page title', () => {
    renderPage();
    expect(screen.getByTestId('page-title')).toHaveTextContent('Analytics Detail');
  });

  // 2. Tabs present
  it('renders workflow and node tabs', () => {
    renderPage();
    expect(screen.getByTestId('tab-workflows')).toBeInTheDocument();
    expect(screen.getByTestId('tab-nodes')).toBeInTheDocument();
  });

  // 3. Default tab is workflows
  it('shows workflows section by default', () => {
    renderPage();
    expect(screen.getByTestId('workflows-section')).toBeInTheDocument();
  });

  // 4. Switch to nodes tab
  it('switches to nodes tab', () => {
    renderPage();
    fireEvent.click(screen.getByTestId('tab-nodes'));
    expect(screen.getByTestId('nodes-section')).toBeInTheDocument();
  });

  // 5. Load button calls GET /analytics/workflows
  it('calls GET /analytics/workflows on Load', async () => {
    const fetchMock = vi.fn().mockResolvedValue(makeOk(WORKFLOW_RESPONSE));
    vi.stubGlobal('fetch', fetchMock);
    renderPage();
    fireEvent.click(screen.getByTestId('load-btn'));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/analytics/workflows'),
        expect.any(Object),
      ),
    );
  });

  // 6. Workflow rows rendered
  it('renders workflow rows after load', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(WORKFLOW_RESPONSE)));
    renderPage();
    fireEvent.click(screen.getByTestId('load-btn'));
    await waitFor(() => {
      const rows = screen.getAllByTestId('workflow-row');
      expect(rows.length).toBeGreaterThanOrEqual(1);
    });
  });

  // 7. Workflow flow IDs shown
  it('displays workflow flow IDs', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(WORKFLOW_RESPONSE)));
    renderPage();
    fireEvent.click(screen.getByTestId('load-btn'));
    await waitFor(() => expect(screen.getByText('flow-1')).toBeInTheDocument());
    expect(screen.getByText('flow-2')).toBeInTheDocument();
  });

  // 8. Load nodes on nodes tab
  it('calls GET /analytics/nodes when on nodes tab', async () => {
    const fetchMock = vi.fn().mockResolvedValue(makeOk(NODE_RESPONSE));
    vi.stubGlobal('fetch', fetchMock);
    renderPage();
    fireEvent.click(screen.getByTestId('tab-nodes'));
    fireEvent.click(screen.getByTestId('load-btn'));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/analytics/nodes'),
        expect.any(Object),
      ),
    );
  });

  // 9. Node rows rendered
  it('renders node rows after load', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(NODE_RESPONSE)));
    renderPage();
    fireEvent.click(screen.getByTestId('tab-nodes'));
    fireEvent.click(screen.getByTestId('load-btn'));
    await waitFor(() => {
      const rows = screen.getAllByTestId('node-row');
      expect(rows.length).toBeGreaterThanOrEqual(1);
    });
  });

  // 10. Flow ID filter appended to URL
  it('includes flow_id param when filter is set', async () => {
    const fetchMock = vi.fn().mockResolvedValue(makeOk(WORKFLOW_RESPONSE));
    vi.stubGlobal('fetch', fetchMock);
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-filter'), { target: { value: 'my-flow' } });
    fireEvent.click(screen.getByTestId('load-btn'));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('flow_id=my-flow'),
        expect.any(Object),
      ),
    );
  });

  // 11. Error displayed on API failure (workflows)
  it('shows error message on workflows API failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeErr(500, 'Internal error')));
    renderPage();
    fireEvent.click(screen.getByTestId('load-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('workflows-error')).toHaveTextContent('Internal error'),
    );
  });

  // 12. Empty state shown when no data
  it('shows empty state when no workflows returned', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk({ workflows: [], total_flows: 0 })));
    renderPage();
    fireEvent.click(screen.getByTestId('load-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('no-workflows')).toBeInTheDocument(),
    );
  });

  // 13. Node type shown in rows
  it('displays node type in node rows', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(NODE_RESPONSE)));
    renderPage();
    fireEvent.click(screen.getByTestId('tab-nodes'));
    fireEvent.click(screen.getByTestId('load-btn'));
    await waitFor(() => expect(screen.getByText('llm')).toBeInTheDocument());
  });
});
