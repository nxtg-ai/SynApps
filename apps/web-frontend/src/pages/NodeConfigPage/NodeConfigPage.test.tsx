import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import NodeConfigPage from './NodeConfigPage';

/** Wrap in MemoryRouter because MainLayout uses react-router Link components. */
function renderPage() {
  return render(
    <MemoryRouter>
      <NodeConfigPage />
    </MemoryRouter>,
  );
}

describe('NodeConfigPage', () => {
  it('renders "Node Configuration" heading', () => {
    renderPage();
    const headings = screen.getAllByRole('heading', { name: /Node Configuration/i });
    expect(headings.length).toBeGreaterThanOrEqual(1);
    expect(headings[0]).toBeInTheDocument();
  });

  it('renders the schema form', () => {
    renderPage();
    expect(screen.getByTestId('schema-form')).toBeInTheDocument();
  });

  it('shows current values as JSON', () => {
    renderPage();
    const preview = screen.getByTestId('json-preview');
    expect(preview).toBeInTheDocument();
    expect(preview.textContent).toContain('{');
  });

  it('shows Save Config button', () => {
    renderPage();
    expect(screen.getByRole('button', { name: /Save Config/i })).toBeInTheDocument();
  });

  it('shows Reset button', () => {
    renderPage();
    expect(screen.getByRole('button', { name: /Reset/i })).toBeInTheDocument();
  });

  it('clicking Reset clears values', () => {
    renderPage();
    // Type into a field first
    const apiKeyInput = screen.getByLabelText(/API Key/);
    fireEvent.change(apiKeyInput, { target: { value: 'test-key' } });

    const preview = screen.getByTestId('json-preview');
    expect(preview.textContent).toContain('test-key');

    // Click Reset
    fireEvent.click(screen.getByRole('button', { name: /Reset/i }));
    expect(preview.textContent).not.toContain('test-key');
  });

  it('clicking Save Config shows success message', () => {
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /Save Config/i }));
    expect(screen.getByRole('status')).toHaveTextContent(/saved successfully/i);
  });

  it('form onChange updates the JSON preview', () => {
    renderPage();
    const apiKeyInput = screen.getByLabelText(/API Key/);
    fireEvent.change(apiKeyInput, { target: { value: 'my-secret' } });

    const preview = screen.getByTestId('json-preview');
    expect(preview.textContent).toContain('my-secret');
  });
});
