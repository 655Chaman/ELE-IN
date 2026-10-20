import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { 
  Sparkles, RefreshCw, 
  Cpu, ArrowUpRight, BarChart3, ShieldCheck, HelpCircle, 
  Play, Layers, Lock, Unlock, AlertTriangle,
  RotateCcw, History, Zap, Gauge, Sliders, ShieldAlert,
  Flame, UserCheck, MessageSquare, XCircle
} from "lucide-react";
import useSWR from "swr";
import { fetchWithAuth, fetcher } from "@/lib/apiClient";
import { usePaywall } from "@/contexts/PaywallContext";
import { toast } from "sonner";

interface SignalCalibrationData {
  signal_name: string;
  label: string;
  category: "FIRMOGRAPHIC" | "BEHAVIORAL" | "INTENT" | string;
  description: string;
  is_frozen: boolean;
  weight_multiplier: number;
  alpha: number;
  beta: number;
  sample_size: number;
  raw_mean: number;
  effective_weight: number;
  variance: number;
  std_dev: number;
  credible_interval_lower: number;
  credible_interval_upper: number;
  confidence_tier: "HIGH" | "MEDIUM" | "LOW" | string;
  empirical_win_rate_pct: number;
}

interface DriftWarning {
  signal_name: string;
  label: string;
  severity: "POSITIVE_ACCELERATION" | "NEGATIVE_DEVIATION" | string;
  message: string;
}

interface CalibrationMatrixResponse {
  workspace_id?: string;
  signals?: SignalCalibrationData[];
  total_signals_tracked?: number;
  total_observations?: number;
  recommended_score_gate?: number;
  model_drift_warnings?: DriftWarning[];
  model_status?: string;
  last_calibrated_at?: string;
}

interface FeedbackEvent {
  id: string;
  event_type: string;
  signals_affected?: string[];
  created_at: string;
  details?: Record<string, any>;
}

export function BayesianIcpView() {
  const { data: matrixData, mutate: mutateMatrix, isLoading: matrixLoading } = useSWR<CalibrationMatrixResponse>(
    "/api/knowledge/icp/calibration", 
    fetcher
  );

  const { data: eventsData, mutate: mutateEvents, isLoading: eventsLoading } = useSWR<{ status: string; events: FeedbackEvent[] }>(
    "/api/knowledge/icp/feedback-events?limit=20", 
    fetcher
  );

  const { openPaywall } = usePaywall();
  const { data: billingData } = useSWR<{
    tier?: string;
    tier_limits?: { can_use_bayesian_icp?: boolean };
  }>('/api/elein/workspaces/billing', fetcher);
  const tier = billingData?.tier || 'FREE';
  const isPro = (tier === 'PRO' || tier === 'ENTERPRISE') || Boolean(billingData?.tier_limits?.can_use_bayesian_icp);
  const isIcpLocked = !isPro;

  // Local state for actions
  const [updatingSignal, setUpdatingSignal] = useState<string | null>(null);
  const [showResetModal, setShowResetModal] = useState(false);
  const [isResettingAll, setIsResettingAll] = useState(false);
  const [activeCategoryFilter, setActiveCategoryFilter] = useState<string>("ALL");

  // Simulator state
  const [testProfile, setTestProfile] = useState({
    title: "VP of Engineering",
    company: "Acme Cloud",
    headcount: 120,
    industry: "Information Technology",
    funding: "Series A",
    recent_posts: true,
  });

  const [simulating, setSimulating] = useState(false);
  const [simResult, setSimResult] = useState<{ score: number; reasoning: string } | null>(null);

  const signals = matrixData?.signals || [];
  const totalObservations = matrixData?.total_observations ?? 0;
  const recommendedScoreGate = matrixData?.recommended_score_gate ?? 65;
  const driftWarnings = matrixData?.model_drift_warnings || [];
  const events = eventsData?.events || [];

  // Filtered signals
  const filteredSignals = activeCategoryFilter === "ALL" 
    ? signals 
    : signals.filter(s => s.category?.toUpperCase() === activeCategoryFilter);

  // Toggle freeze on a signal
  const handleToggleFreeze = async (signal: SignalCalibrationData) => {
    if (isIcpLocked) {
      openPaywall({ featureName: "Bayesian ICP Machine Learning" });
      return;
    }
    const newFreezeState = !signal.is_frozen;
    setUpdatingSignal(signal.signal_name);
    try {
      const res = await fetchWithAuth(`/api/knowledge/icp/signals/${signal.signal_name}/calibrate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_frozen: newFreezeState }),
      });
      if (res.ok) {
        toast.success(
          newFreezeState 
            ? `Signal "${signal.label}" frozen. Automated learning locked to prevent drift.`
            : `Signal "${signal.label}" unfrozen. Auto-adaptation re-enabled.`
        );
        mutateMatrix();
        mutateEvents();
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || "Failed to update freeze state");
      }
    } catch (e: any) {
      toast.error(e.message || "Network error");
    } finally {
      setUpdatingSignal(null);
    }
  };

  // Adjust multiplier on a signal
  const handleMultiplierChange = async (signal: SignalCalibrationData, newMultiplier: number) => {
    if (isIcpLocked) {
      openPaywall({ featureName: "Bayesian ICP Machine Learning" });
      return;
    }
    setUpdatingSignal(signal.signal_name);
    try {
      const res = await fetchWithAuth(`/api/knowledge/icp/signals/${signal.signal_name}/calibrate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ weight_multiplier: newMultiplier }),
      });
      if (res.ok) {
        toast.success(`Weight multiplier for "${signal.label}" adjusted to ${newMultiplier}x`);
        mutateMatrix();
        mutateEvents();
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || "Failed to update multiplier");
      }
    } catch (e: any) {
      toast.error(e.message || "Network error");
    } finally {
      setUpdatingSignal(null);
    }
  };

  // Reset single signal prior
  const handleResetSignalPrior = async (signal: SignalCalibrationData) => {
    if (isIcpLocked) {
      openPaywall({ featureName: "Bayesian ICP Machine Learning" });
      return;
    }
    setUpdatingSignal(signal.signal_name);
    try {
      const res = await fetchWithAuth(`/api/knowledge/icp/signals/${signal.signal_name}/calibrate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reset_prior: true }),
      });
      if (res.ok) {
        toast.success(`Signal "${signal.label}" reset to neutral prior Beta(2,2)`);
        mutateMatrix();
        mutateEvents();
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || "Failed to reset signal");
      }
    } catch (e: any) {
      toast.error(e.message || "Network error");
    } finally {
      setUpdatingSignal(null);
    }
  };

  // Emergency Circuit Breaker: Reset All Signals
  const handleResetAllSignals = async () => {
    if (isIcpLocked) {
      openPaywall({ featureName: "Bayesian ICP Machine Learning" });
      return;
    }
    setIsResettingAll(true);
    try {
      const res = await fetchWithAuth("/api/knowledge/icp/reset-all", {
        method: "POST",
      });
      if (res.ok) {
        toast.success("All Bayesian weights restored to baseline Beta(2,2)");
        setShowResetModal(false);
        mutateMatrix();
        mutateEvents();
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || "Failed to reset signals");
      }
    } catch (e: any) {
      toast.error(e.message || "Network error");
    } finally {
      setIsResettingAll(false);
    }
  };

  // Simulator: Run score
  const handleSimulateScore = async () => {
    if (isIcpLocked) {
      openPaywall({ featureName: "Bayesian ICP Machine Learning" });
      return;
    }
    setSimulating(true);
    try {
      const res = await fetchWithAuth("/api/knowledge/icp/score", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile_data: testProfile }),
      });
      const json = await res.json();
      if (res.ok && json.status === "success") {
        setSimResult({ score: json.score, reasoning: json.reasoning });
        toast.success("Bayesian ICP Score computed successfully");
      } else {
        if (res.status === 402 || res.status === 403) {
          openPaywall({ featureName: "Bayesian ICP Machine Learning" });
          return;
        }
        toast.error(json.detail || "Failed to calculate score");
      }
    } catch (e: any) {
      toast.error(e.message || "Simulation error");
    } finally {
      setSimulating(false);
    }
  };

  // Simulator: Simulate outcome
  const handleSimulateOutcome = async (outcome: "MEETING_BOOKED" | "POSITIVE_REPLY" | "GHOSTED_OR_LOST") => {
    if (isIcpLocked) {
      openPaywall({ featureName: "Bayesian ICP Machine Learning" });
      return;
    }
    try {
      const res = await fetchWithAuth("/api/knowledge/icp/record-outcome", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lead_id: "simulated_lead_" + Date.now(),
          outcome: outcome,
          signal_flags: {
            is_decision_maker: testProfile.title.toLowerCase().includes("vp") || testProfile.title.toLowerCase().includes("chief") || testProfile.title.toLowerCase().includes("director"),
            is_target_industry: testProfile.industry.toLowerCase().includes("technology") || testProfile.industry.toLowerCase().includes("software"),
            is_target_size: testProfile.headcount >= 50 && testProfile.headcount <= 500,
            has_recent_activity: testProfile.recent_posts,
            has_funding: !!testProfile.funding,
            job_change_6mo: false,
            hiring_gtm: true
          }
        }),
      });
      if (res.ok) {
        toast.success(`Feedback recorded for ${outcome.replace(/_/g, " ").toLowerCase()}`);
        mutateMatrix();
        mutateEvents();
        if (simResult) {
          handleSimulateScore();
        }
      }
    } catch (e: any) {
      toast.error("Failed to record learning signal");
    }
  };

  const getEventBadge = (type: string) => {
    switch (type) {
      case "MEETING_BOOKED":
        return <span className="text-[10px] font-medium px-2 py-0.5 rounded-md bg-muted text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">Meeting Booked (+3x Win)</span>;
      case "POSITIVE_REPLY":
        return <span className="text-[10px] font-medium px-2 py-0.5 rounded-md bg-muted text-foreground border border-border/50">Positive Reply (+2x Win)</span>;
      case "CONNECTION_ACCEPTED":
        return <span className="text-[10px] font-medium px-2 py-0.5 rounded-md bg-muted text-muted-foreground border border-border/50">Connected (+1x Win)</span>;
      case "GHOSTED_OR_LOST":
      case "lost":
        return <span className="text-[10px] font-medium px-2 py-0.5 rounded-md bg-muted text-rose-600 dark:text-rose-400 border border-rose-500/20">Ghosted / Lost (+1x Loss)</span>;
      case "MANUAL_OVERRIDE":
        return <span className="text-[10px] font-medium px-2 py-0.5 rounded-md bg-muted text-muted-foreground border border-border/50">Operator Override</span>;
      case "RESET_ALL":
        return <span className="text-[10px] font-medium px-2 py-0.5 rounded-md bg-muted text-amber-600 dark:text-amber-400 border border-amber-500/20">Reset to Defaults</span>;
      default:
        return <span className="text-[10px] font-medium px-2 py-0.5 rounded-md bg-muted text-muted-foreground border border-border/50">{type}</span>;
    }
  };

  return (
    <div className="space-y-6 pb-8">
      {/* ── Growth Pro Lock Banner ── */}
      {!isPro && (
        <div className="p-5 rounded-xl border border-border/50 bg-card/40 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-lg bg-muted/60 border border-border/40 flex items-center justify-center text-foreground/80 shrink-0 mt-0.5">
              <Sparkles size={16} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-medium text-foreground">
                  Lead Fit AI (Smart Lead Qualification)
                </h3>
                <span className="text-[10px] font-medium px-2 py-0.5 rounded-md bg-muted text-muted-foreground border border-border/50 font-mono">
                  Growth Pro
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5 max-w-xl leading-relaxed">
                Automatically scores lead buying intent before sending outreach. As you book calls, the AI learns which job titles and industries convert best—protecting your credits and sending accounts.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => openPaywall({ featureName: "Bayesian ICP Machine Learning" })}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-foreground text-background text-xs font-medium hover:bg-foreground/90 transition-all shadow-2xs shrink-0 whitespace-nowrap cursor-pointer"
          >
            <span>Unlock Lead Fit AI</span>
            <ArrowUpRight size={13} />
          </button>
        </div>
      )}

      {/* ── Studio Cockpit Header ── */}
      <div className="p-6 lg:p-7 rounded-xl bg-card/40 border border-border/50 relative overflow-hidden">
        <div className="relative z-10 flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          <div className="max-w-2xl">
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-md bg-muted/60 border border-border/40 text-[11px] text-muted-foreground font-medium">
                <Sparkles size={13} />
                Auto-Learning Prospect Filter
              </span>
              <span className="text-[11px] text-muted-foreground font-mono font-medium flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                Learns from Won Deals
              </span>
            </div>
            <h2 className="text-sm font-medium text-foreground tracking-tight flex items-center gap-2">
              Lead Fit AI &amp; Smart Lead Qualification
              <span className="text-[11px] text-muted-foreground font-normal">(elesium.online)</span>
            </h2>
            <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
              Every meeting booked (+3x win signal) or positive reply (+2x win signal) automatically trains the AI to prioritize similar prospects. Ghosted deals (+1x loss signal) lower priority—saving your outreach credits.
            </p>
          </div>

          {/* Quick Metrics & Controls */}
          <div className="flex flex-wrap items-center gap-3 bg-muted/20 border border-border/40 p-3 rounded-lg">
            <div className="px-2">
              <p className="text-[10px] text-muted-foreground uppercase font-medium tracking-wider">Lead Traits</p>
              <p className="text-lg font-mono font-medium text-foreground">{signals.length || 8}</p>
            </div>
            <div className="h-6 w-px bg-border/40" />
            <div className="px-2">
              <p className="text-[10px] text-muted-foreground uppercase font-medium tracking-wider">Leads Evaluated</p>
              <p className="text-lg font-mono font-medium text-foreground">{totalObservations}</p>
            </div>
            <div className="h-6 w-px bg-border/40" />
            <div className="px-2">
              <p className="text-[10px] text-muted-foreground uppercase font-medium tracking-wider">Credit Gate</p>
              <p className="text-lg font-mono font-medium text-foreground">{recommendedScoreGate}%</p>
            </div>
            <div className="h-6 w-px bg-border/40" />
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => setShowResetModal(true)}
                className="px-2.5 py-1.5 rounded-lg border border-border/50 bg-card hover:bg-muted/50 text-muted-foreground hover:text-foreground text-xs font-medium flex items-center gap-1 transition-all cursor-pointer"
                title="Reset all qualification learning to baseline defaults"
              >
                <ShieldAlert size={12} />
                <span>Reset</span>
              </button>
              <button 
                type="button"
                onClick={() => { mutateMatrix(); mutateEvents(); }}
                className="w-7 h-7 flex items-center justify-center rounded-lg border border-border/50 bg-card hover:bg-muted/50 text-muted-foreground hover:text-foreground transition-all cursor-pointer"
                title="Refresh Matrix"
              >
                <RefreshCw size={12} className={matrixLoading || eventsLoading ? "animate-spin" : ""} />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ── Model Drift Radar Alert Banner ── */}
      {driftWarnings.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <Zap size={13} className="text-amber-500" />
            <span>Real-Time Conversion Trends</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {driftWarnings.map((warn, idx) => (
              <div 
                key={idx}
                className="p-3.5 rounded-xl border border-border/50 bg-card/40 flex items-start justify-between gap-3"
              >
                <div className="flex items-start gap-2.5">
                  <div className="w-6 h-6 rounded-md bg-muted/60 border border-border/40 flex items-center justify-center text-muted-foreground shrink-0 mt-0.5">
                    {warn.severity === "POSITIVE_ACCELERATION" ? <Flame size={13} className="text-emerald-500" /> : <AlertTriangle size={13} className="text-amber-500" />}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h4 className="text-xs font-medium text-foreground">{warn.label}</h4>
                      <span className="text-[10px] font-medium px-2 py-0.5 rounded-md bg-muted text-muted-foreground border border-border/40 font-mono">
                        {warn.severity === "POSITIVE_ACCELERATION" ? "High Win Rate" : "Low Win Rate"}
                      </span>
                    </div>
                    <p className="text-[11px] text-muted-foreground mt-0.5 leading-relaxed">
                      {warn.message}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Adaptive Score Gate Gauge Section ── */}
      <div className="p-5 rounded-xl border border-border/50 bg-card/40 flex flex-col md:flex-row items-center justify-between gap-4">
        <div className="space-y-0.5 max-w-xl">
          <div className="flex items-center gap-2">
            <Gauge size={15} className="text-muted-foreground" />
            <h3 className="text-xs font-medium text-foreground">Credit Protection Gate ({recommendedScoreGate}/100)</h3>
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed">
            Based on {totalObservations} evaluated prospects, leads scoring below <strong className="text-foreground">{recommendedScoreGate}/100</strong> are automatically held from campaigns. This saves your daily outreach credits and protects domain reputation.
          </p>
        </div>

        <div className="flex items-center gap-4 w-full md:w-auto shrink-0">
          <div className="flex-1 md:w-48 space-y-1">
            <div className="flex justify-between text-[11px] font-mono text-muted-foreground">
              <span>Gate Threshold</span>
              <span className="text-foreground font-medium">{recommendedScoreGate} / 100</span>
            </div>
            <div className="w-full bg-muted/60 h-2 rounded-full overflow-hidden border border-border/40">
              <div 
                className="bg-foreground h-full rounded-full transition-all duration-500"
                style={{ width: `${recommendedScoreGate}%` }}
              />
            </div>
          </div>
          <div className="px-2.5 py-1.5 rounded-lg bg-muted/30 border border-border/40 text-center">
            <span className="text-[9px] text-muted-foreground block font-mono uppercase">Status</span>
            <span className="text-xs font-mono font-medium text-foreground">Active Gate</span>
          </div>
        </div>
      </div>

      {/* ── Signal Calibration Studio Matrix ── */}
      <div className="space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h3 className="text-xs font-medium text-foreground tracking-tight flex items-center gap-1.5">
              <BarChart3 size={14} className="text-muted-foreground" />
              Lead Qualification Rules &amp; Learning
            </h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              How the AI evaluates each lead trait. Booked calls boost importance; ghosted messages lower it.
            </p>
          </div>

          {/* Category Filter Pills */}
          <div className="flex items-center gap-1 p-0.5 rounded-lg bg-muted/30 border border-border/40">
            {["ALL", "FIRMOGRAPHIC", "BEHAVIORAL", "INTENT"].map((cat) => (
              <button
                type="button"
                key={cat}
                onClick={() => setActiveCategoryFilter(cat)}
                className={`text-[11px] font-medium px-2.5 py-1 rounded-md transition-all cursor-pointer ${
                  activeCategoryFilter === cat
                    ? "bg-card text-foreground shadow-2xs border border-border/50"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/30"
                }`}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>

        {/* Grid of Signals */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
          {filteredSignals.map((signal) => {
            const isBusy = updatingSignal === signal.signal_name;
            const ciLowerPct = (signal.credible_interval_lower * 100).toFixed(1);
            const ciUpperPct = (signal.credible_interval_upper * 100).toFixed(1);
            const rawMeanPct = (signal.raw_mean * 100).toFixed(1);
            const effectiveWeight = (signal.effective_weight).toFixed(2);

            return (
              <div 
                key={signal.signal_name}
                className="p-4 rounded-xl border border-border/50 bg-card/40 hover:bg-card/70 hover:border-border/80 transition-all flex flex-col justify-between shadow-2xs"
              >
                <div>
                  {/* Card Top Header */}
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <div>
                      <div className="flex items-center gap-1.5">
                        <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-md bg-muted text-muted-foreground border border-border/40">
                          {signal.category}
                        </span>
                        <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-md bg-muted text-muted-foreground border border-border/40">
                          {signal.confidence_tier}
                        </span>
                      </div>
                      <h4 className="text-xs font-medium text-foreground mt-1.5">{signal.label}</h4>
                    </div>

                    {/* Freeze Lock Toggle Button */}
                    <button
                      type="button"
                      onClick={() => handleToggleFreeze(signal)}
                      disabled={isBusy}
                      className={`p-1.5 rounded-md border transition-all cursor-pointer flex items-center gap-1 text-[10px] font-medium shrink-0 ${
                        signal.is_frozen
                          ? "bg-amber-500/10 border-amber-500/20 text-amber-600 dark:text-amber-400"
                          : "bg-muted/40 border-border/40 text-muted-foreground hover:text-foreground hover:bg-muted/60"
                      }`}
                      title={signal.is_frozen ? "Trait is locked: Click to unlock automated learning" : "Auto-learning is active: Click to lock against automated changes"}
                    >
                      {signal.is_frozen ? (
                        <>
                          <Lock size={11} />
                          <span>Locked</span>
                        </>
                      ) : (
                        <>
                          <Unlock size={11} />
                          <span>Auto-Learns</span>
                        </>
                      )}
                    </button>
                  </div>

                  <p className="text-xs text-muted-foreground mb-3 leading-relaxed line-clamp-2">
                    {signal.description}
                  </p>
                </div>

                {/* Mathematical Metrics & Credible Interval */}
                <div className="space-y-2.5 pt-2.5 border-t border-border/40">
                  {/* Empirical Win Rate & Weight */}
                  <div className="flex items-center justify-between text-xs">
                    <div>
                      <span className="text-[9px] text-muted-foreground font-mono block uppercase">Win Rate</span>
                      <span className="text-xs font-mono font-medium text-foreground">{rawMeanPct}%</span>
                    </div>
                    <div className="text-right">
                      <span className="text-[9px] text-muted-foreground font-mono block uppercase">Scoring Impact</span>
                      <span className="text-xs font-mono font-medium text-foreground">{effectiveWeight} ({signal.weight_multiplier}x)</span>
                    </div>
                  </div>

                  {/* 95% Credible Interval Bar */}
                  <div className="space-y-1">
                    <div className="flex justify-between text-[10px] font-mono text-muted-foreground">
                      <span>Confidence Range</span>
                      <span className="text-foreground">[{ciLowerPct}% — {ciUpperPct}%]</span>
                    </div>
                    <div className="w-full bg-muted/60 h-1.5 rounded-full overflow-hidden relative border border-border/40">
                      <div 
                        className="bg-foreground/20 h-full rounded-full absolute"
                        style={{ 
                          left: `${Math.max(0, signal.credible_interval_lower * 100)}%`,
                          width: `${Math.max(5, (signal.credible_interval_upper - signal.credible_interval_lower) * 100)}%`
                        }}
                      />
                      <div 
                        className="bg-foreground h-full rounded-full absolute transition-all duration-300"
                        style={{ 
                          left: `${Math.max(0, (signal.raw_mean * 100) - 1)}%`,
                          width: "3%"
                        }}
                      />
                    </div>
                  </div>

                  {/* Learning Counts */}
                  <div className="flex items-center justify-between text-[10px] font-mono text-muted-foreground bg-muted/20 px-2 py-1 rounded-md border border-border/30">
                    <span>Won: <strong className="text-foreground font-medium">{signal.alpha}</strong></span>
                    <span>Lost: <strong className="text-foreground font-medium">{signal.beta}</strong></span>
                    <span>Tested: <strong className="text-foreground font-medium">{signal.sample_size}</strong></span>
                  </div>

                  {/* Operator Multiplier Quick Adjust */}
                  <div className="pt-1 flex items-center justify-between gap-1 text-[10px]">
                    <span className="text-muted-foreground flex items-center gap-1">
                      <Sliders size={11} /> Boost:
                    </span>
                    <div className="flex items-center gap-1">
                      {[0.5, 1.0, 1.5, 2.0].map((mult) => (
                        <button
                          type="button"
                          key={mult}
                          onClick={() => handleMultiplierChange(signal, mult)}
                          disabled={isBusy}
                          className={`px-1.5 py-0.5 rounded-md font-mono text-[10px] transition-all cursor-pointer ${
                            Math.abs(signal.weight_multiplier - mult) < 0.05
                              ? "bg-foreground text-background font-medium"
                              : "bg-muted/40 hover:bg-muted text-muted-foreground hover:text-foreground"
                          }`}
                        >
                          {mult}x
                        </button>
                      ))}
                      <button
                        type="button"
                        onClick={() => handleResetSignalPrior(signal)}
                        disabled={isBusy}
                        className="p-1 rounded-md bg-muted/30 hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-all cursor-pointer ml-1"
                        title="Reset this trait to baseline default"
                      >
                        <RotateCcw size={10} />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Chronological Adaptive Feedback Ledger ── */}
      <div className="p-5 rounded-xl border border-border/50 bg-card/40 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <History size={14} className="text-muted-foreground" />
            <h3 className="text-xs font-medium text-foreground">Live Conversion Learning History</h3>
          </div>
          <span className="text-[11px] text-muted-foreground font-mono">Recent Campaign Outcomes</span>
        </div>

        <div className="divide-y divide-border/30 max-h-60 overflow-y-auto pr-1">
          {events.length === 0 ? (
            <div className="py-6 text-center text-xs text-muted-foreground">
              No outcome events recorded yet. As prospects book meetings and reply, learning events will stream here in real time.
            </div>
          ) : (
            events.map((evt) => (
              <div key={evt.id} className="py-2.5 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
                <div className="flex items-center gap-2.5">
                  {getEventBadge(evt.event_type)}
                  <div>
                    <span className="font-medium text-foreground">
                      {evt.signals_affected?.join(", ") || "General Trait"}
                    </span>
                    {evt.details && Object.keys(evt.details).length > 0 && (
                      <span className="text-[11px] text-muted-foreground block font-mono mt-0.5">
                        {JSON.stringify(evt.details).slice(0, 70)}
                      </span>
                    )}
                  </div>
                </div>
                <div className="text-[10px] text-muted-foreground font-mono shrink-0">
                  {new Date(evt.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* ── Interactive Prospect Score Simulator ── */}
      <div className="p-6 rounded-xl border border-border/50 bg-card/40">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-xs font-medium text-foreground flex items-center gap-1.5">
              <Layers size={14} className="text-muted-foreground" />
              Lead Qualification Simulator
            </h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Test any prospect profile to see how the AI grades them before spending outreach credits.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 items-start">
          {/* Form */}
          <div className="space-y-3 bg-card/60 p-4 rounded-xl border border-border/50">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[11px] font-medium text-muted-foreground mb-1 block">Job Title</label>
                <input
                  type="text"
                  value={testProfile.title}
                  onChange={(e) => setTestProfile({ ...testProfile, title: e.target.value })}
                  className="w-full text-xs px-3 py-2 rounded-lg bg-background border border-border/60 text-foreground focus:outline-none focus:border-border focus:ring-1 focus:ring-ring"
                />
              </div>
              <div>
                <label className="text-[11px] font-medium text-muted-foreground mb-1 block">Company Name</label>
                <input
                  type="text"
                  value={testProfile.company}
                  onChange={(e) => setTestProfile({ ...testProfile, company: e.target.value })}
                  className="w-full text-xs px-3 py-2 rounded-lg bg-background border border-border/60 text-foreground focus:outline-none focus:border-border focus:ring-1 focus:ring-ring"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[11px] font-medium text-muted-foreground mb-1 block">Employee Headcount</label>
                <input
                  type="number"
                  value={testProfile.headcount}
                  onChange={(e) => setTestProfile({ ...testProfile, headcount: parseInt(e.target.value) || 0 })}
                  className="w-full text-xs px-3 py-2 rounded-lg bg-background border border-border/60 text-foreground focus:outline-none focus:border-border focus:ring-1 focus:ring-ring"
                />
              </div>
              <div>
                <label className="text-[11px] font-medium text-muted-foreground mb-1 block">Industry Vertical</label>
                <input
                  type="text"
                  value={testProfile.industry}
                  onChange={(e) => setTestProfile({ ...testProfile, industry: e.target.value })}
                  className="w-full text-xs px-3 py-2 rounded-lg bg-background border border-border/60 text-foreground focus:outline-none focus:border-border focus:ring-1 focus:ring-ring"
                />
              </div>
            </div>

            <div className="flex items-center justify-between pt-1">
              <label className="text-xs font-normal text-foreground flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={testProfile.recent_posts}
                  onChange={(e) => setTestProfile({ ...testProfile, recent_posts: e.target.checked })}
                  className="rounded border-border text-foreground focus:ring-ring"
                />
                <span>Active posts in last 14 days</span>
              </label>

              <button
                type="button"
                onClick={handleSimulateScore}
                disabled={simulating}
                className="px-3.5 py-1.5 bg-foreground text-background text-xs font-medium rounded-lg transition-all shadow-2xs flex items-center gap-1.5 disabled:opacity-50 cursor-pointer"
              >
                {simulating ? (
                  <RefreshCw size={13} className="animate-spin" />
                ) : isIcpLocked ? (
                  <Lock size={13} className="text-amber-500" />
                ) : (
                  <Play size={13} />
                )}
                <span>Run Evaluation</span>
                {isIcpLocked && (
                  <span className="px-1.5 py-0.2 rounded-md bg-muted text-muted-foreground text-[9px] font-mono">
                    PRO
                  </span>
                )}
              </button>
            </div>
          </div>

          {/* Results Display */}
          <div className="p-4 rounded-xl border border-border/50 bg-card/60 h-full flex flex-col justify-between">
            {simResult ? (
              <div>
                <div className="flex items-center justify-between pb-3 border-b border-border/40 mb-3">
                  <span className="text-xs font-medium text-muted-foreground">Computed Fit Score</span>
                  <span className="text-xl font-mono font-medium px-2.5 py-0.5 rounded-md border border-border/50 bg-muted/30 text-foreground">
                    {simResult.score}/100
                  </span>
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-medium text-foreground">Qualification Analysis:</p>
                    <span className={`text-[10px] font-medium px-2 py-0.5 rounded-md ${
                      simResult.score >= recommendedScoreGate 
                        ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20' 
                        : 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20'
                    }`}>
                      {simResult.score >= recommendedScoreGate ? "Passed Credit Gate" : "Held to Save Credits"}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed bg-muted/20 p-3 rounded-lg border border-border/40">
                    {simResult.reasoning || "Evaluation completed against your conversion history."}
                  </p>
                </div>

                {/* Simulate Feedback Outcomes */}
                <div className="mt-4 pt-3 border-t border-border/40">
                  <p className="text-[11px] font-medium text-muted-foreground mb-2">Simulate Conversion Learning:</p>
                  <div className="grid grid-cols-3 gap-2">
                    <button
                      type="button"
                      onClick={() => handleSimulateOutcome("MEETING_BOOKED")}
                      className="py-1.5 px-1 rounded-lg bg-card hover:bg-muted text-foreground border border-border/50 text-xs font-medium flex items-center justify-center gap-1 transition-all cursor-pointer"
                    >
                      <UserCheck size={12} className="text-emerald-500" />
                      <span>Booked (+3x Win)</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => handleSimulateOutcome("POSITIVE_REPLY")}
                      className="py-1.5 px-1 rounded-lg bg-card hover:bg-muted text-foreground border border-border/50 text-xs font-medium flex items-center justify-center gap-1 transition-all cursor-pointer"
                    >
                      <MessageSquare size={12} />
                      <span>Reply (+2x Win)</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => handleSimulateOutcome("GHOSTED_OR_LOST")}
                      className="py-1.5 px-1 rounded-lg bg-card hover:bg-muted text-foreground border border-border/50 text-xs font-medium flex items-center justify-center gap-1 transition-all cursor-pointer"
                    >
                      <XCircle size={12} className="text-rose-500" />
                      <span>Lost (+1x Loss)</span>
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="h-56 flex flex-col items-center justify-center text-center p-4 text-muted-foreground">
                <Sparkles size={24} className="text-muted-foreground/40 mb-2" />
                <p className="text-xs font-medium text-foreground">No Simulation Run Yet</p>
                <p className="text-[11px] text-muted-foreground mt-0.5 max-w-xs leading-relaxed">
                  Enter candidate parameters on the left and click "Run Evaluation" to preview scoring before spending credits.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Emergency Reset Modal (Circuit Breaker) ── */}
      <AnimatePresence>
        {showResetModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm">
            <motion.div
              initial={{ scale: 0.98, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.98, opacity: 0 }}
              className="bg-card border border-border/60 rounded-xl max-w-sm w-full p-5 shadow-2xl relative space-y-3"
            >
              <div className="w-8 h-8 rounded-lg bg-destructive/10 text-destructive flex items-center justify-center mb-1">
                <ShieldAlert size={16} />
              </div>
              <h3 className="text-sm font-medium text-foreground">Reset Qualification Model</h3>
              <p className="text-xs text-muted-foreground leading-relaxed">
                This will reset all learned qualification probabilities back to default neutral baselines across your workspace. Multipliers will reset to 1.0x and trait locks will be removed.
              </p>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowResetModal(false)}
                  disabled={isResettingAll}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-all cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleResetAllSignals}
                  disabled={isResettingAll}
                  className="px-3.5 py-1.5 rounded-lg bg-destructive text-destructive-foreground text-xs font-medium hover:bg-destructive/90 transition-all shadow-2xs flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                >
                  {isResettingAll ? <RefreshCw size={12} className="animate-spin" /> : <ShieldAlert size={12} />}
                  <span>Confirm Full Reset</span>
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
