import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import { ChevronDown, Check } from 'lucide-react'

interface Option {
  id: string
  name: string
}

interface FilterDropdownProps {
  label: string
  icon?: any
  options: Option[]
  selectedIds: string[]
  onChange: (ids: string[]) => void
  placeholder?: string
}

export function FilterDropdown({ label, options, selectedIds, onChange, placeholder = "All" }: FilterDropdownProps) {
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

  const cleanLabel = label.replace(/:$/, '')

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 h-8 px-3 bg-background border border-border rounded-lg cursor-pointer hover:border-foreground/30 transition-colors text-xs"
      >
        <span className="text-muted-foreground font-medium">{cleanLabel}</span>
        <span className="w-px h-3.5 bg-border" />
        <span className="font-semibold text-foreground whitespace-nowrap">
          {selectedIds.length === 0 ? placeholder : `${selectedIds.length} Selected`}
        </span>
        <ChevronDown size={13} className="text-muted-foreground ml-0.5" />
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            transition={{ duration: 0.12 }}
            className="absolute top-full left-0 mt-1.5 w-60 bg-card border border-border rounded-xl shadow-lg z-50 overflow-hidden"
          >
            <div className="max-h-60 overflow-y-auto p-1.5 flex flex-col gap-0.5">
              {options.length === 0 ? (
                <div className="px-3 py-2 text-xs text-muted-foreground text-center">No options available</div>
              ) : (
                options.map(opt => {
                  const isSelected = selectedIds.includes(opt.id)
                  return (
                    <div
                      key={opt.id}
                      onClick={() => toggleOption(opt.id)}
                      className={`flex items-center justify-between px-2.5 py-1.5 rounded-xl cursor-pointer text-xs transition-colors ${
                        isSelected ? 'bg-primary/10 text-primary font-semibold' : 'hover:bg-muted text-foreground'
                      }`}
                    >
                      <span className="truncate pr-4">{opt.name}</span>
                      {isSelected && <Check size={13} />}
                    </div>
                  )
                })
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
