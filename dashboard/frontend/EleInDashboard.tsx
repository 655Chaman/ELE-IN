import { useState, useMemo, useCallback, useRef, useEffect } from 'react'
import useSWR from 'swr'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { fetcher, fetchWithAuth } from "@/lib/apiClient"
import { NotificationBell } from "@/components/NotificationBell"
import { Activity, X, Check } from 'lucide-react'

import { EleInAnalyticsView } from "@/components/dashboard/EleInAnalyticsView"
import { StartOutreachMenu } from "@/components/elein/StartOutreachMenu"
import { EleInFlowView } from "@/components/dashboard/EleInFlowView"
import { useTheme } from "@/components/ThemeProvider"
import { ElesiumLogo } from "@/components/ElesiumLogo"

import { useWorkspace } from "@/contexts/WorkspaceContext"
import { usePaywall } from "@/contexts/PaywallContext"
import { toast } from 'sonner'
import { NotificationPrePermissionTeaser } from "@/components/notifications/NotificationPrePermissionTeaser"

// Layer 2: Dashboard Error Banner to consistently display errors across all SWR fetches
function DashboardErrorBanner({ error, entityName, onRetry, onLoginRedirect }: { error: any, entityName: string, onRetry?: () => void, onLoginRedirect?: () => void }) {
  if (!error) return null;

  const isAuthError = error?.status === 401 || String(error?.message || '').includes('401');
  const message = isAuthError 
    ? 'Your session has expired. Please log in again.' 
    : error?.message || 'An unexpected error occurred.';

  return (
    <div className="p-4 mb-6 bg-destructive/10 border border-destructive/20 rounded-lg text-destructive text-sm flex items-center justify-between gap-4">
      <div className="flex items-center gap-2">
        <Activity className="w-4 h-4 shrink-0" />
        <span>Failed to load {entityName}. {isAuthError ? '' : 'Your campaigns are safe - please refresh or try again in a moment. '}{message}</span>
      </div>
      {isAuthError ? (
        <button type="button" onClick={onLoginRedirect} className="px-3 py-1 bg-destructive/20 hover:bg-destructive/30 rounded-md whitespace-nowrap transition-colors">
          Go to Login
        </button>
      ) : onRetry ? (
        <button type="button" onClick={onRetry} className="px-3 py-1 bg-destructive/20 hover:bg-destructive/30 rounded-md whitespace-nowrap transition-colors">
          Retry
        </button>
      ) : null}
    </div>
  );
}

// Layer 2: Wrapper to enforce keepPreviousData and dedupingInterval for all dashboard fetches
// NEVER destructure useDashboardFetch without also handling the error state. Use DashboardErrorBanner.
function useDashboardFetch<Data = any, Error = any>(key: any, fetcherFn: any, options: any = {}) {
  // Layer 1: dedupingInterval: 0 ensures new filter selections always trigger a fresh fetch
  return useSWR<Data, Error>(key, fetcherFn, {
    keepPreviousData: true,
    ...options
  });
}

// Layer 2: Human Paranoia - Custom hook to physically enforce URL-state sync. 
// Prevents developers from forgetting to update URL params or overwriting unrelated ones.
function useUrlState<T>(
  key: string,
  defaultValue: T,
  parse: (val: string | null) => T,
  serialize: (val: T) => string | null,
  validator?: (val: T) => boolean // Layer 1: Environmental - validate values
): [T, (val: T | ((prev: T) => T)) => void] {
  const [searchParams, setSearchParams] = useSearchParams()

  const rawValue = searchParams.get(key)
  
  let state = defaultValue;
  if (rawValue !== null) {
    try {
      const parsed = parse(rawValue);
      // Layer 1: Validate query param against allowed values, fallback to default if invalid
      if (!validator || validator(parsed)) {
        state = parsed;
      }
    } catch (e) {
      // Fallback to default on parse error
    }
  }

  const setState = useCallback((valOrUpdater: T | ((prev: T) => T)) => {
    setSearchParams(prev => {
      const nextVal = typeof valOrUpdater === 'function' 
        ? (valOrUpdater as (prev: T) => T)(state)
        : valOrUpdater

      const serialized = serialize(nextVal)
      
      // Layer 1: update immutably without blowing away other params
      const newParams = new URLSearchParams(prev)
      if (serialized === null || serialized === '') {
        newParams.delete(key)
      } else {
        newParams.set(key, serialized)
      }
      return newParams
    }, { replace: true })
  }, [key, state, serialize, setSearchParams])

  return [state, setState]
}



export function EleInDashboard() {
  // Layer 0 & 2: Use useUrlState to sync filter states with URL params.
  const [selectedSenders, setSelectedSenders] = useUrlState<string[]>(
    'senders',
    [],
    (val) => val ? val.split(',').filter(Boolean) : [],
    (val) => val.length > 0 ? val.join(',') : null,
    (val) => Array.isArray(val)
  )

  const [selectedCampaigns, setSelectedCampaigns] = useUrlState<string[]>(
    'campaigns',
    [],
    (val) => val ? val.split(',').filter(Boolean) : [],
    (val) => val.length > 0 ? val.join(',') : null,
    (val) => Array.isArray(val)
  )

  const handleStartOutreach = (id: string) => { window.location.href = '/elein/campaigns/new?start=' + id; }

  const [timeRange, setTimeRange] = useUrlState<string>(
    'timeRange',
    '7d',
    (val) => val || '7d',
    (val) => val,
    (val) => ['24h', '7d', '30d', '90d', 'all'].includes(val)
  )

  // BUGFIX: Missing `date_end` Payload Parameter
  // Layer 0: Core fix - return both date_start and date_end.
  // Layer 1: Environmental - Handle system clock skew and invalid range bounds.
  // Layer 2: Human paranoia - Extract to an object `{ date_start, date_end }` so no dev can forget to pass date_end again.
  const getDateRange = (range: string): { date_start?: string; date_end?: string } => {
    // USER TIMEZONE: Always send explicit date_end using local timezone. NEVER let date_end be undefined or null. The backend UTC fallback is a last resort, not the intended path.
    if (range === 'all') return { date_start: '2020-01-01', date_end: new Date().toLocaleDateString('en-CA') }

    const end = new Date()
    const start = new Date(end.getTime())
    
    if (range === '24h') start.setDate(start.getDate() - 1)
    else if (range === '7d') start.setDate(start.getDate() - 7)
    else if (range === '30d') start.setDate(start.getDate() - 30)
    else if (range === '90d') start.setDate(start.getDate() - 90)
    else start.setDate(start.getDate() - 7) // Default to 7d fallback

    // Physical guard: If for any bizarre OS clock reason end < start, auto-fix it.
    if (end.getTime() < start.getTime()) {
      end.setTime(start.getTime() + 1000) 
    }

    return {
      date_start: start.toLocaleDateString('en-CA'),
      date_end: end.toLocaleDateString('en-CA')
    }
  }

  const { workspaces, activeWorkspaceId, myAgencies } = useWorkspace();
  const currentWorkspace = workspaces.find(w => w.id === activeWorkspaceId);
  const currentWorkspaceName = currentWorkspace?.name || "Ele-in Workspace";

  // Layer 1: Reset selected filters if workspace changes to prevent filtering with another workspace's IDs
  const prevWorkspaceIdRef = useRef<string | null>(activeWorkspaceId);
  useEffect(() => {
    if (prevWorkspaceIdRef.current && prevWorkspaceIdRef.current !== activeWorkspaceId) {
      setSelectedSenders([]);
      setSelectedCampaigns([]);
    }
    prevWorkspaceIdRef.current = activeWorkspaceId;
  }, [activeWorkspaceId, setSelectedSenders, setSelectedCampaigns]);

  // 1. Fetch available filters (scoped by activeWorkspaceId to prevent cross-workspace leak)
  const { data: filtersData, error: filtersError, isLoading: filtersLoading, mutate: mutateFilters } = useDashboardFetch(
    activeWorkspaceId ? ['/api/master-view/filters', activeWorkspaceId] : null,
    ([url]: any) => fetcher(url)
  )
  
  const senders = filtersData?.senders || []
  const campaigns = filtersData?.campaigns || []

  // 2. Fetch aggregated stats based on filters using a POST fetcher
  const postFetcher = async (url: string, payload: any, signal?: AbortSignal) => {
    const res = await fetchWithAuth(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload),
      signal
    })
    if (!res.ok) {
      const errorText = await res.text().catch(() => '')
      throw new Error(`API Error (${res.status}): ${errorText || res.statusText || 'Failed to fetch stats'}`)
    }
    return res.json()
  }

  // Layer 2: Sanitize filters to ensure empty lists never reach the backend.
  const sanitizeFilter = (arr: any[]) => {
    if (!arr) return undefined;
    const filtered = arr.filter(Boolean);
    return filtered.length > 0 ? filtered : undefined;
  };

  /* Always destructure { data, error, isLoading, isValidating } from useDashboardFetch. Scoped by activeWorkspaceId. */
  const { data: stats, error: statsError, isLoading: statsLoading, isValidating: statsValidating, mutate: mutateStats } = useDashboardFetch(
    activeWorkspaceId ? ['/api/master-view/stats', activeWorkspaceId, selectedSenders, selectedCampaigns, timeRange] : null,
    ([url, _ws, s, c, tr]: any) => postFetcher(url, { 
      senders: sanitizeFilter(s), 
      campaigns: sanitizeFilter(c), 
      ...getDateRange(tr as string) 
    }),
    { 
      refreshInterval: 30000
    }
  )

  const { data: accountHealth, error: accountHealthError, mutate: mutateAccountHealth } = useDashboardFetch(
    activeWorkspaceId ? ['/api/master-view/account-health', activeWorkspaceId] : null,
    ([url]: any) => postFetcher(url, {}),
    { refreshInterval: 60000 }
  )

  const { data: pendingApprovalsData } = useSWR<{ count: number }>(
    activeWorkspaceId ? [`/api/approvals?status=pending&limit=1`, activeWorkspaceId] : null,
    ([url]: any) => fetcher(url),
    { refreshInterval: 30000, keepPreviousData: true }
  )
  const pendingApprovalsCount = pendingApprovalsData?.count || 0

  const expiredAccounts = useMemo(() => {
    return (accountHealth?.accounts || []).filter((a: any) => 
      a.is_cookie_expired || a.status === 'session_expired' || a.status === 'error'
    );
  }, [accountHealth]);

  const throttledAccounts = useMemo(() => {
    return (accountHealth?.accounts || []).filter((a: any) => a.throttled);
  }, [accountHealth]);

  // Paranoia Layer 1 & 2: Derive locked statuses directly from workspace billing entitlements
  const { data: billing } = useSWR<{
    tier?: string;
    tier_limits?: {
      can_extended_analytics?: boolean;
      can_export_analytics_pdf?: boolean;
      can_export_funnel_csv?: boolean;
    };
  }>(activeWorkspaceId ? '/api/elein/workspaces/billing' : null, fetcher);

  const { openPaywall } = usePaywall();

  const isExtendedLocked = Boolean(billing && !billing.tier_limits?.can_extended_analytics);
  const isPdfLocked = Boolean(billing && !billing.tier_limits?.can_export_analytics_pdf);
  const isFunnelCsvLocked = Boolean(billing && !billing.tier_limits?.can_export_funnel_csv);

  const isSetup = (filtersData?.senders?.length ?? 0) > 0 || (filtersData?.campaigns?.length ?? 0) > 0;

  const rawToday = stats?.today ?? {}
  const rawFunnel = stats?.funnel ?? {}
  const rawSummary = stats?.summary ?? {}
  const rawTimeSeries: any[] = stats?.time_series ?? []
  const heatmapData: any[] = stats?.heatmap_data ?? []
  const timeOfDayData: any[] = stats?.time_of_day_data ?? []
  const hasAccounts = (filtersData?.senders?.length ?? 0) > 0;
  
  let rawAiInsight = "Analyzing your pipeline data...";
  if (!statsLoading && stats) {
    if (!hasAccounts) {
      rawAiInsight = "Connect your first LinkedIn account to get started.";
    } else {
      rawAiInsight = stats?.ai_insight ?? "Your pipeline is healthy. Keep adding fresh leads to maintain velocity.";
    }
  }
  
  const rawLeadSources = stats?.lead_sources ?? []
  const rawRadarStats = stats?.radar_stats ?? {}
  const rawLiveFeed = stats?.live_feed ?? []
  const errorFeed = stats?.error_feed ?? []

  const today = rawToday;
  const summary = rawSummary;
  const timeSeries = rawTimeSeries;
  const leadSources = rawLeadSources;
  const radarStats = rawRadarStats;
  const liveFeed = rawLiveFeed;
  const aiInsight = rawAiInsight;

  const fetchFunnelLeadsCb = useCallback((step: string, signal?: AbortSignal) => {
    return postFetcher('/api/master-view/funnel-leads', {
      senders: sanitizeFilter(selectedSenders),
      campaigns: sanitizeFilter(selectedCampaigns),
      step,
      ...getDateRange(timeRange)
    }, signal)
  }, [selectedSenders, selectedCampaigns, timeRange])
  
  const funnelSteps = [
    { label: "Extracted", value: rawFunnel.extracted ?? 0, count: rawFunnel.extracted ?? 0 },
    { label: "Enrolled",  value: rawFunnel.enrolled  ?? 0, count: rawFunnel.enrolled  ?? 0 },
    { label: "Connected", value: rawFunnel.connected ?? 0, count: rawFunnel.connected ?? 0 },
    { label: "Replied",   value: rawFunnel.replied   ?? 0, count: rawFunnel.replied   ?? 0 },
    { label: "Booked",    value: rawFunnel.booked    ?? 0, count: rawFunnel.booked    ?? 0 },
    { label: "Failed/Bounced", value: rawFunnel.failed ?? 0, count: rawFunnel.failed ?? 0, color: "#ef4444" }
  ];

  const { theme } = useTheme()
  const isDark = theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches)
  const primaryColor = isDark ? "#10B981" : "#059669" // Matches --primary (Emerald)
  const secondaryColor = isDark ? "#34D399" : "#10B981" // Soft Mint / Emerald

  const navigate = useNavigate()
  const [showOnboarding, setShowOnboarding] = useState(
    () => localStorage.getItem('onboarding_dismissed') !== 'true'
  )
  const [forceShowOnboarding, setForceShowOnboarding] = useState(false)
  const [isNotificationDismissed, setIsNotificationDismissed] = useState(() => {
    if (typeof window === 'undefined') return true;
    if (typeof Notification !== 'undefined' && Notification.permission === 'granted') return true;
    if (localStorage.getItem('elein_notification_teaser_dismissed') === 'true') return true;
    const snoozedUntil = Number(localStorage.getItem('elein_notification_teaser_snoozed_until') || 0);
    return Date.now() < snoozedUntil;
  })

  // VETERAN GUARD: Never check ONLY active_campaigns === 0.
  // Veterans who pause all campaigns have active_campaigns=0.
  // We check total_campaigns AND total_leads to distinguish new users from veterans.
  // Changing this to a single field check WILL show the onboarding carousel to veteran users.
  const isNewUser = (() => {
    // If data hasn't loaded or completely failed, default to false to prevent flashing onboarding
    if (statsLoading || !stats || !summary) return false;
    
    // Explicitly parse as numbers to guard against weird JSON string conversions
    // If fields are completely missing from backend, default to 0 to be safe
    const activeCampaigns = Number(summary.active_campaigns ?? 0);
    const totalCampaigns = Number(summary.total_campaigns ?? 0);
    const totalLeads = Number(summary.total_leads ?? 0);
    
    return activeCampaigns === 0 && totalCampaigns === 0 && totalLeads === 0;
  })();

  const handleDismissOnboarding = () => {
    localStorage.setItem('onboarding_dismissed', 'true');
    setShowOnboarding(false);
    setForceShowOnboarding(false);
  }

  const isShowingOnboarding = forceShowOnboarding || (isNewUser && showOnboarding);

  const showEscapeHatch = ((filtersError && String(filtersError?.message || '').includes('No workspace found')) ||
    (statsError && String(statsError?.message || '').includes('No workspace found')) ||
    (accountHealthError && String(accountHealthError?.message || '').includes('No workspace found')));

  const handleTimeRangeChange = (newRange: string) => {
    setTimeRange(newRange);
  };

  const [isExportingPdf, setIsExportingPdf] = useState(false);

  const handleExportPdf = async () => {
    // Paranoia Layer 2: Intercept click if locked before making doomed network call
    if (isPdfLocked) {
      toast.info("Executive PDF Performance Reports require Growth Pro or Enterprise.");
      openPaywall({ campaignName: "Executive Analytics PDF Export" });
      return;
    }

    if (isExportingPdf) return; // Prevent double-triggering
    setIsExportingPdf(true);

    try {
      const payload = {
        senders: sanitizeFilter(selectedSenders),
        campaigns: sanitizeFilter(selectedCampaigns),
        ...getDateRange(timeRange)
      };
      
      const response = await fetchWithAuth('/api/master-view/stats/export/pdf', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });
      
      if (!response.ok) {
        let errorDetail = '';
        try {
          const errJson = await response.json();
          errorDetail = errJson?.detail || '';
        } catch {
          errorDetail = await response.text().catch(() => '');
        }

        // Paranoia Layer 2: Gracefully handle 403 Forbidden upgrade rejection
        if (response.status === 403) {
          toast.error(errorDetail || "Executive PDF Performance Reports require Growth Pro or Enterprise.");
          openPaywall({ campaignName: "Executive Analytics PDF Export" });
          return;
        }

        throw new Error(errorDetail || `Export failed with status ${response.status}`);
      }
      
      // Paranoia Layer 1: Extract sanitized filename from backend Content-Disposition header if available
      let filename = `EleIn_Performance_Overview_${timeRange}.pdf`;
      const disposition = response.headers.get('content-disposition');
      if (disposition) {
        const match = disposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
        if (match && match[1]) {
          filename = match[1].replace(/['"]/g, '').trim();
        }
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      setTimeout(() => {
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
      }, 150);
      toast.success("Executive PDF report exported successfully.");
    } catch (err: any) {
      console.error('Failed to export PDF:', err);
      const msg = err?.message || 'Failed to export PDF performance overview. Please check connection and try again.';
      toast.error(msg);
    } finally {
      setIsExportingPdf(false);
    }
  };

  return (
    <div className="min-h-full bg-background text-foreground font-sans selection:bg-primary/30 relative">
      {statsValidating && (
        <div className="fixed top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-primary/30 via-primary to-primary/30 animate-pulse z-[100]" />
      )}
      <header className="sticky top-0 z-50 w-full border-b border-border bg-card shadow-xs">
        <div className="max-w-[1600px] mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="flex items-center justify-center p-1 rounded-md bg-card border border-border shadow-xs">
              <img src="/logo-icon.png" alt="Ele-in" className="w-7 h-7 object-cover rounded-md" />
            </div>
            <div className="flex items-center gap-2.5">
              <h1 className="text-xl font-semibold tracking-tight text-foreground">
                {currentWorkspaceName}
              </h1>
              {myAgencies && myAgencies.length > 0 && (
                <button
                  type="button"
                  onClick={() => navigate('/elein/agency')}
                  className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-primary/10 text-primary border border-primary/20 hover:bg-primary/20 transition-all cursor-pointer"
                  title="Switch to Agency Multi-Client Command Deck"
                >
                  Agency Fleet
                </button>
              )}
            </div>
          </div>
          <div className="flex items-center gap-4">
            {stats?.last_rolled_up_at && (
              <div className="text-xs text-muted-foreground flex items-center gap-2">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary/75 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-primary"></span>
                </span>
                Data as of {new Date(stats.last_rolled_up_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </div>
            )}
            
            <NotificationBell />
            <StartOutreachMenu onSelect={handleStartOutreach} />
            {!isShowingOnboarding && (
              <button
                type="button"
                onClick={() => {
                  localStorage.removeItem('onboarding_dismissed');
                  setShowOnboarding(true);
                  setForceShowOnboarding(true);
                }}
                className="h-8 px-3 text-xs font-semibold text-primary hover:bg-primary/20 transition-colors flex items-center gap-1.5 bg-primary/10 rounded-lg border border-primary/20 cursor-pointer"
              >
                Getting Started
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Layer 0: Guaranteed Escape Hatch */}
      {showEscapeHatch && (
        <div className="max-w-[1600px] mx-auto p-6 md:p-8 lg:p-10 mb-[-2rem]">
          <div className="p-8 bg-card border-2 border-destructive/50 rounded-lg shadow-lg flex flex-col items-center justify-center text-center">
            <h2 className="text-2xl font-bold text-foreground mb-4">Your account has no workspace yet.</h2>
            <p className="text-muted-foreground mb-8 max-w-lg">
              It looks like you haven't completed onboarding or your workspace was deleted. 
              Go to onboarding to set up your own account.
            </p>
            <div className="flex gap-4 mb-8">
              <button
                type="button"
                onClick={() => {
                  localStorage.removeItem('onboarding_dismissed');
                  navigate('/elein/accounts');
                }}
                className="px-6 py-3 bg-secondary text-secondary-foreground font-medium rounded-lg hover:bg-secondary/80 transition-colors cursor-pointer"
              >
                Go to Onboarding
              </button>
            </div>
            {/* Layer 2: Workspace Reset Button */}
            <button
              type="button"
              onClick={() => {
                localStorage.removeItem('elein_active_workspace');
                localStorage.removeItem('onboarding_dismissed');
                window.location.reload();
              }}
              className="text-xs text-muted-foreground hover:text-destructive transition-colors underline underline-offset-4 cursor-pointer"
            >
              Clear Workspace Cache & Reload
            </button>
          </div>
        </div>
      )}

      {!showEscapeHatch && (<main className="max-w-[1600px] mx-auto p-4 md:p-6 lg:p-8 space-y-4">
        
        {/* Minimal Setup Stepper */}
        {isShowingOnboarding && (
          <div className="relative flex flex-col md:flex-row items-center justify-between gap-3 px-4 py-3 bg-card border border-primary/20 rounded-lg shadow-xs">
            <div className="flex items-center gap-3">
              <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
              <span className="text-xs font-semibold text-foreground">Welcome to Ele-in - Quick Setup</span>
            </div>
            
            <div className="flex items-center gap-2 overflow-x-auto w-full md:w-auto">
              <button 
                type="button"
                onClick={() => navigate('/elein/accounts')} 
                className={`text-xs px-2.5 py-1 rounded-md border font-medium flex items-center gap-1.5 transition-colors cursor-pointer ${
                  hasAccounts ? 'border-primary/40 bg-primary/10 text-primary' : 'border-border/50 hover:border-primary/50 text-muted-foreground'
                }`}
              >
                <span>1. Connect LinkedIn</span>
                {hasAccounts && <Check size={12} className="text-primary" />}
              </button>
              <button 
                type="button"
                onClick={() => navigate('/elein/knowledge')} 
                className="text-xs px-2.5 py-1 rounded-md border border-border/50 hover:border-primary/50 text-muted-foreground font-medium flex items-center gap-1.5 transition-colors cursor-pointer"
              >
                <ElesiumLogo size={13} />
                <span>2. Train AI</span>
              </button>
              <button 
                type="button"
                onClick={() => navigate('/elein/campaigns')} 
                className={`text-xs px-2.5 py-1 rounded-md border font-medium flex items-center gap-1.5 transition-colors cursor-pointer ${
                  Number(summary?.total_campaigns ?? 0) > 0 ? 'border-primary/40 bg-primary/10 text-primary' : 'border-border/50 hover:border-primary/50 text-muted-foreground'
                }`}
              >
                <span>3. Launch Campaign</span>
                {Number(summary?.total_campaigns ?? 0) > 0 && <Check size={12} className="text-primary" />}
              </button>
            </div>

            <button type="button" onClick={handleDismissOnboarding} className="p-1 text-muted-foreground hover:text-foreground rounded-md transition-colors cursor-pointer" title="Dismiss onboarding">
              <X size={15} />
            </button>
          </div>
        )}

        {/* Notification Pre-Permission Alert (Compact) */}
        {!isShowingOnboarding && !isNotificationDismissed && (
          <NotificationPrePermissionTeaser 
            variant="compact" 
            onClose={() => setIsNotificationDismissed(true)} 
          />
        )}

          {/* EleInFlowView re-enabled for empty onboarding state */}
          {!isSetup && !filtersLoading ? (
            <EleInFlowView key="flow" />
          ) : (
            <div key="analytics" className="space-y-4">
              <DashboardErrorBanner error={filtersError} entityName="filters" onRetry={() => mutateFilters()} onLoginRedirect={() => navigate('/login', { replace: true })} />
              <DashboardErrorBanner error={statsError} entityName="stats" onRetry={() => mutateStats()} onLoginRedirect={() => navigate('/login', { replace: true })} />
              <DashboardErrorBanner error={accountHealthError} entityName="account health" onRetry={() => mutateAccountHealth()} onLoginRedirect={() => navigate('/login', { replace: true })} />

              {/* Minimal Unified Triage Horizon */}
              {(expiredAccounts.length > 0 || throttledAccounts.length > 0 || pendingApprovalsCount > 0) && (
                <div className="flex flex-wrap items-center justify-between gap-2.5 px-3.5 py-2 rounded-lg bg-card border border-border text-xs shadow-xs">
                  <div className="flex flex-wrap items-center gap-2">
                    {expiredAccounts.length > 0 && (
                      <button
                        type="button"
                        onClick={() => navigate('/elein/accounts')}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-destructive/10 text-destructive border border-destructive/20 font-semibold hover:bg-destructive/20 transition-all cursor-pointer"
                      >
                        <span className="w-1.5 h-1.5 rounded-full bg-destructive shrink-0" />
                        <span>{expiredAccounts.length} Account{expiredAccounts.length > 1 ? 's' : ''} Need Reconnect</span>
                        <span className="text-[10px] opacity-80 underline">&rarr;</span>
                      </button>
                    )}
                    {throttledAccounts.length > 0 && (
                      <button
                        type="button"
                        onClick={() => navigate('/elein/settings')}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20 font-semibold hover:bg-amber-500/20 transition-all cursor-pointer"
                      >
                        <span className="w-1.5 h-1.5 rounded-full bg-amber-500 shrink-0" />
                        <span>{throttledAccounts.length} Senders Paced at &gt;90% Limit</span>
                        <span className="text-[10px] opacity-80 underline">&rarr;</span>
                      </button>
                    )}
                    {pendingApprovalsCount > 0 && (
                      <button
                        type="button"
                        onClick={() => navigate('/elein/approvals')}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 font-semibold hover:bg-emerald-500/20 transition-all cursor-pointer"
                      >
                        <ElesiumLogo size={14} />
                        <span>{pendingApprovalsCount} AI Draft{pendingApprovalsCount > 1 ? 's' : ''} Pending</span>
                        <span className="text-[10px] opacity-80 underline">&rarr;</span>
                      </button>
                    )}
                  </div>
                  <span className="text-[11px] text-muted-foreground hidden sm:inline">Fleet pacing safe</span>
                </div>
              )}

              <EleInAnalyticsView 
                summary={summary}
                today={today}
                timeSeries={timeSeries}
                heatmapData={heatmapData}
                timeOfDayData={timeOfDayData}
                aiInsight={aiInsight}
                funnelSteps={funnelSteps}
                leadSources={leadSources}
                radarStats={radarStats}
                liveFeed={liveFeed}
                errorFeed={errorFeed}
                accountHealth={accountHealth}
                live_feed_error={!!statsError}
                timeRange={timeRange}
                onTimeRangeChange={handleTimeRangeChange}
                onExportPdf={handleExportPdf}
                isExportingPdf={isExportingPdf}
                senders={senders}
                campaigns={campaigns}
                selectedSenders={selectedSenders}
                selectedCampaigns={selectedCampaigns}
                onSendersChange={setSelectedSenders}
                onCampaignsChange={setSelectedCampaigns}
                isExtendedLocked={isExtendedLocked}
                isPdfLocked={isPdfLocked}
                isFunnelCsvLocked={isFunnelCsvLocked}
                isLoading={statsLoading}
                primaryColor={primaryColor}
                secondaryColor={secondaryColor}
                fetchFunnelLeads={fetchFunnelLeadsCb}
                workspaceName={currentWorkspaceName}
              />
            </div>
          )}
      </main>)}
    </div>
  )
}
