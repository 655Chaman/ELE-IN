import { useState } from "react"
import { useNavigate, useLocation } from "react-router-dom"
import useSWR from "swr"
import { motion, AnimatePresence } from "motion/react"
import { 
  CheckCircle2, Circle, ChevronDown, ChevronUp, 
  Sparkles, X, ArrowRight, Shield, BrainCircuit, 
  Target, Users, Zap, HeartHandshake
} from "lucide-react"
import { fetcher } from "@/lib/apiClient"
import { cn } from "@/lib/utils"

export function OnboardingChecklistWidget() {
  const navigate = useNavigate()
  const location = useLocation()

  // Layer 1: Hide on /onboarding, /login, or setup routes
  const isHiddenRoute = 
    location.pathname.startsWith("/onboarding") || 
    location.pathname.startsWith("/login") ||
    location.pathname.startsWith("/mfa-setup")

  const [isDismissed, setIsDismissed] = useState(() => {
    return localStorage.getItem("elein_checklist_dismissed") === "true"
  })

  const [isCollapsed, setIsCollapsed] = useState(() => {
    return localStorage.getItem("elein_checklist_collapsed") === "true"
  })

  // Fetch real workspace stats
  const { data: dashboardData } = useSWR(
    isHiddenRoute || isDismissed ? null : "/api/elein/dashboard/stats",
    fetcher,
    { revalidateOnFocus: true }
  )

  const summary = dashboardData?.summary || {}
  const connectedAccounts = Number(summary?.connected_accounts || 0)
  const totalLeads = Number(summary?.total_leads || 0)
  const campaigns = dashboardData?.campaigns || []
  const hasCampaign = campaigns.length > 0
  const hasActiveCampaign = campaigns.some((c: any) => c.status === "ACTIVE")

  // Check knowledge assets
  const { data: assetsData } = useSWR(
    isHiddenRoute || isDismissed ? null : "/api/assets",
    fetcher
  )
  const hasKnowledge = Array.isArray(assetsData) && assetsData.length > 0

  // 6 Mural-Pattern Milestones
  const steps = [
    {
      id: "icp",
      title: "Define ICP & Value Prop",
      desc: "Configure target roles and core pitch",
      completed: true, // Completed in wizard or default
      action: () => navigate("/elein/knowledge"),
      actionLabel: "View ICP",
      icon: Target
    },
    {
      id: "account",
      title: "Connect LinkedIn Account",
      desc: "Link residential sender or sandbox proxy",
      completed: connectedAccounts > 0,
      action: () => navigate("/elein/accounts"),
      actionLabel: "Connect Account",
      icon: Shield
    },
    {
      id: "knowledge",
      title: "Train AI on Your Product",
      desc: "Scrape company URL or upload PDF deck",
      completed: hasKnowledge,
      action: () => navigate("/elein/knowledge"),
      actionLabel: "Add Asset",
      icon: BrainCircuit
    },
    {
      id: "leads",
      title: "Import Target Prospects",
      desc: "Add CSV lead list or single profile URL",
      completed: totalLeads > 0,
      action: () => navigate("/elein/leads"),
      actionLabel: "View Leads",
      icon: Users
    },
    {
      id: "campaign",
      title: "Inspect Outreach Sequence",
      desc: "Check delays and safety safeguards",
      completed: hasCampaign,
      action: () => navigate("/elein/campaigns"),
      actionLabel: "Open Campaigns",
      icon: Sparkles
    },
    {
      id: "launch",
      title: "Activate Outreach Engine",
      desc: "Start residential sending queue",
      completed: hasActiveCampaign,
      action: () => navigate("/elein/campaigns"),
      actionLabel: "Activate",
      icon: Zap
    }
  ]

  const completedCount = steps.filter(s => s.completed).length
  const progressPercent = Math.round((completedCount / steps.length) * 100)
  const allComplete = completedCount === steps.length

  const handleToggleCollapse = () => {
    setIsCollapsed(prev => {
      const next = !prev
      localStorage.setItem("elein_checklist_collapsed", String(next))
      return next
    })
  }

  const handleDismiss = () => {
    localStorage.setItem("elein_checklist_dismissed", "true")
    setIsDismissed(true)
  }

  if (isHiddenRoute || isDismissed) return null

  return (
    <div className="fixed bottom-5 right-5 z-40 font-sans pointer-events-auto">
      <AnimatePresence mode="wait">
        {isCollapsed ? (
          /* ─── Collapsed Pill ─── */
          <motion.button
            key="collapsed-pill"
            type="button"
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.9, opacity: 0 }}
            onClick={handleToggleCollapse}
            className="flex items-center gap-3 px-4 py-2.5 bg-card/95 backdrop-blur-md border border-border/80 rounded-full shadow-xl hover:border-primary/50 transition-all group cursor-pointer"
          >
            <div className="w-6 h-6 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center text-primary text-xs font-bold">
              {completedCount}/{steps.length}
            </div>
            <span className="text-xs font-semibold text-foreground group-hover:text-primary transition-colors">
              Onboarding Checklist
            </span>
            <div className="w-16 h-1.5 bg-muted rounded-full overflow-hidden">
              <div 
                className="h-full bg-primary rounded-full transition-all duration-500"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
            <ChevronUp size={14} className="text-muted-foreground group-hover:text-foreground transition-colors" />
          </motion.button>
        ) : (
          /* ─── Expanded Card (Mural Pattern) ─── */
          <motion.div
            key="expanded-card"
            initial={{ y: 20, opacity: 0, scale: 0.96 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            exit={{ y: 20, opacity: 0, scale: 0.96 }}
            transition={{ duration: 0.2 }}
            className="w-80 md:w-96 bg-card/95 backdrop-blur-md border border-border/80 rounded-xl shadow-2xl overflow-hidden flex flex-col"
          >
            {/* Header */}
            <div className="p-4 pb-3 border-b border-border/40 flex items-center justify-between bg-muted/20">
              <div className="flex items-center gap-2.5">
                <div className="w-7 h-7 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center text-primary">
                  <Sparkles size={15} />
                </div>
                <div>
                  <h4 className="text-xs font-bold text-foreground">Launch Checklist</h4>
                  <p className="text-[11px] text-muted-foreground">{completedCount} of {steps.length} milestones complete</p>
                </div>
              </div>

              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={handleToggleCollapse}
                  className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors cursor-pointer"
                  title="Minimize"
                >
                  <ChevronDown size={15} />
                </button>
                <button
                  type="button"
                  onClick={handleDismiss}
                  className="p-1 rounded-md text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors cursor-pointer"
                  title="Dismiss Checklist"
                >
                  <X size={15} />
                </button>
              </div>
            </div>

            {/* Progress Bar */}
            <div className="h-1 bg-muted/60 w-full overflow-hidden">
              <div 
                className="h-full bg-primary transition-all duration-500 ease-out"
                style={{ width: `${progressPercent}%` }}
              />
            </div>

            {/* Checklist Items */}
            <div className="p-3 space-y-1.5 max-h-[320px] overflow-y-auto">
              {steps.map((st) => {
                const Icon = st.icon
                return (
                  <div
                    key={st.id}
                    className={cn(
                      "flex items-start gap-3 p-2.5 rounded-xl border transition-all text-left",
                      st.completed 
                        ? "bg-muted/20 border-transparent text-muted-foreground"
                        : "bg-card border-border/60 hover:border-primary/40 shadow-xs"
                    )}
                  >
                    <div className="mt-0.5 shrink-0">
                      {st.completed ? (
                        <CheckCircle2 size={16} className="text-emerald-500 fill-emerald-500/20" />
                      ) : (
                        <Circle size={16} className="text-muted-foreground/60" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <span className={cn(
                          "text-xs font-semibold leading-tight flex items-center gap-1.5 truncate",
                          st.completed ? "line-through text-muted-foreground" : "text-foreground"
                        )}>
                          <Icon size={12} className={cn("shrink-0", st.completed ? "text-muted-foreground/60" : "text-primary/70")} />
                          {st.title}
                        </span>
                        {!st.completed && (
                          <button
                            type="button"
                            onClick={st.action}
                            className="text-[11px] font-bold text-primary hover:underline flex items-center gap-0.5 shrink-0 cursor-pointer"
                          >
                            {st.actionLabel}
                            <ArrowRight size={10} />
                          </button>
                        )}
                      </div>
                      <p className="text-[10px] text-muted-foreground mt-0.5 truncate">
                        {st.desc}
                      </p>
                    </div>
                  </div>
                )
              })}
            </div>

            {/* Footer */}
            <div className="p-3 bg-muted/30 border-t border-border/40 flex items-center justify-between text-[11px]">
              <a
                href="mailto:krdeeksha@gmail.com?subject=%5BEle-in%5D%20Founder%20Support%20Request"
                className="text-muted-foreground hover:text-primary font-medium flex items-center gap-1.5 cursor-pointer transition-colors"
                title="Email the founder directly for personal onboarding assistance"
              >
                <HeartHandshake size={12} className="text-primary" />
                <span>Ask Founder</span>
              </a>
              <button
                type="button"
                onClick={() => navigate("/onboarding")}
                className="text-primary hover:underline font-medium flex items-center gap-1 cursor-pointer"
              >
                <Sparkles size={11} />
                Restart Full Wizard
              </button>
              {allComplete && (
                <span className="text-emerald-500 font-bold flex items-center gap-1">
                  Setup complete
                </span>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
