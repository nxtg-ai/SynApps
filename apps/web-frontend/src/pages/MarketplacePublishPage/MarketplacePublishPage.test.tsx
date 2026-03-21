/**
 * Tests for MarketplacePublishPage
 * Covers: POST /api/v1/marketplace/publish
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children, title }: { children: React.ReactNode; title: string }) => (
    <div data-testid="layout">
      <h1>{title}</h1>
      {children}
    </div>
  ),
}));

import MarketplacePublishPage from './MarketplacePublishPage';

const mockListing = {
  id: 'listing-abc-123',
  name: 'Slack Notifier',
  description: 'Sends Slack alerts on any trigger',
  category: 'notification',
  tags: ['slack', 'alert'],
  author: 'alice',
  install_count: 0,
  publisher_id: 'user-1',
};

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

beforeEach(() => {
  mockFetch.mockReset();
  localStorage.setItem('access_token', 'tok');
});

const renderPage = () =>
  render(
    <MemoryRouter>
      <MarketplacePublishPage />
    </MemoryRouter>,
  );

describe('MarketplacePublishPage', () => {
  it('renders page title', () => {
    renderPage();
    expect(screen.getByRole('heading', { name: 'Publish to Marketplace' })).toBeTruthy();
  });

  it('renders the publish form', () => {
    renderPage();
    expect(screen.getByTestId('publish-form')).toBeTruthy();
  });

  it('Publish button disabled without flow ID and name', () => {
    renderPage();
    const btn = screen.getByTestId('publish-btn') as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it('Publish button disabled when only flow ID filled', () => {
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-1' } });
    const btn = screen.getByTestId('publish-btn') as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it('Publish button enabled when flow ID and name are filled', () => {
    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-1' } });
    fireEvent.change(screen.getByTestId('name-input'), { target: { value: 'My Flow' } });
    const btn = screen.getByTestId('publish-btn') as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
  });

  it('renders category select with all categories', () => {
    renderPage();
    const select = screen.getByTestId('category-select') as HTMLSelectElement;
    const options = Array.from(select.options).map((o) => o.value);
    expect(options).toContain('notification');
    expect(options).toContain('data-sync');
    expect(options).toContain('monitoring');
    expect(options).toContain('content');
    expect(options).toContain('devops');
  });

  it('calls POST /api/v1/marketplace/publish with correct body', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => mockListing });

    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.change(screen.getByTestId('name-input'), { target: { value: 'Slack Notifier' } });
    fireEvent.change(screen.getByTestId('category-select'), { target: { value: 'notification' } });
    fireEvent.change(screen.getByTestId('description-input'), {
      target: { value: 'Sends Slack alerts' },
    });
    fireEvent.change(screen.getByTestId('tags-input'), { target: { value: 'slack, alert' } });
    fireEvent.change(screen.getByTestId('author-input'), { target: { value: 'alice' } });
    fireEvent.click(screen.getByTestId('publish-btn'));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/marketplace/publish'),
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
        }),
      );
      const body = JSON.parse(mockFetch.mock.calls[0][1].body);
      expect(body.flow_id).toBe('flow-abc');
      expect(body.name).toBe('Slack Notifier');
      expect(body.category).toBe('notification');
      expect(body.tags).toEqual(['slack', 'alert']);
      expect(body.author).toBe('alice');
    });
  });

  it('shows success result after publish', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => mockListing });

    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.change(screen.getByTestId('name-input'), { target: { value: 'Slack Notifier' } });
    fireEvent.click(screen.getByTestId('publish-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('publish-result')).toBeTruthy();
    });
  });

  it('shows listing name in result', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => mockListing });

    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.change(screen.getByTestId('name-input'), { target: { value: 'Slack Notifier' } });
    fireEvent.click(screen.getByTestId('publish-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('result-name').textContent).toContain('Slack Notifier');
    });
  });

  it('shows listing ID in result', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => mockListing });

    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.change(screen.getByTestId('name-input'), { target: { value: 'Slack Notifier' } });
    fireEvent.click(screen.getByTestId('publish-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('result-id').textContent).toContain('listing-abc-123');
    });
  });

  it('shows result tags', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => mockListing });

    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.change(screen.getByTestId('name-input'), { target: { value: 'Slack Notifier' } });
    fireEvent.click(screen.getByTestId('publish-btn'));

    await waitFor(() => {
      const tags = screen.getByTestId('result-tags');
      expect(tags.textContent).toContain('slack');
      expect(tags.textContent).toContain('alert');
    });
  });

  it('shows error on failed publish', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: async () => ({ detail: 'Flow not found' }),
    });

    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'bad-flow' } });
    fireEvent.change(screen.getByTestId('name-input'), { target: { value: 'My Flow' } });
    fireEvent.click(screen.getByTestId('publish-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('publish-error').textContent).toContain('Flow not found');
    });
  });

  it('shows conflict error on duplicate publish', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 409,
      json: async () => ({ detail: 'Listing already exists' }),
    });

    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-1' } });
    fireEvent.change(screen.getByTestId('name-input'), { target: { value: 'Duplicate' } });
    fireEvent.click(screen.getByTestId('publish-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('publish-error').textContent).toContain('Listing already exists');
    });
  });

  it('Publish Another button resets the form', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => mockListing });

    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.change(screen.getByTestId('name-input'), { target: { value: 'Slack Notifier' } });
    fireEvent.click(screen.getByTestId('publish-btn'));

    await waitFor(() => screen.getByTestId('publish-result'));
    fireEvent.click(screen.getByTestId('publish-another-btn'));

    expect(screen.getByTestId('publish-form')).toBeTruthy();
  });

  it('sends empty tags array when tags input is blank', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => mockListing });

    renderPage();
    fireEvent.change(screen.getByTestId('flow-id-input'), { target: { value: 'flow-abc' } });
    fireEvent.change(screen.getByTestId('name-input'), { target: { value: 'My Flow' } });
    fireEvent.click(screen.getByTestId('publish-btn'));

    await waitFor(() => {
      const body = JSON.parse(mockFetch.mock.calls[0][1].body);
      expect(body.tags).toEqual([]);
    });
  });
});
