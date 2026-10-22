import React, { useState, useRef, useEffect, useMemo, useCallback } from 'react'
import { useHRTreeStore } from "@campaigns/eiTreeStore"
import type { StickyNote } from "@campaigns/eiTreeStore"
import { 
  X, Edit3, GripVertical, Pin, PinOff,
  Minimize2, Maximize2, Trash2, CheckSquare, Square,
  StickyNote as StickyIcon, Compass, UserCheck, AlertTriangle,
  Palette, Check, ChevronDown, CheckCircle2, RotateCcw, Sparkles
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { motion, AnimatePresence } from 'motion/react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'

export type StickyColor = "amber" | "emerald" | "sky" | "rose" | "violet"
export type StickyCategory = "note" | "todo" | "warning" | "strategy" | "handover"

export const STICKY_PALETTES: Record<StickyColor, {
  name: string
  bg: string
  border: string
  text: string
  mutedText: string
  headerBg: string
  badgeBg: string
  dot: string
  accent: string
  focusRing: string
}> = {
  amber: {
    name: "Sun (Idea)",
    bg: "bg-amber-50/95 dark:bg-amber-950/85",
    border: "border-amber-300/80 dark:border-amber-700/80",
    text: "text-amber-950 dark:text-amber-100",
    mutedText: "text-amber-800/80 dark:text-amber-300/80",
    headerBg: "bg-amber-100/80 dark:bg-amber-900/40 border-b border-amber-200 dark:border-amber-800/50",
    badgeBg: "bg-amber-200/70 dark:bg-amber-900/70 text-amber-900 dark:text-amber-200 border-amber-300/60 dark:border-amber-700/60",
    dot: "bg-amber-400",
    accent: "text-amber-600 dark:text-amber-400",
    focusRing: "focus:ring-amber-500/30"
  },
  emerald: {
    name: "Emerald (Goal)",
    bg: "bg-emerald-50/95 dark:bg-emerald-950/85",
    border: "border-emerald-300/80 dark:border-emerald-700/80",
    text: "text-emerald-950 dark:text-emerald-100",
    mutedText: "text-emerald-800/80 dark:text-emerald-300/80",
    headerBg: "bg-emerald-100/80 dark:bg-emerald-900/40 border-b border-emerald-200 dark:border-emerald-800/50",
    badgeBg: "bg-emerald-200/70 dark:bg-emerald-900/70 text-emerald-900 dark:text-emerald-200 border-emerald-300/60 dark:border-emerald-700/60",
    dot: "bg-emerald-400",
    accent: "text-emerald-600 dark:text-emerald-400",
    focusRing: "focus:ring-emerald-500/30"
  },
  sky: {
    name: "Sky (Info)",
    bg: "bg-sky-50/95 dark:bg-sky-950/85",
    border: "border-sky-300/80 dark:border-sky-700/80",
    text: "text-sky-950 dark:text-sky-100",
    mutedText: "text-sky-800/80 dark:text-sky-300/80",
    headerBg: "bg-sky-100/80 dark:bg-sky-900/40 border-b border-sky-200 dark:border-sky-800/50",
    badgeBg: "bg-sky-200/70 dark:bg-sky-900/70 text-sky-900 dark:text-sky-200 border-sky-300/60 dark:border-sky-700/60",
    dot: "bg-sky-400",
    accent: "text-sky-600 dark:text-sky-400",
    focusRing: "focus:ring-sky-500/30"
  },
  rose: {
    name: "Rose (Caution)",
    bg: "bg-rose-50/95 dark:bg-rose-950/85",
    border: "border-rose-300/80 dark:border-rose-700/80",
    text: "text-rose-950 dark:text-rose-100",
    mutedText: "text-rose-800/80 dark:text-rose-300/80",
    headerBg: "bg-rose-100/80 dark:bg-rose-900/40 border-b border-rose-200 dark:border-rose-800/50",
    badgeBg: "bg-rose-200/70 dark:bg-rose-900/70 text-rose-900 dark:text-rose-200 border-rose-300/60 dark:border-rose-700/60",
    dot: "bg-rose-400",
    accent: "text-rose-600 dark:text-rose-400",
    focusRing: "focus:ring-rose-500/30"
  },
  violet: {
    name: "Violet (Strategy)",
    bg: "bg-violet-50/95 dark:bg-violet-950/85",
    border: "border-violet-300/80 dark:border-violet-700/80",
    text: "text-violet-950 dark:text-violet-100",
    mutedText: "text-violet-800/80 dark:text-violet-300/80",
    headerBg: "bg-violet-100/80 dark:bg-violet-900/40 border-b border-violet-200 dark:border-violet-800/50",
    badgeBg: "bg-violet-200/70 dark:bg-violet-900/70 text-violet-900 dark:text-violet-200 border-violet-300/60 dark:border-violet-700/60",
    dot: "bg-violet-400",
    accent: "text-violet-600 dark:text-violet-400",
    focusRing: "focus:ring-violet-500/30"
  }
}

export const STICKY_CATEGORIES: Record<StickyCategory, {
  label: string
  icon: React.ComponentType<{ size?: number; className?: string }>
}> = {
  note: { label: "Note", icon: StickyIcon },
  todo: { label: "Checklist", icon: CheckSquare },
  warning: { label: "Caution", icon: AlertTriangle },
  strategy: { label: "Strategy", icon: Compass },
  handover: { label: "SDR Handover", icon: UserCheck }
}

const PRESET_TEMPLATES = [
  {
    id: "checklist",
    label: "Checklist",
    icon: CheckSquare,
    title: "Launch Checklist",
    category: "todo" as const,
    color: "emerald" as const,
    text: `- [ ] Connect 3+ sender accounts\n- [ ] Set daily limit to 25/day per sender\n- [ ] Verify recipient curfew (9 AM - 5 PM)\n- [ ] Test spintax variation in message copy`
  },
  {
    id: "ab_test",
    label: "A/B Hypothesis",
    icon: Compass,
    title: "A/B Copy Hypothesis",
    category: "strategy" as const,
    color: "violet" as const,
    text: `**Hypothesis:** Pain-point opener will outperform compliment lead.\n\n- **Variant A:** Mutual connection intro\n- **Variant B:** Specific workflow bottleneck question\n- **Target Goal:** > 28% reply rate`
  },
  {
    id: "warning",
    label: "Safety / Curfew",
    icon: AlertTriangle,
    title: "Account Safety Rule",
    category: "warning" as const,
    color: "rose" as const,
    text: `**Compliance Gate:**\n- Max 20 connection requests/day\n- Auto-withdraw pending requests after 14 days\n- Never send messages on weekends`
  },
  {
    id: "handover",
    label: "SDR Handover",
    icon: UserCheck,
    title: "Lead Triage Rule",
    category: "handover" as const,
    color: "sky" as const,
    text: `**When lead replies:**\n- If Positive -> Assign to AE in CRM\n- If Question -> Respond within 15 mins\n- If Objection -> Apply price-anchor battlecard`
  }
]

function normalizeColor(raw?: string): StickyColor {
  if (!raw) return "amber"
  const l = raw.toLowerCase()
  if (l.includes("emerald") || l.includes("green")) return "emerald"
  if (l.includes("sky") || l.includes("blue") || l.includes("cyan")) return "sky"
  if (l.includes("rose") || l.includes("pink") || l.includes("red")) return "rose"
  if (l.includes("violet") || l.includes("purple") || l.includes("indigo")) return "violet"
  return "amber"
}

export function EIStickyNote({ note }: { note: StickyNote }) {
  const { 
    updateStickyNote, 
    updateStickyNoteFull, 
    moveStickyNote, 
    removeStickyNote, 
    changeStickyNoteColor,
    toggleStickyNoteCollapse,
    toggleStickyNotePin
  } = useHRTreeStore()

  const [isDragging, setIsDragging] = useState(false)
  const [isEditing, setIsEditing] = useState(!note.text && !note.title)
  const [isHovered, setIsHovered] = useState(false)
  const [showColorPicker, setShowColorPicker] = useState(false)
  const [showCategoryPicker, setShowCategoryPicker] = useState(false)

  const [draftTitle, setDraftTitle] = useState(note.title || "")
  const [draftText, setDraftText] = useState(note.text || "")

  const noteRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const titleInputRef = useRef<HTMLInputElement>(null)
  const dragStartRef = useRef({ mouseX: 0, mouseY: 0, noteX: note.x, noteY: note.y })
  const posRef = useRef({ x: note.x, y: note.y })

  // Keep local draft in sync with props when not actively editing
  useEffect(() => {
    if (!isEditing) {
      setDraftTitle(note.title || "")
      setDraftText(note.text || "")
    }
  }, [note.title, note.text, isEditing])

  useEffect(() => {
    if (!isDragging) {
      posRef.current = { x: note.x, y: note.y }
    }
  }, [note.x, note.y, isDragging])

  const activeColorKey = normalizeColor(note.color)
  const palette = STICKY_PALETTES[activeColorKey]
  const activeCategoryKey: StickyCategory = (note.category as StickyCategory) || "note"
  const CategoryIcon = STICKY_CATEGORIES[activeCategoryKey]?.icon || StickyIcon

  // Calculate subtle natural rotation from note ID hash for authentic post-it feel
  const naturalRotation = useMemo(() => {
    let hash = 0
    for (let i = 0; i < note.id.length; i++) {
      hash = (hash << 5) - hash + note.id.charCodeAt(i)
      hash |= 0
    }
    // Return subtle -0.7deg to +0.7deg
    return ((hash % 14) - 7) * 0.1
  }, [note.id])

  // Checklist statistics
  const checklistStats = useMemo(() => {
    const text = note.text || ""
    const matches = text.match(/^\s*-\s*\[([ xX])\]/gm)
    if (!matches) return null
    const total = matches.length
    const checked = matches.filter(m => m.includes("x") || m.includes("X")).length
    return { total, checked, allDone: total > 0 && checked === total }
  }, [note.text])

  // Delta-based, zoom-compensated drag handler (Layer 1 Environmental Paranoia)
  const handleDragStart = (e: React.MouseEvent) => {
    if (note.isPinned) return
    if (isEditing) return
    const target = e.target as HTMLElement
    if (target.closest('button, input, textarea, select, [data-no-drag]')) return

    e.stopPropagation()
    e.preventDefault()

    dragStartRef.current = {
      mouseX: e.clientX,
      mouseY: e.clientY,
      noteX: note.x,
      noteY: note.y
    }
    setIsDragging(true)
  }

  useEffect(() => {
    if (!isDragging) return

    const handleMouseMove = (e: MouseEvent) => {
      if (!noteRef.current) return
      // Inspect canvas zoom compensation (FLAW-FE-18: standard data-canvas-zoom with style.zoom fallback)
      const el = noteRef.current.closest('[data-canvas-zoom]') || noteRef.current.closest('[style*="zoom"]')
      const zoom = el 
        ? parseFloat(el.getAttribute('data-canvas-zoom') || (el as HTMLElement).style.zoom || "1") 
        : 1

      const deltaX = (e.clientX - dragStartRef.current.mouseX) / zoom
      const deltaY = (e.clientY - dragStartRef.current.mouseY) / zoom

      posRef.current.x = Math.round(dragStartRef.current.noteX + deltaX)
      posRef.current.y = Math.round(dragStartRef.current.noteY + deltaY)

      noteRef.current.style.left = `${posRef.current.x}px`
      noteRef.current.style.top = `${posRef.current.y}px`
    }

    const handleMouseUp = () => {
      setIsDragging(false)
      moveStickyNote(note.id, posRef.current.x, posRef.current.y)
    }

    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }
  }, [isDragging, note.id, moveStickyNote])

  // Auto-focus and resize textarea on edit
  useEffect(() => {
    if (isEditing) {
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto'
        textareaRef.current.style.height = `${Math.max(80, textareaRef.current.scrollHeight)}px`
      }
    }
  }, [isEditing, draftText])

  const handleSaveEdit = useCallback(() => {
    updateStickyNoteFull(note.id, {
      title: draftTitle.trim(),
      text: draftText.trim(),
      updatedAt: new Date().toISOString()
    })
    setIsEditing(false)
    setShowColorPicker(false)
    setShowCategoryPicker(false)
  }, [draftTitle, draftText, note.id, updateStickyNoteFull])

  const handleDeleteWithUndo = () => {
    const backup = { ...note }
    removeStickyNote(note.id)
    toast("Sticky note removed from canvas", {
      action: {
        label: "Undo",
        onClick: () => {
          useHRTreeStore.setState(s => ({
            stickyNotes: [...s.stickyNotes, backup]
          }))
        }
      }
    })
  }

  const applyPreset = (preset: typeof PRESET_TEMPLATES[0]) => {
    setDraftTitle(preset.title)
    setDraftText(preset.text)
    updateStickyNoteFull(note.id, {
      title: preset.title,
      text: preset.text,
      color: preset.color,
      category: preset.category,
      updatedAt: new Date().toISOString()
    })
    setIsEditing(false)
    toast.success(`Loaded "${preset.label}" template`)
  }

  // Interactive Checklist Check/Uncheck toggle in View Mode
  const toggleChecklistLine = (lineContent: string) => {
    const raw = note.text || ""
    const isChecked = lineContent.startsWith("[x] ") || lineContent.startsWith("[X] ")
    const itemText = lineContent.slice(4)

    const lines = raw.split("\n")
    const updatedLines = lines.map(line => {
      const trimmed = line.trim()
      if (isChecked && (trimmed === `- [x] ${itemText}` || trimmed === `- [X] ${itemText}`)) {
        return line.replace(/- \[[xX]\]/, "- [ ]")
      }
      if (!isChecked && trimmed === `- [ ] ${itemText}`) {
        return line.replace(/- \[ \]/, "- [x]")
      }
      return line
    })

    const nextText = updatedLines.join("\n")
    updateStickyNote(note.id, nextText)
  }

  // ─── Collapsed State (Ultra-Compact Canvas Pill) ─────────────────────────
  if (note.isCollapsed) {
    return (
      <motion.div
        ref={noteRef}
        layout
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.9 }}
        style={{ left: note.x, top: note.y }}
        onMouseDown={handleDragStart}
        onClick={(e) => {
          e.stopPropagation()
          toggleStickyNoteCollapse(note.id)
        }}
        className={cn(
          "sticky-note absolute rounded-full border px-3 py-1.5 flex items-center gap-2 backdrop-blur-md shadow-md hover:shadow-lg transition-all cursor-pointer z-30 select-none",
          palette.bg,
          palette.border,
          palette.text,
          isDragging ? "cursor-grabbing ring-2 ring-primary/40 z-[100]" : "cursor-grab"
        )}
      >
        <span className={cn("w-2 h-2 rounded-full shrink-0", palette.dot)} />
        <CategoryIcon size={12} className={cn("shrink-0", palette.accent)} />
        <span className="text-xs font-bold truncate max-w-[160px]">
          {note.title || (note.text ? note.text.slice(0, 24) : "Note")}
        </span>
        {checklistStats && (
          <span className="text-[10px] font-mono font-semibold px-1.5 py-0.2 rounded-full bg-black/10 dark:bg-white/10 shrink-0">
            {checklistStats.checked}/{checklistStats.total}
          </span>
        )}
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            toggleStickyNoteCollapse(note.id)
          }}
          className="p-1 rounded-full hover:bg-black/10 dark:hover:bg-white/10 transition-colors ml-1"
          title="Expand note"
          aria-label="Expand sticky note"
        >
          <Maximize2 size={11} />
        </button>
      </motion.div>
    )
  }

  // ─── Expanded State (Full Canvas Post-It Card) ───────────────────────────
  return (
    <motion.div
      ref={noteRef}
      initial={{ opacity: 0, scale: 0.94, y: 8 }}
      animate={{ 
        opacity: 1, 
        scale: 1, 
        y: 0,
        rotate: isHovered || isEditing || isDragging ? 0 : naturalRotation
      }}
      transition={{ type: "spring", stiffness: 380, damping: 28 }}
      className={cn(
        "sticky-note absolute rounded-2xl border shadow-xl transition-all duration-150 flex flex-col z-30 overflow-hidden select-none",
        palette.bg,
        palette.border,
        palette.text,
        isDragging && "cursor-grabbing z-[100] ring-2 ring-primary/50 shadow-2xl scale-[1.02]",
        isEditing && "ring-2 ring-primary/40 shadow-2xl",
        note.isPinned && "border-dashed"
      )}
      style={{ left: note.x, top: note.y, width: 290 }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => {
        setIsHovered(false)
        setShowColorPicker(false)
        setShowCategoryPicker(false)
      }}
      onClick={(e) => e.stopPropagation()}
    >
      {/* ─── Top Control & Drag Header ─────────────────────────────────────── */}
      <div 
        onMouseDown={handleDragStart}
        className={cn(
          "px-3 py-2 flex items-center justify-between transition-colors",
          palette.headerBg,
          note.isPinned ? "cursor-default" : "cursor-grab active:cursor-grabbing"
        )}
      >
        <div className="flex items-center gap-1.5 min-w-0">
          <GripVertical size={13} className={cn("shrink-0", note.isPinned ? "opacity-30" : "opacity-60")} />
          
          {/* Category Badge Pill with Dropdown */}
          <div className="relative">
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                setShowCategoryPicker(p => !p)
                setShowColorPicker(false)
              }}
              className={cn(
                "flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold border transition-all cursor-pointer shadow-2xs",
                palette.badgeBg
              )}
              title="Change note type"
            >
              <CategoryIcon size={11} className="shrink-0" />
              <span>{STICKY_CATEGORIES[activeCategoryKey]?.label || "Note"}</span>
              <ChevronDown size={9} className="opacity-60" />
            </button>

            {/* Category Dropdown Menu */}
            <AnimatePresence>
              {showCategoryPicker && (
                <motion.div
                  initial={{ opacity: 0, y: -4, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -4, scale: 0.95 }}
                  className="absolute left-0 top-full mt-1.5 z-50 w-36 rounded-xl bg-card border border-border shadow-xl p-1 text-foreground"
                >
                  {(Object.keys(STICKY_CATEGORIES) as StickyCategory[]).map(catKey => {
                    const Cat = STICKY_CATEGORIES[catKey]
                    const Icon = Cat.icon
                    const isSelected = activeCategoryKey === catKey
                    return (
                      <button
                        key={catKey}
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation()
                          updateStickyNoteFull(note.id, { category: catKey })
                          setShowCategoryPicker(false)
                        }}
                        className={cn(
                          "w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-xs font-semibold transition-colors cursor-pointer text-left",
                          isSelected ? "bg-primary/10 text-primary" : "hover:bg-muted text-foreground"
                        )}
                      >
                        <Icon size={13} className="shrink-0" />
                        <span>{Cat.label}</span>
                      </button>
                    )
                  })}
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {note.isPinned && (
            <span title="Pinned to canvas">
              <Pin size={11} className="text-primary shrink-0 opacity-80" />
            </span>
          )}
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-1 shrink-0">
          {/* Color Switcher Button */}
          <div className="relative">
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                setShowColorPicker(p => !p)
                setShowCategoryPicker(false)
              }}
              className="p-1 rounded-md hover:bg-black/10 dark:hover:bg-white/10 transition-colors cursor-pointer"
              title="Change palette"
              aria-label="Change sticky note color"
            >
              <Palette size={12} className="opacity-70 hover:opacity-100" />
            </button>

            {/* Color Palette Popover */}
            <AnimatePresence>
              {showColorPicker && (
                <motion.div
                  initial={{ opacity: 0, scale: 0.95, y: -2 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.95, y: -2 }}
                  className="absolute right-0 top-full mt-1.5 z-50 flex items-center gap-1.5 p-1.5 rounded-xl bg-card border border-border shadow-xl"
                >
                  {(Object.keys(STICKY_PALETTES) as StickyColor[]).map(c => (
                    <button
                      type="button"
                      key={c}
                      onClick={(e) => {
                        e.stopPropagation()
                        changeStickyNoteColor(note.id, c)
                        setShowColorPicker(false)
                      }}
                      className={cn(
                        "w-5 h-5 rounded-full transition-transform hover:scale-110 cursor-pointer shadow-xs",
                        STICKY_PALETTES[c].dot,
                        activeColorKey === c && "ring-2 ring-foreground ring-offset-1 ring-offset-card"
                      )}
                      title={STICKY_PALETTES[c].name}
                      aria-label={`Select ${STICKY_PALETTES[c].name} color`}
                    />
                  ))}
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Pin/Lock Toggle Button */}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              toggleStickyNotePin(note.id)
            }}
            className={cn(
              "p-1 rounded-md transition-colors cursor-pointer",
              note.isPinned 
                ? "bg-primary/20 text-primary" 
                : "hover:bg-black/10 dark:hover:bg-white/10 opacity-70 hover:opacity-100"
            )}
            title={note.isPinned ? "Unpin from canvas" : "Pin position on canvas"}
            aria-label={note.isPinned ? "Unpin sticky note" : "Pin sticky note"}
          >
            {note.isPinned ? <Pin size={12} /> : <PinOff size={12} />}
          </button>

          {/* Minimize / Fold Button */}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              toggleStickyNoteCollapse(note.id)
            }}
            className="p-1 rounded-md hover:bg-black/10 dark:hover:bg-white/10 opacity-70 hover:opacity-100 transition-colors cursor-pointer"
            title="Collapse to compact pill"
            aria-label="Collapse sticky note"
          >
            <Minimize2 size={12} />
          </button>

          {/* Delete Button with Undo */}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              handleDeleteWithUndo()
            }}
            disabled={note.isPinned}
            className="p-1 rounded-md hover:bg-destructive/20 text-destructive opacity-70 hover:opacity-100 transition-colors cursor-pointer disabled:opacity-20 disabled:cursor-not-allowed"
            title={note.isPinned ? "Unpin before deleting" : "Delete note"}
            aria-label="Delete sticky note"
          >
            <Trash2 size={12} />
          </button>
        </div>
      </div>

      {/* ─── Note Content Area ────────────────────────────────────────────── */}
      <div className="p-4 flex flex-col gap-2.5">
        {/* Title Field */}
        {isEditing ? (
          <input
            ref={titleInputRef}
            type="text"
            maxLength={100}
            value={draftTitle}
            onChange={(e) => setDraftTitle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                textareaRef.current?.focus()
              }
              if (e.key === 'Escape') handleSaveEdit()
            }}
            placeholder="Note title (optional)..."
            className={cn(
              "w-full bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/10 rounded-lg px-2.5 py-1.5 text-xs font-bold focus:outline-none placeholder:text-current/40 leading-snug",
              palette.focusRing
            )}
          />
        ) : note.title ? (
          <div 
            onDoubleClick={(e) => { e.stopPropagation(); setIsEditing(true); }}
            className="text-xs font-bold leading-snug cursor-text select-text"
          >
            {note.title}
          </div>
        ) : null}

        {/* Empty Note Starter Presets */}
        {isEditing && !draftText && !draftTitle && (
          <div className="py-1">
            <span className="text-[10px] font-semibold opacity-70 block mb-1.5 flex items-center gap-1">
              <Sparkles size={11} className={palette.accent} /> Quick Starter Presets:
            </span>
            <div className="grid grid-cols-2 gap-1.5">
              {PRESET_TEMPLATES.map(preset => {
                const PIcon = preset.icon
                return (
                  <button
                    key={preset.id}
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      applyPreset(preset)
                    }}
                    className="flex items-center gap-1.5 px-2 py-1.5 rounded-lg bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 border border-black/10 dark:border-white/10 text-left transition-all cursor-pointer group"
                  >
                    <PIcon size={11} className={cn("shrink-0", STICKY_PALETTES[preset.color].accent)} />
                    <span className="text-[10px] font-bold truncate">{preset.label}</span>
                  </button>
                )
              })}
            </div>
          </div>
        )}

        {/* Body Editor or Rendered View */}
        {isEditing ? (
          <div className="space-y-2">
            <textarea
              ref={textareaRef}
              rows={4}
              maxLength={5000}
              value={draftText}
              onChange={(e) => {
                setDraftText(e.target.value)
                e.target.style.height = 'auto'
                e.target.style.height = `${Math.max(80, e.target.scrollHeight)}px`
              }}
              onKeyDown={(e) => {
                if (e.key === 'Escape') handleSaveEdit()
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault()
                  handleSaveEdit()
                }
              }}
              placeholder="Type note (Markdown & checklists supported: - [ ] Task)..."
              className={cn(
                "w-full bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/10 rounded-lg p-2.5 text-xs font-medium leading-relaxed resize-none focus:outline-none placeholder:text-current/40",
                palette.focusRing
              )}
            />
            <div className="flex items-center justify-between pt-1">
              <span className="text-[10px] opacity-60">Cmd+Enter to save</span>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  handleSaveEdit()
                }}
                className={cn(
                  "px-3 py-1 rounded-md text-[11px] font-bold border transition-colors cursor-pointer shadow-2xs",
                  palette.badgeBg
                )}
              >
                Done
              </button>
            </div>
          </div>
        ) : (
          <div
            onDoubleClick={(e) => {
              e.stopPropagation()
              setIsEditing(true)
            }}
            className="text-xs font-medium leading-relaxed cursor-text select-text min-h-[40px]"
          >
            {note.text ? (
              <ReactMarkdown
                components={{
                  p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                  ul: ({ children }) => <ul className="pl-4 list-disc space-y-1 mb-2 last:mb-0">{children}</ul>,
                  ol: ({ children }) => <ol className="pl-4 list-decimal space-y-1 mb-2 last:mb-0">{children}</ol>,
                  li: ({ children }) => {
                    const text = React.Children.toArray(children)
                      .map(c => (typeof c === 'string' ? c : ''))
                      .join('')
                    if (text.startsWith('[ ] ') || text.startsWith('[x] ') || text.startsWith('[X] ')) {
                      const isChecked = text.startsWith('[x] ') || text.startsWith('[X] ')
                      const labelText = text.slice(4)
                      return (
                        <li 
                          onClick={(e) => {
                            e.stopPropagation()
                            toggleChecklistLine(text)
                          }}
                          className="list-none -ml-4 flex items-start gap-2 my-1 cursor-pointer select-none group/item"
                        >
                          <span className="mt-0.5 shrink-0 opacity-70 group-hover/item:opacity-100 transition-opacity">
                            {isChecked ? (
                              <CheckSquare size={13} className={palette.accent} />
                            ) : (
                              <Square size={13} className="opacity-60" />
                            )}
                          </span>
                          <span className={cn("text-xs leading-relaxed", isChecked && "line-through opacity-60")}>
                            {labelText}
                          </span>
                        </li>
                      )
                    }
                    return <li className="mb-1">{children}</li>
                  },
                  h1: ({ children }) => <h1 className="text-sm font-bold mb-1 mt-2 first:mt-0">{children}</h1>,
                  h2: ({ children }) => <h2 className="text-xs font-bold mb-1 mt-2 first:mt-0">{children}</h2>,
                  h3: ({ children }) => <h3 className="text-xs font-semibold mb-0.5 mt-1.5 first:mt-0">{children}</h3>,
                  strong: ({ children }) => <strong className="font-bold">{children}</strong>,
                  em: ({ children }) => <em className="italic opacity-90">{children}</em>,
                  code: ({ children }) => (
                    <code className="px-1.5 py-0.5 rounded bg-black/10 dark:bg-white/10 font-mono text-[10px]">
                      {children}
                    </code>
                  ),
                  blockquote: ({ children }) => (
                    <blockquote className="border-l-2 border-current/30 pl-2.5 italic opacity-85 my-1.5">
                      {children}
                    </blockquote>
                  ),
                  a: ({ href, children }) => {
                    const safeHref = href && /^(https?:\/\/|mailto:)/i.test(href.trim()) ? href.trim() : '#'
                    return (
                      <a 
                        href={safeHref} 
                        target="_blank" 
                        rel="noopener noreferrer" 
                        className="underline hover:opacity-80"
                        onClick={(e) => {
                          e.stopPropagation()
                          if (safeHref === '#') e.preventDefault()
                        }}
                      >
                        {children}
                      </a>
                    )
                  }
                }}
              >
                {note.text}
              </ReactMarkdown>
            ) : (
              <span className="text-xs italic opacity-40">
                Empty note. Double-click to write thoughts or checklists...
              </span>
            )}
          </div>
        )}

        {/* ─── Footer Details ─────────────────────────────────────────────── */}
        {!isEditing && (
          <div className="pt-2 border-t border-black/5 dark:border-white/5 flex items-center justify-between text-[10px] opacity-60">
            {checklistStats ? (
              <span className="flex items-center gap-1 font-medium">
                {checklistStats.allDone ? (
                  <CheckCircle2 size={11} className="text-emerald-500" />
                ) : (
                  <CheckSquare size={11} />
                )}
                {checklistStats.checked} of {checklistStats.total} done
              </span>
            ) : (
              <span>Double-click to edit</span>
            )}
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                setIsEditing(true)
              }}
              className="flex items-center gap-1 hover:opacity-100 transition-opacity p-0.5 rounded hover:bg-black/5 dark:hover:bg-white/5 cursor-pointer"
            >
              <Edit3 size={10} />
              <span>Edit</span>
            </button>
          </div>
        )}
      </div>
    </motion.div>
  )
}
