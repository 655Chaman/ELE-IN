import { fetcher, fetchWithAuth } from "@/lib/apiClient"
import { supabase } from "@/lib/supabase"
import { useState, useRef, useEffect, useMemo } from "react"
import { useParams, Link, useNavigate } from "react-router-dom"
import useSWR from "swr"
import {
  ArrowLeft, Activity, Users, CheckCircle2,
  AlertTriangle, Clock, RefreshCw, Play, Pause, Search, LayoutDashboard, Share2,
  Zap, Lock, ArrowRight, Shield, Download, ExternalLink, Copy, Check,
  ChevronLeft, ChevronRight, ChevronDown, Filter, ShieldAlert, Sparkles, UserCheck, UserX, Award,
  Brain, Flame, Mic, Building2, Layers, Repeat, X
} from "lucide-react"
import { toast } from "sonner"
import { dagToTree } from "@campaigns/eiTreeStore"
import { EISequenceTree } from "@/components/elein/EISequenceTree"
import { LeadTraceDrawer } from "@/components/leads/LeadTraceDrawer"
import { cn } from "@/lib/utils"
import { usePaywall } from "@/contexts/PaywallContext"
import { ElesiumLogo } from "@/components/ElesiumLogo"
import { AnimatedList } from "@/components/ui/animated-list"
import { NumberTicker } from "@/components/ui/number-ticker"
import { buildSafeCsv } from "@/lib/csvSanitize"
import { CampaignPreflightModal } from "./CampaignPreflightModal"
import { CampaignROICertificateModal } from "@/components/campaigns/CampaignROICertificateModal"
import { PreWarmStudioModal } from "@/components/campaigns/PreWarmStudioModal"
import { BanditOptimizerStudioModal } from "@/components/campaigns/BanditOptimizerStudioModal"
import { EventMultimodalStudioModal } from "@/components/campaigns/EventMultimodalStudioModal"
import { AbmMultithreadStudioModal } from "@/components/campaigns/AbmMultithreadStudioModal"
import { OmnichannelRetargetingStudioModal } from "@/components/campaigns/OmnichannelRetargetingStudioModal"
import { BoomerangRevivalStudioModal } from "@/components/campaigns/BoomerangRevivalStudioModal"

export function EleInCampaignDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { data: campaign, mutate, error } = useSWR(
    id ? `/api/elein/campaigns/${id}/detail` : null,
    fetcher
  )
  
  const { data: attribution } = useSWR(
    id ? `/api/elein/campaigns/${id}/attribution` : null,
    fetcher
  )

  const nodeAnalytics = attribution?.nodes?.reduce((acc: any, node: any) => {
    acc[node.node_id] = node
    return acc
  }, {})

  const { data: leads = [] } = useSWR(
    id ? `/api/elein/campaigns/${id}/leads` : null,
    fetcher
  )

  const [toggling, setToggling] = useState(false)
  const [search, setSearch] = useState("")
  const [statusFilter, setStatusFilter] = useState<string>("all")
  const [currentPage, setCurrentPage] = useState(1)
  const pageSize = 25
  const [selectedLeadForTrace, setSelectedLeadForTrace] = useState<any>(null)
  const [copiedLeadId, setCopiedLeadId] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return;
    const channel = supabase
      .channel(`campaign-status-${id}`)
      .on('postgres_changes', {
        event: 'UPDATE',
        schema: 'public',
        table: 'campaigns',
        filter: `id=eq.${id}`
      }, (payload) => {
        if (payload.new) {
          mutate((prev: any) => ({ ...prev, ...payload.new }), { revalidate: false })
        }
      })
      .subscribe();
    return () => { supabase.removeChannel(channel); };
  }, [id, mutate]);

  const campaignTreeNodes = useMemo(() => {
    if (!campaign) return [];
    try {
      const nodes = campaign.nodes || (campaign.nodes_json ? (typeof campaign.nodes_json === "string" ? JSON.parse(campaign.nodes_json) : campaign.nodes_json) : []);
      const edges = campaign.edges || (campaign.edges_json ? (typeof campaign.edges_json === "string" ? JSON.parse(campaign.edges_json) : campaign.edges_json) : []);
      return dagToTree(nodes, edges);
    } catch (e) {
      console.error("Failed to parse campaign graph", e);
      return [];
    }
  }, [campaign?.id, typeof campaign?.nodes_json === "string" ? campaign.nodes_json : JSON.stringify(campaign?.nodes_json), typeof campaign?.edges_json === "string" ? campaign.edges_json : JSON.stringify(campaign?.edges_json)]);

  const { openPaywall } = usePaywall()
  const { data: billingData } = useSWR<{ tier?: string }>(
    '/api/elein/workspaces/billing',
    fetcher
  )
  const tier = billingData?.tier || 'FREE'
  const isPro = tier === 'PRO' || tier === 'ENTERPRISE'

  const hasRestrictedNodes = useMemo(() => {
    if (!campaign?.nodes && !campaign?.nodes_json) return false
    try {
      const nodes = campaign.nodes || (typeof campaign.nodes_json === "string" ? JSON.parse(campaign.nodes_json) : campaign.nodes_json)
      if (!Array.isArray(nodes)) return false
      const restricted = ["apify_scrape", "apollo_enrich", "find_email", "find_personal_email", "find_tech_stack", "find_funding_round", "ai_score_icp", "icp_score_gate"]
      return nodes.some((n: any) => restricted.includes(n.type || n.node_type))
    } catch {
      return false
    }
  }, [campaign])

  const togglingRef = useRef(false);
  const [showPreflightModal, setShowPreflightModal] = useState(false);
  const [showRoiCertModal, setShowRoiCertModal] = useState(false);
  const [showBanditModal, setShowBanditModal] = useState(false);
  const [showPreWarmModal, setShowPreWarmModal] = useState(false);
  const [selectedLeadForPrewarm, setSelectedLeadForPrewarm] = useState<{ id: string; name: string } | null>(null);
  const [showEventModal, setShowEventModal] = useState(false);
  const [showAbmModal, setShowAbmModal] = useState(false);
  const [showOmnichannelModal, setShowOmnichannelModal] = useState(false);
  const [showBoomerangModal, setShowBoomerangModal] = useState(false);
  const [showGrowthMenu, setShowGrowthMenu] = useState(false);
  const growthMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (growthMenuRef.current && !growthMenuRef.current.contains(event.target as Node)) {
        setShowGrowthMenu(false);
      }
    }
    if (showGrowthMenu) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [showGrowthMenu]);

  const toggleStatus = async () => {
    if (!campaign || togglingRef.current || toggling) return
    togglingRef.current = true;
    setToggling(true)
    const action = campaign.status === 'ACTIVE' ? 'pause' : 'activate'
    try {
      const res = await fetchWithAuth(`/api/elein/campaigns/${id}/${action}`, { method: 'PATCH' })
      if (!res.ok) {
        let errMsg = `Failed to ${action} campaign`
        try {
          const errJson = await res.json()
          errMsg = errJson.detail || errMsg
        } catch {
          const text = await res.text()
          if (text) errMsg = text
        }
        
        if (errMsg === "no_active_senders") {
          toast.error("No active sender accounts linked to this campaign. Please connect or activate a LinkedIn account first.")
        } else if (errMsg === "insufficient_credits") {
          openPaywall({ featureName: "Campaign Activation Credits" })
          toast.info("Credit balance exhausted. Top up credits to activate this campaign.")
        } else if (res.status === 403 || errMsg.includes("Free Tier") || errMsg.includes("upgrade") || errMsg.includes("Campaign limit reached") || errMsg.includes("enrichment") || errMsg.includes("Bayesian")) {
          const feature = errMsg.toLowerCase().includes("enrichment") || errMsg.toLowerCase().includes("scraping")
            ? "Enrichment & Scraping Nodes"
            : errMsg.toLowerCase().includes("bayesian") || errMsg.toLowerCase().includes("icp")
            ? "Bayesian ICP Machine Learning"
            : "Active Campaigns Limit"
          openPaywall({ featureName: feature })
          toast.info(errMsg)
        } else {
          toast.error(errMsg)
        }
        return
      }
      toast.success(action === 'activate' ? "Campaign activated  -  scheduler is live" : "Campaign paused  -  active delay timers frozen safely")
      mutate()
    } catch (e: any) {
      toast.error(e.message || `Failed to ${action} campaign`)
    } finally {
      togglingRef.current = false;
      setToggling(false)
      mutate()
    }
  }

  // Filter leads by search query and status filter
  const filteredLeads = useMemo(() => {
    return leads.filter((l: any) => {
      const fullName = ((l.kdm_first || "") + " " + (l.kdm_last || "")).toLowerCase()
      const comp = (l.company_name || "").toLowerCase()
      const title = (l.job_title || "").toLowerCase()
      const q = search.toLowerCase().trim()
      const matchesSearch = !q || fullName.includes(q) || comp.includes(q) || title.includes(q)

      const status = (l.status || "").toLowerCase()
      const matchesStatus = 
        statusFilter === "all" ? true :
        statusFilter === "running" ? status === "running" :
        statusFilter === "completed" ? (status === "completed" || status === "exited") :
        statusFilter === "error" ? (status === "error" || status === "failed") :
        statusFilter === "pending" ? (status === "pending" || status === "waiting") :
        true

      return matchesSearch && matchesStatus
    })
  }, [leads, search, statusFilter])

  // Reset page when filter changes
  useEffect(() => {
    setCurrentPage(1)
  }, [search, statusFilter])

  // Pagination slice
  const totalPages = Math.ceil(filteredLeads.length / pageSize) || 1
  const paginatedLeads = useMemo(() => {
    const start = (currentPage - 1) * pageSize
    return filteredLeads.slice(start, start + pageSize)
  }, [filteredLeads, currentPage, pageSize])

  // Status counts for filter chips
  const statusCounts = useMemo(() => {
    let running = 0, pending = 0, completed = 0, error = 0
    for (const l of leads) {
      const s = (l.status || "").toLowerCase()
      if (s === "running") running++
      else if (s === "pending" || s === "waiting") pending++
      else if (s === "completed" || s === "exited") completed++
      else if (s === "error" || s === "failed") error++
    }
    return { all: leads.length, running, pending, completed, error }
  }, [leads])

  // Live execution telemetry events for AnimatedList
  const telemetryEvents = useMemo(() => {
    if (!leads || leads.length === 0) return []
    return leads.slice(0, 6).map((l: any, i: number) => {
      const name = `${l.kdm_first || ''} ${l.kdm_last || ''}`.trim() || 'Prospect'
      const status = (l.status || 'pending').toLowerCase()
      const time = l.updated_at ? new Date(l.updated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'Active'
      const actionText = 
        status === 'completed' || status === 'exited'
          ? 'Sequence execution completed'
          : status === 'running'
          ? 'Step in flight - cadence delay running'
          : status === 'error' || status === 'failed'
          ? 'Action required - verify sender limits'
          : 'Enrolled in sequence pipeline'
      return {
        id: l.id || l.enrollment_id || `lead-${i}`,
        name,
        company: l.company_name || 'Target Account',
        action: actionText,
        status,
        time,
      }
    })
  }, [leads])

  // Export Campaign Leads to CSV with Formula Injection Defense
  const handleExportCsv = () => {
    if (!leads || leads.length === 0) {
      toast.info("No leads available in this campaign to export")
      return
    }
    const headers = ["Lead ID", "First Name", "Last Name", "Job Title", "Company", "Status", "LinkedIn URL", "Updated At"]
    const rows = leads.map((l: any) => [
      l.id || l.opportunity_id || "",
      l.kdm_first || "",
      l.kdm_last || "",
      l.job_title || "",
      l.company_name || "",
      l.status || "pending",
      l.linkedin_url || "",
      l.updated_at || l.next_run_at || ""
    ])
    const csvContent = buildSafeCsv(headers, rows)
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" })
    const url = URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.setAttribute("href", url)
    link.setAttribute("download", `${(campaign?.name || 'campaign').toLowerCase().replace(/\s+/g, '_')}_leads_${new Date().toISOString().slice(0, 10)}.csv`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    toast.success(`Exported ${leads.length} leads to CSV!`)
  }

  if (error) {
    return (
      <div className="min-h-full flex items-center justify-center p-8">
        <div className="text-center space-y-4 max-w-sm">
          <AlertTriangle className="mx-auto h-8 w-8 text-destructive" />
          <h2 className="text-lg font-bold text-foreground">Campaign not found</h2>
          <p className="text-xs text-muted-foreground">This campaign may have been deleted or moved to another workspace.</p>
          <Link to="/elein/campaigns" className="inline-flex items-center gap-1.5 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-xs font-bold hover:bg-primary/90 transition-all shadow-sm">
            <ArrowLeft size={14} /> Back to Campaigns
          </Link>
        </div>
      </div>
    )
  }

  if (!campaign) {
    return (
      <div className="min-h-full p-8 space-y-8 animate-pulse max-w-7xl mx-auto">
        <div className="flex gap-4 items-center">
          <div className="w-8 h-8 rounded-lg bg-muted/40" />
          <div className="h-8 w-64 rounded-lg bg-muted/40" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map(i => <div key={i} className="h-24 rounded-lg bg-muted/30" />)}
        </div>
        <div className="h-64 rounded-lg bg-muted/20" />
      </div>
    )
  }

  const hasSenders = campaign.accounts && campaign.accounts.length > 0

  return (
    <div className="min-h-full max-w-7xl mx-auto p-8 space-y-8 font-sans">
      {/* Pre-Flight Launch Cockpit Gate */}
      <CampaignPreflightModal
        isOpen={showPreflightModal}
        onClose={() => setShowPreflightModal(false)}
        onConfirmLaunch={toggleStatus}
        campaignId={campaign.id}
        campaignName={campaign.name}
      />

      {/* Viral ROI Certificate & Wrapped Performance Card Studio */}
      <CampaignROICertificateModal
        isOpen={showRoiCertModal}
        onClose={() => setShowRoiCertModal(false)}
        campaignId={campaign.id}
        campaignName={campaign.name}
      />

      {/* Dynamic Multi-Armed Bandit Copy Optimizer & Trigger Radar Studio */}
      {showBanditModal && (
        <BanditOptimizerStudioModal
          campaignId={campaign.id}
          onClose={() => setShowBanditModal(false)}
        />
      )}

      {/* Autonomous Social Pre-Warm & Omnichannel Cascade Studio */}
      {(showPreWarmModal || selectedLeadForPrewarm) && (
        <PreWarmStudioModal
          initialLeadId={selectedLeadForPrewarm?.id}
          initialLeadName={selectedLeadForPrewarm?.name}
          onClose={() => {
            setShowPreWarmModal(false);
            setSelectedLeadForPrewarm(null);
          }}
        />
      )}

      {/* LinkedIn Event Harvester & Multimodal Voice/Video Studio */}
      {showEventModal && (
        <EventMultimodalStudioModal
          campaignId={campaign.id}
          onClose={() => setShowEventModal(false)}
        />
      )}

      {/* ABM Buying Committees & Multithreading Studio */}
      {showAbmModal && (
        <AbmMultithreadStudioModal
          campaignId={campaign.id}
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
          campaignId={campaign.id}
          onClose={() => setShowBoomerangModal(false)}
        />
      )}

      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between pb-2 border-b border-border/40">
        <div className="space-y-1.5">
          <Link to="/elein/campaigns" className="inline-flex items-center gap-2 text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors">
            <ArrowLeft size={14} /> Back to Campaigns
          </Link>
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground">{campaign.name}</h1>
            <span className={cn(
              "px-3 py-1 text-xs font-bold uppercase tracking-wider rounded-full border flex items-center gap-1.5",
              campaign.status === 'ACTIVE' ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" :
              campaign.status === 'PAUSED' ? "bg-amber-500/10 text-amber-400 border-amber-500/20" :
              "bg-muted text-muted-foreground border-border"
            )}>
              {campaign.status === 'ACTIVE' && <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />}
              {campaign.status}
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            {leads.length} total prospects enrolled • {campaign.accounts?.length || 0} active sender accounts
          </p>
        </div>

        {/* Primary Action Controls (Streamlined: 3 Main Actions + Dropdown) */}
        <div className="flex items-center gap-2.5 flex-wrap">
          {/* 1. Primary Operational Action: Launch / Pause Campaign */}
          <button
            type="button"
            onClick={() => {
              if (campaign.status === 'ACTIVE') {
                toggleStatus()
              } else {
                setShowPreflightModal(true)
              }
            }}
            disabled={toggling || campaign.status === 'DRAFT'}
            className={cn(
              "flex items-center gap-2 px-4 py-2 font-bold text-xs rounded-lg transition-all disabled:opacity-50 cursor-pointer shadow-sm",
              campaign.status === 'ACTIVE'
                ? "bg-amber-500/15 hover:bg-amber-500/25 text-amber-300 border border-amber-500/30"
                : "bg-emerald-600 hover:bg-emerald-500 text-white"
            )}
          >
            {toggling ? (
              <RefreshCw size={14} className="animate-spin" />
            ) : campaign.status === 'ACTIVE' ? (
              <Pause size={14} />
            ) : !isPro && hasRestrictedNodes ? (
              <Lock size={14} className="text-amber-500" />
            ) : (
              <Play size={14} className="fill-current" />
            )}
            <span>
              {toggling
                ? (campaign.status === 'ACTIVE' ? 'Pausing...' : 'Starting...')
                : campaign.status === 'ACTIVE'
                ? 'Pause Campaign'
                : !isPro && hasRestrictedNodes
                ? 'Upgrade to Start'
                : 'Launch Campaign'}
            </span>
          </button>

          {/* 2. Secondary Action: Edit Sequence */}
          <button
            type="button"
            onClick={() => navigate(`/elein/campaigns/new?edit=${campaign.id}`)}
            className="flex items-center gap-1.5 px-3.5 py-2 bg-muted/40 hover:bg-muted text-foreground font-semibold text-xs rounded-lg transition-colors border border-border/60 cursor-pointer shadow-xs"
          >
            <LayoutDashboard size={14} />
            <span>Edit Sequence</span>
          </button>

          {/* 3. Elesium Growth Tools Dropdown Menu */}
          <div className="relative" ref={growthMenuRef}>
            <button
              type="button"
              aria-haspopup="true"
              aria-expanded={showGrowthMenu}
              onClick={() => setShowGrowthMenu(prev => !prev)}
              className="flex items-center gap-2 px-3.5 py-2 bg-gradient-to-r from-blue-600/10 via-cyan-500/10 to-blue-600/10 hover:from-blue-600/20 hover:to-cyan-500/20 text-foreground font-semibold text-xs rounded-lg border border-blue-500/30 transition-all cursor-pointer shadow-xs"
            >
              <ElesiumLogo size={16} className="shrink-0" />
              <span>Elesium Growth Tools</span>
              <ChevronDown size={14} className={cn("text-muted-foreground transition-transform duration-200", showGrowthMenu && "rotate-180")} />
            </button>

            {showGrowthMenu && (
              <div className="absolute right-0 top-full mt-2 w-80 rounded-lg border border-border/80 bg-card/95 backdrop-blur-md shadow-2xl p-2 z-50 animate-in fade-in zoom-in-95 duration-100">
                {/* Brand header */}
                <div className="px-3 py-2 border-b border-border/60 mb-1 flex items-center justify-between">
                  <div>
                    <div className="text-[11px] font-bold uppercase tracking-wider text-primary flex items-center gap-1.5">
                      <ElesiumLogo size={14} className="shrink-0" />
                      <span>Elesium Growth Suite</span>
                    </div>
                    <div className="text-[10px] text-muted-foreground">
                      Powered by <a href="https://elesium.online" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline font-semibold">elesium.online</a>
                    </div>
                  </div>
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-primary/10 text-primary font-bold">
                    8 Tools
                  </span>
                </div>

                <div className="space-y-1 text-xs">
                  {/* Tool 1: Elesium Copy Intelligence */}
                  <button
                    type="button"
                    onClick={() => {
                      setShowBanditModal(true);
                      setShowGrowthMenu(false);
                    }}
                    className="w-full text-left p-2.5 rounded-lg hover:bg-muted/60 transition-colors flex items-start gap-2.5 group cursor-pointer"
                  >
                    <div className="w-8 h-8 rounded-lg bg-blue-500/10 flex items-center justify-center shrink-0 mt-0.5 p-1.5">
                      <ElesiumLogo size={20} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-bold text-foreground flex items-center justify-between">
                        <span>Elesium Copy Intelligence</span>
                        <span className="text-[10px] px-1.5 py-0.2 rounded bg-blue-500/10 text-blue-500 font-semibold">Bandit</span>
                      </div>
                      <p className="text-[11px] text-muted-foreground line-clamp-1">
                        Dynamic A/B testing across connection notes & emails
                      </p>
                    </div>
                  </button>

                  {/* Tool 2: Pre-Flight Gate */}
                  <button
                    type="button"
                    onClick={() => {
                      setShowPreflightModal(true);
                      setShowGrowthMenu(false);
                    }}
                    className="w-full text-left p-2.5 rounded-lg hover:bg-muted/60 transition-colors flex items-start gap-2.5 group cursor-pointer"
                  >
                    <div className="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-500 flex items-center justify-center shrink-0 mt-0.5">
                      <Shield size={16} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-bold text-foreground">Pre-Flight Launch Gate</div>
                      <p className="text-[11px] text-muted-foreground line-clamp-1">
                        Inspect readiness, sender health & spam flags
                      </p>
                    </div>
                  </button>

                  {/* Tool 3: Social Pre-Warm */}
                  <button
                    type="button"
                    onClick={() => {
                      setShowPreWarmModal(true);
                      setShowGrowthMenu(false);
                    }}
                    className="w-full text-left p-2.5 rounded-lg hover:bg-muted/60 transition-colors flex items-start gap-2.5 group cursor-pointer"
                  >
                    <div className="w-8 h-8 rounded-lg bg-amber-500/10 text-amber-500 flex items-center justify-center shrink-0 mt-0.5">
                      <Flame size={16} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-bold text-foreground">Social Feed Pre-Warm</div>
                      <p className="text-[11px] text-muted-foreground line-clamp-1">
                        Warm leads with likes & visits before connecting
                      </p>
                    </div>
                  </button>

                  {/* Tool 4: Event & Voice Studio */}
                  <button
                    type="button"
                    onClick={() => {
                      setShowEventModal(true);
                      setShowGrowthMenu(false);
                    }}
                    className="w-full text-left p-2.5 rounded-lg hover:bg-muted/60 transition-colors flex items-start gap-2.5 group cursor-pointer"
                  >
                    <div className="w-8 h-8 rounded-lg bg-indigo-500/10 text-indigo-500 flex items-center justify-center shrink-0 mt-0.5">
                      <Mic size={16} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-bold text-foreground">Event & Voice Studio</div>
                      <p className="text-[11px] text-muted-foreground line-clamp-1">
                        LinkedIn Event harvester & audio voice prospecting
                      </p>
                    </div>
                  </button>

                  {/* Tool 5: ABM Multithreading */}
                  <button
                    type="button"
                    onClick={() => {
                      setShowAbmModal(true);
                      setShowGrowthMenu(false);
                    }}
                    className="w-full text-left p-2.5 rounded-lg hover:bg-muted/60 transition-colors flex items-start gap-2.5 group cursor-pointer"
                  >
                    <div className="w-8 h-8 rounded-lg bg-rose-500/10 text-rose-500 flex items-center justify-center shrink-0 mt-0.5">
                      <Building2 size={16} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-bold text-foreground">ABM Multithreading</div>
                      <p className="text-[11px] text-muted-foreground line-clamp-1">
                        Target economic buyers & committee champions
                      </p>
                    </div>
                  </button>

                  {/* Tool 6: Omnichannel Cascade */}
                  <button
                    type="button"
                    onClick={() => {
                      setShowOmnichannelModal(true);
                      setShowGrowthMenu(false);
                    }}
                    className="w-full text-left p-2.5 rounded-lg hover:bg-muted/60 transition-colors flex items-start gap-2.5 group cursor-pointer"
                  >
                    <div className="w-8 h-8 rounded-lg bg-cyan-500/10 text-cyan-500 flex items-center justify-center shrink-0 mt-0.5">
                      <Layers size={16} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-bold text-foreground">Omnichannel Cascade</div>
                      <p className="text-[11px] text-muted-foreground line-clamp-1">
                        LinkedIn to email 4-tier fallback routing
                      </p>
                    </div>
                  </button>

                  {/* Tool 7: Boomerang & Revival */}
                  <button
                    type="button"
                    onClick={() => {
                      setShowBoomerangModal(true);
                      setShowGrowthMenu(false);
                    }}
                    className="w-full text-left p-2.5 rounded-lg hover:bg-muted/60 transition-colors flex items-start gap-2.5 group cursor-pointer"
                  >
                    <div className="w-8 h-8 rounded-lg bg-teal-500/10 text-teal-500 flex items-center justify-center shrink-0 mt-0.5">
                      <Repeat size={16} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-bold text-foreground">Boomerang & Revival</div>
                      <p className="text-[11px] text-muted-foreground line-clamp-1">
                        Champion job change & closed-lost revival
                      </p>
                    </div>
                  </button>

                  {/* Tool 8: ROI Certificate */}
                  <button
                    type="button"
                    onClick={() => {
                      setShowRoiCertModal(true);
                      setShowGrowthMenu(false);
                    }}
                    className="w-full text-left p-2.5 rounded-lg hover:bg-muted/60 transition-colors flex items-start gap-2.5 group cursor-pointer"
                  >
                    <div className="w-8 h-8 rounded-lg bg-sky-500/10 text-sky-500 flex items-center justify-center shrink-0 mt-0.5">
                      <Award size={16} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-bold text-foreground">Viral ROI Certificate</div>
                      <p className="text-[11px] text-muted-foreground line-clamp-1">
                        Download branded campaign performance card
                      </p>
                    </div>
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* 4. Share Icon Button */}
          <button
            type="button"
            onClick={() => {
              navigator.clipboard.writeText(window.location.href);
              toast.success("Campaign link copied to clipboard");
            }}
            className="flex items-center gap-1.5 px-3 py-2 bg-muted/40 hover:bg-muted text-foreground font-semibold text-xs rounded-lg transition-colors border border-border/60 cursor-pointer shadow-xs"
            title="Share campaign link"
            aria-label="Share campaign link"
          >
            <Share2 size={14} />
          </button>
        </div>
      </div>

      {/* Zero Senders Environmental Alert Banner (Layer 1) */}
      {!hasSenders && (
        <div className="p-4 rounded-lg bg-amber-500/10 border border-amber-500/25 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-2.5 text-amber-300 font-semibold">
            <ShieldAlert size={18} className="shrink-0 text-amber-400" />
            <span>No LinkedIn sender accounts are attached to this campaign. Outreach cannot execute until senders are assigned.</span>
          </div>
          <button
            type="button"
            onClick={() => navigate(`/elein/campaigns/new?edit=${campaign.id}`)}
            className="px-3.5 py-1.5 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 font-bold shrink-0 self-start sm:self-auto transition-colors cursor-pointer"
          >
            Attach Senders Now →
          </button>
        </div>
      )}

      {/* Pro Preflight Pay Ramp Banner */}
      {!isPro && (
        <div className="p-5 rounded-lg border border-primary/20 bg-gradient-to-r from-primary/10 via-primary/[0.03] to-transparent shadow-sm flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-start gap-3.5">
            <div className="p-2.5 bg-primary/15 rounded-lg text-primary mt-0.5 shrink-0">
              <Zap size={20} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-foreground">
                  {hasRestrictedNodes ? "Pro Enrichment Sequence Detected" : "Multi-Campaign Scaling & Sender Rotation"}
                </h3>
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-primary/15 text-primary border border-primary/25">
                  Growth Pro
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-1 max-w-2xl leading-relaxed">
                {hasRestrictedNodes
                  ? "This sequence includes deep web scraping or data enrichment nodes. Upgrade to Growth Pro to run live automated email lookups and Apify extraction."
                  : "Free plan is limited to 1 active campaign. Upgrade to Growth Pro to run up to 20 campaigns simultaneously across multiple LinkedIn sender accounts."}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => openPaywall({ featureName: hasRestrictedNodes ? "Enrichment & Scraping Nodes" : "Active Campaigns Limit" })}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-xs font-bold hover:bg-primary/90 transition-all shadow-sm shrink-0 whitespace-nowrap cursor-pointer"
          >
            <span>{hasRestrictedNodes ? "Unlock Enrichment" : "Unlock 20 Campaigns"}</span>
            <ArrowRight size={14} />
          </button>
        </div>
      )}

      {/* 4 Core Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "Enrolled Audience", rawValue: campaign.stats?.total_leads ?? 0, isPercent: false, icon: Users, color: "text-primary", bg: "bg-primary/10", border: "border-primary/20" },
          { label: "In-Flight Running", rawValue: campaign.stats?.running ?? 0, isPercent: false, icon: Activity, color: "text-blue-500", bg: "bg-blue-500/10", border: "border-blue-500/20" },
          { label: "Completed Sequences", rawValue: campaign.stats?.completed ?? 0, isPercent: false, icon: CheckCircle2, color: "text-emerald-500", bg: "bg-emerald-500/10", border: "border-emerald-500/20" },
          { label: "Funnel Conversion Rate", rawValue: Number(((campaign.stats?.conversion_rate ?? 0) * 100).toFixed(1)), isPercent: true, icon: RefreshCw, color: "text-indigo-500", bg: "bg-indigo-500/10", border: "border-indigo-500/20" }
        ].map((stat, i) => (
          <div key={i} className="bg-card border border-border/80 p-5 rounded-lg flex items-center gap-4 shadow-sm hover:border-border transition-all">
            <div className={cn("p-3 rounded-lg border flex items-center justify-center shrink-0", stat.color, stat.bg, stat.border)}>
              <stat.icon size={20} />
            </div>
            <div>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">{stat.label}</p>
              <h3 className="text-2xl font-bold text-foreground mt-0.5 tabular-nums">
                <NumberTicker value={stat.rawValue} decimalPlaces={stat.isPercent ? 1 : 0} />
                {stat.isPercent ? "%" : ""}
              </h3>
            </div>
          </div>
        ))}
      </div>

      {/* Accounts & Workflow Topography */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-muted/10 border border-border/60 rounded-lg p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
              <LayoutDashboard size={14} className="text-primary" /> Active Sequence DAG Nodes
            </h3>
            <span className="text-[11px] font-mono text-muted-foreground">
              {campaign.nodes?.length || 0} Steps
            </span>
          </div>

          <div className="flex items-center flex-wrap gap-2.5">
            {campaign.nodes && campaign.nodes.length > 0 ? (
              campaign.nodes.map((node: any, idx: number) => (
                <div key={node.id} className="flex items-center gap-2">
                  <div className="px-3.5 py-2 rounded-lg border border-border/60 bg-background text-xs font-semibold text-foreground flex items-center gap-1.5 shadow-xs">
                    <span className="w-1.5 h-1.5 rounded-full bg-primary" />
                    <span>{node.data?.label || node.type}</span>
                  </div>
                  {idx < campaign.nodes.length - 1 && (
                    <ArrowLeft size={13} className="text-muted-foreground/60 rotate-180" />
                  )}
                </div>
              ))
            ) : (
              <p className="text-xs text-muted-foreground">No sequence steps defined yet.</p>
            )}
          </div>
        </div>

        {/* Senders Station */}
        <div className="bg-muted/10 border border-border/60 rounded-lg p-6 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
              <Users size={14} className="text-emerald-400" /> Assigned Senders
            </h3>
            <Link to="/elein/accounts" className="text-[11px] text-primary hover:underline font-semibold">
              Manage
            </Link>
          </div>

          <div className="space-y-2">
            {campaign.accounts && campaign.accounts.length > 0 ? (
              campaign.accounts.map((acc: any) => (
                <div key={acc.id} className="flex items-center gap-3 p-2.5 rounded-lg border border-border/40 bg-background/60 shadow-xs">
                  <div className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center font-bold text-xs uppercase shrink-0">
                    {acc.name ? acc.name.substring(0, 2) : "LK"}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-bold text-foreground truncate">{acc.name}</p>
                    <p className="text-[11px] text-muted-foreground truncate font-mono">
                      {acc.linkedin_profile_url || "LinkedIn Session Active"}
                    </p>
                  </div>
                  <span className="w-2 h-2 rounded-full bg-emerald-400 shrink-0" title="Account connected" />
                </div>
              ))
            ) : (
              <div className="p-3 rounded-lg border border-dashed border-border/60 text-center text-xs text-muted-foreground">
                No accounts linked.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Sequence Copy & Multi-Arm Routing Banner */}
      <div className="p-4 rounded-lg border border-border bg-card flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-muted flex items-center justify-center shrink-0 text-foreground border border-border">
            <Layers size={16} />
          </div>
          <div>
            <div className="font-semibold text-foreground">
              Sequence Copy & Variant Routing
            </div>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              Evaluate connection notes, follow-ups, and email fallbacks with multi-arm traffic routing.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setShowBanditModal(true)}
          className="px-3.5 py-2 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground font-medium shrink-0 self-start sm:self-auto transition-all text-xs cursor-pointer flex items-center gap-1.5"
        >
          <span>Open Copy Optimizer</span>
          <ArrowRight size={13} />
        </button>
      </div>

      {/* Visual Sequence DAG Canvas */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-semibold text-foreground uppercase tracking-wider flex items-center gap-2">
            <LayoutDashboard size={14} className="text-primary" /> Visual Sequence Canvas & Node Attribution
          </h3>
          <span className="text-xs text-muted-foreground">
            Read-only execution projection
          </span>
        </div>
        <div className="border border-border/80 rounded-lg overflow-hidden relative h-[460px] shadow-sm bg-card">
          <div className="absolute inset-0 pointer-events-auto">
            <EISequenceTree readOnly={true} initialNodes={campaignTreeNodes} nodeAnalytics={nodeAnalytics} />
          </div>
        </div>
      </div>

      {/* Live Execution Telemetry Feed (AnimatedList) */}
      {telemetryEvents.length > 0 && (
        <div className="bg-card border border-border/80 rounded-lg p-5 shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Live Execution Telemetry
              </h3>
            </div>
            <span className="text-[11px] font-mono text-muted-foreground">
              {telemetryEvents.length} Recent Activity Events
            </span>
          </div>

          <AnimatedList delay={1200} className="w-full">
            {telemetryEvents.map((evt: any) => (
              <div
                key={evt.id}
                className="w-full flex items-center justify-between p-3 rounded-lg border border-border/50 bg-background/80 hover:bg-muted/40 transition-colors text-xs"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-7 h-7 rounded-lg bg-primary/10 text-primary border border-primary/20 flex items-center justify-center font-bold text-[10px] shrink-0 font-mono">
                    {evt.name[0] || "L"}
                  </div>
                  <div className="min-w-0">
                    <p className="font-semibold text-foreground truncate">
                      {evt.name} <span className="font-normal text-muted-foreground">at {evt.company}</span>
                    </p>
                    <p className="text-[11px] text-muted-foreground font-mono">
                      {evt.action}
                    </p>
                  </div>
                </div>
                <span className="text-[10px] font-mono text-muted-foreground shrink-0 ml-2">
                  {evt.time}
                </span>
              </div>
            ))}
          </AnimatedList>
        </div>
      )}

      {/* Lead Matrix Station */}
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h3 className="text-lg font-bold text-foreground flex items-center gap-2">
              Lead Matrix & Execution Inspector
              <span className="text-xs font-mono font-bold px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
                {filteredLeads.length} of {leads.length}
              </span>
            </h3>
            <p className="text-xs text-muted-foreground">
              Inspect live lead progression, node execution traces, and individual contact records.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleExportCsv}
              disabled={leads.length === 0}
              className="px-3 py-1.5 rounded-lg bg-background hover:bg-muted border border-border/60 text-xs font-semibold text-foreground flex items-center gap-1.5 transition-colors disabled:opacity-40 cursor-pointer shadow-xs"
            >
              <Download size={13} className="text-primary" />
              <span>Export CSV</span>
            </button>

            <div className="relative w-64">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={14} />
              <input 
                type="text" 
                placeholder="Search leads, companies..." 
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full pl-8 pr-4 py-1.5 bg-background border border-border/60 rounded-lg text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-primary/50"
              />
              {search && (
                <button
                  type="button"
                  aria-label="Clear search"
                  onClick={() => setSearch("")}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground text-xs cursor-pointer"
                >
                  <X size={12} />
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Lead Status Filter Chips */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none">
          {[
            { id: "all", label: "All Leads", count: statusCounts.all },
            { id: "running", label: "Running", count: statusCounts.running },
            { id: "pending", label: "Pending", count: statusCounts.pending },
            { id: "completed", label: "Completed", count: statusCounts.completed },
            { id: "error", label: "Attention Needed", count: statusCounts.error }
          ].map(f => (
            <button
              type="button"
              key={f.id}
              onClick={() => setStatusFilter(f.id)}
              className={cn(
                "px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all cursor-pointer flex items-center gap-1.5",
                statusFilter === f.id
                  ? "bg-primary text-primary-foreground font-semibold shadow-xs"
                  : "bg-muted/30 text-muted-foreground hover:text-foreground hover:bg-muted/50 border border-border/40"
              )}
            >
              <span>{f.label}</span>
              <span className={cn(
                "text-[10px] px-1.5 py-0.2 rounded-full font-mono",
                statusFilter === f.id ? "bg-white/20 text-white" : "bg-muted text-muted-foreground"
              )}>
                {f.count}
              </span>
            </button>
          ))}
        </div>

        {/* Table Container */}
        <div className="border border-border/60 rounded-lg overflow-hidden bg-card shadow-sm">
          <table className="w-full text-left text-xs whitespace-nowrap">
            <thead className="bg-muted/30 text-muted-foreground uppercase text-[10px] tracking-wider font-semibold border-b border-border/60">
              <tr>
                <th className="px-5 py-3.5">Prospect & Title</th>
                <th className="px-5 py-3.5">Company</th>
                <th className="px-5 py-3.5">Execution Status</th>
                <th className="px-5 py-3.5">Last Scheduled / Run</th>
                <th className="px-5 py-3.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {paginatedLeads.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-12 text-center text-muted-foreground">
                    <div className="max-w-xs mx-auto space-y-2">
                      <p className="font-semibold text-foreground">No leads found</p>
                      <p className="text-[11px]">
                        {search || statusFilter !== "all" 
                          ? "Try clearing your search query or status filter."
                          : "Enroll leads into this campaign to begin outreach execution."}
                      </p>
                      {search || statusFilter !== "all" ? (
                        <button
                          type="button"
                          onClick={() => {
                            setSearch("")
                            setStatusFilter("all")
                          }}
                          className="text-xs text-primary font-bold hover:underline cursor-pointer"
                        >
                          Reset Filters
                        </button>
                      ) : (
                        <div className="pt-2">
                          <Link
                            to={`/elein/campaigns/${id}/edit?step=1`}
                            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors shadow-xs"
                          >
                            <Users size={12} />
                            <span>Select Audience &amp; Enroll Leads</span>
                          </Link>
                        </div>
                      )}
                    </div>
                  </td>
                </tr>
              ) : (
                paginatedLeads.map((lead: any) => {
                  const leadName = `${lead.kdm_first || ''} ${lead.kdm_last || ''}`.trim() || 'Prospect'
                  const status = (lead.status || 'pending').toLowerCase()
                  return (
                    <tr 
                      key={lead.id || lead.enrollment_id} 
                      className="hover:bg-muted/20 transition-colors group cursor-pointer"
                      onClick={() => setSelectedLeadForTrace(lead)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          setSelectedLeadForTrace(lead);
                        }
                      }}
                      tabIndex={0}
                      role="button"
                      aria-label={`View execution trace for ${leadName}`}
                    >
                      <td className="px-5 py-3.5">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-primary/10 text-primary border border-primary/20 flex items-center justify-center font-bold text-xs shrink-0">
                            {(lead.kdm_first?.[0] || leadName[0] || "?").toUpperCase()}
                          </div>
                          <div className="min-w-0">
                            <p className="font-bold text-foreground group-hover:text-primary transition-colors truncate">
                              {leadName}
                            </p>
                            <p className="text-[11px] text-muted-foreground truncate max-w-[220px]">
                              {lead.job_title || "Lead Contact"}
                            </p>
                          </div>
                        </div>
                      </td>

                      <td className="px-5 py-3.5 text-muted-foreground font-medium">
                        {lead.company_name || " - "}
                      </td>

                      <td className="px-5 py-3.5">
                        <span className={cn(
                          "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold border",
                          status === 'completed' || status === 'exited'
                            ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                            : status === 'error' || status === 'failed'
                            ? "bg-rose-500/10 text-rose-400 border-rose-500/20"
                            : status === 'running'
                            ? "bg-primary/10 text-primary border-primary/20"
                            : "bg-muted text-muted-foreground border-border/40"
                        )}>
                          {status === 'running' && <Clock size={11} className="animate-spin" />}
                          {lead.status || 'Pending'}
                        </span>
                      </td>

                      <td className="px-5 py-3.5 text-muted-foreground text-[11px] font-mono">
                        {new Date(lead.updated_at || lead.next_run_at || new Date().toISOString()).toLocaleDateString()}
                      </td>

                      <td className="px-5 py-3.5 text-right" onClick={(e) => e.stopPropagation()}>
                        <div className="inline-flex items-center gap-1">
                          {lead.linkedin_url && (
                            <a
                              href={lead.linkedin_url}
                              target="_blank"
                              rel="noreferrer"
                              className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                              title="Open LinkedIn Profile"
                              aria-label="Open LinkedIn Profile"
                            >
                              <ExternalLink size={13} />
                            </a>
                          )}

                          <button
                            type="button"
                            onClick={() => {
                              navigator.clipboard.writeText(lead.id || lead.enrollment_id || '');
                              setCopiedLeadId(lead.id || lead.enrollment_id);
                              toast.success("Lead ID copied");
                              setTimeout(() => setCopiedLeadId(null), 2000);
                            }}
                            className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
                            title="Copy Lead ID"
                            aria-label="Copy Lead ID"
                          >
                            {copiedLeadId === (lead.id || lead.enrollment_id) ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
                          </button>

                          <button
                            type="button"
                            onClick={() => {
                              setSelectedLeadForPrewarm({
                                id: lead.id || lead.enrollment_id,
                                name: `${lead.kdm_first || ''} ${lead.kdm_last || ''}`.trim() || lead.company_name || 'Prospect'
                              });
                            }}
                            className="p-1.5 rounded-md text-amber-400 hover:text-amber-300 hover:bg-amber-500/10 transition-colors cursor-pointer"
                            title="Autonomous Social Pre-Warm & Comment Generator"
                            aria-label="Autonomous Social Pre-Warm & Comment Generator"
                          >
                            <Flame size={13} />
                          </button>

                          <button
                            type="button"
                            onClick={() => setSelectedLeadForTrace(lead)}
                            className="px-2.5 py-1 rounded-md bg-primary/10 text-primary hover:bg-primary/20 text-[11px] font-bold transition-colors cursor-pointer"
                          >
                            View Trace
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>

          {/* Pagination Controls */}
          {totalPages > 1 && (
            <div className="p-3.5 border-t border-border/60 bg-muted/10 flex items-center justify-between text-xs text-muted-foreground">
              <span>
                Showing {(currentPage - 1) * pageSize + 1}-{Math.min(currentPage * pageSize, filteredLeads.length)} of {filteredLeads.length} leads
              </span>

              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  aria-label="Previous page"
                  onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className="p-1.5 rounded-md border border-border/60 bg-background hover:bg-muted disabled:opacity-40 cursor-pointer"
                >
                  <ChevronLeft size={14} />
                </button>
                <span className="px-2 font-mono font-bold text-foreground">
                  {currentPage} / {totalPages}
                </span>
                <button
                  type="button"
                  aria-label="Next page"
                  onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                  className="p-1.5 rounded-md border border-border/60 bg-background hover:bg-muted disabled:opacity-40 cursor-pointer"
                >
                  <ChevronRight size={14} />
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Execution Trace Drawer */}
      {selectedLeadForTrace && (
        <LeadTraceDrawer 
          campaignId={campaign.id} 
          enrollmentId={selectedLeadForTrace.enrollment_id} 
          leadName={`${selectedLeadForTrace.kdm_first || ''} ${selectedLeadForTrace.kdm_last || ''}`.trim() || 'Lead'} 
          onClose={() => setSelectedLeadForTrace(null)} 
        />
      )}
    </div>
  )
}
