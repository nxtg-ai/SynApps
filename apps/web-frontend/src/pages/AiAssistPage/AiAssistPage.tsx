/**
 * AiAssistPage — AI Workflow Assistant UI (N-72).
 *
 * Three panels that expose the N-39 AI Assist API:
 *   Suggest Next Node   — POST /ai-assist/suggest-next
 *   Autocomplete        — POST /ai-assist/autocomplete (natural-language → node type)
 *   Workflow Patterns   — GET  /ai-assist/patterns?tag=
 *
 * Route: /ai-assist (ProtectedRoute)
 */
import React, { useCallback, useEffect, useState } from 'react';
import MainLayout from '../../components/Layout/MainLayout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface NodeSuggestion {
  node_type: string;
  score: number;
  config_template: Record<string, unknown>;
}

interface AutocompleteMatch {
  node_type: string;
  confidence: number;
  config_template: Record<string, unknown>;
}

interface WorkflowPattern {
  name: string;
  description: string;
  sequence: string[];
  tags: string[];
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

function getAuthToken(): string | null {
  return typeof window !== 'undefined' ? window.localStorage.getItem('access_token') : null;
}

function authHeaders(): Record<string, string> {
  const token = getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function jsonHeaders(): Record<string, string> {
  return { ...authHeaders(), 'Content-Type': 'application/json' };
}

const NODE_TYPES = [
  'start', 'end', 'llm', 'imagegen', 'code', 'http', 'transform',
  'ifelse', 'merge', 'foreach', 'scheduler', 'webhook_trigger', 'subflow', 'memory',
];

/** Confidence/score → colour */
function scoreClass(score: number): string {
  if (score >= 0.7) return 'text-emerald-400';
  if (score >= 0.4) return 'text-yellow-400';
  return 'text-slate-400';
}

// ---------------------------------------------------------------------------
// Suggest Next Node Panel
// ---------------------------------------------------------------------------

const SuggestNextPanel: React.FC = () => {
  const [currentType, setCurrentType] = useState('llm');
  const [suggestions, setSuggestions] = useState<NodeSuggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    setSuggestions([]);
    try {
      const resp = await fetch(`${getBaseUrl()}/ai-assist/suggest-next`, {
        method: 'POST',
        headers: jsonHeaders(),
        body: JSON.stringify({ current_node_type: currentType, existing_node_types: [], limit: 8 }),
      });
      if (!resp.ok) {
        setError(`API returned ${resp.status}`);
        return;
      }
      const data: { suggestions: NodeSuggestion[] } = await resp.json();
      setSuggestions(data.suggestions ?? []);
    } catch {
      setError('Network error fetching suggestions');
    } finally {
      setLoading(false);
    }
  }, [currentType]);

  return (
    <section data-testid="suggest-panel">
      <h2 className="mb-2 text-lg font-semibold text-slate-200">Suggest Next Node</h2>
      <p className="mb-4 text-sm text-slate-400">
        Given a current node type, see the most likely next nodes based on common workflow patterns.
      </p>

      <div className="mb-4 flex items-end gap-3">
        <div>
          <label htmlFor="current-node-select" className="mb-1 block text-xs text-slate-400">
            Current node type
          </label>
          <select
            id="current-node-select"
            value={currentType}
            onChange={(e) => setCurrentType(e.target.value)}
            className="rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 focus:outline-none"
            data-testid="current-node-select"
          >
            {NODE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <button
          onClick={handleFetch}
          disabled={loading}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
          data-testid="suggest-btn"
        >
          {loading ? 'Loading…' : 'Suggest'}
        </button>
      </div>

      {error && (
        <div className="mb-3 rounded border border-red-700 bg-red-900/40 px-3 py-2 text-sm text-red-300" data-testid="suggest-error">
          {error}
        </div>
      )}

      {suggestions.length > 0 && (
        <div className="space-y-2" data-testid="suggest-results">
          {suggestions.map((s, i) => (
            <div
              key={`${s.node_type}-${i}`}
              className="flex items-center justify-between rounded border border-slate-700 bg-slate-800/40 px-3 py-2"
              data-testid="suggest-item"
            >
              <span className="font-mono text-sm text-slate-200">{s.node_type}</span>
              <span className={`text-xs font-medium ${scoreClass(s.score)}`}>
                score {s.score.toFixed(2)}
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
};

// ---------------------------------------------------------------------------
// Autocomplete Panel
// ---------------------------------------------------------------------------

const AutocompletePanel: React.FC = () => {
  const [description, setDescription] = useState('');
  const [matches, setMatches] = useState<AutocompleteMatch[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFetch = useCallback(async () => {
    const desc = description.trim();
    if (!desc) return;
    setLoading(true);
    setError(null);
    setMatches([]);
    try {
      const resp = await fetch(`${getBaseUrl()}/ai-assist/autocomplete`, {
        method: 'POST',
        headers: jsonHeaders(),
        body: JSON.stringify({ description: desc, limit: 6 }),
      });
      if (!resp.ok) {
        setError(`API returned ${resp.status}`);
        return;
      }
      const data: { matches: AutocompleteMatch[] } = await resp.json();
      setMatches(data.matches ?? []);
    } catch {
      setError('Network error fetching autocomplete');
    } finally {
      setLoading(false);
    }
  }, [description]);

  return (
    <section data-testid="autocomplete-panel">
      <h2 className="mb-2 text-lg font-semibold text-slate-200">Autocomplete from Description</h2>
      <p className="mb-4 text-sm text-slate-400">
        Describe what you want to do in plain English — get matching node types with confidence scores.
      </p>

      <div className="mb-4 flex gap-2">
        <input
          type="text"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleFetch()}
          placeholder="e.g. call an external API and transform the response"
          className="flex-1 rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
          data-testid="autocomplete-input"
        />
        <button
          onClick={handleFetch}
          disabled={loading || !description.trim()}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
          data-testid="autocomplete-btn"
        >
          {loading ? 'Loading…' : 'Match'}
        </button>
      </div>

      {error && (
        <div className="mb-3 rounded border border-red-700 bg-red-900/40 px-3 py-2 text-sm text-red-300" data-testid="autocomplete-error">
          {error}
        </div>
      )}

      {matches.length > 0 && (
        <div className="space-y-2" data-testid="autocomplete-results">
          {matches.map((m, i) => (
            <div
              key={`${m.node_type}-${i}`}
              className="flex items-center justify-between rounded border border-slate-700 bg-slate-800/40 px-3 py-2"
              data-testid="autocomplete-item"
            >
              <span className="font-mono text-sm text-slate-200">{m.node_type}</span>
              <span className={`text-xs font-medium ${scoreClass(m.confidence)}`}>
                {(m.confidence * 100).toFixed(0)}% match
              </span>
            </div>
          ))}
        </div>
      )}

      {matches.length === 0 && !loading && !error && description.trim() && (
        <p className="text-sm text-slate-500" data-testid="autocomplete-empty">
          No matches found. Try different keywords.
        </p>
      )}
    </section>
  );
};

// ---------------------------------------------------------------------------
// Workflow Patterns Panel
// ---------------------------------------------------------------------------

const PatternsPanel: React.FC = () => {
  const [patterns, setPatterns] = useState<WorkflowPattern[]>([]);
  const [tagFilter, setTagFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchPatterns = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const url = tagFilter.trim()
        ? `${getBaseUrl()}/ai-assist/patterns?tag=${encodeURIComponent(tagFilter.trim())}`
        : `${getBaseUrl()}/ai-assist/patterns`;
      const resp = await fetch(url, { headers: authHeaders() });
      if (!resp.ok) {
        setError(`API returned ${resp.status}`);
        return;
      }
      const data: { patterns: WorkflowPattern[]; total: number } = await resp.json();
      setPatterns(data.patterns ?? []);
    } catch {
      setError('Network error loading patterns');
    } finally {
      setLoading(false);
    }
  }, [tagFilter]);

  useEffect(() => {
    fetchPatterns();
  }, []); // initial load with no filter

  return (
    <section data-testid="patterns-panel">
      <h2 className="mb-2 text-lg font-semibold text-slate-200">Workflow Patterns</h2>
      <p className="mb-4 text-sm text-slate-400">
        Browse built-in workflow patterns. Use as starting points for new workflows.
      </p>

      <div className="mb-4 flex gap-2">
        <input
          type="text"
          value={tagFilter}
          onChange={(e) => setTagFilter(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && fetchPatterns()}
          placeholder="Filter by tag (e.g. api, reporting)"
          className="flex-1 rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
          data-testid="pattern-tag-input"
        />
        <button
          onClick={fetchPatterns}
          disabled={loading}
          className="rounded bg-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-600 disabled:opacity-50"
          data-testid="pattern-filter-btn"
        >
          Filter
        </button>
      </div>

      {error && (
        <div className="mb-3 rounded border border-red-700 bg-red-900/40 px-3 py-2 text-sm text-red-300" data-testid="patterns-error">
          {error}
        </div>
      )}

      {loading ? (
        <div className="py-6 text-center text-slate-400" data-testid="patterns-loading">Loading…</div>
      ) : patterns.length === 0 ? (
        <div className="py-6 text-center text-slate-500" data-testid="patterns-empty">
          No patterns found{tagFilter.trim() ? ` matching "${tagFilter}"` : ''}.
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2" data-testid="patterns-grid">
          {patterns.map((p) => (
            <div
              key={p.name}
              className="rounded border border-slate-700 bg-slate-800/40 p-4"
              data-testid="pattern-card"
            >
              <h3 className="mb-1 font-semibold text-slate-200">{p.name}</h3>
              <p className="mb-2 text-xs text-slate-400">{p.description}</p>
              <div className="mb-2 flex flex-wrap gap-1">
                {p.sequence.map((node, i) => (
                  <span key={i} className="rounded bg-slate-700 px-1.5 py-0.5 font-mono text-xs text-slate-300">
                    {node}
                  </span>
                ))}
              </div>
              <div className="flex flex-wrap gap-1">
                {p.tags.map((tag) => (
                  <span
                    key={tag}
                    className="rounded bg-blue-900/40 px-1.5 py-0.5 text-xs text-blue-300"
                    data-testid="pattern-tag"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
};

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const AiAssistPage: React.FC = () => {
  return (
    <MainLayout title="AI Assist">
      <h1 className="mb-2 text-2xl font-bold text-slate-100" data-testid="page-title">
        AI Workflow Assistant
      </h1>
      <p className="mb-8 text-sm text-slate-400">
        Intelligent suggestions to help you build workflows faster — next-node recommendations,
        natural-language node matching, and curated workflow patterns.
      </p>

      <div className="space-y-10">
        <div className="grid gap-10 lg:grid-cols-2">
          <SuggestNextPanel />
          <AutocompletePanel />
        </div>
        <PatternsPanel />
      </div>
    </MainLayout>
  );
};

export default AiAssistPage;
