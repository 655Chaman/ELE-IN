import * as Dialog from "@radix-ui/react-dialog";
import { useState } from "react";
import { Trash2, AlertTriangle, X } from "lucide-react";
import { motion, AnimatePresence } from "motion/react";

interface DeleteAccountConfirmationDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  accountId: string;
  accountName: string;
  onConfirm: (id: string) => Promise<void>;
}

export default function DeleteAccountConfirmationDialog({
  isOpen,
  onOpenChange,
  accountId,
  accountName,
  onConfirm,
}: DeleteAccountConfirmationDialogProps) {
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const handleDelete = async () => {
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await onConfirm(accountId);
      onOpenChange(false);
    } catch (e: any) {
      setDeleteError(e.message || "Failed to remove account");
    } finally {
      setIsDeleting(false);
    }
  };

  const handleOpenChange = (open: boolean) => {
    if (!open) setDeleteError(null);
    onOpenChange(open);
  };

  return (
    <Dialog.Root open={isOpen} onOpenChange={handleOpenChange}>
      <AnimatePresence>
        {isOpen && (
          <Dialog.Portal forceMount>
            <Dialog.Overlay asChild>
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="fixed inset-0 z-[100] bg-black/60 backdrop-blur-sm"
              />
            </Dialog.Overlay>
            <Dialog.Content asChild>
              <motion.div
                initial={{ opacity: 0, scale: 0.95, y: 10 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 10 }}
                transition={{ duration: 0.2 }}
                className="fixed left-[50%] top-[50%] z-[101] w-full max-w-md translate-x-[-50%] translate-y-[-50%] p-4"
              >
                <div className="rounded-2xl border border-border bg-card p-6 shadow-2xl">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-destructive/10 text-destructive">
                        <AlertTriangle size={20} />
                      </div>
                      <div>
                        <Dialog.Title className="text-lg font-bold text-foreground">
                          Disconnect {accountName}?
                        </Dialog.Title>
                        <Dialog.Description className="mt-1 text-sm text-muted-foreground leading-relaxed">
                          This will disconnect <span className="font-semibold text-foreground">{accountName}</span> from Ele-in. Any campaigns using this account will be paused.
                        </Dialog.Description>
                        {deleteError && <p className='text-red-500 text-xs mt-2'>{deleteError}</p>}
                      </div>
                    </div>
                    <Dialog.Close asChild>
                      <button className="flex h-8 w-8 items-center justify-center rounded-full bg-muted/50 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground">
                        <X size={16} />
                      </button>
                    </Dialog.Close>
                  </div>

                  <div className="mt-8 flex justify-end gap-3">
                    <Dialog.Close asChild>
                      <button
                        autoFocus
                        disabled={isDeleting}
                        className="rounded-lg bg-muted px-4 py-2 text-sm font-semibold text-foreground transition-colors hover:bg-muted/80 disabled:opacity-50"
                      >
                        Cancel
                      </button>
                    </Dialog.Close>
                    <button
                      onClick={handleDelete}
                      disabled={isDeleting}
                      className="flex items-center gap-2 rounded-lg bg-destructive px-4 py-2 text-sm font-bold text-destructive-foreground shadow-sm transition-all hover:bg-destructive/90 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isDeleting ? (
                        <>
                          <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
                          Disconnecting...
                        </>
                      ) : (
                        <>
                          <Trash2 size={14} />
                          Yes, disconnect account
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </motion.div>
            </Dialog.Content>
          </Dialog.Portal>
        )}
      </AnimatePresence>
    </Dialog.Root>
  );
}
