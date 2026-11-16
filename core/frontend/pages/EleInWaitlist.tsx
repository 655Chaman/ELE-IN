import React, { useState, useEffect } from "react"
import { useSearchParams } from "react-router-dom"
import { toast } from "sonner"
import {
  Check,
  Copy,
  ArrowRight,
  ChevronDown,
  ChevronUp,
  Clock,
  CheckCircle2,
} from "lucide-react"
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
  const [showCopyPreview, setShowCopyPreview] = useState(false)

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

If you're scaling B2B pipeline and want early access, grab a spot here:
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

  const handleSwitchToWorkEmail = () => {
    setActiveEntry(null)
    setEmail("")
  }

  const formattedPositionNumber = String(activeEntry?.position || totalCount || 385).padStart(6, "0")

  return (
    <div className="min-h-screen bg-[#060708] text-zinc-100 flex flex-col justify-between font-sans selection:bg-zinc-800 selection:text-white antialiased">
      {/* Symmetrical Hero / Content */}
      <main className="w-full max-w-2xl mx-auto px-6 py-12 sm:py-16 text-center my-auto flex flex-col items-center">
        {/* Top Wordmark */}
        <span className="text-[11px] font-mono tracking-[0.32em] text-zinc-500 uppercase mb-4 select-none">
          {activeEntry ? "Ele-in · Access Confirmed" : "Ele-in"}
        </span>

        {/* Visually Appealing Brand Mark */}
        <div className="relative mb-6 sm:mb-8 flex items-center justify-center">
          <div className="absolute inset-0 rounded-3xl bg-emerald-500/15 blur-xl -z-10" />
          <div className="w-20 h-20 sm:w-24 sm:h-24 rounded-2xl sm:rounded-3xl p-1 bg-[#001507] border border-emerald-500/25 shadow-2xl shadow-emerald-950/80 flex items-center justify-center overflow-hidden">
            <img
              src="/logo-icon.png"
              alt="Ele-in"
              className="w-full h-full object-cover rounded-xl sm:rounded-2xl"
            />
          </div>
        </div>

        {!activeEntry ? (
          /* ========================================================================= */
          /* 1. PRE-SIGNUP VIEW (Clean Symmetrical Pitch & Form)                       */
          /* ========================================================================= */
          <>
            <h1 className="text-4xl sm:text-5xl md:text-6xl font-medium tracking-tight text-white font-heading leading-[1.12] text-balance">
              LinkedIn outreach, automated.
            </h1>

            <p className="mt-5 text-sm sm:text-base text-zinc-400 max-w-md mx-auto leading-relaxed text-balance font-normal">
              Stop sending manual messages. Ele-in finds leads, initiates conversations, and books qualified meetings on autopilot.
            </p>

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
          </>
        ) : (
          /* ========================================================================= */
          /* 2. POST-SIGNUP VIEW (Complete Visual Overhaul: VIP Boarding Pass)          */
          /* ========================================================================= */
          <div className="w-full max-w-lg mx-auto flex flex-col items-center animate-in fade-in zoom-in-95 duration-300">
            {/* Celebration Heading */}
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/25 text-[11px] uppercase tracking-wider text-emerald-400 font-mono mb-3">
              <span className="size-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span>{isEssential ? "Essential Customer · Priority Cohort" : "Early Access Reserved · Cohort 01"}</span>
            </div>

            <h1 className="text-3xl sm:text-4xl md:text-5xl font-medium tracking-tight text-white font-heading leading-tight">
              {isEssential ? "Priority B2B Access Secured." : "Your spot is reserved."}
            </h1>

            <p className="mt-3 text-sm text-zinc-400 max-w-md mx-auto leading-relaxed">
              {isEssential ? (
                <>
                  Welcome aboard, <span className="text-zinc-200 font-medium">{displayName}</span>. Your spot on the Priority B2B Queue has been confirmed{companyName ? ` for ${companyName}` : ""}.
                </>
              ) : (
                <>
                  Welcome aboard, <span className="text-zinc-200 font-medium">{displayName}</span>. Your pass #{formattedPositionNumber} has been verified and registered.
                </>
              )}
            </p>

            {/* Tactile VIP Pass / Boarding Ticket */}
            <div className="w-full max-w-md mx-auto mt-7 relative rounded-3xl bg-gradient-to-b from-zinc-900/90 via-[#0a0c0e] to-black border border-zinc-800/90 shadow-2xl shadow-emerald-950/30 overflow-hidden text-left">
              {/* Subtle metallic emerald glow overlay */}
              <div className="absolute top-0 inset-x-0 h-32 bg-gradient-to-b from-emerald-500/10 via-emerald-500/5 to-transparent pointer-events-none" />

              {/* Ticket Top Bar */}
              <div className="p-6 pb-5 flex items-center justify-between border-b border-zinc-800/60 relative z-10">
                <div className="flex items-center gap-2.5">
                  <div className="size-8 rounded-lg bg-emerald-950 border border-emerald-500/30 flex items-center justify-center p-0.5">
                    <img src="/logo-icon.png" alt="Ele-in" className="size-full object-cover rounded-md" />
                  </div>
                  <div>
                    <div className="text-[11px] font-mono uppercase tracking-[0.2em] text-white font-medium">
                      Ele-in Access Pass
                    </div>
                    <div className="text-[10px] font-mono text-zinc-500">
                      Cohort 01 · Launch 2026
                    </div>
                  </div>
                </div>

                <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/25 text-[10px] font-mono uppercase tracking-wider text-emerald-400">
                  <span className="size-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  <span>{isEssential ? "Priority B2B" : "Standard"}</span>
                </div>
              </div>

              {/* Ticket Hero Number */}
              <div className="px-6 py-6 text-center relative z-10">
                <span className="text-[10px] font-mono tracking-[0.25em] text-zinc-500 uppercase block mb-1">
                  Queue Position
                </span>
                <div className="text-5xl sm:text-6xl font-heading font-medium tracking-tight text-white my-1 text-emerald-50 drop-shadow-[0_0_24px_rgba(16,185,129,0.3)]">
                  #{formattedPositionNumber}
                </div>
                <p className="text-xs text-zinc-400 font-mono mt-1">
                  {isEssential ? (
                    <span>
                      Priority allocation for <span className="text-white font-medium">{displayName}</span>
                      {companyName && <span className="text-emerald-400 font-medium"> · {companyName}</span>}
                    </span>
                  ) : (
                    <span>
                      Reserved for <span className="text-white font-medium">{displayName}</span>
                    </span>
                  )}
                </p>
              </div>

              {/* Detail Metadata Grid */}
              <div className="px-6 pb-6 grid grid-cols-2 gap-2.5 relative z-10">
                <div className="p-3 rounded-xl bg-zinc-950/70 border border-zinc-800/80">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 block">Tier</span>
                  <span className="text-xs font-mono font-medium text-zinc-200 mt-0.5 block truncate">
                    {isEssential ? "Essential Customer" : "Standard Access"}
                  </span>
                </div>
                <div className="p-3 rounded-xl bg-zinc-950/70 border border-zinc-800/80">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 block">Organization</span>
                  <span className="text-xs font-mono font-medium text-zinc-200 mt-0.5 block truncate">
                    {companyName || "Independent"}
                  </span>
                </div>
                <div className="p-3 rounded-xl bg-zinc-950/70 border border-zinc-800/80">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 block">Founder Lock</span>
                  <span className="text-xs font-mono font-medium text-emerald-400 mt-0.5 block">
                    30% Off First Year
                  </span>
                </div>
                <div className="p-3 rounded-xl bg-zinc-950/70 border border-zinc-800/80">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 block">Status</span>
                  <span className="text-xs font-mono font-medium text-zinc-200 mt-0.5 flex items-center gap-1.5">
                    <span className="size-1.5 rounded-full bg-emerald-400" />
                    <span>Confirmed & Queued</span>
                  </span>
                </div>
              </div>

              {/* Perforation Cutouts */}
              <div className="relative flex items-center justify-between my-1">
                <div className="size-5 -ml-2.5 rounded-full bg-[#060708] border-r border-zinc-800" />
                <div className="flex-1 border-t border-dashed border-zinc-800/90 mx-2" />
                <div className="size-5 -mr-2.5 rounded-full bg-[#060708] border-l border-zinc-800" />
              </div>

              {/* Digital Barcode & Pass ID */}
              <div className="p-6 pt-4 bg-black/40 flex items-center justify-between">
                <div>
                  <span className="text-[10px] font-mono text-zinc-500 block uppercase tracking-wider">
                    Pass Security ID
                  </span>
                  <span className="text-xs font-mono text-zinc-300 font-medium">
                    {activeEntry.referral_code}
                  </span>
                </div>

                <div className="flex items-center gap-0.5 h-6 opacity-60">
                  <div className="w-0.5 h-6 bg-zinc-300" />
                  <div className="w-1 h-6 bg-zinc-400" />
                  <div className="w-0.5 h-6 bg-zinc-500" />
                  <div className="w-1.5 h-6 bg-zinc-300" />
                  <div className="w-0.5 h-6 bg-zinc-400" />
                  <div className="w-1 h-6 bg-zinc-300" />
                  <div className="w-0.5 h-6 bg-zinc-600" />
                  <div className="w-1 h-6 bg-zinc-400" />
                  <div className="w-0.5 h-6 bg-zinc-300" />
                  <div className="w-1.5 h-6 bg-zinc-500" />
                  <div className="w-0.5 h-6 bg-zinc-300" />
                  <div className="w-1 h-6 bg-zinc-400" />
                  <div className="w-0.5 h-6 bg-zinc-300" />
                </div>
              </div>
            </div>

            {/* Viral Referral Station ("Skip Ahead in Line") */}
            <div className="w-full max-w-md mx-auto mt-6 p-6 rounded-2xl bg-zinc-900/40 border border-zinc-800/80 text-left">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-white">Skip ahead in the queue</span>
                <span className="text-[11px] font-mono text-emerald-400">+5 spots per invite</span>
              </div>
              <p className="text-xs text-zinc-400 leading-relaxed">
                Every teammate or founder who joins with your link moves you ahead 5 spots in line.
              </p>

              {/* Visual Jump Progression */}
              <div className="mt-3.5 p-2.5 rounded-xl bg-black/50 border border-zinc-800/70 flex items-center justify-between text-[11px] font-mono text-zinc-400">
                <div className="text-zinc-300">
                  Current: <span className="text-white font-medium">#{formattedPositionNumber}</span>
                </div>
                <ArrowRight className="size-3 text-zinc-600" />
                <div className="text-zinc-300">
                  1 invite: <span className="text-emerald-400 font-medium">#{String(Math.max(1, (activeEntry.position || totalCount) - 5)).padStart(6, "0")}</span>
                </div>
                <ArrowRight className="size-3 text-zinc-600" />
                <div className="text-emerald-400 font-medium">
                  ⚡ Front Cohort
                </div>
              </div>

              {/* Referral Link & Copy Button */}
              <div className="mt-4 flex gap-2">
                <input
                  type="text"
                  readOnly
                  value={shareUrl}
                  className="flex-1 bg-black/60 border border-zinc-800/90 rounded-xl px-3.5 py-2.5 text-xs text-zinc-300 font-mono select-all focus:outline-none"
                />
                <button
                  type="button"
                  onClick={handleCopyLink}
                  className="flex items-center gap-1.5 px-4 py-2.5 bg-zinc-800 hover:bg-zinc-700 text-white text-xs font-medium rounded-xl transition-colors shrink-0 cursor-pointer"
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

              {/* High-Converting Social Share Buttons */}
              <div className="mt-4 grid grid-cols-2 gap-2.5">
                <button
                  type="button"
                  onClick={handleShareLinkedIn}
                  className="flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl bg-[#0a66c2]/15 hover:bg-[#0a66c2]/25 border border-[#0a66c2]/35 text-xs font-medium text-sky-300 hover:text-white transition-all shadow-xs cursor-pointer"
                  title="Copies optimized post copy and opens LinkedIn"
                >
                  <svg className="size-4 fill-current text-sky-400 shrink-0" viewBox="0 0 24 24">
                    <path d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.28 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.75M6.46 10.9v8.37H9.2V10.9H6.46M7.83 6.45c-.95 0-1.72.78-1.72 1.73s.77 1.73 1.72 1.73 1.73-.78 1.73-1.73-.78-1.73-1.73-1.73Z"/>
                  </svg>
                  <span>Share on LinkedIn</span>
                </button>

                <a
                  href={`https://twitter.com/intent/tweet?text=${encodeURIComponent(xPostText)}`}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 text-xs font-medium text-zinc-300 hover:text-white transition-all shadow-xs"
                >
                  <svg className="size-3.5 fill-current text-zinc-100 shrink-0" viewBox="0 0 24 24">
                    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
                  </svg>
                  <span>Share on X</span>
                </a>
              </div>

              {/* Expandable Preview */}
              <div className="mt-3 text-center">
                <button
                  type="button"
                  onClick={() => setShowCopyPreview(!showCopyPreview)}
                  className="text-[11px] font-mono text-zinc-500 hover:text-zinc-300 transition-colors inline-flex items-center gap-1 cursor-pointer"
                >
                  <span>{showCopyPreview ? "Hide post preview" : "Preview share copy"}</span>
                  {showCopyPreview ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
                </button>

                {showCopyPreview && (
                  <div className="mt-2.5 p-3 rounded-xl bg-black/60 border border-zinc-800/80 text-[11px] text-zinc-300 font-mono text-left whitespace-pre-wrap leading-relaxed animate-in fade-in duration-200">
                    {linkedInPostText}
                  </div>
                )}
              </div>
            </div>

            {/* Onboarding Roadmap */}
            <div className="w-full max-w-md mx-auto mt-6 p-6 rounded-2xl bg-zinc-900/30 border border-zinc-800/60 text-left">
              <span className="text-xs font-medium text-zinc-300 block mb-3 font-heading">
                What happens next
              </span>

              <div className="space-y-3.5">
                <div className="flex items-start gap-3">
                  <div className="size-5 rounded-full bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center shrink-0 mt-0.5">
                    <CheckCircle2 className="size-3.5 text-emerald-400" />
                  </div>
                  <div>
                    <div className="text-xs font-medium text-white">Pass Issued & Position Locked</div>
                    <div className="text-[11px] text-zinc-500 mt-0.5 leading-relaxed">
                      Your spot #{formattedPositionNumber} and 30% lifetime discount (EARLY30) are secured.
                    </div>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <div className="size-5 rounded-full bg-sky-500/10 border border-sky-500/30 flex items-center justify-center shrink-0 mt-0.5">
                    <span className="size-1.5 rounded-full bg-sky-400 animate-pulse" />
                  </div>
                  <div>
                    <div className="text-xs font-medium text-white">Cohort Onboarding Invitation</div>
                    <div className="text-[11px] text-zinc-500 mt-0.5 leading-relaxed">
                      We invite accounts in staggered batches to guarantee deliverability and dedicated proxy allocation.
                    </div>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <div className="size-5 rounded-full bg-zinc-800 border border-zinc-700 flex items-center justify-center shrink-0 mt-0.5">
                    <Clock className="size-3 text-zinc-400" />
                  </div>
                  <div>
                    <div className="text-xs font-medium text-zinc-300">One-Click Workspace Access</div>
                    <div className="text-[11px] text-zinc-500 mt-0.5 leading-relaxed">
                      Connect your LinkedIn in under 60 seconds — zero complicated extensions or manual scraping required.
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Action Bar (Reset / Switch) */}
            <div className="mt-6 text-center text-xs text-zinc-500 font-mono">
              {!isEssential && (
                <div className="mb-2">
                  Have a company work email?{" "}
                  <button
                    type="button"
                    onClick={handleSwitchToWorkEmail}
                    className="text-emerald-400 hover:text-emerald-300 underline cursor-pointer"
                  >
                    Upgrade to Priority B2B Queue
                  </button>
                </div>
              )}
              <button
                type="button"
                onClick={() => setActiveEntry(null)}
                className="text-zinc-500 hover:text-zinc-400 underline cursor-pointer"
              >
                Sign up another email
              </button>
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
