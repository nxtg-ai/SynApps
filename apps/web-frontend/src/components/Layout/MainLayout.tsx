/**
 * MainLayout component
 * Provides consistent layout with sidebar navigation and header
 */
import React, { ReactNode, useState, useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import NotificationCenter from '../Notifications/NotificationCenter';
import { useAuthStore } from '../../stores/authStore';
import { authService } from '../../services/AuthService';
import webSocketService from '../../services/WebSocketService';
import './MainLayout.css';

interface MainLayoutProps {
  children: ReactNode;
  title: string;
  actions?: ReactNode;
}

function useOnboardingIncomplete(): boolean {
  const [incomplete, setIncomplete] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem('synapps_onboarding');
      if (!raw) {
        setIncomplete(false);
        return;
      }
      const progress = JSON.parse(raw);
      if (progress && Array.isArray(progress.completed) && !progress.completed.every(Boolean)) {
        setIncomplete(true);
      } else {
        setIncomplete(false);
      }
    } catch {
      setIncomplete(false);
    }
  }, []);

  return incomplete;
}

const MainLayout: React.FC<MainLayoutProps> = ({ children, title, actions }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const clearAuth = useAuthStore((s) => s.clearAuth);
  const showResumeSetup = useOnboardingIncomplete();

  const handleLogout = async () => {
    const refreshToken =
      typeof window !== 'undefined' ? window.localStorage.getItem('refresh_token') : null;

    // Clear client-side auth immediately (resilient: even if server call fails)
    webSocketService.disconnect();
    clearAuth();
    navigate('/login', { replace: true });

    if (refreshToken) {
      try {
        await authService.logout(refreshToken);
      } catch {
        // Server-side revocation failed – tokens already cleared locally
      }
    }
  };

  // Navigation items
  const navItems = [
    { path: '/dashboard', icon: '🏠', label: 'Dashboard' },
    { path: '/editor', icon: '🔄', label: 'Workflow Editor' },
    { path: '/history', icon: '📋', label: 'Run History' },
    { path: '/applets', icon: '🧩', label: 'Applet Library' },
    { path: '/playground', icon: '⚡', label: 'Playground' },
    { path: '/gallery', icon: '🗂️', label: 'Gallery' },
    { path: '/search', icon: '🔍', label: 'Search' },
    { path: '/wizard', icon: '🧙', label: 'Wizard' },
    { path: '/publisher/dashboard', icon: '📊', label: 'Publisher' },
    { path: '/publisher/credits', icon: '💰', label: 'Credits' },
    { path: '/publisher/analytics', icon: '📈', label: 'Analytics' },
    { path: '/sla', icon: '⏱', label: 'SLA' },
    { path: '/webhooks/debug', icon: '🔗', label: 'Webhooks' },
    { path: '/admin/featured', icon: '⭐', label: 'Featured' },
    { path: '/admin/executions', icon: '🖥', label: 'Exec Monitor' },
    { path: '/collaboration', icon: '👥', label: 'Collaboration' },
    { path: '/plugins', icon: '🔌', label: 'Plugins' },
    { path: '/import-wizard', icon: '📥', label: 'Import' },
    { path: '/node-config', icon: '🛠', label: 'Node Config' },
    { path: '/api-keys', icon: '🔑', label: 'API Keys' },
    { path: '/node-profiler', icon: '📊', label: 'Node Profiler' },
    { path: '/monitoring', icon: '🔔', label: 'Monitoring' },
    { path: '/ai-assist', icon: '🤖', label: 'AI Assist' },
    { path: '/workflow-debug', icon: '🐛', label: 'Step Debugger' },
    { path: '/workflow-vars', icon: '🔧', label: 'Workflow Vars' },
    { path: '/audit-trail', icon: '📜', label: 'Audit Trail' },
    { path: '/schedules', icon: '⏰', label: 'Schedules' },
    { path: '/dlq', icon: '💀', label: 'Dead Letter Queue' },
    { path: '/workflow-notifications', icon: '🔔', label: 'Notifications' },
    { path: '/execution-logs', icon: '📋', label: 'Execution Logs' },
    { path: '/usage', icon: '📊', label: 'Usage & Quota' },
    { path: '/cost-tracker', icon: '💵', label: 'Cost Tracker' },
    { path: '/workflow-permissions', icon: '🔒', label: 'Permissions' },
    { path: '/connectors', icon: '🔌', label: 'Connectors' },
    { path: '/subflows', icon: '🔀', label: 'Subflows' },
    { path: '/workflow-activity', icon: '💬', label: 'Activity' },
    { path: '/run-trace', icon: '🔬', label: 'Run Trace' },
    { path: '/quota-manager', icon: '📊', label: 'Quota Manager' },
    { path: '/failed-requests', icon: '🚨', label: 'Failed Requests' },
    { path: '/webhook-triggers', icon: '🎣', label: 'Webhook Triggers' },
    { path: '/execution-replay', icon: '🔁', label: 'Exec Replay' },
    { path: '/providers', icon: '🤖', label: 'Providers' },
    { path: '/task-monitor', icon: '📋', label: 'Task Monitor' },
    { path: '/cost-estimator', icon: '💲', label: 'Cost Estimator' },
    { path: '/applets-registry', icon: '🧱', label: 'Applets' },
    { path: '/oauth-clients', icon: '🔐', label: 'OAuth2 Clients' },
    { path: '/templates-manager', icon: '📦', label: 'Templates' },
    { path: '/flow-versions', icon: '🕰', label: 'Flow Versions' },
    { path: '/server-info', icon: '🖥', label: 'Server Info' },
    { path: '/managed-keys', icon: '🗝', label: 'Managed Keys' },
    { path: '/admin-keys', icon: '🔑', label: 'Admin Keys' },
    { path: '/marketplace-reviews', icon: '⭐', label: 'Mkt Reviews' },
    { path: '/webhook-registry', icon: '📡', label: 'Webhook Registry' },
    { path: '/template-tools', icon: '🔧', label: 'Template Tools' },
    { path: '/node-comments', icon: '💬', label: 'Node Comments' },
    { path: '/settings', icon: '⚙️', label: 'Settings' },
  ];

  return (
    <div className="main-layout">
      <aside className="sidebar">
        <div className="logo">
          <img src="logo50.png" alt="Logo" className="logo-icon" />
          <span className="logo-text">SynApps</span>
        </div>

        <nav className="nav-menu">
          {showResumeSetup && (
            <Link
              to="/onboarding"
              className="nav-item"
              style={{ color: '#818cf8' }}
            >
              <span className="nav-icon">{'\uD83D\uDE80'}</span>
              <span className="nav-label">Resume Setup</span>
            </Link>
          )}
          {navItems.map((item) => (
            <Link
              key={item.path}
              to={item.path}
              className={`nav-item ${location.pathname.startsWith(item.path) ? 'active' : ''}`}
            >
              <span className="nav-icon">{item.icon}</span>
              <span className="nav-label">{item.label}</span>
            </Link>
          ))}
        </nav>

        {user && (
          <div className="sidebar-user">
            <span className="sidebar-user-email" title={user.email}>
              {user.email}
            </span>
            <button className="sidebar-logout-btn" onClick={handleLogout}>
              Sign out
            </button>
          </div>
        )}

        <div className="version-info">
          <span>
            <a
              href="https://github.com/nxtg-ai/SynApps-v0.4.0"
              target="_blank"
              rel="noopener noreferrer"
            >
              SynApps v1.0
            </a>
          </span>
        </div>
      </aside>

      <main className="main-content">
        <header className="header">
          <h1 className="page-title">{title}</h1>

          <div className="header-actions">
            {actions}
            <NotificationCenter />
          </div>
        </header>

        <div className="content">{children}</div>
      </main>
    </div>
  );
};

export default MainLayout;
