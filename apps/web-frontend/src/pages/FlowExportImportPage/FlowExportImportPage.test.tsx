import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import FlowExportImportPage from './FlowExportImportPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children, title }: { children: React.ReactNode; title: string }) => (
    <div data-testid="layout">
      <span data-testid="layout-title">{title}</span>
      {children}
    </div>
  ),
}));

const EXPORT_RESPONSE = {
  synapps_version: '1.0.0',
  name: 'My Workflow',
  nodes: [
    { id: 'n1', type: 'start', position: { x: 0, y: 0 }, data: {} },
    { id: 'n2', type: 'end', position: { x: 200, y: 0 }, data: {} },
  ],
  edges: [{ id: 'e1', source: 'n1', target: 'n2', animated: false }],
};

const IMPORT_RESPONSE = {
  id: 'flow-new-123',
  name: 'My Workflow (imported)',
  node_count: 2,
  edge_count: 1,
};

function makeOk(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response;
}

function makeCreated(body: unknown) {
  return { ok: true, status: 201, json: async () => body } as Response;
}

function makeErr(status: number, detail: string) {
  return { ok: false, status, json: async () => ({ detail }) } as Response;
}

function renderPage() {
  return render(
    <MemoryRouter>
      <FlowExportImportPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn());
  window.localStorage.setItem('access_token', 'tok-test');
});

describe('FlowExportImportPage', () => {
  // 1. Page title
  it('renders page title', () => {
    renderPage();
    expect(screen.getByTestId('page-title')).toHaveTextContent('Flow Export / Import');
  });

  // 2. Two tabs present
  it('renders export and import tabs', () => {
    renderPage();
    expect(screen.getByTestId('tab-export')).toBeInTheDocument();
    expect(screen.getByTestId('tab-import')).toBeInTheDocument();
  });

  // 3. Default tab is export
  it('shows export section by default', () => {
    renderPage();
    expect(screen.getByTestId('export-section')).toBeInTheDocument();
  });

  // 4. Export button disabled without flow ID
  it('export button disabled without flow ID', () => {
    renderPage();
    expect(screen.getByTestId('export-btn')).toBeDisabled();
  });

  // 5. Export calls GET /flows/{flow_id}/export
  it('calls GET /flows/{id}/export', async () => {
    const fetchMock = vi.fn().mockResolvedValue(makeOk(EXPORT_RESPONSE));
    vi.stubGlobal('fetch', fetchMock);
    renderPage();
    fireEvent.change(screen.getByTestId('export-flow-id-input'), {
      target: { value: 'flow-1' },
    });
    fireEvent.click(screen.getByTestId('export-btn'));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/flows/flow-1/export'),
        expect.any(Object),
      ),
    );
  });

  // 6. Export name shown
  it('displays exported flow name', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(EXPORT_RESPONSE)));
    renderPage();
    fireEvent.change(screen.getByTestId('export-flow-id-input'), {
      target: { value: 'flow-1' },
    });
    fireEvent.click(screen.getByTestId('export-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('export-name')).toHaveTextContent('My Workflow'),
    );
  });

  // 7. Node count shown
  it('displays node count', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(EXPORT_RESPONSE)));
    renderPage();
    fireEvent.change(screen.getByTestId('export-flow-id-input'), {
      target: { value: 'flow-1' },
    });
    fireEvent.click(screen.getByTestId('export-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('export-node-count')).toHaveTextContent('2'),
    );
  });

  // 8. Export preview shown
  it('shows JSON preview after export', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(EXPORT_RESPONSE)));
    renderPage();
    fireEvent.change(screen.getByTestId('export-flow-id-input'), {
      target: { value: 'flow-1' },
    });
    fireEvent.click(screen.getByTestId('export-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('export-preview')).toBeInTheDocument(),
    );
  });

  // 9. Export error shown
  it('shows error on export failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeErr(404, 'Flow not found')));
    renderPage();
    fireEvent.change(screen.getByTestId('export-flow-id-input'), {
      target: { value: 'missing' },
    });
    fireEvent.click(screen.getByTestId('export-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('export-error')).toHaveTextContent('Flow not found'),
    );
  });

  // 10. Switch to import tab
  it('switches to import tab', () => {
    renderPage();
    fireEvent.click(screen.getByTestId('tab-import'));
    expect(screen.getByTestId('import-section')).toBeInTheDocument();
  });

  // 11. Import calls POST /flows/import
  it('calls POST /flows/import with JSON body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(makeCreated(IMPORT_RESPONSE));
    vi.stubGlobal('fetch', fetchMock);
    renderPage();
    fireEvent.click(screen.getByTestId('tab-import'));
    fireEvent.change(screen.getByTestId('import-json-input'), {
      target: { value: JSON.stringify(EXPORT_RESPONSE) },
    });
    fireEvent.click(screen.getByTestId('import-btn'));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/flows/import'),
        expect.objectContaining({ method: 'POST' }),
      ),
    );
  });

  // 12. Import result shows new flow ID
  it('shows imported flow ID on success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeCreated(IMPORT_RESPONSE)));
    renderPage();
    fireEvent.click(screen.getByTestId('tab-import'));
    fireEvent.change(screen.getByTestId('import-json-input'), {
      target: { value: JSON.stringify(EXPORT_RESPONSE) },
    });
    fireEvent.click(screen.getByTestId('import-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('import-flow-id')).toHaveTextContent('flow-new-123'),
    );
  });

  // 13. Invalid JSON shows parse error
  it('shows error for invalid JSON input', async () => {
    renderPage();
    fireEvent.click(screen.getByTestId('tab-import'));
    fireEvent.change(screen.getByTestId('import-json-input'), {
      target: { value: 'not valid json' },
    });
    fireEvent.click(screen.getByTestId('import-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('import-error')).toHaveTextContent('Invalid JSON'),
    );
  });

  // 14. Import API error shown
  it('shows API error on import failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeErr(400, 'Invalid flow format')));
    renderPage();
    fireEvent.click(screen.getByTestId('tab-import'));
    fireEvent.change(screen.getByTestId('import-json-input'), {
      target: { value: JSON.stringify({ name: 'x', nodes: [], edges: [] }) },
    });
    fireEvent.click(screen.getByTestId('import-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('import-error')).toHaveTextContent('Invalid flow format'),
    );
  });
});
