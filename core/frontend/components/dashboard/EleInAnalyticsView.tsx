import { useState, useMemo, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import { 
  Users, Target, Zap, TrendingUp, MessageSquareHeart, ShieldCheck,
  MousePointerClick, Send, RefreshCw, UserX, BarChart2, Clock, CheckCircle2,
  AlertTriangle, Sparkles, X, ArrowRight, ExternalLink, Activity, Download
} from 'lucide-react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis
} from 'recharts'

// --- Custom Tooltips ---
const CustomAreaTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-white/95 dark:bg-background/95 backdrop-blur-xl border border-border/60 dark:border-border/50 p-4 rounded-xl shadow-xl shadow-black/5 dark:shadow-2xl">
        <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-3">{label}</p>
        {payload.map((entry: any, index: number) => (
          <div key={index} className="flex items-center justify-between gap-6 mb-2 last:mb-0">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full shadow-sm" style={{ backgroundColor: entry.color }} />
              <span className="text-sm text-foreground/80 capitalize">{entry.name}</span>
            </div>
            <span className="text-sm font-semibold tabular-nums" style={{ color: entry.color }}>
              {entry.value}
            </span>
          </div>
        ))}
      </div>
    )
  }
  return null
}

const formatXAxisDate = (dateStr: string) => {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  } catch {
    return dateStr;
  }
};

// --- Mock Data Generators ---



const timeAgo = (dateString: string) => {
  if (!dateString) return '';
  const date = new Date(dateString);
  const now = new Date();
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);
  if (seconds < 60) return 'Just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
};

// --- Animated Number (count-up on mount) ---
function AnimatedNumber({ value, duration = 800 }: { value: string | number; duration?: number }) {
  const numericValue = typeof value === 'number' ? value : Number(value);
  const isNumeric = !isNaN(numericValue) && typeof value !== 'string';
  const [display, setDisplay] = useState(isNumeric ? 0 : value);
  const rafRef = useRef<number | null>(null);
  const startTimeRef = useRef<number | null>(null);

  useEffect(() => {
    if (!isNumeric) {
      setDisplay(value);
      return;
    }
    const target = numericValue;
    startTimeRef.current = null;
    const animate = (timestamp: number) => {
      if (!startTimeRef.current) startTimeRef.current = timestamp;
      const elapsed = timestamp - startTimeRef.current;
      const progress = Math.min(elapsed / duration, 1);
      // ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(Math.round(eased * target));
      if (progress < 1) rafRef.current = requestAnimationFrame(animate);
    };
    rafRef.current = requestAnimationFrame(animate);
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  }, [numericValue, duration, isNumeric, value]);

  return <>{display}</>;
}

// --- Components ---

/* DataSectionWrapper: always wrap data sections in this component. It handles empty and loading states automatically, preventing blank voids. */
export function DataSectionWrapper({ 
  data, 
  emptyLabel = 'No Data',
  emptySubtext = 'Data will appear here once available',
  isLoading, 
  children,
  skeletonHeightClass = "h-[110px]",
  gridCols = 12
}: { 
  data: any[] | null | undefined, 
  emptyLabel?: string,
  emptySubtext?: string,
  isLoading?: boolean, 
  children: React.ReactNode,
  skeletonHeightClass?: string,
  gridCols?: number
}) {
  return (
    <AnimatePresence mode="wait">
      {isLoading ? (
        <motion.div
          key="loading"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
          className={`w-full ${skeletonHeightClass} flex items-center justify-center animate-pulse bg-muted/20 rounded-md border border-border/30`}
        >
          <div className="text-muted-foreground text-sm flex items-center gap-2">
            <RefreshCw className="w-4 h-4 animate-spin" /> Loading...
          </div>
        </motion.div>
      ) : !data || data.length === 0 ? (
        <motion.div
          key="empty"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
          className={`w-full ${skeletonHeightClass} relative rounded-md border border-border/30 overflow-hidden bg-background`}
        >
          <div className="absolute inset-0 flex flex-col items-center justify-center z-10 pointer-events-none">
            <div className="bg-background/80 backdrop-blur-sm px-3 py-1.5 rounded-md border border-border/50 text-muted-foreground text-sm shadow-sm font-medium text-center">
              {emptyLabel}
              {emptySubtext && <div className="text-xs mt-0.5 opacity-80">{emptySubtext}</div>}
            </div>
          </div>
          <div className="absolute inset-0 p-1 opacity-20 pointer-events-none flex gap-1 overflow-hidden">
            <div className="grid grid-rows-7 grid-flow-col gap-1 w-full h-full">
              {Array.from({ length: 7 * gridCols }).map((_, i) => (
                <div key={i} className="w-full h-full rounded-[2px] bg-muted/30" />
              ))}
            </div>
          </div>
        </motion.div>
      ) : (
        <motion.div
          key="content"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
          className="w-full h-full"
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function formatKpiValue(value: string | number | undefined | null, options?: { unit?: 'count' | 'percentage' }): string {
  if (value === null || value === undefined || value === '') {
    return options?.unit === 'count' ? '0' : 'Unknown';
  }

  if (options?.unit === 'count') {
    return String(Math.round(Number(value) || 0));
  }

  if (typeof value === 'number') {
    return `${Math.round(value)}%`;
  }

  return String(value);
}

export function LimitProgressBar({ used, limit, pct, label }: { used: number, limit: number, pct?: number | null, label: string }) {
  const width = pct ?? (limit > 0 ? (used / limit) * 100 : 0);
  const clampedWidth = Math.min(width, 100);
  let colorClass = 'bg-primary';
  if (clampedWidth >= 90) colorClass = 'bg-destructive';
  else if (clampedWidth >= 70) colorClass = 'bg-primary';

  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium text-foreground">{used} / {limit}</span>
      </div>
      <div className="w-full h-1.5 bg-slate-100 dark:bg-muted rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${colorClass}`} style={{ width: `${clampedWidth}%` }} />
      </div>
    </div>
  );
}

export function getHeatmapColorClass(value: number, max: number): string {
  if (typeof value !== 'number' || isNaN(value) || value <= 0) {
    return 'bg-accent/40 dark:bg-muted/50';
  }
  
  const safeMax = Math.max(max, 1);
  const ratio = value / safeMax;
  
  if (ratio >= 0.75) return 'bg-primary';
  if (ratio >= 0.50) return 'bg-primary/80';
  if (ratio >= 0.25) return 'bg-primary/60';
  return 'bg-primary/40';
}

interface EleInAnalyticsViewProps {
  summary?: any;
  today?: any;
  timeSeries?: any[];
  heatmapData?: any[];
  timeOfDayData?: any[];
  multiCampaignData?: any[];
  multiCampaignLabels?: any[];
  aiInsight?: string;
  funnelSteps?: any[];
  leadSources?: any[];
  radarStats?: any;
  liveFeed?: any[];
  errorFeed?: any[];
  accountHealth?: any;
  onTimeRangeChange?: (range: string) => void;
  onExportPdf?: () => void;
  isLoading?: boolean;
  primaryColor?: string;
  secondaryColor?: string;
  fetchFunnelLeads?: (step: string, signal?: AbortSignal) => Promise<any[]>;
  live_feed_error?: boolean;
  timeRange?: string;
}

export function EleInAnalyticsView({ 
  summary, today, timeSeries, heatmapData, timeOfDayData, multiCampaignData, multiCampaignLabels, aiInsight, funnelSteps, leadSources, radarStats, liveFeed, errorFeed, accountHealth, onTimeRangeChange, onExportPdf, isLoading, primaryColor, secondaryColor, fetchFunnelLeads, live_feed_error, timeRange = '7d'
}: EleInAnalyticsViewProps) {
  const [hoveredSeries, setHoveredSeries] = useState<string | null>(null)
  const [hoveredFunnelStep, setHoveredFunnelStep] = useState<number | null>(null)
  const [selectedFunnelStep, setSelectedFunnelStep] = useState<string | null>(null)
  
  const [funnelLeads, setFunnelLeads] = useState<any[]>([])
  const [isFunnelLoading, setIsFunnelLoading] = useState(false)
  const [heatmapFilter, setHeatmapFilter] = useState<'all' | 'connections' | 'messages'>('all')

  // Fallback for time series
  const safeTimeSeries = timeSeries ?? []
  
  const liveFeedError = live_feed_error ?? false;

  // Dynamic radar chart transformation - maps whatever fields the API sends
  const radarChartData = useMemo(() => {
    if (!radarStats || typeof radarStats !== 'object' || Array.isArray(radarStats)) return [];
    return Object.entries(radarStats).map(([key, value]) => ({
      subject: key,
      value: Math.min(Number(value) || 0, 100), // cap at 100
      fullMark: 100
    }));
  }, [radarStats]);

  // IMPORTANT: This useEffect MUST have a cleanup function to cancel in-flight requests. Never remove the return () => ... statement.
  useEffect(() => {
    if (!selectedFunnelStep || !fetchFunnelLeads) {
      return
    }

    const controller = new AbortController()

    setIsFunnelLoading(true)
    setFunnelLeads([])

    fetchFunnelLeads(selectedFunnelStep, controller.signal)
      .then((data: any[]) => {
        if (controller.signal.aborted) return
        setFunnelLeads(data || [])
      })
      .catch((err: any) => {
        if (err.name === 'AbortError' || controller.signal.aborted) return
        setFunnelLeads([])
      })
      .finally(() => {
        if (controller.signal.aborted) return
        setIsFunnelLoading(false)
      })

    return () => controller.abort()
  }, [selectedFunnelStep, fetchFunnelLeads]) // fetchFunnelLeads is now stable via useCallback



  const safeSummary = summary || {}
  const safeToday = today || {}

  const kpiCards = [
    // PARANOIA RULE: Every .value here MUST use ?? 0 or || 0.
    // NEVER access backend fields without a fallback. The backend may 500.
    { label: "Total Audience", value: safeSummary.total_leads || 0, icon: Users, color: "text-primary", bg: "bg-primary/10" },
    { label: "Active Campaigns", value: safeSummary.active_campaigns || 0, icon: TrendingUp, color: "text-primary", bg: "bg-primary/10" },
    { label: "Connections (24h)", value: safeSummary.connections_today || 0, icon: MousePointerClick, color: "text-success", bg: "bg-success/10" },
    { label: "Messages (24h)", value: safeSummary.messages_today || 0, icon: Send, color: "text-success", bg: "bg-success/10" },
    { label: "Inmails (24h)", value: safeSummary.inmails_today || 0, icon: Send, color: "text-warning", bg: "bg-warning/10" },
    /* account_health is a categorical label (e.g. 'Excellent', 'Good') — do NOT append %. Backend may also return a number 0-100, handled by formatKpiValue. */
    { label: "Account Health", value: formatKpiValue(safeSummary.account_health as any), icon: ShieldCheck, color: "text-success", bg: "bg-success/10" },
    // Backend returns absolute count, NOT a percentage. Do not add % sign.
    { label: "Positive Sentiment", value: formatKpiValue(safeSummary.positive_sentiment as any, { unit: 'count' }), icon: MessageSquareHeart, color: "text-success", bg: "bg-success/10" },
    { label: "Auto-Withdrawals", value: safeSummary.auto_withdrawals ?? 0, icon: UserX, color: "text-destructive", bg: "bg-destructive/10" }
  ]

  const mergedFeed = useMemo(() => {
    const combined = [
      ...(liveFeed || []).map((item: any) => ({ ...item, type: item.type || 'info' })),
      ...(errorFeed || []).map((item: any) => ({ ...item, type: 'error' }))
    ];
    return combined.sort((a, b) => new Date(b.time || 0).getTime() - new Date(a.time || 0).getTime()).slice(0, 8);
  }, [liveFeed, errorFeed]);

  const maxHeatmapActions = useMemo(() => {
    if (!heatmapData || !Array.isArray(heatmapData) || heatmapData.length === 0) return 10;
    const values = heatmapData.map(d => {
      if (typeof d === 'number') return d;
      if (heatmapFilter === 'connections') return d.connections ?? 0;
      if (heatmapFilter === 'messages') return d.messages ?? 0;
    return d.count ?? 0;
    });
    return Math.max(...values, 10);
  }, [heatmapData, heatmapFilter]);

  const TIME_RANGES = [
    { value: "24h", label: "24h" },
    { value: "7d", label: "7d" },
    { value: "30d", label: "30d" },
    { value: "90d", label: "90d" },
    { value: "all", label: "All Time" }
  ]

  return (
    <>
      <motion.div
        key="analytics-bento"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -20 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className="space-y-6 max-w-[1800px] mx-auto pb-12 relative"
      >
        {/* Light mode dot pattern background */}
        <div className="absolute inset-0 bg-[radial-gradient(#e5e7eb_1px,transparent_1px)] [background-size:20px_20px] [mask-image:radial-gradient(ellipse_60%_60%_at_50%_40%,#000_70%,transparent_100%)] opacity-70 dark:opacity-0 pointer-events-none -z-10" />

        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 px-1">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-slate-100 flex items-center gap-2">
              Performance Overview
              {isLoading && (
                <span className="flex space-x-1 ml-2">
                  <span className="w-1.5 h-1.5 bg-primary/40 rounded-full animate-bounce [animation-delay:-0.3s]"></span>
                  <span className="w-1.5 h-1.5 bg-primary/60 rounded-full animate-bounce [animation-delay:-0.15s]"></span>
                  <span className="w-1.5 h-1.5 bg-primary/80 rounded-full animate-bounce"></span>
                </span>
              )}
            </h2>
            <p className="text-sm text-muted-foreground mt-1">Real-time performance tracking and network actions</p>
          </div>
          
          <div className="inline-flex items-center p-1 bg-white dark:bg-muted/50 backdrop-blur-md rounded-xl border border-slate-200 dark:border-border/50 shadow-sm" role="group" aria-label="Time range selection">
            {TIME_RANGES.map((range) => (
              <button
                key={range.value}
                aria-pressed={timeRange === range.value}
                aria-label={`Show data for ${range.label}`}
                onClick={() => {
                  if (onTimeRangeChange) onTimeRangeChange(range.value)
                }}
                className={`relative px-4 py-1.5 text-sm font-medium rounded-lg transition-colors ${
                  timeRange === range.value ? 'text-foreground' : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {timeRange === range.value && (
                  <motion.div
                    layoutId="timeRangeIndicator"
                    className="absolute inset-0 bg-slate-100 dark:bg-muted rounded-md -z-10"
                    transition={{ type: "spring", bounce: 0.2, duration: 0.6 }}
                  />
                )}
                {range.label}
              </button>
            ))}
            {onExportPdf && (
              <button
                onClick={onExportPdf}
                className="ml-2 inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-lg text-primary hover:bg-primary/10 transition-colors"
                title="Export performance overview to PDF"
              >
                <Download className="h-4 w-4" />
                Export PDF
              </button>
            )}
          </div>
        </div>

        {/* AI Insight Box */}
        <div className="relative overflow-hidden rounded-2xl bg-gradient-to-r from-primary/5 to-primary/10 dark:from-primary/10 dark:to-primary/5 border border-primary/20 dark:border-primary/30 p-6 flex items-start gap-4">
          <div className="absolute left-0 top-0 bottom-0 w-1 bg-primary rounded-l-2xl" />
          <div className="p-2.5 bg-primary/20 text-primary rounded-xl shrink-0">
            <Sparkles className="w-5 h-5" />
          </div>
          <div className="flex-1 space-y-1.5">
            <div className="flex items-center gap-2">
              <h3 className="font-semibold text-foreground">Captain's Brief</h3>
              <span className="text-[10px] font-bold tracking-wider uppercase bg-primary/20 text-primary px-2 py-0.5 rounded-full">AI Generated</span>
            </div>
            <p className="text-sm text-foreground/80 leading-relaxed max-w-4xl">
              {aiInsight}
            </p>
              <button className="text-xs font-semibold text-primary bg-background/50 hover:bg-background px-3 py-1.5 rounded-lg border border-primary/20 transition-colors flex items-center gap-1.5">
                A/B Test New Hook <ArrowRight size={12} />
              </button>
            </div>
          </div>

        {/* Row 1: High Density KPI Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-4">
          {kpiCards.map((stat, i) => (
            <motion.div 
              key={stat.label}
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.4, delay: i * 0.05 }}
              className="relative overflow-hidden rounded-2xl border border-slate-200 dark:border-border/50 bg-white dark:bg-card/40 backdrop-blur-md p-4 group transition-colors shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-none hover:border-slate-300 dark:hover:bg-card/60"
            >
              <div className={`absolute top-0 right-0 w-20 h-20 -mr-6 -mt-6 rounded-full blur-2xl opacity-40 group-hover:opacity-60 transition-opacity ${stat.bg}`} />
              <div className="flex justify-between items-start mb-3">
                <div className={`p-2 rounded-xl ${stat.bg} ${stat.color} shrink-0 ring-1 ring-inset ring-foreground/5`}>
                  <stat.icon size={16} strokeWidth={2} />
                </div>
              </div>
              <div>
                <p className="text-2xl font-light tracking-tight text-foreground mb-1 tabular-nums">
                  <AnimatedNumber value={stat.value} />
                </p>
                <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider line-clamp-1">{stat.label}</p>
              </div>
            </motion.div>
          ))}
        </div>

        {/* Row 1.5: Account Throttle Status */}
        {accountHealth?.accounts && accountHealth.accounts.length > 0 && (
          <div className="space-y-4">
            <h3 className="text-lg font-medium tracking-tight text-foreground flex items-center gap-2">
              <ShieldCheck size={18} className="text-primary" /> Account Throttle Status
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
              {(accountHealth?.accounts || []).map((acc: any, i: number) => {
                if (!acc) return null
                const connPct = acc.connection_pct ?? (acc.connections_limit > 0 ? (acc.connections_used / acc.connections_limit) * 100 : 0)
                const msgPct = acc.message_pct ?? (acc.messages_limit > 0 ? (acc.messages_used / acc.messages_limit) * 100 : 0)
                const maxPct = Math.max(connPct, msgPct)
                
                let dotColor = 'bg-primary'
                if (maxPct >= 90) dotColor = 'bg-destructive'
                else if (maxPct >= 70) dotColor = 'bg-primary'

                return (
                  <div key={i} className="rounded-2xl border border-slate-200 dark:border-border/50 bg-white dark:bg-card/40 backdrop-blur-md p-4 shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-none relative">
                    {acc.throttled && (
                      <div className="absolute top-4 right-4 bg-destructive/10 text-destructive text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded-md flex items-center gap-1">
                        <AlertTriangle size={10} /> Approaching Limit
                      </div>
                    )}
                    <div className="flex items-center gap-2 mb-4">
                      <div className={`w-2.5 h-2.5 rounded-full ${dotColor} shadow-sm`} />
                      <span className="font-semibold text-foreground">{acc.name}</span>
                    </div>
                    
                    <div className="space-y-3">
                      <LimitProgressBar 
                        used={acc.connections_used} 
                        limit={acc.connections_limit} 
                        pct={acc.connection_pct} 
                        label="Connections" 
                      />
                      <LimitProgressBar 
                        used={acc.messages_used} 
                        limit={acc.messages_limit} 
                        pct={acc.message_pct} 
                        label="Messages" 
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Row 2: Volume */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          {/* Area Chart: Volume */}

          <motion.div 
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            className="xl:col-span-2 rounded-3xl border border-slate-200 dark:border-border/50 bg-white dark:bg-card/40 backdrop-blur-md p-6 flex flex-col relative overflow-hidden shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-none"
          >
            <div className="flex items-center justify-between mb-6 z-10">
              <div>
                <h3 className="text-lg font-medium tracking-tight mb-1 text-foreground">Network Velocity</h3>
                <p className="text-xs text-muted-foreground">Connection & messaging volume over time</p>
              </div>
              <div className="flex gap-4 text-xs font-medium bg-slate-50 dark:bg-background/50 p-1.5 rounded-lg border border-slate-200 dark:border-border/50 shadow-sm">
                <button 
                  className={`flex items-center gap-1.5 px-2 transition-opacity ${hoveredSeries && hoveredSeries !== 'connections' ? 'opacity-40' : 'opacity-100'}`}
                  onMouseEnter={() => setHoveredSeries('connections')}
                  onMouseLeave={() => setHoveredSeries(null)}
                >
                  <div className="w-2.5 h-2.5 rounded-full shadow-sm" style={{ backgroundColor: primaryColor }} />
                  <span className="text-foreground">Connections</span>
                </button>
                <button 
                  className={`flex items-center gap-1.5 px-2 transition-opacity ${hoveredSeries && hoveredSeries !== 'messages' ? 'opacity-40' : 'opacity-100'}`}
                  onMouseEnter={() => setHoveredSeries('messages')}
                  onMouseLeave={() => setHoveredSeries(null)}
                >
                  <div className="w-2.5 h-2.5 rounded-full shadow-sm" style={{ backgroundColor: secondaryColor }} />
                  <span className="text-foreground">Messages</span>
                </button>
                <button 
                  className={`flex items-center gap-1.5 px-2 transition-opacity ${hoveredSeries && hoveredSeries !== 'inmails' ? 'opacity-40' : 'opacity-100'}`}
                  onMouseEnter={() => setHoveredSeries('inmails')}
                  onMouseLeave={() => setHoveredSeries(null)}
                >
                  <div className="w-2.5 h-2.5 rounded-full shadow-sm bg-[#FFB020]" />
                  <span className="text-foreground">Inmails</span>
                </button>
                {/* TODO: Re-add Replied area when rollup_daily_stats populates daily replied counts */}
                <div className="flex items-center gap-1.5 px-2 opacity-50 cursor-help group relative">
                  <div className="w-2.5 h-2.5 rounded-full shadow-sm bg-primary/50" />
                  <span className="text-foreground/50">Replied</span>
                  <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1 bg-foreground text-background text-[10px] font-medium rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none z-50">
                    ℹ️ Reply tracking coming soon
                  </div>
                </div>
              </div>
            </div>
            
            <div className="flex-1 min-h-[280px] z-10">
              {safeTimeSeries.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={safeTimeSeries} margin={{ top: 10, right: 0, left: -25, bottom: 0 }}>
                    <defs>
                      <linearGradient id="colorConn" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={primaryColor} stopOpacity={0.2}/>
                        <stop offset="95%" stopColor={primaryColor} stopOpacity={0}/>
                      </linearGradient>
                      <linearGradient id="colorMsg" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={secondaryColor} stopOpacity={0.2}/>
                        <stop offset="95%" stopColor={secondaryColor} stopOpacity={0}/>
                      </linearGradient>
                      <linearGradient id="colorInmails" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#FFB020" stopOpacity={0.2}/>
                        <stop offset="95%" stopColor="#FFB020" stopOpacity={0}/>
                      </linearGradient>
                      <linearGradient id="colorRep" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.2}/>
                        <stop offset="95%" stopColor="#f59e0b" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-border/40" vertical={false} />
                    <XAxis dataKey="date" tick={{ fill: "currentColor", fontSize: 10, opacity: 0.6 }} className="text-muted-foreground" tickLine={false} axisLine={false} tickFormatter={formatXAxisDate} dy={10} />
                    <YAxis tick={{ fill: "currentColor", fontSize: 10, opacity: 0.6 }} className="text-muted-foreground" tickLine={false} axisLine={false} dx={-10} />
                    <Tooltip cursor={{ stroke: 'currentColor', strokeWidth: 1, strokeDasharray: '4 4', opacity: 0.2 }} content={<CustomAreaTooltip />} />
                    {/* Maps to 'connections' in API response */}
                    <Area type="monotone" dataKey="connections" stroke={primaryColor} strokeWidth={3} fill="url(#colorConn)" style={{ opacity: hoveredSeries && hoveredSeries !== 'connections' ? 0.2 : 1, transition: 'all 0.3s ease' }} activeDot={{ r: 5, fill: primaryColor, stroke: 'hsl(var(--background))', strokeWidth: 2 }} />
                    {/* Maps to 'messages' in API response */}
                    <Area type="monotone" dataKey="messages" stroke={secondaryColor} strokeWidth={3} fill="url(#colorMsg)" style={{ opacity: hoveredSeries && hoveredSeries !== 'messages' ? 0.2 : 1, transition: 'all 0.3s ease' }} activeDot={{ r: 5, fill: secondaryColor, stroke: 'hsl(var(--background))', strokeWidth: 2 }} />
                    {/* PARANOIA: Every metric returned by the backend's time_series MUST have a corresponding <Area> chart line, otherwise the data is invisible to the user. */}
                    {/* Maps to 'inmails' in API response */}
                    <Area type="monotone" dataKey="inmails" stroke="#FFB020" strokeWidth={3} fill="url(#colorInmails)" style={{ opacity: hoveredSeries && hoveredSeries !== 'inmails' ? 0.2 : 1, transition: 'all 0.3s ease' }} activeDot={{ r: 5, fill: "#FFB020", stroke: 'hsl(var(--background))', strokeWidth: 2 }} />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center text-muted-foreground/50"><BarChart2 className="mb-2 opacity-50" /></div>
              )}
            </div>
          </motion.div>

          {/* Live Feed */}
          <div className="rounded-3xl border border-slate-200 dark:border-border/50 bg-white dark:bg-card/40 backdrop-blur-md p-6 flex flex-col shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-none min-h-[400px] overflow-hidden">
            <h3 className="text-lg font-medium tracking-tight mb-4 text-foreground flex items-center gap-2">
              <Activity size={16} className="text-primary animate-pulse" /> Live Feed
            </h3>
            <div className="flex-1 overflow-y-auto pr-2 space-y-3 scrollbar-hide">
              <AnimatePresence initial={false}>
                {mergedFeed.map((item: any, index: number) => {
                  const isError = item.type === 'error';
                  return (
                  <motion.div
                    key={item.id || `${item.time}-${item.text}`}
                    initial={{ opacity: 0, y: -8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -8 }}
                    transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
                    className={`flex gap-3 text-sm p-3 rounded-xl border ${isError ? 'bg-destructive/10 border-destructive/20' : 'bg-muted/30 border-border/50'}`}
                  >
                    <div className={`mt-0.5 w-6 h-6 rounded-full flex items-center justify-center shrink-0 ${isError ? 'bg-destructive/20 text-destructive' : 'bg-primary/20 text-primary'}`}>
                      {isError ? <AlertTriangle size={12} /> : <MessageSquareHeart size={12} />}
                    </div>
                    <div>
                      <p className="text-foreground">{item.text}</p>
                      <p className="text-xs text-muted-foreground mt-1">{timeAgo(item.time)}</p>
                    </div>
                  </motion.div>
                  );
                })}
              </AnimatePresence>
              {/* PARANOIA: live_feed_error distinguishes a DB failure from genuine zero activity. Never merge these two states into a single 'empty' UI. */}
              {mergedFeed.length === 0 && liveFeedError && (
                <div className="h-full flex flex-col items-center justify-center text-center p-4">
                  <div className="bg-warning/10 border border-warning/20 rounded-lg p-3 text-warning flex items-center gap-2 text-sm font-medium">
                    <AlertTriangle size={16} /> Activity feed temporarily unavailable
                  </div>
                </div>
              )}
              {mergedFeed.length === 0 && !liveFeedError && (
                <div className="h-full flex items-center justify-center text-muted-foreground text-sm">
                  No recent activity
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Row 3: Funnel & Heatmaps & Radar */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          
          {/* Feature 3: Interactive Drill-Down Funnel */}
          <div className="rounded-3xl border border-slate-200 dark:border-border/50 bg-white dark:bg-card/40 backdrop-blur-md p-6 flex flex-col shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-none">
            <div className="mb-6 flex justify-between items-start">
              <div>
                <h3 className="text-lg font-medium tracking-tight mb-1 text-foreground">Conversion Funnel</h3>
                <p className="text-xs text-muted-foreground">Click a stage to view leads</p>
              </div>
            </div>
            
            <div className="flex-1 flex flex-col justify-center space-y-5">
              {!funnelSteps || funnelSteps.length === 0 ? (
                <p className="text-muted-foreground text-sm text-center py-8">No funnel data yet</p>
              ) : funnelSteps.map((step: any, i: number) => {
                const maxVal = (typeof funnelSteps[0]?.value === 'number' ? funnelSteps[0].value : typeof funnelSteps[0]?.count === 'number' ? funnelSteps[0].count : undefined) || 1
                const stepVal = typeof step?.value === 'number' ? step.value : typeof step?.count === 'number' ? step.count : 0
                const widthPct = (stepVal / maxVal) * 100
                const isHovered = hoveredFunnelStep === i
                const stepColor = step.color || 'var(--primary)'
                const isFailedStep = step.label === 'Failed/Bounced'
                
                return (
                  <div 
                    key={step.label} 
                    className={`relative group ${isFunnelLoading ? 'cursor-wait opacity-80' : 'cursor-pointer'} ${isFailedStep ? 'mt-4 border-t border-border/50 pt-4' : ''}`} 
                    onMouseEnter={() => setHoveredFunnelStep(i)} 
                    onMouseLeave={() => setHoveredFunnelStep(null)}
                    onClick={() => {
                      if (isFunnelLoading) return;
                      setSelectedFunnelStep(step.label);
                    }}
                  >
                    {i > 0 && !isFailedStep && <div className="absolute -top-5 left-4 w-px h-5 bg-border/60 group-hover:bg-primary/50 transition-colors" />}
                    
                    <div className="flex items-center gap-4">
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-colors shadow-sm ${isHovered ? 'bg-primary text-primary-foreground scale-110' : 'bg-white dark:bg-muted text-muted-foreground border border-border'}`} style={isHovered && step.color ? { backgroundColor: step.color, color: '#fff' } : {}}>
                        {i + 1}
                      </div>
                      <div className="flex-1">
                        <div className="flex justify-between items-baseline mb-1">
                          <span className={`text-xs font-bold uppercase tracking-wider transition-colors ${isHovered ? 'text-primary' : 'text-muted-foreground'}`} style={isHovered && step.color ? { color: step.color } : {}}>{step.label}</span>
                          <span className="text-sm font-medium tabular-nums text-foreground">{(stepVal ?? 0).toLocaleString()}</span>
                        </div>
                        <div className="w-full h-2 bg-background dark:bg-background/50 rounded-full overflow-hidden shadow-inner">
                          <motion.div className="h-full" style={{ backgroundColor: stepColor, opacity: 0.8 }} initial={{ width: 0 }} animate={{ width: `${widthPct}%` }} transition={{ duration: 1, delay: i * 0.1 }} />
                        </div>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Feature 1 & 2: Heatmaps */}
          <div className="rounded-3xl border border-slate-200 dark:border-border/50 bg-white dark:bg-card/40 backdrop-blur-md p-6 flex flex-col shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-none">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h3 className="text-lg font-medium tracking-tight mb-1 text-foreground">Activity Topography</h3>
                <p className="text-xs text-muted-foreground">Daily volume & Time-of-day hot zones</p>
              </div>
            </div>
            
            <div className="flex flex-col gap-8 flex-1">
              
              {/* Consistency Heatmap (GitHub style) */}
              <div>
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3">
                  <p className="text-xs font-medium text-foreground flex items-center gap-2"><Clock size={12}/> 12-Month Consistency</p>
                  <div className="flex bg-slate-100 dark:bg-muted/50 p-1 rounded-lg border border-border/50 text-[10px] font-semibold w-max self-end sm:self-auto">
                    <button onClick={() => setHeatmapFilter('all')} className={`px-2.5 py-1 rounded-md transition-colors ${heatmapFilter === 'all' ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}>All</button>
                    <button onClick={() => setHeatmapFilter('connections')} className={`px-2.5 py-1 rounded-md transition-colors ${heatmapFilter === 'connections' ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}>Connections</button>
                    <button onClick={() => setHeatmapFilter('messages')} className={`px-2.5 py-1 rounded-md transition-colors ${heatmapFilter === 'messages' ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}>Messages</button>
                  </div>
                </div>
                <DataSectionWrapper data={heatmapData} emptyLabel="12-Month Consistency" emptySubtext="Activity data will appear here once campaigns are running" isLoading={isLoading} skeletonHeightClass="h-[110px]" gridCols={52}>
                  <div className="flex gap-1 overflow-x-auto pb-2 scrollbar-hide">
                    <div className="grid grid-rows-7 grid-flow-col gap-1 w-max">
                      {heatmapData?.map((val: any, i: number) => {
                        let displayVal = 0;
                        if (typeof val === 'number') {
                          displayVal = val;
                        } else {
                          if (heatmapFilter === 'connections') displayVal = val.connections ?? 0;
                          else if (heatmapFilter === 'messages') displayVal = val.messages ?? 0;
                          else displayVal = val.count ?? 0;
                        }
                        const colorClass = getHeatmapColorClass(displayVal, maxHeatmapActions);
                        return (
                          <div key={i} className={`w-3 h-3 rounded-[2px] ${colorClass} hover:ring-2 hover:ring-foreground/20 transition-all cursor-pointer`} title={`${displayVal} actions`} />
                        )
                      })}
                    </div>
                  </div>
                </DataSectionWrapper>
              </div>

              {/* Time of Day Heatmap */}
              <div>
                <p className="text-xs font-medium text-foreground mb-3 flex items-center gap-2"><Target size={12}/> High-Conversion Hours</p>
                <DataSectionWrapper data={timeOfDayData} emptyLabel="High-Conversion Hours" emptySubtext="Activity data will appear here once campaigns are running" isLoading={isLoading} skeletonHeightClass="h-[110px]" gridCols={24}>
                  <div className="flex gap-2">
                    <div className="flex flex-col justify-between text-[9px] text-muted-foreground uppercase font-semibold h-[110px] py-1">
                      <span>Mon</span><span>Wed</span><span>Fri</span><span>Sun</span>
                    </div>
                    <div className="flex-1">
                      <div className="grid grid-rows-7 grid-flow-col gap-1 h-[110px]">
                        {timeOfDayData?.map((d: any, i: number) => {
                          const colorClass = getHeatmapColorClass(d.rate, 100);
                          return (
                            <div 
                              key={i} 
                              className={`w-full h-full rounded-[2px] ${colorClass} cursor-pointer hover:ring-1 hover:ring-foreground/30 transition-all`}
                              title={`${d.day} at ${d.hour}:00 - ${d.count || Math.round(d.rate)} actions`}
                            />
                          )
                        })}
                      </div>
                      <div className="flex justify-between text-[9px] text-muted-foreground mt-2 font-semibold">
                        <span>12AM</span><span>6AM</span><span>12PM</span><span>6PM</span><span>11PM</span>
                      </div>
                    </div>
                  </div>
                </DataSectionWrapper>
              </div>

            </div>
          </div>

          {/* Radar Chart: Campaign Health */}
          <div className="rounded-3xl border border-slate-200 dark:border-border/50 bg-white dark:bg-card/40 backdrop-blur-md p-6 flex flex-col shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-none">
            <div className="mb-2">
              <h3 className="text-lg font-medium tracking-tight mb-1 text-foreground">Campaign AI Health</h3>
              <p className="text-xs text-muted-foreground">Performance Profile Metrics</p>
            </div>
            
            <div className="flex-1 min-h-[250px] w-full text-foreground">
              {radarChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  {/* Maps all fields provided in radarStats dynamically */}
                  <RadarChart cx="50%" cy="50%" outerRadius="60%" data={radarChartData} margin={{ top: 10, right: 30, bottom: 10, left: 30 }}>
                    <PolarGrid stroke="currentColor" className="text-border" strokeDasharray="3 3" />
                    <PolarAngleAxis dataKey="subject" tick={{ fill: "currentColor", fontSize: 10, fontWeight: 500 }} />
                    <PolarRadiusAxis angle={30} domain={[0, 100]} tick={false} axisLine={false} />
                    <Radar name="Metrics" dataKey="value" stroke={primaryColor} fill={primaryColor} fillOpacity={0.2} />
                    <Tooltip contentStyle={{ backgroundColor: 'hsl(var(--background))', border: '1px solid hsl(var(--border))', borderRadius: '8px', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }} itemStyle={{ fontSize: '12px' }} />
                  </RadarChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center text-muted-foreground/50"><Target className="mb-2 opacity-50" /></div>
              )}
            </div>
          </div>

        </div>

        {/* Drill-down Slide Panel */}
        <AnimatePresence>
          {selectedFunnelStep && (
            <motion.div 
              initial={{ opacity: 0 }} 
              animate={{ opacity: 1 }} 
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-50 flex justify-end bg-background/80 backdrop-blur-sm"
              onClick={() => setSelectedFunnelStep(null)}
            >
              <motion.div 
                initial={{ x: '100%', opacity: 0.5 }} 
                animate={{ x: 0, opacity: 1 }} 
                exit={{ x: '100%', opacity: 0.5 }}
                transition={{ type: "spring", damping: 25, stiffness: 200 }}
                className="w-full max-w-md h-full bg-white dark:bg-background border-l border-border/50 shadow-2xl flex flex-col"
                onClick={e => e.stopPropagation()}
              >
                <div className="p-5 border-b border-border/50 flex items-center justify-between bg-muted/20">
                  <div>
                    <h2 className="text-xl font-semibold text-foreground">{selectedFunnelStep} Leads</h2>
                    <p className="text-sm text-muted-foreground">Showing leads currently at this stage</p>
                  </div>
                  <button onClick={() => setSelectedFunnelStep(null)} className="p-2 bg-background border border-border/50 rounded-xl text-muted-foreground hover:text-foreground hover:bg-muted transition-colors shadow-sm">
                    <X size={18} />
                  </button>
                </div>
                
                <div className="flex-1 overflow-y-auto p-5 space-y-4">
                  {isFunnelLoading ? (
                    Array.from({ length: 4 }).map((_, i) => (
                      <div key={i} className="p-4 rounded-xl border border-border/50 bg-background/50 flex items-center justify-between animate-pulse">
                        <div className="flex items-center gap-3 w-full">
                          <div className="w-10 h-10 rounded-full bg-muted flex-shrink-0" />
                          <div className="space-y-2 w-full">
                            <div className="h-4 bg-muted rounded w-1/3" />
                            <div className="h-3 bg-muted rounded w-1/2" />
                          </div>
                        </div>
                      </div>
                    ))
                  ) : funnelLeads.length > 0 ? (
                    funnelLeads.map((lead, i) => (
                      <motion.div 
                        key={lead.id || i} 
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: i * 0.05 }}
                        className="p-4 rounded-xl border border-border/50 bg-background hover:bg-muted/30 transition-colors flex items-center justify-between group cursor-pointer"
                      >
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-full bg-primary/10 text-primary flex items-center justify-center font-bold text-sm">
                            {(lead.name || "?").charAt(0).toUpperCase()}
                          </div>
                          <div>
                            <p className="text-sm font-semibold text-foreground group-hover:text-primary transition-colors">{lead.name}</p>
                            <p className="text-xs text-muted-foreground">
                              {lead.title}{lead.title && lead.company ? ' · ' : ''}{lead.company}
                            </p>
                          </div>
                        </div>
                        <ExternalLink size={16} className="text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                      </motion.div>
                    ))
                  ) : isFunnelLoading ? (
                    <div className="flex items-center justify-center h-full text-muted-foreground text-sm flex-col gap-3">
                      <span className="flex space-x-1">
                        <span className="w-1.5 h-1.5 bg-primary/40 rounded-full animate-bounce [animation-delay:-0.3s]"></span>
                        <span className="w-1.5 h-1.5 bg-primary/60 rounded-full animate-bounce [animation-delay:-0.15s]"></span>
                        <span className="w-1.5 h-1.5 bg-primary/80 rounded-full animate-bounce"></span>
                      </span>
                      Loading leads...
                    </div>
                  ) : (
                    <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
                      No leads found in this stage yet.
                    </div>
                  )}
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>

      </motion.div>
    </>
  )
}

export { formatKpiValue }
