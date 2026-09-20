import { memo, useState } from "react"
import { Handle, Position, type NodeProps } from "@xyflow/react"
import {
  UserPlus, MessageSquare, Eye, Heart, Users, Mail,
  AtSign, Zap, CheckCircle2, Search,
  PlayCircle, StopCircle, Clock, Trash2, ChevronDown, ChevronUp,
  Phone, CalendarCheck, Star, Mic2, Tag, Bell,
  Database
} from "lucide-react"
import { useHRSequenceStore } from "@campaigns/eiSequenceStore"
import SpotlightCard from "../SpotlightCard"
import ShinyText from "../ShinyText"
const NODE_ICONS: Record<string, any> = {
  // Warmup
  view_profile:         Eye,
  follow_profile:       Users,
  like_post:            Heart,
  endorse_skill:        Star,
  // Connect
  connection_request:   UserPlus,
  // Conditions
  if_connected:         CheckCircle2,
  if_replied:           MessageSquare,
  if_email_found:       AtSign,
  // if_meeting_booked:    CalendarCheck,
  open_profile_check:   Search,
  // Messages
  send_message:         MessageSquare,
  send_voice_note:      Mic2,
  send_inmail:          Mail,
  // Convert
  send_meeting_invite:  CalendarCheck,
  mark_converted:       Tag,
  // Enrichment
  find_email:           AtSign,
  find_phone:           Phone,
  // Multichannel
  add_to_smartlead:     Zap,
  add_to_instantly:     Zap,
  add_to_emailbison:    Zap,
  push_to_crm:          Database,
  send_slack_alert:     Bell,
  // Control
  sequence_end:         StopCircle,
  start:                PlayCircle,
}

// Category → color map (matches eiNodeDefs)
const CATEGORY_COLORS: Record<string, string> = {
  warmup:       "#8b5cf6",
  connect:      "#6366f1",
  conditions:   "#10b981",
  messages:     "#6366f1",
  convert:      "#f59e0b",
  enrichment:   "#f59e0b",
  multichannel: "#ec4899",
  control:      "#52525b",
}

// Node type → category (for color lookup)
const NODE_CATEGORY: Record<string, string> = {
  view_profile: "warmup", follow_profile: "warmup", like_post: "warmup", endorse_skill: "warmup",
  connection_request: "connect",
  if_connected: "conditions", if_replied: "conditions", if_email_found: "conditions",
  // if_meeting_booked: "conditions", open_profile_check: "conditions",
  send_message: "messages", send_voice_note: "messages", send_inmail: "messages",
  send_meeting_invite: "convert", mark_converted: "convert",
  find_email: "enrichment", find_phone: "enrichment",
  add_to_smartlead: "multichannel", add_to_instantly: "multichannel",
  add_to_emailbison: "multichannel", push_to_crm: "multichannel", send_slack_alert: "multichannel",
  sequence_end: "control", start: "control",
}

export const EINode = memo(function EINode({ id, data, selected }: NodeProps) {
  const { deleteNode, selectNode } = useHRSequenceStore()
  const d = data as any
  const nodeType: string = d.type || "send_message"
  const Icon = NODE_ICONS[nodeType] || MessageSquare
  const category = NODE_CATEGORY[nodeType] || "messages"
  const color: string = d.color || CATEGORY_COLORS[category] || "#6366f1"
  const outputs: string[] = d.outputs || ["output"]
  const isStart = nodeType === "start"
  const isEnd = nodeType === "sequence_end" || nodeType === "mark_converted"
  const isCondition = outputs.length > 1
  const [showMsg, setShowMsg] = useState(false)

  return (
    <SpotlightCard
      onClick={() => selectNode(id)}
      style={{ borderColor: selected ? color : "rgba(255,255,255,0.1)" }}
      className="!p-0 relative group min-w-[210px] max-w-[250px] !rounded-2xl !bg-zinc-900/80 backdrop-blur-md border transition-all duration-300 cursor-pointer select-none shadow-xl hover:shadow-2xl hover:!border-white/20 hover:-translate-y-0.5"
     
    >
      {/* Delete button */}
      {!isStart && (
        <button
          onClick={(e) => { e.stopPropagation(); deleteNode(id) }}
          className="absolute -top-2.5 -right-2.5 z-20 hidden group-hover:flex items-center justify-center
                     w-5 h-5 rounded-full bg-zinc-900/90 backdrop-blur-sm border border-white/10 hover:border-red-500/50 hover:bg-red-500/10
                     hover:text-red-400 text-zinc-500 transition-all shadow-sm"
        >
          <Trash2 size={9} />
        </button>
      )}

      {/* Input handle */}
      {!isStart && (
        <Handle
          type="target"
          position={Position.Top}
          className="!w-3.5 !h-3.5 !bg-zinc-950 !border-[1.5px] !rounded-full hover:!scale-125 transition-transform shadow-md"
          style={{ borderColor: color }}
        />
      )}

      {/* Body */}
      <div className="p-3.5">
        {/* Delay badge */}
        {d.delay != null && d.delay > 0 && (
          <div className="flex items-center gap-1 mb-2.5 px-2 py-0.5 rounded-md bg-white/5 backdrop-blur-sm border border-white/10 w-fit shadow-sm">
            <Clock size={9} className="text-zinc-500" />
            <span className="text-[9px] text-zinc-400 font-mono">Wait {d.delay}d, then</span>
          </div>
        )}

        {/* Header */}
        <div className="flex items-center gap-2.5">
          <div
            className="w-8 h-8 rounded-xl flex items-center justify-center shrink-0"
            style={{ background: `${color}20`, border: `1.5px solid ${color}50` }}
          >
            <Icon size={14} style={{ color }} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[11px] font-bold text-white truncate leading-tight">
              <ShinyText text={d.label} speed={3} />
            </div>
            <p className="text-[9px] text-zinc-500 mt-0.5 truncate">{d.description?.slice(0, 50)}</p>
          </div>
        </div>

        {/* Message preview */}
        {(d.note || d.body) && (
          <div className="mt-2.5 border-t border-zinc-800/60 pt-2">
            <button
              onClick={(e) => { e.stopPropagation(); setShowMsg(p => !p) }}
              className="flex items-center gap-1 text-[9px] text-zinc-600 hover:text-zinc-400 transition-colors"
            >
              {showMsg ? <ChevronUp size={8} /> : <ChevronDown size={8} />}
              {showMsg ? "Hide" : "View"} message
            </button>
            {showMsg && (
              <p className="mt-1.5 text-[10px] text-zinc-400 leading-relaxed p-2 rounded-lg bg-white/5 backdrop-blur-sm border border-white/10 line-clamp-3 shadow-inner">
                {d.note || d.body}
              </p>
            )}
          </div>
        )}

        {/* Withdraw badge */}
        {d.withdraw_enabled && d.withdraw_days && (
          <div className="mt-2 flex items-center gap-1">
            <span className="text-[9px] text-zinc-500 bg-zinc-800 px-2 py-0.5 rounded border border-zinc-700">
              ↩ withdraw after {d.withdraw_days}d
            </span>
          </div>
        )}
      </div>

      {/* Output handles */}
      {!isEnd && (
        isCondition ? (
          <div className="flex justify-around border-t border-zinc-800/60 pt-2 pb-3 px-3">
            {outputs.map((out: string, i: number) => {
              const outColor = i === 0 ? "#10b981" : "#f43f5e"
              return (
                <div key={out} className="flex flex-col items-center gap-1.5">
                  <span className="text-[8px] font-bold uppercase tracking-wider" style={{ color: outColor }}>
                    {i === 0 ? "✓" : "✗"} {out}
                  </span>
                  <Handle
                    type="source"
                    position={Position.Bottom}
                    id={out}
                    style={{
                      position: "relative",
                      transform: "none",
                      left: "auto",
                      bottom: "auto",
                      width: 14,
                      height: 14,
                      backgroundColor: "#09090b",
                      borderColor: outColor,
                      borderWidth: 1.5,
                      borderRadius: "50%",
                      boxShadow: "0 2px 4px rgba(0,0,0,0.2)"
                    }}
                  />
                </div>
              )
            })}
          </div>
        ) : (
          <Handle
            type="source"
            position={Position.Bottom}
            id="output"
            className="!w-3.5 !h-3.5 !bg-zinc-950 !border-[1.5px] !rounded-full hover:!scale-125 transition-transform shadow-md"
            style={{ borderColor: color }}
          />
        )
      )}
    </SpotlightCard>
  )
})

export const HR_NODE_TYPES = { eiNode: EINode }
