import { useState, useEffect, useRef } from "react";
import { AlertTriangle, Trash2, Loader2, X } from "lucide-react";
import { toast } from "sonner"
import { friendlyToast } from "../../components/FriendlyError";
import { useWorkspaceData } from "./useWorkspaceData";
import { motion, AnimatePresence } from "motion/react";
import { fetcher, fetchWithAuth } from "@/lib/apiClient";
import { SettingsLoadingSkeleton } from "@/components/SettingsLoadingSkeleton";
import { EmptyState } from "@/components/EmptyState";

export function DangerZone({ workspaceId }: { workspaceId: string | null }) {
  const [confirmText, setConfirmText] = useState("");
  const [requesting, setRequesting] = useState(false);
  const [deletionRequested, setDeletionRequested] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [countdown, setCountdown] = useState<number | null>(null);
  
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  const { data: workspaceData, error: fetchError, mutate: mutateData, isLoading } = useWorkspaceData(workspaceId);

  const activeWsName = workspaceData?.name || "";
  const isPendingDeletion = deletionRequested || workspaceData?.status === "pending_deletion";
  const isConfirmed = confirmText === activeWsName && activeWsName !== "";

  const handleCancelDeletion = async () => {
    if (!workspaceId || cancelling) return;
    setCancelling(true);
    try {
      const res = await fetchWithAuth(`/api/workspaces/${workspaceId}/cancel-deletion`, {
        method: "POST",
      });
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText || "Failed to cancel deletion");
      }
      toast.success(`Deletion cancelled. Workspace "${activeWsName}" restored.`);
      setDeletionRequested(false);
      mutateData();
    } catch (e: any) {
      friendlyToast('Failed to cancel deletion — please try again.', e);
    } finally {
      setCancelling(false);
    }
  };


  const confirmDeletion = async () => {
    const isConfirmedCheck = (confirmText === activeWsName);
    if (!workspaceId || !isConfirmedCheck || requesting) return;
    
    // Extra safety: double check the name matches in backend, but we'll send a confirm flag
    setRequesting(true);
    try {
      if (!workspaceId) return;
      const res = await fetchWithAuth(`/api/workspaces/${workspaceId}/request-deletion`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: true }),
      });
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText || "Failed to request deletion");
      }
      setDeletionRequested(true);
      setConfirmText("");
      toast.success(`Workspace "${activeWsName}" deletion requested. 14-day grace period started.`);
      mutateData();
    } catch (e: any) {
      friendlyToast('Failed to request deletion — please try again.', e);
    } finally {
      setRequesting(false);
      setCountdown(null);
    }
  };

  if (fetchError) {
    return (
      <div className="flex flex-col items-center justify-center p-6 border border-destructive/20 bg-destructive/5 rounded-lg text-destructive">
        <AlertTriangle className="h-8 w-8 mb-2" />
        <h3 className="font-semibold">Failed to load workspace data</h3>
        <p className="text-sm opacity-80">Please check your connection and try again.</p>
      </div>
    );
  }

  if (!workspaceId) {
    return <EmptyState title="No Workspace Selected" description="No workspace selected." />;
  }

  if (isLoading && !activeWsName) {
    return <SettingsLoadingSkeleton />;
  }

  const consequences = [
    "All campaign data and analytics",
    "All connected LinkedIn accounts",
    "All knowledge base assets",
    "All lead lists and sequences",
    "All team member access"
  ];
  
  // Determine input styling based on progress
  let inputBorderClass = "border-gray-200 focus:ring-border";
  if (confirmText.length > 0 && confirmText !== activeWsName) {
    inputBorderClass = "border-warning/50 focus:ring-warning/30 text-warning";
  } else if (isConfirmed) {
    inputBorderClass = "border-destructive focus:ring-destructive shadow-[0_0_15px_rgba(239,68,68,0.3)] text-destructive";
  }

  return (
    <div className="space-y-6">
      {/* 
        Psychological Principle: High Friction by Design
        Desaturated background, heavy red borders, warning iconography 
      */}
      <div className="p-6 md:p-8 rounded-xl border border-border bg-card relative overflow-hidden shadow-sm">
        
        {isPendingDeletion && (
          <div className="bg-destructive text-destructive-foreground px-6 py-4 flex items-center justify-between font-bold rounded-t-xl mb-4">
            <div className="flex items-center gap-3">
              <AlertTriangle className="animate-pulse" />
              <span>Workspace Pending Permanent Deletion</span>
            </div>
            <div className="text-xs bg-background/20 px-3 py-1 rounded-md font-mono">
              14-Day Grace Window Active
            </div>
          </div>
        )}

        <div>
          <div className="flex items-start gap-5 mb-8">
            <div className="p-4 bg-destructive/10 text-destructive rounded-xl border border-destructive/20 relative">
              <AlertTriangle size={32} />
            </div>
            <div>
              <h2 className="text-2xl font-bold tracking-tight text-destructive mb-1">
                Danger Zone
              </h2>
              <p className="text-sm text-muted-foreground mt-1">
                This is a highly destructive action. Operations here will result in permanent workspace and lead loss.
              </p>
            </div>
          </div>

          <div className="max-w-2xl bg-background border border-border/60 rounded-xl p-6 md:p-8 relative shadow-lg">
            
            {isPendingDeletion ? (
              <div className="space-y-6">
                <div className="p-5 bg-destructive/10 rounded-lg border border-destructive/30">
                  <h3 className="text-lg font-bold tracking-tight text-foreground">
                    Deletion Grace Period Active
                  </h3>
                  <p className="text-sm text-muted-foreground mt-1">
                    A 14-day grace period is currently running for <strong>{activeWsName}</strong>. The following actions have taken place:
                  </p>
                  <ul className="mt-4 space-y-2">
                    <li className="flex items-center gap-2 text-sm font-semibold text-muted-foreground">
                      <X size={16} className="text-destructive shrink-0" /> Campaigns have been automatically paused
                    </li>
                    <li className="flex items-center gap-2 text-sm font-semibold text-muted-foreground">
                      <X size={16} className="text-destructive shrink-0" /> Webhooks and integrations paused
                    </li>
                    <li className="flex items-center gap-2 text-sm font-semibold text-muted-foreground">
                      <X size={16} className="text-destructive shrink-0" /> Non-owner access restricted
                    </li>
                  </ul>
                </div>
                
                <div className="p-5 bg-muted/20 border border-border/60 rounded-lg flex flex-col items-center text-center">
                  <p className="text-sm font-bold text-foreground mb-4">
                    Changed your mind? Restore this workspace immediately:
                  </p>
                  <button
                    type="button"
                    onClick={handleCancelDeletion}
                    disabled={cancelling}
                    className="flex items-center justify-center gap-2 px-6 py-2.5 bg-primary text-primary-foreground font-bold rounded-xl hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-md cursor-pointer"
                  >
                    {cancelling ? (
                      <>
                        <Loader2 size={18} className="animate-spin" />
                        <span>Restoring Workspace...</span>
                      </>
                    ) : (
                      <>
                        <X size={18} />
                        <span>Cancel Deletion & Restore Workspace</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-8">
                <div className="space-y-3">
                  <h3 className="text-lg font-bold tracking-tight text-foreground">
                    What will be permanently deleted:
                  </h3>
                  <div className="space-y-2.5">
                    {consequences.map((item, i) => (
                      <div key={i} className="flex items-center gap-3 p-3 bg-muted/20 border border-border/60 rounded-lg">
                        <div className="p-1 bg-destructive/10 rounded-md">
                          <X size={16} className="text-destructive" />
                        </div>
                        <span className="text-sm font-semibold text-foreground">{item}</span>
                      </div>
                    ))}
                  </div>
                </div>
                
                <div className="p-5 bg-destructive/5 border border-destructive/20 rounded-lg flex items-start gap-4 shadow-sm">
                  <div className="text-destructive mt-0.5 p-2 bg-destructive/10 rounded-full">
                    <AlertTriangle size={20} />
                  </div>
                  <div className="space-y-1">
                    <p className="text-sm font-bold text-destructive">Caution: 14-Day Grace Period Protection</p>
                    <p className="text-sm text-muted-foreground font-medium leading-relaxed">
                      Initiating deletion pauses all outreach instantly and starts a 14-day hold before permanent GDPR purge.
                      <br/>You can cancel anytime during this window from this page.
                    </p>
                  </div>
                </div>

                <div className="space-y-3">
                  <label className="text-sm font-bold block text-foreground">
                    To commit to this action, type <span className="text-foreground bg-muted border border-border px-2 py-0.5 rounded select-none font-mono">{activeWsName}</span> below:
                  </label>
                  
                  <div className="relative group">
                    <input
                      type="text"
                      value={confirmText}
                      onChange={(e) => setConfirmText(e.target.value)}
                      autoComplete="off"
                      autoCorrect="off"
                      spellCheck="false"
                      placeholder="Type the workspace name manually"
                      className={`w-full bg-background border-2 rounded-xl px-5 py-3 text-sm focus:outline-none transition-all font-bold placeholder:text-muted-foreground ${inputBorderClass}`}
                    />
                  </div>
                </div>

                <div className="pt-2 flex justify-end">
                  <button
                    type="button"
                    onClick={confirmDeletion}
                    disabled={!isConfirmed || requesting}
                    className={`
                      relative flex items-center justify-center gap-2 px-8 py-3 font-bold rounded-xl transition-all duration-300 cursor-pointer
                      ${!isConfirmed 
                        ? 'bg-muted text-muted-foreground border border-border cursor-not-allowed opacity-60' 
                        : countdown !== null 
                          ? 'bg-destructive/80 text-white scale-95 shadow-[0_0_20px_rgba(239,68,68,0.5)]'
                          : 'bg-destructive text-white hover:bg-destructive/90 shadow-[0_0_10px_rgba(239,68,68,0.2)] hover:shadow-[0_0_20px_rgba(239,68,68,0.4)]'
                      }
                    `}
                  >
                    <AnimatePresence mode="wait">
                      {requesting ? (
                        <motion.div key="loading" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex items-center gap-2">
                          <Loader2 size={18} className="animate-spin" />
                          <span>Requesting Deletion...</span>
                        </motion.div>
                      ) : countdown !== null ? (
                        <motion.div key="countdown" initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 10 }} className="flex items-center gap-2">
                          <Trash2 size={18} className="animate-pulse" />
                          <span>Deleting in {countdown}...</span>
                        </motion.div>
                      ) : (
                        <motion.div key="idle" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex items-center gap-2">
                          <Trash2 size={18} />
                          <span>Initiate 14-Day Deletion</span>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
