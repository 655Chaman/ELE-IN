import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import { ChevronDown, Check } from 'lucide-react'

interface Option {
  id: string
  name: string
}

interface FilterDropdownProps {
  label: string
  icon: any
  options: Option[]
  selectedIds: string[]
  onChange: (ids: string[]) => void
  placeholder?: string
}

export function FilterDropdown({ label, icon: Icon, options, selectedIds, onChange, placeholder = "All" }: FilterDropdownProps) {
  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const toggleOption = (id: string) => {
    if (selectedIds.includes(id)) {
      onChange(selectedIds.filter(x => x !== id))
    } else {
      onChange([...selectedIds, id])
    }
  }

  return (
    <div className="flex flex-col gap-1.5" ref={dropdownRef}>
      <span className="text-xs font-semibold text-muted-foreground ml-1">{label}</span>
      <div className="relative">
        <div 
          onClick={() => setIsOpen(!isOpen)}
          className="flex items-center gap-2 px-4 py-2 bg-background border border-border rounded-xl cursor-pointer hover:border-primary/50 transition-colors"
        >
          <Icon size={16} className="text-muted-foreground transition-colors" />
          <span className="text-sm font-medium whitespace-nowrap min-w-[120px]">
            {selectedIds.length === 0 ? placeholder : `${selectedIds.length} Selected`}
          </span>
          <ChevronDown size={14} className="text-muted-foreground ml-2" />
        </div>

        <AnimatePresence>
          {isOpen && (
            <motion.div
              initial={{ opacity: 0, y: 5 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 5 }}
              transition={{ duration: 0.15 }}
              className="absolute top-full left-0 mt-2 w-64 bg-card border border-border/50 rounded-xl shadow-xl z-50 overflow-hidden"
            >
              <div className="max-h-64 overflow-y-auto p-2 flex flex-col gap-1">
                {options.length === 0 ? (
                  <div className="px-3 py-2 text-sm text-muted-foreground text-center">No options available</div>
                ) : (
                  options.map(opt => {
                    const isSelected = selectedIds.includes(opt.id)
                    return (
                      <div
                        key={opt.id}
                        onClick={() => toggleOption(opt.id)}
                        className={`flex items-center justify-between px-3 py-2 rounded-lg cursor-pointer text-sm transition-colors ${
                          isSelected ? 'bg-primary/10 text-primary font-medium' : 'hover:bg-muted text-foreground'
                        }`}
                      >
                        <span className="truncate pr-4">{opt.name}</span>
                        {isSelected && <Check size={14} />}
                      </div>
                    )
                  })
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
