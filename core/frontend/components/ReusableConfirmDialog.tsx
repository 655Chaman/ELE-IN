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
            className="relative bg-white border border-gray-100 shadow-2xl rounded-[24px] w-full max-w-md p-6 overflow-hidden flex flex-col focus:outline-none"
            role="dialog"
            aria-modal="true"
            aria-labelledby="confirm-title"
            aria-describedby="confirm-description"
          >
            <h3 id="confirm-title" className="text-[20px] font-bold text-gray-900 mb-2">{title}</h3>
            <p id="confirm-description" className="text-[14px] text-gray-500 mb-8 leading-relaxed">
              {description}
            </p>
            <div className="flex gap-3 w-full justify-end">
              <button 
                autoFocus
                onClick={onCancel}
                className="px-4 py-2.5 rounded-[12px] border border-gray-200 bg-white text-gray-700 text-[15px] font-semibold hover:bg-gray-50 transition-colors"
              >
                Cancel
              </button>
              <button 
                onClick={onConfirm}
                className={`px-4 py-2.5 rounded-[12px] text-[15px] font-semibold transition-colors shadow-sm ${
                  isDestructive 
                    ? 'bg-red-600 text-white hover:bg-red-700 shadow-sm' 
                    : 'bg-gray-900 text-white hover:bg-gray-800 shadow-sm'
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
