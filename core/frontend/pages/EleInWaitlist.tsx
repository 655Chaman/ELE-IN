import React, { useState, useEffect } from "react"
import { useSearchParams, Link } from "react-router-dom"
import { 
  Sparkles, ArrowRight, Check, Copy, Share2, Users, ShieldCheck, 
  Zap, CheckCircle2 
} from "lucide-react"
import { Linkedin } from "@/components/icons/Linkedin"
import { toast } from "sonner"
import {
  submitWaitlistSignup,
  fetchWaitlistStats,
  type WaitlistEntry,
} from "@/lib/waitlistApi"

export function EleInWaitlist() {
  const [searchParams] = useSearchParams()

  // Form State
  const [email, setEmail] = useState("")
  const [fullName, setFullName] = useState("")
  const [referralCode, setReferralCode] = useState("")
  const [honeypot, setHoneypot] = useState("") // Layer 2 Bot Trap

  // Submission / Loading State
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [activeEntry, setActiveEntry] = useState<WaitlistEntry | null>(null)
  const [hasCopied, setHasCopied] = useState(false)

  // Public Social Proof State
  const [totalCount, setTotalCount] = useState(1480)

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

    // Fetch live aggregate stats (Backend API -> Supabase Serverless fallback)
    fetchWaitlistStats()
      .then((count) => {
        if (count && count > 0) setTotalCount(count)
      })
      .catch(() => {})
  }, [searchParams])

  // Paranoia Layer 2: Validated submission handler
  const handleJoinSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    const cleanEmail = email.trim().toLowerCase()
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!cleanEmail || !emailRegex.test(cleanEmail)) {
      toast.error("Please provide a valid work email address.")
      return
    }

    // Extract name if provided or fallback to email username
    const cleanName = fullName.trim() || cleanEmail.split("@")[0].replace(/[._-]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())

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
        toast.info("Welcome back! Here is your queue status.")
      } else {
        toast.success("Spot secured! Welcome to the priority waitlist.")
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
    navigator.clipboard.writeText(link).then(() => {
      setHasCopied(true)
      toast.success("Invite link copied to clipboard.")
      setTimeout(() => setHasCopied(false), 2500)
    }).catch(() => {
      toast.error("Failed to copy link.")
    })
  }

  return (
    <div className="min-h-screen bg-[#070809] text-white selection:bg-emerald-500/30 selection:text-emerald-200 relative overflow-hidden font-sans">
      {/* Ambient background glows */}
      <div 
        aria-hidden="true" 
        className="pointer-events-none absolute top-0 left-1/2 -translate-x-1/2 w-[1000px] h-[550px] bg-[radial-gradient(ellipse_60%_50%_at_50%_0%,rgba(16,185,129,0.18),transparent_70%)]" 
      />
      <div 
        aria-hidden="true" 
        className="pointer-events-none absolute top-[400px] left-1/2 -translate-x-1/2 w-[700px] h-[350px] bg-[radial-gradient(ellipse_50%_50%_at_50%_50%,rgba(5,150,105,0.08),transparent_70%)]" 
      />

      {/* Subtle background grid texture */}
      <div 
        aria-hidden="true" 
        className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,#ffffff04_1px,transparent_1px),linear-gradient(to_bottom,#ffffff04_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_70%_60%_at_50%_0%,#000_70%,transparent_100%)]" 
      />

      {/* Header Navigation */}
      <header className="relative z-20 border-b border-white/[0.06] backdrop-blur-md">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-20 flex items-center justify-between">
          {/* Logo with Green "e" */}
          <Link to="/" className="flex items-center gap-3 group">
            <div className="w-10 h-10 rounded-xl overflow-hidden ring-1 ring-emerald-500/40 shadow-lg shadow-emerald-950/60 bg-[#001507] flex items-center justify-center transition-transform group-hover:scale-105">
              <img 
                src="/logo-icon.png" 
                alt="Ele-in" 
                className="w-full h-full object-cover" 
              />
            </div>
            <div className="flex items-baseline gap-1.5">
              <span className="text-xl font-bold tracking-tight text-white font-heading">
                Ele-in
              </span>
              <span className="text-[10px] uppercase font-mono tracking-wider text-emerald-400 font-semibold px-1.5 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20">
                AI
              </span>
            </div>
          </Link>

          {/* Top Status & Sign In */}
          <div className="flex items-center gap-3 sm:gap-4">
            <div className="hidden sm:inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-xs font-medium text-emerald-400">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span>Private Beta · Limited Access</span>
            </div>
            <Link
              to="/login"
              className="text-xs font-medium text-zinc-400 hover:text-white transition-colors flex items-center gap-1.5 py-2 px-3.5 rounded-xl border border-white/10 hover:border-white/20 bg-white/[0.02] hover:bg-white/[0.05]"
            >
              <span>Member Sign In</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <main className="relative z-10 pt-16 sm:pt-24 pb-20 px-4 sm:px-6">
        <div className="max-w-4xl mx-auto text-center">
          {/* Eyebrow Pill */}
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white/[0.03] border border-white/10 text-xs text-zinc-300 backdrop-blur-md mb-6 shadow-xs">
            <Sparkles className="w-3.5 h-3.5 text-emerald-400" />
            <span>Autonomous Outbound Intelligence</span>
          </div>

          {/* Master Headline */}
          <h1 className="text-4xl sm:text-6xl md:text-7xl font-bold tracking-tight text-white leading-[1.08] font-heading">
            Outbound on Autopilot.
            <span className="block mt-1 sm:mt-2 bg-gradient-to-r from-emerald-400 via-teal-300 to-emerald-500 bg-clip-text text-transparent">
              Zero Spam. Real Meetings.
            </span>
          </h1>

          {/* Subtitle */}
          <p className="mt-6 text-base sm:text-lg md:text-xl text-zinc-400 max-w-2xl mx-auto leading-relaxed">
            Ele-in coordinates multi-channel LinkedIn touches, deliverability-protected cold email, and live ICP research into one high-converting agent.
          </p>

          {/* Waitlist Form or Success Card */}
          {!activeEntry ? (
            <div className="mt-10 sm:mt-12 max-w-xl mx-auto">
              <form onSubmit={handleJoinSubmit} className="space-y-3">
                <div className="p-2 sm:p-2.5 rounded-2xl bg-white/[0.03] border border-white/10 backdrop-blur-xl shadow-2xl shadow-emerald-950/40 relative">
                  <div className="flex flex-col sm:flex-row gap-2">
                    <input
                      type="text"
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      placeholder="Your name"
                      className="w-full sm:w-2/5 bg-white/[0.03] sm:bg-transparent px-4 py-3 text-white placeholder-zinc-500 text-sm rounded-xl border border-white/5 sm:border-0 focus:outline-none focus:ring-1 focus:ring-emerald-500/50"
                    />
                    <div className="hidden sm:block w-px self-stretch bg-white/10 my-1" />
                    <input
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="Work email address"
                      required
                      className="w-full sm:w-3/5 bg-white/[0.03] sm:bg-transparent px-4 py-3 text-white placeholder-zinc-500 text-sm rounded-xl border border-white/5 sm:border-0 focus:outline-none focus:ring-1 focus:ring-emerald-500/50"
                    />
                    {/* Bot Trap */}
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
                      className="shrink-0 px-6 py-3.5 bg-emerald-500 hover:bg-emerald-400 active:scale-[0.98] text-black font-semibold text-sm rounded-xl transition-all shadow-lg shadow-emerald-500/25 hover:shadow-emerald-500/40 flex items-center justify-center gap-2 cursor-pointer disabled:opacity-60"
                    >
                      {isSubmitting ? (
                        <span>Securing spot...</span>
                      ) : (
                        <>
                          <span>Join Waitlist</span>
                          <ArrowRight className="w-4 h-4" />
                        </>
                      )}
                    </button>
                  </div>
                </div>

                <div className="flex flex-wrap items-center justify-center gap-3 sm:gap-4 text-xs text-zinc-500 pt-1">
                  <span className="flex items-center gap-1.5">
                    <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                    <span>Private Beta Access</span>
                  </span>
                  <span>·</span>
                  <span>Zero Spam</span>
                  <span>·</span>
                  <span>1-Click Unsubscribe</span>
                </div>
              </form>
            </div>
          ) : (
            /* Celebratory Confirmation Card (Zero Voucher Codes) */
            <div className="mt-10 sm:mt-12 max-w-lg mx-auto p-6 sm:p-8 rounded-2xl bg-white/[0.03] border border-emerald-500/30 backdrop-blur-xl shadow-2xl shadow-emerald-950/50 relative overflow-hidden text-center animate-fade-in-up">
              <div className="absolute top-0 inset-x-0 h-1 bg-gradient-to-r from-emerald-500 via-teal-300 to-emerald-500" />
              
              <div className="w-12 h-12 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 flex items-center justify-center mx-auto mb-4">
                <CheckCircle2 className="w-6 h-6" />
              </div>

              <h3 className="text-2xl font-bold text-white font-heading">
                You are on the priority waitlist!
              </h3>
              <p className="mt-1 text-sm text-zinc-400">
                We reserved your spot for <span className="text-white font-medium">{activeEntry.email}</span>.
              </p>

              {/* Position Card */}
              <div className="mt-6 p-4 rounded-xl bg-white/[0.03] border border-white/10 flex items-center justify-between">
                <div className="text-left">
                  <div className="text-xs text-zinc-400">Your Queue Position</div>
                  <div className="text-2xl font-bold text-emerald-400 font-heading mt-0.5">
                    #{activeEntry.position || 385}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-xs text-zinc-400">Access Status</div>
                  <div className="text-sm font-semibold text-emerald-300 mt-0.5">
                    Priority Wave 1
                  </div>
                </div>
              </div>

              {/* Referral Boost */}
              <div className="mt-5 text-left">
                <label className="text-xs font-medium text-zinc-300 block mb-1.5">
                  Invite colleagues to jump 5 spots per teammate:
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    readOnly
                    value={`https://ele-in.com?ref=${activeEntry.referral_code}`}
                    className="w-full bg-white/[0.04] border border-white/10 px-3 py-2 text-xs text-zinc-300 rounded-lg focus:outline-none select-all"
                  />
                  <button
                    type="button"
                    onClick={handleCopyLink}
                    className="shrink-0 px-3.5 py-2 bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/30 text-emerald-300 text-xs font-medium rounded-lg transition-colors flex items-center gap-1.5 cursor-pointer"
                  >
                    {hasCopied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                    <span>{hasCopied ? "Copied" : "Copy"}</span>
                  </button>
                </div>
              </div>

              {/* Social Share */}
              <div className="mt-5 pt-4 border-t border-white/5 flex items-center justify-between">
                <span className="text-xs text-zinc-400">Share with team:</span>
                <div className="flex items-center gap-2">
                  <a
                    href={`https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(`https://ele-in.com?ref=${activeEntry.referral_code}`)}`}
                    target="_blank"
                    rel="noreferrer"
                    className="px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-xs text-zinc-300 transition-colors flex items-center gap-1.5"
                  >
                    <Linkedin size={13} />
                    <span>LinkedIn</span>
                  </a>
                  <a
                    href={`https://twitter.com/intent/tweet?text=${encodeURIComponent(`Joining the @Ele_in priority waitlist for autonomous sales outbound. Skip the queue here: https://ele-in.com?ref=${activeEntry.referral_code}`)}`}
                    target="_blank"
                    rel="noreferrer"
                    className="px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-xs text-zinc-300 transition-colors flex items-center gap-1.5"
                  >
                    <Share2 className="w-3.5 h-3.5" />
                    <span>Share</span>
                  </a>
                </div>
              </div>
            </div>
          )}

          {/* Live Proof Counter */}
          <div className="mt-12 sm:mt-14 inline-flex items-center gap-3 px-4 py-2 rounded-full bg-white/[0.02] border border-white/5 text-xs text-zinc-400">
            <div className="flex -space-x-1.5">
              <div className="w-5 h-5 rounded-full bg-emerald-500/20 border border-emerald-500/40 text-[9px] font-bold text-emerald-300 flex items-center justify-center">E</div>
              <div className="w-5 h-5 rounded-full bg-teal-500/20 border border-teal-500/40 text-[9px] font-bold text-teal-300 flex items-center justify-center">L</div>
              <div className="w-5 h-5 rounded-full bg-cyan-500/20 border border-cyan-500/40 text-[9px] font-bold text-cyan-300 flex items-center justify-center">N</div>
            </div>
            <span>
              Join <strong className="text-zinc-200 font-semibold">{totalCount.toLocaleString()}</strong> revenue leaders already on the list
            </span>
          </div>
        </div>

        {/* Feature Pillars: 3 Clean Value Propositions */}
        <div className="mt-28 sm:mt-36 max-w-5xl mx-auto">
          <div className="text-center mb-12 sm:mb-16">
            <h2 className="text-2xl sm:text-3xl md:text-4xl font-bold text-white font-heading">
              Engineered for Real Sales Pipeline
            </h2>
            <p className="mt-3 text-sm sm:text-base text-zinc-400 max-w-xl mx-auto">
              Built from scratch for revenue leaders who want qualified meetings without sending generic templates.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Card 1 */}
            <div className="p-6 sm:p-7 rounded-2xl bg-white/[0.02] border border-white/5 hover:border-emerald-500/30 transition-all group">
              <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 flex items-center justify-center mb-5 group-hover:scale-105 transition-transform">
                <Zap className="w-5 h-5" />
              </div>
              <h3 className="text-lg font-semibold text-white font-heading">
                Multi-Channel Orchestration
              </h3>
              <p className="mt-2 text-sm text-zinc-400 leading-relaxed">
                Seamlessly connects LinkedIn profile engagement, connection requests, and deliverability-verified email sequences into a unified rhythm.
              </p>
            </div>

            {/* Card 2 */}
            <div className="p-6 sm:p-7 rounded-2xl bg-white/[0.02] border border-white/5 hover:border-emerald-500/30 transition-all group">
              <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 flex items-center justify-center mb-5 group-hover:scale-105 transition-transform">
                <Users className="w-5 h-5" />
              </div>
              <h3 className="text-lg font-semibold text-white font-heading">
                Bayesian ICP Intelligence
              </h3>
              <p className="mt-2 text-sm text-zinc-400 leading-relaxed">
                Learns from every response in real-time, sharpening your target persona and message angles without manual prompt tweaking.
              </p>
            </div>

            {/* Card 3 */}
            <div className="p-6 sm:p-7 rounded-2xl bg-white/[0.02] border border-white/5 hover:border-emerald-500/30 transition-all group">
              <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 flex items-center justify-center mb-5 group-hover:scale-105 transition-transform">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <h3 className="text-lg font-semibold text-white font-heading">
                Sender Pod Protection
              </h3>
              <p className="mt-2 text-sm text-zinc-400 leading-relaxed">
                Rotates distributed inboxes with automated warmup and RFC 8058 1-click unsubscription to ensure high inbox placement.
              </p>
            </div>
          </div>
        </div>

        {/* Minimal Bottom Invitation */}
        <div className="mt-24 sm:mt-32 max-w-3xl mx-auto text-center">
          <div className="p-8 sm:p-12 rounded-3xl bg-gradient-to-b from-white/[0.04] to-white/[0.01] border border-white/10 relative overflow-hidden">
            <div className="absolute top-0 inset-x-0 h-px bg-gradient-to-r from-transparent via-emerald-500/40 to-transparent" />
            <h2 className="text-2xl sm:text-3xl font-bold text-white font-heading">
              Ready to scale outbound the right way?
            </h2>
            <p className="mt-3 text-sm text-zinc-400 max-w-lg mx-auto">
              Private beta invites are rolling out in batches. Enter your work email above to claim your spot in the earliest cohort.
            </p>
            <div className="mt-6 flex justify-center">
              <button
                type="button"
                onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
                className="px-6 py-3 bg-emerald-500 hover:bg-emerald-400 text-black font-semibold text-sm rounded-xl transition-all shadow-lg shadow-emerald-500/20 hover:shadow-emerald-500/35 flex items-center gap-2 cursor-pointer"
              >
                <span>Request Early Access</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="relative z-10 border-t border-white/[0.06] py-10 px-4 sm:px-6">
        <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-zinc-500">
          <div className="flex items-center gap-2.5">
            <div className="w-5 h-5 rounded-md overflow-hidden bg-[#001507] ring-1 ring-emerald-500/40 flex items-center justify-center">
              <img src="/logo-icon.png" alt="Ele-in" className="w-full h-full object-cover" />
            </div>
            <span className="text-zinc-400 font-medium">Ele-in</span>
            <span>© 2026 Ele-in. All rights reserved.</span>
          </div>
          <div className="flex items-center gap-6">
            <Link to="/login" className="hover:text-zinc-300 transition-colors">
              Member Sign In
            </Link>
            <a href="mailto:contact@ele-in.com" className="hover:text-zinc-300 transition-colors">
              Contact
            </a>
            <span className="text-zinc-600">Strictly High-Signal</span>
          </div>
        </div>
      </footer>
    </div>
  )
}
