import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import { ChevronDown, ArrowUpRight } from 'lucide-react'

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
    { id: 'get_customers', label: 'Customer Acquisition', info: 'Sequence decision-makers to book pipeline meetings.' },
    { id: 'hire_people', label: 'Talent Outreach', info: 'Engage candidates directly for open roles.' },
    { id: 'get_intros', label: 'Strategic Introductions', info: 'Connect with investors, partners, or warm connectors.' }
  ]
  
  return (
    <div className="relative" ref={ref}>
      <button 
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center justify-center gap-1.5 bg-primary hover:bg-primary/90 text-primary-foreground h-8 px-3.5 rounded-lg font-semibold text-xs transition-colors shadow-xs cursor-pointer"
      >
        <span>New Campaign</span>
        <ChevronDown size={13} className="opacity-80" />
      </button>
      
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            transition={{ duration: 0.12 }}
            className="absolute top-full right-0 mt-1.5 w-72 bg-card border border-border rounded-xl shadow-lg z-50 overflow-hidden"
          >
            <div className="p-1.5 flex flex-col gap-0.5">
              {options.map(opt => (
                <button
                  type="button"
                  key={opt.id}
                  className="flex flex-col gap-0.5 p-2.5 rounded-lg hover:bg-muted transition-colors cursor-pointer group text-left w-full"
                  onClick={() => { setIsOpen(false); onSelect(opt.id); }}
                >
                  <div className="flex items-center justify-between w-full">
                    <span className="text-xs font-semibold text-foreground group-hover:text-primary transition-colors">
                      {opt.label}
                    </span>
                    <ArrowUpRight size={12} className="text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                  <span className="text-[11px] text-muted-foreground leading-snug">
                    {opt.info}
                  </span>
                </button>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}