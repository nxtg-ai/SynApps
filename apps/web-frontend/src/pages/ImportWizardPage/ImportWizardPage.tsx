/**
 * ImportWizardPage -- Full-page wrapper for the WorkflowImportWizard.
 *
 * Route: /import-wizard (ProtectedRoute)
 */
import React from 'react';
import MainLayout from '../../components/Layout/MainLayout';
import WorkflowImportWizard from '../../components/WorkflowImportWizard/WorkflowImportWizard';

const ImportWizardPage: React.FC = () => {
  return (
    <MainLayout title="Import Workflow">
      <div style={{ maxWidth: 800, margin: '0 auto', padding: 24 }}>
        <h2 className="mb-6 text-xl font-bold text-slate-100">Import Workflow</h2>
        <WorkflowImportWizard />
      </div>
    </MainLayout>
  );
};

export default ImportWizardPage;
