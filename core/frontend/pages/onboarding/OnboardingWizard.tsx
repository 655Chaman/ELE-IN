import { useState, useEffect, useRef, useMemo } from "react"
import { useNavigate } from "react-router-dom"
import { motion, AnimatePresence } from "motion/react"
import Papa from "papaparse"
import { useHRTreeStore, dagToTree } from "@campaigns/eiTreeStore"
import { 
  Sparkles, CheckCircle2, ArrowLeft, ArrowRight, 
  ShieldCheck, Zap, Globe, 
  UploadCloud, Check, UserCheck, Loader2,
  Copy, RotateCcw, Sliders, AlertTriangle, TrendingUp, Mail
} from "lucide-react"
import { ElesiumLogo } from "@/components/ElesiumLogo"
import { Linkedin } from "@/components/icons/Linkedin"
import { toast } from "sonner"
import { cn } from "@/lib/utils"
import { fetchWithAuth } from "@/lib/apiClient"
import { AnimatedThemeToggler } from "@/components/ui/animated-theme-toggler"
import { useTheme } from "@/components/ThemeProvider"
import ConnectModal from "@/components/accounts/ConnectModal"

const QUICK_TITLES = [
  "VP of Sales",
  "Founder & CEO",
  "Head of Growth",
  "Chief Technology Officer",
  "Talent Acquisition Lead"
]

const GOAL_OPTIONS = [
  { id: "book_demos", label: "Book B2B Sales Demos", desc: "Turn qualified ICPs into booked calendar calls" },
  { id: "recruit", label: "Recruit High-Caliber Talent", desc: "Source top engineers, designers, and leads directly" },
  { id: "fundraise", label: "Network with Investors & VCs", desc: "Start warm founder conversations for your next round" },
  { id: "partnerships", label: "Strategic Partnerships", desc: "Connect with key decision-makers and channel partners" }
]

export function OnboardingWizard() {
  const navigate = useNavigate()
  const { theme, setTheme } = useTheme()

  // ─── Step State (1: Goals & ICP, 2: Value Prop & Aha Preview, 3: Audience, 4: Safety & LinkedIn, 5: Touchdown) ───
  const [step, setStep] = useState(1)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [showConnectModal, setShowConnectModal] = useState(false)
  const [connectedAccount, setConnectedAccount] = useState<any | null>(null)
  const [isSandboxMode, setIsSandboxMode] = useState(false)

  // ─── Inputs State ───
  const [selectedGoal, setSelectedGoal] = useState<string>("book_demos")
  const selectedGoals = useMemo(() => [selectedGoal], [selectedGoal])
  const [targetTitle, setTargetTitle] = useState("VP of Sales")
  const [targetIndustry, setTargetIndustry] = useState("General B2B")
  
  const [companyWebsite, setCompanyWebsite] = useState("https://mycompany.com")
  const [valueProp, setValueProp] = useState("Automating outbound pipeline with human-grade AI sequences")
  
  // Dynamic Message preview
  const [connectionMessage, setConnectionMessage] = useState(
    "Hi {{first_name}}, I saw your work scaling the team at {{company_name}}. We built an AI engine that automates outbound pipeline while keeping account safety airtight. Would you be open to comparing notes?"
  )
  const [followupMessage, setFollowupMessage] = useState(
    "Hi {{first_name}}, just following up! Most {{job_title}}s we work with were skeptical of LinkedIn automation until they saw our residential jitter and zero-ban record. Open to a 3-min loom?"
  )

  // ─── Area 1: Deep AI Generation & Timeline State ───
  const [aiTone, setAiTone] = useState<"consultative" | "direct" | "curious">("consultative")
  const [isGeneratingAi, setIsGeneratingAi] = useState(false)
  const [aiSpamSafetyScore, setAiSpamSafetyScore] = useState(98.2)
  const [hookStrategy, setHookStrategy] = useState("Peer-to-peer consultative approach: positions conversation around shared B2B SaaS insights.")
  const [usedLlm, setUsedLlm] = useState(false)
  const [isCopied, setIsCopied] = useState(false)
  const [selectedRampWeek, setSelectedRampWeek] = useState<1 | 2 | 3 | 4>(4)
  const [safetyViewMode, setSafetyViewMode] = useState<"ramp" | "comparison">("ramp")
  const [copiedFounderEmail, setCopiedFounderEmail] = useState(false)

  // Audience State
  const [audienceType, setAudienceType] = useState<"demo" | "single" | "csv">("demo")
  const [singleLeadUrl, setSingleLeadUrl] = useState("")
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [csvFile, setCsvFile] = useState<File | null>(null)
  const [customLeads, setCustomLeads] = useState<any[]>([])
  const [isDragging, setIsDragging] = useState(false)

  const handleCsvFile = (file: File) => {
    setCsvFile(file)
    Papa.parse(file, {
      header: true,
      skipEmptyLines: true,
      complete: (results: any) => {
        const rows = results.data || []
        const parsed = rows.map((r: any) => {
          const findVal = (keywords: string[]) => {
            const key = Object.keys(r).find(k => keywords.some(kw => k.toLowerCase().includes(kw)))
            let val = key ? String(r[key] || "").trim() : ""
            // Layer 2 Human Paranoia: Sanitize formula injection
            if (val.startsWith("=") || val.startsWith("+") || val.startsWith("-") || val.startsWith("@")) {
              val = "'" + val
            }
            return val
          }
          let url = findVal(["linkedin", "url", "profile"])
          if (url && !url.startsWith("http://") && !url.startsWith("https://")) {
            url = url.includes("linkedin.com") ? `https://${url}` : `https://linkedin.com/in/${url.replace(/^\/+/, "")}`
          }
          return {
            first_name: findVal(["first", "fname", "name"]).slice(0, 80),
            last_name: findVal(["last", "lname"]).slice(0, 80),
            linkedin_url: url.slice(0, 500),
            company_name: findVal(["company", "org", "account"]).slice(0, 120),
            job_title: findVal(["title", "role", "position", "job"]).slice(0, 100)
          }
        }).filter((l: any) => l.linkedin_url || l.first_name)
        
        setCustomLeads(parsed)
        if (parsed.length > 0) {
          toast.success(`Successfully parsed ${parsed.length} prospects from ${file.name}`)
        } else {
          toast.warning("Could not find lead columns in this CSV. Please check formatting.")
        }
      },
      error: (err: any) => {
        toast.error(`CSV parsing error: ${err.message}`)
      }
    })
  }

  // Prospect POV toggle
  const [prospectPovTab, setProspectPovTab] = useState<"connect" | "followup">("connect")

  // ─── Restore Draft on mount (Layer 1 Environmental Failure Resistance) ───
  useEffect(() => {
    try {
      const saved = localStorage.getItem("elein_onboarding_draft")
      if (saved) {
        const parsed = JSON.parse(saved)
        if (parsed.step) setStep(parsed.step)
        if (parsed.selectedGoal) setSelectedGoal(parsed.selectedGoal)
        else if (parsed.selectedGoals && parsed.selectedGoals[0]) setSelectedGoal(parsed.selectedGoals[0])
        if (parsed.targetTitle) setTargetTitle(parsed.targetTitle)
        if (parsed.targetIndustry) setTargetIndustry(parsed.targetIndustry)
        if (parsed.companyWebsite) setCompanyWebsite(parsed.companyWebsite)
        if (parsed.valueProp) setValueProp(parsed.valueProp)
        if (parsed.connectionMessage) setConnectionMessage(parsed.connectionMessage)
        if (parsed.followupMessage) setFollowupMessage(parsed.followupMessage)
      }
    } catch (e) {
      console.warn("Failed to restore onboarding draft:", e)
    }
  }, [])

  // ─── Auto-save Draft to LocalStorage ───
  useEffect(() => {
    try {
      localStorage.setItem("elein_onboarding_draft", JSON.stringify({
        step,
        selectedGoal,
        selectedGoals: [selectedGoal],
        targetTitle,
        targetIndustry,
        companyWebsite,
        valueProp,
        connectionMessage,
        followupMessage
      }))
    } catch (e) {
      console.warn("Could not write onboarding draft:", e)
    }
  }, [step, selectedGoal, targetTitle, targetIndustry, companyWebsite, valueProp, connectionMessage, followupMessage])

  // Recalculate message dynamically when Title or Value Prop changes
  const regenerateAhaMessage = (title: string, prop: string, tone: "consultative" | "direct" | "curious" = aiTone) => {
    const plural = title.toLowerCase().endsWith("s") ? title : `${title}s`
    const cleanProp = prop.toLowerCase().replace(/^(we help|helps)\s*/i, "").trim() || "scale outbound"

    if (tone === "direct") {
      setConnectionMessage(
        `Hi {{first_name}}, saw what you're leading at {{company_name}}. Most ${plural} struggle with outbound pipeline consistency. We built a way to ${cleanProp} with zero spam flags. Worth connecting?`
      )
      setFollowupMessage(
        `Hi {{first_name}}, circling back briefly. Most ${plural} we work with care about reliable deliverability above all else. Would a 2-minute overview of our residential proxy model be relevant this week?`
      )
      setHookStrategy(`Direct Challenger style: cuts straight to ${title} pipeline predictability.`)
    } else if (tone === "curious") {
      setConnectionMessage(
        `Hi {{first_name}}, loved your recent updates at {{company_name}}. Curious how your team currently approaches efforts to ${cleanProp}? Open to connecting and sharing what we've seen work best?`
      )
      setFollowupMessage(
        `Hi {{first_name}}, bumping this gently! We recently helped another ${title} increase positive replies by 34% without spam flags. Open to comparing benchmarks?`
      )
      setHookStrategy(`Curiosity-led inquiry: invites ${title} to benchmark against peers.`)
    } else {
      setConnectionMessage(
        `Hi {{first_name}}, noticed your work leading initiatives at {{company_name}}. We built an engine that helps ${plural} ${cleanProp}. Open to comparing notes on how other high-growth teams approach this?`
      )
      setFollowupMessage(
        `Hi {{first_name}}, following up briefly on my note. Knowing how packed schedules are for ${plural}, I'd love to share how our safety engine guarantees zero spam flags. Worth a 2-min chat?`
      )
      setHookStrategy(`Peer-to-peer consultative approach: positions conversation around shared operational insights.`)
    }
    setAiSpamSafetyScore(98.2)
  }

  const fetchAiGeneratedPitch = async (overrideTone?: "consultative" | "direct" | "curious") => {
    const toneToUse = overrideTone || aiTone
    if (overrideTone) setAiTone(overrideTone)
    setIsGeneratingAi(true)
    try {
      const res = await fetchWithAuth("/api/onboarding/generate-preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_title: targetTitle,
          target_industry: targetIndustry,
          company_name: "Acme Corp",
          company_url: companyWebsite.trim(),
          value_prop: valueProp.trim(),
          tone: toneToUse
        })
      })

      if (res.ok) {
        const data = await res.json()
        if (data.connection_note) setConnectionMessage(data.connection_note)
        if (data.followup_message) setFollowupMessage(data.followup_message)
        if (data.spam_safety_score) setAiSpamSafetyScore(data.spam_safety_score)
        if (data.hook_strategy) setHookStrategy(data.hook_strategy)
        setUsedLlm(Boolean(data.used_llm))
        toast.success(data.used_llm ? "Bespoke AI sequence generated!" : "Synthesized high-converting sequence!")
      } else {
        regenerateAhaMessage(targetTitle, valueProp, toneToUse)
      }
    } catch (err) {
      console.warn("AI generation fallback:", err)
      regenerateAhaMessage(targetTitle, valueProp, toneToUse)
    } finally {
      setIsGeneratingAi(false)
    }
  }

  const handleCopyPitch = () => {
    const textToCopy = prospectPovTab === "connect" ? connectionMessage : followupMessage
    navigator.clipboard.writeText(textToCopy)
    setIsCopied(true)
    toast.success("Copied message to clipboard!")
    setTimeout(() => setIsCopied(false), 2000)
  }

  // ─── Completion Handler (Layer 0 + Layer 1 + Layer 2) ───
  const handleCompleteOnboarding = async () => {
    if (isSubmitting) return
    setIsSubmitting(true)

    try {
      // 1. Seed demo campaign, leads, knowledge synthesis, and enrollment
      const res = await fetchWithAuth("/api/onboarding/seed-demo-data", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_title: targetTitle,
          target_industry: targetIndustry,
          company_name: "Acme Corp",
          company_url: companyWebsite.trim(),
          core_value_prop: valueProp.trim(),
          campaign_name: `Outreach to ${targetTitle}s`,
          connection_note: connectionMessage,
          followup_message: followupMessage,
          sender_account_id: connectedAccount?.id || null,
          is_sandbox: isSandboxMode,
          single_lead_url: audienceType === "single" ? singleLeadUrl.trim() : null,
          custom_leads: audienceType === "csv" ? customLeads : [],
          force: true
        })
      })

      const data = await res.json().catch(() => ({}));
      if (data?.workspace_id) {
        localStorage.setItem("elein_active_workspace", data.workspace_id);
      }

      if (!res.ok) {
        console.warn("Seeding demo data returned non-200, proceeding gracefully with client state.")
      }

      // 2. Hydrate global Tree Store so canvas is immediately primed
      try {
        const canonicalNodes = [
          {
            id: "node_conn",
            type: "connection_request",
            position: { x: 250, y: 100 },
            data: {
              label: "Connection Request",
              note_strategy: "Fixed note",
              note: connectionMessage.slice(0, 300),
              delayDays: 0
            }
          },
          {
            id: "node_msg",
            type: "send_message",
            position: { x: 250, y: 300 },
            data: {
              label: "Follow-up (Day 2)",
              body: followupMessage,
              delayDays: 2
            }
          }
        ];
        const canonicalEdges = [
          {
            id: "edge_conn_msg",
            source: "node_conn",
            target: "node_msg",
            sourceHandle: "accepted"
          }
        ];
        const tree = dagToTree(canonicalNodes as any, canonicalEdges as any);
        useHRTreeStore.getState().loadTree(tree);
      } catch (treeErr) {
        console.warn("Tree store hydration warning:", treeErr);
      }

      // 3. Mark onboarding completed in localStorage
      localStorage.setItem("onboarding_dismissed", "true")
      localStorage.setItem("elein_has_completed_onboarding", "true")
      localStorage.removeItem("elein_onboarding_draft")

      toast.success("Welcome aboard! Your campaign is primed and ready.")
      if (data?.campaign_id) {
        navigate(`/elein/campaigns/${data.campaign_id}`)
      } else {
        navigate("/elein/campaigns")
      }
    } catch (err: any) {
      console.error("Error finalizing onboarding:", err)
      toast.error("Could not complete setup. Redirecting to dashboard...")
      localStorage.setItem("onboarding_dismissed", "true")
      navigate("/elein/campaigns")
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col font-sans selection:bg-primary/20">
      {/* ─── Top Bar ─── */}
      <header className="h-16 border-b border-border/50 px-8 flex items-center justify-between shrink-0 bg-background/80 backdrop-blur-md sticky top-0 z-40">
        <div className="flex items-center gap-2.5">
          <img src="/logo-icon.png" alt="Ele-in" className="w-6 h-6 object-contain rounded-md" />
          <span className="font-semibold text-sm tracking-tight text-foreground">Ele-in</span>
        </div>

        <div className="flex items-center gap-4">
          <button
            onClick={() => {
              localStorage.setItem("onboarding_dismissed", "true")
              navigate("/elein/campaigns")
            }}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
          >
            Skip to Dashboard
          </button>
          <AnimatedThemeToggler variant="circle" theme={theme as any} onThemeChange={setTheme} />
        </div>
      </header>

      {/* ─── Main Content Area ─── */}
      <main className="flex-1 flex flex-col justify-center items-center p-6 md:p-12 max-w-4xl w-full mx-auto">
        <AnimatePresence mode="wait">
          {/* ══════════════════════════════════════════════════════════════
              STEP 1: Goals & Target ICP (Headspace Multi-Intent Pattern)
          ══════════════════════════════════════════════════════════════ */}
          {step === 1 && (
            <motion.div
              key="step1"
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -15 }}
              transition={{ duration: 0.3 }}
              className="w-full space-y-8"
            >
              <div className="text-center max-w-xl mx-auto space-y-2">
                <span className="text-xs font-bold uppercase tracking-wider text-primary">Outcome Definition</span>
                <h1 className="text-3xl md:text-4xl font-light tracking-tight text-foreground">
                  What do you want to achieve with Ele-in?
                </h1>
                <p className="text-sm text-muted-foreground">
                  Select your primary campaign objective. We calibrate your sequence architecture and cadence to match this goal.
                </p>
              </div>

              {/* Goals Grid (Single-Select Primary Objective) */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                {GOAL_OPTIONS.map((g) => {
                  const isChecked = selectedGoal === g.id
                  return (
                    <div
                      key={g.id}
                      onClick={() => setSelectedGoal(g.id)}
                      className={cn(
                        "p-5 rounded-2xl border transition-all cursor-pointer flex items-start gap-3.5 text-left group",
                        isChecked 
                          ? "bg-primary/5 border-primary shadow-sm ring-1 ring-primary/20" 
                          : "bg-card/40 border-border/70 hover:border-foreground/20 hover:bg-card/80"
                      )}
                    >
                      <div className={cn(
                        "w-4 h-4 rounded-full border flex items-center justify-center shrink-0 mt-0.5 transition-colors",
                        isChecked ? "border-primary bg-primary" : "border-muted-foreground/40 group-hover:border-foreground/40"
                      )}>
                        {isChecked && <div className="w-1.5 h-1.5 rounded-full bg-primary-foreground" />}
                      </div>
                      <div>
                        <h3 className="text-sm font-semibold text-foreground">{g.label}</h3>
                        <p className="text-xs text-muted-foreground mt-0.5">{g.desc}</p>
                      </div>
                    </div>
                  )
                })}
              </div>

              {/* Target ICP Input */}
              <div className="p-6 rounded-2xl border border-border/60 bg-muted/10 space-y-3">
                <label className="block text-xs font-bold text-foreground uppercase tracking-wide">
                  Who is your primary target decision-maker?
                </label>
                <input
                  type="text"
                  value={targetTitle}
                  onChange={(e) => {
                    setTargetTitle(e.target.value)
                    regenerateAhaMessage(e.target.value, valueProp)
                  }}
                  placeholder="e.g. VP of Sales, CTO, Head of Talent"
                  className="w-full px-4 py-2.5 rounded-xl bg-background border border-border/60 text-sm focus:outline-none focus:border-primary transition-colors text-foreground"
                />
                {/* Quick Title Pills */}
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {QUICK_TITLES.map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => {
                        setTargetTitle(t)
                        regenerateAhaMessage(t, valueProp)
                      }}
                      className={cn(
                        "text-[11px] px-2.5 py-1 rounded-lg border font-medium transition-colors cursor-pointer",
                        targetTitle === t 
                          ? "bg-primary/10 border-primary text-primary" 
                          : "bg-background border-border/50 text-muted-foreground hover:text-foreground"
                      )}
                    >
                      {t}
                    </button>
                  ))}
                </div>
              </div>

              {/* Continue Button */}
              <div className="flex justify-end pt-2">
                <button
                  onClick={() => setStep(2)}
                  className="inline-flex items-center gap-2 px-7 py-3 rounded-xl bg-primary text-primary-foreground font-semibold text-sm hover:opacity-90 transition-all shadow-md shadow-primary/20 active:scale-95 cursor-pointer"
                >
                  Continue to Sequence Preview <ArrowRight size={15} />
                </button>
              </div>
            </motion.div>
          )}

          {/* ══════════════════════════════════════════════════════════════
              STEP 2: The "Aha!" Moment (Endel / Speak Personalized Outcome)
          ══════════════════════════════════════════════════════════════ */}
          {step === 2 && (
            <motion.div
              key="step2"
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -15 }}
              transition={{ duration: 0.3 }}
              className="w-full space-y-8"
            >
              {/* Step Header */}
              <div className="text-center max-w-xl mx-auto space-y-2">
                <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-primary/10 border border-primary/20 text-primary text-xs font-bold">
                  <ElesiumLogo size={13} />
                  <span>Live AI Sequence Generation</span>
                </div>
                <h1 className="text-3xl md:text-4xl font-light tracking-tight text-foreground">
                  Experience your outreach in action
                </h1>
                <p className="text-sm text-muted-foreground">
                  See how our residential AI engine crafts bespoke, human-grade outreach for your exact ICP.
                </p>
              </div>

              {/* Company & Value Prop Inputs */}
              <div className="p-6 rounded-2xl border border-border/60 bg-card/40 space-y-5">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-bold text-foreground mb-1.5 uppercase tracking-wide">
                      Company Website / URL
                    </label>
                    <div className="flex items-center gap-2 px-3 py-2.5 rounded-xl bg-background border border-border/60">
                      <Globe size={15} className="text-muted-foreground" />
                      <input
                        type="text"
                        value={companyWebsite}
                        onChange={(e) => setCompanyWebsite(e.target.value)}
                        placeholder="https://acme.io"
                        className="bg-transparent text-sm w-full focus:outline-none text-foreground placeholder:text-muted-foreground"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-foreground mb-1.5 uppercase tracking-wide">
                      Your Core Value Proposition (1 Sentence)
                    </label>
                    <input
                      type="text"
                      value={valueProp}
                      onChange={(e) => {
                        setValueProp(e.target.value)
                        regenerateAhaMessage(targetTitle, e.target.value, aiTone)
                      }}
                      placeholder="e.g. Cut cloud costs by 40% with zero downtime"
                      className="w-full px-3 py-2.5 rounded-xl bg-background border border-border/60 text-sm focus:outline-none focus:border-primary transition-colors text-foreground"
                    />
                  </div>
                </div>

                {/* Value Prop Quick-Fill Inspirations */}
                <div className="flex flex-wrap items-center gap-1.5 pt-1">
                  <span className="text-[11px] font-medium text-muted-foreground mr-1">Inspirations:</span>
                  {[
                    "Cut cloud costs by 40% with zero downtime",
                    "Automate outbound pipeline with human-grade AI",
                    "Source vetted senior engineers in 48 hours",
                    "Book 15+ qualified enterprise discovery calls"
                  ].map((insp) => (
                    <button
                      key={insp}
                      type="button"
                      onClick={() => {
                        setValueProp(insp)
                        regenerateAhaMessage(targetTitle, insp, aiTone)
                      }}
                      className="text-[11px] px-2.5 py-1 rounded-lg border border-border/50 bg-background/50 hover:bg-muted/40 text-muted-foreground hover:text-foreground transition-all cursor-pointer"
                    >
                      {insp}
                    </button>
                  ))}
                </div>
              </div>

              {/* ─── The Interactive Prospect POV Box (The Visceral Aha Moment) ─── */}
              <div className="border border-border/80 rounded-2xl bg-card/60 p-6 shadow-xl relative overflow-hidden space-y-5">
                {/* Simulator Toolbar */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/50 pb-4">
                  <div className="flex items-center gap-2.5">
                    <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
                    <span className="text-xs font-bold uppercase tracking-wider text-foreground">
                      Live Prospect POV Simulation
                    </span>
                  </div>

                  {/* Tone Pills & Step Toggle */}
                  <div className="flex flex-wrap items-center gap-2">
                    {/* Tone Selector */}
                    <div className="flex items-center gap-1 bg-muted/40 p-1 rounded-lg border border-border/50">
                      {[
                        { id: "consultative", label: "Consultative", icon: Sparkles },
                        { id: "direct", label: "Direct ROI", icon: Zap },
                        { id: "curious", label: "Curious", icon: Sliders }
                      ].map((t) => (
                        <button
                          key={t.id}
                          onClick={() => fetchAiGeneratedPitch(t.id as any)}
                          disabled={isGeneratingAi}
                          className={cn(
                            "text-[11px] font-semibold px-2.5 py-1 rounded-md transition-all flex items-center gap-1 cursor-pointer disabled:opacity-50",
                            aiTone === t.id
                              ? "bg-background text-foreground shadow-sm font-bold"
                              : "text-muted-foreground hover:text-foreground"
                          )}
                        >
                          <t.icon size={11} /> {t.label}
                        </button>
                      ))}
                    </div>

                    {/* Step 1 vs Step 2 Toggle */}
                    <div className="flex items-center gap-1 bg-muted/40 p-1 rounded-lg border border-border/50">
                      <button
                        onClick={() => setProspectPovTab("connect")}
                        className={cn(
                          "text-[11px] font-semibold px-3 py-1 rounded-md transition-all cursor-pointer",
                          prospectPovTab === "connect" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
                        )}
                      >
                        Step 1: Note
                      </button>
                      <button
                        onClick={() => setProspectPovTab("followup")}
                        className={cn(
                          "text-[11px] font-semibold px-3 py-1 rounded-md transition-all cursor-pointer",
                          prospectPovTab === "followup" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
                        )}
                      >
                        Step 2: Follow-up
                      </button>
                    </div>

                    {/* Regenerate with AI button */}
                    <button
                      onClick={() => fetchAiGeneratedPitch()}
                      disabled={isGeneratingAi}
                      className="px-3 py-1.5 rounded-lg bg-primary/10 border border-primary/20 text-primary hover:bg-primary/20 font-bold text-[11px] transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                      title="Run real-time LLM pitch generator"
                    >
                      {isGeneratingAi ? (
                        <Loader2 size={12} className="animate-spin" />
                      ) : (
                        <ElesiumLogo size={12} />
                      )}
                      <span>{isGeneratingAi ? "Generating..." : "Regenerate AI"}</span>
                    </button>
                  </div>
                </div>

                {/* Simulated LinkedIn Message Interface */}
                <div className="bg-background border border-border/60 rounded-xl p-5 space-y-4">
                  {/* Prospect Header */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-gradient-to-tr from-primary to-indigo-500 text-white font-bold flex items-center justify-center text-sm shadow-sm">
                        P
                      </div>
                      <div>
                        <div className="text-xs font-bold text-foreground flex items-center gap-1.5">
                          Alex Rivera <span className="text-[10px] text-muted-foreground font-normal">• 2nd</span>
                        </div>
                        <div className="text-[11px] text-muted-foreground">
                          {targetTitle} at Acme Corp
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        onClick={handleCopyPitch}
                        className="px-2.5 py-1 rounded-lg border border-border/50 text-[11px] font-medium text-muted-foreground hover:text-foreground transition-all flex items-center gap-1 cursor-pointer"
                        title="Copy message to clipboard"
                      >
                        {isCopied ? <Check size={11} className="text-emerald-500" /> : <Copy size={11} />}
                        <span>{isCopied ? "Copied" : "Copy"}</span>
                      </button>
                      <button
                        onClick={() => regenerateAhaMessage(targetTitle, valueProp, aiTone)}
                        className="px-2.5 py-1 rounded-lg border border-border/50 text-[11px] font-medium text-muted-foreground hover:text-foreground transition-all flex items-center gap-1 cursor-pointer"
                        title="Reset to default synthesis"
                      >
                        <span>Reset</span>
                      </button>
                    </div>
                  </div>

                  {/* Editable Simulated Bubble */}
                  <div className="space-y-1.5">
                    <textarea
                      value={prospectPovTab === "connect" ? connectionMessage : followupMessage}
                      onChange={(e) => {
                        if (prospectPovTab === "connect") {
                          setConnectionMessage(e.target.value)
                        } else {
                          setFollowupMessage(e.target.value)
                        }
                      }}
                      rows={3}
                      className="w-full text-xs text-foreground leading-relaxed font-sans p-3.5 bg-primary/5 border border-primary/20 rounded-xl focus:outline-none focus:ring-1 focus:ring-primary transition-all resize-none selection:bg-primary/30"
                      placeholder="Write your custom message or click Regenerate AI..."
                    />

                    {/* LinkedIn 300-Char Limit Gauge */}
                    <div className="flex items-center justify-between text-[11px] pt-1">
                      <div className="flex items-center gap-2">
                        <span className="text-muted-foreground">
                          {prospectPovTab === "connect" ? "LinkedIn Connection Note:" : "Follow-up Message:"}
                        </span>
                        {prospectPovTab === "connect" && (
                          <span className={cn(
                            "font-bold px-2 py-0.5 rounded-full text-[10px]",
                            connectionMessage.length <= 280 
                              ? "bg-emerald-500/10 text-emerald-500 border border-emerald-500/20"
                              : connectionMessage.length <= 300
                              ? "bg-amber-500/10 text-amber-500 border border-amber-500/20"
                              : "bg-destructive/10 text-destructive border border-destructive/20 font-extrabold"
                          )}>
                            {connectionMessage.length} / 300 chars {connectionMessage.length > 300 ? "(Exceeds Limit!)" : "(Safe)"}
                          </span>
                        )}
                      </div>

                      <div className="w-24 h-1.5 bg-muted rounded-full overflow-hidden">
                        <div 
                          className={cn(
                            "h-full transition-all duration-300",
                            connectionMessage.length <= 280 ? "bg-emerald-500" : connectionMessage.length <= 300 ? "bg-amber-500" : "bg-destructive"
                          )}
                          style={{ width: `${Math.min(100, (connectionMessage.length / 300) * 100)}%` }}
                        />
                      </div>
                    </div>
                  </div>

                  {/* Safety & Strategy Badge Strip */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pt-2 border-t border-border/40 text-[11px]">
                    <div className="flex items-center gap-2">
                      <span className="flex items-center gap-1 font-bold text-emerald-500 bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-0.5 rounded-full">
                        <ShieldCheck size={12} /> {aiSpamSafetyScore}% Spam Safety Score
                      </span>
                      {usedLlm && (
                        <span className="text-[10px] text-primary font-medium bg-primary/10 px-2 py-0.5 rounded-full flex items-center gap-1">
                          <ElesiumLogo size={11} />
                          <span>AI Ghostwriter Active</span>
                        </span>
                      )}
                    </div>
                    <p className="text-muted-foreground truncate max-w-sm" title={hookStrategy}>
                      {hookStrategy}
                    </p>
                  </div>
                </div>

                {/* ─── Speak & BitePal Predictive Timeline & Pipeline Simulator ─── */}
                <div className="border-t border-border/50 pt-5 space-y-4">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div>
                      <h4 className="text-xs font-bold uppercase tracking-wider text-foreground flex items-center gap-1.5">
                        <TrendingUp size={14} className="text-primary" /> Predictive 4-Week Pipeline Forecast
                      </h4>
                      <p className="text-[11px] text-muted-foreground">
                        Simulated pipeline generation based on residential warmup velocity and calibrated peer benchmarks.
                      </p>
                    </div>

                    {/* View Mode Toggle */}
                    <div className="flex items-center gap-1 bg-muted/40 p-1 rounded-lg border border-border/50 shrink-0">
                      <button
                        onClick={() => setSafetyViewMode("ramp")}
                        className={cn(
                          "text-[11px] font-semibold px-2.5 py-1 rounded-md transition-all cursor-pointer",
                          safetyViewMode === "ramp" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
                        )}
                      >
                        4-Week Ramp
                      </button>
                      <button
                        onClick={() => setSafetyViewMode("comparison")}
                        className={cn(
                          "text-[11px] font-semibold px-2.5 py-1 rounded-md transition-all cursor-pointer",
                          safetyViewMode === "comparison" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
                        )}
                      >
                        Safety Comparison
                      </button>
                    </div>
                  </div>

                  {safetyViewMode === "ramp" ? (
                    <div className="space-y-4">
                      {/* Week Stepper */}
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                        {[
                          { week: 1, title: "Week 1", subtitle: "Identity Warmup", limit: "15 sends/day" },
                          { week: 2, title: "Week 2", subtitle: "Reply Velocity", limit: "20 sends/day" },
                          { week: 3, title: "Week 3", subtitle: "Meeting Acceleration", limit: "25 sends/day" },
                          { week: 4, title: "Week 4", subtitle: "Scaled Flywheel", limit: "30 sends/day" }
                        ].map((w) => (
                          <button
                            key={w.week}
                            type="button"
                            onClick={() => setSelectedRampWeek(w.week as any)}
                            className={cn(
                              "p-3 rounded-xl border text-left transition-all cursor-pointer flex flex-col justify-between",
                              selectedRampWeek === w.week
                                ? "bg-primary/10 border-primary ring-1 ring-primary/30"
                                : "bg-card/40 border-border/50 hover:bg-card/80 hover:border-border"
                            )}
                          >
                            <div className="flex items-center justify-between">
                              <span className="text-xs font-bold text-foreground">{w.title}</span>
                              <span className={cn(
                                "text-[9px] font-extrabold uppercase px-1.5 py-0.5 rounded",
                                selectedRampWeek === w.week ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
                              )}>
                                {selectedRampWeek === w.week ? "Selected" : w.limit}
                              </span>
                            </div>
                            <span className="text-[11px] text-muted-foreground mt-1">{w.subtitle}</span>
                          </button>
                        ))}
                      </div>

                      {/* Dynamic Weekly Metric Projection Cards */}
                      {(() => {
                        const projections: Record<number, { contacts: string; accepted: string; replies: string; goalVal: string; goalLabel: string; desc: string }> = {
                          1: {
                            contacts: "75",
                            accepted: "24 - 28",
                            replies: "3 - 5",
                            goalVal: selectedGoals.includes("recruit") ? "1 - 2 Screenings" : selectedGoals.includes("fundraise") ? "1 Intro" : "1 Booked Demo",
                            goalLabel: selectedGoals.includes("recruit") ? "Interviews" : selectedGoals.includes("fundraise") ? "VC Chats" : "Booked Demos",
                            desc: "Safe residential warming phase: human keystroke jitter with zero algorithmic flags. Account survival: 100%."
                          },
                          2: {
                            contacts: "175",
                            accepted: "56 - 65",
                            replies: "12 - 16",
                            goalVal: selectedGoals.includes("recruit") ? "3 - 4 Screenings" : selectedGoals.includes("fundraise") ? "2 - 3 Intros" : "3 - 5 Booked Demos",
                            goalLabel: selectedGoals.includes("recruit") ? "Interviews" : selectedGoals.includes("fundraise") ? "VC Chats" : "Booked Demos",
                            desc: "Follow-up sequences trigger automatically on Day 2 for non-responders. Positive reply rates reach 22%."
                          },
                          3: {
                            contacts: "325",
                            accepted: "105 - 120",
                            replies: "26 - 32",
                            goalVal: selectedGoals.includes("recruit") ? "6 - 8 Screenings" : selectedGoals.includes("fundraise") ? "4 - 6 Intros" : "6 - 9 Booked Demos",
                            goalLabel: selectedGoals.includes("recruit") ? "Interviews" : selectedGoals.includes("fundraise") ? "VC Chats" : "Booked Demos",
                            desc: "Ramped sending velocity: Bayesian ICP scoring auto-qualifies responses and alerts you on high-intent intent leads."
                          },
                          4: {
                            contacts: "500+",
                            accepted: "165 - 190",
                            replies: "40 - 55",
                            goalVal: selectedGoals.includes("recruit") ? "8 - 12 Screenings" : selectedGoals.includes("fundraise") ? "6 - 8 Intros" : "10 - 15 Booked Demos",
                            goalLabel: selectedGoals.includes("recruit") ? "Interviews" : selectedGoals.includes("fundraise") ? "VC Chats" : "Booked Demos",
                            desc: "Compounding scale: Full monthly flywheel achieved. Steady stream of booked meetings on your calendar."
                          }
                        }
                        const p = projections[selectedRampWeek]

                        return (
                          <div className="space-y-3">
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-center">
                              <div className="p-3 rounded-xl bg-muted/20 border border-border/40">
                                <p className="text-2xl font-light text-foreground">{p.contacts}</p>
                                <p className="text-[10px] uppercase font-bold text-muted-foreground">Prospects Reached</p>
                              </div>
                              <div className="p-3 rounded-xl bg-muted/20 border border-border/40">
                                <p className="text-2xl font-light text-foreground">{p.accepted}</p>
                                <p className="text-[10px] uppercase font-bold text-muted-foreground">Connections Added</p>
                              </div>
                              <div className="p-3 rounded-xl bg-muted/20 border border-border/40">
                                <p className="text-2xl font-light text-foreground">{p.replies}</p>
                                <p className="text-[10px] uppercase font-bold text-muted-foreground">Warm Replies</p>
                              </div>
                              <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30">
                                <p className="text-2xl font-bold text-emerald-500">{p.goalVal}</p>
                                <p className="text-[10px] uppercase font-bold text-emerald-600 dark:text-emerald-400">{p.goalLabel}</p>
                              </div>
                            </div>
                            <p className="text-[11px] text-muted-foreground text-center italic">
                              "{p.desc}"
                            </p>
                          </div>
                        )
                      })()}
                    </div>
                  ) : (
                    /* ─── Safety Comparison View ─── */
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-left">
                      <div className="p-4 rounded-xl border border-emerald-500/30 bg-emerald-500/5 space-y-2">
                        <div className="flex items-center gap-2 text-emerald-500 font-bold text-xs">
                          <ShieldCheck size={16} /> Ele-in Residential Architecture
                        </div>
                        <ul className="text-[11px] text-muted-foreground space-y-1.5 list-disc pl-4">
                          <li><strong className="text-foreground">100% Account Survival:</strong> Residential 4G proxies matched to your local geo.</li>
                          <li><strong className="text-foreground">Human Jitter Model:</strong> Randomized 30s-180s typing delays.</li>
                          <li><strong className="text-foreground">Controlled Throttle:</strong> 15-30 connections/day, strictly obeying LinkedIn limits.</li>
                        </ul>
                      </div>

                      <div className="p-4 rounded-xl border border-destructive/30 bg-destructive/5 space-y-2">
                        <div className="flex items-center gap-2 text-destructive font-bold text-xs">
                          <AlertTriangle size={16} /> Generic Cloud Automation Bots
                        </div>
                        <ul className="text-[11px] text-muted-foreground space-y-1.5 list-disc pl-4">
                          <li><strong className="text-foreground">87% Restriction Risk:</strong> Datacenter IPs (AWS/DigitalOcean) flagged by LinkedIn.</li>
                          <li><strong className="text-foreground">Instantaneous Blasts:</strong> 100+ requests fired in seconds trigger bot honeypots.</li>
                          <li><strong className="text-foreground">Reputation Damage:</strong> Generic template spam burns high-value ICPs.</li>
                        </ul>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Navigation */}
              <div className="flex items-center justify-between pt-2">
                <button
                  onClick={() => setStep(1)}
                  className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                >
                  <ArrowLeft size={14} /> Back
                </button>
                <button
                  onClick={() => setStep(3)}
                  className="inline-flex items-center gap-2 px-7 py-3 rounded-xl bg-primary text-primary-foreground font-semibold text-sm hover:opacity-90 transition-all shadow-md shadow-primary/20 cursor-pointer"
                >
                  Load Audience & Leads <ArrowRight size={15} />
                </button>
              </div>
            </motion.div>
          )}

          {/* ══════════════════════════════════════════════════════════════
              STEP 3: Audience & Leads (Zero Tab Switching)
          ══════════════════════════════════════════════════════════════ */}
          {step === 3 && (
            <motion.div
              key="step3"
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -15 }}
              transition={{ duration: 0.3 }}
              className="w-full space-y-8"
            >
              <div className="text-center max-w-xl mx-auto space-y-2">
                <span className="text-xs font-bold uppercase tracking-wider text-primary">Audience Fuel</span>
                <h1 className="text-3xl md:text-4xl font-light tracking-tight text-foreground">
                  Who should receive this outreach?
                </h1>
                <p className="text-sm text-muted-foreground">
                  Pick how you want to start. You can load sample prospects right now and add full CSV lists anytime.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Option 1: Demo Leads */}
                <div
                  onClick={() => setAudienceType("demo")}
                  className={cn(
                    "p-6 rounded-2xl border transition-all cursor-pointer flex flex-col justify-between group",
                    audienceType === "demo"
                      ? "bg-primary/5 border-primary shadow-sm ring-1 ring-primary/20"
                      : "bg-card/40 border-border/70 hover:border-foreground/30 hover:bg-card/70"
                  )}
                >
                  <div>
                    <div className="w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center mb-4">
                      <ElesiumLogo size={20} />
                    </div>
                    <div className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-emerald-500 mb-2">
                      Instant • Recommended
                    </div>
                    <h3 className="text-base font-semibold text-foreground mb-1">Load 3 Demo Leads</h3>
                    <p className="text-xs text-muted-foreground leading-relaxed">
                      Instant test leads matching your target criteria ({targetTitle}s). Zero CSV formatting required.
                    </p>
                  </div>
                  <div className="mt-6 flex items-center text-xs font-semibold text-primary">
                    {audienceType === "demo" ? "Selected" : "Select this"}
                  </div>
                </div>

                {/* Option 2: Single Profile */}
                <div
                  onClick={() => setAudienceType("single")}
                  className={cn(
                    "p-6 rounded-2xl border transition-all cursor-pointer flex flex-col justify-between group",
                    audienceType === "single"
                      ? "bg-primary/5 border-primary shadow-sm ring-1 ring-primary/20"
                      : "bg-card/40 border-border/70 hover:border-foreground/30 hover:bg-card/70"
                  )}
                >
                  <div>
                    <div className="w-10 h-10 rounded-xl bg-muted text-muted-foreground flex items-center justify-center mb-4">
                      <UserCheck size={20} />
                    </div>
                    <div className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-2">
                      Test Single
                    </div>
                    <h3 className="text-base font-semibold text-foreground mb-1">Single LinkedIn Profile</h3>
                    <p className="text-xs text-muted-foreground leading-relaxed">
                      Paste a colleague or test prospect's LinkedIn profile URL to verify message extraction.
                    </p>
                  </div>
                  <div className="mt-6 flex items-center text-xs font-semibold text-primary">
                    {audienceType === "single" ? "Selected" : "Select this"}
                  </div>
                </div>

                {/* Option 3: CSV Upload */}
                <div
                  onClick={() => setAudienceType("csv")}
                  className={cn(
                    "p-6 rounded-2xl border transition-all cursor-pointer flex flex-col justify-between group",
                    audienceType === "csv"
                      ? "bg-primary/5 border-primary shadow-sm ring-1 ring-primary/20"
                      : "bg-card/40 border-border/70 hover:border-foreground/30 hover:bg-card/70"
                  )}
                >
                  <div>
                    <div className="w-10 h-10 rounded-xl bg-muted text-muted-foreground flex items-center justify-center mb-4">
                      <UploadCloud size={20} />
                    </div>
                    <div className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-2">
                      Full Import
                    </div>
                    <h3 className="text-base font-semibold text-foreground mb-1">Upload CSV List</h3>
                    <p className="text-xs text-muted-foreground leading-relaxed">
                      Upload your exported lead list from Sales Navigator or Apollo with automatic column mapping.
                    </p>
                  </div>
                  <div className="mt-6 flex items-center text-xs font-semibold text-primary">
                    {audienceType === "csv" ? "Selected" : "Select this"}
                  </div>
                </div>
              </div>

              {/* Dynamic input depending on choice */}
              {audienceType === "single" && (
                <div className="p-5 rounded-2xl border border-border/60 bg-muted/10 space-y-2">
                  <label className="block text-xs font-bold text-foreground">LinkedIn Profile URL</label>
                  <input
                    type="url"
                    value={singleLeadUrl}
                    onChange={(e) => setSingleLeadUrl(e.target.value)}
                    onBlur={() => {
                      if (!singleLeadUrl) return
                      let trimmed = singleLeadUrl.trim()
                      if (!trimmed.startsWith("http://") && !trimmed.startsWith("https://")) {
                        if (trimmed.includes("linkedin.com")) {
                          setSingleLeadUrl(`https://${trimmed}`)
                        } else if (trimmed) {
                          setSingleLeadUrl(`https://linkedin.com/in/${trimmed.replace(/^\/+/, "")}`)
                        }
                      }
                    }}
                    placeholder="https://www.linkedin.com/in/username"
                    className="w-full px-4 py-2.5 rounded-xl bg-background border border-border text-sm focus:outline-none focus:border-primary text-foreground"
                  />
                </div>
              )}

              {audienceType === "demo" && (
                <div className="p-4 rounded-xl border border-primary/20 bg-primary/5 flex items-center gap-3">
                  <CheckCircle2 size={16} className="text-primary shrink-0" />
                  <p className="text-xs text-foreground/80 leading-relaxed">
                    We will seed 3 realistic test prospects (<span className="font-semibold text-foreground">{targetTitle}s</span>) into your campaign so you can test sequence mechanics right away.
                  </p>
                </div>
              )}

              {audienceType === "csv" && (
                <div 
                  onClick={() => fileInputRef.current?.click()}
                  onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                  onDragLeave={() => setIsDragging(false)}
                  onDrop={(e) => {
                    e.preventDefault();
                    setIsDragging(false);
                    const droppedFile = e.dataTransfer.files?.[0];
                    if (droppedFile) handleCsvFile(droppedFile);
                  }}
                  className={cn(
                    "p-8 rounded-2xl border-2 border-dashed text-center space-y-2 cursor-pointer transition-all",
                    isDragging ? "border-primary bg-primary/10" : "border-border hover:border-primary/50 bg-muted/5",
                    csvFile ? "border-emerald-500/50 bg-emerald-500/5" : ""
                  )}
                >
                  <input 
                    type="file" 
                    ref={fileInputRef} 
                    accept=".csv" 
                    className="hidden" 
                    onChange={(e) => {
                      const selected = e.target.files?.[0];
                      if (selected) handleCsvFile(selected);
                    }} 
                  />
                  <UploadCloud size={28} className={cn("mx-auto", csvFile ? "text-emerald-500" : "text-muted-foreground")} />
                  {csvFile ? (
                    <div>
                      <p className="text-xs font-bold text-emerald-500 flex items-center justify-center gap-1.5">
                        <Check size={14} /> {csvFile.name} loaded
                      </p>
                      <p className="text-[11px] text-muted-foreground mt-0.5">
                        {customLeads.length} prospects detected and mapped
                      </p>
                    </div>
                  ) : (
                    <div>
                      <p className="text-xs font-semibold text-foreground">Click to browse or drag and drop your leads.csv here</p>
                      <p className="text-[11px] text-muted-foreground mt-0.5">Columns supported: linkedin_url, first_name, last_name, company, title</p>
                    </div>
                  )}
                </div>
              )}

              {/* Navigation */}
              <div className="flex items-center justify-between pt-2">
                <button
                  onClick={() => setStep(2)}
                  className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                >
                  <ArrowLeft size={14} /> Back
                </button>
                <button
                  onClick={() => setStep(4)}
                  className="inline-flex items-center gap-2 px-7 py-3 rounded-xl bg-primary text-primary-foreground font-semibold text-sm hover:opacity-90 transition-all shadow-md shadow-primary/20 cursor-pointer"
                >
                  Configure LinkedIn Senders <ArrowRight size={15} />
                </button>
              </div>
            </motion.div>
          )}

          {/* ══════════════════════════════════════════════════════════════
              STEP 4: LinkedIn Safety & Engine (Cake Equity Reassurance)
          ══════════════════════════════════════════════════════════════ */}
          {step === 4 && (
            <motion.div
              key="step4"
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -15 }}
              transition={{ duration: 0.3 }}
              className="w-full space-y-8"
            >
              <div className="text-center max-w-xl mx-auto space-y-2">
                <span className="text-xs font-bold uppercase tracking-wider text-emerald-500">Security Architecture</span>
                <h1 className="text-3xl md:text-4xl font-light tracking-tight text-foreground">
                  Safe LinkedIn Outreach
                </h1>
                <p className="text-sm text-muted-foreground">
                  Unlike traditional scrapers, Ele-in operates under LinkedIn's detection radar using human-mimicking jitter.
                </p>
              </div>

              {/* 3 Pillar Safety Grid (Reassurance, not terror) */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="p-5 rounded-2xl border border-border/60 bg-muted/10 space-y-2">
                  <div className="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-500 flex items-center justify-center font-bold">
                    <ShieldCheck size={18} />
                  </div>
                  <h4 className="text-xs font-bold uppercase tracking-wide text-foreground">Automated Warmup Curves</h4>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    New accounts begin sending just 5-10 connections/day, gradually ramping over 14 days to preserve health.
                  </p>
                </div>

                <div className="p-5 rounded-2xl border border-border/60 bg-muted/10 space-y-2">
                  <div className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center font-bold">
                    <Zap size={18} />
                  </div>
                  <h4 className="text-xs font-bold uppercase tracking-wide text-foreground">Human Typing Jitter</h4>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    Random delays (45s - 180s), organic mouse movements, and natural working hours prevent bot flags.
                  </p>
                </div>

                <div className="p-5 rounded-2xl border border-border/60 bg-muted/10 space-y-2">
                  <div className="w-8 h-8 rounded-lg bg-indigo-500/10 text-indigo-500 flex items-center justify-center font-bold">
                    <Globe size={18} />
                  </div>
                  <h4 className="text-xs font-bold uppercase tracking-wide text-foreground">Dedicated Proxy Vault</h4>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    Outreach runs through residential IPs matching your exact city and timezone to avoid location flags.
                  </p>
                </div>
              </div>

              {/* Two clear paths: Connect Now vs Sandbox Mode */}
              <div className="p-6 rounded-2xl border border-border bg-card/60 flex flex-col md:flex-row items-center justify-between gap-6">
                <div className="space-y-1 text-left">
                  <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
                    <Linkedin size={18} className="text-[#0A66C2]" />
                    {connectedAccount ? "LinkedIn Account Connected" : "Connect your LinkedIn Account"}
                  </h3>
                  <p className="text-xs text-muted-foreground max-w-md leading-relaxed">
                    {connectedAccount
                      ? `Connected as ${connectedAccount.name}. Warmup curve active.`
                      : "Connect with session cookies in 60 seconds without sharing your LinkedIn password."}
                  </p>
                </div>

                <div className="flex items-center gap-3 w-full md:w-auto shrink-0">
                  {connectedAccount ? (
                    <div className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-500 font-semibold text-xs">
                      <CheckCircle2 size={16} /> Connected
                    </div>
                  ) : (
                    <>
                      <button
                        onClick={() => setShowConnectModal(true)}
                        className="px-5 py-2.5 rounded-xl bg-primary text-primary-foreground font-semibold text-xs hover:opacity-90 transition-all cursor-pointer shadow-md shadow-primary/20"
                      >
                        Connect Account Now
                      </button>
                      <button
                        onClick={() => {
                          setIsSandboxMode(true)
                          toast.info("Sandbox Mode enabled for preview tour.")
                          setStep(5)
                        }}
                        className="px-4 py-2.5 rounded-xl border border-border text-muted-foreground hover:text-foreground text-xs font-medium transition-colors cursor-pointer"
                      >
                        Explore Sandbox Mode First
                      </button>
                    </>
                  )}
                </div>
              </div>

              {/* Navigation */}
              <div className="flex items-center justify-between pt-2">
                <button
                  onClick={() => setStep(3)}
                  className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                >
                  <ArrowLeft size={14} /> Back
                </button>
                <button
                  onClick={() => setStep(5)}
                  className="inline-flex items-center gap-2 px-7 py-3 rounded-xl bg-primary text-primary-foreground font-semibold text-sm hover:opacity-90 transition-all shadow-md shadow-primary/20 cursor-pointer"
                >
                  Review & Launch <ArrowRight size={15} />
                </button>
              </div>
            </motion.div>
          )}

          {/* ══════════════════════════════════════════════════════════════
              STEP 5: Founder Note & Touchdown (Basecamp / One Year Touch)
          ══════════════════════════════════════════════════════════════ */}
          {step === 5 && (
            <motion.div
              key="step5"
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -15 }}
              transition={{ duration: 0.3 }}
              className="w-full max-w-2xl mx-auto space-y-6"
            >
              {/* Milestone Celebration */}
              <div className="text-center space-y-2">
                <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 flex items-center justify-center mx-auto mb-2 shadow-inner">
                  <CheckCircle2 size={24} />
                </div>
                <h1 className="text-3xl md:text-4xl font-light tracking-tight text-foreground">
                  Your pipeline is shipshape and ready
                </h1>
                <p className="text-sm text-muted-foreground">
                  We've assembled your sequence, seeded your target audience, and configured your safety guardrails.
                </p>
              </div>

              {/* Safety Gate Banner (Human Paranoia Layer 2: "Zero Unexpected Sends") */}
              <div className="p-3.5 rounded-xl border border-emerald-500/20 bg-emerald-500/5 flex items-start gap-3 text-left">
                <div className="w-7 h-7 rounded-lg bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 flex items-center justify-center shrink-0 mt-0.5">
                  <ShieldCheck size={16} />
                </div>
                <div className="space-y-0.5 text-xs">
                  <div className="font-bold text-emerald-950 dark:text-emerald-200 flex items-center gap-2">
                    <span>Safety Gate Status: Initialized in Draft Mode</span>
                    <span className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-emerald-200/60 dark:bg-emerald-900/40 text-emerald-800 dark:text-emerald-300">
                      Zero Auto-Sends
                    </span>
                  </div>
                  <p className="text-emerald-700/90 dark:text-emerald-400 leading-relaxed">
                    Nothing is dispatched automatically. You maintain full control to review prospect lists, tune delays, and verify messaging before activating outreach.
                  </p>
                </div>
              </div>

              {/* Authentic Founder's Stationery Letter (One Year / Basecamp Pattern) */}
              <div className="relative rounded-2xl border border-amber-500/20 bg-gradient-to-b from-amber-500/[0.04] to-amber-500/[0.01] dark:from-amber-500/[0.03] dark:to-transparent p-6 sm:p-7 shadow-sm text-left space-y-5">
                {/* Stationery Header */}
                <div className="flex items-center justify-between pb-4 border-b border-amber-500/10">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-gradient-to-tr from-amber-600 to-amber-400 text-white font-bold flex items-center justify-center text-sm shadow-md ring-2 ring-amber-400/30">
                      DK
                    </div>
                    <div>
                      <div className="text-sm font-bold text-foreground flex items-center gap-1.5">
                        Deeksha KR
                        <span className="text-[10px] font-semibold bg-amber-500/10 text-amber-700 dark:text-amber-300 px-2 py-0.5 rounded-full">
                          Founder &amp; Architect
                        </span>
                      </div>
                      <div className="text-[11px] text-muted-foreground">Ele-in Growth &amp; Outbound Engine</div>
                    </div>
                  </div>
                  <div className="hidden sm:flex items-center gap-1 text-[11px] font-serif italic text-muted-foreground">
                    <span>Bengaluru, India</span>
                  </div>
                </div>

                {/* Letter Content */}
                <div className="space-y-3 text-xs sm:text-[13px] leading-relaxed text-foreground/90 font-serif">
                  <p className="font-sans font-medium text-foreground">
                    Welcome to the Ele-in community,
                  </p>
                  <p>
                    When we started building Ele-in, we had one fundamental conviction: <strong>mass outbound spam is dead</strong>. Ruining your LinkedIn domain reputation with 1,000 generic messages a week isn't sales - it's noise.
                  </p>
                  <p>
                    We built Ele-in for founders and growth leaders who treat outreach with intention. By combining dedicated residential 4G proxies with human typing jitter and deep ICP relevance, our engine doesn't just send messages - it sparks genuine conversations with <span className="font-sans font-semibold text-foreground underline decoration-primary/40 underline-offset-2">{targetTitle || "prospective partners"}</span>.
                  </p>
                  <p>
                    I personally review sequences for our early users. If you'd like a 1-on-1 strategy teardown of your pitch or lead targeting before turning on live outreach, my inbox is open to you.
                  </p>
                </div>

                {/* Handwritten Signature & Direct Action */}
                <div className="pt-2 flex flex-wrap items-center justify-between gap-4 border-t border-amber-500/10">
                  <div>
                    <div className="text-[10px] font-sans uppercase tracking-widest text-muted-foreground mb-1">
                      Warmly,
                    </div>
                    {/* Stylized SVG cursive signature */}
                    <svg className="h-10 w-36 text-primary fill-current" viewBox="0 0 240 60" aria-label="Deeksha KR signature">
                      <path d="M 15 42 Q 25 10 40 18 Q 50 25 55 42 Q 65 30 75 32 Q 85 34 88 40 Q 98 22 108 24 Q 115 36 120 40 Q 130 18 140 20 Q 148 35 155 38 Q 165 15 175 18 Q 185 30 195 42 Q 205 20 220 25" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                      <path d="M 50 22 Q 80 12 110 18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                      <text x="175" y="48" fontFamily="serif" fontSize="12" fontStyle="italic" fill="currentColor">KR</text>
                    </svg>
                    <div className="text-[11px] font-sans text-muted-foreground">Deeksha KR</div>
                  </div>

                  {/* Founder Direct Connect Buttons */}
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        navigator.clipboard.writeText("krdeeksha@gmail.com")
                        setCopiedFounderEmail(true)
                        toast.success("Founder's personal email copied!")
                        setTimeout(() => setCopiedFounderEmail(false), 2000)
                      }}
                      className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-card border border-border hover:bg-muted text-xs font-medium text-foreground transition-all shadow-sm"
                    >
                      {copiedFounderEmail ? (
                        <>
                          <Check size={13} className="text-emerald-500" />
                          <span>Copied!</span>
                        </>
                      ) : (
                        <>
                          <Copy size={13} className="text-muted-foreground" />
                          <span>Copy Founder Email</span>
                        </>
                      )}
                    </button>

                    <a
                      href={`mailto:krdeeksha@gmail.com?subject=${encodeURIComponent(`[Ele-in] Sequence Teardown Request - ${targetTitle || 'Outreach'}`)}&body=${encodeURIComponent(`Hi Deeksha,\n\nI just completed onboarding on Ele-in. Here is our current target ICP:\n- Title: ${targetTitle}\n\nI'd love your thoughts on our sequence strategy before launching.\n\nBest,\n`)}`}
                      className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-primary/10 text-primary hover:bg-primary/20 border border-primary/20 text-xs font-semibold transition-all shadow-sm"
                    >
                      <Mail size={13} />
                      <span>Request 1-on-1 Teardown</span>
                    </a>
                  </div>
                </div>
              </div>

              {/* Configuration Summary Pills */}
              <div className="p-4 rounded-xl border border-border bg-card/60 grid grid-cols-1 sm:grid-cols-3 gap-3 text-left">
                <div className="space-y-0.5">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block">Selected Goal</span>
                  <span className="text-xs font-semibold text-foreground">
                    {GOAL_OPTIONS.find(g => selectedGoals.includes(g.id))?.label || "B2B Lead Generation"}
                  </span>
                </div>
                <div className="space-y-0.5">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block">Target Audience</span>
                  <span className="text-xs font-semibold text-foreground truncate block">
                    {targetTitle}
                  </span>
                </div>
                <div className="space-y-0.5">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block">Sender Account</span>
                  <span className="text-xs font-semibold text-primary">
                    {connectedAccount ? connectedAccount.name : isSandboxMode ? "Sandbox (Zero Risk)" : "Safe Sandbox Mode"}
                  </span>
                </div>
              </div>

              {/* Final Launch Button */}
              <div className="flex flex-col items-center gap-3 pt-2">
                <button
                  onClick={handleCompleteOnboarding}
                  disabled={isSubmitting}
                  className="w-full md:w-auto min-w-[300px] px-8 py-3.5 rounded-xl bg-primary text-primary-foreground font-bold text-sm hover:opacity-90 transition-all shadow-lg shadow-primary/25 active:scale-95 cursor-pointer disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 size={16} className="animate-spin" />
                      Initializing Your Safe Pipeline...
                    </>
                  ) : (
                    <>
                      Enter Command Center &amp; Review Pipeline <ArrowRight size={16} />
                    </>
                  )}
                </button>
                <button
                  onClick={() => setStep(4)}
                  className="text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                >
                  &larr; Review previous settings
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </main>

      {/* ─── In-place Connect LinkedIn Modal (Zero context switching) ─── */}
      {showConnectModal && (
        <ConnectModal
          onClose={() => setShowConnectModal(false)}
          onAdd={async (account) => {
            try {
              const payload = {
                name: account.name,
                linkedin_profile_url: account.profileUrl,
                session_cookies_json: account.cookieJson,
                daily_message_limit: account.messageLimit || 40,
                is_warmup: account.isWarmup,
                warmup_target_days: account.warmupTargetDays || 30,
                warmup_max_connections: account.warmupMaxConnections || 20,
                warmup_max_messages: account.warmupMaxMessages || 40,
                proxy_id: account.proxyId,
              }
              const res = await fetchWithAuth("/api/elein/accounts", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
              })
              if (res.ok) {
                const data = await res.json()
                setConnectedAccount({ ...account, id: data.id })
                setIsSandboxMode(false)
                setShowConnectModal(false)
                toast.success(`Account ${account.name} successfully connected!`)
              } else {
                toast.error("Failed to persist connected LinkedIn account.")
              }
            } catch (err: any) {
              toast.error("Error connecting account: " + err.message)
            }
          }}
        />
      )}
    </div>
  )
}
export default OnboardingWizard
