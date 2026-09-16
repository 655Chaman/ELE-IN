import React, { useState, useRef, useEffect } from 'react'
import { useHRTreeStore } from "@campaigns/eiTreeStore";
import type { StickyNote } from "@campaigns/eiTreeStore"
import { X, Palette, Edit2, GripHorizontal } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { motion, AnimatePresence } from 'motion/react'

export function EIStickyNote({ note }: { note: StickyNote }) {
  const { updateStickyNote, moveStickyNote, removeStickyNote, changeStickyNoteColor } = useHRTreeStore()
  const [isDragging, setIsDragging] = useState(false)
  const [isEditing, setIsEditing] = useState(!note.text)
  const [isHovered, setIsHovered] = useState(false)
  
  const noteRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  
  // Vibrant classic sticky note colors
  const colorMap: Record<string, string> = {
    "yellow": "bg-[#FEF08A] border-[#FDE047] text-slate-800 shadow-[0_8px_30px_-4px_rgba(253,224,71,0.3)]",
    "blue": "bg-[#BAE6FD] border-[#7DD3FC] text-slate-800 shadow-[0_8px_30px_-4px_rgba(125,211,252,0.3)]",
    "pink": "bg-[#FECDD3] border-[#FDA4AF] text-slate-800 shadow-[0_8px_30px_-4px_rgba(253,164,175,0.3)]",
    "green": "bg-[#A7F3D0] border-[#6EE7B7] text-slate-800 shadow-[0_8px_30px_-4px_rgba(110,231,183,0.3)]",
    "purple": "bg-[#E9D5FF] border-[#D8B4FE] text-slate-800 shadow-[0_8px_30px_-4px_rgba(216,180,254,0.3)]"
  }
  
  // Default to yellow if old color format or undefined
  let baseColorKey = "yellow"
  if (note.color && note.color.includes("blue")) baseColorKey = "blue"
  if (note.color && note.color.includes("pink")) baseColorKey = "pink"
  if (note.color && note.color.includes("green")) baseColorKey = "green"
  if (note.color && note.color.includes("purple")) baseColorKey = "purple"
  
  const activeStyle = colorMap[baseColorKey]

  const handleMouseDown = (e: React.MouseEvent) => {
    if (isEditing) return
    // Prevent dragging if clicking buttons
    if ((e.target as HTMLElement).closest('button')) return
    
    e.stopPropagation()
    setIsDragging(true)
  }

  const posRef = useRef({ x: note.x, y: note.y })
  
  useEffect(() => {
    if (!isDragging) {
      posRef.current = { x: note.x, y: note.y }
    }
  }, [note.x, note.y, isDragging])

  useEffect(() => {
    if (!isDragging) return
    
    const handleMouseMove = (e: MouseEvent) => {
      if (!noteRef.current) return
      const el = noteRef.current.closest('[style*="zoom"]')
      const zoom = el ? parseFloat((el as HTMLElement).style.zoom || "1") : 1
      
      posRef.current.x += e.movementX / zoom
      posRef.current.y += e.movementY / zoom
      
      // Mutate DOM directly for zero-latency dragging
      noteRef.current.style.left = `${posRef.current.x}px`
      noteRef.current.style.top = `${posRef.current.y}px`
    }
    const handleMouseUp = () => {
      setIsDragging(false)
      // Save final position to store once
      moveStickyNote(note.id, posRef.current.x, posRef.current.y)
    }
    
    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }
  }, [isDragging, note.id, moveStickyNote])

  // Auto-resize textarea
  useEffect(() => {
    if (isEditing && textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = textareaRef.current.scrollHeight + 'px'
      textareaRef.current.focus()
    }
  }, [isEditing, note.text])

  const handleBlur = () => {
    if (!note.text.trim()) {
      updateStickyNote(note.id, "Empty note. Double click to edit.")
    }
    setIsEditing(false)
  }

  return (
    <motion.div
      ref={noteRef}
      initial={{ opacity: 0, scale: 0.9, y: 10 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      whileHover={{ scale: isDragging ? 1.05 : 1.01 }}
      className={`absolute rounded-2xl border backdrop-blur-xl transition-colors group ${activeStyle} ${isDragging ? 'cursor-grabbing z-[100] ring-2 ring-white/20' : 'cursor-grab z-40'}`}
      style={{ left: note.x, top: note.y, minWidth: 240, maxWidth: 320 }}
      onMouseDown={handleMouseDown}
      onClick={(e) => e.stopPropagation()}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Hover Toolbar */}
      <AnimatePresence>
        {isHovered && !isDragging && (
          <motion.div
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 2 }}
            className="absolute -top-10 left-1/2 -translate-x-1/2 flex items-center gap-1.5 p-1.5 rounded-xl bg-background/90 backdrop-blur-md border border-border shadow-xl z-50"
          >
            {Object.keys(colorMap).map(c => (
              <button
                key={c}
                onClick={(e) => { e.stopPropagation(); changeStickyNoteColor(note.id, c) }}
                className={`w-5 h-5 rounded-full transition-transform hover:scale-110 ${c === 'yellow' ? 'bg-amber-400' : c === 'blue' ? 'bg-sky-400' : c === 'pink' ? 'bg-rose-400' : c === 'green' ? 'bg-emerald-400' : 'bg-purple-400'} ${baseColorKey === c ? 'ring-2 ring-white ring-offset-1 ring-offset-background' : ''}`}
              />
            ))}
            <div className="w-px h-4 bg-border mx-1" />
            <button
              onClick={(e) => { e.stopPropagation(); setIsEditing(true) }}
              className="p-1 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            >
              <Edit2 size={14} />
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); removeStickyNote(note.id) }}
              className="p-1 rounded-lg hover:bg-red-500/20 text-red-400 transition-colors"
            >
              <X size={14} />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="p-5 flex flex-col gap-2">
        <div className="flex items-center justify-between opacity-50 group-hover:opacity-100 transition-opacity">
          <GripHorizontal size={14} className="text-current/50 mx-auto cursor-grab active:cursor-grabbing" />
        </div>
        
        {isEditing ? (
          <textarea
            ref={textareaRef}
            className="w-full bg-transparent border-none resize-none focus:outline-none placeholder-current/30 text-sm font-medium leading-relaxed overflow-hidden"
            placeholder="Type a note (Markdown supported)..."
            value={note.text}
            onChange={(e) => {
              updateStickyNote(note.id, e.target.value)
              e.target.style.height = 'auto'
              e.target.style.height = e.target.scrollHeight + 'px'
            }}
            onBlur={handleBlur}
            onKeyDown={(e) => {
              if (e.key === 'Escape') handleBlur()
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleBlur()
            }}
            autoFocus
          />
        ) : (
          <div 
            className="text-sm font-medium leading-relaxed cursor-text"
            onDoubleClick={(e) => { e.stopPropagation(); setIsEditing(true) }}
          >
            <ReactMarkdown
              components={{
                p: ({node, ...props}) => <p className="mb-2 last:mb-0" {...props} />,
                ul: ({node, ...props}) => <ul className="list-disc pl-4 mb-2 last:mb-0" {...props} />,
                ol: ({node, ...props}) => <ol className="list-decimal pl-4 mb-2 last:mb-0" {...props} />,
                li: ({node, ...props}) => <li className="mb-1" {...props} />,
                h1: ({node, ...props}) => <h1 className="text-lg font-bold mb-2 mt-4 first:mt-0" {...props} />,
                h2: ({node, ...props}) => <h2 className="text-base font-bold mb-2 mt-3 first:mt-0" {...props} />,
                h3: ({node, ...props}) => <h3 className="text-sm font-bold mb-1 mt-2 first:mt-0" {...props} />,
                a: ({node, ...props}) => <a className="underline hover:opacity-80" target="_blank" rel="noopener noreferrer" {...props} />,
                strong: ({node, ...props}) => <strong className="font-bold" {...props} />,
                em: ({node, ...props}) => <em className="italic opacity-90" {...props} />,
                blockquote: ({node, ...props}) => <blockquote className="border-l-2 border-current/30 pl-3 italic opacity-90 my-2" {...props} />,
              }}
            >{note.text}</ReactMarkdown>
          </div>
        )}
      </div>
    </motion.div>
  )
}
