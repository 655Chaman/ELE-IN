import * as Dialog from "@radix-ui/react-dialog";
import { useState } from "react";
import { Trash2, AlertTriangle, X, ShieldAlert } from "lucide-react";
import { motion, AnimatePresence } from "motion/react";
import { cn } from "@/lib/utils";

interface DeleteAccountConfirmationDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  accountId: string;
  accountName: string;
  onConfirm: (id: string, force?: boolean) => Promise<void>;
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
  const [hasConflict, setHasConflict] = useState(false);

  const handleDelete = async (force: boolean = false) => {
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await onConfirm(accountId, force);
      onOpenChange(false);
      setHasConflict(false);
    } catch (e: any) {
      const msg = e.message || 'Failed to remove account';
      setDeleteError(msg);
      if (
        msg.toLowerCase().includes('assigned to active campaign') ||
        msg.toLowerCase().includes('force=true') ||
        msg.includes('409')
      ) {
        setHasConflict(true);
      }
    } finally {
      setIsDeleting(false);
    }
  };

  const handleOpenChange = (open: boolean) => {
    if (!open) {
      setDeleteError(null);
      setHasConflict(false);
    }
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
                className="fixed inset-0 z-[100] bg-black/30 backdrop-blur-sm"
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
                <div className="rounded-xl bg-card shadow-2xl border border-border text-card-foreground p-6">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-destructive/10 text-destructive">
                        {hasConflict ? <ShieldAlert size={20} /> : <AlertTriangle size={20} />}
                      </div>
                      <div>
                        <Dialog.Title className="text-lg font-bold text-foreground">
                          {hasConflict ? `Active Campaigns Using ${accountName}` : `Disconnect ${accountName}?`}
                        </Dialog.Title>
                        <Dialog.Description className="mt-1 text-xs text-muted-foreground leading-relaxed">
                          {hasConflict
                            ? "This sender is currently powering active campaign sequences. Disconnecting will unassign it."
                            : `Disconnecting will remove ${accountName} from Ele-in. Any automated outreach assigned to this account will be stopped.`}
                        </Dialog.Description>
                      </div>
                    </div>
                    <Dialog.Close asChild>
                      <button type="button" aria-label="Close" className="flex h-8 w-8 items-center justify-center rounded-full bg-muted/50 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground cursor-pointer">
                        <X size={16} />
                      </button>
                    </Dialog.Close>
                  </div>

                  {/* Conflict or Error Callout */}
                  {deleteError && (
                    <div className={cn(
                      "mt-4 p-3 rounded-lg border text-xs leading-relaxed space-y-1.5",
                      hasConflict 
                        ? "bg-warning/10 border-warning/30 text-warning" 
                        : "bg-destructive/10 border-destructive/30 text-destructive"
                    )}>
                      <div className="flex items-start gap-2">
                        <AlertTriangle size={14} className="shrink-0 mt-0.5" />
                        <div className="space-y-1">
                          <p className="font-semibold">{deleteError}</p>
                          {hasConflict && (
                            <p className="text-[11px] opacity-90">
                              You can force disconnect to immediately pause this sender and decouple it from these campaigns.
                            </p>
                          )}
                        </div>
                      </div>
                    </div>
                  )}

                  <div className="mt-6 flex flex-col sm:flex-row justify-end gap-2.5">
                    <Dialog.Close asChild>
                      <button
                        type="button"
                        autoFocus
                        disabled={isDeleting}
                        className="rounded-xl border border-border bg-muted/50 hover:bg-muted px-4 py-2 text-xs font-semibold text-foreground transition-colors disabled:opacity-50 cursor-pointer"
                      >
                        Cancel
                      </button>
                    </Dialog.Close>

                    {hasConflict ? (
                      <button
                        type="button"
                        onClick={() => handleDelete(true)}
                        disabled={isDeleting}
                        className="flex items-center justify-center gap-2 rounded-xl bg-destructive hover:bg-destructive/90 px-4 py-2 text-xs font-bold text-destructive-foreground shadow-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                      >
                        {isDeleting ? (
                          <>
                            <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
                            <span>Force Disconnecting...</span>
                          </>
                        ) : (
                          <>
                            <Trash2 size={13} />
                            <span>Force Disconnect &amp; Decouple</span>
                          </>
                        )}
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => handleDelete(false)}
                        disabled={isDeleting}
                        className="flex items-center justify-center gap-2 rounded-xl bg-destructive hover:bg-destructive/90 px-4 py-2 text-xs font-bold text-destructive-foreground shadow-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                      >
                        {isDeleting ? (
                          <>
                            <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
                            <span>Disconnecting...</span>
                          </>
                        ) : (
                          <>
                            <Trash2 size={13} />
                            <span>Yes, disconnect account</span>
                          </>
                        )}
                      </button>
                    )}
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
