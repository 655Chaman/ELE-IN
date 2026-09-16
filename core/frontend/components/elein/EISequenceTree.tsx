import { EIStickyNote } from "./EIStickyNote";
import React from "react";
import { cn } from "@/lib/utils"

import { useState, useCallback } from "react"
import { AnimatePresence, motion } from "motion/react"
import {
  Plus, Check, X, Clock, Trash2, Edit2,
  UserPlus, MessageSquare, Eye, Heart, Users, Mail,
  AtSign, Zap, CheckCircle2, Shield, StopCircle, AlertCircle,
  Phone, CalendarCheck, Star, Mic2, Tag, Bell, Database, Info, ZoomIn, ZoomOut, Maximize, Undo, Redo, FileText, Save
} from "lucide-react"
import { HR_NODE_DEFS } from "@/lib/eiNodeDefs"
import type { EINodeType } from "@/lib/eiNodeDefs"
import { useHRTreeStore, type SeqTreeNode } from "@campaigns/eiTreeStore"
import { validateTree } from "@/lib/treeValidator"
import SpotlightCard from "../SpotlightCard"
import { EITreeNodeConfigPanel, hasAutoWithdrawConnection } from "./EINodeConfigPanel"

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
  if_email_found: AtSign, if_phone_found: Phone, open_profile_check: Shield,
  if_premium_member: Star, if_large_following: Users, if_mutual_connections: Users,
  if_recently_active: Zap, if_has_recent_posts: MessageSquare,
  if_company_hiring: Zap, icp_score_gate: CheckCircle2,
  if_meeting_booked: CalendarCheck, if_request_pending: Clock,
  if_lead_matches: Shield,
  // Messages
  send_message: MessageSquare, send_ai_message: MessageSquare,
  send_voice_note: Mic2, send_inmail: Mail, send_paid_inmail: Mail,
  // AI
  ai_personalize: Zap, ai_detect_sentiment: Zap,
  ai_generate_icebreaker: MessageSquare, ai_translate_message: Zap,
  ai_score_icp: CheckCircle2, ai_buying_signal: Zap,
  ai_summarize_profile: Eye, ai_detect_competitor: Shield, 
  ai_best_send_time: Clock, ai_query_knowledge_base: Zap,
  // Enrichment
  find_email: AtSign, find_personal_email: AtSign, find_phone: Phone,
  find_tech_stack: Database, find_funding_round: Zap,
  find_headcount: Users, find_job_postings: Zap,
  get_linkedin_activity: Star, get_mutual_connections: Users,
  verify_email: CheckCircle2,
  // Multichannel
  push_to_crm: Database, add_to_email_sequencer: Zap,
  send_slack_alert: Bell, send_webhook: Zap,
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
  ["ai",           "ai_personalize"],
  ["enrichment",   "find_email"],
  ["conditions",   "icp_score_gate"],
  ["conditions",   "if_recently_active"],
  ["conditions",   "if_has_recent_posts"],
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
  ["messages",     "send_paid_inmail"],
  ["messages",     "send_voice_note"],
  // Logic & Flow
  ["conditions",   "if_connected"],
  ["conditions",   "if_replied"],
  ["conditions",   "if_recently_active"],
  ["conditions",   "if_has_recent_posts"],
  ["conditions",   "if_meeting_booked"],
  ["conditions",   "if_lead_matches"],
  ["conditions",   "open_profile_check"],
  ["conditions",   "icp_score_gate"],
  ["conditions",   "if_company_hiring"],
  ["conditions",   "if_phone_found"],
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
  ["enrichment",   "find_email"],
  ["enrichment",   "verify_email"],
  ["enrichment",   "find_tech_stack"],
  ["enrichment",   "find_funding_round"],
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
  warmup:       "#8b5cf6",
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
  
  // Group by category
  const grouped: Record<string, string[]> = {}
  for (const [cat, type] of nodeList) {
    if (!grouped[cat]) grouped[cat] = []
    grouped[cat].push(type)
  }

  return (
    <div className="fixed inset-y-0 right-0 z-[60] pointer-events-none flex">
      <motion.div 
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ type: "spring", damping: 25, stiffness: 200 }}
        className={cn(
          "pointer-events-auto bg-background shadow-[config(theme.boxShadow.2xl)] border-l border-border flex flex-col h-full",
          "w-[360px]"
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border/50 bg-muted/10">
          <div>
            <p className="text-[15px] font-bold text-foreground tracking-tight">
              {isFirstStep ? "Build sequence" : "Add a step"}
            </p>

          </div>
          <div className="flex items-center gap-2 pointer-events-auto">
            <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors z-50">
              <X size={20} />
            </button>
          </div>
        </div>
        
          <>

        {/* Node list */}
        <div className="flex-1 overflow-y-auto overscroll-none px-6 py-5 space-y-10">
          {Object.entries(grouped).map(([cat, types]) => (
            <div key={cat}>
              <div className="flex items-center gap-2 mb-4">
                <p className="text-[14px] font-bold text-foreground tracking-wide uppercase">{CAT_LABELS[cat]}</p>
                <span className="text-[10px] font-bold text-muted-foreground bg-muted/30 border border-border rounded px-2 py-0.5">
                  {types.length}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-3">
                {types.map(type => {
                  const def = HR_NODE_DEFS[type as EINodeType]
                  if (!def) return null
                  const Icon = NODE_ICONS[type] || Zap
                  const color = CAT_ICON_COLORS[cat]
                  return (
                    <div key={type} className="relative group h-full">
                      <button
                        onClick={() => onPick(type as EINodeType)}
                        className="w-full h-full flex flex-col items-start p-4 rounded-xl border border-border/50 bg-muted/10 hover:bg-muted/30 text-left transition-all relative overflow-hidden group-hover:border-foreground/30 shadow-lg"
                      >
                        {/* Glow effect */}
                        <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" style={{ background: `radial-gradient(circle at center, ${color}15 0%, transparent 70%)` }} />
                        <div
                          className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0 mb-3 border backdrop-blur-sm z-10 transition-transform group-hover:scale-105"
                          style={{ borderColor: `${color}33`, color, background: `${color}10` }}
                        >
                          <Icon size={18} strokeWidth={1.5} />
                        </div>
                        <div className="min-w-0 z-10 flex-1">
                          <p className="text-[13px] font-bold text-foreground leading-tight transition-colors">{def.label}</p>
                          <p className="text-[11px] text-muted-foreground mt-1.5 leading-snug line-clamp-2">{def.description}</p>
                        </div>
                        {type === "find_email" && (
                          <div className="absolute left-4 bottom-4 flex items-center gap-0.5 px-1.5 py-0.5 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 rounded text-[10px] font-bold border border-emerald-500/20">
                            <Database size={9} /> 1
                          </div>
                        )}
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); setInfoNode(type as EINodeType) }}
                        className="absolute right-2 top-2 p-2 rounded-lg bg-muted/30 text-muted-foreground hover:text-foreground hover:bg-muted/50 opacity-0 group-hover:opacity-100 transition-all z-20"
                        title="More info"
                      >
                        <Info size={14} />
                      </button>
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>

        <div className="flex-none border-t border-border px-6 py-4 bg-background">
          <button onClick={onClose} className="px-5 py-2 rounded-lg border border-border text-sm font-semibold text-foreground hover:border-foreground/30 bg-muted/20 transition-all">
            Dismiss
          </button>
        </div>

        {/* Info Popover */}
        <AnimatePresence>
          {infoNode && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="absolute inset-0 z-50 flex items-center justify-center p-6 bg-background/80 backdrop-blur-sm"
              onClick={() => setInfoNode(null)}
            >
              <div 
                className="w-full max-w-sm bg-card border border-border rounded-2xl shadow-2xl overflow-hidden"
                onClick={e => e.stopPropagation()}
              >
                <div className="p-6 border-b border-border bg-card">
                  <div className="flex items-center justify-between mb-4">
                    <div 
                      className="w-12 h-12 rounded-xl flex items-center justify-center border"
                      style={{ 
                        color: CAT_ICON_COLORS[HR_NODE_DEFS[infoNode].category] || "currentColor",
                        borderColor: `${CAT_ICON_COLORS[HR_NODE_DEFS[infoNode].category]}40`,
                        background: `${CAT_ICON_COLORS[HR_NODE_DEFS[infoNode].category]}15`
                      }}
                    >
                      {(() => {
                        const Icon = NODE_ICONS[infoNode] || Zap
                        return <Icon size={24} />
                      })()}
                    </div>
                    <button onClick={() => setInfoNode(null)} className="p-2 text-muted-foreground hover:text-foreground bg-muted/50 rounded-lg transition-colors">
                      <X size={16} />
                    </button>
                  </div>
                  <h3 className="text-lg font-bold text-foreground mb-1">{HR_NODE_DEFS[infoNode].label}</h3>
                  <div className="flex gap-2 mb-4">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground bg-muted/50 px-2 py-0.5 rounded border border-border">
                      {CAT_LABELS[HR_NODE_DEFS[infoNode].category]}
                    </span>
                  </div>
                  <p className="text-[13px] text-muted-foreground leading-relaxed">
                    {HR_NODE_DEFS[infoNode].description}
                  </p>
                </div>
                <div className="p-6 bg-muted/10 space-y-4">
                  <div>
                    <p className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider mb-2">Branches / Outputs</p>
                    <div className="flex flex-wrap gap-2">
                      {HR_NODE_DEFS[infoNode].outputs?.map(out => (
                        <span key={out} className="text-xs font-semibold text-foreground bg-muted/30 border border-border px-2 py-1 rounded-md">
                          {out}
                        </span>
                      ))}
                      {!HR_NODE_DEFS[infoNode].outputs?.length && (
                        <span className="text-xs text-muted-foreground italic">None (Ends Sequence)</span>
                      )}
                    </div>
                  </div>
                  <button 
                    onClick={() => { onPick(infoNode); setInfoNode(null) }}
                    className="w-full py-2.5 bg-foreground text-background font-bold rounded-lg hover:opacity-90 transition-opacity mt-2"
                  >
                    Add to Sequence
                  </button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
          </>
      </motion.div>
    </div>
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
    <div className="flex items-center gap-2">
      <button
        onClick={() => openPicker(parentId, branchLabel, isFirstStep)}
        className="w-10 h-10 rounded-xl border-2 border-border bg-card hover:border-indigo-500/50 hover:shadow-md flex items-center justify-center text-muted-foreground hover:text-indigo-500 dark:hover:text-indigo-400 transition-all shadow-sm relative z-20 active:scale-95 cursor-pointer"
        title="Add step"
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openPicker(parentId, branchLabel, isFirstStep); } }}
      >
        <Plus size={18} />
      </button>
      <div className="relative">
        <button
          onClick={onEnd}
          onMouseEnter={() => setShowEndTip(true)}
          onMouseLeave={() => setShowEndTip(false)}
          className="w-10 h-10 rounded-xl border-2 border-border bg-card hover:border-foreground/30 hover:shadow-md flex items-center justify-center text-muted-foreground hover:text-foreground transition-all shadow-sm"
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
      
      {/* Side-panel for configuring selected node */}
      <EITreeNodeConfigPanel />
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
      <div className="group relative flex items-center gap-2 px-4 py-2 rounded-xl bg-card border border-border text-muted-foreground text-sm font-medium shadow-sm hover:border-red-500/50 transition-colors cursor-pointer pr-10" onClick={onDelete}>
        <StopCircle size={14} /> End sequence
        
        {/* Delete Button (visible on hover) */}
        {onDelete && (
          <button
            onClick={(e) => { e.stopPropagation(); onDelete(); }}
            className="absolute right-2 opacity-0 group-hover:opacity-100 p-1.5 rounded-lg bg-red-500/10 text-red-500 hover:bg-red-500 hover:text-white transition-all"
            title="Remove End Node to continue sequence"
          >
            <Trash2 size={13} />
          </button>
        )}
      </div>
    )
  }

  return (
    <SpotlightCard
      draggable={draggable}
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDrop={onDrop}
      onDragEnd={onDragEnd}
      onClick={onSelect}
      className={`!p-0 group w-[320px] !rounded-2xl !bg-card border transition-all duration-200 cursor-pointer shadow-sm hover:shadow-md hover:-translate-y-[2px] ${
        isSelected ? "ring-2 ring-indigo-500 ring-offset-2 ring-offset-background z-10 border-transparent" : "hover:!border-indigo-500/50"
      } ${isDragging ? "opacity-30 scale-95" : ""} ${isDragOver ? "border-dashed !border-indigo-500 !bg-indigo-50/50" : ""}`}
     
      style={(!isDragOver && !isSelected) ? { borderColor: `${color}66` } : isSelected ? { borderColor: color } : {}}
    >
      {/* Delay Configurator */}
      {delay !== undefined && !hideDelay && (
        <div className="border-b border-border/50 bg-muted/10 rounded-t-2xl overflow-hidden">
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
              <button className="text-muted-foreground hover:text-foreground">
                <div className="p-1 rounded hover:bg-muted/50"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"></path></svg></div>
              </button>
            )}
          </div>
          
          {isEditingDelay && (
            <div 
              className="px-4 py-3 border-t border-border/50 bg-background/50 flex items-center gap-3"
              onClick={e => e.stopPropagation()}
            >
              <div className="relative flex-1">
                <input 
                  type="number" 
                  min="0"
                  value={delay}
                  onChange={(e) => updateNodeData(node.id, { delay: parseInt(e.target.value) || 0 })}
                  className="w-full bg-background border border-border rounded-lg pl-3 pr-8 py-1.5 text-[13px] text-foreground focus:outline-none focus:border-indigo-500 font-medium"
                />
                <div className="absolute right-2 top-0 bottom-0 flex flex-col justify-center gap-0.5">
                  <button onClick={() => updateNodeData(node.id, { delay: delay + 1 })} className="text-muted-foreground hover:text-foreground"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="m18 15-6-6-6 6"/></svg></button>
                  <button onClick={() => updateNodeData(node.id, { delay: Math.max(0, delay - 1) })} className="text-muted-foreground hover:text-foreground"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="m6 9 6 6 6-6"/></svg></button>
                </div>
              </div>
              <div className="flex-1 relative">
                <select 
                  value={node.data.delayUnit || 'days'}
                  onChange={(e) => updateNodeData(node.id, { delayUnit: e.target.value })}
                  className="w-full bg-background border border-border rounded-lg pl-3 pr-8 py-1.5 text-[13px] text-foreground focus:outline-none focus:border-indigo-500 font-medium cursor-pointer appearance-none"
                >
                  <option value="minutes">Minutes</option>
                  <option value="hours">Hours</option>
                  <option value="days">Days</option>
                  <option value="weeks">Weeks</option>
                </select>
                <div className="absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none text-muted-foreground">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6"/></svg>
                </div>
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
        
        return (
          <div className={`flex flex-col px-4 py-3.5 relative ${hasError ? 'bg-red-500/5' : ''}`}>
            <div className="flex items-center gap-3">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0 border"
                style={{ background: `${displayColor}15`, borderColor: `${displayColor}40`, color: displayColor }}
              >
                {hasError ? <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/></svg> : <Icon size={18} strokeWidth={1.5} />}
              </div>
              <div className="flex-1 min-w-0 pr-6">
                <div className={hasError ? "text-[14px] font-bold text-red-500 leading-tight" : "text-[14px] font-bold text-foreground leading-tight"}>
                  <span>{label}</span>
                </div>
                <p className={hasError ? "text-[12px] font-semibold text-red-500/80 mt-0.5" : "text-[12px] text-muted-foreground mt-0.5 leading-snug line-clamp-2 max-w-[210px]"}>
                  {hasError ? "Action required" : description}
                </p>
              </div>
              
              {onDelete && (
                <button
                  onClick={(e) => { e.stopPropagation(); onDelete(); }}
                  className="absolute right-3 opacity-0 group-hover:opacity-100 p-1.5 rounded-lg bg-red-500/10 text-red-500 hover:bg-red-500 hover:text-white transition-colors z-20"
                  title="Delete node"
                >
                  <Trash2 size={13} />
                </button>
              )}
            </div>

            {analytics && (
              <div className="mt-3 flex items-center gap-4 pt-3 border-t border-border">
                <div className="flex flex-col">
                  <span className="text-[9px] text-muted-foreground uppercase tracking-widest font-bold">Sent</span>
                  <span className="text-xs text-foreground">{analytics.sent}</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-[9px] text-muted-foreground uppercase tracking-widest font-bold">Replied</span>
                  <span className="text-xs text-foreground">{analytics.replied}</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-[9px] text-indigo-500 uppercase tracking-widest font-bold">Rate</span>
                  <span className="text-xs text-indigo-500 dark:text-indigo-400 font-semibold">{analytics.reply_rate}%</span>
                </div>
              </div>
            )}

            {errors && errors.length > 0 && (
          <div className="mt-3 text-xs bg-red-500/10 border border-red-500/20 text-red-500 p-2.5 rounded-md flex flex-col gap-1.5">
            <div className="font-semibold flex items-center gap-1">
              <AlertCircle className="h-3.5 w-3.5" />
              Action Required
            </div>
            {errors.map((e: string, i: number) => (
              <div key={i} className="flex items-start gap-1.5">
                <span className="opacity-60 mt-0.5">•</span>
                <span className="leading-snug">{e}</span>
              </div>
            ))}
          </div>
        )}
        {warnings && warnings.length > 0 && (
          <div className="mt-3 text-xs bg-yellow-500/10 border border-yellow-500/20 text-yellow-600 dark:text-yellow-400 p-2.5 rounded-md flex flex-col gap-1.5">
            <div className="font-semibold flex items-center gap-1">
              <AlertCircle className="h-3.5 w-3.5" />
              Warning
            </div>
            {warnings.map((w: string, i: number) => (
              <div key={i} className="flex items-start gap-1.5">
                <span className="opacity-60 mt-0.5">•</span>
                <span className="leading-snug">{w}</span>
              </div>
            ))}
          </div>
        )}
          </div>
        )
      })()}
    </SpotlightCard>
  )
}

// ─── Branch pill ───────────────────────────────────────────────────────────────

function BranchPill({ label }: { label: string }) {
  const isPositive = label === "Connected" || label === "Replied" || label === "Booked" || label === "Email found" || label === "Open" || label === "Success" || label === "Yes"

  return (
    <div className="flex items-center gap-2 px-3.5 py-1.5 rounded-full text-[10px] font-bold tracking-[0.08em] uppercase bg-background border border-border/60 shadow-sm z-10 backdrop-blur-md transition-all hover:border-foreground/30 hover:shadow-md">
      <div className={`w-1.5 h-1.5 rounded-full ${isPositive ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.8)]" : "bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.8)]"}`} />
      <span className="text-foreground/80">{label}</span>
    </div>
  )
}

// ─── Vertical connector line ───────────────────────────────────────────────────
function VLine({ height = 32 }: { height?: number }) {
  return <div className="w-px bg-border mx-auto" style={{ height }} />
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
}

function Branch({ nodes, parentId, branchLabel, depth, isFirstStep, readOnly, nodeAnalytics, parentAnalytics, treeErrors, treeWarnings }: BranchProps ) {
  const { addRoot, addChild, endBranch, removeNode, selectNode, selectedNodeId, moveNodeInBranch } = useHRTreeStore()
  const closePicker = usePickerStore(s => s.closePicker)

  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)

  const handleAdd = useCallback((type: EINodeType) => {
    const def = HR_NODE_DEFS[type]
    if (!parentId) {
      addRoot(type, { label: def.label, type, color: def.color, outputs: def.outputs, delay: def.delayDefault ?? 0, description: def.description })
    } else {
      addChild(parentId, branchLabel, type, { label: def.label, type, color: def.color, outputs: def.outputs, delay: def.delayDefault ?? 0, description: def.description })
    }
  }, [parentId, branchLabel, addRoot, addChild])

  const handleEnd = useCallback(() => {
    if (!parentId) return
    endBranch(parentId, branchLabel)
  }, [parentId, branchLabel, endBranch])

  if (nodes.length === 0) {
    return (
      <div className="flex flex-col items-center">
        <VLine />
        {!readOnly && <AddEndPair isFirstStep={isFirstStep} parentId={parentId} branchLabel={branchLabel} onEnd={handleEnd} />}
      </div>
    )
  }

  return (
    <div className="flex flex-col items-center">
      {nodes.map((node, idx) => {
        const outputsDef = HR_NODE_DEFS[node.type as EINodeType]?.outputs || node.data?.outputs
        const expectedLabels = outputsDef && outputsDef.length > 0 ? outputsDef : (node.type === "sequence_end" ? [] : ["then"])
        const actualLabels = Object.keys(node.children || {})
        const branchLabels = Array.from(new Set([...expectedLabels, ...actualLabels]))
        const isCondition = branchLabels.length > 1
        const isEnd = node.type === "sequence_end"

        return (
          <div key={node.id} className="flex flex-col items-center relative">
            <VLine />

            
            {/* Drop-off badge */}
            {readOnly && parentAnalytics && nodeAnalytics?.[node.id] && parentAnalytics.sent > 0 && (
              <div className="absolute -top-7 left-1/2 -translate-x-1/2 z-10 whitespace-nowrap px-2.5 py-1 rounded-lg bg-red-500/10 backdrop-blur-md border border-red-500/20 text-[10px] font-bold text-red-400 shadow-[0_0_15px_rgba(239,68,68,0.1)] flex items-center gap-1.5">
                Drop-off: {Math.max(0, parentAnalytics.sent - nodeAnalytics[node.id].sent)} ({parentAnalytics.sent > 0 ? Math.round(Math.max(0, parentAnalytics.sent - nodeAnalytics[node.id].sent) / parentAnalytics.sent * 100) : '0'}%)
              </div>
            )}

            {/* The node card */}
            {isEnd ? (
              <NodeCard node={node} onSelect={() => {}} onDelete={readOnly ? undefined : () => removeNode(node.id)} isSelected={false} analytics={nodeAnalytics?.[node.id]} errors={treeErrors?.[node.id]} warnings={treeWarnings?.[node.id]} hideDelay={depth === 0 && idx === 0} />
            ) : (
              <NodeCard
                node={node}
                hideDelay={depth === 0 && idx === 0}
                onSelect={() => { selectNode(node.id); closePicker(); }}
                onDelete={readOnly ? undefined : () => removeNode(node.id)}
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

                  {branchLabels.map((bl, i) => (
                    <div key={bl} className="relative flex flex-col items-center min-w-[320px] flex-1">
                      {branchLabels.length > 1 && (
                        <div 
                          className="absolute top-0 h-px bg-border z-0"
                          style={{
                            left: i === 0 ? '50%' : '-1rem',
                            right: i === branchLabels.length - 1 ? '50%' : '-1rem'
                          }}
                        />
                      )}
                      {/* Vertical line dropping down to the pill */}
                      <div className="w-px h-4 bg-border z-0" />
                      
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
                      />
                    </div>
                  ))}
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
                />
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ─── Root: Sequence Tree ───────────────────────────────────────────────────────

export function EISequenceTree({ 
  readOnly = false, 
  nodeAnalytics,
  onSave,
  onTemplatesClick
}: { 
  readOnly?: boolean
  treeErrors?: Record<string, string[]>
  treeWarnings?: Record<string, string[]>, 
  nodeAnalytics?: Record<string, {sent: number, replied: number, reply_rate: number}>,
  onSave?: (nodes: SeqTreeNode[]) => void | Promise<void>,
  onTemplatesClick?: () => void
}) {
  const { rootNodes, addRoot, addChild, stickyNotes, addStickyNote } = useHRTreeStore()
  const updateNodeData = useHRTreeStore(s => s.updateNodeData)
  const picker = usePickerStore()
  const [zoom, setZoom] = useState(1)
  const [hasFitView, setHasFitView] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [conflictModalOpen, setConflictModalOpen] = useState(false)
  const [pendingAddParams, setPendingAddParams] = useState<{type: EINodeType, data: any, parentId: string | null, branchLabel: string} | null>(null)
  const selectedNodeId = useHRTreeStore(s => s.selectedNodeId)
  const validation = React.useMemo(() => validateTree(rootNodes), [JSON.stringify(rootNodes)])
  const treeErrors = validation.errors;
  const treeWarnings = validation.warnings;

  

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




  // Drag to pan logic
  React.useEffect(() => {
    const handleKeyDown = async (e: KeyboardEvent) => {
      
      
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        if (onSave && !isSaving) {
          setIsSaving(true);
          try {
            await onSave(rootNodes);
          } finally {
            setIsSaving(false);
          }
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onSave, rootNodes, isSaving]);

  const containerRef = React.useRef<HTMLDivElement>(null)
  const isDragging = React.useRef(false)
  const lastMousePos = React.useRef({ x: 0, y: 0 })

  const handleMouseDown = (e: React.MouseEvent) => {
    // Only drag on left click, and ignore if clicking on a button or interactive element
    if (e.button !== 0) return
    const target = e.target as HTMLElement
    if (target.closest('button') || target.closest('.node-card')) return
    
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
              const data = { 
                label: def.label, 
                type, 
                color: def.color, 
                outputs: def.outputs, 
                delay: def.delayDefault ?? 0, 
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
          <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="bg-card border border-border shadow-2xl rounded-2xl p-6 max-w-md w-full mx-4"
            >
              <div className="flex items-center gap-3 text-amber-500 mb-4">
                <AlertCircle size={24} />
                <h3 className="text-lg font-bold text-foreground">Conflict Detected</h3>
              </div>
              <p className="text-sm text-muted-foreground leading-relaxed mb-6">
                You already have auto-withdraw enabled on your Connection node. Adding a manual Withdraw node will create a conflict. Do you want to disable auto-withdraw on the Connection node first?
              </p>
              <div className="flex items-center justify-end gap-3">
                <button
                  onClick={() => {
                    setConflictModalOpen(false)
                    setPendingAddParams(null)
                  }}
                  className="px-4 py-2 rounded-lg border border-border text-sm font-semibold text-foreground hover:bg-muted/50 transition-colors"
                >
                  Cancel
                </button>
                <button
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
                  className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-sm font-bold text-white transition-colors"
                >
                  Disable Auto-Withdraw and Continue
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Left Vertical Toolbar */}
      <div className="absolute top-6 left-6 z-40 flex flex-col gap-3 pointer-events-auto">
        {/* Zoom Group */}
        <div className="flex flex-row bg-card border border-border/60 shadow-sm rounded-xl overflow-hidden w-fit">
          <button onClick={() => setZoom(z => Math.min(z + 0.1, 2))} className="w-11 h-11 flex items-center justify-center hover:bg-muted/50 text-muted-foreground hover:text-foreground transition-colors border-r border-border/50" title="Zoom In">
            <ZoomIn size={18} />
          </button>
          <button onClick={() => setZoom(z => Math.max(z - 0.1, 0.4))} className="w-11 h-11 flex items-center justify-center hover:bg-muted/50 text-muted-foreground hover:text-foreground transition-colors border-r border-border/50" title="Zoom Out">
            <ZoomOut size={18} />
          </button>
          <button 
            onClick={() => {
            if (hasFitView) return;
            setHasFitView(true);
            if (containerRef.current) {
              const el = containerRef.current;
              const contentEl = el.firstElementChild as HTMLElement;
              if (contentEl) {
                // Determine unscaled dimensions
                // Since zoom is applied via CSS 'zoom' on this element, scrollWidth is already the intrinsic (unscaled) width
                const unscaledW = contentEl.scrollWidth;
                const unscaledH = contentEl.scrollHeight;
                
                // Calculate required zoom to fit inside container with padding
                const targetZoom = Math.min(
                  (el.clientWidth - 80) / Math.max(unscaledW, 1),
                  (el.clientHeight - 80) / Math.max(unscaledH, 1)
                );
                
                // Clamp zoom between 0.2 and 1.0
                const finalZoom = Math.max(0.2, Math.min(1.0, targetZoom));
                setZoom(finalZoom);
                
                // Center it after zoom applies
                setTimeout(() => {
                  el.scrollTo({
                    left: (el.scrollWidth - el.clientWidth) / 2,
                    top: (el.scrollHeight - el.clientHeight) / 2,
                    behavior: 'smooth'
                  });
                }, 50);
              }
            }
          }} className={cn("w-11 h-11 flex items-center justify-center transition-colors", hasFitView ? "text-muted-foreground/30 cursor-not-allowed pointer-events-none" : "hover:bg-muted/50 text-muted-foreground hover:text-foreground")} title="Fit to Canvas">
            <Maximize size={18} />
          </button>
        </div>

        {/* Action Group */}
        {!readOnly && (
          <div className="flex flex-col bg-card border border-border/60 shadow-sm rounded-2xl overflow-hidden mt-2">
            <button
              onClick={() => useHRTreeStore.getState().undo()}
              disabled={useHRTreeStore.getState().history.length === 0}
              className="flex items-center gap-2 px-4 py-3 hover:bg-muted/50 text-xs font-semibold text-muted-foreground hover:text-foreground disabled:opacity-50 transition-colors border-b border-border/50 w-full"
            >
              <Undo size={14} className="shrink-0" /> <span className="font-medium">Undo</span>
            </button>
            <button
              onClick={() => useHRTreeStore.getState().redo()}
              disabled={useHRTreeStore.getState().future.length === 0}
              className="flex items-center gap-2 px-4 py-3 hover:bg-muted/50 text-xs font-semibold text-muted-foreground hover:text-foreground disabled:opacity-50 transition-colors border-b border-border/50 w-full"
            >
              <Redo size={14} className="shrink-0" /> <span className="font-medium">Redo</span>
            </button>
            <button
              onClick={() => {
                let x = window.innerWidth / 2 - 100;
                let y = 100;
                if (containerRef.current) {
                  x = (containerRef.current.scrollLeft + containerRef.current.clientWidth / 2) / zoom - 100;
                  y = (containerRef.current.scrollTop + 100) / zoom;
                }
                addStickyNote(x, y);
              }}
              className="flex items-center gap-2 px-4 py-3 hover:bg-muted/50 text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors border-b border-border/50 w-full"
            >
              <MessageSquare size={14} className="shrink-0" /> <span className="font-medium">Add Sticky Note</span>
            </button>
            <button
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
              className="flex items-center gap-2 px-4 py-3 bg-indigo-500/5 hover:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 text-xs font-semibold transition-colors w-full disabled:opacity-50"
            >
              {isSaving ? (
                <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-indigo-600 dark:text-indigo-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
              ) : (
                <Save size={14} className="shrink-0" />
              )}
              <span className="font-medium">{isSaving ? 'Saving...' : 'Save'}</span>
            </button>
          </div>
        )}
      </div>
      <div 
        ref={containerRef}
        className="w-full h-full overflow-auto overscroll-none" 
        style={{ cursor: 'grab' }}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
      >
        <div 
          className="relative flex flex-col items-center min-w-max min-h-max py-20 px-20 transition-all duration-200 ease-out origin-top"
          style={{ zoom: zoom } as any}
        >
          {stickyNotes?.map(note => <EIStickyNote key={note.id} note={note} />)}
          {/* Sequence start node */}
          <div className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-card border border-border shadow-sm text-foreground text-sm font-semibold">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-indigo-500 dark:text-indigo-400">
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
          />
        </div>
      </div>
      
      {/* Side-panel for configuring selected node */}
      <EITreeNodeConfigPanel />
    </div>
  )
}

