import { fetcher, fetchWithAuth } from "@/lib/apiClient"
import React, { useState, useEffect } from "react"
import { useNavigate, useSearchParams, useLocation } from "react-router-dom"
import useSWR from "swr"

import { motion, AnimatePresence } from "motion/react"
import { ReactFlowProvider } from "@xyflow/react"
import "@xyflow/react/dist/style.css"

import { Zap, Play, Loader2, Save, MoreHorizontal, ArrowLeft, Plus, UserPlus, FileText, Copy, Undo, Redo, ArrowRight, ChevronLeft, Check, CheckCircle2, ChevronRight, X, Search, Tag, Users, MessageSquare, ArrowUpRight, Eye, AlertTriangle, Briefcase, Link as LinkIcon } from "lucide-react"
import { cn } from "@/lib/utils"
import { useHRTreeStore, dagToTree, treeToDag } from "@campaigns/eiTreeStore"
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

import { toast } from "sonner"
import { mutate } from "swr"
import { BackgroundBeams } from "@/components/ui/background-beams"
import { AnimatedThemeToggler } from "@/components/ui/animated-theme-toggler"
import { useTheme } from "@/components/ThemeProvider"
import { Meteors } from "@/components/ui/meteors"
import { WarmupWizard } from "./WarmupWizard"


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
  { id: "leads", label: "Setup" },
  { id: "sequence", label: "Sequence" },
  { id: "senders", label: "LinkedIn Senders" },
  { id: "schedule", label: "Schedule" },
  { id: "preview", label: "Preview" },
]

function StepHeader({ current, onBack, onStepClick }: { current: number, onBack: () => void, onStepClick?: (step: number) => void }) {
  const { theme, setTheme } = useTheme()
  return (
    <div className="relative flex items-center justify-center gap-0 py-5 border-b border-border/50 bg-background/50 backdrop-blur-md z-10 shrink-0">
      {/* Top Left Back Button */}
      <button
        onClick={onBack}
        className="absolute left-6 top-1/2 -translate-y-1/2 flex items-center gap-1.5 px-4 py-2 rounded-xl border border-border/50 hover:border-foreground/20 text-xs font-semibold text-muted-foreground transition-all hover:bg-muted/30 hover:text-foreground shadow-sm"
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

function StepLeads({ state, onChange, onNext }: { state: any; onChange: (k: string, v: any) => void; onNext?: () => void }) {
  const { data, error, isLoading, mutate } = useSWR("/api/elein/leads/lists", fetcher)
  const lists = data || []
  
  useEffect(() => {
    if (lists.length === 1 && !state.leadListId) {
      onChange("leadListId", lists[0].id)
    }
  }, [lists, state.leadListId, onChange])
  
  const [timedOut, setTimedOut] = useState(false)
  useEffect(() => {
    let timer: NodeJS.Timeout
    if (isLoading && !data && !error) {
      timer = setTimeout(() => {
        setTimedOut(true)
      }, 15000)
    }
    return () => clearTimeout(timer)
  }, [isLoading, data, error])

  const hasError = error || timedOut

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-10 max-w-4xl mx-auto py-8 px-6">
      {/* Left */}
      <SpotlightCard className="p-6 rounded-2xl bg-card/30 border border-border/50 backdrop-blur-md">
        <div className="space-y-5">
          <div>
            <label className="block text-xs font-semibold text-foreground mb-2">Campaign name</label>
            <input
              value={state.campaignName}
              onChange={e => onChange("campaignName", e.target.value)}
              onKeyDown={e => {
                if (e.key === "Enter" && onNext) {
                  e.preventDefault();
                  onNext();
                }
              }}
              placeholder="e.g. BIOTECH Q3 OUTREACH"
              className="w-full rounded-lg bg-background/50 border border-border/50 px-3 py-2.5 text-sm text-foreground
                         placeholder-muted-foreground focus:outline-none focus:border-foreground/30 transition-colors"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-foreground mb-1">Select Lead List</label>
            <p className="text-[10px] text-muted-foreground mb-2">The LinkedIn profiles you want to reach — enrolled into your sequence below.</p>
            {hasError ? (
              <div className="p-4 rounded-lg border border-destructive/50 bg-destructive/10 text-center space-y-3">
                <p className="text-xs text-destructive font-medium">Could not load your lead lists. Check your connection and try again.</p>
                <button
                  onClick={() => {
                    setTimedOut(false);
                    mutate();
                  }}
                  className="px-4 py-2 bg-destructive hover:bg-destructive text-white text-xs font-bold rounded-md transition-colors"
                >
                  Retry
                </button>
              </div>
            ) : (
            <>
            <div className="relative">
              <select
                value={state.leadListId || ""}
                onChange={e => onChange("leadListId", e.target.value)}
                disabled={isLoading || lists.length === 0}
                className="w-full appearance-none rounded-lg bg-background/50 border border-border/50 px-3 py-2.5 text-sm
                           text-foreground focus:outline-none focus:border-foreground/30 transition-colors disabled:opacity-50"
              >
                {isLoading ? (
                  <option value="">Loading your lists...</option>
                ) : lists.length === 0 ? (
                  <option value="">No lists found in this workspace</option>
                ) : (
                  <option value="">Choose a lead list (or add later)...</option>
                )}
                
                {lists.map((list: any) => (
                  <option key={list.id} value={list.id} disabled={list.row_count === 0}>
                    {list.name} ({list.row_count} leads{list.row_count === 0 ? " — Empty" : ""})
                  </option>
                ))}
              </select>
              <ChevronRight size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 rotate-90 pointer-events-none" />
            </div>
            {state.leadListId && lists.find((l: any) => l.id === state.leadListId)?.row_count === 0 && (
              <p className="mt-2 text-xs text-amber-500 font-medium">⚠️ This lead list is empty. You cannot launch a campaign with 0 leads.</p>
            )}
            </>
            )}
          </div>
        </div>
      </SpotlightCard>

      {/* Right */}
      <SpotlightCard className="p-6 rounded-2xl bg-card/30 border border-border/50 backdrop-blur-md">
        <div className="space-y-5">
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1">Exclude list</label>
          <p className="text-[10px] text-muted-foreground mb-2">Block contacts who've already heard from you (optional).</p>
          <div className="relative">
            <select
              value={state.excludeListId || ""}
              onChange={e => onChange("excludeListId", e.target.value)}
              disabled={isLoading || hasError || lists.length === 0}
              className="w-full appearance-none rounded-lg bg-muted/30 border border-border px-3 py-2.5 text-sm
                         text-foreground focus:outline-none focus:border-foreground/30 transition-colors disabled:opacity-50"
            >
                {isLoading ? (
                  <option value="">Loading your lists...</option>
                ) : hasError ? (
                  <option value="">Error loading lists</option>
                ) : lists.length === 0 ? (
                  <option value="">No lists found in this workspace</option>
                ) : (
                  <option value="">Select an exclusion list (optional)</option>
                )}
              {lists.map((list: any) => (
                <option key={list.id} value={list.id}>
                  {list.name} ({list.row_count} leads)
                </option>
              ))}
            </select>
            <ChevronRight size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 rotate-90 pointer-events-none" />
          </div>
        </div>
        <div>
          <AdvancedSettingsPanel label="Advanced: Global Deduplication">
            <div className="space-y-3 bg-primary/5 p-4 rounded-xl border border-primary/20">
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
          </AdvancedSettingsPanel>
        </div>
        </div>
      </SpotlightCard>
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.96 }}
        className="w-full max-w-5xl h-[88vh] rounded-2xl bg-background border border-border/50 shadow-2xl flex flex-col overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border/50 shrink-0">
          <div>
            <h2 className="text-base font-bold text-foreground">Browse templates</h2>
            <p className="text-[10px] text-muted-foreground mt-0.5">Ready-to-use sequences with sticky notes to guide you through each step</p>
          </div>
          <button onClick={onClose} className="text-gray-600 hover:text-foreground transition-colors">
            <X size={18} />
          </button>
        </div>

        <div className="flex flex-1 overflow-hidden">
          {/* Left list */}
          <div className="w-72 border-r border-border/50 flex flex-col shrink-0">
            {/* Search */}
            <div className="flex items-center gap-2 mx-4 mt-4 mb-2 rounded-lg bg-black/40 border border-border/50 px-3 py-2">
              <Search size={12} className="text-gray-600 shrink-0" />
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search templates…"
                className="flex-1 bg-transparent text-xs text-gray-200 placeholder-gray-500 focus:outline-none"
              />
            </div>

            {/* Tag filters */}
            <div className="px-4 pb-3 flex flex-wrap gap-1">
              {TEMPLATE_TAGS.map(tag => (
                <button
                  key={tag}
                  onClick={() => setActiveTag(tag)}
                  className={cn(
                    "flex items-center gap-1 text-[9px] px-2 py-1 rounded-md font-semibold transition-all",
                    activeTag === tag
                      ? "bg-primary/20 text-primary/80 border border-primary/30"
                      : "text-muted-foreground border border-transparent hover:text-zinc-300 hover:bg-muted/30"
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
                  key={t.id}
                  onClick={() => setSelected(t.id)}
                  className={cn(
                    "w-full text-left p-4 rounded-xl border transition-all mt-2",
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
                      <span className="text-[8px] text-primary/80 bg-primary/10 px-1.5 py-0.5 rounded font-bold">★ Top pick</span>
                    )}
                  </div>
                  <p className="text-xs font-bold text-foreground mb-1 leading-tight">{t.name}</p>
                  <p className="text-[10px] text-gray-500 mb-2 line-clamp-2">{t.description}</p>
                  <div className="flex items-center gap-2">
                    <span className="flex items-center gap-1 text-[10px] text-success bg-success/10 px-1.5 py-0.5 rounded">
                      <Users size={9} /> {t.connectionRate}%
                    </span>
                    <span className="flex items-center gap-1 text-[10px] text-primary bg-primary/10 px-1.5 py-0.5 rounded">
                      <MessageSquare size={9} /> {t.replyRate}%
                    </span>
                    <span className="ml-auto flex items-center gap-1 text-[10px] text-gray-600">
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
            <button onClick={onClose} className="px-4 py-2 rounded-lg border border-border/50 hover:border-border/50 text-xs text-gray-400 hover:text-gray-200 transition-all">
              Close
            </button>
            {selectedTemplate && (
              <button
                onClick={() => { onImport(selected); onClose() }}
                className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-primary/90 hover:bg-primary text-xs font-bold text-foreground transition-all"
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
        <button onClick={() => selectNode(null)} className="text-muted-foreground hover:text-foreground p-1 rounded-md hover:bg-muted/50 transition-colors">
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
  const startParam = new URLSearchParams(window.location.search).get("start");
  const initialMode = startParam || rootNodes.length > 0 ? "preview" : "choose";
  const [mode, setMode] = useState<"choose" | "build" | "template" | "wizard" | "preview">(initialMode as any)
  const [showBrowser, setShowBrowser] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  
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
            <SpotlightCard className="p-8 border border-border/50 bg-card/30 rounded-2xl cursor-pointer hover:border-foreground/30 transition-all flex flex-col items-center justify-center text-center group relative overflow-hidden" onClick={() => {
              const template = HR_TEMPLATES.find(t => t.id === 'get_customers');
              if (template) { loadTree(dagToTree(template.nodes, template.edges), []); setMode("preview"); }
            }}>
              <div className="w-16 h-16 rounded-full bg-primary/20 flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
                <Users size={24} className="text-primary" />
              </div>
              <h3 className="text-lg font-semibold text-foreground mb-2">Get customers</h3>
              <p className="text-xs text-muted-foreground">Message people who can buy. Goal: book a meeting.</p>
            </SpotlightCard>

            {/* Option B */}
            <SpotlightCard className="p-8 border border-border/50 bg-card/30 rounded-2xl cursor-pointer hover:border-foreground/30 transition-all flex flex-col items-center justify-center text-center group relative overflow-hidden" onClick={() => {
              const template = HR_TEMPLATES.find(t => t.id === 'hire_people');
              if (template) { loadTree(dagToTree(template.nodes, template.edges), []); setMode("preview"); }
            }}>
              <div className="w-16 h-16 rounded-full bg-primary/20 flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
                <Briefcase size={24} className="text-primary" />
              </div>
              <h3 className="text-lg font-semibold text-foreground mb-2">Hire people</h3>
              <p className="text-xs text-muted-foreground">Message people you want on the team. Goal: a hire.</p>
            </SpotlightCard>

            {/* Option C */}
            <SpotlightCard className="p-8 border border-border/50 bg-card/30 rounded-2xl cursor-pointer hover:border-foreground/30 transition-all flex flex-col items-center justify-center text-center group relative overflow-hidden" onClick={() => {
              const template = HR_TEMPLATES.find(t => t.id === 'get_intros');
              if (template) { loadTree(dagToTree(template.nodes, template.edges), []); setMode("preview"); }
            }}>
              <div className="w-16 h-16 rounded-full bg-primary/20 flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
                <LinkIcon size={24} className="text-primary" />
              </div>
              <h3 className="text-lg font-semibold text-foreground mb-2">Get intros</h3>
              <p className="text-xs text-muted-foreground">Message people who can open a door — investor, partner, or their network.</p>
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

  
  if (mode === "preview") {
    // Generate an EITemplate from the current tree state
    const templateForPreview = {
      id: "preview", name: "Sequence", description: "", connectionRate: 0, replyRate: 0, uses: 0, difficulty: "beginner" as any, tags: [],
      nodes: treeToDag(rootNodes).nodes, edges: treeToDag(rootNodes).edges
    };
    return (
      <div className="flex-1 flex flex-col items-center p-8 bg-background relative z-10 h-full overflow-y-auto">
        <div className="max-w-2xl w-full">
          <div className="flex justify-between items-center mb-8">
            <div>
              <h2 className="text-2xl font-light tracking-tight text-foreground">Sequence Preview</h2>
              <p className="text-sm text-muted-foreground mt-1">This is the sequence that will be sent to your leads.</p>
            </div>
            <button onClick={() => setMode("build")} className="px-4 py-2 bg-muted/50 hover:bg-muted text-foreground text-sm font-semibold rounded-lg transition-colors border border-border/50">
              Edit Sequence (Graph Wizard)
            </button>
          </div>
          <LinearTemplatePreview template={templateForPreview} />
        </div>
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

function StepSenders({ state, onChange }: { state: any; onChange: (k: string, v: any) => void }) {
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
          <div className="bg-destructive/10 border border-destructive/20 rounded-xl p-4 flex gap-4 text-left shadow-sm">
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
          <div className="bg-primary/5 border border-primary/20 rounded-xl p-4 flex gap-4 text-left shadow-sm">
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
        </div>

        {error ? (
          <div className="bg-destructive/10 border border-destructive/50 rounded-2xl p-12 text-center shadow-sm">
            <h3 className="text-lg font-bold text-destructive mb-2">Error loading accounts</h3>
            <p className="text-sm text-destructive mb-6">{error.message || "Failed to fetch accounts from the server."}</p>
          </div>
        ) : !accounts ? (
          <div className="flex justify-center p-12">
            <div className="w-8 h-8 rounded-full border-2 border-primary border-t-transparent animate-spin" />
          </div>
        ) : accounts.length === 0 ? (
          <div className="bg-card border border-border rounded-2xl p-12 text-center shadow-sm">
            <div className="w-16 h-16 rounded-2xl bg-muted/50 border border-border mx-auto flex items-center justify-center mb-6">
              <Linkedin size={24} className="text-muted-foreground" />
            </div>
            <h3 className="text-lg font-bold text-foreground mb-2">No LinkedIn accounts connected</h3>
            <p className="text-sm text-muted-foreground mb-6">You need to connect at least one LinkedIn account to launch a campaign.</p>
            <button 
              onClick={() => navigate('/elein/accounts')}
              className="px-6 py-2.5 rounded-xl bg-primary text-primary-foreground font-medium hover:bg-primary/90 transition-colors">
              Connect Account
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {accounts.map((acc: any) => {
              const isSelected = (state.senderIds || []).includes(acc.id)
              return (
                <div 
                  key={acc.id}
                  onClick={() => toggleSender(acc.id)}
                  className={`relative p-5 rounded-2xl border transition-all cursor-pointer ${
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
                    <div className="w-12 h-12 rounded-xl bg-muted/50 flex items-center justify-center text-lg font-bold text-foreground border border-border">
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
                             ⚠️ This account is in warmup. It can only send <strong>{limits.connLimit} connections</strong> and <strong>{limits.msgLimit} messages</strong> today to prevent shadow-bans.
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

  return (
    <div className="flex-1 overflow-auto p-8 flex flex-col items-center justify-center min-h-0">
      <div className="w-full max-w-2xl mx-auto text-center">
        <h2 className="text-3xl font-light mb-4">Campaign Schedule</h2>
        <p className="text-muted-foreground mb-8">Ensure your campaign runs during the correct business hours.</p>
        <div className="bg-card/30 border border-border/50 rounded-2xl p-8 backdrop-blur-md space-y-6 text-left">
          
          <div className="space-y-2">
            <label className="text-sm font-medium">Target Timezone</label>
            <p className="text-xs text-muted-foreground mb-2">When sending messages at "9 AM", which timezone should we use?</p>
            <select 
              value={state.timezone || localTz || "America/New_York"}
              onChange={(e) => onChange("timezone", e.target.value)}
              className="w-full bg-background border border-border rounded-lg p-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
            >
              {localTz && !COMMON_TIMEZONES.includes(localTz) && (
                <option value={localTz}>{formatTimezone(localTz)} (Auto-detected)</option>
              )}
              {COMMON_TIMEZONES.map(tz => (
                <option key={tz} value={tz}>{formatTimezone(tz)}{tz === localTz ? " (Auto-detected)" : ""}</option>
              ))}
            </select>
          </div>

          <div className="space-y-2 pt-4 border-t border-border/50">
             <label className="text-sm font-medium">Sending Hours (Mon-Fri)</label>
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
             <p className="text-[11px] text-muted-foreground mt-1">Campaigns will pause outside these hours.</p>
          </div>
        </div>
      </div>
    </div>
  )
}

function StepPreview({ state, onChange }: { state: any; onChange: (k: string, v: any) => void }) {
  return (
    <div className="flex-1 overflow-auto p-8 flex flex-col items-center justify-center min-h-0">
      <div className="w-full max-w-2xl mx-auto text-center">
        <h2 className="text-3xl font-light mb-4">Review & Launch</h2>
        <p className="text-muted-foreground mb-8">Verify your campaign settings before going live.</p>
        <div className="bg-card/30 border border-border/50 rounded-2xl p-8 backdrop-blur-md">
          <p className="text-sm text-muted-foreground">Campaign: {state.campaignName || "Untitled"}</p>
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
          <div className="bg-destructive/10 border border-destructive/50 p-8 rounded-2xl text-center max-w-md">
            <h2 className="text-xl font-bold text-destructive mb-2">Something went wrong</h2>
            <p className="text-sm text-destructive mb-6">Something went wrong loading this campaign. Click here to go back.</p>
            {/* Kept as window.location.href because CampaignErrorBoundary is a class component without hook access */}
            <button onClick={() => window.location.href = '/elein/campaigns'} className="px-6 py-2 bg-destructive hover:bg-destructive text-white rounded-xl font-medium transition-colors">
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

  // ─── Draft autosave & restore ──────────────────────────────────────────────
  const location = useLocation()

  // On mount: if ?resume=true, restore EVERYTHING from localStorage. If ?edit=id, load from API
  useEffect(() => {
    const params = new URLSearchParams(location.search)
    const editId = params.get("edit")
    const startId = params.get("start")
    
    if (startId) {
      const template = HR_TEMPLATES.find(t => t.id === startId)
      if (template) {
        useHRTreeStore.getState().loadTree(dagToTree(template.nodes, template.edges), [])
        setState((prev: any) => ({ ...prev, campaignName: template.name }))
      }
      // clear url without reload
      window.history.replaceState({}, '', '/elein/campaigns/new')
      return
    }
    
    if (editId) {
      // Edit mode: fetch campaign from API
      setState((prev: any) => ({ ...prev, campaignId: editId }))
      fetchWithAuth(`/api/elein/campaigns/${editId}/detail`)
        .then(res => {
          if (!res.ok) {
            throw new Error(res.status === 404 ? "Not found" : "API error");
          }
          return res.json()
        })
        .then(data => {
          if (!data || !data.id) {
            toast.error("Campaign not found. It may have been deleted.")
            navigate("/elein/campaigns")
            return
          }
          const nodes = data.nodes_json ? (typeof data.nodes_json === "string" ? JSON.parse(data.nodes_json) : data.nodes_json) : []
          const edges = data.edges_json ? (typeof data.edges_json === "string" ? JSON.parse(data.edges_json) : data.edges_json) : []
          if (nodes.length > 0) {
            useHRTreeStore.getState().loadTree(dagToTree(nodes, edges), [])
          }
          setState((prev: any) => ({
            ...prev,
            campaignName: data.name || "Untitled Campaign",
            senderIds: data.sender_account_ids_json ? (typeof data.sender_account_ids_json === "string" ? JSON.parse(data.sender_account_ids_json) : data.sender_account_ids_json) : [],
            timezone: data.metadata?.timezone || ""
          }))
          // Jump directly to the Sequence builder
          setStep(1)
        })
        .catch(err => {
          console.error(err)
          toast.error("Campaign not found. It may have been deleted.")
          navigate("/elein/campaigns")
        })
      return
    }

    if (params.get("resume") !== "true") return
    
    // Draft restore is handled automatically by Zustand persist!
    // But we should ensure we jump to step 1 if we were at step 0 to match old behavior
    const currentStep = useHRTreeStore.getState().campaignStep
    if (currentStep === 0 && useHRTreeStore.getState().rootNodes.length > 0) {
      setStep(1)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.search])



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
    if (isSaving) return;
    const { rootNodes } = useHRTreeStore.getState();
    const campaignName = state.campaignName?.trim() || "Untitled Campaign";

    const { errors: treeErrs } = validateTree(rootNodes);
    const criticalErrors = Object.values(treeErrs).flat();

    if (status === "DRAFT" && criticalErrors.length > 0) {
      setDraftErrors(criticalErrors);
    } else {
      setDraftErrors([]);
    }

    if (status === "ACTIVE") {
      if (rootNodes.length === 0) {
        toast.error("Cannot launch: Your sequence is empty.");
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
        return;
      }
    }

    setIsSaving(true);
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
          status
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
          await fetchWithAuth(`/api/elein/campaigns/${campaignIdToEnroll}/enroll_list`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              list_id: state.leadListId,
              excludeOtherCampaigns: state.excludeOtherCampaigns || false,
              excludeOtherSenders: state.excludeOtherSenders || false,
              excludeSameSender: state.excludeSameSender || false
            })
          });
        } catch (enrollErr) {
          console.error("Failed to enroll list", enrollErr);
        }
      }

      toast.success(status === "ACTIVE" ? `Campaign "${campaignName}" launched!` : `Campaign "${campaignName}" saved as draft.`, {
        description: "You can find it in your Campaigns dashboard."
      });
      // Clear the local draft so the "Unsaved Draft" banner doesn't reappear
      
      useHRTreeStore.getState().reset();
      mutate("/api/elein/dashboard/stats");
      navigate("/elein/campaigns");
    } catch (e: any) {
      const msg = e instanceof Error ? e.message : String(e)
      if (e instanceof TypeError || (e instanceof Error && e.name === 'AbortError') || msg === 'Failed to fetch' || msg.includes('ERR_CONNECTION_REFUSED') || msg.includes('NetworkError')) {
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
    if (step === 0) {
      if (!state.campaignName || !state.campaignName.trim()) {
        toast.error("Please enter a campaign name")
        return
      }
    }
    if (step === 1) {
      const { rootNodes } = useHRTreeStore.getState()
      if (rootNodes.length === 0) {
        toast.error("Please choose a starting option or add at least one node.", {
          position: "top-center"
        })
        return
      }
      const { errors, warnings } = validateTree(rootNodes)
      const hasErrors = Object.values(errors).some(e => e.length > 0)
      if (hasErrors) {
        toast.error("Please fix the highlighted errors in your sequence before continuing.")
        return
      }
    }
    if (step === 2) {
      if (!state.senderIds || state.senderIds.length === 0) {
        toast.error("You must connect at least one LinkedIn sender account.")
        return
      }
    }
    if (step < STEPS.length - 1) setStep(step + 1)
  }

  const handleStateChange = (k: string, v: any) => {
    setState((prev: any) => ({ ...prev, [k]: v }))
  }

  return (
    <div className="h-[100dvh] bg-background text-foreground flex flex-col overflow-hidden relative">
      <div className="absolute inset-0 z-0 pointer-events-none opacity-40 mix-blend-screen">
        <BackgroundBeams />
      </div>

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
          <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
            <motion.div
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.96 }}
              className="w-full max-w-md rounded-2xl bg-background border border-destructive/50 shadow-2xl overflow-hidden p-6"
            >
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-full bg-destructive/10 flex items-center justify-center shrink-0">
                  <AlertTriangle className="text-destructive" size={20} />
                </div>
                <div>
                  <h2 className="text-lg font-bold text-foreground">Cannot Launch Campaign</h2>
                  <p className="text-xs text-muted-foreground">Please fix the following errors:</p>
                </div>
              </div>
              <ul className="bg-destructive/5 rounded-xl border border-destructive/20 p-4 space-y-2 mb-6 max-h-60 overflow-y-auto">
                {activationErrors.map((err, i) => (
                  <li key={i} className="text-xs text-destructive flex gap-2">
                    <span className="shrink-0">•</span> <span>{err}</span>
                  </li>
                ))}
              </ul>
              <div className="flex justify-end">
                <button
                  onClick={() => setActivationErrors([])}
                  className="px-5 py-2.5 bg-foreground text-background font-bold text-xs rounded-xl hover:bg-foreground/90 transition-all"
                >
                  Close & Fix Errors
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

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
            {step === 0 && (
              <div className="flex-1 overflow-auto p-8 relative z-10 flex flex-col items-center justify-center min-h-0">
                <div className="w-full max-w-4xl mx-auto flex flex-col items-center justify-center">
                  <div className="mb-10 text-center">
                    <h1 className="text-4xl font-light tracking-tight text-foreground mb-3">Campaign Setup</h1>
                    <p className="text-base text-muted-foreground">Give your campaign a name and select your target audience.</p>
                  </div>
                  <div className="w-full">
                    <StepLeads state={state} onChange={handleStateChange} onNext={handleNext} />
                  </div>
                </div>
              </div>
            )}
            {step === 1 && <StepSequence onSave={() => handleSaveDraft("DRAFT")} />}
            {step === 2 && <StepSenders state={state} onChange={handleStateChange} />}
            {step === 3 && <StepSchedule state={state} onChange={handleStateChange} />}
            {step === 4 && <StepPreview state={state} onChange={handleStateChange} />}
          </motion.div>
        </AnimatePresence>
      </div>

      {/* Footer Navigation */}
      {(true) && (
        <div className="relative z-10 flex items-center justify-between p-6 border-t border-border/50 bg-background/50 backdrop-blur-md shrink-0">
          <div className="text-sm text-muted-foreground">
            Step {step + 1} of {STEPS.length}
          </div>
          <button
            onClick={step === STEPS.length - 1 ? () => handleSaveDraft("ACTIVE") : handleNext}
            disabled={isSaving}
            className="flex items-center gap-2 bg-primary hover:bg-primary/90 text-primary-foreground px-6 py-2.5 rounded-xl font-semibold transition-all shadow-xl shadow-primary/10 hover:shadow-primary/20 active:scale-95 disabled:opacity-50"
          >
            {step === STEPS.length - 1 ? (
              isSaving ? <><svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-background" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> Launching...</> : <><Zap size={16} className="text-warning fill-warning" /> Launch Campaign</>
            ) : (
              <>Continue <ArrowRight size={16} /></>
            )}
          </button>
        </div>
      )}
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
