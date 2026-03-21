import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import NodeConfigModal from './NodeConfigModal';

const baseProps = {
  isOpen: true,
  onClose: vi.fn(),
  nodeId: 'node-1',
  onSave: vi.fn(),
};

describe('NodeConfigModal — Memory Node', () => {
  it('renders operation select with store as default', () => {
    render(
      <NodeConfigModal
        {...baseProps}
        nodeType="memory"
        nodeData={{ label: 'Memory' }}
      />,
    );
    const select = screen.getByLabelText('Operation') as HTMLSelectElement;
    expect(select).toBeDefined();
    expect(select.value).toBe('store');
    const options = Array.from(select.options).map((o) => o.value);
    expect(options).toEqual(['store', 'retrieve', 'delete', 'clear']);
  });

  it('renders backend select with sqlite_fts as default', () => {
    render(
      <NodeConfigModal
        {...baseProps}
        nodeType="memory"
        nodeData={{ label: 'Memory' }}
      />,
    );
    const select = screen.getByLabelText('Backend') as HTMLSelectElement;
    expect(select.value).toBe('sqlite_fts');
    const options = Array.from(select.options).map((o) => o.value);
    expect(options.length).toBeGreaterThanOrEqual(2); // Gate 2: non-empty
    expect(options).toContain('chroma');
  });

  it('hides chroma-specific fields when backend is sqlite_fts', () => {
    render(
      <NodeConfigModal
        {...baseProps}
        nodeType="memory"
        nodeData={{ label: 'Memory', backend: 'sqlite_fts' }}
      />,
    );
    expect(screen.queryByLabelText('Collection Name')).toBeNull();
    expect(screen.queryByLabelText('Persist Path')).toBeNull();
  });

  it('shows chroma-specific fields when backend is chroma', () => {
    render(
      <NodeConfigModal
        {...baseProps}
        nodeType="memory"
        nodeData={{ label: 'Memory', backend: 'chroma' }}
      />,
    );
    expect(screen.getByLabelText('Collection Name')).toBeDefined();
    expect(screen.getByLabelText('Persist Path')).toBeDefined();
  });

  it('reveals chroma fields after switching backend to chroma', () => {
    render(
      <NodeConfigModal
        {...baseProps}
        nodeType="memory"
        nodeData={{ label: 'Memory', backend: 'sqlite_fts' }}
      />,
    );
    const backendSelect = screen.getByLabelText('Backend');
    fireEvent.change(backendSelect, { target: { value: 'chroma' } });
    expect(screen.getByLabelText('Collection Name')).toBeDefined();
  });

  it('saves all memory config fields on submit', () => {
    const onSave = vi.fn();
    render(
      <NodeConfigModal
        {...baseProps}
        onSave={onSave}
        nodeType="memory"
        nodeData={{
          label: 'My Memory',
          operation: 'retrieve',
          backend: 'sqlite_fts',
          namespace: 'test-ns',
          top_k: 10,
          include_metadata: true,
        }}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    expect(onSave).toHaveBeenCalledOnce();
    const [savedNodeId, savedData] = onSave.mock.calls[0];
    expect(savedNodeId).toBe('node-1');
    expect(savedData.operation).toBe('retrieve');
    expect(savedData.backend).toBe('sqlite_fts');
    expect(savedData.namespace).toBe('test-ns');
    expect(savedData.top_k).toBe(10);
    expect(savedData.include_metadata).toBe(true);
  });

  it('saves chroma-specific fields', () => {
    const onSave = vi.fn();
    render(
      <NodeConfigModal
        {...baseProps}
        onSave={onSave}
        nodeType="memory"
        nodeData={{
          label: 'Chroma Memory',
          backend: 'chroma',
          collection: 'my_collection',
          persist_path: '/tmp/chroma',
        }}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    const [, savedData] = onSave.mock.calls[0];
    expect(savedData.collection).toBe('my_collection');
    expect(savedData.persist_path).toBe('/tmp/chroma');
  });

  it('does not render when isOpen is false', () => {
    const { container } = render(
      <NodeConfigModal
        {...baseProps}
        isOpen={false}
        nodeType="memory"
        nodeData={{}}
      />,
    );
    expect(container.firstChild).toBeNull();
  });
});

describe('NodeConfigModal — Plugin Node (default case)', () => {
  const pluginSchema = {
    type: 'object',
    properties: {
      api_key: { type: 'string', title: 'API Key' },
      max_retries: { type: 'number', title: 'Max Retries' },
    },
    required: ['api_key'],
  };

  it('renders generic label input for unknown nodeType without config_schema', () => {
    render(
      <NodeConfigModal
        {...baseProps}
        nodeType="custom_unknown"
        nodeData={{ label: 'My Plugin' }}
      />,
    );
    const labelInput = screen.getByLabelText('Node Label') as HTMLInputElement;
    expect(labelInput).toBeDefined();
    expect(labelInput.value).toBe('My Plugin');
    // SchemaForm should NOT be present
    expect(screen.queryByTestId('schema-form')).toBeNull();
  });

  it('renders SchemaForm when nodeData has config_schema', () => {
    render(
      <NodeConfigModal
        {...baseProps}
        nodeType="custom_plugin"
        nodeData={{ label: 'Plugin Node', config_schema: pluginSchema }}
      />,
    );
    // Both the label input and SchemaForm should be present
    expect(screen.getByLabelText('Node Label')).toBeDefined();
    expect(screen.getByTestId('schema-form')).toBeDefined();
    expect(screen.getByText('Plugin Configuration')).toBeDefined();
  });

  it('SchemaForm receives correct schema prop', () => {
    render(
      <NodeConfigModal
        {...baseProps}
        nodeType="custom_plugin"
        nodeData={{ label: 'Plugin Node', config_schema: pluginSchema }}
      />,
    );
    // The schema fields should be rendered by SchemaForm (exact: false to ignore required asterisk)
    expect(screen.getByLabelText('API Key', { exact: false })).toBeDefined();
    expect(screen.getByLabelText('Max Retries', { exact: false })).toBeDefined();
  });

  it('SchemaForm value updates are reflected in formData on save', () => {
    const onSave = vi.fn();
    render(
      <NodeConfigModal
        {...baseProps}
        onSave={onSave}
        nodeType="custom_plugin"
        nodeData={{ label: 'Plugin', config_schema: pluginSchema }}
      />,
    );
    // Fill in the API Key field rendered by SchemaForm
    const apiKeyInput = screen.getByLabelText('API Key', { exact: false }) as HTMLInputElement;
    fireEvent.change(apiKeyInput, { target: { value: 'sk-test-123' } });

    // Save and verify formData includes the SchemaForm value
    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    expect(onSave).toHaveBeenCalledOnce();
    const [savedNodeId, savedData] = onSave.mock.calls[0];
    expect(savedNodeId).toBe('node-1');
    expect(savedData.api_key).toBe('sk-test-123');
    expect(savedData.label).toBe('Plugin');
  });
});
