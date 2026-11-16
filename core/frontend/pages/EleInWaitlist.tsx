import React, { useState, useEffect } from "react"
import { useSearchParams } from "react-router-dom"
import { toast } from "sonner"
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
        toast.success(entry.is_business_customer ? "Priority B2B pass secured!" : "Spot reserved on the waitlist!")
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

  const xPostText = isEssential
    ? `Automating our LinkedIn outbound without the manual copy-paste grind.

Just joined the priority access queue for @ele_in — autonomous lead discovery, context-aware personalized messaging, and meeting booking.

Early access waitlist: ${shareUrl}`
    : `Outbound on LinkedIn is either 10 hours a week of manual copy-paste or spam.

Excited to see how @ele_in solves this — autonomous prospecting, personalized messaging, and meeting booking on autopilot.

Grab a spot on the waitlist: ${shareUrl}`

  const linkedInPostText = isEssential
    ? `Outbound prospecting on LinkedIn shouldn't require 15+ hours a week of manual lead searching and repetitive messages.

I just claimed priority early access to Ele-in${companyName ? ` for ${companyName}` : ""}.

It's built as an autonomous LinkedIn outbound engine:
• Discovers and verifies high-intent ICP leads
• Initiates personalized, context-aware conversations (no generic templates)
• Books qualified meetings directly into your calendar

If you're looking to scale your B2B pipeline on autopilot, grab an early access spot here:
${shareUrl}`
    : `Outbound prospecting on LinkedIn shouldn't be a manual full-time grind.

Excited to join the waitlist for Ele-in — an autonomous LinkedIn outreach engine that finds qualified leads, initiates personalized conversations, and books meetings on autopilot.

Key capabilities that caught my eye:
• Multi-source intent lead discovery
• Hyper-personalized conversation openers (not generic templates)
• Automated meeting scheduling directly to calendar

If you're exploring modern sales automation and AI pipeline generation, check it out here:
${shareUrl}`

  const handleShareLinkedIn = () => {
    navigator.clipboard?.writeText(linkedInPostText).then(() => {
      toast.success("Post text copied to clipboard! Paste it into your LinkedIn post.")
    }).catch(() => {})
    window.open(`https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(shareUrl)}`, "_blank", "noopener,noreferrer")
  }

  const formattedPositionNumber = String(activeEntry?.position || totalCount || 385).padStart(6, "0")

  return (
    <div className="min-h-screen bg-[#060708] text-zinc-100 flex flex-col justify-between font-sans selection:bg-zinc-800 selection:text-white antialiased">
      {/* Central Symmetrical Hero */}
      <main className="w-full max-w-2xl mx-auto px-6 py-12 sm:py-16 text-center my-auto flex flex-col items-center">
        {/* Wordmark */}
        <span className="text-[11px] font-mono tracking-[0.32em] text-zinc-500 uppercase mb-4 select-none">
          Ele-in
        </span>

        {/* Enlarged Visually Appealing Brand Mark */}
        <div className="relative mb-8 sm:mb-10 flex items-center justify-center">
          {/* Subtle deep ambient glow behind the logo */}
          <div className="absolute inset-0 rounded-3xl bg-emerald-500/10 blur-xl -z-10" />

          {/* Squircle logo container with emerald accent stroke */}
          <div className="w-24 h-24 sm:w-28 sm:h-28 rounded-2xl sm:rounded-3xl p-1 bg-[#001507] border border-emerald-500/25 shadow-2xl shadow-emerald-950/80 flex items-center justify-center overflow-hidden">
            <img
              src="/logo-icon.png"
              alt="Ele-in"
              className="w-full h-full object-cover rounded-xl sm:rounded-2xl"
            />
          </div>
        </div>

        <h1 className="text-4xl sm:text-5xl md:text-6xl font-medium tracking-tight text-white font-heading leading-[1.12] text-balance">
          LinkedIn outreach, automated.
        </h1>

        <p className="mt-5 text-sm sm:text-base text-zinc-400 max-w-md mx-auto leading-relaxed text-balance font-normal">
          Stop sending manual messages. Ele-in finds leads, initiates conversations, and books qualified meetings on autopilot.
        </p>

        {!activeEntry ? (
          <div className="mt-8 max-w-md mx-auto w-full">
            <form onSubmit={handleJoinSubmit} className="space-y-2.5">
              <div className="grid grid-cols-2 gap-2">
                <input
                  type="text"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  placeholder="First name"
                  required
                  className="w-full bg-zinc-900/60 border border-zinc-800/80 hover:border-zinc-700/80 focus:border-zinc-500 rounded-xl px-4 py-3 text-white placeholder-zinc-500 text-sm focus:outline-none transition-colors"
                />
                <input
                  type="text"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  placeholder="Last name"
                  required
                  className="w-full bg-zinc-900/60 border border-zinc-800/80 hover:border-zinc-700/80 focus:border-zinc-500 rounded-xl px-4 py-3 text-white placeholder-zinc-500 text-sm focus:outline-none transition-colors"
                />
              </div>

              <div>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="Enter your work email"
                  required
                  className="w-full bg-zinc-900/60 border border-zinc-800/80 hover:border-zinc-700/80 focus:border-zinc-500 rounded-xl px-4 py-3 text-white placeholder-zinc-500 text-sm focus:outline-none transition-colors"
                />
                {hasValidEmailFormat && (
                  <div className="mt-2 text-left px-1">
                    {isWorkEmail ? (
                      <div className="flex items-center gap-1.5 text-xs text-emerald-400 font-mono">
                        <span className="size-1.5 rounded-full bg-emerald-400 animate-pulse" />
                        <span>Essential Customer recognized {detectedCompany ? `(${detectedCompany})` : ""} · Priority queue unlocked</span>
                      </div>
                    ) : (
                      <div className="flex items-center gap-1.5 text-xs text-zinc-500 font-mono">
                        <span className="size-1.5 rounded-full bg-zinc-500" />
                        <span>Personal email · Tip: Use your work email to unlock Essential Customer priority</span>
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
                className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-sm py-3 px-6 rounded-xl transition-colors cursor-pointer disabled:opacity-50 mt-1"
              >
                {isSubmitting ? "Joining waitlist..." : "Join the waitlist"}
              </button>
            </form>
          </div>
        ) : (
          /* Post-Join State: Clean Minimalist Pass */
          <div className="mt-10 max-w-md mx-auto p-7 rounded-2xl bg-zinc-900/40 border border-zinc-800/80 text-center shadow-xl">
            {isEssential ? (
              <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-950/80 border border-emerald-500/30 text-[11px] uppercase tracking-wider text-emerald-400 font-mono mb-2">
                <span className="size-1.5 rounded-full bg-emerald-400 animate-pulse" />
                <span>Essential Customer · Priority Cohort</span>
              </div>
            ) : (
              <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-zinc-800/80 border border-zinc-700/60 text-[11px] uppercase tracking-wider text-zinc-400 font-mono mb-2">
                <span className="size-1.5 rounded-full bg-zinc-400" />
                <span>Standard Waitlist Pass</span>
              </div>
            )}

            <div className={`text-3xl sm:text-4xl font-light tracking-tight font-mono my-2 ${isEssential ? "text-white text-emerald-50 drop-shadow-[0_0_12px_rgba(16,185,129,0.25)]" : "text-zinc-200"}`}>
              #{formattedPositionNumber}
            </div>

            <p className="text-xs text-zinc-400 font-mono mt-1">
              {isEssential ? (
                <>
                  Priority B2B Access for <span className="text-white font-medium">{activeEntry.full_name || activeEntry.email}</span>
                  {activeEntry.company && (
                    <span className="text-emerald-400 font-medium"> · {activeEntry.company}</span>
                  )}
                </>
              ) : (
                <>
                  Reserved for <span className="text-zinc-300">{activeEntry.full_name || activeEntry.email}</span>
                </>
              )}
            </p>

            {isEssential ? (
              <div className="mt-3 flex items-center justify-center gap-2.5 text-[11px] text-zinc-400 font-mono">
                <span className="text-emerald-400">✓ Priority onboarding</span>
                <span className="text-zinc-600">·</span>
                <span className="text-emerald-400">✓ 30% Founder lock</span>
              </div>
            ) : (
              <div className="mt-3 text-[11px] text-zinc-500 font-mono">
                Have a work email? Sign up with your company domain to get Essential Customer priority.
              </div>
            )}

            <div className="mt-6 pt-5 border-t border-zinc-800/80">
              <div className="text-xs text-zinc-400 mb-2.5">
                {isEssential ? "Invite teammates to skip ahead in priority onboarding:" : "Skip 5 spots for each referral:"}
              </div>
              <div className="flex gap-2">
                <input
                  type="text"
                  readOnly
                  value={shareUrl}
                  className="flex-1 bg-black/60 border border-zinc-800/80 rounded-lg px-3 py-2 text-xs text-zinc-300 font-mono text-center select-all focus:outline-none"
                />
                <button
                  type="button"
                  onClick={handleCopyLink}
                  className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-white text-xs font-medium rounded-lg transition-colors cursor-pointer shrink-0"
                >
                  {hasCopied ? "Copied" : "Copy"}
                </button>
              </div>

              <div className="mt-4 flex items-center justify-center gap-2.5">
                <button
                  type="button"
                  onClick={handleShareLinkedIn}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[#0077b5]/15 hover:bg-[#0077b5]/25 border border-[#0077b5]/30 text-xs font-medium text-sky-300 hover:text-white transition-all cursor-pointer shadow-xs"
                  title="Copies post copy and opens LinkedIn"
                >
                  <svg className="size-3.5 fill-current text-sky-400 shrink-0" viewBox="0 0 24 24">
                    <path d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.28 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.75M6.46 10.9v8.37H9.2V10.9H6.46M7.83 6.45c-.95 0-1.72.78-1.72 1.73s.77 1.73 1.72 1.73 1.73-.78 1.73-1.73-.78-1.73-1.73-1.73Z"/>
                  </svg>
                  <span>Share on LinkedIn</span>
                </button>

                <a
                  href={`https://twitter.com/intent/tweet?text=${encodeURIComponent(xPostText)}`}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 text-xs font-medium text-zinc-300 hover:text-white transition-all shadow-xs"
                >
                  <svg className="size-3.5 fill-current text-zinc-100 shrink-0" viewBox="0 0 24 24">
                    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
                  </svg>
                  <span>Share on X</span>
                </a>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Symmetrical Minimal Footer */}
      <footer className="w-full max-w-md mx-auto px-6 pb-12 pt-4 text-center text-[11px] font-mono text-zinc-600">
        <div>© 2026 Ele-in · All rights reserved</div>
      </footer>
    </div>
  )
}
