import React, { useState, useEffect } from "react"
import { useSearchParams } from "react-router-dom"
import { toast } from "sonner"
import { Check, Copy, ArrowRight } from "lucide-react"
import {
  submitWaitlistSignup,
  fetchWaitlistStats,
  isBusinessEmail,
  extractCompanyFromEmail,
  type WaitlistEntry,
} from "@/lib/waitlistApi"

export function EleInWaitlist() {
  const [searchParams] = useSearchParams()

  const [firstName, setFirstName] = useState("")
  const [lastName, setLastName] = useState("")
  const [email, setEmail] = useState("")
  const [referralCode, setReferralCode] = useState("")
  const [honeypot, setHoneypot] = useState("")

  const [isSubmitting, setIsSubmitting] = useState(false)
  const [activeEntry, setActiveEntry] = useState<WaitlistEntry | null>(null)
  const [hasCopied, setHasCopied] = useState(false)
  const [totalCount, setTotalCount] = useState<number>(385)

  useEffect(() => {
    const refParam = searchParams.get("ref")
    if (refParam) {
      const cleanRef = refParam.trim().toUpperCase()
      setReferralCode(cleanRef)
      try {
        localStorage.setItem("elein_referrer", cleanRef)
      } catch (_) {}
    } else {
      try {
        const storedRef = localStorage.getItem("elein_referrer")
        if (storedRef) setReferralCode(storedRef)
      } catch (_) {}
    }

    fetchWaitlistStats()
      .then((count) => {
        if (count && count > 0) setTotalCount(count)
      })
      .catch(() => {})
  }, [searchParams])

  const emailTrimmed = email.trim().toLowerCase()
  const hasValidEmailFormat = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(emailTrimmed)
  const isWorkEmail = hasValidEmailFormat ? isBusinessEmail(emailTrimmed) : false
  const detectedCompany = isWorkEmail ? extractCompanyFromEmail(emailTrimmed) : null

  const handleJoinSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    const cleanFirst = firstName.trim()
    const cleanLast = lastName.trim()
    if (!cleanFirst || !cleanLast) {
      toast.error("Please enter both your first and last name.")
      return
    }

    const cleanEmail = emailTrimmed
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!cleanEmail || !emailRegex.test(cleanEmail)) {
      toast.error("Please enter a valid email address.")
      return
    }

    const combinedFullName = `${cleanFirst} ${cleanLast}`.trim()

    setIsSubmitting(true)
    try {
      const entry = await submitWaitlistSignup({
        email: cleanEmail,
        full_name: combinedFullName,
        first_name: cleanFirst,
        last_name: cleanLast,
        referred_by_code: referralCode || undefined,
        hp_website_security: honeypot || undefined,
      })

      setActiveEntry(entry)
      if (entry.status === "already_registered") {
        toast.info("Welcome back. Here is your access pass.")
      } else {
        toast.success(entry.is_business_customer ? "Priority B2B access secured." : "Spot reserved.")
        setTotalCount((prev) => prev + 1)
      }
    } catch (err: any) {
      toast.error(err?.message || "Unable to join right now. Please try again.")
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleCopyLink = () => {
    if (!activeEntry?.referral_code) return
    const link = `https://ele-in.com?ref=${activeEntry.referral_code}`
    if (navigator?.clipboard?.writeText) {
      navigator.clipboard
        .writeText(link)
        .then(() => {
          setHasCopied(true)
          toast.success("Link copied to clipboard.")
          setTimeout(() => setHasCopied(false), 2000)
        })
        .catch(() => {
          toast.error("Failed to copy link.")
        })
    } else {
      setHasCopied(true)
      toast.success("Link: " + link)
      setTimeout(() => setHasCopied(false), 2000)
    }
  }

  const handleReset = () => {
    setActiveEntry(null)
    setFirstName("")
    setLastName("")
    setEmail("")
  }

  const shareUrl = activeEntry?.referral_code
    ? `https://ele-in.com?ref=${activeEntry.referral_code}`
    : "https://ele-in.com"

  const isEssential = Boolean(activeEntry?.is_business_customer)
  const companyName = activeEntry?.company

  const getDisplayName = (entry: WaitlistEntry | null) => {
    if (!entry) return "Founder"
    if (entry.full_name && entry.full_name.trim().length > 0) return entry.full_name.trim()
    if (entry.first_name) {
      return `${entry.first_name} ${entry.last_name || ""}`.trim()
    }
    if (entry.email) {
      const handle = entry.email.split("@")[0] || ""
      return handle.charAt(0).toUpperCase() + handle.slice(1)
    }
    return "Founder"
  }

  const displayName = getDisplayName(activeEntry)

  const xPostText = isEssential
    ? `Automating our outbound prospecting without the manual grind.

Just joined priority access for @ele_in — autonomous LinkedIn prospecting and personalized conversations on autopilot.

Waitlist: ${shareUrl}`
    : `Scaling outbound prospecting without the manual grind.

Just joined the waitlist for @ele_in — autonomous LinkedIn prospecting and messaging on autopilot.

Waitlist: ${shareUrl}`

  const linkedInPostText = isEssential
    ? `Outbound prospecting on LinkedIn shouldn't take 20 hours a week of manual copy-pasting.

I just secured priority early access to Ele-in${companyName ? ` for ${companyName}` : ""}.

Ele-in runs LinkedIn prospecting on autopilot: finding ICP leads, initiating warm conversations, and booking meetings directly into your calendar.

If you run B2B outbound, check it out here:
${shareUrl}`
    : `Outbound prospecting on LinkedIn shouldn't take 20 hours a week of manual copy-pasting.

I just joined the waitlist for Ele-in — an autonomous engine that finds ICP leads, initiates personalized conversations, and books qualified meetings on autopilot.

Check out the early access waitlist:
${shareUrl}`

  const handleShareLinkedIn = () => {
    navigator.clipboard?.writeText(linkedInPostText).then(() => {
      toast.success("Post text copied. Opening LinkedIn...")
    }).catch(() => {})
    window.open(`https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(shareUrl)}`, "_blank", "noopener,noreferrer")
  }

  const formattedPositionNumber = String(activeEntry?.position || totalCount || 385).padStart(6, "0")

  return (
    <div className="min-h-screen bg-[#070809] text-zinc-100 flex flex-col justify-between font-sans selection:bg-emerald-900/60 selection:text-white antialiased overflow-x-hidden relative">
      {/* Subtle Ambient Emerald Aura */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-4xl h-96 bg-[radial-gradient(ellipse_at_top,rgba(16,185,129,0.14),transparent_70%)] pointer-events-none -z-10" />

      <main className="w-full max-w-[380px] sm:max-w-[400px] mx-auto px-4 py-12 sm:py-20 text-center my-auto flex flex-col items-center relative z-10">
        {/* Brand Mark with Ele-in Emerald Glow */}
        <div className="mb-7 flex flex-col items-center justify-center">
          <div className="relative group">
            <div className="absolute -inset-1 rounded-2xl bg-gradient-to-br from-emerald-500/25 to-emerald-700/0 blur-md opacity-80" />
            <div className="relative w-12 h-12 rounded-2xl p-1 bg-[#0a1410] border border-emerald-500/30 flex items-center justify-center overflow-hidden shadow-lg shadow-emerald-950/40">
              <img
                src="/logo-icon.png"
                alt="Ele-in"
                className="w-full h-full object-cover rounded-[10px]"
              />
            </div>
          </div>
          <span className="mt-3 text-[11px] font-mono tracking-[0.25em] text-emerald-500/80 uppercase font-semibold select-none">
            Ele-in
          </span>
        </div>

        {!activeEntry ? (
          /* ========================================================================= */
          /* 1. PRE-SIGNUP VIEW (Clean Layout with Ele-in Emerald & Obsidian Identity) */
          /* ========================================================================= */
          <>
            <h1 className="text-[28px] sm:text-[32px] font-semibold tracking-tight text-white leading-tight font-sans">
              LinkedIn outreach, automated
            </h1>

            <p className="mt-2.5 text-[14px] text-zinc-400 max-w-[340px] mx-auto leading-relaxed font-sans">
              Stop sending manual messages. Ele-in finds leads and books qualified meetings on autopilot.
            </p>

            <form onSubmit={handleJoinSubmit} className="mt-8 w-full space-y-3 text-left">
              <div className="grid grid-cols-2 gap-2.5">
                <div>
                  <input
                    type="text"
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                    placeholder="First name"
                    required
                    className="w-full h-[48px] bg-zinc-900/70 border border-zinc-800 hover:border-zinc-700 focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500/40 focus:outline-none rounded-xl px-4 text-white placeholder-zinc-500 text-base sm:text-[14px] transition-all font-sans"
                  />
                </div>
                <div>
                  <input
                    type="text"
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                    placeholder="Last name"
                    required
                    className="w-full h-[48px] bg-zinc-900/70 border border-zinc-800 hover:border-zinc-700 focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500/40 focus:outline-none rounded-xl px-4 text-white placeholder-zinc-500 text-base sm:text-[14px] transition-all font-sans"
                  />
                </div>
              </div>

              <div>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="Enter your work email"
                  required
                  className="w-full h-[48px] bg-zinc-900/70 border border-zinc-800 hover:border-zinc-700 focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500/40 focus:outline-none rounded-xl px-4 text-white placeholder-zinc-500 text-base sm:text-[14px] transition-all font-sans"
                />
                {hasValidEmailFormat && (
                  <div className="mt-2 text-left px-1">
                    {isWorkEmail ? (
                      <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-[12px] text-emerald-400 font-sans">
                        <span className="size-1.5 rounded-full bg-emerald-400 shrink-0 animate-pulse" />
                        <span>Priority B2B Access unlocked {detectedCompany ? `(${detectedCompany})` : ""}</span>
                      </div>
                    ) : (
                      <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-zinc-900 border border-zinc-800 text-[12px] text-zinc-400 font-sans">
                        <span className="size-1.5 rounded-full bg-zinc-500 shrink-0" />
                        <span>Personal email · Use work email for priority queue</span>
                      </div>
                    )}
                  </div>
                )}
              </div>

              <input
                type="text"
                name="hp_website_security"
                value={honeypot}
                onChange={(e) => setHoneypot(e.target.value)}
                tabIndex={-1}
                autoComplete="off"
                className="hidden"
              />

              {/* The Signature Ele-in Emerald Primary CTA */}
              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full h-[48px] mt-4 rounded-xl bg-emerald-500 hover:bg-emerald-400 active:scale-[0.99] text-zinc-950 font-semibold text-[15px] shadow-lg shadow-emerald-500/20 hover:shadow-emerald-500/30 transition-all cursor-pointer disabled:opacity-50 font-sans flex items-center justify-center gap-2 group"
              >
                {isSubmitting ? (
                  <span>Reserving spot...</span>
                ) : (
                  <>
                    <span>Join the waitlist</span>
                    <ArrowRight className="size-4 text-zinc-950/80 group-hover:translate-x-0.5 transition-transform" />
                  </>
                )}
              </button>
            </form>

            {/* Subtle Founder Discount & Cohort Release Note */}
            <div className="mt-5 flex items-center justify-center gap-2 text-[12px] text-zinc-400 font-sans">
              <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-emerald-500/10 text-emerald-400 font-mono text-[11px] font-medium border border-emerald-500/20">
                EARLY30
              </span>
              <span>Locks 30% founder pricing for early cohorts</span>
            </div>
          </>
        ) : (
          /* ========================================================================= */
          /* 2. POST-SIGNUP VIEW (Ele-in Emerald & Obsidian VIP Access Pass)          */
          /* ========================================================================= */
          <div className="w-full flex flex-col items-center text-center">
            <h1 className="text-[28px] sm:text-[32px] font-semibold tracking-tight text-white leading-tight font-sans">
              Spot #{formattedPositionNumber} reserved
            </h1>

            <p className="mt-2.5 text-[14px] text-zinc-400 max-w-[340px] mx-auto leading-relaxed font-sans">
              Reserved for {displayName}
              {companyName ? ` · ${companyName}` : ""}. We'll notify you as soon as your cohort opens.
            </p>

            {/* Premium Obsidian & Emerald Pass Card */}
            <div className="w-full mt-6 rounded-2xl bg-zinc-950/80 backdrop-blur-md border border-emerald-500/25 p-5 sm:p-6 text-left shadow-2xl shadow-emerald-950/30 relative overflow-hidden">
              {/* Subtle top edge gradient highlight */}
              <div className="absolute top-0 inset-x-0 h-px bg-gradient-to-r from-transparent via-emerald-400/40 to-transparent" />

              <div className="flex items-center justify-between pb-3.5 border-b border-zinc-800">
                <span className="text-[11px] uppercase tracking-wider text-zinc-400 font-mono font-medium">
                  Access Pass
                </span>
                <span className={`text-[11px] font-mono px-2.5 py-0.5 rounded-full border ${
                  isEssential 
                    ? "bg-emerald-500/15 border-emerald-500/30 text-emerald-400" 
                    : "bg-zinc-800 border-zinc-700 text-zinc-300"
                }`}>
                  {isEssential ? "Priority B2B" : "Cohort 1"}
                </span>
              </div>

              <div className="py-5 text-center">
                <span className="text-[11px] text-zinc-500 uppercase tracking-widest block mb-1 font-mono">
                  Queue Position
                </span>
                <div className="text-4xl sm:text-5xl font-mono font-bold text-white tracking-tight">
                  #{formattedPositionNumber}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 text-[12px] border-t border-zinc-800 pt-3.5">
                <div className="bg-zinc-900/60 rounded-xl p-3 border border-zinc-800">
                  <span className="text-[10px] text-zinc-500 uppercase block font-mono">Tier</span>
                  <span className="font-medium text-white truncate block mt-0.5 font-sans">
                    {isEssential ? "Priority B2B" : "Standard"}
                  </span>
                </div>
                <div className="bg-emerald-950/20 rounded-xl p-3 border border-emerald-500/20">
                  <span className="text-[10px] text-emerald-500/80 uppercase block font-mono">Discount</span>
                  <span className="font-medium text-emerald-400 truncate block mt-0.5 font-sans">
                    30% off (EARLY30)
                  </span>
                </div>
              </div>

              <div className="mt-4 pt-3.5 border-t border-zinc-800">
                <div className="text-[12px] text-zinc-400 mb-2 font-sans">
                  Move up 5 spots for each teammate you invite:
                </div>
                <div className="flex gap-2">
                  <input
                    type="text"
                    readOnly
                    value={shareUrl}
                    className="flex-1 bg-zinc-900/80 border border-zinc-800 rounded-xl px-3 py-2 text-base sm:text-xs text-zinc-300 font-mono select-all focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={handleCopyLink}
                    className="flex items-center gap-1.5 px-4 py-2 bg-emerald-500 hover:bg-emerald-400 text-zinc-950 text-xs font-semibold rounded-xl transition-all shrink-0 cursor-pointer font-sans shadow-sm"
                  >
                    {hasCopied ? (
                      <>
                        <Check className="size-3.5 text-zinc-950" />
                        <span>Copied</span>
                      </>
                    ) : (
                      <>
                        <Copy className="size-3.5 text-zinc-950" />
                        <span>Copy</span>
                      </>
                    )}
                  </button>
                </div>

                {/* Social Share Buttons */}
                <div className="mt-3.5 grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={handleShareLinkedIn}
                    className="flex items-center justify-center gap-1.5 py-2.5 px-3 rounded-xl bg-zinc-900 hover:bg-zinc-850 border border-zinc-800 hover:border-zinc-700 text-[13px] font-medium text-zinc-200 hover:text-white transition-all cursor-pointer font-sans"
                  >
                    <svg className="size-3.5 fill-current text-zinc-400 shrink-0" viewBox="0 0 24 24">
                      <path d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.28 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.75M6.46 10.9v8.37H9.2V10.9H6.46M7.83 6.45c-.95 0-1.72.78-1.72 1.73s.77 1.73 1.72 1.73s.77 1.73 1.72 1.73-.78 1.73-1.73-.78-1.73-1.73Z"/>
                    </svg>
                    <span>LinkedIn</span>
                  </button>

                  <a
                    href={`https://twitter.com/intent/tweet?text=${encodeURIComponent(xPostText)}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center justify-center gap-1.5 py-2.5 px-3 rounded-xl bg-zinc-900 hover:bg-zinc-850 border border-zinc-800 hover:border-zinc-700 text-[13px] font-medium text-zinc-200 hover:text-white transition-all font-sans"
                  >
                    <svg className="size-3.5 fill-current text-zinc-400 shrink-0" viewBox="0 0 24 24">
                      <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
                    </svg>
                    <span>Post on X</span>
                  </a>
                </div>
              </div>
            </div>

            <div className="mt-5 text-center">
              <button
                type="button"
                onClick={handleReset}
                className="py-2 px-3 text-[12px] text-zinc-500 hover:text-zinc-400 transition-colors cursor-pointer font-sans inline-block"
              >
                Register another email
              </button>
            </div>
          </div>
        )}
      </main>

      {/* Minimal Symmetrical Footer */}
      <footer className="w-full max-w-[380px] sm:max-w-[400px] mx-auto px-4 pb-8 pt-2 text-center text-[12px] text-zinc-600 font-sans relative z-10">
        <div>© 2026 Ele-in · All rights reserved</div>
      </footer>
    </div>
  )
}
