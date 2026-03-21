/**
 * PluginSchemaPage
 *
 * Covers:
 *   GET /api/v1/plugins/{plugin_id}/schema  — returns config_schema for a plugin (public, no auth)
 *
 * Route: /plugin-schema
 */
import React, { useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

function getBaseUrl(): string {
  return (window as any).__API_BASE__ ?? '';
}
function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('access_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

interface SchemaProperty {
  type?: string;
  description?: string;
  enum?: unknown[];
  default?: unknown;
}

interface ConfigSchema {
  type?: string;
  properties?: Record<string, SchemaProperty>;
  required?: string[];
  [key: string]: unknown;
}

interface PluginSchemaResponse {
  plugin_id: string;
  config_schema: ConfigSchema;
}

const PluginSchemaPage: React.FC = () => {
  const [pluginId, setPluginId] = useState('');
  const [result, setResult] = useState<PluginSchemaResponse | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const fetchSchema = async () => {
    if (!pluginId.trim()) return;
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/api/v1/plugins/${encodeURIComponent(pluginId.trim())}/schema`,
        { headers: authHeaders() },
      );
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setResult(await resp.json());
    } catch (err: unknown) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  const properties = result?.config_schema?.properties ?? {};
  const required = new Set(result?.config_schema?.required ?? []);

  return (
    <MainLayout title="Plugin Schema Viewer">
      <div data-testid="plugin-schema-page" style={{ padding: 24, maxWidth: 800 }}>
        <p style={{ color: '#9ca3af', marginBottom: 16 }}>
          Inspect the configuration schema for any registered plugin.
        </p>

        <div style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
          <input
            data-testid="plugin-id-input"
            placeholder="Plugin ID (e.g. my-plugin)"
            value={pluginId}
            onChange={(e) => setPluginId(e.target.value)}
            style={{
              flex: 1,
              padding: '8px 12px',
              borderRadius: 6,
              border: '1px solid #4b5563',
              background: '#1f2937',
              color: '#fff',
            }}
          />
          <button
            data-testid="fetch-schema-btn"
            disabled={!pluginId.trim()}
            onClick={fetchSchema}
            style={{
              padding: '8px 20px',
              borderRadius: 6,
              background: '#6366f1',
              color: '#fff',
              border: 'none',
              cursor: 'pointer',
            }}
          >
            Fetch Schema
          </button>
        </div>

        {loading && <p data-testid="schema-loading">Loading…</p>}
        {error && (
          <p data-testid="schema-error" style={{ color: '#f87171' }}>
            {error}
          </p>
        )}

        {result && (
          <div data-testid="schema-result">
            <div style={{ background: '#1f2937', borderRadius: 8, padding: 16, marginBottom: 16 }}>
              <p style={{ margin: 0, color: '#9ca3af', fontSize: 13 }}>
                Plugin: <strong data-testid="schema-plugin-id" style={{ color: '#e5e7eb' }}>{result.plugin_id}</strong>
              </p>
              <p style={{ margin: '4px 0 0', color: '#9ca3af', fontSize: 13 }}>
                Schema type: <span data-testid="schema-type">{result.config_schema?.type ?? 'object'}</span>
              </p>
              {required.size > 0 && (
                <p style={{ margin: '4px 0 0', color: '#9ca3af', fontSize: 13 }}>
                  Required:{' '}
                  <span data-testid="schema-required">
                    {Array.from(required).join(', ')}
                  </span>
                </p>
              )}
            </div>

            {Object.keys(properties).length > 0 ? (
              <div>
                <h4 style={{ color: '#e5e7eb', marginBottom: 8 }}>Properties</h4>
                <table data-testid="properties-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ background: '#1f2937', color: '#9ca3af', fontSize: 13 }}>
                      <th style={{ padding: '8px 12px', textAlign: 'left' }}>Field</th>
                      <th style={{ padding: '8px 12px', textAlign: 'left' }}>Type</th>
                      <th style={{ padding: '8px 12px', textAlign: 'left' }}>Required</th>
                      <th style={{ padding: '8px 12px', textAlign: 'left' }}>Description</th>
                      <th style={{ padding: '8px 12px', textAlign: 'left' }}>Default</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(properties).map(([name, prop]) => (
                      <tr
                        key={name}
                        data-testid="property-row"
                        style={{ borderBottom: '1px solid #374151' }}
                      >
                        <td style={{ padding: '8px 12px', fontFamily: 'monospace', fontWeight: 600 }}>
                          {name}
                        </td>
                        <td style={{ padding: '8px 12px', color: '#818cf8' }}>
                          {prop.enum
                            ? `enum(${prop.enum.join('|')})`
                            : (prop.type ?? '—')}
                        </td>
                        <td style={{ padding: '8px 12px' }}>
                          {required.has(name) ? (
                            <span style={{ color: '#f87171' }}>yes</span>
                          ) : (
                            <span style={{ color: '#6b7280' }}>no</span>
                          )}
                        </td>
                        <td style={{ padding: '8px 12px', color: '#9ca3af', fontSize: 12 }}>
                          {prop.description ?? '—'}
                        </td>
                        <td style={{ padding: '8px 12px', fontFamily: 'monospace', fontSize: 12 }}>
                          {prop.default !== undefined ? JSON.stringify(prop.default) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p data-testid="no-properties">No properties defined in this schema.</p>
            )}

            <details style={{ marginTop: 16 }}>
              <summary style={{ cursor: 'pointer', color: '#9ca3af', fontSize: 13 }}>
                Raw JSON
              </summary>
              <pre
                data-testid="raw-json"
                style={{
                  background: '#111827',
                  borderRadius: 6,
                  padding: 12,
                  marginTop: 8,
                  fontSize: 12,
                  color: '#d1d5db',
                  overflowX: 'auto',
                }}
              >
                {JSON.stringify(result.config_schema, null, 2)}
              </pre>
            </details>
          </div>
        )}
      </div>
    </MainLayout>
  );
};

export default PluginSchemaPage;
