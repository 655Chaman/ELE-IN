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
import { Users, Megaphone, CheckCircle2, ArrowRight, ChevronRight } from "lucide-react"



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
        "relative p-8 rounded-2xl border transition-all duration-300",
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
                <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
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
            className="border border-border rounded-2xl p-8 mb-12 bg-muted/5"
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
                  className="p-6 rounded-2xl border border-border bg-background hover:bg-muted/30 hover:-translate-y-0.5 transition-all group"
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

      </div>
    </div>
  )
}
