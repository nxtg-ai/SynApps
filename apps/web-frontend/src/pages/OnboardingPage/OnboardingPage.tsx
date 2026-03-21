/**
 * OnboardingPage - Full-screen page wrapper for the OnboardingWizard.
 *
 * Route: /onboarding
 * No MainLayout wrapper — provides a distraction-free onboarding experience.
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import OnboardingWizard from '../../components/OnboardingWizard/OnboardingWizard';

const OnboardingPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <OnboardingWizard
      onComplete={() => navigate('/dashboard')}
      onDismiss={() => navigate('/')}
    />
  );
};

export default OnboardingPage;
