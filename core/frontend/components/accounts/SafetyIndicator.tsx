import { cn } from "@/lib/utils"
import type { LinkedInAccount } from "@accounts/eiAccountsStore"

type SafetyStatus = "critical" | "warning" | "watch" | "healthy" | "loading"

interface SafetyIndicatorProps {
  accountId: string
  status: LinkedInAccount["accountStatus"]
}

export function computeSafetyIndicatorLocally(status: string): { level: SafetyStatus; label: string } {
  switch (status) {
    case "BANNED":
    case "DISCONNECTED":
      return { level: "critical", label: "Critical" }
    case "RATE_LIMITED":
      return { level: "warning", label: "Needs Attention" }
    case "MANUAL_MODE":
    case "PENDING":
      return { level: "watch", label: "Watch" }
    case "ACTIVE":
      return { level: "healthy", label: "Healthy" }
    default:
      return { level: "watch", label: "Watch" }
  }
}

const LEVEL_CONFIG: Record<SafetyStatus, { color: string; dotClass: string }> = {
  critical: { color: "text-destructive", dotClass: "bg-destructive" },
  warning: { color: "text-primary", dotClass: "bg-primary" },
  watch: { color: "text-primary", dotClass: "bg-primary" },
  healthy: { color: "text-success", dotClass: "bg-success" },
  loading: { color: "text-muted-foreground", dotClass: "bg-muted-foreground animate-pulse" },
}

export default function SafetyIndicator({ accountId, status }: SafetyIndicatorProps) {
  const computed = computeSafetyIndicatorLocally(status)
  
  const level = computed.level
  const label = computed.label
  const cfg = LEVEL_CONFIG[level]

  return (
    <div className="flex items-center gap-1.5">
      <div className={cn("w-2 h-2 rounded-full", cfg.dotClass)} />
      <span className={cn("text-[10px] font-medium", cfg.color)}>{label}</span>
    </div>
  )
}
