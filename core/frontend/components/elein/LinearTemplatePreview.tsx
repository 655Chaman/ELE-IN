import { type EITemplate } from "@/lib/eiTemplates"
import {
  Eye, UserPlus, MessageSquare, CheckCircle2, XCircle,
  Mail, ThumbsUp, UserCheck, Flag, Clock, StickyNote,
  ArrowDown
} from "lucide-react"
import { cn } from "@/lib/utils"

const NODE_TYPE_CONFIG: Record<string, { label: string; icon: React.ComponentType<{ size?: number; className?: string }>; color: string; bg: string }> = {
  start:              { label: "Sequence Start",       icon: Flag,           color: "text-indigo-400",  bg: "bg-indigo-500/10 border-indigo-500/30" },
  view_profile:       { label: "View Profile",         icon: Eye,            color: "text-violet-400",  bg: "bg-violet-500/10 border-violet-500/30" },
  follow_profile:     { label: "Follow Profile",       icon: UserCheck,      color: "text-purple-400",  bg: "bg-purple-500/10 border-purple-500/30" },
  connection_request: { label: "Connection Request",   icon: UserPlus,       color: "text-indigo-400",  bg: "bg-indigo-500/10 border-indigo-500/30" },
  if_connected:       { label: "If Connected",         icon: CheckCircle2,   color: "text-emerald-400", bg: "bg-emerald-500/10 border-emerald-500/30" },
  send_message:       { label: "Send Message",         icon: MessageSquare,  color: "text-blue-400",    bg: "bg-blue-500/10 border-blue-500/30" },
  send_inmail:        { label: "Send InMail",          icon: Mail,           color: "text-sky-400",     bg: "bg-sky-500/10 border-sky-500/30" },
  like_post:          { label: "Like Post",            icon: ThumbsUp,       color: "text-pink-400",    bg: "bg-pink-500/10 border-pink-500/30" },
  end:                { label: "Sequence End",         icon: XCircle,        color: "text-zinc-500",    bg: "bg-zinc-800/60 border-zinc-700/40" },
}

interface Props {
  template: EITemplate
}

function StepCard({ node, stickyNote, delay }: {
  node: any
  stickyNote?: { title: string; body: string; why: string }
  delay?: number
}) {
  const typeKey = (node.type || node.data?.type) as string
  let cfg = NODE_TYPE_CONFIG[typeKey]
  if (!cfg) {
    console.warn(`Unknown node type encountered: ${typeKey}. Falling back to send_message.`)
    cfg = NODE_TYPE_CONFIG["send_message"]
  }
  const Icon = cfg.icon
  const isEnd = typeKey === "end"
  const isStart = typeKey === "start"

  if (isEnd) {
    return (
      <div className="flex items-center gap-3 px-4 py-2 rounded-lg border border-zinc-800 bg-zinc-900/40">
        <XCircle size={13} className="text-zinc-600 shrink-0" />
        <span className="text-xs text-zinc-600 font-medium">Sequence ends here</span>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] overflow-hidden">
      {/* Step header */}
      <div className="flex items-start gap-3 p-4">
        <div className={cn("w-8 h-8 rounded-lg border flex items-center justify-center shrink-0 mt-0.5", cfg.bg)}>
          <Icon size={15} className={cfg.color} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={cn("text-[10px] font-bold uppercase tracking-widest", cfg.color)}>{cfg.label}</span>
            {delay !== undefined && delay > 0 && (
              <span className="flex items-center gap-1 text-[9px] text-zinc-500 bg-zinc-800/60 px-1.5 py-0.5 rounded">
                <Clock size={8} /> Wait {delay}d
              </span>
            )}
            {isStart && (
              <span className="text-[9px] text-indigo-400 bg-indigo-500/10 px-1.5 py-0.5 rounded">Entry point</span>
            )}
          </div>

          {/* Note / message body */}
          {node.data?.note && (
            <div className="mt-2 text-xs text-zinc-300 bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2.5 leading-relaxed whitespace-pre-wrap">
              <span className="text-[9px] text-zinc-500 font-semibold uppercase tracking-widest block mb-1.5">Connection note</span>
              {node.data.note}
            </div>
          )}
          {node.data?.body && (
            <div className="mt-2 text-xs text-zinc-300 bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2.5 leading-relaxed whitespace-pre-wrap">
              <span className="text-[9px] text-zinc-500 font-semibold uppercase tracking-widest block mb-1.5">Message body</span>
              {node.data.body}
            </div>
          )}
          {node.data?.subject && (
            <div className="mt-2 text-xs text-zinc-400 bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2">
              <span className="text-[9px] text-zinc-500 font-semibold uppercase tracking-widest block mb-1">Subject</span>
              {node.data.subject}
            </div>
          )}
        </div>
      </div>

      {/* Sticky note */}
      {stickyNote && (
        <div className="mx-4 mb-4 rounded-lg bg-primary/80/[0.07] border border-primary/80/20 px-3 py-2.5">
          <div className="flex items-center gap-1.5 mb-1.5">
            <StickyNote size={10} className="text-primary/80 shrink-0" />
            <span className="text-[10px] font-bold text-primary/80">{stickyNote.title}</span>
          </div>
          <p className="text-[11px] text-amber-200/80 leading-relaxed mb-1.5">{stickyNote.body}</p>
          <p className="text-[10px] text-primary/80/60 leading-relaxed">
            <span className="font-semibold text-primary/80/80">Why it works: </span>
            {stickyNote.why}
          </p>
        </div>
      )}
    </div>
  )
}

export function LinearTemplatePreview({ template }: Props) {
  // Build display order: start → middle steps → branch ends by Y position
  const orderedNodes = [...template.nodes].sort((a, b) => {
    const ay = a.position?.y ?? 0
    const by = b.position?.y ?? 0
    return ay - by
  })

  return (
    <div className="h-full overflow-y-auto px-5 py-5 space-y-2 scrollbar-thin scrollbar-track-transparent scrollbar-thumb-zinc-800">
      {/* Template header */}
      <div className="mb-5">
        <div className="flex items-center gap-2 flex-wrap mb-2">
          <span className={cn(
            "text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-widest",
            template.difficulty === "beginner" ? "bg-emerald-500/15 text-emerald-400" :
            template.difficulty === "intermediate" ? "bg-primary/15 text-primary/80" :
            "bg-rose-500/15 text-rose-400"
          )}>
            {template.difficulty}
          </span>
          {template.tags.map(tag => (
            <span key={tag} className="text-[9px] text-zinc-500 bg-zinc-800/60 px-1.5 py-0.5 rounded border border-zinc-700/40">
              {tag}
            </span>
          ))}
        </div>
        <p className="text-[11px] text-zinc-400 leading-relaxed mb-1">{template.description}</p>
        <p className="text-[10px] text-zinc-600">
          <span className="text-zinc-500 font-semibold">Best for: </span>
          {template.bestFor}
        </p>
      </div>

      {/* Stats bar */}
      <div className="flex items-center gap-4 p-3 rounded-lg bg-white/[0.02] border border-white/[0.05] mb-4">
        <div className="text-center">
          <p className="text-sm font-bold text-emerald-400">{template.connectionRate}%</p>
          <p className="text-[9px] text-zinc-500 uppercase tracking-widest">Accept rate</p>
        </div>
        <div className="w-px h-6 bg-zinc-800" />
        <div className="text-center">
          <p className="text-sm font-bold text-blue-400">{template.replyRate}%</p>
          <p className="text-[9px] text-zinc-500 uppercase tracking-widest">Reply rate</p>
        </div>
        <div className="w-px h-6 bg-zinc-800" />
        <div className="text-center">
          <p className="text-sm font-bold text-zinc-300">{template.uses.toLocaleString()}</p>
          <p className="text-[9px] text-zinc-500 uppercase tracking-widest">Uses</p>
        </div>
        <div className="ml-auto text-[10px] text-zinc-600">
          {template.nodes.filter(n => n.data?.type !== "start" && n.data?.type !== "end").length} steps
        </div>
      </div>

      {/* Sticky note legend */}
      {template.stickyNotes && Object.keys(template.stickyNotes).length > 0 && (
        <div className="flex items-center gap-1.5 mb-3">
          <StickyNote size={10} className="text-primary/80" />
          <span className="text-[10px] text-primary/80/70">Yellow cards explain what each step does and why it works</span>
        </div>
      )}

      {/* Step cards */}
      {orderedNodes.map((node, i) => {
        const isLast = i === orderedNodes.length - 1
        const delay = node.data?.delay as number | undefined
        const sticky = template.stickyNotes?.[node.id]

        return (
          <div key={node.id}>
            <StepCard node={node} stickyNote={sticky} delay={delay} />
            {!isLast && (node.type !== "end" && node.data?.type !== "end") && (
              <div className="flex justify-center py-1">
                <ArrowDown size={12} className="text-zinc-700" />
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
