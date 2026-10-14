import useSWR from "swr"
import { fetcher, fetchWithAuth } from "@/lib/apiClient"
import { CheckCircle2, AlertTriangle, AlertCircle, Clock, RefreshCw, Lock } from "lucide-react"
import { cn } from "@/lib/utils"
import { useState } from "react"
import { usePaywall } from "@/contexts/PaywallContext"

interface HealthCheck {
  id: string
  check_type: string
  result: "pass" | "warn" | "fail"
  checked_at: string
  detail?: string
}

const CHECK_LABELS: Record<string, string> = {
  session_valid: "Session Valid",
  cookie_freshness: "Cookie Freshness",
}

const RESULT_CONFIG = {
  pass: { icon: CheckCircle2, color: "text-success", bg: "bg-success/10" },
  warn: { icon: AlertTriangle, color: "text-primary", bg: "bg-primary/10" },
  fail: { icon: AlertCircle, color: "text-destructive", bg: "bg-destructive/10" },
}

import { formatRelativeTime } from "@/lib/utils/date";

export default function HealthTimeline({ accountId }: { accountId: string }) {
  const { data: checks, error, isLoading, mutate } = useSWR<HealthCheck[]>(
    `/api/elein/accounts/${accountId}/health-history`,
    fetcher
  )
  const { data: billing } = useSWR<{ tier?: string; tier_limits?: { can_run_manual_health_check?: boolean } }>(
    '/api/elein/workspaces/billing',
    fetcher
  )
  const { openPaywall } = usePaywall()
  const isHealthCheckLocked = Boolean(billing && !billing.tier_limits?.can_run_manual_health_check)
  const [running, setRunning] = useState(false)

  const runCheck = async () => {
    if (isHealthCheckLocked) {
      openPaywall({ featureName: "Real-Time Account Health Diagnostics" })
      return
    }
    setRunning(true)
    try {
      await fetchWithAuth(`/api/elein/accounts/${accountId}/health-check`, { method: "POST" })
      mutate()
    } catch (e) {
      console.error(e)
    } finally {
      setRunning(false)
    }
  }

  if (isLoading) {
    return <div className="animate-pulse flex items-center justify-center p-4 text-xs text-muted-foreground">Loading history...</div>
  }

  if (error) {
    return <div className="p-4 text-xs text-destructive">Failed to load health history.</div>
  }

  return (
    <div className="mt-4 p-3 rounded-lg bg-background/40 border border-border/50">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-xs font-semibold text-foreground flex items-center gap-1.5"><Clock size={12} /> Health Checks</h4>
        {isHealthCheckLocked ? (
          <button 
            onClick={runCheck}
            className="flex items-center gap-1.5 px-2 py-1 bg-amber-500/10 hover:bg-amber-500/20 text-amber-700 dark:text-amber-400 rounded text-[10px] font-medium transition-colors cursor-pointer"
          >
            <Lock size={10} className="text-amber-500" />
            <span>Run Health Check</span>
            <span className="text-[9px] font-bold px-1 py-0.2 bg-amber-500/20 text-amber-600 dark:text-amber-400 rounded">PRO</span>
          </button>
        ) : (
          <button 
            onClick={runCheck}
            disabled={running}
            className="flex items-center gap-1 px-2 py-1 bg-primary/10 hover:bg-primary/20 text-primary rounded text-[10px] font-medium transition-colors disabled:opacity-50"
          >
            <RefreshCw size={10} className={cn(running && "animate-spin")} />
            Run Health Check
          </button>
        )}
      </div>

      {!checks || checks.length === 0 ? (
        <div className="text-center py-4 text-[11px] text-muted-foreground">No health checks yet.</div>
      ) : (
        <div className="space-y-2">
          {checks.map(check => {
            const Cfg = RESULT_CONFIG[check.result] || RESULT_CONFIG.warn
            const Icon = Cfg.icon
            return (
              <div key={check.id} className="flex items-start justify-between text-[11px]">
                <div className="flex items-center gap-2">
                  <div className={cn("p-1 rounded flex items-center justify-center", Cfg.bg)}>
                    <Icon size={12} className={Cfg.color} />
                  </div>
                  <div>
                    <p className="text-foreground font-medium">{CHECK_LABELS[check.check_type] || check.check_type}</p>
                    {check.detail && <p className="text-muted-foreground text-[10px] mt-0.5">{check.detail}</p>}
                  </div>
                </div>
                <span className="text-muted-foreground whitespace-nowrap">{formatRelativeTime(check.checked_at)}</span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
