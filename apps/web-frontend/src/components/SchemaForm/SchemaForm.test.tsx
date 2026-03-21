import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import SchemaForm from './SchemaForm';

const SCHEMA = {
  type: 'object',
  required: ['apiKey'],
  properties: {
    apiKey: { type: 'string', title: 'API Key', description: 'Your secret API key' },
    retries: { type: 'integer', title: 'Retries', default: 3 },
    enabled: { type: 'boolean', title: 'Enabled', default: true },
    tags: { type: 'array', title: 'Tags', items: { type: 'string' } },
    nested: {
      type: 'object',
      title: 'Advanced',
      properties: { timeout: { type: 'number', title: 'Timeout' } },
    },
  },
};

describe('SchemaForm', () => {
  it('renders string field with label from title', () => {
    render(<SchemaForm schema={SCHEMA} value={{}} onChange={() => {}} />);
    expect(screen.getByLabelText(/API Key/)).toBeInTheDocument();
  });

  it('renders string field label fallback from key name', () => {
    const schema = {
      type: 'object',
      properties: {
        myFieldName: { type: 'string' },
      },
    };
    render(<SchemaForm schema={schema} value={{}} onChange={() => {}} />);
    expect(screen.getByLabelText(/My Field Name/)).toBeInTheDocument();
  });

  it('renders number field', () => {
    render(<SchemaForm schema={SCHEMA} value={{}} onChange={() => {}} />);
    const retriesInput = screen.getByLabelText(/Retries/);
    expect(retriesInput).toBeInTheDocument();
    expect(retriesInput).toHaveAttribute('type', 'number');
  });

  it('renders boolean as checkbox', () => {
    render(<SchemaForm schema={SCHEMA} value={{}} onChange={() => {}} />);
    const checkbox = screen.getByLabelText(/Enabled/);
    expect(checkbox).toBeInTheDocument();
    expect(checkbox).toHaveAttribute('type', 'checkbox');
  });

  it('renders array field as comma-separated text', () => {
    render(
      <SchemaForm schema={SCHEMA} value={{ tags: ['a', 'b', 'c'] }} onChange={() => {}} />,
    );
    const tagsInput = screen.getByLabelText(/Tags/);
    expect(tagsInput).toHaveValue('a, b, c');
  });

  it('marks required fields with asterisk', () => {
    render(<SchemaForm schema={SCHEMA} value={{}} onChange={() => {}} />);
    const apiKeyLabel = screen.getByText(/API Key/);
    const container = apiKeyLabel.closest('label') ?? apiKeyLabel.parentElement;
    expect(container?.textContent).toContain('*');
  });

  it('shows description helper text', () => {
    render(<SchemaForm schema={SCHEMA} value={{}} onChange={() => {}} />);
    expect(screen.getByText('Your secret API key')).toBeInTheDocument();
  });

  it('calls onChange when string field changes', () => {
    const onChange = vi.fn();
    render(<SchemaForm schema={SCHEMA} value={{}} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText(/API Key/), { target: { value: 'sk-123' } });
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ apiKey: 'sk-123' }));
  });

  it('calls onChange when number field changes', () => {
    const onChange = vi.fn();
    render(<SchemaForm schema={SCHEMA} value={{}} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText(/Retries/), { target: { value: '5' } });
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ retries: 5 }));
  });

  it('calls onChange when checkbox toggled', () => {
    const onChange = vi.fn();
    render(<SchemaForm schema={SCHEMA} value={{ enabled: false }} onChange={onChange} />);
    fireEvent.click(screen.getByLabelText(/Enabled/));
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ enabled: true }));
  });

  it('calls onChange when array field changes (splits on comma)', () => {
    const onChange = vi.fn();
    render(<SchemaForm schema={SCHEMA} value={{}} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText(/Tags/), { target: { value: 'foo, bar' } });
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ tags: ['foo', 'bar'] }));
  });

  it('renders nested object fields', () => {
    render(<SchemaForm schema={SCHEMA} value={{}} onChange={() => {}} />);
    expect(screen.getByText('Advanced')).toBeInTheDocument();
    expect(screen.getByLabelText(/Timeout/)).toBeInTheDocument();
  });

  it('pre-populates field from default value', () => {
    render(<SchemaForm schema={SCHEMA} value={{}} onChange={() => {}} />);
    const retriesInput = screen.getByLabelText(/Retries/);
    expect(retriesInput).toHaveValue(3);
  });

  it('disables all inputs when disabled=true', () => {
    render(<SchemaForm schema={SCHEMA} value={{}} onChange={() => {}} disabled />);
    const inputs = screen.getAllByRole('textbox');
    const checkboxes = screen.getAllByRole('checkbox');
    const spinbuttons = screen.getAllByRole('spinbutton');
    [...inputs, ...checkboxes, ...spinbuttons].forEach((el) => {
      expect(el).toBeDisabled();
    });
  });
});
