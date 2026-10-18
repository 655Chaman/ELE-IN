import React, { useState, useEffect } from 'react';
import useSWR from 'swr';
import { 
  Layers, ArrowRight, CheckCircle2, ShieldCheck, 
  RefreshCw, Zap, Lock, X, Compass, Copy, Check, ChevronDown, ChevronUp, RotateCcw
} from 'lucide-react';
import { toast } from 'sonner';
import { motion, AnimatePresence } from 'motion/react';
import { fetchWithAuth } from '@/lib/apiClient';
import { usePaywall } from '@/contexts/PaywallContext';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

const fetcher = (url: string) => fetchWithAuth(url).then(r => r.json());

interface OmnichannelRetargetingStudioProps {
  onClose?: () => void;
  initialLeadId?: string;
  initialEmail?: string;
  initialLinkedinUrl?: string;
}

export function OmnichannelRetargetingStudioModal({
  onClose,
  initialLeadId,
  initialEmail,
  initialLinkedinUrl
}: OmnichannelRetargetingStudioProps) {
  const { openPaywall } = usePaywall();
  const { data: billingData } = useSWR<{ tier?: string }>('/api/elein/workspaces/billing', fetcher);
  const isPro = billingData?.tier === 'PRO' || billingData?.tier === 'ENTERPRISE';

  // Simulation Form State
  const [leadId, setLeadId] = useState<string>(initialLeadId || "");
  const [email, setEmail] = useState<string>(initialEmail || "alex.vance@techscale.io");
  const [linkedinUrl, setLinkedinUrl] = useState<string>(initialLinkedinUrl || "https://linkedin.com/in/alex-vance");
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [inmailEligible, setInmailEligible] = useState<boolean>(true);
  const [cascadePriority, setCascadePriority] = useState<string>("linkedin,email,inmail");

  // Evaluation Execution State
  const [isSimulating, setIsSimulating] = useState<boolean>(false);
  const [simulationResult, setSimulationResult] = useState<any>(null);
  const [showVariablesInspector, setShowVariablesInspector] = useState<boolean>(false);
  const [copiedResult, setCopiedResult] = useState<boolean>(false);

  // Escape key dismiss listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && onClose) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const handleResetDefaults = () => {
    setLeadId(initialLeadId || "");
    setEmail(initialEmail || "alex.vance@techscale.io");
    setLinkedinUrl(initialLinkedinUrl || "https://linkedin.com/in/alex-vance");
    setIsConnected(false);
    setInmailEligible(true);
    setCascadePriority("linkedin,email,inmail");
    setSimulationResult(null);
    toast.info("Reset simulator inputs to default test prospect.");
  };

  const handleCopyJson = () => {
    if (!simulationResult) return;
    navigator.clipboard.writeText(JSON.stringify(simulationResult, null, 2));
    setCopiedResult(true);
    toast.success("Copied evaluation result JSON to clipboard!");
    setTimeout(() => setCopiedResult(false), 2000);
  };

  const handleSimulateRoute = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();

    if (!isPro) {
      openPaywall({
        featureName: "Omnichannel Retargeting Cascade",
        minTier: "PRO",
        description: "Simulate and execute automated 4-tier channel handoffs across LinkedIn DMs, Verified Email, and Open InMail."
      });
      return;
    }

    if (!email.trim() && !linkedinUrl.trim()) {
      toast.error("Please provide at least a Corporate Email or a LinkedIn Profile URL.");
      return;
    }

    setIsSimulating(true);
    try {
      const payload: any = {
        email: email.trim(),
        linkedin_url: linkedinUrl.trim(),
        is_connected: isConnected,
        inmail_eligible: inmailEligible,
        cascade_order: cascadePriority.split(",").map(s => s.trim().toLowerCase())
      };
      if (leadId.trim()) {
        payload.lead_id = leadId.trim();
      }

      const res = await fetchWithAuth('/api/elein/campaigns/evaluate-omnichannel-route', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail?.message || err.detail || 'Evaluation failed');
      }

      const data = await res.json();
      setSimulationResult(data);
      toast.success(`Route Evaluated: Selected channel is ${(data.routed_channel || '').toUpperCase()}`);
    } catch (err: any) {
      toast.error(err.message || "Failed to simulate omnichannel route.");
    } finally {
      setIsSimulating(false);
    }
  };

  // Decoupled evaluation highlights
  const isTier1Active = simulationResult && (
    simulationResult.branch?.toLowerCase().includes("1st-degree") || 
    (simulationResult.routed_channel === 'linkedin' && simulationResult.variables?.omnichannel_is_connected === true)
  );
  const isTier2Active = simulationResult && simulationResult.routed_channel === 'email';
  const isTier3Active = simulationResult && simulationResult.routed_channel === 'inmail';
  const isTier4Active = simulationResult && (
    simulationResult.branch?.toLowerCase().includes("fallback") ||
    (simulationResult.routed_channel === 'linkedin' && simulationResult.variables?.omnichannel_is_connected === false)
  );

  return (
    <div 
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-background/80 backdrop-blur-sm overflow-hidden animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div 
        role="dialog"
        aria-modal="true"
        aria-labelledby="omnichannel-studio-title"
        onClick={(e) => e.stopPropagation()}
        className="relative w-full max-w-4xl h-[90dvh] max-h-[90dvh] bg-card border border-border rounded-xl shadow-2xl overflow-hidden flex flex-col text-foreground"
      >
        {/* Header */}
        <div className="px-5 sm:px-6 py-4 border-b border-border bg-card/60 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center text-primary">
              <Layers size={18} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 id="omnichannel-studio-title" className="text-base font-bold text-foreground">
                  Omnichannel Retargeting &amp; Step Forking Studio
                </h2>
                {isPro ? (
                  <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase tracking-wider bg-primary/10 text-primary border border-primary/20">
                    Pro Enabled
                  </span>
                ) : (
                  <button 
                    type="button"
                    onClick={() => openPaywall({ featureName: "Omnichannel Retargeting Studio", minTier: "PRO" })}
                    className="text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase tracking-wider bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20 flex items-center gap-1 hover:bg-amber-500/20 transition-colors cursor-pointer"
                  >
                    <Lock size={10} /> Pro Required
                  </button>
                )}
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Simulate 4-tier omnichannel dispatch cascades, suppression defense, and dynamic sequence branching across LinkedIn, Email, and InMail.
              </p>
            </div>
          </div>

          {onClose && (
            <button 
              type="button"
              onClick={onClose}
              aria-label="Close studio"
              className="w-8 h-8 rounded-lg border border-border hover:bg-muted text-muted-foreground hover:text-foreground flex items-center justify-center transition-colors cursor-pointer"
            >
              <X size={16} />
            </button>
          )}
        </div>

        {/* Free Tier In-Situ Paywall Banner */}
        {!isPro && (
          <div className="px-5 sm:px-6 py-3 bg-amber-500/10 border-b border-amber-500/20 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs shrink-0">
            <div className="flex items-center gap-3">
              <div className="w-7 h-7 rounded-lg bg-amber-500/20 border border-amber-500/30 flex items-center justify-center text-amber-500 shrink-0">
                <Lock size={14} />
              </div>
              <div>
                <span className="font-semibold text-foreground block">
                  Unlock 4-Tier Omnichannel Routing with Growth Pro
                </span>
                <span className="text-[11px] text-muted-foreground">
                  Upgrade to automate multi-channel fallback across LinkedIn DMs, verified cold email, and paid InMails to triple meeting conversion rates.
                </span>
              </div>
            </div>
            <button
              type="button"
              onClick={() => openPaywall({ featureName: "Omnichannel Retargeting Cascade", minTier: "PRO" })}
              className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 font-semibold text-xs transition-colors shrink-0 self-start sm:self-auto cursor-pointer"
            >
              <Zap size={13} />
              <span>Unlock Omnichannel</span>
              <ArrowRight size={13} />
            </button>
          </div>
        )}

        {/* Body */}
        <div className="p-5 sm:p-6 overflow-y-auto flex-1 space-y-6">
          {/* Architecture Cascade Visualizer */}
          <div className="p-4 bg-muted/20 border border-border rounded-xl space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-foreground flex items-center gap-2">
                <Compass size={14} className="text-primary" />
                <span>4-Tier Waterfall Dispatch Cascade</span>
              </span>
              <span className="text-[11px] text-muted-foreground">
                Automatic Failover Algorithm
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2.5 text-xs">
              <div className={`p-3 rounded-lg border transition-all ${
                isTier1Active
                  ? 'bg-primary/10 border-primary text-foreground font-semibold shadow-sm'
                  : 'bg-card border-border text-muted-foreground'
              }`}>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono uppercase tracking-wider">Tier 1</span>
                  {isTier1Active && (
                    <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
                  )}
                </div>
                <p className="font-semibold text-foreground mt-1">1st-Degree LinkedIn</p>
                <p className="text-[10px] text-muted-foreground mt-0.5">Direct Message / Voice Note</p>
              </div>

              <div className={`p-3 rounded-lg border transition-all ${
                isTier2Active
                  ? 'bg-primary/10 border-primary text-foreground font-semibold shadow-sm'
                  : 'bg-card border-border text-muted-foreground'
              }`}>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono uppercase tracking-wider">Tier 2</span>
                  {isTier2Active && (
                    <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
                  )}
                </div>
                <p className="font-semibold text-foreground mt-1">Verified Cold Email</p>
                <p className="text-[10px] text-muted-foreground mt-0.5">SendGrid / Smartlead Bridge</p>
              </div>

              <div className={`p-3 rounded-lg border transition-all ${
                isTier3Active
                  ? 'bg-primary/10 border-primary text-foreground font-semibold shadow-sm'
                  : 'bg-card border-border text-muted-foreground'
              }`}>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono uppercase tracking-wider">Tier 3</span>
                  {isTier3Active && (
                    <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
                  )}
                </div>
                <p className="font-semibold text-foreground mt-1">InMail / Open Profile</p>
                <p className="text-[10px] text-muted-foreground mt-0.5">Sales Nav / Sponsored InMail</p>
              </div>

              <div className={`p-3 rounded-lg border transition-all ${
                isTier4Active
                  ? 'bg-primary/10 border-primary text-foreground font-semibold shadow-sm'
                  : 'bg-card border-border text-muted-foreground'
              }`}>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono uppercase tracking-wider">Tier 4</span>
                  {isTier4Active && (
                    <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
                  )}
                </div>
                <p className="font-semibold text-foreground mt-1">Social Touch Fallback</p>
                <p className="text-[10px] text-muted-foreground mt-0.5">Connection Request / View</p>
              </div>
            </div>
          </div>

          {/* Interactive Simulator Deck */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Input Attributes Form */}
            <form onSubmit={handleSimulateRoute} className="p-5 rounded-xl bg-card border border-border space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-foreground block">
                    Prospect Attribute Inputs
                  </span>
                  <span className="px-1.5 py-0.2 rounded text-[9px] font-mono font-medium bg-muted text-muted-foreground border border-border">
                    Simulated Sandbox
                  </span>
                </div>
                <button
                  type="button"
                  onClick={handleResetDefaults}
                  className="text-[11px] text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors"
                  title="Reset to default test values"
                >
                  <RotateCcw size={11} />
                  <span>Reset</span>
                </button>
              </div>

              <div className="space-y-3 text-xs">
                <div>
                  <label htmlFor="omni-email" className="text-muted-foreground font-medium block mb-1">
                    Corporate Email:
                  </label>
                  <input
                    id="omni-email"
                    type="email"
                    disabled={isSimulating}
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="prospect@company.com"
                    className="w-full bg-background border border-border rounded-lg px-3 py-2 text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all disabled:opacity-50"
                  />
                </div>

                <div>
                  <label htmlFor="omni-linkedin" className="text-muted-foreground font-medium block mb-1">
                    LinkedIn Profile URL:
                  </label>
                  <input
                    id="omni-linkedin"
                    type="url"
                    disabled={isSimulating}
                    value={linkedinUrl}
                    onChange={(e) => setLinkedinUrl(e.target.value)}
                    placeholder="https://linkedin.com/in/prospect"
                    className="w-full bg-background border border-border rounded-lg px-3 py-2 text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all disabled:opacity-50"
                  />
                </div>

                <div className="pt-2 border-t border-border space-y-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <label htmlFor="conn-checkbox" className="font-semibold text-foreground block cursor-pointer">
                        1st-Degree Connection Accepted?
                      </label>
                      <span className="text-[11px] text-muted-foreground">Prospect is already connected to sender</span>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        id="conn-checkbox"
                        type="checkbox"
                        disabled={isSimulating}
                        checked={isConnected}
                        onChange={(e) => setIsConnected(e.target.checked)}
                        aria-label="1st-Degree Connection Accepted"
                        className="sr-only peer"
                      />
                      <div className="w-10 h-5 bg-muted peer-focus-visible:ring-2 peer-focus-visible:ring-primary peer-focus-visible:ring-offset-2 rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-background after:border-border after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-primary"></div>
                    </label>
                  </div>

                  <div className="flex items-center justify-between">
                    <div>
                      <label htmlFor="inmail-checkbox" className="font-semibold text-foreground block cursor-pointer">
                        InMail / Open Profile Eligible?
                      </label>
                      <span className="text-[11px] text-muted-foreground">Allows free InMails or credits available</span>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        id="inmail-checkbox"
                        type="checkbox"
                        disabled={isSimulating}
                        checked={inmailEligible}
                        onChange={(e) => setInmailEligible(e.target.checked)}
                        aria-label="InMail or Open Profile Eligible"
                        className="sr-only peer"
                      />
                      <div className="w-10 h-5 bg-muted peer-focus-visible:ring-2 peer-focus-visible:ring-primary peer-focus-visible:ring-offset-2 rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-background after:border-border after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-primary"></div>
                    </label>
                  </div>
                </div>

                <div>
                  <label htmlFor="omni-priority" className="text-muted-foreground font-medium block mb-1">
                    Cascade Priority Order:
                  </label>
                  <Select
                    value={cascadePriority}
                    onValueChange={(val) => setCascadePriority(val)}
                  >
                    <SelectTrigger id="omni-priority" className="w-full bg-background border-border h-9 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="linkedin,email,inmail">Default (LinkedIn 1st &rarr; Email &rarr; InMail &rarr; Fallback)</SelectItem>
                      <SelectItem value="email,linkedin,inmail">Email-First (Email &rarr; LinkedIn 1st &rarr; InMail &rarr; Fallback)</SelectItem>
                      <SelectItem value="inmail,email,linkedin">InMail-First (InMail &rarr; Email &rarr; LinkedIn 1st &rarr; Fallback)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <button
                type="submit"
                disabled={isSimulating}
                className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground font-semibold text-xs transition-colors cursor-pointer disabled:opacity-50 mt-2"
              >
                {isSimulating ? (
                  <>
                    <RefreshCw size={14} className="animate-spin" />
                    <span>Simulating Cascade...</span>
                  </>
                ) : !isPro ? (
                  <>
                    <Lock size={13} />
                    <span>Unlock Pro to Simulate Route</span>
                  </>
                ) : (
                  <>
                    <Zap size={14} />
                    <span>Simulate Omnichannel Route</span>
                  </>
                )}
              </button>
            </form>

            {/* Simulation Results Radar Card */}
            <div className="p-5 rounded-xl bg-card border border-border space-y-4 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs font-semibold text-foreground">
                    Cascade Evaluation Outcome
                  </span>
                  <span className="text-[10px] px-2 py-0.5 rounded-md font-mono bg-muted text-muted-foreground border border-border">
                    Deterministic Engine
                  </span>
                </div>

                {simulationResult ? (
                  <div className="space-y-4 animate-in fade-in duration-150">
                    <div className="p-4 rounded-xl bg-muted/30 border border-border space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-[11px] text-muted-foreground block font-medium">Selected Outreach Channel:</span>
                        <button
                          type="button"
                          onClick={handleCopyJson}
                          className="text-[11px] text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors"
                          title="Copy evaluated JSON"
                        >
                          {copiedResult ? <Check size={12} className="text-emerald-500" /> : <Copy size={12} />}
                          <span>{copiedResult ? "Copied" : "Copy JSON"}</span>
                        </button>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-lg font-bold uppercase tracking-wide text-foreground">
                          {simulationResult.routed_channel}
                        </span>
                        <span className="text-xs px-2.5 py-0.5 rounded-full bg-card border border-border font-medium text-foreground">
                          Branch: {simulationResult.branch}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground leading-relaxed pt-1">
                        {simulationResult.routing_reason}
                      </p>
                    </div>

                    {/* Safety Guardrails Checked */}
                    <div className="space-y-2 text-xs">
                      <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block">
                        Safety Guardrails Verified:
                      </span>
                      <div className="flex items-center gap-2 text-foreground">
                        <ShieldCheck size={14} className="text-emerald-600 dark:text-emerald-400" />
                        <span>Suppression List Check: Clean (Not unsubscribed)</span>
                      </div>
                      <div className="flex items-center gap-2 text-foreground">
                        <CheckCircle2 size={14} className="text-emerald-600 dark:text-emerald-400" />
                        <span>Workspace Tenant Isolation: Enforced</span>
                      </div>
                      <div className="flex items-center gap-2 text-foreground">
                        <Zap size={14} className="text-emerald-600 dark:text-emerald-400" />
                        <span>Daily Channel Quota: Under limit, safe to dispatch</span>
                      </div>
                    </div>

                    {/* Variable Output Inspector Disclosure */}
                    {simulationResult.variables && (
                      <div className="pt-2 border-t border-border">
                        <button
                          type="button"
                          onClick={() => setShowVariablesInspector(!showVariablesInspector)}
                          className="w-full flex items-center justify-between text-xs text-muted-foreground hover:text-foreground transition-colors py-1"
                        >
                          <span className="font-medium">Inspect Node Variables</span>
                          {showVariablesInspector ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                        </button>
                        {showVariablesInspector && (
                          <pre className="mt-2 p-3 bg-muted/40 rounded-lg text-[10px] font-mono text-foreground overflow-x-auto border border-border max-h-36">
                            {JSON.stringify(simulationResult.variables, null, 2)}
                          </pre>
                        )}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="p-8 text-center space-y-2 border border-dashed border-border rounded-xl">
                    <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center mx-auto text-muted-foreground">
                      <Compass className="w-5 h-5 text-primary" />
                    </div>
                    <div className="text-sm font-semibold text-foreground">Awaiting Route Simulation</div>
                    <p className="text-xs text-muted-foreground max-w-xs mx-auto">
                      Configure prospect attributes on the left and click "Simulate Omnichannel Route" to evaluate the 4-tier dispatch cascade.
                    </p>
                  </div>
                )}
              </div>

              <div className="p-3 bg-muted/30 border border-border rounded-lg text-[11px] text-muted-foreground">
                Tip: When adding the <code className="text-foreground font-mono">retarget_omnichannel</code> node into sequence trees, downstream connections branch automatically along <span className="text-foreground font-semibold">LinkedIn</span>, <span className="text-foreground font-semibold">Email</span>, and <span className="text-foreground font-semibold">InMail</span> paths.
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-5 sm:px-6 py-4 border-t border-border bg-card/60 flex items-center justify-between text-xs text-muted-foreground shrink-0">
          <span>Deterministic omnichannel routing active</span>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg border border-border bg-muted/60 hover:bg-muted text-foreground text-xs font-medium transition-colors cursor-pointer"
          >
            Close Studio
          </button>
        </div>
      </div>
    </div>
  );
}
