/**
 * Unit tests for WebhookRegistryPage (N-102).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import WebhookRegistryPage from './WebhookRegistryPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const HOOKS_LIST = [
  {
    id: 'hook-aaa',
    url: 'https://example.com/wh1',
    events: ['template_started', 'template_completed'],
  },
  {
    id: 'hook-bbb',
    url: 'https://example.com/wh2',
    events: ['step_failed'],
  },
];

const NEW_HOOK = {
  id: 'hook-new-999',
  url: 'https://example.com/new',
  events: ['template_started'],
};

function renderPage() {
  return render(
    <MemoryRouter>
      <WebhookRegistryPage />
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

describe('WebhookRegistryPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title', () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk({ webhooks: [], total: 0 }));
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
  });

  it('create-btn disabled when url or events empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk({ webhooks: [] }));
    renderPage();
    await waitFor(() => expect(screen.getByTestId('create-btn')).toBeDisabled());
  });

  it('loads and shows hook list on mount', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk({ webhooks: HOOKS_LIST }));
    renderPage();
    await waitFor(() => expect(screen.getByTestId('hooks-table')).toBeInTheDocument());
    const rows = screen.getAllByTestId('hook-row');
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain('https://example.com/wh1');
    expect(rows[0].textContent).toContain('template_started');
  });

  it('shows no-hooks when list is empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk({ webhooks: [] }));
    renderPage();
    await waitFor(() => expect(screen.getByTestId('no-hooks')).toBeInTheDocument());
  });

  it('handles array response shape', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk(HOOKS_LIST));
    renderPage();
    await waitFor(() => {
      const rows = screen.getAllByTestId('hook-row');
      expect(rows).toHaveLength(2);
    });
  });

  it('shows list-error on fetch failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(401, 'Unauthorized'));
    renderPage();
    await waitFor(() => expect(screen.getByTestId('list-error')).toBeInTheDocument());
    expect(screen.getByTestId('list-error').textContent).toContain('Unauthorized');
  });

  it('creates webhook and shows create-success with new-hook-id', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ webhooks: [] }))
      .mockResolvedValueOnce(makeOk(NEW_HOOK));
    renderPage();
    await waitFor(() => screen.getByTestId('no-hooks'));

    fireEvent.change(screen.getByTestId('create-url-input'), {
      target: { value: 'https://example.com/new' },
    });
    // Check one event
    fireEvent.click(screen.getByTestId('event-checkbox-template_started'));
    fireEvent.submit(screen.getByTestId('create-form'));

    await waitFor(() => expect(screen.getByTestId('create-success')).toBeInTheDocument());
    expect(screen.getByTestId('new-hook-id').textContent).toContain('hook-new-999');
    // Hook should appear in table
    expect(screen.getByTestId('hooks-table')).toBeInTheDocument();
  });

  it('shows create-error on failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ webhooks: [] }))
      .mockResolvedValueOnce(makeErr(422, 'Invalid events'));
    renderPage();
    await waitFor(() => screen.getByTestId('no-hooks'));

    fireEvent.change(screen.getByTestId('create-url-input'), {
      target: { value: 'https://example.com/fail' },
    });
    fireEvent.click(screen.getByTestId('event-checkbox-step_failed'));
    fireEvent.submit(screen.getByTestId('create-form'));

    await waitFor(() => expect(screen.getByTestId('create-error')).toBeInTheDocument());
    expect(screen.getByTestId('create-error').textContent).toContain('Invalid events');
  });

  it('create-btn disabled when events selected but URL empty', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk({ webhooks: [] }));
    renderPage();
    await waitFor(() => screen.getByTestId('no-hooks'));
    fireEvent.click(screen.getByTestId('event-checkbox-template_started'));
    expect(screen.getByTestId('create-btn')).toBeDisabled();
  });

  it('create-btn enabled when URL and at least one event selected', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk({ webhooks: [] }));
    renderPage();
    await waitFor(() => screen.getByTestId('no-hooks'));
    fireEvent.change(screen.getByTestId('create-url-input'), {
      target: { value: 'https://example.com/wh' },
    });
    fireEvent.click(screen.getByTestId('event-checkbox-template_started'));
    expect(screen.getByTestId('create-btn')).not.toBeDisabled();
  });

  it('delete removes hook row', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ webhooks: HOOKS_LIST }))
      .mockResolvedValueOnce(makeOk({ message: 'Webhook deleted', id: 'hook-aaa' }));
    renderPage();
    await waitFor(() => screen.getByTestId('hooks-table'));
    fireEvent.click(screen.getAllByTestId('delete-btn')[0]);
    await waitFor(() => {
      const rows = screen.getAllByTestId('hook-row');
      expect(rows).toHaveLength(1);
    });
  });

  it('delete shows delete-error on failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ webhooks: HOOKS_LIST }))
      .mockResolvedValueOnce(makeErr(404, 'Webhook not found'));
    renderPage();
    await waitFor(() => screen.getByTestId('hooks-table'));
    fireEvent.click(screen.getAllByTestId('delete-btn')[0]);
    await waitFor(() => expect(screen.getByTestId('delete-error')).toBeInTheDocument());
    expect(screen.getByTestId('delete-error').textContent).toContain('not found');
  });

  it('refresh-btn reloads hook list', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ webhooks: HOOKS_LIST }))
      .mockResolvedValueOnce(makeOk({ webhooks: HOOKS_LIST }));
    renderPage();
    await waitFor(() => expect(screen.getByTestId('refresh-btn')).not.toBeDisabled());
    fireEvent.click(screen.getByTestId('refresh-btn'));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.length).toBeGreaterThanOrEqual(2));
  });

  it('secret is included in create payload when provided', async () => {
    let capturedBody: Record<string, unknown> = {};
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ webhooks: [] }))
      .mockImplementationOnce(async (_url, opts) => {
        capturedBody = JSON.parse((opts?.body as string) ?? '{}');
        return makeOk(NEW_HOOK);
      });
    renderPage();
    await waitFor(() => screen.getByTestId('no-hooks'));
    fireEvent.change(screen.getByTestId('create-url-input'), {
      target: { value: 'https://example.com/sec' },
    });
    fireEvent.change(screen.getByTestId('create-secret-input'), {
      target: { value: 'my-secret' },
    });
    fireEvent.click(screen.getByTestId('event-checkbox-key.rotated'));
    fireEvent.submit(screen.getByTestId('create-form'));
    await waitFor(() => expect(screen.getByTestId('create-success')).toBeInTheDocument());
    expect(capturedBody.secret).toBe('my-secret');
  });
});
