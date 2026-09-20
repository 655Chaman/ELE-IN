import { useState, useEffect, useRef } from "react"
import { motion, AnimatePresence } from "motion/react"
import {
  X, ChevronDown, Eye, Plus, RotateCcw, Info,
  UserPlus, MessageSquare, Mail, Search, Users,
  Heart, AtSign, Zap, CheckCircle2, Clock,
  Star, Mic2, CalendarCheck, Tag, Phone, Database, Bell, StopCircle
} from "lucide-react"

import { usePickerStore } from "./EISequenceTree"

import { useHRTreeStore } from "@campaigns/eiTreeStore"
import { HR_NODE_DEFS } from "@/lib/eiNodeDefs"

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
const VARIABLES = [
  { label: "First name", value: "{{first_name}}" },
  { label: "Last name", value: "{{last_name}}" },
  { label: "Company", value: "{{company}}" },
  { label: "Job title", value: "{{job_title}}" },
  { label: "Location", value: "{{location}}" },
  { label: "Industry", value: "{{industry}}" },
  { label: "Mutual connections", value: "{{mutual_connections}}" },
]

function NakedVariableWarning({ text }: { text: string }) {
  if (!text.includes('{{')) return null;
  if (text.includes('| fallback:')) return null;
  
  const match = text.match(/{{([a-zA-Z0-9_]+)\s*}}/);
  const varName = match ? match[1] : "variable";
  
  return (
    <div className="mt-3 p-3 rounded-xl bg-primary/10 border border-primary/20 text-xs text-amber-600 dark:text-primary flex items-start gap-2 leading-relaxed shadow-sm">
      <span className="shrink-0 mt-0.5">⚠️</span>
      <div className="flex flex-col gap-1">
        <span className="font-bold">Missing Fallback on {"{{"}{varName}{"}}"}</span>
        <span className="text-amber-700/80 dark:text-primary/80/90 text-[11px]">
          Even with a valid LinkedIn URL, this data can be blocked by privacy walls (3rd-degree connections) or left blank by the user. If we can't scrape it, your message will fail to send to protect your reputation.
        </span>
        <span className="mt-1 font-medium text-[11px]">
          Fix: Add a pipe and a fallback word. Example: <strong>{"{{"}{varName} | fallback: there{"}}"}</strong>
        </span>
      </div>
    </div>
  )
}

// ─── Delay selector ───────────────────────────────────────────────────────────
function DelaySelector({ value, unit = "days", onChange }: { value: number; unit?: string; onChange: (v: number, u: string) => void }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <Clock size={13} className="text-muted-foreground shrink-0" />
        <span className="text-xs text-muted-foreground">Wait</span>
        <input
          type="number"
          min={1}
          step="1"
          value={value}
          onChange={e => {
            const val = parseFloat(e.target.value);
            const clamped = isNaN(val) ? 1 : Math.max(1, Math.ceil(val));
            onChange(clamped, unit);
          }}
          className="w-16 rounded-lg bg-card border border-border px-2 py-1.5 text-xs text-foreground focus:outline-none focus:border-indigo-600 text-center"
        />
        <div className="relative">
          <select 
            value={unit} 
            onChange={e => onChange(value, e.target.value)}
            className="appearance-none rounded-lg bg-card border border-border pl-2 pr-6 py-1.5 text-xs text-foreground focus:outline-none focus:border-indigo-600"
          >
            <option value="minutes">Minutes</option>
            <option value="hours">Hours</option>
            <option value="days">Days</option>
            <option value="weeks">Weeks</option>
          </select>
          <div className="absolute right-1.5 top-1/2 -translate-y-1/2 pointer-events-none text-muted-foreground">
            <ChevronDown size={12} />
          </div>
        </div>
        <span className="text-xs text-muted-foreground">before this step</span>
      </div>
      {value < 1 && (
        <div className="text-[10px] text-red-500 font-medium border border-red-500/50 p-2 rounded bg-red-500/10 mt-1">
          ⚠️ Minimum delay is 1 day. A 0-day delay will blast your account and trigger LinkedIn spam detection.
        </div>
      )}
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
  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setShowVars(false)
    }
    if (showVars) document.addEventListener("keydown", handleKeyDown)
    return () => document.removeEventListener("keydown", handleKeyDown)
  }, [showVars])

    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowVars(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [dropdownRef])

  const insertVar = (varStr: string) => {
    onChange((value || "") + varStr)
    setShowVars(false)
  }

  const previewText = (value || "")
    .replace(/{{first_name}}/g, "Alex")
    .replace(/{{last_name}}/g, "Johnson")
    .replace(/{{company}}/g, "Acme Corp")
    .replace(/{{job_title}}/g, "VP of Engineering")
    .replace(/{{location}}/g, "San Francisco, CA")
    .replace(/{{industry}}/g, "SaaS / B2B")
    .replace(/{{mutual_connections}}/g, "3")

  const charsLeft = maxChars - (value?.length || 0)

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <label className="text-xs font-semibold text-foreground">{label}</label>
      </div>

      {showPreview ? (
        <div className="w-full rounded-xl bg-indigo-950/20 border border-indigo-500/30 px-3.5 py-3 text-xs text-foreground leading-relaxed whitespace-pre-wrap min-h-[92px]">
          {previewText || <span className="text-muted-foreground italic">No message yet</span>}
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
                     placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none transition-colors leading-relaxed"
        />
      )}
      
      <NakedVariableWarning text={value || ""} />

      <div className="flex items-center justify-between mt-1">
        <span className={`text-[10px] ${charsLeft < 50 ? "text-red-400" : "text-muted-foreground"}`}>
          {charsLeft} characters left
        </span>
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-2 mt-2">
        <div className="relative flex-1" ref={dropdownRef}>
          <button
            onClick={() => setShowVars(p => !p)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border
                       bg-card hover:bg-muted text-xs text-muted-foreground transition-all w-full justify-between"
          >
            <span className="flex items-center gap-1.5"><span>✦</span> Add variables</span>
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
                    onClick={() => insertVar(v.value)}
                    className="w-full flex items-center justify-between px-3 py-2.5 text-xs hover:bg-muted transition-colors"
                  >
                    <span className="text-foreground whitespace-nowrap mr-2">{v.label}</span>
                    <span className="text-muted-foreground font-mono text-[10px] truncate">{v.value}</span>
                  </button>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <button
          onClick={() => setShowPreview(p => !p)}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs transition-all ${
            showPreview
              ? "border-indigo-600 bg-indigo-950/30 text-indigo-300"
              : "border-border bg-card hover:bg-muted text-muted-foreground"
          }`}
        >
          <Eye size={12} /> {showPreview ? "Edit" : "Preview"}
        </button>
      </div>
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
        <DelaySelector value={data.delay !== undefined ? Math.max(1, data.delay) : 1} unit={data.delayUnit || "days"} onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }} />
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
  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Delay</label>
        <DelaySelector value={data.delay !== undefined ? Math.max(1, data.delay) : 1} unit={data.delayUnit || "days"} onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }} />
      </div>
      <MessageEditor
        label="Message"
        value={data.body || ""}
        onChange={v => onChange("body", v)}
        maxChars={8000}
        placeholder="Write a message"
      />
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
// ─── Node-specific config panels ──────────────────────────────────────────────
// ─── Node-specific config panels ──────────────────────────────────────────────
function ConnectionRequestConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  const note: string = data.note || ""
  const charsLeft = 300 - note.length
  const [showVars, setShowVars] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

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
    onChange("note", note + v)
    setShowVars(false)
  }

  const rootNodes = useHRTreeStore(s => s.rootNodes);
  const hasManualWithdraw = hasNodeType(rootNodes, "withdraw_request");

  return (
    <div className="space-y-6">
      {/* Delay */}
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Delay</label>
        <DelaySelector value={data.delay !== undefined ? Math.max(1, data.delay) : 1} unit={data.delayUnit || "days"} onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }} />
      </div>

      {/* Withdraw toggle */}
      <div className="p-4 rounded-xl bg-background border border-border space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1">
            <p className="text-xs font-semibold text-white mb-0.5 flex items-center gap-1.5">
              <RotateCcw size={11} className="text-muted-foreground" /> Withdraw connection request
            </p>
            <p className="text-[10px] text-muted-foreground leading-relaxed">
              Auto-withdraw the invite if not accepted after N days. Helps keep your pending list clean.
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

      {/* Note */}
      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">Connection request note</label>
        <p className="text-[10px] text-muted-foreground mb-2 leading-relaxed flex items-start gap-1.5">
          <Info size={11} className="shrink-0 mt-0.5 text-muted-foreground" />
          LinkedIn limits personalized connection invites on non-premium accounts. When an account reaches its limit, we'll still send the invite — just without the note.
        </p>
        <textarea
          maxLength={300}
          value={note}
          onChange={e => onChange("note", e.target.value)}
          rows={4}
          placeholder={`Hi {{first_name}}, I noticed your work at {{company}} and would love to connect!`}
          className="w-full rounded-xl bg-card border border-border px-3.5 py-3 text-xs text-foreground
                     placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none leading-relaxed"
        />
        
        <NakedVariableWarning text={note || ""} />
        
        <div className="flex flex-col mt-1">
          <div className="flex items-center justify-between">
            <span className={`text-[10px] ${note.length > 300 ? "text-red-500" : "text-muted-foreground"}`}>
              {note.length} / 300
            </span>
          </div>
          {note.length > 300 && (
            <span className="text-[10px] text-red-500 font-medium mt-1">
              Connection requests cannot exceed 300 characters.
            </span>
          )}
        </div>

        {/* Vars */}
        <div className="flex items-center gap-2 mt-2">
          <div className="relative flex-1" ref={dropdownRef}>
            <button
              onClick={() => setShowVars(p => !p)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border bg-card hover:bg-muted text-xs text-muted-foreground transition-all w-full justify-between"
            >
              <span className="flex items-center gap-1.5"><span>✦</span> Add variables</span>
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
                    <button key={v.value} onClick={() => insertVar(v.value)}
                      className="w-full flex items-center justify-between px-3 py-2.5 text-xs hover:bg-muted transition-colors">
                      <span className="text-foreground whitespace-nowrap mr-2">{v.label}</span>
                      <span className="text-muted-foreground font-mono text-[10px] truncate">{v.value}</span>
                    </button>
                  ))}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>

      <FallbackEditor data={data} onChange={onChange} maxChars={300} fallbackLabel="Fallback connection note" />
    </div>
  )
}
function SendInMailConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Delay</label>
        <DelaySelector value={data.delay !== undefined ? Math.max(1, data.delay) : 1} unit={data.delayUnit || "days"} onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }} />
      </div>
      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">Subject line</label>
        <input
          value={data.subject || ""}
          onChange={e => onChange("subject", e.target.value)}
          placeholder="e.g. Quick thought on {{company}}"
          className="w-full rounded-lg bg-card border border-border px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
        <NakedVariableWarning text={data.subject || ""} />
      </div>
      <MessageEditor
        label="Body"
        value={data.body || ""}
        onChange={v => onChange("body", v)}
        maxChars={1900}
        placeholder="Hi {{first_name}}, ..."
      />
    </div>
  )
}

function SimpleDelayConfig({ data, onChange, label }: { data: any; onChange: (k: string, v: any) => void; label: string }) {
  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Delay</label>
        <DelaySelector value={data.delay !== undefined ? Math.max(1, data.delay) : 1} unit={data.delayUnit || "days"} onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }} />
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

function ConditionConfig({ data, onChange, label }: { data: any; onChange: (k: string, v: any) => void; label: string }) {
  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Check after delay</label>
        <DelaySelector value={data.delay !== undefined ? Math.max(1, data.delay) : 1} unit={data.delayUnit || "days"} onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }} />
      </div>
      <div className="p-4 rounded-xl bg-background border border-border">
        <p className="text-xs text-muted-foreground leading-relaxed">
          <strong className="text-foreground">{label}</strong> — the sequence will branch into two paths based on the result.
        </p>
        <div className="flex items-center gap-3 mt-3">
          <span className="text-[10px] font-bold text-emerald-400 bg-emerald-950/40 px-2.5 py-1 rounded-full border border-emerald-800/40">✓ Yes path</span>
          <span className="text-[10px] font-bold text-red-400 bg-red-950/40 px-2.5 py-1 rounded-full border border-red-800/40">✗ No path</span>
        </div>
      </div>
    </div>
  )
}

function MultichannelConfig({ data, onChange, platform }: { data: any; onChange: (k: string, v: any) => void; platform: string }) {
  return (
    <div className="space-y-6">
      <div className="p-4 rounded-xl bg-background border border-border">
        <p className="text-xs text-muted-foreground leading-relaxed">
          Lead will be added to a <strong className="text-foreground">{platform}</strong> campaign. Configure your {platform} integration in Settings first.
        </p>
      </div>
      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5">{platform} Campaign ID</label>
        <input
          value={data.campaign_id || ""}
          onChange={e => onChange("campaign_id", e.target.value)}
          placeholder={`Enter ${platform} campaign ID`}
          className="w-full rounded-lg bg-card border border-border px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
        />
      </div>
    </div>
  )
}

function SendVoiceNoteConfig({ data, onChange }: { data: any; onChange: (k: string, v: any) => void }) {
  const [errorMsg, setErrorMsg] = useState("");
  const [warningMsg, setWarningMsg] = useState("");
  const [isValid, setIsValid] = useState(false);

  const validateUrl = async (url: string) => {
    setErrorMsg("");
    setWarningMsg("");
    setIsValid(false);

    if (!url) return;

    if (!url.startsWith("https://")) {
      setErrorMsg("Must be a direct link to an audio file (mp3, wav, etc.). Paste a direct download URL, not a browser page link.");
      return;
    }

    const validExts = [".mp3", ".mp4", ".wav", ".ogg", ".m4a", ".webm"];
    const validCDNs = ["drive.google.com", "dropbox.com", "loom.com"];
    
    let hasValidExt = false;
    try {
      const parsedUrl = new URL(url);
      hasValidExt = validExts.some(ext => parsedUrl.pathname.toLowerCase().endsWith(ext));
    } catch {
      const lowerUrl = url.toLowerCase();
      hasValidExt = validExts.some(ext => lowerUrl.endsWith(ext) || lowerUrl.includes(ext + "?"));
    }
    
    const lowerUrl = url.toLowerCase();
    const hasValidCDN = validCDNs.some(cdn => lowerUrl.includes(cdn));

    if (!hasValidExt && !hasValidCDN) {
      setErrorMsg("Must be a direct link to an audio file (mp3, wav, etc.). Paste a direct download URL, not a browser page link.");
      return;
    }

    setIsValid(true);

    try {
      await fetch(url, { method: "HEAD", mode: "no-cors" });
    } catch (e) {
      setWarningMsg("Could not verify this URL is reachable. Double-check it before saving.");
      setIsValid(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-xs font-semibold text-foreground mb-2">Delay</label>
        <DelaySelector value={data.delay !== undefined ? Math.max(1, data.delay) : 1} unit={data.delayUnit || "days"} onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }} />
      </div>
      <div>
        <label className="block text-xs font-semibold text-foreground mb-1.5 flex items-center justify-between">
          <span>Audio file URL</span>
          {isValid && !warningMsg && !errorMsg && <CheckCircle2 size={14} className="text-emerald-500" />}
        </label>
        <input 
          value={data.audio_url || ""} 
          onChange={e => {
            onChange("audio_url", e.target.value);
            setErrorMsg("");
            setWarningMsg("");
            setIsValid(false);
          }}
          onBlur={(e) => validateUrl(e.target.value)}
          placeholder="https://... (mp3/wav, max 5min)"
          className="w-full rounded-lg bg-card border border-border px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600" 
        />
        {errorMsg && <p className="text-red-500 text-[10px] mt-1">{errorMsg}</p>}
        {warningMsg && <p className="text-primary text-[10px] mt-1">{warningMsg}</p>}
      </div>
      <div className="p-3 rounded-xl bg-indigo-950/20 border border-indigo-800/30">
        <p className="text-xs text-indigo-300">💡 Voice notes have 3× higher reply rates than text messages. Pre-record a personal 60-second pitch and upload it here.</p>
      </div>
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
    color: "#8b5cf6",
    render: (data, onChange) => <SimpleDelayConfig data={data} onChange={onChange} label="visit the lead's LinkedIn profile (creates a 'viewed your profile' notification)" />,
  },
  follow_profile: {
    title: "Follow Profile",
    icon: Users,
    color: "#8b5cf6",
    render: (data, onChange) => <SimpleDelayConfig data={data} onChange={onChange} label="follow the lead's profile to create a follow notification" />,
  },
  like_post: {
    title: "Like Recent Post",
    icon: Heart,
    color: "#8b5cf6",
    render: (data, onChange) => <SimpleDelayConfig data={data} onChange={onChange} label="like the lead's most recent LinkedIn post" />,
  },
  endorse_skill: {
    title: "Endorse a Skill",
    icon: Star,
    color: "#8b5cf6",
    render: (data, onChange) => <SimpleDelayConfig data={data} onChange={onChange} label="endorse one of the lead's top skills — creates a strong notification" />,
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
    render: (data, onChange) => <ConditionConfig data={data} onChange={onChange} label="Did the lead accept your connection request?" />,
  },
  if_replied: {
    title: "If Replied?",
    icon: MessageSquare,
    color: "#10b981",
    render: (data, onChange) => <ConditionConfig data={data} onChange={onChange} label="Did the lead reply to your last message?" />,
  },
  if_email_found: {
    title: "If Email Found?",
    icon: AtSign,
    color: "#10b981",
    render: (data, onChange) => <ConditionConfig data={data} onChange={onChange} label="Did enrichment return a valid email address?" />,
  },
/*
  if_meeting_booked: {
    title: "If Meeting Booked?",
    icon: CalendarCheck,
    color: "#10b981",
    render: (data, onChange) => <ConditionConfig data={data} onChange={onChange} label="Did the lead click your link and book a meeting?" />,
  },
*/
  open_profile_check: {
    title: "Open Profile Check",
    icon: Search,
    color: "#10b981",
    render: (data, onChange) => <ConditionConfig data={data} onChange={onChange} label="Is the lead's profile open to InMail without connecting?" />,
  },
if_large_following: {
    title: "If High Follower Count?",
    icon: Users,
    color: "#10b981",
    render: (data, onChange) => (
      <div className="space-y-6">
        <div className="p-4 rounded-xl bg-background border border-border">
          <p className="text-xs text-muted-foreground leading-relaxed">
            Checks if the lead's follower count exceeds your threshold. Routes to a high-following path.
          </p>
          <div className="flex items-center gap-3 mt-3">
            <span className="text-[10px] font-bold text-emerald-400 bg-emerald-950/40 px-2.5 py-1 rounded-full border border-emerald-800/40">✓ High following</span>
            <span className="text-[10px] font-bold text-red-400 bg-red-950/40 px-2.5 py-1 rounded-full border border-red-800/40">✗ Normal following</span>
          </div>
        </div>
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">Follower threshold</label>
          <input
            type="number"
            value={data.follower_threshold || 10000}
            onChange={e => onChange("follower_threshold", Number(e.target.value))}
            className="w-full rounded-lg bg-card border border-border px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600"
          />
        </div>
      </div>
    ),
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
    render: (data, onChange) => <SendMessageConfig data={data} onChange={onChange} />,
  },
  send_message_with_image: {
    title: "Send Message + Image",
    icon: MessageSquare,
    color: "#6366f1",
    render: (data, onChange) => <SendMessageConfig data={data} onChange={onChange} />,
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
  // ── Convert ────────────────────────────────────────────────────────────────
  send_meeting_invite: {
    title: "Send Meeting Invite",
    icon: CalendarCheck,
    color: "#f59e0b",
    render: (data, onChange) => (
      <div className="space-y-6">
        <div><label className="block text-xs font-semibold text-foreground mb-2">Delay</label><DelaySelector value={data.delay !== undefined ? Math.max(1, data.delay) : 1} unit={data.delayUnit || "days"} onChange={(v, u) => { onChange("delay", v); onChange("delayUnit", u); }} /></div>
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">Calendly / Booking URL</label>
          <input value={data.calendly_url || ""} onChange={e => onChange("calendly_url", e.target.value)}
            placeholder="https://calendly.com/your-link"
            className="w-full rounded-lg bg-card border border-border px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600" />
        </div>
        <MessageEditor label="Message body" value={data.body || ""} onChange={v => onChange("body", v)} maxChars={8000} placeholder="Hey {{first_name}}, would love to show you what we do..." />
        <div className="p-3 rounded-xl bg-amber-950/20 border border-amber-800/30">
          <p className="text-xs text-amber-300">📅 If the lead books, all subsequent steps in this path will stop automatically.</p>
        </div>
      </div>
    ),
  },
  mark_converted: {
    title: "Mark as Converted",
    icon: Tag,
    color: "#f59e0b",
    render: (data, onChange) => (
      <div className="space-y-6">
        <div className="p-3 rounded-xl bg-amber-950/20 border border-amber-800/30">
          <p className="text-xs text-amber-300">✅ Ends this sequence path and marks the lead as converted. No further steps will run.</p>
        </div>
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">CRM tag</label>
          <input value={data.tag || ""} onChange={e => onChange("tag", e.target.value)}
            placeholder="e.g. meeting_booked"
            className="w-full rounded-lg bg-card border border-border px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600" />
        </div>
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">Internal note <span className="text-muted-foreground font-normal">(optional)</span></label>
          <textarea value={data.note || ""} onChange={e => onChange("note", e.target.value)} rows={3}
            placeholder="Optional note for your CRM records..."
            className="w-full rounded-xl bg-card border border-border px-3.5 py-3 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none" />
        </div>
      </div>
    ),
  },
  // ── Enrichment ─────────────────────────────────────────────────────────────
  find_email: {
    title: "Find Email",
    icon: AtSign,
    color: "#f59e0b",
    render: (data, onChange) => <SimpleDelayConfig data={data} onChange={onChange} label="run waterfall enrichment (Apollo → Hunter → Clearbit) to find a verified email. Costs 1 credit per found lead." />,
  },
  find_phone: {
    title: "Find Phone Number",
    icon: Phone,
    color: "#f59e0b",
    render: (data, onChange) => <SimpleDelayConfig data={data} onChange={onChange} label="enrich a mobile or direct-dial phone number from Apollo / PDL for SDR follow-up." />,
  },
  // ── Multichannel ──────────────────────────────────────────────────────────
  add_to_smartlead: {
    title: "Add to Smartlead",
    icon: Zap,
    color: "#ec4899",
    render: (data, onChange) => <MultichannelConfig data={data} onChange={onChange} platform="Smartlead" />,
  },
  add_to_instantly: {
    title: "Add to Instantly",
    icon: Zap,
    color: "#ec4899",
    render: (data, onChange) => <MultichannelConfig data={data} onChange={onChange} platform="Instantly" />,
  },
  add_to_emailbison: {
    title: "Add to EmailBison",
    icon: Zap,
    color: "#ec4899",
    render: (data, onChange) => <MultichannelConfig data={data} onChange={onChange} platform="EmailBison" />,
  },
  push_to_crm: {
    title: "Push to CRM",
    icon: Database,
    color: "#ec4899",
    render: (data, onChange) => (
      <div className="space-y-5">
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">CRM</label>
          <div className="relative">
            <select value={data.crm || ""} onChange={e => onChange("crm", e.target.value)}
              className="appearance-none w-full rounded-lg bg-card border border-border pl-3 pr-8 py-2.5 text-xs text-foreground focus:outline-none focus:border-indigo-600">
              <option value="">Select CRM</option>
              {["HubSpot", "Salesforce", "Pipedrive", "Notion CRM"].map(c => <option key={c}>{c}</option>)}
            </select>
            <div className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none text-muted-foreground">
              <ChevronDown size={14} />
            </div>
          </div>
        </div>
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">Pipeline stage</label>
          <input value={data.stage || ""} onChange={e => onChange("stage", e.target.value)}
            placeholder="e.g. New Lead / Warm / Demo Requested"
            className="w-full rounded-lg bg-card border border-border px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600" />
        </div>
      </div>
    ),
  },
  send_slack_alert: {
    title: "Send Slack Alert",
    icon: Bell,
    color: "#ec4899",
    render: (data, onChange) => (
      <div className="space-y-5">
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">Slack channel</label>
          <input value={data.channel || ""} onChange={e => onChange("channel", e.target.value)}
            placeholder="#sales-signals"
            className="w-full rounded-lg bg-card border border-border px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600" />
        </div>
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">Alert message</label>
          <textarea value={data.message || ""} onChange={e => onChange("message", e.target.value)} rows={4}
            placeholder="🔥 {{first_name}} from {{company}} replied to your LinkedIn sequence!"
            className="w-full rounded-xl bg-card border border-border px-3.5 py-3 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-indigo-600 resize-none" />
          <NakedVariableWarning text={data.message || ""} />
        </div>
      </div>
    ),
  },
  // ── Control ────────────────────────────────────────────────────────────────
  sequence_end: {
    title: "Sequence End",
    icon: StopCircle,
    color: "#52525b",
    render: (data, onChange) => (
      <div className="space-y-5">
        <div>
          <label className="block text-xs font-semibold text-foreground mb-1.5">Exit reason</label>
          <div className="relative">
            <select value={data.exit_reason || ""} onChange={e => onChange("exit_reason", e.target.value)}
              className="appearance-none w-full rounded-lg bg-card border border-border pl-3 pr-8 py-2.5 text-xs text-foreground focus:outline-none focus:border-indigo-600">
              <option value="">Select a reason</option>
              {["unresponsive", "not_interested", "meeting_booked", "replied_positive", "replied_negative", "opted_out", "other"].map(r =>
                <option key={r} value={r}>{r.replace(/_/g, " ")}</option>)}
            </select>
            <div className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none text-muted-foreground">
              <ChevronDown size={14} />
            </div>
          </div>
        </div>
        <div className="p-3 rounded-xl bg-background border border-border">
          <p className="text-xs text-muted-foreground">This marks a terminal state for this path. Analytics will track exit reason breakdowns per campaign.</p>
        </div>
      </div>
    ),
  },
  withdraw_request: {
    title: "Withdraw Request",
    icon: RotateCcw,
    color: "#f59e0b",
    render: (data, onChange) => {
      const rootNodes = useHRTreeStore(s => s.rootNodes);
      const hasAuto = hasAutoWithdrawConnection(rootNodes);
      
      return (
        <div className="space-y-6">
          <SimpleDelayConfig data={data} onChange={onChange} label="withdraw the pending connection request" />
          {hasAuto && (
            <div className="p-3 bg-primary/10 border border-primary/20 rounded-xl text-xs text-primary mt-4">
              Warning: A connection node in this sequence has auto-withdraw enabled. This Withdraw node is redundant and will be ignored by the validator.
            </div>
          )}
        </div>
      );
    }
  },
}

// ─── Nodal Guide Recommendations ────────────────────────────────────────────────
const NODAL_GUIDE: Record<string, string> = {
  "linkedin_view": "The most logical next step is to add a Wait delay, then a Connect node.",
  "linkedin_connect": "The most logical next step is an 'If Connected' conditional node.",
  "linkedin_message": "The most logical next step is an 'If Replied' conditional node.",
  "linkedin_like": "The most logical next step is a View Profile or Connect node.",
  "linkedin_inmail": "The most logical next step is an 'If Replied' conditional node.",
  "condition_connected": "Add a Message node in the YES path, and a View Profile or Connect follow-up in the NO path.",
  "condition_replied": "Add a Goal/Success node in the YES path, and a follow-up Message in the NO path.",
  "goal": "This is a terminal node. The sequence ends here."
}

// ─── Main panel ───────────────────────────────────────────────────────────────
export function EINodeConfigPanel() {
  const { selectedNodeId, rootNodes, updateNodeData, selectNode } = useHRTreeStore()

  
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
  const config = NODE_CONFIG[nodeType]

  if (!config) return null

  const onChange = (key: string, value: any) => {
    updateNodeData(selectedNode.id, { [key]: value })
  }

  const handleSave = () => {
    selectNode(null)
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
        className="absolute right-0 top-0 bottom-0 w-[400px] bg-background border-l border-border z-30 flex flex-col shadow-2xl"
      >
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-border shrink-0">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
            style={{ background: `${config.color}22`, border: `1px solid ${config.color}44` }}
          >
            <Icon size={15} style={{ color: config.color }} />
          </div>
          <p className="text-sm font-bold text-white flex-1">{config.title}</p>
          <button
            onClick={() => selectNode(null)}
            className="text-muted-foreground hover:text-white transition-colors p-1"
          >
            <X size={16} />
          </button>
        </div>

        {/* Guidance Banner */}
        <div className="px-5 py-4 bg-card/40 border-b border-border flex items-start gap-3 shrink-0">
          <Info size={16} className="text-indigo-400 mt-0.5 shrink-0" />
          <div>
            <p className="text-xs text-foreground leading-relaxed font-medium mb-1">
              {HR_NODE_DEFS[nodeType as keyof typeof HR_NODE_DEFS]?.description || "Configure this step."}
            </p>
            {NODAL_GUIDE[nodeType] && (
              <p className="text-[11px] text-muted-foreground leading-relaxed">
                <span className="text-indigo-400/80 font-semibold">💡 Pro Tip:</span> {NODAL_GUIDE[nodeType]}
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
          <button
            onClick={handleSave}
            className="px-5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-xs font-bold text-white transition-all"
          >
            Save
          </button>
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
      
      {def.fields?.map((f: any) => {
        if (f.showIf) {
            const [depKey, depVal] = f.showIf.split("==");
            const targetField = def.fields.find((df: any) => df.key === depKey);
            const currentVal = data[depKey] !== undefined ? data[depKey] : (targetField?.default || targetField?.options?.[0]);
            if (String(currentVal) !== String(depVal)) return null;
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
            <div className="relative">
              <select
                value={data[f.key] !== undefined ? data[f.key] : (f.default || "")}
                onChange={e => onChange(f.key, e.target.value)}
                className="appearance-none w-full rounded-lg bg-card border border-border pl-3 pr-8 py-2.5 text-xs text-foreground focus:outline-none focus:border-indigo-600 transition-colors"
              >
                {f.options?.map((opt: string) => (
                  <option key={opt} value={opt}>{opt}</option>
                ))}
              </select>
              <div className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none text-muted-foreground">
                <ChevronDown size={14} />
              </div>
            </div>
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
      })}
      
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
        <div className="flex items-center gap-3 px-5 py-4 border-b border-border shrink-0">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
            style={{ background: `${config.color}15`, border: `1px solid ${config.color}30` }}
          >
            <Icon size={15} style={{ color: config.color }} />
          </div>
          <p className="text-sm font-bold text-foreground flex-1">{config.title}</p>
          <button onClick={() => selectNode(null)} className="text-muted-foreground hover:text-foreground transition-colors p-1">
            <X size={16} />
          </button>
        </div>



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
          <button
            onClick={() => selectNode(null)}
            className="px-5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-xs font-bold text-white transition-all"
          >
            Save
          </button>
        </div>
      </motion.div>
    </AnimatePresence>
  )
}
