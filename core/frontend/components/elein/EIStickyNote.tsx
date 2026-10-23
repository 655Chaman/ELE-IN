import React, { useState, useRef, useEffect, useMemo, useCallback } from 'react'
import { useHRTreeStore } from "@campaigns/eiTreeStore"
import type { StickyNote } from "@campaigns/eiTreeStore"
import { 
  X, Edit3, GripVertical, Pin, PinOff,
  Minimize2, Maximize2, Trash2, CheckSquare, Square,
  StickyNote as StickyIcon, Compass, UserCheck, AlertTriangle,
  Palette, Check, ChevronDown, CheckCircle2, RotateCcw, Sparkles,
  Bold, List, Minus, CheckCheck
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
  progressBar: string
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
    focusRing: "focus:ring-amber-500/30",
    progressBar: "bg-amber-500"
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
    focusRing: "focus:ring-emerald-500/30",
    progressBar: "bg-emerald-500"
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
    focusRing: "focus:ring-sky-500/30",
    progressBar: "bg-sky-500"
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
    focusRing: "focus:ring-rose-500/30",
    progressBar: "bg-rose-500"
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
    focusRing: "focus:ring-violet-500/30",
    progressBar: "bg-violet-500"
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

interface EIStickyNoteProps {
  note: StickyNote
  zoom?: number
}

export function EIStickyNote({ note, zoom = 1 }: EIStickyNoteProps) {
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
  const [isResizing, setIsResizing] = useState(false)
  const [isEditing, setIsEditing] = useState(!note.text && !note.title)
  const [isHovered, setIsHovered] = useState(false)
  const [showColorPicker, setShowColorPicker] = useState(false)
  const [showCategoryPicker, setShowCategoryPicker] = useState(false)

  const [draftTitle, setDraftTitle] = useState(note.title || "")
  const [draftText, setDraftText] = useState(note.text || "")

  const noteRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const titleInputRef = useRef<HTMLInputElement>(null)

  // Drag tracking refs (Layer 1 Environmental Paranoia: 120fps Pointer Capture + RAF)
  const isDraggingRef = useRef(false)
  const hasMovedRef = useRef(false)
  const dragStartRef = useRef({
    pointerId: -1,
    startX: 0,
    startY: 0,
    noteX: note.x,
    noteY: note.y,
    zoom: 1
  })
  const currentPosRef = useRef({ x: note.x, y: note.y })
  const dragRafIdRef = useRef<number | null>(null)

  // Resize tracking refs
  const isResizingRef = useRef(false)
  const resizeStartRef = useRef({
    pointerId: -1,
    startX: 0,
    startWidth: note.width || 290,
    zoom: 1
  })
  const currentWidthRef = useRef(note.width || 290)
  const resizeRafIdRef = useRef<number | null>(null)

  // Sync state when props change outside of edit mode
  useEffect(() => {
    if (!isEditing) {
      setDraftTitle(note.title || "")
      setDraftText(note.text || "")
    }
  }, [note.title, note.text, isEditing])

  useEffect(() => {
    if (!isDraggingRef.current) {
      currentPosRef.current = { x: note.x, y: note.y }
      if (noteRef.current) {
        noteRef.current.style.left = `${note.x}px`
        noteRef.current.style.top = `${note.y}px`
      }
    }
  }, [note.x, note.y])

  useEffect(() => {
    if (!isResizingRef.current) {
      currentWidthRef.current = note.width || 290
      if (noteRef.current) {
        noteRef.current.style.width = `${note.width || 290}px`
      }
    }
  }, [note.width])

  // Cleanup RAF on unmount
  useEffect(() => {
    return () => {
      if (dragRafIdRef.current !== null) cancelAnimationFrame(dragRafIdRef.current)
      if (resizeRafIdRef.current !== null) cancelAnimationFrame(resizeRafIdRef.current)
    }
  }, [])

  const activeColorKey = normalizeColor(note.color)
  const palette = STICKY_PALETTES[activeColorKey]
  const activeCategoryKey: StickyCategory = (note.category as StickyCategory) || "note"
  const CategoryIcon = STICKY_CATEGORIES[activeCategoryKey]?.icon || StickyIcon

  // Calculate subtle natural rotation from note ID hash for authentic post-it aesthetic
  const naturalRotation = useMemo(() => {
    let hash = 0
    for (let i = 0; i < note.id.length; i++) {
      hash = (hash << 5) - hash + note.id.charCodeAt(i)
      hash |= 0
    }
    return ((hash % 14) - 7) * 0.08
  }, [note.id])

  // Checklist statistics & completion ratio
  const checklistStats = useMemo(() => {
    const text = note.text || ""
    const matches = text.match(/^\s*-\s*\[([ xX])\]/gm)
    if (!matches) return null
    const total = matches.length
    const checked = matches.filter(m => m.includes("x") || m.includes("X")).length
    const percentage = total > 0 ? Math.round((checked / total) * 100) : 0
    return { total, checked, percentage, allDone: total > 0 && checked === total }
  }, [note.text])

  // Resolve active canvas zoom accurately
  const getEffectiveZoom = useCallback(() => {
    if (typeof zoom === 'number' && zoom > 0) return zoom
    if (noteRef.current) {
      const el = noteRef.current.closest('[data-canvas-zoom]') || noteRef.current.closest('[style*="zoom"]')
      if (el) {
        const parsed = parseFloat(el.getAttribute('data-canvas-zoom') || (el as HTMLElement).style.zoom || "1")
        if (!isNaN(parsed) && parsed > 0) return parsed
      }
    }
    return 1
  }, [zoom])

  // ─── Silky Smooth Pointer-Capture Drag Engine (Zero Lag, 120fps Native Feel) ─────
  const startDrag = useCallback((e: React.PointerEvent) => {
    if (note.isPinned) return
    if (e.button !== 0) return // Left click only

    const target = e.target as HTMLElement
    // Disallow drag on interactive controls
    if (target.closest('button, input, textarea, select, a, [data-no-drag], [role="menu"]')) return

    // In edit mode: Allow drag ONLY via the top header / drag handle
    if (isEditing && !target.closest('[data-drag-handle]')) return

    e.stopPropagation()
    e.preventDefault()

    const effectiveZoom = getEffectiveZoom()
    isDraggingRef.current = true
    hasMovedRef.current = false

    dragStartRef.current = {
      pointerId: e.pointerId,
      startX: e.clientX,
      startY: e.clientY,
      noteX: note.x,
      noteY: note.y,
      zoom: effectiveZoom
    }
    currentPosRef.current = { x: note.x, y: note.y }

    try {
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
    } catch {
      // Fallback if browser limits capture
    }

    setIsDragging(true)
  }, [note.isPinned, note.x, note.y, isEditing, getEffectiveZoom])

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    if (!isDraggingRef.current) return
    if (e.pointerId !== dragStartRef.current.pointerId) return

    const deltaX = (e.clientX - dragStartRef.current.startX) / dragStartRef.current.zoom
    const deltaY = (e.clientY - dragStartRef.current.startY) / dragStartRef.current.zoom

    if (Math.abs(deltaX) > 3 || Math.abs(deltaY) > 3) {
      hasMovedRef.current = true
    }

    const nextX = Math.round(dragStartRef.current.noteX + deltaX)
    const nextY = Math.round(dragStartRef.current.noteY + deltaY)

    currentPosRef.current = { x: nextX, y: nextY }

    if (dragRafIdRef.current === null) {
      dragRafIdRef.current = requestAnimationFrame(() => {
        if (noteRef.current) {
          noteRef.current.style.left = `${currentPosRef.current.x}px`
          noteRef.current.style.top = `${currentPosRef.current.y}px`
        }
        dragRafIdRef.current = null
      })
    }
  }, [])

  const endDrag = useCallback((e: React.PointerEvent) => {
    if (!isDraggingRef.current) return
    if (e.pointerId !== dragStartRef.current.pointerId) return

    isDraggingRef.current = false
    if (dragRafIdRef.current !== null) {
      cancelAnimationFrame(dragRafIdRef.current)
      dragRafIdRef.current = null
    }

    try {
      (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId)
    } catch {}

    setIsDragging(false)

    if (hasMovedRef.current) {
      moveStickyNote(note.id, currentPosRef.current.x, currentPosRef.current.y)
      // Clear movement flag after a tiny tick to prevent synthetic clicks
      setTimeout(() => {
        hasMovedRef.current = false
      }, 50)
    }
  }, [note.id, moveStickyNote])

  // ─── Smooth Width Resize Engine ──────────────────────────────────────────
  const startResize = useCallback((e: React.PointerEvent) => {
    if (note.isPinned) return
    if (e.button !== 0) return

    e.stopPropagation()
    e.preventDefault()

    const effectiveZoom = getEffectiveZoom()
    isResizingRef.current = true

    resizeStartRef.current = {
      pointerId: e.pointerId,
      startX: e.clientX,
      startWidth: note.width || 290,
      zoom: effectiveZoom
    }
    currentWidthRef.current = note.width || 290

    try {
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
    } catch {}

    setIsResizing(true)
  }, [note.isPinned, note.width, getEffectiveZoom])

  const handleResizeMove = useCallback((e: React.PointerEvent) => {
    if (!isResizingRef.current) return
    if (e.pointerId !== resizeStartRef.current.pointerId) return

    const deltaX = (e.clientX - resizeStartRef.current.startX) / resizeStartRef.current.zoom
    const nextWidth = Math.min(650, Math.max(270, Math.round(resizeStartRef.current.startWidth + deltaX)))

    currentWidthRef.current = nextWidth

    if (resizeRafIdRef.current === null) {
      resizeRafIdRef.current = requestAnimationFrame(() => {
        if (noteRef.current) {
          noteRef.current.style.width = `${currentWidthRef.current}px`
        }
        resizeRafIdRef.current = null
      })
    }
  }, [])

  const endResize = useCallback((e: React.PointerEvent) => {
    if (!isResizingRef.current) return
    if (e.pointerId !== resizeStartRef.current.pointerId) return

    isResizingRef.current = false
    if (resizeRafIdRef.current !== null) {
      cancelAnimationFrame(resizeRafIdRef.current)
      resizeRafIdRef.current = null
    }

    try {
      (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId)
    } catch {}

    setIsResizing(false)
    updateStickyNoteFull(note.id, { width: currentWidthRef.current })
  }, [note.id, updateStickyNoteFull])

  // Auto-focus and resize textarea on edit
  useEffect(() => {
    if (isEditing) {
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto'
        textareaRef.current.style.height = `${Math.max(90, textareaRef.current.scrollHeight)}px`
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

  // Save changes automatically when clicking outside the sticky note card
  useEffect(() => {
    if (!isEditing) return
    const handleOutsideClick = (e: MouseEvent) => {
      if (noteRef.current && !noteRef.current.contains(e.target as Node)) {
        handleSaveEdit()
      }
    }
    document.addEventListener("mousedown", handleOutsideClick)
    return () => document.removeEventListener("mousedown", handleOutsideClick)
  }, [isEditing, handleSaveEdit])

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
    toast.success(`Loaded "${preset.label}" template`)
    // Focus textarea immediately for quick tweaking
    setTimeout(() => {
      textareaRef.current?.focus()
    }, 50)
  }

  // Quick Markdown formatting helpers with zero-blur textarea preservation
  const insertFormatting = (type: "checklist" | "bold" | "bullet" | "rule") => {
    if (!textareaRef.current) return
    const el = textareaRef.current
    const start = el.selectionStart ?? 0
    const end = el.selectionEnd ?? 0
    const current = draftText
    const selected = current.slice(start, end)

    let replacement = ""
    let selectionOffsetStart = 0
    let selectionOffsetEnd = 0

    if (type === "checklist") {
      if (selected) {
        replacement = selected.split("\n").map(l => l.startsWith("- [ ] ") ? l : `- [ ] ${l}`).join("\n")
        selectionOffsetStart = 0
        selectionOffsetEnd = replacement.length
      } else {
        replacement = "- [ ] "
        selectionOffsetStart = replacement.length
        selectionOffsetEnd = replacement.length
      }
    } else if (type === "bullet") {
      if (selected) {
        replacement = selected.split("\n").map(l => l.startsWith("- ") ? l : `- ${l}`).join("\n")
        selectionOffsetStart = 0
        selectionOffsetEnd = replacement.length
      } else {
        replacement = "- "
        selectionOffsetStart = replacement.length
        selectionOffsetEnd = replacement.length
      }
    } else if (type === "bold") {
      const inner = selected || "bold text"
      replacement = `**${inner}**`
      selectionOffsetStart = 2
      selectionOffsetEnd = 2 + inner.length
    } else if (type === "rule") {
      const prefix = (start > 0 && current[start - 1] !== "\n") ? "\n---\n" : "---\n"
      replacement = prefix
      selectionOffsetStart = replacement.length
      selectionOffsetEnd = replacement.length
    }

    const next = current.slice(0, start) + replacement + current.slice(end)
    setDraftText(next)

    // Dynamic auto-grow
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto"
      textareaRef.current.style.height = `${Math.min(320, Math.max(90, textareaRef.current.scrollHeight))}px`
    }

    setTimeout(() => {
      el.focus()
      el.setSelectionRange(start + selectionOffsetStart, start + selectionOffsetEnd)
    }, 10)
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
      <div
        ref={noteRef}
        onPointerDown={startDrag}
        onPointerMove={handlePointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onClick={(e) => {
          e.stopPropagation()
          if (!hasMovedRef.current) {
            toggleStickyNoteCollapse(note.id)
          }
        }}
        style={{ left: note.x, top: note.y }}
        className={cn(
          "sticky-note absolute rounded-full border px-3.5 py-1.5 flex items-center gap-2.5 backdrop-blur-md shadow-md z-30 select-none",
          !isDragging && "transition-[box-shadow,border-color,background-color] duration-150 hover:shadow-lg cursor-grab",
          isDragging && "cursor-grabbing ring-2 ring-primary/60 z-[100] shadow-2xl scale-[1.03] !transition-none",
          palette.bg,
          palette.border,
          palette.text
        )}
      >
        <GripVertical size={12} className="opacity-40 shrink-0" />
        <span className={cn("w-2 h-2 rounded-full shrink-0 shadow-2xs", palette.dot)} />
        <CategoryIcon size={12} className={cn("shrink-0", palette.accent)} />
        <span className="text-xs font-bold truncate max-w-[170px]">
          {note.title || (note.text ? note.text.slice(0, 24) : "Note")}
        </span>
        {checklistStats && (
          <span className="text-[10px] font-mono font-bold px-1.5 py-0.2 rounded-full bg-black/10 dark:bg-white/10 shrink-0">
            {checklistStats.checked}/{checklistStats.total}
          </span>
        )}
        <button
          type="button"
          data-no-drag="true"
          onClick={(e) => {
            e.stopPropagation()
            toggleStickyNoteCollapse(note.id)
          }}
          className="p-1 rounded-full hover:bg-black/10 dark:hover:bg-white/10 transition-colors ml-0.5 cursor-pointer"
          title="Expand note"
          aria-label="Expand sticky note"
        >
          <Maximize2 size={11} />
        </button>
      </div>
    )
  }

  // ─── Expanded State (Full Canvas Post-It Card) ───────────────────────────
  return (
    <div
      ref={noteRef}
      onPointerDown={isEditing ? undefined : startDrag}
      onPointerMove={isEditing ? undefined : handlePointerMove}
      onPointerUp={isEditing ? undefined : endDrag}
      onPointerCancel={isEditing ? undefined : endDrag}
      className={cn(
        "sticky-note absolute rounded-2xl border shadow-xl flex flex-col z-30 select-none min-w-[270px] max-w-[650px]",
        // Crucial: Only transition visual aesthetics, NEVER position or transform!
        !isDragging && "transition-[box-shadow,border-color,background-color] duration-150",
        isDragging && "cursor-grabbing z-[100] ring-2 ring-primary/60 shadow-2xl scale-[1.015] !transition-none",
        isEditing && "ring-2 ring-primary/30 shadow-2xl",
        note.isPinned && "border-dashed",
        !isEditing && (note.isPinned ? "cursor-default" : "cursor-grab active:cursor-grabbing"),
        palette.bg,
        palette.border,
        palette.text
      )}
      style={{
        left: note.x,
        top: note.y,
        width: note.width || 290,
        transform: isDragging || isEditing || isHovered ? "none" : `rotate(${naturalRotation}deg)`
      }}
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
        data-drag-handle="true"
        onPointerDown={startDrag}
        onPointerMove={handlePointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        className={cn(
          "px-3 py-2 flex items-center justify-between transition-colors select-none",
          palette.headerBg,
          note.isPinned ? "cursor-default" : "cursor-grab active:cursor-grabbing hover:bg-black/5 dark:hover:bg-white/5"
        )}
      >
        <div className="flex items-center gap-1.5 min-w-0">
          <div 
            title={note.isPinned ? "Pinned (Unpin to drag)" : "Drag to move note anywhere"}
            className="flex items-center gap-1 opacity-70 hover:opacity-100 transition-opacity p-0.5 rounded cursor-grab active:cursor-grabbing"
          >
            <GripVertical size={14} className="shrink-0" />
          </div>
          
          {/* Category Badge Pill with Dropdown */}
          <div className="relative" data-no-drag="true">
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
        <div className="flex items-center gap-0.5 shrink-0" data-no-drag="true">
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
              <Palette size={13} className="opacity-70 hover:opacity-100" />
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
            {note.isPinned ? <Pin size={13} /> : <PinOff size={13} />}
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
            <Minimize2 size={13} />
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
            <Trash2 size={13} />
          </button>
        </div>
      </div>

      {/* ─── Checklist Visual Progress Bar (if checklists exist) ────────────── */}
      {checklistStats && (
        <div className="w-full bg-black/10 dark:bg-white/10 h-1 overflow-hidden">
          <div 
            className={cn("h-full transition-all duration-300", palette.progressBar)}
            style={{ width: `${checklistStats.percentage}%` }}
          />
        </div>
      )}

      {/* ─── Note Content Area ────────────────────────────────────────────── */}
      <div className="p-3.5 flex flex-col gap-2.5 min-w-0">
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
              "w-full bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/10 rounded-lg px-2.5 py-1.5 text-xs font-bold focus:outline-none placeholder:text-current/40 leading-snug min-w-0",
              palette.focusRing
            )}
          />
        ) : note.title ? (
          <div 
            onDoubleClick={(e) => { e.stopPropagation(); setIsEditing(true); }}
            className="text-xs font-bold leading-snug cursor-text select-text truncate"
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
          <div className="space-y-2 min-w-0">
            {/* Markdown Micro-Toolbar - Contained, Responsive & Zero-Bleed */}
            <div className="flex items-center justify-between pb-1.5 border-b border-black/10 dark:border-white/10 text-xs min-w-0">
              <div className="flex items-center gap-1 min-w-0">
                <button
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => insertFormatting("checklist")}
                  className="px-2 py-1 rounded-md text-[10px] font-bold bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 flex items-center gap-1.5 opacity-80 hover:opacity-100 transition-all cursor-pointer"
                  title="Checklist item (- [ ])"
                >
                  <CheckSquare size={12} className="shrink-0" />
                  <span>Checklist</span>
                </button>
                <button
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => insertFormatting("bold")}
                  className="w-6 h-6 rounded-md text-[10px] font-bold bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 flex items-center justify-center opacity-80 hover:opacity-100 transition-all cursor-pointer shrink-0"
                  title="Bold (**text**)"
                >
                  <Bold size={12} className="shrink-0" />
                </button>
                <button
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => insertFormatting("bullet")}
                  className="w-6 h-6 rounded-md text-[10px] font-bold bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 flex items-center justify-center opacity-80 hover:opacity-100 transition-all cursor-pointer shrink-0"
                  title="Bullet list (- item)"
                >
                  <List size={12} className="shrink-0" />
                </button>
                <button
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => insertFormatting("rule")}
                  className="w-6 h-6 rounded-md text-[10px] font-bold bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 flex items-center justify-center opacity-80 hover:opacity-100 transition-all cursor-pointer shrink-0"
                  title="Divider rule (---)"
                >
                  <Minus size={12} className="shrink-0" />
                </button>
              </div>

              {/* Template re-apply / Clear draft */}
              {(draftText || draftTitle) && (
                <button
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => {
                    setDraftText("")
                    setDraftTitle("")
                  }}
                  className="text-[10px] font-semibold opacity-60 hover:opacity-100 hover:text-destructive transition-colors cursor-pointer shrink-0 px-1 py-0.5"
                  title="Clear note title and text"
                >
                  Clear
                </button>
              )}
            </div>

            <textarea
              ref={textareaRef}
              rows={4}
              maxLength={5000}
              value={draftText}
              onChange={(e) => {
                setDraftText(e.target.value)
                e.target.style.height = 'auto'
                e.target.style.height = `${Math.min(320, Math.max(90, e.target.scrollHeight))}px`
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
                "w-full max-h-[320px] overflow-y-auto bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/10 rounded-lg p-2.5 text-xs font-medium leading-relaxed resize-none focus:outline-none placeholder:text-current/40",
                palette.focusRing
              )}
            />
            <div className="flex items-center justify-between pt-1">
              <span className="text-[10px] opacity-60">Cmd+Enter to save</span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setDraftTitle(note.title || "")
                    setDraftText(note.text || "")
                    setIsEditing(false)
                  }}
                  className="px-2.5 py-1 rounded-lg text-xs font-semibold opacity-70 hover:opacity-100 hover:bg-black/5 dark:hover:bg-white/5 transition-all cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    handleSaveEdit()
                  }}
                  className={cn(
                    "px-3.5 py-1.5 rounded-lg text-xs font-bold border transition-colors cursor-pointer shadow-xs hover:brightness-105 active:scale-95",
                    palette.badgeBg
                  )}
                >
                  Done
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div
            onDoubleClick={(e) => {
              e.stopPropagation()
              setIsEditing(true)
            }}
            className="text-xs font-medium leading-relaxed cursor-text select-text min-h-[44px]"
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
                          <span className={cn("text-xs leading-relaxed transition-all", isChecked && "line-through opacity-50")}>
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
          <div className="pt-2 border-t border-black/5 dark:border-white/5 flex items-center justify-between text-[10px] opacity-65">
            {checklistStats ? (
              <span className="flex items-center gap-1 font-semibold">
                {checklistStats.allDone ? (
                  <CheckCircle2 size={11} className="text-emerald-500" />
                ) : (
                  <CheckSquare size={11} />
                )}
                <span>{checklistStats.checked} of {checklistStats.total} done</span>
                <span className="opacity-50">({checklistStats.percentage}%)</span>
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
              className="flex items-center gap-1 hover:opacity-100 transition-opacity p-0.5 rounded hover:bg-black/5 dark:hover:bg-white/5 cursor-pointer font-bold"
            >
              <Edit3 size={10} />
              <span>Edit</span>
            </button>
          </div>
        )}
      </div>

      {/* ─── Bottom-Right Resize Grip Handle ──────────────────────────────── */}
      {!note.isPinned && !note.isCollapsed && (
        <div
          data-no-drag="true"
          onPointerDown={startResize}
          onPointerMove={handleResizeMove}
          onPointerUp={endResize}
          onPointerCancel={endResize}
          onDoubleClick={(e) => {
            e.stopPropagation()
            updateStickyNoteFull(note.id, { width: 290 })
          }}
          title="Drag to resize width (Double-click to reset)"
          className="absolute bottom-1 right-1 p-1 text-current/30 hover:text-current/80 cursor-se-resize select-none transition-colors"
        >
          <svg width="8" height="8" viewBox="0 0 8 8" className="stroke-current fill-none stroke-[1.5]">
            <line x1="7" y1="1" x2="1" y2="7" />
            <line x1="7" y1="4" x2="4" y2="7" />
          </svg>
        </div>
      )}
    </div>
  )
}
