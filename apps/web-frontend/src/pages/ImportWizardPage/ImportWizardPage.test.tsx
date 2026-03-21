/**
 * Tests for ImportWizardPage -- N-62 Workflow Import Wizard page wrapper.
 *
 * 4 tests covering page render.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect } from 'vitest';

vi.mock('../../components/Layout/MainLayout', () => ({
  default: ({ children, title }: { children: React.ReactNode; title: string }) => (
    <div data-testid="main-layout" data-title={title}>
      {children}
    </div>
  ),
}));

import ImportWizardPage from './ImportWizardPage';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderPage() {
  return render(
    <MemoryRouter>
      <ImportWizardPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ImportWizardPage', () => {
  // 1. renders within MainLayout
  it('renders within MainLayout', () => {
    renderPage();
    expect(screen.getByTestId('main-layout')).toBeInTheDocument();
  });

  // 2. passes "Import Workflow" as MainLayout title
  it('passes "Import Workflow" as MainLayout title', () => {
    renderPage();
    expect(screen.getByTestId('main-layout').getAttribute('data-title')).toBe('Import Workflow');
  });

  // 3. renders "Import Workflow" heading
  it('renders "Import Workflow" heading', () => {
    renderPage();
    expect(screen.getByText('Import Workflow')).toBeInTheDocument();
  });

  // 4. renders wizard step 1 (format selection) by default
  it('renders wizard step 1 with format radio buttons', () => {
    renderPage();
    const radios = screen.getAllByRole('radio');
    expect(radios).toBeTruthy();
    expect(radios.length).toBeGreaterThanOrEqual(1); // Gate 2
    expect(radios.length).toBe(3);
  });
});
