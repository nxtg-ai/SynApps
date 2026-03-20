/**
 * TemplateWizardPage - Thin page wrapper for the TemplateWizard component.
 *
 * Route: /wizard
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import MainLayout from '../../components/Layout/MainLayout';
import TemplateWizard from '../../components/TemplateWizard/TemplateWizard';

const TemplateWizardPage: React.FC = () => {
  const navigate = useNavigate();

  const handleComplete = (_listingId: string) => {
    navigate('/gallery');
  };

  return (
    <MainLayout title="Workflow Wizard">
      <TemplateWizard onComplete={handleComplete} />
    </MainLayout>
  );
};

export default TemplateWizardPage;
