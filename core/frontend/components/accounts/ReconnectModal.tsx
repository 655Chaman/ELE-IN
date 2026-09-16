import { useState, useEffect, useRef } from "react"
import { motion } from "motion/react"
import { X, CheckCircle2, AlertCircle, Info, RefreshCw } from "lucide-react"
import SpotlightCard from "../SpotlightCard"
import { fetchWithAuth } from "@/lib/apiClient"

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
    return () => {
      abortControllerRef.current?.abort()
    }
  }, [])

  const handleReconnect = async () => {
    if (!cookieJson.trim()) {
      setError("Please paste the exported JSON.")
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
      setError('Request timed out. Please try again.')
      setLoading(false)
    }, 30000)

    try {
      const initRes = await fetchWithAuth(`/api/elein/accounts/${accountId}/reconnect/initiate`, { method: "POST", signal })
      if (!initRes.ok) throw new Error("Failed to initiate reconnect")
      const { token } = await initRes.json()

      const compRes = await fetchWithAuth(`/api/elein/accounts/reconnect/complete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, session_cookies_json: cookieJson }),
        signal
      })

      if (!compRes.ok) {
        const err = await compRes.json()
        throw new Error(err.detail || err.error || "Failed to reconnect")
      }

      setSuccess(true)
      setTimeout(() => {
        onSuccess()
        onClose()
      }, 2000)

    } catch (e: any) {
      if (e.name === 'AbortError') {
        // do nothing
      } else {
        setError(e.message)
      }
    } finally {
      clearTimeout(timeoutId)
      if (!isTimeout && !signal.aborted) {
        setLoading(false)
      }
    }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        transition={{ duration: 0.25 }}
        className="w-full max-w-md"
      >
        <SpotlightCard className="p-6 rounded-2xl bg-card border border-border shadow-2xl overflow-hidden" spotlightColor="rgba(255, 255, 255, 0.05)">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-bold text-card-foreground flex items-center gap-2">
              <RefreshCw size={18} className="text-emerald-500" />
              Reconnect {accountName}
            </h2>
            <button onClick={onClose} className="p-1 rounded-md text-muted-foreground hover:bg-muted transition-colors">
              <X size={16} />
            </button>
          </div>

          {!success ? (
            <div className="space-y-4">
              <div className="p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg flex gap-2">
                <Info size={14} className="text-blue-500 shrink-0 mt-0.5" />
                <p className="text-xs text-blue-500 leading-relaxed">
                  Your LinkedIn session has expired. You need to re-export your cookies. Don't worry, <strong>your warmup progress, limits, and campaigns are all preserved.</strong>
                </p>
              </div>

              <div className="space-y-1">
                <p className="text-xs text-foreground font-semibold">1. Open LinkedIn and export cookies</p>
                <p className="text-[11px] text-muted-foreground">Use the EditThisCookie extension to copy your session.</p>
              </div>

              <div className="space-y-1.5">
                <label className="text-[11px] font-semibold text-foreground">2. Paste New Cookies</label>
                <textarea
                  value={cookieJson}
                  onChange={e => setCookieJson(e.target.value)}
                  rows={4}
                  placeholder={`[{"domain":".linkedin.com","name":"li_at",...}]`}
                  className="w-full rounded-lg bg-background border border-input px-3 py-2 text-xs font-mono text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 resize-none transition-all"
                />
              </div>

              {error && (
                <div className="flex items-center gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-500 text-xs">
                  <AlertCircle size={14} className="shrink-0" />
                  <p>{error}</p>
                </div>
              )}

              <button
                onClick={handleReconnect}
                disabled={loading || !cookieJson.trim()}
                className="w-full flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-sm font-bold transition-all disabled:opacity-50"
              >
                {loading ? "Reconnecting..." : "Reconnect Account"}
              </button>
            </div>
          ) : (
            <div className="py-8 flex flex-col items-center justify-center text-center space-y-3">
              <div className="w-12 h-12 rounded-full bg-emerald-500/20 flex items-center justify-center">
                <CheckCircle2 size={24} className="text-emerald-500" />
              </div>
              <div>
                <p className="text-sm font-bold text-foreground">Session Reconnected!</p>
                <p className="text-xs text-muted-foreground mt-1">Your warmup progress is preserved.</p>
              </div>
            </div>
          )}
        </SpotlightCard>
      </motion.div>
    </div>
  )
}
