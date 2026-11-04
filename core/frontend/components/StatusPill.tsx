import { cn } from "@/lib/utils"

export type StatusType = 
  | "active" 
  | "connected" 
  | "running" 
  | "live"
  | "paused" 
  | "manual_mode" 
  | "warmup" 
  | "needs_attention" 
  | "rate_limited"
  | "completed" 
  | "ready" 
  | "sent" 
  | "booked"
  | "draft" 
  | "idle" 
  | "pending" 
  | "verifying"
  | "failed" 
  | "error" 
  | "banned" 
  | "expired" 
  | "disconnected" 
  | "challenge_required" 
  | "suspended" 
  | "disabled"
  | string

interface StatusPillProps {
  status: StatusType
  label?: string
  className?: string
  pulse?: boolean
  size?: "xs" | "sm" | "md"
}

const STATUS_CONFIGS: Record<string, { label: string; bg: string; text: string; border: string; dot: string }> = {
  // Positive / Active / Converting
  active: { label: "Active", bg: "bg-emerald-500/10", text: "text-emerald-600 dark:text-emerald-400", border: "border-emerald-500/25", dot: "bg-emerald-500" },
  connected: { label: "Connected", bg: "bg-emerald-500/10", text: "text-emerald-600 dark:text-emerald-400", border: "border-emerald-500/25", dot: "bg-emerald-500" },
  running: { label: "Running", bg: "bg-emerald-500/10", text: "text-emerald-600 dark:text-emerald-400", border: "border-emerald-500/25", dot: "bg-emerald-500" },
  live: { label: "Live", bg: "bg-emerald-500/10", text: "text-emerald-600 dark:text-emerald-400", border: "border-emerald-500/25", dot: "bg-emerald-500" },
  ready: { label: "Ready", bg: "bg-emerald-500/10", text: "text-emerald-600 dark:text-emerald-400", border: "border-emerald-500/25", dot: "bg-emerald-500" },
  booked: { label: "Meeting Booked", bg: "bg-emerald-500/10", text: "text-emerald-600 dark:text-emerald-400", border: "border-emerald-500/25", dot: "bg-emerald-500" },

  // Warmup / Paused / Attention Needed
  paused: { label: "Paused", bg: "bg-amber-500/10", text: "text-amber-600 dark:text-amber-400", border: "border-amber-500/25", dot: "bg-amber-500" },
  warmup: { label: "Warming Up", bg: "bg-amber-500/10", text: "text-amber-600 dark:text-amber-400", border: "border-amber-500/25", dot: "bg-amber-500" },
  manual_mode: { label: "Manual Mode", bg: "bg-purple-500/10", text: "text-purple-600 dark:text-purple-400", border: "border-purple-500/25", dot: "bg-purple-500" },
  needs_attention: { label: "Needs Attention", bg: "bg-amber-500/10", text: "text-amber-600 dark:text-amber-400", border: "border-amber-500/25", dot: "bg-amber-500" },
  rate_limited: { label: "Rate Limited", bg: "bg-amber-500/10", text: "text-amber-600 dark:text-amber-400", border: "border-amber-500/25", dot: "bg-amber-500" },
  pending: { label: "Pending", bg: "bg-amber-500/10", text: "text-amber-600 dark:text-amber-400", border: "border-amber-500/25", dot: "bg-amber-500" },
  verifying: { label: "Verifying...", bg: "bg-amber-500/10", text: "text-amber-600 dark:text-amber-400", border: "border-amber-500/25", dot: "bg-amber-500" },

  // Success / Milestone / Completed
  completed: { label: "Completed", bg: "bg-blue-500/10", text: "text-blue-600 dark:text-blue-400", border: "border-blue-500/25", dot: "bg-blue-500" },
  sent: { label: "Sent", bg: "bg-blue-500/10", text: "text-blue-600 dark:text-blue-400", border: "border-blue-500/25", dot: "bg-blue-500" },

  // Neutral / Draft
  draft: { label: "Draft", bg: "bg-muted/60", text: "text-muted-foreground", border: "border-border/60", dot: "bg-muted-foreground/60" },
  idle: { label: "Idle", bg: "bg-muted/60", text: "text-muted-foreground", border: "border-border/60", dot: "bg-muted-foreground/60" },

  // Destructive / Critical / Action Required
  failed: { label: "Failed", bg: "bg-destructive/10", text: "text-destructive", border: "border-destructive/25", dot: "bg-destructive" },
  error: { label: "Error", bg: "bg-destructive/10", text: "text-destructive", border: "border-destructive/25", dot: "bg-destructive" },
  banned: { label: "Account Banned", bg: "bg-destructive/10", text: "text-destructive", border: "border-destructive/25", dot: "bg-destructive" },
  expired: { label: "Session Expired", bg: "bg-destructive/10", text: "text-destructive", border: "border-destructive/25", dot: "bg-destructive" },
  disconnected: { label: "Disconnected", bg: "bg-destructive/10", text: "text-destructive", border: "border-destructive/25", dot: "bg-destructive" },
  challenge_required: { label: "Security Challenge", bg: "bg-destructive/10", text: "text-destructive", border: "border-destructive/25", dot: "bg-destructive" },
  suspended: { label: "Suspended", bg: "bg-destructive/10", text: "text-destructive", border: "border-destructive/25", dot: "bg-destructive" },
  disabled: { label: "Disabled", bg: "bg-muted/40", text: "text-muted-foreground/80", border: "border-border/40", dot: "bg-muted-foreground/40" }
}

export function StatusPill({ 
  status, 
  label, 
  className, 
  pulse, 
  size = "sm" 
}: StatusPillProps) {
  const normKey = (status || "idle").toLowerCase().replace(/[\s-]/g, "_")
  const config = STATUS_CONFIGS[normKey] || {
    label: status || "Unknown",
    bg: "bg-muted/60",
    text: "text-muted-foreground",
    border: "border-border/60",
    dot: "bg-muted-foreground/60"
  }

  const displayLabel = label || config.label
  const shouldPulse = pulse ?? (normKey === "running" || normKey === "verifying" || normKey === "live")

  const sizeClasses = {
    xs: "px-2 py-0.5 text-[10px] gap-1",
    sm: "px-2.5 py-0.5 text-xs gap-1.5",
    md: "px-3 py-1 text-xs gap-2"
  }

  return (
    <span
      className={cn(
        "inline-flex items-center font-medium rounded-full border shadow-2xs backdrop-blur-xs transition-colors",
        config.bg,
        config.text,
        config.border,
        sizeClasses[size],
        className
      )}
    >
      <span className="relative flex shrink-0 size-1.5">
        {shouldPulse && (
          <span className={cn("animate-ping absolute inline-flex h-full w-full rounded-full opacity-75", config.dot)} />
        )}
        <span className={cn("relative inline-flex rounded-full size-1.5", config.dot)} />
      </span>
      <span className="tracking-wide select-none font-semibold truncate">{displayLabel}</span>
    </span>
  )
}

