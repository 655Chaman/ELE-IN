import { useState } from "react"
import useSWR from "swr"
import { fetcher, fetchWithAuth } from "@/lib/apiClient"
import { Shield, TrendingUp, Lock, Zap, Gauge, Sparkles } from "lucide-react"
import { cn } from "@/lib/utils"
import { usePaywall } from "@/contexts/PaywallContext"
import { toast } from "sonner"

// ── Warmup Timeline Card ──────────────────────────────────────────────────────
const PHASE_COLORS: Record<string, string> = {
  observe: "bg-zinc-600",
  seed: "bg-amber-500",
  ramp: "bg-primary",
  cruise: "bg-emerald-500",
  active: "bg-emerald-500",
}
const PHASE_LABELS: Record<string, string> = {
  observe: "Observing", seed: "Seeding", ramp: "Ramping", cruise: "Full Cruise", active: "Active"
}

export default function WarmupTimeline({ accountId }: { accountId: string }) {
  const { data, mutate } = useSWR(
    `/api/elein/accounts/${accountId}/warmup`, fetcher,
    { refreshInterval: 60000 }
  )

  const { data: billing } = useSWR<{ plan?: string; tier?: string; tier_limits?: { can_advanced_warmup?: boolean } }>(
    '/api/elein/workspaces/billing',
    fetcher
  )
  const { openPaywall } = usePaywall()
  const isAdvancedWarmupLocked = Boolean(billing && !billing.tier_limits?.can_advanced_warmup)
  const [updatingCurve, setUpdatingCurve] = useState(false)

  if (!data) return null

  const phases = data.phases || []
  const currentPhase = data.phase || 'observe'
  const safety = data.safety_score ?? 100
  const safetyColor = safety >= 80 ? 'text-emerald-500' : safety >= 50 ? 'text-amber-500' : 'text-destructive'
  const isActivePhase = currentPhase === 'active'
  const targetDays = data.target_days || 14

  const handleSelectCurve = async (curveDays: number) => {
    if (curveDays === targetDays) return
    if (isAdvancedWarmupLocked && (curveDays === 7 || curveDays === 30)) {
      openPaywall({ featureName: "Multi-Step Warmup Curves & Telemetry Auto-Throttling" })
      return
    }

    setUpdatingCurve(true)
    try {
      const res = await fetchWithAuth(`/api/elein/accounts/${accountId}/warmup-curve`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ curve_days: curveDays })
      })
      if (!res.ok) {
        const err = await res.text()
        throw new Error(err || "Failed to update warmup curve")
      }
      toast.success(`Warmup schedule updated to ${curveDays}-day curve`)
      mutate()
    } catch (e: any) {
      toast.error(e?.message || "Failed to update curve")
    } finally {
      setUpdatingCurve(false)
    }
  }

  return (
    <div className="mt-3 p-3.5 rounded-xl bg-background/50 border border-border/60 space-y-3 font-sans">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isActivePhase ? (
             <Shield size={13} className="text-emerald-500" />
          ) : (
             <TrendingUp size={13} className="text-primary" />
          )}
          <span className="text-xs font-bold text-foreground">
             {isActivePhase ? "Account Active" : `Warmup — Day ${data.day || 1} of ${targetDays}`}
          </span>
          {!isActivePhase && (
            <span className={cn('text-[10px] font-bold px-1.5 py-0.5 rounded',
              PHASE_COLORS[currentPhase] || 'bg-gray-500', 'text-white')}>
              {PHASE_LABELS[currentPhase] || currentPhase}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <Shield size={12} className={safetyColor} />
          <span className={cn('text-xs font-bold', safetyColor)}>{safety}% safe</span>
        </div>
      </div>

      {/* Warmup Curve Selection Ramp */}
      {!isActivePhase && (
        <div className="space-y-1.5 pt-1">
          <div className="flex items-center justify-between text-[11px] text-muted-foreground font-semibold">
            <span className="flex items-center gap-1">
              <Gauge size={12} className="text-primary" />
              Warmup Curve Profile:
            </span>
            <span className="text-[10px] uppercase font-bold text-muted-foreground/80">
              {targetDays}d Active
            </span>
          </div>

          <div className="grid grid-cols-3 gap-2">
            {[
              { days: 7, label: "7d Accelerated", tag: "Fast", isPro: true, icon: Zap },
              { days: 14, label: "14d Balanced", tag: "Safe Baseline", isPro: false, icon: Shield },
              { days: 30, label: "30d Enterprise", tag: "Zero-Risk", isPro: true, icon: Sparkles },
            ].map(curve => {
              const isSelected = targetDays === curve.days
              const Icon = curve.icon
              return (
                <button
                  key={curve.days}
                  type="button"
                  disabled={updatingCurve}
                  onClick={() => handleSelectCurve(curve.days)}
                  className={cn(
                    "p-2 rounded-lg border text-left transition-all cursor-pointer relative",
                    isSelected
                      ? "border-primary bg-primary/10 shadow-xs"
                      : "border-border/60 bg-card/60 hover:border-primary/40 hover:bg-muted/40",
                    isAdvancedWarmupLocked && curve.isPro && "opacity-90"
                  )}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[10px] font-bold text-foreground flex items-center gap-1">
                      <Icon size={10} className={isSelected ? "text-primary" : "text-muted-foreground"} />
                      {curve.days}d Ramp
                    </span>
                    {isAdvancedWarmupLocked && curve.isPro ? (
                      <span className="flex items-center gap-0.5 text-[9px] font-extrabold text-amber-600 bg-amber-500/10 px-1 py-0.2 rounded border border-amber-500/20">
                        <Lock size={8} /> Pro
                      </span>
                    ) : isSelected ? (
                      <span className="w-1.5 h-1.5 rounded-full bg-primary" />
                    ) : null}
                  </div>
                  <p className="text-[9px] text-muted-foreground leading-tight truncate">{curve.tag}</p>
                </button>
              )
            })}
          </div>
        </div>
      )}

      {!isActivePhase && (
         <p className="text-[11px] text-muted-foreground/90 italic leading-relaxed">
            Here's why we're sending slowly: To protect your account from shadow-bans, volume scales gradually across the {targetDays}-day safety curve.
         </p>
      )}

      {!isActivePhase && phases.length > 0 && (
        <div className="flex gap-1 h-2">
          {phases.map((p: any, i: number) => {
            const isActive = p.status === 'current' || p.id === currentPhase
            const isPast = p.status === 'completed'
            return (
              <div 
                key={p.id || p.name || i} 
                title={`${p.label || p.name}: ${p.status || ''}`}
                className={cn(
                  'flex-1 rounded-full transition-all',
                  isActive ? (PHASE_COLORS[p.id || p.name] || 'bg-primary') : isPast ? 'bg-primary/50' : 'bg-muted'
                )} 
              />
            )
          })}
        </div>
      )}

      {/* Telemetry Auto-Throttling Badge & Daily Limits */}
      <div className="pt-2 border-t border-border/40 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-[11px]">
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground font-medium">
            Limit: <strong className="text-foreground">{data.daily_limit === 0 ? 'Observe only' : `${data.daily_limit}/day`}</strong>
          </span>
          <span className="text-muted-foreground/40">•</span>
          <span className="text-muted-foreground truncate max-w-[160px]" title={(data.allowed_actions || []).join(' · ')}>
            {(data.allowed_actions || []).join(' · ')}
          </span>
        </div>

        {/* Telemetry Auto-Throttle Status */}
        {data.telemetry_auto_throttle ? (
          <div className="flex items-center gap-1.5 text-[10px] font-bold text-emerald-600 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20 self-start sm:self-auto" title="Autonomous Telemetry Throttle: Volume dynamically reduces if acceptance drops < 20%">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            <span>Telemetry Auto-Throttle Active</span>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => openPaywall({ featureName: "Autonomous Telemetry Auto-Throttling" })}
            className="flex items-center gap-1 text-[10px] font-bold text-amber-600 bg-amber-500/10 hover:bg-amber-500/20 px-2 py-0.5 rounded-full border border-amber-500/20 transition-all cursor-pointer self-start sm:self-auto"
            title="Static limits active. Upgrade to Growth Pro for AI safety telemetry auto-throttling."
          >
            <Lock size={9} />
            <span>Auto-Throttle (Pro)</span>
          </button>
        )}
      </div>
    </div>
  )
}
