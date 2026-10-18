import { useState } from "react"
import { useNavigate } from "react-router-dom";
import { useHRTreeStore } from "@campaigns/eiTreeStore";
import { fetcher } from "@/lib/apiClient"
import { motion } from "motion/react"
import { Link } from "react-router-dom"
import useSWR from "swr"
import { cn } from "@/lib/utils"
import { AnimatedThemeToggler } from "@/components/ui/animated-theme-toggler"
import { useTheme } from "@/components/ThemeProvider"
import { Linkedin } from "@/components/icons/Linkedin"
import { Users, Megaphone, CheckCircle2, ArrowRight, ChevronRight, Zap, Sparkles, ShieldCheck } from "lucide-react"
import { EleInPaywallModal } from "@campaigns/EleInPaywallModal"
import { toast } from "sonner"



interface OnboardingStatus {
  has_account: boolean
  has_leads: boolean
  has_campaign: boolean
  completed: boolean
  account_count: number
  lead_list_count: number
  campaign_count: number
}

function StepCard({
  step, title, description, cta, href, done, locked, delay,
}: {
  step: number; title: string; description: string; cta: string; href: string
  done: boolean; locked: boolean; delay: number
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, delay, ease: [0.16, 1, 0.3, 1] }}
      className={cn(
        "relative p-8 rounded-xl border transition-all duration-300",
        done
          ? "border-border bg-muted/20"
          : locked
          ? "border-border/40 bg-muted/5 opacity-40 pointer-events-none"
          : "border-border bg-background hover:border-foreground/20 hover:shadow-xl hover:-translate-y-1"
      )}
    >
      <div className="flex items-start justify-between mb-6">
        <div className={cn(
          "w-8 h-8 rounded-full border-2 flex items-center justify-center shrink-0 transition-all",
          done ? "border-foreground bg-foreground" : "border-border bg-transparent"
        )}>
          {done
            ? <CheckCircle2 size={14} className="text-background" />
            : <span className="text-[11px] font-bold text-muted-foreground">{step}</span>
          }
        </div>
        {done && (
          <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground">
            Done
          </span>
        )}
      </div>

      <h3 className="text-lg font-light tracking-tight text-foreground mb-2">{title}</h3>
      <p className="text-sm text-muted-foreground leading-relaxed mb-8">{description}</p>

      {!locked && (
        <Link
          to={href}
          onClick={() => {
            if (href === "/elein/campaigns/new") {
              useHRTreeStore.getState().reset();
            }
          }}
          className={cn(
            "inline-flex items-center gap-2 text-xs font-semibold transition-all group",
            done
              ? "text-muted-foreground hover:text-foreground"
              : "text-foreground hover:gap-3"
          )}
        >
          {done ? "Manage" : cta}
          <ChevronRight size={13} className="group-hover:translate-x-0.5 transition-transform" />
        </Link>
      )}
    </motion.div>
  )
}

export function EleInWelcome() {
  const { theme, setTheme } = useTheme();
  const [showPaywallModal, setShowPaywallModal] = useState(false);
  const { data: billingData, mutate: mutateBilling } = useSWR<any>(
    '/api/elein/workspaces/billing',
    fetcher
  );
  const isPro = billingData?.tier === 'PRO' || billingData?.tier === 'ENTERPRISE';

  const { data: status } = useSWR<OnboardingStatus>(
    null,
    fetcher,
    { fallbackData: { has_account: true, has_leads: true, has_campaign: true, completed: true, account_count: 1, lead_list_count: 1, campaign_count: 1 } }
  )

  const hasAccount = status?.has_account ?? false
  const hasLeads = status?.has_leads ?? false
  const hasCampaign = status?.has_campaign ?? false
  const allDone = hasAccount && hasLeads && hasCampaign

  return (
    <div className="min-h-[100dvh] bg-background text-foreground font-sans">

      {/* Top bar */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="flex items-center justify-between px-10 pt-8"
      >
        <div className="text-[11px] font-bold tracking-[0.3em] uppercase text-muted-foreground">
          Ele-in
        </div>
        <div className="flex items-center gap-4">
          {allDone && (
            <Link
              to="/elein"
              className="text-[11px] font-semibold text-muted-foreground hover:text-foreground transition-colors tracking-wide"
            >
              View Dashboard →
            </Link>
          )}
          <AnimatedThemeToggler variant="circle" theme={theme as any} onThemeChange={setTheme} />
        </div>
      </motion.div>

      <div className="max-w-4xl mx-auto px-10 py-14">

        {/* Hero headline */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
          className="mb-16"
        >
          {allDone ? (
            <>
              <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-border bg-muted/30 mb-6">
                <div className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" />
                <span className="text-[10px] font-bold uppercase tracking-[0.25em] text-muted-foreground">Live</span>
              </div>
              <h1 className="text-5xl md:text-7xl font-light tracking-tighter leading-[1.05] mb-5">
                Your outreach<br />is running.
              </h1>
              <p className="text-lg text-muted-foreground max-w-lg leading-relaxed">
                Connections are being sent. Replies are coming in.<br />You'll wake up to conversations.
              </p>
            </>
          ) : (
            <>
              <h1 className="text-5xl md:text-7xl font-light tracking-tighter leading-[1.05] mb-5">
                LinkedIn outreach<br />on autopilot.
              </h1>
              <p className="text-lg text-muted-foreground max-w-lg leading-relaxed">
                3 steps. One tool. Real conversations — while you sleep.
              </p>
            </>
          )}
        </motion.div>

        {/* Three-step checklist */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-16">
          <StepCard
            step={1} title="Connect your LinkedIn"
            description="Paste your LinkedIn session cookie. We handle warmup, rate limiting, and rotation. Your account stays safe."
            cta="Connect LinkedIn account"
            href="/elein/accounts"
            done={hasAccount} locked={false} delay={0.1}
          />
          <StepCard
            step={2} title="Import your leads"
            description="Upload a CSV, paste LinkedIn URLs, or sync from Sales Navigator. We validate and prepare them for outreach."
            cta="Import a lead list"
            href="/elein/leads"
            done={hasLeads} locked={!hasAccount} delay={0.2}
          />
          <StepCard
            step={3} title="Launch a campaign"
            description="Build your sequence, assign a sender, set a schedule. Then let it run. Wake up to replies."
            cta="Start a campaign"
            href="/elein/campaigns/new"
            done={hasCampaign} locked={!hasLeads} delay={0.3}
          />
        </div>

        {/* How it works — only shown before completion */}
        {!allDone && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.4, ease: [0.16, 1, 0.3, 1] }}
            className="border border-border rounded-xl p-8 mb-12 bg-muted/5 shadow-xs"
          >
            <p className="text-[10px] font-bold uppercase tracking-[0.25em] text-muted-foreground mb-8">
              How it works
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
              {[
                {
                  icon: <Linkedin size={18} />,
                  title: "We act as you",
                  body: "Using your LinkedIn session, Ele-in sends connection requests, messages, and follows up — exactly as if you did it manually, but 24/7."
                },
                {
                  icon: <Users size={18} />,
                  title: "We respect LinkedIn's limits",
                  body: "Built-in warmup, rate limiting, and human-like delays keep your account safe. We start slow, build trust, then scale."
                },
                {
                  icon: <Megaphone size={18} />,
                  title: "You close the deals",
                  body: "When a lead replies, it lands in your Inbox with an AI-drafted response ready. You review and send. We handle everything else."
                }
              ].map((item, i) => (
                <div key={i} className="flex flex-col gap-3">
                  <div className="text-muted-foreground">{item.icon}</div>
                  <h4 className="text-sm font-semibold text-foreground">{item.title}</h4>
                  <p className="text-xs text-muted-foreground leading-relaxed">{item.body}</p>
                </div>
              ))}
            </div>
          </motion.div>
        )}

        {/* Post-Onboarding Pay Ramp & Armed Engine Card */}
        {allDone && !isPro && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.35 }}
            className="relative p-8 md:p-10 rounded-xl border border-border bg-card shadow-xs mb-12 overflow-hidden"
          >
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-8 relative z-10">
              <div>
                <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-primary/20 text-primary text-[10px] font-black uppercase tracking-widest mb-3 border border-primary/30">
                  <Sparkles size={12} /> Unlock Full Autopilot
                </div>
                <h2 className="text-2xl md:text-3xl font-bold tracking-tight text-foreground">
                  Scale Beyond Free Tier Limits
                </h2>
                <p className="text-sm text-muted-foreground mt-2 max-w-xl leading-relaxed">
                  Your workspace is currently running on the <strong className="text-foreground">Free Tier</strong> (capped at 1 active campaign & 500 credits). Upgrade to <strong className="text-primary">Growth Tier</strong> to unleash 20 concurrent campaigns, 5,000 credits, and reach up to 5x more prospects automatically.
                </p>
              </div>

              <div className="shrink-0 flex flex-col items-start md:items-end gap-1">
                <div className="text-3xl font-black text-foreground">₹6,499<span className="text-xs text-muted-foreground font-normal">/mo</span></div>
                <span className="text-[11px] font-bold text-success bg-success/10 border border-success/20 px-2.5 py-0.5 rounded-full uppercase tracking-wider">
                  Save 2 Months Yearly
                </span>
              </div>
            </div>

            {/* Feature Pillars Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8 relative z-10 text-xs">
              <div className="p-3.5 rounded-lg bg-background/60 border border-border/50">
                <span className="text-muted-foreground block text-[10px] uppercase font-bold tracking-wider">Active Campaigns</span>
                <span className="text-foreground font-bold text-sm mt-1 block">20 Active <span className="text-[10px] text-muted-foreground font-normal">(vs 1)</span></span>
              </div>
              <div className="p-3.5 rounded-lg bg-background/60 border border-border/50">
                <span className="text-muted-foreground block text-[10px] uppercase font-bold tracking-wider">Monthly Credits</span>
                <span className="text-foreground font-bold text-sm mt-1 block">5,000 Credits <span className="text-[10px] text-muted-foreground font-normal">(vs 500)</span></span>
              </div>
              <div className="p-3.5 rounded-lg bg-background/60 border border-border/50">
                <span className="text-muted-foreground block text-[10px] uppercase font-bold tracking-wider">Sending Accounts</span>
                <span className="text-foreground font-bold text-sm mt-1 block">Up to 5 Accounts <span className="text-[10px] text-muted-foreground font-normal">(vs 1)</span></span>
              </div>
              <div className="p-3.5 rounded-lg bg-background/60 border border-border/50">
                <span className="text-muted-foreground block text-[10px] uppercase font-bold tracking-wider">Enrichment Tools</span>
                <span className="text-emerald-400 font-bold text-sm mt-1 block">Apollo & Apify</span>
              </div>
            </div>

            {/* CTAs */}
            <div className="flex flex-col sm:flex-row items-center gap-4 relative z-10">
              <button
                onClick={() => setShowPaywallModal(true)}
                className="w-full sm:w-auto px-8 py-4 rounded-xl bg-primary text-primary-foreground font-bold hover:bg-primary/90 transition shadow-xl flex items-center justify-center gap-2 group text-sm"
              >
                <Zap size={16} className="fill-current" />
                <span>Unlock Growth Tier Now</span>
                <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
              </button>
              <Link
                to="/elein"
                className="text-xs text-muted-foreground hover:text-foreground transition underline underline-offset-4 py-2"
              >
                Continue with Free Tier to Dashboard →
              </Link>
            </div>
          </motion.div>
        )}

        {/* Growth Tier Active Celebration Card */}
        {allDone && isPro && (
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            className="p-6 rounded-xl border border-primary/20 bg-primary/5 flex items-center justify-between mb-12 shadow-xs"
          >
            <div className="flex items-center gap-3">
              <div className="p-2 bg-primary/10 text-primary rounded-lg">
                <ShieldCheck size={20} />
              </div>
              <div>
                <h3 className="text-sm font-bold text-foreground">Growth Tier Active</h3>
                <p className="text-xs text-muted-foreground">Full autopilot enabled: 20 active campaigns & 5,000 monthly credits available.</p>
              </div>
            </div>
            <Link
              to="/elein"
              className="px-5 py-2.5 rounded-xl bg-foreground text-background text-xs font-bold hover:opacity-90 transition shrink-0"
            >
              Open Dashboard →
            </Link>
          </motion.div>
        )}

        {/* Live stats when all done */}
        {allDone && (
          <>
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.4 }}
              className="grid grid-cols-3 gap-5 mb-8"
            >
              {[
                { label: "Accounts", value: status?.account_count ?? 0, href: "/elein/accounts" },
                { label: "Lead Lists", value: status?.lead_list_count ?? 0, href: "/elein/leads" },
                { label: "Campaigns", value: status?.campaign_count ?? 0, href: "/elein/campaigns" },
              ].map(stat => (
                <Link
                  key={stat.label}
                  to={stat.href}
                  className="p-6 rounded-xl border border-border bg-card hover:bg-muted/30 transition-colors shadow-xs group"
                >
                  <p className="text-4xl font-light tracking-tighter text-foreground tabular-nums mb-1">
                    {stat.value}
                  </p>
                  <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground group-hover:text-foreground transition-colors">
                    {stat.label}
                  </p>
                </Link>
              ))}
            </motion.div>

            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.5, delay: 0.5 }}
              className="flex items-center gap-4 mb-16"
            >
              <Link
                to="/elein"
                className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-foreground text-background text-xs font-bold hover:opacity-80 transition-opacity"
              >
                View Dashboard <ArrowRight size={13} />
              </Link>
              <Link
                to="/elein/campaigns"
                className="inline-flex items-center gap-2 px-5 py-3 rounded-xl border border-border text-xs font-semibold text-foreground hover:bg-muted/30 transition-colors"
              >
                View Campaigns <ChevronRight size={13} />
              </Link>
              <Link
                to="/inbox"
                className="inline-flex items-center gap-2 px-5 py-3 rounded-xl border border-border text-xs font-semibold text-foreground hover:bg-muted/30 transition-colors"
              >
                Open Inbox <ChevronRight size={13} />
              </Link>
            </motion.div>
          </>
        )}

        {/* Founder CTA — always visible */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.7 }}
          className="border-t border-border pt-8"
        >
          <p className="text-[11px] text-muted-foreground">
            Questions? I read every email personally.{" "}
            <a
              href="mailto:krdeeksha@gmail.com"
              className="text-foreground underline underline-offset-2 hover:no-underline transition-all"
            >
              krdeeksha@gmail.com
            </a>
          </p>
        </motion.div>

        {/* High-Converting In-Situ Paywall Modal */}
        <EleInPaywallModal
          isOpen={showPaywallModal}
          onClose={() => setShowPaywallModal(false)}
          campaignName="Your Outbound Engine"
          onSuccess={() => {
            toast.success("Account upgraded to Growth Tier! Welcome to full autopilot.");
            mutateBilling();
          }}
        />

      </div>
    </div>
  )
}
