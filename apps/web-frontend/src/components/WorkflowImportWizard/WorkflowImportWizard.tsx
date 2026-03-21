/**
 * WorkflowImportWizard -- 3-step wizard for importing n8n, Zapier, or SynApps
 * workflows into SynApps via POST /api/v1/workflows/import.
 *
 * Step 1: Select format (n8n | zapier | synapps)
 * Step 2: Paste or upload JSON
 * Step 3: Review & import
 */
import React, { useCallback, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ImportFormat = 'n8n' | 'zapier' | 'synapps';

interface ImportResult {
  flow_id: string;
  name: string;
  nodes_imported: number;
  edges_imported: number;
}

const FORMAT_LABELS: Record<ImportFormat, string> = {
  n8n: 'n8n',
  zapier: 'Zapier',
  synapps: 'SynApps (native)',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getAuthHeaders(): HeadersInit {
  const token = localStorage.getItem('access_token') || '';
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

function tryParseJson(raw: string): { valid: boolean; data: unknown; error: string } {
  try {
    const data: unknown = JSON.parse(raw);
    return { valid: true, data, error: '' };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Invalid JSON';
    return { valid: false, data: null, error: message };
  }
}

function countJsonLines(raw: string): number {
  return raw.split('\n').length;
}

function detectNodeCount(data: unknown): number | null {
  if (data && typeof data === 'object') {
    const record = data as Record<string, unknown>;
    if (Array.isArray(record.nodes)) return record.nodes.length;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const WorkflowImportWizard: React.FC = () => {
  const navigate = useNavigate();

  // Wizard step: 1, 2, or 3
  const [step, setStep] = useState<1 | 2 | 3>(1);

  // Step 1 state
  const [format, setFormat] = useState<ImportFormat>('n8n');

  // Step 2 state
  const [rawJson, setRawJson] = useState('');
  const [parseError, setParseError] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Step 3 state
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [importError, setImportError] = useState('');

  // ------- Step navigation -------

  const goToStep2 = useCallback(() => {
    setStep(2);
  }, []);

  const goToStep3 = useCallback(() => {
    const { valid, error } = tryParseJson(rawJson);
    if (!valid) {
      setParseError(error);
      return;
    }
    setParseError('');
    setStep(3);
  }, [rawJson]);

  const goBackToStep2 = useCallback(() => {
    setImportError('');
    setImportResult(null);
    setStep(2);
  }, []);

  // ------- File upload -------

  const handleFileUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const text = await file.text();
    setRawJson(text);

    const { valid, error } = tryParseJson(text);
    setParseError(valid ? '' : error);

    // Reset file input so the same file can be re-selected
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, []);

  // ------- Textarea change -------

  const handleTextareaChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setRawJson(value);

    if (value.trim().length > 0) {
      const { valid, error } = tryParseJson(value);
      setParseError(valid ? '' : error);
    } else {
      setParseError('');
    }
  }, []);

  // ------- Import -------

  const handleImport = useCallback(async () => {
    const { valid, data } = tryParseJson(rawJson);
    if (!valid) return;

    setImporting(true);
    setImportError('');

    try {
      const res = await fetch('/api/v1/workflows/import', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ format, data }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const detail = (body as Record<string, string>).detail || `Import failed (${res.status})`;
        setImportError(detail);
        return;
      }

      const result = (await res.json()) as ImportResult;
      setImportResult(result);
    } catch {
      setImportError('Network error during import');
    } finally {
      setImporting(false);
    }
  }, [rawJson, format]);

  // ------- Derived state -------

  const jsonIsValid = rawJson.trim().length > 0 && tryParseJson(rawJson).valid;
  const lineCount = rawJson.trim().length > 0 ? countJsonLines(rawJson) : 0;
  const parsedData = jsonIsValid ? tryParseJson(rawJson).data : null;
  const nodeCount = parsedData ? detectNodeCount(parsedData) : null;

  // ------- Render -------

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      {/* Step indicator */}
      <div className="flex items-center gap-2 text-sm text-slate-400">
        <span className={step === 1 ? 'font-bold text-indigo-400' : ''}>1. Format</span>
        <span>{'>'}</span>
        <span className={step === 2 ? 'font-bold text-indigo-400' : ''}>2. JSON</span>
        <span>{'>'}</span>
        <span className={step === 3 ? 'font-bold text-indigo-400' : ''}>3. Import</span>
      </div>

      {/* ── Step 1: Select Format ── */}
      {step === 1 && (
        <div className="space-y-4" data-testid="step-1">
          <h3 className="text-lg font-semibold text-slate-100">Select Workflow Format</h3>

          <fieldset className="space-y-2">
            <legend className="sr-only">Workflow format</legend>
            {(Object.keys(FORMAT_LABELS) as ImportFormat[]).map((key) => (
              <label
                key={key}
                className="flex cursor-pointer items-center gap-3 rounded-lg border border-slate-700 bg-slate-800/50 px-4 py-3 hover:border-indigo-500/50"
              >
                <input
                  type="radio"
                  name="import-format"
                  value={key}
                  checked={format === key}
                  onChange={() => setFormat(key)}
                  className="accent-indigo-500"
                />
                <span className="text-slate-200">{FORMAT_LABELS[key]}</span>
              </label>
            ))}
          </fieldset>

          <button
            onClick={goToStep2}
            className="rounded-lg bg-indigo-600 px-6 py-2 font-semibold text-white hover:bg-indigo-500"
          >
            Next
          </button>
        </div>
      )}

      {/* ── Step 2: Paste or Upload JSON ── */}
      {step === 2 && (
        <div className="space-y-4" data-testid="step-2">
          <h3 className="text-lg font-semibold text-slate-100">Paste or Upload JSON</h3>

          <div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".json"
              onChange={handleFileUpload}
              className="block text-sm text-slate-400 file:mr-4 file:rounded-lg file:border-0 file:bg-slate-700 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-slate-200 hover:file:bg-slate-600"
            />
          </div>

          <textarea
            value={rawJson}
            onChange={handleTextareaChange}
            placeholder="Paste your workflow JSON here..."
            rows={12}
            className="w-full rounded-lg border border-slate-700 bg-slate-900 p-3 font-mono text-sm text-slate-200 placeholder:text-slate-500 focus:border-indigo-500 focus:outline-none"
            data-testid="json-textarea"
          />

          {parseError && (
            <p className="text-sm text-red-400" role="alert" data-testid="parse-error">
              {parseError}
            </p>
          )}

          <div className="flex gap-3">
            <button
              onClick={() => setStep(1)}
              className="rounded-lg border border-slate-600 px-6 py-2 font-semibold text-slate-300 hover:bg-slate-800"
            >
              Back
            </button>
            <button
              onClick={goToStep3}
              disabled={!jsonIsValid}
              className="rounded-lg bg-indigo-600 px-6 py-2 font-semibold text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
              data-testid="step2-next"
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* ── Step 3: Review & Import ── */}
      {step === 3 && (
        <div className="space-y-4" data-testid="step-3">
          <h3 className="text-lg font-semibold text-slate-100">Review & Import</h3>

          {/* Summary */}
          <div className="rounded-lg border border-slate-700 bg-slate-800/50 p-4 space-y-2">
            <p className="text-slate-300">
              <span className="font-semibold text-slate-100">Format:</span>{' '}
              <span data-testid="review-format">{FORMAT_LABELS[format]}</span>
            </p>
            <p className="text-slate-300">
              <span className="font-semibold text-slate-100">JSON lines:</span> {lineCount}
            </p>
            {nodeCount !== null && (
              <p className="text-slate-300">
                <span className="font-semibold text-slate-100">Nodes detected:</span> {nodeCount}
              </p>
            )}
          </div>

          {/* Import result */}
          {importResult && (
            <div className="rounded-lg border border-green-700/50 bg-green-900/20 p-4 space-y-2">
              <p className="font-semibold text-green-400" data-testid="import-success">
                Imported! {importResult.nodes_imported} nodes, {importResult.edges_imported} edges
              </p>
              <button
                onClick={() => navigate(`/editor/${importResult.flow_id}`)}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500"
                data-testid="open-editor-link"
              >
                Open in Editor
              </button>
            </div>
          )}

          {/* Import error */}
          {importError && (
            <div className="rounded-lg border border-red-700/50 bg-red-900/20 p-4" role="alert">
              <p className="text-red-400" data-testid="import-error">{importError}</p>
            </div>
          )}

          {/* Action buttons */}
          {!importResult && (
            <div className="flex gap-3">
              <button
                onClick={goBackToStep2}
                className="rounded-lg border border-slate-600 px-6 py-2 font-semibold text-slate-300 hover:bg-slate-800"
              >
                Back
              </button>
              <button
                onClick={handleImport}
                disabled={importing}
                className="rounded-lg bg-indigo-600 px-6 py-2 font-semibold text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
                data-testid="import-button"
              >
                {importing ? 'Importing...' : 'Import'}
              </button>
            </div>
          )}

          {/* Back button shown on error (alongside action buttons above) */}
          {importError && importResult === null && null}
        </div>
      )}
    </div>
  );
};

export default WorkflowImportWizard;
