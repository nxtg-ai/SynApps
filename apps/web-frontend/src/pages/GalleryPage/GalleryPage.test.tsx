/**
 * GalleryPage unit tests
 *
 * Covers: search debounce, category filter toggling, install flow (success +
 * error), empty state, load-more visibility, star rating derivation, node
 * preview rendering, featured hero section, featured badge on listing cards.
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
  is_featured: boolean;
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
    is_featured: overrides.is_featured ?? false,
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

/** Empty featured response — used as the default featured mock. */
const EMPTY_FEATURED = { items: [], total: 0 };

/** Empty trending response — used as the default trending mock. */
const EMPTY_TRENDING = { items: [], total: 0 };

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

/**
 * Set up the 3 standard on-mount fetch calls: (1) search, (2) trending, (3) featured.
 * Optionally override any of the three response bodies.
 */
function setupMountMocks(opts?: {
  search?: ReturnType<typeof makeSearchResponse>;
  trending?: { items: ReturnType<typeof makeListing>[]; total: number };
  featured?: { items: Record<string, unknown>[]; total: number };
}) {
  // Call 1: search listings
  mockFetch.mockResolvedValueOnce({
    ok: true,
    json: async () => opts?.search ?? makeSearchResponse([]),
  });
  // Call 2: trending
  mockFetch.mockResolvedValueOnce({
    ok: true,
    json: async () => opts?.trending ?? EMPTY_TRENDING,
  });
  // Call 3: featured
  mockFetch.mockResolvedValueOnce({
    ok: true,
    json: async () => opts?.featured ?? EMPTY_FEATURED,
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('GalleryPage', () => {
  describe('initial load', () => {
    it('renders the hero title', async () => {
      setupMountMocks();

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
      setupMountMocks({ search: makeSearchResponse([listing]) });

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
      setupMountMocks();

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
      // Call 1: initial listings load
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => makeSearchResponse([]),
      });
      // Call 2: trending
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => EMPTY_TRENDING,
      });
      // Call 3: featured
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => EMPTY_FEATURED,
      });
      // Call 4: after search
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => makeSearchResponse([makeListing({ name: 'LLM Pipeline' })]),
      });

      const Page = await importPage();
      renderPage(Page);

      // Settle initial load (listings + trending + featured)
      await act(async () => { vi.runAllTimers(); });
      await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(3));

      const input = screen.getByRole('searchbox');
      fireEvent.change(input, { target: { value: 'llm' } });

      // Advance debounce (400 ms)
      await act(async () => { vi.advanceTimersByTime(500); });
      await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(4));

      const searchCall = mockFetch.mock.calls[3][0] as string;
      expect(searchCall).toContain('q=llm');
    });
  });

  describe('category filter', () => {
    it('toggles a category pill active/inactive', async () => {
      setupMountMocks();

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
        .mockResolvedValueOnce({ ok: true, json: async () => EMPTY_TRENDING }) // trending
        .mockResolvedValueOnce({ ok: true, json: async () => EMPTY_FEATURED }) // featured
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
        .mockResolvedValueOnce({ ok: true, json: async () => EMPTY_TRENDING }) // trending
        .mockResolvedValueOnce({ ok: true, json: async () => EMPTY_FEATURED }) // featured
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
      setupMountMocks({ search: makeSearchResponse([listing]) });

      const Page = await importPage();
      renderPage(Page);

      await act(async () => { vi.runAllTimers(); });
      await waitFor(() => screen.getByTitle('llm'));

      expect(screen.getByTitle('llm')).toBeInTheDocument();
      expect(screen.getByTitle('http')).toBeInTheDocument();
    });

    it('shows placeholder when no nodes', async () => {
      const listing = makeListing({ nodes: [] });
      setupMountMocks({ search: makeSearchResponse([listing]) });

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
      setupMountMocks({ search: makeSearchResponse(items, 24) });

      const Page = await importPage();
      renderPage(Page);

      await act(async () => { vi.runAllTimers(); });

      await waitFor(() => {
        expect(screen.getByText(/Load More/)).toBeInTheDocument();
      });
    });

    it('hides Load More button when all items loaded', async () => {
      const items = [makeListing()];
      setupMountMocks({ search: makeSearchResponse(items, 1) });

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
      setupMountMocks({ search: makeSearchResponse([listing]) });

      const Page = await importPage();
      renderPage(Page);

      await act(async () => { vi.runAllTimers(); });

      await waitFor(() => {
        expect(screen.getByTitle('Rating: 3.5')).toBeInTheDocument();
      });
    });

    it('caps rating at 5.0 for high install counts', async () => {
      const listing = makeListing({ install_count: 9999 });
      setupMountMocks({ search: makeSearchResponse([listing]) });

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

  describe('featured section', () => {
    it('shows featured hero section when featured listings returned', async () => {
      const featuredListing = {
        ...makeListing({ id: 'feat-1', name: 'Amazing Workflow' }),
        blurb: 'Editor pick of the month',
        featured_at: 1_700_100_000,
        featured_by: 'admin-1',
        is_featured: true,
      };

      setupMountMocks({
        search: makeSearchResponse([]),
        featured: { items: [featuredListing], total: 1 },
      });

      const Page = await importPage();
      renderPage(Page);

      await act(async () => { vi.runAllTimers(); });

      await waitFor(() => {
        expect(screen.getByTestId('featured-hero-section')).toBeInTheDocument();
      });
      expect(screen.getByTestId('featured-hero-card')).toBeInTheDocument();
      expect(screen.getByText('Amazing Workflow')).toBeInTheDocument();
    });

    it('shows featured badge on featured listing card', async () => {
      const listing = makeListing({ id: 'feat-card', name: 'Featured Card', is_featured: true });

      setupMountMocks({
        search: makeSearchResponse([listing]),
      });

      const Page = await importPage();
      renderPage(Page);

      await act(async () => { vi.runAllTimers(); });

      await waitFor(() => {
        expect(screen.getByText('Featured Card')).toBeInTheDocument();
      });

      expect(screen.getByTestId('featured-badge')).toBeInTheDocument();
    });
  });
});
