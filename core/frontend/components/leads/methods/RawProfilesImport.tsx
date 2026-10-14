import { useMemo } from "react"
import { useLeadImport } from "../LeadImportContext"
import { usePaywall } from "@/contexts/PaywallContext"
import { Rocket, ArrowRight, Compass, AlertCircle, Sparkles } from "lucide-react"
import { toast } from "sonner"

export function RawProfilesImport() {
  const { urlList, setUrlList, billing, name, setMethod, setSalesNavUrl } = useLeadImport();
  const { openPaywall } = usePaywall();
  const isPro = billing?.tier === 'PRO' || billing?.tier === 'ENTERPRISE';

  const lines = useMemo(() => {
    return urlList.split("\n").map(l => l.trim()).filter(Boolean);
  }, [urlList]);

  const urlCount = lines.length;

  // Paranoia Layer 2: Detect accidental search query URLs in profile input
  const detectedSearchUrls = useMemo(() => {
    return lines.filter(l => 
      l.toLowerCase().includes("linkedin.com/sales/search") || 
      l.toLowerCase().includes("linkedin.com/search/results") ||
      l.toLowerCase().includes("linkedin.com/sales/lead/search") ||
      l.toLowerCase().includes("/search/results/people")
    );
  }, [lines]);

  // Detect non-profile URLs (company, jobs)
  const invalidUrls = useMemo(() => {
    return lines.filter(l => {
      const lower = l.toLowerCase();
      return lower.includes("linkedin.com/company/") || 
             lower.includes("linkedin.com/jobs/") ||
             lower.includes("linkedin.com/feed");
    });
  }, [lines]);

  const handleTransferToSalesNav = (searchUrl: string) => {
    setSalesNavUrl(searchUrl);
    // Remove search URL from raw profiles list
    const remaining = lines.filter(l => l !== searchUrl).join("\n");
    setUrlList(remaining);
    setMethod("sales_nav");
    toast.success("Transferred search query to Sales Navigator scraper!");
  };

  const handleRemoveInvalid = () => {
    const valid = lines.filter(l => !detectedSearchUrls.includes(l) && !invalidUrls.includes(l));
    setUrlList(valid.join("\n"));
    toast.info("Removed invalid and search URLs from list.");
  };

  return (
    <div className="animate-in fade-in max-w-xl space-y-4">
      {/* Search URL Interception Alert (Paranoia Layer 2) */}
      {detectedSearchUrls.length > 0 && (
        <div className="p-4 rounded-xl bg-primary/10 border border-primary/25 space-y-2.5 shadow-sm">
          <div className="flex items-center gap-2 text-primary font-bold text-xs">
            <Compass size={17} className="animate-pulse" />
            <span>Search / Sales Navigator Query Detected</span>
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed">
            You pasted a search query containing multiple leads. Individual profile lists cannot process search queries directly. Would you like to switch to the automated Sales Navigator scraper to pull these leads?
          </p>
          <div className="flex items-center gap-2 pt-1 flex-wrap">
            <button
              type="button"
              onClick={() => handleTransferToSalesNav(detectedSearchUrls[0])}
              className="px-3 py-1.5 rounded-lg bg-primary text-primary-foreground font-semibold text-xs flex items-center gap-1.5 hover:opacity-90 transition-all shadow-sm"
            >
              <Sparkles size={13} />
              <span>Transfer to Sales Navigator Import</span>
            </button>
            <button
              type="button"
              onClick={handleRemoveInvalid}
              className="px-2.5 py-1.5 rounded-lg bg-muted text-muted-foreground hover:text-foreground text-xs transition-colors"
            >
              Remove Search URL
            </button>
          </div>
        </div>
      )}

      {/* Invalid URLs Alert */}
      {invalidUrls.length > 0 && (
        <div className="p-3 rounded-xl bg-destructive/10 border border-destructive/20 flex items-start gap-2.5 text-xs text-destructive">
          <AlertCircle size={15} className="shrink-0 mt-0.5" />
          <div className="flex-1">
            <span className="font-semibold block">Non-profile URLs detected</span>
            <span className="text-[11px] opacity-90 block">
              {invalidUrls.length} URL(s) point to company or job pages. Only individual profiles (/in/username) can be imported.
            </span>
          </div>
        </div>
      )}

      {urlCount > 50 && !isPro && (
        <div className="p-3.5 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-2.5">
            <div className="p-1.5 rounded-lg bg-primary/20 text-primary">
              <Rocket size={15} />
            </div>
            <div>
              <span className="font-bold text-foreground block">
                {urlCount.toLocaleString()} profiles detected
              </span>
              <span className="text-[11px] text-muted-foreground">
                Free Tier is limited to 1 active campaign.
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={() => openPaywall({ 
              campaignName: name || "Profile List Outreach", 
              featureName: "Multi-Campaign Scale" 
            })}
            className="px-3 py-1.5 rounded-lg bg-foreground text-background font-bold text-xs hover:opacity-90 transition-all shrink-0 flex items-center gap-1.5"
          >
            <span>Upgrade</span>
            <ArrowRight size={12} />
          </button>
        </div>
      )}

      <div className="grid gap-2">
        <div className="flex items-center justify-between mb-1">
          <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider block">LinkedIn Profile URLs</label>
          <span className="text-[11px] uppercase font-bold text-primary tracking-wider bg-primary/10 px-3 py-1 rounded-full">
            {urlCount} URLs detected
          </span>
        </div>
        <textarea 
          value={urlList} 
          onChange={e => setUrlList(e.target.value)} 
          rows={10} 
          placeholder={"Paste LinkedIn URLs here, one per line:\n\nhttps://linkedin.com/in/person-one\nhttps://linkedin.com/in/person-two"} 
          className="flex w-full rounded-lg border border-input bg-background px-4 py-3 text-sm font-mono shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-none leading-relaxed" 
        />
      </div>
    </div>
  )
}
