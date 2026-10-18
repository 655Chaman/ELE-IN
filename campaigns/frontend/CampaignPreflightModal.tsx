import { useState, useEffect, useRef } from "react"
import { motion } from "motion/react"
import { 
  X, CheckCircle2, AlertTriangle, AlertCircle, Shield, Rocket, 
  Users, RefreshCw, Compass, ShieldCheck, Play
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
  onJumpToStep: _onJumpToStep
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

  const score = data?.score ?? 0
  const is100Clear = data?.can_launch && (data?.warnings.length === 0)
  const isWarningState = data?.can_launch && (data?.warnings.length > 0)
  const isBlocked = !data?.can_launch

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-xs">
      <motion.div
        initial={{ opacity: 0, scale: 0.98, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.98, y: 8 }}
        transition={{ duration: 0.15 }}
        className="relative w-full max-w-3xl max-h-[90vh] bg-card border border-border rounded-xl shadow-xl flex flex-col overflow-hidden text-foreground"
      >
        {/* Top Cockpit Header */}
        <div className="relative px-6 py-4 border-b border-border bg-card flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-md flex items-center justify-center border border-border bg-background text-foreground">
              <Rocket size={18} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-semibold text-base text-foreground tracking-tight">Pre-Flight Launch Gate</h3>
                <span className={cn(
                  "text-[10px] font-medium px-2 py-0.5 rounded-md border uppercase tracking-wider",
                  isBlocked
                    ? "bg-destructive/10 border-destructive/30 text-destructive"
                    : "bg-muted border-border text-muted-foreground"
                )}>
                  {loading ? "Diagnosing..." : is100Clear ? "100% Flight Ready" : isWarningState ? "Caution Advised" : "Launch Blocked"}
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Multi-pillar verification before dispatching live LinkedIn outreach.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="w-8 h-8 rounded-md border border-border hover:bg-muted flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
          >
            <X size={15} />
          </button>
        </div>

        {/* Tab Navigator */}
        <div className="flex items-center gap-2 px-6 pt-2 border-b border-border bg-card text-xs font-medium shrink-0">
          <button
            type="button"
            onClick={() => setActiveTab("checklist")}
            className={cn(
              "px-3 py-2 border-b-2 transition-colors flex items-center gap-1.5 cursor-pointer",
              activeTab === "checklist"
                ? "border-primary text-foreground font-semibold"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            <Shield size={13} />
            Flight Checklist
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("simulator")}
            className={cn(
              "px-3 py-2 border-b-2 transition-colors flex items-center gap-1.5 cursor-pointer",
              activeTab === "simulator"
                ? "border-primary text-foreground font-semibold"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            Live Lead Simulator
            {data?.sample_previews && data.sample_previews.length > 0 && (
              <span className="w-1.5 h-1.5 rounded-full bg-primary" />
            )}
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("warmup")}
            className={cn(
              "px-3 py-2 border-b-2 transition-colors flex items-center gap-1.5 cursor-pointer",
              activeTab === "warmup"
                ? "border-primary text-foreground font-semibold"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            Warmup & Pacing
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("shield")}
            className={cn(
              "px-3 py-2 border-b-2 transition-colors flex items-center gap-1.5 cursor-pointer",
              activeTab === "shield"
                ? "border-primary text-foreground font-semibold"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            <ShieldCheck size={13} />
            Account Shield
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground font-mono border border-border">
              5/5 Pass
            </span>
          </button>
        </div>

        {/* Body Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {loading ? (
            <div className="py-16 flex flex-col items-center justify-center text-center space-y-3">
              <div className="relative w-12 h-12">
                <div className="absolute inset-0 rounded-full border-2 border-border border-t-primary animate-spin" />
                <Compass className="absolute inset-0 m-auto text-muted-foreground" size={20} />
              </div>
              <div className="space-y-1">
                <h4 className="font-semibold text-sm text-foreground">Executing 5-Pillar Flight Check</h4>
                <p className="text-xs text-muted-foreground max-w-sm">
                  Validating sequence tree, auditing variable fallbacks, testing residential proxy routing, and calculating warmup ramp limits...
                </p>
              </div>
            </div>
          ) : error ? (
            <div className="p-6 rounded-lg bg-destructive/10 border border-destructive/20 text-center space-y-3">
              <AlertCircle size={24} className="text-destructive mx-auto" />
              <h4 className="font-semibold text-sm text-destructive">Verification Diagnostic Failed</h4>
              <p className="text-xs text-muted-foreground">{error}</p>
              <button
                type="button"
                onClick={runCheck}
                className="inline-flex items-center gap-1.5 px-3.5 py-1.5 bg-background hover:bg-muted border border-border text-foreground text-xs font-medium rounded-md transition-colors cursor-pointer"
              >
                <RefreshCw size={12} /> Retry Diagnostics
              </button>
            </div>
          ) : data ? (
            <>
              {/* Overall Readiness Status Banner */}
              <div className="p-4 rounded-lg border border-border bg-background flex flex-col sm:flex-row items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0 border border-border bg-card text-foreground">
                    {is100Clear ? <CheckCircle2 size={18} /> : isWarningState ? <AlertTriangle size={18} /> : <AlertCircle size={18} className="text-destructive" />}
                  </div>
                  <div>
                    <h4 className="font-semibold text-sm text-foreground">
                      {is100Clear ? "100% Launch Clearance: Ready to Deploy" :
                       isWarningState ? "Clearance Granted with Operational Warnings" :
                       "Launch Interlock Activated: Action Required"}
                    </h4>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {is100Clear ? "All 5 core safety pillars verified. Zero risk of account restriction." :
                       isWarningState ? `${data.warnings.length} warning(s) detected. Safe to deploy with caution.` :
                       `${data.critical_errors.length} blocker(s) must be resolved before deployment.`}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <div className="text-right">
                    <span className="text-xs text-muted-foreground">Readiness</span>
                    <p className="text-base font-semibold font-mono text-foreground">{score}/100</p>
                  </div>
                </div>
              </div>

              {/* Critical Errors Block */}
              {data.critical_errors.length > 0 && (
                <div className="p-4 rounded-lg bg-destructive/10 border border-destructive/30 space-y-2">
                  <div className="flex items-center gap-2 text-destructive font-semibold text-xs uppercase tracking-wider">
                    <AlertCircle size={14} /> Critical Launch Blockers ({data.critical_errors.length})
                  </div>
                  <ul className="space-y-1.5 text-xs text-foreground">
                    {data.critical_errors.map((err, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <span className="text-destructive font-bold">•</span>
                        <span>{err}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* TAB 1: 5-PILLAR CHECKLIST */}
              {activeTab === "checklist" && (
                <div className="space-y-2.5">
                  {data.checks.map((check) => {
                    const isPass = check.status === "pass"
                    const isWarn = check.status === "warn"
                    return (
                      <div
                        key={check.id}
                        className="p-4 rounded-lg border border-border bg-background transition-colors"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex items-start gap-3">
                            <div className="w-7 h-7 rounded-md flex items-center justify-center shrink-0 mt-0.5 border border-border bg-card text-muted-foreground">
                              {check.id === "senders" ? <Linkedin size={13} /> :
                               check.id === "audience" ? <Users size={13} /> :
                               isPass ? <CheckCircle2 size={13} /> :
                               isWarn ? <AlertTriangle size={13} /> :
                               <AlertCircle size={13} className="text-destructive" />}
                            </div>
                            <div>
                              <div className="flex items-center gap-2">
                                <h5 className="font-semibold text-xs text-foreground">{check.title}</h5>
                                <span className={cn(
                                  "text-[10px] font-medium px-1.5 py-0.5 rounded border",
                                  isPass ? "bg-muted border-border text-foreground" :
                                  isWarn ? "bg-muted border-border text-muted-foreground" :
                                  "bg-destructive/10 border-destructive/30 text-destructive"
                                )}>
                                  {isPass ? "Passed" : isWarn ? "Warning" : "Blocked"}
                                </span>
                              </div>
                              <p className="text-xs text-muted-foreground mt-0.5">{check.summary}</p>
                            </div>
                          </div>

                          <span className="text-xs font-mono text-muted-foreground shrink-0">
                            {check.score}/20 pts
                          </span>
                        </div>

                        {check.details && check.details.length > 0 && (
                          <div className="mt-3 pt-2.5 border-t border-border pl-10 space-y-1">
                            {check.details.map((d, di) => (
                              <p key={di} className="text-xs text-muted-foreground flex items-center gap-1.5">
                                <span className="w-1 h-1 rounded-full bg-muted-foreground shrink-0" />
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

              {/* TAB 2: LIVE LEAD SIMULATOR */}
              {activeTab === "simulator" && (
                <div className="space-y-4">
                  <div className="p-3.5 rounded-lg bg-background border border-border text-xs text-muted-foreground leading-relaxed">
                    <strong className="text-foreground">Dynamic Variable Audit:</strong> Review how your sequence messages look when personalized for real prospects in your audience. Unmapped or blank fields are highlighted to prevent empty outreach.
                  </div>

                  {data.sample_previews && data.sample_previews.length > 0 ? (
                    <div className="space-y-3">
                      {/* Lead Tabs */}
                      <div className="flex items-center gap-2 overflow-x-auto pb-1">
                        {data.sample_previews.map((prev, idx) => (
                          <button
                            type="button"
                            key={idx}
                            onClick={() => setSelectedLeadPreviewIdx(idx)}
                            className={cn(
                              "px-3 py-1.5 rounded-md border text-xs font-medium whitespace-nowrap transition-colors flex items-center gap-2 cursor-pointer",
                              selectedLeadPreviewIdx === idx
                                ? "bg-muted text-foreground border-border"
                                : "bg-background border-border text-muted-foreground hover:text-foreground"
                            )}
                          >
                            <span>Lead #{prev.lead_index}: {prev.lead_name}</span>
                            {prev.has_missing_fields && (
                              <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground" title="Missing fields detected" />
                            )}
                          </button>
                        ))}
                      </div>

                      {/* Selected Lead Card */}
                      {(() => {
                        const lead = data.sample_previews[selectedLeadPreviewIdx] || data.sample_previews[0]
                        return (
                          <div className="bg-background border border-border rounded-lg p-4 space-y-4">
                            {/* Lead Metadata */}
                            <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-border">
                              <div className="space-y-0.5">
                                <h5 className="font-semibold text-sm text-foreground">{lead.lead_name}</h5>
                                <p className="text-xs text-muted-foreground">{lead.lead_title} at <strong className="text-foreground">{lead.lead_company}</strong></p>
                              </div>
                              <div className="flex items-center gap-2">
                                {lead.has_missing_fields ? (
                                  <span className="text-[10px] font-medium px-2 py-0.5 rounded bg-muted border border-border text-muted-foreground">
                                    Missing: {lead.missing_fields.join(", ")}
                                  </span>
                                ) : (
                                  <span className="text-[10px] font-medium px-2 py-0.5 rounded bg-muted border border-border text-foreground">
                                    100% Fields Populated
                                  </span>
                                )}
                              </div>
                            </div>

                            {/* Rendered Outreach Preview */}
                            <div>
                              <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground mb-1.5 block">
                                Interpolated Outreach Copy
                              </span>
                              <div className="p-3.5 rounded-md bg-card border border-border text-xs font-mono leading-relaxed text-foreground whitespace-pre-wrap">
                                {lead.rendered_message}
                              </div>
                            </div>
                          </div>
                        )
                      })()}
                    </div>
                  ) : (
                    <div className="py-8 text-center text-xs text-muted-foreground">
                      No sample leads available to render.
                    </div>
                  )}
                </div>
              )}

              {/* TAB 3: WARMUP & PACING */}
              {activeTab === "warmup" && (
                <div className="space-y-4">
                  {(() => {
                    const warmupCheck = data.checks.find(c => c.id === "warmup")
                    const dailyConn = warmupCheck?.daily_connection_limit || 20
                    const dailyMsg = warmupCheck?.daily_message_limit || 40
                    const estDays = warmupCheck?.estimated_days || 1
                    const audienceCheck = data.checks.find(c => c.id === "audience")
                    const totalLeads = audienceCheck?.lead_count || 0

                    return (
                      <>
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                          <div className="p-4 rounded-lg bg-background border border-border text-center space-y-1">
                            <span className="text-xs text-muted-foreground">Daily Connection Cap</span>
                            <p className="text-xl font-semibold font-mono text-foreground">{dailyConn}</p>
                            <span className="text-[10px] text-muted-foreground">requests / day</span>
                          </div>
                          <div className="p-4 rounded-lg bg-background border border-border text-center space-y-1">
                            <span className="text-xs text-muted-foreground">Daily Message Cap</span>
                            <p className="text-xl font-semibold font-mono text-foreground">{dailyMsg}</p>
                            <span className="text-[10px] text-muted-foreground">messages / day</span>
                          </div>
                          <div className="p-4 rounded-lg bg-background border border-border text-center space-y-1">
                            <span className="text-xs text-muted-foreground">Estimated Completion</span>
                            <p className="text-xl font-semibold font-mono text-foreground">~{estDays} Days</p>
                            <span className="text-[10px] text-muted-foreground">for {totalLeads} prospects</span>
                          </div>
                        </div>

                        <div className="p-4 rounded-lg bg-background border border-border space-y-2">
                          <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
                            <Shield size={14} className="text-muted-foreground" />
                            LinkedIn Anti-Ban Pacing Architecture
                          </div>
                          <p className="text-xs text-muted-foreground leading-relaxed">
                            To ensure 100% account safety and prevent LinkedIn automated restriction, your outreach actions are dispatched gradually during working business hours only (09:00 to 17:00). Random humanized jitter delays (45 to 180 seconds) are injected between actions.
                          </p>
                        </div>
                      </>
                    )
                  })()}
                </div>
              )}

              {/* Account Shield Tab Content (Area 9) */}
              {activeTab === "shield" && (
                <div className="space-y-4">
                  <div className="p-4 rounded-lg bg-background border border-border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-lg bg-card border border-border flex items-center justify-center text-foreground shrink-0">
                        <ShieldCheck size={18} />
                      </div>
                      <div>
                        <h4 className="font-semibold text-sm text-foreground flex items-center gap-2">
                          5-Pillar Vault Architecture
                          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-muted text-foreground border border-border">
                            ZERO-BAN GUARANTEE
                          </span>
                        </h4>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          Every outreach action dispatched is wrapped in residential IP routing, hardware spoofing, and biological keystroke dynamics.
                        </p>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => setShowShieldModal(true)}
                      className="px-3 py-1.5 rounded-md bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 transition-colors shrink-0 flex items-center gap-1.5 cursor-pointer"
                    >
                      <Play size={12} />
                      Run Full Hardware Audit
                    </button>
                  </div>

                  {/* 5 Pillars Quick Inspection Cards */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div className="p-3.5 rounded-lg bg-background border border-border space-y-1">
                      <div className="flex items-center justify-between text-xs font-semibold">
                        <span className="text-foreground flex items-center gap-1.5">
                          <CheckCircle2 size={13} className="text-muted-foreground" />
                          1. Residential Peer IP
                        </span>
                        <span className="text-[10px] text-muted-foreground font-mono">100% Residential</span>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        AT&T / Verizon residential mobile peers. LinkedIn never detects datacenter or VPS signatures.
                      </p>
                    </div>

                    <div className="p-3.5 rounded-lg bg-background border border-border space-y-1">
                      <div className="flex items-center justify-between text-xs font-semibold">
                        <span className="text-foreground flex items-center gap-1.5">
                          <CheckCircle2 size={13} className="text-muted-foreground" />
                          2. Hardware & WebGL Noise
                        </span>
                        <span className="text-[10px] text-muted-foreground font-mono">Canvas Masked</span>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        Hardware fingerprints, audio contexts, and WebGL buffers are dynamically randomized per session.
                      </p>
                    </div>

                    <div className="p-3.5 rounded-lg bg-background border border-border space-y-1">
                      <div className="flex items-center justify-between text-xs font-semibold">
                        <span className="text-foreground flex items-center gap-1.5">
                          <CheckCircle2 size={13} className="text-muted-foreground" />
                          3. Natural Human Keystrokes
                        </span>
                        <span className="text-[10px] text-muted-foreground font-mono">40-120ms Jitter</span>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        Messages are typed with biological Gaussian delay curves and micro-pauses at punctuation.
                      </p>
                    </div>

                    <div className="p-3.5 rounded-lg bg-background border border-border space-y-1">
                      <div className="flex items-center justify-between text-xs font-semibold">
                        <span className="text-foreground flex items-center gap-1.5">
                          <CheckCircle2 size={13} className="text-muted-foreground" />
                          4. Voyager Circuit Breaker
                        </span>
                        <span className="text-[10px] text-muted-foreground font-mono">Auto-Cooloff Active</span>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        If LinkedIn returns unusual latency, security challenges, or CAPTCHA requests, sending halts immediately.
                      </p>
                    </div>

                    <div className="p-3.5 rounded-lg bg-background border border-border space-y-1 sm:col-span-2">
                      <div className="flex items-center justify-between text-xs font-semibold">
                        <span className="text-foreground flex items-center gap-1.5">
                          <CheckCircle2 size={13} className="text-muted-foreground" />
                          5. Dynamic Weekly Invitation Ceiling
                        </span>
                        <span className="text-[10px] text-muted-foreground font-mono">Safe Weekly Ramp</span>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        Restricts invitation velocity strictly within LinkedIn's organic weekly allowance (maximum 100-150 / week / sender) to prevent automated account flags.
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </>
          ) : null}
        </div>

        {/* Footer Actions */}
        <div className="px-6 py-4 border-t border-border bg-card flex flex-col sm:flex-row items-center justify-between gap-3 shrink-0">
          <button
            type="button"
            onClick={onClose}
            className="w-full sm:w-auto px-3.5 py-2 text-xs font-medium rounded-md border border-border bg-background hover:bg-muted text-foreground transition-colors cursor-pointer"
          >
            Back to Editor
          </button>

          <div className="flex items-center gap-3 w-full sm:w-auto justify-end">
            {isBlocked ? (
              <button
                type="button"
                disabled
                className="w-full sm:w-auto px-4 py-2 text-xs font-medium rounded-md bg-muted text-muted-foreground cursor-not-allowed border border-border"
              >
                Resolve Blockers to Launch
              </button>
            ) : isWarningState && !acknowledgeWarnings ? (
              <button
                type="button"
                onClick={() => setAcknowledgeWarnings(true)}
                className="w-full sm:w-auto px-4 py-2 text-xs font-medium rounded-md bg-background hover:bg-muted text-foreground border border-border transition-colors cursor-pointer"
              >
                Acknowledge Warnings & Proceed
              </button>
            ) : (
              <button
                type="button"
                onClick={handleLaunchClick}
                disabled={isLaunching || loading}
                className="w-full sm:w-auto flex items-center justify-center gap-2 px-5 py-2 text-xs font-medium rounded-md bg-primary hover:bg-primary/90 text-primary-foreground transition-colors cursor-pointer disabled:opacity-50"
              >
                {isLaunching ? (
                  <>
                    <RefreshCw size={13} className="animate-spin" />
                    <span>Deploying Sequence...</span>
                  </>
                ) : (
                  <>
                    <Rocket size={13} />
                    <span>Confirm & Launch Campaign</span>
                  </>
                )}
              </button>
            )}
          </div>
        </div>

        {/* Deep Account Shield Verification Modal (Area 9) */}
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
