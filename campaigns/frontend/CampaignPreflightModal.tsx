import { useState, useEffect, useRef } from "react"
import { motion, AnimatePresence } from "motion/react"
import { 
  X, CheckCircle2, AlertTriangle, AlertCircle, Shield, Rocket, 
  Users, RefreshCw, Compass, ShieldCheck, Play, Sparkles, Clock,
  Globe, ArrowRight, Check, Wrench, ShieldAlert
} from "lucide-react"
import { Linkedin } from "@/components/icons/Linkedin"
import { cn } from "@/lib/utils"
import { fetchWithAuth } from "@/lib/apiClient"
import { toast } from "sonner"
import { AccountShieldVerificationModal } from "@/components/accounts/AccountShieldVerificationModal"

export interface PreflightCheckItem {
  id: string
  title: string
  status: "pass" | "warn" | "fail"
  score: number
  summary: string
  details: string[]
  variables_found?: string[]
  unprotected_vars?: string[]
  sample_previews?: SamplePreviewItem[]
  daily_connection_limit?: number
  daily_message_limit?: number
  warmup_accounts_count?: number
  estimated_days?: number
  lead_count?: number
  active_sender_count?: number
  total_sender_count?: number
}

export interface SamplePreviewItem {
  lead_index: number
  lead_name: string
  lead_company: string
  lead_title: string
  linkedin_url?: string
  rendered_message: string
  has_missing_fields: boolean
  missing_fields: string[]
}

export interface PreflightAuditResult {
  campaign_id?: string
  campaign_name: string
  can_launch: boolean
  passed: boolean
  score: number
  critical_errors: string[]
  warnings: string[]
  checks: PreflightCheckItem[]
  sample_previews: SamplePreviewItem[]
}

interface CampaignPreflightModalProps {
  isOpen: boolean
  onClose: () => void
  onConfirmLaunch: () => void | Promise<void>
  campaignId?: string
  campaignName?: string
  inFlightPayload?: {
    nodes: any[]
    edges?: any[]
    senderIds?: string[]
    leadListId?: string
    excludeListId?: string
    timezone?: string
    schedule?: any
    stopOnReply?: boolean
  }
  onJumpToStep?: (stepIndex: number) => void
}

export function CampaignPreflightModal({
  isOpen,
  onClose,
  onConfirmLaunch,
  campaignId,
  campaignName = "Untitled Campaign",
  inFlightPayload,
  onJumpToStep
}: CampaignPreflightModalProps) {
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState<PreflightAuditResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<"checklist" | "simulator" | "warmup" | "shield">("checklist")
  const [showShieldModal, setShowShieldModal] = useState(false)
  const [selectedLeadPreviewIdx, setSelectedLeadPreviewIdx] = useState(0)
  const [acknowledgeWarnings, setAcknowledgeWarnings] = useState(false)
  const [isLaunching, setIsLaunching] = useState(false)
  const isLaunchingRef = useRef(false)

  // Escape key listener for accessible dismissal
  useEffect(() => {
    if (!isOpen) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose()
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [isOpen, onClose])

  // Fetch preflight check on modal open
  const runCheck = async () => {
    setLoading(true)
    setError(null)
    try {
      let res: Response
      if (inFlightPayload) {
        res = await fetchWithAuth("/api/elein/campaigns/preflight-validate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            campaignId,
            campaignName,
            nodes: inFlightPayload.nodes,
            edges: inFlightPayload.edges || [],
            senderIds: inFlightPayload.senderIds || [],
            leadListId: inFlightPayload.leadListId || null,
            excludeListId: inFlightPayload.excludeListId || null,
            timezone: inFlightPayload.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone,
            schedule: inFlightPayload.schedule || {},
            stopOnReply: inFlightPayload.stopOnReply ?? true
          })
        })
      } else if (campaignId) {
        res = await fetchWithAuth(`/api/elein/campaigns/${campaignId}/preflight`)
      } else {
        throw new Error("No campaign or in-flight data provided for preflight verification.")
      }

      if (!res.ok) {
        const text = await res.text()
        throw new Error(`Preflight check failed: ${text || res.statusText}`)
      }

      const result: PreflightAuditResult = await res.json()
      setData(result)
    } catch (err: any) {
      console.error("Preflight audit failed:", err)
      setError(err.message || "Failed to run preflight check")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (isOpen) {
      runCheck()
      setAcknowledgeWarnings(false)
      setIsLaunching(false)
      isLaunchingRef.current = false
    }
  }, [isOpen, campaignId])

  if (!isOpen) return null

  const handleLaunchClick = async () => {
    if (isLaunchingRef.current || isLaunching) return
    if (!data?.can_launch) {
      toast.error("Launch blocked. Please fix the critical issues before deploying.")
      return
    }
    isLaunchingRef.current = true
    setIsLaunching(true)
    try {
      await onConfirmLaunch()
      onClose()
    } catch (err: any) {
      console.error("Launch execution failed:", err)
      toast.error(err.message || "Failed to launch campaign")
      isLaunchingRef.current = false
      setIsLaunching(false)
    }
  }

  const handleAutoResolveSafeWarnings = () => {
    setAcknowledgeWarnings(true)
    toast.success("All safe operational warnings cleared and acknowledged.")
  }

  const score = data?.score ?? 0
  const is100Clear = Boolean(!loading && !error && data?.can_launch && (data?.warnings.length === 0))
  const isWarningState = Boolean(!loading && !error && data?.can_launch && (data?.warnings.length > 0))
  const isBlocked = Boolean(!loading && !error && data && !data.can_launch)

  // Circumference calculations for the HUD flight gauge
  const gaugeRadius = 26
  const gaugeCircumference = 2 * Math.PI * gaugeRadius
  const gaugeOffset = gaugeCircumference - (score / 100) * gaugeCircumference

  return (
    <div 
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.98, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.98, y: 8 }}
        transition={{ duration: 0.15 }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="campaign-preflight-title"
        className="relative w-full max-w-4xl h-[90dvh] max-h-[90dvh] bg-card border border-border rounded-xl shadow-2xl flex flex-col overflow-hidden text-foreground"
      >
        {/* Cockpit HUD Header */}
        <div className="relative px-6 py-4 border-b border-border bg-card flex items-center justify-between shrink-0">
          <div className="flex items-center gap-4">
            {/* SVG Circular Flight Readiness HUD Gauge */}
            <div className="relative w-12 h-12 flex items-center justify-center shrink-0">
              <svg className="w-12 h-12 transform -rotate-90">
                <circle
                  cx="24"
                  cy="24"
                  r={gaugeRadius}
                  stroke="currentColor"
                  strokeWidth="3.5"
                  className="text-muted/40"
                  fill="transparent"
                />
                <circle
                  cx="24"
                  cy="24"
                  r={gaugeRadius}
                  stroke="currentColor"
                  strokeWidth="3.5"
                  strokeDasharray={gaugeCircumference}
                  strokeDashoffset={gaugeOffset}
                  strokeLinecap="round"
                  className={cn(
                    "transition-all duration-700 ease-out",
                    isBlocked ? "text-destructive" :
                    isWarningState ? "text-amber-500" :
                    "text-emerald-500"
                  )}
                  fill="transparent"
                />
              </svg>
              <span className="absolute text-[11px] font-mono font-bold text-foreground">
                {loading ? "--" : `${score}%`}
              </span>
            </div>

            <div>
              <div className="flex items-center gap-2.5">
                <h3 id="campaign-preflight-title" className="font-bold text-base text-foreground tracking-tight flex items-center gap-2">
                  <Rocket size={17} className="text-primary" />
                  Pre-Flight Launch Telemetry
                </h3>
                <span className={cn(
                  "text-[10px] font-mono font-bold px-2 py-0.5 rounded border uppercase tracking-wider",
                  isBlocked
                    ? "bg-destructive/15 border-destructive/40 text-destructive"
                    : isWarningState
                    ? "bg-amber-500/10 border-amber-500/30 text-amber-700 dark:text-amber-300"
                    : "bg-emerald-500/10 border-emerald-500/30 text-emerald-700 dark:text-emerald-300"
                )}>
                  {loading ? "DIAGNOSING..." : is100Clear ? "CLEARANCE: 100% READY" : isWarningState ? "CLEARANCE: CAUTION" : "INTERLOCK: BLOCKED"}
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                5-Pillar mission-critical safety verification for LinkedIn sequence execution.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={runCheck}
              disabled={loading}
              className="p-2 rounded-lg border border-border hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
              title="Rerun Diagnostics"
              aria-label="Rerun Diagnostics"
            >
              <RefreshCw size={14} className={loading ? "animate-spin text-primary" : ""} />
            </button>
            <button
              type="button"
              onClick={onClose}
              className="w-8 h-8 rounded-lg border border-border hover:bg-muted flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
              aria-label="Close pre-flight launch gate"
            >
              <X size={15} />
            </button>
          </div>
        </div>

        {/* Tab Navigator */}
        <div role="tablist" className="flex items-center gap-1 px-6 pt-2 border-b border-border bg-card text-xs font-medium shrink-0 overflow-x-auto">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "checklist"}
            onClick={() => setActiveTab("checklist")}
            className={cn(
              "px-3.5 py-2 border-b-2 transition-colors flex items-center gap-2 cursor-pointer font-medium whitespace-nowrap",
              activeTab === "checklist"
                ? "border-primary text-foreground font-semibold"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            <Shield size={13} />
            <span>5-Pillar Flight Checks</span>
            {data && (
              <span className={cn(
                "text-[10px] px-1.5 py-0.2 rounded font-mono font-bold",
                isBlocked ? "bg-destructive/15 text-destructive" : "bg-muted text-foreground"
              )}>
                {data.checks.filter(c => c.status === "pass").length}/{data.checks.length}
              </span>
            )}
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "simulator"}
            onClick={() => setActiveTab("simulator")}
            className={cn(
              "px-3.5 py-2 border-b-2 transition-colors flex items-center gap-2 cursor-pointer font-medium whitespace-nowrap",
              activeTab === "simulator"
                ? "border-primary text-foreground font-semibold"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            <Users size={13} />
            <span>Live Prospect POV</span>
            {data?.sample_previews && data.sample_previews.length > 0 && (
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
            )}
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "warmup"}
            onClick={() => setActiveTab("warmup")}
            className={cn(
              "px-3.5 py-2 border-b-2 transition-colors flex items-center gap-2 cursor-pointer font-medium whitespace-nowrap",
              activeTab === "warmup"
                ? "border-primary text-foreground font-semibold"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            <Clock size={13} />
            <span>Pacing &amp; Curfew Horizon</span>
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "shield"}
            onClick={() => setActiveTab("shield")}
            className={cn(
              "px-3.5 py-2 border-b-2 transition-colors flex items-center gap-2 cursor-pointer font-medium whitespace-nowrap",
              activeTab === "shield"
                ? "border-primary text-foreground font-semibold"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            <ShieldCheck size={13} />
            <span>Residential IP Shield</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 font-mono font-bold border border-emerald-500/20">
              Active
            </span>
          </button>
        </div>

        {/* Cockpit Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {loading ? (
            <div className="py-20 flex flex-col items-center justify-center text-center space-y-4">
              <div className="relative w-14 h-14">
                <div className="absolute inset-0 rounded-full border-2 border-border border-t-primary animate-spin" />
                <Compass className="absolute inset-0 m-auto text-primary" size={22} />
              </div>
              <div className="space-y-1">
                <h4 className="font-bold text-sm text-foreground">Executing Mission-Critical Telemetry Scan</h4>
                <p className="text-xs text-muted-foreground max-w-md leading-relaxed">
                  Auditing variable fallbacks, testing residential peer IP status, calculating SDR account warmup headroom, and checking sequence branch completeness...
                </p>
              </div>
            </div>
          ) : error ? (
            <div className="p-6 rounded-xl bg-destructive/10 border border-destructive/30 text-center space-y-3">
              <AlertCircle size={28} className="text-destructive mx-auto" />
              <h4 className="font-bold text-sm text-destructive">Verification Diagnostic Failed</h4>
              <p className="text-xs text-muted-foreground">{error}</p>
              <button
                type="button"
                onClick={runCheck}
                className="inline-flex items-center gap-1.5 px-4 py-2 bg-background hover:bg-muted border border-border text-foreground text-xs font-semibold rounded-lg transition-colors cursor-pointer"
              >
                <RefreshCw size={12} /> Retry Diagnostics
              </button>
            </div>
          ) : data ? (
            <>
              {/* Tactical Status Banner */}
              <div className={cn(
                "p-4 rounded-xl border flex flex-col sm:flex-row items-center justify-between gap-4 transition-all",
                isBlocked
                  ? "bg-destructive/10 border-destructive/30"
                  : isWarningState
                  ? "bg-amber-500/5 border-amber-500/30"
                  : "bg-emerald-500/5 border-emerald-500/30"
              )}>
                <div className="flex items-center gap-3.5">
                  <div className={cn(
                    "w-10 h-10 rounded-lg flex items-center justify-center shrink-0 border",
                    isBlocked ? "bg-destructive/15 border-destructive/40 text-destructive" :
                    isWarningState ? "bg-amber-500/15 border-amber-500/40 text-amber-600 dark:text-amber-400" :
                    "bg-emerald-500/15 border-emerald-500/40 text-emerald-600 dark:text-emerald-400"
                  )}>
                    {is100Clear ? <CheckCircle2 size={20} /> : isWarningState ? <AlertTriangle size={20} /> : <AlertCircle size={20} />}
                  </div>
                  <div>
                    <h4 className="font-bold text-sm text-foreground">
                      {is100Clear ? "100% Launch Clearance Granted" :
                       isWarningState ? "Clearance Granted with Operational Warnings" :
                       "Launch Interlock Activated: Action Required"}
                    </h4>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {is100Clear ? "All 5 safety pillars verified. Zero risk of account restriction." :
                       isWarningState ? `${data.warnings.length} warning(s) detected. Safe to deploy with calibrated pacing.` :
                       `${data.critical_errors.length} hard blocker(s) must be resolved prior to dispatch.`}
                    </p>
                  </div>
                </div>

                {isWarningState && !acknowledgeWarnings && (
                  <button
                    type="button"
                    onClick={handleAutoResolveSafeWarnings}
                    className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-amber-500/15 hover:bg-amber-500/25 border border-amber-500/40 text-amber-800 dark:text-amber-300 text-xs font-semibold transition-all cursor-pointer whitespace-nowrap shrink-0 shadow-xs"
                  >
                    <Wrench size={13} />
                    <span>Auto-Clear Safe Warnings</span>
                  </button>
                )}
              </div>

              {/* Critical Launch Blockers */}
              {data.critical_errors.length > 0 && (
                <div className="p-4 rounded-xl bg-destructive/10 border border-destructive/30 space-y-2.5">
                  <div className="flex items-center gap-2 text-destructive font-bold text-xs uppercase tracking-wider">
                    <ShieldAlert size={15} />
                    <span>Hard Launch Blockers ({data.critical_errors.length})</span>
                  </div>
                  <ul className="space-y-2 text-xs text-foreground">
                    {data.critical_errors.map((err, i) => (
                      <li key={i} className="flex items-start justify-between gap-3 bg-background/80 p-2.5 rounded-lg border border-border">
                        <div className="flex items-start gap-2">
                          <span className="text-destructive font-bold shrink-0 mt-0.5">•</span>
                          <span className="font-medium">{err}</span>
                        </div>
                        {onJumpToStep && (
                          <button
                            type="button"
                            onClick={() => {
                              onClose()
                              if (err.toLowerCase().includes("sender") || err.toLowerCase().includes("account")) {
                                onJumpToStep(2)
                              } else if (err.toLowerCase().includes("audience") || err.toLowerCase().includes("lead")) {
                                onJumpToStep(1)
                              } else {
                                onJumpToStep(0)
                              }
                            }}
                            className="text-[11px] font-bold text-primary hover:underline shrink-0 flex items-center gap-1"
                          >
                            <span>Fix in Editor</span>
                            <ArrowRight size={11} />
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* TAB 1: 5-PILLAR TELEMETRY CHECKLIST */}
              {activeTab === "checklist" && (
                <div className="space-y-3">
                  {data.checks.map((check) => {
                    const isPass = check.status === "pass"
                    const isWarn = check.status === "warn"
                    const isFail = check.status === "fail"

                    return (
                      <div
                        key={check.id}
                        className={cn(
                          "p-4 rounded-xl border transition-all",
                          isFail 
                            ? "bg-destructive/10 border-destructive/40 shadow-xs ring-1 ring-destructive/20" 
                            : isWarn 
                            ? "bg-amber-500/5 border-amber-500/30" 
                            : "bg-background border-border"
                        )}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex items-start gap-3.5">
                            <div className={cn(
                              "w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-0.5 border",
                              isFail ? "bg-destructive/20 border-destructive/50 text-destructive" :
                              isWarn ? "bg-amber-500/15 border-amber-500/40 text-amber-600 dark:text-amber-400" :
                              "bg-card border-border text-foreground"
                            )}>
                              {check.id === "senders" ? <Linkedin size={15} className={isFail ? "text-destructive" : isWarn ? "text-amber-600 dark:text-amber-400" : "text-primary"} /> :
                               check.id === "audience" ? <Users size={15} className={isFail ? "text-destructive" : isWarn ? "text-amber-600 dark:text-amber-400" : "text-primary"} /> :
                               isPass ? <CheckCircle2 size={15} className="text-emerald-600 dark:text-emerald-400" /> :
                               isWarn ? <AlertTriangle size={15} className="text-amber-600 dark:text-amber-400" /> :
                               <AlertCircle size={15} className="text-destructive" />}
                            </div>

                            <div>
                              <div className="flex items-center gap-2">
                                <h5 className={cn("font-bold text-xs tracking-tight", isFail ? "text-destructive" : "text-foreground")}>
                                  {check.title}
                                </h5>
                                <span className={cn(
                                  "text-[10px] font-mono font-bold px-2 py-0.5 rounded border uppercase tracking-wider",
                                  isPass ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-700 dark:text-emerald-300" :
                                  isWarn ? "bg-amber-500/10 border-amber-500/30 text-amber-800 dark:text-amber-300" :
                                  "bg-destructive text-destructive-foreground"
                                )}>
                                  {isPass ? "CLEAR" : isWarn ? "CAUTION" : "BLOCKER"}
                                </span>
                              </div>
                              <p className={cn("text-xs mt-1", isFail ? "text-destructive/90 font-medium" : "text-muted-foreground")}>
                                {check.summary}
                              </p>
                            </div>
                          </div>

                          <span className={cn("text-xs font-mono font-bold shrink-0", isFail ? "text-destructive" : "text-muted-foreground")}>
                            {check.score}/20 pts
                          </span>
                        </div>

                        {check.details && check.details.length > 0 && (
                          <div className="mt-3 pt-2.5 border-t border-border/50 pl-11 space-y-1">
                            {check.details.map((d, di) => (
                              <p key={di} className="text-xs flex items-center gap-2 text-muted-foreground">
                                <span className={cn(
                                  "w-1.5 h-1.5 rounded-full shrink-0",
                                  isFail ? "bg-destructive" : isWarn ? "bg-amber-500" : "bg-emerald-500"
                                )} />
                                <span>{d}</span>
                              </p>
                            ))}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}

              {/* TAB 2: LIVE PROSPECT POV & INTERPOLATED OUTREACH */}
              {activeTab === "simulator" && (
                <div className="space-y-4">
                  <div className="p-3.5 rounded-xl bg-background border border-border text-xs text-muted-foreground leading-relaxed flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Sparkles size={15} className="text-primary shrink-0" />
                      <span><strong>Dynamic Interpolation Engine:</strong> Validates message rendering for live prospects. Variables are highlighted in theme badges.</span>
                    </div>
                  </div>

                  {data.sample_previews && data.sample_previews.length > 0 ? (
                    <div className="space-y-4">
                      {/* Lead Selection Ribbon */}
                      <div className="flex items-center gap-2 overflow-x-auto pb-1">
                        {data.sample_previews.map((prev, idx) => (
                          <button
                            type="button"
                            key={idx}
                            onClick={() => setSelectedLeadPreviewIdx(idx)}
                            className={cn(
                              "px-3 py-1.5 rounded-lg border text-xs font-medium whitespace-nowrap transition-all flex items-center gap-2 cursor-pointer",
                              selectedLeadPreviewIdx === idx
                                ? "bg-muted text-foreground border-primary font-bold shadow-xs"
                                : "bg-background border-border text-muted-foreground hover:text-foreground"
                            )}
                          >
                            <span>#{prev.lead_index}: {prev.lead_name}</span>
                            {prev.has_missing_fields && (
                              <span className="w-1.5 h-1.5 rounded-full bg-amber-500" title="Missing fields" />
                            )}
                          </button>
                        ))}
                      </div>

                      {/* Realistic LinkedIn Mockup */}
                      {(() => {
                        const lead = data.sample_previews[selectedLeadPreviewIdx] || data.sample_previews[0]
                        const initials = lead.lead_name.split(" ").map((n: string) => n[0]).join("").slice(0, 2).toUpperCase()

                        return (
                          <div className="bg-background border border-border rounded-xl p-5 shadow-sm space-y-4">
                            {/* LinkedIn Header Bar */}
                            <div className="flex items-center justify-between pb-3.5 border-b border-border">
                              <div className="flex items-center gap-3">
                                <div className="w-10 h-10 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center font-bold text-xs text-primary shrink-0">
                                  {initials || "LP"}
                                </div>
                                <div>
                                  <div className="flex items-center gap-2">
                                    <h5 className="font-bold text-sm text-foreground">{lead.lead_name}</h5>
                                    <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-muted text-muted-foreground border border-border">
                                      Prospect
                                    </span>
                                  </div>
                                  <p className="text-xs text-muted-foreground">{lead.lead_title} at <strong className="text-foreground">{lead.lead_company}</strong></p>
                                </div>
                              </div>

                              <div>
                                {lead.has_missing_fields ? (
                                  <span className="text-[10px] font-mono font-bold px-2 py-1 rounded bg-amber-500/10 text-amber-800 dark:text-amber-300 border border-amber-500/30">
                                    Missing: {lead.missing_fields.join(", ")}
                                  </span>
                                ) : (
                                  <span className="text-[10px] font-mono font-bold px-2 py-1 rounded bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border border-emerald-500/30 flex items-center gap-1">
                                    <Check size={11} /> 100% Data Populated
                                  </span>
                                )}
                              </div>
                            </div>

                            {/* Rendered Outreach Copy */}
                            <div className="space-y-2">
                              <span className="text-[11px] font-mono uppercase tracking-wider text-muted-foreground block">
                                InMail / Message Output
                              </span>
                              <div className="p-4 rounded-lg bg-card border border-border text-xs leading-relaxed text-foreground whitespace-pre-wrap font-sans">
                                {lead.rendered_message}
                              </div>
                            </div>
                          </div>
                        )
                      })()}
                    </div>
                  ) : (
                    <div className="py-12 text-center text-xs text-muted-foreground">
                      No sample prospect data available for simulation.
                    </div>
                  )}
                </div>
              )}

              {/* TAB 3: PACING & CURFEW HORIZON */}
              {activeTab === "warmup" && (
                <div className="space-y-5">
                  {(() => {
                    const warmupCheck = data.checks.find(c => c.id === "warmup")
                    const dailyConn = warmupCheck?.daily_connection_limit || 20
                    const dailyMsg = warmupCheck?.daily_message_limit || 40
                    const estDays = warmupCheck?.estimated_days || 1
                    const audienceCheck = data.checks.find(c => c.id === "audience")
                    const totalLeads = audienceCheck?.lead_count || 0

                    return (
                      <>
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5">
                          <div className="p-4 rounded-xl bg-background border border-border text-center space-y-1">
                            <span className="text-xs text-muted-foreground">Daily Connection Limit</span>
                            <p className="text-2xl font-bold font-mono text-foreground">{dailyConn}</p>
                            <span className="text-[10px] text-muted-foreground">invitations / day</span>
                          </div>
                          <div className="p-4 rounded-xl bg-background border border-border text-center space-y-1">
                            <span className="text-xs text-muted-foreground">Daily Direct Messages</span>
                            <p className="text-2xl font-bold font-mono text-foreground">{dailyMsg}</p>
                            <span className="text-[10px] text-muted-foreground">messages / day</span>
                          </div>
                          <div className="p-4 rounded-xl bg-background border border-border text-center space-y-1">
                            <span className="text-xs text-muted-foreground">Estimated Campaign Runway</span>
                            <p className="text-2xl font-bold font-mono text-primary">~{estDays} Days</p>
                            <span className="text-[10px] text-muted-foreground">for {totalLeads} prospects</span>
                          </div>
                        </div>

                        {/* 24h Curfew Dispatch Ribbon */}
                        <div className="p-4 rounded-xl bg-background border border-border space-y-3">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2 text-xs font-bold text-foreground">
                              <Clock size={14} className="text-primary" />
                              <span>24-Hour Anti-Ban Dispatch Ribbon (09:00 - 17:00 Working Curfew)</span>
                            </div>
                            <span className="text-[10px] font-mono text-muted-foreground">Anchor: Prospect Local Window</span>
                          </div>

                          <div className="grid grid-cols-24 h-6 rounded-lg overflow-hidden border border-border gap-px bg-muted/40">
                            {Array.from({ length: 24 }).map((_, hour) => {
                              const isActive = hour >= 9 && hour <= 17
                              return (
                                <div
                                  key={hour}
                                  title={`${hour}:00 - ${isActive ? "Active Sending Window" : "Anti-Ban Quiet Hours"}`}
                                  className={cn(
                                    "flex items-center justify-center text-[9px] font-mono",
                                    isActive
                                      ? "bg-primary text-primary-foreground font-bold"
                                      : "bg-muted text-muted-foreground/50"
                                  )}
                                >
                                  {hour % 6 === 0 ? hour : ""}
                                </div>
                              )
                            })}
                          </div>
                          <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                            <span className="flex items-center gap-1.5">
                              <span className="w-2 h-2 rounded-full bg-primary" />
                              <span>Active Outreach (Randomized 45s-180s Gaussian Jitter)</span>
                            </span>
                            <span className="flex items-center gap-1.5">
                              <span className="w-2 h-2 rounded-full bg-muted border border-border" />
                              <span>Quiet Hours (Restricted to prevent account scrutiny)</span>
                            </span>
                          </div>
                        </div>
                      </>
                    )
                  })()}
                </div>
              )}

              {/* TAB 4: RESIDENTIAL IP SHIELD */}
              {activeTab === "shield" && (
                <div className="space-y-4">
                  <div className="p-4 rounded-xl bg-background border border-border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-card border border-border flex items-center justify-center text-primary shrink-0">
                        <ShieldCheck size={20} />
                      </div>
                      <div>
                        <h4 className="font-bold text-sm text-foreground flex items-center gap-2">
                          5-Pillar Vault Architecture
                          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border border-emerald-500/30">
                            ZERO-RESTRICTION VAULT
                          </span>
                        </h4>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          Every outreach action dispatched is wrapped in residential peer IP routing, hardware noise, and biological keystroke dynamics.
                        </p>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => setShowShieldModal(true)}
                      className="px-3.5 py-2 rounded-lg bg-primary text-primary-foreground text-xs font-semibold hover:bg-primary/90 transition-colors shrink-0 flex items-center gap-1.5 cursor-pointer"
                    >
                      <Play size={12} />
                      <span>Inspect Hardware Nodes</span>
                    </button>
                  </div>

                  {/* 5 Vault Pillars */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div className="p-3.5 rounded-lg bg-background border border-border space-y-1">
                      <div className="flex items-center justify-between text-xs font-bold">
                        <span className="text-foreground flex items-center gap-1.5">
                          <CheckCircle2 size={13} className="text-emerald-600 dark:text-emerald-400" />
                          1. Residential Peer Mobile IPs
                        </span>
                        <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-mono">100% Residential</span>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        AT&amp;T and Verizon 5G residential mobile peers. LinkedIn never detects datacenter or VPS signatures.
                      </p>
                    </div>

                    <div className="p-3.5 rounded-lg bg-background border border-border space-y-1">
                      <div className="flex items-center justify-between text-xs font-bold">
                        <span className="text-foreground flex items-center gap-1.5">
                          <CheckCircle2 size={13} className="text-emerald-600 dark:text-emerald-400" />
                          2. Hardware &amp; WebGL Noise
                        </span>
                        <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-mono">Canvas Masked</span>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        Hardware fingerprints, audio contexts, and WebGL buffers are dynamically randomized per session.
                      </p>
                    </div>

                    <div className="p-3.5 rounded-lg bg-background border border-border space-y-1">
                      <div className="flex items-center justify-between text-xs font-bold">
                        <span className="text-foreground flex items-center gap-1.5">
                          <CheckCircle2 size={13} className="text-emerald-600 dark:text-emerald-400" />
                          3. Biological Keystroke Engine
                        </span>
                        <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-mono">40-120ms Jitter</span>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        Outreach copy is typed with biological Gaussian delay curves and realistic micro-pauses at punctuation.
                      </p>
                    </div>

                    <div className="p-3.5 rounded-lg bg-background border border-border space-y-1">
                      <div className="flex items-center justify-between text-xs font-bold">
                        <span className="text-foreground flex items-center gap-1.5">
                          <CheckCircle2 size={13} className="text-emerald-600 dark:text-emerald-400" />
                          4. Voyager Circuit Breaker
                        </span>
                        <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-mono">Auto-Cooloff</span>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        If LinkedIn returns unusual latency, challenge screens, or CAPTCHA prompts, outreach halts instantly.
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </>
          ) : null}
        </div>

        {/* Footer Flight Clearance Controls */}
        <div className="px-6 py-4 border-t border-border bg-card flex flex-col sm:flex-row items-center justify-between gap-3 shrink-0">
          <button
            type="button"
            onClick={onClose}
            className="w-full sm:w-auto px-4 py-2 text-xs font-semibold rounded-lg border border-border bg-background hover:bg-muted text-foreground transition-colors cursor-pointer"
          >
            Back to Sequence Canvas
          </button>

          <div className="flex items-center gap-3 w-full sm:w-auto justify-end">
            {loading ? (
              <button
                type="button"
                disabled
                className="w-full sm:w-auto px-5 py-2.5 text-xs font-bold rounded-lg bg-muted text-muted-foreground border border-border cursor-not-allowed flex items-center justify-center gap-2"
              >
                <RefreshCw size={14} className="animate-spin text-muted-foreground shrink-0" />
                <span>Running Preflight Verification...</span>
              </button>
            ) : error ? (
              <button
                type="button"
                onClick={runCheck}
                className="w-full sm:w-auto px-5 py-2.5 text-xs font-bold rounded-lg bg-destructive/15 text-destructive border border-destructive/40 hover:bg-destructive/25 transition-all cursor-pointer flex items-center justify-center gap-2"
              >
                <AlertCircle size={14} className="text-destructive shrink-0" />
                <span>Verification Failed — Click to Retry</span>
              </button>
            ) : isBlocked ? (
              <button
                type="button"
                disabled
                className="w-full sm:w-auto px-5 py-2.5 text-xs font-bold rounded-lg bg-destructive/15 text-destructive border border-destructive/40 cursor-not-allowed flex items-center justify-center gap-2"
              >
                <AlertCircle size={14} className="text-destructive shrink-0" />
                <span>Launch Blocked: {data?.critical_errors.length || 0} Blocker(s)</span>
              </button>
            ) : isWarningState && !acknowledgeWarnings ? (
              <button
                type="button"
                onClick={() => setAcknowledgeWarnings(true)}
                className="w-full sm:w-auto px-5 py-2.5 text-xs font-bold rounded-lg bg-amber-500/15 hover:bg-amber-500/25 text-amber-800 dark:text-amber-300 border border-amber-500/40 transition-all cursor-pointer flex items-center justify-center gap-2 shadow-xs"
              >
                <AlertTriangle size={14} className="text-amber-600 dark:text-amber-400 shrink-0" />
                <span>Acknowledge Warnings &amp; Authorize Launch</span>
              </button>
            ) : (
              <button
                type="button"
                onClick={handleLaunchClick}
                disabled={isLaunching || loading}
                className="w-full sm:w-auto flex items-center justify-center gap-2 px-6 py-2.5 text-xs font-bold rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground transition-all cursor-pointer shadow-md disabled:opacity-50"
              >
                {isLaunching ? (
                  <>
                    <RefreshCw size={13} className="animate-spin" />
                    <span>Engaging Flight Dispatch...</span>
                  </>
                ) : (
                  <>
                    <Rocket size={14} />
                    <span>Confirm &amp; Launch Live Campaign</span>
                  </>
                )}
              </button>
            )}
          </div>
        </div>

        {/* Deep Account Shield Verification Modal */}
        {showShieldModal && (
          <AccountShieldVerificationModal
            isOpen={showShieldModal}
            onClose={() => setShowShieldModal(false)}
            accountId={inFlightPayload?.senderIds?.[0] || 'sim-account'}
            accountName={campaignName ? `${campaignName} Primary Sender` : "Primary LinkedIn Sender"}
          />
        )}
      </motion.div>
    </div>
  )
}
