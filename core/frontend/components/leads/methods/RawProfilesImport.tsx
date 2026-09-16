import { useLeadImport } from "../LeadImportContext"

export function RawProfilesImport() {
  const { urlList, setUrlList } = useLeadImport();

  return (
    <div className="animate-in fade-in max-w-xl">
      <div className="grid gap-2">
        <div className="flex items-center justify-between mb-1">
          <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider block">LinkedIn Profile URLs</label>
          <span className="text-[11px] uppercase font-bold text-primary tracking-wider bg-primary/10 px-3 py-1 rounded-full">
            {urlList.split("\n").filter(l => l.trim()).length} URLs detected
          </span>
        </div>
        <textarea value={urlList} onChange={e => setUrlList(e.target.value)} rows={10} placeholder={"Paste LinkedIn URLs here, one per line:\n\nhttps://linkedin.com/in/person-one\nhttps://linkedin.com/in/person-two"} className="flex w-full rounded-lg border border-input bg-background px-4 py-3 text-sm font-mono shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-none leading-relaxed" />
      </div>
    </div>
  )
}
