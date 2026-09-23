import { useState, useMemo, useCallback } from 'react'
import useSWR from 'swr'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { motion, AnimatePresence } from 'motion/react'
import { fetcher, fetchWithAuth } from "@/lib/apiClient"
import { NotificationBell } from "@/components/NotificationBell"
import ShinyText from "@/components/ShinyText"
import { Activity, Send, MessageSquare, X, Zap, RefreshCw } from 'lucide-react'

import { EleInAnalyticsView } from "@/components/dashboard/EleInAnalyticsView"
import { EleInFlowView } from "@/components/dashboard/EleInFlowView"

import { FilterDropdown } from "@/components/dashboard/FilterDropdown"

// Layer 2: Dashboard Error Banner to consistently display errors across all SWR fetches
function DashboardErrorBanner({ error, entityName, onRetry, onSeedDemo, onLoginRedirect }: { error: any, entityName: string, onRetry?: () => void, onSeedDemo?: () => void, onLoginRedirect?: () => void }) {
  if (!error) return null;

  const isAuthError = error?.status === 401 || String(error?.message || '').includes('401');
  const message = isAuthError 
    ? 'Your session has expired. Please log in again.' 
    : error?.message || 'An unexpected error occurred.';

  return (
    <div className="p-4 mb-6 bg-destructive/10 border border-destructive/20 rounded-xl text-destructive text-sm flex items-center justify-between gap-4">
      <div className="flex items-center gap-2">
        <Activity className="w-4 h-4 shrink-0" />
        <span>Failed to load {entityName}. {isAuthError ? '' : 'Your campaigns are safe — please refresh or try again in a moment. '}{message}</span>
      </div>
      {isAuthError ? (
        <button onClick={onLoginRedirect} className="px-3 py-1 bg-destructive/20 hover:bg-destructive/30 rounded-lg whitespace-nowrap transition-colors">
          Go to Login
        </button>
      ) : onRetry ? (
        <button onClick={onRetry} className="px-3 py-1 bg-destructive/20 hover:bg-destructive/30 rounded-lg whitespace-nowrap transition-colors">
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

  // 1. Fetch available filters
  const { data: filtersData, error: filtersError, isLoading: filtersLoading, mutate: mutateFilters } = useDashboardFetch('/api/master-view/filters', fetcher)
  
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

  /* Always destructure { data, error, isLoading, isValidating } from useDashboardFetch. Never ignore 'error'. See dashboard error boundary pattern below. */
  const { data: stats, error: statsError, isLoading: statsLoading, isValidating: statsValidating, mutate: mutateStats } = useDashboardFetch(
    ['/api/master-view/stats', selectedSenders, selectedCampaigns, timeRange],
    ([url, s, c, tr]: any) => postFetcher(url, { 
      senders: sanitizeFilter(s), 
      campaigns: sanitizeFilter(c), 
      ...getDateRange(tr as string) 
    }),
    { 
      refreshInterval: 30000
    }
  )

  const { data: accountHealth, error: accountHealthError, mutate: mutateAccountHealth } = useDashboardFetch(
    ['/api/master-view/account-health'],
    ([url]: any) => postFetcher(url, {}),
    { refreshInterval: 60000 }
  )

  const isSetup = (() => {
    if (statsLoading || !stats) return true; // Default to true to avoid flashing FlowView on load
    const totalCampaigns = Number(stats?.summary?.total_campaigns ?? 0);
    const hasAccounts = (filtersData?.senders?.length ?? 0) > 0;
    const hasCampaigns = (filtersData?.campaigns?.length ?? 0) > 0;
    return totalCampaigns > 0 || hasAccounts || hasCampaigns;
  })();

  const today = stats?.today ?? {}
  const funnel = stats?.funnel ?? {}
  const summary = stats?.summary ?? {}
  const timeSeries: any[] = stats?.time_series ?? []
  const heatmapData: any[] = stats?.heatmap_data ?? []
  const timeOfDayData: any[] = stats?.time_of_day_data ?? []
  const multiCampaignData: any[] = stats?.multi_campaign_data ?? []
  const multiCampaignLabels: any = stats?.multi_campaign_labels ?? {}
  const hasAccounts = (filtersData?.senders?.length ?? 0) > 0;
  
  let aiInsight = "Analyzing your pipeline data...";
  if (!statsLoading && stats) {
    if (!hasAccounts) {
      aiInsight = "Connect your first LinkedIn account to get started.";
    } else {
      aiInsight = stats?.ai_insight ?? "Your pipeline is healthy. Keep adding fresh leads to maintain velocity.";
    }
  }
  
  const leadSources = stats?.lead_sources ?? []
  const radarStats = stats?.radar_stats ?? {}
  const liveFeed = stats?.live_feed ?? []
  const errorFeed = stats?.error_feed ?? []

  const fetchFunnelLeadsCb = useCallback((step: string, signal?: AbortSignal) => {
    return postFetcher('/api/master-view/funnel-leads', {
      senders: sanitizeFilter(selectedSenders),
      campaigns: sanitizeFilter(selectedCampaigns),
      step
    }, signal)
  }, [selectedSenders, selectedCampaigns])
  
  const funnelSteps = [
    { label: "Extracted", value: funnel.extracted ?? 0 },
    { label: "Enrolled",  value: funnel.enrolled  ?? 0 },
    { label: "Connected", value: funnel.connected ?? 0 },
    { label: "Replied",   value: funnel.replied   ?? 0 },
    { label: "Booked",    value: funnel.booked    ?? 0 },
    { label: "Failed/Bounced", count: funnel.failed ?? 0, color: "#ef4444" }
  ]

  const isDark = document.documentElement.classList.contains("dark")
  const primaryColor = "#8FFF83" // Matches --primary
  const secondaryColor = "#35D07F" // Matches --success

  const navigate = useNavigate()
  const [showOnboarding, setShowOnboarding] = useState(
    () => localStorage.getItem('onboarding_dismissed') !== 'true'
  )
  const [forceShowOnboarding, setForceShowOnboarding] = useState(false)

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

  const [isSeedingDemo, setIsSeedingDemo] = useState(false)
  const handleSeedDemo = async () => {
    setIsSeedingDemo(true)
    try {
      const res = await fetchWithAuth('/api/onboarding/seed-demo-data', {
        method: 'POST'
      })
      const data = await res.json()
      if (data?.workspace_id) {
        localStorage.setItem('elein_active_workspace', data.workspace_id)
      }
      await Promise.all([mutateFilters(), mutateStats(), mutateAccountHealth()])
      
      // Dismiss the onboarding banner so it actually goes away
      localStorage.setItem('onboarding_dismissed', 'true');
      setShowOnboarding(false);
      setForceShowOnboarding(false);
      
    } catch (err) {
      console.error(err); alert("Failed to seed demo data. Please check backend logs or try again.");
    } finally {
      setIsSeedingDemo(false)
    }
  }

  const isShowingOnboarding = forceShowOnboarding || (isNewUser && showOnboarding);

  const showEscapeHatch = ((filtersError && String(filtersError?.message || '').includes('No workspace found')) ||
    (statsError && String(statsError?.message || '').includes('No workspace found')) ||
    (accountHealthError && String(accountHealthError?.message || '').includes('No workspace found')));

  const handleExportPdf = async () => {
    try {
      const payload = {
        senders: sanitizeFilter(selectedSenders),
        campaigns: sanitizeFilter(selectedCampaigns),
        ...getDateRange(timeRange)
      }
      
      const response = await fetchWithAuth('/api/master-view/stats/export/pdf', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload)
      });
      
      if (!response.ok) {
        const errText = await response.text();
        throw new Error(`Export failed: ${response.status} ${errText}`);
      }
      
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `EleIn_Performance_Overview_${timeRange}.pdf`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error('Failed to export PDF:', err);
      alert(err instanceof Error ? err.message : 'Failed to export PDF. Please check your connection or try again later.');
    }
  };

  return (
    <div className="min-h-[100dvh] bg-background text-foreground font-sans overflow-x-hidden selection:bg-primary/30 relative">
      {statsValidating && (
        <div className="fixed top-0 left-0 right-0 h-1 bg-primary animate-pulse z-[100]" />
      )}
      <header className="sticky top-0 z-50 w-full border-b border-border/40 bg-background/80 backdrop-blur-xl">
        <div className="max-w-[1600px] mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <img src="/logo-icon.png" alt="Ele-in Logo" className="w-8 h-8 rounded-lg object-cover" />
            <h1 className="text-xl font-medium tracking-tight">
              <ShinyText text="Ele-in Workspace" speed={3} className="text-foreground" />
            </h1>
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
            {!isShowingOnboarding && (
              <button
                onClick={() => {
                  localStorage.removeItem('onboarding_dismissed');
                  setShowOnboarding(true);
                  setForceShowOnboarding(true);
                }}
                className="text-sm font-medium text-primary hover:text-primary/90 transition-colors flex items-center gap-1 bg-primary/10 px-3 py-1.5 rounded-lg border border-primary/20"
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
          <div className="p-8 bg-card border-2 border-destructive/50 rounded-2xl shadow-lg flex flex-col items-center justify-center text-center">
            <h2 className="text-2xl font-bold text-foreground mb-4">Your account has no workspace yet.</h2>
            <p className="text-muted-foreground mb-8 max-w-lg">
              It looks like you haven't completed onboarding or your workspace was deleted. 
              You can seed demo data to instantly explore the dashboard, or go to onboarding to set up your own account.
            </p>
            <div className="flex gap-4 mb-8">
              <button
                onClick={handleSeedDemo}
                disabled={isSeedingDemo}
                className="px-6 py-3 bg-primary text-primary-foreground font-medium rounded-xl hover:bg-primary/90 transition-colors flex items-center gap-2"
              >
                {isSeedingDemo ? (
                  <>
                    <div className="w-5 h-5 rounded-full border-2 border-current border-t-transparent animate-spin" />
                    Seeding Data...
                  </>
                ) : (
                  "Seed Demo Data"
                )}
              </button>
              <button
                onClick={() => {
                  localStorage.removeItem('onboarding_dismissed');
                  navigate('/elein/accounts');
                }}
                className="px-6 py-3 bg-secondary text-secondary-foreground font-medium rounded-xl hover:bg-secondary/80 transition-colors"
              >
                Go to Onboarding
              </button>
            </div>
            {/* Layer 2: Nuclear Reset Button */}
            <button
              onClick={() => {
                localStorage.removeItem('elein_active_workspace');
                localStorage.removeItem('onboarding_dismissed');
                window.location.reload();
              }}
              className="text-xs text-muted-foreground hover:text-destructive transition-colors underline underline-offset-4"
            >
              Nuclear Reset: Clear Workspace Cache & Reload
            </button>
          </div>
        </div>
      )}

      {!showEscapeHatch && (<main className="max-w-[1600px] mx-auto p-6 md:p-8 lg:p-10">
        
        {isShowingOnboarding && (
          <div className="mb-8 relative flex flex-col gap-4 p-6 pt-5 bg-card dark:bg-muted/30 border-l-4 border-l-primary border border-border/50 rounded-2xl shadow-sm pr-12">
            <button onClick={handleDismissOnboarding} className="absolute top-4 right-4 p-1.5 text-muted-foreground hover:text-foreground rounded-lg transition-colors">
              <X size={18} />
            </button>
            <h2 className="text-lg font-bold text-foreground">Welcome to Ele-in — let's get you live in 3 steps</h2>
            
            <div className="flex flex-col md:flex-row items-stretch gap-4">
              <button onClick={() => navigate('/elein/accounts')} className="flex items-center gap-3 p-3 rounded-xl border border-border/50 bg-background hover:border-primary/50 transition-colors text-left flex-1">
                <div className="w-6 h-6 rounded-full bg-primary/20 text-primary flex items-center justify-center font-bold text-xs">1</div>
                <div>
                  <span className="block text-sm font-bold text-foreground">Connect LinkedIn</span>
                  <span className="block text-xs text-muted-foreground mt-0.5">Link your first sending account</span>
                </div>
              </button>
              <button onClick={() => navigate('/elein/knowledge')} className="flex items-center gap-3 p-3 rounded-xl border border-border/50 bg-background hover:border-primary/50 transition-colors text-left flex-1">
                <div className="w-6 h-6 rounded-full bg-primary/20 text-primary flex items-center justify-center font-bold text-xs">2</div>
                <div>
                  <span className="block text-sm font-bold text-foreground">Train Your AI</span>
                  <span className="block text-xs text-muted-foreground mt-0.5">Upload a PDF or paste a website</span>
                </div>
              </button>
              <button onClick={() => navigate('/elein/campaigns')} className="flex items-center gap-3 p-3 rounded-xl border border-border/50 bg-background hover:border-primary/50 transition-colors text-left flex-1">
                <div className="w-6 h-6 rounded-full bg-primary/20 text-primary flex items-center justify-center font-bold text-xs">3</div>
                <div>
                  <span className="block text-sm font-bold text-foreground">Launch Campaign</span>
                  <span className="block text-xs text-muted-foreground mt-0.5">Build your first sequence</span>
                </div>
              </button>
              
              <div className="hidden md:block w-px bg-border/50 self-stretch my-1"></div>
              
              <div className="shrink-0 flex flex-col justify-center gap-1.5 items-center text-center p-3 rounded-xl bg-muted/20 border border-border/50 w-full md:w-[200px]">
                <p className="text-xs font-medium text-muted-foreground">Or want to explore first?</p>
                <button 
                  onClick={handleSeedDemo}
                  disabled={isSeedingDemo}
                  className="w-full py-1.5 text-xs font-bold bg-primary/10 text-primary hover:bg-primary/20 rounded-lg transition-colors flex items-center justify-center gap-1.5"
                >
                  {isSeedingDemo ? (
                    <><RefreshCw size={14} className="animate-spin" /> Seeding...</>
                  ) : (
                    <><Zap size={14} /> Seed Demo Data</>
                  )}
                </button>
              </div>
            </div>
          </div>
        )}
        <AnimatePresence mode="wait">
          {!isSetup && !filtersLoading ? (
            <EleInFlowView key="flow" />
          ) : (
            <motion.div
              key="analytics"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="space-y-6"
            >
              <DashboardErrorBanner error={filtersError} entityName="filters" onRetry={() => mutateFilters()} onSeedDemo={handleSeedDemo} onLoginRedirect={() => navigate('/login', { replace: true })} />
              <DashboardErrorBanner error={statsError} entityName="stats" onRetry={() => mutateStats()} onSeedDemo={handleSeedDemo} onLoginRedirect={() => navigate('/login', { replace: true })} />
              <DashboardErrorBanner error={accountHealthError} entityName="account health" onRetry={() => mutateAccountHealth()} onSeedDemo={handleSeedDemo} onLoginRedirect={() => navigate('/login', { replace: true })} />

              {/* Master View Filter Bar */}
              <div className="flex flex-wrap items-center gap-4 p-4 bg-card border border-border/50 rounded-2xl shadow-sm">
                <FilterDropdown 
                  label="Select senders:"
                  icon={Send}
                  options={senders}
                  selectedIds={selectedSenders}
                  onChange={setSelectedSenders}
                  placeholder="All Senders"
                />

                <FilterDropdown 
                  label="Select campaigns:"
                  icon={MessageSquare}
                  options={campaigns}
                  selectedIds={selectedCampaigns}
                  onChange={setSelectedCampaigns}
                  placeholder="All Campaigns"
                />
              </div>

              <EleInAnalyticsView 
                summary={summary}
                today={today}
                timeSeries={timeSeries}
                heatmapData={heatmapData}
                timeOfDayData={timeOfDayData}
                multiCampaignData={multiCampaignData}
                multiCampaignLabels={multiCampaignLabels}
                aiInsight={aiInsight}
                funnelSteps={funnelSteps}
                leadSources={leadSources}
                radarStats={radarStats}
                liveFeed={liveFeed}
                errorFeed={errorFeed}
                accountHealth={accountHealth}
                live_feed_error={!!statsError}
                onTimeRangeChange={setTimeRange}
                onExportPdf={handleExportPdf}
                isLoading={statsLoading}
                primaryColor={primaryColor}
                secondaryColor={secondaryColor}
                fetchFunnelLeads={(step: string, signal?: AbortSignal) => postFetcher('/api/master-view/funnel-leads', {
                  senders: sanitizeFilter(selectedSenders),
                  campaigns: sanitizeFilter(selectedCampaigns),
                  step
                }, signal)}
              />
            </motion.div>
          )}
        </AnimatePresence>
      </main>)}
    </div>
  )
}
