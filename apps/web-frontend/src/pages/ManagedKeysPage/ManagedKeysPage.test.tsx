/**
 * Unit tests for ManagedKeysPage (N-99).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import ManagedKeysPage from './ManagedKeysPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const KEYS_LIST = [
  {
    id: 'key-aaa',
    name: 'CI Integration Key',
    scopes: ['read', 'execute'],
    active: true,
    usage_count: 150,
  },
  {
    id: 'key-bbb',
    name: 'Read-Only Key',
    scopes: ['read'],
    active: false,
    usage_count: 0,
  },
];

const NEW_KEY = {
  id: 'key-new-123',
  name: 'New Key',
  scopes: ['read', 'write'],
  active: true,
  key_value: 'supersecretkeyvalue',
};

const KEY_DETAIL = {
  id: 'key-aaa',
  name: 'CI Integration Key',
  scopes: ['read', 'execute'],
  active: true,
  usage_count: 150,
};

const ROTATED_KEY = {
  id: 'key-aaa-rotated',
  name: 'CI Integration Key',
  scopes: ['read', 'execute'],
  active: true,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <ManagedKeysPage />
    </MemoryRouter>,
  );
}

function makeOk(body: unknown) {
  return { ok: true, json: async () => body } as Response;
}
function makeErr(status: number, detail: string) {
  return { ok: false, status, json: async () => ({ detail }) } as unknown as Response;
}

function setupMasterKey() {
  fireEvent.change(screen.getByTestId('master-key-input'), {
    target: { value: 'master-secret' },
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ManagedKeysPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title and master-key input', () => {
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
    expect(screen.getByTestId('master-key-input')).toBeInTheDocument();
  });

  it('create btn disabled when name or master key empty', async () => {
    renderPage();
    await waitFor(() => screen.getByTestId('create-form'));
    expect(screen.getByTestId('create-btn')).toBeDisabled();
  });

  it('loads keys after master key is entered', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk({ keys: KEYS_LIST }));
    renderPage();
    setupMasterKey();
    await waitFor(() => expect(screen.getByTestId('keys-table')).toBeInTheDocument());
    const rows = screen.getAllByTestId('key-row');
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain('CI Integration Key');
  });

  it('shows no-keys when list is empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk({ keys: [] }));
    renderPage();
    setupMasterKey();
    await waitFor(() => expect(screen.getByTestId('no-keys')).toBeInTheDocument());
  });

  it('shows list-error on fetch failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(403, 'Invalid master key'));
    renderPage();
    setupMasterKey();
    await waitFor(() => expect(screen.getByTestId('list-error')).toBeInTheDocument());
    expect(screen.getByTestId('list-error').textContent).toContain('Invalid master key');
  });

  it('handles array response shape for keys', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(KEYS_LIST));
    renderPage();
    setupMasterKey();
    await waitFor(() => {
      const rows = screen.getAllByTestId('key-row');
      expect(rows).toHaveLength(2);
    });
  });

  it('shows active/inactive status badges', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk({ keys: KEYS_LIST }));
    renderPage();
    setupMasterKey();
    await waitFor(() => screen.getByTestId('keys-table'));
    const badges = screen.getAllByTestId('key-status');
    expect(badges[0].textContent).toContain('active');
    expect(badges[1].textContent).toContain('inactive');
  });

  it('create shows create-success with new-key-id', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ keys: [] }))
      .mockResolvedValueOnce(makeOk(NEW_KEY));
    renderPage();
    setupMasterKey();
    await waitFor(() => screen.getByTestId('no-keys'));
    fireEvent.change(screen.getByTestId('create-name-input'), { target: { value: 'New Key' } });
    fireEvent.submit(screen.getByTestId('create-form'));
    await waitFor(() => expect(screen.getByTestId('create-success')).toBeInTheDocument());
    expect(screen.getByTestId('new-key-id').textContent).toContain('key-new-123');
    expect(screen.getByTestId('new-key-value').textContent).toContain('supersecretkeyvalue');
  });

  it('create shows create-error on failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ keys: [] }))
      .mockResolvedValueOnce(makeErr(422, 'Invalid scopes'));
    renderPage();
    setupMasterKey();
    await waitFor(() => screen.getByTestId('no-keys'));
    fireEvent.change(screen.getByTestId('create-name-input'), { target: { value: 'Bad Key' } });
    fireEvent.submit(screen.getByTestId('create-form'));
    await waitFor(() => expect(screen.getByTestId('create-error')).toBeInTheDocument());
    expect(screen.getByTestId('create-error').textContent).toContain('Invalid scopes');
  });

  it('clicking key name loads key detail', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ keys: KEYS_LIST }))
      .mockResolvedValueOnce(makeOk(KEY_DETAIL));
    renderPage();
    setupMasterKey();
    await waitFor(() => screen.getByTestId('keys-table'));
    fireEvent.click(screen.getAllByTestId('key-name-btn')[0]);
    await waitFor(() => expect(screen.getByTestId('key-detail')).toBeInTheDocument());
    expect(screen.getByTestId('detail-name').textContent).toContain('CI Integration Key');
    expect(screen.getByTestId('detail-usage-count').textContent).toBe('150');
  });

  it('shows detail-error on detail fetch failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ keys: KEYS_LIST }))
      .mockResolvedValueOnce(makeErr(404, 'Key not found'));
    renderPage();
    setupMasterKey();
    await waitFor(() => screen.getByTestId('keys-table'));
    fireEvent.click(screen.getAllByTestId('key-name-btn')[0]);
    await waitFor(() => expect(screen.getByTestId('detail-error')).toBeInTheDocument());
  });

  it('rotate shows rotate-result with rotated-id', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ keys: KEYS_LIST }))
      .mockResolvedValueOnce(makeOk(KEY_DETAIL))
      .mockResolvedValueOnce(makeOk(ROTATED_KEY));
    renderPage();
    setupMasterKey();
    await waitFor(() => screen.getByTestId('keys-table'));
    fireEvent.click(screen.getAllByTestId('key-name-btn')[0]);
    await waitFor(() => screen.getByTestId('rotate-form'));
    fireEvent.submit(screen.getByTestId('rotate-form'));
    await waitFor(() => expect(screen.getByTestId('rotate-result')).toBeInTheDocument());
    expect(screen.getByTestId('rotated-id').textContent).toContain('key-aaa-rotated');
  });

  it('rotate shows rotate-error on failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ keys: KEYS_LIST }))
      .mockResolvedValueOnce(makeOk(KEY_DETAIL))
      .mockResolvedValueOnce(makeErr(404, 'Key not found'));
    renderPage();
    setupMasterKey();
    await waitFor(() => screen.getByTestId('keys-table'));
    fireEvent.click(screen.getAllByTestId('key-name-btn')[0]);
    await waitFor(() => screen.getByTestId('rotate-form'));
    fireEvent.submit(screen.getByTestId('rotate-form'));
    await waitFor(() => expect(screen.getByTestId('rotate-error')).toBeInTheDocument());
  });

  it('revoke marks key as inactive in table', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ keys: KEYS_LIST }))
      .mockResolvedValueOnce(makeOk({ message: 'Key revoked', id: 'key-aaa' }));
    renderPage();
    setupMasterKey();
    await waitFor(() => screen.getByTestId('keys-table'));
    fireEvent.click(screen.getAllByTestId('revoke-btn')[0]);
    await waitFor(() => {
      const badges = screen.getAllByTestId('key-status');
      expect(badges[0].textContent).toContain('inactive');
    });
  });

  it('revoke shows action-error on failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ keys: KEYS_LIST }))
      .mockResolvedValueOnce(makeErr(404, 'Key not found'));
    renderPage();
    setupMasterKey();
    await waitFor(() => screen.getByTestId('keys-table'));
    fireEvent.click(screen.getAllByTestId('revoke-btn')[0]);
    await waitFor(() => expect(screen.getByTestId('action-error')).toBeInTheDocument());
  });

  it('delete removes key row', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ keys: KEYS_LIST }))
      .mockResolvedValueOnce(makeOk({ message: 'Key deleted', id: 'key-aaa' }));
    renderPage();
    setupMasterKey();
    await waitFor(() => screen.getByTestId('keys-table'));
    fireEvent.click(screen.getAllByTestId('delete-btn')[0]);
    await waitFor(() => {
      const rows = screen.getAllByTestId('key-row');
      expect(rows).toHaveLength(1);
    });
  });

  it('delete shows action-error on failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ keys: KEYS_LIST }))
      .mockResolvedValueOnce(makeErr(404, 'Key not found'));
    renderPage();
    setupMasterKey();
    await waitFor(() => screen.getByTestId('keys-table'));
    fireEvent.click(screen.getAllByTestId('delete-btn')[0]);
    await waitFor(() => expect(screen.getByTestId('action-error')).toBeInTheDocument());
  });

  it('refresh-btn reloads keys', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ keys: KEYS_LIST }))
      .mockResolvedValueOnce(makeOk({ keys: KEYS_LIST }));
    renderPage();
    setupMasterKey();
    await waitFor(() => expect(screen.getByTestId('refresh-btn')).not.toBeDisabled());
    fireEvent.click(screen.getByTestId('refresh-btn'));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.length).toBeGreaterThanOrEqual(2));
  });
});
