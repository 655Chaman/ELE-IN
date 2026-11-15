import React, { useState, useEffect } from "react"
import { useSearchParams } from "react-router-dom"
import { toast } from "sonner"
import {
  submitWaitlistSignup,
  fetchWaitlistStats,
  type WaitlistEntry,
} from "@/lib/waitlistApi"

export function EleInWaitlist() {
  const [searchParams] = useSearchParams()

  // Primary Applicant State
  const [firstName, setFirstName] = useState("")
  const [lastName, setLastName] = useState("")
  const [email, setEmail] = useState("")
  const [company, setCompany] = useState("")
  const [role, setRole] = useState("")
  const [linkedinUrl, setLinkedinUrl] = useState("")
  const [outboundVolume, setOutboundVolume] = useState("")
  const [referralCode, setReferralCode] = useState("")
  const [honeypot, setHoneypot] = useState("")

  // UI Control State
  const [showBooster, setShowBooster] = useState(false)
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

  const handleJoinSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    const cleanFirst = firstName.trim()
    const cleanLast = lastName.trim()
    if (!cleanFirst || !cleanLast) {
      toast.error("Please enter both your first and last name.")
      return
    }

    const cleanEmail = email.trim().toLowerCase()
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!cleanEmail || !emailRegex.test(cleanEmail)) {
      toast.error("Please enter a valid work email.")
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
        company: company.trim() || undefined,
        role: role.trim() || undefined,
        linkedin_url: linkedinUrl.trim() || undefined,
        monthly_outbound_volume: outboundVolume || undefined,
        referred_by_code: referralCode || undefined,
        hp_website_security: honeypot || undefined,
      })

      setActiveEntry(entry)
      if (entry.status === "already_registered") {
        toast.info("Welcome back. Here is your access pass.")
      } else {
        toast.success("VIP Spot reserved! Access pass generated.")
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
        toast.success("Referral link copied to clipboard.")
        setTimeout(() => setHasCopied(false), 2000)
      })
      .catch(() => {
        toast.error("Failed to copy link.")
      })
  }

  const cohortCapacity = 500
  const claimedInCurrentCohort = Math.min(totalCount % cohortCapacity || 385, cohortCapacity)
  const cohortPercent = Math.min(Math.round((claimedInCurrentCohort / cohortCapacity) * 100), 100)
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
          <div className="mt-10 w-full max-w-lg mx-auto">
            <div className="p-6 sm:p-8 rounded-2xl bg-zinc-900/50 backdrop-blur-xl border border-zinc-800/80 shadow-2xl text-left">
              <form onSubmit={handleJoinSubmit} className="space-y-4">
                {/* 1. First & Last Name */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[11px] font-mono uppercase tracking-wider text-zinc-400 mb-1.5">
                      First name <span className="text-emerald-400">*</span>
                    </label>
                    <input
                      type="text"
                      value={firstName}
                      onChange={(e) => setFirstName(e.target.value)}
                      placeholder="Alex"
                      required
                      className="w-full bg-zinc-950/80 border border-zinc-800 focus:border-emerald-500/80 focus:ring-1 focus:ring-emerald-500/30 rounded-xl px-3.5 py-2.5 text-sm text-white placeholder-zinc-600 transition-all outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-mono uppercase tracking-wider text-zinc-400 mb-1.5">
                      Last name <span className="text-emerald-400">*</span>
                    </label>
                    <input
                      type="text"
                      value={lastName}
                      onChange={(e) => setLastName(e.target.value)}
                      placeholder="Mercer"
                      required
                      className="w-full bg-zinc-950/80 border border-zinc-800 focus:border-emerald-500/80 focus:ring-1 focus:ring-emerald-500/30 rounded-xl px-3.5 py-2.5 text-sm text-white placeholder-zinc-600 transition-all outline-none"
                    />
                  </div>
                </div>

                {/* 2. Work Email */}
                <div>
                  <label className="block text-[11px] font-mono uppercase tracking-wider text-zinc-400 mb-1.5">
                    Work email <span className="text-emerald-400">*</span>
                  </label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="alex@company.com"
                    required
                    className="w-full bg-zinc-950/80 border border-zinc-800 focus:border-emerald-500/80 focus:ring-1 focus:ring-emerald-500/30 rounded-xl px-3.5 py-2.5 text-sm text-white placeholder-zinc-600 transition-all outline-none"
                  />
                </div>

                {/* 3. Company & Role */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[11px] font-mono uppercase tracking-wider text-zinc-400 mb-1.5">
                      Company <span className="text-zinc-600 lowercase">(optional)</span>
                    </label>
                    <input
                      type="text"
                      value={company}
                      onChange={(e) => setCompany(e.target.value)}
                      placeholder="Acme Inc"
                      className="w-full bg-zinc-950/80 border border-zinc-800 focus:border-emerald-500/80 focus:ring-1 focus:ring-emerald-500/30 rounded-xl px-3.5 py-2.5 text-sm text-white placeholder-zinc-600 transition-all outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-mono uppercase tracking-wider text-zinc-400 mb-1.5">
                      Role / Title <span className="text-zinc-600 lowercase">(optional)</span>
                    </label>
                    <input
                      type="text"
                      value={role}
                      onChange={(e) => setRole(e.target.value)}
                      placeholder="Head of Growth"
                      className="w-full bg-zinc-950/80 border border-zinc-800 focus:border-emerald-500/80 focus:ring-1 focus:ring-emerald-500/30 rounded-xl px-3.5 py-2.5 text-sm text-white placeholder-zinc-600 transition-all outline-none"
                    />
                  </div>
                </div>

                {/* 4. Priority Booster (Accordion / Fast-track) */}
                <div className="pt-1">
                  <button
                    type="button"
                    onClick={() => setShowBooster(!showBooster)}
                    className="text-xs font-mono text-zinc-400 hover:text-emerald-400 flex items-center gap-1.5 transition-colors cursor-pointer select-none"
                  >
                    <span>{showBooster ? "▾" : "▸"}</span>
                    <span>Fast-track access: LinkedIn & Outreach scale</span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      Skip queue
                    </span>
                  </button>

                  {showBooster && (
                    <div className="mt-3 p-3.5 rounded-xl bg-zinc-950/60 border border-zinc-800/80 space-y-3">
                      <div>
                        <label className="block text-[10px] font-mono uppercase tracking-wider text-zinc-500 mb-1">
                          LinkedIn Profile URL
                        </label>
                        <input
                          type="url"
                          value={linkedinUrl}
                          onChange={(e) => setLinkedinUrl(e.target.value)}
                          placeholder="https://linkedin.com/in/alex-mercer"
                          className="w-full bg-zinc-900/80 border border-zinc-800 focus:border-emerald-500/80 focus:ring-1 focus:ring-emerald-500/30 rounded-lg px-3 py-2 text-xs text-white placeholder-zinc-600 transition-all outline-none font-mono"
                        />
                      </div>
                      <div>
                        <label className="block text-[10px] font-mono uppercase tracking-wider text-zinc-500 mb-1">
                          Target Monthly Outbound Volume
                        </label>
                        <select
                          value={outboundVolume}
                          onChange={(e) => setOutboundVolume(e.target.value)}
                          className="w-full bg-zinc-900/80 border border-zinc-800 focus:border-emerald-500/80 focus:ring-1 focus:ring-emerald-500/30 rounded-lg px-3 py-2 text-xs text-zinc-200 transition-all outline-none"
                        >
                          <option value="">Select outbound volume...</option>
                          <option value="under_1k">Under 1,000 messages / month</option>
                          <option value="1k_5k">1,000 – 5,000 messages / month</option>
                          <option value="5k_20k">5,000 – 20,000 messages / month</option>
                          <option value="20k_plus">20,000+ messages / month (Enterprise)</option>
                        </select>
                      </div>
                    </div>
                  )}
                </div>

                {/* Honeypot Trap (Hidden for bots) */}
                <input
                  type="text"
                  name="hp_website_security"
                  value={honeypot}
                  onChange={(e) => setHoneypot(e.target.value)}
                  tabIndex={-1}
                  autoComplete="off"
                  className="hidden"
                />

                {/* 5. Submit CTA */}
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="w-full bg-emerald-500 hover:bg-emerald-400 text-zinc-950 font-semibold text-sm py-3 px-6 rounded-xl transition-all shadow-lg shadow-emerald-500/20 hover:shadow-emerald-500/30 active:scale-[0.99] cursor-pointer disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {isSubmitting ? (
                    <>
                      <span className="size-4 border-2 border-zinc-950/30 border-t-zinc-950 rounded-full animate-spin" />
                      <span>Securing VIP Access Pass...</span>
                    </>
                  ) : (
                    <span>Claim VIP Early Access</span>
                  )}
                </button>

                {/* Scarcity Meter */}
                <div className="pt-2">
                  <div className="flex items-center justify-between text-[11px] font-mono text-zinc-500 mb-1.5">
                    <span>Cohort 1 Priority Queue</span>
                    <span className="text-emerald-400 font-medium">
                      {claimedInCurrentCohort} / {cohortCapacity} Seats Claimed
                    </span>
                  </div>
                  <div className="w-full bg-zinc-950 border border-zinc-800/80 h-1.5 rounded-full overflow-hidden">
                    <div
                      className="bg-emerald-500 h-full rounded-full transition-all duration-500"
                      style={{ width: `${cohortPercent}%` }}
                    />
                  </div>
                </div>

                {/* Guarantees & Perks */}
                <div className="pt-2 border-t border-zinc-800/60 flex flex-wrap items-center justify-between gap-2 text-[11px] font-mono text-zinc-500">
                  <span className="text-emerald-400/90 flex items-center gap-1">
                    ✓ 30% Founder Discount (EARLY30) Locked
                  </span>
                  <span>Zero spam, ever</span>
                </div>
              </form>
            </div>
          </div>
        ) : (
          /* Post-Join State: Stunning VIP Access Pass */
          <div className="mt-8 w-full max-w-lg mx-auto p-6 sm:p-8 rounded-2xl bg-zinc-900/50 backdrop-blur-xl border border-zinc-800/80 text-center shadow-2xl relative overflow-hidden">
            {/* Top glowing ambient highlight */}
            <div className="absolute top-0 left-1/2 -translate-x-1/2 w-48 h-1 bg-gradient-to-r from-transparent via-emerald-500 to-transparent" />

            <div className="flex items-center justify-between text-[11px] font-mono text-zinc-400 mb-4 border-b border-zinc-800/80 pb-3">
              <span className="text-zinc-500 uppercase tracking-widest">Early Access Confirmed</span>
              <span className="text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-full text-[10px]">
                Cohort 1 VIP Priority
              </span>
            </div>

            <div className="text-4xl sm:text-5xl font-mono font-light tracking-tight text-white my-3">
              #{formattedPositionNumber}
            </div>

            <div className="space-y-1 mb-5">
              <div className="text-base font-medium text-white">
                {activeEntry.full_name}
              </div>
              <div className="text-xs text-zinc-400 font-mono">
                {activeEntry.email} {activeEntry.company ? `· ${activeEntry.company}` : ""}
              </div>
            </div>

            {/* Locked Early Adopter Perks */}
            <div className="p-3.5 rounded-xl bg-zinc-950/80 border border-zinc-800/80 text-left space-y-2 mb-6">
              <div className="text-[10px] font-mono uppercase tracking-wider text-emerald-400 font-semibold">
                VIP Early Adopter Perks Locked:
              </div>
              <div className="flex items-center gap-2 text-xs text-zinc-300">
                <div className="size-1.5 rounded-full bg-emerald-400 shrink-0" />
                <span>30% off all plans for your first 12 months (<span className="font-mono text-emerald-400">EARLY30</span>)</span>
              </div>
              <div className="flex items-center gap-2 text-xs text-zinc-300">
                <div className="size-1.5 rounded-full bg-emerald-400 shrink-0" />
                <span>Priority multi-account LinkedIn sender pod allocation</span>
              </div>
              <div className="flex items-center gap-2 text-xs text-zinc-300">
                <div className="size-1.5 rounded-full bg-emerald-400 shrink-0" />
                <span>Stealth anti-fingerprinting automation pipeline</span>
              </div>
            </div>

            {/* Viral Referral Skip */}
            <div className="pt-4 border-t border-zinc-800/80">
              <div className="text-xs font-medium text-zinc-300 mb-1">
                Want to skip ahead in line?
              </div>
              <div className="text-xs text-zinc-400 mb-3">
                Skip 5 spots for each teammate or colleague who joins with your link:
              </div>

              <div className="flex gap-2">
                <input
                  type="text"
                  readOnly
                  value={`https://ele-in.com?ref=${activeEntry.referral_code}`}
                  className="flex-1 bg-zinc-950 border border-zinc-800 rounded-xl px-3.5 py-2.5 text-xs text-zinc-200 font-mono text-center select-all focus:outline-none"
                />
                <button
                  type="button"
                  onClick={handleCopyLink}
                  className="px-4 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-xl transition-colors cursor-pointer shrink-0"
                >
                  {hasCopied ? "Copied" : "Copy"}
                </button>
              </div>

              <div className="mt-4 flex items-center justify-center gap-4 text-xs font-mono text-zinc-400">
                <a
                  href={`https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(`https://ele-in.com?ref=${activeEntry.referral_code}`)}`}
                  target="_blank"
                  rel="noreferrer"
                  className="hover:text-emerald-400 transition-colors underline"
                >
                  Share on LinkedIn
                </a>
                <span>·</span>
                <a
                  href={`https://twitter.com/intent/tweet?text=${encodeURIComponent(`Just claimed VIP Pass #${formattedPositionNumber} for @Ele_in. Automated LinkedIn outreach: https://ele-in.com?ref=${activeEntry.referral_code}`)}`}
                  target="_blank"
                  rel="noreferrer"
                  className="hover:text-emerald-400 transition-colors underline"
                >
                  Share on X
                </a>
              </div>
            </div>

            <button
              type="button"
              onClick={() => setActiveEntry(null)}
              className="mt-6 text-[11px] font-mono text-zinc-600 hover:text-zinc-400 transition-colors cursor-pointer"
            >
              ← Register another colleague
            </button>
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
