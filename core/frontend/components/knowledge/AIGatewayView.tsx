import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  Cpu,
  Sparkles,
  Zap,
  Key,
  Lock,
  ArrowUpRight,
  Check,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Coins,
  Server,
  ChevronRight,
  Eye,
  EyeOff,
  Trash2,
  ExternalLink,
  ShieldCheck,
  Activity,
  Layers,
  Clock,
  Gauge
} from "lucide-react";
import useSWR from "swr";
import { fetchWithAuth, fetcher } from "@/lib/apiClient";
import { usePaywall } from "@/contexts/PaywallContext";
import { toast } from "sonner";

interface ModelInfo {
  id: string;
  name: string;
  provider: string;
  description: string;
  is_pro: boolean;
  cost_in: string;
  cost_out: string;
  latency: string;
  context_window: string;
}

interface TelemetryData {
  status: string;
  is_locked: boolean;
  tier: string;
  total_tokens: number;
  total_cost: number;
  total_calls: number;
  monthly_token_budget: number;
  model_breakdown: Array<{
    model: string;
    count: number;
    tokens: number;
    cost: number;
  }>;
  recent_generations: Array<{
    id: string;
    model: string;
    tokens_used: number;
    cost: number;
    prompt_preview: string;
    output_preview: string;
    created_at: string;
  }>;
}

interface AISettingsData {
  status: string;
  tier: string;
  can_choose_ai_models: boolean;
  can_byok_ai_keys: boolean;
  can_view_token_telemetry: boolean;
  default_model: string;
  byok_provider: string | null;
  byok_key_masked: string | null;
  has_byok: boolean;
  temperature: number;
  max_tokens_budget: number;
  available_models: ModelInfo[];
}

export function AIGatewayView({ isPro }: { isPro: boolean }) {
  const { openPaywall } = usePaywall();

  const {
    data: settings,
    mutate: mutateSettings,
    isLoading: isSettingsLoading,
  } = useSWR<AISettingsData>("/api/knowledge/ai/settings", fetcher);

  const {
    data: telemetry,
    mutate: mutateTelemetry,
    isLoading: isTelemetryLoading,
  } = useSWR<TelemetryData>("/api/knowledge/ai/telemetry", fetcher);

  // BYOK form state
  const [selectedProvider, setSelectedProvider] = useState<string>("openai");
  const [apiKeyInput, setApiKeyInput] = useState<string>("");
  const [showKeyText, setShowKeyText] = useState<boolean>(false);
  const [isSavingKey, setIsSavingKey] = useState<boolean>(false);
  const [isTestingKey, setIsTestingKey] = useState<boolean>(false);
  const [isUpdatingModel, setIsUpdatingModel] = useState<string | null>(null);

  const currentModel = settings?.default_model || "Auto-Route (Recommended)";
  const canChooseModels = isPro || Boolean(settings?.can_choose_ai_models);
  const canByok = isPro || Boolean(settings?.can_byok_ai_keys);
  const canViewTelemetry = isPro || Boolean(settings?.can_view_token_telemetry);

  const handleSelectModel = async (model: ModelInfo) => {
    if (model.id === currentModel) return;

    if (model.is_pro && !canChooseModels) {
      openPaywall({ featureName: "Advanced AI Model Selection" });
      return;
    }

    setIsUpdatingModel(model.id);
    // Optimistic update
    mutateSettings(
      (prev) => prev ? { ...prev, default_model: model.id } : prev,
      false
    );

    try {
      const res = await fetchWithAuth("/api/knowledge/ai/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ default_model: model.id }),
      });

      if (!res.ok) {
        if (res.status === 402 || res.status === 403) {
          openPaywall({ featureName: "Advanced AI Model Selection" });
          mutateSettings();
          return;
        }
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to switch AI model");
      }

      toast.success(`Active AI Model set to ${model.name}`);
      mutateSettings();
    } catch (e: any) {
      toast.error(e.message || "Failed to update AI model");
      mutateSettings();
    } finally {
      setIsUpdatingModel(null);
    }
  };

  const handleTestKey = async () => {
    if (!apiKeyInput.trim()) {
      toast.error("Please enter an API key to test");
      return;
    }
    if (!canByok) {
      openPaywall({ featureName: "Bring Your Own Key (BYOK)" });
      return;
    }

    setIsTestingKey(true);
    try {
      const res = await fetchWithAuth("/api/knowledge/ai/test-key", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: selectedProvider,
          api_key: apiKeyInput.trim(),
        }),
      });

      const json = await res.json();
      if (!res.ok) {
        if (res.status === 402 || res.status === 403) {
          openPaywall({ featureName: "Bring Your Own Key (BYOK)" });
          return;
        }
        throw new Error(json.detail || "Invalid API key format");
      }

      toast.success(json.message || "Key format verified successfully!");
    } catch (e: any) {
      toast.error(e.message || "Key verification failed");
    } finally {
      setIsTestingKey(false);
    }
  };

  const handleSaveKey = async () => {
    if (!apiKeyInput.trim()) {
      toast.error("Please enter your provider API key");
      return;
    }
    if (!canByok) {
      openPaywall({ featureName: "Bring Your Own Key (BYOK)" });
      return;
    }

    setIsSavingKey(true);
    try {
      const res = await fetchWithAuth("/api/knowledge/ai/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          byok_provider: selectedProvider,
          byok_key: apiKeyInput.trim(),
        }),
      });

      const json = await res.json();
      if (!res.ok) {
        if (res.status === 402 || res.status === 403) {
          openPaywall({ featureName: "Bring Your Own Key (BYOK)" });
          return;
        }
        throw new Error(json.detail || "Failed to save BYOK configuration");
      }

      toast.success(`${selectedProvider.toUpperCase()} key connected securely!`);
      setApiKeyInput("");
      mutateSettings();
    } catch (e: any) {
      toast.error(e.message || "Failed to save API key");
    } finally {
      setIsSavingKey(false);
    }
  };

  const handleDisconnectKey = async () => {
    setIsSavingKey(true);
    try {
      const res = await fetchWithAuth("/api/knowledge/ai/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ remove_byok: true }),
      });

      if (!res.ok) throw new Error("Failed to disconnect key");

      toast.success("BYOK key disconnected. Reverted to Managed AI Gateway.");
      mutateSettings();
    } catch (e: any) {
      toast.error(e.message || "Failed to disconnect key");
    } finally {
      setIsSavingKey(false);
    }
  };

  // Metrics calculations
  const totalTokens = telemetry?.total_tokens || 0;
  const totalCost = telemetry?.total_cost || 0.0;
  const totalCalls = telemetry?.total_calls || 0;
  const monthlyBudget = telemetry?.monthly_token_budget || 2000000;
  const budgetPercent = Math.min(100, Math.round((totalTokens / monthlyBudget) * 100));

  const modelsList = settings?.available_models || [
    {
      id: "Auto-Route (Recommended)",
      name: "Elesium Adaptive Auto-Route",
      provider: "Elesium Neural Cluster (elesium.online)",
      description: "Dynamic routing per subtask (synthesis, scoring, drafting) for maximum deliverability & throughput.",
      is_pro: false,
      cost_in: "$0.10 - $0.35",
      cost_out: "$0.10 - $0.35",
      latency: "< 800ms",
      context_window: "32K",
    },
    {
      id: "DeepSeek V4 Pro",
      name: "DeepSeek-R1 Reasoning",
      provider: "DeepSeek",
      description: "Deep chain-of-thought mathematical and conversational reasoning for complex objections.",
      is_pro: true,
      cost_in: "$0.55",
      cost_out: "$2.19",
      latency: "1.2s - 2.5s",
      context_window: "64K",
    },
    {
      id: "Nemotron 120B",
      name: "NVIDIA Nemotron-4 340B",
      provider: "NVIDIA",
      description: "High-parameter enterprise sales synthesis and corporate persona alignment.",
      is_pro: true,
      cost_in: "$4.20",
      cost_out: "$4.20",
      latency: "900ms - 1.8s",
      context_window: "128K",
    },
    {
      id: "Llama-3.2 11B",
      name: "Meta Llama 3.2 11B Vision",
      provider: "Meta",
      description: "Ultra-low latency reasoning with vision and profile screenshot multi-modal comprehension.",
      is_pro: true,
      cost_in: "$0.16",
      cost_out: "$0.16",
      latency: "< 450ms",
      context_window: "128K",
    },
    {
      id: "GPT-OS",
      name: "OpenAI GPT-4o-Mini",
      provider: "OpenAI",
      description: "Industry-standard precision for structured JSON output and intent classification.",
      is_pro: true,
      cost_in: "$0.15",
      cost_out: "$0.60",
      latency: "600ms - 1.2s",
      context_window: "128K",
    },
    {
      id: "Kimi k3",
      name: "Moonshot Kimi K3 32K",
      provider: "Moonshot",
      description: "Ultra-long context window for digesting extensive corporate whitepapers and 10-K filings.",
      is_pro: true,
      cost_in: "$0.30",
      cost_out: "$0.30",
      latency: "1.0s - 2.0s",
      context_window: "32K",
    },
  ];

  const byokProviders = [
    { id: "openai", name: "OpenAI", prefix: "sk-...", desc: "GPT-4o, GPT-4o-mini" },
    { id: "anthropic", name: "Anthropic", prefix: "sk-ant-...", desc: "Claude 3.5 Sonnet / Haiku" },
    { id: "deepseek", name: "DeepSeek", prefix: "sk-...", desc: "DeepSeek-V3, DeepSeek-R1" },
    { id: "groq", name: "Groq LPU", prefix: "gsk_...", desc: "Llama-3.3 70B @ 300 t/s" },
    { id: "openrouter", name: "OpenRouter", prefix: "sk-or-...", desc: "Unified Multi-Provider Gateway" },
  ];

  return (
    <div className="space-y-8">
      {/* ─── SECTION 1: HEADER & LIVE KPI METER ──────────────────────────────── */}
      <div className="bg-white dark:bg-card/40 backdrop-blur-xl border border-slate-200 dark:border-border/50 rounded-[32px] p-6 lg:p-8 relative overflow-hidden shadow-sm">
        <div className="absolute top-0 right-0 w-80 h-80 -mr-20 -mt-20 rounded-full bg-indigo-500/10 blur-[80px] pointer-events-none" />

        <div className="relative z-10 space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center shadow-xs">
                <img src="/elesium-icon.png" alt="Elesium" className="w-7 h-7 object-contain" />
              </div>
              <div>
                <h2 className="text-xl font-bold tracking-tight text-foreground flex items-center gap-2">
                  Elesium AI Gateway & Model Orchestration
                  <a
                    href="https://elesium.online"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20 font-bold hover:underline"
                  >
                    elesium.online
                  </a>
                </h2>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Powered by Elesium Automation. Real-time compute telemetry, reasoning model selection, and zero-markup Bring-Your-Own-Key vault.
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2 self-start sm:self-auto">
              <button
                onClick={() => {
                  mutateSettings();
                  mutateTelemetry();
                  toast.success("Telemetry refreshed");
                }}
                className="p-2 rounded-xl border border-border/60 hover:bg-muted/50 text-muted-foreground hover:text-foreground transition-all"
                title="Refresh Telemetry"
              >
                <RefreshCw size={14} className={isTelemetryLoading ? "animate-spin" : ""} />
              </button>
            </div>
          </div>

          {/* ─── 4 KPI METERS ─── */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {/* KPI 1: Tokens */}
            <div className="p-4 rounded-2xl bg-slate-50 dark:bg-muted/20 border border-border/50 relative overflow-hidden">
              <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
                <span>Tokens Consumed</span>
                <Coins size={14} className="text-indigo-500" />
              </div>
              <div className="text-2xl font-bold font-mono tracking-tight text-foreground">
                {totalTokens.toLocaleString()}
              </div>
              <div className="mt-2.5">
                <div className="flex justify-between text-[10px] text-muted-foreground mb-1 font-mono">
                  <span>Quota: {budgetPercent}%</span>
                  <span>{(monthlyBudget / 1000000).toFixed(1)}M Limit</span>
                </div>
                <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-blue-600 to-cyan-500 rounded-full transition-all duration-500"
                    style={{ width: `${budgetPercent}%` }}
                  />
                </div>
              </div>
            </div>

            {/* KPI 2: Compute Cost */}
            <div className="p-4 rounded-2xl bg-slate-50 dark:bg-muted/20 border border-border/50 relative overflow-hidden">
              <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
                <span>Compute Cost</span>
                <Activity size={14} className="text-emerald-500" />
              </div>
              <div className="text-2xl font-bold font-mono tracking-tight text-emerald-600 dark:text-emerald-400">
                ${totalCost.toFixed(4)}
              </div>
              <div className="text-[11px] text-muted-foreground mt-2">
                Managed by Ele-in NIM Cluster
              </div>
            </div>

            {/* KPI 3: Invocations */}
            <div className="p-4 rounded-2xl bg-slate-50 dark:bg-muted/20 border border-border/50 relative overflow-hidden">
              <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
                <span>Invocations</span>
                <Gauge size={14} className="text-orange-500" />
              </div>
              <div className="text-2xl font-bold font-mono tracking-tight text-foreground">
                {totalCalls.toLocaleString()}
              </div>
              <div className="text-[11px] text-muted-foreground mt-2">
                Outreach & synthesis calls
              </div>
            </div>

            {/* KPI 4: Active Engine */}
            <div className="p-4 rounded-2xl bg-slate-50 dark:bg-muted/20 border border-border/50 relative overflow-hidden">
              <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
                <span>Active Engine</span>
                <Server size={14} className="text-blue-500" />
              </div>
              <div className="text-sm font-bold truncate text-foreground mt-1">
                {currentModel}
              </div>
              <div className="text-[11px] text-muted-foreground mt-2 flex items-center gap-1">
                {settings?.has_byok ? (
                  <span className="text-emerald-500 font-medium">BYOK Active</span>
                ) : (
                  <span>Managed NIM Cluster</span>
                )}
              </div>
            </div>
          </div>

          {/* Locked Telemetry Banner for Free Tier */}
          {!canViewTelemetry && (
            <div className="p-4 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex flex-col sm:flex-row items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-xl bg-amber-500/20 text-amber-600 dark:text-amber-400 shrink-0">
                  <Lock size={18} />
                </div>
                <div>
                  <h4 className="text-xs font-bold text-foreground">
                    Unlock Live AI Token Telemetry & Granular Cost Accounting
                  </h4>
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    Growth Pro unlocks real-time token tracking, prompt cost audit trails, and multi-model consumption heatmaps.
                  </p>
                </div>
              </div>
              <button
                onClick={() => openPaywall({ featureName: "AI Token Telemetry" })}
                className="px-4 py-2 rounded-xl text-xs font-semibold bg-amber-600 hover:bg-amber-500 text-white shadow-sm shrink-0 flex items-center gap-1.5 transition-all"
              >
                <span>Upgrade to Pro</span>
                <ArrowUpRight size={14} />
              </button>
            </div>
          )}
        </div>
      </div>

      {/* ─── SECTION 2: AI ROUTING ENGINE CARDS ──────────────────────────────── */}
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <h3 className="text-base font-bold text-foreground flex items-center gap-2">
              <Layers size={16} className="text-indigo-500" />
              Specialized Reasoning & Inference Engines
            </h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Select which foundational model powers your campaign messages, ICP scoring, and objection handling.
            </p>
          </div>
          {!canChooseModels && (
            <div className="flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-400 bg-amber-500/10 px-3 py-1 rounded-full border border-amber-500/20 self-start sm:self-auto font-medium">
              <Lock size={12} />
              <span>Specialized Models Locked (Pro)</span>
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {modelsList.map((m) => {
            const isSelected = currentModel === m.id;
            const isLocked = m.is_pro && !canChooseModels;
            const isUpdating = isUpdatingModel === m.id;

            return (
              <div
                key={m.id}
                onClick={() => handleSelectModel(m)}
                className={`p-5 rounded-2xl border transition-all cursor-pointer relative flex flex-col justify-between ${
                  isSelected
                    ? "bg-indigo-500/5 border-indigo-600 dark:border-indigo-500 ring-2 ring-indigo-500/20 shadow-md"
                    : "bg-white dark:bg-card/40 border-slate-200 dark:border-border/60 hover:border-slate-300 dark:hover:border-border hover:shadow-sm"
                }`}
              >
                <div>
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <div className="space-y-0.5">
                      <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-muted-foreground block">
                        {m.provider}
                      </span>
                      <h4 className="text-sm font-bold text-foreground flex items-center gap-1.5">
                        {m.name}
                        {isSelected && (
                          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                        )}
                      </h4>
                    </div>

                    <div className="flex items-center gap-1.5">
                      {isLocked ? (
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20 flex items-center gap-1">
                          <Lock size={10} /> Pro
                        </span>
                      ) : isSelected ? (
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-500/20 flex items-center gap-1">
                          <Check size={10} /> Active
                        </span>
                      ) : null}
                    </div>
                  </div>

                  <p className="text-xs text-muted-foreground leading-relaxed mb-4">
                    {m.description}
                  </p>
                </div>

                <div className="pt-3 border-t border-border/40 space-y-2">
                  <div className="grid grid-cols-3 gap-1 text-[10px] text-muted-foreground font-mono">
                    <div className="p-1.5 rounded-lg bg-slate-50 dark:bg-muted/30">
                      <span className="block text-[9px] uppercase tracking-wider text-muted-foreground/80">In / 1M</span>
                      <span className="font-semibold text-foreground">{m.cost_in}</span>
                    </div>
                    <div className="p-1.5 rounded-lg bg-slate-50 dark:bg-muted/30">
                      <span className="block text-[9px] uppercase tracking-wider text-muted-foreground/80">Out / 1M</span>
                      <span className="font-semibold text-foreground">{m.cost_out}</span>
                    </div>
                    <div className="p-1.5 rounded-lg bg-slate-50 dark:bg-muted/30">
                      <span className="block text-[9px] uppercase tracking-wider text-muted-foreground/80">Latency</span>
                      <span className="font-semibold text-foreground">{m.latency}</span>
                    </div>
                  </div>

                  <div className="flex items-center justify-between pt-1">
                    <span className="text-[10px] text-muted-foreground">
                      Context: <span className="font-mono font-medium text-foreground">{m.context_window}</span>
                    </span>
                    <button
                      type="button"
                      disabled={isUpdating}
                      className={`text-[11px] font-semibold px-2.5 py-1 rounded-lg transition-colors ${
                        isSelected
                          ? "bg-indigo-600 text-white"
                          : isLocked
                          ? "bg-muted text-muted-foreground hover:bg-muted/80"
                          : "bg-slate-100 dark:bg-muted hover:bg-slate-200 dark:hover:bg-muted/80 text-foreground"
                      }`}
                    >
                      {isUpdating ? "Switching..." : isSelected ? "Selected" : isLocked ? "Unlock Pro" : "Select"}
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ─── SECTION 3: BYOK (BRING YOUR OWN KEY) VAULT ─────────────────────── */}
      <div className="bg-white dark:bg-card/40 backdrop-blur-xl border border-slate-200 dark:border-border/50 rounded-[32px] p-6 lg:p-8 relative overflow-hidden shadow-sm">
        <div className="relative z-10 space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-500/20 border border-blue-100 dark:border-blue-500/30 flex items-center justify-center text-blue-600 dark:text-blue-400">
                <Key className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-foreground flex items-center gap-2">
                  Bring Your Own Key (BYOK) Vault
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20 font-bold">
                    Zero-Markup
                  </span>
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Route completions directly through your corporate API accounts (OpenAI, Anthropic, DeepSeek, Groq, OpenRouter).
                </p>
              </div>
            </div>

            {!canByok && (
              <span className="text-xs font-semibold text-amber-600 dark:text-amber-400 bg-amber-500/10 px-3 py-1 rounded-full border border-amber-500/20 flex items-center gap-1.5 self-start sm:self-auto">
                <Lock size={12} />
                Pro Feature
              </span>
            )}
          </div>

          {!canByok ? (
            /* Free Tier Locked Overlay Card */
            <div className="p-6 rounded-2xl bg-slate-50 dark:bg-muted/10 border border-border/60 flex flex-col sm:flex-row items-center justify-between gap-4">
              <div className="space-y-1 text-center sm:text-left">
                <h4 className="text-sm font-bold text-foreground">
                  Connect Direct LLM Provider Keys
                </h4>
                <p className="text-xs text-muted-foreground max-w-xl leading-relaxed">
                  Avoid platform token surcharges by streaming prompts directly from your corporate OpenAI or Anthropic quotas. Includes automated failover to Ele-in NIM clusters during provider downtime.
                </p>
              </div>
              <button
                onClick={() => openPaywall({ featureName: "Bring Your Own Key (BYOK)" })}
                className="px-5 py-2.5 rounded-xl text-xs font-semibold bg-primary text-primary-foreground hover:bg-primary/90 shadow-md shrink-0 flex items-center gap-2 transition-all"
              >
                <span>Upgrade to Growth Pro</span>
                <ArrowUpRight size={14} />
              </button>
            </div>
          ) : (
            /* Pro Unlocked BYOK Management */
            <div className="space-y-6">
              {/* Connected Key Banner */}
              {settings?.has_byok && (
                <div className="p-4 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className="p-2 rounded-xl bg-emerald-500/20 text-emerald-600 dark:text-emerald-400">
                      <ShieldCheck size={18} />
                    </div>
                    <div>
                      <span className="text-xs font-bold text-foreground flex items-center gap-2">
                        Connected: {settings.byok_provider?.toUpperCase()}
                        <span className="text-[10px] font-mono px-2 py-0.2 rounded bg-emerald-500/20 text-emerald-600 dark:text-emerald-400">
                          Active
                        </span>
                      </span>
                      <p className="text-xs font-mono text-muted-foreground mt-0.5">
                        {settings.byok_key_masked}
                      </p>
                    </div>
                  </div>

                  <button
                    onClick={handleDisconnectKey}
                    disabled={isSavingKey}
                    className="text-xs font-semibold px-3 py-1.5 rounded-lg border border-rose-500/30 text-rose-600 dark:text-rose-400 hover:bg-rose-500/10 transition-colors flex items-center gap-1.5"
                  >
                    <Trash2 size={13} />
                    <span>Disconnect Key</span>
                  </button>
                </div>
              )}

              {/* Provider Selector Tabs */}
              <div>
                <label className="block text-xs font-semibold text-foreground mb-2">
                  Select Provider
                </label>
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
                  {byokProviders.map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => setSelectedProvider(p.id)}
                      className={`p-3 rounded-xl border text-left transition-all ${
                        selectedProvider === p.id
                          ? "bg-blue-500/10 border-blue-500 text-blue-900 dark:text-blue-200 shadow-xs"
                          : "bg-slate-50 dark:bg-muted/20 border-border/50 hover:bg-slate-100 dark:hover:bg-muted/40 text-foreground"
                      }`}
                    >
                      <span className="block text-xs font-bold">{p.name}</span>
                      <span className="text-[10px] text-muted-foreground truncate block mt-0.5">
                        {p.desc}
                      </span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Key Input Form */}
              <div className="space-y-3">
                <label className="block text-xs font-semibold text-foreground">
                  {selectedProvider.toUpperCase()} API Key
                </label>
                <div className="relative">
                  <input
                    type={showKeyText ? "text" : "password"}
                    value={apiKeyInput}
                    onChange={(e) => setApiKeyInput(e.target.value)}
                    placeholder={`Paste key (${byokProviders.find(p => p.id === selectedProvider)?.prefix})`}
                    className="w-full rounded-xl bg-card border border-border px-3.5 py-2.5 text-xs font-mono text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-blue-600 pr-20"
                  />
                  <button
                    type="button"
                    onClick={() => setShowKeyText(!showKeyText)}
                    className="absolute right-3 top-2.5 text-muted-foreground hover:text-foreground text-xs"
                  >
                    {showKeyText ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>

                <div className="flex items-center gap-2 pt-1">
                  <button
                    type="button"
                    onClick={handleTestKey}
                    disabled={isTestingKey || !apiKeyInput.trim()}
                    className="px-3.5 py-2 rounded-xl text-xs font-semibold border border-border hover:bg-muted transition-colors disabled:opacity-50"
                  >
                    {isTestingKey ? "Testing..." : "Test Format"}
                  </button>

                  <button
                    type="button"
                    onClick={handleSaveKey}
                    disabled={isSavingKey || !apiKeyInput.trim()}
                    className="px-4 py-2 rounded-xl text-xs font-semibold bg-blue-600 hover:bg-blue-500 text-white transition-colors disabled:opacity-50 shadow-sm"
                  >
                    {isSavingKey ? "Saving..." : "Save Key to Vault"}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ─── SECTION 4: RECENT GENERATION AUDIT LOG (Pro) ────────────────────── */}
      {canViewTelemetry && telemetry?.recent_generations && telemetry.recent_generations.length > 0 && (
        <div className="bg-white dark:bg-card/40 backdrop-blur-xl border border-slate-200 dark:border-border/50 rounded-[32px] p-6 lg:p-8 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-sm font-bold text-foreground flex items-center gap-2">
                <Clock size={16} className="text-indigo-500" />
                Recent AI Generation Invocations
              </h3>
              <p className="text-xs text-muted-foreground mt-0.5">
                Audit trail of latest outreach messages and reasoning inferences.
              </p>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-border/50 text-muted-foreground">
                  <th className="pb-2.5 font-medium">Timestamp</th>
                  <th className="pb-2.5 font-medium">Model</th>
                  <th className="pb-2.5 font-medium">Tokens</th>
                  <th className="pb-2.5 font-medium">Cost</th>
                  <th className="pb-2.5 font-medium">Preview</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/30 font-mono">
                {telemetry.recent_generations.slice(0, 8).map((gen) => (
                  <tr key={gen.id} className="hover:bg-muted/20 transition-colors">
                    <td className="py-2.5 text-muted-foreground text-[11px]">
                      {new Date(gen.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                    </td>
                    <td className="py-2.5 font-semibold text-foreground text-[11px] truncate max-w-[140px]">
                      {gen.model}
                    </td>
                    <td className="py-2.5 text-foreground text-[11px]">
                      {gen.tokens_used}
                    </td>
                    <td className="py-2.5 text-emerald-600 dark:text-emerald-400 text-[11px]">
                      ${gen.cost.toFixed(5)}
                    </td>
                    <td className="py-2.5 font-sans text-muted-foreground text-[11px] truncate max-w-[280px]">
                      {gen.output_preview || gen.prompt_preview || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
