import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { 
  Sparkles, TrendingUp, CheckCircle2, XCircle, RefreshCw, 
  Cpu, ArrowUpRight, BarChart3, ShieldCheck, HelpCircle, 
  Check, Play, Layers, Lock, Unlock, AlertTriangle,
  RotateCcw, History, Zap, Gauge, Sliders, ShieldAlert,
  Flame, ArrowDownRight, UserCheck, MessageSquare, Briefcase
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
        toast.success(`Weight multiplier for "${signal.label}" set to ${newMultiplier}x`);
        mutateMatrix();
        mutateEvents();
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || "Failed to adjust multiplier");
      }
    } catch (e: any) {
      toast.error(e.message || "Network error");
    } finally {
      setUpdatingSignal(null);
    }
  };

  // Reset individual signal prior to Beta(2,2)
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
        body: JSON.stringify({ reset_to_prior: true, weight_multiplier: 1.0, is_frozen: false }),
      });
      if (res.ok) {
        toast.success(`Signal "${signal.label}" reset to neutral prior Beta(2,2).`);
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
        toast.success("Emergency Circuit Breaker Triggered: All Bayesian weights restored to baseline Beta(2,2)");
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
        toast.success("Bayesian ICP Score computed successfully!");
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
        toast.success(`Adaptive feedback loop recorded! Prior distribution reinforced for ${outcome.replace(/_/g, " ")}.`);
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

  const getCategoryColor = (cat: string) => {
    switch (cat?.toUpperCase()) {
      case "FIRMOGRAPHIC":
        return "bg-cyan-500/10 text-cyan-400 border-cyan-500/20";
      case "BEHAVIORAL":
        return "bg-blue-500/10 text-blue-400 border-blue-500/20";
      case "INTENT":
        return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
      default:
        return "bg-slate-500/10 text-slate-400 border-slate-500/20";
    }
  };

  const getConfidenceTierBadge = (tier: string) => {
    switch (tier?.toUpperCase()) {
      case "HIGH":
        return (
          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 flex items-center gap-1">
            <ShieldCheck size={11} /> High Conf (N≥30)
          </span>
        );
      case "MEDIUM":
        return (
          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-blue-500/15 text-blue-400 border border-blue-500/30 flex items-center gap-1">
            <Gauge size={11} /> Medium Conf (N≥10)
          </span>
        );
      default:
        return (
          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-400 border border-amber-500/30 flex items-center gap-1">
            <HelpCircle size={11} /> Sparse / Early Prior
          </span>
        );
    }
  };

  const getEventBadge = (type: string) => {
    switch (type) {
      case "MEETING_BOOKED":
        return <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">Meeting Booked (+3α)</span>;
      case "POSITIVE_REPLY":
        return <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-indigo-500/20 text-indigo-400 border border-indigo-500/30">Positive Reply (+2α)</span>;
      case "CONNECTION_ACCEPTED":
        return <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-blue-500/20 text-blue-400 border border-blue-500/30">Connected (+1α)</span>;
      case "GHOSTED_OR_LOST":
      case "lost":
        return <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-rose-500/20 text-rose-400 border border-rose-500/30">Ghosted / Lost (+1β)</span>;
      case "MANUAL_OVERRIDE":
        return <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-sky-500/20 text-sky-400 border border-sky-500/30">Operator Override</span>;
      case "RESET_ALL":
        return <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-amber-500/20 text-amber-400 border border-amber-500/30">Circuit Breaker Reset</span>;
      default:
        return <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-muted text-muted-foreground border border-border/50">{type}</span>;
    }
  };

  return (
    <div className="space-y-8 pb-12">
      {/* ── Growth Pro Lock Banner ── */}
      {!isPro && (
        <div className="p-6 rounded-[28px] border border-primary/20 bg-gradient-to-r from-primary/10 via-primary/[0.03] to-transparent shadow-sm flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-start gap-4">
            <div className="p-3 bg-primary/15 rounded-2xl text-primary mt-0.5 shrink-0 shadow-sm">
              <Cpu size={24} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-bold text-foreground">
                  Bayesian ICP Calibration Studio & Adaptive Feedback Loop
                </h3>
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-primary/15 text-primary border border-primary/25">
                  Growth Pro
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-1 max-w-xl leading-relaxed">
                Autonomous Beta-Binomial conjugate updating continuously adapts scoring weights across won and lost outreach signals. Upgrade to Growth Pro to adjust operator multiplier sliders, freeze signal drift, and automate qualification score gates.
              </p>
            </div>
          </div>
          <button
            onClick={() => openPaywall({ featureName: "Bayesian ICP Machine Learning" })}
            className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-primary text-primary-foreground text-xs font-bold hover:bg-primary/90 transition-all shadow-md shrink-0 whitespace-nowrap active:scale-95 cursor-pointer"
          >
            <span>Unlock Calibration Studio</span>
            <ArrowUpRight size={14} />
          </button>
        </div>
      )}

      {/* ── Studio Cockpit Header ── */}
      <div className="p-8 rounded-[32px] bg-gradient-to-br from-indigo-950/40 via-background to-muted/20 border border-indigo-500/20 backdrop-blur-xl relative overflow-hidden shadow-2xl">
        <div className="absolute top-0 right-0 w-80 h-80 bg-indigo-500/10 rounded-full blur-[80px] pointer-events-none" />
        
        <div className="relative z-10 flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          <div className="max-w-2xl">
            <div className="flex flex-wrap items-center gap-2 mb-3">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/30 text-indigo-400 text-xs font-semibold">
                <Cpu size={14} className="animate-pulse" />
                Beta-Binomial Conjugate Engine
              </div>
              <span className="text-xs text-emerald-400 font-mono font-medium flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping" />
                Continuous Thomson Sampling
              </span>
            </div>
            <h2 className="text-2xl font-bold text-foreground tracking-tight flex items-center gap-2">
              Elesium Bayesian ICP Calibration Studio
              <img src="/elesium-icon.png" alt="Elesium" className="w-5 h-5 object-contain" />
              <a
                href="https://elesium.online"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs font-semibold text-primary hover:underline ml-1"
              >
                (elesium.online)
              </a>
            </h2>
            <p className="text-sm text-muted-foreground mt-2 leading-relaxed">
              Every meeting booked (+3α), positive reply (+2α), connection accepted (+1α), or ghosted deal (+1β) updates the posterior Beta distribution in real time. Rigorously protected by operator freeze locks and sample damping.
            </p>
          </div>

          {/* Quick Metrics & Controls */}
          <div className="flex flex-wrap items-center gap-4 bg-background/50 border border-border/50 p-4 rounded-2xl backdrop-blur-md">
            <div>
              <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider">Signals</p>
              <p className="text-2xl font-mono font-bold text-foreground">{signals.length || 8}</p>
            </div>
            <div className="h-8 w-px bg-border/60" />
            <div>
              <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider">Total Data Points</p>
              <p className="text-2xl font-mono font-bold text-indigo-400">{totalObservations}</p>
            </div>
            <div className="h-8 w-px bg-border/60" />
            <div>
              <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider">Score Gate Cutoff</p>
              <p className="text-2xl font-mono font-bold text-emerald-400">{recommendedScoreGate}%</p>
            </div>
            <div className="h-8 w-px bg-border/60" />
            <div className="flex flex-col gap-1.5">
              <button
                onClick={() => setShowResetModal(true)}
                className="px-3 py-1.5 rounded-lg border border-rose-500/30 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 text-[11px] font-bold flex items-center gap-1.5 transition-all cursor-pointer"
                title="1-Click Emergency Factory Reset"
              >
                <ShieldAlert size={12} />
                <span>Circuit Breaker</span>
              </button>
              <button 
                onClick={() => { mutateMatrix(); mutateEvents(); }}
                className="text-[11px] text-muted-foreground hover:text-foreground flex items-center justify-center gap-1.5 px-3 py-1 rounded-lg border border-border/50 hover:bg-muted/50 transition-all cursor-pointer"
              >
                <RefreshCw size={11} className={matrixLoading || eventsLoading ? "animate-spin" : ""} /> Refresh
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ── Model Drift Radar Alert Banner (Layer 2 Paranoia) ── */}
      {driftWarnings.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-muted-foreground">
            <Zap size={14} className="text-amber-400" />
            <span>Autonomous Model Drift Detection Radar</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {driftWarnings.map((warn, idx) => (
              <div 
                key={idx}
                className={`p-4 rounded-2xl border backdrop-blur-md flex items-start justify-between gap-4 ${
                  warn.severity === "POSITIVE_ACCELERATION"
                    ? "bg-emerald-950/20 border-emerald-500/30 text-emerald-300"
                    : "bg-rose-950/20 border-rose-500/30 text-rose-300"
                }`}
              >
                <div className="flex items-start gap-3">
                  <div className={`p-2 rounded-xl mt-0.5 ${
                    warn.severity === "POSITIVE_ACCELERATION" ? "bg-emerald-500/20 text-emerald-400" : "bg-rose-500/20 text-rose-400"
                  }`}>
                    {warn.severity === "POSITIVE_ACCELERATION" ? <Flame size={18} /> : <AlertTriangle size={18} />}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h4 className="text-xs font-bold text-foreground">{warn.label}</h4>
                      <span className={`text-[10px] font-bold px-1.5 py-0.2 rounded ${
                        warn.severity === "POSITIVE_ACCELERATION" ? "bg-emerald-500/20 text-emerald-400" : "bg-rose-500/20 text-rose-400"
                      }`}>
                        {warn.severity === "POSITIVE_ACCELERATION" ? "High-Yield Catalyst" : "Negative Divergence"}
                      </span>
                    </div>
                    <p className="text-[11px] text-muted-foreground mt-1 leading-relaxed">
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
      <div className="p-6 rounded-[28px] border border-border/60 bg-muted/5 backdrop-blur-xl flex flex-col md:flex-row items-center justify-between gap-6">
        <div className="space-y-1 max-w-xl">
          <div className="flex items-center gap-2">
            <Gauge size={18} className="text-indigo-400" />
            <h3 className="text-sm font-bold text-foreground">Recommended Qualification Score Gate</h3>
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed">
            Based on empirical convergence across {totalObservations} historical feedback data points, candidate prospects scoring below <strong className="text-indigo-400">{recommendedScoreGate}/100</strong> are recommended for secondary enrichment before costly connection requests.
          </p>
        </div>

        <div className="flex items-center gap-4 w-full md:w-auto shrink-0">
          <div className="flex-1 md:w-56 space-y-1.5">
            <div className="flex justify-between text-[11px] font-mono">
              <span className="text-muted-foreground">Cutoff Yield</span>
              <span className="text-emerald-400 font-bold">{recommendedScoreGate} / 100</span>
            </div>
            <div className="w-full bg-muted/60 h-2.5 rounded-full overflow-hidden p-0.5 border border-border/40">
              <div 
                className="bg-gradient-to-r from-amber-500 via-indigo-500 to-emerald-400 h-full rounded-full transition-all duration-700"
                style={{ width: `${recommendedScoreGate}%` }}
              />
            </div>
          </div>
          <div className="px-3 py-2 rounded-xl bg-background border border-border/50 text-center">
            <span className="text-[10px] text-muted-foreground block font-bold">STATUS</span>
            <span className="text-xs font-mono font-bold text-emerald-400">ACTIVE GATE</span>
          </div>
        </div>
      </div>

      {/* ── Signal Calibration Studio Matrix ── */}
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h3 className="text-base font-bold text-foreground flex items-center gap-2">
              <BarChart3 size={18} className="text-indigo-400" />
              Bayesian Signal Calibration Matrix
            </h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Inspect Beta(α, β) distributions, 95% Credible Intervals, operator freeze locks, and multiplier scalers.
            </p>
          </div>

          {/* Category Filter Pills */}
          <div className="flex items-center gap-1.5 p-1 rounded-xl bg-muted/20 border border-border/40">
            {["ALL", "FIRMOGRAPHIC", "BEHAVIORAL", "INTENT"].map((cat) => (
              <button
                key={cat}
                onClick={() => setActiveCategoryFilter(cat)}
                className={`text-[11px] font-bold px-3 py-1 rounded-lg transition-all cursor-pointer ${
                  activeCategoryFilter === cat
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/30"
                }`}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>

        {/* Grid of Signals */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {filteredSignals.map((signal) => {
            const isBusy = updatingSignal === signal.signal_name;
            const ciLowerPct = (signal.credible_interval_lower * 100).toFixed(1);
            const ciUpperPct = (signal.credible_interval_upper * 100).toFixed(1);
            const rawMeanPct = (signal.raw_mean * 100).toFixed(1);
            const effectiveWeight = (signal.effective_weight).toFixed(2);

            return (
              <div 
                key={signal.signal_name}
                className={`p-5 rounded-2xl border transition-all duration-200 flex flex-col justify-between backdrop-blur-sm relative overflow-hidden ${
                  signal.is_frozen
                    ? "border-amber-500/30 bg-amber-950/[0.04]"
                    : "border-border/60 bg-muted/10 hover:border-indigo-500/40"
                }`}
              >
                {/* Frozen Indicator Glow */}
                {signal.is_frozen && (
                  <div className="absolute top-0 right-0 w-16 h-16 bg-amber-500/10 rounded-full blur-xl pointer-events-none" />
                )}

                <div>
                  {/* Card Top Header */}
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <div>
                      <div className="flex items-center gap-1.5">
                        <span className={`text-[9px] font-bold px-2 py-0.5 rounded-full border ${getCategoryColor(signal.category)}`}>
                          {signal.category}
                        </span>
                        {getConfidenceTierBadge(signal.confidence_tier)}
                      </div>
                      <h4 className="text-sm font-bold text-foreground mt-2">{signal.label}</h4>
                    </div>

                    {/* Freeze Lock Toggle Button */}
                    <button
                      onClick={() => handleToggleFreeze(signal)}
                      disabled={isBusy}
                      className={`p-1.5 rounded-xl border transition-all cursor-pointer flex items-center gap-1 text-[10px] font-bold shrink-0 ${
                        signal.is_frozen
                          ? "bg-amber-500/20 border-amber-500/40 text-amber-300 hover:bg-amber-500/30"
                          : "bg-muted/40 border-border/50 text-muted-foreground hover:text-foreground hover:bg-muted/60"
                      }`}
                      title={signal.is_frozen ? "Signal is frozen: Click to unlock automated adaptation" : "Signal is auto-adapting: Click to freeze against drift"}
                    >
                      {signal.is_frozen ? (
                        <>
                          <Lock size={12} className="text-amber-400" />
                          <span>Frozen</span>
                        </>
                      ) : (
                        <>
                          <Unlock size={12} />
                          <span>Adapt</span>
                        </>
                      )}
                    </button>
                  </div>

                  <p className="text-xs text-muted-foreground mb-4 leading-relaxed line-clamp-2">
                    {signal.description}
                  </p>
                </div>

                {/* Mathematical Metrics & Credible Interval */}
                <div className="space-y-3 pt-3 border-t border-border/40">
                  {/* Empirical Win Rate & Weight */}
                  <div className="flex items-center justify-between text-xs">
                    <div>
                      <span className="text-[10px] text-muted-foreground font-mono block">WIN PROBABILITY</span>
                      <span className="text-sm font-bold font-mono text-emerald-400">{rawMeanPct}%</span>
                      <span className="text-[10px] text-muted-foreground font-mono ml-1">(±{(signal.std_dev * 100).toFixed(1)}%)</span>
                    </div>
                    <div className="text-right">
                      <span className="text-[10px] text-muted-foreground font-mono block">EFFECTIVE WEIGHT</span>
                      <span className="text-sm font-bold font-mono text-indigo-400">{effectiveWeight}</span>
                      <span className="text-[10px] text-muted-foreground font-mono ml-1">({signal.weight_multiplier}x)</span>
                    </div>
                  </div>

                  {/* 95% Credible Interval Bar */}
                  <div className="space-y-1">
                    <div className="flex justify-between text-[10px] font-mono text-muted-foreground">
                      <span>95% Credible Interval</span>
                      <span className="text-foreground font-bold">[{ciLowerPct}% — {ciUpperPct}%]</span>
                    </div>
                    <div className="w-full bg-muted/60 h-2 rounded-full overflow-hidden relative">
                      <div 
                        className="bg-indigo-500/30 h-full rounded-full absolute"
                        style={{ 
                          left: `${Math.max(0, signal.credible_interval_lower * 100)}%`,
                          width: `${Math.max(5, (signal.credible_interval_upper - signal.credible_interval_lower) * 100)}%`
                        }}
                      />
                      <div 
                        className="bg-emerald-400 h-full rounded-full absolute transition-all duration-500"
                        style={{ 
                          left: `${Math.max(0, (signal.raw_mean * 100) - 2)}%`,
                          width: "4%"
                        }}
                      />
                    </div>
                  </div>

                  {/* Beta Parameters α & β */}
                  <div className="flex items-center justify-between text-[11px] font-mono text-muted-foreground bg-background/50 px-3 py-1.5 rounded-xl border border-border/40">
                    <span>α (Wins) = <strong className="text-emerald-400">{signal.alpha}</strong></span>
                    <span>β (Losses) = <strong className="text-rose-400">{signal.beta}</strong></span>
                    <span>N = <strong className="text-foreground">{signal.sample_size}</strong></span>
                  </div>

                  {/* Operator Multiplier Quick Adjust */}
                  <div className="pt-2 flex items-center justify-between gap-1 text-[10px]">
                    <span className="text-muted-foreground font-bold flex items-center gap-1">
                      <Sliders size={11} /> Boost:
                    </span>
                    <div className="flex items-center gap-1">
                      {[0.5, 1.0, 1.5, 2.0].map((mult) => (
                        <button
                          key={mult}
                          onClick={() => handleMultiplierChange(signal, mult)}
                          disabled={isBusy}
                          className={`px-2 py-0.5 rounded font-mono font-bold transition-all cursor-pointer ${
                            Math.abs(signal.weight_multiplier - mult) < 0.05
                              ? "bg-indigo-600 text-white"
                              : "bg-muted/40 hover:bg-muted text-muted-foreground hover:text-foreground"
                          }`}
                        >
                          {mult}x
                        </button>
                      ))}
                      <button
                        onClick={() => handleResetSignalPrior(signal)}
                        disabled={isBusy}
                        className="p-1 rounded bg-muted/30 hover:bg-rose-500/10 text-muted-foreground hover:text-rose-400 transition-all cursor-pointer ml-1"
                        title="Reset this signal to Beta(2,2)"
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

      {/* ── Chronological Adaptive Feedback Ledger (Live Activity Log) ── */}
      <div className="p-6 rounded-[28px] border border-border/60 bg-muted/5 backdrop-blur-xl space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <History size={18} className="text-indigo-400" />
            <h3 className="text-base font-bold text-foreground">Adaptive Feedback Ledger</h3>
          </div>
          <span className="text-xs text-muted-foreground font-mono">Recent Reinforcement Events</span>
        </div>

        <div className="divide-y divide-border/40 max-h-72 overflow-y-auto pr-2">
          {events.length === 0 ? (
            <div className="py-8 text-center text-xs text-muted-foreground">
              No outcome events recorded yet. Deal conversions will stream here in real time.
            </div>
          ) : (
            events.map((evt) => (
              <div key={evt.id} className="py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
                <div className="flex items-center gap-3">
                  {getEventBadge(evt.event_type)}
                  <div>
                    <span className="font-semibold text-foreground">
                      Signals Updated: {evt.signals_affected?.join(", ") || "General Prior"}
                    </span>
                    {evt.details && Object.keys(evt.details).length > 0 && (
                      <span className="text-[11px] text-muted-foreground block font-mono">
                        {JSON.stringify(evt.details).slice(0, 80)}
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
      <div className="p-8 rounded-[32px] border border-border/60 bg-muted/5 backdrop-blur-xl">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="text-lg font-bold text-foreground flex items-center gap-2">
              <Layers size={20} className="text-indigo-400" />
              Live Bayesian Prospect Simulator
            </h3>
            <p className="text-xs text-muted-foreground mt-1">
              Verify how candidate prospect attributes score against active Bayesian posterior distributions before dispatching sequences.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-start">
          {/* Form */}
          <div className="space-y-4 bg-background/50 p-6 rounded-2xl border border-border/50">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-xs font-semibold text-muted-foreground mb-1 block">Job Title</label>
                <input
                  type="text"
                  value={testProfile.title}
                  onChange={(e) => setTestProfile({ ...testProfile, title: e.target.value })}
                  className="w-full text-xs px-3 py-2 rounded-xl bg-background border border-border/60 text-foreground focus:outline-none focus:border-indigo-500"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-muted-foreground mb-1 block">Company Name</label>
                <input
                  type="text"
                  value={testProfile.company}
                  onChange={(e) => setTestProfile({ ...testProfile, company: e.target.value })}
                  className="w-full text-xs px-3 py-2 rounded-xl bg-background border border-border/60 text-foreground focus:outline-none focus:border-indigo-500"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-xs font-semibold text-muted-foreground mb-1 block">Employee Headcount</label>
                <input
                  type="number"
                  value={testProfile.headcount}
                  onChange={(e) => setTestProfile({ ...testProfile, headcount: parseInt(e.target.value) || 0 })}
                  className="w-full text-xs px-3 py-2 rounded-xl bg-background border border-border/60 text-foreground focus:outline-none focus:border-indigo-500"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-muted-foreground mb-1 block">Industry Vertical</label>
                <input
                  type="text"
                  value={testProfile.industry}
                  onChange={(e) => setTestProfile({ ...testProfile, industry: e.target.value })}
                  className="w-full text-xs px-3 py-2 rounded-xl bg-background border border-border/60 text-foreground focus:outline-none focus:border-indigo-500"
                />
              </div>
            </div>

            <div className="flex items-center justify-between pt-2">
              <label className="text-xs font-semibold text-foreground flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={testProfile.recent_posts}
                  onChange={(e) => setTestProfile({ ...testProfile, recent_posts: e.target.checked })}
                  className="rounded border-border text-indigo-600 focus:ring-indigo-500"
                />
                Published active posts in last 14 days
              </label>

              <button
                onClick={handleSimulateScore}
                disabled={simulating}
                className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold rounded-xl transition-all shadow-md flex items-center gap-2 disabled:opacity-50 cursor-pointer"
              >
                {simulating ? (
                  <RefreshCw size={14} className="animate-spin" />
                ) : isIcpLocked ? (
                  <Lock size={14} className="text-amber-300" />
                ) : (
                  <Play size={14} />
                )}
                <span>Run Bayesian Evaluation</span>
                {isIcpLocked && (
                  <span className="px-1.5 py-0.2 rounded bg-amber-400 text-slate-950 text-[9px] font-black tracking-wide">
                    PRO
                  </span>
                )}
              </button>
            </div>
          </div>

          {/* Results Display */}
          <div className="p-6 rounded-2xl border border-border/50 bg-background/50 h-full flex flex-col justify-between">
            {simResult ? (
              <div>
                <div className="flex items-center justify-between pb-4 border-b border-border/50 mb-4">
                  <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Computed Fit Score</span>
                  <span className={`text-2xl font-black font-mono px-3 py-1 rounded-xl ${
                    simResult.score >= recommendedScoreGate
                      ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30" 
                      : simResult.score >= 50
                      ? "bg-amber-500/10 text-amber-400 border border-amber-500/30"
                      : "bg-rose-500/10 text-rose-400 border border-rose-500/30"
                  }`}>
                    {simResult.score}/100
                  </span>
                </div>

                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-semibold text-foreground">Probabilistic Reasoning & Active Signals:</p>
                    <span className="text-[10px] font-mono text-muted-foreground">
                      Gate: {simResult.score >= recommendedScoreGate ? "PASS" : "BELOW GATE"}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed bg-muted/20 p-4 rounded-xl border border-border/40 font-mono">
                    {simResult.reasoning || "Evaluation converged across active prior distribution matrix."}
                  </p>
                </div>

                {/* Simulate Feedback Outcomes */}
                <div className="mt-6 pt-4 border-t border-border/50">
                  <p className="text-[11px] font-semibold text-muted-foreground mb-2">Simulate Real-World Outcome Feedback:</p>
                  <div className="grid grid-cols-3 gap-2">
                    <button
                      onClick={() => handleSimulateOutcome("MEETING_BOOKED")}
                      className="py-2 px-1 rounded-xl bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 text-[11px] font-bold flex items-center justify-center gap-1 transition-all cursor-pointer"
                    >
                      <UserCheck size={12} />
                      <span>Booked (+3α)</span>
                    </button>
                    <button
                      onClick={() => handleSimulateOutcome("POSITIVE_REPLY")}
                      className="py-2 px-1 rounded-xl bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 text-[11px] font-bold flex items-center justify-center gap-1 transition-all cursor-pointer"
                    >
                      <MessageSquare size={12} />
                      <span>Reply (+2α)</span>
                    </button>
                    <button
                      onClick={() => handleSimulateOutcome("GHOSTED_OR_LOST")}
                      className="py-2 px-1 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 text-[11px] font-bold flex items-center justify-center gap-1 transition-all cursor-pointer"
                    >
                      <XCircle size={12} />
                      <span>Lost (+1β)</span>
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="h-64 flex flex-col items-center justify-center text-center p-6 text-muted-foreground">
                <Cpu size={32} className="text-muted-foreground/40 mb-3" />
                <p className="text-xs font-semibold text-foreground">No Simulation Run Yet</p>
                <p className="text-[11px] text-muted-foreground mt-1 max-w-xs">
                  Fill in candidate variables on the left and click "Run Bayesian Evaluation" to preview real-time scoring.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Emergency Reset Modal (Circuit Breaker) ── */}
      <AnimatePresence>
        {showResetModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="bg-card border border-rose-500/30 rounded-3xl max-w-md w-full p-6 shadow-2xl relative space-y-4"
            >
              <div className="flex items-center gap-3 text-rose-400">
                <div className="p-3 bg-rose-500/15 rounded-2xl">
                  <ShieldAlert size={24} />
                </div>
                <div>
                  <h3 className="text-base font-bold text-foreground">Emergency Circuit Breaker</h3>
                  <p className="text-xs text-rose-400/80 font-mono">Reset All Priors to Beta(2,2)</p>
                </div>
              </div>

              <p className="text-xs text-muted-foreground leading-relaxed">
                This will reset all learned Bayesian probabilities and alpha/beta parameters across your entire workspace back to baseline neutral priors (50% win rate). All operator multipliers will be restored to 1.0x and freeze locks will be removed.
              </p>

              <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-[11px] leading-relaxed">
                <strong>Safety Notice:</strong> Historical deal logs in the Feedback Ledger will be retained for audit trails, but model scoring weights will immediately reset.
              </div>

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  onClick={() => setShowResetModal(false)}
                  disabled={isResettingAll}
                  className="px-4 py-2 rounded-xl text-xs font-semibold text-muted-foreground hover:text-foreground hover:bg-muted/40 transition-all cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  onClick={handleResetAllSignals}
                  disabled={isResettingAll}
                  className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold transition-all shadow-md flex items-center gap-2 cursor-pointer disabled:opacity-50"
                >
                  {isResettingAll ? <RefreshCw size={14} className="animate-spin" /> : <ShieldAlert size={14} />}
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
