import { useEffect } from "react"
import { motion } from "motion/react"
import { toast } from "sonner"
import { X, ChevronRight, ArrowLeft, FileSpreadsheet, Compass, Link2, Search, Lock, Loader2, Sparkles } from "lucide-react"
import { fetchWithAuth } from "@/lib/apiClient"
import { usePaywall } from "@/contexts/PaywallContext"
import { LeadImportProvider, useLeadImport } from "./LeadImportContext"

import { HubSpotImport } from "./methods/HubSpotImport"
import { CSVImport } from "./methods/CSVImport"
import { SalesNavImport } from "./methods/SalesNavImport"
import { RawProfilesImport } from "./methods/RawProfilesImport"
import { SearchImport } from "./methods/SearchImport"
import { TargetRegionSelector } from "./TargetRegionSelector"
import { TARGET_REGIONS } from "../../../shared/constants/regions"

function ImportLeadsModalContent({ onClose, onAdd }: { onClose: () => void; onAdd: () => void }) {
  const { openPaywall, openTopUp } = usePaywall();
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
    salesNavMaxResults,
    targetTimezone, setTargetTimezone,
    isSubmitting, setIsSubmitting,
    billing
  } = useLeadImport();

  const isPro = billing?.tier === 'PRO' || billing?.tier === 'ENTERPRISE';

  const isUploading = isSubmitting;

  // Escape key dismiss handler with nested step unwinding
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (!isUploading) {
          if (method === "csv" && step === 2) {
            setStep(1);
          } else if (method) {
            setMethod(null);
            setStep(1);
          } else {
            onClose();
          }
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isUploading, method, step, onClose, setStep, setMethod]);

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

    if (method === "csv" && step === 2) {
      if (!mappings.linkedin_url && !mappings.email) {
        toast.error("Please map at least the LinkedIn URL or Email column before importing.");
        return;
      }
    }

    setIsSubmitting(true)
    try {
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
        if (!res.ok) {
          let errDetail = "Search import failed";
          try {
            const errJson = await res.json();
            errDetail = errJson.detail || errDetail;
          } catch {
            const raw = await res.text();
            if (raw) errDetail = raw;
          }
          throw new Error(errDetail);
        }
        toast.success(`Native search import started for "${name}"! Leads will appear shortly.`)
      } else if (method === "csv") {
        const formData = new FormData()
        formData.append("file", file!)
        formData.append("list_name", name)
        formData.append("name", name)
        formData.append("target_timezone", targetTimezone)
        formData.append("target_region_label", regionLabel)
        formData.append("mappings", JSON.stringify(mappings))
        formData.append("clean_data", String(cleanData))
        const res = await fetchWithAuth("/api/elein/leads/upload_csv", { method: "POST", body: formData })
        if (!res.ok) {
          let errDetail = "Failed to upload CSV";
          try {
            const errJson = await res.json();
            errDetail = errJson.detail || errDetail;
          } catch {
            const raw = await res.text();
            if (raw) errDetail = raw;
          }
          throw new Error(errDetail);
        }
        toast.success(`CSV Import started in the background for "${name}"!`)
      } else if (method === "linkedin_url") {
        const urls = urlList.split("\n").map(u => u.trim()).filter(Boolean)
        if (urls.length === 0) { toast.error("Please enter at least one URL"); setIsSubmitting(false); return; }
        const res = await fetchWithAuth("/api/elein/leads/upload_urls", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, urls, target_timezone: targetTimezone, target_region_label: regionLabel })
        })
        if (!res.ok) {
          let errDetail = "Failed to upload profile URLs";
          try {
            const errJson = await res.json();
            errDetail = errJson.detail || errDetail;
          } catch {
            const raw = await res.text();
            if (raw) errDetail = raw;
          }
          throw new Error(errDetail);
        }
        const data = await res.json()
        toast.success(`${data.row_count || urls.length} URLs uploaded successfully to "${name}"!`)
      } else if (method === "sales_nav") {
        if (!salesNavUrl.trim()) { toast.error("Please enter a Sales Navigator URL"); setIsSubmitting(false); return; }
        if (!activeAccount) { toast.error("No active LinkedIn account connected. Go to Accounts to connect one."); setIsSubmitting(false); return; }
        const res = await fetchWithAuth("/api/elein/leads/upload_sales_nav", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, url: salesNavUrl, account_id: activeAccount.id, max_results: salesNavMaxResults || 50, target_timezone: targetTimezone, target_region_label: regionLabel })
        })
        if (!res.ok) {
          let errDetail = "Failed to import Sales Navigator query";
          try {
            const errJson = await res.json();
            errDetail = errJson.detail || errDetail;
          } catch {
            const raw = await res.text();
            if (raw) errDetail = raw;
          }
          throw new Error(errDetail);
        }
        toast.success(`Sales Navigator import started for "${name}"!`)
      }
      onAdd(); onClose();
    } catch (e: any) { 
      let errMsg = e?.message || "Failed to upload — please check your file and try again.";
      try {
        const parsed = JSON.parse(errMsg);
        if (parsed.detail) errMsg = parsed.detail;
      } catch (_) {}

      if (errMsg === "insufficient_credits" || errMsg.includes("insufficient_credits")) {
        toast.error("Insufficient credits for data cleaning. Please top up your credits or disable AI Data Hygiene.");
        openTopUp({ featureName: "AI Data Hygiene", neededCredits: 100 });
      } else {
        toast.error(errMsg);
      }
    } finally { 
      setIsSubmitting(false); 
    }
  }

  const METHODS = [
    { id: "search", label: "Build a Search", desc: "Use our native LinkedIn URL generator for pinpoint accuracy.", icon: Search, color: "text-primary", bg: "bg-primary/10", active: true },
    { id: "csv", label: "Upload CSV", desc: "Map your spreadsheet columns directly to our database.", icon: FileSpreadsheet, color: "text-success", bg: "bg-success/10", active: true },
    { id: "sales_nav", label: "Sales Navigator", desc: "Paste an existing Sales Nav query to scrape instantly.", icon: Compass, color: "text-primary", bg: "bg-primary/10", active: true, proOnly: true },
    { id: "linkedin_url", label: "Raw Profiles", desc: "Paste a raw list of LinkedIn profile URLs.", icon: Link2, color: "text-primary", bg: "bg-primary/10", active: true },
    { id: "hubspot", label: "HubSpot Sync", desc: "Pull directly from your CRM.", icon: () => <img src="https://cdn.simpleicons.org/hubspot/ff7a59" className="w-[18px] h-[18px]" alt="HubSpot" />, color: "text-primary", bg: "bg-primary/10", active: true, proOnly: true },
  ];

  const currentMethod = METHODS.find(m => m.id === method);

  return (
    <div 
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4 overflow-y-auto"
      role="dialog"
      aria-modal="true"
      aria-labelledby="import-leads-title"
      onClick={() => !isUploading && onClose()}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.97, y: 15 }}
        animate={{ opacity: 1, scale: 1, y: 0, transition: { type: "spring", damping: 25, stiffness: 300 } }}
        exit={{ opacity: 0, scale: 0.97, y: 10, transition: { duration: 0.15, ease: "easeIn" } }}
        onClick={(e) => e.stopPropagation()}
        className={`w-full ${method ? 'max-w-[1100px]' : 'max-w-[550px]'} max-h-[90dvh] bg-card rounded-xl shadow-2xl border border-border/80 flex flex-col relative overflow-hidden`}
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Close modal"
          className="absolute right-5 top-5 text-muted-foreground hover:text-foreground transition-all duration-100 z-50 p-2 rounded-full hover:bg-muted active:bg-muted/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          <X size={18} />
        </button>

        {!method ? (
          // Step 1: Premium List View
          <div className="p-8">
            <div className="mb-8">
              <h1 id="import-leads-title" className="text-xl font-bold tracking-tight mb-1 text-foreground">Import Leads</h1>
              <p className="text-sm text-muted-foreground">Select a data source to begin building your audience.</p>
            </div>
            
            <div className="flex flex-col gap-3">
              {METHODS.map(m => {
                const isLocked = (m as any).proOnly && !isPro;
                return (
                  <button
                    type="button"
                    key={m.id}
                    onClick={() => {
                      if (isLocked) {
                        openPaywall({ featureName: m.label, campaignName: "Prospecting & CRM Sync" });
                        return;
                      }
                      if (m.active) setMethod(m.id as any);
                    }}
                    disabled={!m.active && !isLocked}
                    className={`group relative flex items-center gap-5 p-4 rounded-lg border transition-all duration-150 text-left overflow-hidden ${
                      m.active || isLocked
                      ? "border-border/60 hover:border-foreground/30 hover:shadow-xs bg-card hover:bg-muted/50 transition-colors cursor-pointer" 
                      : "opacity-60 cursor-not-allowed bg-muted/20 border-transparent"
                    }`}
                  >
                    <div className={`p-3.5 rounded-lg ${m.bg} ${m.color} shrink-0`}>
                      <m.icon size={22} strokeWidth={2} />
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-0.5">
                        <h3 className="font-semibold text-sm">{m.label}</h3>
                        {isLocked && (
                          <span className="flex items-center gap-1 text-[9px] uppercase tracking-wider font-bold bg-primary/20 text-primary border border-primary/30 px-1.5 py-0.5 rounded shadow-sm">
                            <Lock size={9} /> PRO
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground">{m.desc}</p>
                    </div>
                    
                    {isLocked ? (
                      <div className="text-primary opacity-60 group-hover:opacity-100 group-hover:translate-x-1 transition-all duration-300 pr-2">
                        <ChevronRight size={18} />
                      </div>
                    ) : m.active ? (
                      <div className="text-muted-foreground opacity-40 group-hover:opacity-100 group-hover:translate-x-1 transition-all duration-300 pr-2">
                         <ChevronRight size={18} />
                      </div>
                    ) : (
                      <span className="text-[10px] uppercase tracking-wider font-bold bg-muted px-2 py-1 rounded text-muted-foreground">Soon</span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        ) : (
          // Step 2: Configure Selected Method
          <div className="flex flex-col h-full max-h-[90dvh] overflow-hidden">
            <div className="p-6 border-b flex items-center gap-4 bg-muted/5 sticky top-0 z-10">
              <button 
                type="button"
                onClick={() => { setMethod(null); setStep(1); }}
                aria-label="Back to methods list"
                className="p-2 rounded-full hover:bg-muted text-muted-foreground hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              >
                <ArrowLeft size={18} />
              </button>
              <div className={`p-2 rounded-lg ${currentMethod?.bg} ${currentMethod?.color}`}>
                {currentMethod && <currentMethod.icon size={18} />}
              </div>
              <div className="flex-1 pr-8">
                <div className="flex items-center justify-between">
                  <h2 id="import-leads-title" className="font-semibold text-foreground">{currentMethod?.label}</h2>
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
                  <button
                    type="button"
                    onClick={() => setStep(1)}
                    className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors px-4 py-2 flex items-center gap-2 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                  >
                    <ArrowLeft size={16} /> Back
                  </button>
                ) : (
                  <div />
                )}
                <button 
                  type="button"
                  onClick={handleSubmit} 
                  disabled={!name.trim() || isUploading || (method === 'search' && !liveUrl) || (method === 'sales_nav' && !salesNavUrl.trim()) || (method === 'linkedin_url' && !urlList.trim()) || (method === 'csv' && step === 1 && !file) || (method === 'csv' && step === 2 && !mappings.linkedin_url)} 
                  className="px-8 py-2.5 text-sm font-bold bg-foreground hover:bg-foreground/90 rounded-lg text-background transition-all disabled:opacity-50 flex justify-center items-center gap-2 shadow-sm cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {isUploading ? (
                    <span className="flex items-center gap-2">
                      <Loader2 size={16} className="animate-spin text-background" />
                      Processing...
                    </span>
                  ) : (
                    <>
                      {(method === 'csv' && step === 1) ? 'Next: Map Columns' : <><Sparkles size={16} /> Import Leads</>}
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
