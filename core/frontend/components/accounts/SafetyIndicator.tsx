import { ShieldCheck, AlertTriangle, ShieldAlert, Clock, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"
import type { LinkedInAccount } from "@accounts/eiAccountsStore"

type SafetyStatus = "critical" | "warning" | "watch" | "healthy" | "loading"

interface SafetyIndicatorProps {
  accountId?: string
  status: LinkedInAccount["accountStatus"]
  className?: string
}

export function computeSafetyIndicatorLocally(status: string): { level: SafetyStatus; label: string; desc: string } {
  switch (status) {
    case "CHALLENGE_REQUIRED":
      return { level: "critical", label: "Security Challenge", desc: "LinkedIn checkpoint or CAPTCHA challenge detected. Action required to resume outreach." }
    case "SUSPENDED":
      return { level: "critical", label: "Suspended", desc: "Account temporarily suspended by LinkedIn. Outreach paused." }
    case "BANNED":
      return { level: "critical", label: "Banned", desc: "Account restricted by LinkedIn. Outreach halted." }
    case "DISCONNECTED":
      return { level: "critical", label: "Disconnected", desc: "Outreach paused to preserve account safety." }
    case "NEEDS_ATTENTION":
      return { level: "warning", label: "Needs Attention", desc: "Configuration, proxy, or session warning detected." }
    case "RATE_LIMITED":
      return { level: "warning", label: "Cooling Down", desc: "LinkedIn rate limit detected. Outreach is paused for safety and will auto-resume after cooling." }
    case "MANUAL_MODE":
      return { level: "watch", label: "Manual Mode", desc: "Actions require human sign-off." }
    case "PAUSED":
      return { level: "watch", label: "Paused", desc: "Outreach automation paused by user." }
    case "DISABLED":
      return { level: "watch", label: "Disabled", desc: "Account outreach disabled." }
    case "PENDING":
      return { level: "watch", label: "Warming Up", desc: "Gradually ramping up send volume according to safety curve." }
    case "ACTIVE":
      return { level: "healthy", label: "100% Safe Zone", desc: "Within safe residential limits & human jitter curve." }
    default:
      return { level: "watch", label: "Monitoring", desc: "Active background health monitoring." }
  }
}

const LEVEL_CONFIG: Record<
  SafetyStatus,
  { pillClass: string; textClass: string; icon: any; dotClass: string }
> = {
  critical: {
    pillClass: "bg-destructive/10 border-destructive/30 text-destructive",
    textClass: "text-destructive",
    icon: ShieldAlert,
    dotClass: "bg-destructive",
  },
  warning: {
    pillClass: "bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400",
    textClass: "text-amber-600 dark:text-amber-400",
    icon: AlertTriangle,
    dotClass: "bg-amber-500",
  },
  watch: {
    pillClass: "bg-sky-500/10 border-sky-500/30 text-sky-600 dark:text-sky-400",
    textClass: "text-sky-600 dark:text-sky-400",
    icon: Clock,
    dotClass: "bg-sky-500",
  },
  healthy: {
    pillClass: "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400",
    textClass: "text-emerald-600 dark:text-emerald-400",
    icon: ShieldCheck,
    dotClass: "bg-emerald-500",
  },
  loading: {
    pillClass: "bg-muted/40 border-border/40 text-muted-foreground",
    textClass: "text-muted-foreground",
    icon: Loader2,
    dotClass: "bg-muted-foreground animate-pulse",
  },
}

export default function SafetyIndicator({ accountId, status, className }: SafetyIndicatorProps) {
  const computed = computeSafetyIndicatorLocally(status)
  const cfg = LEVEL_CONFIG[computed.level]
  const Icon = cfg.icon

  return (
    <div
      title={computed.desc}
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[11px] font-semibold transition-all shadow-2xs backdrop-blur-md cursor-help",
        cfg.pillClass,
        className
      )}
    >
      <Icon size={12} className={cn("shrink-0", computed.level === "loading" && "animate-spin")} />
      <span>{computed.label}</span>
    </div>
  )
}
