import React, { useState, useMemo } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import { X, CheckCircle2, AlertCircle, RefreshCw, KeyRound, ShieldCheck, Clipboard } from 'lucide-react'
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
  const [cookieInput, setCookieInput] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(false)

  // Layer 2 Paranoia: Close on Escape key
  React.useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !loading) onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose, loading])

  // ─── Three-Layer Paranoia: Client-side Universal Cookie Normalizer & Format Sniffer ───
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

  const handleRenew = async () => {
    if (!parsedCookieInfo?.valid) {
      setError(parsedCookieInfo?.warning || parsedCookieInfo?.error || "Please enter valid LinkedIn session cookies.")
      return
    }

    const payloadJson = parsedCookieInfo.normalized
    setLoading(true)
    setError('')

    try {
      const res = await fetchWithAuth(`/api/elein/accounts/${accountId}/renew-session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_cookies_json: payloadJson })
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
        }, 1200)
      } else {
        setError(data.detail || data.error || 'Failed to verify new session with LinkedIn.')
      }
    } catch (e: any) {
      setError(e.message || 'Network error occurred during session renewal.')
    } finally {
      setLoading(false)
    }
  }

  const handlePasteClipboard = async () => {
    try {
      const text = await navigator.clipboard.readText()
      if (text) {
        setCookieInput(text.trim())
        setError('')
      }
    } catch {
      toast.info('Clipboard access unavailable. Please paste manually.')
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="renew-session-title"
      onClick={onClose}
      className="fixed inset-0 z-[120] flex items-center justify-center bg-black/50 backdrop-blur-sm p-4 animate-in fade-in duration-200"
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.97, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.97, y: 8 }}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-lg rounded-xl bg-card border border-border shadow-2xl overflow-hidden flex flex-col p-6 space-y-4 text-foreground"
      >
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center text-primary shrink-0">
              <KeyRound size={18} />
            </div>
            <div>
              <h2 id="renew-session-title" className="text-base font-semibold tracking-tight text-foreground">
                Renew LinkedIn Session
              </h2>
              <p className="text-xs text-muted-foreground">
                Account: <strong className="text-foreground">{accountName}</strong>
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close modal"
            className="w-8 h-8 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted flex items-center justify-center transition-colors cursor-pointer"
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
              <div className="p-3 rounded-lg bg-muted/20 border border-border/70 flex items-center gap-2.5 text-xs text-muted-foreground leading-relaxed">
                <ShieldCheck size={16} className="text-success shrink-0" />
                <p>
                  Renewing session cookies refreshes your connection without resetting warmup progress, daily counters, or paused campaign sequences.
                </p>
              </div>

              {/* Textarea */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <label className="text-foreground font-medium">
                    New Cookie Token (<code className="text-primary font-mono font-semibold">li_at</code> or JSON)
                  </label>
                  <button
                    type="button"
                    onClick={handlePasteClipboard}
                    className="text-primary hover:text-primary/80 font-medium flex items-center gap-1 cursor-pointer focus:outline-none"
                  >
                    <Clipboard size={12} />
                    <span>Paste from Clipboard</span>
                  </button>
                </div>

                <textarea
                  value={cookieInput}
                  onChange={e => { setCookieInput(e.target.value); setError('') }}
                  rows={3}
                  placeholder="Paste your new li_at value (AQEDA...) or EditThisCookie JSON export"
                  className="w-full px-3 py-2 rounded-lg bg-background border border-input text-foreground font-mono text-xs placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary resize-none transition-all"
                />

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

              {error && (
                <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-xs text-destructive flex items-center gap-2">
                  <AlertCircle size={15} className="shrink-0" />
                  <span className="font-medium">{error}</span>
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-3.5 py-2 rounded-xl text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted border border-border transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleRenew}
                  disabled={loading || !parsedCookieInfo?.valid}
                  className="px-4 py-2 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold transition-all shadow-xs flex items-center gap-1.5 disabled:opacity-50 cursor-pointer focus:outline-none focus:ring-2 focus:ring-ring"
                >
                  <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
                  <span>{loading ? "Verifying with LinkedIn..." : "Verify & Renew Session"}</span>
                </button>
              </div>
            </motion.div>
          ) : (
            <motion.div
              key="success"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="py-8 flex flex-col items-center justify-center text-center space-y-2.5"
            >
              <div className="w-12 h-12 rounded-full bg-success/10 border border-success/30 flex items-center justify-center text-success">
                <CheckCircle2 size={24} />
              </div>
              <h3 className="text-base font-semibold text-foreground">Session Renewed</h3>
              <p className="text-xs text-muted-foreground max-w-sm">
                Your credentials were encrypted and all campaign senders are operational.
              </p>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  )
}
