import { useMemo } from "react"
import { Compass, CheckCircle2, AlertTriangle, ShieldCheck, Zap, UserCheck } from "lucide-react"
import { useLeadImport } from "../LeadImportContext"

export function SalesNavImport() {
  const { 
    salesNavUrl, 
    setSalesNavUrl, 
    salesNavMaxResults, 
    setSalesNavMaxResults, 
    budget, 
    activeAccount 
  } = useLeadImport();

  const remainingDaily = budget?.remaining ?? 150;
  const maxLimit = budget?.limit ?? 150;

  // Real-time URL validation state
  const validation = useMemo(() => {
    const trimmed = salesNavUrl.trim().toLowerCase();
    if (!trimmed) {
      return { status: "empty", message: "Paste a Sales Navigator or LinkedIn Search URL" };
    }
    if (trimmed.includes("/in/") || trimmed.includes("/sales/lead/") || trimmed.includes("/sales/people/")) {
      return { 
        status: "profile_warning", 
        message: "This is a single personal profile URL. Please switch to 'Raw Profiles' to import individuals." 
      };
    }
    if (trimmed.includes("linkedin.com/sales/search") || trimmed.includes("linkedin.com/sales/lead/search")) {
      return { status: "valid_sales_nav", message: "Valid Sales Navigator search query detected" };
    }
    if (trimmed.includes("linkedin.com/search/results/people") || trimmed.includes("linkedin.com/search/results")) {
      return { status: "valid_standard", message: "Valid LinkedIn people search query detected" };
    }
    if (trimmed.includes("linkedin.com")) {
      return { status: "unknown_linkedin", message: "Ensure this is a people search or Sales Nav search query" };
    }
    return { status: "invalid", message: "Please enter a valid LinkedIn URL" };
  }, [salesNavUrl]);

  const presetCounts = [25, 50, 100, Math.min(150, remainingDaily)].filter((v, i, arr) => arr.indexOf(v) === i && v > 0);

  return (
    <div className="animate-in fade-in max-w-xl space-y-5">
      {/* Search URL Input */}
      <div className="grid gap-2">
        <div className="flex items-center justify-between mb-0.5">
          <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider block">
            Sales Navigator or Search URL
          </label>
          {validation.status === "valid_sales_nav" && (
            <span className="flex items-center gap-1 text-[11px] font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full">
              <CheckCircle2 size={13} /> Sales Nav Query
            </span>
          )}
          {validation.status === "valid_standard" && (
            <span className="flex items-center gap-1 text-[11px] font-semibold text-blue-600 dark:text-blue-400 bg-blue-500/10 px-2 py-0.5 rounded-full">
              <CheckCircle2 size={13} /> LinkedIn Search Query
            </span>
          )}
          {validation.status === "profile_warning" && (
            <span className="flex items-center gap-1 text-[11px] font-semibold text-amber-700 dark:text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded-full">
              <AlertTriangle size={13} /> Single Profile
            </span>
          )}
        </div>

        <input 
          value={salesNavUrl} 
          onChange={e => setSalesNavUrl(e.target.value)} 
          placeholder="https://www.linkedin.com/sales/search/people?query=..." 
          className={`flex h-12 w-full rounded-lg border bg-background px-4 py-2 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring font-mono text-xs ${
            validation.status === "profile_warning" ? "border-amber-500/60 focus-visible:ring-amber-500" :
            validation.status.startsWith("valid") ? "border-emerald-500/50 focus-visible:ring-emerald-500" :
            "border-input"
          }`} 
        />

        {validation.status === "profile_warning" && (
          <p className="text-xs text-amber-600 dark:text-amber-400 flex items-center gap-1.5 mt-0.5">
            <AlertTriangle size={14} className="shrink-0" />
            {validation.message}
          </p>
        )}
      </div>

      {/* Leads Cap Selector */}
      <div className="p-4 rounded-xl border bg-muted/20 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <span className="text-xs font-bold text-foreground block">Max Leads to Scrape</span>
            <span className="text-[11px] text-muted-foreground">Paginates automatically with anti-ban stealth delays</span>
          </div>
          <span className="text-sm font-extrabold text-primary bg-primary/10 px-2.5 py-1 rounded-md">
            {salesNavMaxResults} leads
          </span>
        </div>

        <div className="flex items-center gap-2">
          {presetCounts.map(count => (
            <button
              key={count}
              type="button"
              onClick={() => setSalesNavMaxResults(count)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                salesNavMaxResults === count 
                  ? "bg-primary text-primary-foreground shadow-sm" 
                  : "bg-muted hover:bg-muted/80 text-muted-foreground hover:text-foreground"
              }`}
            >
              {count}
            </button>
          ))}
        </div>

        <input
          type="range"
          min={10}
          max={Math.min(150, Math.max(remainingDaily, 10))}
          step={5}
          value={salesNavMaxResults}
          onChange={e => setSalesNavMaxResults(Number(e.target.value))}
          className="w-full accent-primary h-1.5 bg-muted rounded-lg cursor-pointer"
        />
      </div>

      {/* Account & Daily Quota Status */}
      <div className="p-4 rounded-xl bg-card border flex items-center justify-between gap-4 text-xs">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-primary/10 text-primary">
            <UserCheck size={16} />
          </div>
          <div>
            <span className="font-semibold text-foreground block">
              {activeAccount?.account_name || activeAccount?.name || "Connected LinkedIn Account"}
            </span>
            <span className="text-[11px] text-muted-foreground">
              {remainingDaily} of {maxLimit} daily scrape credits remaining today
            </span>
          </div>
        </div>

        <div className="text-right">
          <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full inline-flex items-center gap-1">
            <ShieldCheck size={11} /> Stealth Safe
          </span>
        </div>
      </div>

      {/* Cloud Scraper Notice */}
      <div className="p-3.5 rounded-lg bg-primary/10 border border-primary/20 text-xs flex gap-3 items-start text-muted-foreground">
        <Compass className="shrink-0 mt-0.5 text-primary" size={17} />
        <p className="leading-relaxed">
          Cloud scraping runs asynchronously in the background using native Voyager session headers. Leads will begin appearing in your list shortly. You can safely close this modal after starting.
        </p>
      </div>
    </div>
  )
}
