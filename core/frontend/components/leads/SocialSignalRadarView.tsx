import React, { useState, useMemo } from "react"
import { motion, AnimatePresence } from "motion/react"
import useSWR from "swr"
import {
  Radio,
  Flame,
  Clock,
  Sparkles,
  RotateCw,
  Copy,
  Check,
  Send,
  SlidersHorizontal,
  TrendingUp,
  ThumbsUp,
  MessageCircle,
  ShieldAlert,
  Search,
  X,
  Wand2,
  AlertTriangle,
  Info,
  Download
} from "lucide-react"
import { toast } from "sonner"
import { fetcher, fetchWithAuth } from "@/lib/apiClient"
import { Linkedin } from "../icons/Linkedin"

interface SocialLead {
  id: string
  first_name: string
  last_name: string
  job_title: string
  company_name: string
  linkedin_url: string
  location?: string
  social_intent_score: number
  social_intent_tier: "HOT" | "WARM" | "MILD" | "COLD"
  last_social_scan_at: string
  best_outreach_angle: string
  social_icebreaker: string
  recommended_timing: string
  is_demo?: boolean
}

interface SocialSignal {
  id?: string
  signal_type: string
  intent_strength: string
  confidence_score: number
  signal_summary: string
  quote_snippet: string
  created_at?: string
  post_id?: string
}

interface SocialPost {
  post_url?: string
  post_text: string
  post_date?: string
  engagement_count?: { likes?: number; comments?: number; reposts?: number }
  media_type?: string
}

interface FeedItem {
  lead: SocialLead
  signals: SocialSignal[]
  top_post?: SocialPost
}

const SIGNAL_LABELS: Record<string, { label: string; color: string; dotColor: string }> = {
  HIRING_EXPANSION: {
    label: "Hiring & Expansion",
    color: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
    dotColor: "bg-emerald-400"
  },
  TECH_STACK_PAIN: {
    label: "Tech Stack Friction",
    color: "bg-rose-500/10 text-rose-400 border-rose-500/30",
    dotColor: "bg-rose-400"
  },
  TOOL_EVALUATION: {
    label: "Tool Evaluation",
    color: "bg-amber-500/10 text-amber-400 border-amber-500/30",
    dotColor: "bg-amber-400"
  },
  EXECUTIVE_PROMOTION: {
    label: "Executive Promotion",
    color: "bg-indigo-500/10 text-indigo-400 border-indigo-500/30",
    dotColor: "bg-indigo-400"
  },
  FUNDING_ANNOUNCEMENT: {
    label: "Funding Round",
    color: "bg-sky-500/10 text-sky-400 border-sky-500/30",
    dotColor: "bg-sky-400"
  },
  GENERAL_THOUGHT_LEADERSHIP: {
    label: "Thought Leadership",
    color: "bg-indigo-500/10 text-indigo-400 border-indigo-500/30",
    dotColor: "bg-indigo-400"
  },
}

export function SocialSignalRadarView({
  onSwitchToLists
}: {
  onSwitchToLists?: () => void
}) {
  const [tierFilter, setTierFilter] = useState<string>("ALL")
  const [signalFilter, setSignalFilter] = useState<string>("ALL")
  const [sortBy, setSortBy] = useState<"score" | "recency" | "engagement">("score")
  const [searchQuery, setSearchQuery] = useState<string>("")
  const [includeDemo, setIncludeDemo] = useState<boolean>(true)
  const [scanningLeadId, setScanningLeadId] = useState<string | null>(null)
  const [copiedId, setCopiedId] = useState<string | null>(null)
  
  // Batch scan modal state
  const [showBatchModal, setShowBatchModal] = useState(false)
  const [selectedListId, setSelectedListId] = useState<string>("")
  const [batchLimit, setBatchLimit] = useState<number>(25)
  const [isBatchScanning, setIsBatchScanning] = useState(false)

  // AI Draft Generator Studio state
  const [draftLead, setDraftLead] = useState<SocialLead | null>(null)
  const [draftSignal, setDraftSignal] = useState<SocialSignal | null>(null)
  const [draftTone, setDraftTone] = useState<"consultative" | "conversational" | "direct" | "analytical">("consultative")
  const [isGeneratingDraft, setIsGeneratingDraft] = useState(false)
  const [generatedDraft, setGeneratedDraft] = useState<{
    connection_note: string
    follow_up_message: string
    angle: string
    estimated_read_time: string
    quote_snippet?: string
  } | null>(null)

  // Enrollment modal state
  const [enrollingLead, setEnrollingLead] = useState<SocialLead | null>(null)
  const [selectedCampaignId, setSelectedCampaignId] = useState<string>("")
  const [selectedSenderAccountId, setSelectedSenderAccountId] = useState<string>("")
  const [customIcebreaker, setCustomIcebreaker] = useState<string>("")
  const [isEnrolling, setIsEnrolling] = useState(false)
  const [isExportingCsv, setIsExportingCsv] = useState(false)

  // Paranoia Layer 2 Collision & Cooldown Guard dialogs
  const [collisionWarning, setCollisionWarning] = useState<{
    detail: string
    lead: SocialLead
    campaignId: string
    senderAccountId?: string
    icebreaker: string
  } | null>(null)

  const [cooldownWarning, setCooldownWarning] = useState<{
    detail: string
    lead: SocialLead
    campaignId: string
    senderAccountId?: string
    icebreaker: string
  } | null>(null)

  // API Queries
  const feedEndpoint = `/api/leads/social-radar/feed?include_demo_fallback=${includeDemo}${tierFilter !== "ALL" ? `&tier=${tierFilter}` : ""}`
  const { data: feedData, isLoading, mutate: mutateFeed } = useSWR<{ feed: FeedItem[]; total_items: number }>(feedEndpoint, fetcher)
  const { data: lists } = useSWR<any[]>('/api/elein/leads/lists', fetcher)
  const { data: campaigns } = useSWR<any[]>('/api/elein/campaigns', fetcher)
  const { data: accounts } = useSWR<any[]>('/api/elein/accounts', fetcher)

  const rawFeed = feedData?.feed || []

  // Filtered & Sorted Feed Items
  const filteredFeed = useMemo(() => {
    let result = rawFeed.filter(item => {
      const lead = item.lead
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase()
        const fullName = `${lead.first_name || ""} ${lead.last_name || ""}`.toLowerCase()
        const company = (lead.company_name || "").toLowerCase()
        const title = (lead.job_title || "").toLowerCase()
        const postText = (item.top_post?.post_text || "").toLowerCase()
        if (!fullName.includes(q) && !company.includes(q) && !title.includes(q) && !postText.includes(q)) {
          return false
        }
      }
      if (signalFilter !== "ALL") {
        const hasSig = item.signals?.some(s => s.signal_type === signalFilter)
        if (!hasSig) return false
      }
      return true
    })

    // Sort
    result.sort((a, b) => {
      if (sortBy === "score") {
        return (b.lead.social_intent_score || 0) - (a.lead.social_intent_score || 0)
      }
      if (sortBy === "recency") {
        const dateA = a.top_post?.post_date ? new Date(a.top_post.post_date).getTime() : 0
        const dateB = b.top_post?.post_date ? new Date(b.top_post.post_date).getTime() : 0
        return dateB - dateA
      }
      if (sortBy === "engagement") {
        const engA = (a.top_post?.engagement_count?.likes || 0) + (a.top_post?.engagement_count?.comments || 0)
        const engB = (b.top_post?.engagement_count?.likes || 0) + (b.top_post?.engagement_count?.comments || 0)
        return engB - engA
      }
      return 0
    })

    return result
  }, [rawFeed, searchQuery, signalFilter, sortBy])

  // Analytics Metrics
  const metrics = useMemo(() => {
    const total = rawFeed.length
    const hotCount = rawFeed.filter(f => f.lead.social_intent_tier === "HOT").length
    const warmCount = rawFeed.filter(f => f.lead.social_intent_tier === "WARM").length
    const totalScore = rawFeed.reduce((acc, f) => acc + (f.lead.social_intent_score || 0), 0)
    const avgScore = total > 0 ? Math.round(totalScore / total) : 0
    return { total, hotCount, warmCount, avgScore }
  }, [rawFeed])

  // Re-scan individual lead
  const handleRescanLead = async (leadId: string) => {
    setScanningLeadId(leadId)
    try {
      const res = await fetchWithAuth(`/api/leads/${leadId}/social-radar/scan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force_refresh: true })
      })
      if (res.ok) {
        toast.success("Live LinkedIn activity scanned and intent refreshed!")
        mutateFeed()
      } else {
        toast.error("Failed to re-scan lead social activity.")
      }
    } catch (e: any) {
      toast.error(e?.message || "Scan failed.")
    } finally {
      setScanningLeadId(null)
    }
  }

  // Copy text to clipboard helper
  const handleCopyText = (id: string, text: string, label: string = "Text") => {
    if (!text) return
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    toast.success(`${label} copied to clipboard!`)
    setTimeout(() => setCopiedId(null), 2000)
  }

  // Export Radar CSV
  const handleExportCsv = async () => {
    setIsExportingCsv(true)
    try {
      const url = `/api/leads/social-radar/export-csv?include_demo_fallback=${includeDemo}${tierFilter !== "ALL" ? `&tier=${tierFilter}` : ""}${signalFilter !== "ALL" ? `&signal_type=${signalFilter}` : ""}`
      const res = await fetchWithAuth(url)
      if (res.ok) {
        const blob = await res.blob()
        const blobUrl = window.URL.createObjectURL(blob)
        const a = document.createElement("a")
        a.href = blobUrl
        a.download = `social_intent_radar_${tierFilter.toLowerCase()}_${new Date().toISOString().slice(0, 10)}.csv`
        document.body.appendChild(a)
        a.click()
        window.URL.revokeObjectURL(blobUrl)
        document.body.removeChild(a)
        toast.success("Downloaded social intent radar CSV with formula defense.")
      } else {
        toast.error("Failed to export radar CSV.")
      }
    } catch (e: any) {
      toast.error(e?.message || "Network error exporting CSV.")
    } finally {
      setIsExportingCsv(false)
    }
  }


  // Open Draft Studio Modal
  const handleOpenDraftStudio = async (lead: SocialLead, signal?: SocialSignal) => {
    setDraftLead(lead)
    const targetSignal = signal || (lead as any).signals?.[0] || null
    setDraftSignal(targetSignal)
    setGeneratedDraft(null)
    setIsGeneratingDraft(true)

    try {
      const res = await fetchWithAuth(`/api/leads/${lead.id}/social-radar/generate-draft`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          signal_id: targetSignal?.id || targetSignal?.signal_type,
          tone: draftTone
        })
      })
      if (res.ok) {
        const json = await res.json()
        setGeneratedDraft(json.data)
      } else {
        toast.error("Failed to generate intent draft.")
      }
    } catch (e: any) {
      toast.error(e?.message || "Draft generation error.")
    } finally {
      setIsGeneratingDraft(false)
    }
  }

  // Re-generate draft with new tone
  const handleRegenerateWithTone = async (newTone: "consultative" | "conversational" | "direct" | "analytical") => {
    if (!draftLead) return
    setDraftTone(newTone)
    setIsGeneratingDraft(true)
    try {
      const res = await fetchWithAuth(`/api/leads/${draftLead.id}/social-radar/generate-draft`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          signal_id: draftSignal?.id || draftSignal?.signal_type,
          tone: newTone
        })
      })
      if (res.ok) {
        const json = await res.json()
        setGeneratedDraft(json.data)
        toast.success(`Draft updated with ${newTone} tone.`)
      }
    } catch {
      toast.error("Failed to update tone.")
    } finally {
      setIsGeneratingDraft(false)
    }
  }

  // Dismiss False Positive Signal
  const handleDismissSignal = async (leadId: string, signal: SocialSignal) => {
    try {
      const res = await fetchWithAuth(`/api/leads/${leadId}/social-radar/dismiss`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ signal_id: signal.id || signal.signal_type })
      })
      if (res.ok) {
        toast.success("Signal dismissed. Prospect intent score recalibrated.")
        mutateFeed()
      } else {
        toast.error("Failed to dismiss signal.")
      }
    } catch {
      toast.error("Dismiss failed.")
    }
  }

  // Launch Batch Scan
  const handleLaunchBatchScan = async () => {
    if (!selectedListId) {
      toast.error("Please select a target lead list to scan.")
      return
    }
    setIsBatchScanning(true)
    try {
      const res = await fetchWithAuth("/api/leads/social-radar/batch-scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          list_id: selectedListId,
          max_leads: batchLimit,
          force_refresh: true
        })
      })
      if (res.ok) {
        const json = await res.json()
        toast.success(`Batch radar scan complete! ${json.scanned_count} leads processed (${json.hot_count} High Intent detected).`)
        setShowBatchModal(false)
        mutateFeed()
      } else {
        toast.error("Batch scan request failed.")
      }
    } catch (e: any) {
      toast.error(e?.message || "Batch scan error.")
    } finally {
      setIsBatchScanning(false)
    }
  }

  // Execute Enrollment with Layer 2 Paranoia Checks
  const handleEnrollLead = async (forceOverride: boolean = false) => {
    const lead = collisionWarning?.lead || cooldownWarning?.lead || enrollingLead
    const campId = collisionWarning?.campaignId || cooldownWarning?.campaignId || selectedCampaignId
    const senderId = collisionWarning?.senderAccountId || cooldownWarning?.senderAccountId || selectedSenderAccountId
    const hook = collisionWarning?.icebreaker || cooldownWarning?.icebreaker || customIcebreaker || lead?.social_icebreaker || ""

    if (!lead || !campId) {
      toast.error("Please select a target campaign sequence.")
      return
    }

    setIsEnrolling(true)
    try {
      const res = await fetchWithAuth(`/api/leads/${lead.id}/social-radar/enroll`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          campaign_id: campId,
          icebreaker: hook,
          sender_account_id: senderId || undefined,
          force_override: forceOverride
        })
      })

      if (res.status === 409) {
        // Collision detected
        const errJson = await res.json().catch(() => ({}))
        const detail = errJson.detail || "Lead is already in an active campaign."
        setCollisionWarning({
          detail,
          lead,
          campaignId: campId,
          senderAccountId: senderId,
          icebreaker: hook
        })
        setEnrollingLead(null)
        setIsEnrolling(false)
        return
      }

      if (res.status === 429) {
        // Cooldown active
        const errJson = await res.json().catch(() => ({}))
        const detail = errJson.detail || "Lead was recently retargeted (cooldown active)."
        setCooldownWarning({
          detail,
          lead,
          campaignId: campId,
          senderAccountId: senderId,
          icebreaker: hook
        })
        setEnrollingLead(null)
        setIsEnrolling(false)
        return
      }

      if (res.ok) {
        toast.success(`${lead.first_name} enrolled in sequence with intent hook!`)
        setEnrollingLead(null)
        setCollisionWarning(null)
        setCooldownWarning(null)
        mutateFeed()
      } else {
        const errJson = await res.json().catch(() => ({}))
        toast.error(errJson.detail || "Failed to enroll lead.")
      }
    } catch (e: any) {
      toast.error(e?.message || "Enrollment error.")
    } finally {
      setIsEnrolling(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Top Header & Stat Strip */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <motion.div
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          className="p-4 rounded-2xl bg-card border border-border/60 shadow-xs flex items-center justify-between"
        >
          <div>
            <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground block">
              Active Radar Leads
            </span>
            <span className="text-2xl font-bold text-foreground mt-0.5 block">
              {metrics.total}
            </span>
          </div>
          <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary">
            <Radio size={20} className="animate-pulse" />
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="p-4 rounded-2xl bg-gradient-to-br from-red-950/20 to-card border border-red-500/20 shadow-xs flex items-center justify-between"
        >
          <div>
            <span className="text-[11px] font-semibold uppercase tracking-wider text-red-400 block">
              High Intent (Hot)
            </span>
            <span className="text-2xl font-bold text-red-300 mt-0.5 block">
              {metrics.hotCount}
            </span>
          </div>
          <div className="w-10 h-10 rounded-xl bg-red-500/10 border border-red-500/30 flex items-center justify-center text-red-400">
            <Flame size={20} />
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="p-4 rounded-2xl bg-card border border-border/60 shadow-xs flex items-center justify-between"
        >
          <div>
            <span className="text-[11px] font-semibold uppercase tracking-wider text-amber-400 block">
              Warm Opportunity
            </span>
            <span className="text-2xl font-bold text-foreground mt-0.5 block">
              {metrics.warmCount}
            </span>
          </div>
          <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400">
            <TrendingUp size={20} />
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="p-4 rounded-2xl bg-card border border-border/60 shadow-xs flex items-center justify-between"
        >
          <div>
            <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground block">
              Avg Buying Intent
            </span>
            <span className="text-2xl font-bold text-foreground mt-0.5 block">
              {metrics.avgScore}<span className="text-xs text-muted-foreground font-normal">/100</span>
            </span>
          </div>
          <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/25 flex items-center justify-center">
            <img src="/elesium-icon.png" alt="Elesium" className="w-5 h-5 object-contain" />
          </div>
        </motion.div>
      </div>

      {/* Action Bar & Controls */}
      <div className="flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-3 p-3 rounded-2xl bg-card/60 border border-border/60 backdrop-blur-md">
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 flex-1">
          <div className="relative flex-1 min-w-[200px] max-w-sm">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search prospect, company, role, or post..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 rounded-xl text-xs bg-background border border-border/60 focus:border-primary focus:outline-none transition-all placeholder:text-muted-foreground/60"
            />
          </div>

          {/* Tier Pills */}
          <div className="flex items-center gap-1 overflow-x-auto py-1 sm:py-0 border-t sm:border-t-0 sm:border-l border-border/60 sm:pl-3">
            {[
              { id: "ALL", label: "All" },
              { id: "HOT", label: "High Intent (80+)" },
              { id: "WARM", label: "Medium (50+)" },
              { id: "MILD", label: "Low (20+)" }
            ].map((t) => (
              <button
                key={t.id}
                onClick={() => setTierFilter(t.id)}
                className={`px-2.5 py-1 rounded-lg text-xs font-semibold whitespace-nowrap transition-all cursor-pointer ${
                  tierFilter === t.id
                    ? "bg-primary text-primary-foreground shadow-xs"
                    : "text-muted-foreground hover:bg-muted/40"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Signal Filter Dropdown */}
          <select
            value={signalFilter}
            onChange={(e) => setSignalFilter(e.target.value)}
            className="px-2.5 py-1.5 rounded-xl text-xs bg-background border border-border/60 text-foreground focus:outline-none focus:border-primary transition-all cursor-pointer"
          >
            <option value="ALL">All Intent Signals</option>
            {Object.keys(SIGNAL_LABELS).map((st) => (
              <option key={st} value={st}>
                {SIGNAL_LABELS[st].label}
              </option>
            ))}
          </select>

          {/* Sort By Dropdown */}
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as any)}
            className="px-2.5 py-1.5 rounded-xl text-xs bg-background border border-border/60 text-foreground focus:outline-none focus:border-primary transition-all cursor-pointer"
          >
            <option value="score">Sort: Intent Score</option>
            <option value="recency">Sort: Post Recency</option>
            <option value="engagement">Sort: Social Engagement</option>
          </select>

          {/* Demo Sandbox Toggle */}
          <button
            onClick={() => setIncludeDemo(!includeDemo)}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold border transition-all cursor-pointer ${
              includeDemo
                ? "bg-primary/10 text-primary border-primary/30"
                : "bg-background text-muted-foreground border-border/60 hover:text-foreground"
            }`}
            title="Toggle high-fidelity demo signals for testing intent triggers"
          >
            <Sparkles size={13} className={includeDemo ? "text-primary" : "text-muted-foreground"} />
            <span>{includeDemo ? "Sandbox Active" : "Live Only"}</span>
          </button>

          {/* Export Radar CSV */}
          <button
            onClick={handleExportCsv}
            disabled={isExportingCsv}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-background border border-border/80 text-foreground hover:bg-muted transition-all shadow-xs shrink-0 cursor-pointer disabled:opacity-50"
            title="Export filtered social intent signals to sanitized CSV"
          >
            <Download size={13} className={isExportingCsv ? "animate-spin" : ""} />
            <span>Export CSV</span>
          </button>

          {/* Launch Batch Scan Button */}
          <button
            onClick={() => setShowBatchModal(true)}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-primary hover:bg-primary/90 text-primary-foreground transition-all shadow-xs shrink-0 cursor-pointer"
          >
            <Radio size={14} />
            <span>Scan Lead List</span>
          </button>
        </div>
      </div>

      {/* Intent Feed Cards */}
      {isLoading ? (
        <div className="p-12 text-center text-muted-foreground text-xs flex flex-col items-center justify-center gap-3">
          <RotateCw size={24} className="animate-spin text-primary" />
          <span>Sweeping LinkedIn social feeds for intent signals & buying triggers...</span>
        </div>
      ) : filteredFeed.length === 0 ? (
        <div className="p-12 rounded-2xl border border-dashed border-border/70 text-center space-y-3 bg-card/20">
          <div className="w-12 h-12 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary mx-auto">
            <Radio size={24} />
          </div>
          <div>
            <h3 className="text-sm font-bold text-foreground">No Intent Signals Detected Yet</h3>
            <p className="text-xs text-muted-foreground max-w-md mx-auto mt-1">
              Select one of your lead lists to scan prospects' live LinkedIn posts, extract hiring pains, and trigger autonomous retargeting.
            </p>
          </div>
          <div className="flex items-center justify-center gap-3 pt-2">
            <button
              onClick={() => setShowBatchModal(true)}
              className="px-4 py-2 rounded-xl text-xs font-semibold bg-primary text-primary-foreground hover:bg-primary/90 transition-all cursor-pointer shadow-sm"
            >
              Launch Radar Scan on List
            </button>
            {onSwitchToLists && (
              <button
                onClick={onSwitchToLists}
                className="px-4 py-2 rounded-xl text-xs font-semibold bg-background border border-border/80 text-foreground hover:bg-muted/40 transition-all cursor-pointer"
              >
                View Lead Lists
              </button>
            )}
            <button
              onClick={() => setIncludeDemo(true)}
              className="px-4 py-2 rounded-xl text-xs font-semibold bg-secondary text-secondary-foreground hover:bg-secondary/80 border border-border/60 transition-all cursor-pointer"
            >
              Enable Sandbox Demo Stream
            </button>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {filteredFeed.map((item) => {
            const lead = item.lead
            const topPost = item.top_post
            const signals = item.signals || []
            const isScanning = scanningLeadId === lead.id
            const isCopied = copiedId === lead.id
            const isDemo = Boolean(lead.is_demo || lead.id.startsWith("demo-"))

            // Tier styling
            const isHot = lead.social_intent_tier === "HOT"
            const isWarm = lead.social_intent_tier === "WARM"
            const badgeBg = isHot
              ? "bg-red-500/15 text-red-300 border-red-500/30"
              : isWarm
              ? "bg-amber-500/15 text-amber-300 border-amber-500/30"
              : "bg-blue-500/15 text-blue-300 border-blue-500/30"

            return (
              <motion.div
                key={lead.id}
                layout
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                className="p-5 rounded-2xl bg-card border border-border/60 hover:border-primary/40 transition-all shadow-xs space-y-4"
              >
                {/* Card Top: Prospect Identity & Intent Score */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="flex items-start gap-3">
                    <div className="w-10 h-10 rounded-xl bg-muted/60 border border-border/60 flex items-center justify-center font-bold text-xs text-foreground shrink-0 uppercase">
                      {lead.first_name?.[0] || ""}{lead.last_name?.[0] || ""}
                    </div>
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-bold text-foreground">
                          {lead.first_name} {lead.last_name}
                        </span>
                        {lead.linkedin_url && (
                          <a
                            href={lead.linkedin_url}
                            target="_blank"
                            rel="noreferrer"
                            className="text-muted-foreground hover:text-primary transition-colors"
                          >
                            <Linkedin className="w-3.5 h-3.5" />
                          </a>
                        )}
                        <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider border flex items-center gap-1.5 ${badgeBg}`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${isHot ? 'bg-destructive' : isWarm ? 'bg-amber-500' : 'bg-primary'}`} />
                          <span>{lead.social_intent_score}/100 {lead.social_intent_tier}</span>
                        </span>
                        {isDemo && (
                          <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold bg-primary/10 text-primary border border-primary/20 flex items-center gap-1">
                            <Sparkles size={10} />
                            <span>Sandbox Demo</span>
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {lead.job_title} at <span className="font-medium text-foreground">{lead.company_name}</span>
                        {lead.location && ` • ${lead.location}`}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 self-start sm:self-auto">
                    {/* Timing Window Pill */}
                    <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-xl bg-background border border-border/60 text-[11px] font-medium text-muted-foreground">
                      <Clock size={12} className="text-primary" />
                      <span>{lead.recommended_timing.replace(/_/g, " ")}</span>
                    </div>

                    {/* Rescan Button */}
                    <button
                      disabled={isScanning}
                      onClick={() => handleRescanLead(lead.id)}
                      title="Re-scan prospect social activity"
                      className="p-1.5 rounded-xl bg-background border border-border/60 hover:border-primary/40 text-muted-foreground hover:text-foreground transition-all cursor-pointer disabled:opacity-50"
                    >
                      <RotateCw size={13} className={isScanning ? "animate-spin text-primary" : ""} />
                    </button>
                  </div>
                </div>

                {/* Signals Tags with Dismiss Option */}
                {signals.length > 0 && (
                  <div className="flex items-center gap-2 flex-wrap">
                    {signals.map((sig, idx) => {
                      const meta = SIGNAL_LABELS[sig.signal_type] || {
                        label: sig.signal_type,
                        color: "bg-muted text-muted-foreground border-border",
                        dotColor: "bg-muted-foreground"
                      }
                      return (
                        <div
                          key={idx}
                          className={`inline-flex items-center gap-1.5 text-[10px] px-2.5 py-1 rounded-lg border font-semibold ${meta.color}`}
                        >
                          <span className={`w-1.5 h-1.5 rounded-full ${meta.dotColor}`} />
                          <span>{meta.label} ({Math.round(sig.confidence_score * 100)}% match)</span>
                          <button
                            onClick={() => handleDismissSignal(lead.id, sig)}
                            title="Dismiss signal as false positive"
                            className="ml-1 text-muted-foreground/60 hover:text-foreground transition-colors cursor-pointer"
                          >
                            <X size={11} />
                          </button>
                        </div>
                      )
                    })}
                  </div>
                )}

                {/* Quoted Post Excerpt */}
                {topPost && (
                  <div className="p-3 rounded-xl bg-muted/30 border border-border/40 text-xs text-foreground/90 space-y-2">
                    <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                      <span className="font-semibold uppercase tracking-wider">Prospect LinkedIn Post Excerpt</span>
                      {topPost.engagement_count && (
                        <div className="flex items-center gap-3">
                          <span className="flex items-center gap-1">
                            <ThumbsUp size={11} /> {topPost.engagement_count.likes || 0}
                          </span>
                          <span className="flex items-center gap-1">
                            <MessageCircle size={11} /> {topPost.engagement_count.comments || 0}
                          </span>
                        </div>
                      )}
                    </div>
                    <p className="italic text-muted-foreground/90 leading-relaxed font-sans">
                      "{topPost.post_text}"
                    </p>
                  </div>
                )}

                {/* AI Opening Hook Box & Dual Action Strip */}
                <div className="p-3.5 rounded-xl bg-gradient-to-r from-primary/5 via-primary/10 to-transparent border border-primary/20 space-y-2.5">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5 text-xs font-bold text-primary">
                      <img src="/elesium-icon.png" alt="Elesium" className="w-3.5 h-3.5 object-contain" />
                      <span>Elesium Contextual Retargeting Hook (Intent-Aware)</span>
                      <a href="https://elesium.online" target="_blank" rel="noopener noreferrer" className="text-[10px] text-primary/80 hover:underline font-semibold ml-1">(elesium.online)</a>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleOpenDraftStudio(lead, signals[0])}
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-semibold bg-background border border-primary/30 text-primary hover:bg-primary/10 transition-all cursor-pointer shadow-2xs"
                      >
                        <Wand2 size={12} />
                        <span>Review & Draft</span>
                      </button>
                      <button
                        onClick={() => handleCopyText(lead.id, lead.social_icebreaker, "Icebreaker")}
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-semibold bg-background border border-border/60 hover:border-primary/40 text-foreground transition-all cursor-pointer"
                      >
                        {isCopied ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
                        <span>{isCopied ? "Copied" : "Copy"}</span>
                      </button>
                      <button
                        onClick={() => {
                          setEnrollingLead(lead)
                          setCustomIcebreaker(lead.social_icebreaker)
                        }}
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-semibold bg-primary hover:bg-primary/90 text-primary-foreground transition-all cursor-pointer shadow-xs"
                      >
                        <Send size={12} />
                        <span>Enroll</span>
                      </button>
                    </div>
                  </div>
                  <p className="text-xs text-foreground font-medium leading-relaxed bg-background/60 p-2.5 rounded-lg border border-border/40">
                    {lead.social_icebreaker || "No icebreaker generated yet. Click Review & Draft to synthesize."}
                  </p>
                </div>
              </motion.div>
            )
          })}
        </div>
      )}

      {/* AI Draft Studio Modal */}
      <AnimatePresence>
        {draftLead && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-2xl p-6 rounded-2xl bg-card border border-border shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto"
            >
              <div className="flex items-center justify-between border-b border-border/60 pb-3">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary">
                    <Wand2 size={16} />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-foreground">
                      Intent Retargeting Draft Studio — {draftLead.first_name} {draftLead.last_name}
                    </h3>
                    <p className="text-[11px] text-muted-foreground">
                      Synthesized from real-time buying signals ({draftLead.company_name})
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => setDraftLead(null)}
                  className="p-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/40 transition-colors"
                >
                  <X size={16} />
                </button>
              </div>

              {/* Tone Selector */}
              <div className="flex items-center justify-between gap-2 bg-muted/30 p-2 rounded-xl border border-border/50">
                <span className="text-xs font-semibold text-muted-foreground flex items-center gap-1.5 pl-1">
                  <SlidersHorizontal size={13} />
                  <span>Outreach Tone:</span>
                </span>
                <div className="flex items-center gap-1">
                  {[
                    { id: "consultative", label: "Consultative" },
                    { id: "conversational", label: "Conversational" },
                    { id: "direct", label: "Direct" },
                    { id: "analytical", label: "Analytical" }
                  ].map((t) => (
                    <button
                      key={t.id}
                      onClick={() => handleRegenerateWithTone(t.id as any)}
                      disabled={isGeneratingDraft}
                      className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                        draftTone === t.id
                          ? "bg-primary text-primary-foreground shadow-2xs"
                          : "text-muted-foreground hover:bg-muted/60"
                      }`}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>
              </div>

              {isGeneratingDraft ? (
                <div className="p-10 text-center space-y-3">
                  <RotateCw size={24} className="animate-spin text-primary mx-auto" />
                  <p className="text-xs text-muted-foreground">
                    Crafting personalized connection note and follow-up message...
                  </p>
                </div>
              ) : generatedDraft ? (
                <div className="space-y-4">
                  {/* Connection Note Section */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5 text-xs font-bold text-foreground">
                        <Send size={13} className="text-primary" />
                        <span>LinkedIn Connection Note (≤ 280 Chars)</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className={`text-[11px] font-mono font-semibold ${
                          generatedDraft.connection_note.length > 280
                            ? "text-rose-400 font-bold"
                            : generatedDraft.connection_note.length > 260
                            ? "text-amber-400"
                            : "text-muted-foreground"
                        }`}>
                          {generatedDraft.connection_note.length}/280 chars
                        </span>
                        <button
                          onClick={() => handleCopyText("cn-note", generatedDraft.connection_note, "Connection note")}
                          className="text-[11px] font-semibold text-primary hover:underline cursor-pointer"
                        >
                          Copy Note
                        </button>
                      </div>
                    </div>
                    <textarea
                      rows={3}
                      value={generatedDraft.connection_note}
                      onChange={(e) => setGeneratedDraft({ ...generatedDraft, connection_note: e.target.value })}
                      className="w-full p-3 rounded-xl text-xs bg-background border border-border/80 text-foreground focus:outline-none focus:border-primary transition-all font-sans leading-relaxed"
                    />
                    {generatedDraft.connection_note.length > 280 && (
                      <p className="text-[10px] text-rose-400 flex items-center gap-1 font-medium">
                        <AlertTriangle size={11} />
                        <span>LinkedIn limits connection requests to 280-300 characters. Trim slightly before sending.</span>
                      </p>
                    )}
                  </div>

                  {/* Follow-up Message Section */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5 text-xs font-bold text-foreground">
                        <MessageCircle size={13} className="text-primary" />
                        <span>Conversational Follow-Up Message (3-Paragraph Sequence)</span>
                      </div>
                      <button
                        onClick={() => handleCopyText("fu-msg", generatedDraft.follow_up_message, "Follow-up message")}
                        className="text-[11px] font-semibold text-primary hover:underline cursor-pointer"
                      >
                        Copy Follow-up
                      </button>
                    </div>
                    <textarea
                      rows={6}
                      value={generatedDraft.follow_up_message}
                      onChange={(e) => setGeneratedDraft({ ...generatedDraft, follow_up_message: e.target.value })}
                      className="w-full p-3 rounded-xl text-xs bg-background border border-border/80 text-foreground focus:outline-none focus:border-primary transition-all font-sans leading-relaxed"
                    />
                  </div>

                  {/* Metadata Pill */}
                  <div className="flex items-center justify-between text-[11px] text-muted-foreground bg-muted/20 p-2.5 rounded-xl border border-border/40">
                    <span className="flex items-center gap-1">
                      <Info size={12} className="text-primary" />
                      <span>Angle: <strong>{generatedDraft.angle}</strong></span>
                    </span>
                    <span className="flex items-center gap-1">
                      <Clock size={12} />
                      <span>{generatedDraft.estimated_read_time}</span>
                    </span>
                  </div>
                </div>
              ) : null}

              {/* Modal Footer */}
              <div className="flex items-center justify-end gap-2 pt-3 border-t border-border/60">
                <button
                  type="button"
                  onClick={() => setDraftLead(null)}
                  className="px-3.5 py-1.5 rounded-xl text-xs font-semibold text-muted-foreground hover:bg-muted/40 transition-all cursor-pointer"
                >
                  Close
                </button>
                <button
                  type="button"
                  disabled={!generatedDraft}
                  onClick={() => {
                    const leadToEnroll = draftLead
                    const noteToUse = generatedDraft?.connection_note || draftLead.social_icebreaker
                    setDraftLead(null)
                    setEnrollingLead(leadToEnroll)
                    setCustomIcebreaker(noteToUse)
                  }}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold bg-primary hover:bg-primary/90 text-primary-foreground transition-all cursor-pointer disabled:opacity-50 shadow-xs"
                >
                  <Send size={13} />
                  <span>Transfer to Sequence Enrollment</span>
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Batch Scan Modal */}
      <AnimatePresence>
        {showBatchModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-md p-6 rounded-2xl bg-card border border-border shadow-xl space-y-4"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary">
                    <Radio size={16} />
                  </div>
                  <h3 className="text-sm font-bold text-foreground">Launch Radar Scan on List</h3>
                </div>
                <button
                  onClick={() => setShowBatchModal(false)}
                  className="text-muted-foreground hover:text-foreground text-xs p-1"
                >
                  <X size={14} />
                </button>
              </div>

              <p className="text-xs text-muted-foreground">
                Sweeps recent LinkedIn posts of leads in the selected list, extracts structured intent signals, and assigns buying intent scores (0-100).
              </p>

              <div className="space-y-3">
                <div>
                  <label className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground block mb-1">
                    Select Target Lead List
                  </label>
                  <select
                    value={selectedListId}
                    onChange={(e) => setSelectedListId(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl text-xs bg-background border border-border/80 text-foreground focus:outline-none focus:border-primary transition-all cursor-pointer"
                  >
                    <option value="">Select a list...</option>
                    {(lists || []).map((l: any) => (
                      <option key={l.id} value={l.id}>
                        {l.name} ({l.row_count || 0} leads)
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <div className="flex items-center justify-between text-[11px] font-semibold text-muted-foreground mb-1">
                    <span>Scan Sample Size</span>
                    <span className="text-foreground font-bold">{batchLimit} Leads</span>
                  </div>
                  <input
                    type="range"
                    min="5"
                    max="50"
                    step="5"
                    value={batchLimit}
                    onChange={(e) => setBatchLimit(parseInt(e.target.value))}
                    className="w-full accent-primary"
                  />
                  <span className="text-[10px] text-muted-foreground">
                    Paranoia Layer 1 safe limit: max 50 leads per batch to avoid rate limiting.
                  </span>
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowBatchModal(false)}
                  className="px-3.5 py-1.5 rounded-xl text-xs font-semibold text-muted-foreground hover:bg-muted/40 transition-all cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={isBatchScanning || !selectedListId}
                  onClick={handleLaunchBatchScan}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold bg-primary hover:bg-primary/90 text-primary-foreground transition-all cursor-pointer disabled:opacity-50 shadow-xs"
                >
                  {isBatchScanning ? (
                    <>
                      <RotateCw size={14} className="animate-spin" />
                      <span>Scanning Feeds...</span>
                    </>
                  ) : (
                    <>
                      <Radio size={14} />
                      <span>Start Radar Scan</span>
                    </>
                  )}
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Enroll Lead Modal with Sender Pod Selection */}
      <AnimatePresence>
        {enrollingLead && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-lg p-6 rounded-2xl bg-card border border-border shadow-xl space-y-4"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary">
                    <Send size={16} />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-foreground">
                      Enroll {enrollingLead.first_name} {enrollingLead.last_name}
                    </h3>
                    <span className="text-[11px] text-muted-foreground">
                      Intent Score: {enrollingLead.social_intent_score}/100 ({enrollingLead.social_intent_tier})
                    </span>
                  </div>
                </div>
                <button
                  onClick={() => setEnrollingLead(null)}
                  className="text-muted-foreground hover:text-foreground text-xs cursor-pointer p-1"
                >
                  <X size={14} />
                </button>
              </div>

              <div className="space-y-3">
                {/* Target Campaign Selector */}
                <div>
                  <label className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground block mb-1">
                    Select Target Campaign Sequence
                  </label>
                  <select
                    value={selectedCampaignId}
                    onChange={(e) => setSelectedCampaignId(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl text-xs bg-background border border-border/80 text-foreground focus:outline-none focus:border-primary transition-all cursor-pointer"
                  >
                    <option value="">Select an active sequence...</option>
                    {(campaigns || []).map((c: any) => (
                      <option key={c.id} value={c.id}>
                        {c.name} ({c.status})
                      </option>
                    ))}
                  </select>
                </div>

                {/* Sender Pod Account Selector */}
                <div>
                  <label className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground block mb-1">
                    Sender Account (Pod Balancing)
                  </label>
                  <select
                    value={selectedSenderAccountId}
                    onChange={(e) => setSelectedSenderAccountId(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl text-xs bg-background border border-border/80 text-foreground focus:outline-none focus:border-primary transition-all cursor-pointer"
                  >
                    <option value="">Auto (Campaign Pod Load Balancer)</option>
                    {(accounts || []).map((acc: any) => (
                      <option key={acc.id} value={acc.id}>
                        {acc.name || acc.first_name ? `${acc.first_name || ""} ${acc.last_name || ""}`.trim() : acc.id} ({acc.status || "active"})
                      </option>
                    ))}
                  </select>
                </div>

                {/* Personalized Social Icebreaker Field */}
                <div>
                  <label className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground block mb-1">
                    Personalized Social Icebreaker (Available as <code className="text-primary font-mono text-[10px]">{"{{social_icebreaker}}"}</code>)
                  </label>
                  <textarea
                    rows={3}
                    value={customIcebreaker}
                    onChange={(e) => setCustomIcebreaker(e.target.value)}
                    className="w-full p-3 rounded-xl text-xs bg-background border border-border/80 text-foreground focus:outline-none focus:border-primary transition-all font-sans"
                    placeholder="Customize the generated hook before enrolling..."
                  />
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setEnrollingLead(null)}
                  className="px-3.5 py-1.5 rounded-xl text-xs font-semibold text-muted-foreground hover:bg-muted/40 transition-all cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={isEnrolling || !selectedCampaignId}
                  onClick={() => handleEnrollLead(false)}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold bg-primary hover:bg-primary/90 text-primary-foreground transition-all cursor-pointer disabled:opacity-50 shadow-xs"
                >
                  {isEnrolling ? (
                    <>
                      <RotateCw size={14} className="animate-spin" />
                      <span>Enrolling...</span>
                    </>
                  ) : (
                    <>
                      <Send size={14} />
                      <span>Confirm Enrollment</span>
                    </>
                  )}
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Layer 2 Paranoia: CollisionGuard Conflict Dialog (409) */}
      <AnimatePresence>
        {collisionWarning && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-md p-6 rounded-2xl bg-card border border-rose-500/40 shadow-2xl space-y-4"
            >
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-xl bg-rose-500/10 border border-rose-500/30 flex items-center justify-center text-rose-400 shrink-0">
                  <ShieldAlert size={20} />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-foreground">
                    CollisionGuard Interlock Triggered
                  </h3>
                  <p className="text-xs text-rose-300 font-medium mt-1 leading-relaxed">
                    {collisionWarning.detail}
                  </p>
                </div>
              </div>

              <div className="p-3 rounded-xl bg-muted/40 border border-border/50 text-[11px] text-muted-foreground space-y-1">
                <p>
                  <strong>Why was this blocked?</strong> Enrolling a prospect who is already active in another campaign leads to double-messaging, burns sender reputation, and causes prospect churn.
                </p>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setCollisionWarning(null)}
                  className="px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-background border border-border/60 hover:bg-muted/40 text-foreground transition-all cursor-pointer"
                >
                  Cancel (Protect Prospect)
                </button>
                <button
                  type="button"
                  disabled={isEnrolling}
                  onClick={() => handleEnrollLead(true)}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold bg-rose-600 hover:bg-rose-500 text-white transition-all cursor-pointer shadow-xs"
                >
                  {isEnrolling ? <RotateCw size={13} className="animate-spin" /> : <AlertTriangle size={13} />}
                  <span>Force Override & Enroll</span>
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Layer 2 Paranoia: Anti-Spam Cooldown Dialog (429) */}
      <AnimatePresence>
        {cooldownWarning && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-md p-6 rounded-2xl bg-card border border-amber-500/40 shadow-2xl space-y-4"
            >
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400 shrink-0">
                  <Clock size={20} />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-foreground">
                    14-Day Anti-Spam Cooldown Active
                  </h3>
                  <p className="text-xs text-amber-300 font-medium mt-1 leading-relaxed">
                    {cooldownWarning.detail}
                  </p>
                </div>
              </div>

              <div className="p-3 rounded-xl bg-muted/40 border border-border/50 text-[11px] text-muted-foreground space-y-1">
                <p>
                  <strong>Why was this blocked?</strong> Re-messaging the same prospect across multiple social posts inside of 14 days looks robotic and damages connection acceptance rates.
                </p>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setCooldownWarning(null)}
                  className="px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-background border border-border/60 hover:bg-muted/40 text-foreground transition-all cursor-pointer"
                >
                  Respect Cooldown Window
                </button>
                <button
                  type="button"
                  disabled={isEnrolling}
                  onClick={() => handleEnrollLead(true)}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold bg-amber-600 hover:bg-amber-500 text-white transition-all cursor-pointer shadow-xs"
                >
                  {isEnrolling ? <RotateCw size={13} className="animate-spin" /> : <AlertTriangle size={13} />}
                  <span>Force Override Cooldown</span>
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  )
}
