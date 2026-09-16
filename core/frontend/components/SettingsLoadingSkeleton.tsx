import { Skeleton } from "@/components/Skeleton";

export function SettingsLoadingSkeleton() {
  return (
    <div className="space-y-4 p-4 animate-pulse">
      <Skeleton className="h-6 w-48 rounded-md" />
      <Skeleton className="h-4 w-full rounded-md" />
      <Skeleton className="h-4 w-3/4 rounded-md" />
      <Skeleton className="h-10 w-full rounded-md" />
      <Skeleton className="h-10 w-full rounded-md" />
    </div>
  );
}
