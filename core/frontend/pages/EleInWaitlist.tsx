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
  const [totalCount, setTotalCount] = useState<number | null>(null)

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
      toast.error("Please provide a valid email address.")
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
        toast.info("You are already registered on the waitlist.")
      } else {
        toast.success("You have been added to the waitlist.")
        setTotalCount((prev) => (prev ? prev + 1 : 1))
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
        toast.success("Link copied.")
        setTimeout(() => setHasCopied(false), 2000)
      })
      .catch(() => {
        toast.error("Failed to copy link.")
      })
  }

  return (
    <div className="min-h-screen bg-[#09090b] text-[#fafafa] flex flex-col justify-between font-sans selection:bg-[#27272a] selection:text-white">
      {/* Top Symmetrical Header */}
      <header className="w-full px-6 pt-12 sm:pt-16 flex items-center justify-center">
        <div className="flex flex-col items-center gap-2.5">
          <div className="w-11 h-11 rounded-xl overflow-hidden bg-[#001507] border border-[#1b3d22] flex items-center justify-center shadow-sm">
            <img
              src="/logo-icon.png"
              alt="Ele-in"
              className="w-full h-full object-cover"
            />
          </div>
          <span className="text-sm font-semibold tracking-wide text-zinc-300 uppercase font-mono">
            Ele-in
          </span>
        </div>
      </header>

      {/* Symmetrical Hero & Form */}
      <main className="w-full max-w-2xl mx-auto px-6 py-10 sm:py-14 text-center my-auto">
        <h1 className="text-3xl sm:text-5xl md:text-6xl font-bold tracking-tight text-white font-heading leading-tight text-balance">
          Autonomous outbound for modern sales teams.
        </h1>

        <p className="mt-4 sm:mt-5 text-sm sm:text-base text-zinc-400 max-w-lg mx-auto leading-relaxed text-balance">
          Ele-in coordinates LinkedIn outreach and verified cold email to book
          meetings on autopilot. Join the waitlist for early access.
        </p>

        {!activeEntry ? (
          <form onSubmit={handleJoinSubmit} className="mt-8 max-w-md mx-auto">
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
                {isSubmitting ? "Joining..." : "Join waitlist"}
              </button>
            </div>

            {totalCount && (
              <p className="mt-3 text-xs text-zinc-500 text-center">
                {totalCount.toLocaleString()} people are currently waiting for access.
              </p>
            )}
          </form>
        ) : (
          <div className="mt-8 max-w-md mx-auto p-6 bg-zinc-900/90 border border-zinc-800 rounded-xl text-center shadow-sm">
            <div className="text-sm font-semibold text-white">
              You are on the waitlist
            </div>
            <p className="mt-1 text-xs text-zinc-400 text-balance">
              We reserved your spot for {activeEntry.email}. We will notify you when the next cohort opens.
            </p>

            <div className="my-4 py-3 px-4 bg-black/50 border border-zinc-800 rounded-lg">
              <div className="text-[11px] uppercase tracking-wider text-zinc-500 font-mono">
                Queue Position
              </div>
              <div className="text-2xl font-bold text-emerald-400 font-mono mt-0.5">
                #{activeEntry.position || 385}
              </div>
            </div>

            <div className="pt-3 border-t border-zinc-800/80 text-center">
              <label className="text-xs text-zinc-400 block mb-2">
                Share your invite link to move up the queue:
              </label>
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
                  {hasCopied ? "Copied" : "Copy"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Symmetrical 3-Column Value Section */}
        <div className="mt-16 sm:mt-20 pt-8 sm:pt-10 border-t border-zinc-800/70 max-w-xl mx-auto">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 sm:gap-6">
            <div className="p-4 rounded-lg bg-zinc-900/30 border border-zinc-800/50 text-center">
              <div className="text-xs font-semibold text-zinc-200">
                Multi-channel
              </div>
              <p className="mt-1.5 text-xs text-zinc-400 leading-relaxed text-balance">
                Connects LinkedIn profile touches and email into one workflow.
              </p>
            </div>
            <div className="p-4 rounded-lg bg-zinc-900/30 border border-zinc-800/50 text-center">
              <div className="text-xs font-semibold text-zinc-200">
                Adaptive targeting
              </div>
              <p className="mt-1.5 text-xs text-zinc-400 leading-relaxed text-balance">
                Refines copy and ICP criteria from actual reply signals.
              </p>
            </div>
            <div className="p-4 rounded-lg bg-zinc-900/30 border border-zinc-800/50 text-center">
              <div className="text-xs font-semibold text-zinc-200">
                Deliverability
              </div>
              <p className="mt-1.5 text-xs text-zinc-400 leading-relaxed text-balance">
                Distributed mailbox rotation with built-in inbox warmup.
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
