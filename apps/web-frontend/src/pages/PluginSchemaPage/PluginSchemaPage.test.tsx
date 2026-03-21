/**
 * Tests for PluginSchemaPage
 * Covers: GET /api/v1/plugins/{plugin_id}/schema
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

import PluginSchemaPage from './PluginSchemaPage';

const mockSchema = {
  plugin_id: 'my-plugin',
  config_schema: {
    type: 'object',
    properties: {
      api_key: { type: 'string', description: 'API key', default: '' },
      model: {
        type: 'string',
        enum: ['gpt-4', 'gpt-3.5-turbo'],
        description: 'Model to use',
      },
      temperature: { type: 'number', description: 'Sampling temperature', default: 0.7 },
    },
    required: ['api_key'],
  },
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
      <PluginSchemaPage />
    </MemoryRouter>,
  );

describe('PluginSchemaPage', () => {
  it('renders page title', () => {
    renderPage();
    expect(screen.getByText('Plugin Schema Viewer')).toBeTruthy();
  });

  it('Fetch Schema button disabled without plugin ID', () => {
    renderPage();
    const btn = screen.getByTestId('fetch-schema-btn') as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it('enables Fetch Schema button when plugin ID entered', () => {
    renderPage();
    fireEvent.change(screen.getByTestId('plugin-id-input'), {
      target: { value: 'my-plugin' },
    });
    const btn = screen.getByTestId('fetch-schema-btn') as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
  });

  it('calls GET /api/v1/plugins/{id}/schema on fetch', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => mockSchema });

    renderPage();
    fireEvent.change(screen.getByTestId('plugin-id-input'), {
      target: { value: 'my-plugin' },
    });
    fireEvent.click(screen.getByTestId('fetch-schema-btn'));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/plugins/my-plugin/schema'),
        expect.any(Object),
      );
    });
  });

  it('renders schema result panel', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => mockSchema });

    renderPage();
    fireEvent.change(screen.getByTestId('plugin-id-input'), { target: { value: 'my-plugin' } });
    fireEvent.click(screen.getByTestId('fetch-schema-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('schema-result')).toBeTruthy();
    });
  });

  it('shows plugin_id in result', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => mockSchema });

    renderPage();
    fireEvent.change(screen.getByTestId('plugin-id-input'), { target: { value: 'my-plugin' } });
    fireEvent.click(screen.getByTestId('fetch-schema-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('schema-plugin-id').textContent).toBe('my-plugin');
    });
  });

  it('shows schema type', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => mockSchema });

    renderPage();
    fireEvent.change(screen.getByTestId('plugin-id-input'), { target: { value: 'my-plugin' } });
    fireEvent.click(screen.getByTestId('fetch-schema-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('schema-type').textContent).toBe('object');
    });
  });

  it('shows required fields', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => mockSchema });

    renderPage();
    fireEvent.change(screen.getByTestId('plugin-id-input'), { target: { value: 'my-plugin' } });
    fireEvent.click(screen.getByTestId('fetch-schema-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('schema-required').textContent).toContain('api_key');
    });
  });

  it('renders properties table with all fields', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => mockSchema });

    renderPage();
    fireEvent.change(screen.getByTestId('plugin-id-input'), { target: { value: 'my-plugin' } });
    fireEvent.click(screen.getByTestId('fetch-schema-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('properties-table')).toBeTruthy();
      const rows = screen.getAllByTestId('property-row');
      expect(rows.length).toBe(3); // api_key, model, temperature
    });
  });

  it('displays enum type for enum properties', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => mockSchema });

    renderPage();
    fireEvent.change(screen.getByTestId('plugin-id-input'), { target: { value: 'my-plugin' } });
    fireEvent.click(screen.getByTestId('fetch-schema-btn'));

    await waitFor(() => {
      // model field has enum
      const rows = screen.getAllByTestId('property-row');
      const modelRow = rows.find((r) => r.textContent?.includes('model'));
      expect(modelRow?.textContent).toContain('enum');
    });
  });

  it('renders raw JSON section', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => mockSchema });

    renderPage();
    fireEvent.change(screen.getByTestId('plugin-id-input'), { target: { value: 'my-plugin' } });
    fireEvent.click(screen.getByTestId('fetch-schema-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('raw-json')).toBeTruthy();
    });
  });

  it('shows error on fetch failure', async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 404 });

    renderPage();
    fireEvent.change(screen.getByTestId('plugin-id-input'), { target: { value: 'bad-plugin' } });
    fireEvent.click(screen.getByTestId('fetch-schema-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('schema-error')).toBeTruthy();
    });
  });

  it('shows no-properties message for empty schema', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ plugin_id: 'empty', config_schema: { type: 'object' } }),
    });

    renderPage();
    fireEvent.change(screen.getByTestId('plugin-id-input'), { target: { value: 'empty' } });
    fireEvent.click(screen.getByTestId('fetch-schema-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('no-properties')).toBeTruthy();
    });
  });
});
