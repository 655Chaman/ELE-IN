import React, { useState, useRef, useEffect } from 'react';
import { ChevronDown } from 'lucide-react';


interface ComboboxProps {
  value?: string;
  options: string[];
  placeholder: string;
  onSelect: (val: string) => void;
  disabled?: boolean;
  clearOnSelect?: boolean;
}

export function Combobox({ value, options, placeholder, onSelect, disabled, clearOnSelect = true }: ComboboxProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [inputValue, setInputValue] = useState(value || "");
  const containerRef = useRef<HTMLDivElement>(null);

  // Sync internal value if external value changes (e.g. for employee range)
  useEffect(() => {
    if (value !== undefined) {
      setInputValue(value);
    }
  }, [value]);

  const filteredOptions = options.filter(o => 
    o.toLowerCase().includes(inputValue.toLowerCase())
  );

  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, []);

  const handleSelect = (val: string) => {
    onSelect(val);
    if (clearOnSelect) {
      setInputValue("");
    } else {
      setInputValue(val);
    }
    setIsOpen(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (inputValue.trim()) {
        handleSelect(inputValue.trim());
      }
    }
    if (e.key === 'Escape') {
      setIsOpen(false);
    }
  };

  return (
    <div className="relative w-full min-w-[200px]" ref={containerRef}>
      <div className="relative">
        <input
          type="text"
          value={inputValue}
          onChange={(e) => {
            setInputValue(e.target.value);
            setIsOpen(true);
            if (!clearOnSelect) {
              onSelect(e.target.value);
            }
          }}
          onFocus={() => setIsOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          className="w-full bg-black/40 border border-white/10 hover:border-white/30 rounded-xl pl-4 pr-10 py-2.5 text-sm text-gray-200 focus:outline-none focus:border-zinc-500/50 focus:ring-1 focus:ring-zinc-500/50 transition-all disabled:opacity-50 placeholder-gray-600 backdrop-blur-md"
        />
        <button 
          type="button" 
          onClick={() => setIsOpen(!isOpen)} 
          className="absolute right-0 top-0 h-full px-3 flex items-center justify-center text-gray-500 hover:text-white transition-colors"
        >
          <ChevronDown size={16} />
        </button>
      </div>

      {isOpen && (
        <div className="absolute top-full left-0 mt-2 w-full min-w-[250px] max-h-64 overflow-y-auto bg-black/80 backdrop-blur-xl border border-white/10 rounded-xl shadow-[0_10px_40px_rgba(0,0,0,0.5)] z-50 py-2">
          {filteredOptions.length > 0 ? (
            filteredOptions.map((opt) => (
              <div
                key={opt}
                onClick={() => handleSelect(opt)}
                className="px-4 py-2.5 text-sm text-gray-300 hover:bg-zinc-600/20 hover:text-white cursor-pointer transition-colors whitespace-nowrap"
              >
                {opt}
              </div>
            ))
          ) : (
            <div className="px-4 py-3 text-sm text-gray-500 italic">
              Press Enter to use "{inputValue}"
            </div>
          )}
        </div>
      )}
    </div>
  );
}
