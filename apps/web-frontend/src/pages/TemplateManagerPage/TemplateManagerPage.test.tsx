/**
 * Unit tests for TemplateManagerPage (N-96).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import TemplateManagerPage from './TemplateManagerPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const TEMPLATES = [
  {
    id: 'tpl-aaa',
    name: 'Notification Pipeline',
    description: 'Sends Slack alerts',
    semver: '1.0.0',
    version: 1,
    tags: ['notification'],
    nodes: [{ id: 'n1' }, { id: 'n2' }],
    edges: [{ id: 'e1' }],
  },
  {
    id: 'tpl-bbb',
    name: 'Data Sync Workflow',
    description: 'Syncs DB to S3',
    semver: '2.1.0',
    version: 3,
    tags: ['data-sync'],
    nodes: [],
    edges: [],
  },
];

const VERSIONS = [
  { version: 1, semver: '1.0.0', created_at: 1700000000 },
  { version: 2, semver: '1.1.0', created_at: 1700001000 },
];

const IMPORTED = {
  id: 'tpl-imported',
  name: 'Imported Template',
  version: 1,
  semver: '1.0.0',
  nodes: [],
  edges: [],
};

const INSTANTIATED = { id: 'flow-new-999', name: 'My Flow' };

function renderPage() {
  return render(
    <MemoryRouter>
      <TemplateManagerPage />
    </MemoryRouter>,
  );
}

function makeOk(body: unknown) {
  return { ok: true, json: async () => body } as Response;
}
function makeErr(status: number, detail: string) {
  return { ok: false, status, json: async () => ({ detail }) } as unknown as Response;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('TemplateManagerPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk({ templates: [] }));
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
  });

  it('shows template items in list', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk({ templates: TEMPLATES }));
    renderPage();
    await waitFor(() => expect(screen.getByTestId('templates-list')).toBeInTheDocument());
    const items = screen.getAllByTestId('template-item');
    expect(items).toHaveLength(2);
    expect(items[0].textContent).toContain('Notification Pipeline');
  });

  it('shows no-templates when empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk({ templates: [] }));
    renderPage();
    await waitFor(() => expect(screen.getByTestId('no-templates')).toBeInTheDocument());
  });

  it('shows list-error on fetch failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 500 } as Response);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('list-error')).toBeInTheDocument());
  });

  it('handles array response shape', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(TEMPLATES));
    renderPage();
    await waitFor(() => {
      const items = screen.getAllByTestId('template-item');
      expect(items).toHaveLength(2);
    });
  });

  it('clicking template shows detail panel', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk({ templates: TEMPLATES }));
    renderPage();
    await waitFor(() => screen.getByTestId('templates-list'));
    fireEvent.click(screen.getAllByTestId('template-item')[0]);
    expect(screen.getByTestId('template-detail')).toBeInTheDocument();
    expect(screen.getByTestId('detail-name').textContent).toContain('Notification Pipeline');
  });

  it('overview tab shows node + edge counts', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk({ templates: TEMPLATES }));
    renderPage();
    await waitFor(() => screen.getByTestId('templates-list'));
    fireEvent.click(screen.getAllByTestId('template-item')[0]);
    expect(screen.getByTestId('detail-node-count').textContent).toBe('2');
    expect(screen.getByTestId('detail-edge-count').textContent).toBe('1');
  });

  it('versions tab loads and shows version rows', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ templates: TEMPLATES }))
      .mockResolvedValueOnce(makeOk({ template_id: 'tpl-aaa', versions: VERSIONS, total: 2 }));
    renderPage();
    await waitFor(() => screen.getByTestId('templates-list'));
    fireEvent.click(screen.getAllByTestId('template-item')[0]);
    fireEvent.click(screen.getByTestId('tab-versions'));
    await waitFor(() => expect(screen.getByTestId('versions-table')).toBeInTheDocument());
    const rows = screen.getAllByTestId('version-row');
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain('1.0.0');
  });

  it('versions tab shows versions-error on failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ templates: TEMPLATES }))
      .mockResolvedValueOnce(makeErr(404, 'Template not found'));
    renderPage();
    await waitFor(() => screen.getByTestId('templates-list'));
    fireEvent.click(screen.getAllByTestId('template-item')[0]);
    fireEvent.click(screen.getByTestId('tab-versions'));
    await waitFor(() => expect(screen.getByTestId('versions-error')).toBeInTheDocument());
  });

  it('rollback btn disabled when input empty', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ templates: TEMPLATES }))
      .mockResolvedValueOnce(makeOk({ template_id: 'tpl-aaa', versions: VERSIONS, total: 2 }));
    renderPage();
    await waitFor(() => screen.getByTestId('templates-list'));
    fireEvent.click(screen.getAllByTestId('template-item')[0]);
    fireEvent.click(screen.getByTestId('tab-versions'));
    await waitFor(() => screen.getByTestId('rollback-form'));
    expect(screen.getByTestId('rollback-btn')).toBeDisabled();
  });

  it('rollback shows rollback-success', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ templates: TEMPLATES }))
      .mockResolvedValueOnce(makeOk({ template_id: 'tpl-aaa', versions: VERSIONS, total: 2 }))
      .mockResolvedValueOnce(makeOk({ id: 'tpl-aaa', name: 'Notification Pipeline', version: 3, semver: '1.0.1' }))
      .mockResolvedValueOnce(makeOk({ template_id: 'tpl-aaa', versions: VERSIONS, total: 2 }));
    renderPage();
    await waitFor(() => screen.getByTestId('templates-list'));
    fireEvent.click(screen.getAllByTestId('template-item')[0]);
    fireEvent.click(screen.getByTestId('tab-versions'));
    await waitFor(() => screen.getByTestId('rollback-form'));
    fireEvent.change(screen.getByTestId('rollback-input'), { target: { value: '1.0.0' } });
    fireEvent.submit(screen.getByTestId('rollback-form'));
    await waitFor(() => expect(screen.getByTestId('rollback-success')).toBeInTheDocument());
  });

  it('rollback shows rollback-error on failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ templates: TEMPLATES }))
      .mockResolvedValueOnce(makeOk({ template_id: 'tpl-aaa', versions: VERSIONS, total: 2 }))
      .mockResolvedValueOnce(makeErr(404, 'Version 9.9.9 not found'));
    renderPage();
    await waitFor(() => screen.getByTestId('templates-list'));
    fireEvent.click(screen.getAllByTestId('template-item')[0]);
    fireEvent.click(screen.getByTestId('tab-versions'));
    await waitFor(() => screen.getByTestId('rollback-form'));
    fireEvent.change(screen.getByTestId('rollback-input'), { target: { value: '9.9.9' } });
    fireEvent.submit(screen.getByTestId('rollback-form'));
    await waitFor(() => expect(screen.getByTestId('rollback-error')).toBeInTheDocument());
    expect(screen.getByTestId('rollback-error').textContent).toContain('not found');
  });

  it('instantiate tab creates flow and shows result', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ templates: TEMPLATES }))
      .mockResolvedValueOnce(makeOk(INSTANTIATED));
    renderPage();
    await waitFor(() => screen.getByTestId('templates-list'));
    fireEvent.click(screen.getAllByTestId('template-item')[0]);
    fireEvent.click(screen.getByTestId('tab-instantiate'));
    fireEvent.change(screen.getByTestId('flow-name-input'), { target: { value: 'My Flow' } });
    fireEvent.submit(screen.getByTestId('instantiate-form'));
    await waitFor(() => expect(screen.getByTestId('instantiate-result')).toBeInTheDocument());
    expect(screen.getByTestId('new-flow-id').textContent).toContain('flow-new-999');
  });

  it('instantiate shows instantiate-error on failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ templates: TEMPLATES }))
      .mockResolvedValueOnce(makeErr(404, 'Template not found'));
    renderPage();
    await waitFor(() => screen.getByTestId('templates-list'));
    fireEvent.click(screen.getAllByTestId('template-item')[0]);
    fireEvent.click(screen.getByTestId('tab-instantiate'));
    fireEvent.submit(screen.getByTestId('instantiate-form'));
    await waitFor(() => expect(screen.getByTestId('instantiate-error')).toBeInTheDocument());
    expect(screen.getByTestId('instantiate-error').textContent).toContain('Template not found');
  });

  it('import btn disabled when textarea empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk({ templates: [] }));
    renderPage();
    await waitFor(() => screen.getByTestId('import-form'));
    expect(screen.getByTestId('import-btn')).toBeDisabled();
  });

  it('import shows import-error on invalid JSON', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk({ templates: [] }));
    renderPage();
    await waitFor(() => screen.getByTestId('import-form'));
    fireEvent.change(screen.getByTestId('import-json-input'), { target: { value: 'not-json' } });
    fireEvent.submit(screen.getByTestId('import-form'));
    await waitFor(() => expect(screen.getByTestId('import-error')).toBeInTheDocument());
    expect(screen.getByTestId('import-error').textContent).toContain('Invalid JSON');
  });

  it('import shows import-success and adds template to list', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ templates: [] }))
      .mockResolvedValueOnce(makeOk(IMPORTED));
    renderPage();
    await waitFor(() => screen.getByTestId('import-form'));
    fireEvent.change(screen.getByTestId('import-json-input'), {
      target: { value: JSON.stringify({ name: 'Imported Template', nodes: [], edges: [] }) },
    });
    fireEvent.submit(screen.getByTestId('import-form'));
    await waitFor(() => expect(screen.getByTestId('import-success')).toBeInTheDocument());
    expect(screen.getByTestId('import-success').textContent).toContain('Imported Template');
    expect(screen.getByTestId('templates-list')).toBeInTheDocument();
  });

  it('import shows import-error on server failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ templates: [] }))
      .mockResolvedValueOnce(makeErr(409, 'Template already exists'));
    renderPage();
    await waitFor(() => screen.getByTestId('import-form'));
    fireEvent.change(screen.getByTestId('import-json-input'), {
      target: { value: '{"name":"x","nodes":[],"edges":[]}' },
    });
    fireEvent.submit(screen.getByTestId('import-form'));
    await waitFor(() => expect(screen.getByTestId('import-error')).toBeInTheDocument());
    expect(screen.getByTestId('import-error').textContent).toContain('already exists');
  });

  it('search form calls search endpoint and updates list', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ templates: TEMPLATES }))
      .mockResolvedValueOnce(makeOk({ items: [TEMPLATES[0]] }));
    renderPage();
    await waitFor(() => screen.getByTestId('search-form'));
    fireEvent.change(screen.getByTestId('search-q-input'), { target: { value: 'notification' } });
    fireEvent.submit(screen.getByTestId('search-form'));
    await waitFor(() => {
      const items = screen.getAllByTestId('template-item');
      expect(items).toHaveLength(1);
    });
  });

  it('search shows search-error on failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ templates: [] }))
      .mockResolvedValueOnce({ ok: false, status: 500 } as Response);
    renderPage();
    await waitFor(() => screen.getByTestId('search-form'));
    fireEvent.change(screen.getByTestId('search-q-input'), { target: { value: 'test' } });
    fireEvent.submit(screen.getByTestId('search-form'));
    await waitFor(() => expect(screen.getByTestId('search-error')).toBeInTheDocument());
  });

  it('refresh-btn reloads template list', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ templates: TEMPLATES }))
      .mockResolvedValueOnce(makeOk({ templates: TEMPLATES }));
    renderPage();
    await waitFor(() => expect(screen.getByTestId('refresh-btn')).not.toBeDisabled());
    fireEvent.click(screen.getByTestId('refresh-btn'));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.length).toBeGreaterThanOrEqual(2));
  });
});
