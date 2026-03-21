/**
 * Unit tests for WorkflowSecretsPage (N-110).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import WorkflowSecretsPage from './WorkflowSecretsPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const SECRETS_DATA = {
  flow_id: 'flow-abc',
  secrets: [
    { name: 'OPENAI_KEY', value: '***' },
    { name: 'DB_PASS', value: '***' },
  ],
  count: 2,
};

const PUT_RESULT = { flow_id: 'flow-abc', secrets: [{ name: 'OPENAI_KEY', value: '***' }], count: 1 };

const DIFF_RESULT = {
  nodes_added: ['node-X'],
  nodes_removed: [],
  edges_added: 1,
  edges_removed: 0,
};

const VERSION_RECORD = {
  version_id: 'ver-001',
  flow_id: 'flow-abc',
  label: 'v1.0',
  saved_at: 1711000000,
  snapshot: { nodes: [], edges: [] },
};

const VERSIONS_LIST = {
  versions: [VERSION_RECORD, { version_id: 'ver-002', flow_id: 'flow-abc', label: 'v1.1' }],
  total: 2,
};

function makeOk(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response;
}
function makeErr(status: number, detail: string) {
  return { ok: false, status, json: async () => ({ detail }) } as unknown as Response;
}

function renderPage() {
  return render(
    <MemoryRouter>
      <WorkflowSecretsPage />
    </MemoryRouter>,
  );
}

function fillFlowId(value = 'flow-abc') {
  fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value } });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('WorkflowSecretsPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'tok');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title and tabs', () => {
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
    expect(screen.getByTestId('tab-secrets')).toBeInTheDocument();
    expect(screen.getByTestId('tab-diff')).toBeInTheDocument();
    expect(screen.getByTestId('tab-versions')).toBeInTheDocument();
  });

  it('loads and shows secrets', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(SECRETS_DATA));
    renderPage();
    fillFlowId();
    fireEvent.click(screen.getByTestId('load-secrets-btn'));
    await waitFor(() => screen.getByTestId('secrets-list'));
    const items = screen.getAllByTestId('secret-item');
    expect(items).toHaveLength(2);
    expect(items[0].textContent).toContain('OPENAI_KEY');
  });

  it('shows no-secrets when list is empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk({ secrets: [], count: 0 }));
    renderPage();
    fillFlowId();
    fireEvent.click(screen.getByTestId('load-secrets-btn'));
    await waitFor(() => expect(screen.getByTestId('no-secrets')).toBeInTheDocument());
  });

  it('shows secrets-error on fetch failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(404, 'Flow not found'));
    renderPage();
    fillFlowId();
    fireEvent.click(screen.getByTestId('load-secrets-btn'));
    await waitFor(() => expect(screen.getByTestId('secrets-error')).toBeInTheDocument());
  });

  it('sets secrets and shows result', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk(PUT_RESULT))      // PUT
      .mockResolvedValueOnce(makeOk(SECRETS_DATA));   // reload
    renderPage();
    fillFlowId();
    fireEvent.click(screen.getByTestId('put-secrets-btn'));
    await waitFor(() => expect(screen.getByTestId('put-result')).toBeInTheDocument());
    expect(screen.getByTestId('secrets-count').textContent).toBe('1');
  });

  it('shows put-error on invalid JSON', async () => {
    renderPage();
    fillFlowId();
    fireEvent.change(screen.getByTestId('put-secrets-json'), { target: { value: 'bad-json' } });
    fireEvent.click(screen.getByTestId('put-secrets-btn'));
    await waitFor(() => expect(screen.getByTestId('put-error')).toBeInTheDocument());
    expect(screen.getByTestId('put-error').textContent).toContain('Invalid JSON');
  });

  it('shows put-error on API failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(422, 'Invalid body'));
    renderPage();
    fillFlowId();
    fireEvent.click(screen.getByTestId('put-secrets-btn'));
    await waitFor(() => expect(screen.getByTestId('put-error')).toBeInTheDocument());
  });

  it('switches to diff tab and computes diff', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(DIFF_RESULT));
    renderPage();
    fillFlowId();
    fireEvent.click(screen.getByTestId('tab-diff'));
    await waitFor(() => screen.getByTestId('tab-panel-diff'));
    fireEvent.click(screen.getByTestId('diff-btn'));
    await waitFor(() => expect(screen.getByTestId('diff-result')).toBeInTheDocument());
    expect(screen.getByTestId('diff-json').textContent).toContain('node-X');
  });

  it('shows diff-error on invalid V1 JSON', async () => {
    renderPage();
    fillFlowId();
    fireEvent.click(screen.getByTestId('tab-diff'));
    await waitFor(() => screen.getByTestId('tab-panel-diff'));
    fireEvent.change(screen.getByTestId('diff-v1-input'), { target: { value: 'bad' } });
    fireEvent.click(screen.getByTestId('diff-btn'));
    await waitFor(() => expect(screen.getByTestId('diff-error')).toBeInTheDocument());
    expect(screen.getByTestId('diff-error').textContent).toContain('Invalid JSON in V1');
  });

  it('shows diff-error on API failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(500, 'Diff failed'));
    renderPage();
    fillFlowId();
    fireEvent.click(screen.getByTestId('tab-diff'));
    await waitFor(() => screen.getByTestId('tab-panel-diff'));
    fireEvent.click(screen.getByTestId('diff-btn'));
    await waitFor(() => expect(screen.getByTestId('diff-error')).toBeInTheDocument());
  });

  it('switches to versions tab and saves a version', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk(VERSION_RECORD))   // POST save
      .mockResolvedValueOnce(makeOk(VERSIONS_LIST));   // reload history
    renderPage();
    fillFlowId();
    fireEvent.click(screen.getByTestId('tab-versions'));
    await waitFor(() => screen.getByTestId('tab-panel-versions'));
    fireEvent.change(screen.getByTestId('save-label-input'), { target: { value: 'v1.0' } });
    fireEvent.click(screen.getByTestId('save-version-btn'));
    await waitFor(() => expect(screen.getByTestId('save-result')).toBeInTheDocument());
    expect(screen.getByTestId('saved-version-id').textContent).toBe('ver-001');
  });

  it('shows save-error on invalid snapshot JSON', async () => {
    renderPage();
    fillFlowId();
    fireEvent.click(screen.getByTestId('tab-versions'));
    await waitFor(() => screen.getByTestId('tab-panel-versions'));
    fireEvent.change(screen.getByTestId('save-snapshot-input'), { target: { value: 'bad' } });
    fireEvent.click(screen.getByTestId('save-version-btn'));
    await waitFor(() => expect(screen.getByTestId('save-error')).toBeInTheDocument());
  });

  it('loads version history', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(VERSIONS_LIST));
    renderPage();
    fillFlowId();
    fireEvent.click(screen.getByTestId('tab-versions'));
    await waitFor(() => screen.getByTestId('tab-panel-versions'));
    fireEvent.click(screen.getByTestId('load-history-btn'));
    await waitFor(() => screen.getByTestId('versions-list'));
    expect(screen.getAllByTestId('version-item')).toHaveLength(2);
  });

  it('shows no-versions when history is empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk({ versions: [], total: 0 }));
    renderPage();
    fillFlowId();
    fireEvent.click(screen.getByTestId('tab-versions'));
    await waitFor(() => screen.getByTestId('tab-panel-versions'));
    fireEvent.click(screen.getByTestId('load-history-btn'));
    await waitFor(() => expect(screen.getByTestId('no-versions')).toBeInTheDocument());
  });

  it('views a single version', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(VERSION_RECORD));
    renderPage();
    fillFlowId();
    fireEvent.click(screen.getByTestId('tab-versions'));
    await waitFor(() => screen.getByTestId('tab-panel-versions'));
    fireEvent.change(screen.getByTestId('view-version-id-input'), { target: { value: 'ver-001' } });
    fireEvent.click(screen.getByTestId('view-version-btn'));
    await waitFor(() => screen.getByTestId('view-version-result'));
    expect(screen.getByTestId('view-version-label').textContent).toBe('v1.0');
  });

  it('shows view-version-error on fetch failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(404, 'Version not found'));
    renderPage();
    fillFlowId();
    fireEvent.click(screen.getByTestId('tab-versions'));
    await waitFor(() => screen.getByTestId('tab-panel-versions'));
    fireEvent.change(screen.getByTestId('view-version-id-input'), { target: { value: 'bad' } });
    fireEvent.click(screen.getByTestId('view-version-btn'));
    await waitFor(() => expect(screen.getByTestId('view-version-error')).toBeInTheDocument());
  });
});
