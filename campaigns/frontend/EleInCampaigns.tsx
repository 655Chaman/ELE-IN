import { useHRTreeStore } from "@campaigns/eiTreeStore";
import useSWR from "swr"
import { fetcher, fetchWithAuth } from "@/lib/apiClient"
import { toast } from "sonner"
import { useState, useEffect, useRef, useMemo, useCallback } from "react"
import { motion, AnimatePresence } from "motion/react"
import { useNavigate, useSearchParams } from "react-router-dom"
import { 
  Plus, Search, Play, Pause,
  Trash2, ChevronRight, BarChart2, Users,
  MoreVertical, Settings,
  Briefcase, Link as LinkIcon, Info, X, Loader2,
  Copy, CheckSquare, Square,
  ArrowUpDown, AlertCircle, Award
} from "lucide-react"

import { NumberTicker } from "@/components/ui/number-ticker"
import { EleInPaywallModal } from "./EleInPaywallModal"
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

export function EleInCampaigns() {
  const navigate = useNavigate()
  const resetTree = useHRTreeStore(state => state.reset)

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

  // ─── Duplication & Toggle State ───
  const [duplicatingId, setDuplicatingId] = useState<string | null>(null)
  const [togglingId, setTogglingId] = useState<string | null>(null)

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
  const [showUpgradeModal, setShowUpgradeModal] = useState(false)
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
  const tier = billingData?.tier || 'FREE'
  const isPro = tier === 'PRO' || tier === 'ENTERPRISE'
  const maxActiveCampaigns = isPro ? (tier === 'ENTERPRISE' ? 100 : 20) : 1

  const { data: dashboardData, mutate } = useSWR("/api/elein/dashboard/stats", fetcher)
  const campaigns: Campaign[] = dashboardData?.recent_campaigns || dashboardData?.campaigns || []

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

  // ─── Single Campaign Toggle ───
  const executeToggleStatus = async (id: string, action: 'activate' | 'pause') => {
    setTogglingId(id);
    try {
      const res = await fetchWithAuth(`/api/elein/campaigns/${id}/${action}`, { method: 'PATCH' });
      if (!res.ok) {
        let errMsg = `Failed to ${action} campaign`;
        try {
          const errJson = await res.json();
          errMsg = errJson.detail || errMsg;
        } catch {
          const text = await res.text();
          if (text) errMsg = text;
        }
        if (res.status === 403 || errMsg.includes("exceeds limit") || errMsg.includes("Free Tier") || errMsg.includes("Campaign limit reached") || errMsg.toLowerCase().includes("forbidden")) {
          const feature = errMsg.toLowerCase().includes("enrichment") || errMsg.toLowerCase().includes("scraping")
            ? "Enrichment & Scraping Nodes"
            : "Active Campaigns Limit";
          openPaywall({ featureName: feature });
          setShowUpgradeModal(true);
          mutate();
          return;
        }
        if (errMsg === "no_active_senders") {
          toast.error("No active sender accounts found for this campaign. Please connect or activate a LinkedIn account first.");
          mutate();
          return;
        }
        if (errMsg === "insufficient_credits") {
          openPaywall({ featureName: "Campaign Activation Credits" });
          toast.info("Insufficient credits to activate campaign. Please top up your credits.");
          mutate();
          return;
        }
        throw new Error(errMsg);
      }
      toast.success(action === 'activate' ? `Campaign activated` : `Campaign paused`);
      mutate();
    } catch (e: any) {
      toast.error(e.message || "Failed to update campaign status");
      mutate();
    } finally {
      setTogglingId(null);
    }
  }
  
  const toggleStatus = async (id: string) => {
    if (togglingId || isBatchOperating) return;
    const campaign = campaigns.find(c => c.id === id);
    if (!campaign) return;
    const action = campaign.status === 'ACTIVE' ? 'pause' : 'activate';

    if (action === 'pause') {
      await executeToggleStatus(id, 'pause');
      return;
    }

    if (!isPro && statusCounts.ACTIVE >= maxActiveCampaigns) {
      openPaywall({ featureName: "Active Campaigns Limit" });
      setShowUpgradeModal(true);
      toast.info("Free plan is limited to 1 active campaign. Upgrade to Growth Pro to run up to 20 campaigns simultaneously.");
      return;
    }

    setPreflightCampaign({ id: campaign.id, name: campaign.name });
  }

  // ─── 1-Click Duplicate Campaign (Layer 0 & Layer 1) ───
  const handleDuplicateCampaign = async (id: string, originalName: string) => {
    if (duplicatingId || isBatchOperating) return;
    setDuplicatingId(id);
    try {
      const detailRes = await fetchWithAuth(`/api/elein/campaigns/${id}/detail`);
      if (!detailRes.ok) throw new Error("Failed to fetch campaign architecture");
      const detail = await detailRes.json();

      const origCamp = detail.campaign || {};
      const newName = `${originalName} (Copy)`;

      // UI-08 Paranoia Layer 0 & 2: Explicitly preserve sender accounts and audience lead_list_id
      const senders = (Array.isArray(detail.accounts) && detail.accounts.length > 0)
        ? detail.accounts.map((a: any) => a.id || a.account_id).filter(Boolean)
        : (origCamp.senders || origCamp.sender_account_ids_json || []);
      const leadListId = origCamp.lead_list_id || origCamp.metadata?.lead_list_id || null;

      const createRes = await fetchWithAuth('/api/elein/campaigns', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newName,
          nodes: detail.nodes || [],
          edges: detail.edges || [],
          senders: senders,
          lead_list_id: leadListId,
          timezone: origCamp.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone,
          status: "DRAFT",
          schedule: origCamp.schedule,
          metadata: {
            ...(origCamp.metadata || { stop_on_reply: true }),
            ...(leadListId ? { lead_list_id: leadListId } : {})
          }
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

  // ─── Batch Operations (Layer 0, 1 & 2 - UI-07) ───
  const handleBatchPause = async () => {
    if (selectedIds.size === 0 || isBatchOperating) return;
    setIsBatchOperating(true);
    setBatchActionType("pause");

    try {
      const targets = Array.from(selectedIds).filter(id => {
        const camp = campaigns.find(c => c.id === id);
        return camp && camp.status === 'ACTIVE';
      });

      const results = await Promise.allSettled(
        targets.map(async (id) => {
          const res = await fetchWithAuth(`/api/elein/campaigns/${id}/pause`, { method: 'PATCH' });
          if (!res.ok) throw new Error("Failed to pause campaign");
          return id;
        })
      );
      const successCount = results.filter(r => r.status === "fulfilled").length;

      toast.success(`Paused ${successCount} campaign${successCount === 1 ? '' : 's'}`);
    } catch (e: any) {
      toast.error(e?.message || "Encountered an error pausing campaigns.");
    } finally {
      setIsBatchOperating(false);
      setBatchActionType(null);
      mutate();
    }
  };

  const handleBatchResume = async () => {
    if (selectedIds.size === 0 || isBatchOperating) return;

    // Quota pre-check (Layer 2 Paranoia)
    const candidates = Array.from(selectedIds).filter(id => {
      const c = campaigns.find(camp => camp.id === id);
      return c && c.status !== 'ACTIVE';
    });

    if (!isPro && (statusCounts.ACTIVE + candidates.length) > maxActiveCampaigns) {
      openPaywall({ featureName: "Active Campaigns Limit" });
      setShowUpgradeModal(true);
      toast.info(`Free plan limit: You can only have ${maxActiveCampaigns} active campaign. Upgrade to Growth Pro to run up to 20.`);
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

    try {
      const results = await Promise.allSettled(
        validCandidates.map(async (id) => {
          const res = await fetchWithAuth(`/api/elein/campaigns/${id}/activate`, { method: 'PATCH' });
          if (!res.ok) throw new Error("Failed to activate campaign");
          return id;
        })
      );
      const successCount = results.filter(r => r.status === "fulfilled").length;
      const failedCount = results.filter(r => r.status === "rejected").length;

      if (successCount > 0) {
        toast.success(`Activated ${successCount} campaign${successCount === 1 ? '' : 's'}`);
      }
      if (failedCount > 0) {
        toast.warning(`${failedCount} campaign${failedCount === 1 ? '' : 's'} could not be activated (check sender assignments or credits).`);
      }
    } catch (e: any) {
      toast.error(e?.message || "Encountered an error activating campaigns.");
    } finally {
      setIsBatchOperating(false);
      setBatchActionType(null);
      mutate();
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

      {/* ─── ZERO STATE OR CAMPAIGN GRID ─────────────────────────────────────── */}
      {campaigns.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 md:py-24 max-w-4xl mx-auto text-center w-full">
          <h2 className="text-2xl md:text-3xl font-semibold tracking-tight text-foreground mb-2">Start outreach</h2>
          <p className="text-sm text-muted-foreground mb-8 max-w-md">
            Choose a campaign objective to generate your sequence, or start from a blank canvas.
          </p>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5 w-full">
            <EmptyCampaignCard 
              id="get_customers"
              icon={Users}
              title="Get customers"
              desc="Message people who can buy. Goal: book a meeting."
              onSelect={(id: string) => { navigate('/elein/campaigns/new?goal=' + id); }}
            />
            <EmptyCampaignCard 
              id="hire_people"
              icon={Briefcase}
              title="Hire people"
              desc="Message people you want on the team. Goal: a hire."
              onSelect={(id: string) => { navigate('/elein/campaigns/new?goal=' + id); }}
            />
            <EmptyCampaignCard 
              id="get_intros"
              icon={LinkIcon}
              title="Get intros"
              desc="Message people who can open a door, such as an investor, partner, or their network."
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
            className="text-xs font-medium text-muted-foreground hover:text-foreground underline underline-offset-4 mt-8 transition-colors cursor-pointer"
          >
            Or start from a blank canvas
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          {/* Multi-Campaign Scaling Pay Ramp Banner */}
          {!isPro && statusCounts.ACTIVE >= maxActiveCampaigns && (
            <div className="border border-border bg-card px-4 py-2.5 rounded-xl flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <span className="font-medium text-foreground">
                  Free plan limit reached ({statusCounts.ACTIVE}/{maxActiveCampaigns} active)
                </span>
                <span className="text-muted-foreground hidden md:inline">
                  Upgrade to Growth Pro to run up to 20 campaigns simultaneously across multiple LinkedIn accounts.
                </span>
              </div>
              <button
                type="button"
                onClick={() => openPaywall({ featureName: "Active Campaigns Limit" })}
                className="px-3.5 py-1.5 rounded-lg bg-background hover:bg-muted text-foreground border border-border text-xs font-medium transition-colors shrink-0 whitespace-nowrap cursor-pointer"
              >
                Unlock 20 Campaigns
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
                    className="text-xs text-muted-foreground hover:text-foreground underline ml-1 cursor-pointer"
                  >
                    Deselect All
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

          {/* ─── CAMPAIGNS DATA TABLE ─────────────────────────────────────────── */}
          {filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center p-10 text-center rounded-xl border border-border bg-card">
              <h3 className="text-sm font-semibold text-foreground mb-1">No matching campaigns found</h3>
              <p className="text-xs text-muted-foreground max-w-sm mb-4">
                No campaigns matched your current filter criteria.
              </p>
              <button
                type="button"
                onClick={() => { setSearch(""); setStatusFilter("ALL"); }}
                className="px-3.5 py-1.5 rounded-lg border border-border bg-background text-foreground text-xs font-medium hover:bg-muted cursor-pointer"
              >
                Clear Filters
              </button>
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
                        <th className="px-4 py-3 w-10 text-center">
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
                        <th className="px-5 py-3 min-w-[200px]">Campaign Name</th>
                        <th className="px-4 py-3 w-28">Status</th>
                        <th className="px-4 py-3 w-24 text-right">Enrolled</th>
                        <th className="px-4 py-3 w-24 text-right">Connected</th>
                        <th className="px-4 py-3 w-28 text-right">Acceptance</th>
                        <th className="px-4 py-3 w-24 text-right">Replied</th>
                        <th className="px-4 py-3 w-28 text-right">Reply Rate</th>
                        <th className="px-4 py-3 w-24 text-right">Booked</th>
                        <th className="px-4 py-3 w-28 text-center">Senders</th>
                        <th className="px-5 py-3 w-36 text-right">Action</th>
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
                          <td className="px-4 py-3.5 text-center" onClick={(e) => e.stopPropagation()}>
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
                          <td className="px-5 py-3.5">
                            <div className="block">
                              <p className="font-medium text-foreground text-xs group-hover:underline underline-offset-2">
                                {c.name}
                              </p>
                              <p className="text-xs text-muted-foreground mt-0.5">{dateStr}</p>
                            </div>
                          </td>

                          {/* Status */}
                          <td className="px-4 py-3.5">
                            <div className="flex flex-col gap-1">
                              <div className="flex items-center gap-1.5">
                                <span className={`w-2 h-2 rounded-full ${statusCfg.dot}`} />
                                <span className={`text-xs font-medium ${statusCfg.text}`}>
                                  {statusCfg.label}
                                </span>
                              </div>
                              {hasZeroSenders && (
                                <span 
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    navigate(`/elein/campaigns/new?edit=${c.id}`);
                                  }}
                                  className="text-xs text-muted-foreground hover:text-foreground underline w-fit"
                                  title="Campaign active but 0 sender accounts assigned"
                                >
                                  0 senders
                                </span>
                              )}
                            </div>
                          </td>

                          {/* Enrolled */}
                          <td className="px-4 py-3.5 text-right font-mono text-xs text-foreground">
                            <NumberTicker value={enrolled} />
                          </td>

                          {/* Connected */}
                          <td className="px-4 py-3.5 text-right font-mono text-xs text-foreground">
                            <NumberTicker value={connected} />
                          </td>

                          {/* Acceptance Rate */}
                          <td className="px-4 py-3.5 text-right font-mono text-xs text-foreground">
                            <NumberTicker value={acceptanceRate} />%
                          </td>

                          {/* Replied */}
                          <td className="px-4 py-3.5 text-right font-mono text-xs text-foreground">
                            <NumberTicker value={replied} />
                          </td>

                          {/* Reply Rate */}
                          <td className="px-4 py-3.5 text-right font-mono text-xs text-foreground">
                            <NumberTicker value={replyRate} />%
                          </td>

                          {/* Booked */}
                          <td className="px-4 py-3.5 text-right font-mono text-xs font-semibold text-primary">
                            <NumberTicker value={booked} />
                          </td>

                          {/* Senders */}
                          <td className="px-4 py-3.5 text-center text-muted-foreground text-xs" onClick={(e) => e.stopPropagation()}>
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

                          {/* Row Action Station */}
                          <td className="px-5 py-3.5 text-right" onClick={(e) => e.stopPropagation()}>
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
                                disabled={!!togglingId || isBatchOperating}
                                className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer disabled:opacity-50"
                                title={c.status === "ACTIVE" ? "Pause Campaign" : "Resume Campaign"}
                              >
                                {togglingId === c.id ? (
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
      {/* High-Converting In-Situ Paywall Modal */}
      <EleInPaywallModal
        isOpen={showUpgradeModal}
        onClose={() => setShowUpgradeModal(false)}
        campaignName="Active Campaigns"
        onSuccess={() => {
          toast.success("Account upgraded to Growth Tier!");
          mutate();
        }}
      />

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
                {/* Section 1: Get More Replies */}
                <div>
                  <h3 className="text-xs font-medium text-muted-foreground border-b border-border pb-1.5 mb-2.5">
                    1. Increase Replies & Bookings
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                    <button
                      type="button"
                      onClick={() => { setShowGrowthHub(false); setBanditCampaign({ id: "", name: "Global Portfolio" }); }}
                      className="w-full text-left p-4 rounded-lg border border-border bg-background hover:bg-muted/40 transition-colors cursor-pointer flex items-start justify-between gap-3 group"
                    >
                      <div>
                        <h4 className="text-sm font-medium text-foreground">A/B Test Messages</h4>
                        <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                          Test multiple message variations to see which one books more meetings.
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
                        <h4 className="text-sm font-medium text-foreground">Auto-Snooze & Intent Filters</h4>
                        <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                          Spot interested replies instantly and snooze leads who are out of the office.
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
                        <h4 className="text-sm font-medium text-foreground">Active Hours Scheduling</h4>
                        <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                          Deliver messages during hours when your leads are active on LinkedIn.
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
                        <h4 className="text-sm font-medium text-foreground">1-Click Meeting Link</h4>
                        <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                          Add a direct booking link so interested leads can schedule without email back-and-forth.
                        </p>
                      </div>
                      <ChevronRight size={14} className="text-muted-foreground group-hover:text-foreground shrink-0 mt-0.5 transition-transform group-hover:translate-x-0.5" />
                    </button>
                  </div>
                </div>

                {/* Section 2: Multi-Channel Follow-ups */}
                <div>
                  <h3 className="text-xs font-medium text-muted-foreground border-b border-border pb-1.5 mb-2.5">
                    2. Multi-Channel Follow-ups & Triggers
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                    <button
                      type="button"
                      onClick={() => { setShowGrowthHub(false); setShowOmnichannelModal(true); }}
                      className="w-full text-left p-4 rounded-lg border border-border bg-background hover:bg-muted/40 transition-colors cursor-pointer flex items-start justify-between gap-3 group"
                    >
                      <div>
                        <h4 className="text-sm font-medium text-foreground">Email if No LinkedIn Reply</h4>
                        <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                          Send an automated email follow-up if a lead does not respond on LinkedIn.
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
                        <h4 className="text-sm font-medium text-foreground">Target Multiple People at One Company</h4>
                        <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                          Reach decision-makers and champions at the same target account simultaneously.
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
                        <h4 className="text-sm font-medium text-foreground">Job Change Alerts</h4>
                        <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                          Get notified and reach out when previous prospects or champions move to new companies.
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
                        <h4 className="text-sm font-medium text-foreground">Message Event Attendees</h4>
                        <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                          Reach leads attending relevant industry webinars and LinkedIn events.
                        </p>
                      </div>
                      <ChevronRight size={14} className="text-muted-foreground group-hover:text-foreground shrink-0 mt-0.5 transition-transform group-hover:translate-x-0.5" />
                    </button>
                  </div>
                </div>

                {/* Section 3: Safety & Deliverability */}
                <div>
                  <h3 className="text-xs font-medium text-muted-foreground border-b border-border pb-1.5 mb-2.5">
                    3. Account Safety & Domain Health
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                    <button
                      type="button"
                      onClick={() => { setShowGrowthHub(false); setShowPreWarmModal(true); }}
                      className="w-full text-left p-4 rounded-lg border border-border bg-background hover:bg-muted/40 transition-colors cursor-pointer flex items-start justify-between gap-3 group"
                    >
                      <div>
                        <h4 className="text-sm font-medium text-foreground">LinkedIn Profile Warmup</h4>
                        <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                          Auto-visit profiles and like recent posts before connecting to keep accounts safe.
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
                        <h4 className="text-sm font-medium text-foreground">Email Spam & Domain Check</h4>
                        <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                          Verify SPF, DKIM, and DMARC settings to keep your emails out of the spam folder.
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
                        <h4 className="text-sm font-medium text-foreground">Competitor Technology Triggers</h4>
                        <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                          Reach target accounts when they install or remove competing sales software.
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