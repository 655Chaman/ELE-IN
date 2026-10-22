import { useState, useMemo, useEffect } from "react"
import { motion, AnimatePresence } from "motion/react"
import { Linkedin } from "../icons/Linkedin"
import { 
  X, CheckCircle2, AlertCircle, ChevronRight, Check, 
  ShieldCheck, Terminal, Puzzle, ExternalLink, Lock, Zap
} from "lucide-react"
import { cn } from "@/lib/utils"
import { fetchWithAuth, fetcher } from "@/lib/apiClient"
import type { LinkedInAccount } from "@accounts/eiAccountsStore"
import useSWR from "swr"
import { usePaywall } from "@/contexts/PaywallContext"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

export default function ConnectModal({ onClose, onAdd }: { onClose: () => void; onAdd: (a: any) => void }) {
  const [step, setStep] = useState(1)
  const [extractionMethod, setExtractionMethod] = useState<"elein_extension" | "devtools" | "editthiscookie">("elein_extension")
  const [cookieJson, setCookieJson] = useState("")
  const [name, setName] = useState("")
  const [isWarmup, setIsWarmup] = useState(false)
  const [error, setError] = useState("")
  const [validating, setValidating] = useState(false)
  const [validated, setValidated] = useState<{ valid: boolean; profile_url?: string; name?: string; is_mock?: boolean } | null>(null)
  const [proxyId, setProxyId] = useState("")
  const { data: proxies } = useSWR("/api/elein/proxies/health", fetcher)
  const { data: billing } = useSWR<{ tier?: string; tier_limits?: { can_use_custom_proxies?: boolean } }>('/api/elein/workspaces/billing', fetcher)
  const { openPaywall } = usePaywall()
  const isProxyLocked = Boolean(billing && !billing.tier_limits?.can_use_custom_proxies)

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !validating) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, validating]);

  // ─── Three-Layer Paranoia: Client-side Cookie Normalizer & Live Format Sniffer ───
  const parsedCookieInfo = useMemo(() => {
    if (!cookieJson.trim()) return null
    let cleaned = cookieJson.trim()
    if (cleaned.startsWith("```")) {
      cleaned = cleaned.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "").trim()
    }

    // 1. Try JSON Array or Object
    try {
      const parsed = JSON.parse(cleaned)
      if (Array.isArray(parsed)) {
        const hasLiAt = parsed.some((c: any) => c.name === "li_at" && c.value)
        if (!hasLiAt) {
          return {
            valid: false,
            warning: "Valid JSON array, but missing 'li_at' cookie. Make sure you exported from linkedin.com.",
            normalized: cleaned,
            type: "json_missing_li_at"
          }
        }
        return {
          valid: true,
          badge: `Valid EditThisCookie export (${parsed.length} cookies, li_at verified)`,
          normalized: cleaned,
          type: "json_array",
          count: parsed.length
        }
      }
      if (typeof parsed === "object" && parsed !== null) {
        if (parsed.name === "li_at" && parsed.value) {
          const arr = [
            parsed,
            { domain: ".linkedin.com", name: "JSESSIONID", value: '"ajax:0123456789012345678"', path: "/", secure: true }
          ]
          return {
            valid: true,
            badge: "Single cookie object normalized to session array",
            normalized: JSON.stringify(arr),
            type: "single_object"
          }
        }
        if (parsed.li_at) {
          const arr = [
            { domain: ".linkedin.com", name: "li_at", value: String(parsed.li_at), path: "/", secure: true, httpOnly: true },
            { domain: ".linkedin.com", name: "JSESSIONID", value: parsed.JSESSIONID ? String(parsed.JSESSIONID) : '"ajax:0123456789012345678"', path: "/", secure: true }
          ]
          return {
            valid: true,
            badge: "Key-value dictionary normalized to session array",
            normalized: JSON.stringify(arr),
            type: "dict"
          }
        }
      }
    } catch {
      // Non-JSON formats handled below
    }

    // 2. Cookie header format (e.g. li_at=AQED...; JSESSIONID=...)
    if (cleaned.includes("li_at=")) {
      const matches = Array.from(cleaned.matchAll(/([a-zA-Z0-9_-]+)=([^;,\s]+)/g))
      if (matches.length > 0) {
        const cookies = matches.map(([_, cName, val]) => ({
          domain: ".linkedin.com",
          name: cName,
          value: val.replace(/^["']|["']$/g, ''),
          path: "/",
          secure: true,
          httpOnly: cName === "li_at"
        }))
        const hasLiAt = cookies.some(c => c.name === "li_at")
        if (hasLiAt) {
          return {
            valid: true,
            badge: `Extracted ${cookies.length} cookies from header format`,
            normalized: JSON.stringify(cookies),
            type: "cookie_header"
          }
        }
      }
    }

    // 3. Raw li_at string (alphanumeric / base64 without brackets)
    const token = cleaned.replace(/^["']|["']$/g, '').trim()
    if (token.length >= 20 && !token.includes("{") && !token.includes("[")) {
      const arr = [
        { domain: ".linkedin.com", name: "li_at", value: token, path: "/", secure: true, httpOnly: true },
        { domain: ".linkedin.com", name: "JSESSIONID", value: '"ajax:0123456789012345678"', path: "/", secure: true, httpOnly: false }
      ]
      return {
        valid: true,
        badge: `Raw li_at token detected (${token.length} chars) — auto-formatted`,
        normalized: JSON.stringify(arr),
        type: "raw_token"
      }
    }

    if (token.length > 0 && token.length < 20) {
      return {
        valid: false,
        warning: `Cookie value is too short (${token.length} chars). Real LinkedIn li_at tokens are typically 150+ chars.`,
        normalized: cleaned,
        type: "too_short"
      }
    }

    return {
      valid: false,
      error: "Unrecognized format. Please paste the EditThisCookie JSON export or your li_at cookie value.",
      normalized: cleaned,
      type: "invalid"
    }
  }, [cookieJson])

  const STEPS = [
    { 
      num: 1, 
      id: 'get-extension',
      title: "Choose Connection Method", 
      sub: "Pick whether you prefer the 1-click Chrome Extension or 15-second browser Developer Tools."
    },
    { 
      num: 2, 
      id: 'login-linkedin',
      title: "Log into LinkedIn", 
      sub: "Open LinkedIn in another browser tab and ensure you are logged into your outbound sender account.",
      action: { label: "Open LinkedIn in New Tab", href: "https://www.linkedin.com" }
    },
    { 
      num: 3, 
      id: 'export-cookies',
      title: "Extract Session Cookie", 
      sub: extractionMethod !== "devtools" 
        ? "Click the EditThisCookie icon in your browser toolbar and click Export."
        : "Inspect LinkedIn application cookies and copy the li_at value."
    },
    { 
      num: 4, 
      id: 'paste-connect',
      title: "Paste & Instant Connect", 
      sub: "Paste your session cookies or raw token below for real-time validation and safe proxy isolation."
    },
  ]

  const handleValidateAndConnect = async () => {
    if (!parsedCookieInfo?.valid) {
      setError(parsedCookieInfo?.warning || parsedCookieInfo?.error || "Please enter valid LinkedIn session cookies.")
      return
    }

    const payloadJson = parsedCookieInfo.normalized
    setValidating(true)
    setError("")
    setValidated(null)

    // Paranoia timeout guard (LinkedIn validation typically takes 3-8s; abort at 25s)
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 25000)

    try {
      const res = await fetchWithAuth("/api/elein/accounts/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_cookies_json: payloadJson, proxy_id: proxyId || undefined }),
        signal: controller.signal,
      })
      clearTimeout(timer)

      if (!res.ok) {
        const errPayload = await res.json().catch(() => null)
        throw new Error(errPayload?.detail || errPayload?.error || `Validation failed (HTTP ${res.status}).`)
      }

      const result = await res.json()

      if (!result.valid) {
        setValidating(false)
        setValidated({ valid: false })
        setError(result.error || "Cookie session is invalid or expired. Log into LinkedIn, refresh the page, and re-copy cookies.")
        return
      }

      setValidated(result)
      const accountName = name || result.name || "LinkedIn Account"
      const profileUrl = result.profile_url || ""

      const account = {
        name: accountName,
        profileUrl,
        cookieJson: payloadJson,
        isWarmup,
        proxyId: proxyId || undefined
      }
      await onAdd(account as any)
      setValidating(false)

      setTimeout(() => onClose(), 800)

    } catch (e: any) {
      clearTimeout(timer)
      setValidating(false)
      setValidated(null)
      if (e.name === 'AbortError') {
        setError("Validation timed out after 25s. The residential proxy tunnel or LinkedIn took too long to respond.")
      } else {
        setError(e.message || "Failed to reach server. Please check your network connection.")
      }
    }
  }

  const activeStep = STEPS.find(s => s.num === step) || STEPS[0]

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        transition={{ duration: 0.25, ease: "easeOut" }}
        className="w-full max-w-[44rem]"
      >
        <div className="rounded-xl bg-card border border-border text-card-foreground shadow-2xl overflow-hidden flex flex-col max-h-[calc(100vh-2rem)] pb-2">
          
          {/* Header */}
          <div className="px-8 pt-7 pb-3 shrink-0 relative border-b border-border">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center text-primary">
                <Linkedin size={20} />
              </div>
              <h2 className="text-[20px] font-bold text-foreground">
                Connect LinkedIn Account
              </h2>
            </div>
            
            <p className="text-[13px] text-muted-foreground mt-1">
              Zero passwords required. Connect securely in seconds via session cookies.
            </p>
            
            <button 
              type="button"
              aria-label="Close modal"
              onClick={onClose} 
              className="absolute top-6 right-6 w-8 h-8 rounded-full bg-muted/60 flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors focus:outline-none focus:ring-2 focus:ring-ring"
            >
              <X size={16} />
            </button>

            {/* Zero Password Security & Trust Reassurance Banner */}
            <div className="mt-3.5 mb-2 bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-3 flex flex-wrap sm:flex-nowrap items-center gap-3">
              <div className="w-7 h-7 rounded-lg bg-emerald-600 text-white flex items-center justify-center shrink-0">
                <ShieldCheck size={16} />
              </div>
              <div className="flex-1 text-xs text-foreground">
                <div className="font-semibold flex items-center gap-2 text-emerald-600 dark:text-emerald-400">
                  <span>Zero Password Architecture</span>
                  <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded-md bg-emerald-500/20 text-emerald-700 dark:text-emerald-300">Bank-Grade</span>
                </div>
                <p className="text-muted-foreground mt-0.5 leading-relaxed">
                  We never ask for or store your login password or 2FA codes. You can revoke access at any time with 1-click in your LinkedIn account settings.
                </p>
              </div>
            </div>
          </div>

          <div className="px-8 py-3 flex-1 flex flex-col overflow-y-auto">
            
            {/* Horizontal Stepper Circles */}
            <div className="flex items-center justify-between px-4 mb-6 mt-1">
              {STEPS.map((s) => {
                const isActive = step === s.num
                const isPast = step > s.num
                
                return (
                  <button 
                    type="button"
                    key={s.num} 
                    className={cn(
                      "cursor-pointer transition-all flex items-center gap-2 bg-transparent border-0 p-0 text-left focus:outline-none",
                      (isPast || isActive) ? "opacity-100" : "opacity-40 pointer-events-none"
                    )}
                    onClick={() => (isPast || isActive) && setStep(s.num)}
                  >
                    <div className={cn(
                      "w-8 h-8 rounded-full flex items-center justify-center text-[13px] font-bold transition-all duration-300",
                      isPast ? "bg-primary text-primary-foreground" : 
                      isActive ? "bg-primary text-primary-foreground shadow-sm" : 
                      "bg-muted text-muted-foreground"
                    )}>
                      {isPast ? <Check size={15} strokeWidth={3} /> : s.num}
                    </div>
                    <span className={cn(
                      "text-xs font-semibold hidden md:inline",
                      isActive ? "text-foreground" : "text-muted-foreground"
                    )}>
                      {s.title}
                    </span>
                  </button>
                )
              })}
            </div>

            {/* Active Step Content */}
            <AnimatePresence mode="wait">
              <motion.div
                key={step}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.18 }}
                className="flex-1 bg-card border border-border rounded-lg p-6 flex flex-col shadow-sm text-card-foreground"
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h3 className="font-bold text-[18px] text-foreground">
                      {activeStep.title}
                    </h3>
                    <p className="text-[14px] text-muted-foreground mt-1 leading-relaxed">
                      {activeStep.sub}
                    </p>
                  </div>
                </div>

                {/* Step 1: Choose extraction method */}
                {activeStep.num === 1 && (
                  <div className="mt-5 space-y-4">
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                      {/* Method 1: Ele-in Chrome Extension */}
                      <div 
                        role="button"
                        tabIndex={0}
                        onClick={() => setExtractionMethod("elein_extension")}
                        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") setExtractionMethod("elein_extension"); }}
                        className={cn(
                          "cursor-pointer p-4 rounded-lg border-2 transition-all text-left flex flex-col justify-between focus:outline-none focus:ring-2 focus:ring-ring",
                          extractionMethod === "elein_extension"
                            ? "border-primary bg-primary/5 shadow-sm"
                            : "border-border hover:border-primary/40 bg-card"
                        )}
                      >
                        <div>
                          <div className="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 flex items-center justify-center mb-3">
                            <Zap size={18} className="fill-emerald-600/20" />
                          </div>
                          <div className="font-bold text-sm text-foreground flex items-center gap-1.5 flex-wrap">
                            Ele-in Extension
                            <span className="text-[10px] bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 px-1.5 py-0.5 rounded-md font-semibold">1-Click Sync</span>
                          </div>
                          <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                            Zero manual copy-pasting. Syncs active session directly with encrypted handshake.
                          </p>
                        </div>
                        <div className="mt-3 text-xs font-semibold text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                          1-Click Setup <ChevronRight size={13} />
                        </div>
                      </div>

                      {/* Method 2: DevTools */}
                      <div 
                        role="button"
                        tabIndex={0}
                        onClick={() => setExtractionMethod("devtools")}
                        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") setExtractionMethod("devtools"); }}
                        className={cn(
                          "cursor-pointer p-4 rounded-lg border-2 transition-all text-left flex flex-col justify-between focus:outline-none focus:ring-2 focus:ring-ring",
                          extractionMethod === "devtools"
                            ? "border-primary bg-primary/5 shadow-sm"
                            : "border-border hover:border-primary/40 bg-card"
                        )}
                      >
                        <div>
                          <div className="w-8 h-8 rounded-lg bg-blue-500/10 text-blue-600 dark:text-blue-400 flex items-center justify-center mb-3">
                            <Terminal size={18} />
                          </div>
                          <div className="font-bold text-sm text-foreground flex items-center gap-1.5 flex-wrap">
                            Developer Tools
                            <span className="text-[10px] bg-blue-500/15 text-blue-700 dark:text-blue-300 px-1.5 py-0.5 rounded-md font-semibold">No Extension</span>
                          </div>
                          <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                            Press F12, copy the <code className="bg-muted px-1 rounded text-primary">li_at</code> cookie value directly. Takes 15 seconds.
                          </p>
                        </div>
                        <div className="mt-3 text-xs font-semibold text-blue-600 dark:text-blue-400 flex items-center gap-1">
                          Inspect & Copy <ChevronRight size={13} />
                        </div>
                      </div>

                      {/* Method 3: EditThisCookie */}
                      <div 
                        role="button"
                        tabIndex={0}
                        onClick={() => setExtractionMethod("editthiscookie")}
                        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") setExtractionMethod("editthiscookie"); }}
                        className={cn(
                          "cursor-pointer p-4 rounded-lg border-2 transition-all text-left flex flex-col justify-between focus:outline-none focus:ring-2 focus:ring-ring",
                          extractionMethod === "editthiscookie"
                            ? "border-primary bg-primary/5 shadow-sm"
                            : "border-border hover:border-primary/40 bg-card"
                        )}
                      >
                        <div>
                          <div className="w-8 h-8 rounded-lg bg-blue-500/10 text-blue-600 dark:text-blue-400 flex items-center justify-center mb-3">
                            <Puzzle size={18} />
                          </div>
                          <div className="font-bold text-sm text-foreground flex items-center gap-1.5 flex-wrap">
                            EditThisCookie
                            <span className="text-[10px] bg-blue-500/15 text-blue-700 dark:text-blue-300 px-1.5 py-0.5 rounded-md font-semibold">JSON Export</span>
                          </div>
                          <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                            Exports complete cookie list as JSON array for direct pasting into Step 4.
                          </p>
                        </div>
                        <div className="mt-3 text-xs font-semibold text-blue-600 dark:text-blue-400 flex items-center gap-1">
                          JSON Export <ChevronRight size={13} />
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center justify-between pt-2">
                      <button
                        type="button"
                        onClick={() => setStep(4)}
                        className="text-xs text-primary hover:text-primary/80 font-semibold flex items-center gap-1 transition-colors underline underline-offset-4 focus:outline-none"
                      >
                        Already have cookies copied? Jump to Paste & Connect →
                      </button>
                      <button 
                        type="button"
                        onClick={() => setStep(2)}
                        className="flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-sm font-semibold transition-all shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
                      >
                        Continue to Step 2 <ChevronRight size={15} />
                      </button>
                    </div>
                  </div>
                )}

                {/* Step 2: Open LinkedIn */}
                {activeStep.num === 2 && (
                  <div className="mt-5 space-y-4">
                    <div className="p-4 rounded-lg bg-muted/40 border border-border flex items-center justify-between">
                      <div className="space-y-1">
                        <div className="font-semibold text-sm text-foreground">Make sure you are logged in</div>
                        <p className="text-xs text-muted-foreground">
                          Open linkedin.com in another tab so your active session cookies are generated.
                        </p>
                      </div>
                      <a
                        href="https://www.linkedin.com"
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-card border border-border text-xs font-bold text-foreground hover:bg-muted transition-colors shadow-sm shrink-0 focus:outline-none focus:ring-2 focus:ring-ring"
                      >
                        Open LinkedIn <ExternalLink size={13} />
                      </a>
                    </div>

                    <div className="flex items-center justify-between pt-2">
                      <button
                        type="button"
                        onClick={() => setStep(4)}
                        className="text-xs text-primary hover:text-primary/80 font-semibold flex items-center gap-1 transition-colors underline underline-offset-4 focus:outline-none"
                      >
                        Skip straight to Paste JSON →
                      </button>
                      <button 
                        type="button"
                        onClick={() => setStep(3)}
                        className="flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-sm font-semibold transition-all shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
                      >
                        Next: How to Extract <ChevronRight size={15} />
                      </button>
                    </div>
                  </div>
                )}

                {/* Step 3: Visual Extraction Guide */}
                {activeStep.num === 3 && (
                  <div className="mt-4 space-y-4">
                    {extractionMethod === "elein_extension" ? (
                      <div className="space-y-3">
                        <div className="p-3.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-xs text-foreground">
                          <div className="font-bold mb-1 flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400">
                            <Zap size={14} className="fill-emerald-500 text-emerald-500" />
                            Zero-Touch Native 1-Click Synchronization
                          </div>
                          <div className="text-muted-foreground leading-relaxed">
                            No manual copy-pasting of sensitive tokens required. Simply open the Ele-in Chrome extension while logged into LinkedIn and press <strong>1-Click Sync</strong>.
                          </div>
                        </div>

                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 text-xs">
                          <div className="p-3 rounded-lg border border-border bg-card">
                            <div className="w-5 h-5 rounded-full bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 font-bold flex items-center justify-center mb-1.5">1</div>
                            <div className="font-semibold text-foreground">Load Extension</div>
                            <div className="text-muted-foreground text-[11px] mt-0.5">Load the Ele-in Chrome extension in your browser.</div>
                          </div>
                          <div className="p-3 rounded-lg border border-border bg-card">
                            <div className="w-5 h-5 rounded-full bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 font-bold flex items-center justify-center mb-1.5">2</div>
                            <div className="font-semibold text-foreground">Open LinkedIn</div>
                            <div className="text-muted-foreground text-[11px] mt-0.5">Ensure you are logged into your outbound sender profile.</div>
                          </div>
                          <div className="p-3 rounded-lg border border-border bg-card">
                            <div className="w-5 h-5 rounded-full bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 font-bold flex items-center justify-center mb-1.5">3</div>
                            <div className="font-semibold text-foreground">Click 1-Click Sync</div>
                            <div className="text-muted-foreground text-[11px] mt-0.5">Click the extension icon & hit Sync. Your account connects instantly!</div>
                          </div>
                        </div>
                      </div>
                    ) : extractionMethod === "editthiscookie" ? (
                      <div className="space-y-3">
                        <div className="flex items-center justify-between p-3 rounded-lg bg-blue-500/10 border border-blue-500/20">
                          <div className="text-xs text-foreground">
                            <strong>Step 3a:</strong> Install EditThisCookie from the official Chrome Web Store.
                          </div>
                          <a
                            href="https://chromewebstore.google.com/detail/editthiscookie-v3/ojfebgpkimhlhcblbalbfjblapadhbol"
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-semibold hover:bg-primary/90 transition-colors shrink-0 focus:outline-none focus:ring-2 focus:ring-ring"
                          >
                            Install Extension <ExternalLink size={12} />
                          </a>
                        </div>

                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 text-xs">
                          <div className="p-3 rounded-lg border border-border bg-card">
                            <div className="w-5 h-5 rounded-full bg-primary/10 text-primary font-bold flex items-center justify-center mb-1.5">1</div>
                            <div className="font-semibold text-foreground">Open LinkedIn</div>
                            <div className="text-muted-foreground text-[11px] mt-0.5">Navigate to your LinkedIn feed in the tab.</div>
                          </div>
                          <div className="p-3 rounded-lg border border-border bg-card">
                            <div className="w-5 h-5 rounded-full bg-primary/10 text-primary font-bold flex items-center justify-center mb-1.5">2</div>
                            <div className="font-semibold text-foreground">Click Extension</div>
                            <div className="text-muted-foreground text-[11px] mt-0.5">Click the cookie icon in your browser toolbar.</div>
                          </div>
                          <div className="p-3 rounded-lg border border-border bg-card">
                            <div className="w-5 h-5 rounded-full bg-primary/10 text-primary font-bold flex items-center justify-center mb-1.5">3</div>
                            <div className="font-semibold text-foreground">Click Export</div>
                            <div className="text-muted-foreground text-[11px] mt-0.5">Click the right-arrow export icon to copy cookies.</div>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-3">
                        <div className="p-3 rounded-lg bg-blue-500/10 border border-blue-500/20 text-xs text-foreground">
                          <strong>No Extension Required:</strong> Extract directly via Chrome, Edge, Brave, or Arc DevTools in 15 seconds.
                        </div>

                        <div className="space-y-2 text-xs">
                          <div className="flex items-start gap-2.5 p-2.5 rounded-lg border border-border bg-card text-foreground">
                            <span className="font-bold text-blue-500 shrink-0">1.</span>
                            <div>On linkedin.com, press <kbd className="px-1.5 py-0.5 bg-muted border border-border rounded font-mono text-[10px] text-foreground">F12</kbd> (or Right Click &gt; <strong>Inspect</strong>).</div>
                          </div>
                          <div className="flex items-start gap-2.5 p-2.5 rounded-lg border border-border bg-card text-foreground">
                            <span className="font-bold text-blue-500 shrink-0">2.</span>
                            <div>Switch to the <strong>Application</strong> tab (in Firefox/Safari: <strong>Storage</strong>) &gt; expand <strong>Cookies</strong> &gt; click <strong>https://www.linkedin.com</strong>.</div>
                          </div>
                          <div className="flex items-start gap-2.5 p-2.5 rounded-lg border border-border bg-card text-foreground">
                            <span className="font-bold text-blue-500 shrink-0">3.</span>
                            <div>Double-click the value under <code className="font-bold text-primary bg-muted px-1 py-0.5 rounded">li_at</code> and copy it (<kbd className="px-1 py-0.5 bg-muted border border-border rounded font-mono text-[10px] text-foreground">Cmd+C</kbd>). Paste it into Step 4!</div>
                          </div>
                        </div>
                      </div>
                    )}

                    <div className="flex items-center justify-between pt-2">
                      <button
                        type="button"
                        onClick={() => setExtractionMethod(extractionMethod === "elein_extension" ? "devtools" : "elein_extension")}
                        className="text-xs text-muted-foreground hover:text-foreground underline underline-offset-4 focus:outline-none"
                      >
                        Switch to {extractionMethod === "elein_extension" ? "DevTools manual method" : "Ele-in 1-Click Extension"}
                      </button>
                      <button 
                        type="button"
                        onClick={() => setStep(4)}
                        className="flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-sm font-semibold transition-all shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
                      >
                        Continue to Step 4 <ChevronRight size={15} />
                      </button>
                    </div>
                  </div>
                )}

                {/* Step 4: Paste & Connect */}
                {activeStep.num === 4 && (
                  <div className="mt-3 space-y-4">
                    {/* Row 1: Account Label & Proxy Selection */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 items-end">
                      <div className="space-y-1">
                        <label className="text-xs font-bold text-foreground">
                          Account Label <span className="text-muted-foreground font-normal">(Optional)</span>
                        </label>
                        <input
                          value={name}
                          onChange={e => setName(e.target.value)}
                          placeholder='e.g. John Doe - Growth'
                          className="w-full rounded-lg bg-background border border-input px-3.5 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all"
                        />
                      </div>
                      
                      <div className="space-y-1">
                        <label className="text-xs font-bold text-foreground flex items-center justify-between">
                          <span className="flex items-center gap-1">
                            <span>Residential Proxy</span>
                            {isProxyLocked && <Lock size={10} className="text-amber-500" />}
                          </span>
                          {isProxyLocked ? (
                            <span className="text-[10px] text-amber-600 font-semibold">Pro: Custom Pool</span>
                          ) : (
                            <span className="text-[10px] text-emerald-600 font-semibold">4G Dedicated</span>
                          )}
                        </label>
                        <Select
                          value={proxyId}
                          onValueChange={val => {
                            if (val !== "" && isProxyLocked) {
                              openPaywall({ featureName: "Custom Residential Proxy Rotation" })
                              return
                            }
                            setProxyId(val)
                          }}
                        >
                          <SelectTrigger className="w-full bg-background border-input px-3.5 py-2.5 text-xs text-foreground h-10">
                            <SelectValue placeholder="Auto-Assign Geolocation Proxy (Recommended)" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="">Auto-Assign Geolocation Proxy (Recommended)</SelectItem>
                            {proxies?.map((p: any) => (
                              <SelectItem key={p.id} value={p.id}>
                                {p.provider || "Residential"} — {p.country_code || "US"} ({p.host}:{p.port})
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                    
                    {/* Row 2: Cookie Input Area */}
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <label className="text-xs font-bold text-foreground flex items-center gap-1.5">
                          <span>LinkedIn Session Cookies / li_at Token</span>
                          <span className="text-[10px] bg-muted text-muted-foreground px-1.5 py-0.5 rounded font-normal">Auto-Detecting</span>
                        </label>
                        <button
                          type="button"
                          onClick={async () => {
                            try {
                              const text = await navigator.clipboard.readText()
                              if (text) {
                                setCookieJson(text.trim())
                                setError("")
                                setValidated(null)
                              }
                            } catch {
                              // Clipboard permission rejected
                            }
                          }}
                          className="text-xs font-semibold text-primary hover:text-primary/80 flex items-center gap-1 transition-colors focus:outline-none"
                        >
                          Paste from Clipboard
                        </button>
                      </div>
                      
                      <textarea
                        value={cookieJson}
                        onChange={e => { setCookieJson(e.target.value); setError(""); setValidated(null) }}
                        rows={3}
                        placeholder={'Paste EditThisCookie JSON export OR paste raw li_at value (AQEDA...)'}
                        className="w-full rounded-lg bg-background border border-input px-3.5 py-2.5 text-xs font-mono text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary resize-none transition-all"
                      />

                      {/* Format sniffer status badge */}
                      {parsedCookieInfo && (
                        <div className={cn(
                          "text-xs px-3 py-1.5 rounded-lg flex items-center gap-2 font-medium transition-all",
                          parsedCookieInfo.valid 
                            ? "bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-500/20" 
                            : parsedCookieInfo.warning 
                              ? "bg-amber-50 text-amber-700 border border-amber-200 dark:bg-amber-500/10 dark:text-amber-400 dark:border-amber-500/20" 
                              : "bg-destructive/10 text-destructive border border-destructive/20"
                        )}>
                          {parsedCookieInfo.valid ? (
                            <>
                              <CheckCircle2 size={13} className="text-emerald-600 dark:text-emerald-400 shrink-0" />
                              <span>{parsedCookieInfo.badge}</span>
                            </>
                          ) : parsedCookieInfo.warning ? (
                            <>
                              <AlertCircle size={13} className="text-amber-600 dark:text-amber-400 shrink-0" />
                              <span>{parsedCookieInfo.warning}</span>
                            </>
                          ) : (
                            <>
                              <AlertCircle size={13} className="text-destructive shrink-0" />
                              <span>{parsedCookieInfo.error}</span>
                            </>
                          )}
                        </div>
                      )}
                    </div>
                    
                    {/* Row 3: 30-Day Warmup Mode Toggle */}
                    <div className="p-3 rounded-lg border border-border bg-muted/30">
                      <label className="flex items-start gap-3 cursor-pointer group">
                        <div className={cn("w-5 h-5 mt-0.5 rounded-md border-[1.5px] flex items-center justify-center transition-colors shrink-0",
                          isWarmup ? "bg-primary border-primary" : "border-border bg-background group-hover:border-primary"
                        )}>
                          {isWarmup && <Check size={13} className="text-primary-foreground" strokeWidth={3.5} />}
                        </div>
                        <input 
                          type="checkbox" 
                          className="hidden" 
                          checked={isWarmup} 
                          onChange={(e) => setIsWarmup(e.target.checked)} 
                        />
                        <div className="space-y-0.5">
                          <span className="text-xs font-bold text-foreground select-none block">
                            Cold or New Account (Enable 30-Day Safe Warmup Mode)
                          </span>
                          <span className="text-[11px] text-muted-foreground block leading-relaxed">
                            Ramps daily limits gradually from 5 to 40 connection requests over 30 days to protect account reputation.
                          </span>
                        </div>
                      </label>
                    </div>

                    {/* Error & Validation Feedback */}
                    {error && (
                      <div className="flex items-center gap-2.5 p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-xs">
                        <AlertCircle size={16} className="shrink-0" />
                        <p className="font-medium leading-relaxed">{error}</p>
                      </div>
                    )}

                    {validating && (
                      <div className="flex items-center gap-2.5 p-3 rounded-lg bg-primary/5 border border-primary/20 text-primary text-xs">
                        <div className="w-4 h-4 rounded-full border-2 border-primary border-t-transparent animate-spin shrink-0" />
                        <p className="font-semibold">Validating session with LinkedIn Voyager API via residential proxy… (~4s)</p>
                      </div>
                    )}

                    {validated?.valid && (
                      <div className="flex items-center gap-3 p-3.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-700 dark:text-emerald-300">
                        <div className="w-8 h-8 rounded-full bg-emerald-500/20 flex items-center justify-center shrink-0">
                          <CheckCircle2 size={18} className="text-emerald-600 dark:text-emerald-400" />
                        </div>
                        <div className="min-w-0">
                          <p className="text-xs font-bold">
                            LinkedIn Account Verified &amp; Connected!
                          </p>
                          {validated.name && (
                            <p className="text-[11px] font-medium truncate opacity-90">
                              {validated.name} {validated.profile_url ? `(${validated.profile_url})` : ''}
                            </p>
                          )}
                        </div>
                      </div>
                    )}
                    
                    {/* Submit Button */}
                    <div className="pt-1">
                      <button
                        type="button"
                        onClick={handleValidateAndConnect}
                        disabled={validating || !parsedCookieInfo?.valid}
                        className="w-full flex items-center justify-center gap-2 px-6 py-3 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-bold shadow-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-ring"
                      >
                        {validating ? "Validating & Securing..." : "Validate & Connect Account"}
                      </button>
                    </div>
                  </div>
                )}
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      </motion.div>
    </div>
  )
}
