/**
 * Unit tests for AiAssistPage (N-72).
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import AiAssistPage from './AiAssistPage';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const SUGGEST_RESPONSE = {
  suggestions: [
    { node_type: 'http', score: 0.85, config_template: {} },
    { node_type: 'transform', score: 0.60, config_template: {} },
    { node_type: 'end', score: 0.35, config_template: {} },
  ],
};

const AUTOCOMPLETE_RESPONSE = {
  matches: [
    { node_type: 'http', confidence: 0.9, config_template: {} },
    { node_type: 'code', confidence: 0.5, config_template: {} },
  ],
};

const PATTERNS_RESPONSE = {
  patterns: [
    { name: 'Inbox Triage', description: 'Classify and route messages', sequence: ['start', 'llm', 'end'], tags: ['triage', 'email'] },
    { name: 'Scheduled Report', description: 'Cron-triggered reporting', sequence: ['scheduler', 'http', 'llm', 'end'], tags: ['reporting', 'scheduled'] },
  ],
  total: 2,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <AiAssistPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('AiAssistPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    window.localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders page title and all three panels', async () => {
    vi.mocked(fetch).mockResolvedValue({ ok: true, json: async () => PATTERNS_RESPONSE } as Response);
    renderPage();
    expect(screen.getByTestId('page-title')).toBeInTheDocument();
    expect(screen.getByTestId('suggest-panel')).toBeInTheDocument();
    expect(screen.getByTestId('autocomplete-panel')).toBeInTheDocument();
    expect(screen.getByTestId('patterns-panel')).toBeInTheDocument();
  });

  it('renders suggest panel with node-type select and Suggest button', () => {
    vi.mocked(fetch).mockResolvedValue({ ok: true, json: async () => PATTERNS_RESPONSE } as Response);
    renderPage();
    expect(screen.getByTestId('current-node-select')).toBeInTheDocument();
    expect(screen.getByTestId('suggest-btn')).toBeInTheDocument();
  });

  it('fetches suggestions and renders items', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => PATTERNS_RESPONSE } as Response) // initial patterns load
      .mockResolvedValueOnce({ ok: true, json: async () => SUGGEST_RESPONSE } as Response);

    renderPage();
    fireEvent.click(screen.getByTestId('suggest-btn'));

    await waitFor(() => expect(screen.getByTestId('suggest-results')).toBeInTheDocument());
    const items = screen.getAllByTestId('suggest-item');
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent('http');
    expect(items[0]).toHaveTextContent('0.85');
  });

  it('shows suggest error on API failure', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => PATTERNS_RESPONSE } as Response)
      .mockResolvedValueOnce({ ok: false, status: 500, json: async () => ({}) } as Response);

    renderPage();
    fireEvent.click(screen.getByTestId('suggest-btn'));

    await waitFor(() => expect(screen.getByTestId('suggest-error')).toBeInTheDocument());
  });

  it('renders autocomplete input and Match button, disabled when empty', () => {
    vi.mocked(fetch).mockResolvedValue({ ok: true, json: async () => PATTERNS_RESPONSE } as Response);
    renderPage();
    expect(screen.getByTestId('autocomplete-input')).toBeInTheDocument();
    expect(screen.getByTestId('autocomplete-btn')).toBeDisabled();
  });

  it('fetches autocomplete matches and renders items', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => PATTERNS_RESPONSE } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => AUTOCOMPLETE_RESPONSE } as Response);

    renderPage();
    fireEvent.change(screen.getByTestId('autocomplete-input'), { target: { value: 'call an API' } });
    fireEvent.click(screen.getByTestId('autocomplete-btn'));

    await waitFor(() => expect(screen.getByTestId('autocomplete-results')).toBeInTheDocument());
    const items = screen.getAllByTestId('autocomplete-item');
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent('http');
    expect(items[0]).toHaveTextContent('90%');
  });

  it('shows empty message when autocomplete returns no matches', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => PATTERNS_RESPONSE } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ matches: [] }) } as Response);

    renderPage();
    fireEvent.change(screen.getByTestId('autocomplete-input'), { target: { value: 'xyz unknown' } });
    fireEvent.click(screen.getByTestId('autocomplete-btn'));

    await waitFor(() => expect(screen.getByTestId('autocomplete-empty')).toBeInTheDocument());
  });

  it('loads and renders pattern cards on mount', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => PATTERNS_RESPONSE } as Response);

    renderPage();
    await waitFor(() => expect(screen.getByTestId('patterns-grid')).toBeInTheDocument());
    const cards = screen.getAllByTestId('pattern-card');
    expect(cards).toHaveLength(2);
    expect(cards[0]).toHaveTextContent('Inbox Triage');
    expect(cards[1]).toHaveTextContent('Scheduled Report');
  });

  it('renders pattern tags', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => PATTERNS_RESPONSE } as Response);

    renderPage();
    await waitFor(() => expect(screen.getAllByTestId('pattern-tag').length).toBeGreaterThan(0));
    const tags = screen.getAllByTestId('pattern-tag').map((el) => el.textContent);
    expect(tags).toContain('triage');
    expect(tags).toContain('email');
  });

  it('filters patterns by tag', async () => {
    const filteredResponse = { patterns: [PATTERNS_RESPONSE.patterns[1]], total: 1 };
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => PATTERNS_RESPONSE } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => filteredResponse } as Response);

    renderPage();
    await waitFor(() => expect(screen.getByTestId('patterns-grid')).toBeInTheDocument());

    fireEvent.change(screen.getByTestId('pattern-tag-input'), { target: { value: 'reporting' } });
    fireEvent.click(screen.getByTestId('pattern-filter-btn'));

    await waitFor(() => expect(screen.getAllByTestId('pattern-card')).toHaveLength(1));
    expect(screen.getByText('Scheduled Report')).toBeInTheDocument();
  });

  it('shows patterns empty state when filter has no results', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => PATTERNS_RESPONSE } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ patterns: [], total: 0 }) } as Response);

    renderPage();
    await waitFor(() => expect(screen.getByTestId('patterns-grid')).toBeInTheDocument());
    fireEvent.change(screen.getByTestId('pattern-tag-input'), { target: { value: 'nonexistent' } });
    fireEvent.click(screen.getByTestId('pattern-filter-btn'));

    await waitFor(() => expect(screen.getByTestId('patterns-empty')).toBeInTheDocument());
  });

  it('sends Authorization header on suggest request', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => PATTERNS_RESPONSE } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => SUGGEST_RESPONSE } as Response);

    renderPage();
    fireEvent.click(screen.getByTestId('suggest-btn'));

    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    const [, opts] = vi.mocked(fetch).mock.calls[1];
    expect((opts as RequestInit).headers).toMatchObject({ Authorization: 'Bearer test-token' });
  });
});
