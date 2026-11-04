import { useState, useEffect, useRef } from "react";
import { AlertTriangle, Trash2, Loader2, X, Download, Database, ShieldCheck } from "lucide-react";
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
  const [exportingArchive, setExportingArchive] = useState(false);
  
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  const { data: workspaceData, error: fetchError, mutate: mutateData, isLoading } = useWorkspaceData(workspaceId);

  const activeWsName = workspaceData?.name || "";
  // Paranoia Layer 2: Fail-closed ownership check. Never treat missing/undefined role as owner.
  const isOwner = Boolean((workspaceData?.role && String(workspaceData.role).toLowerCase() === 'owner') || workspaceData?.is_owner);
  const isPendingDeletion = deletionRequested || workspaceData?.status === "pending_deletion";
  const isConfirmed = confirmText === activeWsName && activeWsName !== "";

  const handleDownloadArchive = async () => {
    if (!workspaceId || exportingArchive) return;
    setExportingArchive(true);
    try {
      const res = await fetchWithAuth(`/api/workspaces/${workspaceId}/export-archive`, {
        method: "POST",
      });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || "Failed to generate workspace archive");
      }
      const data = await res.json();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${activeWsName || "workspace"}-complete-archive-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      toast.success("Complete workspace archive exported successfully");
    } catch (e: any) {
      friendlyToast("Failed to download workspace backup archive", e);
    } finally {
      setExportingArchive(false);
    }
  };

  // 5-second countdown hold logic
  useEffect(() => {
    if (countdown === null) return;
    if (countdown > 0) {
      timerRef.current = setTimeout(() => {
        setCountdown(prev => (prev !== null ? prev - 1 : null));
      }, 1000);
      return () => {
        if (timerRef.current) clearTimeout(timerRef.current);
      };
    } else if (countdown === 0) {
      // Countdown expired, execute deletion
      executeDeletion();
    }
  }, [countdown]);

  const handleCancelCountdown = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setCountdown(null);
    toast.info("Deletion sequence aborted.");
  };

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

  const startDeletionSequence = () => {
    if (!isOwner) {
      toast.error("Only workspace owners can initiate workspace deletion.");
      return;
    }
    if (!isConfirmed || requesting) return;
    setCountdown(5);
  };

  const executeDeletion = async () => {
    if (!workspaceId || !isOwner || requesting) return;
    
    setRequesting(true);
    setCountdown(null);
    try {
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
      {/* Pre-Deletion Complete Workspace Archive Vault */}
      <div className="p-6 md:p-8 rounded-xl border border-border bg-card shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-border">
          <div className="flex items-center gap-3.5">
            <div className="p-2.5 bg-primary/10 text-primary rounded-xl">
              <Database size={22} />
            </div>
            <div>
              <h3 className="text-base font-bold text-foreground flex items-center gap-2">
                Pre-Deletion Archive Vault
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 border border-emerald-500/20">
                  Full Backup Available
                </span>
              </h3>
              <p className="text-xs text-muted-foreground mt-0.5">
                Download a complete, structured snapshot of workspace data before requesting permanent deletion.
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={handleDownloadArchive}
            disabled={exportingArchive}
            className="px-4 py-2 bg-primary text-primary-foreground font-semibold text-xs rounded-xl hover:bg-primary/90 transition-colors disabled:opacity-40 cursor-pointer flex items-center gap-2 shrink-0 shadow-xs"
          >
            {exportingArchive ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
            {exportingArchive ? "Generating Archive..." : "Download Full Archive (.json)"}
          </button>
        </div>

        <div className="p-4 rounded-xl bg-muted/20 border border-border flex items-start gap-3 text-xs text-muted-foreground">
          <ShieldCheck size={16} className="text-primary shrink-0 mt-0.5" />
          <p className="leading-relaxed">
            Archive includes all workspace configurations, legal postal address filings, deliverability reputation guardrails, team member permission registers, active suppression exclusions, and system audit logs.
          </p>
        </div>
      </div>

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

                {!isOwner ? (
                  <div className="p-4 bg-muted/30 border border-border rounded-xl flex items-center gap-3 text-xs text-muted-foreground">
                    <AlertTriangle size={16} className="text-amber-500 shrink-0" />
                    <span>Workspace deletion can only be initiated by the primary workspace owner. Your current role is <strong>{workspaceData?.role || 'member'}</strong>.</span>
                  </div>
                ) : (
                  <>
                    <div className="space-y-3">
                      <label className="text-sm font-bold block text-foreground">
                        To commit to this action, type <span className="text-foreground bg-muted border border-border px-2 py-0.5 rounded select-none font-mono">{activeWsName}</span> below:
                      </label>
                      
                      <div className="relative group">
                        <input
                          type="text"
                          value={confirmText}
                          onChange={(e) => setConfirmText(e.target.value)}
                          onPaste={(e) => {
                            e.preventDefault();
                            toast.error("For safety, please type the workspace name manually.");
                          }}
                          autoComplete="off"
                          autoCorrect="off"
                          spellCheck="false"
                          placeholder="Type the workspace name manually (copy-paste disabled)"
                          className={`w-full bg-background border-2 rounded-xl px-5 py-3 text-sm focus:outline-none transition-all font-bold placeholder:text-muted-foreground ${inputBorderClass}`}
                        />
                      </div>
                    </div>

                    <div className="pt-2 flex items-center justify-end gap-3">
                      {countdown !== null && (
                        <button
                          type="button"
                          onClick={handleCancelCountdown}
                          className="px-5 py-3 text-xs font-bold text-foreground bg-muted hover:bg-muted/80 rounded-xl transition-all cursor-pointer"
                        >
                          Cancel Countdown
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={startDeletionSequence}
                        disabled={!isConfirmed || requesting || countdown !== null}
                        className={`
                          relative flex items-center justify-center gap-2 px-8 py-3 font-bold rounded-xl transition-all duration-300 cursor-pointer text-xs
                          ${!isConfirmed 
                            ? 'bg-muted text-muted-foreground border border-border cursor-not-allowed opacity-60' 
                            : countdown !== null 
                              ? 'bg-destructive/80 text-destructive-foreground scale-95 shadow-[0_0_20px_rgba(239,68,68,0.5)] animate-pulse'
                              : 'bg-destructive text-destructive-foreground hover:bg-destructive/90 shadow-[0_0_10px_rgba(239,68,68,0.2)] hover:shadow-[0_0_20px_rgba(239,68,68,0.4)]'
                          }
                        `}
                      >
                        <AnimatePresence mode="wait">
                          {requesting ? (
                            <motion.div key="loading" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex items-center gap-2">
                              <Loader2 size={16} className="animate-spin" />
                              <span>Requesting Deletion...</span>
                            </motion.div>
                          ) : countdown !== null ? (
                            <motion.div key="countdown" initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 10 }} className="flex items-center gap-2">
                              <Trash2 size={16} className="animate-pulse" />
                              <span>Confirming in {countdown}s...</span>
                            </motion.div>
                          ) : (
                            <motion.div key="idle" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex items-center gap-2">
                              <Trash2 size={16} />
                              <span>Initiate 14-Day Deletion</span>
                            </motion.div>
                          )}
                        </AnimatePresence>
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
