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
    <div className="min-h-screen bg-[#212121] text-white flex flex-col justify-between font-sans selection:bg-zinc-700 selection:text-white antialiased overflow-x-hidden">
      <main className="w-full max-w-[360px] sm:max-w-[370px] mx-auto px-4 py-12 sm:py-20 text-center my-auto flex flex-col items-center">
        {/* Subtle Brand Mark */}
        <div className="mb-6 flex items-center justify-center">
          <div className="w-10 h-10 rounded-xl p-0.5 bg-[#171717] border border-[#383838] flex items-center justify-center overflow-hidden shadow-sm">
            <img
              src="/logo-icon.png"
              alt="Ele-in"
              className="w-full h-full object-cover rounded-[8px]"
            />
          </div>
        </div>

        {!activeEntry ? (
          /* ========================================================================= */
          /* 1. PRE-SIGNUP VIEW (Exact OpenAI Verification Minimal UI)                 */
          /* ========================================================================= */
          <>
            <h1 className="text-[28px] sm:text-[30px] font-medium tracking-tight text-white leading-tight font-sans">
              LinkedIn outreach, automated
            </h1>

            <p className="mt-2.5 text-[14px] text-[#b4b4b4] max-w-[320px] mx-auto leading-normal font-sans">
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
                    className="w-full h-[52px] bg-[#212121] border border-[#424242] hover:border-[#525252] focus:border-white focus:outline-none rounded-2xl px-4 text-white placeholder-[#737373] text-base sm:text-[14px] transition-colors font-sans"
                  />
                </div>
                <div>
                  <input
                    type="text"
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                    placeholder="Last name"
                    required
                    className="w-full h-[52px] bg-[#212121] border border-[#424242] hover:border-[#525252] focus:border-white focus:outline-none rounded-2xl px-4 text-white placeholder-[#737373] text-base sm:text-[14px] transition-colors font-sans"
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
                  className="w-full h-[52px] bg-[#212121] border border-[#424242] hover:border-[#525252] focus:border-white focus:outline-none rounded-2xl px-4 text-white placeholder-[#737373] text-base sm:text-[14px] transition-colors font-sans"
                />
                {hasValidEmailFormat && (
                  <div className="mt-2 text-left px-1">
                    {isWorkEmail ? (
                      <div className="flex items-center gap-1.5 text-[12px] text-emerald-400 font-sans">
                        <span className="size-1.5 rounded-full bg-emerald-400 shrink-0" />
                        <span>Priority B2B Access unlocked {detectedCompany ? `(${detectedCompany})` : ""}</span>
                      </div>
                    ) : (
                      <div className="flex items-center gap-1.5 text-[12px] text-[#8e8e8e] font-sans">
                        <span className="size-1.5 rounded-full bg-[#8e8e8e] shrink-0" />
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

              {/* The Signature OpenAI White Pill Button */}
              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full h-[52px] mt-4 rounded-full bg-white text-black font-medium text-[15px] hover:bg-[#e3e3e3] active:bg-[#d4d4d4] transition-colors cursor-pointer disabled:opacity-50 font-sans shadow-sm flex items-center justify-center"
              >
                {isSubmitting ? "Submitting..." : "Continue"}
              </button>
            </form>

            {/* Subtle Legal / Disclaimer Text */}
            <p className="mt-6 text-[12px] text-[#8e8e8e] leading-relaxed max-w-[320px] font-sans">
              By continuing, you lock <span className="text-[#b4b4b4]">30% founder pricing</span> (EARLY30). Early access invitations are dispatched in cohorts to ensure high deliverability.
            </p>
          </>
        ) : (
          /* ========================================================================= */
          /* 2. POST-SIGNUP VIEW (Clean OpenAI Verification Confirmation Style)       */
          /* ========================================================================= */
          <div className="w-full flex flex-col items-center text-center">
            <h1 className="text-[28px] sm:text-[30px] font-medium tracking-tight text-white leading-tight font-sans">
              Spot #{formattedPositionNumber} reserved
            </h1>

            <p className="mt-2.5 text-[14px] text-[#b4b4b4] max-w-[320px] mx-auto leading-normal font-sans">
              Reserved for {displayName}
              {companyName ? ` · ${companyName}` : ""}. We'll notify you as soon as your cohort opens.
            </p>

            {/* Clean Ticket Card */}
            <div className="w-full mt-6 rounded-2xl bg-[#262626] border border-[#383838] p-5 text-left shadow-md">
              <div className="flex items-center justify-between pb-3 border-b border-[#383838]">
                <span className="text-[11px] uppercase tracking-wider text-[#8e8e8e] font-sans">
                  Access Pass
                </span>
                <span className="text-[11px] font-mono text-emerald-400">
                  {isEssential ? "Priority B2B" : "Cohort 1"}
                </span>
              </div>

              <div className="py-4 text-center">
                <span className="text-[10px] text-[#8e8e8e] uppercase tracking-widest block mb-1 font-sans">
                  Queue Position
                </span>
                <div className="text-4xl sm:text-5xl font-mono text-white tracking-tight">
                  #{formattedPositionNumber}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 text-[12px] border-t border-[#383838] pt-3">
                <div className="bg-[#212121] rounded-xl p-2.5 border border-[#383838]">
                  <span className="text-[10px] text-[#8e8e8e] uppercase block font-sans">Tier</span>
                  <span className="font-medium text-white truncate block mt-0.5 font-sans">
                    {isEssential ? "Priority B2B" : "Standard"}
                  </span>
                </div>
                <div className="bg-[#212121] rounded-xl p-2.5 border border-[#383838]">
                  <span className="text-[10px] text-[#8e8e8e] uppercase block font-sans">Discount</span>
                  <span className="font-medium text-emerald-400 truncate block mt-0.5 font-sans">
                    30% off (EARLY30)
                  </span>
                </div>
              </div>

              <div className="mt-4 pt-3.5 border-t border-[#383838]">
                <div className="text-[12px] text-[#b4b4b4] mb-2 font-sans">
                  Move up 5 spots for each teammate you invite:
                </div>
                <div className="flex gap-2">
                  <input
                    type="text"
                    readOnly
                    value={shareUrl}
                    className="flex-1 bg-[#212121] border border-[#383838] rounded-xl px-3 py-2 text-base sm:text-xs text-zinc-300 font-mono select-all focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={handleCopyLink}
                    className="flex items-center gap-1.5 px-4 py-2 bg-[#383838] hover:bg-[#424242] text-white text-xs font-medium rounded-xl transition-colors shrink-0 cursor-pointer font-sans"
                  >
                    {hasCopied ? (
                      <>
                        <Check className="size-3.5 text-emerald-400" />
                        <span>Copied</span>
                      </>
                    ) : (
                      <>
                        <Copy className="size-3.5 text-[#8e8e8e]" />
                        <span>Copy</span>
                      </>
                    )}
                  </button>
                </div>

                {/* Social Share Buttons */}
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={handleShareLinkedIn}
                    className="flex items-center justify-center gap-1.5 py-2.5 px-3 rounded-full bg-[#212121] hover:bg-[#2e2e2e] border border-[#383838] text-[13px] font-medium text-white transition-colors cursor-pointer font-sans"
                  >
                    <svg className="size-3.5 fill-current text-[#b4b4b4] shrink-0" viewBox="0 0 24 24">
                      <path d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.28 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.75M6.46 10.9v8.37H9.2V10.9H6.46M7.83 6.45c-.95 0-1.72.78-1.72 1.73s.77 1.73 1.72 1.73s.77 1.73 1.72 1.73-.78 1.73-1.73-.78-1.73-1.73Z"/>
                    </svg>
                    <span>LinkedIn</span>
                  </button>

                  <a
                    href={`https://twitter.com/intent/tweet?text=${encodeURIComponent(xPostText)}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center justify-center gap-1.5 py-2.5 px-3 rounded-full bg-[#212121] hover:bg-[#2e2e2e] border border-[#383838] text-[13px] font-medium text-white transition-colors font-sans"
                  >
                    <svg className="size-3.5 fill-current text-[#b4b4b4] shrink-0" viewBox="0 0 24 24">
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
                className="py-2 px-3 text-[12px] text-[#8e8e8e] hover:text-[#b4b4b4] transition-colors cursor-pointer font-sans inline-block"
              >
                Register another email
              </button>
            </div>
          </div>
        )}
      </main>

      {/* Minimal Footer */}
      <footer className="w-full max-w-[360px] sm:max-w-[370px] mx-auto px-4 pb-8 pt-2 text-center text-[12px] text-[#8e8e8e] font-sans">
        <div>© 2026 Ele-in · All rights reserved</div>
      </footer>
    </div>
  )
}
