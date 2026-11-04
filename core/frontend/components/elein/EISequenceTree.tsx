import { EIStickyNote } from "./EIStickyNote";
import { CampaignBlueprintModal } from "./CampaignBlueprintModal";
import { DAGSimulationDrawer } from "./DAGSimulationDrawer";
import { 
  parseBlueprintFile, 
  sniffDroppedFile, 
  exportBlueprint, 
  downloadBlueprintFile, 
  copyBlueprintToClipboard, 
  saveCanvasSnapshot, 
  prepareImportNodes,
  type EleInBlueprint 
} from "@/lib/blueprintSchema";
import React from "react";
import { cn } from "@/lib/utils"
import { ElesiumLogo } from "@/components/ElesiumLogo"

import { useState, useCallback, useRef, useEffect } from "react"
import { AnimatePresence, motion } from "motion/react"
import { DotPattern } from "@/components/ui/dot-pattern"
import {
  Plus, Check, X, Clock, Trash2, Edit2,
  UserPlus, MessageSquare, Eye, Heart, Users, Mail,
  AtSign, Zap, CheckCircle2, Shield, StopCircle, AlertCircle,
  Phone, CalendarCheck, Star, Mic2, Tag, Bell, Database, Info, ZoomIn, ZoomOut, Maximize, Undo, Redo, FileText, Save,
  Lock, Sparkles, ShieldCheck, AlertTriangle, Layers, Flame, Search, ArrowRight, StickyNote, Download, Upload,
  ChevronDown, Copy, FileCode
} from "lucide-react"
import useSWR, { useSWRConfig } from "swr"
import { fetcher, fetchWithAuth } from "@/lib/apiClient"
import { toast } from "sonner"
import { usePaywall } from "@/contexts/PaywallContext"
import { HR_NODE_DEFS } from "@/lib/eiNodeDefs"
import type { EINodeType } from "@/lib/eiNodeDefs"
import { useHRTreeStore, type SeqTreeNode, dagToTree } from "@campaigns/eiTreeStore"
import { HR_TEMPLATES } from "@/lib/eiTemplates"
import { validateTree } from "@/lib/treeValidator"
import { EITreeNodeConfigPanel, hasAutoWithdrawConnection } from "./EINodeConfigPanel"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

import { create } from "zustand"

type PickerState = {
  isOpen: boolean;
  parentId: string | null;
  branchLabel: string;
  isFirstStep: boolean;
  openPicker: (parentId: string | null, branchLabel: string, isFirstStep: boolean) => void;
  closePicker: () => void;
}

export const usePickerStore = create<PickerState>((set) => ({
  isOpen: false,
  parentId: null,
  branchLabel: "then",
  isFirstStep: false,
  openPicker: (parentId, branchLabel, isFirstStep) => set({ isOpen: true, parentId, branchLabel, isFirstStep }),
  closePicker: () => set({ isOpen: false })
}))

// ─── Icon map ──────────────────────────────────────────────────────────────────
const NODE_ICONS: Record<string, any> = {
  // Warm-up
  view_profile: Eye, follow_profile: Users,
  like_post: Heart, comment_on_post: MessageSquare,
  endorse_skill: CheckCircle2, follow_company: Users, 
  share_post: Heart, invite_to_event: Bell,
  // Connect
  connection_request: UserPlus, withdraw_request: UserPlus,
  remove_connection: UserPlus,
  // Conditions
  if_connected: CheckCircle2, if_replied: MessageSquare,
  seamless_identity_matching: ShieldCheck,
  if_email_found: AtSign, if_phone_found: Phone, open_profile_check: Shield,
  if_premium_member: Star, if_large_following: Users, if_mutual_connections: Users,
  if_recently_active: Zap, if_has_recent_posts: MessageSquare,
  if_company_hiring: Zap, icp_score_gate: CheckCircle2,
  if_meeting_booked: CalendarCheck, if_request_pending: Clock,
  if_lead_matches: Shield,
  if_email_opened: Eye, if_email_clicked: Zap,
  if_email_bounced: AlertTriangle, if_connection_accepted: CheckCircle2,
  // Messages
  send_message: MessageSquare, send_ai_message: ElesiumLogo,
  send_voice_note: Mic2, send_inmail: Mail, send_paid_inmail: Mail,
  fallback_to_inmail: Mail,
  // AI
  ai_personalize: ElesiumLogo, ai_detect_sentiment: ElesiumLogo,
  ai_generate_icebreaker: ElesiumLogo, ai_translate_message: ElesiumLogo,
  ai_score_icp: ElesiumLogo, ai_buying_signal: ElesiumLogo,
  ai_summarize_profile: ElesiumLogo, ai_detect_competitor: ElesiumLogo, 
  ai_best_send_time: ElesiumLogo, ai_query_knowledge_base: ElesiumLogo,
  // Enrichment
  zero_cost_discovery: Zap,
  find_email: AtSign, find_personal_email: AtSign, find_phone: Phone,
  find_tech_stack: Database, find_funding_round: Zap,
  find_headcount: Users, find_job_postings: Zap,
  get_linkedin_activity: Star, get_mutual_connections: Users,
  verify_email: CheckCircle2,
  // Multichannel
  push_to_crm: Database, add_to_email_sequencer: Zap,
  send_slack_alert: Bell, send_webhook: Zap,
  retarget_omnichannel: Layers,
  // Convert
  update_lead_status: CheckCircle2, send_meeting_invite: CalendarCheck, 
  send_intro_call_invite: Phone,
  // Control
  ab_split: Zap, weighted_split: Zap, daily_limit_check: Shield,
  blacklist_check: Shield, add_tag: Tag, sequence_end: CheckCircle2,
  retry_step: Clock,
}

// ─── Node picker panel ─────────────────────────────────────────────────────────
// Context-aware: first step vs subsequent steps

const FIRST_STEP_NODES: [string, string][] = [
  ["warmup",       "view_profile"],
  ["warmup",       "like_post"],
  ["warmup",       "comment_on_post"],
  ["connect",      "connection_request"],
  ["messages",     "send_inmail"],
  ["messages",     "send_email"],
  ["ai",           "ai_personalize"],
  ["enrichment",   "zero_cost_discovery"],
  ["enrichment",   "find_email"],
  ["conditions",   "icp_score_gate"],
  ["conditions",   "if_recently_active"],
  ["conditions",   "if_email_found"],
  ["conditions",   "if_has_recent_posts"],
  ["multichannel", "retarget_omnichannel"],
  ["multichannel", "add_to_email_sequencer"],
  ["multichannel", "send_webhook"],
]

const SUBSEQUENT_NODES: [string, string][] = [
  // Warmup
  ["warmup",       "view_profile"],
  ["warmup",       "like_post"],
  ["warmup",       "comment_on_post"],
  ["warmup",       "endorse_skill"],
  ["warmup",       "follow_profile"],
  ["warmup",       "follow_company"],
  ["warmup",       "share_post"],
  ["warmup",       "invite_to_event"],
  // Actions
  ["connect",      "connection_request"],
  ["connect",      "withdraw_request"],
  ["connect",      "remove_connection"],
  ["messages",     "send_message"],
  ["messages",     "send_inmail"],
  ["messages",     "send_email"],
  ["messages",     "send_paid_inmail"],
  ["messages",     "send_voice_note"],
  ["messages",     "fallback_to_inmail"],
  // Logic & Flow
  ["conditions",   "if_connected"],
  ["conditions",   "if_connection_accepted"],
  ["conditions",   "seamless_identity_matching"],
  ["conditions",   "if_replied"],
  ["conditions",   "if_email_found"],
  ["conditions",   "if_email_opened"],
  ["conditions",   "if_email_clicked"],
  ["conditions",   "if_email_bounced"],
  ["conditions",   "if_recently_active"],
  ["conditions",   "if_has_recent_posts"],
  ["conditions",   "if_meeting_booked"],
  ["conditions",   "if_lead_matches"],
  ["conditions",   "open_profile_check"],
  ["conditions",   "icp_score_gate"],
  ["conditions",   "if_company_hiring"],
  ["conditions",   "if_phone_found"],
  ["multichannel", "retarget_omnichannel"],
  ["control",      "ab_split"],
  ["control",      "daily_limit_check"],
  ["control",      "blacklist_check"],
  ["control",      "add_tag"],
  ["control",      "retry_step"],
  // AI Agents
  ["ai",           "ai_personalize"],
  ["ai",           "ai_detect_sentiment"],
  ["ai",           "ai_score_icp"],
  ["ai",           "ai_buying_signal"],
  ["ai",           "ai_query_knowledge_base"],
  ["ai",           "ai_detect_competitor"],
  // Data & Handoffs
  ["enrichment",   "zero_cost_discovery"],
  ["enrichment",   "find_email"],
  ["enrichment",   "find_personal_email"],
  ["enrichment",   "verify_email"],
  ["enrichment",   "find_tech_stack"],
  ["enrichment",   "find_funding_round"],
  ["enrichment",   "find_headcount"],
  ["enrichment",   "find_job_postings"],
  ["enrichment",   "get_linkedin_activity"],
  ["enrichment",   "get_mutual_connections"],
  ["enrichment",   "find_phone"],
  ["multichannel", "push_to_crm"],
  ["multichannel", "add_to_email_sequencer"],
  ["multichannel", "send_slack_alert"],
  ["multichannel", "send_webhook"],
  ["convert",      "update_lead_status"],
  ["convert",      "send_meeting_invite"],
  ["convert",      "send_intro_call_invite"],
]

const CAT_LABELS: Record<string, string> = {
  warmup:       "Warm-up actions",
  connect:      "Connection",
  messages:     "Direct messages",
  conditions:   "Logic & branching",
  control:      "Flow control",
  ai:           "AI agents",
  enrichment:   "Data enrichment",
  multichannel: "Data & handoffs",
  convert:      "Conversion & status",
}

const CAT_ICON_COLORS: Record<string, string> = {
  core_actions: "#3b82f6",
  conditions:   "#10b981",
  warmup:       "#06b6d4",
  connect:      "#6366f1",
  messages:     "#6366f1",
  ai:           "#f97316",
  enrichment:   "#f59e0b",
  convert:      "#f59e0b",
  multichannel: "#ec4899",
  control:      "#71717a",
}

interface PickerPanelProps {
  isFirstStep: boolean
  readOnly?: boolean
  treeErrors?: Record<string, string[]>
  treeWarnings?: Record<string, string[]>
  onPick: (type: EINodeType) => void
  onClose: () => void
}

function PickerPanel({ isFirstStep, onPick, onClose }: PickerPanelProps) {
  const nodeList = isFirstStep ? FIRST_STEP_NODES : SUBSEQUENT_NODES
  const [infoNode, setInfoNode] = useState<EINodeType | null>(null)
  const [searchQuery, setSearchQuery] = useState("")
  const { openPaywall } = usePaywall()
  const { data: billingData } = useSWR<any>('/api/elein/workspaces/billing', fetcher)
  const isWorkspacePro = billingData?.tier === 'PRO' || billingData?.tier === 'ENTERPRISE' || billingData?.tier === 'AGENCY'
  const canUseIcp = isWorkspacePro || Boolean(billingData?.tier_limits?.can_use_bayesian_icp)

  // Escape key handling
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (infoNode) {
          setInfoNode(null)
        } else {
          onClose()
        }
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [infoNode, onClose])
  
  // Group by category with search filter
  const query = searchQuery.trim().toLowerCase()
  const grouped: Record<string, string[]> = {}
  for (const [cat, type] of nodeList) {
    const def = HR_NODE_DEFS[type as EINodeType]
    if (query && def) {
      const match = def.label.toLowerCase().includes(query) || 
                    def.description.toLowerCase().includes(query) ||
                    cat.toLowerCase().includes(query)
      if (!match) continue
    }
    if (!grouped[cat]) grouped[cat] = []
    grouped[cat].push(type)
  }

  return (
    <>
      {/* Backdrop overlay */}
      <div 
        className="fixed inset-0 z-[59] bg-background/60 backdrop-blur-xs transition-opacity" 
        onClick={onClose} 
      />
      <div className="fixed inset-y-0 right-0 z-[60] pointer-events-none flex">
        <motion.div 
          initial={{ x: "100%" }}
          animate={{ x: 0 }}
          exit={{ x: "100%" }}
          transition={{ type: "spring", damping: 25, stiffness: 200 }}
          role="dialog"
          aria-modal="true"
          aria-label="Add a step to sequence"
          className={cn(
            "pointer-events-auto bg-background/95 backdrop-blur-xl shadow-2xl border-l border-border/40 flex flex-col h-full",
            "w-[380px]"
          )}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-border/40 bg-muted/10">
            <div>
              <p className="text-[15px] font-bold text-foreground tracking-tight">
                {isFirstStep ? "Build sequence" : "Add a step"}
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Select an outreach action, condition gate, or AI tool.
              </p>
            </div>
            <div className="flex items-center gap-2 pointer-events-auto">
              <button 
                type="button" 
                onClick={onClose} 
                className="text-muted-foreground hover:text-foreground transition-colors p-1.5 rounded-lg hover:bg-muted"
                aria-label="Close step picker"
              >
                <X size={18} />
              </button>
            </div>
          </div>

          {/* Search Filter Bar */}
          <div className="px-6 py-3 border-b border-border/40 bg-card">
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Filter actions, AI gates, delays..."
                className="w-full bg-background border border-border/60 rounded-lg pl-8 pr-8 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary transition-colors"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery("")}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground p-0.5"
                  aria-label="Clear search"
                >
                  <X size={12} />
                </button>
              )}
            </div>
          </div>
          
          {/* Node list */}
          <div className="flex-1 overflow-y-auto overscroll-none px-6 py-5 space-y-8">
            {Object.keys(grouped).length === 0 ? (
              <div className="py-12 text-center text-xs text-muted-foreground">
                No sequence steps found matching &quot;{searchQuery}&quot;.
              </div>
            ) : (
              Object.entries(grouped).map(([cat, types]) => (
                <div key={cat}>
                  <div className="flex items-center gap-2 mb-3">
                    {cat === 'ai' && <ElesiumLogo size={15} className="shrink-0" />}
                    <p className="text-[12px] font-bold text-foreground tracking-wide uppercase">{CAT_LABELS[cat] || cat}</p>
                    <span className="text-[10px] font-semibold text-muted-foreground bg-muted/30 border border-border/40 rounded-md px-2 py-0.5">
                      {types.length}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-2.5">
                    {types.map(type => {
                      const def = HR_NODE_DEFS[type as EINodeType]
                      if (!def) return null
                      const Icon = NODE_ICONS[type] || Zap
                      const color = CAT_ICON_COLORS[cat] || "#6366f1"
                      const isEnrichmentNode = cat === "enrichment" || type === "find_email" || type.includes("enrich") || type.includes("scrape")
                      const isIcpNode = type === "ai_score_icp" || type === "icp_score_gate"
                      const isOmniNode = type === "retarget_omnichannel" || type === "fallback_to_inmail"
                      const isAbmNode = type === "abm_committee_touch" || type === "champion_job_change"
                      const isRevivalNode = type === "boomerang_revival" || type === "competitive_displacement"
                      const isPremiumNode = isOmniNode || isAbmNode || isRevivalNode
                      const isLocked = (isEnrichmentNode && !isWorkspacePro) || (isIcpNode && !canUseIcp) || (isPremiumNode && !isWorkspacePro)
                      return (
                        <div key={type} className="relative group h-full">
                          <button
                            type="button"
                            onClick={() => {
                              if (isLocked) {
                                if (isIcpNode) {
                                  openPaywall({
                                    campaignName: "Bayesian ICP Machine Learning",
                                    featureName: def.label,
                                    reason: `Unlock ${def.label} with Growth Pro to qualify prospects probabilistically using continuous Bayesian learning.`,
                                  });
                                } else if (isOmniNode) {
                                  openPaywall({
                                    campaignName: "Omnichannel Retargeting Cascade",
                                    featureName: def.label,
                                    reason: `Unlock ${def.label} with Growth Pro to orchestrate multi-channel outreach across LinkedIn and Email.`,
                                  });
                                } else if (isAbmNode) {
                                  openPaywall({
                                    campaignName: "ABM Multithreading & Buying Committees",
                                    featureName: def.label,
                                    reason: `Unlock ${def.label} with Growth Pro to penetrate enterprise accounts with buying committee multithreading.`,
                                  });
                                } else if (isRevivalNode) {
                                  openPaywall({
                                    campaignName: "Revival & Takeover Engine",
                                    featureName: def.label,
                                    reason: `Unlock ${def.label} with Growth Pro to automatically revive lost deals and displace competitors.`,
                                  });
                                } else {
                                  openPaywall({
                                    campaignName: "Automated Data Enrichment",
                                    featureName: def.label,
                                    reason: `Unlock ${def.label} with Growth Tier to run automated multi-channel enrichment.`,
                                  });
                                }
                                return;
                              }
                              if (!(def as any).comingSoon) onPick(type as EINodeType)
                            }}
                            disabled={(def as any).comingSoon}
                            className={cn(
                              "w-full h-full flex flex-col items-start p-3.5 rounded-xl border border-border/50 bg-card text-left relative overflow-hidden transition-all duration-200 shadow-xs",
                              (def as any).comingSoon 
                                ? "opacity-60 cursor-not-allowed grayscale" 
                                : isLocked
                                ? "hover:bg-primary/5 hover:border-primary/40 group-hover:border-primary/40 cursor-pointer"
                                : "hover:bg-muted/40 hover:border-border group-hover:border-border cursor-pointer"
                            )}
                          >
                            <div
                              className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mb-2.5 border z-10 transition-colors"
                              style={{ borderColor: `${color}33`, color, background: `${color}10` }}
                            >
                              <Icon size={16} strokeWidth={1.5} />
                            </div>
                            <div className="min-w-0 z-10 flex-1 w-full relative">
                              {(def as any).comingSoon ? (
                                <span className="absolute top-0 right-0 text-[9px] font-medium tracking-wider uppercase bg-muted/50 text-muted-foreground px-1.5 py-0.5 rounded border border-border/40">
                                  Soon
                                </span>
                              ) : isLocked ? (
                                <span className="absolute top-0 right-0 text-[9px] font-bold tracking-wider uppercase bg-primary/20 text-primary px-1.5 py-0.5 rounded border border-primary/30 flex items-center gap-1 shadow-xs">
                                  <Lock size={9} /> PRO
                                </span>
                              ) : null}
                              <p className="text-[12px] font-bold text-foreground leading-tight transition-colors pr-12 flex items-center gap-1">
                                {(cat === "ai" || def.label.includes("AI")) && (
                                  <ElesiumLogo size={12} className="shrink-0" />
                                )}
                                <span className="line-clamp-1">{def.label}</span>
                              </p>
                              <p className="text-[11px] text-muted-foreground mt-1 leading-snug line-clamp-2">{def.description}</p>
                            </div>
                          </button>
                          <button
                            type="button"
                            onClick={(e) => { e.stopPropagation(); setInfoNode(type as EINodeType) }}
                            className="absolute right-2 bottom-2 p-1.5 rounded-lg bg-muted/40 text-muted-foreground hover:text-foreground hover:bg-muted/70 opacity-0 group-hover:opacity-100 transition-all z-20 cursor-pointer"
                            title="More info"
                            aria-label={`More info about ${def.label}`}
                          >
                            <Info size={13} />
                          </button>
                        </div>
                      )
                    })}
                  </div>
                </div>
              ))
            )}
          </div>

          <div className="flex-none border-t border-border/40 px-6 py-4 bg-background/80">
            <button type="button" onClick={onClose} className="w-full py-2 rounded-lg border border-border text-xs font-semibold text-foreground hover:bg-muted transition-all cursor-pointer">
              Dismiss Drawer
            </button>
          </div>

          {/* Info Popover */}
          <AnimatePresence>
            {infoNode && (
              <motion.div
                initial={{ opacity: 0, scale: 0.95, y: 10 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 10 }}
                className="absolute inset-0 z-50 flex items-center justify-center p-6 bg-background/80 backdrop-blur-xs"
                onClick={() => setInfoNode(null)}
              >
                <div 
                  className="w-full max-w-sm bg-card border border-border rounded-xl shadow-2xl overflow-hidden"
                  onClick={e => e.stopPropagation()}
                >
                  <div className="p-6 border-b border-border/40 bg-card">
                    {(() => {
                      const def = HR_NODE_DEFS[infoNode] || {
                        label: infoNode,
                        category: "actions",
                        description: "Custom sequence step imported from workflow blueprint.",
                        outputs: ["next"]
                      }
                      const Icon = NODE_ICONS[infoNode] || Zap
                      const catColor = CAT_ICON_COLORS[def.category] || "currentColor"
                      return (
                        <>
                          <div className="flex items-center justify-between mb-4">
                            <div 
                              className="w-12 h-12 rounded-xl flex items-center justify-center border"
                              style={{ 
                                color: catColor,
                                borderColor: `${catColor}40`,
                                background: `${catColor}15`
                              }}
                            >
                              <Icon size={24} />
                            </div>
                            <button type="button" onClick={() => setInfoNode(null)} className="p-2 text-muted-foreground hover:text-foreground bg-muted/50 rounded-lg transition-colors cursor-pointer" aria-label="Close info">
                              <X size={16} />
                            </button>
                          </div>
                          <h3 className="text-lg font-bold text-foreground mb-1">{def.label}</h3>
                          <div className="flex gap-2 mb-4">
                            <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground bg-muted/50 px-2 py-0.5 rounded border border-border/40">
                              {CAT_LABELS[def.category] || "Action"}
                            </span>
                          </div>
                          <p className="text-[13px] text-muted-foreground leading-relaxed">
                            {def.description}
                          </p>
                        </>
                      )
                    })()}
                  </div>
                  <div className="p-6 bg-muted/10 space-y-4">
                    <div>
                      <p className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider mb-2">Branches / Outputs</p>
                      {(() => {
                        const def = HR_NODE_DEFS[infoNode] || { outputs: ["next"] }
                        return (
                          <div className="flex flex-wrap gap-2">
                            {def.outputs?.map(out => (
                              <span key={out} className="text-xs font-semibold text-foreground bg-muted/30 border border-border/40 px-2 py-1 rounded-md">
                                {out}
                              </span>
                            ))}
                            {!def.outputs?.length && (
                              <span className="text-xs text-muted-foreground italic">None (Ends Sequence)</span>
                            )}
                          </div>
                        )
                      })()}
                    </div>
                    <button 
                      type="button"
                      onClick={() => { onPick(infoNode); setInfoNode(null) }}
                      className="w-full py-2.5 bg-primary text-primary-foreground font-bold rounded-lg hover:bg-primary/90 transition-opacity mt-2 cursor-pointer shadow-xs text-xs"
                    >
                      Add to Sequence
                    </button>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      </div>
    </>
  )
}

// ─── Add/End button pair ───────────────────────────────────────────────────────

interface AddEndPairProps {
  isFirstStep: boolean
  parentId: string | null
  branchLabel: string
  onEnd: () => void
}

function AddEndPair({ isFirstStep, parentId, branchLabel, onEnd }: AddEndPairProps) {
  const openPicker = usePickerStore(s => s.openPicker)
  const selectNode = useHRTreeStore(s => s.selectNode)
  const [showEndTip, setShowEndTip] = useState(false)

  return (
    <div className="add-step-pair flex items-center gap-2">
      <button
        type="button"
        onClick={() => openPicker(parentId, branchLabel, isFirstStep)}
        className="w-10 h-10 rounded-lg border border-border/60 bg-card/80 hover:bg-card hover:border-primary/50 hover:shadow-md flex items-center justify-center text-muted-foreground hover:text-primary transition-all shadow-sm relative z-20 cursor-pointer"
        title="Add step"
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openPicker(parentId, branchLabel, isFirstStep); } }}
      >
        <Plus size={18} />
      </button>
      <div className="relative">
        <button
          type="button"
          onClick={onEnd}
          onMouseEnter={() => setShowEndTip(true)}
          onMouseLeave={() => setShowEndTip(false)}
          className="w-10 h-10 rounded-lg border border-border/60 bg-card/80 hover:bg-card hover:border-border hover:shadow-md flex items-center justify-center text-muted-foreground hover:text-foreground transition-all shadow-sm cursor-pointer"
          title="End sequence"
        >
          <Check size={18} />
        </button>
        {showEndTip && (
          <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2.5 py-1 bg-foreground text-background text-xs rounded-lg whitespace-nowrap pointer-events-none">
            End sequence
          </div>
        )}
      </div>
    </div>
  )
}
interface NodeCardProps {
  node: SeqTreeNode
  onSelect: () => void
  analytics?: {sent: number, replied: number, reply_rate: number}
  hideDelay?: boolean
  onDelete?: () => void
  isSelected: boolean
  errors?: string[]
  warnings?: string[]
  draggable?: boolean
  onDragStart?: (e: React.DragEvent) => void
  onDragOver?: (e: React.DragEvent) => void
  onDrop?: (e: React.DragEvent) => void
  onDragEnd?: (e: React.DragEvent) => void
  isDragging?: boolean
  isDragOver?: boolean
}

function NodeCard({ node, onSelect, onDelete, isSelected, draggable, onDragStart, onDragOver, onDrop, onDragEnd, isDragging, isDragOver, analytics, hideDelay, warnings, errors }: NodeCardProps) {
  const [isEditingDelay, setIsEditingDelay] = useState(false)
  const updateNodeData = useHRTreeStore(s => s.updateNodeData)

  const def = node.type !== "sequence_end" ? HR_NODE_DEFS[node.type as EINodeType] : null
  const Icon = NODE_ICONS[node.type] || Zap
  const color = def?.color || "#52525b"
  const label = def?.label || node.data.label || node.type
  const description = def?.description || ""
  const delay = node.data.delay as number | undefined
  const isEnd = node.type === "sequence_end"

  if (isEnd) {
    return (
      <div className="node-card group relative flex items-center gap-2 px-4 py-2.5 rounded-lg bg-card border border-border/50 text-muted-foreground text-sm font-medium shadow-sm transition-colors pr-10">
        <StopCircle size={14} className="text-zinc-500" />
        <span>End sequence</span>
        
        {/* Delete Button (visible on hover) */}
        {onDelete && (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onDelete(); }}
            className="absolute right-2 opacity-0 group-hover:opacity-100 p-1.5 rounded-md bg-destructive/10 text-destructive hover:bg-destructive hover:text-destructive-foreground transition-all cursor-pointer"
            title="Remove End Node to continue sequence"
          >
            <Trash2 size={13} />
          </button>
        )}
      </div>
    )
  }

  return (
    <div
      draggable={draggable}
      onDragStart={(e) => {
        const target = e.target as HTMLElement;
        if (target.closest('button, input, select, textarea, [data-no-drag]')) {
          e.preventDefault();
          return;
        }
        onDragStart?.(e);
      }}
      onDragOver={onDragOver}
      onDrop={onDrop}
      onDragEnd={onDragEnd}
      onClick={onSelect}
      className={`node-card !p-0 group w-[320px] !rounded-xl !bg-card border transition-all duration-200 cursor-pointer shadow-sm hover:shadow-md hover:-translate-y-[2px] ${
        isSelected ? "!border-primary ring-2 ring-primary/20 shadow-md z-10" : "hover:!border-primary/50"
      } ${isDragging ? "opacity-30 scale-95" : ""} ${isDragOver ? "border-dashed !border-primary !bg-primary/5 dark:!bg-primary/10" : ""}`}
     
      style={(!isDragOver && !isSelected) ? { borderColor: `${color}45` } : {}}
    >
      {/* Delay Configurator */}
      {delay !== undefined && !hideDelay && (
        <div className="border-b border-border/40 bg-muted/10 rounded-t-xl overflow-hidden">
          <div 
            className="flex items-center justify-between px-4 py-2.5 cursor-pointer hover:bg-muted/30 transition-colors"
            onClick={(e) => {
              e.stopPropagation()
              setIsEditingDelay(!isEditingDelay)
            }}
          >
            <div className="flex items-center gap-2 text-muted-foreground">
              <Clock size={14} />
              <span className="text-[12px] font-semibold text-foreground">
                {delay === 0 ? "No delay" : `Wait ${delay} ${node.data.delayUnit || 'days'}, then`}
              </span>
            </div>
            {!isEditingDelay && (
              <button type="button" className="text-muted-foreground hover:text-foreground">
                <div className="p-1 rounded hover:bg-muted/50"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"></path></svg></div>
              </button>
            )}
          </div>
          
          {isEditingDelay && (
            <div 
              className="px-4 py-3 border-t border-border/40 bg-muted/20 flex items-center gap-3"
              onClick={e => e.stopPropagation()}
            >
              <div className="relative flex-1">
                <input 
                  type="number" 
                  min="0"
                  value={delay}
                  onChange={(e) => updateNodeData(node.id, { delay: parseInt(e.target.value) || 0 })}
                  className="w-full bg-card border border-border/60 rounded-md pl-3 pr-8 py-1.5 text-[13px] text-foreground focus:outline-none focus:border-primary font-medium"
                />
                <div className="absolute right-2 top-0 bottom-0 flex flex-col justify-center gap-0.5">
                  <button type="button" onClick={() => updateNodeData(node.id, { delay: delay + 1 })} className="text-muted-foreground hover:text-foreground"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="m18 15-6-6-6 6"/></svg></button>
                  <button type="button" onClick={() => updateNodeData(node.id, { delay: Math.max(0, delay - 1) })} className="text-muted-foreground hover:text-foreground"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="m6 9 6 6 6-6"/></svg></button>
                </div>
              </div>
              <div className="flex-1">
                <Select 
                  value={node.data.delayUnit || 'days'}
                  onValueChange={(val) => updateNodeData(node.id, { delayUnit: val })}
                >
                  <SelectTrigger size="sm" className="w-full bg-card border-border/60 text-[13px] h-8">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="minutes">Minutes</SelectItem>
                    <SelectItem value="hours">Hours</SelectItem>
                    <SelectItem value="days">Days</SelectItem>
                    <SelectItem value="weeks">Weeks</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Node body */}
      {(() => {
        const needsMessage = node.type.includes("message") || node.type.includes("inmail")
        const missingMessage = needsMessage && (!node.data?.message && !node.data?.body && !node.data?.note)
        const hasError = node.data?.error || missingMessage
        const displayColor = hasError ? "#ef4444" : color
        
        const isAiNode = def?.category === 'ai' || node.type.startsWith('ai_') || node.type.includes('brain') || node.type.includes('icebreaker')
        const noteText = node.data?.note || node.data?.message || ""
        const isConnection = node.type.includes("connection")
        const charCount = noteText.length
        const isConnWithNote = isConnection && charCount > 0
        
        return (
          <div className={`flex flex-col px-4 py-3.5 relative ${hasError ? 'bg-red-500/5' : ''}`}>
            <div className="flex items-center gap-3">
              <div
                className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0 border"
                style={{ background: `${displayColor}18`, borderColor: `${displayColor}50`, color: displayColor }}
              >
                {hasError ? (
                  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/></svg>
                ) : isAiNode ? (
                  <ElesiumLogo size={20} />
                ) : (
                  <Icon size={18} strokeWidth={1.5} />
                )}
              </div>
              <div data-no-drag className="flex-1 min-w-0 pr-6 select-text">
                <div className={hasError ? "text-[14px] font-bold text-rose-600 dark:text-rose-400 leading-tight" : "text-[14px] font-bold text-foreground leading-tight flex items-center gap-1.5"}>
                  <span>{label}</span>
                  {isAiNode && (
                     <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-primary/10 text-primary border border-primary/20 shrink-0">
                      Elesium
                    </span>
                  )}
                </div>
                <p className={hasError ? "text-[12px] font-semibold text-rose-600/90 dark:text-rose-400/90 mt-0.5" : "text-[12px] text-muted-foreground mt-0.5 leading-snug line-clamp-2 max-w-[210px]"}>
                  {hasError ? "Action required" : description}
                </p>
              </div>
              
              {onDelete && (
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); onDelete(); }}
                  className="absolute right-3 opacity-0 group-hover:opacity-100 p-1.5 rounded-lg bg-destructive/10 text-destructive hover:bg-destructive hover:text-destructive-foreground transition-colors z-20 cursor-pointer"
                  title="Delete node"
                >
                  <Trash2 size={13} />
                </button>
              )}
            </div>

            {/* Real-time Connection Note Safe Character Budget Bar */}
            {isConnWithNote && (
              <div className="mt-2.5 pt-2 border-t border-border/40 flex items-center justify-between text-[11px]">
                <div className="flex items-center gap-1.5 font-mono text-[10px]">
                  <span className={cn(
                    "font-bold",
                    charCount > 300 ? "text-destructive" :
                    charCount > 240 ? "text-amber-600 dark:text-amber-400" :
                    "text-emerald-600 dark:text-emerald-400"
                  )}>
                    {charCount}
                  </span>
                  <span className="text-muted-foreground">/ 300 chars</span>
                </div>
                <div className="w-24 h-1.5 rounded-full bg-muted overflow-hidden">
                  <div 
                    className={cn(
                      "h-full rounded-full transition-all",
                      charCount > 300 ? "bg-destructive" :
                      charCount > 240 ? "bg-amber-500" :
                      "bg-emerald-500"
                    )}
                    style={{ width: `${Math.min(100, (charCount / 300) * 100)}%` }}
                  />
                </div>
              </div>
            )}

            {analytics && (
              <div className="mt-3 flex items-center gap-4 pt-3 border-t border-border/40">
                <div className="flex flex-col">
                  <span className="text-[9px] text-muted-foreground uppercase tracking-widest font-bold">Sent</span>
                  <span className="text-xs font-semibold text-foreground">{analytics.sent}</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-[9px] text-muted-foreground uppercase tracking-widest font-bold">Replied</span>
                  <span className="text-xs font-semibold text-foreground">{analytics.replied}</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-[9px] text-primary uppercase tracking-widest font-bold">Rate</span>
                  <span className="text-xs text-primary font-semibold">{analytics.reply_rate}%</span>
                </div>
              </div>
            )}

            {errors && errors.length > 0 && (
              <div className="mt-3 text-xs bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-900/40 p-3 rounded-lg flex flex-col gap-2">
                <div className="font-semibold text-rose-700 dark:text-rose-400 flex items-center gap-1.5 text-[11px] tracking-wide uppercase">
                  <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                  Action Required
                </div>
                <div className="flex flex-col gap-1.5 pl-0.5">
                  {errors.map((e: string, i: number) => (
                    <div key={i} className="flex items-start gap-2 text-rose-700/90 dark:text-rose-300 text-[11px] leading-relaxed">
                      <span className="text-rose-400 dark:text-rose-500 shrink-0 font-bold">•</span>
                      <span>{e}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {warnings && warnings.length > 0 && (
              <div className="mt-2.5 text-xs">
                <div 
                  className="flex items-center justify-between gap-1.5 px-2.5 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-700 dark:text-amber-400 text-[11px] font-semibold transition-all hover:bg-amber-500/15 cursor-help"
                  title={warnings.join("\n\n")}
                >
                  <div className="flex items-center gap-1.5 min-w-0">
                    <AlertCircle className="h-3.5 w-3.5 shrink-0 text-amber-500" />
                    <span className="truncate">{warnings[0]}</span>
                  </div>
                  {warnings.length > 1 && (
                    <span className="text-[10px] bg-amber-500/20 px-1.5 py-0.2 rounded font-bold text-amber-600 dark:text-amber-300 shrink-0">
                      +{warnings.length - 1}
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>
        )
      })()}
    </div>
  )
}

// ─── Branch pill ───────────────────────────────────────────────────────────────

function BranchPill({ label }: { label: string }) {
  const norm = label.toLowerCase()
  const isPositive =
    norm === "connected" ||
    norm === "replied" ||
    norm === "booked" ||
    norm === "email found" ||
    norm === "open" ||
    norm === "success" ||
    norm === "yes" ||
    norm === "accepted" ||
    norm === "found" ||
    norm === "hiring" ||
    norm === "has mutuals" ||
    norm.includes("strong fit") ||
    norm.includes("high fit")

  const isNegative =
    norm === "no" ||
    norm === "ignored" ||
    norm === "rejected" ||
    norm === "not found" ||
    norm === "not hiring" ||
    norm === "no mutuals" ||
    norm === "unopened" ||
    norm === "bounced" ||
    norm.includes("weak fit") ||
    norm.includes("low fit") ||
    norm.includes("disqualif")

  const dotClass = isPositive
    ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.8)]"
    : isNegative
    ? "bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.8)]"
    : "bg-sky-500 shadow-[0_0_8px_rgba(14,165,233,0.8)]"

  return (
    <div className={cn(
      "branch-pill flex items-center gap-2 px-3.5 py-1.5 rounded-full text-[10px] font-bold tracking-[0.08em] uppercase border shadow-xs z-10 transition-all hover:shadow-md",
      isNegative ? "bg-rose-500/10 border-rose-500/40 text-rose-600 dark:text-rose-400 ring-1 ring-rose-500/20" :
      isPositive ? "bg-emerald-500/10 border-emerald-500/40 text-emerald-600 dark:text-emerald-400" :
      "bg-background border-border/80 text-foreground"
    )}>
      <div className={`w-2 h-2 rounded-full ${dotClass} ${isNegative ? 'animate-pulse' : ''}`} />
      <span className="font-bold">{label}</span>
    </div>
  )
}

// ─── Vertical connector line ───────────────────────────────────────────────────
function VLine({ height = 32, active = true }: { height?: number; active?: boolean }) {
  return (
    <div className="relative w-[2px] bg-zinc-300 dark:bg-zinc-600/90 mx-auto overflow-hidden rounded-full shadow-[0_0_2px_rgba(255,255,255,0.08)]" style={{ height }}>
      {active && (
        <motion.div
          className="absolute left-0 w-full bg-gradient-to-b from-transparent via-primary to-transparent shadow-[0_0_8px_hsl(var(--primary))]"
          style={{ height: Math.max(12, Math.floor(height * 0.5)) }}
          initial={{ y: -height }}
          animate={{ y: height }}
          transition={{
            duration: 2.2,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        />
      )}
    </div>
  )
}

// ─── Recursive branch renderer ─────────────────────────────────────────────────

interface BranchProps {
  nodeAnalytics?: Record<string, {sent: number, replied: number, reply_rate: number}>
  parentAnalytics?: {sent: number, replied: number, reply_rate: number}
  nodes: SeqTreeNode[]
  parentId: string | null
  branchLabel: string
  depth: number
  isFirstStep: boolean
  readOnly?: boolean
  treeErrors?: Record<string, string[]>
  treeWarnings?: Record<string, string[]>
  firstNodeRef?: React.RefObject<HTMLDivElement | null>
  onSafeDelete?: (targetNode: SeqTreeNode) => void
}

function Branch({ nodes, parentId, branchLabel, depth, isFirstStep, readOnly, nodeAnalytics, parentAnalytics, treeErrors, treeWarnings, firstNodeRef, onSafeDelete }: BranchProps ) {
  const { addRoot, addChild, endBranch, removeNode, selectNode, selectedNodeId, moveNodeInBranch, undo } = useHRTreeStore()
  const closePicker = usePickerStore(s => s.closePicker)

  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)

  const handleSafeDeleteNode = (targetNode: SeqTreeNode) => {
    if (onSafeDelete) {
      onSafeDelete(targetNode);
      return;
    }
    removeNode(targetNode.id)
    toast("Step removed from sequence", {
      action: {
        label: "Undo",
        onClick: () => undo()
      }
    })
  }

  const handleAdd = useCallback((type: EINodeType) => {
    const def = HR_NODE_DEFS[type]
    const initialDelay = def.delayDefault !== undefined && def.delayDefault >= 1 ? def.delayDefault : 1
    if (!parentId) {
      addRoot(type, { label: def.label, type, color: def.color, outputs: def.outputs, delay: initialDelay, description: def.description })
    } else {
      addChild(parentId, branchLabel, type, { label: def.label, type, color: def.color, outputs: def.outputs, delay: initialDelay, description: def.description })
    }
  }, [parentId, branchLabel, addRoot, addChild])

  const handleEnd = useCallback(() => {
    if (!parentId) return
    endBranch(parentId, branchLabel)
  }, [parentId, branchLabel, endBranch])

  const safeNodes = Array.isArray(nodes) ? nodes.filter(n => n && typeof n === "object" && n.id) : []

  if (safeNodes.length === 0) {
    return (
      <div className="flex flex-col items-center">
        <VLine height={20} active={false} />
        {readOnly ? (
          <div className="px-3 py-1 rounded-full bg-muted/40 border border-border/40 text-[10px] text-muted-foreground font-medium flex items-center gap-1.5 shadow-sm">
            <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/60" />
            End of branch
          </div>
        ) : (
          <AddEndPair isFirstStep={isFirstStep} parentId={parentId} branchLabel={branchLabel} onEnd={handleEnd} />
        )}
      </div>
    )
  }

  return (
    <div className="flex flex-col items-center">
      {safeNodes.map((node, idx) => {
        const outputsDef = HR_NODE_DEFS[node.type as EINodeType]?.outputs || node.data?.outputs
        const expectedLabels = outputsDef && outputsDef.length > 0 ? outputsDef : (node.type === "sequence_end" ? [] : ["then"])
        const actualLabels = Object.keys(node.children || {})
        const branchLabels = Array.from(new Set([...expectedLabels, ...actualLabels]))
        const isCondition = branchLabels.length > 1
        const isEnd = node.type === "sequence_end"

        return (
          <div key={node.id} ref={depth === 0 && idx === 0 ? firstNodeRef : undefined} className="flex flex-col items-center relative">
            <VLine />

            
            {/* Drop-off badge */}
            {readOnly && parentAnalytics && nodeAnalytics?.[node.id] && parentAnalytics.sent > 0 && (
              <div className="absolute -top-7 left-1/2 -translate-x-1/2 z-10 whitespace-nowrap px-2.5 py-1 rounded-lg bg-red-500/10 border border-red-500/20 text-[10px] font-bold text-red-600 dark:text-red-400 shadow-sm flex items-center gap-1.5">
                Drop-off: {Math.max(0, parentAnalytics.sent - nodeAnalytics[node.id].sent)} ({parentAnalytics.sent > 0 ? Math.round(Math.max(0, parentAnalytics.sent - nodeAnalytics[node.id].sent) / parentAnalytics.sent * 100) : '0'}%)
              </div>
            )}

            {/* The node card */}
            {isEnd ? (
              <NodeCard node={node} onSelect={() => {}} onDelete={readOnly ? undefined : () => handleSafeDeleteNode(node)} isSelected={false} analytics={nodeAnalytics?.[node.id]} errors={treeErrors?.[node.id]} warnings={treeWarnings?.[node.id]} hideDelay={depth === 0 && idx === 0} />
            ) : (
              <NodeCard
                node={node}
                hideDelay={depth === 0 && idx === 0}
                onSelect={() => { selectNode(node.id); closePicker(); }}
                onDelete={readOnly ? undefined : () => handleSafeDeleteNode(node)}
                isSelected={node.id === selectedNodeId}
                errors={treeErrors?.[node.id]} warnings={treeWarnings?.[node.id]}
                draggable={!readOnly}
                onDragStart={(e) => {
                  e.dataTransfer.setData('text/plain', idx.toString())
                  e.dataTransfer.effectAllowed = 'move'
                  setDragIndex(idx)
                }}
                onDragOver={(e) => {
                  e.preventDefault()
                  e.dataTransfer.dropEffect = 'move'
                  if (dragIndex !== null && dragIndex !== idx) {
                    setHoverIndex(idx)
                  }
                }}
                onDrop={(e) => {
                  e.preventDefault()
                  if (dragIndex !== null && dragIndex !== idx) {
                    moveNodeInBranch(parentId, branchLabel, dragIndex, idx)
                  }
                  setDragIndex(null)
                  setHoverIndex(null)
                }}
                onDragEnd={() => {
                  setDragIndex(null)
                  setHoverIndex(null)
                }}
                isDragging={dragIndex === idx}
                isDragOver={hoverIndex === idx}
              />
            )}

            {/* If this is a condition node, use spine layout */}
            {isCondition && !isEnd && (
              <div className="flex flex-col items-center relative">
                <VLine height={24} />
                <div className="relative flex flex-row items-start justify-center" style={{ gap: "2rem" }}>

                  {branchLabels.map((bl, i) => {
                    const norm = bl.toLowerCase();
                    const isFallback = norm === "ignored" || norm === "not_replied" || norm === "unopened" || norm === "bounced" || norm === "timeout" || norm === "closed" || norm.includes("weak fit") || norm.includes("disqualif");
                    return (
                    <div key={bl} className="relative flex flex-col items-center min-w-[320px] flex-1">
                      {branchLabels.length > 1 && (
                        <div 
                          className={cn(
                            "absolute top-0 h-[2px] z-0",
                            isFallback ? "border-t-2 border-dashed border-rose-500/60 dark:border-rose-400/60" : "bg-zinc-300 dark:bg-zinc-600/90 shadow-[0_0_2px_rgba(255,255,255,0.08)]"
                          )}
                          style={{
                            left: i === 0 ? '50%' : '-1rem',
                            right: i === branchLabels.length - 1 ? '50%' : '-1rem'
                          }}
                        />
                      )}
                      {/* Vertical line dropping down to the pill */}
                      <div className={cn(
                        "w-[2px] h-4 z-0 shadow-[0_0_2px_rgba(255,255,255,0.08)]",
                        isFallback ? "border-l-2 border-dashed border-rose-500/60 dark:border-rose-400/60" : "bg-zinc-300 dark:bg-zinc-600/90"
                      )} />
                      
                      <div className="relative z-10 bg-background rounded-full">
                        <BranchPill label={bl} />
                      </div>
                      
                      <Branch
                        nodes={(node.children || {})[bl] || []}
                        parentId={node.id}
                        branchLabel={bl}
                        depth={depth + 1}
                        isFirstStep={false}
                        readOnly={readOnly}
                        treeErrors={treeErrors}
                        treeWarnings={treeWarnings}
                        nodeAnalytics={nodeAnalytics}
                        parentAnalytics={nodeAnalytics?.[node.id]}
                        onSafeDelete={onSafeDelete}
                      />
                    </div>
                  );
                })}
                </div>
              </div>
            )}

            {/* Linear continuation */}
            {!isCondition && !isEnd && idx === nodes.length - 1 && (
              <div className="flex flex-col items-center">
                {/* The single child branch */}
                <Branch
                  nodes={(node.children || {})["then"] || []}
                  parentId={node.id}
                  branchLabel="then"
                  depth={depth + 1}
                  isFirstStep={false}
                  readOnly={readOnly}
                  treeErrors={treeErrors}
                  treeWarnings={treeWarnings}
                  nodeAnalytics={nodeAnalytics}
                  parentAnalytics={nodeAnalytics?.[node.id]}
                  onSafeDelete={onSafeDelete}
                />
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ─── Quick Architecture Presets ────────────────────────────────────────────────
const QUICK_PRESETS = [
  {
    id: "3_touch_followup",
    name: "3-Touch Followup",
    badge: "42% Reply Rate",
    description: "Connect → Value Message → Calibrated Bump",
    icon: Sparkles,
    color: "from-blue-500/10 to-indigo-500/10 border-blue-500/30 text-blue-600 dark:text-blue-400",
    getNodes: (): SeqTreeNode[] => {
      const template = HR_TEMPLATES.find(t => t.id === "get_customers")
      if (template) return dagToTree(template.nodes, template.edges)
      return []
    }
  },
  {
    id: "warmup_connect",
    name: "Warmup & Connect",
    badge: "100% Safe Zone",
    description: "Profile View → Safe Connection Request",
    icon: ShieldCheck,
    color: "from-emerald-500/10 to-teal-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400",
    getNodes: (): SeqTreeNode[] => [
      {
        id: "w_1",
        type: "view_profile" as any,
        data: { label: "View Profile", delay: 0 },
        children: {
          then: [
            {
              id: "w_2",
              type: "connection_request" as any,
              data: {
                label: "Connection Request",
                note_strategy: "No note (Higher acceptance)",
                delay: 1,
                withdraw_enabled: true,
                withdraw_days: 14
              },
              children: {
                Accepted: [
                  {
                    id: "w_3",
                    type: "send_message" as any,
                    data: {
                      label: "Friendly Value Intro",
                      body: "Hi {{first_name|there}}, glad to connect! How is everything going at {{company|your team}}?",
                      delay: 2
                    },
                    children: { then: [] }
                  }
                ],
                "Not Accepted": []
              }
            }
          ]
        }
      }
    ]
  },
  {
    id: "recruiting_outreach",
    name: "Talent Acquisition",
    badge: "55% Acceptance",
    description: "High-Response Outreach for Key Hires",
    icon: Flame,
    color: "from-amber-500/10 to-orange-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400",
    getNodes: (): SeqTreeNode[] => {
      const template = HR_TEMPLATES.find(t => t.id === "hire_people")
      if (template) return dagToTree(template.nodes, template.edges)
      return []
    }
  }
]

// ─── Tree Lookup Helper ────────────────────────────────────────────────────────
function findNodeInTree(nodes: SeqTreeNode[], id: string): SeqTreeNode | null {
  for (const n of nodes) {
    if (n.id === id) return n;
    if (n.children) {
      for (const branch of Object.values(n.children)) {
        if (Array.isArray(branch)) {
          const found = findNodeInTree(branch, id);
          if (found) return found;
        }
      }
    }
  }
  return null;
}

// ─── Root: Sequence Tree ───────────────────────────────────────────────────────

export function EISequenceTree({ 
  readOnly = false, 
  initialNodes,
  nodeAnalytics,
  onSave,
  onTemplatesClick
}: { 
  readOnly?: boolean
  initialNodes?: SeqTreeNode[]
  treeErrors?: Record<string, string[]>
  treeWarnings?: Record<string, string[]>, 
  nodeAnalytics?: Record<string, {sent: number, replied: number, reply_rate: number}>,
  onSave?: (nodes: SeqTreeNode[]) => void | Promise<void>,
  onTemplatesClick?: () => void
}) {
  const storeRootNodes = useHRTreeStore(s => s.rootNodes)
  const rootNodes = (readOnly && initialNodes !== undefined) ? initialNodes : storeRootNodes
  const { addRoot, addChild, stickyNotes, addStickyNote, loadTree, formState } = useHRTreeStore()
  const updateNodeData = useHRTreeStore(s => s.updateNodeData)
  const historyLength = useHRTreeStore(s => s.history.length)
  const futureLength = useHRTreeStore(s => s.future.length)
  const undo = useHRTreeStore(s => s.undo)
  const redo = useHRTreeStore(s => s.redo)
  const picker = usePickerStore()
  const [zoom, setZoom] = useState(1)
  const [isSaving, setIsSaving] = useState(false)
  const [conflictModalOpen, setConflictModalOpen] = useState(false)
  const [pendingAddParams, setPendingAddParams] = useState<{type: EINodeType, data: any, parentId: string | null, branchLabel: string} | null>(null)
  const [presetModalOpen, setPresetModalOpen] = useState(false)
  const [selectedPreset, setSelectedPreset] = useState<typeof QUICK_PRESETS[0] | null>(null)
  const [nodeToDelete, setNodeToDelete] = useState<SeqTreeNode | null>(null)
  const selectedNodeId = useHRTreeStore(s => s.selectedNodeId)

  // Blueprint Export/Import Engine State
  const [isBlueprintModalOpen, setIsBlueprintModalOpen] = useState(false)
  const [blueprintModalTab, setBlueprintModalTab] = useState<"gallery" | "export" | "import" | "vault">("export")
  const [preloadedBlueprint, setPreloadedBlueprint] = useState<EleInBlueprint | null>(null)
  const [isDraggingBlueprintFile, setIsDraggingBlueprintFile] = useState(false)
  const [showExportMenu, setShowExportMenu] = useState(false)
  const [showImportMenu, setShowImportMenu] = useState(false)
  const canvasFileInputRef = useRef<HTMLInputElement>(null)
  const exportMenuRef = useRef<HTMLDivElement>(null)
  const importMenuRef = useRef<HTMLDivElement>(null)
  const dragCounterRef = useRef(0)

  // Multi-Channel DAG Simulation Studio State
  const [isSimulationDrawerOpen, setIsSimulationDrawerOpen] = useState(false)
  const [simulationResult, setSimulationResult] = useState<any>(null)
  const [isSimulating, setIsSimulating] = useState(false)

  // Close export & import dropdowns on outside pointerdown or Escape
  useEffect(() => {
    if (!showExportMenu && !showImportMenu) return
    const handleClickOutside = (e: PointerEvent) => {
      if (exportMenuRef.current && !exportMenuRef.current.contains(e.target as Node)) {
        setShowExportMenu(false)
      }
      if (importMenuRef.current && !importMenuRef.current.contains(e.target as Node)) {
        setShowImportMenu(false)
      }
    }
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setShowExportMenu(false)
        setShowImportMenu(false)
      }
    }
    document.addEventListener("pointerdown", handleClickOutside)
    document.addEventListener("keydown", handleKeyDown)
    return () => {
      document.removeEventListener("pointerdown", handleClickOutside)
      document.removeEventListener("keydown", handleKeyDown)
    }
  }, [showExportMenu, showImportMenu])

  // Direct 1-click export JSON (Universal format)
  const handleQuickExportJson = () => {
    try {
      if (rootNodes.length === 0) {
        toast.info("Sequence canvas is empty. Add steps to your sequence before exporting.")
        setShowExportMenu(false)
        return
      }
      const campaignName = formState?.campaignName || "Campaign Sequence"
      const bp = exportBlueprint(rootNodes, stickyNotes, {
        name: campaignName,
        description: "Exported sequence blueprint",
        version: "1.0.0"
      }, { sanitize: true, includeStickyNotes: true })

      downloadBlueprintFile(bp, `${campaignName}.json`, "json")
      toast.success(`Exported "${campaignName}.json" (${rootNodes.length} steps)`)
      setShowExportMenu(false)
    } catch (err: any) {
      toast.error("Failed to export sequence", { description: err.message || "An unexpected error occurred." })
    }
  }

  // Direct 1-click export .elein (Native format)
  const handleQuickExportElein = () => {
    try {
      if (rootNodes.length === 0) {
        toast.info("Sequence canvas is empty. Add steps to your sequence before exporting.")
        setShowExportMenu(false)
        return
      }
      const campaignName = formState?.campaignName || "Campaign Sequence"
      const bp = exportBlueprint(rootNodes, stickyNotes, {
        name: campaignName,
        description: "Exported sequence blueprint",
        version: "1.0.0"
      }, { sanitize: true, includeStickyNotes: true })

      downloadBlueprintFile(bp, `${campaignName}.elein`, "elein")
      toast.success(`Exported "${campaignName}.elein" (${rootNodes.length} steps)`)
      setShowExportMenu(false)
    } catch (err: any) {
      toast.error("Failed to export sequence", { description: err.message || "An unexpected error occurred." })
    }
  }

  // Direct 1-click copy JSON to clipboard
  const handleQuickCopyJson = async () => {
    try {
      if (rootNodes.length === 0) {
        toast.info("Sequence canvas is empty.")
        setShowExportMenu(false)
        return
      }
      const campaignName = formState?.campaignName || "Campaign Sequence"
      const bp = exportBlueprint(rootNodes, stickyNotes, {
        name: campaignName,
        description: "Exported sequence blueprint",
        version: "1.0.0"
      }, { sanitize: true, includeStickyNotes: true })

      const ok = await copyBlueprintToClipboard(bp)
      if (ok) {
        toast.success("Copied sequence blueprint JSON to clipboard!")
      } else {
        toast.error("Failed to copy JSON to clipboard")
      }
      setShowExportMenu(false)
    } catch (err: any) {
      toast.error("Failed to copy sequence", { description: err.message || "An unexpected error occurred." })
    }
  }

  // Phase S: Multi-Channel Sequence DAG Simulation Sandbox
  const handleRunSimulation = async () => {
    try {
      const { treeToDag } = await import("@campaigns/eiTreeStore");
      const { nodes, edges } = treeToDag(rootNodes);
      if (!nodes || nodes.length === 0) {
        toast.info("Sequence canvas is empty. Add steps to your sequence before running simulation.");
        return;
      }
      setIsSimulating(true);
      toast.info("Simulating Sequence DAG execution...");
      const res = await fetchWithAuth("/api/elein/campaigns/simulate-dag", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          dag: { nodes, edges }
        })
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || "Simulation failed");
        setIsSimulating(false);
        return;
      }
      const data = await res.json();
      setSimulationResult(data);
      setIsSimulationDrawerOpen(true);
      setIsSimulating(false);

      const dispatches = data.simulation_summary?.total_dispatches ?? data.summary?.total_dispatches ?? 0;
      const days = data.simulation_summary?.timeline_span_days ?? data.summary?.timeline_span_days ?? 0;
      const collisions = data.simulation_summary?.collisions_detected ?? data.summary?.collisions_detected ?? 0;
      const coverage = data.token_resolution_report?.resolution_percentage ?? data.token_resolution_coverage?.resolution_percentage ?? 100;
      if (collisions > 0) {
        toast.warning(`Simulation Complete: ${dispatches} steps across ~${days}d. ${collisions} pacing collision(s) detected. Token coverage: ${coverage}%.`);
      } else {
        toast.success(`Simulation Complete: ${dispatches} steps across ~${days}d with zero collisions. Token coverage: ${coverage}%.`);
      }
    } catch (e: any) {
      setIsSimulating(false);
      toast.error(e?.message || "Failed to execute DAG simulation.");
    }
  };

  // Direct 1-click file selector import (Zero modal friction)
  const handleDirectCanvasFileInput = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    e.target.value = "" // Reset for re-selection

    try {
      const blueprint = await parseBlueprintFile(file)
      const bpName = blueprint.metadata?.name || file.name
      // Save safety snapshot in vault
      saveCanvasSnapshot(rootNodes, stickyNotes, `Pre-import: ${bpName}`)
      const prevRoots = [...rootNodes]
      const prevNotes = [...stickyNotes]

      const { nodes: importedRoots, stickyNotes: importedNotes } = prepareImportNodes(
        blueprint,
        rootNodes,
        stickyNotes,
        "replace"
      )

      loadTree(importedRoots, importedNotes)
      toast.success(`Imported blueprint "${bpName}" (${importedRoots.length} steps)`, {
        action: {
          label: "Undo",
          onClick: () => {
            loadTree(prevRoots, prevNotes)
            toast.info("Import reverted.")
          }
        },
        duration: 9000
      })
    } catch (err: any) {
      toast.error("Failed to import blueprint", {
        description: err.message || "Invalid blueprint structure.",
        action: {
          label: "Open Studio",
          onClick: () => {
            setBlueprintModalTab("import")
            setIsBlueprintModalOpen(true)
          }
        }
      })
    }
  }

  const handleCanvasFileDrop = async (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounterRef.current = 0
    setIsDraggingBlueprintFile(false)

    const file = e.dataTransfer.files?.[0]
    if (!file) return

    // Layer 2 Paranoia: Intelligent file sniffer
    const sniffed = await sniffDroppedFile(file)

    if (sniffed.type === "leads_csv") {
      toast.error("Lead List detected", {
        description: "You dropped a CSV / spreadsheet. Prospect lead lists are imported under Campaign Audience step or the Lead Lists page.",
        duration: 7000,
      })
      return
    }

    if (sniffed.type === "image") {
      toast.error("Image file detected", {
        description: "Ele-in canvas accepts .elein and .json workflow blueprints. For image attachments, configure individual message steps.",
        duration: 6000,
      })
      return
    }

    if (sniffed.type === "unknown") {
      toast.error("Unsupported file format", {
        description: sniffed.guidance || "Please drop an .elein or .json workflow blueprint file.",
        duration: 6000,
      })
      return
    }

    try {
      const blueprint = await parseBlueprintFile(file)
      setPreloadedBlueprint(blueprint)
      setBlueprintModalTab("import")
      setIsBlueprintModalOpen(true)
      toast.success(`Loaded blueprint: "${blueprint.metadata?.name || 'Workflow Blueprint'}"`)
    } catch (err: any) {
      toast.error("Failed to parse blueprint", {
        description: err.message || "Invalid blueprint file structure.",
      })
    }
  }

  const handleSafeDeleteNode = React.useCallback((targetNode: SeqTreeNode) => {
    const hasChildren = Object.values(targetNode.children || {}).some(branch => (branch as any[])?.length > 0)
    if (hasChildren) {
      setNodeToDelete(targetNode)
      return
    }
    useHRTreeStore.getState().removeNode(targetNode.id)
    toast("Step removed from sequence", {
      action: {
        label: "Undo",
        onClick: () => useHRTreeStore.getState().undo()
      }
    })
  }, [])

  const containerRef = React.useRef<HTMLDivElement>(null)
  const contentWrapperRef = React.useRef<HTMLDivElement>(null)
  const startNodeRef = React.useRef<HTMLDivElement>(null)
  const firstNodeRef = React.useRef<HTMLDivElement>(null)
  const isDragging = React.useRef(false)
  const lastMousePos = React.useRef({ x: 0, y: 0 })

  const fitToCanvas = React.useCallback(() => {
    if (!containerRef.current || !contentWrapperRef.current) return;
    const container = containerRef.current;
    const wrapper = contentWrapperRef.current;

    const viewportW = container.clientWidth;
    const viewportH = container.clientHeight;
    if (viewportW <= 0 || viewportH <= 0) return;

    // Structure elements that define the rendered DAG boundaries
    const selector = '.node-card, .sticky-note, .sequence-start-node, .add-step-pair, .branch-pill';
    const elements = Array.from(wrapper.querySelectorAll(selector)) as HTMLElement[];

    const currentZoom = zoom || 1;
    const wrapperRect = wrapper.getBoundingClientRect();

    let minRelX = Infinity;
    let maxRelX = -Infinity;
    let minRelY = Infinity;
    let maxRelY = -Infinity;

    try {
      if (elements.length > 0) {
        elements.forEach(el => {
          const r = el.getBoundingClientRect();
          if (!r || (r.width === 0 && r.height === 0)) return;
          const left = (r.left - wrapperRect.left) / currentZoom;
          const right = (r.right - wrapperRect.left) / currentZoom;
          const top = (r.top - wrapperRect.top) / currentZoom;
          const bottom = (r.bottom - wrapperRect.top) / currentZoom;

          if (isFinite(left) && left < minRelX) minRelX = left;
          if (isFinite(right) && right > maxRelX) maxRelX = right;
          if (isFinite(top) && top < minRelY) minRelY = top;
          if (isFinite(bottom) && bottom > maxRelY) maxRelY = bottom;
        });
      }
    } catch (err) {
      console.warn("Failed measuring tree geometry for fitToCanvas:", err);
    }

    if (!isFinite(minRelX) || !isFinite(maxRelX) || !isFinite(minRelY) || !isFinite(maxRelY)) {
      minRelX = 0;
      maxRelX = wrapper.offsetWidth || 400;
      minRelY = 0;
      maxRelY = wrapper.offsetHeight || 300;
    }

    const structureW = Math.max(maxRelX - minRelX, 50);
    const structureH = Math.max(maxRelY - minRelY, 50);
    const centerRelX = (minRelX + maxRelX) / 2;
    const centerRelY = (minRelY + maxRelY) / 2;

    // Viewport padding in pixels: 240px horizontal clearance accounts for the left floating toolbar (180px + margin)
    const paddingX = 240;
    const paddingY = 160;
    const availW = Math.max(viewportW - paddingX, 100);
    const availH = Math.max(viewportH - paddingY, 100);

    const targetZoom = Math.min(availW / structureW, availH / structureH);
    if (isNaN(targetZoom) || !isFinite(targetZoom)) return;

    // Clamped between 0.1 (never cut off massive trees) and 1.0 (never overscale small trees)
    const finalZoom = Math.max(0.1, Math.min(1.0, Number(targetZoom.toFixed(2))));

    setZoom(finalZoom);

    const prefersReducedMotion = typeof window !== 'undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const scrollBehavior = prefersReducedMotion ? 'auto' : 'smooth';

    const scheduleCenter = () => {
      if (!containerRef.current || !contentWrapperRef.current) return;
      const c = containerRef.current;
      const w = contentWrapperRef.current;

      const scaledCenterX = centerRelX * finalZoom;
      const scaledCenterY = centerRelY * finalZoom;

      const targetScrollLeft = (w.offsetLeft + scaledCenterX) - (viewportW / 2);
      const targetScrollTop = (w.offsetTop + scaledCenterY) - (viewportH / 2);

      c.scrollTo({
        left: Math.max(0, targetScrollLeft),
        top: Math.max(0, targetScrollTop),
        behavior: scrollBehavior
      });
    };

    requestAnimationFrame(scheduleCenter);
    setTimeout(scheduleCenter, 60);
    setTimeout(scheduleCenter, 220);
  }, [zoom]);
  const validation = React.useMemo(() => validateTree(rootNodes), [JSON.stringify(rootNodes)])
  const treeErrors = validation.errors;
  const treeWarnings = validation.warnings;

  // Compute safety radar and touchpoint stats
  const sequenceStats = React.useMemo(() => {
    let nodeCount = 0;
    let touchpoints = 0;
    let minDelay = 999;
    let totalDelayDays = 0;
    let hasZeroDelaySubsequent = false;

    function walk(nodes: SeqTreeNode[], isRoot: boolean) {
      for (const n of nodes) {
        nodeCount++;
        const isMsg = n.type.startsWith('send_message') || 
                      n.type.startsWith('send_ai_message') || 
                      n.type === 'connection_request' || 
                      n.type === 'send_inmail' || 
                      n.type === 'send_voice_note';
        if (isMsg) touchpoints++;
        const delay = n.data?.delay !== undefined ? Number(n.data.delay) : 0;
        totalDelayDays += delay;
        if (!isRoot) {
          if (delay < minDelay) minDelay = delay;
          if (delay < 1) hasZeroDelaySubsequent = true;
        }
        for (const branch of Object.values(n.children || {})) {
          walk(branch, false);
        }
      }
    }
    walk(rootNodes, true);

    const errorCount = Object.values(treeErrors || {}).reduce((acc, errs) => acc + errs.length, 0);
    const warningCount = Object.values(treeWarnings || {}).reduce((acc, warns) => acc + warns.length, 0);

    return {
      nodeCount,
      touchpoints,
      totalDelayDays,
      minDelay: minDelay === 999 ? 0 : minDelay,
      hasZeroDelaySubsequent,
      errorCount,
      warningCount,
      isFullySafe: nodeCount > 0 && errorCount === 0 && warningCount === 0 && !hasZeroDelaySubsequent
    };
  }, [rootNodes, treeErrors, treeWarnings]);

  const applyPreset = (preset: typeof QUICK_PRESETS[0]) => {
    if (rootNodes.length > 0) {
      setSelectedPreset(preset);
      setPresetModalOpen(true);
    } else {
      const nodes = preset.getNodes();
      loadTree(nodes);
      toast.success(`Loaded "${preset.name}" preset`);
    }
  };

  const confirmApplyPreset = () => {
    if (selectedPreset) {
      const nodes = selectedPreset.getNodes();
      loadTree(nodes);
      toast.success(`Loaded "${selectedPreset.name}" preset`);
      setPresetModalOpen(false);
      setSelectedPreset(null);
    }
  };

  const handleAddStickyNote = useCallback((color: string = "amber", category: string = "note") => {
    const currentCount = stickyNotes?.length || 0;
    const stagger = (currentCount % 6) * 32;
    let x = 40 + stagger;
    let y = 140 + stagger;
    if (contentWrapperRef.current && containerRef.current) {
      const containerRect = containerRef.current.getBoundingClientRect();
      const wrapperRect = contentWrapperRef.current.getBoundingClientRect();
      const centerScreenX = containerRect.left + containerRect.width / 2;
      const centerScreenY = containerRect.top + 200;
      x = Math.round((centerScreenX - wrapperRect.left) / zoom - 145 + stagger);
      y = Math.round((centerScreenY - wrapperRect.top) / zoom + stagger);
    } else if (containerRef.current) {
      x = Math.round(((containerRef.current.scrollLeft + containerRef.current.clientWidth / 2) / zoom - 145) + stagger);
      y = Math.round(((containerRef.current.scrollTop + 140) / zoom) + stagger);
    }
    const id = addStickyNote(x, y, color, category);
    toast.success("Sticky note added to canvas", {
      description: "Drag to reposition • Double-click to edit • Alt+Click canvas to drop anywhere"
    });
    return id;
  }, [stickyNotes, zoom, addStickyNote]);

  

  const disableAllAutoWithdraw = (nodes: SeqTreeNode[]) => {
    for (const n of nodes) {
      if ((n.data?.type === "connection_request" || n.type === "connection_request") && n.data?.withdraw_enabled) {
        updateNodeData(n.id, { withdraw_enabled: false })
      }
      for (const branch of Object.values(n.children || {}) as any[][]) {
        disableAllAutoWithdraw(branch)
      }
    }
  }

  
  const isPickerOpen = usePickerStore(s => s.isOpen);
  const prevSelectedRef = React.useRef(selectedNodeId);
  const prevPickerRef = React.useRef(isPickerOpen);

  React.useEffect(() => {
    let active = true;
    if (selectedNodeId && !prevSelectedRef.current && isPickerOpen) {
      if (active) usePickerStore.getState().closePicker();
    } else if (isPickerOpen && !prevPickerRef.current && selectedNodeId) {
      if (active) useHRTreeStore.getState().selectNode(null);
    }
    prevSelectedRef.current = selectedNodeId;
    prevPickerRef.current = isPickerOpen;
    return () => { active = false; }
  }, [selectedNodeId, isPickerOpen]);




  // Keyboard navigation & accessibility engine (WCAG 2.2 AAA + Linear-grade keyboard fluidity)
  React.useEffect(() => {
    const handleKeyDown = async (e: KeyboardEvent) => {
      // 1. Guard against capturing typing inside inputs, textareas, contenteditables, or selects
      const target = e.target as HTMLElement | null;
      if (
        target && (
          target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.isContentEditable ||
          target.tagName === 'SELECT' ||
          (target.closest('[role="dialog"]') !== null && !target.closest('.canvas-tree-root'))
        )
      ) {
        return;
      }

      // 2. Save sequence shortcut (Cmd/Ctrl + S)
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault();
        if (onSave && !isSaving && !readOnly) {
          setIsSaving(true);
          try {
            await onSave(rootNodes);
          } finally {
            setIsSaving(false);
          }
        }
        return;
      }

      // 2b. Fit to Canvas shortcut (Cmd/Ctrl + 0)
      if ((e.ctrlKey || e.metaKey) && e.key === '0') {
        e.preventDefault();
        fitToCanvas();
        return;
      }

      // 3. Undo / Redo shortcuts (Cmd/Ctrl + Z, Cmd/Ctrl + Shift + Z)
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
        if (!readOnly) {
          e.preventDefault();
          if (e.shiftKey) {
            useHRTreeStore.getState().redo();
            toast.info("Redone sequence edit");
          } else {
            useHRTreeStore.getState().undo();
            toast.info("Undone sequence edit");
          }
        }
        return;
      }

      // 3b. Add Sticky Note shortcut ('N')
      if ((e.key === 'n' || e.key === 'N') && !e.ctrlKey && !e.metaKey && !e.altKey && !readOnly && !isPickerOpen) {
        e.preventDefault();
        handleAddStickyNote("amber", "note");
        return;
      }

      // 4. Escape: Close picker or deselect node
      if (e.key === 'Escape') {
        if (isPickerOpen) {
          usePickerStore.getState().closePicker();
          return;
        }
        if (selectedNodeId) {
          useHRTreeStore.getState().selectNode(null);
          return;
        }
      }

      // 5. Delete or Backspace: Remove selected node with safety gate & undo toast
      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedNodeId && !readOnly) {
        e.preventDefault();
        const target = findNodeInTree(rootNodes, selectedNodeId);
        if (target) {
          handleSafeDeleteNode(target);
        }
        return;
      }

      // 6. Tree Traversal (Tab / Shift+Tab, Arrow Keys)
      const flatNodes: SeqTreeNode[] = [];
      const collectFlat = (list: SeqTreeNode[]) => {
        for (const node of list) {
          flatNodes.push(node);
          if (node.children) {
            for (const branch of Object.values(node.children)) {
              if (Array.isArray(branch)) collectFlat(branch);
            }
          }
        }
      };
      collectFlat(rootNodes);

      if (flatNodes.length === 0) return;

      if (e.key === 'Tab') {
        e.preventDefault();
        if (!selectedNodeId) {
          useHRTreeStore.getState().selectNode(flatNodes[0].id);
        } else {
          const idx = flatNodes.findIndex(n => n.id === selectedNodeId);
          if (idx === -1) {
            useHRTreeStore.getState().selectNode(flatNodes[0].id);
          } else {
            const nextIdx = e.shiftKey
              ? (idx - 1 + flatNodes.length) % flatNodes.length
              : (idx + 1) % flatNodes.length;
            useHRTreeStore.getState().selectNode(flatNodes[nextIdx].id);
          }
        }
        return;
      }

      // Arrow navigation
      if (['ArrowDown', 'ArrowUp', 'ArrowLeft', 'ArrowRight'].includes(e.key)) {
        if (!selectedNodeId) {
          if (flatNodes.length > 0) {
            e.preventDefault();
            useHRTreeStore.getState().selectNode(flatNodes[0].id);
          }
          return;
        }

        const idx = flatNodes.findIndex(n => n.id === selectedNodeId);
        if (idx === -1) return;
        const currentNode = flatNodes[idx];

        if (e.key === 'ArrowDown') {
          e.preventDefault();
          // Find first child if exists
          let firstChild: SeqTreeNode | null = null;
          if (currentNode.children) {
            for (const branch of Object.values(currentNode.children)) {
              if (Array.isArray(branch) && branch.length > 0) {
                firstChild = branch[0];
                break;
              }
            }
          }
          if (firstChild) {
            useHRTreeStore.getState().selectNode(firstChild.id);
          } else {
            const nextIdx = (idx + 1) % flatNodes.length;
            useHRTreeStore.getState().selectNode(flatNodes[nextIdx].id);
          }
        } else if (e.key === 'ArrowUp') {
          e.preventDefault();
          const prevIdx = (idx - 1 + flatNodes.length) % flatNodes.length;
          useHRTreeStore.getState().selectNode(flatNodes[prevIdx].id);
        } else if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
          e.preventDefault();
          const step = e.key === 'ArrowRight' ? 1 : -1;
          const nextIdx = (idx + step + flatNodes.length) % flatNodes.length;
          useHRTreeStore.getState().selectNode(flatNodes[nextIdx].id);
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onSave, rootNodes, isSaving, readOnly, selectedNodeId, isPickerOpen, fitToCanvas, handleAddStickyNote]);

  const handleMouseDown = (e: React.MouseEvent) => {
    // Dismiss floating dropdowns on background click without initiating canvas pan
    if (showExportMenu) {
      setShowExportMenu(false)
      return
    }
    if (showImportMenu) {
      setShowImportMenu(false)
      return
    }

    // Alt/Option + Left Click: Drop a new sticky note right under the mouse cursor!
    if (e.altKey && e.button === 0 && !readOnly && contentWrapperRef.current) {
      const target = e.target as HTMLElement;
      if (!target.closest('button, input, textarea, select, .node-card, .sticky-note, [role="dialog"]')) {
        const wrapperRect = contentWrapperRef.current.getBoundingClientRect();
        const clickX = Math.round((e.clientX - wrapperRect.left) / zoom - 145);
        const clickY = Math.round((e.clientY - wrapperRect.top) / zoom - 30);
        addStickyNote(clickX, clickY, "amber", "note");
        toast.success("Sticky note dropped at cursor!");
        return;
      }
    }

    // Only drag on left click, and ignore if clicking on a button or interactive element
    if (e.button !== 0) return
    const target = e.target as HTMLElement
    if (target.closest('button, .node-card, .sticky-note, input, textarea, select')) return
    
    isDragging.current = true
    lastMousePos.current = { x: e.clientX, y: e.clientY }
    if (containerRef.current) {
      containerRef.current.style.cursor = 'grabbing'
    }
  }

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging.current || !containerRef.current) return
    const dx = e.clientX - lastMousePos.current.x
    const dy = e.clientY - lastMousePos.current.y
    containerRef.current.scrollLeft -= dx
    containerRef.current.scrollTop -= dy
    lastMousePos.current = { x: e.clientX, y: e.clientY }
  }

  const handleMouseUp = () => {
    isDragging.current = false
    if (containerRef.current) {
      containerRef.current.style.cursor = 'grab'
    }
  }

  React.useEffect(() => {
    const handleUp = () => handleMouseUp()
    window.addEventListener('mouseup', handleUp)
    return () => window.removeEventListener('mouseup', handleUp)
  }, [])


  return (
    <div className="relative w-full h-full overflow-hidden bg-background">
      <AnimatePresence>
        {picker.isOpen && (
          <PickerPanel 
            isFirstStep={picker.isFirstStep}
            onPick={(type: EINodeType) => {
              const def = HR_NODE_DEFS[type];
              const initialDelay = def.delayDefault !== undefined && def.delayDefault >= 1 ? def.delayDefault : 1;
              const data = { 
                label: def.label, 
                type, 
                color: def.color, 
                outputs: def.outputs, 
                delay: initialDelay, 
                description: def.description 
              };

              if (type === "withdraw_request" && hasAutoWithdrawConnection(rootNodes)) {
                 setPendingAddParams({ type, data, parentId: picker.parentId, branchLabel: picker.branchLabel })
                 setConflictModalOpen(true)
                 return;
              }

              if (picker.parentId === null) {
                addRoot(type, data)
              } else {
                addChild(picker.parentId, picker.branchLabel, type, data)
              }
              picker.closePicker()
            }}
            onClose={picker.closePicker}
          />
        )}
      </AnimatePresence>
      
      {/* Auto-withdraw Conflict Modal */}
      <AnimatePresence>
        {conflictModalOpen && (
          <div 
            className="fixed inset-0 z-[100] flex items-center justify-center bg-background/80 backdrop-blur-sm p-4"
            onClick={(e) => {
              if (e.target === e.currentTarget) {
                setConflictModalOpen(false)
                setPendingAddParams(null)
              }
            }}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              role="dialog"
              aria-modal="true"
              aria-labelledby="conflict-dialog-title"
              className="bg-card border border-border shadow-2xl rounded-xl p-6 max-w-md w-full"
            >
              <div className="flex items-center gap-3 text-primary mb-4">
                <AlertCircle size={22} />
                <h3 id="conflict-dialog-title" className="text-base font-bold text-foreground">Conflict Detected</h3>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed mb-6">
                You already have auto-withdraw enabled on your Connection node. Adding a manual Withdraw node will create a conflict. Do you want to disable auto-withdraw on the Connection node first?
              </p>
              <div className="flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => {
                    setConflictModalOpen(false)
                    setPendingAddParams(null)
                  }}
                  className="px-4 py-2 rounded-lg border border-border text-xs font-semibold text-foreground hover:bg-muted transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => {
                    disableAllAutoWithdraw(rootNodes)
                    if (pendingAddParams) {
                      if (pendingAddParams.parentId === null) {
                        addRoot(pendingAddParams.type as any, pendingAddParams.data)
                      } else {
                        addChild(pendingAddParams.parentId, pendingAddParams.branchLabel, pendingAddParams.type as any, pendingAddParams.data)
                      }
                    }
                    setConflictModalOpen(false)
                    setPendingAddParams(null)
                  }}
                  className="px-4 py-2 rounded-lg bg-primary hover:bg-primary/90 text-xs font-bold text-primary-foreground transition-colors cursor-pointer shadow-xs"
                >
                  Disable Auto-Withdraw and Continue
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Safe Delete Step Confirmation Modal */}
      <AnimatePresence>
        {nodeToDelete && (
          <div 
            className="fixed inset-0 z-[100] flex items-center justify-center bg-background/80 backdrop-blur-sm p-4"
            onClick={(e) => {
              if (e.target === e.currentTarget) setNodeToDelete(null)
            }}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              role="dialog"
              aria-modal="true"
              aria-labelledby="delete-step-dialog-title"
              className="bg-card border border-border shadow-2xl rounded-xl p-6 max-w-md w-full"
            >
              <div className="flex items-center gap-3 text-destructive mb-4">
                <AlertCircle size={22} />
                <h3 id="delete-step-dialog-title" className="text-base font-bold text-foreground">Remove Step & Branches?</h3>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed mb-6">
                Removing this step will also remove its downstream connected branches. You can always undo this action immediately from the toast notification.
              </p>
              <div className="flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setNodeToDelete(null)}
                  className="px-4 py-2 rounded-lg border border-border text-xs font-semibold text-foreground hover:bg-muted transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => {
                    const id = nodeToDelete.id;
                    setNodeToDelete(null);
                    useHRTreeStore.getState().removeNode(id);
                    toast("Step removed from sequence", {
                      action: {
                        label: "Undo",
                        onClick: () => useHRTreeStore.getState().undo()
                      }
                    });
                  }}
                  className="px-4 py-2 rounded-lg bg-destructive hover:bg-destructive/90 text-xs font-bold text-destructive-foreground transition-colors cursor-pointer shadow-xs"
                >
                  Remove Step & Downstream
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Preset Overwrite Confirmation Modal */}
      <AnimatePresence>
        {presetModalOpen && (
          <div 
            className="fixed inset-0 z-[100] flex items-center justify-center bg-background/80 backdrop-blur-sm p-4"
            onClick={(e) => {
              if (e.target === e.currentTarget) {
                setPresetModalOpen(false)
                setSelectedPreset(null)
              }
            }}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              role="dialog"
              aria-modal="true"
              aria-labelledby="preset-dialog-title"
              className="bg-card border border-border shadow-2xl rounded-xl p-6 max-w-md w-full"
            >
              <div className="flex items-center gap-3 text-amber-600 dark:text-amber-400 mb-3">
                <AlertTriangle size={22} />
                <h3 id="preset-dialog-title" className="text-base font-bold text-foreground">Replace Sequence Canvas?</h3>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed mb-6">
                You currently have <span className="font-semibold text-foreground">{rootNodes.length} step(s)</span> on your canvas. Loading <span className="font-semibold text-foreground">&quot;{selectedPreset?.name}&quot;</span> will replace your existing sequence with this calibrated architecture.
              </p>
              <div className="flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => { setPresetModalOpen(false); setSelectedPreset(null); }}
                  className="px-4 py-2 rounded-lg border border-border text-xs font-semibold text-foreground hover:bg-muted transition-colors cursor-pointer"
                >
                  Keep Current Sequence
                </button>
                <button
                  type="button"
                  onClick={confirmApplyPreset}
                  className="px-4 py-2 rounded-lg bg-primary hover:bg-primary/90 text-xs font-bold text-primary-foreground transition-colors shadow-xs cursor-pointer"
                >
                  Replace Canvas
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Left Vertical Toolbar - All Controls Unified */}
      <div className="absolute top-6 left-6 z-40 flex flex-col gap-3 pointer-events-auto">
        {/* Zoom Group */}
        <div className="flex flex-row items-center bg-card/90 backdrop-blur-md border border-border shadow-sm rounded-xl overflow-hidden w-fit">
          <button 
            type="button" 
            onClick={() => setZoom(z => Math.min(Math.round((z + 0.1) * 10) / 10, 2))} 
            className="w-10 h-10 flex items-center justify-center hover:bg-muted text-muted-foreground hover:text-foreground transition-colors border-r border-border cursor-pointer" 
            title="Zoom In"
            aria-label="Zoom in"
          >
            <ZoomIn size={16} />
          </button>
          <button
            type="button"
            onClick={() => setZoom(1)}
            className="px-2.5 h-10 flex items-center justify-center hover:bg-muted text-muted-foreground hover:text-foreground font-mono text-xs font-semibold transition-colors border-r border-border cursor-pointer"
            title="Reset Zoom to 100%"
            aria-label="Reset zoom to 100%"
          >
            {Math.round(zoom * 100)}%
          </button>
          <button 
            type="button" 
            onClick={() => setZoom(z => Math.max(Math.round((z - 0.1) * 10) / 10, 0.2))} 
            className="w-10 h-10 flex items-center justify-center hover:bg-muted text-muted-foreground hover:text-foreground transition-colors border-r border-border cursor-pointer" 
            title="Zoom Out"
            aria-label="Zoom out"
          >
            <ZoomOut size={16} />
          </button>
          <button 
            type="button"
            onClick={fitToCanvas} 
            className="w-10 h-10 flex items-center justify-center hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer" 
            title="Fit to Canvas (Cmd+0)"
            aria-label="Fit to canvas"
          >
            <Maximize size={16} />
          </button>
        </div>

        {/* Action Group */}
        {!readOnly && (
          <div className="flex flex-col bg-card/90 backdrop-blur-md border border-border shadow-sm rounded-xl mt-1 w-52 relative">
            {/* Safety & Health Radar Badge */}
            {sequenceStats.nodeCount > 0 && (
              <div className="px-3 py-2 bg-muted/40 border-b border-border flex flex-col gap-1 rounded-t-xl">
                {sequenceStats.isFullySafe ? (
                  <div className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400 text-[11px] font-semibold">
                    <ShieldCheck size={13} className="shrink-0" />
                    <span>Anti-Spam Safe</span>
                    <span className="opacity-40">•</span>
                    <span>{sequenceStats.touchpoints} Touch{sequenceStats.touchpoints !== 1 ? 'es' : ''}</span>
                  </div>
                ) : sequenceStats.errorCount > 0 ? (
                  <div className="flex items-center gap-1.5 text-rose-600 dark:text-rose-400 text-[11px] font-semibold">
                    <AlertCircle size={13} className="shrink-0" />
                    <span>{sequenceStats.errorCount} Issue{sequenceStats.errorCount > 1 ? 's' : ''} to Resolve</span>
                  </div>
                ) : (
                  <div className="flex items-center gap-1.5 text-amber-600 dark:text-amber-400 text-[11px] font-semibold">
                    <AlertTriangle size={13} className="shrink-0" />
                    <span>{sequenceStats.warningCount} Notice{sequenceStats.warningCount > 1 ? 's' : ''}</span>
                  </div>
                )}
                {sequenceStats.totalDelayDays > 0 && (
                  <div className="flex items-center gap-1 text-[10px] text-muted-foreground font-medium">
                    <Clock size={11} className="text-primary shrink-0" />
                    <span>{sequenceStats.totalDelayDays}d Cadence</span>
                  </div>
                )}
              </div>
            )}

            {/* Primary Workflow Tools: Templates & Simulate DAG */}
            <div className={cn("border-b border-border p-1.5 bg-card/40 flex flex-col gap-1", sequenceStats.nodeCount === 0 && "rounded-t-xl")}>
              {onTemplatesClick && (
                <button
                  type="button"
                  onClick={onTemplatesClick}
                  className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg hover:bg-muted text-xs font-semibold text-foreground hover:text-primary transition-colors cursor-pointer w-full text-left"
                  title="Open Sequence Templates Gallery"
                >
                  <Layers size={14} className="text-primary shrink-0" />
                  <span>Templates</span>
                </button>
              )}
              <button
                type="button"
                onClick={handleRunSimulation}
                disabled={isSimulating}
                className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg hover:bg-muted text-xs font-semibold text-foreground hover:text-primary transition-colors cursor-pointer w-full text-left disabled:opacity-50"
                title="Run Multi-Channel DAG Simulation Sandbox"
              >
                <Sparkles size={14} className={cn("text-primary shrink-0", isSimulating && "animate-spin")} />
                <span>{isSimulating ? "Simulating..." : "Simulate DAG"}</span>
              </button>
            </div>

            {/* History: Undo & Redo */}
            <div className="grid grid-cols-2 border-b border-border bg-card/20">
              <button
                type="button"
                onClick={undo}
                disabled={historyLength === 0}
                className="flex items-center justify-center gap-1.5 py-2 hover:bg-muted text-xs font-medium text-muted-foreground hover:text-foreground disabled:opacity-30 disabled:cursor-not-allowed transition-colors border-r border-border cursor-pointer"
                title="Undo (Cmd+Z)"
              >
                <Undo size={13} />
                <span>Undo</span>
              </button>
              <button
                type="button"
                onClick={redo}
                disabled={futureLength === 0}
                className="flex items-center justify-center gap-1.5 py-2 hover:bg-muted text-xs font-medium text-muted-foreground hover:text-foreground disabled:opacity-30 disabled:cursor-not-allowed transition-colors cursor-pointer"
                title="Redo (Cmd+Shift+Z)"
              >
                <Redo size={13} />
                <span>Redo</span>
              </button>
            </div>

            {/* Sticky Notes Tool */}
            <div className="border-b border-border p-2 bg-card/40 flex flex-col gap-1.5">
              <button
                type="button"
                onClick={() => handleAddStickyNote("amber", "note")}
                className="flex items-center gap-2 hover:bg-muted text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors rounded-lg px-2 py-1.5 w-full cursor-pointer"
                title="Add Sticky Note (Shortcut: Press 'N' or Alt+Click canvas)"
              >
                <StickyNote size={14} className="text-amber-500 shrink-0" />
                <span className="font-medium">Sticky Note</span>
                <kbd className="ml-auto font-mono text-[9px] px-1.5 py-0.2 bg-muted rounded border border-border/60 text-muted-foreground">N</kbd>
              </button>

              {/* Quick Palette Chips - Drop Instant Category Templates */}
              <div className="flex items-center justify-between px-1 gap-1">
                <span className="text-[10px] text-muted-foreground/60 font-medium">Templates:</span>
                <div className="flex items-center gap-1.5">
                  {[
                    { key: "amber", category: "note", title: "Idea Note", dot: "bg-amber-400" },
                    { key: "emerald", category: "todo", title: "Launch Checklist", dot: "bg-emerald-400" },
                    { key: "sky", category: "handover", title: "SDR Handover", dot: "bg-sky-400" },
                    { key: "rose", category: "warning", title: "Caution / Curfew", dot: "bg-rose-400" },
                    { key: "violet", category: "strategy", title: "A/B Strategy", dot: "bg-violet-400" }
                  ].map(c => (
                    <button
                      key={c.key}
                      type="button"
                      onClick={() => handleAddStickyNote(c.key, c.category)}
                      className={cn(
                        "w-3.5 h-3.5 rounded-full transition-transform hover:scale-125 cursor-pointer shadow-2xs",
                        c.dot
                      )}
                      title={`Drop ${c.title}`}
                      aria-label={`Drop ${c.title}`}
                    />
                  ))}
                </div>
              </div>
            </div>

            {/* Canvas Notes Status & Batch Collapse */}
            {stickyNotes && stickyNotes.length > 0 && (
              <div className="flex items-center justify-between px-3 py-1.5 bg-muted/30 text-[10px] font-medium text-muted-foreground border-b border-border">
                <span>{stickyNotes.length} {stickyNotes.length === 1 ? "note" : "notes"}</span>
                <button
                  type="button"
                  onClick={() => {
                    const anyExpanded = stickyNotes.some(sn => !sn.isCollapsed);
                    stickyNotes.forEach(sn => {
                      if (anyExpanded && !sn.isCollapsed) {
                        useHRTreeStore.getState().toggleStickyNoteCollapse(sn.id);
                      } else if (!anyExpanded && sn.isCollapsed) {
                        useHRTreeStore.getState().toggleStickyNoteCollapse(sn.id);
                      }
                    });
                  }}
                  className="hover:text-foreground transition-colors underline cursor-pointer"
                >
                  {stickyNotes.some(sn => !sn.isCollapsed) ? "Collapse all" : "Expand all"}
                </button>
              </div>
            )}

            {/* Import & Export Dropdowns */}
            <div className="border-b border-border p-1.5 bg-card/30 flex items-center gap-1.5 relative z-20">
              {/* Import Dropdown */}
              <div className={cn("relative flex-1", showImportMenu && "z-30")} ref={importMenuRef}>
                <button
                  type="button"
                  onClick={() => {
                    setShowImportMenu(!showImportMenu)
                    setShowExportMenu(false)
                  }}
                  className={cn(
                    "w-full flex items-center justify-center gap-1 text-[11px] font-semibold transition-colors rounded-lg px-2 py-1.5 border cursor-pointer",
                    showImportMenu 
                      ? "bg-primary/10 border-primary/40 text-primary shadow-xs" 
                      : "hover:bg-muted text-muted-foreground hover:text-foreground border-border/50"
                  )}
                  title="Import sequence (.json, .elein)"
                >
                  <Upload size={12} className="text-primary shrink-0" />
                  <span>Import</span>
                  <ChevronDown size={10} className={cn("opacity-60 transition-transform duration-150", showImportMenu && "rotate-180")} />
                </button>

                {showImportMenu && (
                  <div 
                    role="menu" 
                    aria-label="Import Options Menu"
                    className="absolute left-0 top-full mt-2 w-56 rounded-xl bg-card/98 backdrop-blur-md border border-border shadow-2xl py-1.5 z-[60] flex flex-col text-xs animate-in fade-in zoom-in-95 duration-150 divide-y divide-border/30"
                  >
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setShowImportMenu(false)
                        canvasFileInputRef.current?.click()
                      }}
                      className="flex items-center gap-2.5 px-3 py-2 text-left hover:bg-muted/70 text-foreground transition-colors cursor-pointer group"
                    >
                      <div className="w-6 h-6 rounded-md bg-primary/10 flex items-center justify-center text-primary shrink-0 group-hover:scale-105 transition-transform">
                        <Upload size={12} />
                      </div>
                      <div className="flex flex-col min-w-0">
                        <span className="font-semibold text-foreground text-xs">Upload File</span>
                        <span className="text-[10px] text-muted-foreground">.json or .elein format</span>
                      </div>
                    </button>
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setShowImportMenu(false)
                        setBlueprintModalTab("import")
                        setIsBlueprintModalOpen(true)
                      }}
                      className="flex items-center gap-2.5 px-3 py-2 text-left hover:bg-muted/70 text-foreground transition-colors cursor-pointer group"
                    >
                      <div className="w-6 h-6 rounded-md bg-muted flex items-center justify-center text-muted-foreground shrink-0 group-hover:scale-105 transition-transform">
                        <FileText size={12} />
                      </div>
                      <div className="flex flex-col min-w-0">
                        <span className="font-semibold text-foreground text-xs">Paste JSON</span>
                        <span className="text-[10px] text-muted-foreground">Direct raw sequence JSON</span>
                      </div>
                    </button>
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setShowImportMenu(false)
                        setBlueprintModalTab("gallery")
                        setIsBlueprintModalOpen(true)
                      }}
                      className="flex items-center gap-2.5 px-3 py-2 text-left hover:bg-muted/70 text-foreground transition-colors cursor-pointer group"
                    >
                      <div className="w-6 h-6 rounded-md bg-amber-500/10 flex items-center justify-center text-amber-500 shrink-0 group-hover:scale-105 transition-transform">
                        <Sparkles size={12} />
                      </div>
                      <div className="flex flex-col min-w-0">
                        <span className="font-semibold text-foreground text-xs">Blueprint Gallery</span>
                        <span className="text-[10px] text-muted-foreground">Curated multi-channel cadences</span>
                      </div>
                    </button>
                  </div>
                )}
              </div>

              {/* Export Dropdown */}
              <div className={cn("relative flex-1", showExportMenu && "z-30")} ref={exportMenuRef}>
                <button
                  type="button"
                  onClick={() => {
                    setShowExportMenu(!showExportMenu)
                    setShowImportMenu(false)
                  }}
                  className={cn(
                    "w-full flex items-center justify-center gap-1 text-[11px] font-semibold transition-colors rounded-lg px-2 py-1.5 border cursor-pointer",
                    showExportMenu 
                      ? "bg-primary/10 border-primary/40 text-primary shadow-xs" 
                      : "hover:bg-muted text-muted-foreground hover:text-foreground border-border/50"
                  )}
                  title="Export sequence options"
                >
                  <Download size={12} className="text-primary shrink-0" />
                  <span>Export</span>
                  <ChevronDown size={10} className={cn("opacity-60 transition-transform duration-150", showExportMenu && "rotate-180")} />
                </button>

                {showExportMenu && (
                  <div 
                    role="menu"
                    aria-label="Export Options Menu"
                    className="absolute right-0 top-full mt-2 w-56 rounded-xl bg-card/98 backdrop-blur-md border border-border shadow-2xl py-1.5 z-[60] flex flex-col text-xs animate-in fade-in zoom-in-95 duration-150 divide-y divide-border/30"
                  >
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setShowExportMenu(false)
                        handleQuickExportJson()
                      }}
                      className="flex items-center gap-2.5 px-3 py-2 text-left hover:bg-muted/70 text-foreground transition-colors cursor-pointer group"
                    >
                      <div className="w-6 h-6 rounded-md bg-primary/10 flex items-center justify-center text-primary shrink-0 group-hover:scale-105 transition-transform">
                        <Download size={12} />
                      </div>
                      <div className="flex flex-col min-w-0">
                        <span className="font-semibold text-foreground text-xs">Export JSON</span>
                        <span className="text-[10px] text-muted-foreground">Standard sequence file</span>
                      </div>
                    </button>
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setShowExportMenu(false)
                        handleQuickExportElein()
                      }}
                      className="flex items-center gap-2.5 px-3 py-2 text-left hover:bg-muted/70 text-foreground transition-colors cursor-pointer group"
                    >
                      <div className="w-6 h-6 rounded-md bg-emerald-500/10 flex items-center justify-center text-emerald-500 shrink-0 group-hover:scale-105 transition-transform">
                        <FileCode size={12} />
                      </div>
                      <div className="flex flex-col min-w-0">
                        <span className="font-semibold text-foreground text-xs">Export Native (.elein)</span>
                        <span className="text-[10px] text-muted-foreground">Canvas nodes + notes backup</span>
                      </div>
                    </button>
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setShowExportMenu(false)
                        handleQuickCopyJson()
                      }}
                      className="flex items-center gap-2.5 px-3 py-2 text-left hover:bg-muted/70 text-foreground transition-colors cursor-pointer group"
                    >
                      <div className="w-6 h-6 rounded-md bg-muted flex items-center justify-center text-muted-foreground shrink-0 group-hover:scale-105 transition-transform">
                        <Copy size={12} />
                      </div>
                      <div className="flex flex-col min-w-0">
                        <span className="font-semibold text-foreground text-xs">Copy to Clipboard</span>
                        <span className="text-[10px] text-muted-foreground">Serialized JSON payload</span>
                      </div>
                    </button>
                  </div>
                )}
              </div>
            </div>

            {/* Save Canvas Button */}
            <button
              type="button"
              onClick={async () => {
                if (onSave) {
                  setIsSaving(true);
                  try {
                    await onSave(rootNodes);
                  } finally {
                    setIsSaving(false);
                  }
                }
              }}
              disabled={isSaving}
              className="flex items-center justify-center gap-2 px-3.5 py-2.5 bg-primary/10 hover:bg-primary/20 text-primary text-xs font-bold transition-colors w-full disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer rounded-b-xl"
            >
              {isSaving ? (
                <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-primary" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
              ) : (
                <Save size={14} className="shrink-0" />
              )}
              <span>{isSaving ? 'Saving...' : 'Save Canvas'}</span>
            </button>
          </div>
        )}
      </div>
      <div 
        ref={containerRef}
        className="w-full h-full overflow-auto overscroll-none relative" 
        style={{ cursor: 'grab' }}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onDragOver={(e) => {
          e.preventDefault()
          e.stopPropagation()
          setIsDraggingBlueprintFile(true)
        }}
        onDragEnter={(e) => {
          e.preventDefault()
          e.stopPropagation()
          dragCounterRef.current++
          if (dragCounterRef.current === 1) {
            setIsDraggingBlueprintFile(true)
          }
        }}
        onDragLeave={(e) => {
          e.preventDefault()
          e.stopPropagation()
          dragCounterRef.current--
          if (dragCounterRef.current <= 0) {
            dragCounterRef.current = 0
            setIsDraggingBlueprintFile(false)
          }
        }}
        onDrop={handleCanvasFileDrop}
      >
        {/* Drag & Drop Visual HUD Overlay */}
        {isDraggingBlueprintFile && (
          <div className="absolute inset-0 z-50 bg-background/85 backdrop-blur-md border-4 border-dashed border-primary flex flex-col items-center justify-center gap-4 animate-in fade-in duration-200 pointer-events-none">
            <div className="w-16 h-16 rounded-3xl bg-primary/20 border-2 border-primary flex items-center justify-center text-primary shadow-2xl animate-bounce">
              <ElesiumLogo className="w-9 h-9" />
            </div>
            <div className="text-center">
              <h3 className="text-xl font-bold text-foreground tracking-tight">
                Drop Ele-in Blueprint to Import
              </h3>
              <p className="text-sm text-muted-foreground mt-1">
                Release anywhere on canvas to inspect, brand, and import sequence
              </p>
            </div>
            <span className="px-3 py-1 rounded-full text-xs font-mono font-semibold bg-primary/10 text-primary border border-primary/20">
              .elein / .json supported
            </span>
          </div>
        )}

        <DotPattern
          width={24}
          height={24}
          cx={1}
          cy={1}
          cr={1}
          className="fill-neutral-400/20 dark:fill-neutral-500/20 [mask-image:radial-gradient(ellipse_at_center,white,transparent_80%)]"
        />

        <div 
          ref={contentWrapperRef}
          data-canvas-zoom={zoom}
          className="relative flex flex-col items-center w-max min-w-full min-h-full py-20 px-20 transition-all duration-200 ease-out origin-top"
          style={{
            transform: `scale(${zoom})`,
            transformOrigin: "top center",
          }}
        >
          {stickyNotes?.map(note => <EIStickyNote key={note.id} note={note} zoom={zoom} />)}
          {/* Sequence start node */}
          <div ref={startNodeRef} className="sequence-start-node flex items-center gap-2 px-5 py-2.5 rounded-xl bg-card/90 backdrop-blur-md border border-border shadow-sm text-foreground text-sm font-semibold">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-primary">
              <polygon points="5 3 19 12 5 21 5 3" />
            </svg>
            Sequence start
          </div>

          {/* The tree */}
          <Branch
            nodes={rootNodes}
            parentId={null}
            branchLabel="root"
            depth={0}
            isFirstStep={rootNodes.length === 0}
            readOnly={readOnly}
            treeErrors={treeErrors}
            treeWarnings={treeWarnings}
            nodeAnalytics={nodeAnalytics}
            firstNodeRef={firstNodeRef}
            onSafeDelete={handleSafeDeleteNode}
          />
        </div>
      </div>
      
      {/* Side-panel for configuring selected node */}
      <EITreeNodeConfigPanel />

      {/* Hidden File Input for Direct 1-Click Sequence Import */}
      <input
        type="file"
        ref={canvasFileInputRef}
        onChange={handleDirectCanvasFileInput}
        accept=".json,.elein,application/json"
        className="hidden"
      />

      {/* Campaign Blueprint Modal (Make / n8n Export & Import) */}
      <CampaignBlueprintModal
        isOpen={isBlueprintModalOpen}
        onClose={() => {
          setIsBlueprintModalOpen(false)
          setPreloadedBlueprint(null)
        }}
        initialTab={blueprintModalTab}
        preloadedBlueprint={preloadedBlueprint}
      />

      {/* Multi-Channel Sequence DAG Simulation Drawer */}
      <DAGSimulationDrawer
        isOpen={isSimulationDrawerOpen}
        onClose={() => setIsSimulationDrawerOpen(false)}
        simulationData={simulationResult}
        onReRun={handleRunSimulation}
        isSimulating={isSimulating}
      />

      {/* Floating Canvas Navigation & Accelerator HUD */}
      <div className="absolute bottom-6 left-6 z-40 pointer-events-auto">
        <div className="flex items-center gap-2.5 px-3.5 py-1.5 rounded-full bg-card/85 backdrop-blur-md border border-border/80 shadow-sm text-[11px] text-muted-foreground select-none">
          <span className="flex items-center gap-1">
            <kbd className="font-mono text-[10px] px-1 py-0.2 bg-muted rounded border border-border/60 text-foreground font-semibold">Space</kbd>
            <span>+ Drag pan</span>
          </span>
          <span className="text-border">•</span>
          <span className="flex items-center gap-1">
            <kbd className="font-mono text-[10px] px-1 py-0.2 bg-muted rounded border border-border/60 text-foreground font-semibold">Scroll</kbd>
            <span>zoom</span>
          </span>
          <span className="text-border">•</span>
          <span className="flex items-center gap-1">
            <kbd className="font-mono text-[10px] px-1 py-0.2 bg-muted rounded border border-border/60 text-foreground font-semibold">⌘Z</kbd>
            <span>undo</span>
          </span>
          <span className="text-border">•</span>
          <span className="flex items-center gap-1">
            <kbd className="font-mono text-[10px] px-1 py-0.2 bg-muted rounded border border-border/60 text-foreground font-semibold">N</kbd>
            <span>note</span>
          </span>
        </div>
      </div>
    </div>
  )
}

