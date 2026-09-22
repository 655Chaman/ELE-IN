import { motion } from "motion/react"
import { toast } from "sonner"
import { X, ChevronRight, ArrowLeft, FileSpreadsheet, Compass, Link2, Search } from "lucide-react"
import { fetchWithAuth } from "@/lib/apiClient"
import { LeadImportProvider, useLeadImport } from "./LeadImportContext"

import { HubSpotImport } from "./methods/HubSpotImport"
import { CSVImport } from "./methods/CSVImport"
import { SalesNavImport } from "./methods/SalesNavImport"
import { RawProfilesImport } from "./methods/RawProfilesImport"
import { SearchImport } from "./methods/SearchImport"
import { TargetRegionSelector } from "./TargetRegionSelector"
import { TARGET_REGIONS } from "../../../shared/constants/regions"

function ImportLeadsModalContent({ onClose, onAdd }: { onClose: () => void; onAdd: () => void }) {
  const {
    method, setMethod,
    name, setName,
    step, setStep,
    file,
    mappings,
    cleanData,
    activeAccount,
    budget,
    liveUrl,
    urlList,
    salesNavUrl,
    targetTimezone, setTargetTimezone,
    isSubmitting, setIsSubmitting
  } = useLeadImport();

  const handleSubmit = async () => {
    if (!name.trim()) { toast.error("Please enter a list name"); return; }
    
    // Validate targetTimezone for methods that require it (all except hubspot)
    if (method !== "hubspot" && !targetTimezone) {
      toast.error("Please select a Target Region");
      return;
    }
    
    if (method === "csv" && step === 1) {
      if (!file) { toast.error("Please select a CSV file"); return; }
      setStep(2);
      return;
    }

    setIsSubmitting(true)
    try {
      // Find the label for the timezone
      // We need to import TARGET_REGIONS from shared, let's do this dynamically if needed or just use state.
      // Wait, we need to import TARGET_REGIONS at the top of ImportLeadsModal.tsx
      // For now, let's assume we can get it or we just send it if it's not strictly needed for UI.
      // Wait, the API requires target_region_label. 
      // Let's import TARGET_REGIONS at the top of the file.
      const selectedRegion = TARGET_REGIONS.find(r => r.timezone === targetTimezone);
      const regionLabel = selectedRegion ? selectedRegion.label : "";
      
      if (method === "search") {
        if (!liveUrl) { toast.error("Please select at least one search filter"); setIsSubmitting(false); return; }
        if (!activeAccount) { toast.error("No active LinkedIn account connected. Go to Accounts to connect one."); setIsSubmitting(false); return; }
        if (budget.remaining <= 0) { toast.error(`Daily scraping limit reached (${budget.limit}/day). Resets tomorrow.`); setIsSubmitting(false); return; }
        const res = await fetchWithAuth("/api/elein/leads/upload_sales_nav", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name, url: liveUrl, account_id: activeAccount.id, max_results: Math.min(100, budget.remaining), target_timezone: targetTimezone, target_region_label: regionLabel })
        })
        if (!res.ok) throw new Error(await res.text())
        toast.success(`Native search import started for "${name}"! Leads will appear shortly.`)
      } else if (method === "csv") {
        const formData = new FormData()
        formData.append("file", file!)
        formData.append("name", name)
        formData.append("target_timezone", targetTimezone)
        formData.append("target_region_label", regionLabel)
        formData.append("mappings", JSON.stringify(mappings))
        formData.append("clean_data", String(cleanData))
        const res = await fetchWithAuth("/api/elein/leads/upload_csv", { method: "POST", body: formData })
        if (!res.ok) throw new Error(await res.text())
        toast.success(`CSV Import started in the background for "${name}"!`)
      } else if (method === "linkedin_url") {
        const urls = urlList.split("\n").map(u => u.trim()).filter(Boolean)
        if (urls.length === 0) { toast.error("Please enter at least one URL"); setIsSubmitting(false); return; }
        const res = await fetchWithAuth("/api/elein/leads/upload_urls", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, urls, target_timezone: targetTimezone, target_region_label: regionLabel })
        })
        if (!res.ok) throw new Error(await res.text())
        const data = await res.json()
        toast.success(`${data.row_count || urls.length} URLs uploaded successfully to "${name}"!`)
      } else if (method === "sales_nav") {
        if (!salesNavUrl.trim()) { toast.error("Please enter a Sales Navigator URL"); setIsSubmitting(false); return; }
        if (!activeAccount) { toast.error("No active LinkedIn account connected. Go to Accounts to connect one."); setIsSubmitting(false); return; }
        const res = await fetchWithAuth("/api/elein/leads/upload_sales_nav", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, url: salesNavUrl, account_id: activeAccount.id, target_timezone: targetTimezone, target_region_label: regionLabel })
        })
        if (!res.ok) throw new Error(await res.text())
        toast.success(`Sales Navigator import started for "${name}"!`)
      }
      onAdd(); onClose();
    } catch (e: any) { 
      let errMsg = "Failed to upload — please check your file and try again.";
      try {
        const parsed = JSON.parse(errMsg);
        if (parsed.detail) errMsg = parsed.detail;
      } catch (_) {}
      toast.error(errMsg);
    } finally { 
      setIsSubmitting(false); 
    }
  }

  const METHODS = [
    { id: "search", label: "Build a Search", desc: "Use our native LinkedIn URL generator for pinpoint accuracy.", icon: Search, color: "text-primary", bg: "bg-primary/10", border: "border-l-2 border-primary/0 group-hover:border-primary/50", active: true },
    { id: "csv", label: "Upload CSV", desc: "Map your spreadsheet columns directly to our database.", icon: FileSpreadsheet, color: "text-success", bg: "bg-success/10", border: "border-l-2 border-success/0 group-hover:border-success/50", active: true },
    { id: "sales_nav", label: "Sales Navigator", desc: "Paste an existing Sales Nav query to scrape instantly.", icon: Compass, color: "text-primary", bg: "bg-primary/10", border: "border-l-2 border-primary/0 group-hover:border-primary/50", active: true },
    { id: "linkedin_url", label: "Raw Profiles", desc: "Paste a raw list of LinkedIn profile URLs.", icon: Link2, color: "text-primary", bg: "bg-primary/10", border: "border-l-2 border-primary/0 group-hover:border-primary/50", active: true },
    { id: "hubspot", label: "HubSpot Sync", desc: "Pull directly from your CRM.", icon: () => <img src="https://cdn.simpleicons.org/hubspot/ff7a59" className="w-[18px] h-[18px]" alt="HubSpot" />, color: "text-primary", bg: "bg-primary/10", border: "border-l-2 border-primary/0 group-hover:border-primary/50", active: true },
  ];

  const currentMethod = METHODS.find(m => m.id === method);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-md p-4 overflow-y-auto">
      <motion.div
        initial={{ opacity: 0, scale: 0.97, y: 15 }}
        animate={{ opacity: 1, scale: 1, y: 0, transition: { type: "spring", damping: 25, stiffness: 300 } }}
        exit={{ opacity: 0, scale: 0.97, y: 10, transition: { duration: 0.15, ease: "easeIn" } }}
        className={`w-full ${method ? 'max-w-[1100px]' : 'max-w-[550px]'} bg-card rounded-2xl shadow-[0_20px_60px_-15px_rgba(0,0,0,0.4)] border flex flex-col relative my-8`}
      >
        <button onClick={onClose} className="absolute right-5 top-5 text-muted-foreground hover:text-foreground transition-all duration-100 z-50 p-2 rounded-full hover:bg-muted active:scale-90 active:bg-muted/80">
          <X size={18} />
        </button>

        {!method ? (
          // Step 1: Premium List View
          <div className="p-8">
            <div className="mb-8">
              <h1 className="text-xl font-bold tracking-tight mb-1">Import Leads</h1>
              <p className="text-sm text-muted-foreground">Select a data source to begin building your audience.</p>
            </div>
            
            <div className="flex flex-col gap-3">
              {METHODS.map(m => (
                <button
                  key={m.id}
                  onClick={() => m.active && setMethod(m.id as any)}
                  disabled={!m.active}
                  className={`group relative flex items-center gap-5 p-4 rounded-xl border transition-all duration-150 text-left overflow-hidden ${
                    m.active 
                    ? `hover:border-foreground/30 hover:shadow-sm bg-gradient-to-br from-background to-muted/30 active:scale-[0.99] active:bg-muted/50 cursor-pointer ${m.border}` 
                    : "opacity-60 cursor-not-allowed bg-muted/20 border-transparent"
                  }`}
                >
                  <div className={`p-3.5 rounded-xl ${m.bg} ${m.color} group-hover:scale-105 transition-transform shrink-0`}>
                    <m.icon size={22} strokeWidth={2} />
                  </div>
                  <div className="flex-1">
                    <h3 className="font-semibold text-sm mb-0.5">{m.label}</h3>
                    <p className="text-xs text-muted-foreground">{m.desc}</p>
                  </div>
                  
                  {m.active ? (
                    <div className="text-muted-foreground opacity-40 group-hover:opacity-100 group-hover:translate-x-1 transition-all duration-300 pr-2">
                       <ChevronRight size={18} />
                    </div>
                  ) : (
                    <span className="text-[10px] uppercase tracking-wider font-bold bg-muted px-2 py-1 rounded text-muted-foreground">Soon</span>
                  )}
                </button>
              ))}
            </div>
          </div>
        ) : (
          // Step 2: Configure Selected Method
          <div className="flex flex-col h-full max-h-[85vh]">
            <div className="p-6 border-b flex items-center gap-4 bg-muted/5 sticky top-0 z-10">
              <button 
                onClick={() => { setMethod(null); setStep(1); }}
                className="p-2 rounded-full hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
              >
                <ArrowLeft size={18} />
              </button>
              <div className={`p-2 rounded-lg ${currentMethod?.bg} ${currentMethod?.color}`}>
                {currentMethod && <currentMethod.icon size={18} />}
              </div>
              <div className="flex-1 pr-8">
                <div className="flex items-center justify-between">
                  <h2 className="font-semibold">{currentMethod?.label}</h2>
                  <span className="text-[10px] font-bold uppercase tracking-wider bg-muted text-muted-foreground px-2.5 py-1 rounded-full">
                    {method === "csv" ? `Step ${step} of 2` : "Step 1 of 1"}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground">{currentMethod?.desc}</p>
              </div>
            </div>

            <div className="p-8 overflow-y-auto flex-1">
              <div className="max-w-3xl mx-auto w-full">
              {method !== "hubspot" && (
                <div className="mb-8">
                  <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider mb-1.5 block">List Name</label>
                  <input
                    value={name}
                    onChange={e => setName(e.target.value)}
                    placeholder='e.g. "Q3 Enterprise Outreach"'
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-1 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    autoFocus
                  />
                </div>
              )}

              {method && method !== "hubspot" && (
                <TargetRegionSelector 
                  value={targetTimezone} 
                  onChange={setTargetTimezone} 
                />
              )}

              {method === "search" && <SearchImport />}
              {method === "hubspot" && <HubSpotImport onClose={onClose} />}
              {method === "csv" && <CSVImport />}
              {method === "sales_nav" && <SalesNavImport />}
              {method === "linkedin_url" && <RawProfilesImport />}

            </div>
            </div>

            {method !== "hubspot" && (
              <div className="p-6 border-t bg-muted/5 flex items-center justify-between shrink-0">
                {method === 'csv' && step === 2 ? (
                  <button onClick={() => setStep(1)} className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors px-4 py-2 flex items-center gap-2">
                    <ArrowLeft size={16} /> Back
                  </button>
                ) : (
                  <div />
                )}
                <button 
                  onClick={handleSubmit} 
                  disabled={!name.trim() || isSubmitting || (method === 'search' && !liveUrl) || (method === 'csv' && step === 1 && !file)} 
                  className="px-8 py-2.5 text-sm font-bold bg-foreground hover:bg-foreground/90 rounded-lg text-background transition-all disabled:opacity-50 flex justify-center items-center gap-2 shadow-sm"
                >
                  {isSubmitting ? (
                    <span className="flex items-center gap-2">
                      <svg className="animate-spin h-4 w-4 text-background" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                      Processing...
                    </span>
                  ) : (
                    <>
                      {(method === 'csv' && step === 1) ? 'Next: Map Columns' : <><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="lucide lucide-sparkles"><path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z"/><path d="M20 3v4"/><path d="M22 5h-4"/><path d="M4 17v2"/><path d="M5 18H3"/></svg> Import Leads</>}
                      {!(method === 'csv' && step === 1) && <ChevronRight size={16} />}
                    </>
                  )}
                </button>
              </div>
            )}
          </div>
        )}
      </motion.div>
    </div>
  )
}

export function ImportLeadsModal({ onClose, onAdd }: { onClose: () => void; onAdd: () => void }) {
  return (
    <LeadImportProvider>
      <ImportLeadsModalContent onClose={onClose} onAdd={onAdd} />
    </LeadImportProvider>
  )
}
