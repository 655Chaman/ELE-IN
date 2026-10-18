import { useState, useEffect, useRef, useMemo } from "react"
import { motion, AnimatePresence } from "motion/react"
import { X, CheckCircle2, AlertCircle, Info, RefreshCw } from "lucide-react"
import { fetchWithAuth } from "@/lib/apiClient"
import { cn } from "@/lib/utils"

interface ReconnectModalProps {
  accountId: string
  accountName: string
  onClose: () => void
  onSuccess: () => void
}

export default function ReconnectModal({ accountId, accountName, onClose, onSuccess }: ReconnectModalProps) {
  const [cookieJson, setCookieJson] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(false)
  const abortControllerRef = useRef<AbortController | null>(null)

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !loading) {
        onClose()
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => {
      window.removeEventListener("keydown", handleKeyDown)
      abortControllerRef.current?.abort()
    }
  }, [onClose, loading])

  // Layer 2: Real-time Cookie JSON sanitization and live structural validation
  const sanitizeCookieJson = (raw: string) => {
    let cleaned = raw.trim()
    if (cleaned.startsWith("```")) {
      cleaned = cleaned.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "").trim()
    }
    return cleaned
  }

  const cookieStatus = useMemo(() => {
    if (!cookieJson.trim()) return null
    const cleaned = sanitizeCookieJson(cookieJson)
    try {
      const parsed = JSON.parse(cleaned)
      if (!Array.isArray(parsed)) {
        return { valid: false, error: "Must be a JSON array of cookies ([{...}])." }
      }
      const hasLiAt = parsed.some((c: any) => c.name === "li_at" && c.value)
      if (!hasLiAt) {
        return { valid: false, warning: "Missing 'li_at' cookie. Make sure you exported while on linkedin.com." }
      }
      return { valid: true, count: parsed.length }
    } catch {
      return { valid: false, error: "Incomplete or invalid JSON syntax." }
    }
  }, [cookieJson])

  const handleReconnect = async () => {
    const cleaned = sanitizeCookieJson(cookieJson)
    if (!cleaned) {
      setError("Please paste the exported JSON.")
      return
    }

    try {
      JSON.parse(cleaned)
    } catch {
      setError("Invalid JSON format. Please re-export from EditThisCookie.")
      return
    }

    setLoading(true)
    setError("")

    abortControllerRef.current = new AbortController()
    const signal = abortControllerRef.current.signal

    let isTimeout = false
    const timeoutId = setTimeout(() => {
      isTimeout = true
      abortControllerRef.current?.abort()
      setError('Request timed out after 30 seconds. Please verify your connection and try again.')
      setLoading(false)
    }, 30000)

    try {
      const initRes = await fetchWithAuth(`/api/elein/accounts/${accountId}/reconnect/initiate`, { method: "POST", signal })
      if (!initRes.ok) {
        const errInit = await initRes.json().catch(() => null)
        throw new Error(errInit?.detail || errInit?.error || "Failed to initiate reconnect")
      }
      const { token } = await initRes.json()

      const compRes = await fetchWithAuth(`/api/elein/accounts/reconnect/complete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, session_cookies_json: cleaned }),
        signal
      })

      if (!compRes.ok) {
        const err = await compRes.json().catch(() => null)
        throw new Error(err?.detail || err?.error || "Failed to reconnect account session.")
      }

      setSuccess(true)
      setTimeout(() => {
        onSuccess()
        onClose()
      }, 2000)

    } catch (e: any) {
      if (e.name === 'AbortError') {
        // Handled by timeout
      } else {
        setError(e.message || 'Connection failed. Please check your credentials and try again.')
      }
    } finally {
      clearTimeout(timeoutId)
      if (!isTimeout && !signal.aborted) {
        setLoading(false)
      }
    }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/30 backdrop-blur-sm p-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        transition={{ duration: 0.25, ease: "easeOut" }}
        className="w-full max-w-[32rem]"
      >
        <div 
          role="dialog"
          aria-modal="true"
          aria-labelledby="reconnect-modal-title"
          className="rounded-xl bg-card border border-border text-card-foreground shadow-2xl overflow-hidden flex flex-col max-h-[calc(100vh-2rem)] p-8"
        >
          
          <div className="flex items-center justify-between mb-6">
            <h2 id="reconnect-modal-title" className="text-[22px] font-bold text-foreground flex items-center gap-2">
              <RefreshCw size={22} className="text-primary" />
              Reconnect {accountName}
            </h2>
            <button 
              type="button"
              aria-label="Close dialog"
              onClick={onClose} 
              className="w-8 h-8 rounded-full bg-muted/60 flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors focus:outline-none focus:ring-2 focus:ring-ring"
            >
              <X size={16} />
            </button>
          </div>

          <AnimatePresence mode="wait">
            {!success ? (
              <motion.div
                key="form"
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -5 }}
                transition={{ duration: 0.2 }}
                className="space-y-6"
              >
                <div className="p-4 bg-primary/5 border border-primary/20 rounded-lg flex gap-3">
                  <Info size={16} className="text-primary shrink-0 mt-0.5" />
                  <p className="text-[14px] text-muted-foreground leading-relaxed">
                    Your LinkedIn session has expired. You need to re-export your cookies. Don't worry, <strong className="text-foreground">your warmup progress, limits, and campaigns are all preserved.</strong>
                  </p>
                </div>

                <div className="space-y-1.5">
                  <p className="text-[14px] text-foreground font-bold">1. Open LinkedIn and export cookies</p>
                  <p className="text-[13px] text-muted-foreground">Use the EditThisCookie extension to copy your session.</p>
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <label htmlFor="reconnect-cookies" className="text-[14px] font-bold text-foreground">
                      2. Paste New Cookies
                    </label>
                    <button
                      type="button"
                      onClick={async () => {
                        try {
                          const text = await navigator.clipboard.readText()
                          if (text) {
                            setCookieJson(text.trim())
                            setError("")
                          }
                        } catch {
                          // Clipboard permission denied
                        }
                      }}
                      className="text-xs font-semibold text-primary hover:text-primary/80 flex items-center gap-1 transition-colors focus:outline-none"
                    >
                      Paste from Clipboard
                    </button>
                  </div>
                  <textarea
                    id="reconnect-cookies"
                    value={cookieJson}
                    onChange={e => { setCookieJson(e.target.value); setError("") }}
                    rows={4}
                    placeholder={'[{"domain":".linkedin.com","name":"li_at",...}]'}
                    className="w-full rounded-lg bg-background border border-input px-4 py-3 text-[13px] font-mono text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary resize-none transition-all"
                  />
                  {cookieStatus && (
                    <div className={cn(
                      "text-xs px-3 py-1.5 rounded-lg flex items-center gap-2 font-medium mt-1.5",
                      cookieStatus.valid 
                        ? "bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-500/20" 
                        : cookieStatus.warning 
                          ? "bg-amber-50 text-amber-700 border border-amber-200 dark:bg-amber-500/10 dark:text-amber-400 dark:border-amber-500/20" 
                          : "bg-destructive/10 text-destructive border border-destructive/20"
                    )}>
                      {cookieStatus.valid ? (
                        <>
                          <CheckCircle2 size={13} className="text-emerald-600 dark:text-emerald-400 shrink-0" />
                          <span>Valid LinkedIn session detected ({cookieStatus.count} cookies, li_at present)</span>
                        </>
                      ) : cookieStatus.warning ? (
                        <>
                          <AlertCircle size={13} className="text-amber-600 dark:text-amber-400 shrink-0" />
                          <span>{cookieStatus.warning}</span>
                        </>
                      ) : (
                        <>
                          <AlertCircle size={13} className="text-destructive shrink-0" />
                          <span>{cookieStatus.error}</span>
                        </>
                      )}
                    </div>
                  )}
                </div>

                {error && (
                  <div className="flex items-center gap-3 p-4 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive">
                    <AlertCircle size={18} className="shrink-0" />
                    <p className="text-[13px] font-medium leading-relaxed">{error}</p>
                  </div>
                )}

                <button
                  type="button"
                  onClick={handleReconnect}
                  disabled={loading || cookieJson.trim() === ""}
                  className="w-full flex items-center justify-center gap-2 px-6 py-3.5 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-sm font-semibold shadow-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed mt-2 focus:outline-none focus:ring-2 focus:ring-ring"
                >
                  {loading ? "Reconnecting..." : "Reconnect Account"}
                </button>
              </motion.div>
            ) : (
              <motion.div
                key="success"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="py-12 flex flex-col items-center justify-center text-center space-y-4"
              >
                <div className="w-16 h-16 rounded-full bg-emerald-500/20 flex items-center justify-center">
                  <CheckCircle2 size={32} className="text-emerald-600 dark:text-emerald-400" />
                </div>
                <div>
                  <p className="text-[18px] font-bold text-foreground">Session Reconnected!</p>
                  <p className="text-[14px] text-muted-foreground mt-1">Your warmup progress is fully preserved.</p>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>
    </div>
  )
}
