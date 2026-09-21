import React, { useState } from "react";
import { ChevronDown } from "lucide-react";
import { motion, AnimatePresence } from "motion/react";
import { cn } from "@/lib/utils";

interface AdvancedSettingsPanelProps {
  children: React.ReactNode;
  label?: string;
  defaultOpen?: boolean;
  className?: string;
}

export function AdvancedSettingsPanel({
  children,
  label = "Advanced Settings",
  defaultOpen = false,
  className
}: AdvancedSettingsPanelProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className={cn("w-full border border-border/50 rounded-xl overflow-hidden bg-muted/10", className)}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between p-3 text-xs font-semibold text-muted-foreground hover:text-foreground hover:bg-muted/30 transition-colors"
      >
        <span>{label}</span>
        <ChevronDown 
          size={14} 
          className={cn("transition-transform duration-200", isOpen ? "rotate-180" : "")} 
        />
      </button>
      <AnimatePresence initial={false}>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeInOut" }}
            className="overflow-hidden"
          >
            <div className="p-4 pt-1 border-t border-border/50">
              {children}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
