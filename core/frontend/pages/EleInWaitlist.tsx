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
      toast.error("Please enter a valid work email.")
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
        toast.success("Link copied to clipboard.")
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
          <div className="mt-10 max-w-md mx-auto">
            <form onSubmit={handleJoinSubmit} className="space-y-4">
              <div className="p-1 rounded-xl bg-zinc-900/60 border border-zinc-800/80 hover:border-zinc-700/80 focus-within:border-zinc-600 transition-colors flex flex-col sm:flex-row gap-1">
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="Enter your work email"
                  required
                  className="flex-1 bg-transparent px-4 py-3 text-white placeholder-zinc-500 text-sm focus:outline-none"
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
                  className="bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-sm px-6 py-3 rounded-lg transition-colors cursor-pointer disabled:opacity-50 shrink-0"
                >
                  {isSubmitting ? "Securing spot..." : "Get early access"}
                </button>
              </div>

              {/* Minimal Scarcity Meter */}
              <div className="pt-2 px-1 text-center">
                <div className="flex items-center justify-between text-[11px] font-mono text-zinc-500 mb-1.5">
                  <span>Cohort 1</span>
                  <span className="text-emerald-400 font-medium">
                    {claimedInCurrentCohort} / {cohortCapacity} Seats
                  </span>
                </div>
                <div className="w-full bg-zinc-900 border border-zinc-800/80 h-1 rounded-full overflow-hidden">
                  <div
                    className="bg-emerald-500 h-full rounded-full transition-all duration-500"
                    style={{ width: `${cohortPercent}%` }}
                  />
                </div>
              </div>
            </form>
          </div>
        ) : (
          /* Post-Join State: Clean Minimalist Pass */
          <div className="mt-10 max-w-md mx-auto p-7 rounded-2xl bg-zinc-900/40 border border-zinc-800/80 text-center shadow-xs">
            <div className="text-[11px] uppercase tracking-widest text-emerald-400 font-mono mb-1">
              Early Access Confirmed
            </div>

            <div className="text-3xl sm:text-4xl font-light tracking-tight text-white font-mono my-2">
              #{formattedPositionNumber}
            </div>

            <p className="text-xs text-zinc-400 font-mono mt-1">
              Reserved for {activeEntry.email}
            </p>

            <div className="mt-6 pt-5 border-t border-zinc-800/80">
              <div className="text-xs text-zinc-400 mb-2.5">
                Skip 5 spots for each teammate you invite:
              </div>
              <div className="flex gap-2">
                <input
                  type="text"
                  readOnly
                  value={`https://ele-in.com?ref=${activeEntry.referral_code}`}
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

              <div className="mt-3.5 flex items-center justify-center gap-3 text-xs text-zinc-500">
                <a
                  href={`https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(`https://ele-in.com?ref=${activeEntry.referral_code}`)}`}
                  target="_blank"
                  rel="noreferrer"
                  className="hover:text-zinc-300 transition-colors underline"
                >
                  Share on LinkedIn
                </a>
                <span>·</span>
                <a
                  href={`https://twitter.com/intent/tweet?text=${encodeURIComponent(`Just claimed Pass #${formattedPositionNumber} for @Ele_in. Automated LinkedIn outreach: https://ele-in.com?ref=${activeEntry.referral_code}`)}`}
                  target="_blank"
                  rel="noreferrer"
                  className="hover:text-zinc-300 transition-colors underline"
                >
                  Share on X
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
