/**
 * GalleryPage unit tests
 *
 * Covers: search debounce, category filter toggling, install flow (success +
 * error), empty state, load-more visibility, star rating derivation, node
 * preview rendering.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// MainLayout renders children directly to keep tests focused on GalleryPage
vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="main-layout">{children}</div>
  ),
}));

// Stable fake listing factory
function makeListing(overrides: Partial<{
  id: string;
  name: string;
  description: string;
  category: string;
  tags: string[];
  install_count: number;
  nodes: Array<{ id: string; type?: string }>;
  featured: boolean;
  published_at: number;
}> = {}) {
  return {
    id: overrides.id ?? 'listing-1',
    name: overrides.name ?? 'Test Workflow',
    description: overrides.description ?? 'A test workflow description',
    category: overrides.category ?? 'automation',
    tags: overrides.tags ?? ['tag1', 'tag2'],
    author: 'tester',
    nodes: overrides.nodes ?? [{ id: 'n1', type: 'llm' }, { id: 'n2', type: 'http' }],
    edges: [],
    install_count: overrides.install_count ?? 10,
    featured: overrides.featured ?? false,
    published_at: overrides.published_at ?? 1_700_000_000,
  };
}

function makeSearchResponse(items: ReturnType<typeof makeListing>[], total?: number) {
  return {
    items,
    total: total ?? items.length,
    page: 1,
    per_page: 12,
  };
}

const mockFetch = vi.fn();

beforeEach(() => {
  vi.useFakeTimers();
  mockFetch.mockReset();
  global.fetch = mockFetch;
  // Suppress console.error for expected API errors in tests
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

// Helper: import GalleryPage lazily so mocks are in place
async function importPage() {
  const mod = await import('./GalleryPage');
  return mod.default;
}

function renderPage(Page: React.ComponentType) {
  return render(
    <MemoryRouter>
      <Page />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('GalleryPage', () => {
  describe('initial load', () => {
    it('renders the hero title', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => makeSearchResponse([]),
      });

      const Page = await importPage();
      renderPage(Page);

      // Advance debounce timer
      await act(async () => {
        vi.runAllTimers();
      });

      await waitFor(() => {
        expect(screen.getByText('Discover & Install Workflows')).toBeInTheDocument();
      });
    });

    it('shows loading spinner while fetching', async () => {
      // Never resolves during this test
      mockFetch.mockReturnValueOnce(new Promise(() => undefined));

      const Page = await importPage();
      renderPage(Page);

      await act(async () => {
        vi.runAllTimers();
      });

      expect(screen.getByText('Loading workflows...')).toBeInTheDocument();
    });

    it('renders listing cards when data arrives', async () => {
      const listing = makeListing({ name: 'My Automation' });
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => makeSearchResponse([listing]),
      });

      const Page = await importPage();
      renderPage(Page);

      await act(async () => {
        vi.runAllTimers();
      });

      await waitFor(() => {
        expect(screen.getByText('My Automation')).toBeInTheDocument();
      });
    });

    it('shows empty state when no listings', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => makeSearchResponse([]),
      });

      const Page = await importPage();
      renderPage(Page);

      await act(async () => {
        vi.runAllTimers();
      });

      await waitFor(() => {
        expect(screen.getByText('No workflows found')).toBeInTheDocument();
      });
    });
  });

  describe('search', () => {
    it('fires API call with q param after debounce', async () => {
      // First call: initial load
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => makeSearchResponse([]),
      });
      // Second call: after search
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => makeSearchResponse([makeListing({ name: 'LLM Pipeline' })]),
      });

      const Page = await importPage();
      renderPage(Page);

      // Settle initial load
      await act(async () => { vi.runAllTimers(); });
      await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));

      const input = screen.getByRole('searchbox');
      fireEvent.change(input, { target: { value: 'llm' } });

      // Advance debounce (400 ms)
      await act(async () => { vi.advanceTimersByTime(500); });
      await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(2));

      const secondCall = mockFetch.mock.calls[1][0] as string;
      expect(secondCall).toContain('q=llm');
    });
  });

  describe('category filter', () => {
    it('toggles a category pill active/inactive', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => makeSearchResponse([]),
      });

      const Page = await importPage();
      renderPage(Page);

      await act(async () => { vi.runAllTimers(); });
      await waitFor(() => screen.getByText('Discover & Install Workflows'));

      const automationBtn = screen.getByRole('button', { name: /automation/i });
      expect(automationBtn).toHaveAttribute('aria-pressed', 'false');

      // Second fetch triggered by category change
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => makeSearchResponse([]),
      });

      fireEvent.click(automationBtn);
      await act(async () => { vi.runAllTimers(); });

      expect(automationBtn).toHaveAttribute('aria-pressed', 'true');
    });

    it('renders Clear filters button when a category is selected', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => makeSearchResponse([]),
      });

      const Page = await importPage();
      renderPage(Page);

      await act(async () => { vi.runAllTimers(); });
      await waitFor(() => screen.getByText('Discover & Install Workflows'));

      const automationBtn = screen.getByRole('button', { name: /automation/i });
      fireEvent.click(automationBtn);

      await act(async () => { vi.runAllTimers(); });

      // There may be multiple "Clear filters" elements (sidebar + empty-state CTA).
      // We just need at least one to be present.
      const clearBtns = screen.getAllByText('Clear filters');
      expect(clearBtns.length).toBeGreaterThanOrEqual(1);
    });
  });

  describe('install flow', () => {
    it('marks card as installed after successful install', async () => {
      const listing = makeListing({ id: 'abc-123', name: 'Pipeline Alpha' });
      mockFetch
        .mockResolvedValueOnce({ ok: true, json: async () => makeSearchResponse([listing]) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ flow_id: 'new-flow' }) });

      const Page = await importPage();
      renderPage(Page);

      await act(async () => { vi.runAllTimers(); });
      await waitFor(() => screen.getByText('Pipeline Alpha'));

      const installBtn = screen.getByRole('button', { name: /install pipeline alpha/i });
      fireEvent.click(installBtn);

      await act(async () => { vi.runAllTimers(); });

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /installed/i })).toBeDisabled();
      });
    });

    it('shows error toast on install failure', async () => {
      const listing = makeListing({ id: 'fail-id', name: 'Broken Pipeline' });
      mockFetch
        .mockResolvedValueOnce({ ok: true, json: async () => makeSearchResponse([listing]) })
        .mockResolvedValueOnce({ ok: false, text: async () => 'Not found' });

      const Page = await importPage();
      renderPage(Page);

      await act(async () => { vi.runAllTimers(); });
      await waitFor(() => screen.getByText('Broken Pipeline'));

      const installBtn = screen.getByRole('button', { name: /install broken pipeline/i });
      fireEvent.click(installBtn);

      await act(async () => { vi.runAllTimers(); });

      await waitFor(() => {
        // Error toast contains "API 0:" (0 because fetch mock returns ok:false, text:"Not found")
        expect(screen.getByText(/API/)).toBeInTheDocument();
      });
    });
  });

  describe('node preview', () => {
    it('renders node type badges for LLM and HTTP nodes', async () => {
      const listing = makeListing({
        nodes: [
          { id: 'n1', type: 'llm' },
          { id: 'n2', type: 'http' },
        ],
      });
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => makeSearchResponse([listing]),
      });

      const Page = await importPage();
      renderPage(Page);

      await act(async () => { vi.runAllTimers(); });
      await waitFor(() => screen.getByTitle('llm'));

      expect(screen.getByTitle('llm')).toBeInTheDocument();
      expect(screen.getByTitle('http')).toBeInTheDocument();
    });

    it('shows placeholder when no nodes', async () => {
      const listing = makeListing({ nodes: [] });
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => makeSearchResponse([listing]),
      });

      const Page = await importPage();
      renderPage(Page);

      await act(async () => { vi.runAllTimers(); });
      await waitFor(() => screen.getByText('No preview'));
    });
  });

  describe('load more', () => {
    it('shows Load More button when total > loaded count', async () => {
      const items = Array.from({ length: 12 }, (_, i) =>
        makeListing({ id: `id-${i}`, name: `Workflow ${i}` }),
      );
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => makeSearchResponse(items, 24), // 24 total, 12 loaded
      });

      const Page = await importPage();
      renderPage(Page);

      await act(async () => { vi.runAllTimers(); });

      await waitFor(() => {
        expect(screen.getByText(/Load More/)).toBeInTheDocument();
      });
    });

    it('hides Load More button when all items loaded', async () => {
      const items = [makeListing()];
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => makeSearchResponse(items, 1),
      });

      const Page = await importPage();
      renderPage(Page);

      await act(async () => { vi.runAllTimers(); });

      await waitFor(() => screen.getByText('Test Workflow'));

      expect(screen.queryByText(/Load More/)).not.toBeInTheDocument();
    });
  });

  describe('star rating derivation', () => {
    it('gives min rating 3.5 for 0 installs', async () => {
      const listing = makeListing({ install_count: 0 });
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => makeSearchResponse([listing]),
      });

      const Page = await importPage();
      renderPage(Page);

      await act(async () => { vi.runAllTimers(); });

      await waitFor(() => {
        expect(screen.getByTitle('Rating: 3.5')).toBeInTheDocument();
      });
    });

    it('caps rating at 5.0 for high install counts', async () => {
      const listing = makeListing({ install_count: 9999 });
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => makeSearchResponse([listing]),
      });

      const Page = await importPage();
      renderPage(Page);

      await act(async () => { vi.runAllTimers(); });

      await waitFor(() => {
        expect(screen.getByTitle('Rating: 5.0')).toBeInTheDocument();
      });
    });
  });

  describe('tag overflow', () => {
    it('shows +N more when listing has >3 tags', async () => {
      // Use real timers for this test so waitFor/setInterval work correctly.
      vi.useRealTimers();

      const listing = makeListing({ tags: ['a', 'b', 'c', 'd', 'e'] });
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => makeSearchResponse([listing]),
      });

      const Page = await importPage();
      renderPage(Page);

      // Tags visible: a, b, c (3 max), overflow = d, e → shows "+2"
      await waitFor(
        () => {
          expect(screen.getByText('+2')).toBeInTheDocument();
        },
        { timeout: 3000 },
      );
    });
  });
});
