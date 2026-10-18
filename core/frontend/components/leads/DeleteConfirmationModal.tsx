import { useState, useEffect } from "react"
import { motion } from "motion/react"
import { toast } from "sonner"
import { Trash2 } from "lucide-react"
import { fetchWithAuth } from "@/lib/apiClient"
import { friendlyToast } from "../FriendlyError"

export function DeleteConfirmationModal({ list, onClose, onConfirm }: { list: any; onClose: () => void; onConfirm: () => void }) {
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !isDeleting) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose, isDeleting]);

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      const res = await fetchWithAuth(`/api/elein/leads/${list.id}`, {method: 'DELETE'});
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || "Failed to delete list");
      }
      toast.success("List deleted successfully");
      onConfirm();
      onClose();
    } catch (e: any) {
      friendlyToast(e?.message || 'Failed to delete list — please try again.', e);
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-4">
      <motion.div 
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        onClick={() => !isDeleting && onClose()}
      />
      <motion.div 
        initial={{ opacity: 0, scale: 0.95, y: 10 }} 
        animate={{ opacity: 1, scale: 1, y: 0 }} 
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-lead-title"
        aria-describedby="delete-lead-desc"
        className="relative w-full max-w-md bg-card border border-border shadow-2xl rounded-xl overflow-hidden text-card-foreground"
      >
        <div className="p-6 text-center">
          <div className="w-12 h-12 rounded-full bg-destructive/10 border border-destructive/20 mx-auto flex items-center justify-center mb-5">
            <Trash2 size={20} className="text-destructive" />
          </div>
          <h2 id="delete-lead-title" className="text-[20px] font-bold text-foreground mb-2">Delete Lead List?</h2>
          <p id="delete-lead-desc" className="text-[14px] text-muted-foreground mb-8 leading-relaxed">
            Are you sure you want to delete <strong className="text-foreground">{list.name}</strong>? This will permanently remove {list.row_count > 0 ? `${list.row_count} leads` : "all leads"} from this list. This action cannot be undone.
          </p>
          <div className="flex gap-3">
            <button
              type="button"
              onClick={onClose}
              disabled={isDeleting}
              className="flex-1 py-2.5 rounded-lg border border-border bg-card hover:bg-muted text-foreground text-[15px] font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-ring"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleDelete}
              disabled={isDeleting}
              className="flex-1 py-2.5 rounded-lg bg-destructive hover:bg-destructive/90 text-destructive-foreground text-[15px] font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-ring"
            >
              {isDeleting ? "Deleting..." : "Yes, Delete"}
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
