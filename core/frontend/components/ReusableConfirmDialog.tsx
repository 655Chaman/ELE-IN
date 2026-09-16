import { useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';

interface ConfirmDialogProps {
  isOpen: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  isDestructive?: boolean;
}

export function ReusableConfirmDialog({
  isOpen,
  title,
  description,
  confirmLabel,
  onConfirm,
  onCancel,
  isDestructive = true
}: ConfirmDialogProps) {
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (isOpen && e.key === 'Escape') {
        onCancel();
      }
    };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [isOpen, onCancel]);

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4">
          <motion.div 
            initial={{ opacity: 0 }} 
            animate={{ opacity: 1 }} 
            exit={{ opacity: 0 }} 
            className="absolute inset-0 bg-slate-900/40 dark:bg-black/60 backdrop-blur-sm"
            onClick={onCancel}
          />
          <motion.div 
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            className="relative bg-white dark:bg-card border border-slate-200 dark:border-border/50 shadow-2xl rounded-3xl w-full max-w-md p-6 overflow-hidden flex flex-col focus:outline-none"
            role="dialog"
            aria-modal="true"
            aria-labelledby="confirm-title"
            aria-describedby="confirm-description"
          >
            <h3 id="confirm-title" className="text-lg font-semibold text-foreground mb-2">{title}</h3>
            <p id="confirm-description" className="text-sm text-muted-foreground mb-6 leading-relaxed">
              {description}
            </p>
            <div className="flex gap-3 w-full justify-end">
              <button 
                autoFocus
                onClick={onCancel}
                className="px-4 py-2.5 rounded-xl border border-slate-200 dark:border-border/50 text-foreground text-sm font-medium hover:bg-slate-50 dark:hover:bg-muted/50 transition-colors"
              >
                Cancel
              </button>
              <button 
                onClick={onConfirm}
                className={`px-4 py-2.5 rounded-xl text-sm font-medium transition-colors shadow-sm ${
                  isDestructive 
                    ? 'bg-red-500 text-white hover:bg-red-600 shadow-red-500/20' 
                    : 'bg-blue-600 text-white hover:bg-blue-700 shadow-blue-500/20'
                }`}
              >
                {confirmLabel}
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
