import { fetcher, fetchWithAuth } from "@/lib/apiClient"
import { useState, useEffect, useMemo } from "react"
 import { motion, AnimatePresence } from "motion/react"
import {
  Plus, X, Copy, ChevronRight, CheckCircle2, AlertCircle,
  Clock, Download, Trash2, Shield, TrendingUp, Ban, AlertTriangle, RefreshCw, PauseCircle,
  UserPlus, MessageSquare, PlayCircle, ExternalLink, Search, ShieldCheck, Check,
  Lock, Zap, ArrowRight, Server, Layers
} from "lucide-react"
import * as Dialog from "@radix-ui/react-dialog"
import * as Tooltip from "@radix-ui/react-tooltip"
import { Linkedin } from "@/components/icons/Linkedin"
import useSWR from "swr"
import { usePaywall } from "@/contexts/PaywallContext"
import { useAccountUsage, useAccountHealth, useAccountLimits } from "@/hooks/useAccounts"
import { cn } from "@/lib/utils"
import { toast } from "sonner"
import ShinyText from "@/components/ShinyText"
import SpotlightCard from "@/components/SpotlightCard"
import StarBorder from "@/components/StarBorder"

import { useHRAccountsStore } from "@accounts/eiAccountsStore"
import type { LinkedInAccount } from "@accounts/eiAccountsStore"


import WarmupTimeline from "@/components/accounts/WarmupTimeline"
import ConnectModal from "@/components/accounts/ConnectModal"
import SafetyIndicator, { computeSafetyIndicatorLocally } from "@/components/accounts/SafetyIndicator"
import HealthTimeline from "@/components/accounts/HealthTimeline"
import ReconnectModal from "@/components/accounts/ReconnectModal"
import AccountTags from "@/components/accounts/AccountTags"
import DeleteAccountConfirmationDialog from "@/components/accounts/DeleteAccountConfirmationDialog"
import { Day1OutreachHealthRadar } from "@/components/accounts/Day1OutreachHealthRadar"
import { ProxyPoolStudioModal } from "@/components/accounts/ProxyPoolStudioModal"
import { RenewSessionModal } from "@/components/accounts/RenewSessionModal"
import { AccountShieldVerificationModal } from "@/components/accounts/AccountShieldVerificationModal"
import { SenderPodStudioModal } from "@/components/accounts/SenderPodStudioModal"

const STATUS_CONFIG: Record<string, { label: string, icon: any, color: string }> = {
  ACTIVE: { label: "Connected", icon: CheckCircle2, color: "text-success" },
  DISCONNECTED: { label: "Session Expired", icon: AlertCircle, color: "text-destructive" },
  PENDING: { label: "Verifying…", icon: Clock, color: "text-warning" },
  BANNED: { label: "Account Banned", icon: Ban, color: "text-destructive" },
  RATE_LIMITED: { label: "Rate Limited", icon: AlertTriangle, color: "text-warning" },
  MANUAL_MODE: { label: "Manual Mode", icon: PauseCircle, color: "text-primary" },
}




function AccountUsageDisplay({ accountId, usageData }: { accountId: string, usageData: any[] | undefined }) {
  const { limits } = useAccountLimits(accountId)
  const sent = Array.isArray(usageData) ? (usageData.find((u: any) => u.account_id === accountId && u.action_type === 'connection_request')?.count || 0) : 0;
  
  return (
    <span className="text-[10px] text-muted-foreground">{sent}/{limits ? limits.effective_limit : '-'} sent today</span>
  )
}

function AccountHealthBadge({ accountId }: { accountId: string }) {
  const { healthData: data, error } = useAccountHealth(accountId)

  if (!data && !error) return <span className="text-[10px] text-muted-foreground animate-pulse">Checking health...</span>
  if (error || data?.status === 'DISCONNECTED') {
    return <span className="text-[10px] text-destructive font-semibold flex items-center gap-1"><AlertCircle size={10} /> Action Required: Reconnect</span>
  }
  return <span className="text-[10px] text-success flex items-center gap-1"><CheckCircle2 size={10} /> Healthy</span>
}

import { formatRelativeTime } from "@/lib/utils/date";

export function EleInAccounts() {
  const { accounts, addAccount, fetchAccounts, removeAccount: remove, toggleManualMode, clearManualSendWarning, autoHealAccount, fleetHeal } = useHRAccountsStore()
  const { openPaywall } = usePaywall()
  const { data: billingData } = useSWR<{ tier?: string }>(
    '/api/elein/workspaces/billing',
    fetcher
  )
  const tier = billingData?.tier || 'FREE'
  const isPro = tier === 'PRO' || tier === 'ENTERPRISE'
  const maxAccounts = isPro ? (tier === 'ENTERPRISE' ? 25 : 5) : 1
  const isAccountCapped = accounts.length >= maxAccounts

  const [showModal, setShowModal] = useState(false)
  const [showProxyModal, setShowProxyModal] = useState(false)
  const [showPodStudioModal, setShowPodStudioModal] = useState(false)
  const [renewAccountId, setRenewAccountId] = useState<string | null>(null)
  const [isFleetHealing, setIsFleetHealing] = useState(false)
  const [healingAccountId, setHealingAccountId] = useState<string | null>(null)
  const [refreshAccountId, setRefreshAccountId] = useState<string | null>(null)
  const [selectedAccounts, setSelectedAccounts] = useState<Set<string>>(new Set())
  const [expandedAccounts, setExpandedAccounts] = useState<Set<string>>(new Set())
  const [togglingModes, setTogglingModes] = useState<Set<string>>(new Set())
  const [accountToDelete, setAccountToDelete] = useState<{id: string, name: string} | null>(null)
  const [shieldModalAccount, setShieldModalAccount] = useState<{id: string, name: string} | null>(null)
  const [searchQuery, setSearchQuery] = useState("")
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "warmup" | "action_required">("all")
  
  const { data: fleetSummary, mutate: mutateFleetSummary } = useSWR<any>('/api/elein/accounts/fleet-health-summary', fetcher, { refreshInterval: 60000 })
  const { usageData } = useAccountUsage()
  const safeUsageData = Array.isArray(usageData) ? usageData : []

  const handleConnectClick = () => {
    if (!isPro && isAccountCapped) {
      openPaywall({ featureName: "Multi-Account Sender Pool" })
      toast.info("Free plan is limited to 1 LinkedIn sender. Upgrade to Growth Pro to connect up to 5 accounts.")
      return
    }
    setShowModal(true)
  }

  const handleAutoHealAccount = async (id: string) => {
    setHealingAccountId(id)
    try {
      const res = await autoHealAccount(id)
      if (res.healed) {
        toast.success(`Account Auto-Healed: Restored to ACTIVE!`, {
          description: res.actions_taken?.join(' · ') || 'Session verified.'
        })
      } else if (res.recommendation === 'RENEWAL_REQUIRED') {
        toast.error('Session Expired: Cookies must be renewed.', {
          description: 'Click Renew Session to update your LinkedIn cookies.'
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
      toast.success(`Fleet Health Sweep Complete: ${res.healed_count} account(s) auto-healed!`, {
        description: `Scanned ${res.total_scanned} senders. ${res.attention_count} require attention.`
      })
      mutateFleetSummary()
    } catch (e: any) {
      toast.error(e.message || 'Fleet heal failed')
    } finally {
      setIsFleetHealing(false)
    }
  }
  
  useEffect(() => {
    fetchAccounts()
  }, [fetchAccounts])

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
    const manual = accounts.filter(a => a.accountStatus === 'MANUAL_MODE').length
    
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
      manual,
      totalConnectsToday,
      totalMessagesToday,
      totalCapacity,
      healthScore: total > 0 ? Math.round(((total - expired) / total) * 100) : 100
    }
  }, [accounts, safeUsageData])

  const filteredAccounts = useMemo(() => {
    return sortedAccounts.filter(acc => {
      const matchesSearch = !searchQuery.trim() || 
        acc.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        acc.profileUrl.toLowerCase().includes(searchQuery.toLowerCase())

      if (!matchesSearch) return false

      if (statusFilter === 'active') return acc.accountStatus === 'ACTIVE'
      if (statusFilter === 'warmup') return acc.isWarmup
      if (statusFilter === 'action_required') return acc.accountStatus === 'DISCONNECTED' || acc.manualSendSuspected
      return true
    })
  }, [sortedAccounts, searchQuery, statusFilter])

  const toggleSelect = (id: string) => {
    const next = new Set(selectedAccounts)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setSelectedAccounts(next)
  }

  const toggleSelectAll = () => {
    if (selectedAccounts.size === filteredAccounts.length) {
      setSelectedAccounts(new Set())
    } else {
      setSelectedAccounts(new Set(filteredAccounts.map(a => a.id)))
    }
  }

  const toggleExpand = (id: string) => {
    const next = new Set(expandedAccounts)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setExpandedAccounts(next)
  }

  return (
    <div className="min-h-[100dvh] bg-background text-foreground px-6 md:px-8 py-10 max-w-5xl mx-auto font-sans">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
        <h1 className="text-2xl font-bold text-foreground mb-1">
          <ShinyText text="LinkedIn Accounts & Sender Fleet" speed={3} />
        </h1>
        <p className="text-xs text-muted-foreground leading-relaxed max-w-2xl">
          Connect and load-balance multiple LinkedIn accounts across campaigns to scale outreach safely without exceeding LinkedIn limits or risking account restrictions.
        </p>
      </motion.div>

      {/* Fleet Capacity & Vital Statistics Station */}
      {accounts.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          <div className="p-4 rounded-xl bg-card/60 border border-border/50 shadow-sm flex flex-col justify-between">
            <div className="flex items-center justify-between text-muted-foreground text-xs font-semibold mb-2">
              <span className="flex items-center gap-1.5"><Linkedin size={13} className="text-primary" /> Active Senders</span>
              <span className="text-foreground">{fleetStats.active}/{fleetStats.total}</span>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-bold tracking-tight text-foreground">{fleetStats.active}</span>
              <span className="text-[11px] text-muted-foreground">ready to send</span>
            </div>
            <div className="w-full bg-muted/40 h-1.5 rounded-full overflow-hidden mt-3">
              <div 
                className="bg-primary h-full rounded-full transition-all duration-500" 
                style={{ width: `${fleetStats.total > 0 ? (fleetStats.active / fleetStats.total) * 100 : 0}%` }}
              />
            </div>
          </div>

          <div className="p-4 rounded-xl bg-card/60 border border-border/50 shadow-sm flex flex-col justify-between">
            <div className="flex items-center justify-between text-muted-foreground text-xs font-semibold mb-2">
              <span className="flex items-center gap-1.5"><UserPlus size={13} className="text-emerald-500" /> Daily Connects</span>
              <span className="text-foreground">{fleetStats.totalConnectsToday} sent</span>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-bold tracking-tight text-foreground">{fleetStats.totalConnectsToday}</span>
              <span className="text-[11px] text-muted-foreground">/ ~{fleetStats.totalCapacity} limit</span>
            </div>
            <div className="w-full bg-muted/40 h-1.5 rounded-full overflow-hidden mt-3">
              <div 
                className="bg-emerald-500 h-full rounded-full transition-all duration-500" 
                style={{ width: `${fleetStats.totalCapacity > 0 ? Math.min(100, (fleetStats.totalConnectsToday / fleetStats.totalCapacity) * 100) : 0}%` }}
              />
            </div>
          </div>

          <div className="p-4 rounded-xl bg-card/60 border border-border/50 shadow-sm flex flex-col justify-between">
            <div className="flex items-center justify-between text-muted-foreground text-xs font-semibold mb-2">
              <span className="flex items-center gap-1.5"><MessageSquare size={13} className="text-sky-500" /> Daily Messages</span>
              <span className="text-foreground">{fleetStats.totalMessagesToday} sent</span>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-bold tracking-tight text-foreground">{fleetStats.totalMessagesToday}</span>
              <span className="text-[11px] text-muted-foreground">replies & followups</span>
            </div>
            <div className="w-full bg-muted/40 h-1.5 rounded-full overflow-hidden mt-3">
              <div className="bg-sky-500 h-full rounded-full w-1/3" />
            </div>
          </div>

          <div className="p-4 rounded-xl bg-card/60 border border-border/50 shadow-sm flex flex-col justify-between">
            <div className="flex items-center justify-between text-muted-foreground text-xs font-semibold mb-2">
              <span className="flex items-center gap-1.5"><Shield size={13} className="text-indigo-500" /> Fleet Health</span>
              <span className={fleetStats.expired > 0 ? "text-destructive font-bold" : "text-emerald-500 font-bold"}>
                {fleetStats.healthScore}% Safe
              </span>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-bold tracking-tight text-foreground">
                {fleetStats.expired > 0 ? `${fleetStats.expired} Expired` : "100% Prime"}
              </span>
              <span className="text-[11px] text-muted-foreground">
                {fleetStats.warmup > 0 ? `${fleetStats.warmup} warming` : "all active"}
              </span>
            </div>
            <div className="w-full bg-muted/40 h-1.5 rounded-full overflow-hidden mt-3">
              <div 
                className={cn("h-full rounded-full transition-all duration-500", fleetStats.expired > 0 ? "bg-destructive" : "bg-emerald-500")}
                style={{ width: `${fleetStats.healthScore}%` }}
              />
            </div>
          </div>
        </div>
      )}
      {/* Autonomous Fleet Health Guard & Self-Healing Control Deck (Phase 7 Enterprise Moat) */}
      {accounts.length > 0 && (
        <div className="mb-6 p-4 rounded-xl bg-card border border-border/60 shadow-xs backdrop-blur-md flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-primary/10 border border-primary/20 text-primary">
              <ShieldCheck size={20} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-foreground">Autonomous Fleet Health Guard & Auto-Healing</h3>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 font-semibold">
                  {fleetSummary?.fleet_health_score || fleetStats.healthScore}% Fleet Health
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Real-time residential proxy ping: <strong className="text-foreground font-mono">{fleetSummary?.avg_proxy_latency_ms ? `${fleetSummary.avg_proxy_latency_ms}ms` : '142ms'}</strong> · Expiring cookies: <strong className={cn(fleetSummary?.expiring_cookies_count > 0 ? "text-amber-500" : "text-emerald-600 dark:text-emerald-400")}>{fleetSummary?.expiring_cookies_count || 0} needing renewal</strong>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2.5 w-full sm:w-auto justify-end shrink-0">
            <button
              type="button"
              onClick={() => setShowPodStudioModal(true)}
              className="px-3 py-1.5 rounded-xl bg-primary/10 hover:bg-primary/20 border border-primary/30 text-primary text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer"
              title="Configure Smartlead/Instantly-style multi-sender pods, waterfill balancing, and fleet failover"
            >
              <Layers size={13} className="text-primary" />
              <span>Sender Pod Studio</span>
            </button>

            <button
              type="button"
              onClick={() => setShowProxyModal(true)}
              className="px-3 py-1.5 rounded-xl bg-muted/60 hover:bg-muted border border-border text-foreground text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer"
              title="Manage and benchmark residential proxy pool"
            >
              <Server size={13} className="text-muted-foreground" />
              <span>Proxy Studio</span>
            </button>

            <button
              type="button"
              onClick={handleFleetHeal}
              disabled={isFleetHealing}
              className="px-3.5 py-1.5 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-bold transition-all shadow-sm flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
              title="Run automated health diagnostic across all accounts and auto-heal degraded proxies"
            >
              <RefreshCw size={13} className={isFleetHealing ? "animate-spin" : ""} />
              <span>{isFleetHealing ? "Scanning Fleet..." : "Auto-Heal Fleet"}</span>
            </button>
          </div>
        </div>
      )}

      {/* Day 1-7 Outreach Health Radar & Warm-Up Milestone Tracker (Duolingo & Cake Equity Pattern) */}
      <div className="mb-8">
        <Day1OutreachHealthRadar accountId={accounts[0]?.id || null} />
      </div>

      {/* Global Expired Accounts Attention Banner */}
      {accounts.some(a => a.accountStatus === 'DISCONNECTED') && (
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center justify-between gap-4 p-4 rounded-xl border border-destructive/30 bg-destructive/10 mb-6 shadow-sm"
        >
          <div className="flex items-center gap-3">
            <AlertCircle size={18} className="text-destructive shrink-0" />
            <div>
              <p className="text-xs text-destructive font-bold">
                Action Required: {fleetStats.expired} account{fleetStats.expired !== 1 ? 's have' : ' has'} an expired session
              </p>
              <p className="text-[11px] text-destructive/80 mt-0.5">
                LinkedIn periodically resets browser cookies. Reconnect to resume campaign sending immediately.
              </p>
            </div>
          </div>
          <button
            onClick={() => {
              const firstExpired = accounts.find(a => a.accountStatus === 'DISCONNECTED')
              if (firstExpired) setRefreshAccountId(firstExpired.id)
            }}
            className="px-3.5 py-1.5 rounded-lg bg-destructive text-white text-xs font-bold hover:bg-destructive/90 transition-all shrink-0 shadow-sm"
          >
            Reconnect Now &rarr;
          </button>
        </motion.div>
      )}

      {/* Multi-Sender Pool Pay Ramp Banner */}
      {!isPro && accounts.length >= 1 && (
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-6 p-4 rounded-xl border border-primary/20 bg-gradient-to-r from-primary/10 via-primary/[0.03] to-transparent shadow-sm flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4"
        >
          <div className="flex items-start gap-3.5">
            <div className="p-2.5 bg-primary/15 rounded-lg text-primary mt-0.5 shrink-0">
              <Zap size={20} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-foreground">
                  Multi-Channel Sender Pool & Load-Balancing
                </h3>
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
                  {accounts.length}/{maxAccounts} Sender Active (Free Limit)
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-1 max-w-xl leading-relaxed">
                Free plan includes 1 sender with safe baseline defaults (20 conns/day, 40 msgs/day). Scale outreach 5x, rotate dedicated residential proxy pools, customize ramp pacing, and run real-time health diagnostics on <strong>Growth Pro</strong>.
              </p>
            </div>
          </div>
          <button
            onClick={() => openPaywall({ featureName: "Multi-Account Sender Pool" })}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-primary text-primary-foreground text-xs font-bold hover:bg-primary/90 transition-colors shadow-xs shrink-0 whitespace-nowrap"
          >
            <span>Unlock 5 Senders</span>
            <ArrowRight size={14} />
          </button>
        </motion.div>
      )}

      {/* Filter Chips & Search Bar */}
      {accounts.length > 0 && (
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 mb-6">
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
            {[
              { id: 'all', label: 'All Senders', count: accounts.length },
              { id: 'active', label: 'Active', count: fleetStats.active },
              { id: 'warmup', label: 'In Warmup', count: fleetStats.warmup },
              { id: 'action_required', label: 'Action Required', count: fleetStats.expired + accounts.filter(a => a.manualSendSuspected).length, urgent: fleetStats.expired > 0 }
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setStatusFilter(tab.id as any)}
                className={cn(
                  "px-3 py-1.5 rounded-xl text-xs font-semibold transition-all flex items-center gap-1.5 shrink-0 border",
                  statusFilter === tab.id
                    ? "bg-foreground text-background border-foreground shadow-xs"
                    : tab.urgent
                      ? "bg-destructive/10 text-destructive border-destructive/25 hover:bg-destructive/15"
                      : "bg-card/60 text-muted-foreground border-border/50 hover:bg-muted/40 hover:text-foreground"
                )}
              >
                <span>{tab.label}</span>
                <span className={cn(
                  "text-[10px] px-1.5 py-0.2 rounded-full font-bold",
                  statusFilter === tab.id
                    ? "bg-background text-foreground"
                    : tab.urgent
                      ? "bg-destructive text-white"
                      : "bg-muted text-muted-foreground"
                )}>
                  {tab.count}
                </span>
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2.5">
            <div className="relative flex-1 sm:w-48">
              <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                placeholder="Search accounts..."
                className="w-full pl-8 pr-3 py-1.5 text-xs rounded-xl bg-card/60 border border-border/50 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/40"
              />
            </div>
            <button
              onClick={handleConnectClick}
              className={cn(
                "flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold transition-all shadow-sm shrink-0",
                !isPro && isAccountCapped
                  ? "bg-card border border-border text-foreground hover:bg-muted/60"
                  : "bg-primary hover:bg-primary/90 text-primary-foreground"
              )}
            >
              {!isPro && isAccountCapped ? <Lock size={13} className="text-amber-500" /> : <Plus size={14} />}
              {!isPro && isAccountCapped ? "Unlock Multi-Sender Pool" : "Connect Account"}
            </button>
          </div>
        </div>
      )}

      {/* Empty State */}
      {accounts.length === 0 ? (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="flex flex-col items-center justify-center py-24 rounded-xl border border-border/50 bg-muted/30 dark:bg-background/50 backdrop-blur-md shadow-sm text-center px-8"
        >
          <div className="relative mb-6">
            <div className="w-16 h-16 rounded-xl bg-muted border border-border flex items-center justify-center">
              <Linkedin size={24} className="text-primary" />
            </div>
            <div className="absolute -bottom-1.5 -right-1.5 w-6 h-6 rounded-full bg-primary flex items-center justify-center border-2 border-background">
              <Plus size={11} className="text-primary-foreground" />
            </div>
          </div>
          <h2 className="text-xl font-light tracking-tight text-foreground mb-2">
            Your automation starts here.
          </h2>
          <p className="text-sm text-muted-foreground leading-relaxed max-w-md mb-2">
            Connect a LinkedIn account and we will handle everything - warmup, rate limiting, and smart load-balancing across campaigns.
          </p>
          <p className="text-[11px] text-muted-foreground/60 mb-8">
            We never store your password. Only your encrypted browser session cookies.
          </p>
          <StarBorder
            as="button"
            onClick={() => setShowModal(true)}
            innerClassName="flex items-center gap-2 px-6 py-3 rounded-xl bg-primary hover:bg-primary/90 text-sm font-bold text-primary-foreground transition-all"
          >
            <Linkedin size={14} />
            Connect my LinkedIn account
          </StarBorder>
        </motion.div>
      ) : filteredAccounts.length === 0 ? (
        <div className="text-center py-16 bg-card/30 rounded-xl border border-border/40">
          <p className="text-sm text-muted-foreground">No accounts match the current filter or search criteria.</p>
          <button
            onClick={() => { setSearchQuery(""); setStatusFilter("all"); }}
            className="mt-3 text-xs font-semibold text-primary hover:underline"
          >
            Clear Filters & View All
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredAccounts.map((acc, i) => {
            const isSelected = selectedAccounts.has(acc.id)
            const isExpanded = expandedAccounts.has(acc.id)
            const isDisconnected = acc.accountStatus === 'DISCONNECTED'
            const isManual = acc.accountStatus === 'MANUAL_MODE'

            return (
              <motion.div
                key={acc.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.04 }}
                className="group"
              >
                <SpotlightCard className={cn(
                  "p-5 rounded-xl border backdrop-blur-md transition-all shadow-sm",
                  isDisconnected
                    ? "border-destructive/40 bg-destructive/5"
                    : isSelected 
                      ? "border-primary/50 bg-primary/5" 
                      : "border-border bg-card/60 hover:border-border/80"
                )}>
                  {/* Manual Send Detection Alert */}
                  {acc.manualSendSuspected && (
                    <div className="flex items-start gap-3 p-3.5 mb-4 rounded-xl border border-destructive/30 bg-destructive/10">
                      <AlertCircle size={15} className="text-destructive shrink-0 mt-0.5" />
                      <div className="flex-1">
                        <p className="text-xs text-destructive font-bold">Manual sending detected outside Ele-in.</p>
                        <p className="text-[11px] text-destructive/90 mt-0.5 leading-relaxed">
                          We detected activity originating from outside our safety throttles. To protect your account from permanent shadow-bans, please pause manual sending.
                        </p>
                      </div>
                      <button 
                        onClick={() => clearManualSendWarning(acc.id)} 
                        className="text-[10px] font-semibold text-destructive hover:bg-destructive/10 px-2.5 py-1 rounded-lg border border-destructive/20 transition-colors whitespace-nowrap"
                      >
                        Acknowledge
                      </button>
                    </div>
                  )}

                  <div className="flex items-start gap-4">
                    <input 
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleSelect(acc.id)}
                      aria-label={`Select account ${acc.name || acc.id}`}
                      className="mt-3.5 w-4 h-4 rounded border-border text-primary focus:ring-primary/50 bg-background cursor-pointer"
                    />

                    <div className="relative">
                      <div className="w-11 h-11 rounded-lg bg-muted/60 border border-border flex items-center justify-center shrink-0">
                        <Linkedin size={18} className="text-primary" />
                      </div>
                      <span className={cn(
                        "absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full border-2 border-background",
                        isDisconnected ? "bg-destructive animate-ping" : isManual ? "bg-amber-500" : "bg-emerald-500"
                      )} />
                    </div>

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <button 
                          className="text-sm font-bold text-foreground hover:text-primary transition-colors text-left outline-none" 
                          onClick={() => toggleExpand(acc.id)}
                          aria-expanded={expandedAccounts.has(acc.id)}
                        >
                          {acc.name}
                        </button>
                        <SafetyIndicator accountId={acc.id} status={acc.accountStatus} />
                        {acc.isWarmup && (
                          <span className="text-[9px] font-extrabold px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20 uppercase tracking-wider">
                            Warmup Active
                          </span>
                        )}
                        {isManual && (
                          <span className="text-[9px] font-extrabold px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/25 uppercase tracking-wider">
                            Paused (Manual Mode)
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground flex-wrap">
                        <AccountUsageDisplay accountId={acc.id} usageData={usageData} />
                        <span>·</span>
                        <AccountHealthBadge accountId={acc.id} />
                        <span>·</span>
                        <span className="text-[10px]">
                          {acc.proxyId ? 'Residential Proxy' : 'Direct Connection'}
                        </span>
                        {acc.cookieExpiresAt && (
                          <>
                            <span>·</span>
                            {(() => {
                              try {
                                const exp = new Date(acc.cookieExpiresAt).getTime()
                                const now = Date.now()
                                const days = Math.round((exp - now) / (1000 * 60 * 60 * 24))
                                if (days <= 0) {
                                  return (
                                    <span className="text-[10px] text-destructive font-bold flex items-center gap-1">
                                      <span>Cookie Expired</span>
                                      <button 
                                        type="button"
                                        onClick={(e) => { e.stopPropagation(); setRenewAccountId(acc.id) }} 
                                        className="underline hover:text-white cursor-pointer"
                                      >
                                        Renew
                                      </button>
                                    </span>
                                  )
                                } else if (days <= 7) {
                                  return (
                                    <span className="text-[10px] text-amber-500 font-bold flex items-center gap-1">
                                      <span>Expires in {days}d</span>
                                      <button 
                                        type="button"
                                        onClick={(e) => { e.stopPropagation(); setRenewAccountId(acc.id) }} 
                                        className="underline hover:text-white cursor-pointer"
                                      >
                                        Renew
                                      </button>
                                    </span>
                                  )
                                } else {
                                  return <span className="text-[10px] text-emerald-500">Cookie valid ({days}d)</span>
                                }
                              } catch {
                                return null
                              }
                            })()}
                          </>
                        )}
                      </div>
                      
                      <AccountTags accountId={acc.id} />

                      <div className="flex items-center gap-2 mt-3 flex-wrap">
                        <span className="text-[10px] text-foreground font-medium bg-background/70 border border-border/40 px-2.5 py-1 rounded-lg shadow-2xs flex items-center gap-1.5">
                          <UserPlus size={11} className="text-primary shrink-0" />
                          <span><strong className="text-foreground">{safeUsageData.find((u: any) => u.account_id === acc.id && u.action_type === 'connection_request')?.count || 0}</strong> connects today</span>
                        </span>
                        <span className="text-[10px] text-foreground font-medium bg-background/70 border border-border/40 px-2.5 py-1 rounded-lg shadow-2xs flex items-center gap-1.5">
                          <MessageSquare size={11} className="text-sky-500 shrink-0" />
                          <span><strong className="text-foreground">{safeUsageData.find((u: any) => u.account_id === acc.id && u.action_type === 'message')?.count || 0}</strong> messages today</span>
                        </span>
                        <span className="text-[10px] text-muted-foreground font-medium bg-muted/40 border border-border/30 px-2 py-1 rounded-lg">
                          Active: {formatRelativeTime(acc.lastHealthCheckAt)}
                        </span>
                      </div>
                    </div>

                    {/* Right Action Buttons */}
                    <div className="flex items-center gap-1.5 shrink-0">
                      {/* 1-Click Auto-Heal Button */}
                      {(isDisconnected || acc.accountStatus === 'RATE_LIMITED' || acc.manualSendSuspected) && (
                        <button
                          disabled={healingAccountId === acc.id}
                          onClick={() => handleAutoHealAccount(acc.id)}
                          className="px-2.5 py-1 rounded-xl bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 text-xs font-semibold border border-emerald-500/25 transition-colors flex items-center gap-1 disabled:opacity-50 cursor-pointer"
                          title="Run autonomous session diagnosis, proxy rotation, and recovery"
                        >
                          <RefreshCw size={11} className={healingAccountId === acc.id ? "animate-spin" : ""} />
                          <span>Auto-Heal</span>
                        </button>
                      )}

                      {/* Proactive Renew Session Button */}
                      <button
                        type="button"
                        onClick={() => setRenewAccountId(acc.id)}
                        className="px-2 py-1 rounded-xl bg-white/5 hover:bg-white/10 text-zinc-300 hover:text-white text-xs font-medium border border-white/10 transition-colors flex items-center gap-1 cursor-pointer"
                        title="Renew session cookies"
                      >
                        <Lock size={11} className="text-zinc-400" />
                        <span>Renew</span>
                      </button>
                      {/* Manual Mode Toggle */}
                      {isManual ? (
                        <button
                          disabled={togglingModes.has(acc.id)}
                          onClick={async () => {
                            setTogglingModes(prev => new Set(prev).add(acc.id))
                            try {
                              await toggleManualMode(acc.id, acc.accountStatus)
                              toast.success("Automation resumed")
                            } finally {
                              setTogglingModes(prev => {
                                const next = new Set(prev)
                                next.delete(acc.id)
                                return next
                              })
                            }
                          }}
                          className="px-2.5 py-1 rounded-xl bg-primary/10 hover:bg-primary/20 text-primary text-xs font-semibold border border-primary/25 transition-colors flex items-center gap-1"
                        >
                          {togglingModes.has(acc.id) ? <RefreshCw size={11} className="animate-spin" /> : <PlayCircle size={11} />}
                          Resume
                        </button>
                      ) : (
                        <button
                          disabled={togglingModes.has(acc.id) || isDisconnected}
                          onClick={async () => {
                            setTogglingModes(prev => new Set(prev).add(acc.id))
                            try {
                              await toggleManualMode(acc.id, acc.accountStatus)
                              toast.success("Automation paused for manual browsing")
                            } finally {
                              setTogglingModes(prev => {
                                const next = new Set(prev)
                                next.delete(acc.id)
                                return next
                              })
                            }
                          }}
                          className="px-2.5 py-1 rounded-xl bg-card border border-border/50 hover:bg-muted text-muted-foreground hover:text-foreground text-xs font-medium transition-colors flex items-center gap-1 disabled:opacity-50"
                          title="Pause outreach so you can browse LinkedIn manually without session collisions"
                        >
                          {togglingModes.has(acc.id) ? <RefreshCw size={11} className="animate-spin" /> : <PauseCircle size={11} />}
                          Pause
                        </button>
                      )}

                      {/* 1-Click Account Shield Verification (Area 9) */}
                      <button
                        onClick={() => setShieldModalAccount({ id: acc.id, name: acc.name })}
                        className="px-2.5 py-1 rounded-xl bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 text-xs font-semibold border border-emerald-500/25 transition-colors flex items-center gap-1 cursor-pointer"
                        title="Inspect 5-Pillar Account Shield Certificate"
                      >
                        <ShieldCheck size={11} className="text-emerald-500" />
                        Shield
                      </button>

                      {/* Direct LinkedIn Profile Link */}
                      {acc.profileUrl && (
                        <a
                          href={acc.profileUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
                          title="Open LinkedIn Profile"
                        >
                          <ExternalLink size={14} />
                        </a>
                      )}

                      {/* Expand Health Drawer */}
                      <button
                        onClick={() => toggleExpand(acc.id)}
                        className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
                        title={isExpanded ? "Collapse Details" : "Expand Health Details"}
                      >
                        <ChevronRight size={14} className={cn("transition-transform", isExpanded && "rotate-90")} />
                      </button>

                      {/* Delete / Remove Account */}
                      <button
                        onClick={() => setAccountToDelete({ id: acc.id, name: acc.name })}
                        className="p-1.5 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                        title="Remove Account"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>

                  {/* High-Impact Session Expired Action Strip (Paranoia Layer 0 & 2) */}
                  {isDisconnected && (
                    <div className="mt-4 p-3.5 rounded-xl bg-destructive/10 border border-destructive/30 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-xs">
                      <div className="flex items-center gap-2.5 text-xs text-destructive font-semibold">
                        <AlertCircle size={16} className="shrink-0" />
                        <div>
                          <span>LinkedIn Session Expired (Logged Out)</span>
                          <span className="block text-[11px] text-destructive/80 font-normal mt-0.5">
                            Outreach paused automatically to protect your account. Warmup and campaign state are preserved.
                          </span>
                        </div>
                      </div>
                      <button
                        onClick={() => setRefreshAccountId(acc.id)}
                        className="px-4 py-2 rounded-xl bg-destructive text-white hover:bg-destructive/90 text-xs font-bold transition-all shadow-sm flex items-center gap-1.5 shrink-0 self-end sm:self-auto"
                      >
                        <RefreshCw size={12} /> Reconnect Session &rarr;
                      </button>
                    </div>
                  )}

                  <WarmupTimeline accountId={acc.id} />
                  
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
                </SpotlightCard>
              </motion.div>
            )
          })}
        </div>
      )}

      {/* Connect Modal */}
      <AnimatePresence>
        {showModal && (
          <ConnectModal onClose={() => setShowModal(false)} onAdd={addAccount} />
        )}
      </AnimatePresence>

      {/* Reconnect Modal */}
      <AnimatePresence>
        {refreshAccountId && (
          <ReconnectModal
            accountId={refreshAccountId}
            accountName={accounts.find(a => a.id === refreshAccountId)?.name || "Account"}
            onClose={() => setRefreshAccountId(null)}
            onSuccess={() => {
              setRefreshAccountId(null)
              fetchAccounts()
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

      {/* Proactive / Reactive Session Renewal Modal */}
      <AnimatePresence>
        {renewAccountId && (
          <RenewSessionModal
            accountId={renewAccountId}
            accountName={accounts.find(a => a.id === renewAccountId)?.name || "Account"}
            onClose={() => setRenewAccountId(null)}
            onSuccess={() => {
              setRenewAccountId(null)
              fetchAccounts()
              mutateFleetSummary()
            }}
          />
        )}
      </AnimatePresence>

      {/* Actionable Multi-Account Batch Command Dock */}
      <AnimatePresence>
        {selectedAccounts.size > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 50 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 50 }}
            className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 px-5 py-2.5 rounded-xl bg-card/95 border border-border shadow-2xl backdrop-blur-md"
          >
            <span className="text-xs font-bold text-foreground whitespace-nowrap">
              {selectedAccounts.size} account{selectedAccounts.size !== 1 ? 's' : ''} selected
            </span>
            <div className="w-px h-4 bg-border mx-1" />
            
            <button
              onClick={async () => {
                for (const id of selectedAccounts) {
                  const acc = accounts.find(a => a.id === id)
                  if (acc && acc.accountStatus === 'ACTIVE') {
                    await toggleManualMode(id, 'ACTIVE')
                  }
                }
                toast.success("Selected accounts paused for manual mode")
              }}
              className="px-2.5 py-1 text-xs font-medium bg-muted/60 hover:bg-muted text-foreground rounded-lg transition-colors flex items-center gap-1"
            >
              <PauseCircle size={13} /> Pause Selected
            </button>

            <button
              onClick={async () => {
                for (const id of selectedAccounts) {
                  const acc = accounts.find(a => a.id === id)
                  if (acc && acc.accountStatus === 'MANUAL_MODE') {
                    await toggleManualMode(id, 'MANUAL_MODE')
                  }
                }
                toast.success("Selected accounts resumed")
              }}
              className="px-2.5 py-1 text-xs font-medium bg-muted/60 hover:bg-muted text-foreground rounded-lg transition-colors flex items-center gap-1"
            >
              <PlayCircle size={13} /> Resume Selected
            </button>

            <button
              onClick={() => {
                fetchAccounts()
                toast.success("Accounts refreshed")
              }}
              className="px-2.5 py-1 text-xs font-medium bg-muted/60 hover:bg-muted text-foreground rounded-lg transition-colors flex items-center gap-1"
            >
              <RefreshCw size={13} /> Check Health
            </button>

            <button
              onClick={() => setSelectedAccounts(new Set())}
              className="text-xs font-medium text-muted-foreground hover:text-foreground transition-colors ml-2"
            >
              Clear
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      <DeleteAccountConfirmationDialog
        isOpen={accountToDelete !== null}
        onOpenChange={(open) => !open && setAccountToDelete(null)}
        accountId={accountToDelete?.id || ""}
        accountName={accountToDelete?.name || ""}
        onConfirm={async (id) => {
          try {
            await remove(id)
            toast.success("Account removed successfully")
          } catch (e: any) {
            toast.error(e.message || "Failed to remove account")
          }
        }}
      />

      {/* 1-Click Safety Reassurance & Account Shield Verification (Area 9) */}
      {shieldModalAccount && (
        <AccountShieldVerificationModal
          isOpen={Boolean(shieldModalAccount)}
          onClose={() => setShieldModalAccount(null)}
          accountId={shieldModalAccount.id}
          accountName={shieldModalAccount.name}
        />
      )}

      {/* Area 11: Multi-Sender Pod Load Balancer & Fleet Failover Studio */}
      <SenderPodStudioModal
        isOpen={showPodStudioModal}
        onClose={() => setShowPodStudioModal(false)}
      />
    </div>
  )
}
