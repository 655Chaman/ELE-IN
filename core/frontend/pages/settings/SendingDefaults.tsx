import { useState, useEffect, useRef } from "react";
import { Send, Info, Loader2, AlertCircle, AlertTriangle, ChevronDown, ChevronUp, CheckCircle2 } from "lucide-react";
import useSWR from "swr";
import { toast } from "sonner";
import { motion, AnimatePresence } from "motion/react";
import SpotlightCard from "@/components/SpotlightCard";
import { fetcher, fetchWithAuth } from "@/lib/apiClient";
import { SettingsLoadingSkeleton } from "@/components/SettingsLoadingSkeleton";
import { EmptyState } from "@/components/EmptyState";

export function SendingDefaults({ workspaceId }: { workspaceId: string | null }) {
  const { data, mutate, isLoading } = useSWR(
    workspaceId ? `/api/workspaces/${workspaceId}/sending-defaults` : null,
    fetcher
  );

  const [connLimit, setConnLimit] = useState(20);
  const [msgLimit, setMsgLimit] = useState(40);
  const [warmupDays, setWarmupDays] = useState(14);
  const [saving, setSaving] = useState(false);
  const [showChart, setShowChart] = useState(false);
  const [showSuccess, setShowSuccess] = useState(false);
  
  const successTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (successTimerRef.current) clearTimeout(successTimerRef.current);
    };
  }, []);

  useEffect(() => {
    if (data) {
      setConnLimit(data.daily_connection_limit ?? 20);
      setMsgLimit(data.daily_message_limit ?? 40);
      setWarmupDays(data.warmup_days ?? 14);
    }
  }, [data]);

  const hasChanges =
    data &&
    (connLimit !== (data.daily_connection_limit ?? 20) ||
      msgLimit !== (data.daily_message_limit ?? 40) ||
      warmupDays !== (data.warmup_days ?? 14));

  const handleSave = async () => {
    if (!workspaceId || saving || !hasChanges) return;
    setSaving(true);
    setShowSuccess(false);
    try {
      const res = await fetchWithAuth(`/api/workspaces/${workspaceId}/sending-defaults`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          daily_connection_limit: connLimit,
          daily_message_limit: msgLimit,
          warmup_days: warmupDays,
        }),
      });
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText || "Failed to update defaults");
      }
      toast.success("Sending defaults saved");
      mutate();
      if (successTimerRef.current) clearTimeout(successTimerRef.current);
      setShowSuccess(true);
      successTimerRef.current = setTimeout(() => setShowSuccess(false), 5000);
    } catch (e: any) {
      toast.error(e.message || "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  if (!workspaceId) {
    return <EmptyState title="No Workspace Selected" description="No workspace selected." icon={Send} />;
  }

  if (isLoading) {
    return <SettingsLoadingSkeleton />;
  }

  const maxActions = connLimit + msgLimit;
  const chartHeight = 160;
  const chartWidth = 600;

  const generateRampPath = () => {
    if (warmupDays === 0) return `M 0,0 L ${chartWidth},0`;

    let path = `M 0,${chartHeight - (chartHeight * 0.1)}`;

    // Iterate up to warmupDays, NOT 30!
    for (let i = 1; i <= Math.max(warmupDays, 1); i++) {
      const x = (i / warmupDays) * chartWidth;
      const progress = Math.min(1, i / warmupDays); // this will always be i/warmupDays up to 1
      const y = chartHeight - (chartHeight * (0.1 + (0.9 * progress)));
      path += ` L ${x},${y}`;
    }
    return path;
  };

  const handleNumInput = (val: string, setter: (n: number) => void, max: number) => {
    if (val === "") { setter(1); return; } // Default to 1, not 0
    const num = parseInt(val, 10);
    if (isNaN(num)) return;
    // Enforce a minimum of 1 and a maximum of max
    setter(Math.max(1, Math.min(num, max)));
  };

  return (
    <div className="space-y-6 max-w-4xl">
      <SpotlightCard className="p-8 rounded-2xl border border-border/50 bg-surface/50 backdrop-blur-md relative overflow-hidden">
        <div className="absolute top-0 left-0 w-1 h-full bg-primary/40"></div>
        
        <div className="flex items-center gap-4 mb-6">
          <div className="p-3 bg-primary/10 rounded-xl">
            <Send className="text-primary" size={24} />
          </div>
          <div>
            <h2 className="text-2xl font-bold tracking-tight text-foreground">Sending Safety Defaults</h2>
            <p className="text-sm text-muted-foreground mt-1">Configure the baseline limits for newly connected accounts.</p>
          </div>
        </div>

        <div className="mb-8 p-4 bg-primary/10 border border-primary/20 rounded-xl flex gap-3">
          <Info className="text-primary shrink-0 mt-0.5" size={20} />
          <div className="text-sm text-primary dark:text-primary font-medium leading-relaxed">
            These settings act as the template for <strong>newly added accounts</strong>. Changing these values will NOT retroactively alter accounts that are already connected.
          </div>
        </div>

        <div className="space-y-6">
          {/* Daily Limits Card */}
          <div className="border border-border/50 bg-background/50 rounded-xl p-6">
            <div className="mb-6">
              <h3 className="text-lg font-bold tracking-tight text-foreground">Daily Limits</h3>
              <p className="text-sm text-muted-foreground mt-1">Set the maximum daily actions for accounts.</p>
            </div>
            <div className="space-y-8">
              {/* Connection Limit */}
              <div>
                <div className="flex justify-between items-center mb-4">
                  <div>
                    <label className="text-base font-semibold text-foreground">Daily Connection Limit</label>
                    <p className="text-xs text-muted-foreground">Number of connection requests sent per day</p>
                  </div>
                  <input 
                    type="number" 
                    value={connLimit} 
                    onChange={(e) => handleNumInput(e.target.value, setConnLimit, 100)}
                    className="w-20 px-3 py-1.5 bg-background border border-border rounded-lg text-right font-mono text-lg font-bold text-foreground focus:ring-2 ring-primary outline-none"
                  />
                </div>
                
                <div className="relative pt-6 pb-2">
                  <div className="absolute top-0 left-[20%] -ml-px w-px h-full bg-foreground/20 z-0"></div>
                  <div className="absolute top-0 left-[20%] -ml-6 text-[10px] text-muted-foreground font-medium">Safe Limit</div>
                  
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={connLimit}
                    onChange={(e) => setConnLimit(parseInt(e.target.value))}
                    className="w-full appearance-none bg-border h-2 rounded-full outline-none z-10 relative slider-thumb-green cursor-pointer"
                    style={{
                      background: `linear-gradient(to right, 
                        ${connLimit <= 20 ? '#22c55e' : connLimit <= 30 ? '#eab308' : '#ef4444'} ${connLimit}%, 
                        transparent ${connLimit}%)`
                    }}
                  />
                </div>
                <AnimatePresence>
                  {connLimit > 20 && (
                    <motion.div 
                      initial={{ opacity: 0, height: 0 }} 
                      animate={{ opacity: 1, height: 'auto' }} 
                      exit={{ opacity: 0, height: 0 }}
                      className="mt-3 flex items-center gap-2 text-sm text-warning dark:text-warning"
                    >
                      <AlertTriangle size={16} />
                      <span>{connLimit > 30 ? 'High risk! Approaching dangerous limits for new accounts.' : 'Caution: Above LinkedIn recommended safe limit (20/day).'}</span>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              {/* Message Limit */}
              <div>
                <div className="flex justify-between items-center mb-4">
                  <div>
                    <label className="text-base font-semibold text-foreground">Daily Message Limit</label>
                    <p className="text-xs text-muted-foreground">Number of follow-up/InMail messages per day</p>
                  </div>
                  <input 
                    type="number" 
                    value={msgLimit} 
                    onChange={(e) => handleNumInput(e.target.value, setMsgLimit, 150)}
                    className="w-20 px-3 py-1.5 bg-background border border-border rounded-lg text-right font-mono text-lg font-bold text-foreground focus:ring-2 ring-primary outline-none"
                  />
                </div>
                
                <div className="relative pt-6 pb-2">
                  <div className="absolute top-0 left-[33.3%] -ml-px w-px h-full bg-foreground/20 z-0"></div>
                  <div className="absolute top-0 left-[33.3%] -ml-6 text-[10px] text-muted-foreground font-medium">Safe Limit</div>
                  
                  <input
                    type="range"
                    min="0"
                    max="150"
                    value={msgLimit}
                    onChange={(e) => setMsgLimit(parseInt(e.target.value))}
                    className="w-full appearance-none bg-border h-2 rounded-full outline-none z-10 relative slider-thumb-blue cursor-pointer"
                    style={{
                      background: `linear-gradient(to right, 
                        ${msgLimit <= 50 ? '#3b82f6' : msgLimit <= 80 ? '#eab308' : '#ef4444'} ${(msgLimit/150)*100}%, 
                        transparent ${(msgLimit/150)*100}%)`
                    }}
                  />
                </div>
                <AnimatePresence>
                  {msgLimit > 50 && (
                    <motion.div 
                      initial={{ opacity: 0, height: 0 }} 
                      animate={{ opacity: 1, height: 'auto' }} 
                      exit={{ opacity: 0, height: 0 }}
                      className="mt-3 flex items-center gap-2 text-sm text-warning dark:text-warning"
                    >
                      <AlertTriangle size={16} />
                      <span>{msgLimit > 80 ? 'High risk! Messaging at this volume may trigger spam filters.' : 'Caution: Above typical safe limit (50/day).'}</span>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              {/* Conflict Warning */}
              <AnimatePresence>
                {connLimit > msgLimit && (
                  <motion.div 
                    initial={{ opacity: 0, height: 0 }} 
                    animate={{ opacity: 1, height: 'auto' }} 
                    exit={{ opacity: 0, height: 0 }}
                    className="p-3 bg-destructive/10 border border-destructive/20 rounded-lg flex items-start gap-2 text-sm text-destructive dark:text-destructive"
                  >
                    <AlertTriangle size={16} className="mt-0.5 shrink-0" />
                    <span>Warning: Your connection limit ({connLimit}) is higher than your message limit ({msgLimit}). This is an unusual configuration that may lead to imbalanced outreach.</span>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>

          {/* Warmup Configuration Card */}
          <div className="border border-border/50 bg-background/50 rounded-xl p-6">
            <div className="mb-6">
              <h3 className="text-lg font-bold tracking-tight text-foreground">Warmup Configuration</h3>
              <p className="text-sm text-muted-foreground mt-1">Control how quickly accounts ramp up to full limits.</p>
            </div>
            
            <div>
              {/* Warmup Days */}
              <div className="mb-6">
                <div className="flex justify-between items-center mb-4">
                  <div>
                    <label className="text-base font-semibold text-foreground">Warmup Duration</label>
                    <p className="text-xs text-muted-foreground">Days to gradually reach full daily limits</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <input 
                      type="number" 
                      value={warmupDays} 
                      onChange={(e) => handleNumInput(e.target.value, setWarmupDays, 30)}
                      className="w-20 px-3 py-1.5 bg-background border border-border rounded-lg text-right font-mono text-lg font-bold text-foreground focus:ring-2 ring-primary outline-none"
                    />
                    <span className="text-sm font-medium text-muted-foreground">days</span>
                  </div>
                </div>
                
                <div className="relative pt-6 pb-2">
                  <input
                    type="range"
                    min="0"
                    max="30"
                    value={warmupDays}
                    onChange={(e) => setWarmupDays(parseInt(e.target.value))}
                    className="w-full appearance-none bg-border h-2 rounded-full outline-none z-10 relative cursor-pointer"
                    style={{
                      background: `linear-gradient(to right, 
                        #a855f7 ${(warmupDays/30)*100}%, 
                        transparent ${(warmupDays/30)*100}%)`
                    }}
                  />
                  <div className="flex justify-between mt-2 text-[10px] text-muted-foreground font-medium px-1">
                    <span>0</span>
                    <span>7</span>
                    <span>14</span>
                    <span>21</span>
                    <span>30</span>
                  </div>
                </div>
              </div>

              {/* Advanced Chart */}
              <div className="border border-border rounded-lg overflow-hidden bg-muted/5">
                <button 
                  onClick={() => setShowChart(!showChart)}
                  className="w-full px-4 py-3 flex items-center justify-between hover:bg-muted/10 transition-colors"
                >
                  <span className="font-semibold text-sm">30-Day Warmup Projection</span>
                  {showChart ? <ChevronUp size={18} className="text-muted-foreground" /> : <ChevronDown size={18} className="text-muted-foreground" />}
                </button>
                
                <AnimatePresence>
                  {showChart && (
                    <motion.div 
                      initial={{ height: 0 }}
                      animate={{ height: 'auto' }}
                      exit={{ height: 0 }}
                      className="overflow-hidden"
                    >
                      <div className="p-4 pt-2">
                        <p className="text-xs text-muted-foreground mb-4">
                          Accounts start at ~10% of their limits on Day 1 and linearly scale to 100% by Day {warmupDays || 1}.
                        </p>
                        <div className="relative w-full overflow-x-auto pb-4">
                          <div className="min-w-[500px]">
                            <svg viewBox={`0 0 ${chartWidth} ${chartHeight + 20}`} width="100%" height={chartHeight + 20} className="overflow-visible">
                              <defs>
                                <linearGradient id="chartGradient" x1="0" y1="0" x2="0" y2="1">
                                  <stop offset="0%" stopColor="var(--color-primary, #6366f1)" stopOpacity="0.4" />
                                  <stop offset="100%" stopColor="var(--color-primary, #6366f1)" stopOpacity="0.0" />
                                </linearGradient>
                              </defs>
                              
                              <line x1="0" y1="0" x2={chartWidth} y2="0" stroke="currentColor" strokeOpacity="0.1" strokeDasharray="4 4" />
                              <line x1="0" y1={chartHeight/2} x2={chartWidth} y2={chartHeight/2} stroke="currentColor" strokeOpacity="0.1" strokeDasharray="4 4" />
                              <line x1="0" y1={chartHeight} x2={chartWidth} y2={chartHeight} stroke="currentColor" strokeOpacity="0.3" />
                              
                              <motion.path
                                initial={{ pathLength: 0, opacity: 0 }}
                                animate={{ pathLength: 1, opacity: 1 }}
                                transition={{ duration: 1, ease: "easeInOut" }}
                                d={`${generateRampPath()} L ${chartWidth} ${chartHeight} L 0 ${chartHeight} Z`}
                                fill="url(#chartGradient)"
                                className="transition-all duration-300"
                              />
                              
                              <motion.path
                                initial={{ pathLength: 0 }}
                                animate={{ pathLength: 1 }}
                                transition={{ duration: 1, ease: "easeInOut" }}
                                d={generateRampPath()}
                                fill="none"
                                stroke="var(--color-primary, #6366f1)"
                                strokeWidth="3"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                className="transition-all duration-300"
                              />
                              
                              <circle cx="0" cy={chartHeight - (chartHeight * 0.1)} r="4" fill="var(--color-primary, #6366f1)" />
                              {warmupDays > 0 && (
                                <circle cx={(Math.min(warmupDays, 30)/30)*chartWidth} cy={warmupDays === 0 ? chartHeight : 0} r="4" fill="var(--color-primary, #6366f1)" />
                              )}
                              
                              <text x="0" y={chartHeight + 16} fontSize="10" fill="currentColor" opacity="0.6">Day 1</text>
                              <text x={chartWidth/2} y={chartHeight + 16} fontSize="10" fill="currentColor" opacity="0.6" textAnchor="middle">Day 15</text>
                              <text x={chartWidth} y={chartHeight + 16} fontSize="10" fill="currentColor" opacity="0.6" textAnchor="end">Day 30</text>
                              
                              <text x={-10} y="4" fontSize="10" fill="currentColor" opacity="0.6" textAnchor="end">{maxActions} acts</text>
                              <text x={-10} y={chartHeight} fontSize="10" fill="currentColor" opacity="0.6" textAnchor="end">0</text>
                            </svg>
                          </div>
                        </div>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </div>
          </div>
          
          <AnimatePresence>
            {showSuccess && (
              <motion.div 
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className="bg-success/10 border border-success/20 text-success dark:text-success p-4 rounded-xl flex items-start gap-3"
              >
                <CheckCircle2 className="shrink-0 mt-0.5" size={20} />
                <div>
                  <p className="font-semibold text-sm">Defaults successfully updated!</p>
                  <p className="text-xs mt-1 opacity-90">
                    Your next connected account will start at safely scaled volumes, reaching {connLimit} connections and {msgLimit} messages per day over {warmupDays} days.
                  </p>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          <div className="pt-4 flex justify-end">
            <button
              onClick={handleSave}
              disabled={!hasChanges || saving}
              className="flex items-center gap-2 px-8 py-3 bg-primary text-primary-foreground font-semibold rounded-xl hover:bg-primary/90 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-md shadow-primary/20"
            >
              {saving ? <Loader2 size={18} className="animate-spin" /> : <Send size={18} />}
              {saving ? "Saving..." : "Save Defaults"}
            </button>
          </div>
        </div>
      </SpotlightCard>
    </div>
  );
}

