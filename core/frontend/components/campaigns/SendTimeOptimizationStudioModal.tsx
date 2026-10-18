import React, { useState, useEffect, useRef } from "react";
import {
  Clock,
  Globe,
  ShieldCheck,
  Zap,
  BarChart3,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  X,
  Lock,
  Calendar,
  UserCheck,
  Activity,
  ArrowRight,
} from "lucide-react";
import { fetchWithAuth as apiFetch } from "@/lib/apiClient";
import { usePaywall } from "../../contexts/PaywallContext";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";

export interface StoWindowResult {
  best_hour: number;
  confidence: number;
  source: "historical_engagement" | "industry_prior" | string;
  data_points?: number;
  sample_size?: number;
  scores?: Record<string, number>;
  hourly_distribution?: Record<string, number>;
  allowed_window?: [number, number];
}

export interface StoEvaluationResponse {
  status: string;
  lead_id: string | null;
  timezone: string;
  sto_window: StoWindowResult;
  jitter_minutes: number;
  recommended_local_time: string;
  next_run_at_utc: string;
  evaluated_at: string;
}

interface SendTimeOptimizationStudioModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialTimezone?: string;
  initialStartHour?: number;
  initialEndHour?: number;
  initialWeekendSending?: boolean;
  canAiSto?: boolean;
  isSchedulingModeSto?: boolean;
  onApplyStoMode?: (config: {
    scheduling_mode: "ai_sto";
    timezone: string;
    start_hour: number;
    end_hour: number;
  }) => void;
}

const GLOBAL_TIMEZONES = [
  { value: "America/New_York", label: "New York (EST/EDT - US East)" },
  { value: "America/Chicago", label: "Chicago (CST/CDT - US Central)" },
  { value: "America/Los_Angeles", label: "San Francisco / LA (PST/PDT - US West)" },
  { value: "Europe/London", label: "London (GMT/BST - UK)" },
  { value: "Europe/Berlin", label: "Berlin / Paris (CET/CEST - EU)" },
  { value: "Asia/Kolkata", label: "Bengaluru / Mumbai (IST - India)" },
  { value: "Asia/Singapore", label: "Singapore (SGT - APAC)" },
  { value: "Asia/Tokyo", label: "Tokyo (JST - Japan)" },
  { value: "Australia/Sydney", label: "Sydney (AEST - Australia)" },
  { value: "UTC", label: "UTC (Universal Coordinated Time)" },
];

const SAMPLE_PROSPECTS = [
  {
    id: "",
    label: "Industry Prior Baseline (Cold Prospect - No Prior History)",
    tz: "America/New_York",
    desc: "Uses B2B executive engagement priors (peaks at 09:00, 10:00, and 14:00 local time).",
  },
  {
    id: "lead_sto_exec_ny",
    label: "VP Engineering @ FinTech (Early Morning Reader)",
    tz: "America/New_York",
    desc: "Simulated prospect profile in US Eastern timezone with deterministic anti-bot jitter.",
  },
  {
    id: "lead_sto_founder_sf",
    label: "Founder @ AI Startup (West Coast Schedule)",
    tz: "America/Los_Angeles",
    desc: "Simulated West Coast executive profile with cross-timezone curfew alignment.",
  },
  {
    id: "lead_sto_director_lon",
    label: "Director of Revenue @ SaaS (EMEA Hub)",
    tz: "Europe/London",
    desc: "Simulated EMEA prospect profile respecting local UK working window.",
  },
];

export const SendTimeOptimizationStudioModal: React.FC<
  SendTimeOptimizationStudioModalProps
> = ({
  isOpen,
  onClose,
  initialTimezone = "America/New_York",
  initialStartHour = 9,
  initialEndHour = 17,
  initialWeekendSending = false,
  canAiSto = true,
  isSchedulingModeSto = false,
  onApplyStoMode,
}) => {
  const { openPaywall } = usePaywall();
  const [timezone, setTimezone] = useState<string>(initialTimezone || "America/New_York");
  const [leadId, setLeadId] = useState<string>("");
  const [startHour, setStartHour] = useState<number>(
    Number.isFinite(initialStartHour) ? initialStartHour : 9
  );
  const [endHour, setEndHour] = useState<number>(
    Number.isFinite(initialEndHour) ? initialEndHour : 17
  );
  const [weekendSending, setWeekendSending] = useState<boolean>(initialWeekendSending);
  const [isEvaluating, setIsEvaluating] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [evaluation, setEvaluation] = useState<StoEvaluationResponse | null>(null);
  const [appliedSuccess, setAppliedSuccess] = useState<boolean>(false);
  const abortRef = useRef<AbortController | null>(null);

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  // Sync props when opened
  useEffect(() => {
    if (isOpen) {
      setTimezone(initialTimezone || "America/New_York");
      setStartHour(Number.isFinite(initialStartHour) ? initialStartHour : 9);
      setEndHour(Number.isFinite(initialEndHour) ? initialEndHour : 17);
      setWeekendSending(Boolean(initialWeekendSending));
      setAppliedSuccess(false);
      setErrorMsg(null);
    }
  }, [isOpen, initialTimezone, initialStartHour, initialEndHour, initialWeekendSending]);

  const clampHours = (s: number, e: number): [number, number] => {
    let safeStart = Math.max(0, Math.min(23, Math.floor(Number(s) || 0)));
    let safeEnd = Math.max(0, Math.min(23, Math.floor(Number(e) || 17)));
    if (safeStart > safeEnd) {
      safeStart = 9;
      safeEnd = 17;
    }
    return [safeStart, safeEnd];
  };

  const isCurfewInverted = startHour > endHour;

  const runStoEvaluation = async (
    overrideTz?: string,
    overrideLeadId?: string,
    overrideStart?: number,
    overrideEnd?: number,
    overrideWeekend?: boolean
  ) => {
    if (isEvaluating) return;

    const targetTz = overrideTz !== undefined ? overrideTz : timezone;
    const targetLead = overrideLeadId !== undefined ? overrideLeadId : leadId;
    const [safeStart, safeEnd] = clampHours(
      overrideStart !== undefined ? overrideStart : startHour,
      overrideEnd !== undefined ? overrideEnd : endHour
    );
    const targetWeekend =
      overrideWeekend !== undefined ? overrideWeekend : weekendSending;

    if (abortRef.current) {
      abortRef.current.abort();
    }
    const controller = new AbortController();
    abortRef.current = controller;

    setIsEvaluating(true);
    setErrorMsg(null);

    try {
      const res = await apiFetch("/api/elein/campaigns/evaluate-sto-slot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          lead_id: targetLead.trim() ? targetLead.trim() : null,
          timezone: targetTz || "UTC",
          schedule: {
            start_hour: safeStart,
            end_hour: safeEnd,
            weekend_sending: targetWeekend,
          },
        }),
      });

      if (res.status === 402 || res.status === 403) {
        openPaywall({
          featureName: "Dynamic AI Send-Time Optimization (STO)",
          minTier: "PRO",
          description:
            "Predict each prospect's peak local engagement hour from historical reply/open telemetry and B2B priors with deterministic anti-bot jitter.",
        });
        setIsEvaluating(false);
        return;
      }

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        // If 404 because simulated demo lead ID isn't in DB, retry without lead_id or synthesize
        if (res.status === 404 && targetLead.startsWith("lead_sto_")) {
          const fallbackRes = await apiFetch("/api/elein/campaigns/evaluate-sto-slot", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              lead_id: null,
              timezone: targetTz || "UTC",
              schedule: {
                start_hour: safeStart,
                end_hour: safeEnd,
                weekend_sending: targetWeekend,
              },
            }),
          });
          if (fallbackRes.ok) {
            const fbData: StoEvaluationResponse = await fallbackRes.json();
            setEvaluation({
              ...fbData,
              lead_id: targetLead,
            });
            setIsEvaluating(false);
            return;
          }
        }
        throw new Error(
          typeof errData?.detail === "string"
            ? errData.detail
            : errData?.detail?.message || `Evaluation failed (${res.status})`
        );
      }

      const data: StoEvaluationResponse = await res.json();
      setEvaluation(data);
    } catch (err: any) {
      if (err?.name === "AbortError") return;
      setErrorMsg(
        err?.message ||
          "Could not reach STO evaluation engine. Verify the backend is running."
      );
    } finally {
      setIsEvaluating(false);
    }
  };

  useEffect(() => {
    if (isOpen && canAiSto) {
      runStoEvaluation(timezone, leadId, startHour, endHour, weekendSending);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  if (!isOpen) return null;

  const rawDist =
    evaluation?.sto_window?.scores ||
    evaluation?.sto_window?.hourly_distribution ||
    null;

  const dist: Record<string, number> =
    rawDist && Object.keys(rawDist).length > 0
      ? rawDist
      : {
          "8": 0.1,
          "9": 0.24,
          "10": 0.22,
          "11": 0.12,
          "13": 0.06,
          "14": 0.14,
          "15": 0.08,
          "16": 0.04,
        };

  const maxProb = Math.max(
    0.01,
    ...Object.values(dist).map((v) => Number(v) || 0)
  );
  const bestHour = evaluation?.sto_window?.best_hour ?? 9;
  const [winStart, winEnd] = evaluation?.sto_window?.allowed_window || [
    startHour,
    endHour,
  ];

  const handleApplySto = () => {
    if (!canAiSto) {
      openPaywall({
        featureName: "Dynamic AI Send-Time Optimization (STO)",
        minTier: "PRO",
        description:
          "Activate AI Send-Time Optimization to automatically deliver every outreach step during each prospect's highest-probability local active hour.",
      });
      return;
    }
    const [safeStart, safeEnd] = clampHours(startHour, endHour);
    if (onApplyStoMode) {
      onApplyStoMode({
        scheduling_mode: "ai_sto",
        timezone: initialTimezone || timezone,
        start_hour: safeStart,
        end_hour: safeEnd,
      });
    }
    setAppliedSuccess(true);
    toast.success("AI Send-Time Optimization applied to campaign schedule");
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="sto-studio-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-4xl max-h-[90vh] rounded-xl bg-card border border-border shadow-lg flex flex-col overflow-hidden text-foreground my-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Top Header */}
        <div className="px-6 py-4 border-b border-border bg-background flex items-center justify-between shrink-0">
          <div>
            <h2 id="sto-studio-modal-title" className="text-base font-semibold tracking-tight text-foreground">
              Send-Time Optimization & Activity Pacing Studio
            </h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Bayesian prospect activity modeling, B2B executive priors, and deterministic anti-bot jitter.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
            aria-label="Close dialog"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-6 flex-1 overflow-y-auto">
          {/* Free Tier Banner if gated */}
          {!canAiSto && (
            <div className="p-4 rounded-lg bg-muted/30 border border-border flex items-center justify-between gap-4">
              <div className="flex items-start gap-3">
                <Lock className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
                <div>
                  <div className="text-xs font-semibold text-foreground">
                    Growth Pro Feature - Predictive Send-Time Optimization
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Upgrade to Growth Pro to unlock per-prospect engagement hour prediction, historical reply heatmaps, and deterministic anti-bot jitter.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() =>
                  openPaywall({
                    featureName: "Dynamic AI Send-Time Optimization (STO)",
                    minTier: "PRO",
                    description:
                      "Unlock AI Send-Time Optimization to automatically deliver messages at each prospect's peak local engagement hour.",
                  })
                }
                className="px-3.5 py-1.5 rounded-lg bg-primary text-primary-foreground font-semibold text-xs hover:bg-primary/90 transition-colors shrink-0 cursor-pointer"
              >
                Unlock Pro
              </button>
            </div>
          )}

          {/* Controls Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Prospect / Cohort Selector */}
            <div className="p-4 rounded-lg bg-muted/30 border border-border space-y-2.5">
              <label className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                <UserCheck className="w-3.5 h-3.5 text-muted-foreground" />
                Prospect Profile / Cohort
              </label>
              <Select
                value={
                  SAMPLE_PROSPECTS.some((p) => p.id === leadId) ? leadId : "custom"
                }
                onValueChange={(val) => {
                  if (val === "custom") return;
                  const preset = SAMPLE_PROSPECTS.find((p) => p.id === val);
                  setLeadId(val);
                  if (preset) {
                    setTimezone(preset.tz);
                    if (canAiSto) {
                      runStoEvaluation(preset.tz, val, startHour, endHour, weekendSending);
                    }
                  }
                }}
              >
                <SelectTrigger className="w-full bg-background border-border text-xs h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SAMPLE_PROSPECTS.map((p) => (
                    <SelectItem key={p.id || "baseline"} value={p.id}>
                      {p.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <input
                type="text"
                value={leadId}
                onChange={(e) => setLeadId(e.target.value)}
                placeholder="Or enter specific Lead ID (optional)"
                className="w-full px-3 py-1.5 rounded-lg bg-background border border-border text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary"
              />
            </div>

            {/* IANA Timezone Selector */}
            <div className="p-4 rounded-lg bg-muted/30 border border-border space-y-2.5">
              <label className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                <Globe className="w-3.5 h-3.5 text-muted-foreground" />
                Prospect Local IANA Timezone
              </label>
              <Select
                value={timezone}
                onValueChange={(val) => {
                  setTimezone(val);
                  if (canAiSto) {
                    runStoEvaluation(val, leadId, startHour, endHour, weekendSending);
                  }
                }}
              >
                <SelectTrigger className="w-full bg-background border-border text-xs h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {GLOBAL_TIMEZONES.map((tz) => (
                    <SelectItem key={tz.value} value={tz.value}>
                      {tz.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <div className="text-xs text-muted-foreground leading-relaxed">
                Invalid or missing prospect timezones automatically fall back to{" "}
                <code className="text-foreground">UTC</code> with zero crash risk.
              </div>
            </div>

            {/* Active Curfew Window */}
            <div className="p-4 rounded-lg bg-muted/30 border border-border space-y-2.5">
              <label className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                <Calendar className="w-3.5 h-3.5 text-muted-foreground" />
                Allowed Working Curfew (Local)
              </label>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <span className="text-xs text-muted-foreground block mb-1">
                    Start Hour (0-23)
                  </span>
                  <input
                    type="number"
                    min={0}
                    max={23}
                    value={startHour}
                    onChange={(e) => {
                      const val = e.target.value;
                      if (val === "") {
                        setStartHour(0);
                      } else {
                        setStartHour(Math.max(0, Math.min(23, parseInt(val, 10) || 0)));
                      }
                    }}
                    className="w-full px-2.5 py-1.5 rounded-lg bg-background border border-border text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
                <div>
                  <span className="text-xs text-muted-foreground block mb-1">
                    End Hour (0-23)
                  </span>
                  <input
                    type="number"
                    min={0}
                    max={23}
                    value={endHour}
                    onChange={(e) => {
                      const val = e.target.value;
                      if (val === "") {
                        setEndHour(0);
                      } else {
                        setEndHour(Math.max(0, Math.min(23, parseInt(val, 10) || 0)));
                      }
                    }}
                    className="w-full px-2.5 py-1.5 rounded-lg bg-background border border-border text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
              </div>

              {isCurfewInverted && (
                <div className="p-2 rounded bg-amber-500/10 border border-amber-500/20 text-[11px] text-amber-500 flex items-start gap-1.5">
                  <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                  <span>
                    Curfew start ({startHour}:00) cannot be after end ({endHour}:00). System will default to 09:00 - 17:00.
                  </span>
                </div>
              )}

              <div className="flex items-center justify-between pt-1">
                <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
                  <input
                    type="checkbox"
                    checked={weekendSending}
                    onChange={(e) => setWeekendSending(e.target.checked)}
                    className="rounded border-border bg-background text-primary"
                  />
                  Allow Weekend Dispatch
                </label>
                <button
                  type="button"
                  onClick={() =>
                    runStoEvaluation(timezone, leadId, startHour, endHour, weekendSending)
                  }
                  disabled={isEvaluating}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-primary/10 hover:bg-primary/20 text-primary text-xs font-medium transition-colors disabled:opacity-50 cursor-pointer"
                >
                  <RefreshCw
                    className={`w-3 h-3 ${isEvaluating ? "animate-spin" : ""}`}
                  />
                  Evaluate
                </button>
              </div>
            </div>
          </div>

          {errorMsg && (
            <div className="p-3.5 rounded-lg bg-destructive/10 border border-destructive/20 flex items-center gap-2.5 text-xs text-destructive">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}

          {/* KPI Summary Strip */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-3.5 rounded-lg bg-card border border-border">
              <div className="text-xs font-medium text-muted-foreground">
                Optimal Local Slot
              </div>
              <div className="text-lg font-semibold text-foreground mt-1 flex items-baseline gap-1.5">
                {evaluation?.recommended_local_time ||
                  `${String(bestHour).padStart(2, "0")}:14`}
                <span className="text-xs font-normal text-muted-foreground">
                  ({evaluation?.timezone || timezone})
                </span>
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                Peak Hour {String(bestHour).padStart(2, "0")}:00 + Jitter
              </div>
            </div>

            <div className="p-3.5 rounded-lg bg-card border border-border">
              <div className="text-xs font-medium text-muted-foreground">
                Anti-Bot MD5 Jitter
              </div>
              <div className="text-lg font-semibold text-foreground mt-1">
                +{evaluation?.jitter_minutes ?? 14} min
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                Deterministic 5-25m spread prevents top-of-hour bursts
              </div>
            </div>

            <div className="p-3.5 rounded-lg bg-card border border-border">
              <div className="text-xs font-medium text-muted-foreground">
                Model Confidence & Source
              </div>
              <div className="text-lg font-semibold text-foreground mt-1">
                {Math.round((evaluation?.sto_window?.confidence ?? 0.35) * 100)}%
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                {evaluation?.sto_window?.source === "historical_engagement"
                  ? `Historical Telemetry (${
                      evaluation.sto_window.data_points ??
                      evaluation.sto_window.sample_size ??
                      0
                    } events)`
                  : "B2B Executive Prior (Cold Start)"}
              </div>
            </div>

            <div className="p-3.5 rounded-lg bg-card border border-border">
              <div className="text-xs font-medium text-muted-foreground">
                Next Scheduled UTC Execution
              </div>
              <div className="text-xs font-mono font-semibold text-foreground mt-1.5 truncate">
                {evaluation?.next_run_at_utc
                  ? new Date(evaluation.next_run_at_utc).toISOString().replace(".000Z", "Z")
                  : "Pending Evaluation"}
              </div>
              <div className="text-xs text-muted-foreground mt-1.5">
                Auto-rolls past weekends & federal holidays
              </div>
            </div>
          </div>

          {/* 24-Hour Engagement Probability Distribution Chart */}
          <div className="p-5 rounded-lg bg-muted/30 border border-border space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-muted-foreground" />
                <span className="text-xs font-semibold text-foreground">
                  24-Hour Local Engagement Probability Distribution ({evaluation?.timezone || timezone})
                </span>
              </div>
              <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
                <span className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-sm bg-primary inline-block" />
                  Selected Peak Slot ({String(bestHour).padStart(2, "0")}:00)
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-sm bg-primary/40 inline-block" />
                  Allowed Working Window ({String(winStart).padStart(2, "0")}:00-{String(winEnd).padStart(2, "0")}:00)
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-sm bg-muted/80 border border-border inline-block" />
                  Curfew Blocked
                </span>
              </div>
            </div>

            {/* Horizontally scrollable wrapper to prevent chart collapse on narrow displays */}
            <div className="overflow-x-auto pb-2 -mx-1 px-1">
              <div className="min-w-[540px]">
                <div className="grid grid-cols-[repeat(24,minmax(0,1fr))] gap-1 items-end h-36 pt-6 px-1 border-b border-border">
                  {Array.from({ length: 24 }, (_, hr) => {
                    const prob = Number(dist[String(hr)] ?? dist[hr] ?? 0.01);
                    const heightPct = Math.max(8, Math.round((prob / maxProb) * 100));
                    const inWindow = hr >= winStart && hr <= winEnd;
                    const isBest = hr === bestHour;

                    const tooltipAlign =
                      hr === 0
                        ? "left-0"
                        : hr === 23
                        ? "right-0"
                        : "left-1/2 -translate-x-1/2";

                    return (
                      <div
                        key={hr}
                        className="flex flex-col items-center justify-end h-full group relative"
                      >
                        {/* Tooltip with boundary-safe clamping */}
                        <div
                          className={`opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity absolute -top-8 z-20 px-1.5 py-0.5 rounded bg-card border border-border text-[11px] text-foreground whitespace-nowrap shadow-sm ${tooltipAlign}`}
                        >
                          {String(hr).padStart(2, "0")}:00 - {(prob * 100).toFixed(1)}%
                        </div>
                        <div
                          style={{ height: `${heightPct}%` }}
                          className={`w-full rounded-t transition-all ${
                            isBest
                              ? "bg-primary shadow-xs ring-1 ring-primary/50"
                              : inWindow
                              ? "bg-primary/40 hover:bg-primary/60"
                              : "bg-muted/70 border border-dashed border-border/60 opacity-60"
                          }`}
                        />
                      </div>
                    );
                  })}
                </div>

                <div className="grid grid-cols-[repeat(24,minmax(0,1fr))] gap-1 text-[11px] text-muted-foreground font-mono text-center pt-2">
                  {Array.from({ length: 24 }, (_, hr) => (
                    <div
                      key={hr}
                      className={
                        hr === bestHour ? "text-primary font-semibold" : ""
                      }
                    >
                      {String(hr).padStart(2, "0")}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Safeguards Summary */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
            <div className="p-3 rounded-lg bg-muted/30 border border-border flex items-start gap-2.5">
              <Activity className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
              <div>
                <div className="font-semibold text-foreground">
                  Weighted Telemetry Recency
                </div>
                <p className="text-muted-foreground text-xs mt-0.5 leading-relaxed">
                  Inbound replies carry 3.0x weight, link clicks 2.0x, and opens 1.0x, blended with B2B executive priors.
                </p>
              </div>
            </div>
            <div className="p-3 rounded-lg bg-muted/30 border border-border flex items-start gap-2.5">
              <ShieldCheck className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
              <div>
                <div className="font-semibold text-foreground">
                  Anti-Bot Burst Protection
                </div>
                <p className="text-muted-foreground text-xs mt-0.5 leading-relaxed">
                  Deterministic MD5 lead jitter (+5 to +25 mins) prevents 500 prospects in the same timezone from firing at :00 sharp.
                </p>
              </div>
            </div>
            <div className="p-3 rounded-lg bg-muted/30 border border-border flex items-start gap-2.5">
              <Zap className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
              <div>
                <div className="font-semibold text-foreground">
                  Curfew & Holiday Guardrails
                </div>
                <p className="text-muted-foreground text-xs mt-0.5 leading-relaxed">
                  Strictly clamped to your allowed working hours and automatically advances past weekends and holidays.
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-t border-border bg-background shrink-0">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            {isSchedulingModeSto || appliedSuccess ? (
              <span className="inline-flex items-center gap-1.5 text-primary font-medium">
                <CheckCircle2 className="w-4 h-4" />
                Send-Time Optimization (ai_sto) is active on this campaign schedule
              </span>
            ) : (
              <span>
                Ready to switch campaign dispatch mode to{" "}
                <strong className="text-foreground">Send-Time Optimization</strong>
              </span>
            )}
          </div>

          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-1.5 rounded-lg border border-border bg-card hover:bg-muted text-xs font-medium text-foreground transition-colors cursor-pointer"
            >
              Close
            </button>
            {onApplyStoMode && (
              <button
                type="button"
                onClick={handleApplySto}
                className="inline-flex items-center gap-2 px-4 py-1.5 rounded-lg bg-primary hover:bg-primary/90 text-xs font-semibold text-primary-foreground transition-all cursor-pointer"
              >
                {appliedSuccess
                  ? "STO Schedule Applied"
                  : "Apply STO to Campaign Schedule"}
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
