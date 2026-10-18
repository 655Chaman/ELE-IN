import { useState, useEffect, useRef, useMemo } from "react"
import { motion, AnimatePresence } from "motion/react"
import {
  X, ChevronDown, Eye, Plus, RotateCcw, Info,
  UserPlus, MessageSquare, Mail, Search, Users,
  Heart, AtSign, Zap, CheckCircle2, Clock,
  Star, Mic2, CalendarCheck, Tag, Phone, Database, Bell, StopCircle,
  Upload, Volume2, Sparkles, AlertTriangle, Check, Copy, Loader2, ShieldCheck,
  Share2, Building2, Briefcase, MapPin, Award, Target,
  UserMinus, Split, GitFork, Gauge, Ban, Flag,
  Languages, Brain, ThumbsUp, ThumbsDown, Bot, Shield, BookOpen, Lock, ArrowUpRight, Cpu, Smile,
  Activity, DollarSign, Layers, TrendingUp
} from "lucide-react"

import useSWR from "swr"
import { usePickerStore } from "./EISequenceTree"
import { AdvancedSettingsPanel } from "@/components/AdvancedSettingsPanel"
import { cn } from "@/lib/utils"
import { ElesiumLogo } from "@/components/ElesiumLogo"
import { fetchWithAuth, fetcher } from "@/lib/apiClient"
import { usePaywall } from "@/contexts/PaywallContext"
import { toast } from "sonner"

import { useHRTreeStore } from "@campaigns/eiTreeStore"
import { HR_NODE_DEFS } from "@/lib/eiNodeDefs"
import { DeliverabilityStudioModal } from "@/components/campaigns/DeliverabilityStudioModal"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

export const hasNodeType = (nodes: any[], type: string): boolean => {
  for (const n of nodes) {
    if (n.data?.type === type || n.type === type) return true;
    for (const branch of Object.values(n.children || {}) as any[][]) {
      if (hasNodeType(branch, type)) return true;
    }
  }
  return false;
}

export const hasAutoWithdrawConnection = (nodes: any[]): boolean => {
  for (const n of nodes) {
    if ((n.data?.type === "connection_request" || n.type === "connection_request") && n.data?.withdraw_enabled) return true;
    for (const branch of Object.values(n.children || {}) as any[][]) {
      if (hasAutoWithdrawConnection(branch)) return true;
    }
  }
  return false;
}


// ─── Variables available for insertion ───────────────────────────────────────
// ─── Variables available for insertion ───────────────────────────────────────
const CREDIT_COST_MAP: Record<string, number> = {
  ai_generate_reply: 5,
  ai_personalize: 2,
  ai_detect_sentiment: 2,
  ai_generate_icebreaker: 2,
  ai_translate_message: 1,
  ai_write_connection_note: 1,
  ai_query_knowledge_base: 3,
  ai_query_brain: 3,
  ai_score_icp: 1,
  ai_buying_signal: 1,
  ai_detect_buying_signal: 1,
  ai_summarize_profile: 1,
  ai_detect_competitor: 1,
  ai_best_send_time: 1,
  find_email: 5,
  find_personal_email: 5,
  verify_email: 1,
  send_email: 1,
  apollo_enrich: 5,
  apify_scrape: 50,
  displacement_pitch: 2,
  social_prewarm_comment: 1,
  thought_leadership_post: 2,
  multimodal_voice_script: 2,
  multimodal_video_card: 3,
};

const VARIABLES = [
  { label: "First name", value: "{{first_name | fallback: there}}", fallback: "there" },
  { label: "Company", value: "{{company | fallback: your team}}", fallback: "your team" },
  { label: "Job title", value: "{{job_title | fallback: your role}}", fallback: "your role" },
  { label: "Industry", value: "{{industry | fallback: your space}}", fallback: "your space" },
  { label: "Location", value: "{{location | fallback: your area}}", fallback: "your area" },
  { label: "Last name", value: "{{last_name | fallback: there}}", fallback: "there" },
  { label: "Mutual connections", value: "{{mutual_connections | fallback: mutual colleagues}}", fallback: "mutual colleagues" },
]

export const PREVIEW_PERSONAS = [
  {
    id: "alex",
    label: "Alex (VP Eng @ Acme)",
    first_name: "Alex",
    last_name: "Johnson",
    company: "Acme Cloud Technologies",
    job_title: "VP of Engineering",
    location: "San Francisco, CA",
    industry: "Enterprise Cloud",
    mutual_connections: "Sarah Miller and 4 others",
  },
  {
    id: "sarah",
    label: "Sarah (Founder @ ScaleUp)",
    first_name: "Sarah",
    last_name: "Chen",
    company: "ScaleUp AI",
    job_title: "Founder & CEO",
    location: "Austin, TX",
    industry: "Artificial Intelligence",
    mutual_connections: "2 mutual colleagues",
  },
  {
    id: "empty",
    label: "Empty Data (Test Fallbacks)",
    first_name: "",
    last_name: "",
    company: "",
    job_title: "",
    location: "",
    industry: "",
    mutual_connections: "",
  },
]

export const WORST_CASE_PERSONA = {
  id: "worst_case",
  label: "Worst Case (Long Fields)",
  first_name: "Christopher",
  last_name: "Montgomery",
  company: "Global Logistics & Freight Solutions Inc.",
  job_title: "Chief Information Security Officer",
  location: "Greater San Francisco Bay Area",
  industry: "Enterprise Supply Chain Infrastructure",
  mutual_connections: "14 mutual colleagues",
}

export function resolveVariables(template: string, persona: typeof PREVIEW_PERSONAS[0] | typeof WORST_CASE_PERSONA): string {
  if (!template) return ""
  return template.replace(/\{\{([a-zA-Z0-9_]+)(\s*\|\s*fallback:\s*([^}]+))?\}\}/g, (_, key, __, fallback) => {
    const trimmedKey = key.trim()
    const fallbackVal = fallback ? fallback.trim() : ""
    const val = (persona as any)[trimmedKey]
    if (val && String(val).trim().length > 0) {
      return String(val)
    }
    return fallbackVal || `[${trimmedKey}]`
  })
}

export const CONNECTION_STARTERS = [
  {
    id: "peer",
    title: "Peer & Space",
    desc: "Warm & respectful peer hook",
    snippet: "Hi {{first_name | fallback: there}}, noticed your work in {{industry | fallback: tech}} at {{company | fallback: your team}}. Always great connecting with leaders in this space!",
    badge: "Recommended",
  },
  {
    id: "growth",
    title: "Growth Curiosity",
    desc: "Conversational problem hook",
    snippet: "Hi {{first_name | fallback: there}}, saw {{company | fallback: your team}}'s recent updates. Curious how your team is approaching growth this quarter — would love to connect!",
    badge: "High Reply",
  },
  {
    id: "short",
    title: "Short & Clean",
    desc: "Lowest friction, high acceptance",
    snippet: "Hi {{first_name | fallback: there}}, came across your profile and would love to connect and follow {{company | fallback: your team}}'s journey!",
    badge: "68% Accept Rate",
  },
  {
    id: "mutual",
    title: "Mutual Orbit",
    desc: "Leverages common ground",
    snippet: "Hi {{first_name | fallback: there}}, saw we share {{mutual_connections | fallback: mutual colleagues}} in {{location | fallback: tech}}. Would love to connect!",
    badge: "Warm Intro",
  },
]

export const MESSAGE_HOOKS = [
  {
    id: "problem",
    title: "Problem-Centric Hook",
    desc: "Addresses core bottleneck",
    snippet: "Hi {{first_name | fallback: there}},\n\nSaw you're leading {{job_title | fallback: your team}} at {{company | fallback: your company}}. Many teams in {{industry | fallback: your space}} tell us their biggest bottleneck is consistent outbound pipeline without burning sender reputation.\n\nCurious if that's something on your radar right now?",
  },
  {
    id: "case_study",
    title: "Metric / Social Proof",
    desc: "Concrete business result",
    snippet: "Hey {{first_name | fallback: there}},\n\nQuick thought — we recently helped another {{industry | fallback: tech}} team book 14 qualified meetings in their first 3 weeks without relying on SDR cold calls.\n\nWorth a 3-minute glance at how they did it?",
  },
  {
    id: "casual",
    title: "Casual Low-Friction",
    desc: "Low pressure conversation",
    snippet: "Hi {{first_name | fallback: there}},\n\nI know you're busy running things at {{company | fallback: your team}}, so I'll keep this brief.\n\nAre you open to a 5-minute chat next Tuesday to see if there's mutual synergy?",
  },
]

function NakedVariableWarning({ text, onFix }: { text: string; onFix?: (fixed: string) => void }) {
  if (!text.includes('{{')) return null;
  if (text.includes('| fallback:')) return null;
  
  const match = text.match(/{{([a-zA-Z0-9_]+)\s*}}/);
  const varName = match ? match[1] : "variable";

  const handleAutoFix = () => {
    if (!onFix) return;
    const fallbackMap: Record<string, string> = {
      first_name: "there",
      last_name: "there",
      company: "your team",
      job_title: "your role",
      location: "your area",
      industry: "your space",
      mutual_connections: "mutual colleagues",
    };
    const chosenFallback = fallbackMap[varName] || "there";
    const fixed = text.replace(new RegExp(`{{${varName}\\s*}}`, 'g'), `{{${varName} | fallback: ${chosenFallback}}}`);
    onFix(fixed);
  };
  
  return (
    <div className="mt-3 p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-xs text-amber-600 dark:text-amber-400 flex items-start justify-between gap-3 leading-relaxed shadow-sm">
      <div className="flex items-start gap-2">
        <AlertTriangle size={14} className="shrink-0 mt-0.5 text-amber-500" />
        <div className="flex flex-col gap-1">
          <span className="font-bold">Missing Fallback on {"{{"}{varName}{"}}"}</span>
          <span className="text-amber-800/80 dark:text-amber-300/80 text-[11px]">
            If privacy walls hide this field, outreach will pause to protect your sender reputation.
          </span>
        </div>
      </div>
      {onFix && (
        <button
          type="button"
          onClick={handleAutoFix}
          className="shrink-0 px-2.5 py-1 bg-amber-500/20 hover:bg-amber-500/30 text-amber-800 dark:text-amber-200 font-semibold rounded-lg text-[11px] transition-colors whitespace-nowrap"
        >
          Auto-Add Fallback
        </button>
      )}
    </div>
  )
}

// ─── Delay selector with calibrated quick presets ────────────────────────────
function DelaySelector({ value, unit = "days", onChange }: { value: number; unit?: string; onChange: (v: number, u: string) => void }) {
  useEffect(() => {
    if (value === undefined || value === null || isNaN(value) || value < 1) {
      onChange(1, unit || "days");
    }
  }, [value, unit, onChange]);

  const displayVal = value !== undefined && value !== null && !isNaN(value) && value >= 1 ? value : 1;

  const PRESETS = [
    { label: "1 Day (Fast)", val: 1, u: "days" },
    { label: "3 Days (Recommended • 42% reply rate)", val: 3, u: "days" },
    { label: "5 Days (Gentle)", val: 5, u: "days" },
    { label: "1 Week", val: 1, u: "weeks" },
  ];

  return (
    <div className="flex flex-col gap-2.5">
      {/* Quick 1-tap Preset Chips (Transcript 1, Invention 3) */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-[11px] font-semibold text-muted-foreground mr-1 flex items-center gap-1">
          <Clock size={12} /> Delay:
        </span>
        {PRESETS.map((p) => {
          const isSelected = displayVal === p.val && unit === p.u;
          return (
            <button
              key={p.label}
              type="button"
              onClick={() => onChange(p.val, p.u)}
              className={cn(
                "px-2.5 py-1 rounded-lg text-[11px] font-medium border transition-all",
                isSelected
                  ? "bg-primary/15 border-primary/40 text-primary font-bold shadow-xs"
                  : "bg-background/40 border-border/40 text-muted-foreground hover:text-foreground hover:bg-muted/40"
              )}
            >
              {p.label}
            </button>
          );
        })}
      </div>

      {/* Granular Custom Override */}
      <div className="flex items-center gap-2 pt-1">
        <span className="text-[11px] text-muted-foreground">Custom: Wait</span>
        <input
          type="number"
          min={1}
          step="1"
          value={displayVal}
          onChange={e => {
            const raw = e.target.value;
            if (raw === "") {
              // User cleared field while typing; avoid emitting NaN to store
              return;
            }
            const val = parseFloat(raw);
            const clamped = isNaN(val) || val < 1 ? 1 : Math.ceil(val);
            onChange(clamped, unit);
          }}
          onBlur={e => {
            if (e.target.value === "" || isNaN(parseFloat(e.target.value)) || parseFloat(e.target.value) < 1) {
              onChange(1, unit);
            }
          }}
          className="w-16 rounded-lg bg-card border border-border px-2 py-1 text-xs text-foreground focus:outline-none focus:border-primary text-center font-mono"
        />
        <Select value={unit} onValueChange={val => onChange(displayVal, val)}>
          <SelectTrigger size="sm" className="w-24 bg-card border-border text-xs h-7">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="minutes">Minutes</SelectItem>
            <SelectItem value="hours">Hours</SelectItem>
            <SelectItem value="days">Days</SelectItem>
            <SelectItem value="weeks">Weeks</SelectItem>
          </SelectContent>
        </Select>
        <span className="text-[11px] text-muted-foreground">before executing</span>
      </div>
    </div>
  )
}

// ─── Message editor with version A/B + variables ──────────────────────────────
function MessageEditor({
  label,
  value,
  onChange,
  maxChars = 8000,
  placeholder = "Write a message",
}: {
  label: string
  value: string
  onChange: (v: string) => void
  maxChars?: number
  placeholder?: string
}) {
  const [showVars, setShowVars] = useState(false)
  const [showPreview, setShowPreview] = useState(false)
  const [previewPersonaId, setPreviewPersonaId] = useState<string>("alex")
  const [pendingHook, setPendingHook] = useState<typeof MESSAGE_HOOKS[0] | null>(null)
  const [copied, setCopied] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setShowVars(false)
        setPendingHook(null)
      }
    }
    if (showVars || pendingHook) document.addEventListener("keydown", handleKeyDown)
    return () => document.removeEventListener("keydown", handleKeyDown)
  }, [showVars, pendingHook])

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowVars(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [dropdownRef])

  const insertVar = (varStr: string) => {
    onChange((value || "") + " " + varStr)
    setShowVars(false)
  }

  const activePersona = PREVIEW_PERSONAS.find(p => p.id === previewPersonaId) || PREVIEW_PERSONAS[0]
  const previewText = resolveVariables(value || "", activePersona)

  const charsLeft = maxChars - (value?.length || 0)

  const handleApplyHook = (hook: typeof MESSAGE_HOOKS[0]) => {
    if ((value || "").trim().length > 0) {
      setPendingHook(hook)
    } else {
      onChange(hook.snippet)
    }
  }

  const handleCopyPreview = () => {
    if (!previewText) return
    navigator.clipboard.writeText(previewText)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="space-y-2.5">
      <div className="flex items-center justify-between">
        <label className="text-xs font-semibold text-foreground flex items-center gap-1.5">
          <span>{label}</span>
        </label>
        <button
          type="button"
          onClick={() => setShowPreview(p => !p)}
          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-[11px] font-medium transition-all ${
            showPreview
              ? "border-primary bg-primary/10 text-primary font-semibold shadow-xs"
              : "border-border bg-card hover:bg-muted text-muted-foreground"
          }`}
        >
          <Eye size={12} /> {showPreview ? "Back to Editor" : "Live Prospect Preview"}
        </button>
      </div>

      {/* Starter Hooks (Layer 0 blank canvas eradication) */}
      {!showPreview && (
        <div className="flex flex-col gap-1.5 p-2.5 rounded-xl bg-card border border-border/70 shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-[10px] uppercase font-bold tracking-wider text-muted-foreground flex items-center gap-1">
              <Sparkles size={11} className="text-indigo-500" /> High-Converting Openers:
            </span>
          </div>
          <div className="flex items-center gap-1.5 flex-wrap">
            {MESSAGE_HOOKS.map((hook) => (
              <button
                key={hook.id}
                type="button"
                onClick={() => handleApplyHook(hook)}
                className="px-2 py-1 rounded-md text-[11px] font-medium bg-muted/40 hover:bg-muted border border-border/40 text-foreground transition-colors text-left cursor-pointer"
              >
                {hook.title}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Overwrite Confirmation Modal / Inline Alert (Layer 2 Paranoia) */}
      {pendingHook && (
        <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-xs flex flex-col gap-2">
          <div className="flex items-start gap-2">
            <AlertTriangle size={15} className="text-amber-500 shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="font-semibold text-amber-700 dark:text-amber-300">
                Replace existing message draft?
              </p>
              <p className="text-[11px] text-amber-800/80 dark:text-amber-300/80">
                Applying &quot;{pendingHook.title}&quot; will overwrite your current text.
              </p>
            </div>
          </div>
          <div className="flex items-center justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={() => setPendingHook(null)}
              className="px-2.5 py-1 text-[11px] rounded-lg border border-border bg-card text-muted-foreground hover:text-foreground"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => {
                onChange(pendingHook.snippet)
                setPendingHook(null)
              }}
              className="px-3 py-1 text-[11px] font-bold rounded-lg bg-amber-500 text-white hover:bg-amber-600 transition-colors"
            >
              Confirm Replace
            </button>
          </div>
        </div>
      )}

      {showPreview ? (
        <div className="flex flex-col gap-2">
          {/* Persona Switcher Tabs */}
          <div className="flex items-center gap-1.5 p-1 rounded-lg bg-muted/40 border border-border/50">
            <span className="text-[10px] font-semibold text-muted-foreground px-1.5">Preview As:</span>
            {PREVIEW_PERSONAS.map(p => (
              <button
                key={p.id}
                type="button"
                onClick={() => setPreviewPersonaId(p.id)}
                className={cn(
                  "px-2 py-0.5 rounded text-[10px] font-medium transition-all",
                  previewPersonaId === p.id
                    ? "bg-primary text-primary-foreground font-bold shadow-xs"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                {p.label}
              </button>
            ))}
          </div>

          <div className="w-full rounded-xl bg-indigo-50/40 dark:bg-indigo-950/20 border border-indigo-200 dark:border-indigo-500/30 px-3.5 py-3 text-xs text-foreground leading-relaxed whitespace-pre-wrap min-h-[120px] relative group">
            {previewText || <span className="text-muted-foreground italic">No message written yet</span>}
            {previewText && (
              <button
                type="button"
                onClick={handleCopyPreview}
                className="absolute top-2.5 right-2.5 px-2 py-1 rounded-md bg-background/80 hover:bg-background border border-border text-[10px] text-muted-foreground hover:text-foreground flex items-center gap-1 transition-all opacity-80 group-hover:opacity-100"
              >
                {copied ? <Check size={11} className="text-emerald-500" /> : <Copy size={11} />}
                <span>{copied ? "Copied" : "Copy"}</span>
              </button>
            )}
          </div>
          <div className="flex items-center justify-between text-[10px] text-muted-foreground px-1">
            <span>Simulated message with live prospect attributes</span>
            <span>{previewText.length} characters resolved</span>
          </div>
        </div>
      ) : (
        <textarea
          maxLength={maxChars}
          value={value || ""}
          onChange={e => {
            if (e.target.value.length <= maxChars) {
              onChange(e.target.value)
            }
          }}
          rows={5}
          placeholder={placeholder}
          className="w-full rounded-xl bg-card border border-border px-3.5 py-3 text-xs text-foreground
                     placeholder:text-muted-foreground focus:outline-none focus:border-primary resize-none transition-colors leading-relaxed"
        />
      )}
      
      {!showPreview && <NakedVariableWarning text={value || ""} onFix={onChange} />}

      {/* Quick Variable Pills */}
      {!showPreview && (
        <div className="flex items-center gap-1.5 mt-2 flex-wrap">
          <span className="text-[10px] uppercase font-bold tracking-wider text-muted-foreground/70 mr-0.5">
            Insert:
          </span>
          {VARIABLES.slice(0, 4).map((v) => (
            <button
              key={v.label}
              type="button"
              onClick={() => insertVar(v.value)}
              className="px-2 py-0.5 rounded-md text-[10px] font-medium bg-muted/40 hover:bg-muted border border-border/40 text-muted-foreground hover:text-foreground transition-colors"
            >
              + {v.label}
            </button>
          ))}
        </div>
      )}

      {/* Toolbar & Character Gauge */}
      {!showPreview && (
        <div className="flex items-center justify-between gap-2 pt-1">
          <div className="relative flex-1" ref={dropdownRef}>
            <button
              type="button"
              onClick={() => setShowVars(p => !p)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border
                         bg-card hover:bg-muted text-xs text-muted-foreground transition-all w-full justify-between"
            >
              <span className="flex items-center gap-1.5"><Sparkles size={11} className="text-primary" /> All variables</span>
              <ChevronDown size={11} className={`transition-transform ${showVars ? "rotate-180" : ""}`} />
            </button>
            <AnimatePresence>
              {showVars && (
                <motion.div
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  className="absolute top-full left-0 right-0 mt-1 z-40 rounded-xl bg-card border border-border shadow-xl overflow-hidden"
                >
                  {VARIABLES.map(v => (
                    <button
                      key={v.value}
                      type="button"
                      onClick={() => insertVar(v.value)}
                      className="w-full flex items-center justify-between px-3 py-2 text-xs hover:bg-muted transition-colors text-left"
                    >
                      <span className="text-foreground whitespace-nowrap mr-2">{v.label}</span>
                      <span className="text-muted-foreground font-mono text-[10px] truncate">{v.value}</span>
                    </button>
                  ))}
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          <span className={`text-[11px] font-mono shrink-0 ${charsLeft < 50 ? "text-rose-500 font-bold" : "text-muted-foreground"}`}>
            {charsLeft} chars left
          </span>
        </div>
      )}
    </div>
  )
}

function ABMessageEditor({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  const [activeTab, setActiveTab] = useState<'a'|'b'|'c'>('a')
  const tabs = ['a', 'b', 'c'] as const
  
  const deleteTab = (tab: 'a'|'b'|'c') => {
    onChange(`body_${tab}`, "")
    setActiveTab('a')
  }

  const hasA = data.body_a !== undefined && data.body_a !== ""
  const hasB = data.body_b !== undefined && data.body_b !== ""
  const hasC = data.body_c !== undefined && data.body_c !== ""
  
  const activeCount = (hasA ? 1 : 0) + (hasB ? 1 : 0) + (hasC ? 1 : 0)
  
  const addVariant = () => {
    if (!hasB) { setActiveTab('b'); onChange('body_b', ' ') }
    else if (!hasC) { setActiveTab('c'); onChange('body_c', ' ') }
  }

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Delay</label>
        <DelaySelector value={data.delay} unit={data.delayUnit || "days"} onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }} />
      </div>

      <div>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-1.5">
            {tabs.map(t => {
              const hasContent = data[`body_${t}`] !== undefined && data[`body_${t}`] !== ""
              if (!hasContent && activeTab !== t) return null
              return (
                <button
                  key={t}
                  onClick={() => setActiveTab(t)}
                  className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
                    activeTab === t
                      ? "bg-indigo-600 text-white"
                      : "bg-muted text-muted-foreground hover:text-foreground"
                  }`}
                >
                  Variant {t.toUpperCase()}
                </button>
              )
            })}
            {activeCount < 3 && (
              <button
                onClick={addVariant}
                className="w-7 h-7 rounded-md bg-muted hover:bg-muted flex items-center justify-center text-muted-foreground hover:text-foreground transition-all"
              >
                <Plus size={14} />
              </button>
            )}
          </div>
          {activeTab !== 'a' && (
            <button onClick={() => deleteTab(activeTab)} className="text-[10px] text-red-400 hover:text-red-300 transition-colors">
              Delete Variant
            </button>
          )}
        </div>

        <MessageEditor
          label={`Message (Variant ${activeTab.toUpperCase()})`}
          value={data[`body_${activeTab}`] || ""}
          onChange={v => onChange(`body_${activeTab}`, v)}
          maxChars={8000}
          placeholder={`Write variant ${activeTab.toUpperCase()}...`}
        />
      </div>

      <FallbackEditor data={data} onChange={onChange} maxChars={8000} />
      
      <div>
        <p className="text-xs font-semibold text-foreground mb-3 flex items-center gap-2">
          Advanced settings <ChevronDown size={13} className="text-muted-foreground" />
        </p>
        <div className="space-y-3 pl-2 border-l border-border/50">
           <div>
            <label className="block text-xs font-semibold text-foreground mb-1">Winner threshold</label>
            <p className="text-[10px] text-muted-foreground mb-2">Auto-pick the winning variant after N replies.</p>
            <input
              type="number"
              value={data.winner_threshold !== undefined ? data.winner_threshold : 50}
              onChange={e => onChange("winner_threshold", Number(e.target.value))}
              className="w-32 rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground
                         placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
            />
          </div>
        </div>
      </div>
    </div>
  )
}

function FallbackEditor({ data, onChange, maxChars = 8000, fallbackLabel = "Fallback message" }: { data: any, onChange: (k: string, v: any) => void, maxChars?: number, fallbackLabel?: string }) {
  return (
    <div>
      <label className="block text-xs font-semibold text-foreground mb-1.5">{fallbackLabel}
        <span className="ml-2 text-[10px] text-muted-foreground font-normal normal-case">
          (Used if the primary note fails due to LinkedIn character limits or premium restrictions)
        </span>
      </label>
      <textarea
        maxLength={maxChars}
        value={data.fallback || ""}
        onChange={e => {
          if (e.target.value.length <= maxChars) {
            onChange("fallback", e.target.value)
          }
        }}
        rows={3}
        placeholder="Fallback message..."
        className="w-full rounded-xl bg-card border border-border px-3.5 py-3 text-xs text-foreground
                   placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none"
      />
      
      <NakedVariableWarning text={data.fallback || ""} />
      
      <p className="text-[10px] text-muted-foreground mt-1">{maxChars - (data.fallback?.length || 0)} characters left</p>
    </div>
  )
}

function SendMessageConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  const [isUploading, setIsUploading] = useState(false);
  const attachmentInputRef = useRef<HTMLInputElement>(null);

  const handleAttachmentUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (file.size > 25 * 1024 * 1024) {
      toast.error("Attachment size cannot exceed 25MB.");
      return;
    }

    setIsUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetchWithAuth("/api/elein/campaigns/upload_attachment", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => null);
        throw new Error(errData?.detail || `Upload failed with status ${res.status}`);
      }

      const payload = await res.json();
      onChange("attachment_url", payload.url);
      onChange("attachment_filename", payload.filename || file.name);
      if (payload.attachment_type === "image") {
        onChange("attachment_type", "Image");
        onChange("image_url", payload.url);
      } else {
        onChange("attachment_type", "Document");
        onChange("doc_url", payload.url);
      }
      toast.success("Attachment uploaded successfully!");
    } catch (err: any) {
      toast.error(err.message || "Failed to upload attachment");
    } finally {
      setIsUploading(false);
      if (attachmentInputRef.current) attachmentInputRef.current.value = "";
    }
  };

  return (
    <div className="space-y-6">
      {/* Prerequisite & Compatibility Banner */}
      <div className="p-3.5 rounded-xl bg-amber-500/10 dark:bg-amber-950/30 border border-amber-500/30 dark:border-amber-600/40 flex items-start gap-2.5">
        <AlertTriangle size={16} className="text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
        <div className="space-y-1">
          <span className="text-xs font-semibold text-amber-900 dark:text-amber-200 block">
            Requires 1st-Degree Connection
          </span>
          <p className="text-[11px] text-amber-800/90 dark:text-amber-300/80 leading-relaxed">
            LinkedIn only supports standard direct messages with accepted 1st-degree connections. Ensure an accepted connection step precedes this, or leave auto-fallback enabled below.
          </p>
        </div>
      </div>

      {/* Auto-Fallback Checkbox (Paranoia Layer 1 & 2) */}
      <div className="p-3 rounded-xl bg-card border border-border flex items-start gap-3">
        <input
          id="fallback_to_connection_request_msg"
          type="checkbox"
          checked={data.fallback_to_connection_request !== false}
          onChange={e => onChange("fallback_to_connection_request", e.target.checked)}
          className="mt-0.5 h-4 w-4 rounded border-border text-indigo-600 focus:ring-indigo-500 cursor-pointer"
        />
        <label htmlFor="fallback_to_connection_request_msg" className="cursor-pointer select-none space-y-0.5">
          <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            Auto-fallback to Connection Request
            <span className="text-[10px] font-medium px-1.5 py-0.2 rounded bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30">
              Recommended
            </span>
          </span>
          <p className="text-[11px] text-muted-foreground leading-relaxed">
            If the lead is not connected (message modal absent), automatically dispatch a Connection Request with this message (up to 300 chars) instead of failing.
          </p>
        </label>
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Delay</label>
        <DelaySelector value={data.delay} unit={data.delayUnit || "days"} onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }} />
      </div>

      <MessageEditor
        label="Message"
        value={data.body || ""}
        onChange={v => onChange("body", v)}
        maxChars={8000}
        placeholder="Write a message"
      />

      {/* Attachments Section (Documents & Images) */}
      <div className="p-4 rounded-xl bg-muted/30 border border-border/70 space-y-3">
        <div className="flex items-center justify-between">
          <label className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            <span>Attachment</span>
            <span className="text-[10px] font-normal text-muted-foreground">(optional)</span>
          </label>
          <div className="flex items-center gap-1 bg-card border border-border p-0.5 rounded-lg">
            {(["None", "Document", "Image"] as const).map(t => (
              <button
                key={t}
                type="button"
                onClick={() => {
                  onChange("attachment_type", t);
                  if (t === "None") onChange("attachment_url", "");
                }}
                className={cn(
                  "px-2 py-0.5 rounded text-[11px] font-medium transition-all",
                  (data.attachment_type || "None") === t
                    ? "bg-indigo-600 text-white font-bold"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        {data.attachment_type && data.attachment_type !== "None" && (
          <div className="space-y-2 pt-1">
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-muted-foreground">
                {data.attachment_type === "Image" ? "PNG, JPG, WEBP (max 25MB)" : "PDF, DOCX, TXT (max 25MB)"}
              </span>
              <div className="flex items-center gap-2">
                <input
                  ref={attachmentInputRef}
                  type="file"
                  accept={data.attachment_type === "Image" ? "image/*" : ".pdf,.doc,.docx,.txt,.csv"}
                  className="hidden"
                  onChange={handleAttachmentUpload}
                />
                <button
                  type="button"
                  disabled={isUploading}
                  onClick={() => attachmentInputRef.current?.click()}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-indigo-50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 hover:bg-indigo-100 dark:hover:bg-indigo-900/60 text-[11px] font-medium border border-indigo-200/80 dark:border-indigo-800/60 transition-colors cursor-pointer disabled:opacity-50"
                >
                  {isUploading ? (
                    <>
                      <Loader2 size={11} className="animate-spin" />
                      <span>Uploading...</span>
                    </>
                  ) : (
                    <>
                      <Upload size={11} />
                      <span>Upload {data.attachment_type}</span>
                    </>
                  )}
                </button>
              </div>
            </div>

            <input
              value={data.attachment_url || data.doc_url || data.image_url || ""}
              onChange={e => {
                onChange("attachment_url", e.target.value);
                if (data.attachment_type === "Document") onChange("doc_url", e.target.value);
                if (data.attachment_type === "Image") onChange("image_url", e.target.value);
              }}
              placeholder={`https://... or click Upload ${data.attachment_type}`}
              className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 font-mono text-[11px]"
            />

            {(data.attachment_url || data.doc_url || data.image_url) && (
              <div className="p-2 rounded-lg bg-card border border-border/80 flex items-center justify-between text-[11px]">
                <span className="text-foreground font-medium truncate max-w-[240px]">
                  {data.attachment_filename || "Attached file"}
                </span>
                <button
                  type="button"
                  onClick={() => {
                    onChange("attachment_url", "");
                    onChange("doc_url", "");
                    onChange("image_url", "");
                    onChange("attachment_filename", "");
                  }}
                  className="text-rose-500 hover:text-rose-600 text-[10px] font-semibold"
                >
                  Remove
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      <FallbackEditor data={data} onChange={onChange} maxChars={8000} />

      <div>
        <p className="text-xs font-semibold text-foreground mb-3 flex items-center gap-2">
          Advanced settings <ChevronDown size={13} className="text-muted-foreground" />
        </p>
        <div className="space-y-3 pl-2 border-l border-border/50">
          <div className="flex items-center gap-2 mt-1">
            <button
              onClick={() => onChange("track_links", !(data.track_links ?? true))}
              className={`w-8 h-4 rounded-full transition-colors relative ${(data.track_links ?? true) ? "bg-indigo-600" : "bg-muted"}`}
            >
              <div className={`w-3 h-3 rounded-full bg-white absolute top-0.5 transition-all ${(data.track_links ?? true) ? "left-4.5" : "left-0.5"}`} />
            </button>
            <span className="text-xs text-muted-foreground">Track link clicks</span>
          </div>
        </div>
      </div>
    </div>
  )
}

function AIModelSelector({
  value,
  onChange,
  models = ["Auto-Route (Recommended)", "DeepSeek V4 Pro", "GPT-OS", "Kimi k3", "Llama-3.2 11B", "Nemotron 120B"],
  label = "AI Routing Model",
}: {
  value?: string;
  onChange: (v: string) => void;
  models?: string[];
  label?: string;
}) {
  const { openPaywall } = usePaywall();
  const { data: billing } = useSWR<any>('/api/elein/workspaces/billing', fetcher);
  const tier = billing?.tier || 'FREE';
  const isPro = (tier === 'PRO' || tier === 'ENTERPRISE') || Boolean(billing?.tier_limits?.can_choose_ai_models);

  const selectedValue = value || models[0];

  const handleSelect = (newVal: string) => {
    if (newVal !== "Auto-Route (Recommended)" && !isPro) {
      openPaywall({ featureName: "Advanced AI Model Selection" });
      return;
    }
    onChange(newVal);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <label className="text-xs font-semibold text-foreground flex items-center gap-1.5">
          <ElesiumLogo size={13} />
          {label}
        </label>
        {!isPro && (
          <span className="text-[10px] font-semibold text-amber-600 dark:text-amber-400 bg-amber-500/10 px-1.5 py-0.2 rounded border border-amber-500/20 flex items-center gap-0.5">
            <Lock size={9} /> Pro Models
          </span>
        )}
      </div>
      <Select value={selectedValue} onValueChange={handleSelect}>
        <SelectTrigger className="w-full bg-card border-border text-xs h-9">
          <SelectValue placeholder="Select model..." />
        </SelectTrigger>
        <SelectContent>
          {models.map((m) => (
            <SelectItem key={m} value={m}>
              {m}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

function SendAiMessageConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  const tones = ["Friendly & Casual", "Professional & Direct", "Short & Punchy", "Funny & Witty"];
  const models = ["Auto-Route (Recommended)", "DeepSeek V4 Pro", "GPT-OS", "Kimi k3", "Llama-3.2 11B", "Nemotron 120B"];

  return (
    <div className="space-y-6">
      {/* Prerequisite Banner */}
      <div className="p-3.5 rounded-xl bg-amber-500/10 dark:bg-amber-950/30 border border-amber-500/30 dark:border-amber-600/40 flex items-start gap-2.5">
        <AlertTriangle size={16} className="text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
        <div className="space-y-1">
          <span className="text-xs font-semibold text-amber-900 dark:text-amber-200 block">
            Requires 1st-Degree Connection
          </span>
          <p className="text-[11px] text-amber-800/90 dark:text-amber-300/80 leading-relaxed">
            AI Direct Messages require an existing 1st-degree connection. If not yet accepted, leave auto-fallback enabled below.
          </p>
        </div>
      </div>

      {/* Auto-Fallback Checkbox */}
      <div className="p-3 rounded-xl bg-card border border-border flex items-start gap-3">
        <input
          id="fallback_to_connection_request_ai"
          type="checkbox"
          checked={data.fallback_to_connection_request !== false}
          onChange={e => onChange("fallback_to_connection_request", e.target.checked)}
          className="mt-0.5 h-4 w-4 rounded border-border text-indigo-600 focus:ring-indigo-500 cursor-pointer"
        />
        <label htmlFor="fallback_to_connection_request_ai" className="cursor-pointer select-none space-y-0.5">
          <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            Auto-fallback to Connection Request
            <span className="text-[10px] font-medium px-1.5 py-0.2 rounded bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30">
              Recommended
            </span>
          </span>
          <p className="text-[11px] text-muted-foreground leading-relaxed">
            If the lead is not connected, automatically send a Connection Request with the AI-generated note instead of failing.
          </p>
        </label>
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Delay</label>
        <DelaySelector value={data.delay} unit={data.delayUnit || "days"} onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }} />
      </div>

      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="block text-xs font-semibold text-foreground flex items-center gap-1.5">
            <ElesiumLogo size={13} />
            <span>AI Goal & Pitch Instruction</span>
          </label>
          <span className="text-[10px] text-muted-foreground">{(data.pitch || data.prompt || "").length}/7000</span>
        </div>
        <textarea
          rows={4}
          maxLength={7000}
          value={data.pitch || data.prompt || ""}
          onChange={e => {
            onChange("pitch", e.target.value);
            onChange("prompt", e.target.value);
          }}
          placeholder="Talk directly to the AI: e.g. See if they are hiring SDRs. If yes, pitch our recruitment platform and propose a 10-minute demo call."
          className="w-full rounded-xl bg-card border border-border px-3.5 py-3 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none leading-relaxed"
        />
        <p className="text-[10px] text-muted-foreground mt-1">
          The AI will blend this goal with each prospect's live LinkedIn headline, bio, and recent posts.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">Tone</label>
          <Select
            value={data.tone || tones[1]}
            onValueChange={val => onChange("tone", val)}
          >
            <SelectTrigger className="w-full bg-card border-border text-xs h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {tones.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <AIModelSelector
            value={data.ai_model}
            onChange={(m) => onChange("ai_model", m)}
            models={models}
            label="AI Routing Model"
          />
        </div>
      </div>

      <FallbackEditor data={data} onChange={onChange} maxChars={8000} />
    </div>
  );
}
// ─── Node-specific config panels ──────────────────────────────────────────────
// ─── Node-specific config panels ──────────────────────────────────────────────
function ConnectionRequestConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  const note: string = data.note || ""
  const [showVars, setShowVars] = useState(false)
  const [showPreview, setShowPreview] = useState(false)
  const [previewPersonaId, setPreviewPersonaId] = useState<string>("alex")
  const [pendingStarter, setPendingStarter] = useState<typeof CONNECTION_STARTERS[0] | null>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setShowVars(false)
        setPendingStarter(null)
      }
    }
    if (showVars || pendingStarter) document.addEventListener("keydown", handleKeyDown)
    return () => document.removeEventListener("keydown", handleKeyDown)
  }, [showVars, pendingStarter])

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowVars(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [dropdownRef])

  const insertVar = (v: string) => {
    onChange("note", note + " " + v)
    setShowVars(false)
  }

  const rootNodes = useHRTreeStore(s => s.rootNodes)
  const hasManualWithdraw = hasNodeType(rootNodes, "withdraw_request")

  const rawLength = note.length
  const activePersona = PREVIEW_PERSONAS.find(p => p.id === previewPersonaId) || PREVIEW_PERSONAS[0]
  const previewText = resolveVariables(note, activePersona)
  const worstCaseExpansion = resolveVariables(note, WORST_CASE_PERSONA)
  const worstCaseLen = worstCaseExpansion.length

  // Gauge calculations
  const gaugePercent = Math.min(100, Math.round((rawLength / 300) * 100))
  const isOverLimit = rawLength > 300
  const isWarningZone = rawLength >= 270 && rawLength <= 300
  const isExpansionRisk = rawLength <= 300 && worstCaseLen > 300

  const handleApplyStarter = (starter: typeof CONNECTION_STARTERS[0]) => {
    if (note.trim().length > 0) {
      setPendingStarter(starter)
    } else {
      onChange("note", starter.snippet)
    }
  }

  return (
    <div className="space-y-6">
      {/* Delay */}
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Delay</label>
        <DelaySelector value={data.delay} unit={data.delayUnit || "days"} onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }} />
      </div>

      {/* Withdraw toggle */}
      <div className="p-4 rounded-xl bg-background border border-border space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1">
            <p className="text-xs font-semibold text-foreground mb-0.5 flex items-center gap-1.5">
              <RotateCcw size={11} className="text-muted-foreground" /> Withdraw connection request
            </p>
            <p className="text-[10px] text-muted-foreground leading-relaxed">
              Auto-withdraw the invite if not accepted after N days. Helps keep your pending list clean and prevents LinkedIn account restrictions.
            </p>
          </div>
          <button
            disabled={hasManualWithdraw}
            onClick={() => onChange("withdraw_enabled", !data.withdraw_enabled)}
            className={`w-9 h-5 rounded-full transition-all shrink-0 ${
              data.withdraw_enabled ? "bg-indigo-600" : "bg-muted"
            } ${hasManualWithdraw ? "opacity-50 cursor-not-allowed" : ""}`}
          >
            <div className={`w-3.5 h-3.5 rounded-full bg-card mx-0.5 transition-transform ${
              data.withdraw_enabled ? "translate-x-4" : "translate-x-0"
            }`} />
          </button>
        </div>
        
        {hasManualWithdraw && (
          <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-xs text-red-500 mt-2">
            Auto-withdraw is disabled because you already have a manual Withdraw node in your sequence. Remove it first to enable auto-withdraw.
          </div>
        )}

        {data.withdraw_enabled && !hasManualWithdraw && (
          <div className="flex items-center gap-2">
            <input
              type="number"
              min={1}
              max={60}
              value={data.withdraw_days || 21}
              onChange={e => onChange("withdraw_days", Number(e.target.value))}
              className="w-16 rounded-lg bg-muted border border-border px-2 py-1.5 text-xs text-foreground text-center focus:outline-none focus:border-indigo-600"
            />
            <span className="text-xs text-muted-foreground">days after sending</span>
          </div>
        )}
      </div>

      {/* Note Section */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <label className="block text-xs font-semibold text-foreground">Connection request note</label>
            <span className="text-[10px] text-muted-foreground">Optional, but increases acceptance when concise</span>
          </div>
          <button
            type="button"
            onClick={() => setShowPreview(p => !p)}
            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-[11px] font-medium transition-all ${
              showPreview
                ? "border-primary bg-primary/10 text-primary font-bold shadow-xs"
                : "border-border bg-card hover:bg-muted text-muted-foreground"
            }`}
          >
            <Eye size={12} /> {showPreview ? "Back to Editor" : "LinkedIn Preview"}
          </button>
        </div>

        {/* 1-Click Connection Starters (Layer 0) */}
        {!showPreview && (
          <div className="p-2.5 rounded-xl bg-card border border-border/80 shadow-xs space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] uppercase font-bold tracking-wider text-muted-foreground flex items-center gap-1">
                <Sparkles size={11} className="text-indigo-500" /> High-Acceptance Starters:
              </span>
            </div>
            <div className="grid grid-cols-2 gap-1.5">
              {CONNECTION_STARTERS.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => handleApplyStarter(s)}
                  className="px-2.5 py-1.5 rounded-lg text-left border border-border/50 bg-muted/30 hover:bg-muted transition-colors flex flex-col gap-0.5 cursor-pointer"
                >
                  <div className="flex items-center justify-between gap-1">
                    <span className="text-[11px] font-semibold text-foreground truncate">{s.title}</span>
                    <span className="text-[9px] px-1 py-0.2 rounded bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 font-bold shrink-0">
                      {s.badge}
                    </span>
                  </div>
                  <span className="text-[10px] text-muted-foreground line-clamp-1">{s.desc}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Overwrite Confirmation Alert (Layer 2 Paranoia) */}
        {pendingStarter && (
          <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-xs flex flex-col gap-2">
            <div className="flex items-start gap-2">
              <AlertTriangle size={15} className="text-amber-500 shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="font-semibold text-amber-700 dark:text-amber-300">
                  Replace existing connection note?
                </p>
                <p className="text-[11px] text-amber-800/80 dark:text-amber-300/80">
                  Applying &quot;{pendingStarter.title}&quot; will overwrite your current draft.
                </p>
              </div>
            </div>
            <div className="flex items-center justify-end gap-2 pt-1">
              <button
                type="button"
                onClick={() => setPendingStarter(null)}
                className="px-2.5 py-1 text-[11px] rounded-lg border border-border bg-card text-muted-foreground hover:text-foreground"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => {
                  onChange("note", pendingStarter.snippet)
                  setPendingStarter(null)
                }}
                className="px-3 py-1 text-[11px] font-bold rounded-lg bg-amber-500 text-white hover:bg-amber-600 transition-colors"
              >
                Confirm Replace
              </button>
            </div>
          </div>
        )}

        {/* Live Preview Mode or Editor Area */}
        {showPreview ? (
          <div className="space-y-2">
            <div className="flex items-center gap-1.5 p-1 rounded-lg bg-muted/40 border border-border/50">
              <span className="text-[10px] font-semibold text-muted-foreground px-1.5">Simulate As:</span>
              {PREVIEW_PERSONAS.map(p => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => setPreviewPersonaId(p.id)}
                  className={cn(
                    "px-2 py-0.5 rounded text-[10px] font-medium transition-all",
                    previewPersonaId === p.id
                      ? "bg-primary text-primary-foreground font-bold shadow-xs"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  {p.label}
                </button>
              ))}
            </div>

            {/* LinkedIn Invite Mockup */}
            <div className="rounded-xl border border-border bg-card p-4 shadow-sm space-y-3">
              <div className="flex items-center gap-2.5 pb-2 border-b border-border/50">
                <div className="w-8 h-8 rounded-full bg-indigo-600 text-white font-bold flex items-center justify-center text-xs">
                  {activePersona.first_name ? activePersona.first_name[0] : "P"}
                </div>
                <div>
                  <p className="text-xs font-bold text-foreground">
                    {activePersona.first_name ? `${activePersona.first_name} ${activePersona.last_name}` : "Prospect"}
                  </p>
                  <p className="text-[10px] text-muted-foreground truncate">
                    {activePersona.job_title ? `${activePersona.job_title} at ${activePersona.company}` : "LinkedIn Member"}
                  </p>
                </div>
              </div>
              <div className="p-3 rounded-lg bg-muted/30 border border-border/40 text-xs text-foreground leading-relaxed whitespace-pre-wrap">
                {previewText || <span className="text-muted-foreground italic">No note written (an empty note sends a blank invite)</span>}
              </div>
              <div className="flex items-center justify-between text-[10px] text-muted-foreground pt-1">
                <span>Simulated length: <strong>{previewText.length}/300 chars</strong></span>
                <span className={previewText.length > 300 ? "text-rose-500 font-bold" : "text-emerald-600 dark:text-emerald-400 font-medium"}>
                  {previewText.length > 300 ? "Exceeds LinkedIn 300 Max" : "Within LinkedIn 300 Max"}
                </span>
              </div>
            </div>
          </div>
        ) : (
          <textarea
            maxLength={350}
            value={note}
            onChange={e => onChange("note", e.target.value)}
            rows={4}
            placeholder={`Hi {{first_name | fallback: there}}, I noticed your work at {{company | fallback: your team}} and would love to connect!`}
            className="w-full rounded-xl bg-card border border-border px-3.5 py-3 text-xs text-foreground
                       placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none leading-relaxed"
          />
        )}
        
        {!showPreview && <NakedVariableWarning text={note || ""} onFix={(fixed) => onChange("note", fixed)} />}

        {/* 300-Char Safety Radar (Layer 1 Environmental & Layer 2 Human Paranoia) */}
        <div className="p-3 rounded-xl bg-card border border-border/80 shadow-xs space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="font-semibold text-foreground flex items-center gap-1.5">
              <span>LinkedIn 300-Char Radar</span>
            </span>
            <div className="flex items-center gap-2">
              <span className="text-[11px] text-muted-foreground">
                Template: <strong className={isOverLimit ? "text-rose-500" : isWarningZone ? "text-amber-500" : "text-foreground"}>{rawLength}</strong>/300
              </span>
              <span className="text-[11px] text-muted-foreground">
                Max Est: <strong className={worstCaseLen > 300 ? "text-rose-500" : "text-foreground"}>~{worstCaseLen}</strong>/300
              </span>
            </div>
          </div>

          {/* Linear Progress Bar */}
          <div className="w-full h-2 rounded-full bg-muted overflow-hidden">
            <div
              className={cn(
                "h-full transition-all duration-300",
                isOverLimit ? "bg-rose-500" :
                isWarningZone ? "bg-orange-500" :
                rawLength >= 240 ? "bg-amber-500" :
                "bg-emerald-500"
              )}
              style={{ width: `${gaugePercent}%` }}
            />
          </div>

          {/* Physical Paranoia Warnings */}
          {isOverLimit ? (
            <div className="p-2.5 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-600 dark:text-rose-400 text-[11px] flex items-start gap-2 font-medium">
              <AlertTriangle size={14} className="shrink-0 text-rose-500 mt-0.5" />
              <div>
                <p className="font-bold">Hard Limit Exceeded by {rawLength - 300} characters!</p>
                <p className="text-[10px] text-rose-700/80 dark:text-rose-300/80">
                  LinkedIn API strictly rejects connection notes over 300 characters. Trim this note before saving.
                </p>
              </div>
            </div>
          ) : isExpansionRisk ? (
            <div className="p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-700 dark:text-amber-300 text-[11px] flex items-start gap-2 font-medium">
              <AlertTriangle size={14} className="shrink-0 text-amber-500 mt-0.5" />
              <div>
                <p className="font-bold">Expansion Risk Warning (~{worstCaseLen} chars)</p>
                <p className="text-[10px] text-amber-800/80 dark:text-amber-300/80">
                  Prospects with long company names or executive titles may push this note over 300 characters on LinkedIn. Keep template under 260 chars for 100% deliverability.
                </p>
              </div>
            </div>
          ) : (
            <p className="text-[10px] text-muted-foreground flex items-center gap-1">
              <Check size={11} className="text-emerald-500" />
              <span>Safe deliverability zone. Character length is optimal for high acceptance.</span>
            </p>
          )}
        </div>

        {/* Quick Variable Pills & Dropdown */}
        {!showPreview && (
          <div className="flex items-center gap-2 mt-2">
            <div className="relative flex-1" ref={dropdownRef}>
              <button
                type="button"
                onClick={() => setShowVars(p => !p)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border bg-card hover:bg-muted text-xs text-muted-foreground transition-all w-full justify-between"
              >
                <span className="flex items-center gap-1.5"><Sparkles size={11} className="text-primary" /> All variables</span>
                <ChevronDown size={11} className={`transition-transform ${showVars ? "rotate-180" : ""}`} />
              </button>
              <AnimatePresence>
                {showVars && (
                  <motion.div
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    className="absolute top-full left-0 right-0 mt-1 z-40 rounded-xl bg-card border border-border shadow-xl overflow-hidden"
                  >
                    {VARIABLES.map(v => (
                      <button
                        key={v.value}
                        type="button"
                        onClick={() => insertVar(v.value)}
                        className="w-full flex items-center justify-between px-3 py-2 text-xs hover:bg-muted transition-colors"
                      >
                        <span className="text-foreground whitespace-nowrap mr-2">{v.label}</span>
                        <span className="text-muted-foreground font-mono text-[10px] truncate">{v.value}</span>
                      </button>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
            {VARIABLES.slice(0, 2).map((v) => (
              <button
                key={v.label}
                type="button"
                onClick={() => insertVar(v.value)}
                className="px-2.5 py-1.5 rounded-lg text-[11px] font-medium bg-muted/40 hover:bg-muted border border-border/40 text-muted-foreground hover:text-foreground transition-colors shrink-0"
              >
                + {v.label}
              </button>
            ))}
          </div>
        )}
      </div>

      <FallbackEditor data={data} onChange={onChange} maxChars={300} fallbackLabel="Fallback connection note" />
    </div>
  )
}
function SendInMailConfig({ data, onChange, isPaid = false }: { data: any; onChange: (k: string, v: any) => void; isPaid?: boolean }) {
  const subject = data.subject || data.subject_template || "";
  const body = data.body || data.body_template || data.message || "";
  const fallbackToConn = Boolean(data.fallback_to_connection_request);

  const insertVarSubject = (v: string) => {
    onChange("subject", subject + ` {{${v}}}`);
  };
  const insertVarBody = (v: string) => {
    onChange("body", body + ` {{${v}}}`);
  };

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Pacing Delay</label>
        <DelaySelector
          value={data.delay !== undefined ? data.delay : 0}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }}
        />
      </div>

      {/* Credit & Capability Banner */}
      <div className="p-3.5 rounded-xl bg-indigo-50/80 dark:bg-indigo-950/30 border border-indigo-200 dark:border-indigo-800/40 space-y-1.5">
        <div className="flex items-center gap-2 text-xs font-semibold text-indigo-700 dark:text-indigo-300">
          <Mail size={14} />
          <span>{isPaid ? "Sponsored InMail Delivery" : "InMail Direct Dispatch"}</span>
        </div>
        <p className="text-[11px] text-indigo-600/80 dark:text-indigo-400 leading-relaxed">
          InMails bypass 1st-degree connection requirements and land straight in the lead's inbox.
          Prospects with <strong>Open Profile</strong> consume 0 InMail credits.
        </p>
      </div>

      {/* Subject Line */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-xs font-semibold text-foreground">Subject Line</label>
          <span className={cn("text-[10px]", subject.length > 200 ? "text-destructive font-bold" : "text-muted-foreground")}>
            {subject.length}/200
          </span>
        </div>
        <input
          value={subject}
          onChange={e => onChange("subject", e.target.value)}
          placeholder="e.g. Quick thought on {{company}}"
          maxLength={200}
          className="w-full rounded-lg bg-card border border-border px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
        <div className="flex flex-wrap gap-1 mt-1.5">
          {["first_name", "company", "title"].map(v => (
            <button
              key={v}
              type="button"
              onClick={() => insertVarSubject(v)}
              className="text-[10px] px-1.5 py-0.5 rounded bg-muted/60 hover:bg-muted text-muted-foreground hover:text-foreground border border-border/40 transition-colors"
            >
              + {`{{${v}}}`}
            </button>
          ))}
        </div>
        <NakedVariableWarning text={subject} />
      </div>

      {/* Message Body */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-xs font-semibold text-foreground">InMail Message Body</label>
          <span className={cn("text-[10px]", body.length > 1900 ? "text-destructive font-bold" : "text-muted-foreground")}>
            {body.length}/1900
          </span>
        </div>
        <textarea
          value={body}
          onChange={e => onChange("body", e.target.value)}
          rows={5}
          maxLength={1900}
          placeholder="Hi {{first_name}}, noticed your team at {{company}} is scaling outreach..."
          className="w-full rounded-xl bg-card border border-border px-3.5 py-3 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none"
        />
        <div className="flex flex-wrap gap-1 mt-1.5">
          {["first_name", "company", "title", "location", "ai_hook"].map(v => (
            <button
              key={v}
              type="button"
              onClick={() => insertVarBody(v)}
              className="text-[10px] px-1.5 py-0.5 rounded bg-muted/60 hover:bg-muted text-muted-foreground hover:text-foreground border border-border/40 transition-colors"
            >
              + {`{{${v}}}`}
            </button>
          ))}
        </div>
        <NakedVariableWarning text={body} />
      </div>

      {/* Layer 1 Paranoia: Credit Exhaustion Fallback */}
      <div className="p-3 rounded-xl border border-border bg-card/50 space-y-2">
        <label className="flex items-start gap-2.5 cursor-pointer">
          <input
            type="checkbox"
            checked={fallbackToConn}
            onChange={e => onChange("fallback_to_connection_request", e.target.checked)}
            className="mt-0.5 rounded border-border text-primary focus:ring-primary"
          />
          <div>
            <span className="text-xs font-semibold text-foreground block">
              Auto-Fallback to Connection Request
            </span>
            <span className="text-[11px] text-muted-foreground block leading-relaxed">
              If account runs out of InMail credits, automatically send a personalized Connection Request instead of failing this sequence step.
            </span>
          </div>
        </label>
      </div>
    </div>
  );
}

function SendEmailConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  const [showDeliverabilityModal, setShowDeliverabilityModal] = useState(false);
  const toEmail = data.to || "";
  const subject = data.subject || data.subject_template || "";
  const body = data.body || data.body_template || data.message || "";
  const includeUnsubscribe = data.include_unsubscribe !== false;
  const useSenderPool = data.use_sender_pool !== false;
  const rotationStrategy = data.rotation_strategy || "HEALTH_WEIGHTED";
  const trackingDomain = data.tracking_domain || "";

  const insertVarSubject = (v: string) => onChange("subject", subject + ` {{${v}}}`);
  const insertVarBody = (v: string) => onChange("body", body + ` {{${v}}}`);

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Pacing Delay</label>
        <DelaySelector
          value={data.delay !== undefined ? data.delay : 0}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }}
        />
      </div>

      {/* Multichannel Callout & Deliverability Studio Launch */}
      <div className="p-3.5 rounded-xl bg-pink-50/80 dark:bg-pink-950/30 border border-pink-200 dark:border-pink-800/40 space-y-2.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs font-semibold text-pink-700 dark:text-pink-300">
            <AtSign size={14} />
            <span>Cold Work Email Dispatch</span>
          </div>
          <button
            type="button"
            onClick={() => setShowDeliverabilityModal(true)}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-pink-500/15 hover:bg-pink-500/25 border border-pink-500/30 text-[11px] font-semibold text-pink-700 dark:text-pink-300 transition-colors"
          >
            <ShieldCheck size={12} />
            Deliverability Studio &rarr;
          </button>
        </div>
        <p className="text-[11px] text-pink-600/80 dark:text-pink-400 leading-relaxed">
          Dispatched via multi-inbox deliverability pool or SendGrid/SMTP. Automatically enforces bounce tripwires and SPF/DKIM/DMARC health.
        </p>
      </div>

      {/* Deliverability Pool & Custom Tracking Domain (Horizon 29) */}
      <div className="p-3.5 rounded-xl border border-border bg-card/50 space-y-3">
        <label className="flex items-center justify-between cursor-pointer">
          <div>
            <span className="text-xs font-semibold text-foreground block">
              Multi-Inbox Deliverability Pool Rotation
            </span>
            <span className="text-[11px] text-muted-foreground block">
              Rotates across healthy inboxes to protect domain reputation and prevent spam filters.
            </span>
          </div>
          <input
            type="checkbox"
            checked={useSenderPool}
            onChange={e => onChange("use_sender_pool", e.target.checked)}
            className="rounded border-border text-primary focus:ring-primary"
          />
        </label>

        {useSenderPool && (
          <div className="pt-2 border-t border-border/50 space-y-2.5">
            <div>
              <label className="block text-[11px] font-semibold text-foreground mb-1">
                Pool Rotation Strategy
              </label>
              <Select
                value={rotationStrategy}
                onValueChange={val => onChange("rotation_strategy", val)}
              >
                <SelectTrigger className="w-full bg-card border-border text-xs h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="HEALTH_WEIGHTED">Health Weighted (Dynamic Deliverability Score)</SelectItem>
                  <SelectItem value="ROUND_ROBIN">Round Robin (Equal Volume Spread)</SelectItem>
                  <SelectItem value="CAPACITY_FIRST">Capacity First (Fill Largest Headroom)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-foreground mb-1">
                Custom SSL Tracking Domain <span className="text-muted-foreground font-normal">(optional CNAME)</span>
              </label>
              <input
                value={trackingDomain}
                onChange={e => onChange("tracking_domain", e.target.value)}
                placeholder="e.g. track.yourcompany.com"
                className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
              />
              <span className="text-[10px] text-muted-foreground block mt-1">
                Rewrites email links via your whitelisted domain to avoid ESP spam flags.
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Recipient */}
      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          Recipient Email <span className="text-muted-foreground font-normal">(optional override)</span>
        </label>
        <input
          value={toEmail}
          onChange={e => onChange("to", e.target.value)}
          placeholder="Defaults to lead's verified email (e.g. {{lead.email}})"
          className="w-full rounded-lg bg-card border border-border px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
      </div>

      {/* Subject Line */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-xs font-semibold text-foreground">Email Subject</label>
          <span className="text-[10px] text-muted-foreground">{subject.length} chars</span>
        </div>
        <input
          value={subject}
          onChange={e => { onChange("subject", e.target.value); onChange("subject_template", e.target.value); }}
          placeholder="e.g. Quick question regarding {{company}}'s outbound"
          className="w-full rounded-lg bg-card border border-border px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
        <div className="flex flex-wrap gap-1 mt-1.5">
          {["first_name", "company", "title"].map(v => (
            <button
              key={v}
              type="button"
              onClick={() => insertVarSubject(v)}
              className="text-[10px] px-1.5 py-0.5 rounded bg-muted/60 hover:bg-muted text-muted-foreground hover:text-foreground border border-border/40 transition-colors"
            >
              + {`{{${v}}}`}
            </button>
          ))}
        </div>
        <NakedVariableWarning text={subject} />
      </div>

      {/* Email Body */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-xs font-semibold text-foreground">Email Body</label>
          <span className="text-[10px] text-muted-foreground">{body.length} chars</span>
        </div>
        <textarea
          value={body}
          onChange={e => { onChange("body", e.target.value); onChange("body_template", e.target.value); }}
          rows={6}
          placeholder="Hi {{first_name}},&#10;&#10;Loved your latest update regarding {{company}}. Wondering if you're exploring..."
          className="w-full rounded-xl bg-card border border-border px-3.5 py-3 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none"
        />
        <div className="flex flex-wrap gap-1 mt-1.5">
          {["first_name", "company", "title", "ai_hook"].map(v => (
            <button
              key={v}
              type="button"
              onClick={() => insertVarBody(v)}
              className="text-[10px] px-1.5 py-0.5 rounded bg-muted/60 hover:bg-muted text-muted-foreground hover:text-foreground border border-border/40 transition-colors"
            >
              + {`{{${v}}}`}
            </button>
          ))}
        </div>
        <NakedVariableWarning text={body} />
      </div>

      {/* Layer 2 Paranoia: Unsubscribe Compliance */}
      <div className="p-3 rounded-xl border border-border bg-card/50">
        <label className="flex items-center gap-2.5 cursor-pointer">
          <input
            type="checkbox"
            checked={includeUnsubscribe}
            onChange={e => onChange("include_unsubscribe", e.target.checked)}
            className="rounded border-border text-primary focus:ring-primary"
          />
          <div>
            <span className="text-xs font-semibold text-foreground block">
              Include One-Click Unsubscribe Link
            </span>
            <span className="text-[11px] text-muted-foreground block">
              CAN-SPAM & GDPR compliant opt-out footer.
            </span>
          </div>
        </label>
      </div>

      <DeliverabilityStudioModal
        isOpen={showDeliverabilityModal}
        onClose={() => setShowDeliverabilityModal(false)}
      />
    </div>
  );
}

function SimpleDelayConfig({ data, onChange, label }: { data: any; onChange: (k: string, v: any) => void; label: string }) {
  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Delay</label>
        <DelaySelector value={data.delay} unit={data.delayUnit || "days"} onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }} />
      </div>
      <div className="p-4 rounded-xl bg-background border border-border">
        <p className="text-xs text-muted-foreground leading-relaxed">
          {HR_NODE_DEFS[data.type as keyof typeof HR_NODE_DEFS]?.description || label}
        </p>
      </div>
      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">Step name <span className="text-muted-foreground font-normal">(optional)</span></label>
        <input
          value={data.step_name || ""}
          onChange={e => onChange("step_name", e.target.value)}
          placeholder="Name your step"
          className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
      </div>
    </div>
  )
}

function ViewProfileConfig({ data, onChange, isRepeat = false }: { data: any; onChange: (k: string, v: any) => void; isRepeat?: boolean }) {
  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Pacing Delay</label>
        <DelaySelector
          value={data.delay !== undefined ? data.delay : (isRepeat ? 3 : 1)}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }}
        />
      </div>

      <div className="p-4 rounded-xl bg-background border border-border space-y-3">
        <div className="flex items-center gap-2">
          <Eye size={16} className="text-blue-500 shrink-0" />
          <h4 className="text-xs font-semibold text-foreground">
            {isRepeat ? "Re-visit Prospect Profile" : "Soft Warmup Visit"}
          </h4>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          {isRepeat
            ? "Visits the lead's profile a second time to trigger another high-visibility notification before follow-up outreach."
            : "Visits the prospect's profile to generate a 'viewed your profile' notification. Prospects who notice your profile view convert at a 42% higher connection rate."}
        </p>
        <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-[11px] text-emerald-700 dark:text-emerald-300 flex items-center gap-2">
          <Check size={13} className="shrink-0 text-emerald-500" />
          <span>Recommended next step: Wait 1–2 days, then send Connection Request.</span>
        </div>
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          Step name <span className="text-muted-foreground font-normal">(optional)</span>
        </label>
        <input
          value={data.step_name || ""}
          onChange={e => onChange("step_name", e.target.value)}
          placeholder={isRepeat ? "e.g. Re-visit before follow-up" : "e.g. Initial profile visit"}
          className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
      </div>
    </div>
  );
}

function FollowProfileConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Pacing Delay</label>
        <DelaySelector
          value={data.delay !== undefined ? data.delay : 1}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }}
        />
      </div>

      <div className="p-4 rounded-xl bg-background border border-border space-y-3">
        <div className="flex items-center gap-2">
          <UserPlus size={16} className="text-blue-500 shrink-0" />
          <h4 className="text-xs font-semibold text-foreground">Follow Lead's Public Profile</h4>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Follows the prospect's personal profile without sending a connection request. Triggers a high-visibility notification and displays your future posts in their feed.
        </p>
        <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-[11px] text-emerald-700 dark:text-emerald-300 flex items-center gap-2">
          <Check size={13} className="shrink-0 text-emerald-500" />
          <span>Layer 1 Resilience: If already following or already connected, the step marks complete and proceeds immediately.</span>
        </div>
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          Step name <span className="text-muted-foreground font-normal">(optional)</span>
        </label>
        <input
          value={data.step_name || ""}
          onChange={e => onChange("step_name", e.target.value)}
          placeholder="e.g. Soft-touch follow before connecting"
          className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
      </div>
    </div>
  );
}

function LikePostConfig({ data, onChange, defaultMaxPosts = 1 }: { data: any; onChange: (k: string, v: any) => void; defaultMaxPosts?: number }) {
  const reactionType = data.reaction_type || "like";
  const maxPosts = data.max_posts ?? defaultMaxPosts;
  const filterLowLikes = data.filter_low_likes ?? true;

  const REACTIONS = [
    { id: "like", label: "Like", icon: ThumbsUp },
    { id: "insightful", label: "Insightful", icon: Sparkles },
    { id: "celebrate", label: "Celebrate", icon: Award },
    { id: "support", label: "Support", icon: Heart },
    { id: "funny", label: "Funny", icon: Smile },
  ];

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Pacing Delay</label>
        <DelaySelector
          value={data.delay !== undefined ? data.delay : 1}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }}
        />
      </div>

      {/* Reaction Type Selector */}
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Reaction Type</label>
        <div className="grid grid-cols-5 gap-1.5">
          {REACTIONS.map(r => {
            const isSelected = reactionType.toLowerCase() === r.id;
            const Icon = r.icon;
            return (
              <button
                key={r.id}
                type="button"
                onClick={() => onChange("reaction_type", r.id)}
                className={cn(
                  "flex flex-col items-center justify-center py-2.5 px-1 rounded-xl border text-xs transition-all",
                  isSelected
                    ? "bg-primary/10 border-primary text-foreground font-semibold shadow-xs"
                    : "bg-card border-border hover:bg-muted/50 text-muted-foreground"
                )}
              >
                <Icon size={16} className={cn("mb-1", isSelected ? "text-primary" : "text-muted-foreground")} />
                <span className="text-[10px] truncate max-w-full">{r.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Number of Posts */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="block text-xs font-semibold text-foreground">Posts to Engage</label>
          <span className="text-[11px] font-medium text-foreground">{maxPosts} {maxPosts === 1 ? "post" : "posts"}</span>
        </div>
        <div className="flex items-center gap-2">
          {[1, 2, 3].map(count => (
            <button
              key={count}
              type="button"
              onClick={() => onChange("max_posts", count)}
              className={cn(
                "flex-1 py-1.5 rounded-lg border text-xs font-medium transition-colors",
                maxPosts === count
                  ? "bg-primary/10 border-primary text-primary"
                  : "bg-card border-border hover:bg-muted text-muted-foreground"
              )}
            >
              {count} {count === 1 ? "Recent Post" : "Recent Posts"}
            </button>
          ))}
        </div>
      </div>

      {/* Smart Noise Filter Toggle */}
      <div className="p-3.5 rounded-xl bg-card border border-border flex items-start justify-between gap-3">
        <div className="space-y-0.5">
          <span className="text-xs font-semibold text-foreground block">Smart Visibility Filter</span>
          <p className="text-[11px] text-muted-foreground leading-relaxed">
            Prioritize posts with under 50 reactions so your notification stands out rather than getting lost in viral noise.
          </p>
        </div>
        <input
          type="checkbox"
          checked={filterLowLikes}
          onChange={e => onChange("filter_low_likes", e.target.checked)}
          className="mt-0.5 h-4 w-4 rounded border-border text-primary focus:ring-primary"
        />
      </div>

      {/* Three-Layer Environmental Fallback Advisory */}
      <div className="p-3.5 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-start gap-2.5 text-xs text-blue-900 dark:text-blue-200">
        <ShieldCheck size={16} className="text-blue-500 shrink-0 mt-0.5" />
        <div className="space-y-1">
          <span className="font-semibold block text-[11px]">Layer 1 Environmental Fallback Active</span>
          <p className="text-[11px] leading-relaxed text-blue-800/80 dark:text-blue-300/80">
            If the prospect has no public posts on LinkedIn, the sequence automatically substitutes with a <strong>Profile View</strong> so your campaign never halts.
          </p>
        </div>
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          Step name <span className="text-muted-foreground font-normal">(optional)</span>
        </label>
        <input
          value={data.step_name || ""}
          onChange={e => onChange("step_name", e.target.value)}
          placeholder="e.g. React to recent post"
          className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
      </div>
    </div>
  );
}

function CommentOnPostConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  const commentMode = data.comment_mode || "Fixed comment";
  const commentText = data.comment || "";
  const fallbackComment = data.fallback_comment || "Great perspective, thanks for sharing this!";
  const aiTone = data.ai_tone || "Insightful Industry Perspective";

  const insertVar = (v: string) => {
    onChange("comment", commentText + ` {{${v}}}`);
  };

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Pacing Delay</label>
        <DelaySelector
          value={data.delay !== undefined ? data.delay : 1}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }}
        />
      </div>

      {/* Mode Selection */}
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Comment Generation Mode</label>
        <div className="grid grid-cols-2 gap-2">
          {["Fixed comment", "AI-generated comment"].map(mode => (
            <button
              key={mode}
              type="button"
              onClick={() => onChange("comment_mode", mode)}
              className={cn(
                "py-2 px-3 rounded-xl border text-xs font-medium transition-all text-center",
                commentMode === mode
                  ? "bg-primary/10 border-primary text-primary font-semibold shadow-xs"
                  : "bg-card border-border hover:bg-muted text-muted-foreground"
              )}
            >
              {mode}
            </button>
          ))}
        </div>
      </div>

      {commentMode === "Fixed comment" ? (
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="block text-xs font-semibold text-foreground">Comment Template</label>
            <span className="text-[10px] text-muted-foreground">{commentText.length}/1000</span>
          </div>
          <textarea
            rows={4}
            maxLength={1000}
            value={commentText}
            onChange={e => onChange("comment", e.target.value)}
            placeholder="e.g. Great perspective on this {{first_name}}! Loved your take on {{company}}'s recent developments."
            className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none leading-relaxed"
          />
          <div className="flex items-center justify-between mt-1 text-[10px] text-muted-foreground">
            <span>Insert variable:</span>
            <div className="flex items-center gap-1 flex-wrap justify-end">
              {["first_name", "company", "title", "industry"].map(varKey => (
                <button
                  key={varKey}
                  type="button"
                  onClick={() => insertVar(varKey)}
                  className="text-[10px] px-1.5 py-0.5 rounded bg-muted hover:bg-muted/80 text-foreground transition-colors cursor-pointer"
                >
                  + {`{{${varKey}}}`}
                </button>
              ))}
            </div>
          </div>
          <NakedVariableWarning text={commentText} onFix={fixed => onChange("comment", fixed)} />
        </div>
      ) : (
        <div className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-foreground mb-1.5 flex items-center gap-1.5">
              <ElesiumLogo size={13} />
              <span>AI Perspective & Tone</span>
            </label>
            <Select
              value={aiTone}
              onValueChange={val => onChange("ai_tone", val)}
            >
              <SelectTrigger className="w-full bg-card border-border text-xs h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="Insightful Industry Perspective">Insightful Industry Perspective (Constructive & analytical)</SelectItem>
                <SelectItem value="Thoughtful Question">Thoughtful Question (Engages prospect in conversation)</SelectItem>
                <SelectItem value="Congratulatory & Supportive">Congratulatory & Supportive (Warm & encouraging)</SelectItem>
                <SelectItem value="Agree & Add Value">Agree & Add Value (Validates thesis and adds quick data point)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <label className="block text-xs font-semibold text-foreground mb-1.5">
              Custom AI Prompt Guidance <span className="text-muted-foreground font-normal">(optional)</span>
            </label>
            <input
              value={data.ai_guidance || ""}
              onChange={e => onChange("ai_guidance", e.target.value)}
              placeholder="e.g. Keep under 2 sentences, mention AI scalability, avoid generic praise"
              className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
            />
          </div>
        </div>
      )}

      {/* Fallback Comment (Layer 2 Paranoia) */}
      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          Safety Fallback Comment <span className="text-muted-foreground font-normal">(Paranoia Guard)</span>
        </label>
        <input
          value={fallbackComment}
          onChange={e => onChange("fallback_comment", e.target.value)}
          placeholder="e.g. Great perspective, thanks for sharing this!"
          className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 text-[11px]"
        />
        <p className="text-[10px] text-muted-foreground mt-1">
          Used if post scrape contains no text or AI generation times out.
        </p>
      </div>

      {/* Layer 1 Environmental Notice */}
      <div className="p-3.5 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-start gap-2.5 text-xs text-blue-900 dark:text-blue-200">
        <ShieldCheck size={16} className="text-blue-500 shrink-0 mt-0.5" />
        <div className="space-y-1">
          <span className="font-semibold block text-[11px]">Layer 1 Environmental Fallback Active</span>
          <p className="text-[11px] leading-relaxed text-blue-800/80 dark:text-blue-300/80">
            If commenting is restricted on the prospect's post or they have no posts, sequence safely falls back to a <strong>Profile View</strong>.
          </p>
        </div>
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          Step name <span className="text-muted-foreground font-normal">(optional)</span>
        </label>
        <input
          value={data.step_name || ""}
          onChange={e => onChange("step_name", e.target.value)}
          placeholder="e.g. Comment on top post"
          className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
      </div>
    </div>
  );
}

function EndorseSkillConfig({ data, onChange, defaultMaxSkills = 1 }: { data: any; onChange: (k: string, v: any) => void; defaultMaxSkills?: number }) {
  const maxSkills = data.max_skills ?? defaultMaxSkills;

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Pacing Delay</label>
        <DelaySelector
          value={data.delay !== undefined ? data.delay : 0}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }}
        />
      </div>

      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="block text-xs font-semibold text-foreground">Skills to Endorse</label>
          <span className="text-[11px] font-medium text-foreground">{maxSkills} {maxSkills === 1 ? "skill" : "skills"}</span>
        </div>
        <div className="flex items-center gap-2">
          {[1, 2, 3].map(count => (
            <button
              key={count}
              type="button"
              onClick={() => onChange("max_skills", count)}
              className={cn(
                "flex-1 py-1.5 rounded-lg border text-xs font-medium transition-colors",
                maxSkills === count
                  ? "bg-primary/10 border-primary text-primary"
                  : "bg-card border-border hover:bg-muted text-muted-foreground"
              )}
            >
              {count} {count === 1 ? "Top Skill" : "Top Skills"}
            </button>
          ))}
        </div>
      </div>

      {/* Layer 2 Paranoia Callout for 1st-degree requirements */}
      <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-start gap-2.5 text-xs text-amber-900 dark:text-amber-200">
        <AlertTriangle size={16} className="text-amber-500 shrink-0 mt-0.5" />
        <div className="space-y-1">
          <span className="font-semibold block text-[11px]">Prerequisite: 1st-Degree Connection</span>
          <p className="text-[11px] leading-relaxed text-amber-800/80 dark:text-amber-300/80">
            LinkedIn only renders skill endorsement buttons for 1st-degree connections. If the lead is not connected or has no skills listed, the system automatically substitutes with a <strong>Profile View</strong>.
          </p>
        </div>
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          Step name <span className="text-muted-foreground font-normal">(optional)</span>
        </label>
        <input
          value={data.step_name || ""}
          onChange={e => onChange("step_name", e.target.value)}
          placeholder="e.g. Endorse top skill"
          className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
      </div>
    </div>
  );
}

function FollowCompanyConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Pacing Delay</label>
        <DelaySelector
          value={data.delay !== undefined ? data.delay : 0}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }}
        />
      </div>

      <div className="p-4 rounded-xl bg-background border border-border space-y-3">
        <div className="flex items-center gap-2">
          <Building2 size={16} className="text-blue-500 shrink-0" />
          <h4 className="text-xs font-semibold text-foreground">Follow Prospect Company Page</h4>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Follows the prospect's company page on LinkedIn to signal deep account research and build familiarity before reaching out to decision makers.
        </p>
        <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-[11px] text-emerald-700 dark:text-emerald-300 flex items-center gap-2">
          <Check size={13} className="shrink-0 text-emerald-500" />
          <span>Layer 1 Resilience: If company page is already followed or unlisted, sequence safely continues.</span>
        </div>
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          Step name <span className="text-muted-foreground font-normal">(optional)</span>
        </label>
        <input
          value={data.step_name || ""}
          onChange={e => onChange("step_name", e.target.value)}
          placeholder="e.g. Follow prospect company"
          className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
      </div>
    </div>
  );
}

function SharePostConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  const shareComment = data.share_comment || "";

  const insertVar = (v: string) => {
    onChange("share_comment", shareComment + ` {{${v}}}`);
  };

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Pacing Delay</label>
        <DelaySelector
          value={data.delay !== undefined ? data.delay : 1}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }}
        />
      </div>

      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="block text-xs font-semibold text-foreground">
            Repost Commentary <span className="text-muted-foreground font-normal">(optional)</span>
          </label>
          <span className="text-[10px] text-muted-foreground">{shareComment.length}/700</span>
        </div>
        <textarea
          rows={3}
          maxLength={700}
          value={shareComment}
          onChange={e => onChange("share_comment", e.target.value)}
          placeholder="e.g. Great perspective shared by {{first_name}} at {{company}}!"
          className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none leading-relaxed"
        />
        <div className="flex items-center justify-between mt-1 text-[10px] text-muted-foreground">
          <span>Insert variable:</span>
          <div className="flex items-center gap-1 flex-wrap justify-end">
            {["first_name", "company", "title"].map(varKey => (
              <button
                key={varKey}
                type="button"
                onClick={() => insertVar(varKey)}
                className="text-[10px] px-1.5 py-0.5 rounded bg-muted hover:bg-muted/80 text-foreground transition-colors cursor-pointer"
              >
                + {`{{${varKey}}}`}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="p-3.5 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-start gap-2.5 text-xs text-blue-900 dark:text-blue-200">
        <ShieldCheck size={16} className="text-blue-500 shrink-0 mt-0.5" />
        <div className="space-y-1">
          <span className="font-semibold block text-[11px]">Layer 1 Environmental Fallback Active</span>
          <p className="text-[11px] leading-relaxed text-blue-800/80 dark:text-blue-300/80">
            If the prospect has no public posts to share, sequence automatically substitutes with a <strong>Profile View</strong>.
          </p>
        </div>
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          Step name <span className="text-muted-foreground font-normal">(optional)</span>
        </label>
        <input
          value={data.step_name || ""}
          onChange={e => onChange("step_name", e.target.value)}
          placeholder="e.g. Repost prospect content"
          className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
      </div>
    </div>
  );
}

function InviteToEventConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  const eventUrl = data.event_url || "";
  const inviteNote = data.invite_note || "";
  const [urlError, setUrlError] = useState("");

  const handleUrlBlur = (val: string) => {
    if (val && !val.startsWith("http")) {
      setUrlError("Please enter a valid URL beginning with https://");
    } else {
      setUrlError("");
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Pacing Delay</label>
        <DelaySelector
          value={data.delay !== undefined ? data.delay : 0}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }}
        />
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">LinkedIn Event URL</label>
        <input
          value={eventUrl}
          onChange={e => {
            onChange("event_url", e.target.value);
            if (urlError) setUrlError("");
          }}
          onBlur={e => handleUrlBlur(e.target.value)}
          placeholder="https://www.linkedin.com/events/your-event-id/"
          className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 font-mono text-[11px]"
        />
        {urlError && <p className="text-rose-600 dark:text-rose-400 text-[10px] mt-1 font-medium">{urlError}</p>}
      </div>

      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="block text-xs font-semibold text-foreground">
            Accompanying Note <span className="text-muted-foreground font-normal">(optional)</span>
          </label>
          <span className="text-[10px] text-muted-foreground">{inviteNote.length}/300</span>
        </div>
        <textarea
          rows={3}
          maxLength={300}
          value={inviteNote}
          onChange={e => onChange("invite_note", e.target.value)}
          placeholder="e.g. Hey {{first_name}}, hosting an executive roundtable on enterprise AI pipelines. Would love to have you join!"
          className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none leading-relaxed"
        />
      </div>

      <div className="p-3.5 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-start gap-2.5 text-xs text-blue-900 dark:text-blue-200">
        <ShieldCheck size={16} className="text-blue-500 shrink-0 mt-0.5" />
        <div className="space-y-1">
          <span className="font-semibold block text-[11px]">Layer 1 Environmental Fallback Active</span>
          <p className="text-[11px] leading-relaxed text-blue-800/80 dark:text-blue-300/80">
            If the event link is closed or unavailable, the system safely falls back to a <strong>Profile View</strong> so the lead is never stranded.
          </p>
        </div>
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          Step name <span className="text-muted-foreground font-normal">(optional)</span>
        </label>
        <input
          value={data.step_name || ""}
          onChange={e => onChange("step_name", e.target.value)}
          placeholder="e.g. Invite to LinkedIn event"
          className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
      </div>
    </div>
  );
}

function WithdrawRequestConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Wait Before Withdrawing</label>
        <DelaySelector
          value={data.delay !== undefined ? data.delay : 14}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }}
        />
      </div>

      <div className="p-4 rounded-xl bg-background border border-border space-y-3">
        <div className="flex items-center gap-2">
          <RotateCcw size={16} className="text-zinc-500 shrink-0" />
          <h4 className="text-xs font-semibold text-foreground">Auto-Withdraw Pending Invitation</h4>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Cancels the pending connection request if the prospect hasn't accepted within the listening window. Keeps your account's pending invitation queue clean to protect sender health.
        </p>
        <div className="p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-[11px] text-amber-800 dark:text-amber-200 flex items-start gap-2">
          <AlertTriangle size={14} className="shrink-0 text-amber-500 mt-0.5" />
          <span>LinkedIn Cooling Period: Once withdrawn, LinkedIn prevents sending another invite to this prospect for 3 weeks.</span>
        </div>
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          Step name <span className="text-muted-foreground font-normal">(optional)</span>
        </label>
        <input
          value={data.step_name || ""}
          onChange={e => onChange("step_name", e.target.value)}
          placeholder="e.g. Withdraw after 14 days"
          className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
      </div>
    </div>
  );
}

function RemoveConnectionConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Pacing Delay</label>
        <DelaySelector
          value={data.delay !== undefined ? data.delay : 0}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }}
        />
      </div>

      <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 space-y-3 text-rose-900 dark:text-rose-200">
        <div className="flex items-center gap-2">
          <UserMinus size={16} className="text-rose-500 shrink-0" />
          <h4 className="text-xs font-bold">Destructive Action: Remove Connection</h4>
        </div>
        <p className="text-xs leading-relaxed text-rose-800/90 dark:text-rose-300/90">
          Permanently removes this lead from your 1st-degree LinkedIn connections. Used for pipeline hygiene when leads explicitly request removal or churn.
        </p>
        <div className="p-2.5 rounded-lg bg-rose-500/20 text-[11px] font-medium flex items-center gap-2">
          <ShieldCheck size={14} className="shrink-0 text-rose-500" />
          <span>Layer 1 Resilience: If lead was already not connected, sequence safely continues without stalling.</span>
        </div>
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          Step name <span className="text-muted-foreground font-normal">(optional)</span>
        </label>
        <input
          value={data.step_name || ""}
          onChange={e => onChange("step_name", e.target.value)}
          placeholder="e.g. Remove non-responsive connection"
          className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
      </div>
    </div>
  );
}

function ABSplitConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Pacing Delay</label>
        <DelaySelector
          value={data.delay !== undefined ? data.delay : 0}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }}
        />
      </div>

      <div className="p-4 rounded-xl bg-background border border-border space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Split size={16} className="text-indigo-500" />
            <h4 className="text-xs font-semibold text-foreground">A/B Traffic Split</h4>
          </div>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-500 font-bold">50% / 50%</span>
        </div>

        {/* Visual Split Bar */}
        <div className="space-y-1.5">
          <div className="h-3 w-full rounded-full overflow-hidden flex bg-muted">
            <div className="h-full bg-indigo-500 w-1/2 flex items-center justify-center text-[9px] text-white font-bold">Path A (50%)</div>
            <div className="h-full bg-cyan-500 w-1/2 flex items-center justify-center text-[9px] text-zinc-950 font-bold">Path B (50%)</div>
          </div>
          <div className="flex justify-between text-[11px] text-muted-foreground">
            <span>Branch: Path A</span>
            <span>Branch: Path B</span>
          </div>
        </div>

        <div className="p-2.5 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-[11px] text-indigo-900 dark:text-indigo-200 leading-relaxed">
          <strong className="font-semibold">Deterministic Hashing:</strong> Each lead is pseudo-randomly hashed by ID so they stay on their assigned track even across campaign pauses and resumes.
        </div>
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          Step name <span className="text-muted-foreground font-normal">(optional)</span>
        </label>
        <input
          value={data.step_name || ""}
          onChange={e => onChange("step_name", e.target.value)}
          placeholder="e.g. 50/50 Message Variant Split"
          className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
      </div>
    </div>
  );
}

function WeightedSplitConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  const pathAPct = Math.max(0, Math.min(100, data.path_a_pct ?? 50));
  const pathBPct = 100 - pathAPct;

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Pacing Delay</label>
        <DelaySelector
          value={data.delay !== undefined ? data.delay : 0}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }}
        />
      </div>

      <div className="p-4 rounded-xl bg-background border border-border space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <GitFork size={16} className="text-indigo-500" />
            <h4 className="text-xs font-semibold text-foreground">Custom Weighted Split</h4>
          </div>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-primary/10 text-primary font-bold">
            {pathAPct}% / {pathBPct}%
          </span>
        </div>

        {/* Visual Split Bar */}
        <div className="space-y-1.5">
          <div className="h-3 w-full rounded-full overflow-hidden flex bg-muted">
            <div
              style={{ width: `${pathAPct}%` }}
              className="h-full bg-indigo-500 transition-all duration-300 flex items-center justify-center text-[9px] text-white font-bold"
            >
              {pathAPct >= 15 && `A (${pathAPct}%)`}
            </div>
            <div
              style={{ width: `${pathBPct}%` }}
              className="h-full bg-cyan-500 transition-all duration-300 flex items-center justify-center text-[9px] text-zinc-950 font-bold"
            >
              {pathBPct >= 15 && `B (${pathBPct}%)`}
            </div>
          </div>
          <div className="flex justify-between text-[11px] text-muted-foreground font-mono">
            <span>Path A: {pathAPct}%</span>
            <span>Path B: {pathBPct}%</span>
          </div>
        </div>

        {/* Slider */}
        <div className="space-y-1.5">
          <label className="block text-xs font-semibold text-foreground">Path A Allocation: {pathAPct}%</label>
          <input
            type="range"
            min="0"
            max="100"
            value={pathAPct}
            onChange={e => onChange("path_a_pct", Number(e.target.value))}
            className="w-full accent-indigo-500 cursor-pointer"
          />
        </div>

        {/* Quick Presets */}
        <div className="flex items-center gap-1.5">
          {[
            { label: "50 / 50", val: 50 },
            { label: "70 / 30", val: 70 },
            { label: "80 / 20", val: 80 },
            { label: "90 / 10", val: 90 },
          ].map(preset => (
            <button
              key={preset.label}
              type="button"
              onClick={() => onChange("path_a_pct", preset.val)}
              className={cn(
                "flex-1 py-1 rounded-lg border text-[11px] font-medium transition-colors",
                pathAPct === preset.val
                  ? "bg-primary/10 border-primary text-primary"
                  : "bg-card border-border hover:bg-muted text-muted-foreground"
              )}
            >
              {preset.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          Step name <span className="text-muted-foreground font-normal">(optional)</span>
        </label>
        <input
          value={data.step_name || ""}
          onChange={e => onChange("step_name", e.target.value)}
          placeholder="e.g. 80/20 Canary Message Test"
          className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
      </div>
    </div>
  );
}

function DailyLimitCheckConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  const actionType = data.action_type || "All actions";

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Pacing Delay</label>
        <DelaySelector
          value={data.delay !== undefined ? data.delay : 0}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }}
        />
      </div>

      <div className="p-4 rounded-xl bg-background border border-border space-y-4">
        <div className="flex items-center gap-2">
          <Gauge size={16} className="text-emerald-500" />
          <h4 className="text-xs font-semibold text-foreground">Anti-Ban Daily Safety Threshold</h4>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Queries current sender account utilization. If quota is reached, lead is held until the next sending window rather than triggering LinkedIn account restrictions.
        </p>

        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">Action Quota to Audit</label>
          <Select
            value={actionType}
            onValueChange={val => onChange("action_type", val)}
          >
            <SelectTrigger className="w-full bg-card border-border text-xs h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="All actions">All actions (Warmup & sending caps)</SelectItem>
              <SelectItem value="Connection requests">Connection requests (Weekly/daily quota)</SelectItem>
              <SelectItem value="Messages">Direct messages</SelectItem>
              <SelectItem value="Profile views">Profile views</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-700 dark:text-emerald-300">
            <span className="font-bold block text-[11px]">Under limit</span>
            <span className="text-[10px] text-muted-foreground">Executes outreach immediately</span>
          </div>
          <div className="p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-700 dark:text-amber-300">
            <span className="font-bold block text-[11px]">Limit reached</span>
            <span className="text-[10px] text-muted-foreground">Pauses until next window</span>
          </div>
        </div>
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          Step name <span className="text-muted-foreground font-normal">(optional)</span>
        </label>
        <input
          value={data.step_name || ""}
          onChange={e => onChange("step_name", e.target.value)}
          placeholder="e.g. Daily connection cap audit"
          className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
      </div>
    </div>
  );
}

function BlacklistCheckConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Pacing Delay</label>
        <DelaySelector
          value={data.delay !== undefined ? data.delay : 0}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }}
        />
      </div>

      <div className="p-4 rounded-xl bg-background border border-border space-y-4">
        <div className="flex items-center gap-2">
          <Ban size={16} className="text-rose-500" />
          <h4 className="text-xs font-semibold text-foreground">Workspace Suppression Audit</h4>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Verifies prospect's LinkedIn URL and email against workspace suppression lists, unsubscribed companies, and manual exclusions before outreach.
        </p>

        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-700 dark:text-emerald-300">
            <span className="font-bold block text-[11px]">Not blacklisted</span>
            <span className="text-[10px] text-muted-foreground">Safe to continue sequence</span>
          </div>
          <div className="p-2.5 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-700 dark:text-rose-300">
            <span className="font-bold block text-[11px]">Blacklisted (skip)</span>
            <span className="text-[10px] text-muted-foreground">Exits sequence silently</span>
          </div>
        </div>
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          Step name <span className="text-muted-foreground font-normal">(optional)</span>
        </label>
        <input
          value={data.step_name || ""}
          onChange={e => onChange("step_name", e.target.value)}
          placeholder="e.g. Verify not on suppression list"
          className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
      </div>
    </div>
  );
}

function AddTagConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  const tag = data.tag || "";
  const SUGGESTIONS = ["warm_lead", "vip_target", "high_intent", "meeting_booked", "unresponsive", "follow_up_q2"];

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Pacing Delay</label>
        <DelaySelector
          value={data.delay !== undefined ? data.delay : 0}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }}
        />
      </div>

      <div className="p-4 rounded-xl bg-background border border-border space-y-3">
        <div className="flex items-center gap-2">
          <Tag size={16} className="text-indigo-500" />
          <h4 className="text-xs font-semibold text-foreground">Attach Pipeline Label / Tag</h4>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Attaches a persistent metadata label to the lead's profile in your workspace CRM for retargeting, segmenting, and reporting.
        </p>

        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">Tag Name</label>
          <input
            value={tag}
            onChange={e => onChange("tag", e.target.value)}
            placeholder="e.g. warm_lead"
            className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 font-mono text-[11px]"
          />
        </div>

        <div>
          <span className="text-[10px] text-muted-foreground block mb-1.5 font-medium">Quick suggestions:</span>
          <div className="flex items-center gap-1.5 flex-wrap">
            {SUGGESTIONS.map(s => (
              <button
                key={s}
                type="button"
                onClick={() => onChange("tag", s)}
                className="text-[10px] px-2 py-0.5 rounded-full bg-muted hover:bg-muted/80 text-foreground transition-colors cursor-pointer font-mono"
              >
                +{s}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          Step name <span className="text-muted-foreground font-normal">(optional)</span>
        </label>
        <input
          value={data.step_name || ""}
          onChange={e => onChange("step_name", e.target.value)}
          placeholder="e.g. Tag as high intent"
          className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
      </div>
    </div>
  );
}

function SequenceEndConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  const exitReason = data.exit_reason || "Completed sequence";

  const REASONS = [
    { id: "Meeting Booked", label: "Meeting Booked" },
    { id: "Unresponsive", label: "Unresponsive / Cold Exit" },
    { id: "Not Interested", label: "Not Interested / Bad Fit" },
    { id: "Re-enroll Later", label: "Re-enroll Later" },
  ];

  return (
    <div className="space-y-6">
      <div className="p-4 rounded-xl bg-background border border-border space-y-4">
        <div className="flex items-center gap-2">
          <Flag size={16} className="text-zinc-500" />
          <h4 className="text-xs font-semibold text-foreground">Sequence Termination Node</h4>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Concludes the outreach journey for this branch. Attributing a clear exit reason ensures your campaign funnel metrics and conversion dashboards are accurate.
        </p>

        <div>
          <label className="block text-xs font-semibold text-foreground mb-2">Exit Attribution Reason</label>
          <div className="grid grid-cols-2 gap-2">
            {REASONS.map(r => (
              <button
                key={r.id}
                type="button"
                onClick={() => onChange("exit_reason", r.id)}
                className={cn(
                  "py-2 px-3 rounded-xl border text-xs font-medium transition-all text-left truncate",
                  exitReason === r.id
                    ? "bg-primary/10 border-primary text-primary font-semibold shadow-xs"
                    : "bg-card border-border hover:bg-muted text-muted-foreground"
                )}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">
            Custom Exit Reason <span className="text-muted-foreground font-normal">(optional)</span>
          </label>
          <input
            value={exitReason}
            onChange={e => onChange("exit_reason", e.target.value)}
            placeholder="e.g. Disqualified due to company size"
            className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
          />
        </div>
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          Step name <span className="text-muted-foreground font-normal">(optional)</span>
        </label>
        <input
          value={data.step_name || ""}
          onChange={e => onChange("step_name", e.target.value)}
          placeholder="e.g. End of Cold Outreach Track"
          className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
      </div>
    </div>
  );
}

function WaitForReplyConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  const waitDays = data.wait_days !== undefined ? data.wait_days : 3;

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Pacing Delay Before Listening</label>
        <DelaySelector
          value={data.delay !== undefined ? data.delay : 0}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => {
            onChange("delay", v);
            onChange("delayUnit", u);
          }}
        />
      </div>

      <div className="p-4 rounded-xl bg-background border border-border space-y-4">
        <div className="flex items-center gap-2">
          <Clock size={16} className="text-indigo-500" />
          <h4 className="text-xs font-semibold text-foreground">Inbound Reply Listener</h4>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Monitors the prospect's LinkedIn thread. If a response arrives, the engine routes to <strong>Replied</strong> immediately. If the duration elapses with no reply, it advances to <strong>Timeout</strong>.
        </p>

        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="block text-xs font-semibold text-foreground">Maximum Wait Window</label>
            <span className="text-xs font-mono font-bold text-primary">{waitDays} {waitDays === 1 ? "day" : "days"}</span>
          </div>
          <input
            type="range"
            min={1}
            max={14}
            step={1}
            value={waitDays}
            onChange={e => onChange("wait_days", Number(e.target.value))}
            className="w-full h-1.5 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
          />
          <div className="flex justify-between text-[10px] text-muted-foreground mt-1">
            <span>1 day</span>
            <span>3 days (Recommended)</span>
            <span>7 days</span>
            <span>14 days</span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs pt-1">
          <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-700 dark:text-emerald-300">
            <span className="font-bold block text-[11px] flex items-center gap-1">
              <CheckCircle2 size={12} /> Replied
            </span>
            <span className="text-[10px] text-muted-foreground">Prospect sent an inbound message</span>
          </div>
          <div className="p-2.5 rounded-lg bg-zinc-500/10 border border-zinc-500/20 text-zinc-700 dark:text-zinc-300">
            <span className="font-bold block text-[11px] flex items-center gap-1">
              <Clock size={12} /> Timeout
            </span>
            <span className="text-[10px] text-muted-foreground">No response after {waitDays}d limit</span>
          </div>
        </div>
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          Step name <span className="text-muted-foreground font-normal">(optional)</span>
        </label>
        <input
          value={data.step_name || ""}
          onChange={e => onChange("step_name", e.target.value)}
          placeholder="e.g. Wait 3 days for reply"
          className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
      </div>
    </div>
  );
}

function RetryStepConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  const maxRetries = data.max_retries !== undefined ? data.max_retries : 3;

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Backoff Delay Between Retries</label>
        <DelaySelector
          value={data.delay !== undefined ? data.delay : 1}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => {
            onChange("delay", v);
            onChange("delayUnit", u);
          }}
        />
      </div>

      <div className="p-4 rounded-xl bg-background border border-border space-y-4">
        <div className="flex items-center gap-2">
          <RotateCcw size={16} className="text-amber-500" />
          <h4 className="text-xs font-semibold text-foreground">Step Execution Fault Tolerance</h4>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Automatically retries the preceding action if transient network hiccups, rate limits, or AI provider timeouts occur.
        </p>

        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">Maximum Retry Attempts</label>
          <input
            type="number"
            min={1}
            max={5}
            value={maxRetries}
            onChange={e => onChange("max_retries", Math.max(1, Math.min(5, Number(e.target.value) || 1)))}
            className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
          />
          <span className="text-[10px] text-muted-foreground mt-1 block">Bounded between 1 and 5 retries to prevent infinite loops.</span>
        </div>

        <div className="p-3 rounded-xl bg-amber-50/80 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/40">
          <p className="text-xs text-amber-800 dark:text-amber-300 font-medium">
            If max retries ({maxRetries}) are exhausted, execution advances downstream down the <strong>then</strong> branch to keep the prospect pipeline moving.
          </p>
        </div>
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          Step name <span className="text-muted-foreground font-normal">(optional)</span>
        </label>
        <input
          value={data.step_name || ""}
          onChange={e => onChange("step_name", e.target.value)}
          placeholder="e.g. Retry failed enrichment"
          className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
      </div>
    </div>
  );
}

function IfConnectedConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  const delayDays = data.delay ?? 3;
  const isPacingWarning = delayDays === 0;

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="block text-xs font-semibold text-foreground">Listening Window / Pacing Delay</label>
          {isPacingWarning ? (
            <span className="text-[10px] font-medium text-amber-500 flex items-center gap-1">
              <AlertTriangle size={11} /> 0-day check risks 100% false negative
            </span>
          ) : (
            <span className="text-[10px] font-medium text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
              <Check size={11} /> Optimal warmup pacing
            </span>
          )}
        </div>
        <DelaySelector
          value={data.delay}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => {
            onChange("delay", v);
            onChange("delayUnit", u);
          }}
        />
        <p className="text-[11px] text-muted-foreground mt-1.5 leading-relaxed">
          Allow 2 to 4 days for prospects to review and accept your connection request before branching.
        </p>
      </div>

      <div className="rounded-xl bg-background border border-border p-4 space-y-3">
        <h4 className="text-xs font-semibold text-foreground flex items-center gap-1.5">
          <CheckCircle2 size={13} className="text-emerald-500" />
          Sequence Branching Architecture
        </h4>
        <div className="space-y-2">
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
            <span className="text-[10px] font-bold text-emerald-700 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/30 whitespace-nowrap">
              Connected
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              Lead accepted your invitation. Advance immediately to 1st-degree outreach (<strong className="text-foreground">Send Message</strong> or <strong className="text-foreground">Voice Note</strong>).
            </p>
          </div>
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-zinc-500/5 border border-border">
            <span className="text-[10px] font-bold text-muted-foreground bg-muted px-2 py-0.5 rounded-full border border-border whitespace-nowrap">
              Not connected
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              Invite remains pending or unanswered. Route to <strong className="text-foreground">Send InMail</strong>, <strong className="text-foreground">Find Email</strong>, or graceful exit.
            </p>
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-border bg-card p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="space-y-0.5">
            <label className="text-xs font-semibold text-foreground">Auto-Withdraw Stale Requests</label>
            <p className="text-[11px] text-muted-foreground">
              Prevents hitting LinkedIn's 1,000 pending invite shadow-ban limit
            </p>
          </div>
          <button
            type="button"
            onClick={() => onChange("withdraw_enabled", !data.withdraw_enabled)}
            className={cn(
              "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none",
              data.withdraw_enabled ? "bg-primary" : "bg-muted"
            )}
          >
            <span
              className={cn(
                "pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out",
                data.withdraw_enabled ? "translate-x-4" : "translate-x-0"
              )}
            />
          </button>
        </div>

        {data.withdraw_enabled && (
          <div className="pt-2 border-t border-border flex items-center justify-between">
            <span className="text-xs text-muted-foreground">Withdraw after</span>
            <div className="flex items-center gap-1.5">
              <input
                type="number"
                min={3}
                max={90}
                value={data.withdraw_days || 14}
                onChange={(e) => onChange("withdraw_days", Math.max(3, Number(e.target.value)))}
                className="w-16 rounded-lg bg-background border border-border px-2 py-1 text-xs text-center text-foreground font-medium focus:outline-none focus:border-primary"
              />
              <span className="text-xs text-muted-foreground">days</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function IfRepliedConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Reply Listening Window</label>
        <DelaySelector
          value={data.delay}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => {
            onChange("delay", v);
            onChange("delayUnit", u);
          }}
        />
        <p className="text-[11px] text-muted-foreground mt-1.5 leading-relaxed">
          The sequence pauses for up to this duration to monitor the lead's LinkedIn inbox for incoming replies.
        </p>
      </div>

      <div className="rounded-xl bg-background border border-border p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            <Sparkles size={13} className="text-primary" />
            4-Branch AI Sentiment Map
          </h4>
          <span className="text-[10px] font-medium text-primary bg-primary/10 px-2 py-0.5 rounded-full border border-primary/20">
            Real-time LLM
          </span>
        </div>
        <p className="text-[11px] text-muted-foreground leading-relaxed">
          When the prospect replies, AI automatically detects their intent and routes them down the matching sequence branch:
        </p>
        <div className="space-y-2">
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
            <span className="text-[10px] font-bold text-emerald-700 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/30 whitespace-nowrap">
              Positive
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              Lead is interested or agreed to chat. Route to <strong className="text-foreground">Send Meeting Invite</strong> or alert sales rep.
            </p>
          </div>
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-rose-500/5 border border-rose-500/20">
            <span className="text-[10px] font-bold text-rose-700 dark:text-rose-400 bg-rose-500/10 px-2 py-0.5 rounded-full border border-rose-500/30 whitespace-nowrap">
              Negative
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              Lead declined, requested removal, or said not now. Route to polite acknowledgement or <strong className="text-foreground">Mark Converted/Opt-out</strong>.
            </p>
          </div>
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-amber-500/5 border border-amber-500/20">
            <span className="text-[10px] font-bold text-amber-700 dark:text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded-full border border-amber-500/30 whitespace-nowrap">
              Neutral
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              Lead asked questions, asked for pricing or deck. Route to value-add follow-up or case study.
            </p>
          </div>
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-zinc-500/5 border border-border">
            <span className="text-[10px] font-bold text-muted-foreground bg-muted px-2 py-0.5 rounded-full border border-border whitespace-nowrap">
              No Reply
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              No response within the window. Advance to your next follow-up nudge or multichannel touchpoint.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

function OpenProfileConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Check Delay</label>
        <DelaySelector
          value={data.delay}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => {
            onChange("delay", v);
            onChange("delayUnit", u);
          }}
        />
      </div>

      <div className="rounded-xl bg-background border border-border p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            <Search size={13} className="text-emerald-500" />
            Open Profile Branching
          </h4>
          <span className="text-[10px] font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
            0-Credit Free InMails
          </span>
        </div>
        <p className="text-[11px] text-muted-foreground leading-relaxed">
          Open Profiles allow anyone on LinkedIn to send direct InMail messages without burning paid InMail credits or waiting for a connection request!
        </p>
        <div className="space-y-2 mt-2">
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
            <span className="text-[10px] font-bold text-emerald-700 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/30 whitespace-nowrap">
              Open
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              Profile is open. Route directly to <strong className="text-foreground">Send InMail</strong> to land straight in their primary inbox.
            </p>
          </div>
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-zinc-500/5 border border-border">
            <span className="text-[10px] font-bold text-muted-foreground bg-muted px-2 py-0.5 rounded-full border border-border whitespace-nowrap">
              Not open
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              Standard profile. Route to <strong className="text-foreground">Connection Request</strong> or profile warmup.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

function SeamlessIdentityMatchingConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  return (
    <div className="space-y-6">
      <div className="rounded-xl bg-background border border-border p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            <ShieldCheck size={14} className="text-cyan-500" />
            Zero-Cost Multichannel Fallback
          </h4>
          <span className="text-[10px] font-semibold text-cyan-600 dark:text-cyan-400 bg-cyan-500/10 px-2 py-0.5 rounded-full border border-cyan-500/20">
            Blue Ocean Engine
          </span>
        </div>
        <p className="text-[11px] text-muted-foreground leading-relaxed">
          Monitors connection acceptance. If the prospect leaves your invite pending past the timeout, the Zero-Cost Engine dynamically discovers their verified corporate email and activates a warm email sequence referencing your pending LinkedIn invite.
        </p>
        <div className="space-y-2 mt-2">
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
            <span className="text-[10px] font-bold text-emerald-700 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/30 whitespace-nowrap">
              Connected
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              Accepted on LinkedIn. Continue your high-converting LinkedIn sequence.
            </p>
          </div>
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-cyan-500/5 border border-cyan-500/20">
            <span className="text-[10px] font-bold text-cyan-700 dark:text-cyan-400 bg-cyan-500/10 px-2 py-0.5 rounded-full border border-cyan-500/30 whitespace-nowrap">
              Email Discovered
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              Pending after timeout. Direct corporate email found. Route to <strong className="text-foreground">Send Email</strong> or cold sequencer.
            </p>
          </div>
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-zinc-500/5 border border-border">
            <span className="text-[10px] font-bold text-muted-foreground bg-muted px-2 py-0.5 rounded-full border border-border whitespace-nowrap">
              Not connected
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              Neither connected nor email found. Route to alternate fallback (e.g. InMail or graceful sequence exit).
            </p>
          </div>
        </div>
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">Timeout Days before Email Discovery</label>
        <input
          type="number"
          min={1}
          max={30}
          value={data.timeout_days || 7}
          onChange={(e) => onChange("timeout_days", Math.max(1, Number(e.target.value)))}
          className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground focus:outline-none focus:border-cyan-500"
        />
        <p className="text-[11px] text-muted-foreground mt-1">
          Default: 7 days. Allows ample time for the prospect to connect on LinkedIn before switching channels.
        </p>
      </div>

      <div className="flex items-center justify-between p-3.5 rounded-xl border border-border bg-card">
        <div className="space-y-0.5">
          <label className="text-xs font-semibold text-foreground">Auto-Discover Corporate Email</label>
          <p className="text-[11px] text-muted-foreground">Uses Zero-Cost SMTP permutation discovery if email is missing</p>
        </div>
        <button
          type="button"
          onClick={() => onChange("auto_discover_email", data.auto_discover_email === false ? true : false)}
          className={cn(
            "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none",
            data.auto_discover_email !== false ? "bg-cyan-600" : "bg-muted"
          )}
        >
          <span
            className={cn(
              "pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out",
              data.auto_discover_email !== false ? "translate-x-4" : "translate-x-0"
            )}
          />
        </button>
      </div>

      <div className="flex items-center justify-between p-3.5 rounded-xl border border-border bg-card">
        <div className="space-y-0.5">
          <label className="text-xs font-semibold text-foreground">Auto-Withdraw Pending LinkedIn Request</label>
          <p className="text-[11px] text-muted-foreground">Releases LinkedIn pending invitation slots once switching to email to prevent shadow-ban caps</p>
        </div>
        <button
          type="button"
          onClick={() => onChange("auto_withdraw_invite", !data.auto_withdraw_invite)}
          className={cn(
            "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none",
            data.auto_withdraw_invite ? "bg-cyan-600" : "bg-muted"
          )}
        >
          <span
            className={cn(
              "pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out",
              data.auto_withdraw_invite ? "translate-x-4" : "translate-x-0"
            )}
          />
        </button>
      </div>

      <div className="flex items-center justify-between p-3.5 rounded-xl border border-border bg-card">
        <div className="space-y-0.5">
          <label className="text-xs font-semibold text-foreground">Apollo.io People Match Fallback</label>
          <p className="text-[11px] text-muted-foreground">Automatically query connected Apollo API if zero-cost SMTP handshake fails</p>
        </div>
        <button
          type="button"
          onClick={() => onChange("apollo_fallback", data.apollo_fallback === false ? true : false)}
          className={cn(
            "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none",
            data.apollo_fallback !== false ? "bg-cyan-600" : "bg-muted"
          )}
        >
          <span
            className={cn(
              "pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out",
              data.apollo_fallback !== false ? "translate-x-4" : "translate-x-0"
            )}
          />
        </button>
      </div>
    </div>
  );
}

function IfEmailFoundConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  return (
    <div className="space-y-6">
      <div className="rounded-xl bg-background border border-border p-4 space-y-3">
        <h4 className="text-xs font-semibold text-foreground flex items-center gap-1.5">
          <AtSign size={13} className="text-emerald-500" />
          Email Availability Branching
        </h4>
        <div className="space-y-2">
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
            <span className="text-[10px] font-bold text-emerald-700 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/30 whitespace-nowrap">
              Has Email
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              Lead possesses a verified corporate or personal email. Route to <strong className="text-foreground">Send Email</strong>, <strong className="text-foreground">Smartlead</strong>, or CRM.
            </p>
          </div>
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-zinc-500/5 border border-border">
            <span className="text-[10px] font-bold text-muted-foreground bg-muted px-2 py-0.5 rounded-full border border-border whitespace-nowrap">
              No Email
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              No email found. Route to alternative LinkedIn action or graceful sequence end.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

function IfMeetingBookedConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Check Delay</label>
        <DelaySelector
          value={data.delay}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => {
            onChange("delay", v);
            onChange("delayUnit", u);
          }}
        />
      </div>

      <div className="rounded-xl bg-background border border-border p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            <CalendarCheck size={13} className="text-emerald-500" />
            Meeting Safety Kill-Switch
          </h4>
          <span className="text-[10px] font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
            Anti-Embarrassment Guard
          </span>
        </div>
        <p className="text-[11px] text-muted-foreground leading-relaxed">
          Checks if the lead booked a meeting through your calendar integration or was tagged as converted.
        </p>
        <div className="space-y-2 mt-2">
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
            <span className="text-[10px] font-bold text-emerald-700 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/30 whitespace-nowrap">
              Booked
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              Meeting booked! Route to <strong className="text-foreground">Mark Converted</strong>. Automatically pauses further outreach so leads aren't annoyed after converting.
            </p>
          </div>
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-zinc-500/5 border border-border">
            <span className="text-[10px] font-bold text-muted-foreground bg-muted px-2 py-0.5 rounded-full border border-border whitespace-nowrap">
              Not booked
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              No meeting booked yet. Continue the automated sequence.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

function ConditionConfig({ data, onChange, label }: { data: any; onChange: (k: string, v: any) => void; label: string }) {
  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Check after delay</label>
        <DelaySelector value={data.delay} unit={data.delayUnit || "days"} onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }} />
      </div>
      <div className="p-4 rounded-xl bg-background border border-border">
        <p className="text-xs text-muted-foreground leading-relaxed">
          <strong className="text-foreground">{label}</strong> — the sequence will branch into two paths based on the result.
        </p>
        <div className="flex items-center gap-3 mt-3">
          <span className="text-[10px] font-bold text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/40 px-2.5 py-1 rounded-full border border-emerald-200 dark:border-emerald-800/40">Yes path</span>
          <span className="text-[10px] font-bold text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-950/40 px-2.5 py-1 rounded-full border border-red-200 dark:border-red-800/40">No path</span>
        </div>
      </div>
    </div>
  )
}

function IfCompanySizeConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  const minSize = data.min_size !== undefined ? Number(data.min_size) : 10;
  const maxSize = data.max_size !== undefined ? Number(data.max_size) : 500;
  const isInverted = maxSize > 0 && maxSize < minSize;

  const PRESETS = [
    { label: "Startup (1-20)", min: 1, max: 20 },
    { label: "SMB (20-100)", min: 20, max: 100 },
    { label: "Mid-Market (100-500)", min: 100, max: 500 },
    { label: "Enterprise (500+)", min: 500, max: 0 },
    { label: "Mega-Enterprise (5k+)", min: 5000, max: 0 },
  ];

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Check Delay</label>
        <DelaySelector
          value={data.delay}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => {
            onChange("delay", v);
            onChange("delayUnit", u);
          }}
        />
      </div>

      <div className="rounded-xl bg-background border border-border p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            <Building2 size={13} className="text-emerald-500" />
            Company Headcount Filter
          </h4>
          <span className="text-[10px] font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
            Account Fit
          </span>
        </div>
        <p className="text-[11px] text-muted-foreground leading-relaxed">
          Splits leads based on verified company employee count. Handles Apollo and LinkedIn bands (e.g. "51-200" or "10,001+").
        </p>
        <div className="space-y-2 mt-2">
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
            <span className="text-[10px] font-bold text-emerald-700 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/30 whitespace-nowrap">
              In range
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              Headcount falls within specified limits ({minSize} - {maxSize === 0 ? "No limit" : maxSize}). Routes to your primary tailored messaging.
            </p>
          </div>
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-zinc-500/5 border border-border">
            <span className="text-[10px] font-bold text-muted-foreground bg-muted px-2 py-0.5 rounded-full border border-border whitespace-nowrap">
              Out of range
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              Company is smaller, larger, or unlisted. Route to secondary outreach or skip.
            </p>
          </div>
        </div>
      </div>

      <div className="space-y-3">
        <label className="block text-xs font-semibold text-foreground">Quick Size Presets</label>
        <div className="flex flex-wrap gap-1.5">
          {PRESETS.map((p) => {
            const isSelected = minSize === p.min && maxSize === p.max;
            return (
              <button
                key={p.label}
                type="button"
                onClick={() => {
                  onChange("min_size", p.min);
                  onChange("max_size", p.max);
                }}
                className={cn(
                  "px-2.5 py-1 text-xs rounded-lg border transition-all",
                  isSelected
                    ? "bg-primary text-primary-foreground border-primary font-medium shadow-xs"
                    : "bg-muted/30 border-border text-foreground hover:bg-muted/60"
                )}
              >
                {p.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">Min Headcount</label>
          <input
            type="number"
            min={1}
            value={minSize}
            onChange={(e) => onChange("min_size", Math.max(1, Number(e.target.value) || 1))}
            className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground focus:outline-none focus:border-indigo-600"
          />
        </div>
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">Max Headcount (0 = ∞)</label>
          <input
            type="number"
            min={0}
            value={maxSize}
            onChange={(e) => onChange("max_size", Math.max(0, Number(e.target.value) || 0))}
            className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground focus:outline-none focus:border-indigo-600"
          />
        </div>
      </div>

      {isInverted && (
        <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-start justify-between gap-3 text-xs text-amber-600 dark:text-amber-400">
          <div className="flex items-start gap-2">
            <AlertTriangle size={15} className="shrink-0 mt-0.5 text-amber-500" />
            <div>
              <p className="font-semibold">Inverted Bounds Detected</p>
              <p className="text-[11px] opacity-90 mt-0.5">
                Max headcount ({maxSize}) is less than Min ({minSize}). The executor will auto-correct at runtime.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => {
              onChange("min_size", maxSize);
              onChange("max_size", minSize);
            }}
            className="shrink-0 px-2 py-1 bg-amber-500/20 hover:bg-amber-500/30 rounded text-[11px] font-semibold border border-amber-500/40"
          >
            Swap
          </button>
        </div>
      )}
    </div>
  );
}

function IfCompanyHiringConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  const roleKeywords = data.role_keywords || "";

  const KEYWORD_CHIPS = ["Engineering", "Sales", "Marketing", "Leadership", "Product", "Operations"];

  const handleChipClick = (kw: string) => {
    if (!roleKeywords) {
      onChange("role_keywords", kw);
      return;
    }
    const parts = roleKeywords.split(",").map((s: string) => s.trim()).filter(Boolean);
    if (parts.includes(kw)) {
      onChange("role_keywords", parts.filter((p: string) => p !== kw).join(", "));
    } else {
      onChange("role_keywords", [...parts, kw].join(", "));
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Check Delay</label>
        <DelaySelector
          value={data.delay}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => {
            onChange("delay", v);
            onChange("delayUnit", u);
          }}
        />
      </div>

      <div className="rounded-xl bg-background border border-border p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            <Briefcase size={13} className="text-emerald-500" />
            Hiring Intent Signal Gate
          </h4>
          <span className="text-[10px] font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
            Buying Intent
          </span>
        </div>
        <p className="text-[11px] text-muted-foreground leading-relaxed">
          Detects if the prospect's company is actively hiring on LinkedIn. Open job postings indicate budget, growth, and organizational readiness.
        </p>
        <div className="space-y-2 mt-2">
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
            <span className="text-[10px] font-bold text-emerald-700 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/30 whitespace-nowrap">
              Hiring
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              Open jobs found. Route to value-oriented growth pitch or tailored solution.
            </p>
          </div>
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-zinc-500/5 border border-border">
            <span className="text-[10px] font-bold text-muted-foreground bg-muted px-2 py-0.5 rounded-full border border-border whitespace-nowrap">
              Not hiring
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              No active job listings. Route to baseline nurture or alternate pain points.
            </p>
          </div>
        </div>
      </div>

      <div className="space-y-2">
        <label className="block text-xs font-semibold text-foreground">
          Role Keywords (Optional Filter)
        </label>
        <input
          type="text"
          placeholder="e.g. Sales, Account Executive, Engineer"
          value={roleKeywords}
          onChange={(e) => onChange("role_keywords", e.target.value)}
          className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
        <p className="text-[11px] text-muted-foreground">
          Leave blank to detect ANY active job posting. Or specify keywords to require specific roles.
        </p>

        <div className="flex flex-wrap gap-1.5 pt-1">
          {KEYWORD_CHIPS.map((chip) => {
            const active = roleKeywords.includes(chip);
            return (
              <button
                key={chip}
                type="button"
                onClick={() => handleChipClick(chip)}
                className={cn(
                  "px-2 py-0.5 text-[11px] rounded-md border transition-all",
                  active
                    ? "bg-emerald-500/15 border-emerald-500/40 text-emerald-600 dark:text-emerald-400 font-medium"
                    : "bg-muted/30 border-border text-muted-foreground hover:text-foreground"
                )}
              >
                + {chip}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function IfPremiumMemberConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Check Delay</label>
        <DelaySelector
          value={data.delay}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => {
            onChange("delay", v);
            onChange("delayUnit", u);
          }}
        />
      </div>

      <div className="rounded-xl bg-background border border-border p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            <Award size={13} className="text-amber-500" />
            LinkedIn Premium Badge Filter
          </h4>
          <span className="text-[10px] font-semibold text-amber-600 dark:text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded-full border border-amber-500/20">
            High Intent
          </span>
        </div>
        <p className="text-[11px] text-muted-foreground leading-relaxed">
          Checks if the prospect has a gold LinkedIn Premium, Sales Navigator, or Recruiter badge. Premium members are active decision-makers with dedicated tools and direct budget.
        </p>
        <div className="space-y-2 mt-2">
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-amber-500/5 border border-amber-500/20">
            <span className="text-[10px] font-bold text-amber-700 dark:text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded-full border border-amber-500/30 whitespace-nowrap">
              Premium
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              Premium member! Route to high-touch personalization or priority messaging with higher velocity follow-ups.
            </p>
          </div>
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-zinc-500/5 border border-border">
            <span className="text-[10px] font-bold text-muted-foreground bg-muted px-2 py-0.5 rounded-full border border-border whitespace-nowrap">
              Free
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              Standard LinkedIn profile. Route down standard sequence path.
            </p>
          </div>
        </div>
      </div>

      <div className="p-3.5 rounded-xl bg-card border border-border space-y-1.5">
        <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
          <Sparkles size={13} className="text-amber-500" />
          Tactical Recommendation
        </div>
        <p className="text-[11px] text-muted-foreground leading-relaxed">
          Premium members check LinkedIn on average 3.2x more often and have higher InMail reply limits. They respond best to concise, executive-level problem statements.
        </p>
      </div>
    </div>
  );
}

function IfMutualConnectionsConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  const minMutuals = data.min_mutuals !== undefined ? Number(data.min_mutuals) : 1;

  const PRESETS = [1, 3, 5, 10];

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Check Delay</label>
        <DelaySelector
          value={data.delay}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => {
            onChange("delay", v);
            onChange("delayUnit", u);
          }}
        />
      </div>

      <div className="rounded-xl bg-background border border-border p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            <Users size={13} className="text-emerald-500" />
            Shared Network Trust Gate
          </h4>
          <span className="text-[10px] font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
            Trust Multiplier
          </span>
        </div>
        <p className="text-[11px] text-muted-foreground leading-relaxed">
          Checks if the lead shares mutual connections with your sending account. Shared network context increases connection acceptance rates by up to 140%.
        </p>
        <div className="space-y-2 mt-2">
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
            <span className="text-[10px] font-bold text-emerald-700 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/30 whitespace-nowrap">
              Has mutuals
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              Shares at least {minMutuals} mutual connection{minMutuals > 1 ? "s" : ""}. Route to high-trust opener referencing your mutual colleagues.
            </p>
          </div>
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-zinc-500/5 border border-border">
            <span className="text-[10px] font-bold text-muted-foreground bg-muted px-2 py-0.5 rounded-full border border-border whitespace-nowrap">
              No mutuals
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              Cold 2nd or 3rd degree connection. Route to standard value-led introduction.
            </p>
          </div>
        </div>
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <label className="text-xs font-semibold text-foreground">
            Minimum Mutual Connections
          </label>
          <span className="text-xs font-bold text-primary">{minMutuals}+</span>
        </div>
        <div className="flex gap-2">
          {PRESETS.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => onChange("min_mutuals", p)}
              className={cn(
                "flex-1 py-1.5 text-xs rounded-lg border font-medium transition-all",
                minMutuals === p
                  ? "bg-primary text-primary-foreground border-primary shadow-xs"
                  : "bg-muted/30 border-border text-foreground hover:bg-muted/60"
              )}
            >
              {p}+ Mutual{p > 1 ? "s" : ""}
            </button>
          ))}
        </div>
        <input
          type="range"
          min={1}
          max={20}
          value={minMutuals}
          onChange={(e) => onChange("min_mutuals", Number(e.target.value))}
          className="w-full accent-primary cursor-pointer"
        />
      </div>
    </div>
  );
}

function IfRecentlyActiveConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  const days = data.days !== undefined ? Number(data.days) : 7;

  const PRESETS = [
    { label: "3 Days (Hyper-Active)", value: 3 },
    { label: "7 Days (Recommended)", value: 7 },
    { label: "14 Days (Bi-Weekly)", value: 14 },
    { label: "30 Days (Monthly)", value: 30 },
  ];

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Check Delay</label>
        <DelaySelector
          value={data.delay}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => {
            onChange("delay", v);
            onChange("delayUnit", u);
          }}
        />
      </div>

      <div className="rounded-xl bg-background border border-border p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            <Zap size={13} className="text-emerald-500" />
            Activity Recency Filter
          </h4>
          <span className="text-[10px] font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
            Engagement Velocity
          </span>
        </div>
        <p className="text-[11px] text-muted-foreground leading-relaxed">
          Checks if the prospect has interacted, commented, or logged into LinkedIn within the last N days. Filtering out dormant accounts protects your daily invitation quota.
        </p>
        <div className="space-y-2 mt-2">
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
            <span className="text-[10px] font-bold text-emerald-700 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/30 whitespace-nowrap">
              Active
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              Active within {days} days. High probability of receiving and responding to LinkedIn notifications.
            </p>
          </div>
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-zinc-500/5 border border-border">
            <span className="text-[10px] font-bold text-muted-foreground bg-muted px-2 py-0.5 rounded-full border border-border whitespace-nowrap">
              Inactive
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              Dormant profile. Route to multichannel email lookup (Find Email) or disqualify.
            </p>
          </div>
        </div>
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <label className="text-xs font-semibold text-foreground">
            Activity Window
          </label>
          <span className="text-xs font-bold text-primary">{days} Days</span>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {PRESETS.map((p) => (
            <button
              key={p.value}
              type="button"
              onClick={() => onChange("days", p.value)}
              className={cn(
                "py-1.5 px-2 text-xs rounded-lg border font-medium text-left transition-all",
                days === p.value
                  ? "bg-primary text-primary-foreground border-primary shadow-xs"
                  : "bg-muted/30 border-border text-foreground hover:bg-muted/60"
              )}
            >
              {p.label}
            </button>
          ))}
        </div>
        <input
          type="range"
          min={1}
          max={60}
          value={days}
          onChange={(e) => onChange("days", Number(e.target.value))}
          className="w-full accent-primary cursor-pointer"
        />
      </div>
    </div>
  );
}

function IfHasRecentPostsConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  const days = data.days !== undefined ? Number(data.days) : 30;

  const PRESETS = [7, 14, 30, 60];

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Check Delay</label>
        <DelaySelector
          value={data.delay}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => {
            onChange("delay", v);
            onChange("delayUnit", u);
          }}
        />
      </div>

      <div className="rounded-xl bg-background border border-border p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            <MessageSquare size={13} className="text-emerald-500" />
            Content Creator / Poster Gate
          </h4>
          <span className="text-[10px] font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
            Warm Engagement
          </span>
        </div>
        <p className="text-[11px] text-muted-foreground leading-relaxed">
          Checks if the lead has published original posts or articles within the last N days. Active content creators are primed for social warmup actions (like or comment) prior to connecting.
        </p>
        <div className="space-y-2 mt-2">
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
            <span className="text-[10px] font-bold text-emerald-700 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/30 whitespace-nowrap">
              Has posts
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              Posted in last {days} days. Route to "Comment on Post" or "Like Top 3 Posts" for high-touch warmup.
            </p>
          </div>
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-zinc-500/5 border border-border">
            <span className="text-[10px] font-bold text-muted-foreground bg-muted px-2 py-0.5 rounded-full border border-border whitespace-nowrap">
              No posts
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              No recent posts found. Skip post engagement steps and proceed directly to "View Profile" or connection request.
            </p>
          </div>
        </div>
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <label className="text-xs font-semibold text-foreground">
            Lookback Window
          </label>
          <span className="text-xs font-bold text-primary">{days} Days</span>
        </div>
        <div className="flex gap-2">
          {PRESETS.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => onChange("days", p)}
              className={cn(
                "flex-1 py-1.5 text-xs rounded-lg border font-medium transition-all",
                days === p
                  ? "bg-primary text-primary-foreground border-primary shadow-xs"
                  : "bg-muted/30 border-border text-foreground hover:bg-muted/60"
              )}
            >
              {p} Days
            </button>
          ))}
        </div>
        <input
          type="range"
          min={7}
          max={90}
          value={days}
          onChange={(e) => onChange("days", Number(e.target.value))}
          className="w-full accent-primary cursor-pointer"
        />
      </div>
    </div>
  );
}

function IfLargeFollowingConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  const threshold = data.follower_threshold !== undefined ? Number(data.follower_threshold) : 10000;

  const PRESETS = [
    { label: "2,500 (Rising)", value: 2500 },
    { label: "5,000 (KOL)", value: 5000 },
    { label: "10,000 (Influencer)", value: 10000 },
    { label: "25,000+ (Executive)", value: 25000 },
  ];

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Check Delay</label>
        <DelaySelector
          value={data.delay}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => {
            onChange("delay", v);
            onChange("delayUnit", u);
          }}
        />
      </div>

      <div className="rounded-xl bg-background border border-border p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            <Users size={13} className="text-emerald-500" />
            Audience Scale & Influence Filter
          </h4>
          <span className="text-[10px] font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
            Influence Tier
          </span>
        </div>
        <p className="text-[11px] text-muted-foreground leading-relaxed">
          Checks if the prospect has a large public following. High-following profiles receive hundreds of connection requests weekly and require differentiated messaging.
        </p>
        <div className="space-y-2 mt-2">
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
            <span className="text-[10px] font-bold text-emerald-700 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/30 whitespace-nowrap">
              High following
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              Followers ≥ {threshold.toLocaleString()}. Route to tailored InMail or personalized high-touch outreach.
            </p>
          </div>
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-zinc-500/5 border border-border">
            <span className="text-[10px] font-bold text-muted-foreground bg-muted px-2 py-0.5 rounded-full border border-border whitespace-nowrap">
              Normal following
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              Standard follower count. Route down regular outbound sequence.
            </p>
          </div>
        </div>
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <label className="text-xs font-semibold text-foreground">
            Follower Threshold
          </label>
          <span className="text-xs font-bold text-primary">{threshold.toLocaleString()} Followers</span>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {PRESETS.map((p) => (
            <button
              key={p.value}
              type="button"
              onClick={() => onChange("follower_threshold", p.value)}
              className={cn(
                "py-1.5 px-2 text-xs rounded-lg border font-medium text-left transition-all",
                threshold === p.value
                  ? "bg-primary text-primary-foreground border-primary shadow-xs"
                  : "bg-muted/30 border-border text-foreground hover:bg-muted/60"
              )}
            >
              {p.label}
            </button>
          ))}
        </div>
        <input
          type="number"
          min={500}
          step={500}
          value={threshold}
          onChange={(e) => onChange("follower_threshold", Math.max(0, Number(e.target.value)))}
          className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground focus:outline-none focus:border-indigo-600"
        />
      </div>
    </div>
  );
}

function IfTitleMatchesConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  const keyword = data.keyword || "";

  const PERSONA_PACKS = [
    { label: "C-Suite & Founders", value: "Founder, Co-Founder, CEO, CTO, COO" },
    { label: "VP & Heads", value: "VP, Vice President, Head of" },
    { label: "Directors", value: "Director, Managing Director" },
    { label: "Sales & Revenue", value: "CRO, VP Sales, Head of Sales, Account Executive, SDR" },
    { label: "Eng & Product", value: "VP Engineering, Head of Product, Tech Lead, Architect" },
  ];

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Check Delay</label>
        <DelaySelector
          value={data.delay}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => {
            onChange("delay", v);
            onChange("delayUnit", u);
          }}
        />
      </div>

      <div className="rounded-xl bg-background border border-border p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            <Tag size={13} className="text-emerald-500" />
            Job Title & Persona Filter
          </h4>
          <span className="text-[10px] font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
            Persona Routing
          </span>
        </div>
        <p className="text-[11px] text-muted-foreground leading-relaxed">
          Branches on whether the lead's current job title or headline matches your target persona keywords.
        </p>
        <div className="space-y-2 mt-2">
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
            <span className="text-[10px] font-bold text-emerald-700 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/30 whitespace-nowrap">
              Matches
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              Title matches target persona. Route to role-specific messaging sequence.
            </p>
          </div>
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-zinc-500/5 border border-border">
            <span className="text-[10px] font-bold text-muted-foreground bg-muted px-2 py-0.5 rounded-full border border-border whitespace-nowrap">
              Does not match
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              Lead has an alternate title. Route to fallback track or alternate campaign.
            </p>
          </div>
        </div>
      </div>

      <div className="space-y-3">
        <label className="block text-xs font-semibold text-foreground">
          Title Keywords (Comma-Separated)
        </label>
        <textarea
          rows={2}
          placeholder="e.g. VP, Head of, Director, Founder"
          value={keyword}
          onChange={(e) => onChange("keyword", e.target.value)}
          className="w-full rounded-lg bg-card border border-border p-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none"
        />
        <p className="text-[11px] text-muted-foreground">
          Case-insensitive matching. Supports comma or pipe separation.
        </p>

        <div className="space-y-1.5 pt-1">
          <span className="text-[11px] font-semibold text-muted-foreground block">Quick Persona Presets:</span>
          <div className="flex flex-wrap gap-1.5">
            {PERSONA_PACKS.map((pack) => (
              <button
                key={pack.label}
                type="button"
                onClick={() => onChange("keyword", pack.value)}
                className="px-2.5 py-1 text-xs rounded-lg border bg-muted/30 border-border text-foreground hover:bg-muted/60 transition-all"
              >
                {pack.label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function IfLocationMatchesConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  const keyword = data.keyword || "";

  const REGION_PACKS = [
    { label: "United States", value: "United States, USA, US" },
    { label: "UK & Ireland", value: "United Kingdom, UK, London, Ireland, Dublin" },
    { label: "DACH Region", value: "Germany, Austria, Switzerland, Berlin, Munich, Zurich" },
    { label: "US Tech Hubs", value: "San Francisco, New York, Austin, Seattle, Boston" },
    { label: "APAC", value: "Singapore, Australia, Sydney, Tokyo, India" },
  ];

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Check Delay</label>
        <DelaySelector
          value={data.delay}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => {
            onChange("delay", v);
            onChange("delayUnit", u);
          }}
        />
      </div>

      <div className="rounded-xl bg-background border border-border p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            <MapPin size={13} className="text-emerald-500" />
            Geographic Territory Filter
          </h4>
          <span className="text-[10px] font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
            Territory Routing
          </span>
        </div>
        <p className="text-[11px] text-muted-foreground leading-relaxed">
          Branches on whether the prospect is located in a target city, state, country, or region.
        </p>
        <div className="space-y-2 mt-2">
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
            <span className="text-[10px] font-bold text-emerald-700 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/30 whitespace-nowrap">
              Matches
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              Located in target territory. Route to localized pitch, local event invitation, or timezone-aligned sender.
            </p>
          </div>
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-zinc-500/5 border border-border">
            <span className="text-[10px] font-bold text-muted-foreground bg-muted px-2 py-0.5 rounded-full border border-border whitespace-nowrap">
              Does not match
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              Outside territory. Route to remote/international outreach track.
            </p>
          </div>
        </div>
      </div>

      <div className="space-y-3">
        <label className="block text-xs font-semibold text-foreground">
          Target Locations (Comma-Separated)
        </label>
        <textarea
          rows={2}
          placeholder="e.g. United States, London, San Francisco, Germany"
          value={keyword}
          onChange={(e) => onChange("keyword", e.target.value)}
          className="w-full rounded-lg bg-card border border-border p-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none"
        />
        <p className="text-[11px] text-muted-foreground">
          Matches against city, country, or geographic area. Case-insensitive.
        </p>

        <div className="space-y-1.5 pt-1">
          <span className="text-[11px] font-semibold text-muted-foreground block">Territory Presets:</span>
          <div className="flex flex-wrap gap-1.5">
            {REGION_PACKS.map((pack) => (
              <button
                key={pack.label}
                type="button"
                onClick={() => onChange("keyword", pack.value)}
                className="px-2.5 py-1 text-xs rounded-lg border bg-muted/30 border-border text-foreground hover:bg-muted/60 transition-all"
              >
                {pack.label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function IfIndustryMatchesConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  const keyword = data.keyword || "";

  const INDUSTRY_PACKS = [
    { label: "Software & SaaS", value: "Software Development, Technology, SaaS, Internet" },
    { label: "Fintech & Finance", value: "Financial Services, Banking, Fintech, Investment" },
    { label: "Healthcare & Biotech", value: "Healthcare, Biotechnology, Pharmaceuticals, Medical" },
    { label: "E-Commerce & Retail", value: "Retail, E-Commerce, Consumer Goods, Apparel" },
    { label: "Manufacturing & Industrial", value: "Manufacturing, Automotive, Industrial, Construction" },
  ];

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Check Delay</label>
        <DelaySelector
          value={data.delay}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => {
            onChange("delay", v);
            onChange("delayUnit", u);
          }}
        />
      </div>

      <div className="rounded-xl bg-background border border-border p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            <Building2 size={13} className="text-emerald-500" />
            Vertical & Industry Segment Filter
          </h4>
          <span className="text-[10px] font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
            Vertical Routing
          </span>
        </div>
        <p className="text-[11px] text-muted-foreground leading-relaxed">
          Branches on whether the lead's company industry contains your target vertical keywords. Enables industry-specific case studies and pain points.
        </p>
        <div className="space-y-2 mt-2">
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
            <span className="text-[10px] font-bold text-emerald-700 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/30 whitespace-nowrap">
              Matches
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              Matches target vertical. Route to industry-tailored sequence with specific case studies.
            </p>
          </div>
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-zinc-500/5 border border-border">
            <span className="text-[10px] font-bold text-muted-foreground bg-muted px-2 py-0.5 rounded-full border border-border whitespace-nowrap">
              Does not match
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              Different industry. Route to horizontal value proposition.
            </p>
          </div>
        </div>
      </div>

      <div className="space-y-3">
        <label className="block text-xs font-semibold text-foreground">
          Industry Keywords (Comma-Separated)
        </label>
        <textarea
          rows={2}
          placeholder="e.g. Software, Financial Services, Healthcare"
          value={keyword}
          onChange={(e) => onChange("keyword", e.target.value)}
          className="w-full rounded-lg bg-card border border-border p-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none"
        />
        <p className="text-[11px] text-muted-foreground">
          Matches LinkedIn company industry field. Case-insensitive.
        </p>

        <div className="space-y-1.5 pt-1">
          <span className="text-[11px] font-semibold text-muted-foreground block">Vertical Presets:</span>
          <div className="flex flex-wrap gap-1.5">
            {INDUSTRY_PACKS.map((pack) => (
              <button
                key={pack.label}
                type="button"
                onClick={() => onChange("keyword", pack.value)}
                className="px-2.5 py-1 text-xs rounded-lg border bg-muted/30 border-border text-foreground hover:bg-muted/60 transition-all"
              >
                {pack.label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function ICPScoreGateConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  const { openPaywall } = usePaywall();
  const { data: billing } = useSWR<any>('/api/elein/workspaces/billing', fetcher);
  const isIcpLocked = Boolean(billing && !billing.tier_limits?.can_use_bayesian_icp);

  const threshold = data.score_threshold !== undefined ? Number(data.score_threshold) : 75;
  const weightTitle = data.weight_title !== undefined ? Number(data.weight_title) : 30;
  const weightSize = data.weight_size !== undefined ? Number(data.weight_size) : 25;
  const weightIndustry = data.weight_industry !== undefined ? Number(data.weight_industry) : 25;
  const weightActivity = data.weight_activity !== undefined ? Number(data.weight_activity) : 20;

  const totalWeight = weightTitle + weightSize + weightIndustry + weightActivity;

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Check Delay</label>
        <DelaySelector
          value={data.delay}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => {
            onChange("delay", v);
            onChange("delayUnit", u);
          }}
        />
      </div>

      <div className="rounded-xl bg-background border border-border p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            <Target size={13} className="text-emerald-500" />
            Composite ICP Score Quality Gate
          </h4>
          <span className="text-[10px] font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
            Account Scoring
          </span>
        </div>
        <p className="text-[11px] text-muted-foreground leading-relaxed">
          Evaluates lead fit using multi-dimensional scoring (Title, Company Size, Industry, and Activity). Only allows leads meeting your quality bar to proceed to premium outreach.
        </p>
        <div className="space-y-2 mt-2">
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
            <span className="text-[10px] font-bold text-emerald-700 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/30 whitespace-nowrap">
              Strong fit (≥{threshold})
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              High-value account. Proceed to personalized outreach, premium InMails, or SDR handoff.
            </p>
          </div>
          <div className="flex items-start gap-2.5 p-2.5 rounded-lg bg-zinc-500/5 border border-border">
            <span className="text-[10px] font-bold text-muted-foreground bg-muted px-2 py-0.5 rounded-full border border-border whitespace-nowrap">
              Weak fit (&lt;{threshold})
            </span>
            <p className="text-[11px] text-muted-foreground leading-snug">
              Sub-optimal fit. Route to lightweight low-touch sequence or disqualify to preserve reputation.
            </p>
          </div>
        </div>
      </div>

      {/* In-Situ Pay Ramp: Adaptive Bayesian Thresholding */}
      <div className={cn(
        "p-3.5 rounded-xl border flex items-center justify-between gap-3 text-xs",
        isIcpLocked 
          ? "bg-amber-500/5 border-amber-500/25" 
          : "bg-emerald-500/5 border-emerald-500/20"
      )}>
        <div className="flex items-center gap-2.5">
          <div className={cn("p-1.5 rounded-lg shrink-0", isIcpLocked ? "bg-amber-500/10 text-amber-500" : "bg-emerald-500/10 text-emerald-400")}>
            <Target size={14} />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="font-bold text-foreground">Continuous Bayesian Deal Learning</span>
              {isIcpLocked ? (
                <span className="px-1.5 py-0.2 rounded bg-amber-400 text-slate-950 text-[9px] font-black tracking-wide">
                  PRO
                </span>
              ) : (
                <span className="px-1.5 py-0.2 rounded bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 text-[9px] font-bold border border-emerald-500/30">
                  ENABLED
                </span>
              )}
            </div>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              {isIcpLocked 
                ? "Static threshold grading. Growth Pro integrates live Bayesian Thompson Sampling to re-weight thresholds automatically."
                : "Active feedback loops continuously tune gate thresholds based on historical deal conversions."
              }
            </p>
          </div>
        </div>
        {isIcpLocked && (
          <button
            type="button"
            onClick={() => openPaywall({ featureName: "Bayesian Quality Threshold Gates" })}
            className="px-2.5 py-1 text-[11px] font-bold rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 shrink-0 transition-colors flex items-center gap-1 cursor-pointer"
          >
            <span>Unlock</span>
            <ArrowUpRight size={12} />
          </button>
        )}
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <label className="text-xs font-semibold text-foreground">
            Minimum Score Threshold (0 - 100)
          </label>
          <span className={cn(
            "text-xs font-bold px-2 py-0.5 rounded-full",
            threshold >= 75
              ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
              : threshold >= 50
              ? "bg-amber-500/15 text-amber-600 dark:text-amber-400"
              : "bg-rose-500/15 text-rose-600 dark:text-rose-400"
          )}>
            {threshold} / 100
          </span>
        </div>
        <input
          type="range"
          min={10}
          max={95}
          step={5}
          value={threshold}
          onChange={(e) => onChange("score_threshold", Number(e.target.value))}
          className="w-full accent-primary cursor-pointer"
        />
        <div className="flex justify-between text-[10px] text-muted-foreground">
          <span>Broad (10)</span>
          <span>Balanced (50)</span>
          <span>Strict Enterprise (75+)</span>
        </div>
      </div>

      <div className="p-4 rounded-xl bg-card border border-border space-y-3">
        <div className="flex items-center justify-between">
          <h5 className="text-xs font-semibold text-foreground">
            Scoring Dimension Weights
          </h5>
          <span className={cn(
            "text-[10px] font-semibold px-2 py-0.5 rounded-full border",
            totalWeight === 100
              ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20"
              : "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20"
          )}>
            Sum: {totalWeight}% {totalWeight === 100 ? "Balanced" : "(Auto-normalized)"}
          </span>
        </div>

        <div className="grid grid-cols-2 gap-3 pt-1">
          <div>
            <label className="text-[11px] text-muted-foreground flex justify-between mb-1">
              <span>Title Weight</span>
              <span className="font-semibold text-foreground">{weightTitle}%</span>
            </label>
            <input
              type="number"
              min={0}
              max={100}
              value={weightTitle}
              onChange={(e) => onChange("weight_title", Math.max(0, Number(e.target.value)))}
              className="w-full rounded-lg bg-background border border-border px-2.5 py-1.5 text-xs text-foreground focus:outline-none focus:border-indigo-600"
            />
          </div>
          <div>
            <label className="text-[11px] text-muted-foreground flex justify-between mb-1">
              <span>Company Size</span>
              <span className="font-semibold text-foreground">{weightSize}%</span>
            </label>
            <input
              type="number"
              min={0}
              max={100}
              value={weightSize}
              onChange={(e) => onChange("weight_size", Math.max(0, Number(e.target.value)))}
              className="w-full rounded-lg bg-background border border-border px-2.5 py-1.5 text-xs text-foreground focus:outline-none focus:border-indigo-600"
            />
          </div>
          <div>
            <label className="text-[11px] text-muted-foreground flex justify-between mb-1">
              <span>Industry Weight</span>
              <span className="font-semibold text-foreground">{weightIndustry}%</span>
            </label>
            <input
              type="number"
              min={0}
              max={100}
              value={weightIndustry}
              onChange={(e) => onChange("weight_industry", Math.max(0, Number(e.target.value)))}
              className="w-full rounded-lg bg-background border border-border px-2.5 py-1.5 text-xs text-foreground focus:outline-none focus:border-indigo-600"
            />
          </div>
          <div>
            <label className="text-[11px] text-muted-foreground flex justify-between mb-1">
              <span>Activity Weight</span>
              <span className="font-semibold text-foreground">{weightActivity}%</span>
            </label>
            <input
              type="number"
              min={0}
              max={100}
              value={weightActivity}
              onChange={(e) => onChange("weight_activity", Math.max(0, Number(e.target.value)))}
              className="w-full rounded-lg bg-background border border-border px-2.5 py-1.5 text-xs text-foreground focus:outline-none focus:border-indigo-600"
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function PushToCRMConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  const crmProvider = data.provider || data.crm || "HubSpot";
  const stage = data.pipeline_stage || data.stage || "";

  const handleProviderSelect = (p: string) => {
    onChange("provider", p);
    onChange("crm", p);
  };

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Pacing Delay</label>
        <DelaySelector
          value={data.delay !== undefined ? data.delay : 0}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }}
        />
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Target CRM</label>
        <div className="grid grid-cols-2 gap-2">
          {["HubSpot", "Salesforce", "Pipedrive", "Notion", "Airtable"].map(crm => (
            <button
              key={crm}
              type="button"
              onClick={() => handleProviderSelect(crm)}
              className={cn(
                "py-2 px-3 rounded-xl border text-xs font-medium transition-all text-center flex items-center justify-center gap-2",
                crmProvider.toLowerCase() === crm.toLowerCase()
                  ? "bg-sky-500/10 border-sky-500 text-sky-500 font-semibold shadow-xs"
                  : "bg-card border-border hover:bg-muted text-muted-foreground"
              )}
            >
              <Database size={13} />
              <span>{crm}</span>
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          Pipeline Stage / Deal Stage <span className="text-muted-foreground font-normal">(optional)</span>
        </label>
        <input
          value={stage}
          onChange={e => { onChange("pipeline_stage", e.target.value); onChange("stage", e.target.value); }}
          placeholder="e.g. Lead, In Outreach, Meeting Booked, SQL"
          className="w-full rounded-lg bg-card border border-border px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
      </div>

      <div className="p-3.5 rounded-xl bg-sky-50/80 dark:bg-sky-950/30 border border-sky-200 dark:border-sky-800/40 space-y-1">
        <p className="text-xs font-semibold text-sky-800 dark:text-sky-300">
          Bidirectional Data Sync
        </p>
        <p className="text-[11px] text-sky-700/80 dark:text-sky-400 leading-relaxed">
          Syncs lead contact details, campaign tags, and sequence milestone timestamps directly to your CRM.
        </p>
      </div>
    </div>
  );
}

function EmailSequencerConfig({ data, onChange, defaultProvider }: { data: any; onChange: (k: string, v: any) => void; defaultProvider?: string }) {
  const provider = data.provider || data.sequencer || defaultProvider || "Smartlead";
  const campaignId = data.campaign_id || data.sequence_id || data.sequencer_campaign_id || "";

  const handleProviderSelect = (p: string) => {
    onChange("provider", p);
    onChange("sequencer", p);
  };

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Pacing Delay</label>
        <DelaySelector
          value={data.delay !== undefined ? data.delay : 0}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }}
        />
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Cold Email Platform</label>
        <div className="grid grid-cols-3 gap-2">
          {["Smartlead", "Instantly", "EmailBison", "Lemlist", "Apollo"].map(p => (
            <button
              key={p}
              type="button"
              onClick={() => handleProviderSelect(p)}
              className={cn(
                "py-2 px-2.5 rounded-xl border text-xs font-medium transition-all text-center",
                provider.toLowerCase() === p.toLowerCase()
                  ? "bg-pink-500/10 border-pink-500 text-pink-500 font-semibold shadow-xs"
                  : "bg-card border-border hover:bg-muted text-muted-foreground"
              )}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          {provider} Campaign / Sequence ID
        </label>
        <input
          value={campaignId}
          onChange={e => {
            onChange("campaign_id", e.target.value);
            onChange("sequence_id", e.target.value);
            onChange("sequencer_campaign_id", e.target.value);
          }}
          placeholder={`Enter your ${provider} campaign UUID or ID`}
          className="w-full rounded-lg bg-card border border-border px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
        <p className="text-[10px] text-muted-foreground mt-1">
          Found in your {provider} dashboard URL or campaign settings.
        </p>
      </div>

      <div className="p-3.5 rounded-xl bg-amber-50/80 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/40 space-y-1">
        <p className="text-xs font-semibold text-amber-800 dark:text-amber-300">
          Verified Email Required
        </p>
        <p className="text-[11px] text-amber-700/80 dark:text-amber-400 leading-relaxed">
          {provider} requires a valid email. Make sure an email enrichment step (e.g. <em>Find Email</em>) runs before this node.
        </p>
      </div>
    </div>
  );
}

function MultichannelConfig({ data, onChange, platform }: { data: any; onChange: (k: string, v: any) => void; platform: string }) {
  return <EmailSequencerConfig data={data} onChange={onChange} defaultProvider={platform} />;
}

function SendSlackAlertConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  const channel = data.channel || "";
  const webhookUrl = data.webhook_url || "";
  const message = data.message || "{{first_name}} from {{company}} replied to your sequence.";

  const presets = [
    { label: "Hot Reply", text: "Priority Reply: {{first_name}} from {{company}} replied to your sequence." },
    { label: "Meeting Booked", text: "Meeting Booked: {{first_name}} booked a demo call." },
    { label: "Connection Accepted", text: "{{first_name}} from {{company}} accepted your connection request." },
  ];

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Pacing Delay</label>
        <DelaySelector
          value={data.delay !== undefined ? data.delay : 0}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }}
        />
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">Slack Channel</label>
        <input
          value={channel}
          onChange={e => onChange("channel", e.target.value)}
          placeholder="#sales-signals or #outreach-alerts"
          className="w-full rounded-lg bg-card border border-border px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          Webhook URL Override <span className="text-muted-foreground font-normal">(optional)</span>
        </label>
        <input
          value={webhookUrl}
          onChange={e => onChange("webhook_url", e.target.value)}
          placeholder="https://hooks.slack.com/services/... (defaults to workspace Slack)"
          className="w-full rounded-lg bg-card border border-border px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
      </div>

      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-xs font-semibold text-foreground">Alert Message</label>
          <span className="text-[10px] text-muted-foreground">{message.length}/500</span>
        </div>
        <textarea
          value={message}
          onChange={e => onChange("message", e.target.value)}
          rows={3}
          maxLength={500}
          placeholder="Enter notification text..."
          className="w-full rounded-xl bg-card border border-border px-3.5 py-3 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none"
        />
        <div className="flex flex-wrap gap-1 mt-1.5">
          {["first_name", "company", "title"].map(v => (
            <button
              key={v}
              type="button"
              onClick={() => onChange("message", message + ` {{${v}}}`)}
              className="text-[10px] px-1.5 py-0.5 rounded bg-muted/60 hover:bg-muted text-muted-foreground hover:text-foreground border border-border/40 transition-colors"
            >
              + {`{{${v}}}`}
            </button>
          ))}
        </div>
        <NakedVariableWarning text={message} />
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">Quick Presets</label>
        <div className="flex flex-wrap gap-1.5">
          {presets.map(p => (
            <button
              key={p.label}
              type="button"
              onClick={() => onChange("message", p.text)}
              className="text-xs px-2.5 py-1 rounded-lg border border-border bg-card hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function SendWebhookConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  const url = data.url || data.webhook_url || "";
  const method = data.method || "POST";
  const authHeader = data.auth_header || "";
  const payloadTemplate = data.payload_template || '{"first_name": "{{first_name}}", "company": "{{company}}", "linkedin_url": "{{linkedin_url}}"}';

  const isUrlValid = !url || url.startsWith("http://") || url.startsWith("https://");

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Pacing Delay</label>
        <DelaySelector
          value={data.delay !== undefined ? data.delay : 0}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }}
        />
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">Webhook Destination URL</label>
        <input
          value={url}
          onChange={e => { onChange("url", e.target.value); onChange("webhook_url", e.target.value); }}
          placeholder="https://hooks.zapier.com/hooks/catch/... or custom API"
          className={cn(
            "w-full rounded-lg bg-card border px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none",
            isUrlValid ? "border-border focus:border-indigo-600" : "border-destructive focus:border-destructive"
          )}
        />
        {!isUrlValid && (
          <p className="text-[10px] text-destructive mt-1 font-medium">
            URL must start with http:// or https://
          </p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">HTTP Method</label>
          <Select
            value={method}
            onValueChange={val => onChange("method", val)}
          >
            <SelectTrigger className="w-full bg-card border-border text-xs h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="POST">POST</SelectItem>
              <SelectItem value="PUT">PUT</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">
            Authorization Header <span className="text-muted-foreground font-normal">(optional)</span>
          </label>
          <input
            value={authHeader}
            onChange={e => onChange("auth_header", e.target.value)}
            placeholder="Bearer token_xyz"
            className="w-full rounded-lg bg-card border border-border px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
          />
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-xs font-semibold text-foreground">JSON Payload Template</label>
          <span className="text-[10px] text-muted-foreground">Interpolates lead variables</span>
        </div>
        <textarea
          value={payloadTemplate}
          onChange={e => onChange("payload_template", e.target.value)}
          rows={5}
          placeholder='{"name": "{{first_name}}", "company": "{{company}}"}'
          className="w-full rounded-xl bg-card border border-border font-mono text-[11px] px-3.5 py-3 text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none"
        />
        <div className="flex flex-wrap gap-1 mt-1.5">
          {["first_name", "last_name", "company", "title", "email", "linkedin_url"].map(v => (
            <button
              key={v}
              type="button"
              onClick={() => onChange("payload_template", payloadTemplate + ` "{{${v}}}"`)}
              className="text-[10px] px-1.5 py-0.5 rounded bg-muted/60 hover:bg-muted text-muted-foreground hover:text-foreground border border-border/40 transition-colors"
            >
              + {`{{${v}}}`}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function SendVoiceNoteConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  const [errorMsg, setErrorMsg] = useState("");
  const [warningMsg, setWarningMsg] = useState("");
  const [isValid, setIsValid] = useState(Boolean(data.audio_url));
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const validateUrl = async (url: string) => {
    setErrorMsg("");
    setWarningMsg("");
    setIsValid(false);

    if (!url) return;

    if (
      !url.startsWith("https://") &&
      !url.startsWith("http://") &&
      !url.startsWith("/api/")
    ) {
      setErrorMsg("Must be a direct audio link (https://, http://, or uploaded /api/ path).");
      return;
    }

    const validExts = [".mp3", ".mp4", ".wav", ".ogg", ".m4a", ".webm"];
    const validCDNs = ["drive.google.com", "dropbox.com", "loom.com"];
    
    let hasValidExt = false;
    try {
      const parsedUrl = new URL(url.startsWith("/") ? `http://localhost${url}` : url);
      hasValidExt = validExts.some(ext => parsedUrl.pathname.toLowerCase().endsWith(ext));
    } catch {
      const lowerUrl = url.toLowerCase();
      hasValidExt = validExts.some(ext => lowerUrl.endsWith(ext) || lowerUrl.includes(ext + "?"));
    }
    
    const lowerUrl = url.toLowerCase();
    const hasValidCDN = validCDNs.some(cdn => lowerUrl.includes(cdn));

    if (!hasValidExt && !hasValidCDN && !url.startsWith("/api/")) {
      setWarningMsg("Audio URL does not end in a common audio extension (.mp3, .wav). Verify it is a direct streamable file.");
    }

    setIsValid(true);

    if (url.startsWith("https://") || url.startsWith("http://")) {
      try {
        await fetch(url, { method: "HEAD", mode: "no-cors" });
      } catch {
        setWarningMsg("Could not verify this external URL is reachable. Double-check before launching.");
        setIsValid(false);
      }
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const validExts = [".mp3", ".wav", ".m4a", ".ogg", ".aac", ".webm", ".mp4"];
    const ext = "." + (file.name.split(".").pop() || "").toLowerCase();
    if (!validExts.includes(ext) && !file.type.includes("audio")) {
      setErrorMsg(`Unsupported file type. Please upload an audio file (${validExts.join(", ")}).`);
      return;
    }

    if (file.size > 25 * 1024 * 1024) {
      setErrorMsg("Audio file size cannot exceed 25MB.");
      return;
    }

    setIsUploading(true);
    setErrorMsg("");
    setWarningMsg("");

    try {
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetchWithAuth("/api/elein/campaigns/upload_audio", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => null);
        const detail = errData?.detail || `Upload failed with status ${res.status}`;
        throw new Error(detail);
      }

      const payload = await res.json();
      const uploadedUrl = payload.url || "";
      onChange("audio_url", uploadedUrl);
      onChange("audio_filename", payload.filename || file.name);
      setIsValid(true);
      toast.success("Voice note uploaded and ready!");
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to upload audio file. Please check connection.");
      setIsValid(false);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const companionNote = data.note ?? data.body ?? "";

  const insertVariable = (varName: string) => {
    const next = companionNote ? `${companionNote} {{${varName}}}` : `Hey {{${varName}}}, `;
    onChange("note", next);
    onChange("body", next);
  };

  return (
    <div className="space-y-6">
      {/* Prerequisite & Compatibility Banner */}
      <div className="p-3.5 rounded-xl bg-amber-500/10 dark:bg-amber-950/30 border border-amber-500/30 dark:border-amber-600/40 flex items-start gap-2.5">
        <AlertTriangle size={16} className="text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
        <div className="space-y-1">
          <span className="text-xs font-semibold text-amber-900 dark:text-amber-200 block">
            Requires 1st-Degree Connection
          </span>
          <p className="text-[11px] text-amber-800/90 dark:text-amber-300/80 leading-relaxed">
            LinkedIn only supports audio voice notes in direct messages with existing connections. If a lead has not connected yet, enable the auto-fallback below to send a connection request instead.
          </p>
        </div>
      </div>

      {/* Auto-Fallback Checkbox (Paranoia Layer 1 & 2) */}
      <div className="p-3 rounded-xl bg-card border border-border flex items-start gap-3">
        <input
          id="fallback_to_connection_request"
          type="checkbox"
          checked={data.fallback_to_connection_request !== false}
          onChange={e => onChange("fallback_to_connection_request", e.target.checked)}
          className="mt-0.5 h-4 w-4 rounded border-border text-indigo-600 focus:ring-indigo-500 cursor-pointer"
        />
        <label htmlFor="fallback_to_connection_request" className="cursor-pointer select-none space-y-0.5">
          <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            Auto-fallback to Connection Request
            <span className="text-[10px] font-medium px-1.5 py-0.2 rounded bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30">
              Recommended
            </span>
          </span>
          <p className="text-[11px] text-muted-foreground leading-relaxed">
            If the lead is not connected (message modal absent), automatically dispatch a Connection Request with the accompanying note instead of failing the action.
          </p>
        </label>
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Delay</label>
        <DelaySelector value={data.delay} unit={data.delayUnit || "days"} onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }} />
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <label className="block text-xs font-semibold text-foreground flex items-center gap-1.5">
            <Volume2 size={13} className="text-indigo-500" />
            <span>Audio Voice File</span>
          </label>
          <div className="flex items-center gap-2">
            <input 
              ref={fileInputRef} 
              type="file" 
              accept="audio/*,.mp3,.wav,.m4a,.ogg,.aac,.webm,.mp4" 
              className="hidden" 
              onChange={handleFileUpload} 
            />
            <button
              type="button"
              disabled={isUploading}
              onClick={() => fileInputRef.current?.click()}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-indigo-50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 hover:bg-indigo-100 dark:hover:bg-indigo-900/60 text-[11px] font-medium border border-indigo-200/80 dark:border-indigo-800/60 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isUploading ? (
                <>
                  <Loader2 size={11} className="animate-spin" />
                  <span>Uploading...</span>
                </>
              ) : (
                <>
                  <Upload size={11} />
                  <span>Upload audio</span>
                </>
              )}
            </button>
            {isValid && !warningMsg && !errorMsg && <CheckCircle2 size={14} className="text-emerald-500" />}
          </div>
        </div>

        <input 
          value={data.audio_url || ""} 
          onChange={e => {
            onChange("audio_url", e.target.value);
            setErrorMsg("");
            setWarningMsg("");
            setIsValid(false);
          }}
          onBlur={(e) => validateUrl(e.target.value)}
          placeholder="https://... (mp3, wav, max 5min) or click Upload"
          className="w-full rounded-lg bg-card border border-border px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 font-mono text-[11px]" 
        />

        {errorMsg && <p className="text-rose-600 dark:text-rose-400 text-[10px] mt-1 font-medium">{errorMsg}</p>}
        {warningMsg && <p className="text-amber-600 dark:text-amber-400 text-[10px] mt-1 font-medium">{warningMsg}</p>}

        {/* Audio Player Preview */}
        {data.audio_url && (
          <div className="p-3 rounded-xl bg-card border border-border/80 shadow-xs flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold text-foreground flex items-center gap-1.5">
                <Volume2 size={12} className="text-indigo-500" />
                Audio Preview {data.audio_filename && <span className="font-normal text-muted-foreground truncate max-w-[150px]">({data.audio_filename})</span>}
              </span>
              <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-medium">Ready to play</span>
            </div>
            <audio 
              controls 
              preload="metadata" 
              src={data.audio_url} 
              className="w-full h-8 rounded"
              onError={() => {
                if (!errorMsg) setWarningMsg("Browser audio preview could not decode stream. Ensure file is accessible.");
              }}
            />
          </div>
        )}
      </div>

      {/* Companion Message Note */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="block text-xs font-semibold text-foreground">
            Accompanying note <span className="text-muted-foreground font-normal">(optional)</span>
          </label>
          <span className="text-[10px] text-muted-foreground">{companionNote.length}/500</span>
        </div>
        <textarea
          rows={3}
          maxLength={500}
          value={companionNote}
          onChange={e => {
            onChange("note", e.target.value);
            onChange("body", e.target.value);
          }}
          placeholder="e.g. Hey {{first_name}}, recorded a quick voice memo for you above!"
          className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none leading-relaxed"
        />
        <div className="flex items-center justify-between mt-1 text-[10px] text-muted-foreground">
          <span>Sent alongside voice note or used in fallback request.</span>
          <div className="flex items-center gap-1 flex-wrap justify-end">
            {["first_name", "company", "title", "location"].map((varKey) => (
              <button
                key={varKey}
                type="button"
                onClick={() => insertVariable(varKey)}
                className="text-[10px] px-1.5 py-0.5 rounded bg-muted hover:bg-muted/80 text-foreground transition-colors cursor-pointer"
              >
                + {`{{${varKey}}}`}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="p-3.5 rounded-xl bg-indigo-50/90 dark:bg-indigo-950/35 border border-indigo-200/90 dark:border-indigo-800/50 flex items-start gap-2.5 shadow-xs">
        <AlertTriangle size={14} className="text-sm shrink-0 mt-0.5 text-amber-500" />
        <p className="text-xs text-indigo-900 dark:text-indigo-200 leading-relaxed font-medium">
          Voice notes produce <strong className="font-bold underline decoration-indigo-300 dark:decoration-indigo-600">3× higher reply rates</strong> than text messages. Pre-record a personal 45-60 second intro and upload it above.
        </p>
      </div>
    </div>
  );
}

// ─── AI Intelligence & Data Enrichment Node Configs ──────────────────────────

interface AIScoreICPConfigProps {
  data: any;
  onChange: (key: string, value: any) => void;
}

export function AIScoreICPConfig({ data, onChange }: AIScoreICPConfigProps) {
  const { openPaywall } = usePaywall();
  const { data: billing } = useSWR<any>('/api/elein/workspaces/billing', fetcher);
  const isIcpLocked = Boolean(billing && !billing.tier_limits?.can_use_bayesian_icp);

  const icpDesc = data.icp_description || "";
  const aiModel = data.ai_model || "Auto-Route (Recommended)";
  const [showAdvanced, setShowAdvanced] = useState(false);

  const AI_MODELS = [
    "Auto-Route (Recommended)",
    "DeepSeek V4 Pro",
    "GPT-OS",
    "Kimi k3",
    "Llama-3.2 11B",
    "Nemotron 120B",
  ];

  return (
    <div className="space-y-6">
      <div className="p-4 rounded-xl bg-card border border-border space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ElesiumLogo size={14} />
            <span className="text-xs font-bold text-foreground">AI Ideal Customer Profile Scoring</span>
          </div>
          <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-orange-500/10 text-orange-600 dark:text-orange-400 border border-orange-500/20">
            1 Credit
          </span>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          AI evaluates lead title, company size, industry, and headline against your ICP description, routing the lead into 3 discrete decision paths:
        </p>
        <div className="grid grid-cols-3 gap-2 pt-1">
          <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-center">
            <span className="block text-[11px] font-bold text-emerald-600 dark:text-emerald-400">High fit</span>
            <span className="text-[10px] text-muted-foreground">&gt; 75 points</span>
          </div>
          <div className="p-2 rounded-lg bg-amber-500/10 border border-amber-500/20 text-center">
            <span className="block text-[11px] font-bold text-amber-600 dark:text-amber-400">Medium fit</span>
            <span className="text-[10px] text-muted-foreground">50 - 75 points</span>
          </div>
          <div className="p-2 rounded-lg bg-rose-500/10 border border-rose-500/20 text-center">
            <span className="block text-[11px] font-bold text-rose-600 dark:text-rose-400">Low fit</span>
            <span className="text-[10px] text-muted-foreground">&lt; 50 points</span>
          </div>
        </div>
      </div>

      {/* In-Situ Pay Ramp: Bayesian Prior Calibration */}
      <div className={cn(
        "p-3.5 rounded-xl border flex items-center justify-between gap-3 text-xs",
        isIcpLocked 
          ? "bg-amber-500/5 border-amber-500/25" 
          : "bg-indigo-500/5 border-indigo-500/20"
      )}>
        <div className="flex items-center gap-2.5">
          <div className={cn("p-1.5 rounded-lg shrink-0", isIcpLocked ? "bg-amber-500/10 text-amber-500" : "bg-indigo-500/10 text-indigo-400")}>
            <Cpu size={14} />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="font-bold text-foreground">Continuous Bayesian Prior Calibration</span>
              {isIcpLocked ? (
                <span className="px-1.5 py-0.2 rounded bg-amber-400 text-slate-950 text-[9px] font-black tracking-wide">
                  PRO
                </span>
              ) : (
                <span className="px-1.5 py-0.2 rounded bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 text-[9px] font-bold border border-emerald-500/30">
                  ACTIVE
                </span>
              )}
            </div>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              {isIcpLocked 
                ? "Free tier runs static 50% prior weights. Growth Pro dynamically updates weights via won/lost signals."
                : "Active Beta-Binomial learning dynamically calibrates decision maker and firmographic weights."
              }
            </p>
          </div>
        </div>
        {isIcpLocked && (
          <button
            type="button"
            onClick={() => openPaywall({ featureName: "Bayesian ICP Machine Learning" })}
            className="px-2.5 py-1 text-[11px] font-bold rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 shrink-0 transition-colors flex items-center gap-1 cursor-pointer"
          >
            <span>Unlock</span>
            <ArrowUpRight size={12} />
          </button>
        )}
      </div>

      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="block text-xs font-semibold text-foreground">
            Target Customer Profile Criteria
          </label>
          <span className="text-[10px] text-muted-foreground">{icpDesc.length}/500</span>
        </div>
        <textarea
          rows={4}
          maxLength={500}
          value={icpDesc}
          onChange={e => onChange("icp_description", e.target.value)}
          placeholder="e.g., B2B SaaS Founders, VPs of Sales, and Growth Directors at tech companies between 20 and 200 employees currently scaling outbound sales..."
          className="w-full rounded-xl bg-card border border-border px-3.5 py-3 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none leading-relaxed"
        />
        <div className="flex items-center gap-1.5 flex-wrap mt-2">
          <span className="text-[10px] text-muted-foreground">Quick ICP inserts:</span>
          {["B2B SaaS, 20-200 HC", "Series A/B Founders", "Sales Leaders", "FinTech / DevTools"].map(preset => (
            <button
              key={preset}
              type="button"
              onClick={() => {
                const combined = icpDesc ? `${icpDesc}, ${preset}` : preset;
                onChange("icp_description", combined.slice(0, 500));
              }}
              className="text-[10px] px-2 py-0.5 rounded-full bg-muted hover:bg-muted/80 text-foreground transition-colors cursor-pointer border border-border/50"
            >
              + {preset}
            </button>
          ))}
        </div>
      </div>

      <AIModelSelector
        value={aiModel}
        onChange={(m) => onChange("ai_model", m)}
        models={AI_MODELS}
        label="AI Routing Engine (Model)"
      />

      <div className="border border-border/60 rounded-xl overflow-hidden bg-card/50">
        <button
          type="button"
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="w-full flex items-center justify-between px-3.5 py-2.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
        >
          <span>Advanced Prompt & Persona Overrides</span>
          <ChevronDown size={14} className={cn("transition-transform", showAdvanced && "rotate-180")} />
        </button>
        {showAdvanced && (
          <div className="p-3.5 pt-1 space-y-3 border-t border-border/50">
            <div>
              <label className="block text-[11px] font-medium text-foreground mb-1">Custom Persona Override</label>
              <textarea
                rows={2}
                value={data.custom_persona || ""}
                onChange={e => onChange("custom_persona", e.target.value)}
                placeholder="e.g., You are an enterprise account executive evaluating buyer urgency..."
                className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none"
              />
            </div>
            <div>
              <label className="block text-[11px] font-medium text-foreground mb-1">Custom Scoring Rules</label>
              <textarea
                rows={2}
                value={data.custom_rules || ""}
                onChange={e => onChange("custom_rules", e.target.value)}
                placeholder="e.g., Penalize companies outside North America by 30 points..."
                className="w-full rounded-lg bg-card border border-border px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none"
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

interface AIBuyingSignalConfigProps {
  data: any;
  onChange: (key: string, value: any) => void;
}

export function AIBuyingSignalConfig({ data, onChange }: AIBuyingSignalConfigProps) {
  const signalKeywords = data.signal_keywords || "";

  const PRESETS = [
    "Hiring SDRs / Sales",
    "Raised Seed / Series A",
    "Expanding to US",
    "Switching Outreach Tool",
    "Complaining About Deliverability",
    "New Leadership Role",
  ];

  return (
    <div className="space-y-6">
      <div className="p-4 rounded-xl bg-card border border-border space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ElesiumLogo size={14} />
            <span className="text-xs font-bold text-foreground">AI Buying Signal Detection</span>
          </div>
          <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-orange-500/10 text-orange-600 dark:text-orange-400 border border-orange-500/20">
            1 Credit
          </span>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          AI scans the prospect's recent LinkedIn posts and headline for high-intent pain points and trigger events, routing along 2 distinct branches:
        </p>
        <div className="grid grid-cols-2 gap-2 pt-1">
          <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-center">
            <span className="block text-xs font-bold text-emerald-600 dark:text-emerald-400">Signal detected</span>
            <span className="text-[10px] text-muted-foreground">High intent trigger</span>
          </div>
          <div className="p-2.5 rounded-lg bg-zinc-500/10 border border-zinc-500/20 text-center">
            <span className="block text-xs font-bold text-muted-foreground">No signal</span>
            <span className="text-[10px] text-muted-foreground">Standard nurture</span>
          </div>
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="block text-xs font-semibold text-foreground">
            Target Signal Topics & Pain Points
          </label>
          <span className="text-[10px] text-muted-foreground">{signalKeywords.length}/300</span>
        </div>
        <textarea
          rows={3}
          maxLength={300}
          value={signalKeywords}
          onChange={e => onChange("signal_keywords", e.target.value)}
          placeholder="e.g., hiring SDRs, pipeline generation, scaling outbound, outbound deliverability, missed quota..."
          className="w-full rounded-xl bg-card border border-border px-3.5 py-3 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none leading-relaxed"
        />
        <div className="flex items-center gap-1.5 flex-wrap mt-2">
          <span className="text-[10px] text-muted-foreground">Click to add signal:</span>
          {PRESETS.map(p => (
            <button
              key={p}
              type="button"
              onClick={() => {
                const combined = signalKeywords ? `${signalKeywords}, ${p}` : p;
                onChange("signal_keywords", combined.slice(0, 300));
              }}
              className="text-[10px] px-2 py-0.5 rounded-full bg-muted hover:bg-muted/80 text-foreground transition-colors cursor-pointer border border-border/50"
            >
              + {p}
            </button>
          ))}
        </div>
      </div>

      <div className="p-3.5 rounded-xl bg-orange-50/80 dark:bg-orange-950/20 border border-orange-200 dark:border-orange-900/30">
        <p className="text-xs text-orange-800 dark:text-orange-300 font-medium">
          <strong>Pro Tip:</strong> Route leads from the <em>"Signal detected"</em> branch directly to a Slack Alert or priority InMail for 4× faster sales response.
        </p>
      </div>
    </div>
  );
}

interface AIDetectCompetitorConfigProps {
  data: any;
  onChange: (key: string, value: any) => void;
}

export function AIDetectCompetitorConfig({ data, onChange }: AIDetectCompetitorConfigProps) {
  const competitors = data.competitors || "";

  const COMPETITOR_PRESETS = [
    "Lemlist", "Apollo", "Salesloft", "Outreach", "HeyReach", "Expandi", "Instantly", "Smartlead"
  ];

  return (
    <div className="space-y-6">
      <div className="p-4 rounded-xl bg-card border border-border space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ElesiumLogo size={14} />
            <span className="text-xs font-bold text-foreground">AI Competitor Detection</span>
          </div>
          <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-orange-500/10 text-orange-600 dark:text-orange-400 border border-orange-500/20">
            1 Credit
          </span>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Checks if the prospect or their company mentions or uses a competitor product. Routes between:
        </p>
        <div className="grid grid-cols-2 gap-2 pt-1">
          <div className="p-2.5 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-center">
            <span className="block text-xs font-bold text-indigo-600 dark:text-indigo-400">Using competitor</span>
            <span className="text-[10px] text-muted-foreground">Switch campaign track</span>
          </div>
          <div className="p-2.5 rounded-lg bg-zinc-500/10 border border-zinc-500/20 text-center">
            <span className="block text-xs font-bold text-muted-foreground">Not detected</span>
            <span className="text-[10px] text-muted-foreground">Standard value track</span>
          </div>
        </div>
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          Competitor Names (comma-separated)
        </label>
        <input
          type="text"
          value={competitors}
          onChange={e => onChange("competitors", e.target.value)}
          placeholder="e.g. Lemlist, Apollo, Outreach, Salesloft"
          className="w-full rounded-lg bg-card border border-border px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
        <div className="flex items-center gap-1.5 flex-wrap mt-2">
          <span className="text-[10px] text-muted-foreground">Quick competitor presets:</span>
          {COMPETITOR_PRESETS.map(comp => (
            <button
              key={comp}
              type="button"
              onClick={() => {
                const existing = competitors.split(",").map((s: string) => s.trim()).filter(Boolean);
                if (!existing.includes(comp)) {
                  onChange("competitors", [...existing, comp].join(", "));
                }
              }}
              className="text-[10px] px-2 py-0.5 rounded-full bg-muted hover:bg-muted/80 text-foreground transition-colors cursor-pointer border border-border/50"
            >
              + {comp}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

interface AISummarizeProfileConfigProps {
  data: any;
  onChange: (key: string, value: any) => void;
}

export function AISummarizeProfileConfig({ data, onChange }: AISummarizeProfileConfigProps) {
  const focus = data.summary_focus || "Comprehensive Intel Card";
  const syncCRM = data.sync_to_crm !== false;

  const FOCUS_OPTIONS = [
    "Comprehensive Intel Card",
    "Recent Career Moves & Accomplishments",
    "Pain Points & Expressed Interests",
    "Executive Leadership & Team Size",
  ];

  return (
    <div className="space-y-6">
      <div className="p-4 rounded-xl bg-card border border-border space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ElesiumLogo size={14} />
            <span className="text-xs font-bold text-foreground">AI Profile Executive Summary</span>
          </div>
          <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-orange-500/10 text-orange-600 dark:text-orange-400 border border-orange-500/20">
            1 Credit
          </span>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Distills the lead's bio, tenure, and posts into an executive intel brief. Stored in sequence variables as <code className="text-[11px] font-mono text-foreground font-semibold">{"{{profile_summary}}"}</code>.
        </p>
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          Summary Focus Lens
        </label>
        <Select
          value={focus}
          onValueChange={val => onChange("summary_focus", val)}
        >
          <SelectTrigger className="w-full bg-card border-border text-xs h-9">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {FOCUS_OPTIONS.map(opt => (
              <SelectItem key={opt} value={opt}>{opt}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="p-3.5 rounded-xl bg-muted/40 border border-border flex items-center justify-between">
        <div>
          <span className="text-xs font-semibold text-foreground block">Auto-Sync Intel to CRM</span>
          <span className="text-[10px] text-muted-foreground">Attach generated summary to CRM lead notes</span>
        </div>
        <input
          type="checkbox"
          checked={syncCRM}
          onChange={e => onChange("sync_to_crm", e.target.checked)}
          className="w-4 h-4 rounded text-indigo-600 focus:ring-indigo-500 border-border cursor-pointer"
        />
      </div>
    </div>
  );
}

interface AIBestSendTimeConfigProps {
  data: any;
  onChange: (key: string, value: any) => void;
}

export function AIBestSendTimeConfig({ data, onChange }: AIBestSendTimeConfigProps) {
  const maxWait = data.max_wait_hours ?? 24;

  return (
    <div className="space-y-6">
      <div className="p-4 rounded-xl bg-card border border-border space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ElesiumLogo size={14} />
            <span className="text-xs font-bold text-foreground">AI Optimal Send Time Prediction</span>
          </div>
          <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-orange-500/10 text-orange-600 dark:text-orange-400 border border-orange-500/20">
            1 Credit
          </span>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Analyzes the lead's historical posting hours, local timezone, and online activity indicators to dispatch the message when they are most likely active.
        </p>
      </div>

      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="block text-xs font-semibold text-foreground">
            Maximum Wait Window (Hours)
          </label>
          <span className="text-xs font-mono font-bold text-foreground">{maxWait} hours</span>
        </div>
        <input
          type="range"
          min={1}
          max={72}
          value={maxWait}
          onChange={e => onChange("max_wait_hours", Number(e.target.value))}
          className="w-full accent-indigo-600 cursor-pointer"
        />
        <div className="flex justify-between text-[10px] text-muted-foreground mt-1">
          <span>1 hour</span>
          <span>24 hours (Default)</span>
          <span>72 hours</span>
        </div>
      </div>

      <div className="p-3.5 rounded-xl bg-indigo-50/80 dark:bg-indigo-950/20 border border-indigo-200 dark:border-indigo-900/30">
        <p className="text-xs text-indigo-800 dark:text-indigo-300 font-medium leading-relaxed">
          ⏱️ If no activity window is confirmed within <strong>{maxWait} hours</strong>, the sequence proceeds automatically to avoid stalling your campaign.
        </p>
      </div>
    </div>
  );
}

interface EnrichmentDiscoveryConfigProps {
  data: any;
  onChange: (key: string, value: any) => void;
  isPersonal?: boolean;
  isApollo?: boolean;
  isZeroCost?: boolean;
}

export function EnrichmentDiscoveryConfig({ data, onChange, isPersonal, isApollo, isZeroCost }: EnrichmentDiscoveryConfigProps) {
  const cost = isZeroCost ? 0 : 5;
  const title = isZeroCost 
    ? "Zero-Cost Email Discovery" 
    : isPersonal 
      ? "Find Personal Email" 
      : isApollo 
        ? "Apollo Direct Enrichment" 
        : "Find Work Email";

  return (
    <div className="space-y-6">
      <div className="p-4 rounded-xl bg-card border border-border space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AtSign size={14} className="text-amber-500" />
            <span className="text-xs font-bold text-foreground">{title}</span>
          </div>
          <span className={cn(
            "text-[10px] px-2 py-0.5 rounded-full font-bold border",
            isZeroCost 
              ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20"
              : "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20"
          )}>
            {cost} Credits
          </span>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          {isZeroCost
            ? "Generates permutation addresses and validates deliverability via zero-cost SMTP handshake without consuming third-party API credits."
            : isPersonal
              ? "Enriches personal email addresses for high-priority founder and decision-maker direct outreach."
              : isApollo
                ? "Directly matches lead against Apollo's global B2B contact database for verified company email and phone."
                : "Runs waterfall enrichment (Apollo → Hunter → Clearbit) to discover a verified business email."}
        </p>
        <div className="grid grid-cols-2 gap-2 pt-1">
          <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-center">
            <span className="block text-xs font-bold text-emerald-600 dark:text-emerald-400">Found</span>
            <span className="text-[10px] text-muted-foreground">Stores in {"{{email}}"}</span>
          </div>
          <div className="p-2.5 rounded-lg bg-zinc-500/10 border border-zinc-500/20 text-center">
            <span className="block text-xs font-bold text-muted-foreground">Not found</span>
            <span className="text-[10px] text-muted-foreground">Continue on LinkedIn</span>
          </div>
        </div>
      </div>

      <div className="p-3.5 rounded-xl bg-muted/40 border border-border flex items-center justify-between">
        <div>
          <span className="text-xs font-semibold text-foreground block">Verify MX Records</span>
          <span className="text-[10px] text-muted-foreground">Confirm destination mail server accepts incoming SMTP</span>
        </div>
        <input
          type="checkbox"
          checked={data.verify_mx !== false}
          onChange={e => onChange("verify_mx", e.target.checked)}
          className="w-4 h-4 rounded text-indigo-600 focus:ring-indigo-500 border-border cursor-pointer"
        />
      </div>
    </div>
  );
}

interface VerifyEmailConfigProps {
  data: any;
  onChange: (key: string, value: any) => void;
}

export function VerifyEmailConfig({ data, onChange }: VerifyEmailConfigProps) {
  return (
    <div className="space-y-6">
      <div className="p-4 rounded-xl bg-card border border-border space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle2 size={14} className="text-amber-500" />
            <span className="text-xs font-bold text-foreground">Verify Email Deliverability</span>
          </div>
          <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
            1 Credit
          </span>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Pings the lead's email server via ZeroBounce and raw SMTP handshake to ensure it will not hard-bounce. Essential before cold email handoffs.
        </p>
        <div className="grid grid-cols-2 gap-2 pt-1">
          <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-center">
            <span className="block text-xs font-bold text-emerald-600 dark:text-emerald-400">Valid</span>
            <span className="text-[10px] text-muted-foreground">Safe to email</span>
          </div>
          <div className="p-2.5 rounded-lg bg-rose-500/10 border border-rose-500/20 text-center">
            <span className="block text-xs font-bold text-rose-600 dark:text-rose-400">Invalid / Risky</span>
            <span className="text-[10px] text-muted-foreground">Bouncing or catch-all</span>
          </div>
        </div>
      </div>

      <div className="p-3.5 rounded-xl bg-amber-50/80 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-900/30">
        <p className="text-xs text-amber-800 dark:text-amber-300 font-medium leading-relaxed">
          <strong>Sender Reputation Protection:</strong> Leads routed to <em>"Invalid / Risky"</em> bypass email sequencers automatically, preventing your domain from landing in spam folders or blacklists.
        </p>
      </div>

      <div className="p-3.5 rounded-xl bg-muted/40 border border-border flex items-center justify-between">
        <div>
          <span className="text-xs font-semibold text-foreground block">Strict Catch-All Filter</span>
          <span className="text-[10px] text-muted-foreground">Treat unconfirmable catch-all domains as risky</span>
        </div>
        <input
          type="checkbox"
          checked={data.strict_catch_all ?? true}
          onChange={e => onChange("strict_catch_all", e.target.checked)}
          className="w-4 h-4 rounded text-indigo-600 focus:ring-indigo-500 border-border cursor-pointer"
        />
      </div>
    </div>
  );
}

interface FindPhoneConfigProps {
  data: any;
  onChange: (key: string, value: any) => void;
}

export function FindPhoneConfig({ data, onChange }: FindPhoneConfigProps) {
  return (
    <div className="space-y-6">
      <div className="p-4 rounded-xl bg-card border border-border space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Phone size={14} className="text-amber-500" />
            <span className="text-xs font-bold text-foreground">Find Direct Dial & Mobile</span>
          </div>
          <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
            1 Credit
          </span>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Enriches verified mobile or direct-dial phone numbers via Apollo and People Data Labs. Perfect for warm cold calls or WhatsApp outreach.
        </p>
        <div className="grid grid-cols-2 gap-2 pt-1">
          <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-center">
            <span className="block text-xs font-bold text-emerald-600 dark:text-emerald-400">Found</span>
            <span className="text-[10px] text-muted-foreground">Stores in {"{{phone}}"}</span>
          </div>
          <div className="p-2.5 rounded-lg bg-zinc-500/10 border border-zinc-500/20 text-center">
            <span className="block text-xs font-bold text-muted-foreground">Not found</span>
            <span className="text-[10px] text-muted-foreground">Continue on LinkedIn</span>
          </div>
        </div>
      </div>

      <div className="p-3.5 rounded-xl bg-muted/40 border border-border flex items-center justify-between">
        <div>
          <span className="text-xs font-semibold text-foreground block">Mobile First</span>
          <span className="text-[10px] text-muted-foreground">Prioritize mobile numbers over corporate switchboards</span>
        </div>
        <input
          type="checkbox"
          checked={data.prefer_mobile ?? true}
          onChange={e => onChange("prefer_mobile", e.target.checked)}
          className="w-4 h-4 rounded text-indigo-600 focus:ring-indigo-500 border-border cursor-pointer"
        />
      </div>
    </div>
  );
}

interface FindTechStackConfigProps {
  data: any;
  onChange: (key: string, value: any) => void;
}

export function FindTechStackConfig({ data, onChange }: FindTechStackConfigProps) {
  return (
    <div className="space-y-6">
      <div className="p-4 rounded-xl bg-card border border-border space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Cpu size={14} className="text-amber-500" />
            <span className="text-xs font-bold text-foreground">Find Company Tech Stack</span>
          </div>
          <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
            Enrichment
          </span>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Detects software, frameworks, and tools used by the lead's company (e.g., Salesforce, HubSpot, Stripe, React). Use for competitive displacement or tailored tech pitches.
        </p>
        <div className="grid grid-cols-2 gap-2 pt-1">
          <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-center">
            <span className="block text-xs font-bold text-emerald-600 dark:text-emerald-400">Found</span>
            <span className="text-[10px] text-muted-foreground">Matches target tools</span>
          </div>
          <div className="p-2.5 rounded-lg bg-zinc-500/10 border border-zinc-500/20 text-center">
            <span className="block text-xs font-bold text-muted-foreground">Not found</span>
            <span className="text-[10px] text-muted-foreground">No matching tech</span>
          </div>
        </div>
      </div>

      <div className="space-y-2">
        <label className="text-xs font-semibold text-foreground flex items-center justify-between">
          <span>Target Tools / Technologies (Optional)</span>
          <span className="text-[10px] text-muted-foreground">Comma-separated</span>
        </label>
        <input
          type="text"
          value={data.target_tools || ""}
          onChange={e => onChange("target_tools", e.target.value)}
          placeholder="e.g. Salesforce, HubSpot, Stripe, React, AWS"
          className="w-full text-xs px-3 py-2 rounded-xl bg-background border border-border focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none text-foreground placeholder:text-muted-foreground"
        />
        <p className="text-[10px] text-muted-foreground">
          Leave blank to discover all technologies, or specify target tools to branch on their presence.
        </p>
      </div>
    </div>
  );
}

interface FindFundingRoundConfigProps {
  data: any;
  onChange: (key: string, value: any) => void;
}

export function FindFundingRoundConfig({ data, onChange }: FindFundingRoundConfigProps) {
  return (
    <div className="space-y-6">
      <div className="p-4 rounded-xl bg-card border border-border space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <DollarSign size={14} className="text-amber-500" />
            <span className="text-xs font-bold text-foreground">Find Funding Round</span>
          </div>
          <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
            Firmographic
          </span>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Checks if the company has recently raised venture capital, seed, or growth rounds. Freshly funded companies have active budgets and aggressive growth goals.
        </p>
        <div className="grid grid-cols-2 gap-2 pt-1">
          <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-center">
            <span className="block text-xs font-bold text-emerald-600 dark:text-emerald-400">Recently funded</span>
            <span className="text-[10px] text-muted-foreground">Within cutoff window</span>
          </div>
          <div className="p-2.5 rounded-lg bg-zinc-500/10 border border-zinc-500/20 text-center">
            <span className="block text-xs font-bold text-muted-foreground">No recent funding</span>
            <span className="text-[10px] text-muted-foreground">Outside window</span>
          </div>
        </div>
      </div>

      <div className="space-y-2">
        <label className="text-xs font-semibold text-foreground flex items-center justify-between">
          <span>Recency Window (Months)</span>
          <span className="text-xs font-bold text-primary">{data.recency_months ?? 12} mo</span>
        </label>
        <input
          type="range"
          min="1"
          max="36"
          step="1"
          value={data.recency_months ?? 12}
          onChange={e => onChange("recency_months", Number(e.target.value))}
          className="w-full h-1.5 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
        />
        <div className="flex justify-between text-[10px] text-muted-foreground">
          <span>1 month</span>
          <span>12 months (Standard)</span>
          <span>36 months</span>
        </div>
      </div>
    </div>
  );
}

interface FindHeadcountConfigProps {
  data: any;
  onChange: (key: string, value: any) => void;
}

export function FindHeadcountConfig({ data, onChange }: FindHeadcountConfigProps) {
  return (
    <div className="space-y-6">
      <div className="p-4 rounded-xl bg-card border border-border space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Building2 size={14} className="text-amber-500" />
            <span className="text-xs font-bold text-foreground">Find Company Headcount</span>
          </div>
          <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
            Firmographic
          </span>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Retrieves exact verified employee headcount and company size tier from LinkedIn company page and data partners.
        </p>
        <div className="grid grid-cols-2 gap-2 pt-1">
          <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-center">
            <span className="block text-xs font-bold text-emerald-600 dark:text-emerald-400">Found</span>
            <span className="text-[10px] text-muted-foreground">Stores in {"{{headcount}}"}</span>
          </div>
          <div className="p-2.5 rounded-lg bg-zinc-500/10 border border-zinc-500/20 text-center">
            <span className="block text-xs font-bold text-muted-foreground">Not found</span>
            <span className="text-[10px] text-muted-foreground">Size unavailable</span>
          </div>
        </div>
      </div>

      <div className="p-3.5 rounded-xl bg-muted/40 border border-border">
        <span className="text-xs font-semibold text-foreground block">Downstream Recommendation</span>
        <span className="text-[10px] text-muted-foreground">
          Follow this node with an <strong>If Company Size?</strong> condition to route SMB vs Enterprise sequences.
        </span>
      </div>
    </div>
  );
}

interface FindJobPostingsConfigProps {
  data: any;
  onChange: (key: string, value: any) => void;
}

export function FindJobPostingsConfig({ data, onChange }: FindJobPostingsConfigProps) {
  return (
    <div className="space-y-6">
      <div className="p-4 rounded-xl bg-card border border-border space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Briefcase size={14} className="text-amber-500" />
            <span className="text-xs font-bold text-foreground">Find Open Job Postings</span>
          </div>
          <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
            Hiring Intent
          </span>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Scrapes active job listings at the lead's organization. Active hiring signals growth, new budget, and specific operational bottlenecks.
        </p>
        <div className="grid grid-cols-2 gap-2 pt-1">
          <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-center">
            <span className="block text-xs font-bold text-emerald-600 dark:text-emerald-400">Hiring</span>
            <span className="text-[10px] text-muted-foreground">Active openings</span>
          </div>
          <div className="p-2.5 rounded-lg bg-zinc-500/10 border border-zinc-500/20 text-center">
            <span className="block text-xs font-bold text-muted-foreground">Not hiring</span>
            <span className="text-[10px] text-muted-foreground">No matches</span>
          </div>
        </div>
      </div>

      <div className="space-y-2">
        <label className="text-xs font-semibold text-foreground flex items-center justify-between">
          <span>Role Keywords (Optional)</span>
          <span className="text-[10px] text-muted-foreground">e.g. Sales, Engineer</span>
        </label>
        <input
          type="text"
          value={data.role_filter || ""}
          onChange={e => onChange("role_filter", e.target.value)}
          placeholder="e.g. Account Executive, Software Engineer, SDR"
          className="w-full text-xs px-3 py-2 rounded-xl bg-background border border-border focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none text-foreground placeholder:text-muted-foreground"
        />
        <p className="text-[10px] text-muted-foreground">
          Leave blank to detect any open roles, or filter by department/title.
        </p>
      </div>
    </div>
  );
}

interface GetLinkedInActivityConfigProps {
  data: any;
  onChange: (key: string, value: any) => void;
}

export function GetLinkedInActivityConfig({ data, onChange }: GetLinkedInActivityConfigProps) {
  return (
    <div className="space-y-6">
      <div className="p-4 rounded-xl bg-card border border-border space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity size={14} className="text-amber-500" />
            <span className="text-xs font-bold text-foreground">LinkedIn Activity Score</span>
          </div>
          <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
            Engagement
          </span>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Analyzes the lead's posting frequency over the last 30 days. Directs active creators to LinkedIn messages and inactive profiles to cold email.
        </p>
        <div className="grid grid-cols-3 gap-2 pt-1">
          <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-center">
            <span className="block text-xs font-bold text-emerald-600 dark:text-emerald-400">Active</span>
            <span className="text-[9px] text-muted-foreground">&gt;4 posts/mo</span>
          </div>
          <div className="p-2 rounded-lg bg-amber-500/10 border border-amber-500/20 text-center">
            <span className="block text-xs font-bold text-amber-600 dark:text-amber-400">Passive</span>
            <span className="text-[9px] text-muted-foreground">1-4 posts/mo</span>
          </div>
          <div className="p-2 rounded-lg bg-zinc-500/10 border border-zinc-500/20 text-center">
            <span className="block text-xs font-bold text-muted-foreground">Inactive</span>
            <span className="text-[9px] text-muted-foreground">&lt;1 post/mo</span>
          </div>
        </div>
      </div>

      <div className="p-3.5 rounded-xl bg-muted/40 border border-border">
        <span className="text-xs font-semibold text-foreground block">Strategic Playbook</span>
        <span className="text-[10px] text-muted-foreground leading-relaxed">
          Route <strong>Active</strong> leads to social warmup (Like Post + Comment) before connecting. Route <strong>Inactive</strong> leads directly to Email Sequencers.
        </span>
      </div>
    </div>
  );
}

interface GetMutualConnectionsConfigProps {
  data: any;
  onChange: (key: string, value: any) => void;
}

export function GetMutualConnectionsConfig({ data, onChange }: GetMutualConnectionsConfigProps) {
  return (
    <div className="space-y-6">
      <div className="p-4 rounded-xl bg-card border border-border space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Users size={14} className="text-amber-500" />
            <span className="text-xs font-bold text-foreground">Get Mutual Connections</span>
          </div>
          <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
            Social Proof
          </span>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Checks if you share 1st-degree mutual connections with the prospect. Shared connections boost connection acceptance rates by over 45%.
        </p>
        <div className="grid grid-cols-2 gap-2 pt-1">
          <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-center">
            <span className="block text-xs font-bold text-emerald-600 dark:text-emerald-400">Has mutuals</span>
            <span className="text-[10px] text-muted-foreground">Shared network</span>
          </div>
          <div className="p-2.5 rounded-lg bg-zinc-500/10 border border-zinc-500/20 text-center">
            <span className="block text-xs font-bold text-muted-foreground">No mutuals</span>
            <span className="text-[10px] text-muted-foreground">Direct intro path</span>
          </div>
        </div>
      </div>

      <div className="p-3.5 rounded-xl bg-muted/40 border border-border">
        <span className="text-xs font-semibold text-foreground flex items-center gap-1.5 mb-1">
          <ElesiumLogo size={13} />
          <span>AI Personalization Hook</span>
        </span>
        <span className="text-[10px] text-muted-foreground leading-relaxed">
          In the <strong>Has mutuals</strong> branch, use an <strong>AI Personalize</strong> node to dynamically reference your shared contact in the connection note.
        </span>
      </div>
    </div>
  );
}

interface AIPersonalizeConfigProps {
  data: any;
  onChange: (key: string, value: any) => void;
}

export function AIPersonalizeConfig({ data, onChange }: AIPersonalizeConfigProps) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const hookSource = data.hook_sources || "Best available";
  const hookLength = data.hook_length || "One sentence";
  const aiModel = data.ai_model || "Auto-Route (Recommended)";
  const fallbackMsg = data.fallback_message ?? "I noticed your impressive background on LinkedIn.";

  const HOOK_SOURCES = [
    "Best available",
    "Recent post",
    "Job title + company",
    "Bio summary",
    "Company news",
  ];

  const HOOK_LENGTHS = [
    "One sentence",
    "Two sentences",
    "One line (punchy)",
  ];

  const AI_MODELS = [
    "Auto-Route (Recommended)",
    "DeepSeek V4 Pro",
    "GPT-OS",
    "Kimi k3",
    "Llama-3.2 11B",
    "Nemotron 120B",
  ];

  return (
    <div className="space-y-6">
      <div className="p-4 rounded-xl bg-card border border-border space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ElesiumLogo size={14} />
            <span className="text-xs font-bold text-foreground">AI Deep Personalization Hook</span>
          </div>
          <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-orange-500/10 text-orange-600 dark:text-orange-400 border border-orange-500/20">
            2 Credits
          </span>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Synthesizes prospect's recent posts, company momentum, and career history into a high-converting opening hook. Automatically stored in <code className="text-primary font-mono text-[11px] bg-primary/10 px-1 py-0.5 rounded">{"{{ai_hook}}"}</code>.
        </p>
        <div className="p-2.5 rounded-lg bg-orange-500/5 border border-orange-500/15 flex items-center justify-between text-[11px]">
          <span className="text-muted-foreground font-medium">Output Variables:</span>
          <div className="flex gap-1.5 font-mono text-[10px] text-orange-600 dark:text-orange-400">
            <span className="bg-orange-500/10 px-1.5 py-0.5 rounded">{"{{ai_hook}}"}</span>
            <span className="bg-orange-500/10 px-1.5 py-0.5 rounded">{"{{icebreaker}}"}</span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">
            Hook Source
          </label>
          <Select
            value={hookSource}
            onValueChange={val => onChange("hook_sources", val)}
          >
            <SelectTrigger className="w-full bg-card border-border text-xs h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {HOOK_SOURCES.map(s => (
                <SelectItem key={s} value={s}>{s}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">
            Hook Length
          </label>
          <Select
            value={hookLength}
            onValueChange={val => onChange("hook_length", val)}
          >
            <SelectTrigger className="w-full bg-card border-border text-xs h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {HOOK_LENGTHS.map(l => (
                <SelectItem key={l} value={l}>{l}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <AIModelSelector
        value={aiModel}
        onChange={(m) => onChange("ai_model", m)}
        models={AI_MODELS}
        label="AI Routing Engine (Model)"
      />

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          Fallback Message (If Profile Has Zero Data)
        </label>
        <input
          type="text"
          value={fallbackMsg}
          onChange={e => onChange("fallback_message", e.target.value)}
          placeholder="I noticed your impressive background on LinkedIn."
          className="w-full rounded-lg bg-card border border-border px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
        <span className="text-[10px] text-muted-foreground mt-1 block">
          Guarantees the outreach message never delivers an empty string.
        </span>
      </div>

      <div className="border-t border-border pt-3">
        <button
          type="button"
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="flex items-center gap-1.5 text-xs font-semibold text-indigo-600 dark:text-indigo-400 hover:underline"
        >
          <ChevronDown size={14} className={cn("transition-transform", showAdvanced && "rotate-180")} />
          <span>{showAdvanced ? "Hide Persona & Prompt Overrides" : "Custom Persona & Prompt Overrides"}</span>
        </button>

        {showAdvanced && (
          <div className="mt-3 space-y-3">
            <div>
              <label className="block text-xs font-semibold text-foreground mb-1">
                Custom Persona Override
              </label>
              <textarea
                value={data.custom_persona || ""}
                onChange={e => onChange("custom_persona", e.target.value)}
                rows={2}
                placeholder="e.g., You are a seasoned technical recruiter speaking to high-caliber engineering leads..."
                className="w-full rounded-lg bg-card border border-border p-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-foreground mb-1">
                Custom Generation Rules
              </label>
              <textarea
                value={data.custom_rules || ""}
                onChange={e => onChange("custom_rules", e.target.value)}
                rows={2}
                placeholder="e.g., Mention their company specifically. Never use exclamation marks. Keep it under 25 words."
                className="w-full rounded-lg bg-card border border-border p-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none"
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

interface AIDetectSentimentConfigProps {
  data: any;
  onChange: (key: string, value: any) => void;
}

export function AIDetectSentimentConfig({ data, onChange }: AIDetectSentimentConfigProps) {
  const aiModel = data.ai_model || "Auto-Route (Recommended)";

  const AI_MODELS = [
    "Auto-Route (Recommended)",
    "DeepSeek V4 Pro",
    "GPT-OS",
    "Kimi k3",
    "Llama-3.2 11B",
    "Nemotron 120B",
  ];

  return (
    <div className="space-y-6">
      <div className="p-4 rounded-xl bg-card border border-border space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ElesiumLogo size={16} />
            <span className="text-xs font-bold text-foreground">Elesium Reply Sentiment Triage</span>
          </div>
          <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-orange-500/10 text-orange-600 dark:text-orange-400 border border-orange-500/20">
            2 Credits
          </span>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Analyzes inbound prospect responses and splits sequence execution into 3 discrete deterministic branches. Automates warm lead acceleration and graceful objection handling.
        </p>
        <div className="grid grid-cols-3 gap-2 pt-1">
          <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-center">
            <span className="block text-xs font-bold text-emerald-600 dark:text-emerald-400">Positive</span>
            <span className="text-[10px] text-muted-foreground">Demo / Interest</span>
          </div>
          <div className="p-2.5 rounded-lg bg-zinc-500/10 border border-zinc-500/20 text-center">
            <span className="block text-xs font-bold text-muted-foreground">− Neutral</span>
            <span className="text-[10px] text-muted-foreground">Inquiry / OOO</span>
          </div>
          <div className="p-2.5 rounded-lg bg-rose-500/10 border border-rose-500/20 text-center">
            <span className="block text-xs font-bold text-rose-600 dark:text-rose-400">Negative</span>
            <span className="text-[10px] text-muted-foreground">Objection / Opt-out</span>
          </div>
        </div>
      </div>

      <AIModelSelector
        value={aiModel}
        onChange={(m) => onChange("ai_model", m)}
        models={AI_MODELS}
        label="AI Classification Model"
      />

      <div className="p-3.5 rounded-xl bg-indigo-50/80 dark:bg-indigo-950/20 border border-indigo-200 dark:border-indigo-900/30 space-y-1.5">
        <div className="flex items-center gap-1.5 text-xs font-bold text-indigo-900 dark:text-indigo-300">
          <Tag size={13} />
          <span>Automated CRM Sync & Triage</span>
        </div>
        <p className="text-[11px] text-indigo-800 dark:text-indigo-300/80 leading-relaxed">
          Stored in <code className="font-mono bg-indigo-100 dark:bg-indigo-900/40 px-1 py-0.5 rounded">{"{{ai_sentiment}}"}</code> and <code className="font-mono bg-indigo-100 dark:bg-indigo-900/40 px-1 py-0.5 rounded">{"{{ai_sentiment_reasoning}}"}</code>. Positive replies immediately flag SDRs via In-App Inbox.
        </p>
      </div>
    </div>
  );
}

interface AIIcebreakerConfigProps {
  data: any;
  onChange: (key: string, value: any) => void;
}

export function AIIcebreakerConfig({ data, onChange }: AIIcebreakerConfigProps) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const tone = data.tone || "Curious";
  const maxChars = data.max_chars ?? 150;
  const aiModel = data.ai_model || "Auto-Route (Recommended)";
  const fallbackMsg = data.fallback_message ?? "Loved your recent activity on LinkedIn.";

  const TONES = [
    "Curious",
    "Agreeable",
    "Challenging (respectfully)",
    "Complimentary",
  ];

  const AI_MODELS = [
    "Auto-Route (Recommended)",
    "DeepSeek V4 Pro",
    "GPT-OS",
    "Kimi k3",
    "Llama-3.2 11B",
    "Nemotron 120B",
  ];

  return (
    <div className="space-y-6">
      <div className="p-4 rounded-xl bg-card border border-border space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ElesiumLogo size={16} />
            <span className="text-xs font-bold text-foreground">Elesium Organic Post Icebreaker</span>
          </div>
          <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-orange-500/10 text-orange-600 dark:text-orange-400 border border-orange-500/20">
            2 Credits
          </span>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Scrapes the lead's latest post and drafts an authentic, contextual icebreaker opening line. Stored in <code className="text-primary font-mono text-[11px] bg-primary/10 px-1 py-0.5 rounded">{"{{ai_icebreaker}}"}</code>.
        </p>
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          Conversation Tone
        </label>
        <Select
          value={tone}
          onValueChange={val => onChange("tone", val)}
        >
          <SelectTrigger className="w-full bg-card border-border text-xs h-9">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TONES.map(t => (
              <SelectItem key={t} value={t}>{t}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="block text-xs font-semibold text-foreground">
            Maximum Character Length
          </label>
          <span className="text-xs font-mono font-bold text-foreground">{maxChars} chars</span>
        </div>
        <input
          type="range"
          min={50}
          max={250}
          value={maxChars}
          onChange={e => onChange("max_chars", Number(e.target.value))}
          className="w-full accent-indigo-600 cursor-pointer"
        />
        <div className="flex justify-between text-[10px] text-muted-foreground mt-1">
          <span>50 chars</span>
          <span>150 chars (Recommended)</span>
          <span>250 chars</span>
        </div>
      </div>

      <AIModelSelector
        value={aiModel}
        onChange={(m) => onChange("ai_model", m)}
        models={AI_MODELS}
        label="AI Routing Engine (Model)"
      />

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          Fallback Icebreaker (If Prospect Has No Recent Posts)
        </label>
        <input
          type="text"
          value={fallbackMsg}
          onChange={e => onChange("fallback_message", e.target.value)}
          placeholder="Loved your recent activity on LinkedIn."
          className="w-full rounded-lg bg-card border border-border px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
      </div>

      <div className="border-t border-border pt-3">
        <button
          type="button"
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="flex items-center gap-1.5 text-xs font-semibold text-indigo-600 dark:text-indigo-400 hover:underline"
        >
          <ChevronDown size={14} className={cn("transition-transform", showAdvanced && "rotate-180")} />
          <span>{showAdvanced ? "Hide Persona & Prompt Overrides" : "Custom Persona & Prompt Overrides"}</span>
        </button>

        {showAdvanced && (
          <div className="mt-3 space-y-3">
            <div>
              <label className="block text-xs font-semibold text-foreground mb-1">
                Custom Persona Override
              </label>
              <textarea
                value={data.custom_persona || ""}
                onChange={e => onChange("custom_persona", e.target.value)}
                rows={2}
                placeholder="e.g., Casual founder-to-founder tone, no corporate buzzwords..."
                className="w-full rounded-lg bg-card border border-border p-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-foreground mb-1">
                Custom Generation Rules
              </label>
              <textarea
                value={data.custom_rules || ""}
                onChange={e => onChange("custom_rules", e.target.value)}
                rows={2}
                placeholder="e.g., Compliment their insight without agreeing blindly. End with a thoughtful question."
                className="w-full rounded-lg bg-card border border-border p-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none"
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

interface AITranslateMessageConfigProps {
  data: any;
  onChange: (key: string, value: any) => void;
}

export function AITranslateMessageConfig({ data, onChange }: AITranslateMessageConfigProps) {
  const targetLang = data.target_language || data.fallback_language || "German";
  const aiModel = data.ai_model || "Auto-Route (Recommended)";
  const fallbackMsg = data.fallback_message || "";

  const LANGUAGES = [
    "German",
    "French",
    "Spanish",
    "Portuguese",
    "Dutch",
    "Italian",
    "Japanese",
    "English",
  ];

  const AI_MODELS = [
    "Auto-Route (Recommended)",
    "DeepSeek V4 Pro",
    "GPT-OS",
    "Kimi k3",
    "Llama-3.2 11B",
    "Nemotron 120B",
  ];

  return (
    <div className="space-y-6">
      <div className="p-4 rounded-xl bg-card border border-border space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ElesiumLogo size={14} />
            <span className="text-xs font-bold text-foreground">AI Native Message Translation</span>
          </div>
          <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-orange-500/10 text-orange-600 dark:text-orange-400 border border-orange-500/20">
            1 Credit
          </span>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Translates outreach messages into the prospect's native language while strictly protecting your template tags (e.g. <code className="text-primary font-mono text-[11px] bg-primary/10 px-1 py-0.5 rounded">{"{{first_name}}"}</code>, <code className="text-primary font-mono text-[11px] bg-primary/10 px-1 py-0.5 rounded">{"{{company}}"}</code>).
        </p>
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          Target Language
        </label>
        <Select
          value={targetLang}
          onValueChange={val => {
            onChange("target_language", val);
            onChange("fallback_language", val);
          }}
        >
          <SelectTrigger className="w-full bg-card border-border text-xs h-9">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {LANGUAGES.map(l => (
              <SelectItem key={l} value={l}>{l}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <AIModelSelector
        value={aiModel}
        onChange={(m) => onChange("ai_model", m)}
        models={AI_MODELS}
        label="AI Translation Model"
      />

      <div className="p-3.5 rounded-xl bg-emerald-50/80 dark:bg-emerald-950/20 border border-emerald-200 dark:border-emerald-900/30 space-y-1">
        <span className="text-xs font-bold text-emerald-900 dark:text-emerald-300 block">
          Variable Preservation Shield Active
        </span>
        <p className="text-[11px] text-emerald-800 dark:text-emerald-300/80 leading-relaxed">
          Dynamic tags like <span className="font-mono">{"{{first_name}}"}</span> are locked during translation and re-injected automatically to prevent broken message syntax.
        </p>
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          Fallback Message (If Translation Engine Fails)
        </label>
        <textarea
          value={fallbackMsg}
          onChange={e => onChange("fallback_message", e.target.value)}
          rows={2}
          placeholder="Optional English fallback message body..."
          className="w-full rounded-lg bg-card border border-border p-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none"
        />
      </div>
    </div>
  );
}

interface AIWriteConnectionNoteConfigProps {
  data: any;
  onChange: (key: string, value: any) => void;
}

export function AIWriteConnectionNoteConfig({ data, onChange }: AIWriteConnectionNoteConfigProps) {
  const angle = data.angle || "Relevant experience";
  const aiModel = data.ai_model || "Auto-Route (Recommended)";
  const fallbackMsg = data.fallback_message ?? "I'd love to connect.";
  const promptOverride = data.prompt || data.custom_rules || "";

  const ANGLES = [
    "Relevant experience",
    "Shared interest in their post",
    "Company context",
    "Direct value offer",
  ];

  const AI_MODELS = [
    "Auto-Route (Recommended)",
    "DeepSeek V4 Pro",
    "GPT-OS",
    "Kimi k3",
    "Llama-3.2 11B",
    "Nemotron 120B",
  ];

  return (
    <div className="space-y-6">
      <div className="p-4 rounded-xl bg-card border border-border space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ElesiumLogo size={14} className="text-indigo-500" />
            <span className="text-xs font-bold text-foreground">AI Hyper-Personalized Connection Note</span>
          </div>
          <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-500/20">
            1 Credit
          </span>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Drafts a customized connection note leveraging real company knowledge and prospect role context. Automatically clamped to 300 characters to adhere to LinkedIn's limits.
        </p>
        <div className="p-2.5 rounded-lg bg-indigo-500/5 border border-indigo-500/15 flex items-center justify-between text-[11px]">
          <span className="text-muted-foreground font-medium">Output Variables:</span>
          <div className="flex gap-1.5 font-mono text-[10px] text-indigo-600 dark:text-indigo-400">
            <span className="bg-indigo-500/10 px-1.5 py-0.5 rounded">{"{{ai_connection_note}}"}</span>
            <span className="bg-indigo-500/10 px-1.5 py-0.5 rounded">{"{{note}}"}</span>
          </div>
        </div>
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          Connection Angle
        </label>
        <Select
          value={angle}
          onValueChange={val => onChange("angle", val)}
        >
          <SelectTrigger className="w-full bg-card border-border text-xs h-9">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {ANGLES.map(a => (
              <SelectItem key={a} value={a}>{a}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <AIModelSelector
        value={aiModel}
        onChange={(m) => onChange("ai_model", m)}
        models={AI_MODELS}
        label="AI Model"
      />

      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="block text-xs font-semibold text-foreground">
            Custom Prompt / Angle Directives <span className="text-muted-foreground font-normal">(optional)</span>
          </label>
          <span className="text-[10px] text-muted-foreground">300 char hard limit enforced</span>
        </div>
        <textarea
          value={promptOverride}
          onChange={e => {
            onChange("prompt", e.target.value);
            onChange("custom_rules", e.target.value);
          }}
          rows={3}
          placeholder="e.g., Focus on their recent transition into VP of Product. Keep it humble and concise."
          className="w-full rounded-lg bg-card border border-border p-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none"
        />
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          Fallback Note (If AI Call Fails)
        </label>
        <input
          type="text"
          value={fallbackMsg}
          maxLength={300}
          onChange={e => onChange("fallback_message", e.target.value)}
          placeholder="I'd love to connect."
          className="w-full rounded-lg bg-card border border-border px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
      </div>
    </div>
  );
}

interface AIGenerateReplyConfigProps {
  data: any;
  onChange: (key: string, value: any) => void;
}

export function AIGenerateReplyConfig({ data, onChange }: AIGenerateReplyConfigProps) {
  const confidenceThreshold = data.confidence_threshold ?? 65;
  const requireApproval = data.require_human_approval ?? true;

  return (
    <div className="space-y-6">
      <div className="p-4 rounded-xl bg-card border border-border space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ElesiumLogo size={16} />
            <span className="text-xs font-bold text-foreground">Elesium Autonomous Reply Generator</span>
          </div>
          <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-orange-500/10 text-orange-600 dark:text-orange-400 border border-orange-500/20">
            5 Credits
          </span>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Queries Workspace Knowledge Base (RAG), checks for brand consistency, and drafts/sends a human-grade contextual reply when a lead responds.
        </p>
      </div>

      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="block text-xs font-semibold text-foreground">
            RAG Confidence Threshold
          </label>
          <span className="text-xs font-mono font-bold text-foreground">{confidenceThreshold}%</span>
        </div>
        <input
          type="range"
          min={50}
          max={95}
          value={confidenceThreshold}
          onChange={e => onChange("confidence_threshold", Number(e.target.value))}
          className="w-full accent-indigo-600 cursor-pointer"
        />
        <div className="flex justify-between text-[10px] text-muted-foreground mt-1">
          <span>50% (Permissive)</span>
          <span>65% (Balanced)</span>
          <span>95% (Strict)</span>
        </div>
      </div>

      <div className="p-3.5 rounded-xl bg-muted/40 border border-border flex items-center justify-between">
        <div>
          <span className="text-xs font-semibold text-foreground block">Human Review on Low Confidence</span>
          <span className="text-[10px] text-muted-foreground">Queue low-confidence replies for manual SDR approval</span>
        </div>
        <input
          type="checkbox"
          checked={requireApproval}
          onChange={e => onChange("require_human_approval", e.target.checked)}
          className="w-4 h-4 rounded text-indigo-600 focus:ring-indigo-500 border-border cursor-pointer"
        />
      </div>

      <div className="p-3.5 rounded-xl bg-rose-50/80 dark:bg-rose-950/20 border border-rose-200 dark:border-rose-900/30 space-y-1">
        <div className="flex items-center gap-1.5 text-xs font-bold text-rose-900 dark:text-rose-300">
          <Shield size={13} />
          <span>Bot-to-Bot Loop Circuit Breaker</span>
        </div>
        <p className="text-[11px] text-rose-800 dark:text-rose-300/80 leading-relaxed">
          Safety architecture enforces a strict ceiling of max 3 autonomous replies per 24 hours per prospect. Prevents infinite conversational ping-pong if talking to an automated bot.
        </p>
      </div>
    </div>
  );
}

interface AIQueryKnowledgeBaseConfigProps {
  data: any;
  onChange: (key: string, value: any) => void;
}

export function AIQueryKnowledgeBaseConfig({ data, onChange }: AIQueryKnowledgeBaseConfigProps) {
  const aiModel = data.ai_model || "Auto-Route (Recommended)";
  const fallbackMsg = data.fallback_message || "";

  const AI_MODELS = [
    "Auto-Route (Recommended)",
    "DeepSeek V4 Pro",
    "GPT-OS",
    "Kimi k3",
    "Llama-3.2 11B",
    "Nemotron 120B",
  ];

  return (
    <div className="space-y-6">
      <div className="p-4 rounded-xl bg-card border border-border space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ElesiumLogo size={16} />
            <span className="text-xs font-bold text-foreground">Elesium Knowledge Base (Brain)</span>
          </div>
          <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-orange-500/10 text-orange-600 dark:text-orange-400 border border-orange-500/20">
            3 Credits
          </span>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Queries your uploaded company documents, pricing FAQs, and objection handling playbooks to generate a hyper-accurate, fact-checked response.
        </p>
        <div className="grid grid-cols-2 gap-2 pt-1">
          <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-center">
            <span className="block text-xs font-bold text-emerald-600 dark:text-emerald-400">Response Generated</span>
            <span className="text-[10px] text-muted-foreground">Answer found in KB</span>
          </div>
          <div className="p-2.5 rounded-lg bg-rose-500/10 border border-rose-500/20 text-center">
            <span className="block text-xs font-bold text-rose-600 dark:text-rose-400">Failed</span>
            <span className="text-[10px] text-muted-foreground">No matching knowledge</span>
          </div>
        </div>
      </div>

      <AIModelSelector
        value={aiModel}
        onChange={(m) => onChange("ai_model", m)}
        models={AI_MODELS}
        label="AI Reasoning Engine"
      />

      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">
          Fallback Message (If Knowledge Base Has No Match)
        </label>
        <textarea
          value={fallbackMsg}
          onChange={e => onChange("fallback_message", e.target.value)}
          rows={3}
          placeholder="e.g., Thanks for asking! Let me look into that and get back to you with the exact details."
          className="w-full rounded-lg bg-card border border-border p-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none"
        />
        <span className="text-[10px] text-muted-foreground mt-1 block">
          If provided, routes to "Response Generated" using this text instead of failing the branch.
        </span>
      </div>

      <div className="p-3.5 rounded-xl bg-muted/40 border border-border space-y-1">
        <span className="text-xs font-semibold text-foreground block">
          Output Variable Mapping
        </span>
        <div className="flex gap-2 font-mono text-[11px] text-orange-600 dark:text-orange-400 pt-1">
          <span className="bg-orange-500/10 px-2 py-0.5 rounded">{"{{ai_objection_handler}}"}</span>
          <span className="bg-orange-500/10 px-2 py-0.5 rounded">{"{{ai_brain_response}}"}</span>
        </div>
      </div>
    </div>
  );
}

function CongratulateConfig({ data, onChange, mode }: { data: any; onChange: (k: string, v: any) => void; mode: "new_job" | "anniversary" }) {
  const isNewJob = mode === "new_job";
  const defaultMsg = isNewJob
    ? "Congrats on the new role at {{company}}, {{first_name}}! Wishing you great success."
    : "Happy work anniversary, {{first_name}}! A real milestone at {{company}}.";

  const rawMsg: string = data.message || data.body || defaultMsg;
  const rawLength = rawMsg.length;
  const isOverLimit = rawLength > 300;

  const presets = isNewJob ? [
    { label: "Role Promotion", text: "Congrats on the new role at {{company}}, {{first_name}}! Excited to see what you build there." },
    { label: "Company Move", text: "Saw your move to {{company}} — massive congratulations {{first_name}}!" },
    { label: "Leadership Transition", text: "Congrats on taking the reins at {{company}}! Wishing you huge success." },
  ] : [
    { label: "Company Milestone", text: "Happy work anniversary, {{first_name}}! Incredible milestone at {{company}}." },
    { label: "Year in Review", text: "Congrats on another year at {{company}}, {{first_name}}! Hope you're celebrating today." },
    { label: "Long-term Impact", text: "Happy anniversary {{first_name}}! Time flies when you're doing impactful work." },
  ];

  const insertVar = (v: string) => {
    onChange("message", (data.message || data.body || "") + ` {{${v}}}`);
    onChange("body", (data.message || data.body || "") + ` {{${v}}}`);
  };

  return (
    <div className="space-y-6">
      {/* Prerequisite & Compatibility Banner */}
      <div className="p-3.5 rounded-xl bg-amber-500/10 dark:bg-amber-950/30 border border-amber-500/30 dark:border-amber-600/40 flex items-start gap-2.5">
        <AlertTriangle size={16} className="text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
        <div className="space-y-1">
          <span className="text-xs font-semibold text-amber-900 dark:text-amber-200 block">
            Natural Warm-Up Trigger
          </span>
          <p className="text-[11px] text-amber-800/90 dark:text-amber-300/80 leading-relaxed">
            {isNewJob
              ? "LinkedIn members are 3.5x more likely to respond when congratulated on a career move. Sent via direct message to 1st-degree connections, or as a connection note if not yet connected."
              : "Work anniversaries are high-visibility touchpoints. People always welcome genuine celebration. Auto-dispatches during their milestone window."}
          </p>
        </div>
      </div>

      {/* Auto-Fallback Checkbox */}
      <div className="p-3 rounded-xl bg-card border border-border flex items-start gap-3">
        <input
          id={`fallback_to_connection_request_${mode}`}
          type="checkbox"
          checked={data.fallback_to_connection_request !== false}
          onChange={e => onChange("fallback_to_connection_request", e.target.checked)}
          className="mt-0.5 h-4 w-4 rounded border-border text-indigo-600 focus:ring-indigo-500 cursor-pointer"
        />
        <label htmlFor={`fallback_to_connection_request_${mode}`} className="cursor-pointer select-none space-y-0.5">
          <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            Auto-fallback to Connection Request
            <span className="text-[10px] font-medium px-1.5 py-0.2 rounded bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30">
              Recommended
            </span>
          </span>
          <p className="text-[11px] text-muted-foreground leading-relaxed">
            If prospect is a 2nd/3rd-degree connection, automatically dispatch a Connection Request with this congratulatory note (max 300 chars) instead of halting.
          </p>
        </label>
      </div>

      {/* Delay Selector */}
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Pacing Delay</label>
        <DelaySelector
          value={data.delay !== undefined ? data.delay : 0}
          unit={data.delayUnit || "days"}
          onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }}
        />
      </div>

      {/* Quick Presets */}
      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">Tactical Presets</label>
        <div className="flex flex-wrap gap-1.5">
          {presets.map(p => (
            <button
              key={p.label}
              type="button"
              onClick={() => {
                onChange("message", p.text);
                onChange("body", p.text);
              }}
              className="px-2.5 py-1 rounded-lg text-xs font-medium bg-muted/60 hover:bg-muted text-muted-foreground hover:text-foreground border border-border/50 transition-colors"
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* Message Editor */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-xs font-semibold text-foreground">Congratulations Message</label>
          <span className={cn("text-[10px]", isOverLimit ? "text-destructive font-bold" : "text-muted-foreground")}>
            {rawLength}/300
          </span>
        </div>
        <textarea
          rows={3}
          maxLength={300}
          value={data.message || data.body || ""}
          onChange={e => {
            onChange("message", e.target.value);
            onChange("body", e.target.value);
          }}
          placeholder={defaultMsg}
          className="w-full rounded-xl bg-card border border-border px-3.5 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none leading-relaxed"
        />
        <div className="flex flex-wrap gap-1 mt-1.5">
          {["first_name", "company", "title"].map(v => (
            <button
              key={v}
              type="button"
              onClick={() => insertVar(v)}
              className="text-[10px] px-1.5 py-0.5 rounded bg-muted/60 hover:bg-muted text-muted-foreground hover:text-foreground border border-border/40 transition-colors"
            >
              + {`{{${v}}}`}
            </button>
          ))}
        </div>
      </div>

      <FallbackEditor data={data} onChange={onChange} maxChars={300} fallbackLabel="Fallback Note" />
    </div>
  );
}

function SequenceMessageConfig({
  data,
  onChange,
  messageType
}: {
  data: any;
  onChange: (k: string, v: any) => void;
  messageType: "intro" | "followup" | "breakup" | "reengage";
}) {
  const meta = {
    intro: {
      title: "Opening Connection Touch",
      desc: "First message after connection accepted. Value-first and relationship-building — avoid aggressive pitches.",
      color: "border-indigo-500/30 bg-indigo-50/10",
      iconColor: "text-indigo-500",
      badge: "Touch #1",
      presets: [
        { label: "Peer Perspective", text: "Hey {{first_name}}, thanks for connecting! Loved seeing your perspective on {{title}} work at {{company}}." },
        { label: "Resource Share", text: "Hi {{first_name}}, glad to connect. Put together some research on industry trends and thought of your team." },
        { label: "Casual Hello", text: "Hey {{first_name}}, great to connect with fellow leaders in this space. Looking forward to keeping in touch!" }
      ]
    },
    followup: {
      title: "Value Follow-Up Touch",
      desc: "80% of B2B conversions happen after touch 3. Add fresh evidence, customer stories, or a new question angle.",
      color: "border-blue-500/30 bg-blue-50/10",
      iconColor: "text-blue-500",
      badge: "Touch #2+",
      presets: [
        { label: "Metric Bump", text: "Following up on my last note, {{first_name}} — we recently helped a team in your space cut cycle times by 40%." },
        { label: "Short Question", text: "Quick question {{first_name}} — is this bottleneck on your radar this quarter, or should I circle back later?" },
        { label: "Alternative Contact", text: "Hey {{first_name}}, if you're not the right person for this at {{company}}, who on your team would be best to chat with?" }
      ]
    },
    breakup: {
      title: "Polite Breakup Touch",
      desc: "The final touch in a sequence. Removing sales pressure triggers curiosity and frequently recovers leads who ignored previous touches.",
      color: "border-rose-500/30 bg-rose-50/10",
      iconColor: "text-rose-500",
      badge: "Final Touch",
      presets: [
        { label: "Permission to Close", text: "Hey {{first_name}}, I haven't heard back so I assume this isn't a priority right now. Permission to close your file?" },
        { label: "Cross You Off?", text: "Quick check, {{first_name}} — should I stop reaching out, or is the timing just bad right now?" },
        { label: "Door Open", text: "I'll pause reaching out here, {{first_name}}. If things change down the road at {{company}}, my door is always open." }
      ]
    },
    reengage: {
      title: "Cold Re-engagement Touch",
      desc: "Re-contact cold leads after 30-90 days with fresh news, new product capabilities, or recent company achievements.",
      color: "border-blue-500/30 bg-blue-50/10",
      iconColor: "text-blue-500",
      badge: "Recycled Lead",
      presets: [
        { label: "Product Update", text: "Hi {{first_name}}, circling back as we just shipped a major update that solves the bottleneck we chatted about." },
        { label: "New Case Study", text: "Hey {{first_name}}, thought of {{company}} when we published this new teardown for modern teams." },
        { label: "Quarterly Check-in", text: "Hi {{first_name}}, checking in for the new quarter — has anything changed regarding your roadmap at {{company}}?" }
      ]
    }
  }[messageType];

  return (
    <div className="space-y-6">
      {/* Contextual Sequence Banner */}
      <div className={cn("p-3.5 rounded-xl border flex items-start gap-2.5", meta.color)}>
        <Sparkles size={16} className={cn("shrink-0 mt-0.5", meta.iconColor)} />
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-foreground block">{meta.title}</span>
            <span className="text-[10px] font-bold px-1.5 py-0.2 rounded bg-primary/10 text-primary border border-primary/20">
              {meta.badge}
            </span>
          </div>
          <p className="text-[11px] text-muted-foreground leading-relaxed">
            {meta.desc}
          </p>
        </div>
      </div>

      {/* Auto-Fallback Checkbox */}
      <div className="p-3 rounded-xl bg-card border border-border flex items-start gap-3">
        <input
          id={`fallback_to_connection_request_${messageType}`}
          type="checkbox"
          checked={data.fallback_to_connection_request !== false}
          onChange={e => onChange("fallback_to_connection_request", e.target.checked)}
          className="mt-0.5 h-4 w-4 rounded border-border text-indigo-600 focus:ring-indigo-500 cursor-pointer"
        />
        <label htmlFor={`fallback_to_connection_request_${messageType}`} className="cursor-pointer select-none space-y-0.5">
          <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            Auto-fallback to Connection Request
            <span className="text-[10px] font-medium px-1.5 py-0.2 rounded bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30">
              Recommended
            </span>
          </span>
          <p className="text-[11px] text-muted-foreground leading-relaxed">
            If the lead is not connected, automatically dispatch a Connection Request with this message (up to 300 chars) instead of failing.
          </p>
        </label>
      </div>

      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Delay</label>
        <DelaySelector value={data.delay} unit={data.delayUnit || "days"} onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }} />
      </div>

      {/* Tactical Presets */}
      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">Starter Presets</label>
        <div className="flex flex-wrap gap-1.5">
          {meta.presets.map(p => (
            <button
              key={p.label}
              type="button"
              onClick={() => {
                onChange("body", p.text);
              }}
              className="px-2.5 py-1 rounded-lg text-xs font-medium bg-muted/60 hover:bg-muted text-muted-foreground hover:text-foreground border border-border/50 transition-colors"
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      <MessageEditor
        label="Message"
        value={data.body || ""}
        onChange={v => onChange("body", v)}
        maxChars={8000}
        placeholder="Write your sequence message..."
      />

      <FallbackEditor data={data} onChange={onChange} maxChars={8000} />
    </div>
  );
}

// ─── Node type → config component + metadata ─────────────────────────────────
const NODE_CONFIG: Record<string, {
  title: string
  icon: any
  color: string
  render: (data: any, onChange: (k: string, v: any) => void) => React.ReactNode
}> = {
  // ── Warmup ─────────────────────────────────────────────────────────────────
  view_profile: {
    title: "View Profile",
    icon: Eye,
    color: "#06b6d4",
    render: (data, onChange) => <ViewProfileConfig data={data} onChange={onChange} />,
  },
  view_profile_repeat: {
    title: "Re-visit Profile",
    icon: Eye,
    color: "#06b6d4",
    render: (data, onChange) => <ViewProfileConfig data={data} onChange={onChange} isRepeat={true} />,
  },
  congratulate_new_job: {
    title: "Congratulate New Job",
    icon: Award,
    color: "#06b6d4",
    render: (data, onChange) => <CongratulateConfig data={data} onChange={onChange} mode="new_job" />,
  },
  congratulate_anniversary: {
    title: "Congratulate Work Anniversary",
    icon: Sparkles,
    color: "#06b6d4",
    render: (data, onChange) => <CongratulateConfig data={data} onChange={onChange} mode="anniversary" />,
  },
  follow_profile: {
    title: "Follow Profile",
    icon: Users,
    color: "#06b6d4",
    render: (data, onChange) => <FollowProfileConfig data={data} onChange={onChange} />,
  },
  like_post: {
    title: "Like Recent Post",
    icon: Heart,
    color: "#06b6d4",
    render: (data, onChange) => <LikePostConfig data={data} onChange={onChange} />,
  },
  like_top_3_posts: {
    title: "React to Top 3 Posts",
    icon: Heart,
    color: "#06b6d4",
    render: (data, onChange) => <LikePostConfig data={data} onChange={onChange} defaultMaxPosts={3} />,
  },
  react_insightful: {
    title: "React Insightful to Post",
    icon: Sparkles,
    color: "#06b6d4",
    render: (data, onChange) => <LikePostConfig data={{ ...data, reaction_type: "insightful" }} onChange={onChange} />,
  },
  react_celebrate: {
    title: "React Celebrate to Post",
    icon: Sparkles,
    color: "#06b6d4",
    render: (data, onChange) => <LikePostConfig data={{ ...data, reaction_type: "celebrate" }} onChange={onChange} />,
  },
  comment_on_post: {
    title: "Comment on Post",
    icon: MessageSquare,
    color: "#06b6d4",
    render: (data, onChange) => <CommentOnPostConfig data={data} onChange={onChange} />,
  },
  endorse_skill: {
    title: "Endorse a Skill",
    icon: Star,
    color: "#06b6d4",
    render: (data, onChange) => <EndorseSkillConfig data={data} onChange={onChange} />,
  },
  endorse_3_skills: {
    title: "Endorse Top 3 Skills",
    icon: Star,
    color: "#06b6d4",
    render: (data, onChange) => <EndorseSkillConfig data={data} onChange={onChange} defaultMaxSkills={3} />,
  },
  follow_company: {
    title: "Follow Company Page",
    icon: Building2,
    color: "#06b6d4",
    render: (data, onChange) => <FollowCompanyConfig data={data} onChange={onChange} />,
  },
  share_post: {
    title: "Share Prospect Post",
    icon: Share2,
    color: "#06b6d4",
    render: (data, onChange) => <SharePostConfig data={data} onChange={onChange} />,
  },
  invite_to_event: {
    title: "LinkedIn Event Invite",
    icon: CalendarCheck,
    color: "#06b6d4",
    render: (data, onChange) => <InviteToEventConfig data={data} onChange={onChange} />,
  },
  // ── Connect ────────────────────────────────────────────────────────────────
  connection_request: {
    title: "Send Connection Request",
    icon: UserPlus,
    color: "#6366f1",
    render: (data, onChange) => <ConnectionRequestConfig data={data} onChange={onChange} />,
  },
  // ── Conditions ─────────────────────────────────────────────────────────────
  if_connected: {
    title: "If Connected?",
    icon: CheckCircle2,
    color: "#10b981",
    render: (data, onChange) => <IfConnectedConfig data={data} onChange={onChange} />,
  },
  if_replied: {
    title: "If Replied?",
    icon: MessageSquare,
    color: "#10b981",
    render: (data, onChange) => <IfRepliedConfig data={data} onChange={onChange} />,
  },
  open_profile_check: {
    title: "Open Profile Check",
    icon: Search,
    color: "#10b981",
    render: (data, onChange) => <OpenProfileConfig data={data} onChange={onChange} />,
  },
  seamless_identity_matching: {
    title: "Seamless Identity Match",
    icon: ShieldCheck,
    color: "#06b6d4",
    render: (data, onChange) => <SeamlessIdentityMatchingConfig data={data} onChange={onChange} />,
  },
  if_email_found: {
    title: "If Email Found?",
    icon: AtSign,
    color: "#10b981",
    render: (data, onChange) => <IfEmailFoundConfig data={data} onChange={onChange} />,
  },
  if_meeting_booked: {
    title: "If Meeting Booked?",
    icon: CalendarCheck,
    color: "#10b981",
    render: (data, onChange) => <IfMeetingBookedConfig data={data} onChange={onChange} />,
  },
  if_company_size: {
    title: "If Company Size?",
    icon: Building2,
    color: "#10b981",
    render: (data, onChange) => <IfCompanySizeConfig data={data} onChange={onChange} />,
  },
  if_company_hiring: {
    title: "If Company is Hiring?",
    icon: Briefcase,
    color: "#10b981",
    render: (data, onChange) => <IfCompanyHiringConfig data={data} onChange={onChange} />,
  },
  if_premium_member: {
    title: "If LinkedIn Premium?",
    icon: Award,
    color: "#10b981",
    render: (data, onChange) => <IfPremiumMemberConfig data={data} onChange={onChange} />,
  },
  if_mutual_connections: {
    title: "If Mutual Connections?",
    icon: Users,
    color: "#10b981",
    render: (data, onChange) => <IfMutualConnectionsConfig data={data} onChange={onChange} />,
  },
  if_recently_active: {
    title: "If Recently Active?",
    icon: Zap,
    color: "#10b981",
    render: (data, onChange) => <IfRecentlyActiveConfig data={data} onChange={onChange} />,
  },
  if_has_recent_posts: {
    title: "If Has Recent Posts?",
    icon: MessageSquare,
    color: "#10b981",
    render: (data, onChange) => <IfHasRecentPostsConfig data={data} onChange={onChange} />,
  },
  if_large_following: {
    title: "If High Follower Count?",
    icon: Users,
    color: "#10b981",
    render: (data, onChange) => <IfLargeFollowingConfig data={data} onChange={onChange} />,
  },
  if_title_matches: {
    title: "If Title Matches?",
    icon: Tag,
    color: "#10b981",
    render: (data, onChange) => <IfTitleMatchesConfig data={data} onChange={onChange} />,
  },
  if_location_matches: {
    title: "If Location Matches?",
    icon: MapPin,
    color: "#10b981",
    render: (data, onChange) => <IfLocationMatchesConfig data={data} onChange={onChange} />,
  },
  if_industry_matches: {
    title: "If Industry Matches?",
    icon: Building2,
    color: "#10b981",
    render: (data, onChange) => <IfIndustryMatchesConfig data={data} onChange={onChange} />,
  },
  icp_score_gate: {
    title: "ICP Score Gate",
    icon: Target,
    color: "#10b981",
    render: (data, onChange) => <ICPScoreGateConfig data={data} onChange={onChange} />,
  },
  // ── Messages ───────────────────────────────────────────────────────────────
  send_message: {
    title: "Send Message",
    icon: MessageSquare,
    color: "#6366f1",
    render: (data, onChange) => <SendMessageConfig data={data} onChange={onChange} />,
  },
  send_message_ab: {
    title: "Send Message (A/B Test)",
    icon: MessageSquare,
    color: "#6366f1",
    render: (data, onChange) => <ABMessageEditor data={data} onChange={onChange} />,
  },
  send_message_with_doc: {
    title: "Send Message + Doc",
    icon: MessageSquare,
    color: "#6366f1",
    render: (data, onChange) => (
      <SendMessageConfig
        data={{ ...data, attachment_type: data.attachment_type || "Document" }}
        onChange={onChange}
      />
    ),
  },
  send_message_with_image: {
    title: "Send Message + Image",
    icon: MessageSquare,
    color: "#6366f1",
    render: (data, onChange) => (
      <SendMessageConfig
        data={{ ...data, attachment_type: data.attachment_type || "Image" }}
        onChange={onChange}
      />
    ),
  },
  send_followup: {
    title: "Send Follow-up Message",
    icon: MessageSquare,
    color: "#6366f1",
    render: (data, onChange) => <SequenceMessageConfig data={data} onChange={onChange} messageType="followup" />,
  },
  send_intro_message: {
    title: "Send Intro Message",
    icon: MessageSquare,
    color: "#6366f1",
    render: (data, onChange) => <SequenceMessageConfig data={data} onChange={onChange} messageType="intro" />,
  },
  send_breakup_message: {
    title: "Send Breakup Message",
    icon: MessageSquare,
    color: "#6366f1",
    render: (data, onChange) => <SequenceMessageConfig data={data} onChange={onChange} messageType="breakup" />,
  },
  send_reengage_message: {
    title: "Send Re-engage Message",
    icon: MessageSquare,
    color: "#6366f1",
    render: (data, onChange) => <SequenceMessageConfig data={data} onChange={onChange} messageType="reengage" />,
  },
  send_ai_message: {
    title: "Send AI-Personalized Message",
    icon: Sparkles,
    color: "#6366f1",
    render: (data, onChange) => <SendAiMessageConfig data={data} onChange={onChange} />,
  },
  send_voice_note: {
    title: "Send Voice Note",
    icon: Mic2,
    color: "#6366f1",
    render: (data, onChange) => <SendVoiceNoteConfig data={data} onChange={onChange} />,
  },
  send_inmail: {
    title: "Send InMail",
    icon: Mail,
    color: "#6366f1",
    render: (data, onChange) => <SendInMailConfig data={data} onChange={onChange} />,
  },
  send_paid_inmail: {
    title: "Send Paid InMail",
    icon: Mail,
    color: "#6366f1",
    render: (data, onChange) => <SendInMailConfig data={data} onChange={onChange} isPaid={true} />,
  },
  send_email: {
    title: "Send Work Email",
    icon: AtSign,
    color: "#ec4899",
    render: (data, onChange) => <SendEmailConfig data={data} onChange={onChange} />,
  },
  // ── Convert ────────────────────────────────────────────────────────────────
  send_meeting_invite: {
    title: "Send Meeting Invite",
    icon: CalendarCheck,
    color: "#f59e0b",
    render: (data, onChange) => (
      <div className="space-y-6">
        <div><label className="block text-xs font-semibold text-foreground mb-2">Delay</label><DelaySelector value={data.delay} unit={data.delayUnit || "days"} onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }} /></div>
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">Calendly / Booking URL</label>
          <input value={data.calendly_url || ""} onChange={e => onChange("calendly_url", e.target.value)}
            placeholder="https://calendly.com/your-link"
            className="w-full rounded-lg bg-card border border-border px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600" />
        </div>
        <MessageEditor label="Message body" value={data.body || ""} onChange={v => onChange("body", v)} maxChars={8000} placeholder="Hey {{first_name}}, would love to show you what we do..." />
        <div className="p-3 rounded-xl bg-amber-50/80 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/40">
          <p className="text-xs text-amber-800 dark:text-amber-300 font-medium">If the lead books, all subsequent steps in this path will stop automatically.</p>
        </div>
      </div>
    ),
  },
  send_intro_call_invite: {
    title: "LinkedIn Intro Call Invite",
    icon: CalendarCheck,
    color: "#f59e0b",
    render: (data, onChange) => (
      <div className="space-y-6">
        <div>
          <label className="block text-xs font-semibold text-foreground mb-2">Delay</label>
          <DelaySelector
            value={data.delay}
            unit={data.delayUnit || "days"}
            onChange={(v, u) => {
              onChange("delay", v);
              onChange("delayUnit", u);
            }}
          />
        </div>
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">Meeting Subject</label>
          <input
            value={data.subject || ""}
            onChange={e => onChange("subject", e.target.value)}
            placeholder="Quick intro call — 20 mins"
            className="w-full rounded-lg bg-card border border-border px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
          />
        </div>
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">Duration</label>
          <Select
            value={String(data.duration_minutes || 20)}
            onValueChange={val => onChange("duration_minutes", Number(val))}
          >
            <SelectTrigger className="w-full bg-card border-border text-xs h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="15">15 minutes</SelectItem>
              <SelectItem value="20">20 minutes (Recommended)</SelectItem>
              <SelectItem value="30">30 minutes</SelectItem>
              <SelectItem value="45">45 minutes</SelectItem>
              <SelectItem value="60">60 minutes</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <MessageEditor
          label="Invitation note body"
          value={data.body || ""}
          onChange={v => onChange("body", v)}
          maxChars={8000}
          placeholder="Hey {{first_name}}, would love to connect for a quick 20-min chat to explore..."
        />
        <div className="p-3.5 rounded-xl bg-amber-50/80 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/40">
          <p className="text-xs text-amber-800 dark:text-amber-300 font-medium">
            <strong>Native Booking Advantage:</strong> LinkedIn native call invites bypass external link friction, yielding an average 2.4x higher acceptance rate than external calendar links.
          </p>
        </div>
      </div>
    ),
  },
  update_lead_status: {
    title: "Update Lead Status",
    icon: Tag,
    color: "#f59e0b",
    render: (data, onChange) => {
      const STATUS_OPTIONS = [
        "Interested",
        "MQL",
        "SQL",
        "Meeting Booked",
        "Converted",
        "Not Interested",
        "Opted Out (GDPR)"
      ];
      return (
        <div className="space-y-6">
          <div>
            <label className="block text-xs font-semibold text-foreground mb-1.5">New Lifecycle Status</label>
            <Select
              value={data.status || "Interested"}
              onValueChange={val => onChange("status", val)}
            >
              <SelectTrigger className="w-full bg-card border-border text-xs h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {STATUS_OPTIONS.map(opt => (
                  <SelectItem key={opt} value={opt}>{opt}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <label className="block text-xs font-semibold text-foreground mb-1.5">CRM Tag <span className="text-muted-foreground font-normal">(optional)</span></label>
            <input
              value={data.tag || ""}
              onChange={e => onChange("tag", e.target.value)}
              placeholder="e.g. warm_lead_q4"
              className="w-full rounded-lg bg-card border border-border px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-foreground mb-1.5">Internal Note <span className="text-muted-foreground font-normal">(optional)</span></label>
            <textarea
              value={data.note || ""}
              onChange={e => onChange("note", e.target.value)}
              rows={3}
              placeholder="Notes for sales team sync..."
              className="w-full rounded-xl bg-card border border-border px-3.5 py-3 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none"
            />
          </div>
          <div className="p-3.5 rounded-xl bg-muted/40 border border-border space-y-1">
            <span className="text-xs font-semibold text-foreground block">Downstream Variable Mapping</span>
            <span className="text-[11px] text-muted-foreground font-mono">
              Stores status in <code className="text-foreground bg-muted px-1 py-0.5 rounded">{"{{lead_status}}"}</code> and synchronizes across HubSpot/Salesforce.
            </span>
          </div>
        </div>
      );
    },
  },
  mark_interested: {
    title: "Mark as Interested",
    icon: ThumbsUp,
    color: "#10b981",
    render: (data, onChange) => (
      <div className="space-y-6">
        <div className="p-3.5 rounded-xl bg-emerald-50/80 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800/40">
          <p className="text-xs text-emerald-800 dark:text-emerald-300 font-medium">
            <strong>High-Intent Milestone:</strong> Marks the lead as "Interested" in the pipeline, alerts SDRs, and enables warm follow-up branching.
          </p>
        </div>
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">CRM Tag</label>
          <input
            value={data.tag || "interested"}
            onChange={e => onChange("tag", e.target.value)}
            placeholder="e.g. interested"
            className="w-full rounded-lg bg-card border border-border px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
          />
        </div>
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">Internal Note <span className="text-muted-foreground font-normal">(optional)</span></label>
          <textarea
            value={data.note || ""}
            onChange={e => onChange("note", e.target.value)}
            rows={3}
            placeholder="Context regarding prospect's interest..."
            className="w-full rounded-xl bg-card border border-border px-3.5 py-3 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none"
          />
        </div>
      </div>
    ),
  },
  mark_mql: {
    title: "Mark as MQL",
    icon: Star,
    color: "#f59e0b",
    render: (data, onChange) => (
      <div className="space-y-6">
        <div className="p-3.5 rounded-xl bg-amber-50/80 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/40">
          <p className="text-xs text-amber-800 dark:text-amber-300 font-medium">
            <strong>Marketing Qualified Lead:</strong> Designates that the lead has met engagement or ICP criteria, qualifying them for marketing nurture or SDR review.
          </p>
        </div>
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">CRM Tag</label>
          <input
            value={data.tag || "mql"}
            onChange={e => onChange("tag", e.target.value)}
            placeholder="e.g. mql"
            className="w-full rounded-lg bg-card border border-border px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
          />
        </div>
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">Internal Note <span className="text-muted-foreground font-normal">(optional)</span></label>
          <textarea
            value={data.note || ""}
            onChange={e => onChange("note", e.target.value)}
            rows={3}
            placeholder="MQL qualification rationale..."
            className="w-full rounded-xl bg-card border border-border px-3.5 py-3 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none"
          />
        </div>
      </div>
    ),
  },
  mark_sql: {
    title: "Mark as SQL",
    icon: Zap,
    color: "#f59e0b",
    render: (data, onChange) => (
      <div className="space-y-6">
        <div className="p-3.5 rounded-xl bg-amber-50/80 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/40">
          <p className="text-xs text-amber-800 dark:text-amber-300 font-medium">
            <strong>Sales Qualified Lead:</strong> Flags lead as ready for direct Account Executive discovery and demo handoff.
          </p>
        </div>
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">CRM Tag</label>
          <input
            value={data.tag || "sql"}
            onChange={e => onChange("tag", e.target.value)}
            placeholder="e.g. sql"
            className="w-full rounded-lg bg-card border border-border px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
          />
        </div>
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">Internal Note <span className="text-muted-foreground font-normal">(optional)</span></label>
          <textarea
            value={data.note || ""}
            onChange={e => onChange("note", e.target.value)}
            rows={3}
            placeholder="Key discovery notes or AE briefing..."
            className="w-full rounded-xl bg-card border border-border px-3.5 py-3 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none"
          />
        </div>
      </div>
    ),
  },
  mark_converted: {
    title: "Mark as Converted",
    icon: Tag,
    color: "#10b981",
    render: (data, onChange) => (
      <div className="space-y-6">
        <div className="p-3.5 rounded-xl bg-emerald-50/80 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800/40">
          <p className="text-xs text-emerald-800 dark:text-emerald-300 font-medium">Ends this sequence path and marks the lead as converted. No further steps will run.</p>
        </div>
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">CRM Tag</label>
          <input
            value={data.tag || "customer_won"}
            onChange={e => onChange("tag", e.target.value)}
            placeholder="e.g. meeting_booked"
            className="w-full rounded-lg bg-card border border-border px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
          />
        </div>
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">Internal Note <span className="text-muted-foreground font-normal">(optional)</span></label>
          <textarea
            value={data.note || ""}
            onChange={e => onChange("note", e.target.value)}
            rows={3}
            placeholder="Optional note for your CRM records..."
            className="w-full rounded-xl bg-card border border-border px-3.5 py-3 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none"
          />
        </div>
      </div>
    ),
  },
  mark_not_interested: {
    title: "Mark as Not Interested",
    icon: ThumbsDown,
    color: "#6b7280",
    render: (data, onChange) => (
      <div className="space-y-6">
        <div className="p-3.5 rounded-xl bg-zinc-100 dark:bg-zinc-800/40 border border-zinc-200 dark:border-zinc-700/50">
          <p className="text-xs text-zinc-700 dark:text-zinc-300 font-medium">
            ⏹️ <strong>Terminal Exit Node:</strong> Immediately ceases all outreach for this prospect across the campaign.
          </p>
        </div>
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">Disqualification Reason</label>
          <Select
            value={data.reason || "Not a fit"}
            onValueChange={val => onChange("reason", val)}
          >
            <SelectTrigger className="w-full bg-card border-border text-xs h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="Not a fit">Not a fit / Bad ICP</SelectItem>
              <SelectItem value="Using competitor">Already using competitor</SelectItem>
              <SelectItem value="No budget">No budget / Freeze</SelectItem>
              <SelectItem value="Bad timing">Bad timing / Follow up in 6 months</SelectItem>
              <SelectItem value="Explicit decline">Explicitly declined</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">Internal Note <span className="text-muted-foreground font-normal">(optional)</span></label>
          <textarea
            value={data.note || ""}
            onChange={e => onChange("note", e.target.value)}
            rows={3}
            placeholder="Disqualification context..."
            className="w-full rounded-xl bg-card border border-border px-3.5 py-3 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none"
          />
        </div>
      </div>
    ),
  },
  mark_opted_out: {
    title: "Opt Out (GDPR Suppression)",
    icon: ShieldCheck,
    color: "#ef4444",
    render: (data, onChange) => (
      <div className="space-y-6">
        <div className="p-3.5 rounded-xl bg-rose-50/80 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-800/40 space-y-1.5">
          <div className="flex items-center gap-1.5 text-xs font-bold text-rose-900 dark:text-rose-300">
            <Ban size={13} />
            <span>Terminal GDPR / CAN-SPAM Compliance Node</span>
          </div>
          <p className="text-[11px] text-rose-800 dark:text-rose-300/80 leading-relaxed">
            Immediately halts outreach and writes the contact's LinkedIn profile and corporate email to the workspace-wide <strong>Suppression List</strong>. Prevents accidental re-enrollment across ALL future campaigns.
          </p>
        </div>
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">Compliance Reason</label>
          <input
            value={data.reason || "Prospect requested unsubscribe"}
            onChange={e => onChange("reason", e.target.value)}
            className="w-full rounded-lg bg-card border border-border px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
          />
        </div>
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">Internal Audit Note <span className="text-muted-foreground font-normal">(optional)</span></label>
          <textarea
            value={data.note || ""}
            onChange={e => onChange("note", e.target.value)}
            rows={2}
            placeholder="Audit log details for unsubscribe request..."
            className="w-full rounded-xl bg-card border border-border px-3.5 py-3 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none"
          />
        </div>
      </div>
    ),
  },
  // ── AI Intelligence ────────────────────────────────────────────────────────
  ai_personalize: {
    title: "AI Personalize",
    icon: Sparkles,
    color: "#f97316",
    render: (data, onChange) => <AIPersonalizeConfig data={data} onChange={onChange} />,
  },
  ai_detect_sentiment: {
    title: "AI Detect Reply Sentiment",
    icon: Brain,
    color: "#f97316",
    render: (data, onChange) => <AIDetectSentimentConfig data={data} onChange={onChange} />,
  },
  ai_generate_icebreaker: {
    title: "AI Generate Icebreaker",
    icon: Sparkles,
    color: "#f97316",
    render: (data, onChange) => <AIIcebreakerConfig data={data} onChange={onChange} />,
  },
  ai_translate_message: {
    title: "AI Translate Message",
    icon: Languages,
    color: "#f97316",
    render: (data, onChange) => <AITranslateMessageConfig data={data} onChange={onChange} />,
  },
  ai_write_connection_note: {
    title: "AI Write Connection Note",
    icon: UserPlus,
    color: "#6366f1",
    render: (data, onChange) => <AIWriteConnectionNoteConfig data={data} onChange={onChange} />,
  },
  ai_generate_reply: {
    title: "AI: Reply to Lead",
    icon: Bot,
    color: "#f97316",
    render: (data, onChange) => <AIGenerateReplyConfig data={data} onChange={onChange} />,
  },
  ai_query_knowledge_base: {
    title: "AI Query Brain",
    icon: BookOpen,
    color: "#f97316",
    render: (data, onChange) => <AIQueryKnowledgeBaseConfig data={data} onChange={onChange} />,
  },
  ai_query_brain: {
    title: "AI Query Brain",
    icon: BookOpen,
    color: "#f97316",
    render: (data, onChange) => <AIQueryKnowledgeBaseConfig data={data} onChange={onChange} />,
  },
  ai_score_icp: {
    title: "AI Score ICP Fit",
    icon: Sparkles,
    color: "#f97316",
    render: (data, onChange) => <AIScoreICPConfig data={data} onChange={onChange} />,
  },
  ai_buying_signal: {
    title: "AI Detect Buying Signal",
    icon: Zap,
    color: "#f97316",
    render: (data, onChange) => <AIBuyingSignalConfig data={data} onChange={onChange} />,
  },
  ai_detect_buying_signal: {
    title: "AI Detect Buying Signal",
    icon: Zap,
    color: "#f97316",
    render: (data, onChange) => <AIBuyingSignalConfig data={data} onChange={onChange} />,
  },
  ai_detect_competitor: {
    title: "AI Detect Competitor User",
    icon: ShieldCheck,
    color: "#f97316",
    render: (data, onChange) => <AIDetectCompetitorConfig data={data} onChange={onChange} />,
  },
  ai_summarize_profile: {
    title: "AI Summarize Profile",
    icon: Sparkles,
    color: "#f97316",
    render: (data, onChange) => <AISummarizeProfileConfig data={data} onChange={onChange} />,
  },
  ai_best_send_time: {
    title: "AI Suggest Best Send Time",
    icon: Clock,
    color: "#f97316",
    render: (data, onChange) => <AIBestSendTimeConfig data={data} onChange={onChange} />,
  },
  ai_suggest_best_send_time: {
    title: "AI Suggest Best Send Time",
    icon: Clock,
    color: "#f97316",
    render: (data, onChange) => <AIBestSendTimeConfig data={data} onChange={onChange} />,
  },
  // ── Enrichment ─────────────────────────────────────────────────────────────
  find_email: {
    title: "Find Work Email",
    icon: AtSign,
    color: "#f59e0b",
    render: (data, onChange) => <EnrichmentDiscoveryConfig data={data} onChange={onChange} />,
  },
  find_personal_email: {
    title: "Find Personal Email",
    icon: AtSign,
    color: "#f59e0b",
    render: (data, onChange) => <EnrichmentDiscoveryConfig data={data} onChange={onChange} isPersonal={true} />,
  },
  apollo_enrich: {
    title: "Apollo Direct Enrichment",
    icon: Database,
    color: "#f59e0b",
    render: (data, onChange) => <EnrichmentDiscoveryConfig data={data} onChange={onChange} isApollo={true} />,
  },
  zero_cost_discovery: {
    title: "Zero-Cost Email Discovery",
    icon: AtSign,
    color: "#10b981",
    render: (data, onChange) => <EnrichmentDiscoveryConfig data={data} onChange={onChange} isZeroCost={true} />,
  },
  verify_email: {
    title: "Verify Email Deliverability",
    icon: CheckCircle2,
    color: "#f59e0b",
    render: (data, onChange) => <VerifyEmailConfig data={data} onChange={onChange} />,
  },
  find_phone: {
    title: "Find Phone Number",
    icon: Phone,
    color: "#f59e0b",
    render: (data, onChange) => <FindPhoneConfig data={data} onChange={onChange} />,
  },
  find_tech_stack: {
    title: "Find Company Tech Stack",
    icon: Cpu,
    color: "#f59e0b",
    render: (data, onChange) => <FindTechStackConfig data={data} onChange={onChange} />,
  },
  find_funding_round: {
    title: "Find Funding Round",
    icon: DollarSign,
    color: "#f59e0b",
    render: (data, onChange) => <FindFundingRoundConfig data={data} onChange={onChange} />,
  },
  find_headcount: {
    title: "Find Company Headcount",
    icon: Building2,
    color: "#f59e0b",
    render: (data, onChange) => <FindHeadcountConfig data={data} onChange={onChange} />,
  },
  find_job_postings: {
    title: "Find Open Job Postings",
    icon: Briefcase,
    color: "#f59e0b",
    render: (data, onChange) => <FindJobPostingsConfig data={data} onChange={onChange} />,
  },
  get_linkedin_activity: {
    title: "LinkedIn Activity Score",
    icon: Activity,
    color: "#f59e0b",
    render: (data, onChange) => <GetLinkedInActivityConfig data={data} onChange={onChange} />,
  },
  get_mutual_connections: {
    title: "Get Mutual Connections",
    icon: Users,
    color: "#f59e0b",
    render: (data, onChange) => <GetMutualConnectionsConfig data={data} onChange={onChange} />,
  },
  // ── Multichannel ──────────────────────────────────────────────────────────
  add_to_email_sequencer: {
    title: "Add to Email Sequencer",
    icon: Zap,
    color: "#ec4899",
    render: (data, onChange) => <EmailSequencerConfig data={data} onChange={onChange} />,
  },
  add_to_smartlead: {
    title: "Add to Smartlead",
    icon: Zap,
    color: "#ec4899",
    render: (data, onChange) => <EmailSequencerConfig data={data} onChange={onChange} defaultProvider="Smartlead" />,
  },
  add_to_instantly: {
    title: "Add to Instantly",
    icon: Zap,
    color: "#ec4899",
    render: (data, onChange) => <EmailSequencerConfig data={data} onChange={onChange} defaultProvider="Instantly" />,
  },
  add_to_emailbison: {
    title: "Add to EmailBison",
    icon: Zap,
    color: "#ec4899",
    render: (data, onChange) => <EmailSequencerConfig data={data} onChange={onChange} defaultProvider="EmailBison" />,
  },
  add_to_lemlist: {
    title: "Add to Lemlist",
    icon: Zap,
    color: "#ec4899",
    render: (data, onChange) => <EmailSequencerConfig data={data} onChange={onChange} defaultProvider="Lemlist" />,
  },
  add_to_apollo: {
    title: "Add to Apollo",
    icon: Zap,
    color: "#ec4899",
    render: (data, onChange) => <EmailSequencerConfig data={data} onChange={onChange} defaultProvider="Apollo" />,
  },
  push_to_crm: {
    title: "Push to CRM",
    icon: Database,
    color: "#0ea5e9",
    render: (data, onChange) => <PushToCRMConfig data={data} onChange={onChange} />,
  },
  push_to_hubspot: {
    title: "Push to HubSpot",
    icon: Database,
    color: "#0ea5e9",
    render: (data, onChange) => <PushToCRMConfig data={{ ...data, provider: "HubSpot", crm: "HubSpot" }} onChange={onChange} />,
  },
  push_to_salesforce: {
    title: "Push to Salesforce",
    icon: Database,
    color: "#0ea5e9",
    render: (data, onChange) => <PushToCRMConfig data={{ ...data, provider: "Salesforce", crm: "Salesforce" }} onChange={onChange} />,
  },
  push_to_pipedrive: {
    title: "Push to Pipedrive",
    icon: Database,
    color: "#0ea5e9",
    render: (data, onChange) => <PushToCRMConfig data={{ ...data, provider: "Pipedrive", crm: "Pipedrive" }} onChange={onChange} />,
  },
  push_to_notion: {
    title: "Push to Notion",
    icon: Database,
    color: "#0ea5e9",
    render: (data, onChange) => <PushToCRMConfig data={{ ...data, provider: "Notion", crm: "Notion" }} onChange={onChange} />,
  },
  push_to_airtable: {
    title: "Push to Airtable",
    icon: Database,
    color: "#0ea5e9",
    render: (data, onChange) => <PushToCRMConfig data={{ ...data, provider: "Airtable", crm: "Airtable" }} onChange={onChange} />,
  },
  send_slack_alert: {
    title: "Send Slack Alert",
    icon: Bell,
    color: "#ec4899",
    render: (data, onChange) => <SendSlackAlertConfig data={data} onChange={onChange} />,
  },
  send_webhook: {
    title: "Send Webhook",
    icon: Zap,
    color: "#ec4899",
    render: (data, onChange) => <SendWebhookConfig data={data} onChange={onChange} />,
  },
  withdraw_request: {
    title: "Withdraw Request",
    icon: RotateCcw,
    color: "#f59e0b",
    render: (data, onChange) => <WithdrawRequestConfig data={data} onChange={onChange} />,
  },
  remove_connection: {
    title: "Remove Connection",
    icon: UserMinus,
    color: "#ef4444",
    render: (data, onChange) => <RemoveConnectionConfig data={data} onChange={onChange} />,
  },
  // ── Control & Flow ──────────────────────────────────────────────────────────
  ab_split: {
    title: "A/B Split (50/50)",
    icon: Split,
    color: "#52525b",
    render: (data, onChange) => <ABSplitConfig data={data} onChange={onChange} />,
  },
  weighted_split: {
    title: "Weighted Split",
    icon: GitFork,
    color: "#52525b",
    render: (data, onChange) => <WeightedSplitConfig data={data} onChange={onChange} />,
  },
  daily_limit_check: {
    title: "Daily Limit Check",
    icon: Gauge,
    color: "#52525b",
    render: (data, onChange) => <DailyLimitCheckConfig data={data} onChange={onChange} />,
  },
  blacklist_check: {
    title: "Blacklist Check",
    icon: Ban,
    color: "#52525b",
    render: (data, onChange) => <BlacklistCheckConfig data={data} onChange={onChange} />,
  },
  add_tag: {
    title: "Add Tag / Label",
    icon: Tag,
    color: "#52525b",
    render: (data, onChange) => <AddTagConfig data={data} onChange={onChange} />,
  },
  wait_for_reply: {
    title: "Wait for Reply",
    icon: Clock,
    color: "#52525b",
    render: (data, onChange) => <WaitForReplyConfig data={data} onChange={onChange} />,
  },
  retry_step: {
    title: "Retry Step",
    icon: RotateCcw,
    color: "#52525b",
    render: (data, onChange) => <RetryStepConfig data={data} onChange={onChange} />,
  },
  sequence_end: {
    title: "Sequence End",
    icon: StopCircle,
    color: "#52525b",
    render: (data, onChange) => <SequenceEndConfig data={data} onChange={onChange} />,
  },
}

// ─── Nodal Guide Recommendations ────────────────────────────────────────────────
const NODAL_GUIDE: Record<string, string> = {
  // Current HR_NODE_DEFS keys
  "view_profile": "The most logical next step is a 1-day Wait delay, followed by a Connection Request.",
  "view_profile_repeat": "Re-visiting prospect profiles sends a second notification ping, ideal right before sending a follow-up DM.",
  "follow_profile": "Follow creates a warm notification. Pair with View Profile or wait 1-2 days before Connect.",
  "follow_company": "Following the company page proves account research. Pair with an account-level insight in your outreach message.",
  "like_post": "Engaging with prospect posts builds warm context before sending a Connection Request.",
  "like_top_3_posts": "Reacting to multiple posts creates a persistent presence in their notifications. Follow with a Connection Request.",
  "react_insightful": "Insightful reactions trigger high-visibility thought-leadership notifications on executive posts.",
  "react_celebrate": "Celebrate reactions acknowledge milestone posts (promotions, funding, awards) before reaching out.",
  "comment_on_post": "Comments get 5x more visibility than likes. Follow with a Connection Request referencing the topic.",
  "endorse_skill": "Skill endorsement triggers a high-visibility LinkedIn notification before outreach.",
  "endorse_3_skills": "Endorsing 3 skills generates 3 notifications in one sweep. Best used 1-2 days before connecting.",
  "connection_request": "The most logical next step is an 'If Connected?' conditional branch.",
  "if_connected": "In the YES path, send a warm welcome Message. In the NO path, send an InMail or enrich email.",
  "if_replied": "In the YES path, Mark as Converted or Send Meeting Invite. In the NO path, send follow-up.",
  "wait_for_reply": "Waits up to N days for an inbound reply before routing down 'Replied' or 'Timeout'.",
  "retry_step": "Retries transiently failed actions up to N times before proceeding downstream.",
  "if_email_found": "In the YES path, push to multichannel (Smartlead/Instantly). In the NO path, continue on LinkedIn.",
  "if_meeting_booked": "In the YES path, Mark as Converted. In the NO path, continue sequence.",
  "if_large_following": "Route high-follower prospects to personalized InMails or higher-touch steps.",
  "if_company_size": "In the 'In range' path, send enterprise value messaging. In 'Out of range', route to SMB pitch or disqualify.",
  "if_company_hiring": "In the 'Hiring' path, address growth scaling pain points. In 'Not hiring', route to efficiency messaging.",
  "if_premium_member": "In the 'Premium' path, follow up with higher velocity. In 'Free', route down standard cadence.",
  "if_mutual_connections": "In 'Has mutuals', reference mutual colleagues via AI Personalize. In 'No mutuals', lead with case study.",
  "if_recently_active": "In 'Active', proceed on LinkedIn. In 'Inactive', route to 'Find Email' or multichannel outreach.",
  "if_has_recent_posts": "In 'Has posts', warm up with 'Comment on Post'. In 'No posts', proceed directly to connection request.",
  "if_title_matches": "In 'Matches', send persona-tailored sequence. In 'Does not match', route to secondary persona track.",
  "if_location_matches": "In 'Matches', send localized territory messaging or event invite. In 'Does not match', route to remote track.",
  "if_industry_matches": "In 'Matches', share industry-specific case study. In 'Does not match', send horizontal value pitch.",
  "icp_score_gate": "In 'Strong fit', invest in high-touch InMails and SDR tasks. In 'Weak fit', route to low-touch sequence.",
  "send_message": "The most logical next step is a 3-day Wait delay, followed by an 'If Replied?' branch.",
  "send_message_ab": "Compare A/B reply rates with a 3-day delay before the next conditional check.",
  "send_message_with_doc": "Share a PDF or slide deck to provide immediate value. Follow with 'If Replied?'.",
  "send_message_with_image": "Visual assets increase engagement. Follow with an 'If Replied?' condition.",
  "send_voice_note": "Voice notes convert 3x higher. Follow with an 'If Replied?' branch after 2-3 days.",
  "congratulate_new_job": "Congratulating on a new role is the highest-reply warmup action. Follow with a 3-day Wait delay then an 'If Replied?' branch.",
  "congratulate_anniversary": "Work anniversaries provide genuine rapport. Follow with a 3-day Wait delay then an 'If Replied?' branch.",
  "send_intro_message": "Opening message after connection. Follow with a 3-day Wait delay then an 'If Replied?' branch.",
  "send_followup": "Follow-up bump. 80% of sales require 5+ touches. Follow with a 3-day Wait delay then an 'If Replied?' branch.",
  "send_breakup_message": "Final polite breakup. Triggers curiosity and replies. Follow with 'Mark Not Interested' or 'Sequence End'.",
  "send_reengage_message": "Re-contacts cold leads with fresh context. Follow with a 3-day Wait delay then an 'If Replied?' branch.",
  "send_inmail": "Use InMails for open profiles or high-priority accounts. Follow with 'If Replied?'.",
  "send_paid_inmail": "Sponsored InMail for tier-1 unreachable accounts. Follow with a 3-day Wait delay then an 'If Replied?' branch.",
  "send_meeting_invite": "Terminal milestone: when the lead books, all remaining steps auto-pause.",
  "mark_converted": "Terminal milestone: ends this sequence path and tags the lead in your CRM.",
  "zero_cost_discovery": "Discovers corporate email addresses using zero-cost direct MX handshakes without burning third-party credits.",
  "find_email": "Follow with an 'If Email Found?' condition to route leads to cold email vs LinkedIn.",
  "find_personal_email": "Enriches personal emails for founders and execs. Follow with an email campaign handoff or direct founder pitch.",
  "verify_email": "Validates deliverability to shield sender reputation. Leads routed to 'Invalid / Risky' bypass sequencers.",
  "find_phone": "Enriches direct dials for SDR cold-call lists or WhatsApp outreach.",
  "find_tech_stack": "Detects technologies used by the company. Follow with tailored competitive displacement messaging.",
  "find_funding_round": "Checks for recent capital raises. Follow with high-priority outreach tracks for funded accounts.",
  "find_headcount": "Scrapes verified company size. Follow with an 'If Company Size' condition for SMB vs Enterprise routing.",
  "find_job_postings": "Detects active job listings and hiring demand. Tailor outreach to active hiring bottlenecks.",
  "get_linkedin_activity": "Scores 30-day posting activity. Route active creators to social interactions and inactive profiles to email.",
  "get_mutual_connections": "Checks for shared 1st-degree connections. Follow with an AI Personalize node to reference mutual colleagues.",
  "send_email": "Sends a direct 1:1 email to the enriched lead. Follow with a 3-day Wait delay then check reply.",
  "add_to_smartlead": "Seamless multichannel handoff to your Smartlead cold email campaign.",
  "add_to_instantly": "Seamless multichannel handoff to your Instantly cold email campaign.",
  "add_to_emailbison": "Seamless multichannel handoff to your EmailBison campaign.",
  "push_to_crm": "Syncs prospect data and stage directly into HubSpot, Salesforce, or Pipedrive.",
  "send_slack_alert": "Notifies your team channel instantly when a high-value signal occurs.",
  "send_webhook": "Dispatches lead data via HTTP POST payload to Zapier, Make, or custom backend endpoints.",
  "sequence_end": "Terminal state: analytics track exit reasons for continuous optimization.",
  "withdraw_request": "Withdraws pending invitations after N days to preserve account health.",

  // Legacy compatibility keys
  "linkedin_view": "The most logical next step is a 1-day Wait delay, followed by a Connection Request.",
  "linkedin_connect": "The most logical next step is an 'If Connected?' conditional branch.",
  "linkedin_message": "The most logical next step is an 'If Replied?' conditional branch.",
  "linkedin_like": "The most logical next step is a View Profile or Connect node.",
  "linkedin_inmail": "The most logical next step is an 'If Replied?' conditional branch.",
  "condition_connected": "Add a Message node in the YES path, and a follow-up in the NO path.",
  "condition_replied": "Add a Goal/Success node in the YES path, and a follow-up Message in the NO path.",
  "goal": "This is a terminal node. The sequence ends here."
}

// ─── Main panel ───────────────────────────────────────────────────────────────
export function EINodeConfigPanel() {
  const { selectedNodeId, rootNodes, updateNodeData, selectNode } = useHRTreeStore()

  // Paranoia Layer 1 & 2: Dynamic credit cost synchronization from backend authoritative registry
  const { data: costsResponse } = useSWR<{ costs?: Array<{ action_type: string; cost: number }> }>(
    '/api/elein/billing/credits/costs',
    fetcher
  );

  const dynamicCostMap = useMemo(() => {
    const map: Record<string, number> = { ...CREDIT_COST_MAP };
    if (costsResponse?.costs && Array.isArray(costsResponse.costs)) {
      for (const item of costsResponse.costs) {
        if (item.action_type && typeof item.cost === 'number') {
          map[item.action_type] = item.cost;
        }
      }
    }
    return map;
  }, [costsResponse]);

  function findInTree(nodes: any[]): any | undefined {
    for (const n of nodes) {
      if (n.id === selectedNodeId) return n
      for (const branch of Object.values(n.children || {}) as any[][]) {
        const found = findInTree(branch)
        if (found) return found
      }
    }
    return undefined
  }
  const selectedNode = findInTree(rootNodes || [])

  if (!selectedNode) return null

  const d = selectedNode.data as Record<string, any>
  const nodeType: string = d.type || ""
  const def = HR_NODE_DEFS[nodeType as keyof typeof HR_NODE_DEFS]
  const config = NODE_CONFIG[nodeType] || (def ? {
    title: def.label,
    icon: Info,
    color: def.color || "#52525b",
    render: (data: any, onChange: (k: string, v: any) => void) => (
      <DynamicNodeConfig data={data} onChange={onChange} def={def} />
    )
  } : null)

  if (!config) return null

  const onChange = (key: string, value: any) => {
    updateNodeData(selectedNode.id, { [key]: value })
  }

  const handleSave = () => {
    selectNode(null)
  }

  const Icon = config.icon
  const isConnectionNoteOverLimit = nodeType === "connection_request" && (d.note?.length || 0) > 300

  return (
    <AnimatePresence>
      <motion.div
        key={selectedNodeId}
        initial={{ x: "100%", opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        exit={{ x: "100%", opacity: 0 }}
        transition={{ type: "spring", stiffness: 380, damping: 34 }}
        className="absolute right-0 top-0 bottom-0 w-[400px] bg-background border-l border-border z-30 flex flex-col shadow-2xl"
      >
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-border shrink-0">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
            style={{ background: `${config.color}15`, border: `1px solid ${config.color}35` }}
          >
            <Icon size={15} style={{ color: config.color }} />
          </div>
          <p className="text-sm font-bold text-foreground flex-1 flex items-center gap-2">
            {(config.title.includes('AI') || nodeType.startsWith('ai_')) && (
              <ElesiumLogo size={14} className="shrink-0" />
            )}
            <span>{config.title}</span>
            {dynamicCostMap[nodeType] ? (
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20 font-bold shrink-0">
                {dynamicCostMap[nodeType]} credits
              </span>
            ) : (
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 font-medium shrink-0">
                Free
              </span>
            )}
          </p>
          <button
            onClick={() => selectNode(null)}
            className="text-muted-foreground hover:text-foreground transition-colors p-1"
          >
            <X size={16} />
          </button>
        </div>

        {/* Guidance Banner */}
        <div className="px-5 py-4 bg-card/40 border-b border-border flex items-start gap-3 shrink-0">
          <Info size={16} className="text-indigo-600 dark:text-indigo-400 mt-0.5 shrink-0" />
          <div>
            <p className="text-xs text-foreground leading-relaxed font-medium mb-1">
              {HR_NODE_DEFS[nodeType as keyof typeof HR_NODE_DEFS]?.description || "Configure this step."}
            </p>
            {NODAL_GUIDE[nodeType] && (
              <p className="text-[11px] text-muted-foreground leading-relaxed">
                <span className="text-indigo-600 dark:text-indigo-400 font-semibold">Pro Tip:</span> {NODAL_GUIDE[nodeType]}
              </p>
            )}
          </div>
        </div>

        {/* Config body */}
        <div className="flex-1 overflow-y-auto px-5 py-5">
          {config.render(d, onChange)}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-5 py-4 border-t border-border shrink-0">
          <button
            onClick={() => selectNode(null)}
            className="px-4 py-2 rounded-lg border border-border hover:border-foreground/20 text-xs text-muted-foreground hover:text-foreground transition-all"
          >
            Dismiss
          </button>
          <div className="flex items-center gap-2">
            {isConnectionNoteOverLimit && (
              <span className="text-[10px] text-rose-500 font-bold">
                Exceeds 300 chars
              </span>
            )}
            <button
              disabled={isConnectionNoteOverLimit}
              onClick={handleSave}
              className={cn(
                "px-5 py-2 rounded-lg text-xs font-bold text-white transition-all shadow-sm",
                isConnectionNoteOverLimit
                  ? "bg-muted text-muted-foreground cursor-not-allowed opacity-60"
                  : "bg-indigo-600 hover:bg-indigo-500"
              )}
            >
              Save Changes
            </button>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  )
}


function DynamicNodeConfig({ data, onChange, def }: { data: any; onChange: (k: string, v: any) => void; def: any }) {
  return (
    <div className="space-y-6">
      {def.hasDelay && (
        <div>
          <label className="block text-xs font-semibold text-foreground mb-2">Wait before executing</label>
          <DelaySelector value={data.delay !== undefined ? data.delay : (def.delayDefault || 1)} unit={data.delayUnit || "days"} onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }} />
        </div>
      )}
      
      {def.fields && (() => {
        const standardFields = def.fields.filter((f: any) => !f.advanced);
        const advancedFields = def.fields.filter((f: any) => f.advanced);
        
        const renderField = (f: any) => {
        if (f.showIf) {
            let [depKey, depVal] = f.showIf.split("==");
            let targetField = def.fields.find((df: any) => df.key === depKey);
            let currentVal = data[depKey] !== undefined ? data[depKey] : (targetField?.default || targetField?.options?.[0]);
            
            // Handle !=
            if (f.showIf.includes("!=")) {
                [depKey, depVal] = f.showIf.split("!=");
                targetField = def.fields.find((df: any) => df.key === depKey);
                currentVal = data[depKey] !== undefined ? data[depKey] : (targetField?.default || targetField?.options?.[0]);
                if (String(currentVal) === String(depVal)) return null;
            } else {
                if (String(currentVal) !== String(depVal)) return null;
            }
        }
        if (f.hideIf) {
            const [depKey, depVal] = f.hideIf.split("==");
            const targetField = def.fields.find((df: any) => df.key === depKey);
            const currentVal = data[depKey] !== undefined ? data[depKey] : (targetField?.default || targetField?.options?.[0]);
            if (String(currentVal) === String(depVal)) return null;
        }
        
        return (
        <div key={f.key}>
          <label className="block text-xs font-semibold text-foreground mb-1.5">{f.label}</label>
          
          {f.type === "info" ? (
            <div className="w-full rounded-lg bg-indigo-500/10 border border-indigo-500/20 px-3 py-2.5 text-xs text-indigo-700 dark:text-indigo-400">
              {f.content || f.placeholder || f.label}
            </div>
          ) : f.type === "input" || f.type === "number" ? (
            <input
              type={f.type === "number" ? "number" : "text"}
              value={data[f.key] !== undefined ? data[f.key] : (f.default || "")}
              onChange={e => {
                let val = f.type === "number" ? Number(e.target.value) : e.target.value;
                if (f.type === "number") {
                  if (f.min !== undefined && val < f.min) val = f.min;
                  if (f.max !== undefined && val > f.max) val = f.max;
                }
                onChange(f.key, val);
              }}
              min={f.min}
              max={f.max}
              className="w-full rounded-lg bg-card border border-border px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 transition-colors"
            />
          ) : f.type === "textarea" ? (
            <>
              <textarea
                value={data[f.key] !== undefined ? data[f.key] : (f.default || "")}
                onChange={e => onChange(f.key, e.target.value)}
                rows={4}
                className="w-full rounded-lg bg-card border border-border px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 transition-colors resize-none"
              />
              <NakedVariableWarning text={data[f.key] || ""} />
            </>
          ) : f.type === "select" ? (
            <Select
              value={data[f.key] !== undefined ? String(data[f.key]) : (String(f.default || ""))}
              onValueChange={val => onChange(f.key, val)}
            >
              <SelectTrigger className="w-full bg-card border-border text-xs h-9">
                <SelectValue placeholder="Select..." />
              </SelectTrigger>
              <SelectContent>
                {f.options?.map((opt: string) => (
                  <SelectItem key={opt} value={opt}>{opt}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : f.type === "toggle" ? (
            <div className="flex items-center gap-2 mt-1">
              <button
                onClick={() => onChange(f.key, !(data[f.key] ?? f.default))}
                className={`w-10 h-5 rounded-full transition-colors relative ${
                  (data[f.key] ?? f.default) ? "bg-indigo-600" : "bg-muted"
                }`}
              >
                <div className={`w-4 h-4 rounded-full bg-white absolute top-0.5 transition-all ${
                  (data[f.key] ?? f.default) ? "left-[22px]" : "left-0.5"
                }`} />
              </button>
            </div>
          ) : null}
        </div>
        );
      }

        return (
          <>
            {standardFields.map(renderField)}
            {advancedFields.length > 0 && (
              <div className="mt-4">
                <AdvancedSettingsPanel label="Advanced Settings">
                  <div className="space-y-4">
                    {advancedFields.map(renderField)}
                  </div>
                </AdvancedSettingsPanel>
              </div>
            )}
          </>
        );
      })()}
      
      {!def.hasDelay && (!def.fields || def.fields.length === 0) && (
        <div className="p-4 rounded-xl bg-background border border-border">
          <p className="text-xs text-muted-foreground leading-relaxed">
            {def.description || "This action executes immediately. No additional configuration needed."}
          </p>
        </div>
      )}
    </div>
  )
}

// ─── Tree-store config panel ───────────────────────────────────────────────────

export function EITreeNodeConfigPanel() {
  const { selectedNodeId, rootNodes, updateNodeData, selectNode } = useHRTreeStore()
  const isPickerOpen = usePickerStore(s => s.isOpen)

  if (isPickerOpen) return null


  function findInTree(nodes: any[]): any | undefined {
    for (const n of nodes) {
      if (n.id === selectedNodeId) return n
      for (const branch of Object.values(n.children || {}) as any[][]) {
        const found = findInTree(branch)
        if (found) return found
      }
    }
  }

  const selectedNode = findInTree(rootNodes)
  if (!selectedNode) return null

  const d = selectedNode.data as Record<string, any>
  const nodeType: string = d.type || ""
  
  const def = HR_NODE_DEFS[nodeType as keyof typeof HR_NODE_DEFS]
  if (!def) return null

  const config = NODE_CONFIG[nodeType] || {
    title: def.label,
    icon: Info,
    color: def.color || "#52525b",
    render: (data: any, onChange: (k: string, v: any) => void) => (
      <DynamicNodeConfig data={data} onChange={onChange} def={def} />
    )
  }

  const onChange = (key: string, value: any) => {
    updateNodeData(selectedNode.id, { [key]: value })
  }

  const Icon = config.icon

  return (
    <AnimatePresence>
      <motion.div
        key={selectedNodeId}
        initial={{ x: "100%", opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        exit={{ x: "100%", opacity: 0 }}
        transition={{ type: "spring", stiffness: 380, damping: 34 }}
        className="fixed right-0 top-0 bottom-0 w-[400px] bg-card border-l border-border z-50 flex flex-col shadow-2xl"
      >
        {(() => {
          const isElesiumNode = nodeType.startsWith("ai_") || nodeType.includes("brain") || nodeType.includes("icebreaker");
          return (
            <>
              <div className="flex items-center gap-3 px-5 py-4 border-b border-border shrink-0">
                <div
                  className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
                  style={{ background: `${config.color}15`, border: `1px solid ${config.color}30` }}
                >
                  {isElesiumNode ? (
                    <ElesiumLogo size={16} />
                  ) : (
                    <Icon size={15} style={{ color: config.color }} />
                  )}
                </div>
                <p className="text-sm font-bold text-foreground flex-1 flex items-center gap-2">
                  {config.title}
                  {isElesiumNode && (
                    <span className="text-[9px] font-bold px-1.5 py-0.2 rounded bg-primary/10 text-primary border border-primary/20 shrink-0">
                      Elesium
                    </span>
                  )}
                  {CREDIT_COST_MAP[nodeType] ? (
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20 font-bold shrink-0">
                      {CREDIT_COST_MAP[nodeType]} credits
                    </span>
                  ) : (
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 font-medium shrink-0">
                      Free
                    </span>
                  )}
                </p>
                <button onClick={() => selectNode(null)} className="text-muted-foreground hover:text-foreground transition-colors p-1">
                  <X size={16} />
                </button>
              </div>

              {/* Guidance Banner */}
              <div className="px-5 py-3.5 bg-muted/30 border-b border-border flex items-start gap-3 shrink-0">
                {isElesiumNode ? (
                  <ElesiumLogo size={16} className="mt-0.5 shrink-0" />
                ) : (
                  <Info size={16} className="text-indigo-600 dark:text-indigo-400 mt-0.5 shrink-0" />
                )}
                <div className="flex-1">
                  <p className="text-xs text-foreground leading-relaxed font-medium mb-0.5">
                    {def.description || "Configure this step."}
                  </p>
                  {isElesiumNode && (
                    <p className="text-[10px] text-primary mt-1 font-semibold">
                      Powered by Elesium Automation (<a href="https://elesium.online" target="_blank" rel="noopener noreferrer" className="underline hover:text-primary/80">elesium.online</a>)
                    </p>
                  )}
                  {NODAL_GUIDE[nodeType] && (
                    <p className="text-[11px] text-muted-foreground leading-relaxed mt-1">
                      <span className="text-indigo-600 dark:text-indigo-400 font-semibold">Pro Tip:</span> {NODAL_GUIDE[nodeType]}
                    </p>
                  )}
                </div>
              </div>
            </>
          );
        })()}

        <div className="flex-1 overflow-y-auto px-5 py-5">
          {config.render(d, onChange)}
        </div>

        <div className="flex items-center justify-between px-5 py-4 border-t border-border shrink-0">
          <button
            onClick={() => selectNode(null)}
            className="px-4 py-2 rounded-lg border border-border hover:border-foreground/20 text-xs text-muted-foreground hover:text-foreground transition-all"
          >
            Dismiss
          </button>
          <div className="flex items-center gap-2">
            {nodeType === "connection_request" && (d.note?.length || 0) > 300 && (
              <span className="text-[10px] text-rose-500 font-bold">
                Exceeds 300 chars
              </span>
            )}
            <button
              disabled={nodeType === "connection_request" && (d.note?.length || 0) > 300}
              onClick={() => selectNode(null)}
              className={cn(
                "px-5 py-2 rounded-lg text-xs font-bold text-white transition-all shadow-sm",
                nodeType === "connection_request" && (d.note?.length || 0) > 300
                  ? "bg-muted text-muted-foreground cursor-not-allowed opacity-60"
                  : "bg-indigo-600 hover:bg-indigo-500"
              )}
            >
              Save Changes
            </button>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  )
}
