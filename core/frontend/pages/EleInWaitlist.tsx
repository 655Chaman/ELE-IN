import React, { useState, useEffect, useId } from "react"
import { useNavigate, useSearchParams, Link } from "react-router-dom"
import { 
  Sparkles, ArrowRight, Check, Copy, Share2, Users, ShieldCheck, 
  Zap, Mail, Search, Clock, HelpCircle, 
  CheckCircle2, AlertCircle, RefreshCw, ChevronRight, ChevronDown, 
  Layers, ExternalLink, Flame
} from "lucide-react"
import { Linkedin } from "@/components/icons/Linkedin"
import { toast } from "sonner"
import { useAuth } from "@/lib/AuthContext"
import { ElesiumLogo } from "@/components/ElesiumLogo"
import { AnimatedThemeToggler } from "@/components/ui/animated-theme-toggler"
import {
  submitWaitlistSignup,
  lookupWaitlistStatus,
  fetchWaitlistStats,
  type WaitlistEntry,
} from "@/lib/waitlistApi"

export function EleInWaitlist() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { session } = useAuth()

  // Form State
  const [mode, setMode] = useState<"join" | "status">("join")
  const [fullName, setFullName] = useState("")
  const [email, setEmail] = useState("")
  const [company, setCompany] = useState("")
  const [role, setRole] = useState("")
  const [teamSize, setTeamSize] = useState("6-20")
  const [outboundVolume, setOutboundVolume] = useState("1,000 - 5,000")
  const [primaryChannel, setPrimaryChannel] = useState("Multi-channel (LinkedIn + Email)")
  const [referralCode, setReferralCode] = useState("")
  const [honeypot, setHoneypot] = useState("") // Layer 2 Bot Trap

  // Status Lookup State
  const [statusQuery, setStatusQuery] = useState("")

  // Submission / Loading State
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isLookingUp, setIsLookingUp] = useState(false)
  const [activeEntry, setActiveEntry] = useState<WaitlistEntry | null>(null)
  const [hasCopied, setHasCopied] = useState(false)

  // Public Stats State
  const [totalCount, setTotalCount] = useState(1482)

  // FAQ Accordion State
  const [openFaq, setOpenFaq] = useState<number | null>(0)

  // Unique Form IDs for Accessibility
  const nameInputId = useId()
  const emailInputId = useId()
  const companyInputId = useId()
  const roleInputId = useId()
  const statusInputId = useId()

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

    // Fetch aggregate stats (Backend API -> Supabase Serverless fallback)
    fetchWaitlistStats()
      .then((count) => {
        if (count) setTotalCount(count)
      })
      .catch(() => {})
  }, [searchParams])

  // Paranoia Layer 2: Debounced and validated submission handler
  const handleJoinSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    const cleanEmail = email.trim().toLowerCase()
    const cleanName = fullName.trim()

    if (!cleanName) {
      toast.error("Please enter your full name.")
      return
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!cleanEmail || !emailRegex.test(cleanEmail)) {
      toast.error("Please provide a valid work email address.")
      return
    }

    setIsSubmitting(true)
    try {
      const data = await submitWaitlistSignup({
        email: cleanEmail,
        full_name: cleanName,
        company: company.trim() || undefined,
        role: role.trim() || undefined,
        team_size: teamSize,
        monthly_outbound_volume: outboundVolume,
        primary_channel: primaryChannel,
        referred_by_code: referralCode.trim().toUpperCase() || undefined,
        utm_source: searchParams.get("utm_source") || "website",
        utm_medium: searchParams.get("utm_medium") || undefined,
        utm_campaign: searchParams.get("utm_campaign") || undefined,
        hp_website_security: honeypot || undefined,
      })

      setActiveEntry(data)
      if (data.is_new !== false) {
        setTotalCount((prev) => prev + 1)
      }

      if (data.is_new === false) {
        toast.info("Welcome back! You are already on the priority waitlist.")
      } else {
        toast.success("Spot reserved! You are on the Ele-in priority waitlist.")
      }
    } catch (err: any) {
      toast.error(err.message || "An unexpected network error occurred.")
    } finally {
      setIsSubmitting(false)
    }
  }

  // Lookup existing status by email or referral code
  const handleStatusLookup = async (e: React.FormEvent) => {
    e.preventDefault()
    const q = statusQuery.trim()
    if (!q) {
      toast.error("Please enter your email address or referral code.")
      return
    }

    setIsLookingUp(true)
    try {
      const data = await lookupWaitlistStatus(q)
      if (!data) {
        throw new Error("No waitlist entry found. Make sure the email is spelled correctly.")
      }
      setActiveEntry(data)
      toast.success("Record found!")
    } catch (err: any) {
      toast.error(err.message || "Could not retrieve waitlist status.")
    } finally {
      setIsLookingUp(false)
    }
  }

  // Copy referral link with visual feedback & fallback
  const shareUrl = activeEntry
    ? `${window.location.origin}/?ref=${activeEntry.referral_code}`
    : `${window.location.origin}`

  const handleCopyLink = async () => {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(shareUrl)
      } else {
        const textArea = document.createElement("textarea")
        textArea.value = shareUrl
        document.body.appendChild(textArea)
        textArea.select()
        document.execCommand("copy")
        document.body.removeChild(textArea)
      }
      setHasCopied(true)
      toast.success("Referral link copied to clipboard!")
      setTimeout(() => setHasCopied(false), 2500)
    } catch (_) {
      toast.error("Could not copy link automatically. Please copy the link manually.")
    }
  }

  // Social sharing helpers
  const shareText = "I just joined the private beta waitlist for Ele-in, the autonomous outbound operating system for modern revenue teams. Join the queue with my priority link:"
  const twitterShareUrl = `https://twitter.com/intent/tweet?text=${encodeURIComponent(shareText)}&url=${encodeURIComponent(shareUrl)}`
  const linkedinShareUrl = `https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(shareUrl)}`
  const whatsappShareUrl = `https://api.whatsapp.com/send?text=${encodeURIComponent(shareText + " " + shareUrl)}`
  const emailShareUrl = `mailto:?subject=${encodeURIComponent("Join the Ele-in Outbound AI Priority Waitlist")}&body=${encodeURIComponent(shareText + "\n\n" + shareUrl)}`

  const faqs = [
    {
      q: "How does the 30% first-year discount work?",
      a: "Every member who joins the priority waitlist automatically receives the EARLY30 founder grant locked to their work email. When your access wave is activated, you can select any plan (Starter, Growth, or Agency) and receive an automatic 30% discount on every billing cycle for your entire first 12 months.",
    },
    {
      q: "When will private beta invitations be released?",
      a: "Beta access is deployed in bi-weekly waves based on queue ranking and GTM volume. Invitations include instant API keys, dedicated sender pods, and 5,000 complimentary AI outreach credits.",
    },
    {
      q: "How does the referral acceleration program work?",
      a: "Every peer or colleague who joins using your unique referral link advances your queue position by 5 spots and awards +10 priority points. Refer 3 colleagues to unlock VIP Wave 1 access.",
    },
    {
      q: "What outbound channels does Ele-in support?",
      a: "Ele-in natively orchestrates dual-channel outbound: automated LinkedIn engagement (profile visits, connection requests, and inMail messaging with humanized jitter) alongside cold email with RFC 8058 1-click unsubscribes and automated inbox warming.",
    },
    {
      q: "Can I register my entire sales or agency team?",
      a: "Yes. In the team size field, specify your sales organization size. Enterprise and Agency teams with 5+ reps receive fast-tracked onboarding and dedicated dedicated proxy IP allocations.",
    },
    {
      q: "Is there any cost during the private beta?",
      a: "No. Private beta participants receive full platform capabilities, multi-channel campaign execution, and lead enrichment at zero platform cost during the beta period.",
    },
  ]

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col selection:bg-primary/20 selection:text-primary">
      {/* ─── Top Navbar ─── */}
      <header className="sticky top-0 z-50 border-b border-border/80 bg-background/80 backdrop-blur-md">
        <div className="max-w-6xl mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link to="/" className="flex items-center gap-2.5 group">
              <ElesiumLogo size={28} variant="auto" />
              <div className="flex flex-col">
                <span className="font-heading font-bold text-lg tracking-tight leading-none">
                  Ele<span className="text-primary">-in</span>
                </span>
                <span className="text-[10px] text-muted-foreground font-medium uppercase tracking-wider">
                  Autonomous Outbound
                </span>
              </div>
            </Link>

            <div className="hidden sm:flex items-center gap-2 ml-4 pl-4 border-l border-border/60">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-primary/10 text-primary border border-primary/20">
                <span className="size-1.5 rounded-full bg-primary animate-pulse" />
                Beta Queue Open
              </span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <AnimatedThemeToggler />

            {session ? (
              <button
                type="button"
                onClick={() => navigate("/elein")}
                className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-semibold hover:bg-primary/90 transition-colors shadow-xs"
              >
                Go to Dashboard
                <ArrowRight className="size-3.5" />
              </button>
            ) : (
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setActiveEntry(null)
                    setMode("status")
                    window.scrollTo({ top: 0, behavior: "smooth" })
                  }}
                  className="hidden md:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                >
                  <Search className="size-3.5" />
                  Check Status
                </button>
                <button
                  type="button"
                  onClick={() => navigate("/login")}
                  className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg border border-border bg-card text-foreground text-xs font-medium hover:bg-muted transition-colors shadow-xs"
                >
                  Member Sign In
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* ─── Hero Section ─── */}
      <main className="flex-1">
        <section className="relative pt-12 pb-16 md:pt-20 md:pb-24 overflow-hidden">
          {/* Subtle Background Radial Glow */}
          <div 
            className="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-5xl h-[450px] bg-gradient-to-b from-primary/10 via-primary/5 to-transparent pointer-events-none blur-3xl -z-10" 
            aria-hidden="true" 
          />

          <div className="max-w-4xl mx-auto px-4 text-center">
            {/* Top Pill */}
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-muted border border-border text-xs text-muted-foreground font-medium mb-6">
              <Sparkles className="size-3.5 text-primary" />
              <span>Private Beta Wave 1: 30% Off Entire 1st Year</span>
              <span className="size-1 rounded-full bg-border" />
              <span className="font-semibold text-foreground">{totalCount.toLocaleString()}+ on waitlist</span>
            </div>

            {/* Main Headline */}
            <h1 className="text-3xl sm:text-5xl md:text-6xl font-bold tracking-tight text-foreground max-w-3xl mx-auto leading-[1.12]">
              The Autonomous Outbound Engine for Revenue Teams
            </h1>

            {/* Subheadline */}
            <p className="mt-5 text-base sm:text-lg text-muted-foreground max-w-2xl mx-auto leading-relaxed">
              Orchestrate personalized LinkedIn and cold email sequences with zero deliverability friction. Join the priority waitlist to lock in guaranteed <strong>30% off all plans for your first year</strong> with voucher code <code className="text-primary font-mono font-semibold">EARLY30</code>.
            </p>

            {/* Waitlist Interactive Card Area */}
            <div className="mt-10 max-w-xl mx-auto text-left">
              {activeEntry ? (
                /* ─── Success & Queue Position Card ─── */
                <div className="bg-card border border-border rounded-xl p-6 sm:p-8 shadow-sm">
                  <div className="flex items-center justify-between pb-5 border-b border-border">
                    <div className="flex items-center gap-2.5">
                      <div className="size-9 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-500 flex items-center justify-center">
                        <CheckCircle2 className="size-5" />
                      </div>
                      <div>
                        <h2 className="font-heading font-semibold text-base text-foreground">
                          Priority Position Reserved
                        </h2>
                        <p className="text-xs text-muted-foreground">
                          {activeEntry.email}
                        </p>
                      </div>
                    </div>
                    <span className="px-2.5 py-1 rounded-full bg-muted border border-border text-xs font-mono font-medium text-foreground">
                      {activeEntry.referral_code}
                    </span>
                  </div>

                  {/* Big Position Display */}
                  <div className="py-6 text-center bg-muted/30 border border-border/60 rounded-xl my-6">
                    <span className="text-xs uppercase font-medium tracking-wider text-muted-foreground block mb-1">
                      Current Queue Position
                    </span>
                    <div className="font-heading font-bold text-4xl sm:text-5xl text-foreground tracking-tight">
                      #{activeEntry.position.toLocaleString()}
                    </div>
                    <div className="mt-2 text-xs text-muted-foreground flex items-center justify-center gap-1.5">
                      <Clock className="size-3.5 text-primary" />
                      <span>Estimated batch access: Wave 1 (Q4 2026)</span>
                    </div>
                  </div>

                  {/* 30% Off First Year Founder Voucher */}
                  <div className="p-4 bg-primary/5 border border-primary/20 rounded-xl mb-6">
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-xs font-semibold text-primary flex items-center gap-1.5">
                        <Sparkles className="size-3.5" />
                        Founder Perk: 30% Off 1st Year Locked
                      </span>
                      <span className="px-2 py-0.5 rounded bg-primary/10 text-primary font-mono text-[11px] font-bold">
                        EARLY30
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Your email is locked in for 30% off all plans for your entire first year (12 full months) upon access activation.
                    </p>
                    <div className="mt-3 pt-3 border-t border-primary/10 grid grid-cols-3 gap-2 text-center text-[11px]">
                      <div className="bg-card/70 p-2 rounded-lg border border-border/50">
                        <span className="text-muted-foreground block text-[10px]">Starter</span>
                        <span className="line-through text-muted-foreground text-[10px]">$29</span>{" "}
                        <span className="font-bold text-foreground">$20.30/mo</span>
                      </div>
                      <div className="bg-card/70 p-2 rounded-lg border border-border/50">
                        <span className="text-muted-foreground block text-[10px]">Growth</span>
                        <span className="line-through text-muted-foreground text-[10px]">$99</span>{" "}
                        <span className="font-bold text-foreground">$69.30/mo</span>
                      </div>
                      <div className="bg-card/70 p-2 rounded-lg border border-border/50">
                        <span className="text-muted-foreground block text-[10px]">Agency</span>
                        <span className="line-through text-muted-foreground text-[10px]">$249</span>{" "}
                        <span className="font-bold text-foreground">$174.30/mo</span>
                      </div>
                    </div>
                  </div>

                  {/* Referral Milestone Accelerator */}
                  <div className="space-y-3 mb-6">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-medium text-foreground flex items-center gap-1.5">
                        <Flame className="size-3.5 text-amber-500" />
                        Referral Boost Progress
                      </span>
                      <span className="text-muted-foreground font-mono">
                        {activeEntry.referrals_count} / 3 Referred
                      </span>
                    </div>
                    <div className="w-full bg-muted rounded-full h-2 overflow-hidden border border-border/50">
                      <div 
                        className="bg-primary h-full transition-all duration-300"
                        style={{ width: `${Math.min(100, (activeEntry.referrals_count / 3) * 100)}%` }}
                      />
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Refer 3 peers to jump 15 spots forward and unlock 2,500 bonus warmup credits.
                    </p>
                  </div>

                  {/* Referral Link & 1-Click Copy */}
                  <div className="space-y-2 mb-6">
                    <label className="text-xs font-medium text-foreground block">
                      Your Unique Priority Referral Link
                    </label>
                    <div className="flex items-center gap-2">
                      <input 
                        type="text" 
                        readOnly 
                        value={shareUrl}
                        className="flex-1 bg-muted/60 border border-border rounded-lg px-3 py-2 text-xs font-mono text-foreground focus:outline-none select-all"
                      />
                      <button
                        type="button"
                        onClick={handleCopyLink}
                        className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 transition-colors shrink-0 shadow-xs"
                      >
                        {hasCopied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
                        <span>{hasCopied ? "Copied" : "Copy Link"}</span>
                      </button>
                    </div>
                  </div>

                  {/* Social Share Buttons */}
                  <div className="pt-4 border-t border-border">
                    <span className="text-xs font-medium text-muted-foreground block mb-2.5">
                      Share with your revenue network
                    </span>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                      <a
                        href={twitterShareUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center justify-center gap-1.5 py-2 px-2 rounded-lg border border-border bg-card hover:bg-muted text-xs font-medium text-foreground transition-colors"
                      >
                        <Share2 className="size-3 text-muted-foreground" />
                        <span>X / Twitter</span>
                      </a>
                      <a
                        href={linkedinShareUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center justify-center gap-1.5 py-2 px-2 rounded-lg border border-border bg-card hover:bg-muted text-xs font-medium text-foreground transition-colors"
                      >
                        <Linkedin className="size-3 text-muted-foreground" />
                        <span>LinkedIn</span>
                      </a>
                      <a
                        href={whatsappShareUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center justify-center gap-1.5 py-2 px-2 rounded-lg border border-border bg-card hover:bg-muted text-xs font-medium text-foreground transition-colors"
                      >
                        <Share2 className="size-3 text-muted-foreground" />
                        <span>WhatsApp</span>
                      </a>
                      <a
                        href={emailShareUrl}
                        className="flex items-center justify-center gap-1.5 py-2 px-2 rounded-lg border border-border bg-card hover:bg-muted text-xs font-medium text-foreground transition-colors"
                      >
                        <Mail className="size-3 text-muted-foreground" />
                        <span>Email</span>
                      </a>
                    </div>
                  </div>

                  <div className="mt-6 pt-4 border-t border-border flex items-center justify-between text-xs text-muted-foreground">
                    <button
                      type="button"
                      onClick={() => {
                        setActiveEntry(null)
                        setEmail("")
                        setFullName("")
                      }}
                      className="hover:text-foreground underline transition-colors"
                    >
                      Register another team member
                    </button>
                    <span className="text-[11px]">Domain: ele-in.com</span>
                  </div>
                </div>
              ) : mode === "join" ? (
                /* ─── Join Waitlist Form ─── */
                <div className="bg-card border border-border rounded-xl p-6 sm:p-8 shadow-sm">
                  <div className="flex items-center justify-between mb-5">
                    <div>
                      <h2 className="font-heading font-semibold text-lg text-foreground">
                        Reserve Your Early Spot
                      </h2>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        Free onboarding, dedicated sender pod, and zero platform fee during beta.
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setMode("status")}
                      className="text-xs text-primary hover:underline font-medium shrink-0 ml-2"
                    >
                      Check Status
                    </button>
                  </div>

                  {/* 30% First-Year Perk Banner */}
                  <div className="p-3 bg-primary/10 border border-primary/20 rounded-lg flex items-center justify-between text-xs mb-4">
                    <div className="flex items-center gap-2 text-foreground font-medium">
                      <Sparkles className="size-4 text-primary shrink-0" />
                      <span>Early Member Perk: <strong>30% Off Entire 1st Year</strong></span>
                    </div>
                    <span className="font-mono px-2 py-0.5 rounded bg-primary/20 text-primary font-bold text-[11px]">
                      EARLY30
                    </span>
                  </div>

                  <form onSubmit={handleJoinSubmit} className="space-y-4">
                    {/* Invisible Honeypot Field for Bot Neutralization (Layer 2) */}
                    <div className="hidden" aria-hidden="true">
                      <input
                        type="text"
                        name="hp_website_security"
                        tabIndex={-1}
                        value={honeypot}
                        onChange={(e) => setHoneypot(e.target.value)}
                        autoComplete="off"
                      />
                    </div>

                    {/* Full Name & Work Email */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <label htmlFor={nameInputId} className="block text-xs font-medium text-foreground mb-1">
                          Full Name <span className="text-primary">*</span>
                        </label>
                        <input
                          id={nameInputId}
                          type="text"
                          required
                          value={fullName}
                          onChange={(e) => setFullName(e.target.value)}
                          placeholder="Sarah Jenkins"
                          className="w-full bg-muted/40 border border-border rounded-lg px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary"
                        />
                      </div>
                      <div>
                        <label htmlFor={emailInputId} className="block text-xs font-medium text-foreground mb-1">
                          Work Email <span className="text-primary">*</span>
                        </label>
                        <input
                          id={emailInputId}
                          type="email"
                          required
                          value={email}
                          onChange={(e) => setEmail(e.target.value)}
                          placeholder="sarah@company.com"
                          className="w-full bg-muted/40 border border-border rounded-lg px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary"
                        />
                      </div>
                    </div>

                    {/* Company Name & Role */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <label htmlFor={companyInputId} className="block text-xs font-medium text-foreground mb-1">
                          Company Name
                        </label>
                        <input
                          id={companyInputId}
                          type="text"
                          value={company}
                          onChange={(e) => setCompany(e.target.value)}
                          placeholder="Acme Corp"
                          className="w-full bg-muted/40 border border-border rounded-lg px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary"
                        />
                      </div>
                      <div>
                        <label htmlFor={roleInputId} className="block text-xs font-medium text-foreground mb-1">
                          Role / Title
                        </label>
                        <input
                          id={roleInputId}
                          type="text"
                          value={role}
                          onChange={(e) => setRole(e.target.value)}
                          placeholder="VP Sales / Founder / SDR"
                          className="w-full bg-muted/40 border border-border rounded-lg px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary"
                        />
                      </div>
                    </div>

                    {/* Outbound Channel Selector */}
                    <div>
                      <span className="block text-xs font-medium text-foreground mb-1.5">
                        Primary Target Outbound Channel
                      </span>
                      <div className="grid grid-cols-3 gap-2">
                        {["Multi-channel", "LinkedIn Only", "Cold Email"].map((ch) => (
                          <button
                            key={ch}
                            type="button"
                            onClick={() => setPrimaryChannel(ch)}
                            className={`py-1.5 px-2 rounded-lg text-xs font-medium border text-center transition-colors ${
                              primaryChannel.includes(ch) || primaryChannel === ch
                                ? "bg-primary/10 border-primary text-primary"
                                : "bg-muted/40 border-border text-muted-foreground hover:bg-muted"
                            }`}
                          >
                            {ch}
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Team Size & Monthly Outreach Volume */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <span className="block text-xs font-medium text-foreground mb-1">
                          GTM / Sales Team Size
                        </span>
                        <div className="grid grid-cols-3 gap-1.5">
                          {["1-5", "6-20", "20+"].map((sz) => (
                            <button
                              key={sz}
                              type="button"
                              onClick={() => setTeamSize(sz)}
                              className={`py-1.5 text-xs font-medium rounded-lg border transition-colors ${
                                teamSize === sz
                                  ? "bg-primary/10 border-primary text-primary"
                                  : "bg-muted/40 border-border text-muted-foreground hover:bg-muted"
                              }`}
                            >
                              {sz}
                            </button>
                          ))}
                        </div>
                      </div>

                      <div>
                        <span className="block text-xs font-medium text-foreground mb-1">
                          Monthly Outbound Volume
                        </span>
                        <div className="grid grid-cols-2 gap-1.5">
                          {["1k - 5k", "5k - 25k"].map((vol) => (
                            <button
                              key={vol}
                              type="button"
                              onClick={() => setOutboundVolume(vol)}
                              className={`py-1.5 text-xs font-medium rounded-lg border transition-colors ${
                                outboundVolume.includes(vol) || outboundVolume === vol
                                  ? "bg-primary/10 border-primary text-primary"
                                  : "bg-muted/40 border-border text-muted-foreground hover:bg-muted"
                              }`}
                            >
                              {vol}
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>

                    {/* Referral Code (if present) */}
                    {referralCode && (
                      <div className="p-2.5 rounded-lg bg-primary/5 border border-primary/20 flex items-center justify-between text-xs">
                        <div className="flex items-center gap-1.5 text-primary">
                          <Sparkles className="size-3.5 shrink-0" />
                          <span>Referral Invitation Applied: <strong>{referralCode}</strong></span>
                        </div>
                        <button
                          type="button"
                          onClick={() => setReferralCode("")}
                          className="text-muted-foreground hover:text-foreground text-[11px]"
                        >
                          Clear
                        </button>
                      </div>
                    )}

                    {/* Submit Action */}
                    <button
                      type="submit"
                      disabled={isSubmitting}
                      className="w-full mt-2 py-2.5 px-4 rounded-lg bg-primary text-primary-foreground font-semibold text-sm hover:bg-primary/90 transition-colors flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed shadow-xs"
                    >
                      {isSubmitting ? (
                        <>
                          <RefreshCw className="size-4 animate-spin" />
                          <span>Securing Your Spot...</span>
                        </>
                      ) : (
                        <>
                          <span>Join Priority Waitlist</span>
                          <ArrowRight className="size-4" />
                        </>
                      )}
                    </button>

                    <p className="text-[11px] text-muted-foreground text-center pt-1">
                      No spam. We will strictly notify you when your access wave is ready.
                    </p>
                  </form>
                </div>
              ) : (
                /* ─── Check Status Form ─── */
                <div className="bg-card border border-border rounded-xl p-6 sm:p-8 shadow-sm">
                  <div className="flex items-center justify-between mb-5">
                    <div>
                      <h2 className="font-heading font-semibold text-lg text-foreground">
                        Check Waitlist Status
                      </h2>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        Enter the email address or referral code you used to register.
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setMode("join")}
                      className="text-xs text-primary hover:underline font-medium shrink-0 ml-2"
                    >
                      Join Waitlist
                    </button>
                  </div>

                  <form onSubmit={handleStatusLookup} className="space-y-4">
                    <div>
                      <label htmlFor={statusInputId} className="block text-xs font-medium text-foreground mb-1">
                        Email Address or Referral Code
                      </label>
                      <input
                        id={statusInputId}
                        type="text"
                        required
                        value={statusQuery}
                        onChange={(e) => setStatusQuery(e.target.value)}
                        placeholder="sarah@company.com or ELE-XXXXXX"
                        className="w-full bg-muted/40 border border-border rounded-lg px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary"
                      />
                    </div>

                    <button
                      type="submit"
                      disabled={isLookingUp}
                      className="w-full py-2.5 px-4 rounded-lg bg-primary text-primary-foreground font-semibold text-sm hover:bg-primary/90 transition-colors flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed shadow-xs"
                    >
                      {isLookingUp ? (
                        <>
                          <RefreshCw className="size-4 animate-spin" />
                          <span>Locating Record...</span>
                        </>
                      ) : (
                        <>
                          <Search className="size-4" />
                          <span>Check Queue Position</span>
                        </>
                      )}
                    </button>
                  </form>
                </div>
              )}
            </div>
          </div>
        </section>

        {/* ─── Key Metrics / Social Proof ─── */}
        <section className="border-y border-border/80 bg-muted/20 py-10">
          <div className="max-w-5xl mx-auto px-4 grid grid-cols-2 md:grid-cols-4 gap-6 text-center">
            <div className="space-y-1">
              <div className="font-heading font-bold text-2xl sm:text-3xl text-foreground">
                99.2%
              </div>
              <p className="text-xs text-muted-foreground">Inbox Placement Rate</p>
            </div>
            <div className="space-y-1">
              <div className="font-heading font-bold text-2xl sm:text-3xl text-foreground">
                4.8x
              </div>
              <p className="text-xs text-muted-foreground">Higher Reply Rate</p>
            </div>
            <div className="space-y-1">
              <div className="font-heading font-bold text-2xl sm:text-3xl text-foreground">
                0 Bans
              </div>
              <p className="text-xs text-muted-foreground">Humanized Safety Cadence</p>
            </div>
            <div className="space-y-1">
              <div className="font-heading font-bold text-2xl sm:text-3xl text-foreground">
                100%
              </div>
              <p className="text-xs text-muted-foreground">RFC 8058 Compliant</p>
            </div>
          </div>
        </section>

        {/* ─── Bento Grid Value Proposition ─── */}
        <section className="py-16 md:py-24 max-w-6xl mx-auto px-4">
          <div className="text-center max-w-2xl mx-auto mb-12">
            <span className="text-xs font-semibold text-primary uppercase tracking-wider block mb-2">
              Autonomous Infrastructure
            </span>
            <h2 className="text-2xl sm:text-4xl font-bold tracking-tight text-foreground">
              Built for Modern Outbound Teams
            </h2>
            <p className="mt-3 text-sm text-muted-foreground">
              Everything your revenue team needs to scale pipeline without burning domains or hiring an army of SDRs.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Bento Card 1: Multi-Channel Orchestration */}
            <div className="md:col-span-2 bg-card border border-border rounded-xl p-6 sm:p-8 flex flex-col justify-between shadow-xs">
              <div>
                <div className="size-10 rounded-lg bg-primary/10 border border-primary/20 text-primary flex items-center justify-center mb-4">
                  <Zap className="size-5" />
                </div>
                <h3 className="font-heading font-semibold text-lg text-foreground">
                  Synchronized Multi-Channel Execution
                </h3>
                <p className="mt-2 text-sm text-muted-foreground max-w-xl">
                  Connect LinkedIn accounts and email sender pods into unified intelligent sequences. Warm prospects on LinkedIn with profile views and soft endorsements before landing your email sequence.
                </p>
              </div>

              <div className="mt-6 pt-6 border-t border-border grid grid-cols-3 gap-3 text-xs">
                <div className="p-3 bg-muted/40 rounded-lg border border-border/50">
                  <span className="font-medium text-foreground block">LinkedIn Jitter</span>
                  <span className="text-muted-foreground text-[11px]">Human-cadence timing</span>
                </div>
                <div className="p-3 bg-muted/40 rounded-lg border border-border/50">
                  <span className="font-medium text-foreground block">Smart Delays</span>
                  <span className="text-muted-foreground text-[11px]">Timezone-aware delivery</span>
                </div>
                <div className="p-3 bg-muted/40 rounded-lg border border-border/50">
                  <span className="font-medium text-foreground block">Pod Rotation</span>
                  <span className="text-muted-foreground text-[11px]">Dynamic domain failover</span>
                </div>
              </div>
            </div>

            {/* Bento Card 2: Deliverability Shield */}
            <div className="bg-card border border-border rounded-xl p-6 sm:p-8 flex flex-col justify-between shadow-xs">
              <div>
                <div className="size-10 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-500 flex items-center justify-center mb-4">
                  <ShieldCheck className="size-5" />
                </div>
                <h3 className="font-heading font-semibold text-lg text-foreground">
                  Deliverability Shield
                </h3>
                <p className="mt-2 text-sm text-muted-foreground">
                  Cryptographic RFC 8058 1-click unsubscribe headers, automated spam score auditing, and auto-cooling protection to safeguard domain reputations permanently.
                </p>
              </div>

              <div className="mt-6 p-3 bg-muted/40 rounded-lg border border-border/50 text-xs">
                <span className="font-medium text-foreground block">Auto-Cooling Engine</span>
                <span className="text-muted-foreground text-[11px]">Pauses sender pods if bounce exceeds 2%</span>
              </div>
            </div>

            {/* Bento Card 3: Bayesian ICP Scoring */}
            <div className="bg-card border border-border rounded-xl p-6 sm:p-8 flex flex-col justify-between shadow-xs">
              <div>
                <div className="size-10 rounded-lg bg-blue-500/10 border border-blue-500/20 text-blue-500 flex items-center justify-center mb-4">
                  <Users className="size-5" />
                </div>
                <h3 className="font-heading font-semibold text-lg text-foreground">
                  Bayesian ICP Scoring
                </h3>
                <p className="mt-2 text-sm text-muted-foreground">
                  Continuously learns from positive and negative replies to score leads and dynamically re-allocate sending credits to high-converting firmographics.
                </p>
              </div>

              <div className="mt-6 p-3 bg-muted/40 rounded-lg border border-border/50 text-xs">
                <span className="font-medium text-foreground block">Adaptive Prioritization</span>
                <span className="text-muted-foreground text-[11px]">Higher conversion per credit</span>
              </div>
            </div>

            {/* Bento Card 4: Knowledge Base & Multimodal Triage */}
            <div className="md:col-span-2 bg-card border border-border rounded-xl p-6 sm:p-8 flex flex-col justify-between shadow-xs">
              <div>
                <div className="size-10 rounded-lg bg-purple-500/10 border border-purple-500/20 text-purple-500 flex items-center justify-center mb-4">
                  <Layers className="size-5" />
                </div>
                <h3 className="font-heading font-semibold text-lg text-foreground">
                  Dynamic Knowledge Base & Smart Inbox
                </h3>
                <p className="mt-2 text-sm text-muted-foreground max-w-xl">
                  Upload case studies, product URLs, and battle cards. The AI drafts hyper-contextual responses, handles objections autonomously, and flags high-intent buyers directly into your CRM.
                </p>
              </div>

              <div className="mt-6 pt-6 border-t border-border grid grid-cols-2 gap-3 text-xs">
                <div className="p-3 bg-muted/40 rounded-lg border border-border/50">
                  <span className="font-medium text-foreground block">Autonomous Objections</span>
                  <span className="text-muted-foreground text-[11px]">Handles pricing & timing queries</span>
                </div>
                <div className="p-3 bg-muted/40 rounded-lg border border-border/50">
                  <span className="font-medium text-foreground block">Human-in-the-Loop</span>
                  <span className="text-muted-foreground text-[11px]">One-click approve or edit</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ─── FAQ Section ─── */}
        <section className="py-16 border-t border-border/80 bg-muted/10">
          <div className="max-w-3xl mx-auto px-4">
            <div className="text-center mb-10">
              <span className="text-xs font-semibold text-primary uppercase tracking-wider block mb-1">
                Frequently Asked Questions
              </span>
              <h2 className="text-2xl sm:text-3xl font-bold text-foreground">
                Everything you need to know about beta access
              </h2>
            </div>

            <div className="space-y-3">
              {faqs.map((faq, idx) => (
                <div 
                  key={faq.q}
                  className="bg-card border border-border rounded-xl overflow-hidden transition-colors"
                >
                  <button
                    type="button"
                    onClick={() => setOpenFaq(openFaq === idx ? null : idx)}
                    className="w-full p-4 sm:p-5 text-left flex items-center justify-between gap-4 font-heading font-medium text-sm text-foreground hover:bg-muted/30 transition-colors"
                  >
                    <span>{faq.q}</span>
                    <ChevronDown className={`size-4 text-muted-foreground shrink-0 transition-transform duration-200 ${openFaq === idx ? "rotate-180" : ""}`} />
                  </button>
                  {openFaq === idx && (
                    <div className="px-4 pb-4 sm:px-5 sm:pb-5 text-xs text-muted-foreground leading-relaxed border-t border-border/50 pt-3">
                      {faq.a}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ─── Bottom CTA Banner ─── */}
        <section className="py-16 md:py-20 border-t border-border text-center max-w-4xl mx-auto px-4">
          <div className="p-8 sm:p-12 rounded-xl bg-gradient-to-b from-card via-card to-muted/40 border border-border shadow-xs">
            <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground">
              Ready to automate your enterprise pipeline?
            </h2>
            <p className="mt-3 text-sm text-muted-foreground max-w-lg mx-auto">
              Secure your spot in Wave 1. Early members receive lifetime preferential credit pricing and direct roadmap access.
            </p>
            <div className="mt-6 flex flex-col sm:flex-row items-center justify-center gap-3">
              <button
                type="button"
                onClick={() => {
                  setActiveEntry(null)
                  setMode("join")
                  window.scrollTo({ top: 0, behavior: "smooth" })
                }}
                className="w-full sm:w-auto px-6 py-2.5 rounded-lg bg-primary text-primary-foreground font-semibold text-xs hover:bg-primary/90 transition-colors shadow-xs"
              >
                Join Waitlist Now
              </button>
              <button
                type="button"
                onClick={() => navigate("/login")}
                className="w-full sm:w-auto px-6 py-2.5 rounded-lg border border-border bg-card text-foreground font-medium text-xs hover:bg-muted transition-colors"
              >
                Already have an account? Sign In
              </button>
            </div>
          </div>
        </section>
      </main>

      {/* ─── Footer ─── */}
      <footer className="border-t border-border bg-background py-8 text-xs text-muted-foreground">
        <div className="max-w-6xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <ElesiumLogo size={20} variant="auto" />
            <span className="font-heading font-medium text-foreground">Ele-in</span>
            <span>&copy; {new Date().getFullYear()} All rights reserved.</span>
          </div>

          <div className="flex items-center gap-4 text-[11px]">
            <span className="inline-flex items-center gap-1.5 text-emerald-500">
              <span className="size-1.5 rounded-full bg-emerald-500 animate-pulse" />
              All Systems Operational
            </span>
            <span className="text-border">|</span>
            <span>Domain: ele-in.com</span>
            <span className="text-border">|</span>
            <Link to="/login" className="hover:text-foreground transition-colors">
              Sign In
            </Link>
          </div>
        </div>
      </footer>
    </div>
  )
}

export default EleInWaitlist
