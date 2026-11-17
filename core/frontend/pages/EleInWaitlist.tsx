import React, { useState, useEffect } from "react"
import { useSearchParams } from "react-router-dom"
import { toast } from "sonner"
import { Check, Copy } from "lucide-react"
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
        toast.success(entry.is_business_customer ? "Priority access secured." : "Spot reserved.")
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
    ? `Automating our LinkedIn outbound without the manual grind.

Just joined priority access for @ele_in — autonomous prospecting and personalized outreach on autopilot.

Waitlist: ${shareUrl}`
    : `Scaling LinkedIn outreach without the manual grind.

Just joined the waitlist for @ele_in — autonomous prospecting and messaging on autopilot.

Waitlist: ${shareUrl}`

  const linkedInPostText = isEssential
    ? `Outbound prospecting on LinkedIn shouldn't be a manual full-time grind.

I just claimed priority early access to Ele-in${companyName ? ` for ${companyName}` : ""}.

It's an autonomous LinkedIn outreach engine that discovers qualified leads, initiates personalized conversations, and books meetings on autopilot.

Early access waitlist:
${shareUrl}`
    : `Outbound prospecting on LinkedIn shouldn't be a manual full-time grind.

I just joined the waitlist for Ele-in — an autonomous LinkedIn outreach engine that discovers qualified leads, initiates personalized conversations, and books meetings on autopilot.

Early access waitlist:
${shareUrl}`

  const handleShareLinkedIn = () => {
    navigator.clipboard?.writeText(linkedInPostText).then(() => {
      toast.success("Post text copied. Opening LinkedIn...")
    }).catch(() => {})
    window.open(`https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(shareUrl)}`, "_blank", "noopener,noreferrer")
  }

  const formattedPositionNumber = String(activeEntry?.position || totalCount || 385).padStart(6, "0")

  return (
    <div className="min-h-screen bg-[#060708] text-zinc-100 flex flex-col justify-between font-sans selection:bg-zinc-800 selection:text-white antialiased overflow-x-hidden">
      <main className="w-full max-w-sm sm:max-w-md mx-auto px-4 py-8 sm:py-14 text-center my-auto flex flex-col items-center">
        {/* Wordmark */}
        <span className="text-[11px] tracking-[0.28em] text-zinc-500 uppercase mb-3 select-none font-sans">
          {activeEntry ? "Access Confirmed" : "Ele-in"}
        </span>

        {/* Brand Mark */}
        <div className="relative mb-5 sm:mb-7 flex items-center justify-center">
          <div className="absolute inset-0 rounded-2xl bg-emerald-500/10 blur-lg -z-10" />
          <div className="w-16 h-16 sm:w-20 sm:h-20 rounded-2xl p-1 bg-[#001507] border border-emerald-500/25 shadow-xl shadow-emerald-950/60 flex items-center justify-center overflow-hidden">
            <img
              src="/logo-icon.png"
              alt="Ele-in"
              className="w-full h-full object-cover rounded-xl"
            />
          </div>
        </div>

        {!activeEntry ? (
          /* ========================================================================= */
          /* 1. PRE-SIGNUP VIEW (Clean, Concise, Responsive)                          */
          /* ========================================================================= */
          <>
            <h1 className="text-3xl sm:text-4xl md:text-5xl font-medium tracking-tight text-white leading-tight font-sans">
              LinkedIn outreach, automated.
            </h1>

            <p className="mt-3 text-sm text-zinc-400 max-w-sm mx-auto leading-relaxed font-sans">
              Find leads, start conversations, and book qualified meetings on autopilot.
            </p>

            <div className="mt-6 w-full">
              <form onSubmit={handleJoinSubmit} className="space-y-2.5">
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="text"
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                    placeholder="First name"
                    required
                    className="w-full bg-zinc-900/60 border border-zinc-800 hover:border-zinc-700 focus:border-zinc-500 rounded-xl px-3.5 py-2.5 text-white placeholder-zinc-500 text-base sm:text-sm focus:outline-none transition-colors font-sans"
                  />
                  <input
                    type="text"
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                    placeholder="Last name"
                    required
                    className="w-full bg-zinc-900/60 border border-zinc-800 hover:border-zinc-700 focus:border-zinc-500 rounded-xl px-3.5 py-2.5 text-white placeholder-zinc-500 text-base sm:text-sm focus:outline-none transition-colors font-sans"
                  />
                </div>

                <div>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="Enter your work email"
                    required
                    className="w-full bg-zinc-900/60 border border-zinc-800 hover:border-zinc-700 focus:border-zinc-500 rounded-xl px-3.5 py-2.5 text-white placeholder-zinc-500 text-base sm:text-sm focus:outline-none transition-colors font-sans"
                  />
                  {hasValidEmailFormat && (
                    <div className="mt-1.5 text-left px-1">
                      {isWorkEmail ? (
                        <div className="flex items-center gap-1.5 text-xs text-emerald-400 font-sans">
                          <span className="size-1.5 rounded-full bg-emerald-400" />
                          <span>Priority B2B Access unlocked {detectedCompany ? `(${detectedCompany})` : ""}</span>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1.5 text-xs text-zinc-500 font-sans">
                          <span className="size-1.5 rounded-full bg-zinc-500" />
                          <span>Personal email · Use work email for priority access</span>
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

                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-sm py-3 px-5 rounded-xl transition-colors cursor-pointer disabled:opacity-50 mt-1 font-sans"
                >
                  {isSubmitting ? "Securing spot..." : "Join the waitlist"}
                </button>
              </form>
            </div>
          </>
        ) : (
          /* ========================================================================= */
          /* 2. POST-SIGNUP VIEW (Minimal, Professional VIP Card, Mobile-first)        */
          /* ========================================================================= */
          <div className="w-full flex flex-col items-center">
            {/* Minimal Status Pill */}
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-400 font-medium mb-3 font-sans">
              <span className="size-1.5 rounded-full bg-emerald-400" />
              <span>{isEssential ? "Priority B2B Queue" : "Early Access Reserved"}</span>
            </div>

            <h1 className="text-2xl sm:text-3xl font-medium tracking-tight text-white font-sans">
              Spot #{formattedPositionNumber} Secured
            </h1>

            <p className="mt-1.5 text-xs sm:text-sm text-zinc-400 font-sans">
              Reserved for {displayName}
              {companyName ? ` · ${companyName}` : ""}
            </p>

            {/* Clean Minimalist Pass Card */}
            <div className="w-full mt-5 rounded-2xl bg-zinc-900/60 border border-zinc-800 p-4 sm:p-5 text-left shadow-xl">
              {/* Card Header */}
              <div className="flex items-center justify-between pb-3 border-b border-zinc-800/80">
                <span className="text-[11px] tracking-wider text-zinc-400 uppercase font-medium font-sans">
                  Access Pass
                </span>
                <span className="text-[11px] font-mono text-emerald-400">
                  Cohort 1
                </span>
              </div>

              {/* Number Display */}
              <div className="py-4 text-center">
                <span className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-0.5 font-sans">
                  Queue Position
                </span>
                <div className="text-4xl sm:text-5xl font-mono text-white tracking-tight">
                  #{formattedPositionNumber}
                </div>
              </div>

              {/* Compact 2-column info */}
              <div className="grid grid-cols-2 gap-2 text-xs border-t border-zinc-800/80 pt-3">
                <div className="bg-black/40 rounded-lg p-2.5 border border-zinc-800/60">
                  <span className="text-[10px] text-zinc-500 uppercase block font-sans">Tier</span>
                  <span className="font-medium text-zinc-200 truncate block mt-0.5 font-sans">
                    {isEssential ? "Priority B2B" : "Standard"}
                  </span>
                </div>
                <div className="bg-black/40 rounded-lg p-2.5 border border-zinc-800/60">
                  <span className="text-[10px] text-zinc-500 uppercase block font-sans">Benefit</span>
                  <span className="font-medium text-emerald-400 truncate block mt-0.5 font-sans">
                    30% off (EARLY30)
                  </span>
                </div>
              </div>

              {/* Referral Station */}
              <div className="mt-4 pt-3.5 border-t border-zinc-800/80">
                <div className="text-xs text-zinc-400 mb-2 font-sans">
                  Move up 5 spots for each teammate you invite:
                </div>
                <div className="flex gap-2">
                  <input
                    type="text"
                    readOnly
                    value={shareUrl}
                    className="flex-1 bg-black/50 border border-zinc-800 rounded-lg px-3 py-2 text-xs text-zinc-300 font-mono select-all focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={handleCopyLink}
                    className="flex items-center gap-1.5 px-3.5 py-2 bg-zinc-800 hover:bg-zinc-700 text-white text-xs font-medium rounded-lg transition-colors shrink-0 cursor-pointer font-sans"
                  >
                    {hasCopied ? (
                      <>
                        <Check className="size-3.5 text-emerald-400" />
                        <span>Copied</span>
                      </>
                    ) : (
                      <>
                        <Copy className="size-3.5 text-zinc-400" />
                        <span>Copy</span>
                      </>
                    )}
                  </button>
                </div>

                {/* Minimalist Monochrome Social Buttons */}
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={handleShareLinkedIn}
                    className="flex items-center justify-center gap-1.5 py-2.5 px-3 rounded-lg bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 text-xs font-medium text-zinc-200 hover:text-white transition-colors cursor-pointer font-sans"
                  >
                    <svg className="size-3.5 fill-current text-zinc-300 shrink-0" viewBox="0 0 24 24">
                      <path d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.28 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.75M6.46 10.9v8.37H9.2V10.9H6.46M7.83 6.45c-.95 0-1.72.78-1.72 1.73s.77 1.73 1.72 1.73 1.73-.78 1.73-1.73-.78-1.73-1.73Z"/>
                    </svg>
                    <span>LinkedIn</span>
                  </button>

                  <a
                    href={`https://twitter.com/intent/tweet?text=${encodeURIComponent(xPostText)}`}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center justify-center gap-1.5 py-2.5 px-3 rounded-lg bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 text-xs font-medium text-zinc-200 hover:text-white transition-colors font-sans"
                  >
                    <svg className="size-3.5 fill-current text-zinc-300 shrink-0" viewBox="0 0 24 24">
                      <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
                    </svg>
                    <span>Post on X</span>
                  </a>
                </div>
              </div>
            </div>

            {/* Back action */}
            <div className="mt-4 text-center">
              <button
                type="button"
                onClick={() => setActiveEntry(null)}
                className="text-xs text-zinc-500 hover:text-zinc-400 transition-colors cursor-pointer font-sans"
              >
                Register another email
              </button>
            </div>
          </div>
        )}
      </main>

      {/* Symmetrical Minimal Footer */}
      <footer className="w-full max-w-sm sm:max-w-md mx-auto px-4 pb-8 pt-2 text-center text-xs text-zinc-600 font-sans">
        <div>© 2026 Ele-in · All rights reserved</div>
      </footer>
    </div>
  )
}
