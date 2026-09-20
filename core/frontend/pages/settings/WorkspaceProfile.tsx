import useSWR from "swr";

import { useState, useEffect } from "react";
import { Info, Loader2, Save, Check, Clock, Hash, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { useWorkspaceData } from "./useWorkspaceData";
import { motion, AnimatePresence } from "motion/react";
import { format } from "date-fns";
import SpotlightCard from "@/components/SpotlightCard";
import { fetcher, fetchWithAuth } from "@/lib/apiClient";
import { useWorkspace } from "../../contexts/WorkspaceContext";
import { SettingsLoadingSkeleton } from "@/components/SettingsLoadingSkeleton";
import { EmptyState } from "@/components/EmptyState";

const getGradient = (name: string) => {
  if (!name) return "from-muted to-muted-foreground";
  const hash = Array.from(name).reduce((acc, char) => acc + char.charCodeAt(0), 0);
  const gradients = [
    "from-blue-500 to-indigo-500",
    "from-purple-500 to-fuchsia-500",
    "from-primary/80 to-primary",
    "from-emerald-400 to-teal-500",
    "from-rose-400 to-red-500",
  ];
  return gradients[hash % gradients.length];
};

const getInitials = (name: string) => {
  if (!name) return "??";
  const parts = name.trim().split(" ").filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
};

export function WorkspaceProfile({ workspaceId }: { workspaceId: string | null }) {
  const { refreshWorkspaces } = useWorkspace();
  const { data, mutate, isLoading, error } = useWorkspaceData(workspaceId);
  
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [savedSuccess, setSavedSuccess] = useState(false);
  const [lastSaved, setLastSaved] = useState<Date | null>(null);

  const serverName = data?.name || "";
  const hasChanges = data?.name !== undefined && name !== data.name;
  const isTooLong = name.length > 50;
  const isEmpty = name.trim().length === 0;

  useEffect(() => {
    if (data?.name && !saving) {
      setName(data.name);
    }
  }, [data?.name, saving]);

  const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setName(e.target.value);
  };

  const handleSave = async () => {
    if (!workspaceId || saving) return;
    if (isEmpty) {
      toast.error("Workspace name cannot be empty");
      return;
    }
    if (isTooLong) {
      toast.error("Workspace name is too long");
      return;
    }
    setSaving(true);
    setSavedSuccess(false);
    try {
      const res = await fetchWithAuth(`/api/workspaces/${workspaceId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim() }),
      });
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText || "Failed to update profile");
      }
      mutate({ ...data, name: name.trim() }, false);
      setSavedSuccess(true);
      setLastSaved(new Date());
      await refreshWorkspaces();
      setTimeout(() => setSavedSuccess(false), 2000);
    } catch (e: any) {
      toast.error(e.message || "Failed to save workspace profile — try again");
    } finally {
      setSaving(false);
    }
  };

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center p-6 border border-destructive/20 bg-destructive/5 rounded-lg text-destructive">
        <AlertTriangle className="h-8 w-8 mb-2" />
        <h3 className="font-semibold">Failed to load workspace data</h3>
        <p className="text-sm opacity-80">Please check your connection and try again.</p>
      </div>
    );
  }

  if (!workspaceId) {
    return <EmptyState title="No Workspace Selected" description="No workspace selected." icon={Info} />;
  }

  if (isLoading && !data) {
    return <SettingsLoadingSkeleton />;
  }

  const charCountRatio = name.length / 50;
  let progressColor = "bg-primary";
  if (charCountRatio > 0.84) progressColor = "bg-primary";
  if (charCountRatio >= 1.0) progressColor = "bg-destructive";

  return (
    <div className="space-y-6">
      <motion.div
        animate={{
          borderColor: savedSuccess ? "var(--color-emerald-500, #10b981)" : "var(--color-border, #262626)",
          boxShadow: savedSuccess ? "0 0 15px -3px rgba(16, 185, 129, 0.3)" : "0 0 0px 0px rgba(0,0,0,0)",
        }}
        transition={{ duration: 0.5, ease: "easeOut" }}
        className="rounded-2xl"
      >
        <SpotlightCard className="p-8 rounded-2xl border border-border/50 bg-surface/50 backdrop-blur-md relative overflow-hidden">
          <div className="absolute top-0 left-0 w-1.5 h-full bg-gradient-to-b from-primary/60 to-primary/10"></div>
          
          <div className="flex flex-col md:flex-row items-start md:items-center gap-6 mb-8">
            <div className={`w-24 h-24 rounded-full shadow-lg flex items-center justify-center text-3xl font-bold text-white bg-gradient-to-br ${getGradient(name || serverName)} transition-all duration-500`}>
              {getInitials(name || serverName)}
            </div>
            <div className="flex-1 space-y-2">
              <h2 className="text-2xl font-bold tracking-tight text-foreground">Workspace Identity</h2>
              <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
                <span className="flex items-center gap-1.5 bg-muted/30 px-2.5 py-1 rounded-md border border-border/50">
                  <Hash size={14} className="opacity-70" />
                  <span className="font-mono">{workspaceId.slice(0, 8)}</span>
                </span>
                {data?.created_at && (
                  <span className="flex items-center gap-1.5">
                    <Clock size={14} className="opacity-70" />
                    Member since {format(new Date(data.created_at), "MMMM yyyy")}
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="space-y-8 max-w-2xl">
            <AnimatePresence>
              {hasChanges && (
                <motion.div
                  initial={{ opacity: 0, y: -20, height: 0 }}
                  animate={{ opacity: 1, y: 0, height: 'auto' }}
                  exit={{ opacity: 0, y: -20, height: 0 }}
                  className="bg-primary/10 border border-primary/20 rounded-lg p-4 flex items-center justify-between overflow-hidden"
                >
                  <div className="flex items-center gap-3 text-primary">
                    <AlertTriangle size={18} />
                    <span className="text-sm font-medium">You have unsaved changes</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setName(serverName)}
                      className="px-3 py-1.5 text-xs font-semibold hover:bg-primary/20 text-primary rounded-md transition-colors"
                      disabled={saving}
                    >
                      Discard
                    </button>
                    <button
                      onClick={handleSave}
                      className="px-3 py-1.5 text-xs font-semibold bg-primary text-white rounded-md hover:bg-amber-600 transition-colors shadow-sm"
                      disabled={saving || isEmpty || isTooLong}
                    >
                      Save
                    </button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            <div className="space-y-3 relative group">
              <label className="text-sm font-semibold flex justify-between text-foreground/90">
                Workspace Name
              </label>
              
              <div className="relative">
                <input
                  type="text"
                  value={name}
                  onChange={handleNameChange}
                  className={`w-full bg-background border rounded-lg px-4 py-3 text-base focus:outline-none focus:ring-2 transition-all font-medium shadow-sm ${
                    isEmpty ? 'border-destructive/50 focus:ring-destructive/50' : 
                    isTooLong ? 'border-destructive focus:ring-destructive' : 
                    'border-border/80 focus:border-primary/50 focus:ring-primary/20'
                  }`}
                  placeholder="e.g. Acme Corp"
                />
                
                {/* Progress bar for char count (Zeigarnik) */}
                <div className="absolute bottom-0 left-0 w-full h-1 bg-muted/50 rounded-b-lg overflow-hidden">
                  <div 
                    className={`h-full transition-all duration-300 ease-out ${progressColor}`} 
                    style={{ width: `${Math.min(100, (name.length / 50) * 100)}%` }}
                  />
                </div>
              </div>
              
              <AnimatePresence>
                {isEmpty && (
                  <motion.p 
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className="text-destructive text-sm"
                  >
                    Name cannot be empty.
                  </motion.p>
                )}
              </AnimatePresence>
            </div>

            <div className="flex items-start gap-4 p-5 bg-surface border border-primary/20 rounded-xl shadow-sm">
              <div className="p-2 bg-primary/10 rounded-full shrink-0">
                <Info size={20} className="text-primary" />
              </div>
              <div className="space-y-1 text-sm text-foreground/80 leading-relaxed">
                <p><strong className="text-foreground">Billing Impact:</strong> Changing your workspace name will update all future billing invoices, receipts, and client-facing reports immediately.</p>
              </div>
            </div>

            <div className="pt-4 flex flex-col sm:flex-row items-center justify-between gap-4 border-t border-border/50">
              <div className="text-xs text-muted-foreground">
                {lastSaved ? (
                  <span className="flex items-center gap-1">
                    <Check size={14} className="text-emerald-500" /> Last saved {format(lastSaved, "HH:mm")}
                  </span>
                ) : (
                  <span>Data synced with server</span>
                )}
              </div>
              
              <div className="w-full sm:w-auto relative group">
                <button
                  onClick={handleSave}
                  disabled={!hasChanges || saving || isEmpty || isTooLong}
                  className="w-full sm:w-auto relative overflow-hidden flex items-center justify-center gap-2 px-8 py-3 bg-primary text-primary-foreground font-semibold rounded-lg hover:bg-primary/90 transition-all disabled:opacity-50 disabled:bg-muted disabled:text-muted-foreground disabled:cursor-not-allowed shadow-md"
                >
                  <AnimatePresence mode="popLayout" initial={false}>
                    {saving ? (
                      <motion.div
                        key="saving"
                        initial={{ opacity: 0, scale: 0.8 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0, scale: 0.8 }}
                        className="flex items-center gap-2"
                      >
                        <Loader2 size={18} className="animate-spin" /> Saving...
                      </motion.div>
                    ) : savedSuccess ? (
                      <motion.div
                        key="saved"
                        initial={{ opacity: 0, scale: 0.8 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0, scale: 0.8 }}
                        className="flex items-center gap-2"
                      >
                        <Check size={18} /> Saved!
                      </motion.div>
                    ) : (
                      <motion.div
                        key="idle"
                        initial={{ opacity: 0, scale: 0.8 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0, scale: 0.8 }}
                        className="flex items-center gap-2"
                      >
                        <Save size={18} /> Save Changes
                      </motion.div>
                    )}
                  </AnimatePresence>
                </button>
                
                {/* Tooltip for disabled state */}
                {!hasChanges && !saving && (
                  <div className="absolute -top-10 left-1/2 -translate-x-1/2 px-3 py-1.5 bg-popover text-popover-foreground text-xs rounded-md opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap border border-border shadow-md">
                    No changes to save
                  </div>
                )}
              </div>
            </div>
          </div>
        </SpotlightCard>
      </motion.div>
    </div>
  );
}
