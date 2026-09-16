
export function PageHeaderSkeleton() {
  return (
    <div className="mb-6 animate-pulse space-y-2">
      <div className="h-8 w-48 rounded-lg bg-foreground/5" />
      <div className="h-4 w-96 rounded bg-foreground/5" />
    </div>
  )
}

export function CardSkeleton() {
  return (
    <div className="p-4 rounded-xl border border-border bg-foreground/[0.02] animate-pulse">
      <div className="flex items-center gap-4">
        <div className="w-10 h-10 rounded-full bg-foreground/5 shrink-0" />
        <div className="flex-1 space-y-2">
          <div className="h-4 w-32 rounded bg-foreground/5" />
          <div className="h-3 w-48 rounded bg-foreground/5" />
        </div>
      </div>
    </div>
  )
}

export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="border border-border rounded-xl overflow-hidden animate-pulse">
      <div className="bg-foreground/[0.03] h-12 border-b border-border" />
      <div className="divide-y divide-border bg-foreground/[0.01]">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="flex items-center gap-4 p-4 h-16">
            <div className="w-8 h-8 rounded-full bg-foreground/5 shrink-0" />
            <div className="h-4 w-48 rounded bg-foreground/5" />
            <div className="ml-auto h-4 w-24 rounded bg-foreground/5" />
          </div>
        ))}
      </div>
    </div>
  )
}
