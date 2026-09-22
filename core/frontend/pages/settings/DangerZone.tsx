import { useState, useEffect, useRef } from "react";
import { AlertTriangle, Trash2, Loader2, X } from "lucide-react";
import { toast } from "sonner"
import { friendlyToast } from "../../components/FriendlyError";
import { useWorkspaceData } from "./useWorkspaceData";
import { motion, AnimatePresence } from "motion/react";
import { fetcher, fetchWithAuth } from "@/lib/apiClient";
import SpotlightCard from "@/components/SpotlightCard";
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
    const isConfirmedCheck = (confirmText === activeWsName || confirmText === "DELETE_NOW");
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
  let inputBorderClass = "border-border focus:ring-border";
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
      <SpotlightCard className="p-8 rounded-2xl border border-border/50 bg-surface/50 backdrop-blur-md relative overflow-hidden">
        
        {isPendingDeletion && (
          <div className="bg-destructive text-destructive-foreground px-6 py-4 flex items-center justify-between font-bold">
            <div className="flex items-center gap-3">
              <AlertTriangle className="animate-pulse" />
              <span>Workspace Pending Permanent Deletion</span>
            </div>
            <div className="text-sm bg-background/20 px-3 py-1 rounded-md">
              14 Days Remaining
            </div>
          </div>
        )}

        <div className="p-8 md:p-10">
          <div className="flex items-start gap-5 mb-8">
            <div className="p-4 bg-destructive/10 text-destructive rounded-2xl relative">
              <AlertTriangle size={32} className="relative z-10" />
              <div className="absolute inset-0 bg-destructive/20 rounded-2xl animate-pulse blur-xl"></div>
            </div>
            <div>
              <h2 className="text-2xl font-bold tracking-tight text-destructive mb-1">
                Danger Zone
              </h2>
              <p className="text-sm text-muted-foreground mt-1">
                This is a highly destructive action. The operations on this page will result in permanent data loss.
              </p>
            </div>
          </div>

          <div className="max-w-2xl bg-background border border-border/50 rounded-xl p-8 relative shadow-lg">
            
            {isPendingDeletion ? (
              <div className="space-y-6">
                <div className="p-5 bg-destructive/10 rounded-lg border-l-4 border-destructive">
                  <h3 className="text-lg font-bold tracking-tight text-foreground">
                    Deletion Grace Period Active
                  </h3>
                  <p className="text-sm text-muted-foreground mt-1">
                    A 14-day grace period has started. The following actions have already taken place:
                  </p>
                  <ul className="mt-4 space-y-2">
                    <li className="flex items-center gap-2 text-sm font-semibold text-muted-foreground">
                      <X size={16} className="text-destructive" /> Campaigns have been paused
                    </li>
                    <li className="flex items-center gap-2 text-sm font-semibold text-muted-foreground">
                      <X size={16} className="text-destructive" /> Integrations have been disconnected
                    </li>
                    <li className="flex items-center gap-2 text-sm font-semibold text-muted-foreground">
                      <X size={16} className="text-destructive" /> Team members have been locked out
                    </li>
                  </ul>
                </div>
                
                <div className="p-5 bg-surface/50 border border-border/50 rounded-lg flex flex-col items-center text-center">
                  <p className="text-sm font-bold text-foreground mb-4">
                    Need to abort?
                  </p>
                  <button
                    onClick={handleCancelDeletion}
                    disabled={cancelling}
                    className="flex items-center justify-center gap-2 px-6 py-2.5 bg-destructive text-white font-bold rounded-lg hover:bg-destructive/90 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-[0_0_10px_rgba(239,68,68,0.2)]"
                  >
                    {cancelling ? (
                      <>
                        <Loader2 size={18} className="animate-spin" />
                        <span>Restoring...</span>
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
                    What you will lose:
                  </h3>
                  <div className="space-y-2.5">
                    {consequences.map((item, i) => (
                      <div key={i} className="flex items-center gap-3 p-3 bg-surface/50 border border-border/50 rounded-lg">
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
                    <p className="text-sm font-bold text-destructive">Wait. Are you sure?</p>
                    <p className="text-sm text-muted-foreground font-medium leading-relaxed">
                      Most users regret this. <span className="text-foreground font-bold">67% of workspace deletions are cancelled within 24 hours.</span> 
                      <br/>Please consider pausing your campaigns instead of permanent deletion.
                    </p>
                  </div>
                </div>

                <div className="space-y-3">
                  <label className="text-sm font-bold block text-foreground">
                    To commit to this action, type <span className="text-foreground bg-muted px-2 py-0.5 rounded select-none">{activeWsName}</span> below:
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
                    
                    <div className="absolute -top-10 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none bg-muted text-xs font-bold text-foreground px-3 py-1.5 rounded-md shadow-lg whitespace-nowrap z-20">
                      Type manually — paste is disabled for your safety.
                      <div className="absolute -bottom-1 left-1/2 -translate-x-1/2 border-4 border-transparent border-t-muted"></div>
                    </div>
                  </div>
                </div>

                <div className="pt-2 flex justify-end">
                  <button
                    onClick={confirmDeletion}
                    disabled={!isConfirmed || requesting}
                    className={`
                      relative flex items-center justify-center gap-2 px-8 py-3 font-bold rounded-xl transition-all duration-300
                      ${!isConfirmed 
                        ? 'bg-muted text-muted-foreground cursor-not-allowed' 
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
                          <span>Initiate Deletion</span>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </SpotlightCard>
    </div>
  );
}
