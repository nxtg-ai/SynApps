import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import MarketplaceDiscoveryPage from './MarketplaceDiscoveryPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children, title }: { children: React.ReactNode; title: string }) => (
    <div data-testid="layout">
      <span data-testid="layout-title">{title}</span>
      {children}
    </div>
  ),
}));

const FEATURED_RESPONSE = {
  items: [
    { id: 'lst-1', name: 'Alpha Workflow', blurb: 'Best one', featured_at: '2026-03-01', is_featured: true },
    { id: 'lst-2', name: 'Beta Workflow', is_featured: true },
  ],
  total: 2,
};

const AUTOCOMPLETE_RESPONSE = {
  suggestions: [
    { id: 'lst-1', name: 'Alpha Workflow', type: 'template' },
    { id: 'lst-3', name: 'Alpha Node', type: 'plugin' },
  ],
};

const REPORT_RESPONSE = {
  issue_id: 'issue-abc',
  listing_id: 'lst-1',
  type: 'spam',
};

function makeOk(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response;
}

function makeCreated(body: unknown) {
  return { ok: true, status: 201, json: async () => body } as Response;
}

function makeErr(status: number, detail: string) {
  return { ok: false, status, json: async () => ({ detail }) } as Response;
}

function renderPage() {
  return render(
    <MemoryRouter>
      <MarketplaceDiscoveryPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn());
  window.localStorage.setItem('access_token', 'tok-test');
});

describe('MarketplaceDiscoveryPage', () => {
  // 1. Page title
  it('renders page title', () => {
    renderPage();
    expect(screen.getByTestId('page-title')).toHaveTextContent('Marketplace Discovery');
  });

  // 2. Three tabs present
  it('renders featured, autocomplete, report tabs', () => {
    renderPage();
    expect(screen.getByTestId('tab-featured')).toBeInTheDocument();
    expect(screen.getByTestId('tab-autocomplete')).toBeInTheDocument();
    expect(screen.getByTestId('tab-report')).toBeInTheDocument();
  });

  // 3. Featured tab default
  it('shows featured section by default', () => {
    renderPage();
    expect(screen.getByTestId('featured-section')).toBeInTheDocument();
  });

  // 4. Load Featured calls /marketplace/featured
  it('calls GET /marketplace/featured on load', async () => {
    const fetchMock = vi.fn().mockResolvedValue(makeOk(FEATURED_RESPONSE));
    vi.stubGlobal('fetch', fetchMock);
    renderPage();
    fireEvent.click(screen.getByTestId('load-featured-btn'));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/marketplace/featured'),
        expect.any(Object),
      ),
    );
  });

  // 5. Featured cards rendered
  it('renders featured listing cards', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(FEATURED_RESPONSE)));
    renderPage();
    fireEvent.click(screen.getByTestId('load-featured-btn'));
    await waitFor(() => {
      const cards = screen.getAllByTestId('featured-card');
      expect(cards.length).toBeGreaterThanOrEqual(1);
    });
  });

  // 6. Featured listing name shown
  it('displays featured listing names', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(FEATURED_RESPONSE)));
    renderPage();
    fireEvent.click(screen.getByTestId('load-featured-btn'));
    await waitFor(() => expect(screen.getByText('Alpha Workflow')).toBeInTheDocument());
    expect(screen.getByText('Beta Workflow')).toBeInTheDocument();
  });

  // 7. Featured error shown
  it('shows error on featured load failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeErr(500, 'Featured failed')));
    renderPage();
    fireEvent.click(screen.getByTestId('load-featured-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('featured-error')).toHaveTextContent('Featured failed'),
    );
  });

  // 8. Autocomplete tab switch
  it('switches to autocomplete tab', () => {
    renderPage();
    fireEvent.click(screen.getByTestId('tab-autocomplete'));
    expect(screen.getByTestId('autocomplete-section')).toBeInTheDocument();
  });

  // 9. Autocomplete search calls /marketplace/autocomplete
  it('calls GET /marketplace/autocomplete on search', async () => {
    const fetchMock = vi.fn().mockResolvedValue(makeOk(AUTOCOMPLETE_RESPONSE));
    vi.stubGlobal('fetch', fetchMock);
    renderPage();
    fireEvent.click(screen.getByTestId('tab-autocomplete'));
    fireEvent.change(screen.getByTestId('ac-query-input'), { target: { value: 'Alpha' } });
    fireEvent.click(screen.getByTestId('ac-search-btn'));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/marketplace/autocomplete'),
        expect.any(Object),
      ),
    );
  });

  // 10. Suggestions rendered
  it('renders suggestion items', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeOk(AUTOCOMPLETE_RESPONSE)));
    renderPage();
    fireEvent.click(screen.getByTestId('tab-autocomplete'));
    fireEvent.click(screen.getByTestId('ac-search-btn'));
    await waitFor(() => {
      const items = screen.getAllByTestId('suggestion-item');
      expect(items.length).toBeGreaterThanOrEqual(1);
    });
  });

  // 11. Report tab switch
  it('switches to report tab', () => {
    renderPage();
    fireEvent.click(screen.getByTestId('tab-report'));
    expect(screen.getByTestId('report-section')).toBeInTheDocument();
  });

  // 12. Report form submits POST /marketplace/{id}/report
  it('submits POST /marketplace/{id}/report', async () => {
    const fetchMock = vi.fn().mockResolvedValue(makeCreated(REPORT_RESPONSE));
    vi.stubGlobal('fetch', fetchMock);
    renderPage();
    fireEvent.click(screen.getByTestId('tab-report'));
    fireEvent.change(screen.getByTestId('report-listing-id-input'), { target: { value: 'lst-1' } });
    fireEvent.change(screen.getByTestId('report-description-input'), { target: { value: 'This is spam' } });
    fireEvent.click(screen.getByTestId('report-submit-btn'));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/marketplace/lst-1/report'),
        expect.objectContaining({ method: 'POST' }),
      ),
    );
  });

  // 13. Report success shows issue ID
  it('shows report success with issue ID', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeCreated(REPORT_RESPONSE)));
    renderPage();
    fireEvent.click(screen.getByTestId('tab-report'));
    fireEvent.change(screen.getByTestId('report-listing-id-input'), { target: { value: 'lst-1' } });
    fireEvent.click(screen.getByTestId('report-submit-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('report-result')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('report-issue-id')).toHaveTextContent('issue-abc');
  });

  // 14. Report error shown
  it('shows error on report failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeErr(403, 'Forbidden')));
    renderPage();
    fireEvent.click(screen.getByTestId('tab-report'));
    fireEvent.change(screen.getByTestId('report-listing-id-input'), { target: { value: 'lst-1' } });
    fireEvent.click(screen.getByTestId('report-submit-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('report-error')).toHaveTextContent('Forbidden'),
    );
  });
});
