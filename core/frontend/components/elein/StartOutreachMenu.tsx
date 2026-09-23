import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import { Info, Users, Briefcase, Link as LinkIcon, Zap } from 'lucide-react'

export function StartOutreachMenu({ onSelect }: { onSelect: (id: string) => void }) {
  const [isOpen, setIsOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])
  
  const options = [
    { id: 'get_customers', icon: Users, label: 'Get customers', info: 'Message people who can buy. Goal: book a meeting.' },
    { id: 'hire_people', icon: Briefcase, label: 'Hire people', info: 'Message people you want on the team. Goal: a hire.' },
    { id: 'get_intros', icon: LinkIcon, label: 'Get intros', info: 'Message people who can open a door — investor, partner, or their network.' }
  ]
  
  return (
    <div className="relative" ref={ref}>
      <button 
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center justify-center gap-2 bg-success hover:bg-success/90 text-success-foreground px-6 py-3 rounded-2xl font-bold transition-all shadow-md active:scale-95"
      >
        <Zap size={18} className="fill-current text-success-foreground" /> Start outreach
      </button>
      
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: 8, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.95 }}
            transition={{ duration: 0.15, ease: [0.16, 1, 0.3, 1] }}
            className="absolute top-full right-0 mt-2 w-64 bg-card border border-border/50 rounded-2xl shadow-xl z-50 overflow-hidden"
          >
             <div className="p-2 flex flex-col gap-1">
               {options.map(opt => (
                 <div key={opt.id} className="flex items-center gap-2 p-2 rounded-xl hover:bg-muted/50 transition-colors group cursor-pointer" onClick={() => { setIsOpen(false); onSelect(opt.id); }}>
                   <div className="text-muted-foreground group-hover:text-primary transition-colors flex-shrink-0">
                     <opt.icon size={16} />
                   </div>
                   <div className="flex-1 text-sm font-semibold text-foreground text-left">
                     {opt.label}
                   </div>
                   <div className="text-muted-foreground hover:text-foreground transition-colors relative cursor-help group/info">
                     <Info size={14} />
                     <div className="absolute right-0 bottom-full mb-2 w-48 p-2 bg-foreground text-background text-[11px] rounded-lg opacity-0 group-hover/info:opacity-100 pointer-events-none transition-opacity z-50 text-left">
                       {opt.info}
                     </div>
                   </div>
                 </div>
               ))}
             </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
