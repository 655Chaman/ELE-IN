import { LinkIcon } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"
import { fetchWithAuth } from "@/lib/apiClient"

export function AddUrlModal() {
  const [scrapeUrl, setScrapeUrl] = useState("")
  const [isScraping, setIsScraping] = useState(false)

  const handleScrape = async () => {
    let finalUrl = scrapeUrl.trim();
    if (!finalUrl) return toast.error("Please enter a URL");
    if (!finalUrl.startsWith("http://") && !finalUrl.startsWith("https://")) {
        finalUrl = "https://" + finalUrl;
    }
    try {
      setIsScraping(true);
      const res = await fetchWithAuth("/api/assets/knowledge/upload/url", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: finalUrl })
      });
      if (!res.ok) {
         let errText = "Failed to scrape URL";
         try {
             const data = await res.json();
             errText = data.detail || errText;
         } catch(err) {
             errText = `Server returned ${res.status}`;
         }
         throw new Error(errText);
      }
      await res.json();
      toast.success("URL submitted! Processing in background...");
      setScrapeUrl("");
    } catch (e: any) {
      toast.error(e.message || "Failed to submit URL");
    } finally {
      setIsScraping(false);
    }
  };

  return (
    <div className="border border-slate-200 dark:border-border/50 bg-slate-50 dark:bg-muted/10 rounded-3xl p-6 flex flex-col justify-between">
      <div>
        <LinkIcon size={20} className="text-foreground mb-2" />
        <h3 className="font-semibold text-sm text-foreground">Add your website</h3>
        <p className="text-xs text-muted-foreground mt-1 mb-3">We'll read it automatically.</p>
      </div>
      <div>
        <input
          type="text"
          value={scrapeUrl}
          onChange={(e) => setScrapeUrl(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') handleScrape(); }}
          placeholder="domain.com"
          className="bg-white dark:bg-background border border-slate-200 dark:border-border/50 rounded-xl px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500 w-full mb-2 shadow-sm"
        />
        <button
          disabled={isScraping}
          onClick={handleScrape}
          className="bg-foreground text-background py-2 rounded-xl text-xs font-semibold hover:bg-foreground/90 transition-colors w-full disabled:opacity-50"
        >
          {isScraping ? "Reading..." : "Read Website"}
        </button>
      </div>
    </div>
  )
}
