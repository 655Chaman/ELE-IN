import { useState, useMemo } from "react"
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
        <div className="rounded-[24px] bg-white shadow-2xl overflow-hidden flex flex-col max-h-[calc(100vh-2rem)] border border-gray-100 pb-2">
          
          {/* Header */}
          <div className="px-8 pt-7 pb-3 shrink-0 relative border-b border-gray-100">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center text-primary">
                <Linkedin size={20} />
              </div>
              <h2 className="text-[20px] font-bold text-gray-900">
                Connect LinkedIn Account
              </h2>
            </div>
            
            <p className="text-[13px] text-gray-500 mt-1">
              Zero passwords required. Connect securely in seconds via session cookies.
            </p>
            
            <button 
              onClick={onClose} 
              className="absolute top-6 right-6 w-8 h-8 rounded-full bg-gray-50 flex items-center justify-center text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
            >
              <X size={16} />
            </button>

            {/* Zero Password Security & Trust Reassurance Banner */}
            <div className="mt-3.5 mb-2 bg-gradient-to-r from-emerald-50 via-teal-50 to-emerald-50 border border-emerald-200/80 rounded-xl p-3 flex flex-wrap sm:flex-nowrap items-center gap-3">
              <div className="w-7 h-7 rounded-lg bg-emerald-600 text-white flex items-center justify-center shrink-0">
                <ShieldCheck size={16} />
              </div>
              <div className="flex-1 text-xs text-emerald-950">
                <div className="font-semibold flex items-center gap-2 text-emerald-900">
                  <span>Zero Password Architecture</span>
                  <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-emerald-200/80 text-emerald-800">Bank-Grade</span>
                </div>
                <p className="text-emerald-700 mt-0.5 leading-relaxed">
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
                  <div 
                    key={s.num} 
                    className={cn(
                      "cursor-pointer transition-all flex items-center gap-2",
                      (isPast || isActive) ? "opacity-100" : "opacity-40 pointer-events-none"
                    )}
                    onClick={() => (isPast || isActive) && setStep(s.num)}
                  >
                    <div className={cn(
                      "w-8 h-8 rounded-full flex items-center justify-center text-[13px] font-bold transition-all duration-300",
                      isPast ? "bg-primary text-white" : 
                      isActive ? "bg-primary text-white shadow-[0_4px_12px_rgba(0,166,62,0.35)]" : 
                      "bg-gray-100 text-gray-500"
                    )}>
                      {isPast ? <Check size={15} strokeWidth={3} /> : s.num}
                    </div>
                    <span className={cn(
                      "text-xs font-semibold hidden md:inline",
                      isActive ? "text-gray-900" : "text-gray-400"
                    )}>
                      {s.title}
                    </span>
                  </div>
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
                className="flex-1 bg-white border border-gray-100 rounded-[16px] p-6 flex flex-col shadow-sm"
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h3 className="font-bold text-[18px] text-gray-900">
                      {activeStep.title}
                    </h3>
                    <p className="text-[14px] text-gray-500 mt-1 leading-relaxed">
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
                        onClick={() => setExtractionMethod("elein_extension")}
                        className={cn(
                          "cursor-pointer p-4 rounded-xl border-2 transition-all text-left flex flex-col justify-between",
                          extractionMethod === "elein_extension"
                            ? "border-primary bg-primary/5 shadow-sm"
                            : "border-gray-200 hover:border-gray-300 bg-white"
                        )}
                      >
                        <div>
                          <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center mb-3">
                            <Zap size={18} className="fill-emerald-600/20" />
                          </div>
                          <div className="font-bold text-sm text-gray-900 flex items-center gap-1.5 flex-wrap">
                            Ele-in Extension
                            <span className="text-[10px] bg-emerald-100 text-emerald-800 px-1.5 py-0.5 rounded font-semibold">1-Click Sync</span>
                          </div>
                          <p className="text-xs text-gray-500 mt-1 leading-relaxed">
                            Zero manual copy-pasting. Syncs active session directly with encrypted handshake.
                          </p>
                        </div>
                        <div className="mt-3 text-xs font-semibold text-emerald-600 flex items-center gap-1">
                          1-Click Setup <ChevronRight size={13} />
                        </div>
                      </div>

                      {/* Method 2: DevTools */}
                      <div 
                        onClick={() => setExtractionMethod("devtools")}
                        className={cn(
                          "cursor-pointer p-4 rounded-xl border-2 transition-all text-left flex flex-col justify-between",
                          extractionMethod === "devtools"
                            ? "border-primary bg-primary/5 shadow-sm"
                            : "border-gray-200 hover:border-gray-300 bg-white"
                        )}
                      >
                        <div>
                          <div className="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center mb-3">
                            <Terminal size={18} />
                          </div>
                          <div className="font-bold text-sm text-gray-900 flex items-center gap-1.5 flex-wrap">
                            Developer Tools
                            <span className="text-[10px] bg-blue-100 text-blue-800 px-1.5 py-0.5 rounded font-semibold">No Extension</span>
                          </div>
                          <p className="text-xs text-gray-500 mt-1 leading-relaxed">
                            Press F12, copy the <code className="bg-gray-100 px-1 rounded text-blue-700">li_at</code> cookie value directly. Takes 15 seconds.
                          </p>
                        </div>
                        <div className="mt-3 text-xs font-semibold text-blue-600 flex items-center gap-1">
                          Inspect & Copy <ChevronRight size={13} />
                        </div>
                      </div>

                      {/* Method 3: EditThisCookie */}
                      <div 
                        onClick={() => setExtractionMethod("editthiscookie")}
                        className={cn(
                          "cursor-pointer p-4 rounded-xl border-2 transition-all text-left flex flex-col justify-between",
                          extractionMethod === "editthiscookie"
                            ? "border-primary bg-primary/5 shadow-sm"
                            : "border-gray-200 hover:border-gray-300 bg-white"
                        )}
                      >
                        <div>
                          <div className="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center mb-3">
                            <Puzzle size={18} />
                          </div>
                          <div className="font-bold text-sm text-gray-900 flex items-center gap-1.5 flex-wrap">
                            EditThisCookie
                            <span className="text-[10px] bg-blue-100 text-blue-800 px-1.5 py-0.5 rounded font-semibold">JSON Export</span>
                          </div>
                          <p className="text-xs text-gray-500 mt-1 leading-relaxed">
                            Exports complete cookie list as JSON array for direct pasting into Step 4.
                          </p>
                        </div>
                        <div className="mt-3 text-xs font-semibold text-blue-600 flex items-center gap-1">
                          JSON Export <ChevronRight size={13} />
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center justify-between pt-2">
                      <button
                        type="button"
                        onClick={() => setStep(4)}
                        className="text-xs text-primary hover:text-primary/80 font-semibold flex items-center gap-1 transition-colors underline underline-offset-4"
                      >
                        Already have cookies copied? Jump to Paste & Connect →
                      </button>
                      <button 
                        onClick={() => setStep(2)}
                        className="flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-gray-900 hover:bg-gray-800 text-white text-sm font-semibold transition-all shadow-sm"
                      >
                        Continue to Step 2 <ChevronRight size={15} />
                      </button>
                    </div>
                  </div>
                )}

                {/* Step 2: Open LinkedIn */}
                {activeStep.num === 2 && (
                  <div className="mt-5 space-y-4">
                    <div className="p-4 rounded-xl bg-gray-50 border border-gray-200 flex items-center justify-between">
                      <div className="space-y-1">
                        <div className="font-semibold text-sm text-gray-900">Make sure you are logged in</div>
                        <p className="text-xs text-gray-500">
                          Open linkedin.com in another tab so your active session cookies are generated.
                        </p>
                      </div>
                      <a
                        href="https://www.linkedin.com"
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-white border border-gray-200 text-xs font-bold text-gray-900 hover:bg-gray-50 transition-colors shadow-sm shrink-0"
                      >
                        Open LinkedIn <ExternalLink size={13} />
                      </a>
                    </div>

                    <div className="flex items-center justify-between pt-2">
                      <button
                        type="button"
                        onClick={() => setStep(4)}
                        className="text-xs text-primary hover:text-primary/80 font-semibold flex items-center gap-1 transition-colors underline underline-offset-4"
                      >
                        Skip straight to Paste JSON →
                      </button>
                      <button 
                        onClick={() => setStep(3)}
                        className="flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-gray-900 hover:bg-gray-800 text-white text-sm font-semibold transition-all shadow-sm"
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
                        <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-200 text-xs text-emerald-950">
                          <div className="font-bold mb-1 flex items-center gap-1.5 text-emerald-800">
                            <Zap size={14} className="fill-emerald-500 text-emerald-500" />
                            Zero-Touch Native 1-Click Synchronization
                          </div>
                          <div className="text-emerald-900 leading-relaxed">
                            No manual copy-pasting of sensitive tokens required. Simply open the Ele-in Chrome extension while logged into LinkedIn and press <strong>1-Click Sync</strong>.
                          </div>
                        </div>

                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 text-xs">
                          <div className="p-3 rounded-xl border border-gray-200 bg-white">
                            <div className="w-5 h-5 rounded-full bg-emerald-100 text-emerald-700 font-bold flex items-center justify-center mb-1.5">1</div>
                            <div className="font-semibold text-gray-900">Load Extension</div>
                            <div className="text-gray-500 text-[11px] mt-0.5">Load the Ele-in Chrome extension in your browser.</div>
                          </div>
                          <div className="p-3 rounded-xl border border-gray-200 bg-white">
                            <div className="w-5 h-5 rounded-full bg-emerald-100 text-emerald-700 font-bold flex items-center justify-center mb-1.5">2</div>
                            <div className="font-semibold text-gray-900">Open LinkedIn</div>
                            <div className="text-gray-500 text-[11px] mt-0.5">Ensure you are logged into your outbound sender profile.</div>
                          </div>
                          <div className="p-3 rounded-xl border border-gray-200 bg-white">
                            <div className="w-5 h-5 rounded-full bg-emerald-100 text-emerald-700 font-bold flex items-center justify-center mb-1.5">3</div>
                            <div className="font-semibold text-gray-900">Click 1-Click Sync</div>
                            <div className="text-gray-500 text-[11px] mt-0.5">Click the extension icon & hit Sync. Your account connects instantly!</div>
                          </div>
                        </div>
                      </div>
                    ) : extractionMethod === "editthiscookie" ? (
                      <div className="space-y-3">
                        <div className="flex items-center justify-between p-3 rounded-xl bg-blue-50 border border-blue-200">
                          <div className="text-xs text-blue-900">
                            <strong>Step 3a:</strong> Install EditThisCookie from the official Chrome Web Store.
                          </div>
                          <a
                            href="https://chromewebstore.google.com/detail/editthiscookie-v3/ojfebgpkimhlhcblbalbfjblapadhbol"
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-blue-600 text-white text-xs font-semibold hover:bg-blue-700 transition-colors shrink-0"
                          >
                            Install Extension <ExternalLink size={12} />
                          </a>
                        </div>

                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 text-xs">
                          <div className="p-3 rounded-xl border border-gray-200 bg-white">
                            <div className="w-5 h-5 rounded-full bg-primary/10 text-primary font-bold flex items-center justify-center mb-1.5">1</div>
                            <div className="font-semibold text-gray-900">Open LinkedIn</div>
                            <div className="text-gray-500 text-[11px] mt-0.5">Navigate to your LinkedIn feed in the tab.</div>
                          </div>
                          <div className="p-3 rounded-xl border border-gray-200 bg-white">
                            <div className="w-5 h-5 rounded-full bg-primary/10 text-primary font-bold flex items-center justify-center mb-1.5">2</div>
                            <div className="font-semibold text-gray-900">Click Extension</div>
                            <div className="text-gray-500 text-[11px] mt-0.5">Click the cookie icon in your browser toolbar.</div>
                          </div>
                          <div className="p-3 rounded-xl border border-gray-200 bg-white">
                            <div className="w-5 h-5 rounded-full bg-primary/10 text-primary font-bold flex items-center justify-center mb-1.5">3</div>
                            <div className="font-semibold text-gray-900">Click Export</div>
                            <div className="text-gray-500 text-[11px] mt-0.5">Click the right-arrow export icon to copy cookies.</div>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-3">
                        <div className="p-3 rounded-xl bg-blue-50 border border-blue-200 text-xs text-blue-950">
                          <strong>No Extension Required:</strong> Extract directly via Chrome, Edge, Brave, or Arc DevTools in 15 seconds.
                        </div>

                        <div className="space-y-2 text-xs">
                          <div className="flex items-start gap-2.5 p-2.5 rounded-lg border border-gray-200 bg-white">
                            <span className="font-bold text-blue-600 shrink-0">1.</span>
                            <div>On linkedin.com, press <kbd className="px-1.5 py-0.5 bg-gray-100 border border-gray-300 rounded font-mono text-[10px]">F12</kbd> (or Right Click &gt; <strong>Inspect</strong>).</div>
                          </div>
                          <div className="flex items-start gap-2.5 p-2.5 rounded-lg border border-gray-200 bg-white">
                            <span className="font-bold text-blue-600 shrink-0">2.</span>
                            <div>Switch to the <strong>Application</strong> tab (in Firefox/Safari: <strong>Storage</strong>) &gt; expand <strong>Cookies</strong> &gt; click <strong>https://www.linkedin.com</strong>.</div>
                          </div>
                          <div className="flex items-start gap-2.5 p-2.5 rounded-lg border border-gray-200 bg-white">
                            <span className="font-bold text-blue-600 shrink-0">3.</span>
                            <div>Double-click the value under <code className="font-bold text-blue-700 bg-blue-50 px-1 py-0.5 rounded">li_at</code> and copy it (<kbd className="px-1 py-0.5 bg-gray-100 border border-gray-300 rounded font-mono text-[10px]">Cmd+C</kbd>). Paste it into Step 4!</div>
                          </div>
                        </div>
                      </div>
                    )}

                    <div className="flex items-center justify-between pt-2">
                      <button
                        type="button"
                        onClick={() => setExtractionMethod(extractionMethod === "elein_extension" ? "devtools" : "elein_extension")}
                        className="text-xs text-gray-500 hover:text-gray-800 underline underline-offset-4"
                      >
                        Switch to {extractionMethod === "elein_extension" ? "DevTools manual method" : "Ele-in 1-Click Extension"}
                      </button>
                      <button 
                        onClick={() => setStep(4)}
                        className="flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-gray-900 hover:bg-gray-800 text-white text-sm font-semibold transition-all shadow-sm"
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
                        <label className="text-xs font-bold text-gray-900">
                          Account Label <span className="text-gray-400 font-normal">(Optional)</span>
                        </label>
                        <input
                          value={name}
                          onChange={e => setName(e.target.value)}
                          placeholder='e.g. John Doe - Growth'
                          className="w-full rounded-xl bg-white border border-gray-200 px-3.5 py-2.5 text-xs text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all"
                        />
                      </div>
                      
                      <div className="space-y-1">
                        <label className="text-xs font-bold text-gray-900 flex items-center justify-between">
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
                        <select
                          value={proxyId}
                          onChange={e => {
                            if (e.target.value !== "" && isProxyLocked) {
                              openPaywall({ featureName: "Custom Residential Proxy Rotation" })
                              return
                            }
                            setProxyId(e.target.value)
                          }}
                          className="w-full rounded-xl bg-white border border-gray-200 px-3.5 py-2.5 text-xs text-gray-700 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all cursor-pointer appearance-none"
                          style={{ backgroundImage: 'url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' fill=\'none\' viewBox=\'0 0 24 24\' stroke=\'%236B7280\'%3E%3Cpath stroke-linecap=\'round\' stroke-linejoin=\'round\' stroke-width=\'2\' d=\'M19 9l-7 7-7-7\'%3E%3C/path%3E%3C/svg%3E")', backgroundRepeat: 'no-repeat', backgroundPosition: 'right 12px center', backgroundSize: '14px' }}
                        >
                          <option value="">Auto-Assign Geolocation Proxy (Recommended)</option>
                          {proxies?.map((p: any) => (
                            <option key={p.id} value={p.id}>
                              {p.provider || "Residential"} — {p.country_code || "US"} ({p.host}:{p.port})
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                    
                    {/* Row 2: Cookie Input Area */}
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <label className="text-xs font-bold text-gray-900 flex items-center gap-1.5">
                          <span>LinkedIn Session Cookies / li_at Token</span>
                          <span className="text-[10px] bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded font-normal">Auto-Detecting</span>
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
                          className="text-xs font-semibold text-primary hover:text-primary/80 flex items-center gap-1 transition-colors"
                        >
                          Paste from Clipboard
                        </button>
                      </div>
                      
                      <textarea
                        value={cookieJson}
                        onChange={e => { setCookieJson(e.target.value); setError(""); setValidated(null) }}
                        rows={3}
                        placeholder={'Paste EditThisCookie JSON export OR paste raw li_at value (AQEDA...)'}
                        className="w-full rounded-xl bg-white border border-gray-200 px-3.5 py-2.5 text-xs font-mono text-gray-600 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary resize-none transition-all"
                      />

                      {/* Format sniffer status badge */}
                      {parsedCookieInfo && (
                        <div className={cn(
                          "text-xs px-3 py-1.5 rounded-lg flex items-center gap-2 font-medium transition-all",
                          parsedCookieInfo.valid 
                            ? "bg-emerald-50 text-emerald-700 border border-emerald-200" 
                            : parsedCookieInfo.warning 
                              ? "bg-amber-50 text-amber-700 border border-amber-200" 
                              : "bg-red-50 text-red-600 border border-red-200"
                        )}>
                          {parsedCookieInfo.valid ? (
                            <>
                              <CheckCircle2 size={13} className="text-emerald-600 shrink-0" />
                              <span>{parsedCookieInfo.badge}</span>
                            </>
                          ) : parsedCookieInfo.warning ? (
                            <>
                              <AlertCircle size={13} className="text-amber-600 shrink-0" />
                              <span>{parsedCookieInfo.warning}</span>
                            </>
                          ) : (
                            <>
                              <AlertCircle size={13} className="text-red-500 shrink-0" />
                              <span>{parsedCookieInfo.error}</span>
                            </>
                          )}
                        </div>
                      )}
                    </div>
                    
                    {/* Row 3: 30-Day Warmup Mode Toggle */}
                    <div className="p-3 rounded-xl border border-gray-200 bg-gray-50/60">
                      <label className="flex items-start gap-3 cursor-pointer group">
                        <div className={cn("w-5 h-5 mt-0.5 rounded-[5px] border-[1.5px] flex items-center justify-center transition-colors shrink-0",
                          isWarmup ? "bg-primary border-primary" : "border-gray-300 bg-white group-hover:border-gray-400"
                        )}>
                          {isWarmup && <Check size={13} className="text-white" strokeWidth={3.5} />}
                        </div>
                        <input 
                          type="checkbox" 
                          className="hidden" 
                          checked={isWarmup} 
                          onChange={(e) => setIsWarmup(e.target.checked)} 
                        />
                        <div className="space-y-0.5">
                          <span className="text-xs font-bold text-gray-900 select-none block">
                            Cold or New Account (Enable 30-Day Safe Warmup Mode)
                          </span>
                          <span className="text-[11px] text-gray-500 block leading-relaxed">
                            Ramps daily limits gradually from 5 to 40 connection requests over 30 days to protect account reputation.
                          </span>
                        </div>
                      </label>
                    </div>

                    {/* Error & Validation Feedback */}
                    {error && (
                      <div className="flex items-center gap-2.5 p-3 rounded-xl bg-red-50 border border-red-100 text-red-600 text-xs">
                        <AlertCircle size={16} className="shrink-0" />
                        <p className="font-medium leading-relaxed">{error}</p>
                      </div>
                    )}

                    {validating && (
                      <div className="flex items-center gap-2.5 p-3 rounded-xl bg-primary/5 border border-primary/20 text-primary text-xs">
                        <div className="w-4 h-4 rounded-full border-2 border-primary border-t-transparent animate-spin shrink-0" />
                        <p className="font-semibold">Validating session with LinkedIn Voyager API via residential proxy… (~4s)</p>
                      </div>
                    )}

                    {validated?.valid && (
                      <div className="flex items-center gap-3 p-3.5 rounded-xl bg-green-50 border border-green-200">
                        <div className="w-8 h-8 rounded-full bg-green-100 flex items-center justify-center shrink-0">
                          <CheckCircle2 size={18} className="text-green-600" />
                        </div>
                        <div className="min-w-0">
                          <p className="text-xs text-green-700 font-bold">
                            LinkedIn Account Verified &amp; Connected!
                          </p>
                          {validated.name && (
                            <p className="text-[11px] text-green-600 font-medium truncate">
                              {validated.name} {validated.profile_url ? `(${validated.profile_url})` : ''}
                            </p>
                          )}
                        </div>
                      </div>
                    )}
                    
                    {/* Submit Button */}
                    <div className="pt-1">
                      <button
                        onClick={handleValidateAndConnect}
                        disabled={validating || !parsedCookieInfo?.valid}
                        className="w-full flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-bold shadow-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed"
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
