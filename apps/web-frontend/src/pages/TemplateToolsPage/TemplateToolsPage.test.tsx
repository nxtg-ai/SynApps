/**
 * Unit tests for TemplateToolsPage (N-103).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import TemplateToolsPage from './TemplateToolsPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <TemplateToolsPage />
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

describe('TemplateToolsPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title and all four sections', () => {
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
    expect(screen.getByTestId('validate-section')).toBeInTheDocument();
    expect(screen.getByTestId('semver-section')).toBeInTheDocument();
    expect(screen.getByTestId('rollback-section')).toBeInTheDocument();
    expect(screen.getByTestId('run-async-section')).toBeInTheDocument();
  });

  // ---- Validate ----

  it('submits validate and shows valid result', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeOk({ valid: true, errors: [], warnings: [] }));
    renderPage();
    fireEvent.change(screen.getByTestId('validate-json-input'), {
      target: { value: '{"name":"T1","nodes":[],"edges":[]}' },
    });
    fireEvent.submit(screen.getByTestId('validate-form'));
    await waitFor(() => expect(screen.getByTestId('validate-result')).toBeInTheDocument());
    expect(screen.getByTestId('validate-valid').textContent).toContain('Valid');
  });

  it('shows invalid validate result with errors', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      makeOk({ valid: false, errors: ['No start node', 'No end node'] }),
    );
    renderPage();
    fireEvent.change(screen.getByTestId('validate-json-input'), {
      target: { value: '{"nodes":[]}' },
    });
    fireEvent.submit(screen.getByTestId('validate-form'));
    await waitFor(() => expect(screen.getByTestId('validate-result')).toBeInTheDocument());
    expect(screen.getByTestId('validate-valid').textContent).toContain('Invalid');
    expect(screen.getByTestId('validate-errors').textContent).toContain('No start node');
  });

  it('shows validate-error on invalid JSON input', async () => {
    renderPage();
    fireEvent.change(screen.getByTestId('validate-json-input'), {
      target: { value: 'not json' },
    });
    fireEvent.submit(screen.getByTestId('validate-form'));
    await waitFor(() => expect(screen.getByTestId('validate-error')).toBeInTheDocument());
    expect(screen.getByTestId('validate-error').textContent).toContain('Invalid JSON');
  });

  it('shows validate-error on API failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(422, 'Validation failed'));
    renderPage();
    fireEvent.change(screen.getByTestId('validate-json-input'), { target: { value: '{}' } });
    fireEvent.submit(screen.getByTestId('validate-form'));
    await waitFor(() => expect(screen.getByTestId('validate-error')).toBeInTheDocument());
    expect(screen.getByTestId('validate-error').textContent).toContain('Validation failed');
  });

  // ---- By semver ----

  it('semver-btn disabled when template id is empty', () => {
    renderPage();
    expect(screen.getByTestId('semver-btn')).toBeDisabled();
  });

  it('fetches template by semver and shows result', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      makeOk({ id: 'tpl-1', name: 'My Template', semver: '1.2.3', version: 3 }),
    );
    renderPage();
    fireEvent.change(screen.getByTestId('semver-template-id-input'), {
      target: { value: 'tpl-1' },
    });
    fireEvent.change(screen.getByTestId('semver-version-input'), {
      target: { value: '1.2.3' },
    });
    fireEvent.submit(screen.getByTestId('semver-form'));
    await waitFor(() => expect(screen.getByTestId('semver-result')).toBeInTheDocument());
    expect(screen.getByTestId('semver-result-name').textContent).toBe('My Template');
    expect(screen.getByTestId('semver-result-semver').textContent).toBe('1.2.3');
  });

  it('shows semver-error on 404', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(404, 'Template not found'));
    renderPage();
    fireEvent.change(screen.getByTestId('semver-template-id-input'), {
      target: { value: 'bad-id' },
    });
    fireEvent.submit(screen.getByTestId('semver-form'));
    await waitFor(() => expect(screen.getByTestId('semver-error')).toBeInTheDocument());
    expect(screen.getByTestId('semver-error').textContent).toContain('not found');
  });

  it('omits version param when blank for latest', async () => {
    let capturedUrl = '';
    vi.mocked(fetch).mockImplementationOnce(async (url) => {
      capturedUrl = String(url);
      return makeOk({ id: 'tpl-1', name: 'T', semver: '2.0.0', version: 5 });
    });
    renderPage();
    fireEvent.change(screen.getByTestId('semver-template-id-input'), {
      target: { value: 'tpl-1' },
    });
    // leave version blank
    fireEvent.submit(screen.getByTestId('semver-form'));
    await waitFor(() => screen.getByTestId('semver-result'));
    expect(capturedUrl).not.toContain('version=');
  });

  // ---- Rollback ----

  it('rollback-btn disabled when template id or version empty', () => {
    renderPage();
    expect(screen.getByTestId('rollback-btn')).toBeDisabled();
  });

  it('rolls back and shows rollback-result with new semver', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      makeOk({ id: 'tpl-1', semver: '1.0.1', version: 4 }),
    );
    renderPage();
    fireEvent.change(screen.getByTestId('rollback-template-id-input'), {
      target: { value: 'tpl-1' },
    });
    fireEvent.change(screen.getByTestId('rollback-version-input'), {
      target: { value: '1.0.0' },
    });
    fireEvent.submit(screen.getByTestId('rollback-form'));
    await waitFor(() => expect(screen.getByTestId('rollback-result')).toBeInTheDocument());
    expect(screen.getByTestId('rollback-new-semver').textContent).toBe('1.0.1');
  });

  it('shows rollback-error on failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(404, 'Version not found'));
    renderPage();
    fireEvent.change(screen.getByTestId('rollback-template-id-input'), {
      target: { value: 'tpl-1' },
    });
    fireEvent.change(screen.getByTestId('rollback-version-input'), {
      target: { value: '9.9.9' },
    });
    fireEvent.submit(screen.getByTestId('rollback-form'));
    await waitFor(() => expect(screen.getByTestId('rollback-error')).toBeInTheDocument());
    expect(screen.getByTestId('rollback-error').textContent).toContain('not found');
  });

  // ---- Run async ----

  it('run-async-btn disabled when template id is empty', () => {
    renderPage();
    expect(screen.getByTestId('run-async-btn')).toBeDisabled();
  });

  it('runs async and shows task-created with task-id', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      makeOk({ task_id: 'task-xyz-789', status: 'pending' }),
    );
    renderPage();
    fireEvent.change(screen.getByTestId('run-template-id-input'), {
      target: { value: 'tpl-1' },
    });
    fireEvent.submit(screen.getByTestId('run-async-form'));
    await waitFor(() => expect(screen.getByTestId('task-created')).toBeInTheDocument());
    expect(screen.getByTestId('task-id').textContent).toContain('task-xyz-789');
  });

  it('shows run-error on invalid JSON input', async () => {
    renderPage();
    fireEvent.change(screen.getByTestId('run-template-id-input'), {
      target: { value: 'tpl-1' },
    });
    fireEvent.change(screen.getByTestId('run-input-json'), {
      target: { value: 'not json' },
    });
    fireEvent.submit(screen.getByTestId('run-async-form'));
    await waitFor(() => expect(screen.getByTestId('run-error')).toBeInTheDocument());
    expect(screen.getByTestId('run-error').textContent).toContain('Invalid JSON');
  });

  it('shows run-error on API failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(makeErr(404, 'Template not found'));
    renderPage();
    fireEvent.change(screen.getByTestId('run-template-id-input'), {
      target: { value: 'bad-tpl' },
    });
    fireEvent.submit(screen.getByTestId('run-async-form'));
    await waitFor(() => expect(screen.getByTestId('run-error')).toBeInTheDocument());
    expect(screen.getByTestId('run-error').textContent).toContain('not found');
  });

  it('polls task status and shows task-status', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ task_id: 'task-abc', status: 'pending' }))
      .mockResolvedValueOnce(
        makeOk({ task_id: 'task-abc', status: 'completed', result: { output: 'done' } }),
      );
    renderPage();
    fireEvent.change(screen.getByTestId('run-template-id-input'), {
      target: { value: 'tpl-1' },
    });
    fireEvent.submit(screen.getByTestId('run-async-form'));
    await waitFor(() => screen.getByTestId('task-created'));

    fireEvent.click(screen.getByTestId('poll-btn'));
    await waitFor(() => expect(screen.getByTestId('task-status')).toBeInTheDocument());
    expect(screen.getByTestId('task-status-value').textContent).toBe('completed');
  });

  it('shows poll-error on task poll failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(makeOk({ task_id: 'task-abc', status: 'pending' }))
      .mockResolvedValueOnce(makeErr(404, 'Task not found'));
    renderPage();
    fireEvent.change(screen.getByTestId('run-template-id-input'), {
      target: { value: 'tpl-1' },
    });
    fireEvent.submit(screen.getByTestId('run-async-form'));
    await waitFor(() => screen.getByTestId('task-created'));

    fireEvent.click(screen.getByTestId('poll-btn'));
    await waitFor(() => expect(screen.getByTestId('poll-error')).toBeInTheDocument());
    expect(screen.getByTestId('poll-error').textContent).toContain('not found');
  });
});
