import { useHRTreeStore } from "@campaigns/eiTreeStore";
import useSWR from "swr"
import { fetcher, fetchWithAuth } from "@/lib/apiClient"
import { toast } from "sonner"
import { useState, useEffect, useRef, useMemo, useCallback } from "react"
import { motion, AnimatePresence } from "motion/react"
import { useNavigate, useSearchParams } from "react-router-dom"
import { 
  Plus, Search, Play, Pause,
  Trash2, ChevronLeft, ChevronRight, BarChart2, Users,
  MoreVertical, Settings,
  Briefcase, Link as LinkIcon, Info, X, Loader2,
  Copy, CheckSquare, Square,
  ArrowUpDown, AlertCircle, Award,
  Database, Sparkles, Cpu, Layers, CheckCircle2,
  Zap, Clock, Compass, RefreshCw, SlidersHorizontal, TrendingUp, Bot
} from "lucide-react"

import { NumberTicker } from "@/components/ui/number-ticker"
import { CampaignPreflightModal } from "./CampaignPreflightModal"
import { CampaignROICertificateModal } from "@/components/campaigns/CampaignROICertificateModal"
import { PreWarmStudioModal } from "@/components/campaigns/PreWarmStudioModal"
import { BanditOptimizerStudioModal } from "@/components/campaigns/BanditOptimizerStudioModal"
import { EventMultimodalStudioModal } from "@/components/campaigns/EventMultimodalStudioModal"
import { AbmMultithreadStudioModal } from "@/components/campaigns/AbmMultithreadStudioModal"
import { OmnichannelRetargetingStudioModal } from "@/components/campaigns/OmnichannelRetargetingStudioModal"
import { BoomerangRevivalStudioModal } from "@/components/campaigns/BoomerangRevivalStudioModal"
import { SendTimeOptimizationStudioModal } from "@/components/campaigns/SendTimeOptimizationStudioModal"
import { DeliverabilityStudioModal } from "@/components/campaigns/DeliverabilityStudioModal"
import { ReplySentimentStudioModal } from "@/components/campaigns/ReplySentimentStudioModal"
import { DisplacementStudioModal } from "@/components/campaigns/DisplacementStudioModal"
import { CalendarConciergeStudioModal } from "@/components/campaigns/CalendarConciergeStudioModal"
import { usePaywall } from "@/contexts/PaywallContext"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { StatusPill } from "@/components/StatusPill"
import { TableViewOptions, type TableDensity, type TableColumnDef } from "@/components/tables/TableViewOptions"
import { cn } from "@/lib/utils"

const STATUS_CONFIG: Record<string, any> = {
  ACTIVE: { label: "Active", dot: "bg-success", text: "text-success", badgeBg: "bg-success/10 border-success/20" },
  PAUSED: { label: "Paused", dot: "bg-warning", text: "text-warning", badgeBg: "bg-warning/10 border-warning/20" },
  DRAFT: { label: "Draft", dot: "bg-muted-foreground", text: "text-muted-foreground", badgeBg: "bg-muted border-border/50" },
  COMPLETED: { label: "Completed", dot: "bg-indigo-500", text: "text-indigo-600 dark:text-indigo-400", badgeBg: "bg-indigo-500/10 border-indigo-500/20" },
}

export interface Campaign {
  id: string
  name: string
  description?: string
  status: "ACTIVE" | "PAUSED" | "DRAFT" | "COMPLETED" | string
  sent?: number
  accepted?: number
  replies?: number
  leads_total?: number
  leads_running?: number
  senders?: any[]
  leads_pending?: number
  created_at?: string
  leads_completed?: number
  conversion_rate?: number
}

function EmptyCampaignCard({ id, icon: Icon, title, desc, onSelect }: any) {
  return (
    <button 
      type="button"
      className="p-7 md:p-8 rounded-lg border border-border bg-card hover:border-foreground/30 hover:bg-card/90 hover:shadow-lg transition-all text-left flex flex-col justify-between group cursor-pointer min-h-[210px] w-full" 
      onClick={() => onSelect(id)}
    >
      <div>
        <div className="w-11 h-11 rounded-lg bg-muted/60 border border-border/50 flex items-center justify-center mb-5 group-hover:border-primary/40 group-hover:bg-primary/5 transition-all">
          {Icon && <Icon size={22} className="text-muted-foreground group-hover:text-primary transition-colors" />}
        </div>
        <h3 className="text-base font-semibold text-foreground mb-2 group-hover:text-primary transition-colors">{title}</h3>
        <p className="text-xs text-muted-foreground leading-relaxed">{desc}</p>
      </div>
      <div className="pt-6 flex items-center gap-1 text-xs font-medium text-muted-foreground group-hover:text-foreground transition-colors">
        <span>Start</span>
        <ChevronRight size={13} className="transition-transform group-hover:translate-x-0.5" />
      </div>
    </button>
  );
}

const SEQUENCE_PLAYBOOKS = [
  {
    id: 'founder',
    title: 'Founder-to-Founder',
    target: 'Early-stage CEOs & Technical Co-Founders',
    avgReplyRate: '18.4%',
    nodes: [
      { step: '01', type: 'ACTION', title: 'Personalized Connection Note', desc: 'Synthesizes recent company news, tech stack and shared mutuals.' },
      { step: '02', type: 'DELAY', title: 'Smart Delay • 48 Hours', desc: 'Monitors acceptance & visits profile without sending push notifications.' },
      { step: '03', type: 'ACTION', title: 'Curiosity-Driven Follow-Up', desc: 'Shares 1 high-leverage peer insight without hard selling.' },
      { step: '04', type: 'AI_AGENT', title: 'Sentiment Response Classifier', desc: 'Tags interested replies and auto-books to Google Calendar.' },
    ]
  },
  {
    id: 'abm',
    title: 'Enterprise Multithreading',
    target: 'VP Sales, RevOps & Head of Pipeline',
    avgReplyRate: '21.0%',
    nodes: [
      { step: '01', type: 'ACTION', title: 'Multi-Account Warm Visit', desc: 'Two team accounts view target profiles 12 hours prior to outreach.' },
      { step: '02', type: 'ACTION', title: 'Connection with Custom Metric', desc: 'Calculates prospect department leakage using public headcount data.' },
      { step: '03', type: 'DELAY', title: 'Dynamic Delay • 72 Hours', desc: 'Skips weekends and local holidays in recipient timezone.' },
      { step: '04', type: 'ACTION', title: 'Direct Case-Study Audio Note', desc: 'Generates conversational dynamic voice drop tailored to title.' },
    ]
  },
  {
    id: 'talent',
    title: 'Elite Executive Headhunting',
    target: 'Principal Engineers & Engineering Directors',
    avgReplyRate: '28.5%',
    nodes: [
      { step: '01', type: 'ACTION', title: 'Technical Thesis InMail / Invite', desc: 'Mentions open-source contributions and specific architecture challenges.' },
      { step: '02', type: 'DELAY', title: 'Wait for Inactivity • 3 Days', desc: 'Auto-checks if prospect changed jobs or recently posted on LinkedIn.' },
      { step: '03', type: 'ACTION', title: 'Founder Direct Forward Note', desc: 'Presents compensation benchmark and immediate technical roadmap.' },
      { step: '04', type: 'AI_AGENT', title: 'Candidate Concierge', desc: 'Answers questions about team culture and equity instantly.' },
    ]
  }
];

const DEMO_CAMPAIGNS: Campaign[] = [
  {
    id: "demo-saas-founders",
    name: "Tier-1 SaaS Founders & AI Execs [Demo]",
    description: "High-touch multi-channel sequence targeting seed & Series-A technical founders.",
    status: "ACTIVE",
    leads_total: 420,
    leads_running: 68,
    leads_pending: 280,
    leads_completed: 72,
    replies: 24,
    conversion_rate: 0.184,
    senders: [{ id: "sender-1", name: "Alex Chen (Founder)" }, { id: "sender-2", name: "Sarah Miller (VP Growth)" }],
    created_at: new Date(Date.now() - 86400000 * 3).toISOString(),
  },
  {
    id: "demo-yc-alumni",
    name: "Y Combinator W24 Alumni Outreach [Demo]",
    description: "Warm hyper-personalized intro leveraging cohort batch synergy.",
    status: "ACTIVE",
    leads_total: 185,
    leads_running: 34,
    leads_pending: 110,
    leads_completed: 41,
    replies: 12,
    conversion_rate: 0.210,
    senders: [{ id: "sender-1", name: "Alex Chen (Founder)" }],
    created_at: new Date(Date.now() - 86400000 * 5).toISOString(),
  },
  {
    id: "demo-enterprise-revops",
    name: "Enterprise VP RevOps & Pipeline Architecture [Demo]",
    description: "Account-based multithreaded playbook targeting $50M+ ARR companies.",
    status: "PAUSED",
    leads_total: 650,
    leads_running: 0,
    leads_pending: 520,
    leads_completed: 130,
    replies: 45,
    conversion_rate: 0.148,
    senders: [{ id: "sender-2", name: "Sarah Miller (VP Growth)" }],
    created_at: new Date(Date.now() - 86400000 * 10).toISOString(),
  },
];

const CAMPAIGN_COLUMNS: TableColumnDef[] = [
  { id: 'name', label: 'Campaign Name', locked: true },
  { id: 'status', label: 'Status' },
  { id: 'enrolled', label: 'Enrolled', responsiveBreakpoint: 'sm' },
  { id: 'connected', label: 'Connected', responsiveBreakpoint: 'md' },
  { id: 'acceptance', label: 'Acceptance Rate', responsiveBreakpoint: 'lg' },
  { id: 'replied', label: 'Replied', responsiveBreakpoint: 'lg' },
  { id: 'replyRate', label: 'Reply Rate', responsiveBreakpoint: 'xl' },
  { id: 'booked', label: 'Booked', responsiveBreakpoint: 'xl' },
  { id: 'senders', label: 'Senders', responsiveBreakpoint: '2xl' },
  { id: 'actions', label: 'Actions', locked: true },
]

const DEFAULT_CAMPAIGN_COLUMNS = ['status', 'enrolled', 'connected', 'acceptance', 'replied', 'replyRate', 'booked', 'senders']

export function EleInCampaigns() {
  const navigate = useNavigate()
  const resetTree = useHRTreeStore(state => state.reset)

  // ─── Table View & Density State ───
  const [density, setDensity] = useState<TableDensity>(() => {
    try {
      const saved = localStorage.getItem('elein_campaigns_density')
      if (saved === 'compact' || saved === 'standard' || saved === 'comfortable') return saved
    } catch {}
    return 'standard'
  })

  const [visibleColumns, setVisibleColumns] = useState<string[]>(() => {
    try {
      const saved = localStorage.getItem('elein_campaigns_columns')
      if (saved) return JSON.parse(saved)
    } catch {}
    return DEFAULT_CAMPAIGN_COLUMNS
  })

  const handleDensityChange = (newDensity: TableDensity) => {
    setDensity(newDensity)
    try {
      localStorage.setItem('elein_campaigns_density', newDensity)
    } catch {}
  }

  const handleToggleColumn = (colId: string) => {
    setVisibleColumns(prev => {
      const next = prev.includes(colId) ? prev.filter(c => c !== colId) : [...prev, colId]
      try {
        localStorage.setItem('elein_campaigns_columns', JSON.stringify(next))
      } catch {}
      return next
    })
  }

  const handleResetViewOptions = () => {
    setDensity('standard')
    setVisibleColumns(DEFAULT_CAMPAIGN_COLUMNS)
    try {
      localStorage.setItem('elein_campaigns_density', 'standard')
      localStorage.setItem('elein_campaigns_columns', JSON.stringify(DEFAULT_CAMPAIGN_COLUMNS))
    } catch {}
  }

  const densityPadding = density === 'compact' ? 'py-2' : density === 'comfortable' ? 'py-5' : 'py-3.5'
  const densityText = density === 'comfortable' ? 'text-sm' : 'text-xs'

  // ─── Filter & Search State ───
  const [search, setSearch] = useState("")
  const [debouncedSearch, setDebouncedSearch] = useState("")
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'ACTIVE' | 'PAUSED' | 'DRAFT' | 'COMPLETED'>('ALL')
  const [sortBy, setSortBy] = useState<'created_desc' | 'created_asc' | 'leads_desc' | 'conversion_desc' | 'name_asc'>('created_desc')
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 15

  // 200ms debounced search to eliminate keystroke jank
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search)
      setPage(1)
    }, 200)
    return () => clearTimeout(timer)
  }, [search])

  // ─── Draft State ───
  const [draftExists, setDraftExists] = useState(false)
  const [draftTime, setDraftTime] = useState("")
  
  // ─── Multi-Select Batch State ───
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [isBatchOperating, setIsBatchOperating] = useState(false)
  const [batchActionType, setBatchActionType] = useState<string | null>(null)

  // ─── Duplication & Optimistic Toggle State (EPF Phase 3) ───
  const [duplicatingId, setDuplicatingId] = useState<string | null>(null)
  const [activeTogglingIds, setActiveTogglingIds] = useState<Set<string>>(new Set())
  const inFlightTogglesRef = useRef<Map<string, { controller: AbortController; timestamp: number }>>(new Map())
  const [isDemoFleetSeeded, setIsDemoFleetSeeded] = useState(() => {
    try {
      return sessionStorage.getItem('elein_demo_fleet_active') === 'true';
    } catch {
      return false;
    }
  })
  const [activePlaybookTab, setActivePlaybookTab] = useState<'founder' | 'abm' | 'talent'>('founder')

  // ─── Modals State ───
  const [confirmModal, setConfirmModal] = useState<{isOpen: boolean, title: string, message: string, onConfirm: () => void} | null>(null)

  // Layer 2 Human Paranoia: Escape key dismissal for confirmation modal
  useEffect(() => {
    if (!confirmModal || !confirmModal.isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setConfirmModal(null);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [confirmModal?.isOpen]);

  // Layer 2 Human Paranoia: Escape key dismissal for batch selection
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && selectedIds.size > 0) {
        setSelectedIds(new Set())
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [selectedIds.size])
  const [preflightCampaign, setPreflightCampaign] = useState<{ id: string; name: string } | null>(null)
  const [selectedCertCampaign, setSelectedCertCampaign] = useState<{ id: string; name: string } | null>(null)
  const [banditCampaign, setBanditCampaign] = useState<{ id: string; name: string } | null>(null)
  const [showPreWarmModal, setShowPreWarmModal] = useState(false)
  const [showEventModal, setShowEventModal] = useState(false)
  const [showAbmModal, setShowAbmModal] = useState(false)
  const [showOmnichannelModal, setShowOmnichannelModal] = useState(false)
  const [showBoomerangModal, setShowBoomerangModal] = useState(false)
  const [showStoModal, setShowStoModal] = useState(false)
  const [showDeliverabilityModal, setShowDeliverabilityModal] = useState(false)
  const [showSentimentModal, setShowSentimentModal] = useState(false)
  const [showDisplacementModal, setShowDisplacementModal] = useState(false)
  const [showCalendarModal, setShowCalendarModal] = useState(false)
  const [showGrowthHub, setShowGrowthHub] = useState(false)
  const [searchParams, setSearchParams] = useSearchParams()
  const [openRowMenuId, setOpenRowMenuId] = useState<string | null>(null)
  const rowMenuRef = useRef<HTMLDivElement>(null)

  const openStudioByKey = useCallback((studioKey: string | null, openTools = false) => {
    if (openTools) setShowGrowthHub(true)
    if (!studioKey) return
    switch (studioKey) {
      case "sto":
        setShowStoModal(true)
        break
      case "calendar":
        setShowCalendarModal(true)
        break
      case "bandit":
        setBanditCampaign({ id: "global-optimizer", name: "Global Multi-Armed Bandit Radar" })
        break
      case "sentiment":
        setShowSentimentModal(true)
        break
      case "deliverability":
        setShowDeliverabilityModal(true)
        break
      case "prewarm":
        setShowPreWarmModal(true)
        break
      case "displacement":
        setShowDisplacementModal(true)
        break
      case "boomerang":
        setShowBoomerangModal(true)
        break
      case "event":
        setShowEventModal(true)
        break
      case "abm":
        setShowAbmModal(true)
        break
      case "retargeting":
        setShowOmnichannelModal(true)
        break
      case "growth":
        setShowGrowthHub(true)
        break
    }
  }, [])

  // Auto-open Growth Tools or AI Studios if navigation linked here with ?tools=true or ?studio=<key>
  useEffect(() => {
    const toolsParam = searchParams.get('tools') === 'true'
    const studioParam = searchParams.get('studio')
    if (toolsParam || studioParam) {
      openStudioByKey(studioParam, toolsParam)
      const nextParams = new URLSearchParams(searchParams)
      nextParams.delete('tools')
      nextParams.delete('studio')
      setSearchParams(nextParams, { replace: true })
    }
  }, [searchParams, setSearchParams, openStudioByKey])

  // Listen for instant CommandPalette open-ai-studio events
  useEffect(() => {
    const handleStudioEvent = (e: Event) => {
      const customEvent = e as CustomEvent<{ studio?: string; tools?: boolean }>
      if (customEvent.detail) {
        openStudioByKey(customEvent.detail.studio || null, !!customEvent.detail.tools)
      }
    }
    window.addEventListener('open-ai-studio', handleStudioEvent)
    return () => window.removeEventListener('open-ai-studio', handleStudioEvent)
  }, [openStudioByKey])

  // Close row actions menu on outside click
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (rowMenuRef.current && !rowMenuRef.current.contains(event.target as Node)) {
        setOpenRowMenuId(null)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // ─── Billing & SWR Fetches ───
  const { openPaywall } = usePaywall()
  const { data: billingData } = useSWR<{ tier?: string }>(
    '/api/elein/workspaces/billing',
    fetcher
  )
  const rawTier = (billingData?.tier || 'FREE').toUpperCase()
  const isEnterprise = rawTier === 'ENTERPRISE'
  const isAgency = rawTier === 'AGENCY'
  const isPro = rawTier === 'PRO' || rawTier === 'GROWTH' || isAgency || isEnterprise
  const maxActiveCampaigns = isEnterprise ? 100 : isAgency ? 50 : isPro ? 20 : 1
  const tier = rawTier

  const { data: dashboardData, mutate } = useSWR("/api/elein/dashboard/stats", fetcher)
  const campaigns: Campaign[] = useMemo(() => {
    let list: Campaign[] = [];
    if (Array.isArray(dashboardData?.recent_campaigns)) list = dashboardData.recent_campaigns;
    else if (Array.isArray(dashboardData?.campaigns)) list = dashboardData.campaigns;

    if (list.length === 0 && isDemoFleetSeeded) {
      return DEMO_CAMPAIGNS;
    }
    return list;
  }, [dashboardData, isDemoFleetSeeded]);

  const handleSeedDemoFleet = useCallback(() => {
    setIsDemoFleetSeeded(true);
    try { sessionStorage.setItem('elein_demo_fleet_active', 'true'); } catch {}
    toast.success("Sandbox demo fleet active!", {
      description: "3 pre-configured campaigns loaded into your workspace view. You can test density modes, column visibility, and filters.",
      duration: 4500,
    });
  }, []);

  const handleClearDemoFleet = useCallback(() => {
    setIsDemoFleetSeeded(false);
    try { sessionStorage.removeItem('elein_demo_fleet_active'); } catch {}
    toast.info("Demo fleet cleared. Restored clean workspace.");
  }, []);

  const { data: masterViewStats } = useSWR(
    "/api/master-view/stats",
    (url: string) => fetchWithAuth(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    }).then(r => r.ok ? r.json() : null),
    { refreshInterval: 30000, keepPreviousData: true }
  )

  const scorecardMap = useMemo(() => {
    const map = new Map<string, any>()
    const list = masterViewStats?.multi_campaign_data
    if (Array.isArray(list)) {
      list.forEach((item: any) => {
        if (item && item.id) map.set(item.id, item)
      })
    }
    return map
  }, [masterViewStats])
  
  const { data: workerStatus } = useSWR('/api/elein/worker/status', fetcher, { refreshInterval: 30000 })

  // Check unsaved drafts
  useEffect(() => {
    const draftStr = localStorage.getItem("elein_unsaved_draft")
    if (draftStr) {
      try {
        const draft = JSON.parse(draftStr)
        if (draft.nodes && draft.nodes.length > 0) {
          setDraftExists(true)
          setDraftTime(new Date(draft.timestamp).toLocaleString())
        }
      } catch(e) {
        console.error('Draft parse error:', e)
      }
    }
  }, [])

  // ─── Status Counts ───
  const statusCounts = useMemo(() => {
    const counts = { ALL: campaigns.length, ACTIVE: 0, PAUSED: 0, DRAFT: 0, COMPLETED: 0 };
    campaigns.forEach(c => {
      if (c.status === 'ACTIVE') counts.ACTIVE++;
      else if (c.status === 'PAUSED') counts.PAUSED++;
      else if (c.status === 'COMPLETED') counts.COMPLETED++;
      else counts.DRAFT++;
    });
    return counts;
  }, [campaigns]);

  // ─── Fleet Statistics Rollup ───
  const fleetStats = useMemo(() => {
    let totalLeads = 0;
    let totalRunning = 0;
    let totalPending = 0;
    let totalCompleted = 0;
    let totalReplies = 0;
    const uniqueSenders = new Set<string>();
    let weightedConvSum = 0;
    let totalWithConv = 0;
    let activeWithZeroSenders = 0;

    campaigns.forEach(c => {
      const lTotal = c.leads_total || 0;
      totalLeads += lTotal;
      totalRunning += c.leads_running || 0;
      totalPending += c.leads_pending || 0;
      totalCompleted += c.leads_completed || 0;
      totalReplies += c.replies || 0;

      if (c.senders && Array.isArray(c.senders)) {
        c.senders.forEach((s: any) => {
          if (s.id || s.name) uniqueSenders.add(s.id || s.name);
        });
      }

      if (c.status === 'ACTIVE' && (!c.senders || c.senders.length === 0)) {
        activeWithZeroSenders++;
      }

      if (c.conversion_rate && c.conversion_rate > 0) {
        weightedConvSum += c.conversion_rate;
        totalWithConv++;
      }
    });

    const avgConversion = totalWithConv > 0 ? (weightedConvSum / totalWithConv) * 100 : 0;

    return {
      totalLeads,
      totalRunning,
      totalPending,
      totalCompleted,
      totalReplies,
      uniqueSenderCount: uniqueSenders.size,
      avgConversion: avgConversion.toFixed(1),
      activeWithZeroSenders
    };
  }, [campaigns]);

  // ─── Filter & Sort ───
  const filtered = useMemo(() => {
    const q = debouncedSearch.trim().toLowerCase();
    const result = campaigns.filter(c => {
      const matchesSearch = 
        !q ||
        (c.name || "").toLowerCase().includes(q) ||
        (c.description || "").toLowerCase().includes(q);
      const matchesStatus = statusFilter === 'ALL' || c.status === statusFilter;
      return matchesSearch && matchesStatus;
    });

    result.sort((a, b) => {
      if (sortBy === 'created_desc') {
        return new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime();
      }
      if (sortBy === 'created_asc') {
        return new Date(a.created_at || 0).getTime() - new Date(b.created_at || 0).getTime();
      }
      if (sortBy === 'leads_desc') {
        return (b.leads_total || 0) - (a.leads_total || 0);
      }
      if (sortBy === 'conversion_desc') {
        return (b.conversion_rate || 0) - (a.conversion_rate || 0);
      }
      if (sortBy === 'name_asc') {
        return (a.name || "").localeCompare(b.name || "");
      }
      return 0;
    });

    return result;
  }, [campaigns, debouncedSearch, statusFilter, sortBy]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const paginatedCampaigns = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return filtered.slice(start, start + PAGE_SIZE);
  }, [filtered, page]);

  // Layer 2 Human Paranoia: Escape key resets filters when search yields zero matches
  useEffect(() => {
    if (filtered.length === 0 && (search || statusFilter !== 'ALL')) {
      const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === "Escape") {
          setSearch("");
          setStatusFilter("ALL");
          setPage(1);
        }
      };
      window.addEventListener("keydown", handleKeyDown);
      return () => window.removeEventListener("keydown", handleKeyDown);
    }
  }, [filtered.length, search, statusFilter]);

  // ─── Single Campaign Toggle (Optimistic Mutation + Immediate Rollback - EPF Phase 3) ───
  const executeToggleStatus = useCallback(async (id: string, action: 'activate' | 'pause') => {
    const currentCampaign = campaigns.find(c => c.id === id);
    if (!currentCampaign) return;

    const now = Date.now();
    const existingFlight = inFlightTogglesRef.current.get(id);

    // Layer 2 Paranoia: Rapid double-click debounce gate (350ms)
    if (existingFlight && (now - existingFlight.timestamp) < 350) {
      return;
    }

    if (existingFlight) {
      existingFlight.controller.abort();
    }

    const controller = new AbortController();
    inFlightTogglesRef.current.set(id, { controller, timestamp: now });
    setActiveTogglingIds(prev => new Set(prev).add(id));

    const targetStatus = action === 'activate' ? 'ACTIVE' : 'PAUSED';
    const previousStatus = currentCampaign.status;

    const optimisticMutator = (currentData: any) => {
      if (!currentData) return currentData;
      const updateList = (list: any[]) =>
        Array.isArray(list)
          ? list.map(c => c.id === id ? { ...c, status: targetStatus } : c)
          : list;

      return {
        ...currentData,
        recent_campaigns: updateList(currentData.recent_campaigns),
        campaigns: updateList(currentData.campaigns),
      };
    };

    try {
      await mutate(
        async (currentCache: any) => {
          const res = await fetchWithAuth(`/api/elein/campaigns/${id}/${action}`, {
            method: 'PATCH',
            signal: controller.signal,
          });

          if (!res.ok) {
            let errDetail = `Server returned ${res.status}`;
            try {
              const errJson = await res.json();
              errDetail = errJson.detail || errDetail;
            } catch {
              const text = await res.text();
              if (text) errDetail = text;
            }
            throw new Error(errDetail);
          }

          const updatedServerCampaign = await res.json().catch(() => null);
          const updateConfirmed = (list: any[]) =>
            Array.isArray(list)
              ? list.map(c => c.id === id ? { ...c, status: targetStatus, ...(updatedServerCampaign || {}) } : c)
              : list;

          return {
            ...currentCache,
            recent_campaigns: updateConfirmed(currentCache?.recent_campaigns),
            campaigns: updateConfirmed(currentCache?.campaigns),
          };
        },
        {
          optimisticData: optimisticMutator(dashboardData),
          rollbackOnError: true,
          populateCache: true,
          revalidate: false,
        }
      );

      toast.success(
        action === 'activate' ? "Campaign activated — scheduler is live" : "Campaign paused — timers frozen safely",
        { duration: 2500 }
      );
    } catch (err: any) {
      if (err.name === 'AbortError') return;

      console.error(`[OptimisticToggle Error] ${id}:`, err);
      const msg = err.message || "Failed to update campaign";
      if (msg.includes("exceeds limit") || msg.includes("Free Tier")) {
        openPaywall({ featureName: "Active Campaigns Limit" });
      } else if (msg === "no_active_senders") {
        toast.error("Cannot activate: No active LinkedIn senders assigned to this campaign.");
        return;
      }

      toast.error(`Failed to ${action} "${currentCampaign.name}". Reverted to ${previousStatus}.`, {
        description: msg.length > 80 ? `${msg.slice(0, 80)}...` : msg,
        duration: 7000,
        action: {
          label: "Retry",
          onClick: () => executeToggleStatus(id, action),
        },
      });
    } finally {
      if (inFlightTogglesRef.current.get(id)?.controller === controller) {
        inFlightTogglesRef.current.delete(id);
        setActiveTogglingIds(prev => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        });
      }
    }
  }, [campaigns, dashboardData, mutate, openPaywall]);
  
  const toggleStatus = async (id: string) => {
    if (activeTogglingIds.has(id) || isBatchOperating) return;
    const campaign = campaigns.find(c => c.id === id);
    if (!campaign) return;
    const action = campaign.status === 'ACTIVE' ? 'pause' : 'activate';

    if (action === 'pause') {
      await executeToggleStatus(id, 'pause');
      return;
    }

    if (statusCounts.ACTIVE >= maxActiveCampaigns) {
      if (!isPro) {
        openPaywall({ featureName: "Active Campaigns Limit", minTier: "PRO" });
        toast.info("Free plan is limited to 1 active campaign. Upgrade to Growth Pro to run up to 20 campaigns simultaneously.");
      } else if (rawTier === 'PRO' || rawTier === 'GROWTH') {
        openPaywall({ featureName: "Agency Active Campaigns", minTier: "AGENCY" });
        toast.info("Growth Pro is limited to 20 active campaigns. Upgrade to Agency Tier to run up to 50 campaigns simultaneously.");
      } else if (isAgency) {
        openPaywall({ featureName: "Enterprise Active Campaigns", minTier: "ENTERPRISE" });
        toast.info("Agency plan is limited to 50 active campaigns. Upgrade to Enterprise to run up to 100 campaigns simultaneously.");
      } else {
        toast.error("Enterprise limit of 100 active campaigns reached. Contact your account manager for custom volume expansion.");
      }
      return;
    }

    setPreflightCampaign({ id: campaign.id, name: campaign.name });
  };

  // ─── 1-Click Duplicate Campaign (Layer 0 & Layer 1) ───
  const handleDuplicateCampaign = async (id: string, originalName: string) => {
    if (duplicatingId || isBatchOperating) return;
    setDuplicatingId(id);
    try {
      const detailRes = await fetchWithAuth(`/api/elein/campaigns/${id}/detail`);
      if (!detailRes.ok) throw new Error("Failed to fetch campaign architecture");
      const detail = await detailRes.json();

      // Paranoia Layer 0 & 1 (FLAW-FE-01): Support both { campaign: {...} } and direct detail object
      const origCamp = detail.campaign || detail || {};
      const newName = `${originalName} (Copy)`;

      // UI-08 Paranoia Layer 0 & 2: Explicitly preserve sender accounts and audience lead_list_id
      const senders = (Array.isArray(detail.accounts) && detail.accounts.length > 0)
        ? detail.accounts.map((a: any) => a.id || a.account_id).filter(Boolean)
        : (origCamp.senders || origCamp.sender_account_ids_json || detail.sender_account_ids || []);
      const leadListId = origCamp.lead_list_id || origCamp.metadata?.lead_list_id || detail.lead_list_id || detail.metadata?.lead_list_id || null;
      const schedule = origCamp.schedule || origCamp.metadata?.schedule || detail.metadata?.schedule || null;
      const metadata = {
        ...(origCamp.metadata || detail.metadata || { stop_on_reply: true }),
        ...(leadListId ? { lead_list_id: leadListId } : {})
      };

      const createRes = await fetchWithAuth('/api/elein/campaigns', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newName,
          nodes: detail.nodes || origCamp.nodes || [],
          edges: detail.edges || origCamp.edges || [],
          senders: senders,
          lead_list_id: leadListId,
          timezone: origCamp.timezone || detail.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone,
          status: "DRAFT",
          schedule: schedule,
          metadata: metadata
        })
      });

      if (!createRes.ok) {
        const text = await createRes.text();
        throw new Error(text || "Failed to clone campaign");
      }

      const created = await createRes.json();
      toast.success(`Cloned "${originalName}" into "${newName}"!`);
      mutate();

      // Open new campaign option
      if (created.campaign_id || created.id) {
        const newId = created.campaign_id || created.id;
        toast.info("Click to inspect your new cloned campaign", {
          action: {
            label: "Open Campaign",
            onClick: () => navigate(`/elein/campaigns/${newId}`)
          }
        });
      }
    } catch (e: any) {
      toast.error(e.message || "Failed to duplicate campaign");
    } finally {
      setDuplicatingId(null);
    }
  }

  // ─── Single Delete ───
  const remove = async (id: string) => {
    const campaign = campaigns.find(c => c.id === id);
    setConfirmModal({
      isOpen: true,
      title: "Delete Campaign",
      message: `Are you sure you want to delete the campaign "${campaign?.name || 'Unknown'}"? This cannot be undone.`,
      onConfirm: async () => {
        setConfirmModal(null);
        try {
          const res = await fetchWithAuth(`/api/elein/campaigns/${id}`, { method: 'DELETE' });
          if (!res.ok) throw new Error("Failed to delete campaign");
          toast.success(`Campaign "${campaign?.name || 'Unknown'}" deleted`);
          setSelectedIds(prev => {
            const next = new Set(prev);
            next.delete(id);
            return next;
          });
          mutate();
        } catch (e: any) {
          toast.error(e.message || "Failed to delete campaign");
          mutate();
        }
      }
    });
  }

  // ─── Multi-Select Selection Handlers ───
  const isAllSelected = filtered.length > 0 && filtered.every(c => selectedIds.has(c.id));

  const handleToggleSelectAll = () => {
    if (isAllSelected) {
      setSelectedIds(prev => {
        const next = new Set(prev);
        filtered.forEach(c => next.delete(c.id));
        return next;
      });
    } else {
      setSelectedIds(prev => {
        const next = new Set(prev);
        filtered.forEach(c => next.add(c.id));
        return next;
      });
    }
  };

  const handleToggleSelectOne = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // ─── Batch Operations (Layer 0, 1 & 2 - UI-07 + EPF Phase 3 Optimistic Mutations) ───
  const handleBatchPause = async () => {
    if (selectedIds.size === 0 || isBatchOperating) return;

    const targets = Array.from(selectedIds).filter(id => {
      const camp = campaigns.find(c => c.id === id);
      return camp && camp.status === 'ACTIVE';
    });

    if (targets.length === 0) return;

    setIsBatchOperating(true);
    setBatchActionType("pause");

    const optimisticMutator = (currentData: any) => {
      if (!currentData) return currentData;
      const updateList = (list: any[]) =>
        Array.isArray(list)
          ? list.map(c => targets.includes(c.id) ? { ...c, status: 'PAUSED' } : c)
          : list;
      return {
        ...currentData,
        recent_campaigns: updateList(currentData.recent_campaigns),
        campaigns: updateList(currentData.campaigns),
      };
    };

    try {
      await mutate(
        async (currentCache: any) => {
          const results = await Promise.allSettled(
            targets.map(async (id) => {
              const res = await fetchWithAuth(`/api/elein/campaigns/${id}/pause`, { method: 'PATCH' });
              if (!res.ok) throw new Error("Failed to pause campaign");
              return id;
            })
          );
          const fulfilledIds = results
            .filter((r): r is PromiseFulfilledResult<string> => r.status === "fulfilled")
            .map(r => r.value);
          const failedCount = results.length - fulfilledIds.length;

          if (failedCount > 0) {
            toast.warning(`Paused ${fulfilledIds.length} campaigns; ${failedCount} failed to pause.`);
          } else {
            toast.success(`Paused ${fulfilledIds.length} campaign${fulfilledIds.length === 1 ? '' : 's'}`);
          }

          const updateList = (list: any[]) =>
            Array.isArray(list)
              ? list.map(c => fulfilledIds.includes(c.id) ? { ...c, status: 'PAUSED' } : c)
              : list;

          return {
            ...currentCache,
            recent_campaigns: updateList(currentCache?.recent_campaigns),
            campaigns: updateList(currentCache?.campaigns),
          };
        },
        {
          optimisticData: optimisticMutator(dashboardData),
          rollbackOnError: true,
          populateCache: true,
          revalidate: false,
        }
      );
    } catch (e: any) {
      toast.error(e?.message || "Encountered an error pausing campaigns. Reverted.");
    } finally {
      setIsBatchOperating(false);
      setBatchActionType(null);
    }
  };

  const handleBatchResume = async () => {
    if (selectedIds.size === 0 || isBatchOperating) return;

    // Quota pre-check (Layer 2 Paranoia)
    const candidates = Array.from(selectedIds).filter(id => {
      const c = campaigns.find(camp => camp.id === id);
      return c && c.status !== 'ACTIVE';
    });

    if ((statusCounts.ACTIVE + candidates.length) > maxActiveCampaigns) {
      openPaywall({ featureName: "Active Campaigns Limit" });
      toast.info(`Active campaign limit reached (${statusCounts.ACTIVE} active, max allowed ${maxActiveCampaigns}). Please upgrade your tier or pause inactive campaigns.`);
      return;
    }

    // Paranoia Layer 1 & 2 (AUDIT-07): Batch Preflight Safety Gate
    // Intercept campaigns with 0 senders or empty targets before dispatching
    const unreadyCampaigns: string[] = [];
    const validCandidates = candidates.filter(id => {
      const c = campaigns.find(camp => camp.id === id);
      if (!c) return false;
      const sendersCount = Array.isArray(c.senders) ? c.senders.length : 0;
      if (sendersCount === 0) {
        unreadyCampaigns.push(`"${c.name}"`);
        return false;
      }
      return true;
    });

    if (unreadyCampaigns.length > 0) {
      toast.error(
        `Preflight Safety Alert: ${unreadyCampaigns.length} campaign${unreadyCampaigns.length === 1 ? '' : 's'} (${unreadyCampaigns.slice(0, 3).join(", ")}${unreadyCampaigns.length > 3 ? '...' : ''}) have 0 senders assigned and cannot be launched. Please configure senders first.`
      );
      if (validCandidates.length === 0) {
        return;
      }
    }

    setIsBatchOperating(true);
    setBatchActionType("resume");

    const optimisticMutator = (currentData: any) => {
      if (!currentData) return currentData;
      const updateList = (list: any[]) =>
        Array.isArray(list)
          ? list.map(c => validCandidates.includes(c.id) ? { ...c, status: 'ACTIVE' } : c)
          : list;
      return {
        ...currentData,
        recent_campaigns: updateList(currentData.recent_campaigns),
        campaigns: updateList(currentData.campaigns),
      };
    };

    try {
      await mutate(
        async (currentCache: any) => {
          const results = await Promise.allSettled(
            validCandidates.map(async (id) => {
              const res = await fetchWithAuth(`/api/elein/campaigns/${id}/activate`, { method: 'PATCH' });
              if (!res.ok) throw new Error("Failed to activate campaign");
              return id;
            })
          );
          const fulfilledIds = results
            .filter((r): r is PromiseFulfilledResult<string> => r.status === "fulfilled")
            .map(r => r.value);
          const failedCount = results.length - fulfilledIds.length;

          if (fulfilledIds.length > 0) {
            toast.success(`Activated ${fulfilledIds.length} campaign${fulfilledIds.length === 1 ? '' : 's'}`);
          }
          if (failedCount > 0) {
            toast.warning(`${failedCount} campaign${failedCount === 1 ? '' : 's'} could not be activated.`);
          }

          const updateList = (list: any[]) =>
            Array.isArray(list)
              ? list.map(c => fulfilledIds.includes(c.id) ? { ...c, status: 'ACTIVE' } : c)
              : list;

          return {
            ...currentCache,
            recent_campaigns: updateList(currentCache?.recent_campaigns),
            campaigns: updateList(currentCache?.campaigns),
          };
        },
        {
          optimisticData: optimisticMutator(dashboardData),
          rollbackOnError: true,
          populateCache: true,
          revalidate: false,
        }
      );
    } catch (e: any) {
      toast.error(e?.message || "Encountered an error activating campaigns. Reverted.");
    } finally {
      setIsBatchOperating(false);
      setBatchActionType(null);
    }
  };

  const handleBatchDelete = () => {
    if (selectedIds.size === 0 || isBatchOperating) return;

    const count = selectedIds.size;
    const affectedLeads = Array.from(selectedIds).reduce((acc, id) => {
      const c = campaigns.find(camp => camp.id === id);
      return acc + (c?.leads_total || 0);
    }, 0);

    setConfirmModal({
      isOpen: true,
      title: `Delete ${count} Campaign${count > 1 ? 's' : ''}`,
      message: `Are you sure you want to permanently delete ${count} campaign${count > 1 ? 's' : ''}? This affects ${affectedLeads.toLocaleString()} total enrolled leads and cannot be undone.`,
      onConfirm: async () => {
        setConfirmModal(null);
        setIsBatchOperating(true);
        setBatchActionType("delete");

        const targets = Array.from(selectedIds);
        const results = await Promise.allSettled(
          targets.map(async (id) => {
            const res = await fetchWithAuth(`/api/elein/campaigns/${id}`, { method: 'DELETE' });
            if (!res.ok) throw new Error("Failed to delete campaign");
            return id;
          })
        );
        const deletedCount = results.filter(r => r.status === "fulfilled").length;

        toast.success(`Successfully deleted ${deletedCount} campaign${deletedCount === 1 ? '' : 's'}`);
        setSelectedIds(new Set());
        setIsBatchOperating(false);
        setBatchActionType(null);
        mutate();
      }
    });
  };

  return (
    <div className="max-w-[1240px] mx-auto p-6 sm:p-8 font-sans">
      {/* ─── HEADER COMMAND DECK ────────────────────────────────────────────── */}
      <div className="mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5 mb-1">
            <h1 className="text-xl font-semibold tracking-tight text-foreground">Campaigns</h1>
            <span className="text-xs text-muted-foreground">
              {statusCounts.ACTIVE}/{maxActiveCampaigns} active
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            Create, launch, and monitor your automated LinkedIn and email outreach campaigns.
          </p>
        </div>

        {/* Global Action Controls */}
        <div className="flex items-center gap-2.5">
          <button
            type="button"
            onClick={() => setShowGrowthHub(true)}
            className="px-3.5 py-2 bg-background hover:bg-muted text-foreground border border-border rounded-xl font-medium text-xs transition-colors cursor-pointer"
          >
            Campaign Automations
          </button>

          <button
            type="button"
            onClick={() => { resetTree(); navigate('/elein/campaigns/new'); }}
            className="flex items-center gap-1.5 bg-primary hover:bg-primary/90 text-primary-foreground px-4 py-2 rounded-xl font-medium text-xs transition-colors cursor-pointer whitespace-nowrap"
          >
            <Plus size={14} />
            <span>New Campaign</span>
          </button>
        </div>
      </div>

      {/* ─── FLEET VITAL STATISTICS RIBBON (Clean 3-Metric Overview) ─────────── */}
      {campaigns.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-border border border-border rounded-xl bg-card mb-6">
          {/* Cell 1: Total Leads */}
          <div className="p-4">
            <p className="text-xs text-muted-foreground">Total Leads</p>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-xl font-semibold text-foreground">
                <NumberTicker value={fleetStats.totalLeads} />
              </span>
              <span className="text-xs text-muted-foreground">{fleetStats.totalRunning} in sequence</span>
            </div>
          </div>

          {/* Cell 2: Connected Senders */}
          <div className="p-4">
            <p className="text-xs text-muted-foreground">Connected Senders</p>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-xl font-semibold text-foreground">
                <NumberTicker value={fleetStats.uniqueSenderCount} />
              </span>
              <span className="text-xs text-muted-foreground">
                {fleetStats.uniqueSenderCount === 1 ? '1 profile active' : 'Profiles rotating'}
              </span>
            </div>
          </div>

          {/* Cell 3: Reply Rate */}
          <div className="p-4">
            <p className="text-xs text-muted-foreground">Reply Rate</p>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-xl font-semibold text-foreground">
                <NumberTicker value={fleetStats.avgConversion} decimalPlaces={1} />%
              </span>
              <span className="text-xs text-muted-foreground">{fleetStats.totalReplies} replies</span>
            </div>
          </div>
        </div>
      )}

      {/* ─── ENVIRONMENTAL ATTENTION BANNERS (Layer 1) ───────────────────────── */}
      {fleetStats.activeWithZeroSenders > 0 && (
        <div className="mb-4 border border-border bg-card px-4 py-2.5 rounded-xl flex items-center justify-between text-xs">
          <div className="flex items-center gap-2 text-foreground">
            <span className="font-medium">
              {fleetStats.activeWithZeroSenders} active campaign{fleetStats.activeWithZeroSenders > 1 ? 's' : ''} with 0 senders assigned.
            </span>
            <span className="text-muted-foreground hidden sm:inline">
              Connect a LinkedIn account to dispatch actions.
            </span>
          </div>
          <button
            type="button"
            onClick={() => navigate('/elein/accounts')}
            className="px-3 py-1.5 bg-background hover:bg-muted text-foreground border border-border rounded-lg text-xs font-medium shrink-0 transition-colors cursor-pointer"
          >
            Assign Senders
          </button>
        </div>
      )}

      {/* ─── DEMO FLEET ATTENTION BANNER (EPF Phase 3) ────────────────────────── */}
      {isDemoFleetSeeded && (
        <div className="mb-4 border border-primary/30 bg-primary/5 px-4 py-3 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs shadow-2xs">
          <div className="flex items-center gap-2.5">
            <span className="w-2 h-2 rounded-full bg-primary animate-pulse shrink-0" />
            <div>
              <span className="font-bold text-foreground">Sandbox Demo Fleet Active: </span>
              <span className="text-muted-foreground">Displaying 3 pre-configured campaigns with live analytics to explore sorting, density modes, and filters.</span>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={handleClearDemoFleet}
              className="px-3 py-1.5 rounded-lg bg-background hover:bg-muted text-foreground border border-border text-xs font-medium transition-colors cursor-pointer flex items-center gap-1.5"
            >
              <Trash2 size={12} className="text-muted-foreground" />
              <span>Clear Demo Fleet</span>
            </button>
            <button
              type="button"
              onClick={() => navigate('/elein/campaigns/new?blank=true')}
              className="px-3 py-1.5 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold shadow-xs transition-colors cursor-pointer flex items-center gap-1.5"
            >
              <Plus size={12} />
              <span>Create Real Campaign</span>
            </button>
          </div>
        </div>
      )}

      {/* ─── DRAFT RESTORATION BANNER ────────────────────────────────────────── */}
      {draftExists && (
        <div className="mb-4 border border-border bg-card px-4 py-2.5 rounded-xl flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <span className="font-medium text-foreground">Unsaved campaign draft</span>
            <span className="text-muted-foreground">Saved locally from {draftTime}.</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                setConfirmModal({
                  isOpen: true,
                  title: "Discard Draft",
                  message: "Are you sure you want to permanently discard this unsaved draft?",
                  onConfirm: () => {
                    localStorage.removeItem("elein_unsaved_draft")
                    setDraftExists(false)
                    setConfirmModal(null)
                  }
                });
              }}
              className="px-2.5 py-1 text-xs font-medium text-muted-foreground hover:text-destructive transition-colors cursor-pointer"
            >
              Discard
            </button>
            <button
              type="button"
              onClick={() => navigate("/elein/campaigns/new?resume=true")}
              className="px-3.5 py-1.5 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-medium transition-colors cursor-pointer"
            >
              Resume Draft
            </button>
          </div>
        </div>
      )}

      {/* ─── ZERO STATE OR CAMPAIGN GRID (EPF Phase 3 - 10/10 Micro-Delight) ─────────── */}
      {campaigns.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-10 md:py-16 max-w-5xl mx-auto w-full px-4">
          {/* Top Pill & Headline */}
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full border border-primary/20 bg-primary/5 text-primary text-xs font-semibold mb-4 shadow-2xs">
            <Sparkles size={13} className="text-primary animate-pulse" />
            <span>Outreach Cadence Architecture</span>
          </div>

          <h2 className="text-2xl md:text-3xl font-bold tracking-tight text-foreground text-center mb-2">
            Design your outreach engine
          </h2>
          <p className="text-xs md:text-sm text-muted-foreground text-center mb-8 max-w-xl leading-relaxed">
            Select an objective playbook or explore an interactive sequence simulation. Experience how multi-agent delay, sentiment classification, and adaptive follow-ups drive conversion.
          </p>

          {/* Interactive Mini-DAG Sequence Blueprint Simulator (EPF Phase 3) */}
          <div className="w-full bg-card border border-border rounded-2xl p-5 md:p-6 mb-8 shadow-xs">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 mb-5 border-b border-border">
              <div className="flex items-center gap-2">
                <Compass size={16} className="text-primary" />
                <span className="text-xs font-bold text-foreground tracking-wide uppercase">
                  Interactive Cadence Simulator
                </span>
                <span className="text-[11px] px-2 py-0.5 rounded-md bg-muted text-muted-foreground font-mono">
                  {SEQUENCE_PLAYBOOKS.find(p => p.id === activePlaybookTab)?.avgReplyRate} avg. replies
                </span>
              </div>

              {/* Playbook Selection Tabs */}
              <div className="flex items-center gap-1 bg-muted/60 p-1 rounded-xl border border-border/40">
                {SEQUENCE_PLAYBOOKS.map((playbook) => {
                  const isActive = activePlaybookTab === playbook.id;
                  return (
                    <button
                      key={playbook.id}
                      type="button"
                      onClick={() => setActivePlaybookTab(playbook.id as any)}
                      className={`relative px-3 py-1 text-xs font-medium rounded-lg transition-all cursor-pointer ${
                        isActive
                          ? "bg-background text-foreground shadow-xs border border-border/80"
                          : "text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      {playbook.title}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Visual Mini-DAG Node Flow */}
            {(() => {
              const currentPlaybook = SEQUENCE_PLAYBOOKS.find(p => p.id === activePlaybookTab) || SEQUENCE_PLAYBOOKS[0];
              return (
                <div>
                  <div className="text-xs text-muted-foreground mb-4 flex items-center justify-between">
                    <span>
                      Target Audience: <strong className="text-foreground">{currentPlaybook.target}</strong>
                    </span>
                    <span className="font-mono text-[11px] text-primary">Live Multi-Touch Preview</span>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5 relative">
                    {currentPlaybook.nodes.map((node) => (
                      <div
                        key={node.step}
                        className="relative rounded-xl border border-border/80 bg-background/80 hover:border-primary/50 transition-all p-3.5 flex flex-col justify-between group"
                      >
                        <div>
                          <div className="flex items-center justify-between mb-2">
                            <span className="font-mono text-[10px] text-muted-foreground font-semibold px-1.5 py-0.5 bg-muted rounded">
                              Step {node.step}
                            </span>
                            {node.type === 'ACTION' ? (
                              <Zap size={13} className="text-primary group-hover:scale-110 transition-transform" />
                            ) : node.type === 'DELAY' ? (
                              <Clock size={13} className="text-warning group-hover:scale-110 transition-transform" />
                            ) : (
                              <Bot size={13} className="text-success group-hover:scale-110 transition-transform" />
                            )}
                          </div>
                          <h4 className="text-xs font-bold text-foreground mb-1 group-hover:text-primary transition-colors">
                            {node.title}
                          </h4>
                          <p className="text-[11px] text-muted-foreground leading-relaxed">
                            {node.desc}
                          </p>
                        </div>

                        <div className="mt-3 pt-2 border-t border-border/40 flex items-center justify-between text-[10px] text-muted-foreground">
                          <span className="font-medium text-foreground/80">
                            {node.type === 'ACTION' ? 'Direct Touch' : node.type === 'DELAY' ? 'Safety Interval' : 'AI Automation'}
                          </span>
                          <span className="text-primary">Verified</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })()}

            {/* Bottom Actions inside Simulator */}
            <div className="mt-6 pt-4 border-t border-border flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Sparkles size={13} className="text-primary" />
                <span>Want to test with realistic mock data before connecting LinkedIn?</span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleSeedDemoFleet}
                  className="px-3.5 py-1.5 rounded-lg border border-border bg-background hover:bg-muted text-foreground text-xs font-semibold transition-all cursor-pointer shadow-xs flex items-center gap-1.5"
                >
                  <Database size={13} className="text-primary" />
                  <span>Seed Sandbox Demo Fleet</span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    navigate('/elein/campaigns/new?goal=' + (activePlaybookTab === 'founder' ? 'get_customers' : activePlaybookTab === 'talent' ? 'hire_people' : 'get_intros'));
                  }}
                  className="px-4 py-1.5 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold transition-all cursor-pointer shadow-xs flex items-center gap-1.5"
                >
                  <span>Build This Campaign</span>
                  <ChevronRight size={13} />
                </button>
              </div>
            </div>
          </div>

          {/* 3 Core Objective Starter Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5 w-full mb-6">
            <EmptyCampaignCard 
              id="get_customers"
              icon={Users}
              title="Get customers"
              desc="Target enterprise buyers, founders, and VP decision-makers with high-intent outreach."
              onSelect={(id: string) => { navigate('/elein/campaigns/new?goal=' + id); }}
            />
            <EmptyCampaignCard 
              id="hire_people"
              icon={Briefcase}
              title="Hire people"
              desc="Recruit high-signal engineers, designers, and operators with personal founder outreach."
              onSelect={(id: string) => { navigate('/elein/campaigns/new?goal=' + id); }}
            />
            <EmptyCampaignCard 
              id="get_intros"
              icon={LinkIcon}
              title="Get intros"
              desc="Network with angels, venture funds, podcast hosts, and prospective distribution partners."
              onSelect={(id: string) => { navigate('/elein/campaigns/new?goal=' + id); }}
            />
          </div>

          <button
            type="button"
            onClick={() => {
              useHRTreeStore.getState().reset();
              try { localStorage.removeItem("elein_unsaved_draft"); } catch (_) {}
              navigate('/elein/campaigns/new?blank=true');
            }}
            className="text-xs font-medium text-muted-foreground hover:text-foreground underline underline-offset-4 transition-colors cursor-pointer"
          >
            Or start from a blank canvas
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          {/* Multi-Campaign Scaling Pay Ramp Banner */}
          {statusCounts.ACTIVE >= maxActiveCampaigns && (
            <div className="border border-border bg-card px-4 py-2.5 rounded-xl flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <span className="font-medium text-foreground">
                  Active campaign limit reached ({statusCounts.ACTIVE}/{maxActiveCampaigns} active)
                </span>
                <span className="text-muted-foreground hidden md:inline">
                  {!isPro ? "Upgrade to Growth Pro to run up to 20 campaigns simultaneously across multiple LinkedIn accounts." : isAgency ? "Upgrade to Enterprise to run up to 100 campaigns." : "Upgrade to Agency Tier to run up to 50 campaigns."}
                </span>
              </div>
              <button
                type="button"
                onClick={() => openPaywall({ featureName: "Active Campaigns Limit" })}
                className="px-3.5 py-1.5 rounded-lg bg-background hover:bg-muted text-foreground border border-border text-xs font-medium transition-colors shrink-0 whitespace-nowrap cursor-pointer"
              >
                {!isPro ? "Unlock 20 Campaigns" : isAgency ? "Unlock 100 Campaigns" : "Unlock 50 Campaigns"}
              </button>
            </div>
          )}

          {/* ─── CONTROLS BAR: SEARCH, FILTERS & SORT ──────────────────────────── */}
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 p-3 bg-card border border-border rounded-xl">
            {/* Filter chips */}
            <div className="flex items-center gap-1.5 flex-wrap">
              {[
                { key: 'ALL', label: 'All', count: statusCounts.ALL, dot: 'bg-primary' },
                { key: 'ACTIVE', label: 'Active', count: statusCounts.ACTIVE, dot: 'bg-success' },
                { key: 'PAUSED', label: 'Paused', count: statusCounts.PAUSED, dot: 'bg-warning' },
                { key: 'DRAFT', label: 'Drafts', count: statusCounts.DRAFT, dot: 'bg-muted-foreground' },
                { key: 'COMPLETED', label: 'Completed', count: statusCounts.COMPLETED, dot: 'bg-indigo-500' },
              ].map(tab => {
                const isActive = statusFilter === tab.key;
                return (
                  <button
                    type="button"
                    key={tab.key}
                    onClick={() => {
                      setStatusFilter(tab.key as any)
                      setSelectedIds(new Set())
                      setPage(1)
                    }}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors border cursor-pointer ${
                      isActive
                        ? 'bg-muted border-border text-foreground'
                        : 'bg-background hover:bg-muted/50 border-transparent text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    <span className={`w-1.5 h-1.5 rounded-full ${tab.dot}`} />
                    <span>{tab.label}</span>
                    <span className="font-mono text-xs text-muted-foreground">
                      {tab.count}
                    </span>
                  </button>
                );
              })}
            </div>

            {/* Search & Sort Controls */}
            <div className="flex items-center gap-2 flex-wrap">
              {/* Search Box */}
              <div className="flex items-center gap-2 px-3 py-1.5 bg-background border border-border rounded-lg w-full sm:w-56">
                <Search size={13} className="text-muted-foreground shrink-0" />
                <input
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  placeholder="Filter campaigns..."
                  className="flex-1 bg-transparent text-xs text-foreground placeholder-muted-foreground focus:outline-none"
                />
                {search && (
                  <button type="button" onClick={() => setSearch("")} className="text-muted-foreground hover:text-foreground">
                    <X size={12} />
                  </button>
                )}
              </div>

              {/* Sort Dropdown */}
              <div className="flex items-center gap-1.5">
                <Select value={sortBy} onValueChange={(val) => setSortBy(val as any)}>
                  <SelectTrigger size="sm" className="w-[150px] bg-background border-border text-xs">
                    <div className="flex items-center gap-1.5 truncate">
                      <ArrowUpDown size={13} className="shrink-0 text-muted-foreground" />
                      <SelectValue placeholder="Sort by..." />
                    </div>
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="created_desc">Newest First</SelectItem>
                    <SelectItem value="created_asc">Oldest First</SelectItem>
                    <SelectItem value="leads_desc">Most Prospects</SelectItem>
                    <SelectItem value="conversion_desc">Top Conversion</SelectItem>
                    <SelectItem value="name_asc">Name (A-Z)</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Table View & Density Options (EPF Phase 1) */}
              <TableViewOptions
                density={density}
                onDensityChange={handleDensityChange}
                columns={CAMPAIGN_COLUMNS}
                visibleColumns={visibleColumns}
                onToggleColumn={handleToggleColumn}
                onResetToDefaults={handleResetViewOptions}
              />
            </div>
          </div>

          {/* ─── STICKY BATCH COMMAND TOOLBAR (Layer 0 & Layer 2) ─────────────── */}
          <AnimatePresence>
            {selectedIds.size > 0 && (
              <motion.div
                initial={{ opacity: 0, y: -6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                className="bg-card text-foreground border border-border rounded-xl shadow-sm px-4 py-2.5 flex flex-col sm:flex-row items-center justify-between gap-3"
              >
                <div className="flex items-center gap-2.5">
                  <span className="px-2 py-0.5 rounded-lg bg-muted text-foreground font-mono text-xs font-medium">
                    {selectedIds.size}
                  </span>
                  <span className="text-xs font-medium text-foreground">
                    Campaign{selectedIds.size > 1 ? 's' : ''} Selected
                  </span>
                  <button
                    type="button"
                    onClick={() => setSelectedIds(new Set())}
                    className="text-xs text-muted-foreground hover:text-foreground underline ml-1 cursor-pointer flex items-center gap-1"
                  >
                    <span>Deselect All</span>
                    <kbd className="font-mono text-[10px] px-1 py-0.2 bg-muted rounded border border-border text-muted-foreground">Esc</kbd>
                  </button>
                </div>

                <div className="flex items-center gap-2 flex-wrap">
                  <button
                    type="button"
                    onClick={handleBatchResume}
                    disabled={isBatchOperating}
                    className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg border border-border bg-background hover:bg-muted text-foreground text-xs font-medium transition-colors disabled:opacity-50 cursor-pointer"
                  >
                    {isBatchOperating && batchActionType === 'resume' ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
                    <span>Resume Selected</span>
                  </button>
                  <button
                    type="button"
                    onClick={handleBatchPause}
                    disabled={isBatchOperating}
                    className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg border border-border bg-background hover:bg-muted text-foreground text-xs font-medium transition-colors disabled:opacity-50 cursor-pointer"
                  >
                    {isBatchOperating && batchActionType === 'pause' ? <Loader2 size={13} className="animate-spin" /> : <Pause size={13} />}
                    <span>Pause Selected</span>
                  </button>
                  <button
                    type="button"
                    onClick={handleBatchDelete}
                    disabled={isBatchOperating}
                    className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg border border-border bg-background hover:bg-muted text-destructive text-xs font-medium transition-colors disabled:opacity-50 cursor-pointer"
                  >
                    {isBatchOperating && batchActionType === 'delete' ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
                    <span>Delete Selected</span>
                  </button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* ─── CAMPAIGNS DATA TABLE (Filter Zero - EPF Phase 3) ──────────────── */}
          {filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center p-10 md:p-14 text-center rounded-xl border border-dashed border-border bg-card/60 backdrop-blur-xs">
              <div className="w-12 h-12 rounded-xl bg-muted/60 border border-border flex items-center justify-center mb-4 text-muted-foreground">
                <Search size={22} className="text-muted-foreground" />
              </div>
              <h3 className="text-sm font-semibold text-foreground mb-1">
                No campaigns match active filters
              </h3>
              <p className="text-xs text-muted-foreground max-w-md mb-4 leading-relaxed">
                {search && statusFilter !== 'ALL' ? (
                  <span>
                    No campaigns found matching <span className="font-semibold text-foreground font-mono bg-muted px-1.5 py-0.5 rounded border border-border">"{search}"</span> with status <span className="font-semibold text-foreground">{statusFilter}</span>.
                  </span>
                ) : search ? (
                  <span>
                    No campaigns found containing <span className="font-semibold text-foreground font-mono bg-muted px-1.5 py-0.5 rounded border border-border">"{search}"</span> across your fleet.
                  </span>
                ) : (
                  <span>
                    You currently have 0 campaigns in <span className="font-semibold text-foreground">{statusFilter}</span> status.
                  </span>
                )}
              </p>
              <div className="flex items-center gap-2 flex-wrap justify-center">
                {search && (
                  <button
                    type="button"
                    onClick={() => setSearch("")}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border bg-background hover:bg-muted text-xs font-medium text-foreground transition-colors cursor-pointer"
                  >
                    <X size={12} className="text-muted-foreground" />
                    <span>Clear "{search}"</span>
                  </button>
                )}
                {statusFilter !== 'ALL' && (
                  <button
                    type="button"
                    onClick={() => setStatusFilter('ALL')}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border bg-background hover:bg-muted text-xs font-medium text-foreground transition-colors cursor-pointer"
                  >
                    <RefreshCw size={12} className="text-muted-foreground" />
                    <span>Show All Statuses</span>
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => { setSearch(""); setStatusFilter("ALL"); setPage(1); }}
                  className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold shadow-xs transition-colors cursor-pointer"
                >
                  <span>Reset All Filters</span>
                  <kbd className="font-mono text-[10px] bg-primary-foreground/20 px-1 py-0.2 rounded">Esc</kbd>
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div>
                  <h2 className="text-sm font-semibold tracking-tight text-foreground">Campaign Fleet Performance Scorecard</h2>
                  <p className="text-xs text-muted-foreground">Cohort conversion velocity and response health across active sequence playbooks</p>
                </div>
              </div>

              <div className="bg-card rounded-xl border border-border overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm whitespace-nowrap">
                    <thead className="bg-muted/30 border-b border-border text-muted-foreground text-xs font-medium">
                      <tr>
                        <th className={cn("px-4 w-10 text-center", densityPadding)}>
                          <button
                            type="button"
                            onClick={handleToggleSelectAll}
                            className="text-muted-foreground hover:text-foreground cursor-pointer"
                            title={isAllSelected ? "Deselect All" : "Select All"}
                          >
                            {isAllSelected ? (
                              <CheckSquare size={15} className="text-primary" />
                            ) : (
                              <Square size={15} />
                            )}
                          </button>
                        </th>
                        <th className={cn("px-5 min-w-[200px]", densityPadding)}>Campaign Name</th>
                        {visibleColumns.includes('status') && (
                          <th className={cn("px-4 w-28", densityPadding)}>Status</th>
                        )}
                        {visibleColumns.includes('enrolled') && (
                          <th className={cn("px-4 w-24 text-right hidden sm:table-cell", densityPadding)}>Enrolled</th>
                        )}
                        {visibleColumns.includes('connected') && (
                          <th className={cn("px-4 w-24 text-right hidden md:table-cell", densityPadding)}>Connected</th>
                        )}
                        {visibleColumns.includes('acceptance') && (
                          <th className={cn("px-4 w-28 text-right hidden lg:table-cell", densityPadding)}>Acceptance</th>
                        )}
                        {visibleColumns.includes('replied') && (
                          <th className={cn("px-4 w-24 text-right hidden lg:table-cell", densityPadding)}>Replied</th>
                        )}
                        {visibleColumns.includes('replyRate') && (
                          <th className={cn("px-4 w-28 text-right hidden xl:table-cell", densityPadding)}>Reply Rate</th>
                        )}
                        {visibleColumns.includes('booked') && (
                          <th className={cn("px-4 w-24 text-right hidden xl:table-cell", densityPadding)}>Booked</th>
                        )}
                        {visibleColumns.includes('senders') && (
                          <th className={cn("px-4 w-28 text-center hidden 2xl:table-cell", densityPadding)}>Senders</th>
                        )}
                        <th className={cn("px-5 w-36 text-right", densityPadding)}>Action</th>
                      </tr>
                    </thead>
                  <tbody className="divide-y divide-border">
                    {paginatedCampaigns.map((c) => {
                      const statusCfg = STATUS_CONFIG[c.status] || STATUS_CONFIG["DRAFT"]
                      const isSelected = selectedIds.has(c.id)
                      const hasZeroSenders = c.status === 'ACTIVE' && (!c.senders || c.senders.length === 0)
                      const dateStr = c.created_at 
                        ? new Date(c.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) 
                        : "Recently"

                      const sc = scorecardMap.get(c.id) || {}
                      const enrolled = Number(sc.enrolled ?? c.leads_total ?? 0)
                      const connected = Number(sc.connected ?? c.leads_completed ?? 0)
                      const acceptanceRate = sc.acceptance_rate !== undefined 
                        ? Number(sc.acceptance_rate) 
                        : (enrolled > 0 ? Math.round((connected / enrolled) * 100) : 0)
                      const replied = Number(sc.replied ?? c.replies ?? 0)
                      const replyRate = sc.reply_rate !== undefined 
                        ? Number(sc.reply_rate) 
                        : (connected > 0 ? Math.round((replied / connected) * 100) : 0)
                      const booked = Number(sc.booked ?? (c.leads_completed && c.conversion_rate ? Math.round(c.leads_completed * c.conversion_rate) : 0))

                      return (
                        <tr
                          key={c.id}
                          className={`transition-colors group cursor-pointer ${
                            isSelected ? 'bg-muted/40' : 'hover:bg-muted/20'
                          }`}
                          onClick={() => navigate(`/elein/campaigns/${c.id}`)}
                        >
                          {/* Checkbox */}
                          <td className={cn("px-4 text-center", densityPadding)} onClick={(e) => e.stopPropagation()}>
                            <button
                              type="button"
                              onClick={(e) => handleToggleSelectOne(c.id, e)}
                              className="text-muted-foreground hover:text-foreground cursor-pointer"
                            >
                              {isSelected ? (
                                <CheckSquare size={15} className="text-primary" />
                              ) : (
                                <Square size={15} />
                              )}
                            </button>
                          </td>

                          {/* Campaign Name & Date */}
                          <td className={cn("px-5", densityPadding)}>
                            <div className="block">
                              <p className={cn("font-medium text-foreground group-hover:underline underline-offset-2", densityText)}>
                                {c.name}
                              </p>
                              <p className="text-[11px] text-muted-foreground mt-0.5">{dateStr}</p>
                            </div>
                          </td>

                          {/* Status */}
                          {visibleColumns.includes('status') && (
                            <td className={cn("px-4", densityPadding)}>
                              <div className="flex flex-col gap-1">
                                <StatusPill 
                                  status={c.status.toLowerCase()} 
                                  size="xs" 
                                  pulse={c.status === 'ACTIVE'} 
                                />
                                {hasZeroSenders && (
                                  <span 
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      navigate(`/elein/campaigns/new?edit=${c.id}`);
                                    }}
                                    className="text-[11px] text-amber-500 hover:text-amber-400 underline w-fit font-medium"
                                    title="Campaign active but 0 sender accounts assigned"
                                  >
                                    0 senders assigned
                                  </span>
                                )}
                              </div>
                            </td>
                          )}

                          {/* Enrolled */}
                          {visibleColumns.includes('enrolled') && (
                            <td className={cn("px-4 text-right font-mono text-foreground hidden sm:table-cell", densityPadding, densityText)}>
                              <NumberTicker value={enrolled} />
                            </td>
                          )}

                          {/* Connected */}
                          {visibleColumns.includes('connected') && (
                            <td className={cn("px-4 text-right font-mono text-foreground hidden md:table-cell", densityPadding, densityText)}>
                              <NumberTicker value={connected} />
                            </td>
                          )}

                          {/* Acceptance Rate */}
                          {visibleColumns.includes('acceptance') && (
                            <td className={cn("px-4 text-right font-mono text-foreground hidden lg:table-cell", densityPadding, densityText)}>
                              <NumberTicker value={acceptanceRate} />%
                            </td>
                          )}

                          {/* Replied */}
                          {visibleColumns.includes('replied') && (
                            <td className={cn("px-4 text-right font-mono text-foreground hidden lg:table-cell", densityPadding, densityText)}>
                              <NumberTicker value={replied} />
                            </td>
                          )}

                          {/* Reply Rate */}
                          {visibleColumns.includes('replyRate') && (
                            <td className={cn("px-4 text-right font-mono text-foreground hidden xl:table-cell", densityPadding, densityText)}>
                              <NumberTicker value={replyRate} />%
                            </td>
                          )}

                          {/* Booked */}
                          {visibleColumns.includes('booked') && (
                            <td className={cn("px-4 text-right font-mono font-semibold text-primary hidden xl:table-cell", densityPadding, densityText)}>
                              <NumberTicker value={booked} />
                            </td>
                          )}

                          {/* Senders */}
                          {visibleColumns.includes('senders') && (
                            <td className={cn("px-4 text-center text-muted-foreground hidden 2xl:table-cell", densityPadding, densityText)} onClick={(e) => e.stopPropagation()}>
                              {c.senders && c.senders.length > 0 ? (
                                <div className="flex justify-center -space-x-1.5 overflow-hidden">
                                  {c.senders.slice(0, 3).map((s: any, idx: number) => (
                                    <div 
                                      key={idx} 
                                      className="inline-block h-6 w-6 rounded-full ring-2 ring-background bg-muted border border-border text-foreground flex items-center justify-center text-xs font-mono font-medium" 
                                      title={s.name}
                                    >
                                      {s.name ? s.name.substring(0, 2).toUpperCase() : "IN"}
                                    </div>
                                  ))}
                                  {c.senders.length > 3 && (
                                    <div className="inline-block h-6 w-6 rounded-full ring-2 ring-background bg-muted text-muted-foreground flex items-center justify-center text-xs font-mono">
                                      +{c.senders.length - 3}
                                    </div>
                                  )}
                                </div>
                              ) : (
                                <span className="text-xs text-muted-foreground">None</span>
                              )}
                            </td>
                          )}

                          {/* Row Action Station */}
                          <td className={cn("px-5 text-right", densityPadding)} onClick={(e) => e.stopPropagation()}>
                            <div className="flex items-center justify-end gap-1.5 relative">
                              {/* Inspect Button */}
                              <button
                                type="button"
                                onClick={() => navigate(`/elein/campaigns/${c.id}`)}
                                className="px-2.5 py-1 rounded-md border border-border bg-background hover:bg-muted text-foreground text-xs font-medium transition-colors cursor-pointer"
                                title="Inspect campaign analytics & leads"
                              >
                                Inspect
                              </button>

                              {/* Toggle Active/Pause */}
                              <button
                                type="button"
                                onClick={() => toggleStatus(c.id)}
                                disabled={activeTogglingIds.has(c.id) || isBatchOperating}
                                className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer disabled:opacity-50"
                                title={c.status === "ACTIVE" ? "Pause Campaign" : "Resume Campaign"}
                              >
                                {activeTogglingIds.has(c.id) ? (
                                  <Loader2 size={14} className="animate-spin" />
                                ) : c.status === "ACTIVE" ? (
                                  <Pause size={14} />
                                ) : (
                                  <Play size={14} />
                                )}
                              </button>

                              {/* Edit Sequence */}
                              <button
                                type="button"
                                onClick={() => navigate(`/elein/campaigns/new?edit=${c.id}`)}
                                className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                                title="Edit Campaign Sequence"
                              >
                                <Settings size={14} />
                              </button>

                              {/* More Options Dropdown */}
                              <div className="relative">
                                <button
                                  type="button"
                                  onClick={() => setOpenRowMenuId(openRowMenuId === c.id ? null : c.id)}
                                  className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                                  title="More Options"
                                >
                                  <MoreVertical size={14} />
                                </button>

                                {openRowMenuId === c.id && (
                                  <div
                                    ref={rowMenuRef}
                                    className="absolute right-0 top-full mt-1 w-48 p-1.5 bg-popover border border-border rounded-xl shadow-lg z-50 text-left"
                                  >
                                    <button
                                      type="button"
                                      onClick={() => {
                                        setOpenRowMenuId(null);
                                        handleDuplicateCampaign(c.id, c.name);
                                      }}
                                      disabled={duplicatingId === c.id}
                                      className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs text-foreground hover:bg-muted rounded-lg transition-colors cursor-pointer"
                                    >
                                      <Copy size={14} className="text-muted-foreground" />
                                      <span>Duplicate Campaign</span>
                                    </button>

                                    <button
                                      type="button"
                                      onClick={() => {
                                        setOpenRowMenuId(null);
                                        setSelectedCertCampaign({ id: c.id, name: c.name });
                                      }}
                                      className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs text-foreground hover:bg-muted rounded-lg transition-colors cursor-pointer"
                                    >
                                      <Award size={14} className="text-muted-foreground" />
                                      <span>Performance Report</span>
                                    </button>

                                    <button
                                      type="button"
                                      onClick={() => {
                                        setOpenRowMenuId(null);
                                        setBanditCampaign({ id: c.id, name: c.name });
                                      }}
                                      className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs text-foreground hover:bg-muted rounded-lg transition-colors cursor-pointer"
                                    >
                                      <BarChart2 size={14} className="text-muted-foreground" />
                                      <span>Copy Intelligence</span>
                                    </button>

                                    <div className="my-1 border-t border-border" />

                                    <button
                                      type="button"
                                      onClick={() => {
                                        setOpenRowMenuId(null);
                                        remove(c.id);
                                      }}
                                      className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs text-destructive hover:bg-destructive/10 rounded-lg transition-colors cursor-pointer"
                                    >
                                      <Trash2 size={14} />
                                      <span>Delete Campaign</span>
                                    </button>
                                  </div>
                                )}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
                {filtered.length > PAGE_SIZE && (
                  <div className="flex flex-col sm:flex-row items-center justify-between gap-3 px-5 py-3.5 border-t border-border bg-card/50 text-xs text-muted-foreground">
                    <div>
                      Showing <span className="font-semibold text-foreground">{(page - 1) * PAGE_SIZE + 1}</span> to{" "}
                      <span className="font-semibold text-foreground">{Math.min(page * PAGE_SIZE, filtered.length)}</span> of{" "}
                      <span className="font-semibold text-foreground">{filtered.length}</span> campaigns
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setPage(p => Math.max(1, p - 1))}
                        disabled={page === 1}
                        className="px-3 py-1.5 rounded-lg border border-border bg-background hover:bg-muted text-foreground disabled:opacity-40 disabled:cursor-not-allowed transition-colors font-medium flex items-center gap-1 cursor-pointer"
                      >
                        <ChevronLeft size={13} />
                        <span>Previous</span>
                      </button>
                      <span className="px-2 font-medium">
                        Page {page} of {totalPages}
                      </span>
                      <button
                        type="button"
                        onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                        disabled={page === totalPages}
                        className="px-3 py-1.5 rounded-lg border border-border bg-background hover:bg-muted text-foreground disabled:opacity-40 disabled:cursor-not-allowed transition-colors font-medium flex items-center gap-1 cursor-pointer"
                      >
                        <span>Next</span>
                        <ChevronRight size={13} />
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
        </div>
      )}

      {/* ─── MODALS ───────────────────────────────────────────────────────────── */}
      {/* Pre-Flight Launch Cockpit Gate */}
      {preflightCampaign && (
        <CampaignPreflightModal
          isOpen={!!preflightCampaign}
          onClose={() => setPreflightCampaign(null)}
          onConfirmLaunch={() => executeToggleStatus(preflightCampaign.id, 'activate')}
          campaignId={preflightCampaign.id}
          campaignName={preflightCampaign.name}
        />
      )}

      {/* Custom Confirmation Modal */}
      <AnimatePresence>
        {confirmModal && confirmModal.isOpen && (
          <motion.div
            key="confirm-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            onClick={(e) => {
              if (e.target === e.currentTarget) setConfirmModal(null)
            }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-xs"
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 8 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 8 }}
              transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
              className="w-full max-w-sm bg-card border border-border rounded-xl shadow-xl overflow-hidden"
            >
              <div className="p-6">
                <h3 className="text-base font-bold text-foreground mb-2 flex items-center gap-2">
                  <AlertCircle size={18} className="text-destructive shrink-0" />
                  {confirmModal.title}
                </h3>
                <p className="text-xs text-muted-foreground leading-relaxed">{confirmModal.message}</p>
              </div>
              <div className="px-6 py-4 bg-muted/30 border-t border-border flex items-center justify-end gap-3">
                <button 
                  type="button"
                  onClick={() => setConfirmModal(null)}
                  className="px-4 py-2 rounded-lg text-xs font-semibold hover:bg-muted text-foreground transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button 
                  type="button"
                  onClick={confirmModal.onConfirm}
                  className="px-4 py-2 rounded-lg text-xs font-bold bg-destructive hover:bg-destructive/90 text-white transition-colors shadow-xs cursor-pointer"
                >
                  Confirm Delete
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ─── GROWTH TOOLS HUB MODAL ────────────────────────────────────────── */}
      <AnimatePresence>
        {showGrowthHub && (
          <motion.div
            key="growth-hub-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-background/80 backdrop-blur-xs"
            onClick={() => setShowGrowthHub(false)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.98, y: 8 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.98, y: 8 }}
              transition={{ duration: 0.15 }}
              onClick={(e) => e.stopPropagation()}
              className="w-full max-w-3xl max-h-[88vh] bg-card border border-border rounded-xl shadow-xl overflow-hidden flex flex-col"
            >
              {/* Hub Header */}
              <div className="px-6 py-4 border-b border-border flex items-center justify-between shrink-0">
                <div>
                  <h2 className="text-base font-semibold text-foreground">Campaign Automations</h2>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Turn on optional automations to increase your replies, follow up across channels, and protect your accounts.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setShowGrowthHub(false)}
                  className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
                >
                  <X size={16} />
                </button>
              </div>

              {/* Hub Content Scrollable Grid */}
              <div className="p-6 overflow-y-auto space-y-5">
                {/* Section 1: Algorithmic Response Velocity */}
                <div>
                  <h3 className="text-xs font-medium text-muted-foreground border-b border-border pb-1.5 mb-2.5">
                    1. Algorithmic Response Velocity & Bandit Optimization
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                    <button
                      type="button"
                      onClick={() => { setShowGrowthHub(false); setBanditCampaign({ id: "", name: "Global Portfolio" }); }}
                      className="w-full text-left p-4 rounded-lg border border-border bg-background hover:bg-muted/40 transition-colors cursor-pointer flex items-start justify-between gap-3 group"
                    >
                      <div>
                        <h4 className="text-sm font-medium text-foreground">Multi-Armed Bandit Strategy Optimizer</h4>
                        <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                          Thompson sampling and algorithmic copy variance routing to maximize verified meeting conversion velocity.
                        </p>
                      </div>
                      <ChevronRight size={14} className="text-muted-foreground group-hover:text-foreground shrink-0 mt-0.5 transition-transform group-hover:translate-x-0.5" />
                    </button>

                    <button
                      type="button"
                      onClick={() => { setShowGrowthHub(false); setShowSentimentModal(true); }}
                      className="w-full text-left p-4 rounded-lg border border-border bg-background hover:bg-muted/40 transition-colors cursor-pointer flex items-start justify-between gap-3 group"
                    >
                      <div>
                        <h4 className="text-sm font-medium text-foreground">7-Class Inbound Intent & Auto-Snooze Engine</h4>
                        <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                          Sub-second zero-shot sentiment classification with autonomous out-of-office pause and CRM re-routing.
                        </p>
                      </div>
                      <ChevronRight size={14} className="text-muted-foreground group-hover:text-foreground shrink-0 mt-0.5 transition-transform group-hover:translate-x-0.5" />
                    </button>

                    <button
                      type="button"
                      onClick={() => { setShowGrowthHub(false); setShowStoModal(true); }}
                      className="w-full text-left p-4 rounded-lg border border-border bg-background hover:bg-muted/40 transition-colors cursor-pointer flex items-start justify-between gap-3 group"
                    >
                      <div>
                        <h4 className="text-sm font-medium text-foreground">AI Send-Time Optimization (STO) & Anti-Bot Jitter</h4>
                        <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                          Algorithmic prospect activity modeling with humanized dispersion windows to guarantee top-of-inbox delivery.
                        </p>
                      </div>
                      <ChevronRight size={14} className="text-muted-foreground group-hover:text-foreground shrink-0 mt-0.5 transition-transform group-hover:translate-x-0.5" />
                    </button>

                    <button
                      type="button"
                      onClick={() => { setShowGrowthHub(false); setShowCalendarModal(true); }}
                      className="w-full text-left p-4 rounded-lg border border-border bg-background hover:bg-muted/40 transition-colors cursor-pointer flex items-start justify-between gap-3 group"
                    >
                      <div>
                        <h4 className="text-sm font-medium text-foreground">Frictionless Calendar Bridge & Availability Sync</h4>
                        <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                          Direct real-time slot resolution preventing scheduling friction and eliminating back-and-forth roundtrips.
                        </p>
                      </div>
                      <ChevronRight size={14} className="text-muted-foreground group-hover:text-foreground shrink-0 mt-0.5 transition-transform group-hover:translate-x-0.5" />
                    </button>
                  </div>
                </div>

                {/* Section 2: Deterministic Omnichannel Orchestration */}
                <div>
                  <h3 className="text-xs font-medium text-muted-foreground border-b border-border pb-1.5 mb-2.5">
                    2. Deterministic Omnichannel Orchestration & ABM
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                    <button
                      type="button"
                      onClick={() => { setShowGrowthHub(false); setShowOmnichannelModal(true); }}
                      className="w-full text-left p-4 rounded-lg border border-border bg-background hover:bg-muted/40 transition-colors cursor-pointer flex items-start justify-between gap-3 group"
                    >
                      <div>
                        <h4 className="text-sm font-medium text-foreground">Omnichannel Fallback & Mailbox Cascade</h4>
                        <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                          Autonomous bridge routing silent LinkedIn prospects to warmed SMTP clusters with thread preservation.
                        </p>
                      </div>
                      <ChevronRight size={14} className="text-muted-foreground group-hover:text-foreground shrink-0 mt-0.5 transition-transform group-hover:translate-x-0.5" />
                    </button>

                    <button
                      type="button"
                      onClick={() => { setShowGrowthHub(false); setShowAbmModal(true); }}
                      className="w-full text-left p-4 rounded-lg border border-border bg-background hover:bg-muted/40 transition-colors cursor-pointer flex items-start justify-between gap-3 group"
                    >
                      <div>
                        <h4 className="text-sm font-medium text-foreground">Account-Based Multithreading (ABM) Engine</h4>
                        <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                          Coordinated multi-stakeholder outreach across target accounts with anti-collision lead locks.
                        </p>
                      </div>
                      <ChevronRight size={14} className="text-muted-foreground group-hover:text-foreground shrink-0 mt-0.5 transition-transform group-hover:translate-x-0.5" />
                    </button>

                    <button
                      type="button"
                      onClick={() => { setShowGrowthHub(false); setShowBoomerangModal(true); }}
                      className="w-full text-left p-4 rounded-lg border border-border bg-background hover:bg-muted/40 transition-colors cursor-pointer flex items-start justify-between gap-3 group"
                    >
                      <div>
                        <h4 className="text-sm font-medium text-foreground">Executive Mobility Telemetry (Boomerang Radar)</h4>
                        <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                          Automated career transition surveillance triggering timely outreach as champions move to new ICP accounts.
                        </p>
                      </div>
                      <ChevronRight size={14} className="text-muted-foreground group-hover:text-foreground shrink-0 mt-0.5 transition-transform group-hover:translate-x-0.5" />
                    </button>

                    <button
                      type="button"
                      onClick={() => { setShowGrowthHub(false); setShowEventModal(true); }}
                      className="w-full text-left p-4 rounded-lg border border-border bg-background hover:bg-muted/40 transition-colors cursor-pointer flex items-start justify-between gap-3 group"
                    >
                      <div>
                        <h4 className="text-sm font-medium text-foreground">High-Intent Event Cohort Ingestion</h4>
                        <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                          Real-time attendee enrichment and instant sequence enrollment for industry summits and webinars.
                        </p>
                      </div>
                      <ChevronRight size={14} className="text-muted-foreground group-hover:text-foreground shrink-0 mt-0.5 transition-transform group-hover:translate-x-0.5" />
                    </button>
                  </div>
                </div>

                {/* Section 3: Deliverability Infrastructure */}
                <div>
                  <h3 className="text-xs font-medium text-muted-foreground border-b border-border pb-1.5 mb-2.5">
                    3. Deliverability Infrastructure & Anti-Ban Protocols
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                    <button
                      type="button"
                      onClick={() => { setShowGrowthHub(false); setShowPreWarmModal(true); }}
                      className="w-full text-left p-4 rounded-lg border border-border bg-background hover:bg-muted/40 transition-colors cursor-pointer flex items-start justify-between gap-3 group"
                    >
                      <div>
                        <h4 className="text-sm font-medium text-foreground">Algorithmic Warmup & Behavioral Conditioning</h4>
                        <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                          Progressive human-mimicry activity curves and engagement priming to protect sender network health.
                        </p>
                      </div>
                      <ChevronRight size={14} className="text-muted-foreground group-hover:text-foreground shrink-0 mt-0.5 transition-transform group-hover:translate-x-0.5" />
                    </button>

                    <button
                      type="button"
                      onClick={() => { setShowGrowthHub(false); setShowDeliverabilityModal(true); }}
                      className="w-full text-left p-4 rounded-lg border border-border bg-background hover:bg-muted/40 transition-colors cursor-pointer flex items-start justify-between gap-3 group"
                    >
                      <div>
                        <h4 className="text-sm font-medium text-foreground">Autonomous DMARC / DKIM / SPF Sentry</h4>
                        <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                          Continuous DNS drift auditing, RFC 8058 compliance, and automated mailbox burnout rotation.
                        </p>
                      </div>
                      <ChevronRight size={14} className="text-muted-foreground group-hover:text-foreground shrink-0 mt-0.5 transition-transform group-hover:translate-x-0.5" />
                    </button>

                    <button
                      type="button"
                      onClick={() => { setShowGrowthHub(false); setShowDisplacementModal(true); }}
                      className="w-full text-left p-4 rounded-lg border border-border bg-background hover:bg-muted/40 transition-colors cursor-pointer flex items-start justify-between gap-3 group"
                    >
                      <div>
                        <h4 className="text-sm font-medium text-foreground">Technographic Displacement Radar</h4>
                        <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                          Immediate competitor rip-and-replace signals detecting sales stack churn across target accounts.
                        </p>
                      </div>
                      <ChevronRight size={14} className="text-muted-foreground group-hover:text-foreground shrink-0 mt-0.5 transition-transform group-hover:translate-x-0.5" />
                    </button>
                  </div>
                </div>

                {/* Section 4: Email Deliverability */}
                <div>
                  <h3 className="text-xs font-medium text-muted-foreground border-b border-border pb-1.5 mb-2.5">
                    Deliverability & Sender Reputation
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                    <button
                      type="button"
                      onClick={() => { setShowGrowthHub(false); setShowDeliverabilityModal(true); }}
                      className="w-full text-left p-4 rounded-lg border border-border bg-background hover:bg-muted/40 transition-colors cursor-pointer flex items-start justify-between gap-3 group"
                    >
                      <div>
                        <h4 className="text-xs font-semibold text-foreground">Email Deliverability & Spam Check</h4>
                        <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                          Verify SPF, DKIM, DMARC records and custom tracking domains to keep emails out of spam.
                        </p>
                      </div>
                      <ChevronRight size={14} className="text-muted-foreground group-hover:text-foreground shrink-0 mt-0.5 transition-transform group-hover:translate-x-0.5" />
                    </button>
                  </div>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Viral ROI Certificate & Wrapped Performance Card Studio */}
      {selectedCertCampaign && (
        <CampaignROICertificateModal
          isOpen={!!selectedCertCampaign}
          onClose={() => setSelectedCertCampaign(null)}
          campaignId={selectedCertCampaign.id}
          campaignName={selectedCertCampaign.name}
        />
      )}

      {/* Dynamic Multi-Armed Bandit Copy Optimizer & Trigger Radar Studio */}
      {banditCampaign && (
        <BanditOptimizerStudioModal
          campaignId={banditCampaign.id || undefined}
          onClose={() => setBanditCampaign(null)}
        />
      )}

      {/* Autonomous Social Pre-Warm & Omnichannel Cascade Studio */}
      {showPreWarmModal && (
        <PreWarmStudioModal
          onClose={() => setShowPreWarmModal(false)}
        />
      )}

      {/* LinkedIn Event Harvester & Multimodal Voice/Video Studio */}
      {showEventModal && (
        <EventMultimodalStudioModal
          onClose={() => setShowEventModal(false)}
        />
      )}

      {/* ABM Buying Committees & Multithreading Studio */}
      {showAbmModal && (
        <AbmMultithreadStudioModal
          onClose={() => setShowAbmModal(false)}
        />
      )}

      {/* Omnichannel Retargeting Cascade & 4-Tier Channel Routing Simulator */}
      {showOmnichannelModal && (
        <OmnichannelRetargetingStudioModal
          onClose={() => setShowOmnichannelModal(false)}
        />
      )}

      {/* Champion Job-Change Boomerang & Closed-Lost Revival Studio */}
      {showBoomerangModal && (
        <BoomerangRevivalStudioModal
          onClose={() => setShowBoomerangModal(false)}
        />
      )}

      {/* AI Send-Time Optimization (Predictive STO) & Prospect Activity Heatmap Studio */}
      {showStoModal && (
        <SendTimeOptimizationStudioModal
          isOpen={showStoModal}
          onClose={() => setShowStoModal(false)}
          canAiSto={isPro}
        />
      )}

      {/* Cold-Email Deliverability Pool & Custom Tracking Domain Studio */}
      {showDeliverabilityModal && (
        <DeliverabilityStudioModal
          isOpen={showDeliverabilityModal}
          onClose={() => setShowDeliverabilityModal(false)}
          canDeliverabilityPool={isPro}
        />
      )}

      {/* Inbound AI Reply Sentiment & OOO Auto-Snooze Studio */}
      {showSentimentModal && (
        <ReplySentimentStudioModal
          isOpen={showSentimentModal}
          onClose={() => setShowSentimentModal(false)}
        />
      )}

      {/* Autonomous Competitive Takeover & Tech Displacement Studio */}
      {showDisplacementModal && (
        <DisplacementStudioModal
          onClose={() => setShowDisplacementModal(false)}
        />
      )}

      {/* Executive Calendar Concierge & Frictionless Meeting Booking Studio */}
      {showCalendarModal && (
        <CalendarConciergeStudioModal
          onClose={() => setShowCalendarModal(false)}
        />
      )}
    </div>
  )
}