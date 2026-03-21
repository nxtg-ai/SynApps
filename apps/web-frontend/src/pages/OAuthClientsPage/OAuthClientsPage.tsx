/**
 * OAuthClientsPage — OAuth2 Client Applications Manager (N-95).
 *
 * Wraps:
 *   GET    /api/v1/oauth/clients             → list all OAuth2 clients
 *   POST   /api/v1/oauth/clients             → register new client
 *   DELETE /api/v1/oauth/clients/{client_id} → revoke client
 *
 * Route: /oauth-clients (ProtectedRoute)
 */
import React, { useCallback, useEffect, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface OAuthClient {
  client_id: string;
  name: string;
  redirect_uris?: string[];
  allowed_scopes?: string[];
  grant_types?: string[];
  created_at?: string;
  [key: string]: unknown;
}

interface RegisteredClient extends OAuthClient {
  client_secret?: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getBaseUrl(): string {
  return (
    (import.meta as unknown as { env?: { VITE_API_URL?: string } }).env?.VITE_API_URL ||
    'http://localhost:8000'
  );
}

function authHeaders(): Record<string, string> {
  const token =
    typeof window !== 'undefined' ? window.localStorage.getItem('access_token') : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const OAuthClientsPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [clients, setClients] = useState<OAuthClient[]>([]);

  // Register form
  const [name, setName] = useState('');
  const [redirectUris, setRedirectUris] = useState('');
  const [scopes, setScopes] = useState('read write');
  const [grantTypes, setGrantTypes] = useState('authorization_code client_credentials');
  const [registering, setRegistering] = useState(false);
  const [registerError, setRegisterError] = useState<string | null>(null);
  const [newClient, setNewClient] = useState<RegisteredClient | null>(null);

  // Revoke state
  const [revokingId, setRevokingId] = useState<string | null>(null);
  const [revokeError, setRevokeError] = useState<string | null>(null);

  const loadClients = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`${getBaseUrl()}/oauth/clients`, { headers: authHeaders() });
      if (!resp.ok) {
        setError(`Failed to load clients (${resp.status})`);
        return;
      }
      const data = await resp.json();
      setClients(Array.isArray(data) ? data : []);
    } catch {
      setError('Network error loading clients');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadClients();
  }, [loadClients]);

  const handleRegister = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!name.trim()) return;
      setRegistering(true);
      setRegisterError(null);
      setNewClient(null);
      try {
        const resp = await fetch(`${getBaseUrl()}/oauth/clients`, {
          method: 'POST',
          headers: { ...authHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: name.trim(),
            redirect_uris: redirectUris
              .split(/\s+/)
              .map((s) => s.trim())
              .filter(Boolean),
            allowed_scopes: scopes
              .split(/\s+/)
              .map((s) => s.trim())
              .filter(Boolean),
            grant_types: grantTypes
              .split(/\s+/)
              .map((s) => s.trim())
              .filter(Boolean),
          }),
        });
        if (!resp.ok) {
          const data = await resp.json().catch(() => ({}));
          setRegisterError(data.detail ?? `Error ${resp.status}`);
          return;
        }
        const registered: RegisteredClient = await resp.json();
        setNewClient(registered);
        setClients((prev) => [registered, ...prev]);
        setName('');
        setRedirectUris('');
      } catch {
        setRegisterError('Network error registering client');
      } finally {
        setRegistering(false);
      }
    },
    [name, redirectUris, scopes, grantTypes],
  );

  const handleRevoke = useCallback(async (clientId: string) => {
    setRevokingId(clientId);
    setRevokeError(null);
    try {
      const resp = await fetch(
        `${getBaseUrl()}/oauth/clients/${encodeURIComponent(clientId)}`,
        { method: 'DELETE', headers: authHeaders() },
      );
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        setRevokeError(data.detail ?? `Error ${resp.status}`);
        return;
      }
      setClients((prev) => prev.filter((c) => c.client_id !== clientId));
    } catch {
      setRevokeError('Network error revoking client');
    } finally {
      setRevokingId(null);
    }
  }, []);

  return (
    <MainLayout title="OAuth2 Clients">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100" data-testid="page-title">
            OAuth2 Clients
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Manage OAuth2 client applications for API integrations.
          </p>
        </div>
        <button
          onClick={loadClients}
          disabled={loading}
          className="rounded bg-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-600 disabled:opacity-50"
          data-testid="refresh-btn"
        >
          Refresh
        </button>
      </div>

      {/* Register form */}
      <section
        className="mb-8 rounded border border-slate-700 bg-slate-800/30 p-5"
        data-testid="register-section"
      >
        <h2 className="mb-4 text-sm font-semibold text-slate-300">Register New Client</h2>
        <form onSubmit={handleRegister} className="space-y-3" data-testid="register-form">
          <div className="flex flex-wrap gap-3">
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Client name"
              className="w-48 rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
              data-testid="name-input"
            />
            <input
              type="text"
              value={redirectUris}
              onChange={(e) => setRedirectUris(e.target.value)}
              placeholder="Redirect URIs (space-separated)"
              className="w-64 rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
              data-testid="redirect-uris-input"
            />
            <input
              type="text"
              value={scopes}
              onChange={(e) => setScopes(e.target.value)}
              placeholder="Scopes"
              className="w-40 rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:outline-none"
              data-testid="scopes-input"
            />
          </div>
          <button
            type="submit"
            disabled={registering || !name.trim()}
            className="rounded bg-indigo-700 px-4 py-1.5 text-sm text-white hover:bg-indigo-600 disabled:opacity-50"
            data-testid="register-btn"
          >
            {registering ? 'Registering…' : 'Register'}
          </button>
        </form>

        {registerError && (
          <p className="mt-2 text-sm text-red-400" data-testid="register-error">{registerError}</p>
        )}

        {newClient && (
          <div
            className="mt-3 rounded border border-emerald-700/50 bg-emerald-900/20 p-4 text-xs"
            data-testid="register-success"
          >
            <p className="mb-1 font-semibold text-emerald-400">Client registered!</p>
            <p className="text-slate-300">
              Client ID:{' '}
              <span className="font-mono" data-testid="new-client-id">
                {newClient.client_id}
              </span>
            </p>
            {newClient.client_secret && (
              <p className="mt-1 text-slate-300">
                Client Secret (shown once):{' '}
                <span className="font-mono text-yellow-300" data-testid="new-client-secret">
                  {newClient.client_secret}
                </span>
              </p>
            )}
          </div>
        )}
      </section>

      {/* Client list */}
      {error && (
        <p className="mb-4 text-sm text-red-400" data-testid="clients-error">{error}</p>
      )}
      {revokeError && (
        <p className="mb-4 text-sm text-red-400" data-testid="revoke-error">{revokeError}</p>
      )}
      {loading && clients.length === 0 && (
        <p className="text-xs text-slate-500" data-testid="clients-loading">Loading…</p>
      )}
      {!loading && clients.length === 0 && !error && (
        <p className="text-xs text-slate-500" data-testid="no-clients">
          No OAuth2 clients registered.
        </p>
      )}

      {clients.length > 0 && (
        <div className="overflow-x-auto" data-testid="clients-table">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-700 text-left text-slate-500">
                <th className="pb-2 pr-4 font-medium">Client ID</th>
                <th className="pb-2 pr-4 font-medium">Name</th>
                <th className="pb-2 pr-4 font-medium">Scopes</th>
                <th className="pb-2 pr-4 font-medium">Grant Types</th>
                <th className="pb-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {clients.map((c) => (
                <tr
                  key={c.client_id}
                  className="border-b border-slate-700/40"
                  data-testid="client-row"
                >
                  <td className="py-2 pr-4 font-mono text-slate-400">{c.client_id}</td>
                  <td className="py-2 pr-4 text-slate-300">{c.name}</td>
                  <td className="py-2 pr-4 text-slate-400">
                    {Array.isArray(c.allowed_scopes) ? c.allowed_scopes.join(', ') : '—'}
                  </td>
                  <td className="py-2 pr-4 text-slate-400">
                    {Array.isArray(c.grant_types) ? c.grant_types.join(', ') : '—'}
                  </td>
                  <td className="py-2">
                    <button
                      onClick={() => handleRevoke(c.client_id)}
                      disabled={revokingId === c.client_id}
                      className="rounded bg-red-900/60 px-2 py-0.5 text-xs text-red-300 hover:bg-red-900 disabled:opacity-50"
                      data-testid="revoke-btn"
                    >
                      {revokingId === c.client_id ? 'Revoking…' : 'Revoke'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </MainLayout>
  );
};

export default OAuthClientsPage;
