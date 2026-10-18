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
            className="absolute inset-0 bg-black/30 backdrop-blur-sm"
            onClick={onCancel}
          />
          <motion.div 
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            className="relative bg-card border border-border shadow-2xl rounded-xl w-full max-w-md p-6 overflow-hidden flex flex-col focus:outline-none text-card-foreground"
            role="dialog"
            aria-modal="true"
            aria-labelledby="confirm-title"
            aria-describedby="confirm-description"
          >
            <h3 id="confirm-title" className="text-[20px] font-bold text-foreground mb-2">{title}</h3>
            <p id="confirm-description" className="text-[14px] text-muted-foreground mb-8 leading-relaxed">
              {description}
            </p>
            <div className="flex gap-3 w-full justify-end">
              <button 
                type="button"
                autoFocus
                onClick={onCancel}
                className="px-4 py-2.5 rounded-lg border border-border bg-card text-foreground text-[15px] font-semibold hover:bg-muted transition-colors focus:outline-none focus:ring-2 focus:ring-ring"
              >
                Cancel
              </button>
              <button 
                type="button"
                onClick={onConfirm}
                className={`px-4 py-2.5 rounded-lg text-[15px] font-semibold transition-colors shadow-sm focus:outline-none focus:ring-2 focus:ring-ring ${
                  isDestructive 
                    ? 'bg-destructive text-destructive-foreground hover:bg-destructive/90' 
                    : 'bg-primary text-primary-foreground hover:bg-primary/90'
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
