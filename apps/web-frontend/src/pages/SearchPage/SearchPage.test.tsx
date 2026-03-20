/**
 * SearchPage unit tests
 *
 * Covers: search input rendering, autocomplete fetch and selection, result
 * display, results-count, category/sort filters, empty state, URL param sync,
 * and error state.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="main-layout">{children}</div>
  ),
}));

function makeListing(
  overrides: Partial<{
    id: string;
    name: string;
    description: string;
    category: string;
    tags: string[];
    install_count: number;
    _score: number;
  }> = {},
) {
  return {
    id: overrides.id ?? 'listing-1',
    name: overrides.name ?? 'Test Workflow',
    description: overrides.description ?? 'A test description',
    category: overrides.category ?? 'automation',
    tags: overrides.tags ?? ['tag1'],
    author: 'tester',
    nodes: [],
    edges: [],
    install_count: overrides.install_count ?? 10,
    featured: false,
    is_featured: false,
    published_at: 1_700_000_000,
    avg_rating: 4.0,
    rating_count: 5,
    _score: overrides._score ?? 3.0,
  };
}

function makeSearchResponse(
  items: ReturnType<typeof makeListing>[],
  total?: number,
) {
  return {
    items,
    total: total ?? items.length,
    page: 1,
    per_page: 12,
    query: '',
    filters_applied: {},
  };
}

const mockFetch = vi.fn();

beforeEach(() => {
  vi.useFakeTimers();
  mockFetch.mockReset();
  global.fetch = mockFetch;
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

async function importPage() {
  const mod = await import('./SearchPage');
  return mod.default;
}

function renderPage(Page: React.ComponentType, initialRoute = '/search') {
  return render(
    <MemoryRouter initialEntries={[initialRoute]}>
      <Page />
    </MemoryRouter>,
  );
}

/** Set up default search response mock. */
function setupSearchMock(
  response = makeSearchResponse([]),
) {
  mockFetch.mockResolvedValueOnce({
    ok: true,
    json: async () => response,
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SearchPage', () => {
  it('renders search input', async () => {
    setupSearchMock();
    const Page = await importPage();
    renderPage(Page);

    await act(async () => {
      vi.runAllTimers();
    });

    expect(screen.getByTestId('search-input')).toBeInTheDocument();
  });

  it('typing triggers autocomplete fetch', async () => {
    // Initial search
    setupSearchMock();

    const Page = await importPage();
    renderPage(Page);

    await act(async () => {
      vi.runAllTimers();
    });

    // Mock autocomplete response
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ suggestions: ['LLM Pipeline', 'llm'] }),
    });

    const input = screen.getByTestId('search-input');
    fireEvent.change(input, { target: { value: 'llm' } });

    // Advance autocomplete debounce (200ms)
    await act(async () => {
      vi.advanceTimersByTime(250);
    });

    // The autocomplete fetch should have been called
    const autocompleteCalls = mockFetch.mock.calls.filter((call: unknown[]) =>
      (call[0] as string).includes('autocomplete'),
    );
    expect(autocompleteCalls.length).toBeGreaterThanOrEqual(1);
  });

  it('clicking autocomplete suggestion fills input', async () => {
    setupSearchMock();

    const Page = await importPage();
    renderPage(Page);

    await act(async () => {
      vi.runAllTimers();
    });

    // Mock autocomplete
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ suggestions: ['LLM Pipeline'] }),
    });

    const input = screen.getByTestId('search-input');
    fireEvent.change(input, { target: { value: 'llm' } });

    await act(async () => {
      vi.advanceTimersByTime(250);
    });

    await waitFor(() => {
      expect(screen.getByTestId('autocomplete-dropdown')).toBeInTheDocument();
    });

    // Mock the search that will happen after selecting
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => makeSearchResponse([makeListing({ name: 'LLM Pipeline' })]),
    });

    fireEvent.click(screen.getByTestId('autocomplete-item-0'));

    expect((input as HTMLInputElement).value).toBe('LLM Pipeline');
  });

  it('submit searches and shows results', async () => {
    const listing = makeListing({ name: 'AI Workflow' });
    setupSearchMock(makeSearchResponse([listing]));

    const Page = await importPage();
    renderPage(Page);

    await act(async () => {
      vi.runAllTimers();
    });

    await waitFor(() => {
      expect(screen.getByText('AI Workflow')).toBeInTheDocument();
    });
  });

  it('results-count reflects total', async () => {
    setupSearchMock(makeSearchResponse([makeListing()], 42));

    const Page = await importPage();
    renderPage(Page);

    await act(async () => {
      vi.runAllTimers();
    });

    await waitFor(() => {
      const countEl = screen.getByTestId('results-count');
      expect(countEl.textContent).toContain('42');
    });
  });

  it('category filter triggers re-search', async () => {
    setupSearchMock();

    const Page = await importPage();
    renderPage(Page);

    await act(async () => {
      vi.runAllTimers();
    });

    // Mock the re-search after category change
    setupSearchMock();

    const catSelect = screen.getByTestId('category-filter');
    fireEvent.change(catSelect, { target: { value: 'ai' } });

    await act(async () => {
      vi.runAllTimers();
    });

    // Should have fetched at least twice (initial + after category change)
    const searchCalls = mockFetch.mock.calls.filter(
      (call: unknown[]) =>
        (call[0] as string).includes('marketplace/search'),
    );
    expect(searchCalls.length).toBeGreaterThanOrEqual(2);
  });

  it('sort-by filter triggers re-search', async () => {
    setupSearchMock();

    const Page = await importPage();
    renderPage(Page);

    await act(async () => {
      vi.runAllTimers();
    });

    setupSearchMock();

    const sortSelect = screen.getByTestId('sort-by-filter');
    fireEvent.change(sortSelect, { target: { value: 'installs' } });

    await act(async () => {
      vi.runAllTimers();
    });

    const searchCalls = mockFetch.mock.calls.filter(
      (call: unknown[]) =>
        (call[0] as string).includes('marketplace/search'),
    );
    expect(searchCalls.length).toBeGreaterThanOrEqual(2);
  });

  it('shows empty state when no results', async () => {
    setupSearchMock(makeSearchResponse([]));

    const Page = await importPage();
    renderPage(Page);

    await act(async () => {
      vi.runAllTimers();
    });

    await waitFor(() => {
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    });
  });

  it('URL params pre-fill search box on mount', async () => {
    setupSearchMock();

    const Page = await importPage();
    renderPage(Page, '/search?q=hello');

    await act(async () => {
      vi.runAllTimers();
    });

    const input = screen.getByTestId('search-input') as HTMLInputElement;
    expect(input.value).toBe('hello');
  });

  it('shows error state on fetch failure', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      text: async () => 'Internal Server Error',
    });

    const Page = await importPage();
    renderPage(Page);

    await act(async () => {
      vi.runAllTimers();
    });

    await waitFor(() => {
      expect(screen.getByTestId('search-error')).toBeInTheDocument();
    });
  });
});
