/**
 * Tests for ApiKeyManagerPage -- N-63 API Key Management UI.
 *
 * Covers: page title, loading state, key list rendering, masked keys,
 * create form, create submission, revealed key display, delete button,
 * delete confirmation flow, empty state, error handling, copy button.
 */
import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, afterEach } from 'vitest';
import ApiKeyManagerPage from './ApiKeyManagerPage';

// ---------------------------------------------------------------------------
// Mock MainLayout
// ---------------------------------------------------------------------------

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="main-layout">{children}</div>
  ),
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeKey(
  overrides: Partial<{
    id: string;
    name: string;
    key_prefix: string;
    is_active: boolean;
    created_at: number;
    last_used_at: number | null;
  }> = {},
) {
  return {
    id: 'key-1',
    name: 'Test Key',
    key_prefix: 'synapps_abcdefghij',
    is_active: true,
    created_at: Date.now() / 1000,
    last_used_at: null,
    ...overrides,
  };
}

function mockFetchKeys(items: ReturnType<typeof makeKey>[] = [makeKey()]) {
  vi.spyOn(global, 'fetch').mockResolvedValue(
    new Response(JSON.stringify({ items, total: items.length, page: 1, page_size: 20 }), {
      status: 200,
    }),
  );
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ApiKeyManagerPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ApiKeyManagerPage', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders page title', async () => {
    mockFetchKeys();
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('page-title')).toBeInTheDocument();
      expect(screen.getByTestId('page-title').textContent).toBe('API Key Management');
    });
  });

  it('shows loading state initially', () => {
    vi.spyOn(global, 'fetch').mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByLabelText('Loading API keys')).toBeInTheDocument();
  });

  it('renders key list after fetch (Gate 2: at least 1 item)', async () => {
    const items = [
      makeKey({ id: 'k1', name: 'Key Alpha' }),
      makeKey({ id: 'k2', name: 'Key Beta' }),
    ];
    mockFetchKeys(items);
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('keys-table')).toBeInTheDocument();
      const rows = screen.getAllByTestId('key-row');
      expect(rows.length).toBeGreaterThanOrEqual(1); // Gate 2
      expect(rows.length).toBe(2);
    });
  });

  it('shows masked key value (not full key)', async () => {
    mockFetchKeys([makeKey({ key_prefix: 'synapps_abcdefghijklmnop' })]);
    renderPage();
    await waitFor(() => {
      const masked = screen.getByTestId('masked-key');
      expect(masked.textContent).toContain('...');
      // Should not contain the full prefix
      expect(masked.textContent).not.toBe('synapps_abcdefghijklmnop');
    });
  });

  it('create form has name input', async () => {
    mockFetchKeys([]);
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('key-name-input')).toBeInTheDocument();
      expect(screen.getByLabelText('Key Name')).toBeInTheDocument();
    });
  });

  it('create form has submit button', async () => {
    mockFetchKeys([]);
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('create-btn')).toBeInTheDocument();
      expect(screen.getByTestId('create-btn').textContent).toBe('Create Key');
    });
  });

  it('submit create form calls POST endpoint', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch');
    // First call: list keys (empty)
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ items: [], total: 0 }), { status: 200 }),
    );

    renderPage();
    await waitFor(() => screen.getByTestId('create-form'));

    // Mock create response
    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          id: 'new-1',
          name: 'My Key',
          key_prefix: 'synapps_xyz123',
          is_active: true,
          created_at: Date.now() / 1000,
          last_used_at: null,
          api_key: 'synapps_full_secret_key_value',
        }),
        { status: 201 },
      ),
    );
    // Mock the re-fetch after create
    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({ items: [makeKey({ id: 'new-1', name: 'My Key' })], total: 1 }),
        { status: 200 },
      ),
    );

    fireEvent.change(screen.getByTestId('key-name-input'), { target: { value: 'My Key' } });
    fireEvent.submit(screen.getByTestId('create-form'));

    await waitFor(() => {
      const postCall = fetchSpy.mock.calls.find(
        (c) =>
          typeof c[1] === 'object' &&
          c[1] !== null &&
          'method' in c[1] &&
          c[1].method === 'POST',
      );
      expect(postCall).toBeTruthy();
      expect(typeof postCall![0] === 'string' && postCall![0].includes('/auth/api-keys')).toBe(
        true,
      );
    });
  });

  it('on create success shows the generated key once', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch');
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ items: [], total: 0 }), { status: 200 }),
    );

    renderPage();
    await waitFor(() => screen.getByTestId('create-form'));

    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          id: 'new-2',
          name: 'Revealed Key',
          key_prefix: 'synapps_abc',
          is_active: true,
          created_at: Date.now() / 1000,
          last_used_at: null,
          api_key: 'synapps_FULL_SECRET_VALUE_12345',
        }),
        { status: 201 },
      ),
    );
    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({ items: [makeKey({ id: 'new-2' })], total: 1 }),
        { status: 200 },
      ),
    );

    fireEvent.change(screen.getByTestId('key-name-input'), { target: { value: 'Revealed Key' } });
    fireEvent.submit(screen.getByTestId('create-form'));

    await waitFor(() => {
      expect(screen.getByTestId('revealed-key-banner')).toBeInTheDocument();
      expect(screen.getByTestId('revealed-key-value').textContent).toBe(
        'synapps_FULL_SECRET_VALUE_12345',
      );
    });
  });

  it('delete button exists per row', async () => {
    mockFetchKeys([
      makeKey({ id: 'k1', name: 'Key One' }),
      makeKey({ id: 'k2', name: 'Key Two' }),
    ]);
    renderPage();
    await waitFor(() => {
      const deleteButtons = screen.getAllByTestId('delete-btn');
      expect(deleteButtons.length).toBe(2);
    });
  });

  it('clicking delete shows confirmation then calls DELETE endpoint', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch');
    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({ items: [makeKey({ id: 'k-del' })], total: 1 }),
        { status: 200 },
      ),
    );

    renderPage();
    await waitFor(() => screen.getByTestId('delete-btn'));

    // Click delete button -- should show confirmation
    fireEvent.click(screen.getByTestId('delete-btn'));
    expect(screen.getByTestId('confirm-delete-btn')).toBeInTheDocument();
    expect(screen.getByTestId('cancel-delete-btn')).toBeInTheDocument();

    // Confirm delete
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ message: 'API key revoked' }), { status: 200 }),
    );
    fireEvent.click(screen.getByTestId('confirm-delete-btn'));

    await waitFor(() => {
      const deleteCall = fetchSpy.mock.calls.find(
        (c) =>
          typeof c[1] === 'object' &&
          c[1] !== null &&
          'method' in c[1] &&
          c[1].method === 'DELETE',
      );
      expect(deleteCall).toBeTruthy();
      expect(typeof deleteCall![0] === 'string' && deleteCall![0].includes('/auth/api-keys/k-del')).toBe(true);
    });
  });

  it('on delete success removes row', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch');
    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          items: [
            makeKey({ id: 'stay', name: 'Stay' }),
            makeKey({ id: 'go', name: 'Go' }),
          ],
          total: 2,
        }),
        { status: 200 },
      ),
    );

    renderPage();
    await waitFor(() => {
      expect(screen.getAllByTestId('key-row').length).toBe(2);
    });

    // Click delete on second row
    const deleteButtons = screen.getAllByTestId('delete-btn');
    fireEvent.click(deleteButtons[1]);

    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ message: 'API key revoked' }), { status: 200 }),
    );
    fireEvent.click(screen.getByTestId('confirm-delete-btn'));

    await waitFor(() => {
      expect(screen.getAllByTestId('key-row').length).toBe(1);
    });
  });

  it('empty state message when no keys', async () => {
    mockFetchKeys([]);
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
      expect(screen.getByTestId('empty-state').textContent).toContain('No API keys yet');
    });
  });

  it('copy button appears alongside revealed key', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch');
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ items: [], total: 0 }), { status: 200 }),
    );

    renderPage();
    await waitFor(() => screen.getByTestId('create-form'));

    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          id: 'cp-1',
          name: 'Copy Test',
          key_prefix: 'synapps_cp',
          is_active: true,
          created_at: Date.now() / 1000,
          last_used_at: null,
          api_key: 'synapps_copy_me',
        }),
        { status: 201 },
      ),
    );
    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({ items: [makeKey({ id: 'cp-1' })], total: 1 }),
        { status: 200 },
      ),
    );

    fireEvent.change(screen.getByTestId('key-name-input'), { target: { value: 'Copy Test' } });
    fireEvent.submit(screen.getByTestId('create-form'));

    await waitFor(() => {
      expect(screen.getByTestId('copy-key-btn')).toBeInTheDocument();
      expect(screen.getByTestId('copy-key-btn').textContent).toBe('Copy');
    });
  });

  it('shows error banner on fetch failure', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(null, { status: 500 }),
    );
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('error-banner')).toBeInTheDocument();
      expect(screen.getByTestId('error-banner').textContent).toContain('Failed to load');
    });
  });
});
