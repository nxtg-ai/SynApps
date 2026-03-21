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
const CollaborationPage = React.lazy(
  () => import('./pages/CollaborationPage/CollaborationPage'),
);
const PluginManagerPage = React.lazy(
  () => import('./pages/PluginManagerPage/PluginManagerPage'),
);
const NodeConfigPage = React.lazy(
  () => import('./pages/NodeConfigPage/NodeConfigPage'),
);
const ImportWizardPage = React.lazy(
  () => import('./pages/ImportWizardPage/ImportWizardPage'),
);
const ApiKeyManagerPage = React.lazy(
  () => import('./pages/ApiKeyManagerPage/ApiKeyManagerPage'),
);
const NodeProfilerPage = React.lazy(
  () => import('./pages/NodeProfilerPage/NodeProfilerPage'),
);
const MonitoringPage = React.lazy(
  () => import('./pages/MonitoringPage/MonitoringPage'),
);
const AiAssistPage = React.lazy(
  () => import('./pages/AiAssistPage/AiAssistPage'),
);
const WorkflowDebugPage = React.lazy(
  () => import('./pages/WorkflowDebugPage/WorkflowDebugPage'),
);
const WorkflowVarsPage = React.lazy(
  () => import('./pages/WorkflowVarsPage/WorkflowVarsPage'),
);
const AuditTrailPage = React.lazy(
  () => import('./pages/AuditTrailPage/AuditTrailPage'),
);
const SchedulesPage = React.lazy(
  () => import('./pages/SchedulesPage/SchedulesPage'),
);
const DLQPage = React.lazy(
  () => import('./pages/DLQPage/DLQPage'),
);
const WorkflowNotificationsPage = React.lazy(
  () => import('./pages/WorkflowNotificationsPage/WorkflowNotificationsPage'),
);
const ExecutionLogsPage = React.lazy(
  () => import('./pages/ExecutionLogsPage/ExecutionLogsPage'),
);
const UsagePage = React.lazy(
  () => import('./pages/UsagePage/UsagePage'),
);
const CostTrackerPage = React.lazy(
  () => import('./pages/CostTrackerPage/CostTrackerPage'),
);
const WorkflowPermissionsPage = React.lazy(
  () => import('./pages/WorkflowPermissionsPage/WorkflowPermissionsPage'),
);
const ConnectorsPage = React.lazy(
  () => import('./pages/ConnectorsPage/ConnectorsPage'),
);
const SubflowsPage = React.lazy(
  () => import('./pages/SubflowsPage/SubflowsPage'),
);
const WorkflowActivityPage = React.lazy(
  () => import('./pages/WorkflowActivityPage/WorkflowActivityPage'),
);
const RunTracePage = React.lazy(
  () => import('./pages/RunTracePage/RunTracePage'),
);
const QuotaManagerPage = React.lazy(
  () => import('./pages/QuotaManagerPage/QuotaManagerPage'),
);
const FailedRequestsPage = React.lazy(
  () => import('./pages/FailedRequestsPage/FailedRequestsPage'),
);
const WebhookTriggersPage = React.lazy(
  () => import('./pages/WebhookTriggersPage/WebhookTriggersPage'),
);
const ExecutionReplayPage = React.lazy(
  () => import('./pages/ExecutionReplayPage/ExecutionReplayPage'),
);
const ProviderStatusPage = React.lazy(
  () => import('./pages/ProviderStatusPage/ProviderStatusPage'),
);
const TaskMonitorPage = React.lazy(
  () => import('./pages/TaskMonitorPage/TaskMonitorPage'),
);
const CostEstimatorPage = React.lazy(
  () => import('./pages/CostEstimatorPage/CostEstimatorPage'),
);
const AppletsRegistryPage = React.lazy(
  () => import('./pages/AppletsRegistryPage/AppletsRegistryPage'),
);
const OAuthClientsPage = React.lazy(
  () => import('./pages/OAuthClientsPage/OAuthClientsPage'),
);
const TemplateManagerPage = React.lazy(
  () => import('./pages/TemplateManagerPage/TemplateManagerPage'),
);
const FlowVersionsPage = React.lazy(
  () => import('./pages/FlowVersionsPage/FlowVersionsPage'),
);
const ServerInfoPage = React.lazy(
  () => import('./pages/ServerInfoPage/ServerInfoPage'),
);
const ManagedKeysPage = React.lazy(
  () => import('./pages/ManagedKeysPage/ManagedKeysPage'),
);
const AdminKeysPage = React.lazy(
  () => import('./pages/AdminKeysPage/AdminKeysPage'),
);
const MarketplaceReviewsPage = React.lazy(
  () => import('./pages/MarketplaceReviewsPage/MarketplaceReviewsPage'),
);
const WebhookRegistryPage = React.lazy(
  () => import('./pages/WebhookRegistryPage/WebhookRegistryPage'),
);
const TemplateToolsPage = React.lazy(
  () => import('./pages/TemplateToolsPage/TemplateToolsPage'),
);
const NodeCommentsPage = React.lazy(
  () => import('./pages/NodeCommentsPage/NodeCommentsPage'),
);
const PortfolioDashboardPage = React.lazy(
  () => import('./pages/PortfolioDashboardPage/PortfolioDashboardPage'),
);
const FlowTestingPage = React.lazy(() => import('./pages/FlowTestingPage/FlowTestingPage'));
const DebugSessionPage = React.lazy(() => import('./pages/DebugSessionPage/DebugSessionPage'));
const SystemConfigPage = React.lazy(() => import('./pages/SystemConfigPage/SystemConfigPage'));
const MonitoringAlertsPage = React.lazy(
  () => import('./pages/MonitoringAlertsPage/MonitoringAlertsPage'),
);
const WorkflowSecretsPage = React.lazy(
  () => import('./pages/WorkflowSecretsPage/WorkflowSecretsPage'),
);
const ConnectorProbePage = React.lazy(
  () => import('./pages/ConnectorProbePage/ConnectorProbePage'),
);
const WorkflowTestRunnerPage = React.lazy(
  () => import('./pages/WorkflowTestRunnerPage/WorkflowTestRunnerPage'),
);
const OAuthInspectorPage = React.lazy(
  () => import('./pages/OAuthInspectorPage/OAuthInspectorPage'),
);
const CollabLocksPage = React.lazy(
  () => import('./pages/CollabLocksPage/CollabLocksPage'),
);
const AnalyticsDetailPage = React.lazy(
  () => import('./pages/AnalyticsDetailPage/AnalyticsDetailPage'),
);
const MarketplaceDiscoveryPage = React.lazy(
  () => import('./pages/MarketplaceDiscoveryPage/MarketplaceDiscoveryPage'),
);
const FlowTestDetailPage = React.lazy(
  () => import('./pages/FlowTestDetailPage/FlowTestDetailPage'),
);
const UsageDetailPage = React.lazy(
  () => import('./pages/UsageDetailPage/UsageDetailPage'),
);
const FlowExportImportPage = React.lazy(
  () => import('./pages/FlowExportImportPage/FlowExportImportPage'),
);
const RunsPage = React.lazy(() => import('./pages/RunsPage/RunsPage'));
const WorkflowSnapshotsPage = React.lazy(
  () => import('./pages/WorkflowSnapshotsPage/WorkflowSnapshotsPage'),
);
const ListingAnalyticsDetailPage = React.lazy(
  () => import('./pages/ListingAnalyticsDetailPage/ListingAnalyticsDetailPage'),
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
          <Route
            path="/collaboration"
            element={
              <ProtectedRoute>
                <CollaborationPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/plugins"
            element={
              <ProtectedRoute>
                <PluginManagerPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/node-config"
            element={
              <ProtectedRoute>
                <NodeConfigPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/import-wizard"
            element={
              <ProtectedRoute>
                <ImportWizardPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/api-keys"
            element={
              <ProtectedRoute>
                <ApiKeyManagerPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/node-profiler"
            element={
              <ProtectedRoute>
                <NodeProfilerPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/monitoring"
            element={
              <ProtectedRoute>
                <MonitoringPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/ai-assist"
            element={
              <ProtectedRoute>
                <AiAssistPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/workflow-debug"
            element={
              <ProtectedRoute>
                <WorkflowDebugPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/workflow-vars"
            element={
              <ProtectedRoute>
                <WorkflowVarsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/audit-trail"
            element={
              <ProtectedRoute>
                <AuditTrailPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/schedules"
            element={
              <ProtectedRoute>
                <SchedulesPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/dlq"
            element={
              <ProtectedRoute>
                <DLQPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/workflow-notifications"
            element={
              <ProtectedRoute>
                <WorkflowNotificationsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/execution-logs"
            element={
              <ProtectedRoute>
                <ExecutionLogsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/usage"
            element={
              <ProtectedRoute>
                <UsagePage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/cost-tracker"
            element={
              <ProtectedRoute>
                <CostTrackerPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/workflow-permissions"
            element={
              <ProtectedRoute>
                <WorkflowPermissionsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/connectors"
            element={
              <ProtectedRoute>
                <ConnectorsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/subflows"
            element={
              <ProtectedRoute>
                <SubflowsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/workflow-activity"
            element={
              <ProtectedRoute>
                <WorkflowActivityPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/run-trace"
            element={
              <ProtectedRoute>
                <RunTracePage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/quota-manager"
            element={
              <ProtectedRoute>
                <QuotaManagerPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/failed-requests"
            element={
              <ProtectedRoute>
                <FailedRequestsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/webhook-triggers"
            element={
              <ProtectedRoute>
                <WebhookTriggersPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/execution-replay"
            element={
              <ProtectedRoute>
                <ExecutionReplayPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/providers"
            element={
              <ProtectedRoute>
                <ProviderStatusPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/task-monitor"
            element={
              <ProtectedRoute>
                <TaskMonitorPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/cost-estimator"
            element={
              <ProtectedRoute>
                <CostEstimatorPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/applets-registry"
            element={
              <ProtectedRoute>
                <AppletsRegistryPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/oauth-clients"
            element={
              <ProtectedRoute>
                <OAuthClientsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/templates-manager"
            element={
              <ProtectedRoute>
                <TemplateManagerPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/flow-versions"
            element={
              <ProtectedRoute>
                <FlowVersionsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/server-info"
            element={
              <ProtectedRoute>
                <ServerInfoPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/managed-keys"
            element={
              <ProtectedRoute>
                <ManagedKeysPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin-keys"
            element={
              <ProtectedRoute>
                <AdminKeysPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/marketplace-reviews"
            element={
              <ProtectedRoute>
                <MarketplaceReviewsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/webhook-registry"
            element={
              <ProtectedRoute>
                <WebhookRegistryPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/template-tools"
            element={
              <ProtectedRoute>
                <TemplateToolsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/node-comments"
            element={
              <ProtectedRoute>
                <NodeCommentsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/portfolio"
            element={
              <ProtectedRoute>
                <PortfolioDashboardPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/flow-testing"
            element={
              <ProtectedRoute>
                <FlowTestingPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/debug-session"
            element={
              <ProtectedRoute>
                <DebugSessionPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/system-config"
            element={
              <ProtectedRoute>
                <SystemConfigPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/monitoring-alerts"
            element={
              <ProtectedRoute>
                <MonitoringAlertsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/workflow-secrets"
            element={
              <ProtectedRoute>
                <WorkflowSecretsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/connector-probe"
            element={
              <ProtectedRoute>
                <ConnectorProbePage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/workflow-test-runner"
            element={
              <ProtectedRoute>
                <WorkflowTestRunnerPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/oauth-inspector"
            element={
              <ProtectedRoute>
                <OAuthInspectorPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/collab-locks"
            element={
              <ProtectedRoute>
                <CollabLocksPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/analytics-detail"
            element={
              <ProtectedRoute>
                <AnalyticsDetailPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/marketplace-discovery"
            element={
              <ProtectedRoute>
                <MarketplaceDiscoveryPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/flow-test-detail"
            element={
              <ProtectedRoute>
                <FlowTestDetailPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/usage-detail"
            element={
              <ProtectedRoute>
                <UsageDetailPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/flow-export-import"
            element={
              <ProtectedRoute>
                <FlowExportImportPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/runs"
            element={
              <ProtectedRoute>
                <RunsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/workflow-snapshots"
            element={
              <ProtectedRoute>
                <WorkflowSnapshotsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/listing-analytics"
            element={
              <ProtectedRoute>
                <ListingAnalyticsDetailPage />
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
