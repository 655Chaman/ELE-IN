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
      {/* Top Header */}
      <header className="w-full max-w-4xl mx-auto px-6 py-8 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg overflow-hidden bg-[#001507] border border-[#1b3d22] flex items-center justify-center">
            <img
              src="/logo-icon.png"
              alt="Ele-in"
              className="w-full h-full object-cover"
            />
          </div>
          <span className="text-lg font-semibold tracking-tight text-white font-heading">
            Ele-in
          </span>
        </div>
      </header>

      {/* Main Content */}
      <main className="w-full max-w-2xl mx-auto px-6 py-12 text-center my-auto">
        <h1 className="text-4xl sm:text-5xl md:text-6xl font-bold tracking-tight text-white font-heading leading-tight">
          Autonomous outbound for modern sales teams.
        </h1>

        <p className="mt-5 text-base sm:text-lg text-zinc-400 max-w-lg mx-auto leading-relaxed">
          Ele-in coordinates LinkedIn outreach and verified cold email to book
          meetings on autopilot. Join the waitlist for early access.
        </p>

        {!activeEntry ? (
          <form onSubmit={handleJoinSubmit} className="mt-8 max-w-md mx-auto">
            <div className="flex flex-col sm:flex-row gap-2.5">
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Enter your work email"
                required
                className="flex-1 bg-zinc-900/90 border border-zinc-800 rounded-lg px-4 py-3 text-white placeholder-zinc-500 text-sm focus:outline-none focus:border-zinc-600 transition-colors"
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
                {isSubmitting ? "Joining..." : "Join waitlist"}
              </button>
            </div>

            {totalCount && (
              <p className="mt-3 text-xs text-zinc-500">
                {totalCount.toLocaleString()} people are currently waiting for access.
              </p>
            )}
          </form>
        ) : (
          <div className="mt-8 max-w-md mx-auto p-6 bg-zinc-900/80 border border-zinc-800 rounded-xl text-left">
            <div className="text-sm font-semibold text-white">
              You are on the waitlist
            </div>
            <p className="mt-1 text-xs text-zinc-400">
              Your position is #{activeEntry.position || 385}. We will send your
              invite to {activeEntry.email} when the next cohort opens.
            </p>

            <div className="mt-5 pt-4 border-t border-zinc-800">
              <label className="text-xs text-zinc-400 block mb-1.5">
                Share your invite link to move up:
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  readOnly
                  value={`https://ele-in.com?ref=${activeEntry.referral_code}`}
                  className="flex-1 bg-black/60 border border-zinc-800 rounded-lg px-3 py-2 text-xs text-zinc-300 font-mono select-all focus:outline-none"
                />
                <button
                  type="button"
                  onClick={handleCopyLink}
                  className="px-3.5 py-2 bg-zinc-800 hover:bg-zinc-700 text-white text-xs font-medium rounded-lg transition-colors cursor-pointer"
                >
                  {hasCopied ? "Copied" : "Copy"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Core Value Points */}
        <div className="mt-20 pt-10 border-t border-zinc-800/60 max-w-xl mx-auto">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 text-left">
            <div>
              <div className="text-xs font-semibold text-zinc-200">
                Multi-channel
              </div>
              <p className="mt-1 text-xs text-zinc-400 leading-relaxed">
                Connects LinkedIn profile touches and email into one workflow.
              </p>
            </div>
            <div>
              <div className="text-xs font-semibold text-zinc-200">
                Adaptive targeting
              </div>
              <p className="mt-1 text-xs text-zinc-400 leading-relaxed">
                Refines copy and ICP criteria from actual reply signals.
              </p>
            </div>
            <div>
              <div className="text-xs font-semibold text-zinc-200">
                Deliverability
              </div>
              <p className="mt-1 text-xs text-zinc-400 leading-relaxed">
                Distributed mailbox rotation with built-in inbox warmup.
              </p>
            </div>
          </div>
        </div>
      </main>

      {/* Clean Minimal Footer */}
      <footer className="w-full max-w-4xl mx-auto px-6 py-8 border-t border-zinc-900 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-zinc-500">
        <div className="flex items-center gap-2">
          <span>© 2026 Ele-in</span>
          <span>·</span>
          <span>All rights reserved</span>
        </div>
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
