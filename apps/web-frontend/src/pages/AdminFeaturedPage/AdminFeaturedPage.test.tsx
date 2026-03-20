/**
 * AdminFeaturedPage unit tests
 *
 * Covers: loading state, listing display, feature/unfeature buttons,
 * blurb input, featured count, empty state, error state.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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

function makeListing(overrides: Partial<{
  id: string;
  name: string;
  description: string;
  category: string;
  is_featured: boolean;
}> = {}) {
  return {
    id: overrides.id ?? 'listing-1',
    name: overrides.name ?? 'Test Listing',
    description: overrides.description ?? 'A test listing',
    category: overrides.category ?? 'automation',
    is_featured: overrides.is_featured ?? false,
  };
}

const mockFetch = vi.fn();

beforeEach(() => {
  mockFetch.mockReset();
  global.fetch = mockFetch;
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
});

afterEach(() => {
  vi.restoreAllMocks();
});

async function importPage() {
  const mod = await import('./AdminFeaturedPage');
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
 * Set up the 2 standard on-mount fetch calls: (1) search, (2) featured.
 */
function setupMountMocks(opts?: {
  listings?: ReturnType<typeof makeListing>[];
  featured?: Array<ReturnType<typeof makeListing> & { listing_id: string; blurb: string; featured_at: number; featured_by: string }>;
}) {
  const listings = opts?.listings ?? [];
  const featured = opts?.featured ?? [];
  // Call 1: search (Promise.all ordering — search first)
  mockFetch.mockResolvedValueOnce({
    ok: true,
    json: async () => ({ items: listings, total: listings.length, page: 1, per_page: 100 }),
  });
  // Call 2: featured
  mockFetch.mockResolvedValueOnce({
    ok: true,
    json: async () => ({ items: featured, total: featured.length }),
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('AdminFeaturedPage', () => {
  it('shows loading indicator on mount', async () => {
    // Never resolves
    mockFetch.mockReturnValue(new Promise(() => undefined));

    const Page = await importPage();
    renderPage(Page);

    expect(screen.getByTestId('loading-indicator')).toBeInTheDocument();
  });

  it('shows listings after data loads', async () => {
    const listing = makeListing({ name: 'My Flow' });
    setupMountMocks({ listings: [listing] });

    const Page = await importPage();
    renderPage(Page);

    await waitFor(() => {
      expect(screen.getByText('My Flow')).toBeInTheDocument();
    });
  });

  it('feature button calls POST API', async () => {
    const listing = makeListing({ id: 'lid-1', name: 'Feature Me' });
    setupMountMocks({ listings: [listing] });

    // Mock for the feature POST call
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ listing_id: 'lid-1', featured_at: 123, featured_by: 'admin', blurb: '' }),
    });

    const Page = await importPage();
    renderPage(Page);

    await waitFor(() => screen.getByText('Feature Me'));

    const featureBtn = screen.getByTestId('feature-btn');
    fireEvent.click(featureBtn);

    await waitFor(() => {
      // After featuring, the button should change to "Unfeature"
      expect(screen.getByTestId('unfeature-btn')).toBeInTheDocument();
    });

    // Verify the POST was called with the right path
    const postCall = mockFetch.mock.calls[2];
    expect(postCall[0]).toContain('/marketplace/lid-1/feature');
    expect(postCall[1].method).toBe('POST');
  });

  it('unfeature button calls DELETE API', async () => {
    const listing = makeListing({ id: 'lid-2', name: 'Unfeat Me' });
    const featured = {
      ...listing,
      listing_id: 'lid-2',
      blurb: 'Great flow',
      featured_at: 123,
      featured_by: 'admin',
    };
    setupMountMocks({ listings: [listing], featured: [featured] });

    // Mock for the DELETE call (204 No Content)
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 204,
      json: async () => ({}),
    });

    const Page = await importPage();
    renderPage(Page);

    await waitFor(() => screen.getByText('Unfeat Me'));

    const unfeatureBtn = screen.getByTestId('unfeature-btn');
    fireEvent.click(unfeatureBtn);

    await waitFor(() => {
      expect(screen.getByTestId('feature-btn')).toBeInTheDocument();
    });

    const deleteCall = mockFetch.mock.calls[2];
    expect(deleteCall[0]).toContain('/marketplace/lid-2/feature');
    expect(deleteCall[1].method).toBe('DELETE');
  });

  it('shows blurb input for non-featured listings', async () => {
    const listing = makeListing({ name: 'Blurb Test' });
    setupMountMocks({ listings: [listing] });

    const Page = await importPage();
    renderPage(Page);

    await waitFor(() => screen.getByText('Blurb Test'));

    const blurbInput = screen.getByTestId('blurb-input');
    expect(blurbInput).toBeInTheDocument();
    fireEvent.change(blurbInput, { target: { value: 'Top pick' } });
    expect(blurbInput).toHaveValue('Top pick');
  });

  it('shows featured count display', async () => {
    const listing = makeListing({ id: 'lid-3' });
    const featured = {
      ...listing,
      listing_id: 'lid-3',
      blurb: '',
      featured_at: 123,
      featured_by: 'admin',
    };
    setupMountMocks({ listings: [listing], featured: [featured] });

    const Page = await importPage();
    renderPage(Page);

    await waitFor(() => {
      const countEl = screen.getByTestId('featured-count');
      expect(countEl).toHaveTextContent('1');
    });
  });

  it('shows empty state when no listings exist', async () => {
    setupMountMocks({ listings: [] });

    const Page = await importPage();
    renderPage(Page);

    await waitFor(() => {
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    });
  });

  it('shows error state on API failure', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));

    const Page = await importPage();
    renderPage(Page);

    await waitFor(() => {
      expect(screen.getByTestId('error-message')).toBeInTheDocument();
    });
  });
});
