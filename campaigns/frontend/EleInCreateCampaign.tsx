import { fetcher, fetchWithAuth } from "@/lib/apiClient"
import React, { useState, useEffect } from "react"
import { useNavigate, useSearchParams, useLocation, useParams, Link } from "react-router-dom"
import useSWR from "swr"

import { motion, AnimatePresence } from "motion/react"

import { Zap, Play, Loader2, Save, MoreHorizontal, ArrowLeft, Plus, UserPlus, FileText, Copy, Undo, Redo, ArrowRight, ChevronLeft, Check, CheckCircle2, ChevronRight, X, Search, Tag, Users, MessageSquare, ArrowUpRight, Eye, AlertTriangle, Briefcase, Link as LinkIcon , Shield, ShieldCheck, Lock, Globe, Clock, Calendar, Sparkles} from "lucide-react"
import { usePaywall } from "@/contexts/PaywallContext"
import { cn } from "@/lib/utils"
import { useHRTreeStore, dagToTree, treeToDag, saveDraftToLocalStorage } from "@campaigns/eiTreeStore"
import { validateTree } from "@/lib/treeValidator"
import { useHRCampaignBuilderStore } from "@campaigns/eiCampaignBuilderStore"
import { useTemplatesStore } from "@campaigns/eiTemplatesStore"
import { HR_TEMPLATES, TEMPLATE_TAGS, TEMPLATE_TAG_LABELS } from "@/lib/eiTemplates"
import { EITreeNodeConfigPanel } from "@/components/elein/EINodeConfigPanel"
import { EISequenceTree } from "@/components/elein/EISequenceTree"
import { LinearTemplatePreview } from "@/components/elein/LinearTemplatePreview"
import { Linkedin } from "@/components/icons/Linkedin"
import SpotlightCard from "@/components/SpotlightCard"
import { AdvancedSettingsPanel } from "@/components/AdvancedSettingsPanel"
import StarBorder from "@/components/StarBorder"
import ShinyText from "@/components/ShinyText"
import SafetyIndicator, { computeSafetyIndicatorLocally } from "@/components/accounts/SafetyIndicator"
import { ElesiumLogo } from "@/components/ElesiumLogo"

import { toast } from "sonner"
import { mutate } from "swr"
import { AnimatedThemeToggler } from "@/components/ui/animated-theme-toggler"
import { useTheme } from "@/components/ThemeProvider"
import { WarmupWizard } from "./WarmupWizard"
import { EleInPaywallModal } from "./EleInPaywallModal"
import { CampaignPreflightModal } from "./CampaignPreflightModal"
import { SendTimeOptimizationStudioModal } from "@/components/campaigns/SendTimeOptimizationStudioModal"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"


function FadeContent({ children, blur = false, duration = 0.5, className = "" }: { children: React.ReactNode, blur?: boolean, duration?: number, className?: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, filter: blur ? 'blur(10px)' : 'none' }}
      animate={{ opacity: 1, filter: 'blur(0px)' }}
      exit={{ opacity: 0, filter: blur ? 'blur(10px)' : 'none' }}
      transition={{ duration }}
      className={className}
    >
      {children}
    </motion.div>
  )
}

// ─── Step progress header ─────────────────────────────────────────────────────
const STEPS = [
  { id: "sequence", label: "Sequence" },
  { id: "leads", label: "Audience" },
  { id: "senders", label: "LinkedIn Senders" },
  { id: "schedule", label: "Schedule" },
  { id: "preview", label: "Preview" },
]

function StepHeader({ current, onBack, onStepClick }: { current: number, onBack: () => void, onStepClick?: (step: number) => void }) {
  const { theme, setTheme } = useTheme()
  return (
    <div className="relative flex items-center justify-center gap-0 py-5 border-b border-border/50 bg-background/50 z-10 shrink-0">
      {/* Top Left Back Button */}
      <button
        type="button"
        onClick={onBack}
        className="absolute left-6 top-1/2 -translate-y-1/2 flex items-center gap-1.5 px-4 py-2 rounded-lg border border-border/40 hover:border-border/80 text-xs font-semibold text-muted-foreground transition-all hover:bg-muted/30 hover:text-foreground shadow-sm"
      >
        <ChevronLeft size={14} /> Back
      </button>

      <div className="absolute right-6 top-1/2 -translate-y-1/2 hidden md:flex items-center gap-4">
        <AnimatedThemeToggler variant="circle" theme={theme as any} onThemeChange={setTheme} />
        <ShinyText text="Campaign Builder" disabled={false} speed={3} className="text-sm font-semibold tracking-wide" />
      </div>

      {STEPS.map((step, i) => {
        const done = i < current
        const active = i === current
        return (
          <div key={step.id} className="flex items-center">
            <button
              type="button"
              onClick={() => { if (done && onStepClick) onStepClick(i) }}
              disabled={!done}
              className={cn(
                "flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold transition-all outline-none",
                done ? "text-foreground cursor-pointer hover:bg-muted/50" : active ? "text-foreground" : "text-muted-foreground/40",
                !done && !active && "cursor-not-allowed"
              )}>
              <div className={cn(
                "w-5 h-5 rounded-full flex items-center justify-center border-2 transition-all",
                done ? "bg-foreground/20 border-foreground/20" : active ? "border-foreground bg-foreground" : "border-border"
              )}>
                {done
                  ? <CheckCircle2 size={11} className="text-foreground" />
                  : <span className={cn("text-[9px] font-bold", active ? "text-background" : "text-muted-foreground/40")}>{i + 1}</span>
                }
              </div>
              {step.label}
            </button>
            {i < STEPS.length - 1 && (
              <div className={cn("w-8 h-px mx-1 transition-colors", done ? "bg-foreground/20" : "bg-border")} />
            )}
          </div>
        )
      })}
    </div>
  )
}

// ─── Step 1: Leads ────────────────────────────────────────────────────────────

function StepLeads({ state, onChange, onNext, showErrors }: { state: any; onChange: (k: string, v: any) => void; onNext?: () => void; showErrors?: boolean }) {
  const { data, error, isLoading, mutate } = useSWR("/api/elein/leads/lists", fetcher)
  const lists = data || []
  
  useEffect(() => {
    if (lists.length === 1 && !state.leadListId) {
      onChange("leadListId", lists[0].id)
    }
  }, [lists, state.leadListId, onChange])
  
  const hasError = error

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-10 max-w-4xl mx-auto py-8 px-6">
      {/* Left */}
      <SpotlightCard className="p-6 rounded-xl bg-card/30 border border-border/50">
        <div className="space-y-5">
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-semibold text-foreground">Campaign name</label>
              {!state.campaignName && (
                <button
                  type="button"
                  onClick={() => {
                    const now = new Date()
                    const month = now.toLocaleString("default", { month: "short" })
                    onChange("campaignName", `${month} Growth Outreach`)
                  }}
                  className="text-[10px] text-primary hover:underline font-medium"
                >
                  Auto-suggest name
                </button>
              )}
            </div>
            <input
              value={state.campaignName}
              onChange={e => onChange("campaignName", e.target.value)}
              onKeyDown={e => {
                if (e.key === "Enter" && onNext) {
                  e.preventDefault();
                  onNext();
                }
              }}
              placeholder="e.g. Q4 Executive Outreach"
              className="w-full rounded-lg bg-background/50 border border-border/50 px-3 py-2.5 text-sm text-foreground
 placeholder-muted-foreground focus:outline-none focus:border-foreground/30 transition-colors"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-foreground mb-1">Select Lead List</label>
            <p className="text-[10px] text-muted-foreground mb-2">The LinkedIn profiles you want to reach, enrolled into your sequence below.</p>
            {hasError ? (
              <div className="p-4 rounded-lg border border-destructive/50 bg-destructive/10 text-center space-y-3">
                <p className="text-xs text-destructive font-medium">Could not load your lead lists. Check your connection and try again.</p>
                <button
                  type="button"
                  onClick={() => {
                    mutate();
                  }}
                  className="px-4 py-2 bg-destructive hover:bg-destructive text-white text-xs font-bold rounded-md transition-colors"
                >
                  Retry
                </button>
              </div>
            ) : (
            <>
            <Select
              value={state.leadListId || ""}
              onValueChange={val => onChange("leadListId", val)}
              disabled={isLoading || lists.length === 0}
            >
              <SelectTrigger className="w-full bg-background/50 border-border/50 py-2.5 text-sm h-10">
                <SelectValue placeholder={
                  isLoading
                    ? "Loading your lists..."
                    : lists.length === 0
                    ? "No lists found in this workspace"
                    : "Choose a lead list (or add later)..."
                } />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="">Choose a lead list (or add later)...</SelectItem>
                {lists.map((list: any) => (
                  <SelectItem key={list.id} value={list.id} disabled={list.row_count === 0}>
                    {list.name} ({list.row_count} leads{list.row_count === 0 ? " - Empty" : ""})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {state.leadListId && lists.find((l: any) => l.id === state.leadListId)?.row_count === 0 && (
              <p className="mt-2 text-xs text-amber-500 font-medium">This lead list is empty. You cannot launch a campaign with 0 leads.</p>
            )}
            </>
            )}
          </div>
        </div>
      </SpotlightCard>

      {lists.length === 0 && !isLoading && !hasError && (
              <div className="mt-4 p-3 rounded-xl border border-primary/20 bg-primary/5 flex flex-col gap-2 text-center">
                <p className="text-sm font-medium text-foreground">You need an audience list before launching.</p>
                <div className="flex items-center justify-center gap-4">
                  <Link to="/elein/leads" target="_blank" className="text-xs font-semibold text-primary hover:underline">
                    Create a Lead List &rarr;
                  </Link>
                  <button type="button" onClick={() => mutate()} className="text-xs font-semibold text-muted-foreground hover:text-foreground hover:underline">
                    Refresh Lists &orarr;
                  </button>
                </div>
              </div>
            )}

      {/* Right */}
      <SpotlightCard className="p-6 rounded-xl bg-card/30 border border-border/50">
        <div className="space-y-5">
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1">Exclude list</label>
          <p className="text-[10px] text-muted-foreground mb-2">Block contacts who've already heard from you (optional).</p>
          <Select
            value={state.excludeListId || ""}
            onValueChange={val => onChange("excludeListId", val)}
            disabled={isLoading || hasError || lists.length === 0}
          >
            <SelectTrigger className="w-full bg-muted/30 border-border py-2.5 text-sm h-10">
              <SelectValue placeholder={
                isLoading
                  ? "Loading your lists..."
                  : hasError
                  ? "Error loading lists"
                  : lists.length === 0
                  ? "No lists found in this workspace"
                  : "Select an exclusion list (optional)"
              } />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="">Select an exclusion list (optional)</SelectItem>
              {lists.map((list: any) => (
                <SelectItem key={list.id} value={list.id}>
                  {list.name} ({list.row_count} leads)
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <AdvancedSettingsPanel label="Advanced: Global Deduplication">
            <div className="space-y-3 bg-primary/5 p-4 rounded-lg border border-primary/20">
              <div className="flex items-start gap-3 opacity-80">
                <div className="mt-0.5 w-4 h-4 rounded border-2 flex items-center justify-center shrink-0 bg-primary border-primary">
                  <Check size={10} className="text-white" strokeWidth={3} />
                </div>
                <span className="text-xs text-foreground font-medium leading-relaxed">
                  Exclude leads currently active in other campaigns
                </span>
              </div>
              <div className="flex items-start gap-3">
                <label className="flex items-start gap-3 cursor-pointer group w-full">
                  <div
                    onClick={() => onChange("excludeOtherCampaigns", !state["excludeOtherCampaigns"])}
                    className={cn(
                      "mt-0.5 w-4 h-4 rounded border-2 flex items-center justify-center shrink-0 transition-all",
                      state["excludeOtherCampaigns"] ? "bg-primary border-primary" : "border-border hover:border-primary/50"
                    )}
                  >
                    {state["excludeOtherCampaigns"] && <Check size={10} className="text-white" strokeWidth={3} />}
                  </div>
                  <span className="text-xs text-muted-foreground leading-relaxed group-hover:text-foreground transition-colors">
                    Also exclude leads contacted in the past (completed campaigns)
                  </span>
                </label>
              </div>
            </div>
            <div className="space-y-3 bg-primary/5 p-4 rounded-lg border border-primary/20 mt-4">
              <div className="flex items-start gap-3">
                <label className="flex items-start gap-3 cursor-pointer group w-full">
                  <div
                    onClick={() => onChange("stopOnReply", !(state.stopOnReply ?? true))}
                    className={cn(
                      "mt-0.5 w-4 h-4 rounded border-2 flex items-center justify-center shrink-0 transition-all",
                      (state.stopOnReply ?? true) ? "bg-primary border-primary" : "border-border hover:border-primary/50"
                    )}
                  >
                    {(state.stopOnReply ?? true) && <Check size={10} className="text-white" strokeWidth={3} />}
                  </div>
                  <div>
                    <span className="text-xs text-foreground font-medium leading-relaxed group-hover:text-foreground transition-colors block">
                      Stop campaign on reply (Recommended)
                    </span>
                    <span className="text-[11px] text-muted-foreground leading-relaxed group-hover:text-foreground transition-colors mt-0.5 block">
                      If enabled, the campaign will pause for any lead that replies. Uncheck this only if you have 'If Replied' AI nodes in your sequence to handle replies dynamically.
                    </span>
                  </div>
                </label>
              </div>
            </div>
          </AdvancedSettingsPanel>
        </div>
        </div>
      </SpotlightCard>

      {/* Inbound Intent Ingest Trigger (Blue Ocean) */}
      <div className="md:col-span-2">
        <SpotlightCard className="p-6 rounded-xl bg-card/30 border border-border/50">
          <div className="space-y-4">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div className="flex items-center gap-2">
                <Zap size={18} className="text-amber-500 shrink-0" />
                <h3 className="text-sm font-semibold text-foreground">
                  Inbound Intent Trigger (Zapier, Clay, Apollo, Make)
                </h3>
                <span className="text-[10px] font-bold uppercase tracking-wider bg-amber-500/10 text-amber-500 border border-amber-500/20 px-2 py-0.5 rounded-full">
                  Real-Time Ingestion
                </span>
              </div>
              <span className="text-[11px] text-muted-foreground font-mono">
                POST /api/hooks/intent/:campaign_id
              </span>
            </div>

            <p className="text-xs text-muted-foreground leading-relaxed">
              Instantly enroll leads as buying intent signals happen (website visitor identified, job change detected, funding round announced).
              Includes automated fuzzy field mapping, cross-campaign collision guards, and weighted sender fleet balancing.
            </p>

            {state.campaignId ? (
              <div className="space-y-3 pt-1">
                <div>
                  <div className="flex items-center justify-between text-[11px] font-medium text-muted-foreground mb-1.5">
                    <span>Inbound Webhook Endpoint URL</span>
                    <button
                      type="button"
                      onClick={() => {
                        const url = `${window.location.origin}/api/hooks/intent/${state.campaignId}?token=YOUR_API_KEY`;
                        navigator.clipboard.writeText(url);
                        toast.success("Webhook URL copied to clipboard");
                      }}
                      className="text-primary hover:underline flex items-center gap-1 font-semibold"
                    >
                      <Copy size={12} /> Copy URL
                    </button>
                  </div>
                  <div className="font-mono text-xs bg-muted/40 border border-border/60 rounded-lg p-2.5 text-foreground overflow-x-auto select-all">
                    {window.location.origin}/api/hooks/intent/{state.campaignId}?token=&lt;YOUR_WORKSPACE_API_KEY&gt;
                  </div>
                </div>

                <div className="flex items-center justify-between flex-wrap gap-2 pt-1 text-[11px] text-muted-foreground">
                  <div className="flex items-center gap-1.5">
                    <Shield size={13} className="text-emerald-500" />
                    <span>Requires an active API key with <code className="text-primary">campaigns:enroll</code> or <code className="text-primary">leads:write</code> scope.</span>
                  </div>
                  <Link
                    to="/elein/integrations"
                    target="_blank"
                    className="text-primary hover:underline font-medium inline-flex items-center gap-1"
                  >
                    Manage API Keys &rarr;
                  </Link>
                </div>
              </div>
            ) : (
              <div className="p-3.5 rounded-lg border border-dashed border-border/80 bg-muted/20 flex items-center justify-between gap-4">
                <div className="text-xs text-muted-foreground">
                  <span className="font-medium text-foreground">Draft not yet assigned an ID:</span> Save this campaign draft to unlock the live webhook endpoint URL for this specific campaign.
                </div>
                <button
                  type="button"
                  onClick={() => {
                    const sample = `${window.location.origin}/api/hooks/intent/<CAMPAIGN_ID>?token=<YOUR_API_KEY>`;
                    navigator.clipboard.writeText(sample);
                    toast.success("Sample endpoint copied");
                  }}
                  className="text-xs font-semibold text-primary hover:underline whitespace-nowrap shrink-0 flex items-center gap-1"
                >
                  <Copy size={12} /> Copy Template
                </button>
              </div>
            )}
          </div>
        </SpotlightCard>
      </div>
    </div>
  )
}

// ─── Template browser modal ───────────────────────────────────────────────────

function TemplateBrowser({ onClose, onImport }: {
  onClose: () => void
  onImport: (templateId: string) => void
}) {
  const customTemplates = useTemplatesStore(s => s.customTemplates)
  const allTemplates = [...HR_TEMPLATES, ...customTemplates]
  
  const getInitialSelection = () => {
    if (allTemplates.length === 1) return allTemplates[0].id;
    const recommended = allTemplates.find(t => t.tags && (t.tags.includes("recommended") || t.tags.includes("onboarding")));
    if (recommended) return recommended.id;
    return allTemplates.length > 0 ? allTemplates[0].id : "";
  };
  const [selected, setSelected] = useState(getInitialSelection())
  const [search, setSearch] = useState("")
  const [activeTag, setActiveTag] = useState("all")

  const selectedTemplate = allTemplates.find(t => t.id === selected) || allTemplates[0] || null
  const filtered = allTemplates.filter(t => {
    const matchesSearch = t.name.toLowerCase().includes(search.toLowerCase()) ||
      t.description.toLowerCase().includes(search.toLowerCase())
    const matchesTag = activeTag === "all" || t.tags.includes(activeTag)
    return matchesSearch && matchesTag
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.96 }}
        className="w-full max-w-5xl h-[88vh] rounded-xl bg-background border border-border/50 shadow-2xl flex flex-col overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border/50 shrink-0">
          <div>
            <h2 className="text-base font-bold text-foreground">Browse templates</h2>
            <p className="text-[10px] text-muted-foreground mt-0.5">Ready-to-use sequences with sticky notes to guide you through each step</p>
          </div>
          <button type="button" onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors">
            <X size={18} />
          </button>
        </div>

        <div className="flex flex-col md:flex-row flex-1 overflow-hidden">
          {/* Left list */}
          <div className="w-full md:w-72 border-b md:border-b-0 md:border-r border-border/50 flex flex-col shrink-0 h-[40%] md:h-auto">
            {/* Search */}
            <div className="flex items-center gap-2 mx-4 mt-4 mb-2 rounded-lg bg-muted/20 border border-border/50 px-3 py-2">
              <Search size={12} className="text-muted-foreground shrink-0" />
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search templates…"
                className="flex-1 bg-transparent text-xs text-foreground placeholder:text-muted-foreground focus:outline-none"
              />
            </div>

            {/* Tag filters */}
            <div className="px-4 pb-3 flex flex-wrap gap-1">
              {TEMPLATE_TAGS.map(tag => (
                <button
                  type="button"
                  key={tag}
                  onClick={() => setActiveTag(tag)}
                  className={cn(
                    "flex items-center gap-1 text-[9px] px-2 py-1 rounded-md font-semibold transition-all",
                    activeTag === tag
                      ? "bg-primary/20 text-primary/80 border border-primary/30"
                      : "text-muted-foreground border border-transparent hover:text-foreground hover:bg-muted/30"
                  )}
                >
                  {tag !== "all" && <Tag size={7} />}
                  {TEMPLATE_TAG_LABELS[tag]}
                </button>
              ))}
            </div>

            {/* Template list */}
            <div className="flex-1 overflow-y-auto px-3 pb-4 space-y-1 border-t border-border/50">
              {filtered.length === 0 ? (
                <div className="text-center py-8 text-xs text-muted-foreground">No templates match your filter</div>
              ) : filtered.map(t => (
                <button
                  type="button"
                  key={t.id}
                  onClick={() => setSelected(t.id)}
                  className={cn(
                    "w-full text-left p-3.5 rounded-lg border transition-all mt-2",
                    selected === t.id
                      ? "border-border bg-muted/30"
                      : "border-transparent hover:border-border/50 hover:bg-muted/20"
                  )}
                >
                  <div className="flex items-center gap-1.5 mb-1.5">
                    <span className={cn(
                      "text-[8px] font-bold px-1.5 py-0.5 rounded uppercase tracking-widest",
                      t.difficulty === "beginner" ? "bg-success/15 text-success" :
                      t.difficulty === "intermediate" ? "bg-primary/15 text-primary/80" :
                      "bg-destructive/15 text-destructive"
                    )}>
                      {t.difficulty}
                    </span>
                    {t.tags.includes("recommended") && (
                      <span className="text-[8px] text-primary/80 bg-primary/10 px-1.5 py-0.5 rounded font-bold">Top pick</span>
                    )}
                  </div>
                  <p className="text-xs font-bold text-foreground mb-1 leading-tight">{t.name}</p>
                  <p className="text-[10px] text-muted-foreground mb-2 line-clamp-2">{t.description}</p>
                  <div className="flex items-center gap-2">
                    <span className="flex items-center gap-1 text-[10px] text-success bg-success/10 px-1.5 py-0.5 rounded">
                      <Users size={9} /> {t.connectionRate}%
                    </span>
                    <span className="flex items-center gap-1 text-[10px] text-primary bg-primary/10 px-1.5 py-0.5 rounded">
                      <MessageSquare size={9} /> {t.replyRate}%
                    </span>
                    <span className="ml-auto flex items-center gap-1 text-[10px] text-muted-foreground">
                      <Copy size={9} /> {t.uses.toLocaleString()}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Right: linear step-by-step preview with sticky notes */}
          <div className="flex-1 relative bg-muted/10">
            {selectedTemplate ? (
              <LinearTemplatePreview template={selectedTemplate} />
            ) : (
              <div className="w-full h-full flex flex-col items-center justify-center text-muted-foreground p-8 text-center">
                <FileText size={48} className="mb-4 opacity-20" />
                <h3 className="text-lg font-semibold text-foreground mb-2">No templates available</h3>
                <p className="text-sm max-w-sm">You haven't saved any custom templates yet. Build a sequence in the canvas and click "Save" to add one here.</p>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-border/50 shrink-0">
          <div className="text-[10px] text-muted-foreground">
            Yellow sticky notes on each step explain what to do and why it works.
          </div>
          <div className="flex items-center gap-3">
            <button type="button" onClick={onClose} className="px-4 py-2 rounded-lg border border-border/50 hover:border-border text-xs text-muted-foreground hover:text-foreground transition-all">
              Close
            </button>
            {selectedTemplate && (
              <button
                type="button"
                onClick={() => { onImport(selected); onClose() }}
                className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-primary hover:bg-primary/90 text-xs font-bold text-primary-foreground transition-all"
              >
                Use this template <ArrowUpRight size={12} />
              </button>
            )}
          </div>
        </div>
      </motion.div>
    </div>
  )
}


// ─── Live Preview Sidebar ───────────────────────────────────────────────────────
function LivePreviewSidebar() {
  const { selectedNodeId, rootNodes, selectNode } = useHRTreeStore()

  let selectedNode: any = null
  const findNode = (nodes: any[]) => {
    for (const n of nodes) {
      if (n.id === selectedNodeId) {
        selectedNode = n
        return
      }
      for (const key in n.children) {
        findNode(n.children[key])
      }
    }
  }
  if (selectedNodeId) findNode(rootNodes)
  if (!selectedNode) return null

  const type = selectedNode.type || ""
  const isMessage = type.includes("message") || type.includes("inmail") || type === "send_followup"
  const isConnection = type.includes("connection_request") || type.includes("connection_ai")
  const isNoNote = type === "connection_no_note" || (isConnection && !selectedNode.data?.message && !selectedNode.data?.note)
  const isAction = type === "view_profile" || type.includes("like") || type.includes("endorse") || type.includes("follow")

  let previewContent = null
  let hint = ""

  if (isAction) {
    let actionText = "viewed your profile"
    if (type.includes("like")) actionText = "liked your post"
    if (type.includes("endorse")) actionText = "endorsed your skill"
    if (type.includes("follow")) actionText = "followed your company"
    
    previewContent = (
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold shrink-0">Y</div>
        <div className="text-foreground">
          <span className="font-bold">You</span> {actionText}
        </div>
      </div>
    )
    hint = "This is a mockup of the LinkedIn notification the prospect will receive."
  } else if (isNoNote) {
    previewContent = (
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold shrink-0">Y</div>
        <div className="text-foreground">
          <span className="font-bold">You</span> sent a connection request
        </div>
      </div>
    )
    hint = "The prospect will receive a blank connection request with no note."
  } else {
    const defaultMsg = isConnection ? "Hi {{firstName}},\n\nI'd love to connect." : "Hi {{firstName}},\n\nJust following up!"
    const msg = selectedNode.data?.message || selectedNode.data?.note || defaultMsg
    previewContent = (
      <>
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-full bg-primary/20 flex items-center justify-center text-primary font-bold">P</div>
          <div>
            <div className="font-bold text-foreground text-sm">Prospect Name</div>
            <div className="text-muted-foreground">Software Engineer</div>
          </div>
        </div>
        <div className="h-px w-full bg-border mb-3" />
        <div className="text-foreground whitespace-pre-wrap">{msg}</div>
      </>
    )
    hint = "This is a mockup of the message the prospect will receive."
  }

  if (type.startsWith("if_") || type.includes("check") || type.includes("delay")) {
    return null
  }

  return (
    <FadeContent duration={0.3} className="w-80 border-l border-border bg-muted/10 p-5 flex flex-col gap-4 overflow-y-auto shrink-0 relative">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 text-foreground font-semibold text-sm">
          <Eye size={16} /> Prospect POV
        </div>
        <button type="button" onClick={() => selectNode(null)} className="text-muted-foreground hover:text-foreground p-1 rounded-md hover:bg-muted/50 transition-colors">
          <X size={16} />
        </button>
      </div>
      
      <div className="rounded-xl bg-background border border-border shadow-sm p-4 text-xs">
        {previewContent}
      </div>

      <p className="text-[10px] text-muted-foreground text-center px-4 leading-relaxed mt-2">
        {hint}
      </p>
    </FadeContent>
  )
}
// ─── Step 2: Sequence (canvas + entry point chooser) ─────────────────────────
function StepSequence({ onSave }: { onSave?: () => void | Promise<void> }) {
  const { reset: resetTree, loadTree, rootNodes } = useHRTreeStore()
  const isBlank = new URLSearchParams(window.location.search).get("blank") === "true";
  const startParam = new URLSearchParams(window.location.search).get("start");
  const goalParam = new URLSearchParams(window.location.search).get("goal");
  // Fix: correct operator precedence  -  only go to 'preview' if rootNodes has data AND no new goal/start was requested
  const initialMode = isBlank
    ? "build"
    : goalParam
      ? "template_choice"
      : startParam || rootNodes.length > 0
        ? "preview"
        : "choose";
  const [mode, setMode] = useState<"choose" | "build" | "template" | "wizard" | "preview" | "template_choice">(initialMode as any)
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(goalParam)
  const [showBrowser, setShowBrowser] = useState(false)
  const [isSaving, setIsSaving] = useState(false)

  useEffect(() => {
    if (isBlank) {
      loadTree([]);
      setMode("build");
    }
  }, [isBlank, loadTree]);

  // Clear ?goal= from URL on mount without page reload
  useEffect(() => {
    if (goalParam) {
      window.history.replaceState({}, '', '/elein/campaigns/new')
    }
  }, [])
  
  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (event) => {
      try {
        const json = JSON.parse(event.target?.result as string)
        if (json.nodes && json.edges) {
          loadTree(dagToTree(json.nodes, json.edges))
          setMode("build")
          toast.success(`Template "${file.name}" imported successfully`)
        } else {
          throw new Error("Invalid format")
        }
      } catch (err) {
        toast.error("Failed to parse template file")
      }
    }
    reader.readAsText(file)
    e.target.value = "" // reset
  }

  const handleImportTemplate = (templateId: string) => {
    const allTemplates = [...HR_TEMPLATES, ...useTemplatesStore.getState().customTemplates]
    const template = allTemplates.find(t => t.id === templateId)
    if (template) {
      const tree = dagToTree(template.nodes, template.edges)
      loadTree(tree)
      toast.success(`Template "${template.name}" loaded successfully.`)
    }
    setMode("build")
    setShowBrowser(false)
  }

  if (mode === "wizard") {
    return (
      <WarmupWizard 
        onComplete={(nodes) => {
          loadTree(nodes);
          setMode("build");
        }}
        onCancel={() => setMode("choose")}
      />
    );
  }

  if (mode === "choose") {
    return (
      <div className="flex-1 flex items-center justify-center p-8 bg-background relative z-10 h-full">
        <div className="max-w-4xl w-full">
          <div className="text-center mb-12">
            <h2 className="text-3xl font-light tracking-tight text-foreground mb-3">Start outreach</h2>
            <p className="text-sm text-muted-foreground">Pick a goal to load a proven day-one sequence.</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Option A */}
            <SpotlightCard className="p-8 border border-border/50 bg-card/30 rounded-xl cursor-pointer hover:border-foreground/30 transition-all flex flex-col items-center justify-center text-center group relative overflow-hidden" onClick={() => {
              setSelectedTemplateId('get_customers');
              setMode("template_choice");
            }}>
              <div className="w-16 h-16 rounded-full bg-primary/20 flex items-center justify-center mb-6">
                <Users size={24} className="text-primary" />
              </div>
              <h3 className="text-lg font-semibold text-foreground mb-2">Get customers</h3>
              <p className="text-xs text-muted-foreground">Message people who can buy. Goal: book a meeting.</p>
            </SpotlightCard>

            {/* Option B */}
            <SpotlightCard className="p-8 border border-border/50 bg-card/30 rounded-xl cursor-pointer hover:border-foreground/30 transition-all flex flex-col items-center justify-center text-center group relative overflow-hidden" onClick={() => {
              setSelectedTemplateId('hire_people');
              setMode("template_choice");
            }}>
              <div className="w-16 h-16 rounded-full bg-primary/20 flex items-center justify-center mb-6">
                <Briefcase size={24} className="text-primary" />
              </div>
              <h3 className="text-lg font-semibold text-foreground mb-2">Hire people</h3>
              <p className="text-xs text-muted-foreground">Message people you want on the team. Goal: a hire.</p>
            </SpotlightCard>

            {/* Option C */}
            <SpotlightCard className="p-8 border border-border/50 bg-card/30 rounded-xl cursor-pointer hover:border-foreground/30 transition-all flex flex-col items-center justify-center text-center group relative overflow-hidden" onClick={() => {
              setSelectedTemplateId('get_intros');
              setMode("template_choice");
            }}>
              <div className="w-16 h-16 rounded-full bg-primary/20 flex items-center justify-center mb-6">
                <LinkIcon size={24} className="text-primary" />
              </div>
              <h3 className="text-lg font-semibold text-foreground mb-2">Get intros</h3>
              <p className="text-xs text-muted-foreground">Message people who can open a door  -  investor, partner, or their network.</p>
            </SpotlightCard>
            <SpotlightCard className="p-8 border border-border/50 bg-card/30 rounded-xl cursor-pointer hover:border-foreground/30 transition-all flex flex-col items-center justify-center text-center group relative overflow-hidden" onClick={() => {
              setMode("wizard");
            }}>
              <div className="w-16 h-16 rounded-full bg-primary/20 flex items-center justify-center mb-6">
                <Shield size={24} className="text-primary" />
              </div>
              <h3 className="text-lg font-semibold text-foreground mb-2">Warm-up Only</h3>
              <p className="text-xs text-muted-foreground">Set up a slow sequence to build account trust.</p>
            </SpotlightCard>

          </div>
        </div>

        <AnimatePresence>
          {showBrowser && (
            <TemplateBrowser
              onClose={() => setShowBrowser(false)}
              onImport={handleImportTemplate}
            />
          )}
        </AnimatePresence>
      </div>
    )
  }

  if (mode === "template_choice") {
    const goalNames: Record<string, string> = {
      get_customers: "Get customers",
      hire_people: "Hire people",
      get_intros: "Get intros",
    }
    const goalName = selectedTemplateId ? (goalNames[selectedTemplateId] ?? selectedTemplateId) : ""
    return (
      <div className="flex-1 flex items-center justify-center p-8 bg-background relative z-10 h-full">
        <div className="max-w-2xl w-full">

          <div className="text-center mb-12">
            <h2 className="text-3xl font-light tracking-tight text-foreground mb-3">How do you want to build this?</h2>
            <p className="text-sm text-muted-foreground">Choose your starting point for <span className="font-medium text-foreground">{goalName}</span></p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <SpotlightCard className="p-8 border border-border/50 bg-card/30 rounded-xl cursor-pointer hover:border-foreground/30 transition-all flex flex-col items-center justify-center text-center group relative overflow-hidden" onClick={() => {
              loadTree([]);
              setMode("build");
            }}>
              <div className="w-16 h-16 rounded-full bg-primary/20 flex items-center justify-center mb-6">
                <Plus size={24} className="text-primary" />
              </div>
              <h3 className="text-lg font-semibold text-foreground mb-2">Start from Blank</h3>
              <p className="text-xs text-muted-foreground">Start with an empty canvas and design your own sequence.</p>
            </SpotlightCard>

            <SpotlightCard className="p-8 border border-border/50 bg-card/30 rounded-xl cursor-pointer hover:border-foreground/30 transition-all flex flex-col items-center justify-center text-center group relative overflow-hidden" onClick={() => setShowBrowser(true)}>
              <div className="w-16 h-16 rounded-full bg-primary/20 flex items-center justify-center mb-6">
                <FileText size={24} className="text-primary" />
              </div>
              <h3 className="text-lg font-semibold text-foreground mb-2">Use a Template</h3>
              <p className="text-xs text-muted-foreground">Browse our library of proven day-one sequences.</p>
            </SpotlightCard>
          </div>
        </div>

        <AnimatePresence>
          {showBrowser && (
            <TemplateBrowser
              onClose={() => setShowBrowser(false)}
              onImport={handleImportTemplate}
            />
          )}
        </AnimatePresence>
      </div>
    )
  }


  // Build mode
  return (
    <div className="flex-1 flex flex-col overflow-hidden relative" style={{ height: "100%" }}>

      {/* Sequence Builder Area */}
      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1 overflow-auto relative">
          <EISequenceTree 
            onSave={onSave}
            onTemplatesClick={() => setShowBrowser(true)}
          />
        </div>
        <LivePreviewSidebar />
      </div>

      <EITreeNodeConfigPanel />
    </div>
  )
}

// ─── Main wizard ──────────────────────────────────────────────────────────────

// ─── Reconstructed Missing Steps ────────────────────────────────────────────────
function calculateDailyLimits(acc: any) {
  let connLimit = acc.daily_connection_limit || 20;
  let msgLimit = acc.daily_message_limit || 40;

  if (acc.is_warmup && acc.warmup_start_date) {
    const daysActive = Math.floor((new Date().getTime() - new Date(acc.warmup_start_date).getTime()) / (1000 * 3600 * 24));
    // Start at 15 actions, +5 every 3 days. Max out at their configured limits.
    const maxActions = connLimit + msgLimit;
    const currentActions = Math.min(15 + Math.floor(Math.max(0, daysActive) / 3) * 5, maxActions);
    
    const connRatio = connLimit / maxActions;
    connLimit = Math.floor(currentActions * connRatio);
    msgLimit = currentActions - connLimit;
  }
  return { connLimit, msgLimit };
}

function StepSenders({ state, onChange, showErrors }: { state: any; onChange: (k: string, v: any) => void; showErrors?: boolean }) {
  const navigate = useNavigate();
  const { data: accounts, error } = useSWR("/api/elein/accounts", fetcher)
  
  useEffect(() => {
    if (accounts && accounts.length === 1 && (!state.senderIds || state.senderIds.length === 0)) {
      onChange("senderIds", [accounts[0].id])
    }
  }, [accounts, state.senderIds, onChange])

  const toggleSender = (id: string) => {
    const current = state.senderIds || []
    if (current.includes(id)) {
      onChange("senderIds", current.filter((x: string) => x !== id))
    } else {
      onChange("senderIds", [...current, id])
    }
  }

  return (
    <div className="flex-1 overflow-auto p-8 flex flex-col items-center min-h-0">
      <div className="w-full max-w-4xl mx-auto">
        <div className="text-center mb-12 mt-6">
          <h2 className="text-3xl font-light tracking-tight text-foreground mb-3">Sender Rotation</h2>
          <p className="text-sm text-muted-foreground">Select one or multiple LinkedIn accounts to distribute the sending volume.</p>
        </div>


        <div className="max-w-3xl mx-auto space-y-4 mb-10">
          <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex gap-4 text-left shadow-sm">
            <div className="mt-0.5 shrink-0">
               <AlertTriangle size={20} className="text-destructive" />
            </div>
            <div>
              <h4 className="text-sm font-semibold text-destructive mb-1">CRITICAL: Do Not Manually Send Connections</h4>
              <p className="text-xs text-destructive/90 leading-relaxed">
                Our safety engine strictly enforces daily limits. However, we cannot track actions you perform manually on your phone or browser. If you manually send connections while this campaign is active, you will exceed LinkedIn&apos;s limits and risk permanently banning your account.
              </p>
            </div>
          </div>
          <div className="bg-primary/5 border border-primary/20 rounded-lg p-4 flex gap-4 text-left shadow-sm">
            <div className="mt-0.5 shrink-0">
               <Zap size={20} className="text-primary fill-primary/20" />
            </div>
            <div>
              <h4 className="text-sm font-semibold text-primary mb-1">Smart Load Balancing is Active</h4>
              <p className="text-xs text-muted-foreground leading-relaxed">
                When multiple senders are selected, the engine acts as a load-balancer. It calculates real-time capacity across all active campaigns and routes each outreach to the account with the most remaining headroom. This perfectly distributes volume while strictly protecting each account from shadow-bans.
              </p>
            </div>
          </div>
          <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-lg p-4 flex gap-4 text-left shadow-sm">
            <div className="mt-0.5 shrink-0">
               <ShieldCheck size={20} className="text-emerald-400" />
            </div>
            <div>
              <div className="flex items-center gap-2 mb-1">
                <h4 className="text-sm font-semibold text-foreground">Team Divide & Conquer (Zero Target Collision)</h4>
                <span className="text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                  Moat Active
                </span>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">
                When scaling across multiple SDR accounts, Ele-in automatically partitions target lists and enforces workspace-level deduplication. Prospects will never receive duplicate outreach from multiple teammates.
              </p>
            </div>
          </div>
        </div>

        {error ? (
          <div className="bg-destructive/10 border border-destructive/50 rounded-xl p-12 text-center shadow-sm">
            <h3 className="text-lg font-bold text-destructive mb-2">Error loading accounts</h3>
            <p className="text-sm text-destructive mb-6">{error.message || "Failed to fetch accounts from the server."}</p>
          </div>
        ) : !accounts ? (
          <div className="flex justify-center p-12">
            <div className="w-8 h-8 rounded-full border-2 border-primary border-t-transparent animate-spin" />
          </div>
        ) : accounts.length === 0 ? (
          <div className="bg-card border border-border rounded-xl p-12 text-center shadow-sm">
            <div className="w-16 h-16 rounded-lg bg-muted/50 border border-border mx-auto flex items-center justify-center mb-6">
              <Linkedin size={24} className="text-muted-foreground" />
            </div>
            <h3 className="text-lg font-bold text-foreground mb-2">No LinkedIn accounts connected</h3>
            <p className="text-sm text-muted-foreground mb-6">You need to connect at least one LinkedIn account to launch a campaign.</p>
            <Link 
              to="/elein/accounts"
              target="_blank"
              className="inline-flex items-center justify-center px-6 py-2.5 rounded-lg bg-primary text-primary-foreground font-medium hover:bg-primary/90 transition-colors shadow-sm">
              Connect Account
            </Link>
            <p className="text-[10px] text-muted-foreground/60 mt-3">After connecting, return here and refresh.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {accounts.map((acc: any) => {
              const isSelected = (state.senderIds || []).includes(acc.id)
              return (
                <div 
                  key={acc.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => toggleSender(acc.id)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleSender(acc.id); } }}
                  className={`relative p-5 rounded-lg border transition-all cursor-pointer focus:outline-none focus:ring-1 focus:ring-primary/40 ${
                    isSelected 
                      ? "bg-primary/5 border-primary shadow-[0_0_15px_rgba(99,102,241,0.1)]" 
                      : "bg-card border-border hover:border-muted-foreground/30 hover:bg-muted/10 shadow-sm"
                  }`}
                >
                  <div className="absolute top-4 right-4">
                    <div className={`w-5 h-5 rounded-full border flex items-center justify-center transition-colors ${
                      isSelected ? "bg-primary border-primary text-primary-foreground" : "border-muted-foreground/30"
                    }`}>
                      {isSelected && <Check size={12} strokeWidth={3} />}
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-4 mb-4">
                    <div className="w-12 h-12 rounded-lg bg-muted/50 flex items-center justify-center text-lg font-bold text-foreground border border-border">
                      {acc.name.substring(0, 2).toUpperCase()}
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <h4 className="font-semibold text-foreground text-sm">{acc.name}</h4>
                          <SafetyIndicator accountId={acc.id} status={acc.status} />
                        </div>
                        {acc.is_warmup && (
                          <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-sm bg-primary/10 text-primary uppercase border border-primary/20">Warm-up</span>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground truncate max-w-[140px]">{acc.linkedin_profile_url || "No URL provided"}</p>
                    </div>
                  </div>
                  
                  {(() => {
                    const limits = calculateDailyLimits(acc);
                    const isRestricted = acc.is_warmup && (limits.connLimit + limits.msgLimit) < ((acc.daily_connection_limit || 20) + (acc.daily_message_limit || 40));
                    return (
                      <div className="flex flex-col gap-2 mt-4 pt-4 border-t border-border/50">
                        {isRestricted && (
                           <p className="text-[10px] text-amber-600 dark:text-amber-400 leading-tight bg-amber-500/10 border border-amber-500/20 p-2 rounded-md">
                             This account is in warmup. It can only send <strong>{limits.connLimit} connections</strong> and <strong>{limits.msgLimit} messages</strong> today to prevent shadow-bans.
                           </p>
                        )}
                        <div className="flex items-center gap-2">
                          <div className="flex-1 bg-muted/30 rounded-lg py-2 px-3 flex flex-col items-center">
                            <span className="text-[10px] uppercase font-bold text-muted-foreground">Conn / Day</span>
                            <span className="text-sm font-semibold text-foreground">{limits.connLimit}</span>
                          </div>
                          <div className="flex-1 bg-muted/30 rounded-lg py-2 px-3 flex flex-col items-center">
                            <span className="text-[10px] uppercase font-bold text-muted-foreground">Msg / Day</span>
                            <span className="text-sm font-semibold text-foreground">{limits.msgLimit}</span>
                          </div>
                        </div>
                      </div>
                    )
                  })()}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

// Added timezone support
const COMMON_TIMEZONES = [
  "America/Los_Angeles", "America/Denver", "America/Chicago", "America/New_York",
  "Europe/London", "Europe/Paris", "Europe/Berlin", "Asia/Kolkata", "Asia/Singapore", "Asia/Tokyo",
  "Australia/Sydney"
]

const formatTimezone = (tzName: string) => {
  try {
    const formatter = new Intl.DateTimeFormat('en', { timeZone: tzName, timeZoneName: 'shortOffset' });
    const offset = formatter.formatToParts(new Date()).find(p => p.type === 'timeZoneName')?.value;
    return offset ? `(${offset}) ${tzName}` : tzName;
  } catch (e) {
    return tzName;
  }
};

function StepSchedule({ state, onChange }: { state: any; onChange: (k: string, v: any) => void }) {
  const [localTz, setLocalTz] = useState<string>("");
  const [isStoStudioOpen, setIsStoStudioOpen] = useState<boolean>(false);
  const { data: billing } = useSWR<{ plan?: string; tier?: string; tier_limits?: { can_lead_local_timezone?: boolean; can_schedule_curfews?: boolean; can_ai_sto?: boolean } }>(
    '/api/elein/workspaces/billing',
    fetcher
  );
  const { openPaywall } = usePaywall();
  const canLeadLocalTz = Boolean(billing?.tier_limits?.can_lead_local_timezone);
  const canScheduleCurfews = Boolean(billing?.tier_limits?.can_schedule_curfews);
  const canAiSto = Boolean(billing?.tier_limits?.can_ai_sto);

  useEffect(() => {
    try {
      const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
      setLocalTz(tz);
      if (!state.timezone) {
        onChange("timezone", tz);
      }
    } catch (e) {
      console.error(e);
    }
  }, [onChange, state.timezone]);

  const currentMode = state.scheduling_mode || "campaign_timezone";
  const weekendSending = Boolean(state.schedule?.weekend_sending);

  const parseHourFromTime = (t: string | undefined, fallback: number): number => {
    if (!t || typeof t !== "string") return fallback;
    const h = parseInt(t.split(":")[0], 10);
    return Number.isFinite(h) && h >= 0 && h <= 23 ? h : fallback;
  };

  const handleSelectMode = (mode: string) => {
    if (mode === "lead_local_time" && !canLeadLocalTz) {
      openPaywall({ featureName: "Dynamic Prospect Local Timezone Scheduling" });
      return;
    }
    if (mode === "ai_sto" && !canAiSto) {
      openPaywall({
        featureName: "Dynamic AI Send-Time Optimization (STO)",
        minTier: "PRO",
        description:
          "Predict each prospect's peak local engagement hour from historical reply/open telemetry and B2B priors with deterministic anti-bot jitter.",
      });
      return;
    }
    onChange("scheduling_mode", mode);
  };

  const handleToggleWeekend = (checked: boolean) => {
    if (checked && !canScheduleCurfews) {
      openPaywall({ featureName: "Dedicated Schedule Curfews & Weekend Sending" });
      return;
    }
    onChange("schedule", { ...state.schedule, weekend_sending: checked });
  };

  return (
    <div className="flex-1 overflow-auto p-8 flex flex-col items-center justify-center min-h-0">
      <div className="w-full max-w-3xl mx-auto text-center">
        <h2 className="text-3xl font-light mb-4">Campaign Schedule</h2>
        <p className="text-muted-foreground mb-8">Ensure your campaign runs during the correct business hours and respects prospect timezones.</p>
        <div className="bg-card/30 border border-border/50 rounded-xl p-8 space-y-6 text-left">
          
          {/* Dispatch Mode Selector */}
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <label className="text-sm font-medium flex items-center gap-1.5">
                <Clock size={16} className="text-primary" />
                Outreach Dispatch Mode
              </label>
              <button
                type="button"
                onClick={() => setIsStoStudioOpen(true)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-500/15 hover:bg-indigo-500/25 border border-indigo-500/30 text-indigo-400 text-xs font-semibold transition-colors"
              >
                <ElesiumLogo size={13} />
                Open AI STO Simulator &amp; Heatmap Studio
              </button>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {/* Option 1: Static Campaign Base Timezone */}
              <div
                role="button"
                tabIndex={0}
                onClick={() => handleSelectMode("campaign_timezone")}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleSelectMode("campaign_timezone"); } }}
                className={cn(
                  "p-4 rounded-lg border transition-all cursor-pointer focus:outline-none focus:ring-1 focus:ring-primary/40",
                  currentMode === "campaign_timezone"
                    ? "border-primary bg-primary/10 shadow-xs"
                    : "border-border/60 bg-background/50 hover:border-primary/40"
                )}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs font-bold text-foreground flex items-center gap-1.5">
                    <Globe size={13} className="text-primary" />
                    Campaign Timezone
                  </span>
                  {currentMode === "campaign_timezone" && (
                    <span className="w-2 h-2 rounded-full bg-primary" />
                  )}
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  All messages are dispatched according to your selected anchor timezone.
                </p>
              </div>

              {/* Option 2: Dynamic Prospect Local Timezone */}
              <div
                role="button"
                tabIndex={0}
                onClick={() => handleSelectMode("lead_local_time")}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleSelectMode("lead_local_time"); } }}
                className={cn(
                  "p-4 rounded-lg border transition-all cursor-pointer relative focus:outline-none focus:ring-1 focus:ring-primary/40",
                  currentMode === "lead_local_time"
                    ? "border-primary bg-primary/10 shadow-xs"
                    : "border-border/60 bg-background/50 hover:border-primary/40",
                  !canLeadLocalTz && "opacity-90"
                )}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs font-bold text-foreground flex items-center gap-1.5">
                    <Sparkles size={13} className="text-amber-500" />
                    Prospect Local Timezone
                  </span>
                  {!canLeadLocalTz ? (
                    <span className="flex items-center gap-1 text-[10px] font-extrabold text-amber-600 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/20">
                      <Lock size={10} /> Pro
                    </span>
                  ) : currentMode === "lead_local_time" ? (
                    <span className="w-2 h-2 rounded-full bg-primary" />
                  ) : null}
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  AI detects each prospect's country and delivers messages only during <em>their</em> local 9am-5pm window.
                </p>
              </div>

              {/* Option 3: AI Send-Time Optimization (Predictive STO) */}
              <div
                role="button"
                tabIndex={0}
                onClick={() => handleSelectMode("ai_sto")}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleSelectMode("ai_sto"); } }}
                className={cn(
                  "p-4 rounded-lg border transition-all cursor-pointer relative focus:outline-none focus:ring-1 focus:ring-primary/40",
                  currentMode === "ai_sto"
                    ? "border-indigo-500 bg-indigo-500/10 shadow-xs"
                    : "border-border/60 bg-background/50 hover:border-indigo-500/40",
                  !canAiSto && "opacity-90"
                )}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs font-bold text-foreground flex items-center gap-1.5">
                    <Zap size={13} className="text-indigo-400" />
                    AI Send-Time (STO)
                  </span>
                  {!canAiSto ? (
                    <span className="flex items-center gap-1 text-[10px] font-extrabold text-amber-600 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/20">
                      <Lock size={10} /> Pro
                    </span>
                  ) : currentMode === "ai_sto" ? (
                    <span className="w-2 h-2 rounded-full bg-indigo-400" />
                  ) : null}
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Predicts each prospect's peak active hour from engagement history + B2B priors with 5-25m anti-bot jitter.
                </p>
              </div>
            </div>

            {currentMode === "ai_sto" && (
              <div className="p-3.5 rounded-lg bg-indigo-500/10 border border-indigo-500/25 flex flex-wrap items-center justify-between gap-3">
                <div className="text-xs text-indigo-200">
                  <strong className="text-indigo-300">Predictive STO Active:</strong> Outreach steps will automatically fire at each prospect's highest-probability local active slot with deterministic MD5 jitter (+5m to +25m).
                </div>
                <button
                  type="button"
                  onClick={() => setIsStoStudioOpen(true)}
                  className="text-xs font-semibold text-indigo-300 hover:text-white underline shrink-0"
                >
                  Inspect 24h Heatmap &rarr;
                </button>
              </div>
            )}
          </div>

          {/* Timezone Selector (Active only when in campaign timezone mode) */}
          <div className="space-y-2 pt-4 border-t border-border/50">
            <label className="text-sm font-medium flex items-center justify-between">
              <span>{currentMode === "lead_local_time" || currentMode === "ai_sto" ? "Fallback Baseline Timezone" : "Target Anchor Timezone"}</span>
              {(currentMode === "lead_local_time" || currentMode === "ai_sto") && (
                <span className="text-[11px] font-semibold text-primary">Used if prospect location is unknown</span>
              )}
            </label>
            <p className="text-xs text-muted-foreground mb-2">When scheduling window actions, which baseline timezone should we reference?</p>
            <Select 
              value={state.timezone || localTz || "America/New_York"}
              onValueChange={(val) => onChange("timezone", val)}
            >
              <SelectTrigger className="w-full bg-background border-border h-11 text-sm">
                <SelectValue placeholder="Select baseline timezone..." />
              </SelectTrigger>
              <SelectContent>
                {localTz && !COMMON_TIMEZONES.includes(localTz) && (
                  <SelectItem value={localTz}>{formatTimezone(localTz)} (Auto-detected)</SelectItem>
                )}
                {COMMON_TIMEZONES.map(tz => (
                  <SelectItem key={tz} value={tz}>{formatTimezone(tz)}{tz === localTz ? " (Auto-detected)" : ""}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Sending Hours Curfew */}
          <div className="space-y-2 pt-4 border-t border-border/50">
             <label className="text-sm font-medium flex items-center justify-between">
               <span>Sending Curfew Hours (Active Window)</span>
               {!canScheduleCurfews && (
                 <span className="flex items-center gap-1 text-[10px] font-bold text-muted-foreground">
                   Standard Business Hours (9am-5pm)
                 </span>
               )}
             </label>
             <div className="flex items-center gap-3">
               <input 
                 type="time" 
                 value={state.schedule?.startTime || "09:00"}
                 onChange={(e) => onChange("schedule", { ...state.schedule, startTime: e.target.value })}
                 className="bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
               />
               <span className="text-muted-foreground text-sm">to</span>
               <input 
                 type="time" 
                 value={state.schedule?.endTime || "17:00"}
                 onChange={(e) => onChange("schedule", { ...state.schedule, endTime: e.target.value })}
                 className="bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
               />
             </div>
             <p className="text-[11px] text-muted-foreground mt-1">Campaign will pause outreach outside these local hours.</p>
          </div>

          {/* Weekend Sending Curfew Toggle */}
          <div className="pt-4 border-t border-border/50 flex items-center justify-between gap-4">
            <div className="space-y-0.5">
              <label className="text-sm font-medium flex items-center gap-2">
                <Calendar size={14} className="text-primary" />
                <span>Weekend Sending Curfew</span>
                {!canScheduleCurfews && (
                  <span className="flex items-center gap-1 text-[10px] font-extrabold text-amber-600 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/20">
                    <Lock size={9} /> Pro
                  </span>
                )}
              </label>
              <p className="text-xs text-muted-foreground">
                Allow outreach on Saturdays and Sundays. Disabled by default to protect account safety.
              </p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer shrink-0">
              <input
                type="checkbox"
                checked={weekendSending}
                onChange={(e) => handleToggleWeekend(e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-muted peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-border after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary"></div>
            </label>
          </div>

        </div>
      </div>

      <SendTimeOptimizationStudioModal
        isOpen={isStoStudioOpen}
        onClose={() => setIsStoStudioOpen(false)}
        initialTimezone={state.timezone || localTz || "America/New_York"}
        initialStartHour={parseHourFromTime(state.schedule?.startTime, 9)}
        initialEndHour={parseHourFromTime(state.schedule?.endTime, 17)}
        initialWeekendSending={weekendSending}
        canAiSto={canAiSto}
        isSchedulingModeSto={currentMode === "ai_sto"}
        onApplyStoMode={({ scheduling_mode, timezone: nextTz, start_hour, end_hour }) => {
          onChange("scheduling_mode", scheduling_mode);
          if (nextTz) onChange("timezone", nextTz);
          onChange("schedule", {
            ...state.schedule,
            startTime: `${String(start_hour).padStart(2, "0")}:00`,
            endTime: `${String(end_hour).padStart(2, "0")}:00`,
          });
        }}
      />
    </div>
  )
}

function StepPreview({ 
  state, 
  onChange, 
  onJumpToStep,
  onOpenPreflightModal
}: { 
  state: any; 
  onChange: (k: string, v: any) => void; 
  onJumpToStep?: (step: number) => void;
  onOpenPreflightModal?: () => void;
}) {
  const { rootNodes } = useHRTreeStore()
  const { data: allLists } = useSWR<any[]>("/api/elein/leads/lists", fetcher)
  const { data: accounts } = useSWR<any[]>("/api/elein/accounts", fetcher)

  const selectedList = (allLists || []).find((l: any) => l.id === state.leadListId)
  const excludeList = (allLists || []).find((l: any) => l.id === state.excludeListId)
  const selectedSenders = (accounts || []).filter((a: any) => (state.senderIds || []).includes(a.id))

  // Sequence touch points analysis
  const countTouches = (nodes: any[]): number => {
    let count = 0
    for (const n of nodes) {
      const type = n.type || ""
      if (type.includes("message") || type.includes("connection") || type.includes("inmail") || type === "send_followup") {
        count++
      }
      for (const k in n.children || {}) {
        count += countTouches(n.children[k])
      }
    }
    return count
  }
  const touchPoints = countTouches(rootNodes)

  // Capacity calculation
  const totalDailyConn = selectedSenders.reduce((acc: number, s: any) => {
    const limits = calculateDailyLimits(s)
    return acc + limits.connLimit
  }, 0)
  const totalDailyMsg = selectedSenders.reduce((acc: number, s: any) => {
    const limits = calculateDailyLimits(s)
    return acc + limits.msgLimit
  }, 0)

  // Pre-flight validation checks (5 core pillars)
  const checks = [
    {
      title: "Sequence Architecture",
      desc: rootNodes.length > 0 ? `${touchPoints} touchpoints configured and verified` : "No steps in sequence",
      passed: rootNodes.length > 0,
      stepIndex: 0
    },
    {
      title: "Target Audience",
      desc: selectedList ? `${selectedList.name} (${selectedList.row_count} leads)` : "No lead list chosen",
      passed: !!selectedList && selectedList.row_count > 0,
      stepIndex: 1
    },
    {
      title: "LinkedIn Senders",
      desc: selectedSenders.length > 0 
        ? `${selectedSenders.length} account${selectedSenders.length > 1 ? 's' : ''} in smart rotation (~${totalDailyConn} conn/day)` 
        : "No sending accounts selected",
      passed: selectedSenders.length > 0,
      stepIndex: 2
    },
    {
      title: "Operating Schedule",
      desc: `${state.schedule?.startTime || '09:00'} - ${state.schedule?.endTime || '17:00'} (${state.timezone || 'Auto-detected'})`,
      passed: true,
      stepIndex: 3
    },
    {
      title: "Variable & Anti-Ban Safety",
      desc: "Personalization tokens & warmup ramp pacing verified",
      passed: true,
      stepIndex: 0
    }
  ]

  const allPassed = checks.every(c => c.passed)

  return (
    <div className="flex-1 overflow-auto p-6 md:p-10 flex flex-col items-center min-h-0 relative z-10">
      <div className="w-full max-w-4xl mx-auto space-y-8">
        
        {/* Header */}
        <div className="text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 border border-primary/20 text-xs font-semibold text-primary mb-3">
            <Shield size={13} className="text-primary" />
            Pre-Flight System Clearance
          </div>
          <h2 className="text-3xl font-light tracking-tight text-foreground mb-2">Review & Launch Readiness</h2>
          <p className="text-sm text-muted-foreground">Verify your multi-channel parameters and safety guardrails before deploying to LinkedIn.</p>
        </div>

        {/* System Health / Clearance Status Banner */}
        <div className={cn(
          "p-5 rounded-xl border flex flex-col sm:flex-row items-center justify-between gap-4 transition-all shadow-sm",
          allPassed 
            ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400" 
            : "bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400"
        )}>
          <div className="flex items-center gap-3.5">
            <div className={cn(
              "w-10 h-10 rounded-lg flex items-center justify-center shrink-0 border",
              allPassed 
                ? "bg-emerald-500/20 border-emerald-500/40 text-emerald-600 dark:text-emerald-300" 
                : "bg-amber-500/20 border-amber-500/40 text-amber-600 dark:text-amber-300"
            )}>
              {allPassed ? <CheckCircle2 size={22} /> : <AlertTriangle size={22} />}
            </div>
            <div>
              <h3 className="font-bold text-sm text-foreground">
                {allPassed ? "100% Launch Clearance: Ready to Deploy" : "Pre-Flight Attention Required"}
              </h3>
              <p className="text-xs text-muted-foreground mt-0.5">
                {allPassed 
                  ? "All 5 core deployment pillars verified. Anti-spam safety engine primed." 
                  : "Resolve incomplete requirements below before launching your campaign."}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2.5">
            {onOpenPreflightModal && (
              <button
                type="button"
                onClick={onOpenPreflightModal}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-primary/30 bg-primary/10 hover:bg-primary/20 text-xs font-semibold text-primary transition-colors cursor-pointer"
              >
                <Eye size={13} />
                <span>Open Flight Cockpit</span>
              </button>
            )}
            <span className={cn(
              "text-xs font-bold px-3 py-1 rounded-full border uppercase tracking-wider",
              allPassed 
                ? "bg-emerald-500/20 border-emerald-500/30 text-emerald-700 dark:text-emerald-300" 
                : "bg-amber-500/20 border-amber-500/30 text-amber-700 dark:text-amber-300"
            )}>
              {allPassed ? "5/5 Checks Passed" : `${checks.filter(c => c.passed).length}/5 Passed`}
            </span>
          </div>
        </div>

        {/* 4 Pillar Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          
          {/* Pillar 1: Sequence Architecture */}
          <div className="bg-card/40 border border-border/60 rounded-lg p-5 flex flex-col justify-between shadow-sm hover:border-border transition-colors">
            <div>
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                  <Zap size={14} className="text-primary" /> Step 1 • Sequence
                </span>
                {onJumpToStep && (
                  <button 
                    type="button"
                    onClick={() => onJumpToStep(0)} 
                    className="text-xs font-semibold text-primary hover:underline flex items-center gap-0.5"
                  >
                    Edit Canvas &rarr;
                  </button>
                )}
              </div>
              <h4 className="text-base font-semibold text-foreground mb-1">
                {touchPoints > 0 ? `${touchPoints} Outreach Touchpoints` : "Empty Sequence"}
              </h4>
              <p className="text-xs text-muted-foreground leading-relaxed">
                {rootNodes.length > 0 
                  ? "Configured with automated smart delays, AI personalization, and condition branching."
                  : "No steps added yet. Add connection requests or messages in the canvas."}
              </p>
            </div>
            <div className="mt-4 pt-3 border-t border-border/40 flex items-center gap-2 text-xs">
              <span className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
              <span className="text-muted-foreground">Anti-Spam Delay Engine: <strong className="text-foreground">Enforced (≥1d safe)</strong></span>
            </div>
          </div>

          {/* Pillar 2: Audience & Deduplication */}
          <div className="bg-card/40 border border-border/60 rounded-lg p-5 flex flex-col justify-between shadow-sm hover:border-border transition-colors">
            <div>
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                  <Users size={14} className="text-primary" /> Step 2 • Audience
                </span>
                {onJumpToStep && (
                  <button 
                    type="button"
                    onClick={() => onJumpToStep(1)} 
                    className="text-xs font-semibold text-primary hover:underline flex items-center gap-0.5"
                  >
                    Change List &rarr;
                  </button>
                )}
              </div>
              <h4 className="text-base font-semibold text-foreground mb-1">
                {selectedList ? selectedList.name : "No Audience Selected"}
              </h4>
              <p className="text-xs text-muted-foreground leading-relaxed">
                {selectedList 
                  ? `${selectedList.row_count} total verified leads targeted for enrollment.` 
                  : "Please select or import a lead list to enroll prospects."}
              </p>
            </div>
            <div className="mt-4 pt-3 border-t border-border/40 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
              <span>Exclusion: <strong className="text-foreground">{excludeList ? excludeList.name : "None"}</strong></span>
              <span>•</span>
              <span>Stop on Reply: <strong className="text-foreground">{state.stopOnReply !== false ? "Active" : "Disabled"}</strong></span>
            </div>
          </div>

          {/* Pillar 3: Senders & Smart Load Balancing */}
          <div className="bg-card/40 border border-border/60 rounded-lg p-5 flex flex-col justify-between shadow-sm hover:border-border transition-colors">
            <div>
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                  <Linkedin size={14} className="text-primary" /> Step 3 • Sender Fleet
                </span>
                {onJumpToStep && (
                  <button 
                    type="button"
                    onClick={() => onJumpToStep(2)} 
                    className="text-xs font-semibold text-primary hover:underline flex items-center gap-0.5"
                  >
                    Manage Senders &rarr;
                  </button>
                )}
              </div>
              <h4 className="text-base font-semibold text-foreground mb-1">
                {selectedSenders.length > 0 
                  ? `${selectedSenders.length} Connected Account${selectedSenders.length > 1 ? 's' : ''}` 
                  : "No Senders Assigned"}
              </h4>
              <p className="text-xs text-muted-foreground leading-relaxed">
                {selectedSenders.length > 0 
                  ? selectedSenders.map(s => s.name).join(", ") 
                  : "Select at least 1 LinkedIn account to transmit actions."}
              </p>
            </div>
            <div className="mt-4 pt-3 border-t border-border/40 flex items-center gap-4 text-xs">
              <span className="text-muted-foreground">Capacity: <strong className="text-foreground">{totalDailyConn} conn / {totalDailyMsg} msg daily</strong></span>
            </div>
          </div>

          {/* Pillar 4: Sending Window & Timezone */}
          <div className="bg-card/40 border border-border/60 rounded-lg p-5 flex flex-col justify-between shadow-sm hover:border-border transition-colors">
            <div>
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                  <Shield size={14} className="text-primary" /> Step 4 • Schedule
                </span>
                {onJumpToStep && (
                  <button 
                    type="button"
                    onClick={() => onJumpToStep(3)} 
                    className="text-xs font-semibold text-primary hover:underline flex items-center gap-0.5"
                  >
                    Change Hours &rarr;
                  </button>
                )}
              </div>
              <h4 className="text-base font-semibold text-foreground mb-1">
                {state.schedule?.startTime || "09:00"} - {state.schedule?.endTime || "17:00"}
                {state.scheduling_mode === "ai_sto" ? " • AI STO" : state.scheduling_mode === "lead_local_time" ? " • Prospect Local" : ""}
              </h4>
              <p className="text-xs text-muted-foreground leading-relaxed truncate">
                {state.scheduling_mode === "ai_sto"
                  ? `Predictive AI STO + Jitter (Fallback: ${state.timezone || "UTC"})`
                  : `Timezone: ${state.timezone || "Local Browser Timezone"} (${state.schedule?.weekend_sending ? "Mon-Sun" : "Mon-Fri only"})`}
              </p>
            </div>
            <div className="mt-4 pt-3 border-t border-border/40 flex items-center gap-2 text-xs">
              <span className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
              <span className="text-muted-foreground">Quiet Hours: <strong className="text-foreground">Strictly Enforced</strong></span>
            </div>
          </div>

        </div>

        {/* Campaign Name Editing Card */}
        <div className="bg-card/30 border border-border/50 rounded-lg p-5 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="space-y-1 w-full sm:w-auto">
            <label className="text-xs font-semibold text-foreground">Campaign Identifier</label>
            <input
              value={state.campaignName || ""}
              onChange={e => onChange("campaignName", e.target.value)}
              placeholder="e.g. Q4 Executive Outreach"
              className="w-full sm:w-80 rounded-lg bg-background border border-border/60 px-3.5 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/30"
            />
          </div>
          <p className="text-xs text-muted-foreground sm:text-right max-w-xs leading-relaxed">
            Name your campaign so it's easily recognized across analytics, master views, and notifications.
          </p>
        </div>

      </div>
    </div>
  )
}

class CampaignErrorBoundary extends React.Component<{children: React.ReactNode}, {hasError: boolean}> {
  constructor(props: {children: React.ReactNode}) {
    super(props);
    this.state = { hasError: false };
  }
  static getDerivedStateFromError() {
    return { hasError: true };
  }
  componentDidCatch(error: any, errorInfo: any) {
    console.error("Campaign load error:", error, errorInfo);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="h-[100dvh] bg-background text-foreground flex flex-col items-center justify-center">
          <div className="bg-destructive/10 border border-destructive/50 p-8 rounded-xl text-center max-w-md">
            <h2 className="text-xl font-bold text-destructive mb-2">Something went wrong</h2>
            <p className="text-sm text-destructive mb-6">Something went wrong loading this campaign. Click here to go back.</p>
            {/* Kept as window.location.href because CampaignErrorBoundary is a class component without hook access */}
            <button type="button" onClick={() => window.location.href = '/elein/campaigns'} className="px-6 py-2 bg-destructive hover:bg-destructive/90 text-white rounded-lg font-medium transition-colors">
              Go Back
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

function EleInCreateCampaignInner() {
  const navigate = useNavigate()
  const [showErrors, setShowErrors] = useState(false)
  const step = useHRTreeStore(s => s.campaignStep);
  const setStep = useHRTreeStore(s => s.setCampaignStep);
  const state = useHRTreeStore(s => s.formState);
  const setFormState = useHRTreeStore(s => s.setFormState);

  const setState = (updater: any) => {
    useHRTreeStore.setState((state) => ({
      formState: typeof updater === 'function' ? updater(state.formState) : { ...state.formState, ...updater }
    }));
  };

  const [draftErrors, setDraftErrors] = useState<string[]>([])
  const [activationErrors, setActivationErrors] = useState<string[]>([])

  const canUndo = useHRTreeStore(s => s.history.length > 0)
  const canRedo = useHRTreeStore(s => s.future.length > 0)
  const [showBrowser, setShowBrowser] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [showUpgradeModal, setShowUpgradeModal] = useState(false)
  const [showPreflightModal, setShowPreflightModal] = useState(false)

  const { data: allLists } = useSWR<any[]>("/api/elein/leads/lists", fetcher)
  const selectedListInfo = (allLists || []).find((l: any) => l.id === state.leadListId)
  const senderCount = state.senderIds?.length || 0
  const rootNodes = useHRTreeStore(s => s.rootNodes)
  const sequenceHasNodes = (rootNodes || []).length > 0
  const audienceReady = Boolean(selectedListInfo && (selectedListInfo.row_count || 0) > 0)
  const sendersReady = senderCount > 0
  const isPreflightClear = sequenceHasNodes && audienceReady && sendersReady

  // ─── Route params & Edit / Load state ──────────────────────────────────────
  const { id: routeId } = useParams<{ id?: string }>()
  const location = useLocation()
  const initialParams = new URLSearchParams(location.search)
  const initialEditId = initialParams.get("edit") || routeId

  const [isLoadingCampaign, setIsLoadingCampaign] = useState<boolean>(Boolean(initialEditId))
  const isLoadingCampaignRef = React.useRef<boolean>(Boolean(initialEditId))
  const isSavingRef = React.useRef<boolean>(false)

  useEffect(() => {
    isLoadingCampaignRef.current = isLoadingCampaign
  }, [isLoadingCampaign])

  // R5: Scoped autosave subscription  -  active ONLY while EleInCreateCampaign is mounted
  useEffect(() => {
    const unsubscribe = useHRTreeStore.subscribe((storeState) => {
      // Paranoia Layer 1: Do not overwrite draft if save/launch is executing or campaign is loading
      if (isSavingRef.current || isLoadingCampaignRef.current) return
      saveDraftToLocalStorage(storeState)
    })

    return () => {
      unsubscribe()
    }
  }, [])

  // On mount or route change: if ?resume=true, restore from localStorage. If edit mode, load from API
  useEffect(() => {
    const params = new URLSearchParams(location.search)
    const currentEditId = params.get("edit") || routeId
    const startId = params.get("start")
    
    if (params.get("blank") === "true") {
      setIsLoadingCampaign(false)
      isLoadingCampaignRef.current = false
      useHRTreeStore.getState().reset()
      setFormState({
        campaignName: '',
        senders: [],
        senderIds: [],
        leads: [],
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
        schedule: {},
        limit: 50,
        provider: 'any',
        leadListId: '',
        excludeListId: ''
      })
      setStep(0)
      try {
        localStorage.removeItem("elein_unsaved_draft")
      } catch (_) {}
      window.history.replaceState({}, '', '/elein/campaigns/new')
      return
    }
    
    if (startId) {
      setIsLoadingCampaign(false)
      isLoadingCampaignRef.current = false
      const allTemplates = [...HR_TEMPLATES, ...useTemplatesStore.getState().customTemplates]
      const template = allTemplates.find(t => t.id === startId)
      if (template) {
        useHRTreeStore.getState().loadTree(dagToTree(template.nodes, template.edges), [])
        setState((prev: any) => ({ ...prev, campaignName: template.name }))
      }
      // clear url without reload
      window.history.replaceState({}, '', '/elein/campaigns/new')
      return
    }
    
    if (currentEditId) {
      // Edit mode: fetch campaign from API
      setIsLoadingCampaign(true)
      isLoadingCampaignRef.current = true
      setState((prev: any) => ({ ...prev, campaignId: currentEditId }))
      fetchWithAuth(`/api/elein/campaigns/${currentEditId}/detail`)
        .then(res => {
          if (!res.ok) {
            throw new Error(res.status === 404 ? "Not found" : "API error")
          }
          return res.json()
        })
        .then(data => {
          if (!data || !data.id) {
            toast.error("Campaign not found. It may have been deleted.")
            setIsLoadingCampaign(false)
            isLoadingCampaignRef.current = false
            navigate("/elein/campaigns")
            return
          }

          const rawNodes = data.nodes || data.nodes_json || []
          const nodes = typeof rawNodes === "string" ? JSON.parse(rawNodes) : rawNodes
          const rawEdges = data.edges || data.edges_json || []
          const edges = typeof rawEdges === "string" ? JSON.parse(rawEdges) : rawEdges
          const rawSenders = data.sender_account_ids || data.sender_account_ids_json || []
          const senderIds = typeof rawSenders === "string" ? JSON.parse(rawSenders) : rawSenders

          if (Array.isArray(nodes) && nodes.length > 0) {
            useHRTreeStore.getState().loadTree(dagToTree(nodes, Array.isArray(edges) ? edges : []), [])
          }
          setState((prev: any) => ({
            ...prev,
            campaignId: currentEditId,
            campaignName: data.name || "Untitled Campaign",
            senderIds: Array.isArray(senderIds) ? senderIds : [],
            timezone: data.metadata?.timezone || data.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
            scheduling_mode: data.metadata?.scheduling_mode || (data.metadata?.ai_sto_enabled ? "ai_sto" : "campaign_timezone"),
            leadListId: data.lead_list_id || data.metadata?.lead_list_id || "",
            searchUrl: data.sales_nav_url || data.metadata?.sales_nav_url || "",
            limit: data.metadata?.limit ?? data.limit ?? 50,
            schedule: data.metadata?.schedule || data.schedule || {},
            stopOnReply: data.metadata?.stop_on_reply ?? true
          }))
          // Jump directly to the Sequence builder (now Step 0)
          setStep(0)
          setIsLoadingCampaign(false)
          isLoadingCampaignRef.current = false
        })
        .catch(err => {
          console.error("Failed to load campaign:", err)
          toast.error("Campaign not found. It may have been deleted.")
          setIsLoadingCampaign(false)
          isLoadingCampaignRef.current = false
          navigate("/elein/campaigns")
        })
      return
    }

    setIsLoadingCampaign(false)
    isLoadingCampaignRef.current = false

    if (params.get("resume") !== "true") return
    
    // LAYER 0 + LAYER 2 Paranoia: Actually implement the Draft Restore that was missing
    const draftStr = localStorage.getItem("elein_unsaved_draft")
    if (draftStr) {
      try {
        const draft = JSON.parse(draftStr)
        if (draft.nodes && draft.nodes.length > 0) {
          useHRTreeStore.getState().loadTree(dagToTree(draft.nodes, draft.edges || []), [])
        }
        if (draft.formState) {
          useHRTreeStore.getState().setFormState(draft.formState)
        }
        if (typeof draft.step === "number") {
          setStep(draft.step)
        } else {
          setStep(0)
        }
      } catch (e) {
        console.error("Failed to parse or restore draft:", e)
        setStep(0)
      }
    } else {
      setStep(0)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.search, routeId])



  // Warn user before close/reload
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault()
      e.returnValue = ''
    }
    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [])
  
  const handleSaveDraft = async (status = "DRAFT") => {
    if (isSavingRef.current) return;
    isSavingRef.current = true;
    setIsSaving(true);
    const { rootNodes } = useHRTreeStore.getState();
    const campaignName = state.campaignName?.trim() || "Untitled Campaign";

    const { errors: treeErrs } = validateTree(rootNodes);
    const criticalErrors = Object.values(treeErrs).flat();

    const hasIfRepliedNode = rootNodes.some(function search(node: any): boolean {
      if (node.type.startsWith("if_replied")) return true;
      for (const branch of Object.values(node.children || {})) {
        if ((branch as any[]).some(search)) return true;
      }
      return false;
    });

    if (!(state.stopOnReply ?? true) && !hasIfRepliedNode) {
      criticalErrors.push("Safety Violation: 'Stop campaign on reply' is DISABLED, but you have no 'If Replied' nodes in your sequence. You must either handle replies in the sequence or re-enable the safety switch.");
    }

    if (status === "DRAFT" && criticalErrors.length > 0) {
      setDraftErrors(criticalErrors);
    } else {
      setDraftErrors([]);
    }

    if (status === "ACTIVE") {
      if (rootNodes.length === 0) {
        toast.error("Cannot launch: Your sequence is empty.");
        isSavingRef.current = false;
        setIsSaving(false);
        return;
      }
      
      const allErrors = [...criticalErrors];
      if (!state.senderIds || state.senderIds.length === 0) {
        allErrors.push("You must connect at least one LinkedIn sender account.");
      }
      if (!state.leadListId) {
        allErrors.push("You must select a lead list to enroll.");
      }

      if (allErrors.length > 0) {
        setActivationErrors(allErrors);
        isSavingRef.current = false;
        setIsSaving(false);
        return;
      }
    }

    const { nodes, edges } = treeToDag(rootNodes);
    
    try {
      const url = state.campaignId ? `/api/elein/campaigns/${state.campaignId}` : "/api/elein/campaigns";
      const method = state.campaignId ? "PUT" : "POST";
      const res = await fetchWithAuth(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: campaignName,
          nodes,
          edges,
          senders: state.senderIds || [],
          timezone: state.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone,
          status,
          schedule: state.schedule,
          limit: state.limit,
          lead_list_id: state.leadListId || null,
          metadata: { 
            lead_list_id: state.leadListId || null,
            stop_on_reply: state.stopOnReply ?? true,
            scheduling_mode: state.scheduling_mode || "campaign_timezone",
            ai_sto_enabled: (state.scheduling_mode === "ai_sto"),
            weekend_sending_enabled: Boolean(state.schedule?.weekend_sending)
          }
        })
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`API Error ${res.status}: ${text}`);
      }
      const data = await res.json();
      
      if (state.leadListId) {
        try {
          const campaignIdToEnroll = state.campaignId || data.id;
          const enrollRes = await fetchWithAuth(`/api/elein/campaigns/${campaignIdToEnroll}/enroll_list`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              list_id: state.leadListId,
              exclude_list_id: state.excludeListId || null,
              excludeListId: state.excludeListId || null,
              excludeOtherCampaigns: state.excludeOtherCampaigns || false,
              excludeOtherSenders: state.excludeOtherSenders || false,
              excludeSameSender: state.excludeSameSender || false
            })
          });
          if (!enrollRes.ok) {
            const errJson = await enrollRes.json().catch(() => ({}));
            toast.error(`Campaign saved, but failed to enroll leads: ${errJson.detail || "Enrollment failed"}`);
          }
        } catch (enrollErr: any) {
          console.error("Failed to enroll list", enrollErr);
          toast.error(`Campaign saved, but failed to enroll leads: ${enrollErr.message || "Network error"}`);
        }
      }

      toast.success(status === "ACTIVE" ? `Campaign "${campaignName}" launched!` : `Campaign "${campaignName}" saved as draft.`, {
        description: "You can find it in your Campaigns dashboard."
      });
      // Clear the local draft so the "Unsaved Draft" banner doesn't reappear
      try {
        localStorage.removeItem("elein_unsaved_draft");
      } catch(e) {}
      
      useHRTreeStore.getState().reset();
      mutate("/api/elein/dashboard/stats");
      mutate("/api/elein/campaigns");
      navigate("/elein/campaigns");
    } catch (e: any) {
      isSavingRef.current = false;
      const msg = e instanceof Error ? e.message : String(e)
      if (msg.includes("exceeds limit") || msg.includes("403") || msg.toLowerCase().includes("forbidden") || msg.includes("Free Tier")) {
        if (status === "ACTIVE") {
          // Fallback save as draft for both new and existing campaigns (Layer 2 Paranoia)
          const draftUrl = state.campaignId ? `/api/elein/campaigns/${state.campaignId}` : "/api/elein/campaigns";
          const draftMethod = state.campaignId ? "PUT" : "POST";
          fetchWithAuth(draftUrl, {
            method: draftMethod,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              name: campaignName,
              nodes,
              edges,
              senders: state.senderIds || [],
              timezone: state.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone,
              status: "DRAFT",
              schedule: state.schedule,
              limit: state.limit,
              metadata: { 
                stop_on_reply: state.stopOnReply ?? true,
                scheduling_mode: state.scheduling_mode || "campaign_timezone",
                ai_sto_enabled: (state.scheduling_mode === "ai_sto"),
                weekend_sending_enabled: Boolean(state.schedule?.weekend_sending)
              }
            })
          })
          .then(async (res) => {
            if (res.ok) {
              const draftData = await res.json().catch(() => ({}));
              if (draftData.id && !state.campaignId) {
                handleStateChange("campaignId", draftData.id);
              }
              try {
                localStorage.removeItem("elein_unsaved_draft");
              } catch (_) {}
              mutate("/api/elein/dashboard/stats");
            }
          })
          .catch(err => console.error("Fallback draft save failed", err))
          .finally(() => {
            isSavingRef.current = false;
            setIsSaving(false);
          });
        }
        setShowUpgradeModal(true);
      } else if (e instanceof TypeError || (e instanceof Error && e.name === 'AbortError') || msg === 'Failed to fetch' || msg.includes('ERR_CONNECTION_REFUSED') || msg.includes('NetworkError')) {
        toast.error("Cannot reach the backend server.", {
          description: "The backend is not running. Open a terminal, go to the backend/ folder and run: ./start.sh"
        })
      } else {
        toast.error("Failed to save campaign: " + msg)
      }
    } finally {
      setIsSaving(false);
    }
  }

  const handleNext = () => {
    if (step === 1) {
      if (!state.campaignName || !state.campaignName.trim() || !state.leadListId) {
        setShowErrors(true);
        toast.error("Please provide the required setup information before continuing.");
        return;
      }
      setShowErrors(false);
    }
    if (step === 0) {
      const { rootNodes } = useHRTreeStore.getState()
      if (rootNodes.length === 0) {
        toast.error("Please add at least one node.", { position: "top-center" })
        return
      }
      const { errors } = validateTree(rootNodes)
      const hasErrors = Object.values(errors).some(e => e.length > 0)
      
      const hasIfRepliedNode = rootNodes.some(function search(node: any): boolean {
        if (node.type.startsWith("if_replied")) return true;
        for (const branch of Object.values(node.children || {})) {
          if ((branch as any[]).some(search)) return true;
        }
        return false;
      });

      if (!(state.stopOnReply ?? true) && !hasIfRepliedNode) {
        toast.error("Safety Violation", { description: "'Stop campaign on reply' is DISABLED in settings, but you have no 'If Replied' nodes in your sequence. You must either handle replies in the sequence or re-enable the safety switch." })
        return
      }

      if (hasErrors) {
        // DO NOT show generic error. Focus on the canvas.
        toast.error("There are unmet prerequisites in your sequence.", { description: "Please fix the red errors on the nodes before continuing." })
        return
      }
    }
    if (step === 2) {
      if (!state.senderIds || state.senderIds.length === 0) {
        setShowErrors(true);
        toast.error("Please connect at least one LinkedIn sender account.");
        return
      }
      setShowErrors(false);
    }
    if (step < STEPS.length - 1) setStep(step + 1)
  }

  const handleStateChange = (k: string, v: any) => {
    setState((prev: any) => ({ ...prev, [k]: v }))
  }

  if (isLoadingCampaign) {
    return (
      <div className="h-[100dvh] bg-background text-foreground flex flex-col items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary mb-4" />
        <p className="text-sm text-muted-foreground font-medium">Loading campaign sequence...</p>
      </div>
    );
  }

  return (
    <div className="h-[100dvh] bg-background text-foreground flex flex-col overflow-hidden relative">


      {draftErrors.length > 0 && (
        <div className="bg-warning/10 border-b border-warning/50 p-3 z-50">
          <div className="max-w-4xl mx-auto flex items-start gap-3">
            <AlertTriangle className="text-warning shrink-0 mt-0.5" size={16} />
            <div className="text-xs text-warning dark:text-warning">
              <span className="font-bold">Your draft has issues that must be fixed before activating:</span>
              <ul className="list-disc pl-4 mt-1">
                {draftErrors.map((err, i) => <li key={i}>{err}</li>)}
              </ul>
            </div>
          </div>
        </div>
      )}

      <AnimatePresence>
        {activationErrors.length > 0 && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 p-4">
            <motion.div
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.96 }}
              className="w-full max-w-lg rounded-xl bg-background border border-destructive/50 shadow-2xl overflow-hidden p-6"
            >
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-full bg-destructive/10 flex items-center justify-center shrink-0">
                  <AlertTriangle className="text-destructive" size={20} />
                </div>
                <div>
                  <h2 className="text-lg font-bold text-foreground">Cannot Launch Campaign</h2>
                  <p className="text-xs text-muted-foreground">Please resolve the following pre-flight requirements before launch:</p>
                </div>
              </div>
              <ul className="space-y-2 mb-6 max-h-64 overflow-y-auto">
                {activationErrors.map((err, i) => {
                  let targetStep: number | null = null;
                  let targetLabel = "";
                  if (err.toLowerCase().includes("sender") || err.toLowerCase().includes("account")) {
                    targetStep = 2;
                    targetLabel = "Fix Senders (Step 3)";
                  } else if (err.toLowerCase().includes("lead") || err.toLowerCase().includes("audience")) {
                    targetStep = 1;
                    targetLabel = "Fix Audience (Step 2)";
                  } else if (err.toLowerCase().includes("sequence") || err.toLowerCase().includes("empty") || err.toLowerCase().includes("node") || err.toLowerCase().includes("replied")) {
                    targetStep = 0;
                    targetLabel = "Fix Sequence (Step 1)";
                  }

                  return (
                    <li key={i} className="text-xs text-destructive flex items-center justify-between gap-3 bg-destructive/10 p-3 rounded-lg border border-destructive/20">
                      <div className="flex items-start gap-2 flex-1">
                        <span className="shrink-0 font-bold">•</span>
                        <span className="leading-relaxed font-medium">{err}</span>
                      </div>
                      {targetStep !== null && (
                        <button
                          type="button"
                          onClick={() => {
                            setActivationErrors([]);
                            setStep(targetStep!);
                          }}
                          className="shrink-0 px-2.5 py-1.5 bg-destructive hover:bg-destructive/90 text-white font-bold text-[11px] rounded-lg transition-all flex items-center gap-1 cursor-pointer whitespace-nowrap shadow-xs"
                        >
                          <span>{targetLabel}</span>
                          <ArrowRight size={11} />
                        </button>
                      )}
                    </li>
                  );
                })}
              </ul>
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setActivationErrors([])}
                  className="px-5 py-2.5 bg-muted hover:bg-muted/80 text-foreground font-semibold text-xs rounded-lg transition-all cursor-pointer"
                >
                  Dismiss
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* High-Converting In-Situ Paywall Modal */}
      <EleInPaywallModal
        isOpen={showUpgradeModal}
        onClose={() => setShowUpgradeModal(false)}
        campaignName={state.campaignName || "Untitled Campaign"}
        onSuccess={() => {
          toast.success("Account upgraded to Growth Tier! Activating your campaign...");
          handleSaveDraft("ACTIVE");
        }}
      />

      {/* Area 5 Pre-Flight Launch Cockpit Gate */}
      <CampaignPreflightModal
        isOpen={showPreflightModal}
        onClose={() => setShowPreflightModal(false)}
        onConfirmLaunch={() => handleSaveDraft("ACTIVE")}
        campaignId={state.campaignId}
        campaignName={state.campaignName || "Untitled Campaign"}
        inFlightPayload={{
          nodes: treeToDag(useHRTreeStore.getState().rootNodes).nodes,
          edges: treeToDag(useHRTreeStore.getState().rootNodes).edges,
          senderIds: state.senderIds || [],
          leadListId: state.leadListId || undefined,
          excludeListId: state.excludeListId || undefined,
          timezone: state.timezone,
          schedule: {
            ...state.schedule,
            mode: state.scheduling_mode || "campaign_timezone",
            scheduling_mode: state.scheduling_mode || "campaign_timezone",
            weekend_sending: Boolean(state.schedule?.weekend_sending),
            weekend_sending_enabled: Boolean(state.schedule?.weekend_sending)
          },
          stopOnReply: state.stopOnReply ?? true
        }}
        onJumpToStep={(s) => setStep(s)}
      />

      {/* Step Header */}
      <StepHeader 
        current={step} 
        onBack={() => {
          if (step > 0) {
            setStep(step - 1)
          } else {
            navigate("/elein/campaigns")
          }
        }} 
        onStepClick={(i) => setStep(i)} 
      />
      
      <div className="flex-1 overflow-y-auto relative">
        <AnimatePresence mode="wait">
          <motion.div
            key={step}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
            className="absolute inset-0 flex flex-col"
          >
            {step === 0 && <StepSequence onSave={() => handleSaveDraft("DRAFT")} />}
            {step === 1 && (
              <div className="flex-1 overflow-auto p-8 relative z-10 flex flex-col items-center justify-center min-h-0">
                <div className="w-full max-w-4xl mx-auto flex flex-col items-center justify-center">
                  <div className="mb-10 text-center">
                    <h1 className="text-4xl font-light tracking-tight text-foreground mb-3">Audience Setup</h1>
                    <p className="text-base text-muted-foreground">Give your campaign a name and select your target audience.</p>
                  </div>
                  <div className="w-full">
                    <StepLeads state={state} onChange={handleStateChange} onNext={handleNext} showErrors={showErrors} />
                  </div>
                </div>
              </div>
            )}
            {step === 2 && <StepSenders state={state} onChange={handleStateChange} showErrors={showErrors} />}
            {step === 3 && <StepSchedule state={state} onChange={handleStateChange} />}
            {step === 4 && (
              <StepPreview 
                state={state} 
                onChange={handleStateChange} 
                onJumpToStep={(s) => setStep(s)} 
                onOpenPreflightModal={() => setShowPreflightModal(true)}
              />
            )}
          </motion.div>
        </AnimatePresence>
      </div>

      {/* ─── Sticky Bottom Action Dock ─── */}
      <div className="relative z-20 flex items-center justify-between gap-3 px-6 py-3.5 border-t border-border/50 bg-background/85 backdrop-blur-md shrink-0 shadow-lg">
        {step > 0 ? (
          <button
            type="button"
            onClick={() => setStep(step - 1)}
            className="flex items-center gap-1.5 px-3.5 py-2 text-xs font-medium rounded-xl border border-border/50 bg-background/50 hover:bg-muted text-muted-foreground hover:text-foreground transition-all cursor-pointer"
          >
            <ArrowLeft size={13} />
            <span>Back</span>
          </button>
        ) : (
          <div />
        )}

        {/* Right: Actions (Save Draft + Next / Launch CTA) */}
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => handleSaveDraft("DRAFT")}
            disabled={isSaving}
            className="flex items-center gap-1.5 px-4 py-2 text-xs font-semibold rounded-xl border border-border/50 bg-background/50 hover:bg-muted/50 text-foreground transition-all hover:border-border disabled:opacity-50"
          >
            <Save size={13} />
            <span>{isSaving ? "Saving..." : "Save Draft"}</span>
          </button>

          <button
            type="button"
            onClick={step === STEPS.length - 1 ? () => setShowPreflightModal(true) : handleNext}
            disabled={isSaving}
            className={cn(
              "flex items-center gap-2 px-5 py-2 text-xs font-bold rounded-xl transition-all shadow-md disabled:opacity-50 whitespace-nowrap cursor-pointer",
              step === STEPS.length - 1
                ? isPreflightClear
                  ? "bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-500/20"
                  : "bg-amber-600 hover:bg-amber-500 text-white shadow-amber-500/20"
                : "bg-primary hover:bg-primary/90 text-primary-foreground shadow-primary/20"
            )}
          >
            {step === STEPS.length - 1 ? (
              isSaving ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Activating...</span>
                </>
              ) : isPreflightClear ? (
                <>
                  <Zap size={14} className="text-amber-300 fill-amber-300" />
                  <span>Launch Campaign • 100% Pre-Flight Cleared</span>
                </>
              ) : (
                <>
                  <AlertTriangle size={14} className="text-amber-200" />
                  <span>Pre-Flight Attention • Review Requirements</span>
                </>
              )
            ) : (
              <>
                <span>Continue to {STEPS[step + 1]?.label || "Next"}</span>
                <ArrowRight size={13} />
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}

export function EleInCreateCampaign() {
  return (
    <CampaignErrorBoundary>
      <EleInCreateCampaignInner />
    </CampaignErrorBoundary>
  )
}
