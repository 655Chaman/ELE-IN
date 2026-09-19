import useSWR from "swr"
import { fetcher } from "@/lib/apiClient"
import { Shield, TrendingUp } from "lucide-react"
import { cn } from "@/lib/utils"

// ── Warmup Timeline Card ──────────────────────────────────────────────────────
const PHASE_COLORS: Record<string, string> = {
  observe: "bg-zinc-600",
  seed: "bg-amber-600",
  ramp: "bg-blue-600",
  cruise: "bg-emerald-600",
  active: "bg-emerald-500",
}
const PHASE_LABELS: Record<string, string> = {
  observe: "Observing", seed: "Seeding", ramp: "Ramping", cruise: "Full Cruise", active: "Active"
}

export default function WarmupTimeline({ accountId }: { accountId: string }) {
  const { data } = useSWR(
    `/api/elein/accounts/${accountId}/warmup`, fetcher,
    { refreshInterval: 60000 }
  )
  if (!data) return null

  const phases = data.phases || []
  const currentPhase = data.phase || 'observe'
  const safety = data.safety_score ?? 100
  const safetyColor = safety >= 80 ? 'text-emerald-400' : safety >= 50 ? 'text-amber-400' : 'text-red-400'
  const isActivePhase = currentPhase === 'active'

  return (
    <div className="mt-3 p-3 rounded-lg bg-background/40 border border-border/50 backdrop-blur-sm space-y-2.5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isActivePhase ? (
             <Shield size={11} className="text-emerald-500" />
          ) : (
             <TrendingUp size={11} className="text-muted-foreground" />
          )}
          <span className="text-[11px] font-semibold text-muted-foreground">
             {isActivePhase ? "Account Active" : `Warmup — Day ${data.day} of 14`}
          </span>
          {!isActivePhase && (
            <span className={cn('text-[10px] font-bold px-1.5 py-0.5 rounded',
              PHASE_COLORS[currentPhase] || 'bg-gray-500', 'text-white')}>
              {PHASE_LABELS[currentPhase] || currentPhase}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <Shield size={10} className={safetyColor} />
          <span className={cn('text-[10px] font-bold', safetyColor)}>{safety}% safe</span>
        </div>
      </div>
      {!isActivePhase && (
         <p className="text-[10px] text-muted-foreground italic mb-2">
            Here's why we're sending slowly: To protect your account from shadow-bans, we gradually ramp up volume over 14 days.
         </p>
      )}
      {!isActivePhase && phases.length > 0 && (
        <div className="flex gap-1 h-1.5">
          {phases.map((p: any, i: number) => {
            const isActive = p.name === currentPhase
            const isPast = phases.findIndex((x: any) => x.name === currentPhase) > i
            return (
              <div key={p.name} className={cn(
                'flex-1 rounded-full transition-all',
                isActive ? (PHASE_COLORS[p.name] || 'bg-gray-500') : isPast ? 'bg-muted-foreground/50' : 'bg-muted'
              )} />
            )
          })}
        </div>
      )}
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-muted-foreground">
          Limit: {data.daily_limit === 0 ? 'None (observe only)' : `${data.daily_limit}/day`}
        </span>
        <span className="text-[10px] text-muted-foreground truncate max-w-[200px]" title={(data.allowed_actions || []).join(' · ')}>
          Allowed: {(data.allowed_actions || []).join(' · ')}
        </span>
      </div>
    </div>
  )
}
