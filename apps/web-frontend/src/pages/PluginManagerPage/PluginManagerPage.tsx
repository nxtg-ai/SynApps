/**
 * PluginManagerPage -- Workflow Marketplace Plugin System (N-60).
 *
 * Two tabs:
 *   - Browse Plugins: fetches and displays installed/available plugins as cards
 *   - Register Plugin: form to register a new plugin via manifest
 *
 * Route: /plugins (ProtectedRoute)
 */
import React, { useCallback, useEffect, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PluginManifest {
  name: string;
  display_name: string;
  description: string;
  node_type: string;
  endpoint_url: string;
  version: string;
  author: string;
  tags: string[];
  config_schema: Record<string, unknown>;
}

interface Plugin {
  id: string;
  manifest: PluginManifest;
  installed_at: number;
  install_count: number;
}

type Tab = 'browse' | 'register';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getBaseUrl(): string {
  return (
    (import.meta as unknown as { env?: { VITE_API_URL?: string; REACT_APP_API_URL?: string } }).env
      ?.VITE_API_URL ||
    (import.meta as unknown as { env?: { REACT_APP_API_URL?: string } }).env?.REACT_APP_API_URL ||
    'http://localhost:8000'
  );
}

function getAuthToken(): string | null {
  return typeof window !== 'undefined' ? window.localStorage.getItem('access_token') : null;
}

function authHeaders(): HeadersInit {
  const token = getAuthToken();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface PluginCardProps {
  plugin: Plugin;
  onInstall: (pluginId: string) => void;
  installing: boolean;
}

const PluginCard: React.FC<PluginCardProps> = ({ plugin, onInstall, installing }) => {
  const { manifest, install_count } = plugin;
  const visibleTags = manifest.tags.slice(0, 3);

  return (
    <div
      data-testid={`plugin-card-${plugin.id}`}
      className="rounded-lg border border-slate-700 bg-slate-800 p-4"
    >
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-slate-100">{manifest.display_name}</h3>
        <span
          data-testid={`badge-${plugin.id}`}
          className="rounded-full bg-indigo-600 px-2 py-0.5 text-xs text-white"
        >
          {manifest.node_type}
        </span>
      </div>

      <p className="mb-3 text-sm text-slate-400">{manifest.description}</p>

      <div className="mb-3 flex flex-wrap gap-1">
        {visibleTags.map((tag) => (
          <span key={tag} className="rounded bg-slate-700 px-2 py-0.5 text-xs text-slate-300">
            {tag}
          </span>
        ))}
      </div>

      <div className="mb-3 flex items-center justify-between text-xs text-slate-500">
        <span>by {manifest.author}</span>
        <span>v{manifest.version}</span>
        <span>{install_count} installs</span>
      </div>

      <button
        onClick={() => onInstall(plugin.id)}
        disabled={installing}
        className="w-full rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
      >
        {installing ? 'Installing...' : 'Install'}
      </button>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Register form
// ---------------------------------------------------------------------------

interface RegisterFormProps {
  onSuccess: () => void;
  onMessage: (msg: { type: 'success' | 'error'; text: string }) => void;
  message: { type: 'success' | 'error'; text: string } | null;
}

const RegisterForm: React.FC<RegisterFormProps> = ({ onSuccess, onMessage, message }) => {
  const [name, setName] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [description, setDescription] = useState('');
  const [nodeType, setNodeType] = useState('');
  const [endpointUrl, setEndpointUrl] = useState('');
  const [version, setVersion] = useState('1.0.0');
  const [author, setAuthor] = useState('');
  const [tags, setTags] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);

    const body = {
      name,
      display_name: displayName,
      description,
      node_type: nodeType,
      endpoint_url: endpointUrl,
      version,
      author,
      tags: tags
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean),
    };

    try {
      const res = await fetch(`${getBaseUrl()}/api/v1/plugins`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Registration failed' }));
        onMessage({ type: 'error', text: err.detail || 'Registration failed' });
        return;
      }

      onMessage({ type: 'success', text: 'Plugin registered!' });
      onSuccess();
    } catch {
      onMessage({ type: 'error', text: 'Network error — could not reach server' });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="mx-auto max-w-lg space-y-4">
      {message && (
        <div
          role="alert"
          className={`rounded p-3 text-sm ${
            message.type === 'success'
              ? 'bg-green-800/40 text-green-300'
              : 'bg-red-800/40 text-red-300'
          }`}
        >
          {message.text}
        </div>
      )}

      <div>
        <label htmlFor="plugin-name" className="mb-1 block text-sm text-slate-300">
          Name
        </label>
        <input
          id="plugin-name"
          type="text"
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-slate-100"
        />
      </div>

      <div>
        <label htmlFor="plugin-display-name" className="mb-1 block text-sm text-slate-300">
          Display Name
        </label>
        <input
          id="plugin-display-name"
          type="text"
          required
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-slate-100"
        />
      </div>

      <div>
        <label htmlFor="plugin-description" className="mb-1 block text-sm text-slate-300">
          Description
        </label>
        <textarea
          id="plugin-description"
          required
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-slate-100"
          rows={3}
        />
      </div>

      <div>
        <label htmlFor="plugin-node-type" className="mb-1 block text-sm text-slate-300">
          Node Type
        </label>
        <input
          id="plugin-node-type"
          type="text"
          required
          value={nodeType}
          onChange={(e) => setNodeType(e.target.value)}
          className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-slate-100"
        />
      </div>

      <div>
        <label htmlFor="plugin-endpoint-url" className="mb-1 block text-sm text-slate-300">
          Endpoint URL
        </label>
        <input
          id="plugin-endpoint-url"
          type="text"
          required
          value={endpointUrl}
          onChange={(e) => setEndpointUrl(e.target.value)}
          className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-slate-100"
        />
      </div>

      <div>
        <label htmlFor="plugin-version" className="mb-1 block text-sm text-slate-300">
          Version
        </label>
        <input
          id="plugin-version"
          type="text"
          value={version}
          onChange={(e) => setVersion(e.target.value)}
          className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-slate-100"
        />
      </div>

      <div>
        <label htmlFor="plugin-author" className="mb-1 block text-sm text-slate-300">
          Author
        </label>
        <input
          id="plugin-author"
          type="text"
          required
          value={author}
          onChange={(e) => setAuthor(e.target.value)}
          className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-slate-100"
        />
      </div>

      <div>
        <label htmlFor="plugin-tags" className="mb-1 block text-sm text-slate-300">
          Tags (comma-separated)
        </label>
        <input
          id="plugin-tags"
          type="text"
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-slate-100"
        />
      </div>

      <button
        type="submit"
        disabled={submitting}
        className="w-full rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
      >
        {submitting ? 'Registering...' : 'Register Plugin'}
      </button>
    </form>
  );
};

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

const PluginManagerPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<Tab>('browse');
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [loading, setLoading] = useState(true);
  const [installingId, setInstallingId] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const fetchPlugins = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${getBaseUrl()}/api/v1/plugins`, {
        headers: authHeaders(),
      });
      if (res.ok) {
        const data = await res.json();
        setPlugins(data.plugins ?? []);
      }
    } catch {
      // Network error -- leave plugins empty
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPlugins();
  }, [fetchPlugins]);

  const handleInstall = async (pluginId: string) => {
    setInstallingId(pluginId);
    setStatusMessage(null);
    try {
      const res = await fetch(`${getBaseUrl()}/api/v1/plugins/${pluginId}/install`, {
        method: 'POST',
        headers: authHeaders(),
      });
      if (res.ok) {
        setStatusMessage({ type: 'success', text: 'Plugin installed successfully!' });
        await fetchPlugins();
      } else {
        setStatusMessage({ type: 'error', text: 'Failed to install plugin' });
      }
    } catch {
      setStatusMessage({ type: 'error', text: 'Network error during install' });
    } finally {
      setInstallingId(null);
    }
  };

  const handleRegisterSuccess = () => {
    setActiveTab('browse');
    fetchPlugins();
  };

  return (
    <MainLayout title="Plugin Manager">
      <div className="mx-auto max-w-5xl px-4 py-6">
        <h1 className="mb-6 text-2xl font-bold text-slate-100">Plugin Manager</h1>

        {/* Tab bar */}
        <div className="mb-6 flex gap-2 border-b border-slate-700 pb-2">
          <button
            onClick={() => setActiveTab('browse')}
            className={`rounded-t px-4 py-2 text-sm font-medium ${
              activeTab === 'browse'
                ? 'bg-slate-800 text-indigo-400'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Browse Plugins
          </button>
          <button
            onClick={() => setActiveTab('register')}
            className={`rounded-t px-4 py-2 text-sm font-medium ${
              activeTab === 'register'
                ? 'bg-slate-800 text-indigo-400'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Register Plugin
          </button>
        </div>

        {/* Status banner (install / register messages) */}
        {statusMessage && (
          <div
            role="status"
            className={`mb-4 rounded p-3 text-sm ${
              statusMessage.type === 'success'
                ? 'bg-green-800/40 text-green-300'
                : 'bg-red-800/40 text-red-300'
            }`}
          >
            {statusMessage.text}
          </div>
        )}

        {/* Browse tab */}
        {activeTab === 'browse' && (
          <>
            {loading ? (
              <div data-testid="loading-spinner" className="py-12 text-center text-slate-400">
                Loading plugins...
              </div>
            ) : plugins.length === 0 ? (
              <div className="py-12 text-center text-slate-500">No plugins registered yet</div>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {plugins.map((p) => (
                  <PluginCard
                    key={p.id}
                    plugin={p}
                    onInstall={handleInstall}
                    installing={installingId === p.id}
                  />
                ))}
              </div>
            )}
          </>
        )}

        {/* Register tab */}
        {activeTab === 'register' && (
          <RegisterForm
            onSuccess={handleRegisterSuccess}
            onMessage={setStatusMessage}
            message={statusMessage}
          />
        )}
      </div>
    </MainLayout>
  );
};

export default PluginManagerPage;
