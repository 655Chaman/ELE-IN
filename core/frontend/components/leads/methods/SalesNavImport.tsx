import { Compass } from "lucide-react"
import { useLeadImport } from "../LeadImportContext"

export function SalesNavImport() {
  const { salesNavUrl, setSalesNavUrl } = useLeadImport();

  return (
    <div className="animate-in fade-in max-w-xl">
      <div className="grid gap-2">
        <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider block mb-1">Sales Navigator URL</label>
        <input value={salesNavUrl} onChange={e => setSalesNavUrl(e.target.value)} placeholder="https://www.linkedin.com/sales/search/people?..." className="flex h-12 w-full rounded-lg border border-input bg-background px-4 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
      </div>
      <div className="mt-4 p-4 rounded-lg bg-primary/10 dark:bg-primary/20 border border-primary/20 text-amber-600 dark:text-primary/80 text-sm flex gap-3 items-start">
        <Compass className="shrink-0 mt-0.5" size={18} />
        <p className="leading-relaxed">Sales Navigator scraping runs in the cloud and may take 5-10 minutes. You can safely close this window after starting.</p>
      </div>
    </div>
  )
}
