import { useState, useMemo, useEffect } from "react"
import { motion, AnimatePresence } from "motion/react"
import { Linkedin } from "../icons/Linkedin"
import { 
  X, CheckCircle2, AlertCircle, ChevronDown, ChevronUp, Check, 
  ShieldCheck, Terminal, Puzzle, ExternalLink, Lock, Zap,
  Clipboard, ArrowRight, Loader2, Sparkles
} from "lucide-react"
import { cn } from "@/lib/utils"
import { fetchWithAuth, fetcher } from "@/lib/apiClient"
import useSWR from "swr"
import { usePaywall } from "@/contexts/PaywallContext"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

interface ConnectModalProps {
  onClose: () => void
  onAdd: (account: any) => Promise<void> | void
}

export default function ConnectModal({ onClose, onAdd }: ConnectModalProps) {
  const [activeTab, setActiveTab] = useState<"token" | "extension">("token")
  const [cookieInput, setCookieInput] = useState("")
  const [name, setName] = useState("")
  const [isWarmup, setIsWarmup] = useState(true)
  const [proxyId, setProxyId] = useState("auto")
  const [error, setError] = useState("")
  const [validating, setValidating] = useState(false)
  const [validated, setValidated] = useState<{ valid: boolean; profile_url?: string; name?: string } | null>(null)
  const [showGuide, setShowGuide] = useState(false)
  const [guideMethod, setGuideMethod] = useState<"devtools" | "editthiscookie">("devtools")

  const { data: proxies } = useSWR("/api/elein/proxies/health", fetcher)
  const { data: billing } = useSWR<{ tier?: string; tier_limits?: { can_use_custom_proxies?: boolean } }>('/api/elein/workspaces/billing', fetcher)
  const { openPaywall } = usePaywall()
  const isProxyLocked = Boolean(billing && !billing.tier_limits?.can_use_custom_proxies)

  // Layer 2 Paranoia: Close on Escape key (unless network validation is actively in-flight)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !validating) {
        onClose()
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [onClose, validating])

  // ─── Three-Layer Paranoia: Client-side Cookie Normalizer & Live Format Sniffer ───
  const parsedCookieInfo = useMemo(() => {
    if (!cookieInput.trim()) return null
    let cleaned = cookieInput.trim()
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
            warning: "JSON array detected, but missing 'li_at' cookie. Make sure you exported from linkedin.com.",
            normalized: cleaned,
            type: "json_missing_li_at"
          }
        }
        return {
          valid: true,
          badge: `Valid EditThisCookie JSON export (${parsed.length} cookies, li_at verified)`,
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
        badge: `Raw li_at token detected (${token.length} chars) - auto-formatted`,
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
      error: "Unrecognized format. Paste your raw li_at token or EditThisCookie JSON export.",
      normalized: cleaned,
      type: "invalid"
    }
  }, [cookieInput])

  const handleValidateAndConnect = async () => {
    if (!parsedCookieInfo?.valid) {
      setError(parsedCookieInfo?.warning || parsedCookieInfo?.error || "Please enter valid LinkedIn session cookies.")
      return
    }

    const payloadJson = parsedCookieInfo.normalized
    setValidating(true)
    setError("")
    setValidated(null)

    // Layer 1 Paranoia: 25-second timeout guard against hung proxy tunnels
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 25000)
    // Paranoia Layer 0 & 2: Normalize "auto" selector to undefined so backend invokes automatic proxy assignment
    const resolvedProxyId = proxyId && proxyId !== "auto" ? proxyId : undefined

    try {
      const res = await fetchWithAuth("/api/elein/accounts/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_cookies_json: payloadJson, proxy_id: resolvedProxyId }),
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
        setError(result.error || "Cookie session is invalid or expired. Please refresh linkedin.com and re-copy cookies.")
        return
      }

      setValidated(result)
      const accountName = name.trim() || result.name || "LinkedIn Account"
      const profileUrl = result.profile_url || ""

      const account = {
        name: accountName,
        profileUrl,
        cookieJson: payloadJson,
        isWarmup,
        dailyLimit: 20,
        messageLimit: 40,
        sent: 0,
        warmupTargetDays: 30,
        warmupMaxConnections: 20,
        warmupMaxMessages: 40,
        proxyId: resolvedProxyId
      }

      await onAdd(account)
      setValidating(false)

      setTimeout(() => onClose(), 600)

    } catch (e: any) {
      clearTimeout(timer)
      setValidating(false)
      setValidated(null)
      if (e.name === 'AbortError') {
        setError("Validation timed out after 25s. The proxy tunnel or LinkedIn took too long to respond.")
      } else {
        setError(e.message || "Failed to reach server. Please check your network connection.")
      }
    }
  }

  const handlePasteClipboard = async () => {
    try {
      const text = await navigator.clipboard.readText()
      if (text) {
        setCookieInput(text.trim())
        setError("")
        setValidated(null)
      }
    } catch {
      // Clipboard permission denied - focus input
      const textarea = document.getElementById("cookie-input-field")
      textarea?.focus()
    }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm p-4 animate-in fade-in duration-200">
      <motion.div
        initial={{ opacity: 0, scale: 0.97, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.97, y: 8 }}
        transition={{ duration: 0.2, ease: "easeOut" }}
        className="w-full max-w-xl"
      >
        <div className="rounded-xl bg-card border border-border text-card-foreground shadow-2xl overflow-hidden flex flex-col max-h-[calc(100vh-2rem)]">
          
          {/* Header */}
          <div className="px-6 pt-6 pb-4 border-b border-border relative">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center text-primary shrink-0">
                  <Linkedin size={20} />
                </div>
                <div>
                  <h2 className="text-lg font-semibold tracking-tight text-foreground">
                    Connect LinkedIn Account
                  </h2>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Zero passwords required. Connect safely in 15 seconds.
                  </p>
                </div>
              </div>

              <button 
                type="button"
                aria-label="Close modal"
                onClick={onClose} 
                className="w-8 h-8 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted flex items-center justify-center transition-colors focus:outline-none focus:ring-2 focus:ring-ring"
              >
                <X size={16} />
              </button>
            </div>

            {/* Tab Switcher: Stupidly Simple 2-Tab Choice */}
            <div className="flex gap-2 mt-4 p-1 bg-muted/50 rounded-lg border border-border/60">
              <button
                type="button"
                onClick={() => { setActiveTab("token"); setError(""); }}
                className={cn(
                  "flex-1 py-1.5 px-3 rounded-md text-xs font-medium transition-all text-center flex items-center justify-center gap-1.5",
                  activeTab === "token"
                    ? "bg-card text-foreground shadow-xs font-semibold border border-border/60"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                <Clipboard size={13} />
                <span>Paste Token / Cookies (15s)</span>
              </button>

              <button
                type="button"
                onClick={() => { setActiveTab("extension"); setError(""); }}
                className={cn(
                  "flex-1 py-1.5 px-3 rounded-md text-xs font-medium transition-all text-center flex items-center justify-center gap-1.5",
                  activeTab === "extension"
                    ? "bg-card text-foreground shadow-xs font-semibold border border-border/60"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                <Zap size={13} />
                <span>1-Click Extension Sync</span>
              </button>
            </div>
          </div>

          {/* Modal Body */}
          <div className="px-6 py-5 overflow-y-auto space-y-4">

            {/* TAB 1: PASTE TOKEN / COOKIES (Instant 15s Flow) */}
            {activeTab === "token" && (
              <div className="space-y-4">
                {/* Account Label & Proxy Selection */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-foreground">
                      Account Label <span className="text-muted-foreground">(Optional)</span>
                    </label>
                    <input
                      value={name}
                      onChange={e => setName(e.target.value)}
                      placeholder="e.g. Founder Outreach"
                      className="w-full rounded-lg bg-background border border-input px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
                    />
                  </div>
                  
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-foreground flex items-center justify-between">
                      <span className="flex items-center gap-1">
                        <span>Residential Proxy</span>
                        {isProxyLocked && <Lock size={11} className="text-warning" />}
                      </span>
                      {isProxyLocked ? (
                        <span className="text-[10px] text-warning font-medium">Pro: Custom Pool</span>
                      ) : (
                        <span className="text-[10px] text-success font-medium">Dedicated Pool</span>
                      )}
                    </label>
                    <Select
                      value={proxyId || "auto"}
                      onValueChange={val => {
                        if (val !== "auto" && isProxyLocked) {
                          openPaywall({ featureName: "Custom Residential Proxy Rotation" })
                          setProxyId("auto")
                          return
                        }
                        setProxyId(val)
                      }}
                    >
                      <SelectTrigger className="w-full bg-background border-input px-3 py-2 text-xs text-foreground h-9">
                        <SelectValue placeholder="Auto-Assign Proxy (Recommended)" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="auto">Auto-Assign Proxy (Recommended)</SelectItem>
                        {proxies?.map((p: any) => (
                          <SelectItem key={p.id} value={p.id}>
                            {p.provider || "Residential"} - {p.country_code || "US"} ({p.host})
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                {/* Single Paste Box */}
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-medium text-foreground">
                      LinkedIn Cookie Token (<code className="text-primary font-mono font-semibold">li_at</code> or JSON)
                    </label>
                    <button
                      type="button"
                      onClick={handlePasteClipboard}
                      className="text-xs font-medium text-primary hover:text-primary/80 flex items-center gap-1 transition-colors focus:outline-none cursor-pointer"
                    >
                      <Clipboard size={12} />
                      <span>Paste from Clipboard</span>
                    </button>
                  </div>

                  <textarea
                    id="cookie-input-field"
                    value={cookieInput}
                    onChange={e => { setCookieInput(e.target.value); setError(""); setValidated(null); }}
                    rows={3}
                    placeholder="Paste your raw li_at value (AQEDA...) or EditThisCookie JSON export here"
                    className="w-full rounded-lg bg-background border border-input px-3 py-2 text-xs font-mono text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary resize-none transition-all"
                  />

                  {/* Format detection badge */}
                  {parsedCookieInfo && (
                    <div className={cn(
                      "text-xs px-2.5 py-1.5 rounded-lg flex items-center gap-2 font-medium transition-all",
                      parsedCookieInfo.valid 
                        ? "bg-success/10 text-success border border-success/20" 
                        : parsedCookieInfo.warning 
                          ? "bg-warning/10 text-warning border border-warning/20" 
                          : "bg-destructive/10 text-destructive border border-destructive/20"
                    )}>
                      {parsedCookieInfo.valid ? (
                        <>
                          <CheckCircle2 size={13} className="shrink-0" />
                          <span>{parsedCookieInfo.badge}</span>
                        </>
                      ) : (
                        <>
                          <AlertCircle size={13} className="shrink-0" />
                          <span>{parsedCookieInfo.warning || parsedCookieInfo.error}</span>
                        </>
                      )}
                    </div>
                  )}
                </div>

                {/* Safe Warmup Toggle */}
                <div className="p-3 rounded-lg border border-border bg-muted/20">
                  <label className="flex items-start gap-3 cursor-pointer select-none">
                    <div className={cn(
                      "w-4 h-4 mt-0.5 rounded border flex items-center justify-center transition-colors shrink-0",
                      isWarmup ? "bg-primary border-primary text-primary-foreground" : "border-input bg-background"
                    )}>
                      {isWarmup && <Check size={11} strokeWidth={3} />}
                    </div>
                    <input 
                      type="checkbox" 
                      className="sr-only" 
                      checked={isWarmup} 
                      onChange={e => setIsWarmup(e.target.checked)} 
                    />
                    <div>
                      <span className="text-xs font-medium text-foreground block">
                        Enable 30-Day Safe Warmup Mode (Recommended)
                      </span>
                      <span className="text-[11px] text-muted-foreground block mt-0.5 leading-relaxed">
                        Gradually ramps daily connection requests from 5 to 40 over 30 days to protect account reputation.
                      </span>
                    </div>
                  </label>
                </div>

                {/* Collapsible 15-Second Help Guide */}
                <div className="rounded-lg border border-border/70 overflow-hidden bg-card">
                  <button
                    type="button"
                    onClick={() => setShowGuide(!showGuide)}
                    className="w-full px-3.5 py-2.5 flex items-center justify-between text-xs font-medium text-muted-foreground hover:text-foreground transition-colors cursor-pointer bg-muted/10"
                  >
                    <span className="flex items-center gap-1.5">
                      <Terminal size={13} className="text-primary" />
                      <span>Where do I find my li_at cookie? (15-second guide)</span>
                    </span>
                    {showGuide ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  </button>

                  {showGuide && (
                    <div className="p-3.5 border-t border-border/70 space-y-3 text-xs bg-background/50">
                      <div className="flex gap-2">
                        <button
                          type="button"
                          onClick={() => setGuideMethod("devtools")}
                          className={cn(
                            "px-2.5 py-1 rounded-md text-[11px] font-medium border transition-colors",
                            guideMethod === "devtools"
                              ? "bg-primary/10 border-primary/30 text-primary font-semibold"
                              : "border-border text-muted-foreground hover:text-foreground"
                          )}
                        >
                          Chrome/Edge DevTools (No Extension)
                        </button>
                        <button
                          type="button"
                          onClick={() => setGuideMethod("editthiscookie")}
                          className={cn(
                            "px-2.5 py-1 rounded-md text-[11px] font-medium border transition-colors",
                            guideMethod === "editthiscookie"
                              ? "bg-primary/10 border-primary/30 text-primary font-semibold"
                              : "border-border text-muted-foreground hover:text-foreground"
                          )}
                        >
                          EditThisCookie Extension
                        </button>
                      </div>

                      {guideMethod === "devtools" ? (
                        <ol className="space-y-1.5 list-decimal list-inside text-muted-foreground leading-relaxed pl-1">
                          <li>Open <a href="https://www.linkedin.com" target="_blank" rel="noreferrer" className="text-foreground underline underline-offset-2">linkedin.com</a> while logged in.</li>
                          <li>Press <kbd className="px-1 py-0.5 rounded bg-muted border border-border font-mono text-[10px] text-foreground">F12</kbd> (or right-click &gt; Inspect).</li>
                          <li>Switch to the <strong>Application</strong> tab (Storage on Firefox) &gt; expand <strong>Cookies</strong> &gt; click <strong>https://www.linkedin.com</strong>.</li>
                          <li>Double-click the value next to <code className="text-primary font-mono font-semibold">li_at</code>, copy it, and paste it above!</li>
                        </ol>
                      ) : (
                        <div className="space-y-2 text-muted-foreground leading-relaxed">
                          <p>
                            Install <a href="https://chromewebstore.google.com/detail/editthiscookie-v3/ojfebgpkimhlhcblbalbfjblapadhbol" target="_blank" rel="noreferrer" className="text-foreground underline underline-offset-2 inline-flex items-center gap-1">EditThisCookie from the Chrome Web Store <ExternalLink size={10} /></a>.
                          </p>
                          <p>
                            On LinkedIn, click the cookie icon in your toolbar, click the Export arrow, and paste the clipboard contents into the box above.
                          </p>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Error Banner */}
                {error && (
                  <div className="flex items-center gap-2 p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-xs">
                    <AlertCircle size={15} className="shrink-0" />
                    <p className="font-medium leading-relaxed">{error}</p>
                  </div>
                )}

                {/* Validated Success Banner */}
                {validated?.valid && (
                  <div className="flex items-center gap-2.5 p-3 rounded-lg bg-success/10 border border-success/20 text-success text-xs">
                    <CheckCircle2 size={16} className="shrink-0" />
                    <div>
                      <p className="font-semibold">Account Verified & Connected</p>
                      {validated.name && <p className="text-[11px] opacity-90">{validated.name}</p>}
                    </div>
                  </div>
                )}

                {/* Connect Action Button */}
                <button
                  type="button"
                  onClick={handleValidateAndConnect}
                  disabled={validating || !parsedCookieInfo?.valid}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold transition-all shadow-xs disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer focus:outline-none focus:ring-2 focus:ring-ring"
                >
                  {validating ? (
                    <>
                      <Loader2 size={14} className="animate-spin" />
                      <span>Validating Session via Dedicated Proxy...</span>
                    </>
                  ) : (
                    <span>Validate & Connect Account</span>
                  )}
                </button>
              </div>
            )}

            {/* TAB 2: 1-CLICK EXTENSION SYNC */}
            {activeTab === "extension" && (
              <div className="space-y-4 py-1">
                <div className="p-4 rounded-xl border border-border bg-card space-y-3">
                  <div className="flex items-center gap-2 text-foreground font-semibold text-xs">
                    <Zap size={15} className="text-primary" />
                    <span>Zero-Touch Synchronization</span>
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    The Ele-in Chrome Extension auto-detects your active LinkedIn session cookies directly from your browser. No copy-pasting of sensitive tokens required.
                  </p>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 pt-2 text-xs">
                    <div className="p-3 rounded-lg border border-border/70 bg-background/60">
                      <div className="w-5 h-5 rounded-full bg-primary/10 text-primary font-bold flex items-center justify-center mb-1.5 text-[11px]">1</div>
                      <div className="font-medium text-foreground">Load Extension</div>
                      <div className="text-muted-foreground text-[11px] mt-0.5">Load the extension folder in Chrome Developer Mode.</div>
                    </div>
                    <div className="p-3 rounded-lg border border-border/70 bg-background/60">
                      <div className="w-5 h-5 rounded-full bg-primary/10 text-primary font-bold flex items-center justify-center mb-1.5 text-[11px]">2</div>
                      <div className="font-medium text-foreground">Open LinkedIn</div>
                      <div className="text-muted-foreground text-[11px] mt-0.5">Keep linkedin.com open in an active tab.</div>
                    </div>
                    <div className="p-3 rounded-lg border border-border/70 bg-background/60">
                      <div className="w-5 h-5 rounded-full bg-primary/10 text-primary font-bold flex items-center justify-center mb-1.5 text-[11px]">3</div>
                      <div className="font-medium text-foreground">Click Sync</div>
                      <div className="text-muted-foreground text-[11px] mt-0.5">Hit Sync in the extension popup to connect.</div>
                    </div>
                  </div>
                </div>

                <div className="flex items-center justify-between p-3.5 rounded-lg border border-border bg-muted/20 text-xs">
                  <div className="space-y-0.5">
                    <div className="font-medium text-foreground">Prefer not to install an extension?</div>
                    <div className="text-muted-foreground text-[11px]">Copy your cookie token once in 15 seconds.</div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setActiveTab("token")}
                    className="px-3 py-1.5 rounded-lg border border-border bg-card hover:bg-muted text-foreground text-xs font-medium transition-colors cursor-pointer shrink-0"
                  >
                    Use Token Paste
                  </button>
                </div>
              </div>
            )}

            {/* Zero Password Security & Trust Guarantee */}
            <div className="p-3 rounded-lg bg-muted/20 border border-border/60 flex items-center gap-2.5 text-[11px] text-muted-foreground">
              <ShieldCheck size={16} className="text-success shrink-0" />
              <span>
                Zero Password Architecture: We never ask for or store your LinkedIn credentials. All sessions are encrypted with AES-256-GCM.
              </span>
            </div>

          </div>
        </div>
      </motion.div>
    </div>
  )
}
