/**
 * Main App component
 */
import React, { useEffect } from 'react';
import {
  BrowserRouter as Router,
  Routes,
  Route,
  Navigate,
  Link,
  useLocation,
  useNavigate,
} from 'react-router-dom';
import webSocketService from './services/WebSocketService';
import { Button } from './components/ui/button';
import { useSettingsStore } from './stores/settingsStore';
import { useAuthStore } from './stores/authStore';
import ProtectedRoute from './components/ProtectedRoute';
import GuestRoute from './components/GuestRoute';

const DashboardPage = React.lazy(() => import('./pages/DashboardPage/DashboardPage'));
const EditorPage = React.lazy(() => import('./pages/EditorPage/EditorPage'));
const HistoryPage = React.lazy(() => import('./pages/HistoryPage/HistoryPage'));
const AppletLibraryPage = React.lazy(() => import('./pages/AppletLibraryPage/AppletLibraryPage'));
const SettingsPage = React.lazy(() => import('./pages/SettingsPage/SettingsPage'));
const AnalyticsDashboard = React.lazy(
  () => import('./pages/AnalyticsDashboard/AnalyticsDashboard'),
);
const NotFoundPage = React.lazy(() => import('./pages/NotFoundPage/NotFoundPage'));
const LoginPage = React.lazy(() => import('./pages/LoginPage/LoginPage'));
const RegisterPage = React.lazy(() => import('./pages/RegisterPage/RegisterPage'));
const PricingPage = React.lazy(() => import('./pages/PricingPage/PricingPage'));
const PlaygroundPage = React.lazy(() => import('./pages/PlaygroundPage/PlaygroundPage'));
const GalleryPage = React.lazy(() => import('./pages/GalleryPage/GalleryPage'));
const WorkflowDiffPage = React.lazy(() => import('./pages/WorkflowDiffPage/WorkflowDiffPage'));
const PublisherDashboardPage = React.lazy(
  () => import('./pages/PublisherDashboardPage/PublisherDashboardPage'),
);
const CreditsPage = React.lazy(() => import('./pages/CreditsPage/CreditsPage'));
const TemplateWizardPage = React.lazy(
  () => import('./pages/TemplateWizardPage/TemplateWizardPage'),
);
const SLADashboardPage = React.lazy(() => import('./pages/SLADashboardPage/SLADashboardPage'));
const WebhookDebuggerPage = React.lazy(
  () => import('./pages/WebhookDebuggerPage/WebhookDebuggerPage'),
);
const AdminFeaturedPage = React.lazy(() => import('./pages/AdminFeaturedPage/AdminFeaturedPage'));
const RollbackPage = React.lazy(() => import('./pages/RollbackPage/RollbackPage'));
const SearchPage = React.lazy(() => import('./pages/SearchPage/SearchPage'));
const PublisherAnalyticsDashboard = React.lazy(
  () => import('./pages/PublisherAnalyticsDashboard/PublisherAnalyticsDashboard'),
);
const ExecutionDashboardPage = React.lazy(
  () => import('./pages/ExecutionDashboardPage/ExecutionDashboardPage'),
);
const TestRunnerPage = React.lazy(
  () => import('./pages/TestRunnerPage/TestRunnerPage'),
);
const OnboardingPage = React.lazy(
  () => import('./pages/OnboardingPage/OnboardingPage'),
);

/**
 * Check whether the onboarding wizard should auto-trigger for new users.
 * Redirects to /onboarding if the user is authenticated and has not completed setup.
 */
function useOnboardingRedirect(): void {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const isLoading = useAuthStore((s) => s.isLoading);
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    if (isLoading || !isAuthenticated) return;
    // Only redirect from dashboard (entry point after login)
    if (location.pathname !== '/dashboard') return;

    try {
      const raw = localStorage.getItem('synapps_onboarding');
      if (!raw) {
        // First visit — send to onboarding
        navigate('/onboarding', { replace: true });
        return;
      }
      const progress = JSON.parse(raw);
      if (progress && !progress.completed?.every(Boolean)) {
        // Incomplete onboarding — do not force redirect, let the "Resume Setup"
        // link in MainLayout handle it. Only redirect on very first visit.
      }
    } catch {
      // corrupt data — treat as new user
      navigate('/onboarding', { replace: true });
    }
  }, [isAuthenticated, isLoading, location.pathname, navigate]);
}

const AppRoutes: React.FC = () => {
  const location = useLocation();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const showShortcut = isAuthenticated && location.pathname !== '/dashboard';

  useOnboardingRedirect();

  return (
    <div className="min-h-screen bg-slate-950 text-slate-900">
      {showShortcut ? (
        <header className="sticky top-0 z-40 border-b border-slate-800/80 bg-slate-950/85 backdrop-blur-sm text-slate-100">
          <div className="mx-auto flex h-12 max-w-7xl items-center justify-end px-4">
            <Button asChild size="sm" variant="outline">
              <Link to="/dashboard">Dashboard</Link>
            </Button>
          </div>
        </header>
      ) : null}

      <React.Suspense
        fallback={
          <div className="mx-auto flex min-h-[40vh] max-w-7xl items-center justify-center px-4 text-sm text-slate-300">
            Loading page...
          </div>
        }
      >
        <Routes>
          {/* Public routes — no auth required */}
          <Route path="/onboarding" element={<OnboardingPage />} />
          <Route path="/pricing" element={<PricingPage />} />

          {/* Guest-only routes */}
          <Route
            path="/login"
            element={
              <GuestRoute>
                <LoginPage />
              </GuestRoute>
            }
          />
          <Route
            path="/register"
            element={
              <GuestRoute>
                <RegisterPage />
              </GuestRoute>
            }
          />

          {/* Protected routes */}
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <DashboardPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/editor/:flowId?"
            element={
              <ProtectedRoute>
                <EditorPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/history"
            element={
              <ProtectedRoute>
                <HistoryPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/applets"
            element={
              <ProtectedRoute>
                <AppletLibraryPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/settings"
            element={
              <ProtectedRoute>
                <SettingsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/analytics"
            element={
              <ProtectedRoute>
                <AnalyticsDashboard />
              </ProtectedRoute>
            }
          />
          <Route
            path="/playground"
            element={
              <ProtectedRoute>
                <PlaygroundPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/gallery"
            element={
              <ProtectedRoute>
                <GalleryPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/publisher/dashboard"
            element={
              <ProtectedRoute>
                <PublisherDashboardPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/publisher/credits"
            element={
              <ProtectedRoute>
                <CreditsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/wizard"
            element={
              <ProtectedRoute>
                <TemplateWizardPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/workflows/:id/diff"
            element={
              <ProtectedRoute>
                <WorkflowDiffPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/sla"
            element={
              <ProtectedRoute>
                <SLADashboardPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/webhooks/debug"
            element={
              <ProtectedRoute>
                <WebhookDebuggerPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/featured"
            element={
              <ProtectedRoute>
                <AdminFeaturedPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/executions"
            element={
              <ProtectedRoute>
                <ExecutionDashboardPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/workflows/:id/rollback"
            element={
              <ProtectedRoute>
                <RollbackPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/workflows/:id/tests"
            element={
              <ProtectedRoute>
                <TestRunnerPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/publisher/analytics/:listingId?"
            element={
              <ProtectedRoute>
                <PublisherAnalyticsDashboard />
              </ProtectedRoute>
            }
          />
          <Route
            path="/search"
            element={
              <ProtectedRoute>
                <SearchPage />
              </ProtectedRoute>
            }
          />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </React.Suspense>
    </div>
  );
};

const App: React.FC = () => {
  const loadSettings = useSettingsStore((state) => state.loadSettings);
  const darkMode = useSettingsStore((state) => state.darkMode);
  const loadAuth = useAuthStore((s) => s.loadAuth);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  // Hydrate auth state from localStorage (synchronous – no flash)
  useEffect(() => {
    loadAuth();
  }, [loadAuth]);

  // Only connect WebSocket when authenticated
  useEffect(() => {
    if (isAuthenticated) {
      webSocketService.connect();
      return () => {
        webSocketService.disconnect();
      };
    }
  }, [isAuthenticated]);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', darkMode);
  }, [darkMode]);

  return (
    <Router>
      <AppRoutes />
    </Router>
  );
};

export default App;
