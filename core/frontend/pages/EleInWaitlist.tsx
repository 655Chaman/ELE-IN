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

  const [email, setEmail] = useState("")
  const [fullName, setFullName] = useState("")
  const [referralCode, setReferralCode] = useState("")
  const [honeypot, setHoneypot] = useState("")

  const [isSubmitting, setIsSubmitting] = useState(false)
  const [activeEntry, setActiveEntry] = useState<WaitlistEntry | null>(null)
  const [hasCopied, setHasCopied] = useState(false)
  const [totalCount, setTotalCount] = useState<number>(385)

  // Auto-detect ?ref= referral parameter from URL or localStorage
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

    const cleanEmail = email.trim().toLowerCase()
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!cleanEmail || !emailRegex.test(cleanEmail)) {
      toast.error("Please provide a valid work email address.")
      return
    }

    const cleanName =
      fullName.trim() ||
      cleanEmail
        .split("@")[0]
        .replace(/[._-]/g, " ")
        .replace(/\b\w/g, (c) => c.toUpperCase())

    setIsSubmitting(true)
    try {
      const entry = await submitWaitlistSignup({
        email: cleanEmail,
        full_name: cleanName,
        referred_by_code: referralCode || undefined,
        hp_website_security: honeypot || undefined,
      })

      setActiveEntry(entry)
      if (entry.status === "already_registered") {
        toast.info("Welcome back. Here is your access pass.")
      } else {
        toast.success("Spot reserved. Access pass generated.")
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
        toast.success("Invite link copied to clipboard.")
        setTimeout(() => setHasCopied(false), 2000)
      })
      .catch(() => {
        toast.error("Failed to copy link.")
      })
  }

  // Calculate cohort capacity (500 per cohort wave)
  const cohortCapacity = 500
  const claimedInCurrentCohort = Math.min(totalCount % cohortCapacity || 385, cohortCapacity)
  const cohortPercent = Math.min(Math.round((claimedInCurrentCohort / cohortCapacity) * 100), 100)
  const formattedPositionNumber = String(activeEntry?.position || totalCount || 385).padStart(6, "0")

  return (
    <div className="min-h-screen bg-[#070809] text-[#f4f4f5] flex flex-col justify-between font-sans selection:bg-[#27272a] selection:text-white">
      {/* Symmetrical Top Brand Spine */}
      <header className="w-full px-6 pt-12 sm:pt-16 flex items-center justify-center">
        <div className="flex flex-col items-center gap-2.5">
          <div className="w-11 h-11 rounded-xl overflow-hidden bg-[#001507] border border-[#1b3d22] flex items-center justify-center shadow-sm">
            <img
              src="/logo-icon.png"
              alt="Ele-in"
              className="w-full h-full object-cover"
            />
          </div>
          <span className="text-xs font-semibold tracking-widest text-zinc-400 uppercase font-mono">
            Ele-in
          </span>
        </div>
      </header>

      {/* Main Container */}
      <main className="w-full max-w-3xl mx-auto px-6 py-10 sm:py-14 text-center my-auto">
        {/* Core Value Headline */}
        <h1 className="text-3xl sm:text-5xl md:text-6xl font-bold tracking-tight text-white font-heading leading-tight text-balance">
          Autonomous outbound for modern revenue teams.
        </h1>

        <p className="mt-4 sm:mt-5 text-sm sm:text-base text-zinc-400 max-w-xl mx-auto leading-relaxed text-balance">
          Ele-in coordinates LinkedIn outreach, verified cold email, and buyer research into one autonomous agent that books qualified meetings on autopilot.
        </p>

        {/* State 1: Symmetrical High-Converting Form */}
        {!activeEntry ? (
          <div className="mt-8 max-w-md mx-auto">
            <form onSubmit={handleJoinSubmit} className="space-y-4">
              <div className="p-1.5 rounded-xl bg-zinc-900 border border-zinc-800 flex flex-col sm:flex-row gap-1.5 shadow-sm">
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="Enter your work email"
                  required
                  className="flex-1 bg-transparent px-3.5 py-2.5 text-white placeholder-zinc-500 text-sm focus:outline-none rounded-lg"
                />
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
                  className="bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-sm px-5 py-2.5 rounded-lg transition-colors cursor-pointer disabled:opacity-50 shrink-0"
                >
                  {isSubmitting ? "Securing spot..." : "Request access"}
                </button>
              </div>

              {/* Scarcity / Cohort Meter */}
              <div className="pt-2 px-1">
                <div className="flex items-center justify-between text-xs text-zinc-400 mb-1.5 font-mono">
                  <span>Cohort 1 (Founders & Early Teams)</span>
                  <span className="text-emerald-400 font-semibold">{claimedInCurrentCohort} / {cohortCapacity} Seats</span>
                </div>
                <div className="w-full bg-zinc-900 border border-zinc-800/80 h-1.5 rounded-full overflow-hidden">
                  <div
                    className="bg-emerald-500 h-full rounded-full transition-all duration-500"
                    style={{ width: `${cohortPercent}%` }}
                  />
                </div>
                <p className="mt-2 text-[11px] text-zinc-500 text-center">
                  Private beta invites roll out weekly. Zero spam, ever.
                </p>
              </div>
            </form>
          </div>
        ) : (
          /* State 2: Symmetrical Matte Obsidian VIP Access Pass */
          <div className="mt-8 max-w-md mx-auto">
            <div className="p-6 sm:p-7 rounded-2xl bg-zinc-900/90 border border-zinc-700/80 text-center shadow-xl relative overflow-hidden">
              {/* Pass Header */}
              <div className="flex items-center justify-between border-b border-zinc-800 pb-4 text-left">
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded-md overflow-hidden bg-[#001507] border border-[#1b3d22] flex items-center justify-center">
                    <img src="/logo-icon.png" alt="Ele-in" className="w-full h-full object-cover" />
                  </div>
                  <span className="text-xs font-bold tracking-wider text-white font-mono uppercase">
                    Ele-in Access Pass
                  </span>
                </div>
                <span className="text-[11px] font-mono uppercase px-2 py-0.5 rounded bg-emerald-950/60 border border-emerald-800/60 text-emerald-300 font-medium">
                  Cohort 1
                </span>
              </div>

              {/* Pass Number Body */}
              <div className="my-6 py-4 px-4 bg-black/70 border border-zinc-800 rounded-xl">
                <div className="text-[11px] uppercase tracking-widest text-zinc-400 font-mono">
                  Priority Pass Number
                </div>
                <div className="text-3xl sm:text-4xl font-bold text-emerald-400 font-mono mt-1 tracking-tight">
                  #{formattedPositionNumber}
                </div>
                <div className="text-xs text-zinc-400 mt-1 font-mono truncate px-2">
                  Issued to {activeEntry.email}
                </div>
              </div>

              {/* Viral Milestone Skip Engine */}
              <div className="pt-3 border-t border-zinc-800 text-center">
                <div className="flex items-center justify-between text-xs text-zinc-300 mb-2">
                  <span className="font-medium">Skip 5 spots per team invite</span>
                  <span className="text-emerald-400 font-mono text-[11px]">Instant Cohort 1</span>
                </div>
                <div className="flex gap-2">
                  <input
                    type="text"
                    readOnly
                    value={`https://ele-in.com?ref=${activeEntry.referral_code}`}
                    className="flex-1 bg-black/60 border border-zinc-800 rounded-lg px-3 py-2 text-xs text-zinc-300 font-mono text-center select-all focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={handleCopyLink}
                    className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-white text-xs font-medium rounded-lg transition-colors cursor-pointer shrink-0"
                  >
                    {hasCopied ? "Copied" : "Copy link"}
                  </button>
                </div>

                <div className="mt-3 flex items-center justify-center gap-3">
                  <a
                    href={`https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(`https://ele-in.com?ref=${activeEntry.referral_code}`)}`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-[11px] text-zinc-400 hover:text-white transition-colors underline"
                  >
                    Share on LinkedIn
                  </a>
                  <span className="text-zinc-600">·</span>
                  <a
                    href={`https://twitter.com/intent/tweet?text=${encodeURIComponent(`Just claimed Pass #${formattedPositionNumber} for @Ele_in. Autonomous outbound on autopilot: https://ele-in.com?ref=${activeEntry.referral_code}`)}`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-[11px] text-zinc-400 hover:text-white transition-colors underline"
                  >
                    Share on X
                  </a>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Part 3: Live Product Teaser ("Window into the Future") */}
        <div className="mt-16 sm:mt-20 max-w-2xl mx-auto">
          <div className="text-left p-5 sm:p-6 rounded-2xl bg-zinc-900/60 border border-zinc-800/90 shadow-sm">
            <div className="flex items-center justify-between border-b border-zinc-800 pb-3 mb-4">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
                <span className="text-xs font-mono font-semibold text-zinc-300 uppercase tracking-wide">
                  Autonomous Agent Activity
                </span>
              </div>
              <span className="text-[11px] font-mono text-zinc-500">
                Live Execution
              </span>
            </div>

            {/* Simulated Agent Steps */}
            <div className="space-y-3 font-mono text-xs">
              <div className="flex items-start gap-3 p-2.5 rounded-lg bg-black/40 border border-zinc-800/60">
                <span className="text-emerald-400 font-bold shrink-0">01</span>
                <div>
                  <span className="text-zinc-200 font-semibold block">Buyer Signal Identified</span>
                  <span className="text-zinc-400 text-[11px]">VP of Sales at Series B SaaS viewed LinkedIn profile after hiring 4 SDRs.</span>
                </div>
              </div>

              <div className="flex items-start gap-3 p-2.5 rounded-lg bg-black/40 border border-zinc-800/60">
                <span className="text-emerald-400 font-bold shrink-0">02</span>
                <div>
                  <span className="text-zinc-200 font-semibold block">Deliverability & Personalization</span>
                  <span className="text-zinc-400 text-[11px]">Synthesized custom research and queued multi-channel touch via warm sender pod.</span>
                </div>
              </div>

              <div className="flex items-start gap-3 p-2.5 rounded-lg bg-black/40 border border-zinc-800/60">
                <span className="text-emerald-400 font-bold shrink-0">03</span>
                <div>
                  <span className="text-zinc-200 font-semibold block">Meeting Booked</span>
                  <span className="text-zinc-400 text-[11px]">Prospect confirmed demo call &mdash; Calendar event scheduled automatically.</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Part 4: Symmetrical 3-Column Specifications */}
        <div className="mt-14 sm:mt-16 pt-8 border-t border-zinc-800/70 max-w-2xl mx-auto">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 sm:gap-6 text-center">
            <div className="p-4 rounded-xl bg-zinc-900/30 border border-zinc-800/50">
              <div className="text-xs font-semibold text-zinc-200">
                Multi-channel Sync
              </div>
              <p className="mt-1.5 text-xs text-zinc-400 leading-relaxed text-balance">
                Coordinates LinkedIn engagement and cold email in one rhythm.
              </p>
            </div>
            <div className="p-4 rounded-xl bg-zinc-900/30 border border-zinc-800/50">
              <div className="text-xs font-semibold text-zinc-200">
                Adaptive ICP Intelligence
              </div>
              <p className="mt-1.5 text-xs text-zinc-400 leading-relaxed text-balance">
                Refines angles and messaging dynamically from actual replies.
              </p>
            </div>
            <div className="p-4 rounded-xl bg-zinc-900/30 border border-zinc-800/50">
              <div className="text-xs font-semibold text-zinc-200">
                Sender Pod Protection
              </div>
              <p className="mt-1.5 text-xs text-zinc-400 leading-relaxed text-balance">
                Automated inbox warmup and RFC 8058 unsubscription built in.
              </p>
            </div>
          </div>
        </div>
      </main>

      {/* Symmetrical Footer */}
      <footer className="w-full max-w-md mx-auto px-6 pb-10 pt-4 text-center text-xs text-zinc-500 space-y-1.5">
        <div>© 2026 Ele-in · All rights reserved</div>
        <div>
          <a
            href="mailto:contact@ele-in.com"
            className="hover:text-zinc-400 transition-colors"
          >
            contact@ele-in.com
          </a>
        </div>
      </footer>
    </div>
  )
}
