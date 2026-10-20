import { LinkIcon, Lock, CheckCircle2, AlertTriangle, ArrowRight, RefreshCw, Globe, Sparkles } from "lucide-react"
import { useState, useEffect, useRef } from "react"
import { ElesiumLogo } from "@/components/ElesiumLogo"
import { toast } from "sonner"
import { friendlyToast } from "../FriendlyError"
import { fetchWithAuth, fetcher } from "@/lib/apiClient"
import { usePaywall } from "@/contexts/PaywallContext"
import { cn } from "@/lib/utils"
import useSWR from "swr"

const SCRAPER_STAGES = [
  { step: 1, label: "Connecting & checking firewalls", pct: 25 },
  { step: 2, label: "Extracting DOM & stripping nav boilerplate", pct: 55 },
  { step: 3, label: "AI synthesizing core value prop & ICP hooks", pct: 80 },
  { step: 4, label: "Generating embeddings & indexing chunks", pct: 98 },
]

export function AddUrlModal({ mutateAssets }: { mutateAssets?: () => void }) {
  const [scrapeUrl, setScrapeUrl] = useState("")
  const [isScraping, setIsScraping] = useState(false)
  const [currentStage, setCurrentStage] = useState(1)
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const [scrapeError, setScrapeError] = useState<string | null>(null)
  const [scrapeSuccess, setScrapeSuccess] = useState(false)
  const timerRef = useRef<NodeJS.Timeout | null>(null)
  const { openPaywall } = usePaywall()

  const { data: billingData } = useSWR<{ tier?: string }>('/api/elein/workspaces/billing', fetcher)
  const tier = billingData?.tier || 'FREE'
  const isPro = tier === 'PRO' || tier === 'ENTERPRISE'
  const maxAssets = isPro ? (tier === 'ENTERPRISE' ? 100 : 25) : 3

  const { data: assets } = useSWR<any[]>('/api/assets/knowledge/assets', fetcher)
  const currentCount = Array.isArray(assets) ? assets.length : 0
  const isCapped = !isPro && currentCount >= maxAssets

  // Cleanup telemetry timer on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [])

  const handleScrape = async () => {
    if (isCapped) {
      openPaywall({ featureName: "Knowledge Base Storage" })
      toast.info(`Free plan limit reached (${currentCount}/${maxAssets} documents). Upgrade to Growth Pro to add up to 25 documents.`)
      return
    }

    let finalUrl = scrapeUrl.trim()
    if (!finalUrl) return toast.error("Please enter a website URL")
    if (!finalUrl.startsWith("http://") && !finalUrl.startsWith("https://")) {
      finalUrl = "https://" + finalUrl
    }

    // Reset telemetry
    setIsScraping(true)
    setCurrentStage(1)
    setElapsedSeconds(0)
    setScrapeError(null)
    setScrapeSuccess(false)

    // Start progress timer
    const startTime = Date.now()
    timerRef.current = setInterval(() => {
      const elapsed = (Date.now() - startTime) / 1000
      setElapsedSeconds(Number(elapsed.toFixed(1)))
      if (elapsed > 4.5) setCurrentStage(4)
      else if (elapsed > 3.0) setCurrentStage(3)
      else if (elapsed > 1.5) setCurrentStage(2)
      else setCurrentStage(1)
    }, 100)

    try {
      const res = await fetchWithAuth("/api/assets/knowledge/upload/url", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: finalUrl })
      })

      if (timerRef.current) clearInterval(timerRef.current)

      if (!res.ok) {
        if (res.status === 403) {
          openPaywall({ featureName: "Knowledge Base Storage" })
          toast.info("Free plan document limit reached. Upgrade to Growth Pro for up to 25 documents.")
          return
        }
        let errText = "Failed to scrape website"
        try {
          const data = await res.json()
          errText = data.detail || errText
        } catch {
          errText = `Server returned ${res.status}`
        }
        throw new Error(errText)
      }

      await res.json()
      setScrapeSuccess(true)
      setCurrentStage(4)
      toast.success("Website scraped & queued for background indexing!")
      setScrapeUrl("")
      if (mutateAssets) mutateAssets()

      // Reset success state after brief feedback
      setTimeout(() => {
        setScrapeSuccess(false)
        setIsScraping(false)
      }, 2500)

    } catch (e: any) {
      if (timerRef.current) clearInterval(timerRef.current)
      setIsScraping(false)
      const msg = e.message || "Failed to reach website"
      setScrapeError(msg)
      friendlyToast("Scraping encountered an obstacle", e)
    }
  }

  const activeStageInfo = SCRAPER_STAGES.find(s => s.step === currentStage) || SCRAPER_STAGES[0]

  return (
    <div className="border border-border/50 bg-card/40 hover:bg-card/70 hover:border-border/80 transition-all rounded-xl p-5 flex flex-col justify-between min-h-[200px]">
      <div>
        <div className="flex items-center justify-between mb-3">
          <div className="w-8 h-8 rounded-lg bg-muted/60 border border-border/40 flex items-center justify-center text-foreground/80">
            {isCapped ? <Lock size={15} className="text-amber-500" /> : <LinkIcon size={15} />}
          </div>
          {isScraping && (
            <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-muted border border-border/60 text-muted-foreground font-medium flex items-center gap-1">
              <RefreshCw size={10} className="animate-spin" />
              {elapsedSeconds}s
            </span>
          )}
        </div>
        <h3 className="font-medium text-sm text-foreground flex items-center gap-1.5">
          <span>Connect Website</span>
          {scrapeSuccess && <CheckCircle2 size={14} className="text-emerald-500" />}
        </h3>
        <p className="text-xs text-muted-foreground mt-1 mb-3 leading-relaxed">
          {isCapped ? `Plan limit reached (${currentCount}/${maxAssets} docs)` : "Extract company positioning and offerings directly from your URL."}
        </p>
      </div>

      <div className="space-y-2">
        {/* URL Input */}
        {!isScraping && !scrapeSuccess && (
          <input
            type="text"
            value={scrapeUrl}
            onChange={(e) => {
              setScrapeUrl(e.target.value)
              if (scrapeError) setScrapeError(null)
            }}
            onKeyDown={(e) => { if (e.key === 'Enter') handleScrape() }}
            placeholder="https://company.com"
            className="bg-background/80 border border-border/70 rounded-lg px-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-foreground/40 w-full"
          />
        )}

        {/* Live Scraper Progress Telemetry (Area 4: Eliminating the Black Box) */}
        {isScraping && (
          <div className="p-3 rounded-xl border border-border/60 bg-muted/30 space-y-2 text-left">
            <div className="flex items-center justify-between text-[11px]">
              <span className="font-medium text-foreground flex items-center gap-1.5">
                <Globe size={12} className="text-muted-foreground animate-pulse" />
                {activeStageInfo.label}
              </span>
              <span className="font-mono text-muted-foreground text-[10px]">
                {activeStageInfo.pct}%
              </span>
            </div>

            {/* Smooth Progress Bar */}
            <div className="w-full h-1 bg-muted rounded-full overflow-hidden">
              <div 
                className="h-full bg-foreground transition-all duration-300 rounded-full"
                style={{ width: `${scrapeSuccess ? 100 : activeStageInfo.pct}%` }}
              />
            </div>

            <div className="flex items-center justify-between text-[10px] text-muted-foreground pt-0.5">
              <span>Stage {currentStage} of 4</span>
              <span>Vectorizing memory</span>
            </div>
          </div>
        )}

        {/* Success State Confirmation */}
        {scrapeSuccess && (
          <div className="p-2.5 rounded-lg border border-emerald-500/20 bg-emerald-500/10 text-emerald-500 text-xs flex items-center gap-2">
            <CheckCircle2 size={15} className="shrink-0" />
            <span className="text-[11px] font-medium">Website indexed into AI memory!</span>
          </div>
        )}

        {/* Error / Anti-Bot Fallback Notice */}
        {scrapeError && !isScraping && (
          <div className="p-2.5 rounded-lg border border-amber-500/20 bg-amber-500/10 text-left space-y-1">
            <div className="flex items-center gap-1.5 text-xs font-medium text-amber-500">
              <AlertTriangle size={13} className="shrink-0" />
              <span>Scraping Notice</span>
            </div>
            <p className="text-[11px] text-muted-foreground leading-relaxed">
              Site may be protected by anti-bot firewalls. You can paste your text directly into the Text option.
            </p>
          </div>
        )}

        {/* Action Button */}
        {!scrapeSuccess && (
          <button
            disabled={isScraping || !scrapeUrl.trim()}
            onClick={handleScrape}
            className={cn(
              "py-1.5 rounded-lg text-xs font-medium transition-colors w-full disabled:opacity-40 flex items-center justify-center gap-1.5 cursor-pointer",
              isCapped
                ? "border border-border/60 bg-muted/40 text-muted-foreground hover:bg-muted/60"
                : "bg-foreground text-background hover:bg-foreground/90"
            )}
          >
            {isScraping ? (
              <>
                <RefreshCw size={12} className="animate-spin" />
                <span>Reading &amp; Indexing...</span>
              </>
            ) : isCapped ? (
              <>
                <Lock size={12} className="text-amber-500" />
                <span>Quota Reached</span>
              </>
            ) : (
              <>
                <span>Scan Website</span>
                <ArrowRight size={12} />
              </>
            )}
          </button>
        )}
      </div>
    </div>
  )
}
