import { fetcher, fetchWithAuth } from "@/lib/apiClient"
import { useState, useEffect, useMemo, useRef } from "react"
import { motion, AnimatePresence } from "motion/react"
import {
  Plus, X, ChevronRight, CheckCircle2, AlertCircle,
  Clock, Trash2, Shield, TrendingUp, Ban, AlertTriangle, RefreshCw, PauseCircle,
  UserPlus, MessageSquare, PlayCircle, ExternalLink, Search, ShieldCheck, Check,
  Lock, Zap, ArrowRight, Server, Layers, MoreVertical, Radio, Activity, Sliders, Tag,
  ShieldAlert
} from "lucide-react"
import { Linkedin } from "@/components/icons/Linkedin"
import useSWR from "swr"
import { usePaywall } from "@/contexts/PaywallContext"
import { useAccountUsage, useAccountLimits } from "@/hooks/useAccounts"
import { cn } from "@/lib/utils"
import { toast } from "sonner"

import { useHRAccountsStore } from "@accounts/eiAccountsStore"
import type { LinkedInAccount } from "@accounts/eiAccountsStore"

import WarmupTimeline from "@/components/accounts/WarmupTimeline"
import ConnectModal from "@/components/accounts/ConnectModal"
import SafetyIndicator, { computeSafetyIndicatorLocally } from "@/components/accounts/SafetyIndicator"
import HealthTimeline from "@/components/accounts/HealthTimeline"
import AccountTags from "@/components/accounts/AccountTags"
import DeleteAccountConfirmationDialog from "@/components/accounts/DeleteAccountConfirmationDialog"
import { Day1OutreachHealthRadar } from "@/components/accounts/Day1OutreachHealthRadar"
import { ProxyPoolStudioModal } from "@/components/accounts/ProxyPoolStudioModal"
import { RenewSessionModal } from "@/components/accounts/RenewSessionModal"
import { EditAccountSettingsModal } from "@/components/accounts/EditAccountSettingsModal"
import { AccountShieldVerificationModal } from "@/components/accounts/AccountShieldVerificationModal"
import { SenderPodStudioModal } from "@/components/accounts/SenderPodStudioModal"
import { formatRelativeTime } from "@/lib/utils/date"

const STATUS_CONFIG: Record<string, { label: string; icon: any; color: string; badge: string }> = {
  ACTIVE: { label: "Connected", icon: CheckCircle2, color: "text-success", badge: "bg-success/10 text-success border-success/20" },
  DISCONNECTED: { label: "Session Expired", icon: AlertCircle, color: "text-destructive", badge: "bg-destructive/10 text-destructive border-destructive/20" },
  CHALLENGE_REQUIRED: { label: "Security Challenge", icon: ShieldAlert, color: "text-destructive", badge: "bg-destructive/10 text-destructive border-destructive/20" },
  SUSPENDED: { label: "Suspended", icon: Ban, color: "text-destructive", badge: "bg-destructive/10 text-destructive border-destructive/20" },
  NEEDS_ATTENTION: { label: "Needs Attention", icon: AlertTriangle, color: "text-warning", badge: "bg-warning/10 text-warning border-warning/20" },
  RATE_LIMITED: { label: "Rate Limited", icon: AlertTriangle, color: "text-warning", badge: "bg-warning/10 text-warning border-warning/20" },
  MANUAL_MODE: { label: "Manual Mode", icon: PauseCircle, color: "text-primary", badge: "bg-primary/10 text-primary border-primary/20" },
  PAUSED: { label: "Paused", icon: PauseCircle, color: "text-warning", badge: "bg-warning/10 text-warning border-warning/20" },
  PENDING: { label: "Verifying...", icon: Clock, color: "text-warning", badge: "bg-warning/10 text-warning border-warning/20" },
  BANNED: { label: "Account Banned", icon: Ban, color: "text-destructive", badge: "bg-destructive/10 text-destructive border-destructive/20" },
  DISABLED: { label: "Disabled", icon: Ban, color: "text-muted-foreground", badge: "bg-muted text-muted-foreground border-border" },
}

function AccountUsageDisplay({ accountId, usageData }: { accountId: string; usageData: any[] | undefined }) {
  const { limits } = useAccountLimits(accountId)
  const sent = Array.isArray(usageData) ? (usageData.find((u: any) => u.account_id === accountId && u.action_type === 'connection_request')?.count || 0) : 0
  
  return (
    <span className="text-xs text-muted-foreground">{sent}/{limits ? limits.effective_limit : 20} sent today</span>
  )
}

export function EleInAccounts() {
  const { 
    accounts, 
    addAccount, 
    fetchAccounts, 
    removeAccount: remove, 
    toggleManualMode, 
    bulkToggleManualMode,
    toggleWarmup,
    clearManualSendWarning, 
    autoHealAccount, 
    fleetHeal 
  } = useHRAccountsStore()
  
  const { openPaywall } = usePaywall()
  const { data: billingData } = useSWR<{ tier?: string }>(
    '/api/elein/workspaces/billing',
    fetcher
  )
  const tier = billingData?.tier || 'FREE'
  const isPro = tier === 'PRO' || tier === 'ENTERPRISE'
  const maxAccounts = isPro ? (tier === 'ENTERPRISE' ? 25 : 5) : 1
  const isAccountCapped = accounts.length >= maxAccounts

  // Modal & Drawer States
  const [showModal, setShowModal] = useState(false)
  const [connectTab, setConnectTab] = useState<"token" | "extension">("token")
  const [showProxyModal, setShowProxyModal] = useState(false)
  const [showPodStudioModal, setShowPodStudioModal] = useState(false)
  const [showRadarDrawer, setShowRadarDrawer] = useState(false)
  const [radarAccountId, setRadarAccountId] = useState<string | null>(null)
  const [renewAccountId, setRenewAccountId] = useState<string | null>(null)
  const [editingAccount, setEditingAccount] = useState<LinkedInAccount | null>(null)
  
  // Operational States
  const [isFleetHealing, setIsFleetHealing] = useState(false)
  const [isBatchProcessing, setIsBatchProcessing] = useState(false)
  const [showBatchTagInput, setShowBatchTagInput] = useState(false)
  const [batchTagInput, setBatchTagInput] = useState("")
  const [healingAccountId, setHealingAccountId] = useState<string | null>(null)
  const [togglingWarmupIds, setTogglingWarmupIds] = useState<Set<string>>(new Set())
  const [selectedAccounts, setSelectedAccounts] = useState<Set<string>>(new Set())
  const [expandedAccounts, setExpandedAccounts] = useState<Set<string>>(new Set())
  const [togglingModes, setTogglingModes] = useState<Set<string>>(new Set())
  const [openRowMenuId, setOpenRowMenuId] = useState<string | null>(null)
  const [accountToDelete, setAccountToDelete] = useState<{id: string; name: string} | null>(null)
  const [shieldModalAccount, setShieldModalAccount] = useState<{id: string; name: string} | null>(null)
  const [searchQuery, setSearchQuery] = useState("")
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "warmup" | "paused" | "action_required">("all")
  
  const rowMenuRef = useRef<HTMLDivElement | null>(null)

  const { data: fleetSummary, mutate: mutateFleetSummary } = useSWR<any>('/api/elein/accounts/fleet-health-summary', fetcher, { refreshInterval: 60000 })
  const { usageData } = useAccountUsage()
  const safeUsageData = Array.isArray(usageData) ? usageData : []

  // Close row menu on click outside
  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (rowMenuRef.current && !rowMenuRef.current.contains(e.target as Node)) {
        setOpenRowMenuId(null)
      }
    }
    document.addEventListener("mousedown", handleOutsideClick)
    return () => document.removeEventListener("mousedown", handleOutsideClick)
  }, [])

  useEffect(() => {
    fetchAccounts()
  }, [fetchAccounts])

  const handleConnectClick = (tab: "token" | "extension" = "token") => {
    if (!isPro && isAccountCapped) {
      openPaywall({ featureName: "Multi-Account Sender Pool" })
      toast.info("Free plan is limited to 1 LinkedIn sender. Upgrade to Growth Pro to connect up to 5 accounts.")
      return
    }
    setConnectTab(tab)
    setShowModal(true)
  }

  const handleAutoHealAccount = async (id: string) => {
    setHealingAccountId(id)
    try {
      const res = await autoHealAccount(id)
      if (res.healed) {
        toast.success(`Account Auto-Healed: Restored to ACTIVE`, {
          description: res.actions_taken?.join(' · ') || 'Session verified.'
        })
      } else if (res.recommendation === 'RENEWAL_REQUIRED') {
        toast.error('Session Expired: Cookies must be renewed.', {
          description: 'Click Renew Session to update your LinkedIn cookies.'
        })
        setRenewAccountId(id)
      } else if (res.new_status === 'CHALLENGE_REQUIRED' || res.recommendation?.includes('CHALLENGE')) {
        toast.warning('Security Challenge Checkpoint Detected', {
          description: 'LinkedIn requires browser verification. Log into LinkedIn, complete verification, then renew session.'
        })
        setRenewAccountId(id)
      } else {
        toast.info(`Diagnostic Completed: ${res.new_status}`, {
          description: res.actions_taken?.join(' · ')
        })
      }
      mutateFleetSummary()
    } catch (e: any) {
      toast.error(e.message || 'Auto-heal diagnostic failed')
    } finally {
      setHealingAccountId(null)
    }
  }

  const handleFleetHeal = async () => {
    setIsFleetHealing(true)
    try {
      const res = await fleetHeal()
      toast.success(`Fleet Health Sweep Complete: ${res.healed_count} account(s) auto-healed`, {
        description: `Scanned ${res.total_scanned} senders. ${res.attention_count} require attention.`
      })
      mutateFleetSummary()
    } catch (e: any) {
      toast.error(e.message || 'Fleet heal failed')
    } finally {
      setIsFleetHealing(false)
    }
  }

  const handleToggleWarmup = async (id: string, currentWarmup: boolean) => {
    if (togglingWarmupIds.has(id)) return
    setTogglingWarmupIds(prev => new Set(prev).add(id))
    try {
      const nextWarmup = !currentWarmup
      await toggleWarmup(id, nextWarmup)
      toast.success(nextWarmup ? "30-Day Safe Warmup Activated" : "Warmup Mode Deactivated", {
        description: nextWarmup 
          ? "Daily connection requests will ramp safely to protect account safety."
          : "Account will use full standard daily limits."
      })
    } catch (e: any) {
      toast.error(e.message || "Failed to update warmup mode")
    } finally {
      setTogglingWarmupIds(prev => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
    }
  }

  const handleApplyBatchTag = async () => {
    const trimmed = batchTagInput.trim()
    if (!trimmed) return
    setIsBatchProcessing(true)
    try {
      const ids = Array.from(selectedAccounts)
      const res = await fetchWithAuth("/api/elein/accounts/bulk/add-tag", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ account_ids: ids, tag: trimmed })
      })
      if (!res.ok) {
        const err = await res.json().catch(() => null)
        throw new Error(err?.detail || "Failed to add batch tag")
      }
      toast.success(`Tag '${trimmed}' applied to ${ids.length} account${ids.length !== 1 ? 's' : ''}`)
      useHRAccountsStore.setState((state) => ({
        accounts: state.accounts.map(a => 
          ids.includes(a.id) 
            ? { ...a, tags: Array.from(new Set([...(a.tags || []), trimmed])) } 
            : a
        )
      }))
      setBatchTagInput("")
      setShowBatchTagInput(false)
    } catch (e: any) {
      toast.error(e?.message || "Failed to apply batch tag")
    } finally {
      setIsBatchProcessing(false)
    }
  }

  const sortedAccounts = useMemo(() => {
    return [...accounts].sort((a, b) => {
      const levelOrder: Record<string, number> = { critical: 0, warning: 1, watch: 2, healthy: 3, loading: 4 }
      const aLevel = computeSafetyIndicatorLocally(a.accountStatus).level
      const bLevel = computeSafetyIndicatorLocally(b.accountStatus).level
      return (levelOrder[aLevel] ?? 4) - (levelOrder[bLevel] ?? 4)
    })
  }, [accounts])

  // Fleet Capacity & Vital Statistics
  const fleetStats = useMemo(() => {
    const total = accounts.length
    const active = accounts.filter(a => a.accountStatus === 'ACTIVE').length
    const warmup = accounts.filter(a => a.isWarmup).length
    const expired = accounts.filter(a => a.accountStatus === 'DISCONNECTED').length
    const challenges = accounts.filter(a => a.accountStatus === 'CHALLENGE_REQUIRED').length
    const manual = accounts.filter(a => a.accountStatus === 'MANUAL_MODE' || a.accountStatus === 'PAUSED').length
    const degradedSenders = accounts.filter(a => 
      ['DISCONNECTED', 'BANNED', 'RATE_LIMITED', 'CHALLENGE_REQUIRED', 'SUSPENDED', 'NEEDS_ATTENTION'].includes(a.accountStatus)
    ).length
    const actionRequiredCount = accounts.filter(a => 
      ['DISCONNECTED', 'BANNED', 'RATE_LIMITED', 'CHALLENGE_REQUIRED', 'SUSPENDED', 'NEEDS_ATTENTION'].includes(a.accountStatus) || 
      Boolean(a.manualSendSuspected)
    ).length
    
    const totalConnectsToday = safeUsageData
      .filter((u: any) => u.action_type === 'connection_request')
      .reduce((sum: number, u: any) => sum + (Number(u.count) || 0), 0)
    
    const totalMessagesToday = safeUsageData
      .filter((u: any) => u.action_type === 'message')
      .reduce((sum: number, u: any) => sum + (Number(u.count) || 0), 0)
    
    const totalCapacity = accounts.reduce((sum: number, a: any) => sum + (Number(a.dailyLimit) || 20), 0)

    return {
      total,
      active,
      warmup,
      expired,
      challenges,
      manual,
      degradedSenders,
      actionRequiredCount,
      totalConnectsToday,
      totalMessagesToday,
      totalCapacity,
      healthScore: total > 0 ? Math.max(0, Math.round(((total - degradedSenders) / total) * 100)) : 100
    }
  }, [accounts, safeUsageData])

  const filteredAccounts = useMemo(() => {
    return sortedAccounts.filter(acc => {
      const q = searchQuery.trim().toLowerCase()
      const matchesSearch = !q || 
        acc.name.toLowerCase().includes(q) ||
        acc.profileUrl.toLowerCase().includes(q) ||
        (Array.isArray(acc.tags) && acc.tags.some(t => t.toLowerCase().includes(q)))

      if (!matchesSearch) return false

      if (statusFilter === 'active') return acc.accountStatus === 'ACTIVE'
      if (statusFilter === 'warmup') return acc.isWarmup
      if (statusFilter === 'paused') return acc.accountStatus === 'MANUAL_MODE' || acc.accountStatus === 'PAUSED'
      if (statusFilter === 'action_required') {
        return (
          ['DISCONNECTED', 'BANNED', 'RATE_LIMITED', 'CHALLENGE_REQUIRED', 'SUSPENDED', 'NEEDS_ATTENTION'].includes(acc.accountStatus) ||
          Boolean(acc.manualSendSuspected)
        )
      }
      return true
    })
  }, [sortedAccounts, searchQuery, statusFilter])

  const toggleSelect = (id: string) => {
    const next = new Set(selectedAccounts)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setSelectedAccounts(next)
  }

  const toggleExpand = (id: string) => {
    const next = new Set(expandedAccounts)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setExpandedAccounts(next)
  }

  const activeRadarAccountId = radarAccountId && accounts.some(a => a.id === radarAccountId) 
    ? radarAccountId 
    : (accounts[0]?.id || null)

  return (
    <div className="max-w-[1240px] mx-auto p-6 sm:p-8 font-sans">
      
      {/* ─── HEADER COMMAND DECK ────────────────────────────────────────────── */}
      <div className="mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5 mb-1">
            <h1 className="text-xl font-semibold tracking-tight text-foreground">Linked Accounts</h1>
            <span className="text-xs text-muted-foreground">
              {fleetStats.active}/{maxAccounts} senders active
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            Connect, warm up, and monitor your LinkedIn sender fleet with automated health protection.
          </p>
        </div>

        {/* Global Action Controls */}
        <div className="flex items-center gap-2 flex-wrap">
          {accounts.length > 0 && (
            <>
              <button
                type="button"
                onClick={() => setShowRadarDrawer(prev => !prev)}
                className={cn(
                  "px-3 py-2 border rounded-xl font-medium text-xs transition-colors cursor-pointer flex items-center gap-1.5",
                  showRadarDrawer 
                    ? "bg-primary/10 border-primary/30 text-primary" 
                    : "bg-background hover:bg-muted text-foreground border-border"
                )}
              >
                <TrendingUp size={13} className="text-primary" />
                <span>Warmup Radar</span>
              </button>

              <button
                type="button"
                onClick={() => setShowPodStudioModal(true)}
                className="px-3 py-2 bg-background hover:bg-muted text-foreground border border-border rounded-xl font-medium text-xs transition-colors cursor-pointer flex items-center gap-1.5"
                title="Configure multi-sender pods, waterfill balancing, and fleet failover"
              >
                <Layers size={13} className="text-muted-foreground" />
                <span>Sender Pods</span>
              </button>

              <button
                type="button"
                onClick={() => setShowProxyModal(true)}
                className="px-3 py-2 bg-background hover:bg-muted text-foreground border border-border rounded-xl font-medium text-xs transition-colors cursor-pointer flex items-center gap-1.5"
                title="Manage residential proxy pools"
              >
                <Server size={13} className="text-muted-foreground" />
                <span>Proxies</span>
              </button>

              <button
                type="button"
                onClick={handleFleetHeal}
                disabled={isFleetHealing}
                className="px-3 py-2 bg-background hover:bg-muted text-foreground border border-border rounded-xl font-medium text-xs transition-colors cursor-pointer flex items-center gap-1.5 disabled:opacity-50"
                title="Run automated health sweep across all accounts"
              >
                <RefreshCw size={13} className={cn("text-muted-foreground", isFleetHealing && "animate-spin")} />
                <span>{isFleetHealing ? "Scanning..." : "Auto-Heal"}</span>
              </button>
            </>
          )}

          <button
            type="button"
            onClick={() => handleConnectClick("token")}
            className="flex items-center gap-1.5 bg-primary hover:bg-primary/90 text-primary-foreground px-4 py-2 rounded-xl font-medium text-xs transition-colors cursor-pointer whitespace-nowrap shadow-xs"
          >
            <Plus size={14} />
            <span>Connect Account</span>
          </button>
        </div>
      </div>

      {/* ─── FLEET VITAL STATISTICS RIBBON (Clean 3-Metric Congruent Overview) ─── */}
      {accounts.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-border border border-border rounded-xl bg-card mb-6 shadow-xs">
          {/* Cell 1: Active Senders */}
          <div className="p-4">
            <p className="text-xs text-muted-foreground">Active Senders</p>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-lg font-semibold tracking-tight text-foreground">
                {fleetStats.active}
              </span>
              <span className="text-xs text-muted-foreground">
                / {fleetStats.total} connected ({fleetStats.warmup} warming)
              </span>
            </div>
            <div className="w-full bg-muted/40 h-1.5 rounded-full overflow-hidden mt-3">
              <div 
                className="bg-primary h-full rounded-full transition-all duration-500" 
                style={{ width: `${fleetStats.total > 0 ? (fleetStats.active / fleetStats.total) * 100 : 0}%` }}
              />
            </div>
          </div>

          {/* Cell 2: Daily Outbound Activity */}
          <div className="p-4">
            <p className="text-xs text-muted-foreground">Daily Outbound Activity</p>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-lg font-semibold tracking-tight text-foreground">
                {fleetStats.totalConnectsToday}
              </span>
              <span className="text-xs text-muted-foreground">
                connects · {fleetStats.totalMessagesToday} messages today
              </span>
            </div>
            <div className="w-full bg-muted/40 h-1.5 rounded-full overflow-hidden mt-3">
              <div 
                className="bg-emerald-500 h-full rounded-full transition-all duration-500" 
                style={{ width: `${fleetStats.totalCapacity > 0 ? Math.min(100, (fleetStats.totalConnectsToday / fleetStats.totalCapacity) * 100) : 0}%` }}
              />
            </div>
          </div>

          {/* Cell 3: Fleet Health & Safety */}
          <div className="p-4">
            <p className="text-xs text-muted-foreground">Fleet Health &amp; Proxy Tunnel</p>
            <div className="flex items-baseline gap-2 mt-1">
              <span className={cn("text-lg font-semibold tracking-tight", fleetStats.degradedSenders > 0 ? "text-destructive" : "text-foreground")}>
                {fleetSummary?.fleet_health_score || fleetStats.healthScore}% Safe
              </span>
              <span className="text-xs text-muted-foreground">
                {fleetStats.challenges > 0
                  ? `${fleetStats.challenges} challenge required`
                  : fleetStats.expired > 0
                  ? `${fleetStats.expired} session expired`
                  : fleetStats.degradedSenders > 0
                  ? `${fleetStats.degradedSenders} require attention`
                  : 'All tunnels operational'}
              </span>
            </div>
            <div className="w-full bg-muted/40 h-1.5 rounded-full overflow-hidden mt-3">
              <div 
                className={cn("h-full rounded-full transition-all duration-500", fleetStats.degradedSenders > 0 ? "bg-destructive" : "bg-emerald-500")}
                style={{ width: `${fleetStats.healthScore}%` }}
              />
            </div>
          </div>
        </div>
      )}

      {/* ─── OPTIONAL EXPANDABLE WARMUP RADAR (Elevated Architecture) ──────── */}
      <AnimatePresence>
        {showRadarDrawer && accounts.length > 0 && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.25 }}
            className="overflow-hidden mb-6"
          >
            <div className="relative border border-border rounded-xl bg-card p-4 shadow-sm">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 mb-2 border-b border-border gap-2">
                <div className="flex items-center gap-3 flex-wrap">
                  <div className="flex items-center gap-2">
                    <TrendingUp size={16} className="text-primary" />
                    <h3 className="text-sm font-semibold text-foreground">30-Day Outreach Warmup Radar &amp; Milestones</h3>
                  </div>

                  {accounts.length > 1 && (
                    <div className="flex items-center gap-1.5 ml-0 sm:ml-2">
                      <span className="text-[11px] font-medium text-muted-foreground">Sender:</span>
                      <div className="flex items-center gap-1 overflow-x-auto max-w-md py-0.5">
                        {accounts.map(acc => (
                          <button
                            key={acc.id}
                            type="button"
                            onClick={() => setRadarAccountId(acc.id)}
                            className={cn(
                              "px-2.5 py-1 rounded-lg text-[11px] font-medium transition-all shrink-0 border cursor-pointer flex items-center gap-1",
                              activeRadarAccountId === acc.id
                                ? "bg-primary text-primary-foreground border-primary font-semibold shadow-2xs"
                                : "bg-card text-muted-foreground border-border hover:bg-muted hover:text-foreground"
                            )}
                          >
                            <span>{acc.name}</span>
                            {acc.isWarmup && (
                              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                            )}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                <button
                  type="button"
                  onClick={() => setShowRadarDrawer(false)}
                  className="w-7 h-7 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted flex items-center justify-center transition-colors cursor-pointer self-end sm:self-auto"
                  aria-label="Close warmup radar"
                >
                  <X size={14} />
                </button>
              </div>
              <Day1OutreachHealthRadar accountId={activeRadarAccountId} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ─── ATTENTION BANNER: CHALLENGE REQUIRED ACCOUNTS ─────────────────── */}
      {accounts.some(a => a.accountStatus === 'CHALLENGE_REQUIRED') && (
        <div className="flex items-center justify-between gap-4 p-4 rounded-xl border border-destructive/30 bg-destructive/10 mb-6 shadow-xs">
          <div className="flex items-center gap-3">
            <ShieldAlert size={18} className="text-destructive shrink-0" />
            <div>
              <p className="text-xs text-destructive font-semibold">
                Action Required: {fleetStats.challenges} account{fleetStats.challenges !== 1 ? 's require' : ' requires'} LinkedIn verification
              </p>
              <p className="text-[11px] text-destructive/80 mt-0.5">
                LinkedIn checkpoint or CAPTCHA detected. Complete the verification in your browser, then run auto-heal or renew session to resume outreach.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={() => {
                const challenged = accounts.find(a => a.accountStatus === 'CHALLENGE_REQUIRED')
                if (challenged) handleAutoHealAccount(challenged.id)
              }}
              disabled={healingAccountId !== null}
              className="px-3 py-1.5 rounded-lg border border-destructive/40 text-destructive hover:bg-destructive/15 text-xs font-semibold transition-all shadow-xs cursor-pointer disabled:opacity-50 flex items-center gap-1.5"
            >
              <RefreshCw size={12} className={healingAccountId ? "animate-spin" : ""} />
              <span>Verify Session</span>
            </button>
            <button
              type="button"
              onClick={() => {
                const challenged = accounts.find(a => a.accountStatus === 'CHALLENGE_REQUIRED')
                if (challenged) setRenewAccountId(challenged.id)
              }}
              className="px-3.5 py-1.5 rounded-lg bg-destructive text-destructive-foreground text-xs font-semibold hover:bg-destructive/90 transition-all shrink-0 shadow-xs cursor-pointer"
            >
              Renew Cookies
            </button>
          </div>
        </div>
      )}

      {/* ─── ATTENTION BANNER: EXPIRED ACCOUNTS ─────────────────────────────── */}
      {accounts.some(a => a.accountStatus === 'DISCONNECTED') && (
        <div className="flex items-center justify-between gap-4 p-4 rounded-xl border border-destructive/30 bg-destructive/10 mb-6 shadow-xs">
          <div className="flex items-center gap-3">
            <AlertCircle size={18} className="text-destructive shrink-0" />
            <div>
              <p className="text-xs text-destructive font-semibold">
                Action Required: {fleetStats.expired} account{fleetStats.expired !== 1 ? 's have' : ' has'} an expired session
              </p>
              <p className="text-[11px] text-destructive/80 mt-0.5">
                LinkedIn session cookies have expired. Renew your session to resume automated outreach safely.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => {
              const firstExpired = accounts.find(a => a.accountStatus === 'DISCONNECTED')
              if (firstExpired) setRenewAccountId(firstExpired.id)
            }}
            className="px-3.5 py-1.5 rounded-lg bg-destructive text-destructive-foreground text-xs font-semibold hover:bg-destructive/90 transition-all shrink-0 shadow-xs cursor-pointer"
          >
            Renew Now
          </button>
        </div>
      )}

      {/* ─── CONTROLS BAR: FILTER CHIPS & SEARCH ────────────────────────────── */}
      {accounts.length > 0 && (
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 mb-5">
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
            {[
              { id: 'all', label: 'All Senders', count: accounts.length },
              { id: 'active', label: 'Active', count: fleetStats.active },
              { id: 'warmup', label: 'In Warmup', count: fleetStats.warmup },
              { id: 'paused', label: 'Paused', count: fleetStats.manual },
              { id: 'action_required', label: 'Action Required', count: fleetStats.actionRequiredCount, urgent: fleetStats.actionRequiredCount > 0 }
            ].map(tab => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setStatusFilter(tab.id as any)}
                className={cn(
                  "px-3 py-1.5 rounded-xl text-xs font-medium transition-all flex items-center gap-1.5 shrink-0 border cursor-pointer",
                  statusFilter === tab.id
                    ? "bg-foreground text-background border-foreground shadow-xs font-semibold"
                    : tab.urgent
                      ? "bg-destructive/10 text-destructive border-destructive/25 hover:bg-destructive/15 font-semibold"
                      : "bg-card text-muted-foreground border-border hover:bg-muted hover:text-foreground"
                )}
              >
                <span>{tab.label}</span>
                <span className={cn(
                  "text-[10px] px-1.5 py-0.2 rounded-full font-bold",
                  statusFilter === tab.id
                    ? "bg-background text-foreground"
                    : tab.urgent
                      ? "bg-destructive text-destructive-foreground"
                      : "bg-muted text-muted-foreground"
                )}>
                  {tab.count}
                </span>
              </button>
            ))}
          </div>

          <div className="relative sm:w-64">
            <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="Search accounts or URLs..."
              className="w-full pl-8 pr-3 py-1.5 text-xs rounded-xl bg-card border border-border text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/40"
            />
          </div>
        </div>
      )}

      {/* ─── MAIN ACCOUNTS LIST / EMPTY STATE ─────────────────────────────────── */}
      {accounts.length === 0 ? (
        <div className="py-12 border border-border rounded-xl bg-card/50 p-8 text-center space-y-6">
          <div className="max-w-md mx-auto space-y-2">
            <div className="w-12 h-12 rounded-xl bg-primary/10 text-primary flex items-center justify-center mx-auto mb-4">
              <Linkedin size={24} />
            </div>
            <h2 className="text-base font-semibold text-foreground">
              Connect your LinkedIn sender account
            </h2>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Scale your outbound outreach safely. We automatically manage warmup schedules, rate limits, and dedicated residential proxies.
            </p>
          </div>

          {/* 2-Choice Stupidly Simple Prompt Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-xl mx-auto text-left">
            <button
              type="button"
              onClick={() => handleConnectClick("token")}
              className="p-5 rounded-xl border border-border bg-card hover:border-primary/50 hover:bg-muted/40 transition-all flex flex-col justify-between group cursor-pointer"
            >
              <div>
                <div className="w-9 h-9 rounded-lg bg-primary/10 text-primary flex items-center justify-center mb-3">
                  <Linkedin size={18} />
                </div>
                <h3 className="text-xs font-bold text-foreground group-hover:text-primary transition-colors">
                  Quick Cookie Token (15s)
                </h3>
                <p className="text-[11px] text-muted-foreground mt-1 leading-relaxed">
                  Paste your LinkedIn session cookie directly. Zero software to download.
                </p>
              </div>
              <div className="pt-4 flex items-center gap-1 text-[11px] font-semibold text-primary">
                <span>Connect via Token</span>
                <ChevronRight size={12} className="transition-transform group-hover:translate-x-0.5" />
              </div>
            </button>

            <button
              type="button"
              onClick={() => handleConnectClick("extension")}
              className="p-5 rounded-xl border border-border bg-card hover:border-primary/50 hover:bg-muted/40 transition-all flex flex-col justify-between group cursor-pointer"
            >
              <div>
                <div className="w-9 h-9 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 flex items-center justify-center mb-3">
                  <Zap size={18} />
                </div>
                <h3 className="text-xs font-bold text-foreground group-hover:text-primary transition-colors">
                  1-Click Chrome Extension
                </h3>
                <p className="text-[11px] text-muted-foreground mt-1 leading-relaxed">
                  Zero manual copy-pasting. Syncs active browser session automatically.
                </p>
              </div>
              <div className="pt-4 flex items-center gap-1 text-[11px] font-semibold text-emerald-600 dark:text-emerald-400">
                <span>1-Click Extension Sync</span>
                <ChevronRight size={12} className="transition-transform group-hover:translate-x-0.5" />
              </div>
            </button>
          </div>
        </div>
      ) : filteredAccounts.length === 0 ? (
        <div className="text-center py-16 bg-card rounded-xl border border-border">
          <p className="text-xs text-muted-foreground">No accounts match the current filter or search criteria.</p>
          <button
            type="button"
            onClick={() => { setSearchQuery(""); setStatusFilter("all"); }}
            className="mt-2 text-xs font-semibold text-primary hover:underline cursor-pointer"
          >
            Clear Filters &amp; View All
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredAccounts.map((acc) => {
            const isSelected = selectedAccounts.has(acc.id)
            const isExpanded = expandedAccounts.has(acc.id)
            const isDisconnected = acc.accountStatus === 'DISCONNECTED'
            const isCritical = ['DISCONNECTED', 'BANNED', 'SUSPENDED', 'CHALLENGE_REQUIRED'].includes(acc.accountStatus)
            const isWarning = ['RATE_LIMITED', 'NEEDS_ATTENTION', 'MANUAL_MODE', 'PAUSED'].includes(acc.accountStatus)
            const isManual = acc.accountStatus === 'MANUAL_MODE' || acc.accountStatus === 'PAUSED'
            const isWarmupToggling = togglingWarmupIds.has(acc.id)
            const statusCfg = STATUS_CONFIG[acc.accountStatus] || STATUS_CONFIG.ACTIVE

            return (
              <div
                key={acc.id}
                className={cn(
                  "p-5 rounded-xl border transition-all shadow-xs bg-card",
                  isCritical
                    ? "border-destructive/40 bg-destructive/5"
                    : isSelected 
                      ? "border-primary/50 bg-primary/5" 
                      : "border-border hover:border-border/80"
                )}
              >
                {/* Manual Send Alert */}
                {acc.manualSendSuspected && (
                  <div className="flex items-start gap-3 p-3 mb-4 rounded-lg border border-destructive/30 bg-destructive/10 text-xs text-destructive">
                    <AlertCircle size={15} className="shrink-0 mt-0.5" />
                    <div className="flex-1">
                      <p className="font-semibold">Manual activity detected outside Ele-in.</p>
                      <p className="text-[11px] opacity-90 mt-0.5">
                        Please pause manual LinkedIn messaging while outreach campaigns are running to avoid rate limits.
                      </p>
                    </div>
                    <button 
                      type="button"
                      onClick={() => clearManualSendWarning(acc.id)} 
                      className="text-[10px] font-semibold hover:bg-destructive/10 px-2 py-0.5 rounded border border-destructive/20 transition-colors whitespace-nowrap cursor-pointer"
                    >
                      Dismiss
                    </button>
                  </div>
                )}

                <div className="flex items-start gap-3.5">
                  <input 
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => toggleSelect(acc.id)}
                    aria-label={`Select account ${acc.name || acc.id}`}
                    className="mt-1 w-4 h-4 rounded border-border text-primary focus:ring-primary/50 bg-background cursor-pointer"
                  />

                  {/* LinkedIn Icon & Status Indicator */}
                  <div className="relative shrink-0">
                    <div className="w-10 h-10 rounded-lg bg-muted/60 border border-border flex items-center justify-center">
                      <Linkedin size={18} className="text-primary" />
                    </div>
                    <span className={cn(
                      "absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-card",
                      isCritical ? "bg-destructive" : isWarning ? "bg-amber-500" : "bg-emerald-500"
                    )} />
                  </div>

                  {/* Account Identity & Tags */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-semibold text-foreground">
                        {acc.name}
                      </span>
                      
                      <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full border", statusCfg.badge)}>
                        {statusCfg.label}
                      </span>

                      <SafetyIndicator accountId={acc.id} status={acc.accountStatus} />

                      {/* 1-Click Inline Warmup Toggle Switch */}
                      <button
                        type="button"
                        onClick={() => handleToggleWarmup(acc.id, Boolean(acc.isWarmup))}
                        disabled={isWarmupToggling}
                        className={cn(
                          "text-[10px] font-semibold px-2 py-0.5 rounded-full border transition-all flex items-center gap-1 cursor-pointer",
                          acc.isWarmup
                            ? "bg-primary/10 text-primary border-primary/25 hover:bg-primary/15"
                            : "bg-muted text-muted-foreground border-border hover:text-foreground"
                        )}
                        title={acc.isWarmup ? "Click to disable warmup mode" : "Click to enable 30-day safe warmup"}
                      >
                        <span className={cn("w-1.5 h-1.5 rounded-full", acc.isWarmup ? "bg-primary animate-pulse" : "bg-muted-foreground")} />
                        <span>{acc.isWarmup ? "Warmup Active" : "Warmup Off"}</span>
                      </button>

                      {isManual && (
                        <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-warning/10 text-warning border border-warning/20">
                          Paused (Manual Mode)
                        </span>
                      )}
                    </div>

                    {/* Vitals Subtitle Row */}
                    <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground flex-wrap">
                      <AccountUsageDisplay accountId={acc.id} usageData={usageData} />
                      <span>·</span>
                      <span className="text-xs">
                        {acc.proxyId ? 'Dedicated Proxy' : 'Direct Connection (No Proxy)'}
                      </span>
                      {acc.cookieExpiresAt && (
                        <>
                          <span>·</span>
                          {(() => {
                            try {
                              if (!acc.cookieExpiresAt) return null
                              const exp = new Date(acc.cookieExpiresAt).getTime()
                              if (isNaN(exp)) return null
                              const now = Date.now()
                              const days = Math.round((exp - now) / (1000 * 60 * 60 * 24))
                              if (isNaN(days)) return null
                              if (days <= 0) {
                                return (
                                  <span className="text-xs text-destructive font-semibold flex items-center gap-1">
                                    <span>Cookie Expired</span>
                                    <button 
                                      type="button"
                                      onClick={() => setRenewAccountId(acc.id)} 
                                      className="underline hover:text-foreground cursor-pointer"
                                    >
                                      Renew
                                    </button>
                                  </span>
                                )
                              } else if (days <= 7) {
                                return (
                                  <span className="text-xs text-warning font-medium flex items-center gap-1">
                                    <span>Expires in {days}d</span>
                                    <button 
                                      type="button"
                                      onClick={() => setRenewAccountId(acc.id)} 
                                      className="underline hover:text-foreground cursor-pointer"
                                    >
                                      Renew
                                    </button>
                                  </span>
                                )
                              } else {
                                return <span className="text-xs text-muted-foreground">Session valid ({days}d)</span>
                              }
                            } catch {
                              return null
                            }
                          })()}
                        </>
                      )}
                    </div>
                    
                    <AccountTags 
                      accountId={acc.id} 
                      initialTags={acc.tags} 
                      onTagsChange={(newTags) => {
                        useHRAccountsStore.setState((state) => ({
                          accounts: state.accounts.map(a => a.id === acc.id ? { ...a, tags: newTags } : a)
                        }))
                      }}
                    />
                  </div>

                  {/* Actions & More Menu */}
                  <div className="flex items-center gap-2 shrink-0 relative">
                    {/* Primary Button */}
                    {isDisconnected || acc.accountStatus === 'CHALLENGE_REQUIRED' ? (
                      <button
                        type="button"
                        onClick={() => setRenewAccountId(acc.id)}
                        className="px-3 py-1.5 rounded-lg bg-destructive text-destructive-foreground hover:bg-destructive/90 text-xs font-semibold transition-colors cursor-pointer flex items-center gap-1"
                      >
                        <RefreshCw size={12} />
                        <span>{acc.accountStatus === 'CHALLENGE_REQUIRED' ? 'Resolve Challenge' : 'Renew Session'}</span>
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => toggleExpand(acc.id)}
                        className="px-3 py-1.5 rounded-lg border border-border bg-card hover:bg-muted text-foreground text-xs font-medium transition-colors cursor-pointer flex items-center gap-1"
                      >
                        <span>Health Details</span>
                        <ChevronRight size={13} className={cn("transition-transform", isExpanded && "rotate-90")} />
                      </button>
                    )}

                    {/* Secondary Actions: MoreVertical Dropdown */}
                    <div className="relative">
                      <button
                        type="button"
                        onClick={() => setOpenRowMenuId(openRowMenuId === acc.id ? null : acc.id)}
                        className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                        title="More Options"
                      >
                        <MoreVertical size={15} />
                      </button>

                      {openRowMenuId === acc.id && (
                        <div
                          ref={rowMenuRef}
                          className="absolute right-0 top-full mt-1 w-52 p-1.5 bg-popover border border-border rounded-xl shadow-lg z-50 text-left text-xs"
                        >
                          {/* Auto-Heal Action */}
                          <button
                            type="button"
                            onClick={() => {
                              setOpenRowMenuId(null)
                              handleAutoHealAccount(acc.id)
                            }}
                            disabled={healingAccountId === acc.id}
                            className="w-full flex items-center gap-2 px-2.5 py-1.5 text-foreground hover:bg-muted rounded-lg transition-colors cursor-pointer"
                          >
                            <RefreshCw size={13} className={cn("text-muted-foreground", healingAccountId === acc.id && "animate-spin")} />
                            <span>Run Auto-Heal Check</span>
                          </button>

                          {/* Renew Session Action */}
                          <button
                            type="button"
                            onClick={() => {
                              setOpenRowMenuId(null)
                              setRenewAccountId(acc.id)
                            }}
                            className="w-full flex items-center gap-2 px-2.5 py-1.5 text-foreground hover:bg-muted rounded-lg transition-colors cursor-pointer"
                          >
                            <Lock size={13} className="text-muted-foreground" />
                            <span>Renew Session Cookies</span>
                          </button>

                          {/* Edit Settings & Limits */}
                          <button
                            type="button"
                            onClick={() => {
                              setOpenRowMenuId(null)
                              setEditingAccount(acc)
                            }}
                            className="w-full flex items-center gap-2 px-2.5 py-1.5 text-foreground hover:bg-muted rounded-lg transition-colors cursor-pointer"
                          >
                            <Sliders size={13} className="text-muted-foreground" />
                            <span>Edit Settings & Limits</span>
                          </button>

                          {/* Pause / Resume Automation */}
                          <button
                            type="button"
                            onClick={async () => {
                              setOpenRowMenuId(null)
                              setTogglingModes(prev => new Set(prev).add(acc.id))
                              try {
                                await toggleManualMode(acc.id, acc.accountStatus)
                                toast.success(isManual ? "Automation resumed" : "Automation paused for manual browsing")
                              } finally {
                                setTogglingModes(prev => {
                                  const next = new Set(prev)
                                  next.delete(acc.id)
                                  return next
                                })
                              }
                            }}
                            className="w-full flex items-center gap-2 px-2.5 py-1.5 text-foreground hover:bg-muted rounded-lg transition-colors cursor-pointer"
                          >
                            {isManual ? <PlayCircle size={13} className="text-muted-foreground" /> : <PauseCircle size={13} className="text-muted-foreground" />}
                            <span>{isManual ? "Resume Automation" : "Pause (Manual Mode)"}</span>
                          </button>

                          {/* Warmup Radar Inspection */}
                          <button
                            type="button"
                            onClick={() => {
                              setOpenRowMenuId(null)
                              setRadarAccountId(acc.id)
                              setShowRadarDrawer(true)
                            }}
                            className="w-full flex items-center gap-2 px-2.5 py-1.5 text-foreground hover:bg-muted rounded-lg transition-colors cursor-pointer"
                          >
                            <TrendingUp size={13} className="text-primary" />
                            <span>View Warmup Radar</span>
                          </button>

                          {/* Account Shield Inspection */}
                          <button
                            type="button"
                            onClick={() => {
                              setOpenRowMenuId(null)
                              setShieldModalAccount({ id: acc.id, name: acc.name })
                            }}
                            className="w-full flex items-center gap-2 px-2.5 py-1.5 text-foreground hover:bg-muted rounded-lg transition-colors cursor-pointer"
                          >
                            <ShieldCheck size={13} className="text-success" />
                            <span>Account Shield Certificate</span>
                          </button>

                          {/* Profile Link */}
                          {acc.profileUrl && (
                            <a
                              href={acc.profileUrl}
                              target="_blank"
                              rel="noreferrer"
                              onClick={() => setOpenRowMenuId(null)}
                              className="w-full flex items-center gap-2 px-2.5 py-1.5 text-foreground hover:bg-muted rounded-lg transition-colors cursor-pointer"
                            >
                              <ExternalLink size={13} className="text-muted-foreground" />
                              <span>View LinkedIn Profile</span>
                            </a>
                          )}

                          <div className="my-1 border-t border-border" />

                          {/* Delete Account */}
                          <button
                            type="button"
                            onClick={() => {
                              setOpenRowMenuId(null)
                              setAccountToDelete({ id: acc.id, name: acc.name })
                            }}
                            className="w-full flex items-center gap-2 px-2.5 py-1.5 text-destructive hover:bg-destructive/10 rounded-lg transition-colors cursor-pointer"
                          >
                            <Trash2 size={13} />
                            <span>Remove Account</span>
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* Inline Warmup Timeline */}
                {acc.isWarmup && <WarmupTimeline accountId={acc.id} />}

                {/* Collapsible Expanded Health History */}
                <AnimatePresence>
                  {isExpanded && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className="overflow-hidden mt-3"
                    >
                      <HealthTimeline accountId={acc.id} />
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            )
          })}
        </div>
      )}

      {/* ─── MODALS & DIALOGS ──────────────────────────────────────────────── */}
      
      {/* Connect Modal */}
      <AnimatePresence>
        {showModal && (
          <ConnectModal 
            onClose={() => setShowModal(false)} 
            onAdd={addAccount} 
          />
        )}
      </AnimatePresence>

      {/* Session Renewal Modal */}
      <AnimatePresence>
        {renewAccountId && (
          <RenewSessionModal
            accountId={renewAccountId}
            accountName={accounts.find(a => a.id === renewAccountId)?.name || "LinkedIn Account"}
            profileUrl={accounts.find(a => a.id === renewAccountId)?.profileUrl}
            onClose={() => setRenewAccountId(null)}
            onSuccess={() => {
              setRenewAccountId(null)
              fetchAccounts()
              mutateFleetSummary()
            }}
          />
        )}
      </AnimatePresence>

      {/* Edit Account Settings Modal */}
      <AnimatePresence>
        {editingAccount && (
          <EditAccountSettingsModal
            account={editingAccount}
            onClose={() => setEditingAccount(null)}
            onSuccess={() => {
              setEditingAccount(null)
              fetchAccounts()
              mutateFleetSummary()
            }}
          />
        )}
      </AnimatePresence>

      {/* Proxy Pool Studio Modal */}
      <AnimatePresence>
        {showProxyModal && (
          <ProxyPoolStudioModal onClose={() => setShowProxyModal(false)} />
        )}
      </AnimatePresence>

      {/* Sender Pod Studio Modal */}
      <SenderPodStudioModal
        isOpen={showPodStudioModal}
        onClose={() => setShowPodStudioModal(false)}
      />

      {/* Account Shield Verification Modal */}
      {shieldModalAccount && (
        <AccountShieldVerificationModal
          isOpen={Boolean(shieldModalAccount)}
          onClose={() => setShieldModalAccount(null)}
          accountId={shieldModalAccount.id}
          accountName={shieldModalAccount.name}
        />
      )}

      {/* Delete Account Confirmation Dialog */}
      <DeleteAccountConfirmationDialog
        isOpen={accountToDelete !== null}
        onOpenChange={(open) => !open && setAccountToDelete(null)}
        accountId={accountToDelete?.id || ""}
        accountName={accountToDelete?.name || ""}
        onConfirm={async (id, force) => {
          try {
            await remove(id, force)
            toast.success(force ? "Account and campaign linkages removed successfully" : "Account removed successfully")
            mutateFleetSummary()
          } catch (e: any) {
            toast.error(e.message || "Failed to remove account")
            throw e
          }
        }}
      />

      {/* Multi-Account Batch Action Bar */}
      <AnimatePresence>
        {selectedAccounts.size > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 50 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 50 }}
            className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 px-5 py-2.5 rounded-xl bg-card border border-border shadow-2xl backdrop-blur-md"
          >
            <span className="text-xs font-semibold text-foreground whitespace-nowrap">
              {selectedAccounts.size} account{selectedAccounts.size !== 1 ? 's' : ''} selected
            </span>
            <div className="w-px h-4 bg-border mx-1" />
            
            <button
              type="button"
              disabled={isBatchProcessing}
              onClick={async () => {
                const ids = Array.from(selectedAccounts)
                setIsBatchProcessing(true)
                try {
                  const res = await bulkToggleManualMode(ids, 'MANUAL_MODE')
                  if (res.succeeded.length === 0 && res.failed.length === 0) {
                    toast.info("No active accounts selected to pause")
                  } else if (res.failed.length === 0) {
                    toast.success(`Successfully paused automation on ${res.succeeded.length} account${res.succeeded.length !== 1 ? 's' : ''}`)
                  } else if (res.succeeded.length > 0) {
                    toast.warning(`Paused ${res.succeeded.length} account(s), but ${res.failed.length} failed`)
                  } else {
                    toast.error("Failed to pause selected accounts")
                  }
                } catch (e: any) {
                  toast.error(e?.message || "Failed to pause selected accounts")
                } finally {
                  setIsBatchProcessing(false)
                }
              }}
              className="px-2.5 py-1 text-xs font-medium bg-muted hover:bg-muted/80 text-foreground rounded-lg transition-colors flex items-center gap-1 cursor-pointer disabled:opacity-50"
            >
              {isBatchProcessing ? (
                <RefreshCw size={13} className="animate-spin" />
              ) : (
                <PauseCircle size={13} />
              )}
              <span>Pause</span>
            </button>

            <button
              type="button"
              disabled={isBatchProcessing}
              onClick={async () => {
                const ids = Array.from(selectedAccounts)
                setIsBatchProcessing(true)
                try {
                  const res = await bulkToggleManualMode(ids, 'ACTIVE')
                  if (res.succeeded.length === 0 && res.failed.length === 0) {
                    toast.info("No paused accounts selected to resume")
                  } else if (res.failed.length === 0) {
                    toast.success(`Successfully resumed automation on ${res.succeeded.length} account${res.succeeded.length !== 1 ? 's' : ''}`)
                  } else if (res.succeeded.length > 0) {
                    toast.warning(`Resumed ${res.succeeded.length} account(s), but ${res.failed.length} failed`)
                  } else {
                    toast.error("Failed to resume selected accounts")
                  }
                } catch (e: any) {
                  toast.error(e?.message || "Failed to resume selected accounts")
                } finally {
                  setIsBatchProcessing(false)
                }
              }}
              className="px-2.5 py-1 text-xs font-medium bg-muted hover:bg-muted/80 text-foreground rounded-lg transition-colors flex items-center gap-1 cursor-pointer disabled:opacity-50"
            >
              {isBatchProcessing ? (
                <RefreshCw size={13} className="animate-spin" />
              ) : (
                <PlayCircle size={13} />
              )}
              <span>Resume</span>
            </button>

            {/* Batch Tag Button */}
            {showBatchTagInput ? (
              <div className="flex items-center gap-1.5 bg-background border border-input rounded-lg px-2 py-0.5">
                <Tag size={12} className="text-muted-foreground" />
                <input
                  type="text"
                  value={batchTagInput}
                  onChange={(e) => setBatchTagInput(e.target.value)}
                  onKeyDown={async (e) => {
                    if (e.key === "Enter") {
                      e.preventDefault()
                      await handleApplyBatchTag()
                    } else if (e.key === "Escape") {
                      setShowBatchTagInput(false)
                      setBatchTagInput("")
                    }
                  }}
                  placeholder="Tag name..."
                  autoFocus
                  maxLength={50}
                  className="w-24 text-xs bg-transparent text-foreground placeholder:text-muted-foreground focus:outline-none"
                />
                <button
                  type="button"
                  disabled={isBatchProcessing || !batchTagInput.trim()}
                  onClick={handleApplyBatchTag}
                  className="text-[11px] font-semibold text-primary hover:underline cursor-pointer disabled:opacity-50"
                >
                  Apply
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowBatchTagInput(false)
                    setBatchTagInput("")
                  }}
                  className="text-muted-foreground hover:text-foreground cursor-pointer"
                >
                  <X size={11} />
                </button>
              </div>
            ) : (
              <button
                type="button"
                disabled={isBatchProcessing}
                onClick={() => setShowBatchTagInput(true)}
                className="px-2.5 py-1 text-xs font-medium bg-muted hover:bg-muted/80 text-foreground rounded-lg transition-colors flex items-center gap-1 cursor-pointer disabled:opacity-50"
              >
                <Tag size={12} />
                <span>Tag</span>
              </button>
            )}

            <button
              type="button"
              onClick={() => {
                fetchAccounts()
                toast.success("Accounts refreshed")
              }}
              className="px-2.5 py-1 text-xs font-medium bg-muted hover:bg-muted/80 text-foreground rounded-lg transition-colors flex items-center gap-1 cursor-pointer"
            >
              <RefreshCw size={13} /> Refresh
            </button>

            <button
              type="button"
              onClick={() => setSelectedAccounts(new Set())}
              className="text-xs font-medium text-muted-foreground hover:text-foreground transition-colors ml-2 cursor-pointer"
            >
              Clear
            </button>
          </motion.div>
        )}
      </AnimatePresence>

    </div>
  )
}
