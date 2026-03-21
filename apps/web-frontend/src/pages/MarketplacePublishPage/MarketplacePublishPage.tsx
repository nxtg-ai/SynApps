/**
 * MarketplacePublishPage
 *
 * Covers:
 *   POST /api/v1/marketplace/publish  — publish an existing flow as a marketplace listing
 *
 * Request body: { flow_id, name, description, category, tags[], author }
 * Returns: listing entry with install_count=0
 *
 * Route: /marketplace-publish (ProtectedRoute)
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

const CATEGORIES = ['notification', 'data-sync', 'monitoring', 'content', 'devops'] as const;

interface Listing {
  id: string;
  name: string;
  description: string;
  category: string;
  tags: string[];
  author: string;
  install_count: number;
  publisher_id: string;
}

const MarketplacePublishPage: React.FC = () => {
  const [flowId, setFlowId] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState<string>(CATEGORIES[0]);
  const [tagsInput, setTagsInput] = useState('');
  const [author, setAuthor] = useState('');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<Listing | null>(null);

  const canSubmit = flowId.trim() && name.trim() && category;

  const handlePublish = async () => {
    if (!canSubmit) return;
    setLoading(true);
    setError('');
    setResult(null);

    const tags = tagsInput
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);

    const body: Record<string, unknown> = {
      flow_id: flowId.trim(),
      name: name.trim(),
      description: description.trim(),
      category,
      tags,
    };
    if (author.trim()) body.author = author.trim();

    try {
      const resp = await fetch(`${getBaseUrl()}/api/v1/marketplace/publish`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        const detail = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }));
        throw new Error(detail?.detail ?? `HTTP ${resp.status}`);
      }
      setResult(await resp.json());
    } catch (err: unknown) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setFlowId('');
    setName('');
    setDescription('');
    setCategory(CATEGORIES[0]);
    setTagsInput('');
    setAuthor('');
    setError('');
    setResult(null);
  };

  return (
    <MainLayout title="Publish to Marketplace">
      <div data-testid="marketplace-publish-page" style={{ padding: 24, maxWidth: 680 }}>
        <p style={{ color: '#9ca3af', marginBottom: 24 }}>
          Publish an existing workflow as a marketplace listing. The flow's nodes and edges are
          snapshotted and credentials are scrubbed automatically.
        </p>

        {result ? (
          <div data-testid="publish-result">
            <div
              style={{
                background: '#064e3b',
                border: '1px solid #10b981',
                borderRadius: 8,
                padding: 16,
                marginBottom: 16,
              }}
            >
              <p style={{ margin: 0, color: '#10b981', fontWeight: 700, fontSize: 15 }}>
                Published successfully!
              </p>
              <p data-testid="result-name" style={{ margin: '4px 0 0', color: '#d1fae5' }}>
                <strong>{result.name}</strong>
              </p>
              <p data-testid="result-id" style={{ margin: '4px 0 0', color: '#6ee7b7', fontFamily: 'monospace', fontSize: 12 }}>
                Listing ID: {result.id}
              </p>
              <p data-testid="result-category" style={{ margin: '4px 0 0', color: '#9ca3af', fontSize: 13 }}>
                Category: {result.category} · Author: {result.author}
              </p>
              {result.tags?.length > 0 && (
                <div data-testid="result-tags" style={{ marginTop: 8, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {result.tags.map((tag) => (
                    <span
                      key={tag}
                      style={{
                        background: '#1e3a5f',
                        color: '#93c5fd',
                        borderRadius: 12,
                        padding: '2px 10px',
                        fontSize: 12,
                      }}
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
            <button
              data-testid="publish-another-btn"
              onClick={handleReset}
              style={{
                padding: '8px 20px',
                borderRadius: 6,
                background: '#374151',
                color: '#fff',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              Publish Another
            </button>
          </div>
        ) : (
          <form
            data-testid="publish-form"
            onSubmit={(e) => { e.preventDefault(); handlePublish(); }}
            style={{ display: 'flex', flexDirection: 'column', gap: 16 }}
          >
            <div>
              <label style={{ display: 'block', color: '#e5e7eb', marginBottom: 4, fontSize: 14 }}>
                Flow ID <span style={{ color: '#f87171' }}>*</span>
              </label>
              <input
                data-testid="flow-id-input"
                placeholder="UUID of the flow to publish"
                value={flowId}
                onChange={(e) => setFlowId(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  borderRadius: 6,
                  border: '1px solid #4b5563',
                  background: '#1f2937',
                  color: '#fff',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            <div>
              <label style={{ display: 'block', color: '#e5e7eb', marginBottom: 4, fontSize: 14 }}>
                Listing Name <span style={{ color: '#f87171' }}>*</span>
              </label>
              <input
                data-testid="name-input"
                placeholder="Display name for the listing"
                value={name}
                onChange={(e) => setName(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  borderRadius: 6,
                  border: '1px solid #4b5563',
                  background: '#1f2937',
                  color: '#fff',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            <div>
              <label style={{ display: 'block', color: '#e5e7eb', marginBottom: 4, fontSize: 14 }}>
                Category <span style={{ color: '#f87171' }}>*</span>
              </label>
              <select
                data-testid="category-select"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  borderRadius: 6,
                  border: '1px solid #4b5563',
                  background: '#1f2937',
                  color: '#fff',
                }}
              >
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label style={{ display: 'block', color: '#e5e7eb', marginBottom: 4, fontSize: 14 }}>
                Description
              </label>
              <textarea
                data-testid="description-input"
                placeholder="What does this workflow do?"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  borderRadius: 6,
                  border: '1px solid #4b5563',
                  background: '#1f2937',
                  color: '#fff',
                  resize: 'vertical',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            <div>
              <label style={{ display: 'block', color: '#e5e7eb', marginBottom: 4, fontSize: 14 }}>
                Tags <span style={{ color: '#9ca3af', fontWeight: 400 }}>(comma-separated)</span>
              </label>
              <input
                data-testid="tags-input"
                placeholder="automation, gpt-4, slack"
                value={tagsInput}
                onChange={(e) => setTagsInput(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  borderRadius: 6,
                  border: '1px solid #4b5563',
                  background: '#1f2937',
                  color: '#fff',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            <div>
              <label style={{ display: 'block', color: '#e5e7eb', marginBottom: 4, fontSize: 14 }}>
                Author
              </label>
              <input
                data-testid="author-input"
                placeholder="Your name (default: anonymous)"
                value={author}
                onChange={(e) => setAuthor(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  borderRadius: 6,
                  border: '1px solid #4b5563',
                  background: '#1f2937',
                  color: '#fff',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            {error && (
              <p data-testid="publish-error" style={{ color: '#f87171', margin: 0 }}>
                {error}
              </p>
            )}

            <button
              data-testid="publish-btn"
              type="submit"
              disabled={!canSubmit || loading}
              style={{
                padding: '10px 24px',
                borderRadius: 6,
                background: canSubmit && !loading ? '#6366f1' : '#374151',
                color: '#fff',
                border: 'none',
                cursor: canSubmit && !loading ? 'pointer' : 'not-allowed',
                fontWeight: 600,
                alignSelf: 'flex-start',
              }}
            >
              {loading ? 'Publishing…' : 'Publish to Marketplace'}
            </button>
          </form>
        )}
      </div>
    </MainLayout>
  );
};

export default MarketplacePublishPage;
