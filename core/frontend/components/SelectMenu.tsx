import { useState, useRef, useEffect } from 'react';
import { ChevronDown } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';

export interface SelectOption {
  value: string;
  label: string;
}

interface SelectMenuProps {
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  className?: string;
  menuClassName?: string;
}

export function SelectMenu({ value, options, onChange, className = "", menuClassName = "" }: SelectMenuProps) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, []);

  const selectedOption = options.find(o => o.value === value) || options[0];

  return (
    <div className={`relative ${className}`} ref={containerRef}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between bg-surface/50 border border-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-accent/50 hover:bg-surface transition-colors"
      >
        <span className="truncate">{selectedOption?.label}</span>
        <ChevronDown size={16} className={`text-gray-400 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: -5, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -5, scale: 0.98 }}
            transition={{ duration: 0.15 }}
            className={`absolute z-50 w-full mt-1 bg-zinc-900 border border-zinc-800 rounded-lg shadow-xl overflow-hidden py-1 ${menuClassName}`}
          >
            <div className="max-h-60 overflow-y-auto custom-scrollbar">
              {options.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => {
                    onChange(opt.value);
                    setIsOpen(false);
                  }}
                  className={`w-full text-left px-3 py-2 text-sm transition-colors ${
                    opt.value === value 
                      ? 'bg-accent/10 text-accent font-medium' 
                      : 'text-gray-300 hover:bg-white/5 hover:text-white'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
