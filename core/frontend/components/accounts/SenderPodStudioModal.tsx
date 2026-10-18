import React, { useState, useMemo } from "react"
import { motion, AnimatePresence } from "motion/react"
import useSWR from "swr"
import {
  Layers,
  ShieldCheck,
  X,
  PauseCircle,
  PlayCircle,
  Activity,
  Sliders,
  Sparkles,
  RotateCw,
  Send
} from "lucide-react"
import { toast } from "sonner"
import { fetcher, fetchWithAuth } from "@/lib/apiClient"
import ShinyText from "@/components/ShinyText"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

interface PodAccount {
  account_id: string
  name: string
  status: string
  health_badge: string
  is_quarantined: boolean
  quarantined_until?: string | null
  quarantine_reason?: string | null
  is_warmup: boolean
  daily_limit: number
  consumed_today: number
  remaining_headroom: number
  utilization_pct: number
  weight: number
  is_primary: boolean
  linkedin_profile_url?: string
}

interface SenderPod {
  pod_id: string
  campaign_id: string
  campaign_name: string
  campaign_status: string
  pod_health_status: "HEALTHY" | "DEGRADED" | "CRITICAL" | "EXHAUSTED" | "EMERGENCY_PAUSED" | "UNASSIGNED"
  dispatch_strategy: "CAPACITY_WEIGHTED" | "ROUND_ROBIN" | "WARMUP_CONSTRAINED"
  failover_enabled: boolean
  emergency_paused: boolean
  total_senders: number
  healthy_senders: number
  quarantined_senders: number
  degraded_senders: number
  total_daily_capacity: number
  total_consumed_today: number
  remaining_capacity_today: number
  pod_utilization_pct: number
  accounts: PodAccount[]
}

interface PodApiResponse {
  status: string
  data: {
    pods: SenderPod[]
    summary: {
      total_pods: number
      total_senders: number
      total_healthy: number
      total_quarantined: number
      total_daily_capacity: number
      total_consumed_today: number
      total_remaining_capacity: number
      fleet_utilization_pct: number
    }
  }
}

export function SenderPodStudioModal({
  isOpen,
  onClose
}: {
  isOpen: boolean
  onClose: () => void
}) {
  const { data: podResponse, error: _err, isLoading, mutate: mutatePods } = useSWR<PodApiResponse>(
    isOpen ? "/api/campaigns/pods" : null,
    fetcher,
    { refreshInterval: 15000 }
  )

  const [testingDispatchPod, setTestingDispatchPod] = useState<SenderPod | null>(null)
  const [testActionType, setTestActionType] = useState<string>("connection_request")
  const [isTestingDispatch, setIsTestingDispatch] = useState<boolean>(false)
  const [testDispatchResult, setTestDispatchResult] = useState<any | null>(null)
  
  // Failover simulation state
  const [failingAccountId, setFailingAccountId] = useState<string | null>(null)
  const [isFailingOver, setIsFailingOver] = useState<boolean>(false)

  // Emergency pause toggle state
  const [pausingCampaignId, setPausingCampaignId] = useState<string | null>(null)

  // Layer 2 Paranoia: Close sub-modal or main modal on Escape
  React.useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (testingDispatchPod) {
          setTestingDispatchPod(null);
        } else {
          onClose();
        }
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen, testingDispatchPod, onClose]);

  const pods = useMemo(() => podResponse?.data?.pods || [], [podResponse])
  const summary = useMemo(() => podResponse?.data?.summary, [podResponse])

  // Change Strategy Handler
  const handleStrategyChange = async (campaignId: string, newStrategy: string) => {
    try {
      const res = await fetchWithAuth(`/api/campaigns/pods/${campaignId}/strategy`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ strategy: newStrategy })
      })
      if (res.ok) {
        toast.success(`Dispatch strategy updated to ${newStrategy.replace(/_/g, " ")}.`)
        mutatePods()
      } else {
        toast.error("Failed to update dispatch strategy.")
      }
    } catch {
      toast.error("Failed to update strategy.")
    }
  }

  // Quarantine Account Handler
  const handleQuarantineAccount = async (accountId: string, hours: number = 24) => {
    try {
      const res = await fetchWithAuth(`/api/campaigns/pods/accounts/${accountId}/quarantine`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ hours, reason: "MANUAL_OPERATOR_QUARANTINE" })
      })
      if (res.ok) {
        toast.warning(`Account isolated into ${hours}h cooling quarantine.`, {
          description: "Removed from active pod rotations to protect sender health."
        })
        mutatePods()
      } else {
        toast.error("Failed to quarantine account.")
      }
    } catch {
      toast.error("Failed to quarantine account.")
    }
  }

  // Release Quarantine Handler
  const handleReleaseQuarantine = async (accountId: string) => {
    try {
      const res = await fetchWithAuth(`/api/campaigns/pods/accounts/${accountId}/release`, {
        method: "POST",
        headers: { "Content-Type": "application/json" }
      })
      if (res.ok) {
        toast.success("Quarantine released. Account restored to pod rotation.")
        mutatePods()
      } else {
        toast.error("Failed to release quarantine.")
      }
    } catch {
      toast.error("Failed to release quarantine.")
    }
  }

  // Emergency Pause / Resume Handler
  const handleToggleEmergencyPause = async (pod: SenderPod) => {
    setPausingCampaignId(pod.campaign_id)
    try {
      const endpoint = pod.emergency_paused
        ? `/api/campaigns/pods/${pod.campaign_id}/resume`
        : `/api/campaigns/pods/${pod.campaign_id}/emergency-pause`
      const res = await fetchWithAuth(endpoint, { method: "POST" })
      if (res.ok) {
        if (pod.emergency_paused) {
          toast.success(`Pod dispatches resumed for ${pod.campaign_name}.`)
        } else {
          toast.error(`Emergency Pause Activated for ${pod.campaign_name}!`, {
            description: "All in-flight outreach dispatches frozen."
          })
        }
        mutatePods()
      } else {
        toast.error("Failed to update emergency state.")
      }
    } catch {
      toast.error("Failed to update emergency state.")
    } finally {
      setPausingCampaignId(null)
    }
  }

  // Trigger Manual Failover
  const handleTriggerFailover = async (campaignId: string, failedAccountId: string) => {
    setIsFailingOver(true)
    setFailingAccountId(failedAccountId)
    try {
      const res = await fetchWithAuth(`/api/campaigns/pods/${campaignId}/failover`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          failed_account_id: failedAccountId,
          failure_reason: "OPERATOR_SIMULATED_DEGRADATION"
        })
      })
      if (res.ok) {
        const json = await res.json()
        const data = json.data
        toast.success(`Pod Failover Executed: ${data.reassigned_count} in-flight leads reassigned!`, {
          description: `Backup Account: ${data.backup_account_id ? data.backup_account_id.slice(0, 8) : 'None available'}`
        })
        mutatePods()
      } else {
        toast.error("Failover failed.")
      }
    } catch {
      toast.error("Failover execution error.")
    } finally {
      setIsFailingOver(false)
      setFailingAccountId(null)
    }
  }

  // Simulate Optimal Sender Selection
  const handleSimulateDispatch = async () => {
    if (!testingDispatchPod) return
    setIsTestingDispatch(true)
    setTestDispatchResult(null)
    try {
      const res = await fetchWithAuth(`/api/campaigns/pods/${testingDispatchPod.campaign_id}/dispatch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action_type: testActionType })
      })
      if (res.ok) {
        const json = await res.json()
        setTestDispatchResult(json.data)
      } else {
        toast.error("Simulation dispatch failed.")
      }
    } catch {
      toast.error("Simulation dispatch error.")
    } finally {
      setIsTestingDispatch(false)
    }
  }

  if (!isOpen) return null

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="sender-pod-title"
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md"
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.96 }}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-5xl bg-card border border-border shadow-2xl rounded-xl flex flex-col h-[90dvh] max-h-[90dvh] overflow-hidden text-foreground"
      >
        {/* Header */}
        <div className="p-5 border-b border-border flex items-center justify-between bg-muted/20 shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center text-primary shrink-0">
              <Layers size={20} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 id="sender-pod-title" className="text-base font-bold text-foreground">
                  <ShinyText text="Sender Pod Studio & Dynamic Fleet Balancer" speed={3} />
                </h2>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20 font-bold uppercase tracking-wider">
                  Smartlead / Instantly Model
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Pool accounts into pods, balance daily limits across healthy senders, lock thread affinity, and auto-failover seamlessly.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close modal"
            className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer shrink-0"
          >
            <X size={18} />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1">
          {/* Top Fleet Summary Metrics */}
          {summary && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="p-3.5 rounded-lg bg-card border border-border shadow-xs">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground block">
                  Active Senders in Pods
                </span>
                <div className="flex items-baseline gap-1.5 mt-1">
                  <span className="text-2xl font-bold text-foreground">{summary.total_healthy}</span>
                  <span className="text-xs text-muted-foreground">/ {summary.total_senders} registered</span>
                </div>
              </div>

              <div className="p-3.5 rounded-lg bg-card border border-border shadow-xs">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground block">
                  Daily Pod Capacity
                </span>
                <div className="flex items-baseline gap-1.5 mt-1">
                  <span className="text-2xl font-bold text-foreground">{summary.total_daily_capacity}</span>
                  <span className="text-xs text-muted-foreground">actions / day</span>
                </div>
              </div>

              <div className="p-3.5 rounded-lg bg-card border border-border shadow-xs">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground block">
                  Consumed Today
                </span>
                <div className="flex items-baseline gap-1.5 mt-1">
                  <span className="text-2xl font-bold text-emerald-500 dark:text-emerald-400">{summary.total_consumed_today}</span>
                  <span className="text-xs text-muted-foreground">
                    ({summary.total_remaining_capacity} headroom left)
                  </span>
                </div>
              </div>

              <div className="p-3.5 rounded-lg bg-card border border-border shadow-xs">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground block">
                  Fleet Utilization
                </span>
                <div className="flex items-baseline gap-1.5 mt-1">
                  <span className="text-2xl font-bold text-foreground">{summary.fleet_utilization_pct}%</span>
                  <span className="text-xs text-muted-foreground">
                    {summary.total_quarantined > 0 ? `(${summary.total_quarantined} quarantined)` : "100% prime"}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Pod Cards Section */}
          {isLoading ? (
            <div className="p-12 text-center text-xs text-muted-foreground flex flex-col items-center justify-center gap-2">
              <RotateCw size={24} className="animate-spin text-primary" />
              <span>Scanning campaign sender pods and calculating capacity headroom...</span>
            </div>
          ) : pods.length === 0 ? (
            <div className="p-12 rounded-lg border border-dashed border-border text-center space-y-3 bg-muted/20">
              <div className="w-12 h-12 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center text-primary mx-auto">
                <Layers size={24} />
              </div>
              <h3 className="text-sm font-bold text-foreground">No Campaign Pods Configured</h3>
              <p className="text-xs text-muted-foreground max-w-md mx-auto">
                Connect multiple LinkedIn accounts in your workspace and assign them to active campaigns to enable pod balancing and dynamic failover.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                  <Activity size={14} className="text-primary" />
                  <span>Configured Campaign Pods ({pods.length})</span>
                </h3>
                <span className="text-[11px] text-muted-foreground">
                  Auto-balances connection requests and messages across assigned senders
                </span>
              </div>

              <div className="grid grid-cols-1 gap-4">
                {pods.map((pod) => {
                  const isPaused = pod.emergency_paused
                  const isDegraded = pod.pod_health_status === "DEGRADED"
                  const isCritical = pod.pod_health_status === "CRITICAL"
                  const isExhausted = pod.pod_health_status === "EXHAUSTED"

                  const statusBadgeClass = isPaused
                    ? "bg-rose-500/15 text-rose-600 dark:text-rose-300 border-rose-500/30"
                    : isCritical
                    ? "bg-rose-500/15 text-rose-600 dark:text-rose-300 border-rose-500/30"
                    : isExhausted
                    ? "bg-amber-500/15 text-amber-600 dark:text-amber-300 border-amber-500/30"
                    : isDegraded
                    ? "bg-amber-500/15 text-amber-600 dark:text-amber-300 border-amber-500/30"
                    : "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300 border-emerald-500/30"

                  return (
                    <motion.div
                      key={pod.pod_id}
                      layout
                      className="p-5 rounded-lg bg-card border border-border shadow-xs space-y-4"
                    >
                      {/* Pod Top Bar */}
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/50 pb-3">
                        <div>
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-bold text-foreground">{pod.campaign_name}</span>
                            <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase bg-muted text-muted-foreground border border-border/60">
                              {pod.campaign_status}
                            </span>
                            <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold uppercase border ${statusBadgeClass}`}>
                              {pod.pod_health_status.replace(/_/g, " ")}
                            </span>
                          </div>
                          <p className="text-xs text-muted-foreground mt-0.5">
                            {pod.total_senders} senders pooled · {pod.healthy_senders} active · {pod.remaining_capacity_today} actions remaining today
                          </p>
                        </div>

                        {/* Controls Strip */}
                        <div className="flex items-center gap-2 flex-wrap">
                          {/* Strategy Dropdown */}
                          <div className="flex items-center gap-1">
                            <Select
                              value={pod.dispatch_strategy}
                              onValueChange={(val) => handleStrategyChange(pod.campaign_id, val)}
                            >
                              <SelectTrigger size="sm" className="h-7 px-2 bg-background border-border text-xs gap-1.5 w-[200px]">
                                <Sliders size={12} className="text-muted-foreground shrink-0" />
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="CAPACITY_WEIGHTED">Capacity Weighted (Waterfill)</SelectItem>
                                <SelectItem value="ROUND_ROBIN">Round Robin</SelectItem>
                                <SelectItem value="WARMUP_CONSTRAINED">Warmup Constrained</SelectItem>
                              </SelectContent>
                            </Select>
                          </div>

                          {/* Test Dispatch Button */}
                          <button
                            type="button"
                            onClick={() => {
                              setTestingDispatchPod(pod)
                              setTestDispatchResult(null)
                            }}
                            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md text-xs font-semibold bg-secondary hover:bg-secondary/80 border border-border text-foreground transition-all cursor-pointer"
                            title="Simulate which sender the load balancer will choose"
                          >
                            <Sparkles size={12} className="text-primary" />
                            <span>Test Dispatch</span>
                          </button>

                          {/* Emergency Freeze Toggle */}
                          <button
                            type="button"
                            disabled={pausingCampaignId === pod.campaign_id}
                            onClick={() => handleToggleEmergencyPause(pod)}
                            className={`inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md text-xs font-semibold transition-all cursor-pointer ${
                              isPaused
                                ? "bg-emerald-600 hover:bg-emerald-500 text-white"
                                : "bg-rose-500/10 hover:bg-rose-500/20 text-rose-600 dark:text-rose-300 border border-rose-500/30"
                            }`}
                          >
                            {isPaused ? <PlayCircle size={13} /> : <PauseCircle size={13} />}
                            <span>{isPaused ? "Resume Pod" : "Emergency Freeze"}</span>
                          </button>
                        </div>
                      </div>

                      {/* Accounts Grid within Pod */}
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                        {pod.accounts.map((acc) => {
                          const isAccQuarantined = acc.is_quarantined
                          const isAccHealthy = acc.status === "ACTIVE" && !isAccQuarantined

                          return (
                            <div
                              key={acc.account_id}
                              className={`p-3 rounded-lg border transition-all text-xs space-y-2 ${
                                isAccQuarantined
                                  ? "bg-amber-500/5 border-amber-500/30"
                                  : isAccHealthy
                                  ? "bg-background border-border/60"
                                  : "bg-rose-500/5 border-rose-500/30"
                              }`}
                            >
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                  <div className="w-7 h-7 rounded-md bg-muted flex items-center justify-center font-bold text-[10px] uppercase text-foreground">
                                    {acc.name[0] || "A"}
                                  </div>
                                  <div>
                                    <span className="font-bold text-foreground block truncate max-w-[120px]">
                                      {acc.name}
                                    </span>
                                    <span className="text-[10px] text-muted-foreground block">
                                      {acc.is_warmup ? "Warmup Stage" : "Active Fleet"}
                                    </span>
                                  </div>
                                </div>
                                <span className={`text-[9px] px-2 py-0.5 rounded-full font-bold uppercase ${
                                  isAccQuarantined
                                    ? "bg-amber-500/20 text-amber-600 dark:text-amber-300"
                                    : isAccHealthy
                                    ? "bg-emerald-500/20 text-emerald-600 dark:text-emerald-300"
                                    : "bg-rose-500/20 text-rose-600 dark:text-rose-300"
                                }`}>
                                  {acc.health_badge}
                                </span>
                              </div>

                              {/* Capacity Progress Bar */}
                              <div>
                                <div className="flex items-center justify-between text-[10px] text-muted-foreground mb-1">
                                  <span>Usage Today</span>
                                  <span className="font-mono font-semibold text-foreground">
                                    {acc.consumed_today}/{acc.daily_limit} ({acc.remaining_headroom} left)
                                  </span>
                                </div>
                                <div className="w-full bg-muted/40 h-1.5 rounded-full overflow-hidden">
                                  <div
                                    className={`h-full rounded-full transition-all ${
                                      acc.utilization_pct >= 90
                                        ? "bg-rose-500"
                                        : acc.utilization_pct >= 60
                                        ? "bg-amber-500"
                                        : "bg-primary"
                                    }`}
                                    style={{ width: `${Math.min(100, acc.utilization_pct)}%` }}
                                  />
                                </div>
                              </div>

                              {/* Action Buttons */}
                              <div className="flex items-center justify-between pt-1 border-t border-border/40 text-[10px]">
                                {isAccQuarantined ? (
                                  <button
                                    type="button"
                                    onClick={() => handleReleaseQuarantine(acc.account_id)}
                                    className="text-primary hover:underline font-semibold cursor-pointer"
                                  >
                                    Release Quarantine
                                  </button>
                                ) : (
                                  <button
                                    type="button"
                                    onClick={() => handleQuarantineAccount(acc.account_id, 24)}
                                    className="text-amber-600 dark:text-amber-400 hover:underline font-semibold cursor-pointer"
                                    title="Quarantine sender for 24h to cool down"
                                  >
                                    Cool Down (24h)
                                  </button>
                                )}

                                <button
                                  type="button"
                                  disabled={isFailingOver && failingAccountId === acc.account_id}
                                  onClick={() => handleTriggerFailover(pod.campaign_id, acc.account_id)}
                                  className="text-rose-600 dark:text-rose-400 hover:underline font-semibold cursor-pointer disabled:opacity-50"
                                  title="Simulate sudden session degradation and test dynamic failover reassignment"
                                >
                                  {isFailingOver && failingAccountId === acc.account_id ? "Failing Over..." : "Test Failover"}
                                </button>
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    </motion.div>
                  )
                })}
              </div>
            </div>
          )}
        </div>

        {/* Dispatch Simulator Sub-Modal */}
        <AnimatePresence>
          {testingDispatchPod && (
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="dispatch-sim-title"
              onClick={() => setTestingDispatchPod(null)}
              className="fixed inset-0 z-60 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs"
            >
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                onClick={(e) => e.stopPropagation()}
                className="w-full max-w-md p-5 rounded-xl bg-card border border-border shadow-2xl space-y-4 text-foreground"
              >
                <div className="flex items-center justify-between border-b border-border/60 pb-3">
                  <div className="flex items-center gap-2">
                    <Sparkles size={16} className="text-primary" />
                    <h3 id="dispatch-sim-title" className="text-sm font-bold text-foreground">
                      Test Pod Balancer Dispatch — {testingDispatchPod.campaign_name}
                    </h3>
                  </div>
                  <button
                    type="button"
                    onClick={() => setTestingDispatchPod(null)}
                    aria-label="Close test dialog"
                    className="text-muted-foreground hover:text-foreground text-xs cursor-pointer p-1 rounded-md hover:bg-muted transition-colors"
                  >
                    <X size={14} />
                  </button>
                </div>

                <div className="space-y-3">
                  <div>
                    <label className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground block mb-1">
                      Action Type
                    </label>
                    <Select
                      value={testActionType}
                      onValueChange={(val) => setTestActionType(val)}
                    >
                      <SelectTrigger className="w-full h-9 px-3 py-2 text-xs bg-background border-border text-foreground">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="connection_request">Connection Request</SelectItem>
                        <SelectItem value="message">LinkedIn Message</SelectItem>
                        <SelectItem value="inmail">Sales Nav InMail</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="p-3 rounded-lg bg-muted/30 border border-border text-xs text-muted-foreground space-y-1">
                    <p>
                      Active Strategy: <strong className="text-foreground">{testingDispatchPod.dispatch_strategy}</strong>
                    </p>
                    <p>
                      Evaluates current daily headroom, warmup constraints, and thread locks across {testingDispatchPod.total_senders} senders.
                    </p>
                  </div>

                  {testDispatchResult && (
                    <div className="p-3.5 rounded-lg bg-primary/10 border border-primary/20 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-[11px] font-bold text-primary">Selected Optimal Sender</span>
                        <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded-full bg-primary/20 text-primary">
                          {testDispatchResult.status}
                        </span>
                      </div>
                      <p className="text-xs font-bold text-foreground">
                        {testDispatchResult.account_name || testDispatchResult.account_id}
                      </p>
                      <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                        <span>Headroom: <strong>{testDispatchResult.remaining_headroom} actions</strong></span>
                        <span>Used: <strong>{testDispatchResult.consumed_today}/{testDispatchResult.daily_limit}</strong></span>
                      </div>
                    </div>
                  )}
                </div>

                <div className="flex items-center justify-end gap-2 pt-2 border-t border-border/60">
                  <button
                    type="button"
                    onClick={() => setTestingDispatchPod(null)}
                    className="px-3.5 py-1.5 rounded-md text-xs font-semibold text-muted-foreground hover:text-foreground hover:bg-muted transition-all cursor-pointer"
                  >
                    Close
                  </button>
                  <button
                    type="button"
                    disabled={isTestingDispatch}
                    onClick={handleSimulateDispatch}
                    className="inline-flex items-center gap-1.5 px-4 py-2 rounded-md text-xs font-semibold bg-primary hover:bg-primary/90 text-primary-foreground transition-all cursor-pointer disabled:opacity-50 shadow-xs"
                  >
                    {isTestingDispatch ? (
                      <>
                        <RotateCw size={13} className="animate-spin" />
                        <span>Evaluating Headroom...</span>
                      </>
                    ) : (
                      <>
                        <Send size={13} />
                        <span>Run Selection Test</span>
                      </>
                    )}
                  </button>
                </div>
              </motion.div>
            </div>
          )}
        </AnimatePresence>

        {/* Modal Footer */}
        <div className="p-4 border-t border-border flex items-center justify-between bg-muted/20 shrink-0">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <ShieldCheck size={14} className="text-emerald-500 dark:text-emerald-400" />
            <span>Autonomous Failover & Thread Affinity Protection active</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-md text-xs font-semibold bg-secondary hover:bg-secondary/80 border border-border text-foreground transition-all cursor-pointer shadow-xs"
          >
            Done
          </button>
        </div>
      </motion.div>
    </div>
  )
}
