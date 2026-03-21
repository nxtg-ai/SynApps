/**
 * Unit tests for AdminKeysPage (N-100).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import AdminKeysPage from './AdminKeysPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const KEYS_LIST = [
  {
    id: 'akey-aaa',
    name: 'CI Admin Key',
    scopes: ['read', 'write', 'admin'],
    rate_limit: 120,
  },
  {
    id: 'akey-bbb',
    name: 'Read Only',
    scopes: ['read'],
    rate_limit: null,
  },
];

const NEW_KEY = {
  id: 'akey-new-999',
  name: 'New Admin Key',
  scopes: ['read', 'write'],
  key_value: 'adminkey_secret_value',
};

function renderPage() {
  return render(
    <MemoryRouter>
      <AdminKeysPage />
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

describe('AdminKeysPage', () => {
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

  it('create btn disabled when name or master key empty', () => {
    renderPage();
    expect(screen.getByTestId('create-btn')).toBeDisabled();
  });

  it('loads keys after master key is entered', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk({ keys: KEYS_LIST }));
    renderPage();
    setupMasterKey();
    await waitFor(() => expect(screen.getByTestId('keys-table')).toBeInTheDocument());
    const rows = screen.getAllByTestId('key-row');
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain('CI Admin Key');
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

  it('handles array response shape', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(KEYS_LIST));
    renderPage();
    setupMasterKey();
    await waitFor(() => {
      const rows = screen.getAllByTestId('key-row');
      expect(rows).toHaveLength(2);
    });
  });

  it('shows scopes and rate limit in table', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk({ keys: KEYS_LIST }));
    renderPage();
    setupMasterKey();
    await waitFor(() => screen.getByTestId('keys-table'));
    const rows = screen.getAllByTestId('key-row');
    expect(rows[0].textContent).toContain('read, write, admin');
    expect(rows[0].textContent).toContain('120 rpm');
    expect(rows[1].textContent).toContain('default');
  });

  it('create shows create-success with new-key-id and new-key-value', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ keys: [] }))
      .mockResolvedValueOnce(makeOk(NEW_KEY));
    renderPage();
    setupMasterKey();
    await waitFor(() => screen.getByTestId('no-keys'));
    fireEvent.change(screen.getByTestId('create-name-input'), {
      target: { value: 'New Admin Key' },
    });
    fireEvent.submit(screen.getByTestId('create-form'));
    await waitFor(() => expect(screen.getByTestId('create-success')).toBeInTheDocument());
    expect(screen.getByTestId('new-key-id').textContent).toContain('akey-new-999');
    expect(screen.getByTestId('new-key-value').textContent).toContain('adminkey_secret_value');
  });

  it('create shows create-error on failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ keys: [] }))
      .mockResolvedValueOnce(makeErr(422, 'Invalid scopes'));
    renderPage();
    setupMasterKey();
    await waitFor(() => screen.getByTestId('no-keys'));
    fireEvent.change(screen.getByTestId('create-name-input'), { target: { value: 'Bad' } });
    fireEvent.submit(screen.getByTestId('create-form'));
    await waitFor(() => expect(screen.getByTestId('create-error')).toBeInTheDocument());
    expect(screen.getByTestId('create-error').textContent).toContain('Invalid scopes');
  });

  it('delete removes key row', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ keys: KEYS_LIST }))
      .mockResolvedValueOnce(makeOk({ message: 'Admin key deleted', id: 'akey-aaa' }));
    renderPage();
    setupMasterKey();
    await waitFor(() => screen.getByTestId('keys-table'));
    fireEvent.click(screen.getAllByTestId('delete-btn')[0]);
    await waitFor(() => {
      const rows = screen.getAllByTestId('key-row');
      expect(rows).toHaveLength(1);
    });
  });

  it('delete shows delete-error on failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ keys: KEYS_LIST }))
      .mockResolvedValueOnce(makeErr(404, 'Admin key not found'));
    renderPage();
    setupMasterKey();
    await waitFor(() => screen.getByTestId('keys-table'));
    fireEvent.click(screen.getAllByTestId('delete-btn')[0]);
    await waitFor(() => expect(screen.getByTestId('delete-error')).toBeInTheDocument());
    expect(screen.getByTestId('delete-error').textContent).toContain('not found');
  });

  it('refresh-btn reloads key list', async () => {
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
