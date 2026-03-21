/**
 * Tests for PluginManagerPage -- N-60 Workflow Marketplace Plugin System.
 *
 * 12 tests covering: browse tab, loading, plugin cards, install, register form.
 */
import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import PluginManagerPage from './PluginManagerPage';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="main-layout">{children}</div>
  ),
}));

const mockFetch = vi.fn();

function makePlugin(overrides: Record<string, unknown> = {}) {
  return {
    id: 'p1',
    manifest: {
      name: 'slack-notifier',
      display_name: 'Slack Notifier',
      description: 'Send Slack messages',
      node_type: 'slack_notify',
      endpoint_url: 'http://localhost:9001',
      version: '1.0.0',
      author: 'community',
      tags: ['slack', 'notifications'],
      config_schema: {},
    },
    installed_at: 1700000000,
    install_count: 5,
    ...overrides,
  };
}

function pluginListResponse(plugins = [makePlugin()]) {
  return {
    ok: true,
    json: async () => ({ plugins, total: plugins.length }),
  };
}

function emptyListResponse() {
  return {
    ok: true,
    json: async () => ({ plugins: [], total: 0 }),
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <PluginManagerPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Setup / Teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.stubGlobal('fetch', mockFetch);
  mockFetch.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('PluginManagerPage', () => {
  // 1. renders "Plugin Manager" heading
  it('renders "Plugin Manager" heading', async () => {
    mockFetch.mockResolvedValueOnce(pluginListResponse());
    renderPage();
    expect(screen.getByText('Plugin Manager')).toBeInTheDocument();
  });

  // 2. shows "Browse Plugins" tab by default
  it('shows "Browse Plugins" tab by default', async () => {
    mockFetch.mockResolvedValueOnce(pluginListResponse());
    renderPage();
    const browseTab = screen.getByText('Browse Plugins');
    expect(browseTab).toBeInTheDocument();
    // Browse tab should be active (has indigo text class)
    expect(browseTab.className).toContain('text-indigo-400');
  });

  // 3. shows "Register Plugin" tab button
  it('shows "Register Plugin" tab button', async () => {
    mockFetch.mockResolvedValueOnce(pluginListResponse());
    renderPage();
    expect(screen.getByText('Register Plugin')).toBeInTheDocument();
  });

  // 4. shows loading state while fetching
  it('shows loading state while fetching', () => {
    // Never resolve the fetch -- stays in loading
    mockFetch.mockReturnValueOnce(new Promise(() => {}));
    renderPage();
    expect(screen.getByTestId('loading-spinner')).toBeInTheDocument();
    expect(screen.getByText('Loading plugins...')).toBeInTheDocument();
  });

  // 5. renders plugin card with display_name after fetch
  it('renders plugin card with display_name after fetch', async () => {
    mockFetch.mockResolvedValueOnce(pluginListResponse());
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Slack Notifier')).toBeInTheDocument();
    });
  });

  // 6. shows plugin node_type badge
  it('shows plugin node_type badge', async () => {
    mockFetch.mockResolvedValueOnce(pluginListResponse());
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('badge-p1')).toHaveTextContent('slack_notify');
    });
  });

  // 7. shows "No plugins registered yet" when list is empty
  it('shows "No plugins registered yet" when list is empty', async () => {
    mockFetch.mockResolvedValueOnce(emptyListResponse());
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('No plugins registered yet')).toBeInTheDocument();
    });
  });

  // 8. shows install button on each plugin card
  it('shows install button on each plugin card', async () => {
    mockFetch.mockResolvedValueOnce(pluginListResponse());
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Install')).toBeInTheDocument();
    });
  });

  // 9. calls install API when Install clicked and shows success
  it('calls install API when Install clicked and shows success', async () => {
    mockFetch.mockResolvedValueOnce(pluginListResponse());
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Install')).toBeInTheDocument();
    });

    // Mock install response + refetch
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({}) });
    mockFetch.mockResolvedValueOnce(pluginListResponse());

    fireEvent.click(screen.getByText('Install'));

    await waitFor(() => {
      expect(screen.getByText('Plugin installed successfully!')).toBeInTheDocument();
    });

    // Verify the install endpoint was called
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/plugins/p1/install'),
      expect.objectContaining({ method: 'POST' }),
    );
  });

  // 10. clicking "Register Plugin" tab shows form
  it('clicking "Register Plugin" tab shows form', async () => {
    mockFetch.mockResolvedValueOnce(pluginListResponse());
    renderPage();

    fireEvent.click(screen.getByText('Register Plugin'));

    expect(screen.getByLabelText('Name')).toBeInTheDocument();
    expect(screen.getByLabelText('Description')).toBeInTheDocument();
  });

  // 11. form has name, display_name, endpoint_url fields
  it('form has name, display_name, endpoint_url fields', async () => {
    mockFetch.mockResolvedValueOnce(pluginListResponse());
    renderPage();

    fireEvent.click(screen.getByText('Register Plugin'));

    expect(screen.getByLabelText('Name')).toBeInTheDocument();
    expect(screen.getByLabelText('Display Name')).toBeInTheDocument();
    expect(screen.getByLabelText('Endpoint URL')).toBeInTheDocument();
  });

  // 12. submitting form calls POST /api/v1/plugins and shows success message
  it('submitting form calls POST /api/v1/plugins and shows success message', async () => {
    // Initial fetch
    mockFetch.mockResolvedValueOnce(pluginListResponse());
    renderPage();

    fireEvent.click(screen.getByText('Register Plugin'));

    // Fill form
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'my-plugin' } });
    fireEvent.change(screen.getByLabelText('Display Name'), { target: { value: 'My Plugin' } });
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'A test plugin' } });
    fireEvent.change(screen.getByLabelText('Node Type'), { target: { value: 'custom_node' } });
    fireEvent.change(screen.getByLabelText('Endpoint URL'), {
      target: { value: 'http://localhost:9002' },
    });
    fireEvent.change(screen.getByLabelText('Author'), { target: { value: 'tester' } });
    fireEvent.change(screen.getByLabelText('Tags (comma-separated)'), {
      target: { value: 'test, demo' },
    });

    // Mock POST success + refetch after switch to browse
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ id: 'p2' }) });
    mockFetch.mockResolvedValueOnce(pluginListResponse());

    // The submit button is inside the form; use the form's submit button (type="submit")
    const submitBtn = screen.getAllByRole('button', { name: 'Register Plugin' }).find(
      (btn) => btn.getAttribute('type') === 'submit',
    )!;
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText('Plugin registered!')).toBeInTheDocument();
    });

    // Verify POST call
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/plugins'),
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"my-plugin"'),
      }),
    );
  });
});
