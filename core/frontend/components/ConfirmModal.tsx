import { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertTriangle, X } from 'lucide-react';

interface ConfirmModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
}

export function ConfirmModal({ 
  isOpen, 
  onClose, 
  onConfirm, 
  title, 
  message, 
  confirmText = "Confirm", 
  cancelText = "Cancel" 
}: ConfirmModalProps) {
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
          />
          <div className="fixed inset-0 z-50 flex items-center justify-center pointer-events-none p-4">
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              transition={{ duration: 0.2 }}
              className="w-full max-w-[28rem] bg-white dark:bg-[#121316] border border-gray-200 dark:border-white/10 rounded-[24px] shadow-2xl overflow-hidden pointer-events-auto flex flex-col relative text-gray-900 dark:text-white"
            >
              <button 
                onClick={onClose}
                className="absolute top-6 right-6 w-8 h-8 rounded-full bg-gray-50 dark:bg-white/5 flex items-center justify-center text-gray-400 dark:text-zinc-400 hover:text-gray-700 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-white/10 transition-colors"
              >
                <X size={16} />
              </button>

              <div className="p-8">
                <div className="w-12 h-12 rounded-full bg-red-50 dark:bg-rose-500/15 border border-red-100 dark:border-rose-500/30 flex items-center justify-center mb-5">
                  <AlertTriangle className="w-6 h-6 text-red-500 dark:text-rose-400" />
                </div>
                
                <h2 className="text-[20px] font-bold text-gray-900 dark:text-white mb-2">{title}</h2>
                <p className="text-[14px] text-gray-500 dark:text-zinc-400 leading-relaxed mb-8">
                  {message}
                </p>

                <div className="flex items-center gap-3 w-full">
                  <button
                    onClick={onClose}
                    className="flex-1 px-4 py-3 rounded-[12px] bg-white dark:bg-white/5 border border-gray-200 dark:border-white/10 text-gray-700 dark:text-zinc-300 text-[15px] font-semibold hover:bg-gray-50 dark:hover:bg-white/10 transition-colors"
                  >
                    {cancelText}
                  </button>
                  <button
                    onClick={() => {
                      onConfirm();
                      onClose();
                    }}
                    className="flex-1 px-4 py-3 rounded-[12px] bg-gray-900 dark:bg-primary hover:bg-gray-800 dark:hover:bg-primary/90 text-white text-[15px] font-semibold transition-all shadow-sm"
                  >
                    {confirmText}
                  </button>
                </div>
              </div>
            </motion.div>
          </div>
        </>
      )}
    </AnimatePresence>
  );
}
