import { useState } from "react";
import {
  Key,
  Lock,
  ArrowUpRight,
  Check,
  RefreshCw,
  Coins,
  Server,
  Eye,
  EyeOff,
  Trash2,
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
    if (!apiKeyInput.trim()) return toast.error("Please enter an API key");
    setIsTestingKey(true);
    try {
      const res = await fetchWithAuth("/api/knowledge/ai/byok/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: selectedProvider, api_key: apiKeyInput.trim() }),
      });
      const data = await res.json();
      if (res.ok && data.status === "valid") {
        toast.success(`Key syntax validated for ${selectedProvider.toUpperCase()}`);
      } else {
        toast.error(data.detail || "Key validation failed");
      }
    } catch (e: any) {
      toast.error(e.message || "Failed to validate key");
    } finally {
      setIsTestingKey(false);
    }
  };

  const handleSaveKey = async () => {
    if (!apiKeyInput.trim()) return toast.error("Please enter an API key");
    if (!canByok) {
      openPaywall({ featureName: "Bring Your Own Key (BYOK)" });
      return;
    }
    setIsSavingKey(true);
    try {
      const res = await fetchWithAuth("/api/knowledge/ai/byok", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: selectedProvider, api_key: apiKeyInput.trim() }),
      });
      if (res.ok) {
        toast.success(`Connected ${selectedProvider.toUpperCase()} key to secure vault`);
        setApiKeyInput("");
        mutateSettings();
      } else {
        const data = await res.json().catch(() => ({}));
        toast.error(data.detail || "Failed to save key");
      }
    } catch (e: any) {
      toast.error(e.message || "Failed to connect key");
    } finally {
      setIsSavingKey(false);
    }
  };

  const handleDisconnectKey = async () => {
    if (!window.confirm("Disconnect your BYOK key? Outreach will route back through managed NIM clusters.")) return;
    setIsSavingKey(true);
    try {
      const res = await fetchWithAuth("/api/knowledge/ai/byok", {
        method: "DELETE",
      });
      if (res.ok) {
        toast.success("BYOK key disconnected");
        mutateSettings();
      } else {
        toast.error("Failed to disconnect key");
      }
    } catch (e: any) {
      toast.error(e.message || "Error disconnecting key");
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
      provider: "Elesium Neural Cluster",
      description: "Balanced & fast. Automatically routes each task to the most cost-effective model for high reply rates.",
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
      description: "Best for objections. Deep chain-of-thought logic to overcome skeptical prospects and technical hurdles.",
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
      description: "Best for enterprise sales. High-parameter corporate persona alignment and C-level outreach.",
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
      description: "Ultra-fast & economical. Ideal for high-speed initial connection requests and profile analysis.",
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
      description: "High precision. Reliable structured data extraction, title normalization, and clean messaging.",
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
      description: "Long-document reader. Best for scanning massive 50-page annual reports, pitch decks, and 10-K filings.",
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
    { id: "openrouter", name: "OpenRouter", prefix: "sk-or-...", desc: "Unified Multi-Provider" },
  ];

  return (
    <div className="space-y-6">
      {/* ─── SECTION 1: HEADER & LIVE KPI METER ──────────────────────────────── */}
      <div className="bg-card/40 border border-border/50 rounded-xl p-6 lg:p-7 relative overflow-hidden">
        <div className="space-y-5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-muted/60 border border-border/40 flex items-center justify-center text-foreground/80 shadow-2xs">
                <img src="/elesium-icon.png" alt="Elesium" className="w-4 h-4 object-contain" />
              </div>
              <div>
                <h3 className="text-sm font-medium tracking-tight text-foreground flex items-center gap-2">
                  AI Models &amp; API Cost Control
                  <span className="text-[11px] text-muted-foreground font-normal">(elesium.online)</span>
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Select your active AI models, audit compute spend down to the penny, or connect your own API key for zero-markup wholesale pricing.
                </p>
              </div>
            </div>

            <button
              type="button"
              onClick={() => {
                mutateSettings();
                mutateTelemetry();
                toast.success("Telemetry refreshed");
              }}
              className="w-8 h-8 rounded-lg border border-border/50 bg-card hover:bg-muted/50 text-muted-foreground hover:text-foreground flex items-center justify-center transition-colors cursor-pointer self-start sm:self-auto"
              title="Refresh Telemetry"
            >
              <RefreshCw size={13} className={isTelemetryLoading ? "animate-spin" : ""} />
            </button>
          </div>

          {/* ─── 4 KPI METERS ─── */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {/* KPI 1: Tokens */}
            <div className="p-3.5 rounded-xl bg-card/60 border border-border/50 shadow-2xs">
              <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
                <span className="text-[10px] uppercase font-medium tracking-wider">Words Processed</span>
                <Coins size={13} className="text-muted-foreground" />
              </div>
              <div className="text-xl font-mono font-medium tracking-tight text-foreground">
                {totalTokens.toLocaleString()}
              </div>
              <div className="mt-2">
                <div className="flex justify-between text-[10px] text-muted-foreground mb-1 font-mono">
                  <span>Usage: {budgetPercent}%</span>
                  <span>{(monthlyBudget / 1000000).toFixed(1)}M Token Cap</span>
                </div>
                <div className="h-1.5 w-full bg-muted/60 rounded-full overflow-hidden border border-border/40">
                  <div
                    className="h-full bg-foreground rounded-full transition-all duration-500"
                    style={{ width: `${budgetPercent}%` }}
                  />
                </div>
              </div>
            </div>

            {/* KPI 2: Compute Cost */}
            <div className="p-3.5 rounded-xl bg-card/60 border border-border/50 shadow-2xs">
              <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
                <span className="text-[10px] uppercase font-medium tracking-wider">Compute Spend</span>
                <Activity size={13} className="text-muted-foreground" />
              </div>
              <div className="text-xl font-mono font-medium tracking-tight text-foreground">
                ${totalCost.toFixed(4)}
              </div>
              <div className="text-[11px] text-muted-foreground mt-2">
                Real-time API tracking
              </div>
            </div>

            {/* KPI 3: Invocations */}
            <div className="p-3.5 rounded-xl bg-card/60 border border-border/50 shadow-2xs">
              <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
                <span className="text-[10px] uppercase font-medium tracking-wider">Outreach Runs</span>
                <Gauge size={13} className="text-muted-foreground" />
              </div>
              <div className="text-xl font-mono font-medium tracking-tight text-foreground">
                {totalCalls.toLocaleString()}
              </div>
              <div className="text-[11px] text-muted-foreground mt-2">
                Drafts, research &amp; replies
              </div>
            </div>

            {/* KPI 4: Active Engine */}
            <div className="p-3.5 rounded-xl bg-card/60 border border-border/50 shadow-2xs">
              <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
                <span className="text-[10px] uppercase font-medium tracking-wider">Active Engine</span>
                <Server size={13} className="text-muted-foreground" />
              </div>
              <div className="text-xs font-medium truncate text-foreground mt-1">
                {currentModel}
              </div>
              <div className="text-[11px] text-muted-foreground mt-2">
                {settings?.has_byok ? "Wholesale BYOK Active" : "Managed Cloud Cluster"}
              </div>
            </div>
          </div>

          {/* Locked Telemetry Banner for Free Tier */}
          {!canViewTelemetry && (
            <div className="p-4 rounded-xl bg-card/40 border border-border/50 flex flex-col sm:flex-row items-center justify-between gap-3">
              <div className="flex items-center gap-2.5">
                <div className="w-7 h-7 rounded-lg bg-muted/60 border border-border/40 flex items-center justify-center text-muted-foreground shrink-0">
                  <Lock size={13} />
                </div>
                <div>
                  <h4 className="text-xs font-medium text-foreground">
                    Live AI Cost Auditing &amp; Telemetry
                  </h4>
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    Growth Pro unlocks real-time token tracking down to a fraction of a cent, prompt cost audit trails, and multi-model routing.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => openPaywall({ featureName: "AI Token Telemetry" })}
                className="px-3.5 py-1.5 rounded-lg text-xs font-medium bg-foreground text-background hover:bg-foreground/90 shadow-2xs shrink-0 flex items-center gap-1.5 transition-all cursor-pointer"
              >
                <span>Upgrade to Pro</span>
                <ArrowUpRight size={13} />
              </button>
            </div>
          )}
        </div>
      </div>

      {/* ─── SECTION 2: AI ROUTING ENGINE CARDS ──────────────────────────────── */}
      <div className="space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <h3 className="text-xs font-medium text-foreground tracking-tight flex items-center gap-1.5">
              <Layers size={14} className="text-muted-foreground" />
              Specialized AI Models
            </h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Choose the intelligence level for your outreach. Use fast, low-cost models for initial messages, or deep-reasoning models (DeepSeek-R1) for complex objections.
            </p>
          </div>
          {!canChooseModels && (
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground bg-muted/40 px-2.5 py-1 rounded-md border border-border/40 self-start sm:self-auto font-medium">
              <Lock size={11} />
              <span>Specialized Models (Pro)</span>
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
          {modelsList.map((m) => {
            const isSelected = currentModel === m.id;
            const isLocked = m.is_pro && !canChooseModels;
            const isUpdating = isUpdatingModel === m.id;

            return (
              <div
                key={m.id}
                role="button"
                tabIndex={0}
                onClick={() => handleSelectModel(m)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    handleSelectModel(m);
                  }
                }}
                className={`p-4 rounded-xl border transition-all cursor-pointer relative flex flex-col justify-between shadow-2xs ${
                  isSelected
                    ? "bg-card border-border shadow-xs ring-1 ring-border"
                    : "bg-card/40 border-border/50 hover:bg-card/70 hover:border-border/80"
                }`}
              >
                <div>
                  <div className="flex items-start justify-between gap-2 mb-1.5">
                    <div className="space-y-0.5">
                      <span className="text-[10px] font-mono font-medium uppercase tracking-wider text-muted-foreground block">
                        {m.provider}
                      </span>
                      <h4 className="text-xs font-medium text-foreground flex items-center gap-1.5">
                        {m.name}
                        {isSelected && (
                          <span className="w-1.5 h-1.5 rounded-full bg-foreground" />
                        )}
                      </h4>
                    </div>

                    <div className="flex items-center gap-1.5 shrink-0">
                      {isLocked ? (
                        <span className="text-[10px] font-medium px-2 py-0.5 rounded-md bg-muted text-muted-foreground border border-border/40 flex items-center gap-1">
                          <Lock size={10} /> Pro
                        </span>
                      ) : isSelected ? (
                        <span className="text-[10px] font-medium px-2 py-0.5 rounded-md bg-muted text-foreground border border-border/50 flex items-center gap-1">
                          <Check size={10} /> Active
                        </span>
                      ) : null}
                    </div>
                  </div>

                  <p className="text-xs text-muted-foreground leading-relaxed mb-3 line-clamp-2">
                    {m.description}
                  </p>
                </div>

                <div className="pt-2.5 border-t border-border/40 space-y-2">
                  <div className="grid grid-cols-3 gap-1 text-[10px] text-muted-foreground font-mono">
                    <div className="p-1.5 rounded-md bg-muted/20 border border-border/30">
                      <span className="block text-[9px] uppercase tracking-wider text-muted-foreground/80">In / 1M</span>
                      <span className="font-normal text-foreground">{m.cost_in}</span>
                    </div>
                    <div className="p-1.5 rounded-md bg-muted/20 border border-border/30">
                      <span className="block text-[9px] uppercase tracking-wider text-muted-foreground/80">Out / 1M</span>
                      <span className="font-normal text-foreground">{m.cost_out}</span>
                    </div>
                    <div className="p-1.5 rounded-md bg-muted/20 border border-border/30">
                      <span className="block text-[9px] uppercase tracking-wider text-muted-foreground/80">Latency</span>
                      <span className="font-normal text-foreground">{m.latency}</span>
                    </div>
                  </div>

                  <div className="flex items-center justify-between pt-0.5">
                    <span className="text-[10px] text-muted-foreground">
                      Context: <span className="font-mono text-foreground">{m.context_window}</span>
                    </span>
                    <button
                      type="button"
                      disabled={isUpdating}
                      className={`text-[11px] font-medium px-2.5 py-1 rounded-md transition-colors cursor-pointer ${
                        isSelected
                          ? "bg-foreground text-background"
                          : isLocked
                          ? "bg-muted/40 text-muted-foreground hover:bg-muted/60"
                          : "bg-muted/40 hover:bg-muted text-foreground border border-border/40"
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
      <div className="bg-card/40 border border-border/50 rounded-xl p-6 lg:p-7 relative overflow-hidden">
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-muted/60 border border-border/40 flex items-center justify-center text-foreground/80 shadow-2xs">
                <Key className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-xs font-medium text-foreground tracking-tight flex items-center gap-2">
                  Bring Your Own Key (BYOK) — Wholesale Pricing
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded-md bg-muted text-muted-foreground border border-border/40">
                    Zero-Markup
                  </span>
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Connect your OpenAI, Anthropic, or DeepSeek API keys to pay raw provider rates with $0.00 platform markup.
                </p>
              </div>
            </div>

            {!canByok && (
              <span className="text-[10px] font-medium text-muted-foreground bg-muted/40 px-2.5 py-0.5 rounded-md border border-border/40 flex items-center gap-1 self-start sm:self-auto">
                <Lock size={10} />
                Pro Feature
              </span>
            )}
          </div>

          {!canByok ? (
            /* Free Tier Locked Overlay Card */
            <div className="p-5 rounded-xl bg-card/60 border border-border/50 flex flex-col sm:flex-row items-center justify-between gap-4">
              <div className="space-y-0.5 text-center sm:text-left">
                <h4 className="text-xs font-medium text-foreground">
                  Wholesale API Keys (Zero-Markup)
                </h4>
                <p className="text-xs text-muted-foreground max-w-xl leading-relaxed">
                  Pay LLM providers directly at wholesale prices with $0.00 platform markup. Save up to 80% on high-volume outbound campaigns and get dedicated enterprise rate limits.
                </p>
              </div>
              <button
                type="button"
                onClick={() => openPaywall({ featureName: "Bring Your Own Key (BYOK)" })}
                className="px-3.5 py-1.5 rounded-lg text-xs font-medium bg-foreground text-background hover:bg-foreground/90 shadow-2xs shrink-0 flex items-center gap-1.5 transition-all cursor-pointer"
              >
                <span>Upgrade to Pro</span>
                <ArrowUpRight size={13} />
              </button>
            </div>
          ) : (
            /* Pro Unlocked BYOK Management */
            <div className="space-y-4">
              {/* Connected Key Banner */}
              {settings?.has_byok && (
                <div className="p-3.5 rounded-xl bg-card/60 border border-border/50 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                  <div className="flex items-center gap-2.5">
                    <div className="w-6 h-6 rounded-md bg-muted/60 border border-border/40 flex items-center justify-center text-foreground">
                      <Check size={13} />
                    </div>
                    <div>
                      <span className="text-xs font-medium text-foreground flex items-center gap-2">
                        Connected: {settings.byok_provider?.toUpperCase()}
                        <span className="text-[10px] font-mono px-1.5 py-0.2 rounded-md bg-muted text-muted-foreground border border-border/40">
                          Active
                        </span>
                      </span>
                      <p className="text-[11px] font-mono text-muted-foreground mt-0.5">
                        {settings.byok_key_masked}
                      </p>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={handleDisconnectKey}
                    disabled={isSavingKey}
                    className="text-xs font-medium px-2.5 py-1 rounded-md border border-border/50 text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors flex items-center gap-1.5 cursor-pointer"
                  >
                    <Trash2 size={12} />
                    <span>Disconnect</span>
                  </button>
                </div>
              )}

              {/* Provider Selector Tabs */}
              <div>
                <label className="block text-[11px] font-medium text-muted-foreground mb-1.5">
                  Select Provider
                </label>
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
                  {byokProviders.map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => setSelectedProvider(p.id)}
                      className={`p-2.5 rounded-lg border text-left transition-all cursor-pointer ${
                        selectedProvider === p.id
                          ? "bg-card border-border text-foreground shadow-2xs"
                          : "bg-muted/20 border-border/40 hover:bg-muted/40 text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      <span className="block text-xs font-medium">{p.name}</span>
                      <span className="text-[10px] text-muted-foreground truncate block mt-0.5">
                        {p.desc}
                      </span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Key Input Form */}
              <div className="space-y-2">
                <label className="block text-[11px] font-medium text-foreground">
                  {selectedProvider.toUpperCase()} API Key
                </label>
                <div className="relative">
                  <input
                    type={showKeyText ? "text" : "password"}
                    value={apiKeyInput}
                    onChange={(e) => setApiKeyInput(e.target.value)}
                    placeholder={`Paste key (${byokProviders.find(p => p.id === selectedProvider)?.prefix})`}
                    className="w-full rounded-lg bg-background border border-border/60 px-3 py-2 text-xs font-mono text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-border focus:ring-1 focus:ring-ring pr-16"
                  />
                  <button
                    type="button"
                    onClick={() => setShowKeyText(!showKeyText)}
                    className="absolute right-2.5 top-2 text-muted-foreground hover:text-foreground text-xs cursor-pointer"
                  >
                    {showKeyText ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>

                <div className="flex items-center gap-2 pt-1">
                  <button
                    type="button"
                    onClick={handleTestKey}
                    disabled={isTestingKey || !apiKeyInput.trim()}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium border border-border/60 hover:bg-muted text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50 cursor-pointer"
                  >
                    {isTestingKey ? "Testing..." : "Test Format"}
                  </button>

                  <button
                    type="button"
                    onClick={handleSaveKey}
                    disabled={isSavingKey || !apiKeyInput.trim()}
                    className="px-3.5 py-1.5 rounded-lg text-xs font-medium bg-foreground text-background hover:bg-foreground/90 transition-colors disabled:opacity-50 shadow-2xs cursor-pointer"
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
        <div className="bg-card/40 border border-border/50 rounded-xl p-5 shadow-2xs">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h3 className="text-xs font-medium text-foreground tracking-tight flex items-center gap-1.5">
                <Clock size={13} className="text-muted-foreground" />
                Recent AI Generation Invocations
              </h3>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                Audit trail of latest outreach messages and inferences.
              </p>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-border/40 text-muted-foreground text-[10px] uppercase font-medium">
                  <th className="pb-2">Timestamp</th>
                  <th className="pb-2">Model</th>
                  <th className="pb-2">Tokens</th>
                  <th className="pb-2">Cost</th>
                  <th className="pb-2">Preview</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/20 font-mono text-[11px]">
                {telemetry.recent_generations.slice(0, 8).map((gen) => (
                  <tr key={gen.id} className="hover:bg-muted/20 transition-colors">
                    <td className="py-2 text-muted-foreground">
                      {new Date(gen.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                    </td>
                    <td className="py-2 font-medium text-foreground truncate max-w-[140px]">
                      {gen.model}
                    </td>
                    <td className="py-2 text-foreground">
                      {gen.tokens_used}
                    </td>
                    <td className="py-2 text-foreground">
                      ${gen.cost.toFixed(5)}
                    </td>
                    <td className="py-2 font-sans text-muted-foreground truncate max-w-[280px]">
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
