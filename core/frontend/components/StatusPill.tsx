import { cn } from "@/lib/utils"

export function StatusPill({ status }: { status: string }) {
  const map: Record<string, string> = {
    idle: "text-gray-400 border-gray-800",
    running: "text-zinc-400 border-zinc-900 animate-pulse",
    completed: "text-zinc-400 border-zinc-900",
    failed: "text-zinc-400 border-zinc-900"
  }

  const s = status?.toLowerCase() || "idle"
  const colorClass = map[s] || map.idle

  return (
    <div className={cn("px-2 py-0.5 text-xs font-mono uppercase tracking-wider border rounded-full inline-block", colorClass)}>
      {s}
    </div>
  )
}
