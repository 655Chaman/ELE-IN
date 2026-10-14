import { useState } from "react"
import { motion } from "motion/react"
import { toast } from "sonner"
import { Trash2 } from "lucide-react"
import { fetchWithAuth } from "@/lib/apiClient"
import { friendlyToast } from "../FriendlyError"

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
      friendlyToast('Failed to delete lead — please try again.', e);
    }
    setIsDeleting(false);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-4">
      <motion.div 
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="absolute inset-0 bg-black/30 backdrop-blur-sm"
        onClick={onClose}
      />
      <motion.div 
        initial={{ opacity: 0, scale: 0.95, y: 10 }} 
        animate={{ opacity: 1, scale: 1, y: 0 }} 
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        className="relative w-full max-w-md bg-white border border-gray-100 shadow-2xl rounded-[24px] overflow-hidden"
      >
        <div className="p-6 text-center">
          <div className="w-12 h-12 rounded-full bg-red-50 border border-red-100 mx-auto flex items-center justify-center mb-5">
            <Trash2 size={20} className="text-red-500" />
          </div>
          <h2 className="text-[20px] font-bold text-gray-900 mb-2">Delete Lead List?</h2>
          <p className="text-[14px] text-gray-500 mb-8 leading-relaxed">
            Are you sure you want to delete <strong>{list.name}</strong>? This will permanently remove {list.row_count > 0 ? `${list.row_count} leads` : "all leads"} from this list. This action cannot be undone.
          </p>
          <div className="flex gap-3">
            <button
              onClick={onClose}
              disabled={isDeleting}
              className="flex-1 py-2.5 rounded-[12px] border border-gray-200 bg-white hover:bg-gray-50 text-gray-700 text-[15px] font-semibold transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleDelete}
              disabled={isDeleting}
              className="flex-1 py-2.5 rounded-[12px] bg-red-600 hover:bg-red-700 text-white text-[15px] font-semibold transition-colors"
            >
              {isDeleting ? "Deleting..." : "Yes, Delete"}
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
