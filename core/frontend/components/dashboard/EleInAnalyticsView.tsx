import { useState, useMemo, useEffect } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { 
  Users, RefreshCw, AlertTriangle, X, ArrowRight, 
  ExternalLink, Download, Search, Copy, Check, Lock,
  Loader2
} from 'lucide-react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis
} from 'recharts'
import { FilterDropdown } from './FilterDropdown'
import { ElesiumLogo } from '@/components/ElesiumLogo'

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

// --- Custom Tooltips ---
const CustomAreaTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-card/95 border border-border/60 p-4 rounded-lg shadow-xl shadow-foreground/5">
        <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-3">
          {formatXAxisDate(label) || label}
        </p>
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

// --- Instant Metric Number Renderer ---
function AnimatedNumber({ value }: { value: string | number; duration?: number }) {
  return <>{value}</>;
}

// --- Components ---

// Static 5-node pipeline visualizer connecting conversion stages
export function FunnelPipelineFlow() {
  const stages = [
    { name: "Audience" },
    { name: "Enrolled" },
    { name: "Connected" },
    { name: "Replied" },
    { name: "Booked" },
  ]

  return (
    <div className="flex items-center justify-between px-3 py-2.5 mb-3 rounded-lg bg-background/50 border border-border/60">
      {stages.map((stage, idx) => (
        <div key={stage.name} className="flex items-center gap-2 flex-1 last:flex-initial">
          <div className="flex flex-col items-center gap-1">
            <div className="w-5 h-5 rounded-full border border-primary/40 bg-card flex items-center justify-center text-[9px] font-mono font-bold text-primary shadow-xs">
              {idx + 1}
            </div>
            <span className="text-[10px] font-medium text-muted-foreground select-none">
              {stage.name}
            </span>
          </div>
          {idx < stages.length - 1 && (
            <div className="flex-1 h-px bg-border/60 mx-1.5 self-center mb-3" />
          )}
        </div>
      ))}
    </div>
  )
}

/* DataSectionWrapper: handles empty and loading states cleanly without artificial skeleton grids. */
export function DataSectionWrapper({ 
  data, 
  emptyLabel = 'No Data',
  emptySubtext = 'Data will appear here once available',
  isLoading, 
  children,
  skeletonHeightClass = "h-[110px]"
}: { 
  data: any[] | null | undefined, 
  emptyLabel?: string,
  emptySubtext?: string,
  isLoading?: boolean, 
  children: React.ReactNode,
  skeletonHeightClass?: string,
  gridCols?: number
}) {
  if (isLoading) {
    return (
      <div className={`w-full ${skeletonHeightClass} flex items-center justify-center animate-pulse bg-background rounded-lg border border-border`}>
        <div className="text-muted-foreground text-sm flex items-center gap-2">
          <RefreshCw className="w-4 h-4 animate-spin" /> Loading...
        </div>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className={`w-full ${skeletonHeightClass} relative rounded-lg border border-border/80 bg-background/50 flex flex-col items-center justify-center p-4 text-center`}>
        <div className="text-xs font-semibold text-foreground/80">{emptyLabel}</div>
        {emptySubtext && <div className="text-[11px] text-muted-foreground mt-0.5">{emptySubtext}</div>}
      </div>
    );
  }

  return <div className="w-full h-full">{children}</div>;
}

function formatKpiValue(value: string | number | undefined | null, options?: { unit?: 'count' | 'percentage' }): string {
  if (value === null || value === undefined || value === '') {
    return options?.unit === 'count' ? '0' : 'Unknown';
  }

  if (options?.unit === 'count') {
    return String(Math.round(Number(value) || 0));
  }

  if (typeof value === 'number') {
    if (isNaN(value)) return '0%';
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
      <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${colorClass}`} style={{ width: `${clampedWidth}%` }} />
      </div>
    </div>
  );
}

export function getHeatmapColorClass(value: number, max: number): string {
  if (typeof value !== 'number' || isNaN(value) || value <= 0) {
    return 'bg-muted dark:bg-muted/60';
  }
  
  const safeMax = Math.max(max, 1);
  const ratio = value / safeMax;
  
  if (ratio >= 0.75) return 'bg-primary';
  if (ratio >= 0.50) return 'bg-primary/80';
  if (ratio >= 0.25) return 'bg-primary/60';
  return 'bg-primary/40';
}

const INTELLIGENCE_TABS = [
  { id: 'topography', label: 'Topography', prefix: 'Activity ', isAi: false },
  { id: 'radar', label: 'Radar', prefix: 'AI Health ', isAi: true },
  { id: 'stream', label: 'Stream', prefix: 'Live ', isAi: false }
] as const;

interface EleInAnalyticsViewProps {
  summary?: any;
  today?: any;
  timeSeries?: any[];
  heatmapData?: any[];
  timeOfDayData?: any[];
  aiInsight?: string;
  funnelSteps?: any[];
  leadSources?: any[];
  radarStats?: any;
  liveFeed?: any[];
  errorFeed?: any[];
  accountHealth?: any;
  onTimeRangeChange?: (range: string) => void;
  onExportPdf?: () => void;
  isExportingPdf?: boolean;
  senders?: any[];
  campaigns?: any[];
  selectedSenders?: string[];
  selectedCampaigns?: string[];
  onSendersChange?: (ids: string[]) => void;
  onCampaignsChange?: (ids: string[]) => void;
  isLoading?: boolean;
  primaryColor?: string;
  secondaryColor?: string;
  fetchFunnelLeads?: (step: string, signal?: AbortSignal) => Promise<any[]>;
  live_feed_error?: boolean;
  timeRange?: string;
  isExtendedLocked?: boolean;
  isPdfLocked?: boolean;
  isFunnelCsvLocked?: boolean;
  workspaceName?: string;
}

export function EleInAnalyticsView({ 
  summary, today, timeSeries, heatmapData, timeOfDayData, aiInsight: _aiInsight, funnelSteps, leadSources, radarStats, liveFeed, errorFeed, accountHealth, onTimeRangeChange, onExportPdf, isExportingPdf = false, senders = [], campaigns = [], selectedSenders = [], selectedCampaigns = [], onSendersChange, onCampaignsChange, isLoading, primaryColor = "#10B981", secondaryColor = "#6366F1", fetchFunnelLeads, live_feed_error, timeRange = '7d', isExtendedLocked = false, isPdfLocked = false, isFunnelCsvLocked = false,
  workspaceName
}: EleInAnalyticsViewProps) {
  const navigate = useNavigate()
  const [hoveredSeries, setHoveredSeries] = useState<string | null>(null)
  const [hoveredFunnelStep, setHoveredFunnelStep] = useState<number | null>(null)
  const [selectedFunnelStep, setSelectedFunnelStep] = useState<string | null>(null)
  
  const [funnelLeads, setFunnelLeads] = useState<any[]>([])
  const [funnelSearch, setFunnelSearch] = useState<string>("")
  const [funnelError, setFunnelError] = useState<string | null>(null)
  const [funnelFetchTrigger, setFunnelFetchTrigger] = useState(0)
  const [copiedLeadId, setCopiedLeadId] = useState<string | null>(null)
  const [isFunnelLoading, setIsFunnelLoading] = useState(false)
  const [heatmapFilter, setHeatmapFilter] = useState<'all' | 'connections' | 'messages'>('all')
  const [intelligenceTab, setIntelligenceTab] = useState<'topography' | 'radar' | 'stream'>('topography')
  const [hoveredIntelligenceTab, setHoveredIntelligenceTab] = useState<string | null>(null)
  const [hoveredTimeRange, setHoveredTimeRange] = useState<string | null>(null)
  const [hoveredHeatmapFilter, setHoveredHeatmapFilter] = useState<string | null>(null)

  // Layer 2: Close cohort lead drawer on Escape key press
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (['INPUT', 'TEXTAREA'].includes((e.target as HTMLElement)?.tagName)) {
        return;
      }
      if (e.key === 'Escape') {
        setSelectedFunnelStep(null);
        setFunnelSearch("");
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Stage explanations
  const STAGE_DESCRIPTIONS: Record<string, string> = {
    Extracted: "Total prospects imported into workspace database ready for campaign allocation",
    Enrolled: "Leads successfully mapped to active campaign versions and scheduled",
    Connected: "Prospects who have actively accepted connection invitations on LinkedIn",
    Replied: "Prospects who sent an inbound response to sequence messaging touchpoints",
    Booked: "Prospects who converted or booked a calendar meeting",
    "Failed/Bounced": "Outreach attempts that encountered deliverability or proxy issues"
  }

  // Filtered leads based on search query
  const filteredFunnelLeads = useMemo(() => {
    if (!funnelSearch.trim()) return funnelLeads
    const q = funnelSearch.toLowerCase()
    return funnelLeads.filter(l => 
      (l.name && l.name.toLowerCase().includes(q)) ||
      (l.title && l.title.toLowerCase().includes(q)) ||
      (l.company && l.company.toLowerCase().includes(q))
    )
  }, [funnelLeads, funnelSearch])

  const safeTimeSeries = timeSeries ?? [];
  const activeFunnelSteps = funnelSteps ?? [];
  
  const liveFeedError = live_feed_error ?? false;

  // Dynamic radar chart transformation - maps whatever fields the API sends
  const radarChartData = useMemo(() => {
    if (!radarStats || typeof radarStats !== 'object' || Array.isArray(radarStats)) return [];
    return Object.entries(radarStats).map(([key, value]) => ({
      subject: key,
      value: Math.max(0, Math.min(Number(value) || 0, 100)), // clamp between 0 and 100
      fullMark: 100
    }));
  }, [radarStats]);

  // Export stage leads to CSV with Layer 2 CSV formula injection shielding
  const handleExportFunnelCsv = () => {
    if (!funnelLeads || funnelLeads.length === 0) {
      toast.info("No leads available to export in this stage")
      return
    }

    const sanitizeCsvCell = (val: any) => {
      if (val === null || val === undefined) return '""';
      let str = String(val);
      // Layer 2 Human Paranoia: Prevent formula injection (=, +, -, @)
      if (/^[=+\-@\t\r]/.test(str)) {
        str = "'" + str;
      }
      return `"${str.replace(/"/g, '""')}"`;
    };

    const headers = ["Lead ID", "Name", "Job Title", "Company", "LinkedIn URL", "Email"]
    const rows = funnelLeads.map(l => [
      sanitizeCsvCell(l.id),
      sanitizeCsvCell(l.name),
      sanitizeCsvCell(l.title),
      sanitizeCsvCell(l.company),
      sanitizeCsvCell(l.linkedin_url),
      sanitizeCsvCell(l.email)
    ])
    const csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows.map(r => r.join(","))].join("\n")
    const encodedUri = encodeURI(csvContent)
    const link = document.createElement("a")
    link.setAttribute("href", encodedUri)
    link.setAttribute("download", `elein-stage-${(selectedFunnelStep || 'funnel').toLowerCase()}-leads-${new Date().toISOString().slice(0, 10)}.csv`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    toast.success(`Exported ${funnelLeads.length} stage leads to CSV!`)
  }

  // IMPORTANT: This useEffect MUST have a cleanup function to cancel in-flight requests. Never remove the return () => ... statement.
  useEffect(() => {
    if (!selectedFunnelStep || !fetchFunnelLeads) {
      return
    }

    const controller = new AbortController()

    setIsFunnelLoading(true)
    setFunnelLeads([])
    setFunnelError(null)

    fetchFunnelLeads(selectedFunnelStep, controller.signal)
      .then((data: any[]) => {
        if (controller.signal.aborted) return
        setFunnelLeads(data || [])
      })
      .catch((err: any) => {
        if (err.name === 'AbortError' || controller.signal.aborted) return
        setFunnelError(err.message || 'Failed to load stage leads')
        setFunnelLeads([])
      })
      .finally(() => {
        if (controller.signal.aborted) return
        setIsFunnelLoading(false)
      })

    return () => controller.abort()
  }, [selectedFunnelStep, fetchFunnelLeads, funnelFetchTrigger]) // fetchFunnelLeads is now stable via useCallback



  const safeSummary = summary || {}
  const safeToday = today || {}

  const primaryKpis = [
    { 
      label: "Total Audience", 
      value: safeSummary.total_leads || 0, 
      unit: "prospects",
      action: (safeSummary.total_leads || 0) === 0 ? { label: "Import Leads", href: "/elein/leads" } : null 
    },
    { 
      label: "Active Campaigns", 
      value: safeSummary.active_campaigns || 0, 
      unit: "sequences",
      action: (safeSummary.active_campaigns || 0) === 0 ? { label: "Launch Sequence", href: "/elein/campaigns/new" } : null 
    },
    { 
      label: "Connections Today", 
      value: safeSummary.connections_today || 0, 
      unit: "sent",
      action: (safeSummary.connections_today || 0) === 0 ? { label: "Connect Senders", href: "/elein/accounts" } : null 
    },
    { 
      label: "Messages Today", 
      value: safeSummary.messages_today || 0, 
      unit: "delivered",
      action: null 
    }
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
      <div className="space-y-6 max-w-[1800px] mx-auto pb-12 relative">
        {/* Unified Command Bar (Linear / Stripe Standard) */}
        <div className="flex flex-col xl:flex-row justify-between items-start xl:items-center gap-4 px-1 pb-1">
          <div>
            <h2 className="text-xl font-semibold tracking-tight text-foreground flex items-center gap-2">
              Performance Overview
              {isLoading && (
                <Loader2 size={13} className="animate-spin text-muted-foreground ml-1.5" />
              )}
            </h2>
            <p className="text-xs text-muted-foreground mt-0.5">Live telemetry across outreach fleet</p>
          </div>
          
          <div className="flex flex-wrap items-center gap-2.5 w-full xl:w-auto">
            {/* Global Scoping Filters */}
            {onSendersChange && (
              <FilterDropdown 
                label="Senders"
                options={senders}
                selectedIds={selectedSenders}
                onChange={onSendersChange}
                placeholder="All Senders"
              />
            )}

            {onCampaignsChange && (
              <FilterDropdown 
                label="Campaigns"
                options={campaigns}
                selectedIds={selectedCampaigns}
                onChange={onCampaignsChange}
                placeholder="All Campaigns"
              />
            )}

            {(selectedSenders.length > 0 || selectedCampaigns.length > 0) && (
              <button
                type="button"
                onClick={() => {
                  if (onSendersChange) onSendersChange([]);
                  if (onCampaignsChange) onCampaignsChange([]);
                }}
                className="text-xs font-semibold text-muted-foreground hover:text-foreground px-1.5 py-1 transition-colors cursor-pointer"
              >
                Reset filters
              </button>
            )}

            {/* Visual Divider between filters and time horizon */}
            {(onSendersChange || onCampaignsChange) && (
              <div className="hidden sm:block w-px h-5 bg-border mx-0.5" />
            )}

            {/* Time Horizon Segmented Control */}
            <div 
              onMouseLeave={() => setHoveredTimeRange(null)}
              className="relative inline-flex items-center p-0.5 bg-card rounded-lg border border-border shadow-xs h-8" 
              role="group" 
              aria-label="Time range selection"
            >
              {TIME_RANGES.map((range) => {
                const isActive = timeRange === range.value;
                const isHovered = hoveredTimeRange === range.value;

                return (
                  <button
                    key={range.value}
                    type="button"
                    aria-pressed={isActive}
                    aria-label={`Show data for ${range.label}`}
                    onClick={() => {
                      if (onTimeRangeChange) onTimeRangeChange(range.value)
                    }}
                    onMouseEnter={() => setHoveredTimeRange(range.value)}
                    className="relative px-2.5 py-1 text-xs font-medium rounded-md transition-colors flex items-center gap-1.5 cursor-pointer select-none focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary h-[calc(100%-2px)]"
                  >
                    {/* Active Sliding Pill */}
                    {isActive && (
                      <motion.span
                        layoutId="time-range-active-pill"
                        className="absolute inset-0 rounded-md bg-muted shadow-xs z-0"
                        transition={{ type: "spring", stiffness: 450, damping: 35 }}
                      />
                    )}

                    {/* Smooth Hover Glider */}
                    <AnimatePresence>
                      {!isActive && isHovered && (
                        <motion.span
                          layoutId="time-range-hover-pill"
                          initial={false}
                          animate={{ opacity: 1 }}
                          exit={{ opacity: 0 }}
                          className="absolute inset-0 rounded-md bg-foreground/[0.06] dark:bg-foreground/[0.1] z-0"
                          transition={{ type: "spring", stiffness: 500, damping: 35 }}
                        />
                      )}
                    </AnimatePresence>

                    <span className={`relative z-10 transition-colors duration-150 ${
                      isActive ? 'text-foreground font-semibold' : 'text-muted-foreground hover:text-foreground'
                    }`}>
                      {range.label}
                    </span>
                  </button>
                );
              })}
            </div>

            {/* Export Action */}
            {onExportPdf && (
              <button
                type="button"
                onClick={onExportPdf}
                disabled={isExportingPdf}
                className={`inline-flex items-center gap-1.5 h-8 px-3 text-xs font-semibold rounded-lg transition-colors cursor-pointer disabled:opacity-50 shadow-xs ${
                  isPdfLocked
                    ? "text-amber-600 dark:text-amber-400 bg-amber-500/10 border border-amber-500/20 hover:bg-amber-500/15"
                    : "text-primary bg-primary/10 border border-primary/20 hover:bg-primary/20"
                }`}
                title={isPdfLocked ? "Executive PDF Export requires Growth Pro or Enterprise (click to upgrade)" : "Export performance overview to PDF"}
              >
                {isExportingPdf ? (
                  <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                ) : isPdfLocked ? (
                  <Lock className="h-3.5 w-3.5 text-amber-500 shrink-0" />
                ) : (
                  <Download className="h-3.5 w-3.5 shrink-0" />
                )}
                <span>{isExportingPdf ? "Generating..." : "Export PDF"}</span>
                {isPdfLocked && (
                  <span className="text-[9px] font-bold uppercase tracking-wider px-1 py-0.5 rounded bg-amber-500/20 text-amber-600 dark:text-amber-400">
                    PRO
                  </span>
                )}
              </button>
            )}
          </div>
        </div>


        {/* Metric Overview (Linear / Stripe Engineering Tier) */}
        <div className="space-y-3">
          {/* 4 Core Primary Vital Signs */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {primaryKpis.map((stat) => (
              <div 
                key={stat.label}
                className="rounded-lg border border-border bg-card p-4 shadow-xs hover:border-foreground/20 flex flex-col justify-between transition-colors"
              >
                <div className="flex items-center justify-between text-muted-foreground mb-2.5">
                  <span className="text-[11px] font-medium uppercase tracking-wider">{stat.label}</span>
                  <span className="text-[10px] font-mono text-muted-foreground/60">{stat.unit}</span>
                </div>
                <div className="flex items-baseline justify-between gap-2">
                  <p className="text-2xl font-semibold tracking-tight text-foreground tabular-nums font-mono">
                    {(typeof stat.value === 'number' ? stat.value : Number(stat.value) || 0).toLocaleString()}
                  </p>
                  {stat.action && (
                    <button
                      type="button"
                      onClick={() => stat.action?.href && navigate(stat.action.href)}
                      className="text-[10px] font-semibold text-primary bg-primary/10 hover:bg-primary/20 px-2 py-0.5 rounded-md flex items-center gap-1 transition-colors cursor-pointer shrink-0"
                    >
                      <span>{stat.action.label}</span>
                      <ArrowRight size={10} />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Secondary Telemetry Strip (Linear/Vercel Divider Pattern - Zero Decorative Icons) */}
          <div className="rounded-lg border border-border bg-card shadow-xs overflow-hidden">
            <div className="grid grid-cols-2 lg:grid-cols-4 divide-y sm:divide-y-0 sm:divide-x divide-border">
              <div className="px-4 py-2.5 flex items-center justify-between text-xs">
                <span className="text-muted-foreground">Inmails (24h)</span>
                <span className="font-mono font-semibold text-foreground tabular-nums">
                  <AnimatedNumber value={safeSummary.inmails_today || 0} />
                </span>
              </div>
              <div className="px-4 py-2.5 flex items-center justify-between text-xs">
                <span className="text-muted-foreground">Account Health</span>
                <span className="inline-flex items-center gap-1.5 font-semibold text-foreground">
                  <span className={`w-1.5 h-1.5 rounded-full ${String(safeSummary.account_health).toLowerCase().includes('good') || String(safeSummary.account_health).toLowerCase().includes('excellent') ? 'bg-primary' : 'bg-amber-500'}`} />
                  <span>{formatKpiValue(safeSummary.account_health as any)}</span>
                </span>
              </div>
              <div className="px-4 py-2.5 flex items-center justify-between text-xs">
                <span className="text-muted-foreground">Positive Sentiment</span>
                <span className="font-mono font-semibold text-foreground tabular-nums">
                  <AnimatedNumber value={formatKpiValue(safeSummary.positive_sentiment as any, { unit: 'count' })} />
                </span>
              </div>
              <div className="px-4 py-2.5 flex items-center justify-between text-xs">
                <span className="text-muted-foreground">Auto-Withdrawals</span>
                <span className="font-mono font-semibold text-foreground tabular-nums">
                  <AnimatedNumber value={safeSummary.auto_withdrawals ?? 0} />
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Sender Fleet Throttle Status */}
        {accountHealth?.accounts && accountHealth.accounts.length > 0 && (
          <div className="p-4 rounded-lg border border-border bg-card shadow-xs space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-foreground">Fleet Throttle & Capacity</span>
              <button
                type="button"
                onClick={() => navigate('/elein/accounts')}
                className="text-[11px] font-semibold text-primary hover:underline flex items-center gap-1 cursor-pointer"
              >
                <span>Manage Fleet</span>
                <ArrowRight size={11} />
              </button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
              {(accountHealth?.accounts || []).map((acc: any, i: number) => {
                if (!acc) return null
                const connPct = acc.connection_pct ?? (acc.connections_limit > 0 ? (acc.connections_used / acc.connections_limit) * 100 : 0)
                const msgPct = acc.message_pct ?? (acc.messages_limit > 0 ? (acc.messages_used / acc.messages_limit) * 100 : 0)
                const maxPct = Math.max(connPct, msgPct)
                let dotColor = 'bg-primary'
                if (maxPct >= 90) dotColor = 'bg-destructive'
                else if (maxPct >= 70) dotColor = 'bg-primary'

                return (
                  <div key={i} className="rounded-lg border border-border bg-background p-3 text-xs space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 min-w-0">
                        <div className={`w-2 h-2 rounded-full ${dotColor}`} />
                        <span className="font-semibold text-foreground truncate">{acc.name}</span>
                      </div>
                      {acc.throttled && (
                        <span className="text-[9px] font-bold px-1.5 py-0.2 rounded-md bg-destructive/10 text-destructive">Paced</span>
                      )}
                    </div>
                    <div className="space-y-1.5">
                      <LimitProgressBar used={acc.connections_used} limit={acc.connections_limit} pct={acc.connection_pct} label="Connections" />
                      <LimitProgressBar used={acc.messages_used} limit={acc.messages_limit} pct={acc.message_pct} label="Messages" />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Dual Cockpit Row: Velocity Chart (Left) + Conversion Funnel (Right) */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          {/* Network Velocity Area Chart */}
          <div className="lg:col-span-7 rounded-lg border border-border bg-card p-5 shadow-xs flex flex-col">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-bold text-foreground">Network Velocity</h3>
                </div>
                <p className="text-[11px] text-muted-foreground">Connections & message actions over time</p>
              </div>
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-3 text-xs">
                  <button 
                    type="button"
                    onClick={() => setHoveredSeries(hoveredSeries === 'connections' ? null : 'connections')}
                    className={`flex items-center gap-1.5 px-2 py-0.5 rounded-md transition-colors cursor-pointer ${hoveredSeries === 'connections' ? 'bg-primary/20 font-bold' : ''}`}
                  >
                    <div className="w-2 h-2 rounded-full" style={{ backgroundColor: primaryColor }} />
                    <span className="text-foreground">Connections</span>
                  </button>
                  <button 
                    type="button"
                    onClick={() => setHoveredSeries(hoveredSeries === 'messages' ? null : 'messages')}
                    className={`flex items-center gap-1.5 px-2 py-0.5 rounded-md transition-colors cursor-pointer ${hoveredSeries === 'messages' ? 'bg-primary/20 font-bold' : ''}`}
                  >
                    <div className="w-2 h-2 rounded-full" style={{ backgroundColor: secondaryColor }} />
                    <span className="text-foreground">Messages</span>
                  </button>
                  <button 
                    type="button"
                    onClick={() => setHoveredSeries(hoveredSeries === 'inmails' ? null : 'inmails')}
                    className={`flex items-center gap-1.5 px-2 py-0.5 rounded-md transition-colors cursor-pointer ${hoveredSeries === 'inmails' ? 'bg-amber-500/20 font-bold' : ''}`}
                  >
                    <div className="w-2 h-2 rounded-full bg-amber-500" />
                    <span className="text-foreground">Inmails</span>
                  </button>
                </div>
              </div>
            </div>

            <div className="h-[280px] w-full pt-1">
              {safeTimeSeries.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={safeTimeSeries} margin={{ top: 10, right: 0, left: -25, bottom: 0 }}>
                    <defs>
                      <linearGradient id="colorConn" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={primaryColor} stopOpacity={0.25}/>
                        <stop offset="95%" stopColor={primaryColor} stopOpacity={0}/>
                      </linearGradient>
                      <linearGradient id="colorMsg" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={secondaryColor} stopOpacity={0.25}/>
                        <stop offset="95%" stopColor={secondaryColor} stopOpacity={0}/>
                      </linearGradient>
                      <linearGradient id="colorInmails" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.25}/>
                        <stop offset="95%" stopColor="#f59e0b" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-border" vertical={false} />
                    <XAxis dataKey="date" tick={{ fill: "currentColor", fontSize: 10, opacity: 0.7 }} className="text-muted-foreground" tickLine={false} axisLine={false} tickFormatter={formatXAxisDate} dy={10} />
                    <YAxis tick={{ fill: "currentColor", fontSize: 10, opacity: 0.7 }} className="text-muted-foreground" tickLine={false} axisLine={false} dx={-10} />
                    <Tooltip cursor={{ stroke: 'currentColor', strokeWidth: 1, strokeDasharray: '4 4', opacity: 0.2 }} content={<CustomAreaTooltip />} />
                    <Area type="monotone" dataKey="connections" stroke={primaryColor} strokeWidth={2.5} fill="url(#colorConn)" style={{ opacity: hoveredSeries && hoveredSeries !== 'connections' ? 0.2 : 1, transition: 'opacity 0.2s ease' }} activeDot={{ r: 5, fill: primaryColor, stroke: 'var(--card)', strokeWidth: 2 }} />
                    <Area type="monotone" dataKey="messages" stroke={secondaryColor} strokeWidth={2.5} fill="url(#colorMsg)" style={{ opacity: hoveredSeries && hoveredSeries !== 'messages' ? 0.2 : 1, transition: 'opacity 0.2s ease' }} activeDot={{ r: 5, fill: secondaryColor, stroke: 'var(--card)', strokeWidth: 2 }} />
                    <Area type="monotone" dataKey="inmails" stroke="#f59e0b" strokeWidth={2.5} fill="url(#colorInmails)" style={{ opacity: hoveredSeries && hoveredSeries !== 'inmails' ? 0.2 : 1, transition: 'opacity 0.2s ease' }} activeDot={{ r: 5, fill: "#f59e0b", stroke: 'var(--card)', strokeWidth: 2 }} />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center text-xs font-mono text-muted-foreground">
                  No telemetry recorded in selected window
                </div>
              )}
            </div>
          </div>

          {/* Interactive Conversion Funnel */}
          <div className="lg:col-span-5 rounded-lg border border-border bg-card p-5 shadow-xs flex flex-col justify-between">
            <div className="mb-2">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-foreground">Conversion Funnel</h3>
              </div>
              <p className="text-[11px] text-muted-foreground">Click any stage to inspect cohort leads</p>
            </div>

            {/* Pipeline Visualizer */}
            <FunnelPipelineFlow />

            <div className="space-y-2.5 my-auto">
              {!activeFunnelSteps || activeFunnelSteps.length === 0 ? (
                <p className="text-muted-foreground text-xs text-center py-8">No funnel data yet</p>
              ) : activeFunnelSteps.map((step: any, i: number) => {
                const maxVal = (typeof activeFunnelSteps[0]?.value === 'number' ? activeFunnelSteps[0].value : typeof activeFunnelSteps[0]?.count === 'number' ? activeFunnelSteps[0].count : undefined) || 1
                const stepVal = typeof step?.value === 'number' ? step.value : typeof step?.count === 'number' ? step.count : 0
                const widthPct = Math.min((stepVal / maxVal) * 100, 100)
                const isHovered = hoveredFunnelStep === i
                const stepColor = step.color || primaryColor
                const isFailedStep = step.label === 'Failed/Bounced'

                return (
                  <div 
                    key={step.label} 
                    role="button"
                    tabIndex={0}
                    aria-label={`Inspect ${step.label} stage leads (${(stepVal ?? 0).toLocaleString()})`}
                    className={`p-2 rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary ${isFunnelLoading ? 'cursor-wait opacity-80' : 'cursor-pointer hover:bg-muted/60'} ${isFailedStep ? 'border-t border-border pt-2.5' : ''}`}
                    onMouseEnter={() => setHoveredFunnelStep(i)} 
                    onMouseLeave={() => setHoveredFunnelStep(null)}
                    onClick={() => {
                      if (isFunnelLoading) return;
                      setSelectedFunnelStep(step.label);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        if (!isFunnelLoading) setSelectedFunnelStep(step.label);
                      }
                    }}
                  >
                    <div className="flex justify-between items-center text-xs mb-1.5">
                      <span className={`font-semibold transition-colors ${isHovered ? 'text-primary' : 'text-foreground'}`}>
                        {step.label}
                      </span>
                      <div className="flex items-center gap-1.5">
                        {i > 0 && typeof activeFunnelSteps[i - 1]?.value === 'number' && activeFunnelSteps[i - 1].value > 0 && (
                          <span className="text-[10px] text-muted-foreground font-mono">
                            {((stepVal / activeFunnelSteps[i - 1].value) * 100).toFixed(0)}%
                          </span>
                        )}
                        <span className="font-mono font-bold text-foreground">
                          {(stepVal ?? 0).toLocaleString()}
                        </span>
                      </div>
                    </div>
                    <div className="w-full h-2 bg-muted rounded-full overflow-hidden">
                      <div 
                        className="h-full rounded-full transition-[width] duration-500 ease-out" 
                        style={{ backgroundColor: stepColor, width: `${widthPct}%` }} 
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>

        {/* Fleet Deep Telemetry Deck (Topography Heatmaps | Radar | Real-Time Stream) */}
        <div className="rounded-lg border border-border bg-card p-5 space-y-4 shadow-xs [content-visibility:auto] [contain-intrinsic-size:auto_260px]">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border pb-3">
            <div>
              <h3 className="text-sm font-bold text-foreground">Fleet Telemetry & Activity Matrix</h3>
              <p className="text-[11px] text-muted-foreground flex items-center gap-1">
                <span>Deep behavioral patterns, activity topographies, and</span>
                <ElesiumLogo size={12} className="inline-block" />
                <span>AI diagnosis</span>
              </p>
            </div>

            {/* Segmented Tab Pill */}
            <div 
              onMouseLeave={() => setHoveredIntelligenceTab(null)}
              className="relative inline-flex items-center p-1 bg-muted/60 rounded-lg border border-border text-xs font-semibold overflow-x-auto max-w-full scrollbar-hide shrink-0"
              role="tablist"
              aria-label="Fleet telemetry views"
            >
              {INTELLIGENCE_TABS.map((tab) => {
                const isActive = intelligenceTab === tab.id;
                const isHovered = hoveredIntelligenceTab === tab.id;

                return (
                  <button
                    key={tab.id}
                    type="button"
                    role="tab"
                    aria-selected={isActive}
                    onClick={() => setIntelligenceTab(tab.id)}
                    onMouseEnter={() => setHoveredIntelligenceTab(tab.id)}
                    className="relative px-3.5 py-1.5 rounded-lg whitespace-nowrap cursor-pointer select-none flex items-center justify-center transition-colors duration-150 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
                  >
                    {/* Active Sliding Pill */}
                    {isActive && (
                      <motion.span
                        layoutId="intelligence-tab-active-pill"
                        className="absolute inset-0 rounded-lg bg-primary shadow-xs z-0"
                        transition={{ type: "spring", stiffness: 450, damping: 35 }}
                      />
                    )}

                    {/* Smooth Hover Glider */}
                    <AnimatePresence>
                      {!isActive && isHovered && (
                        <motion.span
                          layoutId="intelligence-tab-hover-pill"
                          initial={false}
                          animate={{ opacity: 1 }}
                          exit={{ opacity: 0 }}
                          className="absolute inset-0 rounded-lg bg-foreground/[0.08] dark:bg-foreground/[0.12] z-0"
                          transition={{ type: "spring", stiffness: 500, damping: 35 }}
                        />
                      )}
                    </AnimatePresence>

                    {/* Tab Label */}
                    <span
                      className={`relative z-10 transition-colors duration-150 flex items-center gap-1.5 ${
                        isActive
                          ? 'text-primary-foreground font-semibold'
                          : 'text-muted-foreground hover:text-foreground font-medium'
                      }`}
                    >
                      {tab.isAi && (
                        <ElesiumLogo 
                          size={14} 
                          className="inline-block shrink-0" 
                        />
                      )}
                      <span>
                        <span className="hidden sm:inline">{tab.prefix}</span>
                        {tab.label}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Tab 1: Activity Topography (Both Heatmaps with Spacious Breathing Room!) */}
          {intelligenceTab === 'topography' && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 pt-1">
              {/* 12-Month Consistency Heatmap */}
              <div className="space-y-3 p-3.5 rounded-lg bg-background/60 border border-border/60">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-foreground">
                    12-Month Consistency
                  </span>
                  <div 
                    onMouseLeave={() => setHoveredHeatmapFilter(null)}
                    className="relative flex bg-muted/60 p-0.5 rounded-lg border border-border text-[10px] font-bold"
                  >
                    {[
                      { id: 'all', label: 'All' },
                      { id: 'connections', label: 'Conn' },
                      { id: 'messages', label: 'Msg' },
                    ].map((filter) => {
                      const isActive = heatmapFilter === filter.id;
                      const isHovered = hoveredHeatmapFilter === filter.id;

                      return (
                        <button
                          key={filter.id}
                          type="button"
                          onClick={() => setHeatmapFilter(filter.id as any)}
                          onMouseEnter={() => setHoveredHeatmapFilter(filter.id)}
                          className="relative px-2 py-0.5 rounded-md transition-colors cursor-pointer select-none focus-visible:outline-none"
                        >
                          {/* Active Sliding Pill */}
                          {isActive && (
                            <motion.span
                              layoutId="heatmap-filter-active-pill"
                              className="absolute inset-0 rounded-md bg-primary shadow-xs z-0"
                              transition={{ type: "spring", stiffness: 450, damping: 35 }}
                            />
                          )}

                          {/* Smooth Hover Glider */}
                          <AnimatePresence>
                            {!isActive && isHovered && (
                              <motion.span
                                layoutId="heatmap-filter-hover-pill"
                                initial={false}
                                animate={{ opacity: 1 }}
                                exit={{ opacity: 0 }}
                                className="absolute inset-0 rounded-md bg-foreground/[0.08] dark:bg-foreground/[0.12] z-0"
                                transition={{ type: "spring", stiffness: 500, damping: 35 }}
                              />
                            )}
                          </AnimatePresence>

                          <span className={`relative z-10 ${
                            isActive ? 'text-primary-foreground font-bold' : 'text-muted-foreground hover:text-foreground font-semibold'
                          }`}>
                            {filter.label}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
                <DataSectionWrapper data={heatmapData} emptyLabel="12-Month Consistency" isLoading={isLoading} skeletonHeightClass="h-[110px]" gridCols={52}>
                  <div className="flex gap-1 overflow-x-auto pb-2 scrollbar-hide">
                    <div className="grid grid-rows-7 grid-flow-col gap-1 w-max">
                      {heatmapData?.map((val: any, i: number) => {
                        let displayVal = 0;
                        if (typeof val === 'number') displayVal = val;
                        else {
                          if (heatmapFilter === 'connections') displayVal = val.connections ?? 0;
                          else if (heatmapFilter === 'messages') displayVal = val.messages ?? 0;
                          else displayVal = val.count ?? 0;
                        }
                        const colorClass = getHeatmapColorClass(displayVal, maxHeatmapActions);
                        return (
                          <div key={i} className={`w-3 h-3 rounded-[2px] ${colorClass} hover:ring-1 hover:ring-primary cursor-pointer`} title={`${displayVal} actions`} />
                        )
                      })}
                    </div>
                  </div>
                </DataSectionWrapper>
              </div>

              {/* 24/7 Time of Day Heatmap */}
              <div className="space-y-3 p-3.5 rounded-lg bg-background/60 border border-border/60">
                <span className="text-xs font-semibold text-foreground">
                  High-Conversion Hours (24/7)
                </span>
                <DataSectionWrapper data={timeOfDayData} emptyLabel="High-Conversion Hours" isLoading={isLoading} skeletonHeightClass="h-[110px]" gridCols={24}>
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
                              className={`w-full h-full rounded-[2px] ${colorClass} cursor-pointer hover:ring-1 hover:ring-primary`}
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
          )}

          {/* Tab 2: AI Health Radar */}
          {intelligenceTab === 'radar' && (
            <div className="space-y-2 pt-1">
              <div className="flex items-center gap-1.5 px-2">
                <ElesiumLogo size={16} className="shrink-0" />
                <span className="text-xs font-semibold text-foreground">Elesium AI Multi-Vector Health Radar</span>
              </div>
              <div className="min-h-[280px] w-full flex items-center justify-center">
              {radarChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={280}>
                  <RadarChart cx="50%" cy="50%" outerRadius="70%" data={radarChartData}>
                    <PolarGrid stroke="currentColor" className="text-border" strokeDasharray="3 3" />
                    <PolarAngleAxis dataKey="subject" tick={{ fill: "currentColor", fontSize: 11, fontWeight: 500 }} />
                    <PolarRadiusAxis angle={30} domain={[0, 100]} tick={false} axisLine={false} />
                    <Radar name="Metrics" dataKey="value" stroke={primaryColor} fill={primaryColor} fillOpacity={0.25} />
                    <Tooltip contentStyle={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)', borderRadius: '8px' }} />
                  </RadarChart>
                </ResponsiveContainer>
              ) : (
                <div className="text-muted-foreground text-xs">No radar data available</div>
              )}
              </div>
            </div>
          )}

          {/* Tab 3: Live Telemetry Stream */}
          {intelligenceTab === 'stream' && (
            <div className="max-h-[300px] overflow-y-auto space-y-2 pr-1">
              {mergedFeed.map((item: any) => {
                const isError = item.type === 'error';
                return (
                  <div
                    key={item.id || `${item.time}-${item.text}`}
                    className={`flex items-center justify-between text-xs p-2.5 rounded-lg border ${
                      isError ? 'bg-destructive/10 border-destructive/20 text-destructive' : 'bg-muted/40 border-border text-foreground'
                    }`}
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <div className={`w-2 h-2 rounded-full ${isError ? 'bg-destructive' : 'bg-primary'}`} />
                      <span className="truncate">{item.text}</span>
                    </div>
                    <span className="text-[10px] text-muted-foreground whitespace-nowrap ml-4">{timeAgo(item.time)}</span>
                  </div>
                )
              })}
              {mergedFeed.length === 0 && (
                <div className="text-center py-8 text-xs text-muted-foreground">No recent live events</div>
              )}
            </div>
          )}
        </div>



        {/* Drill-down Slide Panel */}
        <AnimatePresence>
          {selectedFunnelStep && (
            <motion.div 
              initial={{ opacity: 0 }} 
              animate={{ opacity: 1 }} 
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-50 flex justify-end bg-background/80 backdrop-blur-xs"
              onClick={() => {
                setSelectedFunnelStep(null);
                setFunnelSearch("");
              }}
            >
              <motion.div 
                initial={{ x: '100%', opacity: 0.5 }} 
                animate={{ x: 0, opacity: 1 }} 
                exit={{ x: '100%', opacity: 0.5 }}
                transition={{ type: "spring", damping: 25, stiffness: 200 }}
                className="w-full max-w-lg h-full bg-card border-l border-border shadow-2xl flex flex-col"
                onClick={e => e.stopPropagation()}
              >
                {/* Drawer Header */}
                <div className="p-5 border-b border-border bg-muted/30 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-full bg-primary" />
                      <h2 className="text-lg font-bold text-foreground">
                        {selectedFunnelStep} Stage Leads
                      </h2>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-primary/10 text-primary font-mono font-bold">
                        {funnelLeads.length}
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={handleExportFunnelCsv}
                        disabled={funnelLeads.length === 0}
                        className="px-2.5 py-1.5 rounded-md bg-card hover:bg-muted border border-border text-xs font-semibold text-foreground flex items-center gap-1.5 transition-colors disabled:opacity-40 cursor-pointer shadow-xs"
                        title="Export this stage's leads to CSV"
                      >
                        <Download size={13} className="text-primary" />
                        <span>Export CSV</span>
                      </button>
                      <button 
                        type="button"
                        onClick={() => {
                          setSelectedFunnelStep(null);
                          setFunnelSearch("");
                        }} 
                        className="p-1.5 bg-card border border-border rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors shadow-xs cursor-pointer flex items-center gap-1.5"
                        title="Close drawer (Esc)"
                      >
                        <kbd className="hidden sm:inline-block text-[10px] font-mono px-1 py-0.2 rounded bg-muted border border-border text-muted-foreground">Esc</kbd>
                        <X size={15} />
                      </button>
                    </div>
                  </div>

                  <p className="text-xs text-muted-foreground leading-relaxed">
                    {STAGE_DESCRIPTIONS[selectedFunnelStep] || "Showing leads currently recorded at this stage in your active funnel."}
                  </p>
                </div>

                {/* In-Drawer Search Bar */}
                <div className="p-3 border-b border-border bg-background/60 flex items-center gap-2">
                  <div className="relative flex-1">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                    <input
                      type="text"
                      value={funnelSearch}
                      onChange={(e) => setFunnelSearch(e.target.value)}
                      placeholder="Search leads by name, title, company..."
                      className="w-full bg-card border border-border rounded-lg pl-8 pr-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-primary/50"
                    />
                    {funnelSearch && (
                      <button
                        type="button"
                        onClick={() => setFunnelSearch("")}
                        className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground text-xs cursor-pointer"
                      >
                        <X size={12} />
                      </button>
                    )}
                  </div>
                  <span className="text-[11px] text-muted-foreground whitespace-nowrap px-1">
                    {filteredFunnelLeads.length} of {funnelLeads.length}
                  </span>
                </div>
                
                {/* Leads Scroll Area */}
                <div className="flex-1 overflow-y-auto p-4 space-y-3">
                  {isFunnelLoading ? (
                    Array.from({ length: 5 }).map((_, i) => (
                      <div key={i} className="p-3.5 rounded-lg border border-border bg-background/50 flex items-center gap-3 animate-pulse">
                        <div className="w-9 h-9 rounded-full bg-muted flex-shrink-0" />
                        <div className="space-y-1.5 flex-1">
                          <div className="h-3.5 bg-muted rounded w-1/3" />
                          <div className="h-3 bg-muted rounded w-1/2" />
                        </div>
                      </div>
                    ))
                  ) : funnelError ? (
                    <div className="p-4 rounded-lg bg-destructive/10 border border-destructive/20 text-center space-y-2">
                      <div className="text-xs text-destructive font-semibold flex items-center justify-center gap-1.5">
                        <AlertTriangle size={14} /> Failed to load leads for {selectedFunnelStep}
                      </div>
                      <p className="text-[11px] text-muted-foreground">{funnelError}</p>
                      <button
                        type="button"
                        onClick={() => setFunnelFetchTrigger(t => t + 1)}
                        className="px-3 py-1 bg-destructive/20 text-destructive text-xs font-bold rounded-md hover:bg-destructive/30 transition-colors inline-flex items-center gap-1 cursor-pointer"
                      >
                        <RefreshCw size={12} /> Retry Fetch
                      </button>
                    </div>
                  ) : filteredFunnelLeads.length > 0 ? (
                    filteredFunnelLeads.map((lead, i) => (
                      <div 
                        key={lead.id || i} 
                        className="p-3.5 rounded-lg border border-border bg-card hover:border-primary/40 hover:bg-muted/30 transition-colors flex items-center justify-between group shadow-xs"
                      >
                        <div className="flex items-center gap-3 min-w-0 flex-1">
                          <div className="w-9 h-9 rounded-full bg-primary/10 text-primary border border-primary/20 flex items-center justify-center font-bold text-xs shrink-0">
                            {(lead.name || "?").charAt(0).toUpperCase()}
                          </div>
                          <div className="min-w-0 flex-1">
                            <p className="text-xs font-bold text-foreground group-hover:text-primary transition-colors truncate">
                              {lead.name}
                            </p>
                            <p className="text-[11px] text-muted-foreground truncate">
                              {lead.title}{lead.title && lead.company ? ' · ' : ''}{lead.company}
                              {lead.email ? ` · ${lead.email}` : ''}
                            </p>
                          </div>
                        </div>

                        <div className="flex items-center gap-1.5 shrink-0 opacity-80 group-hover:opacity-100 transition-opacity">
                          {lead.linkedin_url && (
                            <a
                              href={lead.linkedin_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="p-1.5 rounded-md bg-blue-500/10 hover:bg-blue-500/20 text-blue-600 dark:text-blue-400 text-[10px] cursor-pointer flex items-center gap-1"
                              title="Open LinkedIn Profile"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <ExternalLink size={12} />
                            </a>
                          )}
                          <button
                            type="button"
                            onClick={() => {
                              navigator.clipboard.writeText(lead.id || '');
                              setCopiedLeadId(lead.id);
                              toast.success(`Copied ID for ${lead.name}`);
                              setTimeout(() => setCopiedLeadId(null), 2000);
                            }}
                            className="p-1.5 rounded-md bg-muted/60 hover:bg-muted text-muted-foreground hover:text-foreground text-[10px] cursor-pointer"
                            title="Copy Lead ID"
                          >
                            {copiedLeadId === lead.id ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              navigate('/elein/leads');
                            }}
                            className="p-1.5 rounded-md bg-primary/10 hover:bg-primary/20 text-primary text-[10px] cursor-pointer"
                            title="View in Leads Hub"
                          >
                            <Users size={12} />
                          </button>
                        </div>
                      </div>
                    ))
                  ) : funnelSearch ? (
                    <div className="text-center py-12 text-xs text-muted-foreground space-y-1">
                      <p>No leads in this stage matched "{funnelSearch}"</p>
                      <button
                        type="button"
                        onClick={() => setFunnelSearch("")}
                        className="text-primary hover:underline font-semibold cursor-pointer"
                      >
                        Clear search
                      </button>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center justify-center text-center py-16 text-muted-foreground text-xs space-y-2">
                      <Users size={28} className="opacity-40" />
                      <p className="font-semibold text-foreground">No leads found in {selectedFunnelStep}</p>
                      <p className="text-[11px] max-w-xs">
                        Leads will appear here dynamically as sequences execute and transitions occur.
                      </p>
                    </div>
                  )}
                </div>
              </motion.div>
            </motion.div>
          )}


        </AnimatePresence>

      </div>
    </>
  )
}

export { formatKpiValue }
