import { cn } from "@/lib/utils"

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("animate-pulse bg-muted/20 brutal-border", className)}
      {...props}
      aria-busy="true"
      aria-label="Loading..."
    />
  )
}

export function PipelineCardSkeleton() {
  return (
    <div className="brutal-border bg-[#0f0f0f] p-6 flex flex-col h-full opacity-50 pointer-events-none" aria-busy="true">
      <div className="flex justify-between items-start mb-4">
        <div>
          <Skeleton className="h-8 w-48 mb-2" />
          <Skeleton className="h-4 w-64 mb-1" />
          <Skeleton className="h-4 w-56" />
        </div>
        <Skeleton className="h-5 w-16 rounded-full" />
      </div>

      <div className="grid grid-cols-2 gap-4 mb-6 pt-4 border-t border-border mt-2">
        <div>
          <Skeleton className="h-3 w-20 mb-2" />
          <Skeleton className="h-10 w-16" />
        </div>
        <div>
          <Skeleton className="h-3 w-20 mb-2" />
          <Skeleton className="h-10 w-16" />
        </div>
      </div>

      <div className="mt-auto space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
        <div className="grid grid-cols-2 gap-3 pt-2">
          <Skeleton className="h-6 w-24 mx-auto" />
          <Skeleton className="h-6 w-24 mx-auto" />
        </div>
      </div>
    </div>
  )
}
