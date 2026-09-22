import { fetcher, fetchWithAuth } from "@/lib/apiClient"
import { useState, useEffect, useMemo } from "react"
 import { motion, AnimatePresence } from "motion/react"
import {
  Plus, X, Copy, ChevronRight, CheckCircle2, AlertCircle,
  Clock, Download, Trash2, Shield, TrendingUp, Ban, AlertTriangle, RefreshCw, PauseCircle
} from "lucide-react"
import * as Dialog from "@radix-ui/react-dialog"
import * as Tooltip from "@radix-ui/react-tooltip"
import { Linkedin } from "@/components/icons/Linkedin"
import useSWR from "swr"
import { useAccountUsage, useAccountHealth, useAccountLimits } from "@/hooks/useAccounts"
import { cn } from "@/lib/utils"
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
  const { accounts, addAccount, fetchAccounts, removeAccount: remove, toggleManualMode, clearManualSendWarning } = useHRAccountsStore()
  const [showModal, setShowModal] = useState(false)
  const [refreshAccountId, setRefreshAccountId] = useState<string | null>(null)
  const [selectedAccounts, setSelectedAccounts] = useState<Set<string>>(new Set())
  const [expandedAccounts, setExpandedAccounts] = useState<Set<string>>(new Set())
  const [accountToDelete, setAccountToDelete] = useState<{id: string, name: string} | null>(null)
  const { usageData } = useAccountUsage()
  const safeUsageData = Array.isArray(usageData) ? usageData : []
  
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

  return (
    <div className="min-h-[100dvh] bg-background text-foreground px-8 py-10 max-w-4xl mx-auto font-sans">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
        <h1 className="text-2xl font-bold text-foreground mb-1">
          <ShinyText text="LinkedIn Accounts" speed={3} />
        </h1>
        <p className="text-xs text-muted-foreground leading-relaxed max-w-xl">
          LinkedIn accounts are called <span className="font-semibold text-foreground">senders</span> when put in a campaign.
          Connect multiple LinkedIn sending accounts on one campaign to increase your daily sending volume.
        </p>
      </motion.div>

      {/* Info banner */}
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="flex items-start gap-3 p-4 rounded-xl border border-border/50 bg-muted/30 dark:bg-background/50 backdrop-blur-md shadow-sm mb-6"
      >
        <Shield size={14} className="text-muted-foreground shrink-0 mt-0.5" />
        <p className="text-xs text-muted-foreground leading-relaxed">
          Accounts are connected via LinkedIn cookies only — no password is stored. Your credentials never leave your browser.
        </p>
      </motion.div>

      {/* Expired Accounts Banner */}
      {accounts.some(a => a.accountStatus === 'DISCONNECTED') && (
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-start gap-3 p-4 rounded-xl border border-destructive/20 bg-destructive/10 mb-6"
        >
          <AlertCircle size={14} className="text-destructive shrink-0 mt-0.5" />
          <p className="text-xs text-destructive leading-relaxed font-medium">
            One or more of your LinkedIn accounts have expired sessions (LinkedIn logged them out). Please remove and reconnect them to resume imports and campaigns.
          </p>
        </motion.div>
      )}

      {/* Action bar */}
      <div className="flex items-center justify-end mb-6">
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-[18px] border border-input bg-background hover:bg-accent hover:text-accent-foreground text-sm font-bold text-foreground transition-all shadow-sm"
        >
          <Plus size={14} />
          Connect account
        </button>
      </div>

      {/* Empty state */}
      {accounts.length === 0 ? (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="flex flex-col items-center justify-center py-24 rounded-2xl border border-border/50 bg-muted/30 dark:bg-background/50 backdrop-blur-md shadow-sm text-center px-8"
        >
          <div className="relative mb-6">
            <div className="w-16 h-16 rounded-2xl bg-muted border border-border flex items-center justify-center">
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
            Connect a LinkedIn account and we'll handle everything — warmup, rate limiting, outreach. Takes 2 minutes.
          </p>
          <p className="text-[11px] text-muted-foreground/60 mb-8">
            We never store your password. Only your session cookie, encrypted.
          </p>
          <StarBorder
            as="button"
            onClick={() => setShowModal(true)}
            innerClassName="flex items-center gap-2 px-6 py-3 rounded-[18px] bg-primary hover:bg-primary/90 text-sm font-bold text-primary-foreground transition-all"
            
          >
            <Linkedin size={14} />
            Connect my LinkedIn account
          </StarBorder>
        </motion.div>
      ) : (
        <div className="space-y-3">
          {sortedAccounts.map((acc, i) => {
            const isSelected = selectedAccounts.has(acc.id)
            const isExpanded = expandedAccounts.has(acc.id)
            return (
              <motion.div
                key={acc.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.06 }}
                className="group"
              >
                <SpotlightCard className={`p-4 rounded-xl border ${isSelected ? 'border-primary/50 bg-primary/5' : 'border-border bg-muted/30 dark:bg-background/50'} backdrop-blur-md hover:border-border/80 transition-all shadow-sm`} >
                  {acc.manualSendSuspected && (
                    <div className="flex items-start gap-3 p-3 mb-4 rounded-lg border border-destructive/20 bg-destructive/10">
                      <AlertCircle size={14} className="text-destructive shrink-0 mt-0.5" />
                      <div className="flex-1">
                        <p className="text-xs text-destructive font-medium">⚠️ Manual sending detected. Your account may be at risk. Pause your campaign immediately.</p>
                        <p className="text-[10px] text-destructive mt-1">We detected a discrepancy between campaign-sent and actual activity on your LinkedIn account.</p>
                      </div>
                      <button onClick={() => clearManualSendWarning(acc.id)} className="text-[10px] font-medium text-destructive hover:text-destructive px-2 py-1 bg-destructive/10 rounded-md transition-colors whitespace-nowrap">
                        I understand
                      </button>
                    </div>
                  )}
                  <div className="flex items-start gap-4">
                    <input 
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleSelect(acc.id)}
                      aria-label={`Select account ${acc.name || acc.id}`}
                      className="mt-3 w-4 h-4 rounded border-border text-primary focus:ring-primary/50 bg-background"
                    />
                    <div className="w-10 h-10 rounded-full bg-muted border border-border flex items-center justify-center shrink-0">
                      <Linkedin size={16} className="text-primary" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p 
                        className="text-sm font-semibold text-foreground cursor-pointer hover:text-primary transition-colors inline-block" 
                        onClick={() => toggleExpand(acc.id)}
                      >
                        {acc.name}
                      </p>
                      <div className="flex items-center gap-2 mt-0.5">
                        <SafetyIndicator accountId={acc.id} status={acc.accountStatus} />
                        <span className="text-[10px] text-muted-foreground">·</span>
                        <AccountUsageDisplay accountId={acc.id} usageData={usageData} />
                        <span className="text-[10px] text-muted-foreground">·</span>
                        <AccountHealthBadge accountId={acc.id} />
                      </div>
                      
                      <AccountTags accountId={acc.id} />

                      <div className="flex gap-3 mt-2">
                        <span className="text-[10px] text-muted-foreground font-medium bg-muted/50 px-2 py-0.5 rounded-md">
                          {safeUsageData.find((u: any) => u.account_id === acc.id && u.action_type === 'connection_request')?.count || 0} Connections Sent Today
                        </span>
                        <span className="text-[10px] text-muted-foreground font-medium bg-muted/50 px-2 py-0.5 rounded-md">
                          {safeUsageData.find((u: any) => u.account_id === acc.id && u.action_type === 'message')?.count || 0} Messages Sent Today
                        </span>
                        <span className="text-[10px] text-muted-foreground font-medium bg-muted/50 px-2 py-0.5 rounded-md">
                          Last Active: {formatRelativeTime(acc.lastHealthCheckAt)}
                        </span>
                      </div>
                    </div>
                    {(acc.accountStatus === "DISCONNECTED") && (
                      <button
                        onClick={() => setRefreshAccountId(acc.id)}
                        className="p-2 rounded-lg text-muted-foreground hover:text-success hover:bg-success/10 transition-all opacity-0 group-hover:opacity-100"
                        title="Reconnect Account"
                      >
                        <RefreshCw size={13} />
                      </button>
                    )}
                    
                    <Tooltip.Provider delayDuration={0}>
                      <Tooltip.Root>
                        <Tooltip.Trigger asChild>
                          <span className="inline-flex">
                            <button
                                disabled={acc.accountStatus !== 'ACTIVE' && acc.accountStatus !== 'MANUAL_MODE'}
                                onClick={() => toggleManualMode(acc.id, acc.accountStatus)}
                                className={`p-2 rounded-lg transition-all opacity-0 group-hover:opacity-100 ${(acc.accountStatus !== 'ACTIVE' && acc.accountStatus !== 'MANUAL_MODE') ? 'opacity-50 cursor-not-allowed text-muted-foreground' : acc.accountStatus === 'MANUAL_MODE' ? 'text-primary bg-primary/10 opacity-100' : 'text-muted-foreground hover:text-primary hover:bg-primary/10'}`}
                                title={acc.accountStatus === 'MANUAL_MODE' ? "Resume Automation" : "Pause Automation for Manual Login"}
                              >
                                <PauseCircle size={13} />
                            </button>
                          </span>
                        </Tooltip.Trigger>
                        {(acc.accountStatus !== 'ACTIVE' && acc.accountStatus !== 'MANUAL_MODE') && (
                          <Tooltip.Portal>
                            <Tooltip.Content className="z-[60] overflow-hidden rounded-md bg-primary px-3 py-1.5 text-xs text-primary-foreground shadow-md animate-in fade-in-0 zoom-in-95" sideOffset={5}>
                              Cannot toggle manual mode for this account status
                              <Tooltip.Arrow className="fill-primary" />
                            </Tooltip.Content>
                          </Tooltip.Portal>
                        )}
                      </Tooltip.Root>
                    </Tooltip.Provider>
                    <button
                      onClick={() => setAccountToDelete({ id: acc.id, name: acc.name })}
                      className="p-2 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all opacity-0 group-hover:opacity-100"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                  <WarmupTimeline accountId={acc.id} />
                  
                  <AnimatePresence>
                    {isExpanded && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="overflow-hidden"
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

      <AnimatePresence>
        {showModal && (
          <ConnectModal onClose={() => setShowModal(false)} onAdd={addAccount} />
        )}
      </AnimatePresence>

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

      <AnimatePresence>
        {selectedAccounts.size > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 50 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 50 }}
            className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 px-6 py-3 rounded-full bg-card border border-border shadow-2xl"
          >
            <span className="text-sm font-semibold text-foreground">
              {selectedAccounts.size} selected
            </span>
            <div className="w-px h-4 bg-border mx-2" />
            <button
              onClick={() => setSelectedAccounts(new Set())}
              className="text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
            >
              Clear
            </button>
            <Tooltip.Provider delayDuration={0}>
              <Tooltip.Root>
                <Tooltip.Trigger asChild>
                  <button disabled className="px-3 py-1.5 rounded-md bg-primary/5 text-primary/50 text-xs font-semibold cursor-not-allowed border border-primary/10">
                    Add Tag
                  </button>
                </Tooltip.Trigger>
                <Tooltip.Portal>
                  <Tooltip.Content className="z-[60] overflow-hidden rounded-md bg-primary px-3 py-1.5 text-xs text-primary-foreground shadow-md animate-in fade-in-0 zoom-in-95" sideOffset={5}>
                    Tag management coming soon
                    <Tooltip.Arrow className="fill-primary" />
                  </Tooltip.Content>
                </Tooltip.Portal>
              </Tooltip.Root>
            </Tooltip.Provider>
          </motion.div>
        )}
      </AnimatePresence>

      <DeleteAccountConfirmationDialog
        isOpen={accountToDelete !== null}
        onOpenChange={(open) => !open && setAccountToDelete(null)}
        accountId={accountToDelete?.id || ""}
        accountName={accountToDelete?.name || ""}
        onConfirm={async (id) => {
          await remove(id)
        }}
      />
    </div>
  )
}
