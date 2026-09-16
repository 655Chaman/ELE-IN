import { useState } from "react"
import { motion, AnimatePresence } from "motion/react"
import { Linkedin } from "../icons/Linkedin"
import { X, CheckCircle2, Clock, AlertCircle, ChevronRight, Info } from "lucide-react"
import * as Popover from "@radix-ui/react-popover"
import { cn } from "@/lib/utils"
import SpotlightCard from "../SpotlightCard"
import { fetchWithAuth, fetcher } from "@/lib/apiClient"
import type { LinkedInAccount } from "@accounts/eiAccountsStore"
import useSWR from "swr"

export default function ConnectModal({ onClose, onAdd }: { onClose: () => void; onAdd: (a: LinkedInAccount) => void }) {
  const [step, setStep] = useState(1)
  const [cookieJson, setCookieJson] = useState("")
  const [name, setName] = useState("")
  const [isWarmup, setIsWarmup] = useState(false)
  const [error, setError] = useState("")
  const [validating, setValidating] = useState(false)
  const [validated, setValidated] = useState<{ valid: boolean; profile_url?: string; name?: string } | null>(null)
  const [proxyId, setProxyId] = useState("")
  const [imgError, setImgError] = useState(false)
  const { data: proxies } = useSWR("/api/elein/proxies/health", fetcher)

  const STEPS = [
    { 
      num: 1, 
      id: 'get-extension',
      title: "Get the EditThisCookie extension", 
      sub: "We use a trusted, open-source extension to securely grab your session without ever needing your password.",
      action: { label: "Install Extension", href: "https://chromewebstore.google.com/detail/editthiscookie-v3/ojfebgpkimhlhcblbalbfjblapadhbol" }
    },
    { 
      num: 2, 
      id: 'login-linkedin',
      title: "Log into LinkedIn", 
      sub: "Open LinkedIn in a new tab and make sure you're logged into the account you want to connect.",
      action: { label: "Open LinkedIn", href: "https://www.linkedin.com" }
    },
    { 
      num: 3, 
      id: 'export-cookies',
      title: "Export your cookies", 
      sub: "Click the EditThisCookie icon in your browser toolbar, then click the 'Export' button (it looks like a copy or download icon).",
    },
    { 
      num: 4, 
      id: 'paste-connect',
      title: "Paste & Connect", 
      sub: "Paste the copied JSON data below to securely connect your account.",
    },
  ]

  const handleValidateAndConnect = async () => {
    if (!cookieJson.trim()) { setError("Paste your LinkedIn cookie JSON first."); return }
    try {
      JSON.parse(cookieJson)
    } catch {
      setError("Invalid JSON — export again from EditThisCookie.")
      return
    }

    setValidating(true)
    setError("")
    setValidated(null)

    try {
      const res = await fetchWithAuth("/api/elein/accounts/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_cookies_json: cookieJson, proxy_id: proxyId }),
      })
      const result = await res.json()

      if (!result.valid) {
        setValidating(false)
        setValidated({ valid: false })
        setError(result.error || "Cookie session is invalid or expired. Log into LinkedIn and re-export.")
        return
      }

      setValidated(result)
      const accountName = name || result.name || "LinkedIn Account"
      const profileUrl = result.profile_url || ""

      const account = {
        name: accountName,
        profileUrl,
        cookieJson,
        isWarmup,
        proxyId: proxyId || undefined
      }
      await onAdd(account as any)
      setValidating(false)

      setTimeout(() => onClose(), 800)

    } catch (e: any) {
      setValidating(false)
      setError("Could not reach backend. Is the server running on localhost:8000?")
    }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        transition={{ duration: 0.25 }}
        className="w-full max-w-xl"
      >
        <SpotlightCard className="!p-0 rounded-2xl bg-card border border-border shadow-2xl overflow-hidden flex flex-col max-h-[calc(100vh-2rem)]" spotlightColor="rgba(255, 255, 255, 0.05)">
          <div className="flex items-center justify-between px-6 pt-6 pb-4 shrink-0 border-b border-border/10 mb-2">
            <div>
              <h2 className="text-lg font-bold text-card-foreground flex items-center gap-2">
                <Linkedin size={20} className="text-primary" />
                Connect LinkedIn Account
              </h2>
              <p className="text-xs text-muted-foreground mt-1">
                No passwords required. Securely connect using browser cookies in 30 seconds.
              </p>
            </div>
            <button onClick={onClose} className="w-8 h-8 rounded-full bg-muted/50 flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors">
              <X size={16} />
            </button>
          </div>

          <div className="px-6 py-2 space-y-3 pb-8 flex-1 overflow-y-auto">
            {STEPS.map((s) => {
              const isActive = step === s.num;
              const isPast = step > s.num;
              
              return (
                <div 
                  key={s.num} 
                  className={cn(
                    "relative flex items-start gap-4 rounded-xl border transition-all duration-300 overflow-hidden",
                    isActive ? "border-primary/50 bg-primary/5 shadow-sm p-5" : "border-border/50 bg-background/30 p-4",
                    isPast && "opacity-70 hover:opacity-100 cursor-pointer hover:bg-muted/30"
                  )}
                  onClick={() => isPast && setStep(s.num)}
                >
                  <div className={cn(
                    "w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 transition-colors mt-0.5",
                    isPast ? "bg-primary text-primary-foreground" : 
                    isActive ? "bg-primary text-primary-foreground shadow-lg shadow-primary/20" : 
                    "bg-muted text-muted-foreground"
                  )}>
                    {isPast ? <CheckCircle2 size={14} /> : s.num}
                  </div>
                  
                  <div className="flex-1 min-w-0">
                    <h3 className={cn("font-semibold text-sm transition-colors pt-1", isActive ? "text-foreground" : "text-muted-foreground")}>
                      {s.title}
                    </h3>
                    
                    <AnimatePresence>
                      {isActive && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: "auto", opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          className="overflow-hidden"
                        >
                          <div className="flex items-start gap-1.5 mt-2">
                            <p className="text-xs text-muted-foreground leading-relaxed">
                              {s.sub}
                            </p>
                            {s.id === 'export-cookies' && (
                              <Popover.Root>
                                <Popover.Trigger asChild>
                                  <button 
                                    className="inline-flex items-center justify-center shrink-0 w-4 h-4 rounded-full bg-muted/50 text-muted-foreground hover:text-foreground hover:bg-muted transition-colors mt-0.5"
                                    title="Show visual guide"
                                    onClick={(e) => e.stopPropagation()}
                                  >
                                    <Info size={12} />
                                  </button>
                                </Popover.Trigger>
                                <Popover.Portal>
                                  <Popover.Content 
                                    side="right" 
                                    align="start" 
                                    sideOffset={12} 
                                    className="z-[200] w-72 bg-card border border-border rounded-xl shadow-xl p-3 animate-in fade-in zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out data-[state=closed]:zoom-out-95"
                                    onClick={(e) => e.stopPropagation()}
                                  >
                                    <h4 className="text-sm font-semibold mb-2">How to export cookies</h4>
                                    <div className="aspect-[4/3] bg-muted/50 rounded-lg flex items-center justify-center border border-border/50 text-xs text-muted-foreground mb-3 overflow-hidden relative">
                                      {imgError ? (
                                        <span>Image placeholder</span>
                                      ) : (
                                        <img 
                                          src="/guide-export-cookie.png" 
                                          alt="Cookie Export Guide" 
                                          className="absolute inset-0 w-full h-full object-cover" 
                                          onError={() => setImgError(true)}
                                        />
                                      )}
                                    </div>
                                    <p className="text-xs text-muted-foreground">
                                      Click the EditThisCookie icon in your extension bar, then click the <strong>Export</strong> button (looks like a right arrow) to copy your session.
                                    </p>
                                    <Popover.Arrow className="fill-border" />
                                  </Popover.Content>
                                </Popover.Portal>
                              </Popover.Root>
                            )}
                          </div>
                          
                          {s.action && (
                            <div className="mt-3">
                              <a 
                                href={s.action.href} 
                                target="_blank" 
                                rel="noreferrer"
                                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-background border border-border hover:bg-muted text-xs font-medium transition-colors"
                              >
                                {s.action.label}
                              </a>
                            </div>
                          )}

                          {s.id === 'paste-connect' && (
                            <div className="mt-4 space-y-4">
                              <div className="space-y-1.5">
                                <label className="text-[11px] font-semibold text-foreground ml-1">Account Label <span className="text-muted-foreground font-normal">(Optional)</span></label>
                                <input
                                  value={name}
                                  onChange={e => setName(e.target.value)}
                                  placeholder='Internal label (Defaults to real LinkedIn name)'
                                  className="w-full rounded-lg bg-background border border-input px-3 py-2.5 text-xs text-foreground
                                             placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                                />
                              </div>
                              
                              <div className="space-y-1.5">
                                <label className="text-[11px] font-semibold text-foreground ml-1">LinkedIn Session Cookies</label>
                                <textarea
                                  value={cookieJson}
                                  onChange={e => { setCookieJson(e.target.value); setError(""); setValidated(null) }}
                                  rows={4}
                                  placeholder={`[{"domain":".linkedin.com","name":"li_at","value":"AQEDA...","path":"/"}]`}
                                  className="w-full rounded-lg bg-background border border-input px-3 py-2.5 text-xs font-mono text-foreground
                                             placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 resize-none transition-all"
                                />
                              </div>
                              
                              <div>
                                <label onClick={() => setIsWarmup(!isWarmup)} className="flex items-start gap-3 cursor-pointer mt-2 group p-2 rounded-lg hover:bg-muted/50 transition-colors -ml-2">
                                  <div className={cn("w-4 h-4 mt-0.5 rounded border flex items-center justify-center transition-colors shrink-0",
                                    isWarmup ? "bg-primary border-primary" : "border-input group-hover:border-muted-foreground"
                                  )}>
                                    {isWarmup && <CheckCircle2 size={12} className="text-primary-foreground" />}
                                  </div>
                                  <div>
                                    <span className="text-xs font-semibold text-foreground select-none block">New or Cold Account (Enable 30-day Warmup Mode)</span>
                                    <span className="text-[10px] text-muted-foreground block mt-0.5 leading-relaxed">Gradually increases your daily sending limits over a month to safely build account reputation and prevent restrictions.</span>
                                  </div>
                                </label>

                                <AnimatePresence>
                                  {isWarmup && (
                                    <motion.div
                                      initial={{ height: 0, opacity: 0 }}
                                      animate={{ height: "auto", opacity: 1 }}
                                      exit={{ height: 0, opacity: 0 }}
                                      className="overflow-hidden"
                                    >
                                      <div className="mt-1 ml-7 p-4 pt-5 rounded-xl bg-background/50 border border-border/50 flex gap-2 h-[110px]">
                                        {[
                                          { label: 'Days 1-3', val: '7/day', fill: 'bg-primary/30', h: 'h-[20%]' },
                                          { label: 'Days 4-7', val: '17/day', fill: 'bg-primary/50', h: 'h-[40%]' },
                                          { label: 'Days 8-14', val: '35/day', fill: 'bg-primary/70', h: 'h-[70%]' },
                                          { label: 'Days 15-21', val: '55/day', fill: 'bg-primary', h: 'h-[100%]' },
                                        ].map((w, i) => (
                                          <div key={i} className="flex-1 flex flex-col items-center justify-end gap-1.5">
                                            <span className="text-[10px] font-bold text-foreground">{w.val}</span>
                                            <div className={`w-full max-w-[28px] rounded-t-md ${w.fill} ${w.h} transition-all`} />
                                            <span className="text-[9px] text-muted-foreground font-medium">{w.label}</span>
                                          </div>
                                        ))}
                                      </div>
                                    </motion.div>
                                  )}
                                </AnimatePresence>
                              </div>

                              <div className="space-y-1.5">
                                <div className="flex items-center gap-1.5 ml-1">
                                  <label className="text-[11px] font-semibold text-foreground">Proxy <span className="text-muted-foreground font-normal">(Optional)</span></label>
                                  <Popover.Root>
                                    <Popover.Trigger asChild>
                                      <button 
                                        className="inline-flex items-center justify-center shrink-0 w-3.5 h-3.5 rounded-full bg-muted/50 text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                                        title="What is a proxy?"
                                        onClick={(e) => e.stopPropagation()}
                                      >
                                        <Info size={10} />
                                      </button>
                                    </Popover.Trigger>
                                    <Popover.Portal>
                                      <Popover.Content 
                                        side="top" 
                                        align="start" 
                                        sideOffset={8} 
                                        className="z-[200] w-64 bg-card border border-border rounded-xl shadow-xl p-3 animate-in fade-in zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out data-[state=closed]:zoom-out-95"
                                        onClick={(e) => e.stopPropagation()}
                                      >
                                        <h4 className="text-sm font-semibold mb-1.5">Why use a proxy?</h4>
                                        <p className="text-xs text-muted-foreground mb-2">
                                          LinkedIn closely monitors login locations. If multiple accounts run from the same central server IP, LinkedIn algorithms often flag them as bots.
                                        </p>
                                        <p className="text-xs text-muted-foreground">
                                          Assigning a Proxy gives this specific account a dedicated, safe IP address (like a normal home connection) to completely prevent location-based bans.
                                        </p>
                                        <Popover.Arrow className="fill-border" />
                                      </Popover.Content>
                                    </Popover.Portal>
                                  </Popover.Root>
                                </div>
                                {proxies && proxies.length > 0 ? (
                                  <select
                                    value={proxyId}
                                    onChange={e => setProxyId(e.target.value)}
                                    className="w-full rounded-lg bg-background border border-input px-3 py-2 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                                  >
                                    <option value="">No proxy (Use server IP)</option>
                                    {proxies.map((p: any) => (
                                      <option key={p.id} value={p.id}>
                                        {p.provider} — {p.host}:{p.port}
                                      </option>
                                    ))}
                                  </select>
                                ) : (
                                  <div className="text-[10px] text-muted-foreground bg-muted/50 p-2.5 rounded-lg border border-border/50">
                                    No proxies configured. Running without proxy is riskier but supported.
                                  </div>
                                )}
                              </div>

                              {error && (
                                <div className="flex items-center gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-500 text-xs mt-2">
                                  <AlertCircle size={14} className="shrink-0" />
                                  <p>{error}</p>
                                </div>
                              )}

                              {validating && (
                                <div className="flex items-center gap-2 p-3 rounded-lg bg-primary/10 border border-primary/20 text-primary mt-2">
                                  <div className="w-3.5 h-3.5 rounded-full border-2 border-primary border-t-transparent animate-spin shrink-0" />
                                  <p className="text-xs">Validating cookies on LinkedIn… (takes ~5s)</p>
                                </div>
                              )}

                              {validated?.valid && (
                                <div className="flex items-center gap-3 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 mt-2">
                                  <div className="w-8 h-8 rounded-full bg-emerald-500/20 flex items-center justify-center shrink-0">
                                    <CheckCircle2 size={16} className="text-emerald-500" />
                                  </div>
                                  <div className="min-w-0">
                                    <p className="text-xs text-emerald-600 dark:text-emerald-400 font-bold">Session Connected Successfully!</p>
                                    {validated.profile_url && (
                                      <p className="text-[10px] text-emerald-600/70 dark:text-emerald-400/70 mt-0.5 truncate">{validated.profile_url}</p>
                                    )}
                                  </div>
                                </div>
                              )}
                              
                              <div className="pt-2">
                                <button
                                  onClick={handleValidateAndConnect}
                                  disabled={validating || cookieJson.trim() === ""}
                                  className="w-full flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-sm font-bold transition-all shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                  {validating ? "Connecting..." : "Connect Account"}
                                </button>
                              </div>
                            </div>
                          )}
                          
                          {s.num < 4 && (
                            <div className="mt-5 mb-1 flex">
                              <button 
                                onClick={(e) => { e.stopPropagation(); setStep(s.num + 1) }}
                                className="flex items-center gap-2 px-5 py-2 rounded-lg bg-foreground hover:bg-foreground/90 text-background text-xs font-bold transition-all shadow-sm"
                              >
                                Continue to next step <ChevronRight size={14} />
                              </button>
                            </div>
                          )}
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                </div>
              )
            })}
          </div>
        </SpotlightCard>
      </motion.div>
    </div>
  )
}
