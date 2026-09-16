import { useState } from "react"
import { motion } from "motion/react"
import { toast } from "sonner"
import { Trash2 } from "lucide-react"
import { fetchWithAuth } from "@/lib/apiClient"

export function DeleteConfirmationModal({ list, onClose, onConfirm }: { list: any; onClose: () => void; onConfirm: () => void }) {
  const [isDeleting, setIsDeleting] = useState(false);

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      const res = await fetchWithAuth(`/api/elein/leads/${list.id}`, {method: 'DELETE'});
      if (!res.ok) throw new Error("Failed to delete");
      toast.success("List deleted successfully");
      onConfirm();
    } catch (e: any) {
      toast.error(e.message);
    }
    setIsDeleting(false);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-4">
      <motion.div 
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />
      <motion.div 
        initial={{ opacity: 0, scale: 0.95, y: 10 }} 
        animate={{ opacity: 1, scale: 1, y: 0 }} 
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        className="relative w-full max-w-md bg-background border border-border shadow-2xl rounded-2xl overflow-hidden"
      >
        <div className="p-6 text-center">
          <div className="w-12 h-12 rounded-full bg-destructive/10 mx-auto flex items-center justify-center mb-4">
            <Trash2 size={20} className="text-destructive" />
          </div>
          <h2 className="text-xl font-bold text-foreground mb-2">Delete Lead List?</h2>
          <p className="text-sm text-muted-foreground mb-6">
            Are you sure you want to delete <strong>{list.name}</strong>? This will permanently remove {list.row_count > 0 ? `${list.row_count} leads` : "all leads"} from this list. This action cannot be undone.
          </p>
          <div className="flex gap-3">
            <button
              onClick={onClose}
              disabled={isDeleting}
              className="flex-1 py-2.5 rounded-xl border border-border bg-background hover:bg-muted text-sm font-medium transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleDelete}
              disabled={isDeleting}
              className="flex-1 py-2.5 rounded-xl bg-destructive hover:bg-destructive/90 text-destructive-foreground text-sm font-medium transition-colors"
            >
              {isDeleting ? "Deleting..." : "Yes, Delete"}
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
