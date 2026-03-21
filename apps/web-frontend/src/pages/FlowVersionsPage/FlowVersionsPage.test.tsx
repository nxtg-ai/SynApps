/**
 * Unit tests for FlowVersionsPage (N-97).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import FlowVersionsPage from './FlowVersionsPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const VERSIONS = [
  { version_id: 'ver-111', version: 1, snapshotted_at: 1700000000 },
  { version_id: 'ver-222', version: 2, snapshotted_at: 1700001000 },
];

const VERSION_DETAIL = {
  version_id: 'ver-111',
  version: 1,
  snapshot: { nodes: [{ id: 'n1' }], edges: [] },
};

const ROLLBACK_RESULT = {
  flow: { id: 'flow-abc', name: 'My Flow' },
  rolled_back_to: 'ver-111',
  audit_entry: { id: 'audit-1', flow_id: 'flow-abc', from_version_id: 'ver-222', to_version_id: 'ver-111' },
};

const AUDIT_ENTRIES = [
  {
    id: 'audit-1',
    flow_id: 'flow-abc',
    from_version_id: 'ver-222',
    to_version_id: 'ver-111',
    performed_by: 'user@test.com',
    reason: 'Bug in v2',
  },
];

const GLOBAL_ENTRIES = [
  { id: 'audit-g1', flow_id: 'flow-abc', from_version_id: 'ver-2', to_version_id: 'ver-1', performed_by: 'admin' },
  { id: 'audit-g2', flow_id: 'flow-xyz', from_version_id: 'ver-3', to_version_id: 'ver-2', performed_by: 'alice' },
];

function renderPage() {
  return render(
    <MemoryRouter>
      <FlowVersionsPage />
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

describe('FlowVersionsPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title and tabs', () => {
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
    expect(screen.getByTestId('section-tabs')).toBeInTheDocument();
    expect(screen.getByTestId('tab-versions')).toBeInTheDocument();
    expect(screen.getByTestId('tab-audit')).toBeInTheDocument();
    expect(screen.getByTestId('tab-global-audit')).toBeInTheDocument();
  });

  it('load versions btn disabled when flow-id empty', () => {
    renderPage();
    expect(screen.getByTestId('load-versions-btn')).toBeDisabled();
  });

  it('loads versions and shows version items', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk({ items: VERSIONS }));
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.submit(screen.getByTestId('versions-form'));
    await waitFor(() => expect(screen.getByTestId('versions-list')).toBeInTheDocument());
    const items = screen.getAllByTestId('version-item');
    expect(items).toHaveLength(2);
    expect(items[0].textContent).toContain('ver-111');
  });

  it('shows versions-error on fetch failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(404, 'Flow not found'));
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'bad-id' } });
    fireEvent.submit(screen.getByTestId('versions-form'));
    await waitFor(() => expect(screen.getByTestId('versions-error')).toBeInTheDocument());
    expect(screen.getByTestId('versions-error').textContent).toContain('not found');
  });

  it('handles array response shape for versions', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(VERSIONS));
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.submit(screen.getByTestId('versions-form'));
    await waitFor(() => {
      const items = screen.getAllByTestId('version-item');
      expect(items).toHaveLength(2);
    });
  });

  it('clicking version item loads detail snapshot', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ items: VERSIONS }))
      .mockResolvedValueOnce(makeOk(VERSION_DETAIL));
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.submit(screen.getByTestId('versions-form'));
    await waitFor(() => screen.getByTestId('versions-list'));
    fireEvent.click(screen.getAllByTestId('version-item')[0]);
    await waitFor(() => expect(screen.getByTestId('version-detail')).toBeInTheDocument());
  });

  it('version detail shows detail-error on fetch failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ items: VERSIONS }))
      .mockResolvedValueOnce(makeErr(404, 'Version not found'));
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.submit(screen.getByTestId('versions-form'));
    await waitFor(() => screen.getByTestId('versions-list'));
    fireEvent.click(screen.getAllByTestId('version-item')[0]);
    await waitFor(() => expect(screen.getByTestId('detail-error')).toBeInTheDocument());
  });

  it('rollback btn disabled when version id empty', async () => {
    renderPage();
    expect(screen.getByTestId('rollback-btn')).toBeDisabled();
  });

  it('rollback shows rollback-result with rolled_back_to', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(ROLLBACK_RESULT));
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.change(screen.getByTestId('rollback-version-id-input'), {
      target: { value: 'ver-111' },
    });
    fireEvent.submit(screen.getByTestId('rollback-form'));
    await waitFor(() => expect(screen.getByTestId('rollback-result')).toBeInTheDocument());
    expect(screen.getByTestId('rolled-back-to').textContent).toBe('ver-111');
  });

  it('rollback shows rollback-error on failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(404, 'Version not found'));
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.change(screen.getByTestId('rollback-version-id-input'), {
      target: { value: 'ver-bad' },
    });
    fireEvent.submit(screen.getByTestId('rollback-form'));
    await waitFor(() => expect(screen.getByTestId('rollback-error')).toBeInTheDocument());
    expect(screen.getByTestId('rollback-error').textContent).toContain('not found');
  });

  it('audit tab loads and shows audit rows', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk({ items: AUDIT_ENTRIES }));
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.click(screen.getByTestId('tab-audit'));
    fireEvent.submit(screen.getByTestId('audit-form'));
    await waitFor(() => expect(screen.getByTestId('audit-table')).toBeInTheDocument());
    const rows = screen.getAllByTestId('audit-row');
    expect(rows).toHaveLength(1);
    expect(rows[0].textContent).toContain('ver-111');
  });

  it('audit tab shows audit-error on failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(404, 'Flow not found'));
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'bad-id' } });
    fireEvent.click(screen.getByTestId('tab-audit'));
    fireEvent.submit(screen.getByTestId('audit-form'));
    await waitFor(() => expect(screen.getByTestId('audit-error')).toBeInTheDocument());
  });

  it('audit tab shows no-audit when empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk({ items: [] }));
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.click(screen.getByTestId('tab-audit'));
    fireEvent.submit(screen.getByTestId('audit-form'));
    await waitFor(() => expect(screen.getByTestId('no-audit')).toBeInTheDocument());
  });

  it('global audit tab loads and shows global rows', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk({ items: GLOBAL_ENTRIES }));
    renderPage();
    fireEvent.click(screen.getByTestId('tab-global-audit'));
    fireEvent.click(screen.getByTestId('load-global-btn'));
    await waitFor(() => expect(screen.getByTestId('global-table')).toBeInTheDocument());
    const rows = screen.getAllByTestId('global-row');
    expect(rows).toHaveLength(2);
  });

  it('global audit shows global-error on failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(500, 'Internal error'));
    renderPage();
    fireEvent.click(screen.getByTestId('tab-global-audit'));
    fireEvent.click(screen.getByTestId('load-global-btn'));
    await waitFor(() => expect(screen.getByTestId('global-error')).toBeInTheDocument());
  });

  it('global audit shows no-global when empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk({ items: [] }));
    renderPage();
    fireEvent.click(screen.getByTestId('tab-global-audit'));
    fireEvent.click(screen.getByTestId('load-global-btn'));
    await waitFor(() => expect(screen.getByTestId('no-global')).toBeInTheDocument());
  });
});
