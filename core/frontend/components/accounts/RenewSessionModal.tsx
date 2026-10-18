import React, { useState, useMemo } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import { X, CheckCircle2, AlertCircle, Info, RefreshCw, KeyRound, ShieldCheck } from 'lucide-react'
import { toast } from 'sonner'
import { fetchWithAuth } from '@/lib/apiClient'
import { cn } from '@/lib/utils'

interface RenewSessionModalProps {
  accountId: string
  accountName: string
  onClose: () => void
  onSuccess: () => void
}

export function RenewSessionModal({ accountId, accountName, onClose, onSuccess }: RenewSessionModalProps) {
  const [cookieJson, setCookieJson] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(false)

  // Layer 2 Paranoia: Close on Escape key
  React.useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  // Layer 2: Real-time Cookie JSON sanitization and live structural validation
  const sanitizeCookieJson = (raw: string) => {
    let cleaned = raw.trim()
    if (cleaned.startsWith('```')) {
      cleaned = cleaned.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim()
    }
    return cleaned
  }

  const cookieStatus = useMemo(() => {
    if (!cookieJson.trim()) return null
    const cleaned = sanitizeCookieJson(cookieJson)
    try {
      const parsed = JSON.parse(cleaned)
      if (!Array.isArray(parsed)) {
        return { valid: false, error: 'Must be a JSON array of cookies ([{...}]).' }
      }
      const hasLiAt = parsed.some((c: any) => c.name === 'li_at' && c.value)
      if (!hasLiAt) {
        return { valid: false, warning: "Missing 'li_at' cookie. Ensure you exported from linkedin.com while logged in." }
      }
      return { valid: true, count: parsed.length }
    } catch {
      return { valid: false, error: 'Incomplete or invalid JSON syntax.' }
    }
  }, [cookieJson])

  const handleRenew = async () => {
    const cleaned = sanitizeCookieJson(cookieJson)
    if (!cleaned) {
      setError('Please paste the exported LinkedIn cookies.')
      return
    }

    setLoading(true)
    setError('')

    try {
      const res = await fetchWithAuth(`/api/elein/accounts/${accountId}/renew-session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_cookies_json: cleaned })
      })

      const data = await res.json()
      if (res.ok && data.success) {
        setSuccess(true)
        toast.success(`Session renewed for ${accountName}`, {
          description: 'All campaign enrollments and warmup pacing preserved.'
        })
        setTimeout(() => {
          onSuccess()
          onClose()
        }, 1500)
      } else {
        setError(data.detail || data.error || 'Failed to verify new session.')
      }
    } catch (e: any) {
      setError(e.message || 'Network error occurred during session renewal.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="renew-session-title"
      onClick={onClose}
      className="fixed inset-0 z-[120] flex items-center justify-center bg-black/60 backdrop-blur-md p-4 animate-in fade-in duration-200"
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 8 }}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-lg rounded-xl bg-card border border-border shadow-2xl overflow-hidden flex flex-col p-6 space-y-5 text-foreground"
      >
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-10 h-10 rounded-lg bg-primary/10 border border-primary/20 text-primary flex items-center justify-center shrink-0">
              <KeyRound size={20} />
            </div>
            <div>
              <h2 id="renew-session-title" className="text-base font-bold text-foreground">Renew LinkedIn Session</h2>
              <p className="text-xs text-muted-foreground">Account: <strong className="text-foreground">{accountName}</strong></p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close modal"
            className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer shrink-0"
          >
            <X size={16} />
          </button>
        </div>

        <AnimatePresence mode="wait">
          {!success ? (
            <motion.div
              key="form"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="space-y-4"
            >
              {/* Informative Banner */}
              <div className="p-3.5 rounded-lg bg-muted/30 border border-border flex gap-3 text-xs leading-relaxed text-muted-foreground">
                <ShieldCheck size={16} className="text-emerald-500 dark:text-emerald-400 shrink-0 mt-0.5" />
                <p>
                  Renewing session cookies refreshes your connection without resetting warmup progress, daily counters, or paused campaign sequences.
                </p>
              </div>

              {/* Textarea */}
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs font-semibold">
                  <label className="text-foreground font-semibold">Paste New Cookies (JSON)</label>
                  <button
                    type="button"
                    onClick={async () => {
                      try {
                        const text = await navigator.clipboard.readText()
                        if (text) {
                          setCookieJson(text.trim())
                          setError('')
                        }
                      } catch {
                        toast.info('Clipboard access unavailable. Please paste manually.')
                      }
                    }}
                    className="text-primary hover:underline text-[11px] font-semibold cursor-pointer"
                  >
                    Paste from Clipboard
                  </button>
                </div>

                <textarea
                  value={cookieJson}
                  onChange={e => { setCookieJson(e.target.value); setError('') }}
                  rows={4}
                  placeholder={'[{"name":"li_at","value":"AQED...","domain":".linkedin.com"},...]'}
                  className="w-full px-3.5 py-2.5 rounded-lg bg-background border border-border text-foreground font-mono text-xs placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary/50 resize-none"
                />

                {cookieStatus && (
                  <div className={cn(
                    "text-xs px-3 py-1.5 rounded-md flex items-center gap-2 font-medium",
                    cookieStatus.valid ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-300 border border-emerald-500/20" :
                    cookieStatus.warning ? "bg-amber-500/10 text-amber-600 dark:text-amber-300 border border-amber-500/20" :
                    "bg-destructive/10 text-rose-600 dark:text-rose-300 border border-destructive/20"
                  )}>
                    {cookieStatus.valid ? <CheckCircle2 size={13} className="text-emerald-500 dark:text-emerald-400 shrink-0" /> : <AlertCircle size={13} className="text-rose-500 dark:text-rose-400 shrink-0" />}
                    <span>{cookieStatus.valid ? `Valid format detected (${cookieStatus.count} cookies, li_at verified)` : (cookieStatus.warning || cookieStatus.error)}</span>
                  </div>
                )}
              </div>

              {error && (
                <div className="p-3 rounded-md bg-destructive/10 border border-destructive/20 text-xs text-rose-600 dark:text-rose-300 flex items-center gap-2">
                  <AlertCircle size={14} className="shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 rounded-md text-xs font-semibold text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleRenew}
                  disabled={loading || !cookieJson.trim()}
                  className="px-5 py-2 rounded-md bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-bold transition-all shadow-xs flex items-center gap-1.5 disabled:opacity-50 cursor-pointer"
                >
                  <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
                  <span>{loading ? "Verifying with LinkedIn..." : "Verify & Renew Session"}</span>
                </button>
              </div>
            </motion.div>
          ) : (
            <motion.div
              key="success"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="py-8 flex flex-col items-center justify-center text-center space-y-3"
            >
              <div className="w-14 h-14 rounded-full bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-500 dark:text-emerald-400">
                <CheckCircle2 size={28} />
              </div>
              <h3 className="text-base font-bold text-foreground">Session Renewed & Active</h3>
              <p className="text-xs text-muted-foreground max-w-sm">
                Your credentials were encrypted with Supabase Vault and all campaign senders are operational.
              </p>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  )
}
