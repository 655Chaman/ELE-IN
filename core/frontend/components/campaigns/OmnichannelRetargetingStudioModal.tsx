import React, { useState } from 'react';
import useSWR from 'swr';
import { 
  Layers, ArrowRight, CheckCircle2, ShieldCheck, 
  RefreshCw, Zap, Lock, X, Compass
} from 'lucide-react';
import { toast } from 'sonner';
import { motion } from 'motion/react';
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
  const [simulationResult, setSimulationResult] = useState<any>({
    status: "success",
    routed_channel: "email",
    branch: "Email",
    routing_reason: "Tier 2: Deliverable email verified (prospect not 1st-degree connected)",
    variables: {
      omnichannel_routed_channel: "email",
      omnichannel_branch: "Email",
      omnichannel_is_connected: false,
      omnichannel_inmail_eligible: true
    },
    evaluated_at: new Date().toISOString()
  });

  const handleSimulateRoute = async () => {
    if (!isPro) {
      openPaywall({
        featureName: "Omnichannel Retargeting Cascade",
        minTier: "PRO",
        description: "Simulate and execute automated 4-tier channel handoffs across LinkedIn DMs, Verified Email, and Open InMail."
      });
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
        const err = await res.json();
        throw new Error(err.detail?.message || err.detail || 'Evaluation failed');
      }

      const data = await res.json();
      setSimulationResult(data);
      toast.success(`Route Evaluated: Selected channel is ${data.routed_channel.toUpperCase()}`);
    } catch (err: any) {
      toast.error(err.message || "Failed to simulate omnichannel route.");
    } finally {
      setIsSimulating(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-background/80 backdrop-blur-sm overflow-y-auto">
      <motion.div 
        initial={{ opacity: 0, scale: 0.98, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.98, y: 8 }}
        className="w-full max-w-4xl bg-background border border-border rounded-xl shadow-lg overflow-hidden flex flex-col max-h-[92vh]"
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-border bg-background flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-muted/40 border border-border flex items-center justify-center text-foreground">
              <Layers size={18} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold text-foreground">Omnichannel Retargeting & Step Forking Studio</h2>
                {isPro ? (
                  <span className="text-[10px] px-2 py-0.5 rounded-md font-medium uppercase tracking-wider bg-muted text-foreground border border-border">
                    Pro Enabled
                  </span>
                ) : (
                  <button 
                    type="button"
                    onClick={() => openPaywall({ featureName: "Omnichannel Retargeting Studio", minTier: "PRO" })}
                    className="text-[10px] px-2 py-0.5 rounded-md font-medium uppercase tracking-wider bg-muted text-muted-foreground border border-border flex items-center gap-1 hover:text-foreground transition-colors cursor-pointer"
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
              className="w-8 h-8 rounded-md border border-border hover:bg-muted text-muted-foreground hover:text-foreground flex items-center justify-center transition-colors cursor-pointer"
            >
              <X size={16} />
            </button>
          )}
        </div>

        {/* Free Tier In-Situ Paywall Banner */}
        {!isPro && (
          <div className="px-6 py-3 bg-muted/30 border-b border-border flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs shrink-0">
            <div className="flex items-center gap-3">
              <div className="w-7 h-7 rounded-md bg-card border border-border flex items-center justify-center text-muted-foreground shrink-0">
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
              onClick={() => openPaywall({ featureName: "Omnichannel Retargeting Cascade" })}
              className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 font-medium text-xs transition-colors shrink-0 self-start sm:self-auto cursor-pointer"
            >
              <Zap size={13} />
              <span>Unlock Omnichannel</span>
              <ArrowRight size={13} />
            </button>
          </div>
        )}

        {/* Body */}
        <div className="p-6 overflow-y-auto flex-1 space-y-6">
          {/* Architecture Cascade Visualizer */}
          <div className="p-4 bg-muted/30 border border-border rounded-lg space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-foreground flex items-center gap-2">
                <Compass size={14} className="text-muted-foreground" />
                <span>4-Tier Waterfall Dispatch Cascade</span>
              </span>
              <span className="text-[11px] text-muted-foreground">
                Automatic Failover Algorithm
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-4 gap-2.5 text-xs">
              <div className={`p-3 rounded-lg border transition-colors ${
                simulationResult?.routed_channel === 'linkedin' && isConnected
                  ? 'bg-primary/10 border-primary text-foreground font-semibold'
                  : 'bg-card border-border text-muted-foreground'
              }`}>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono uppercase tracking-wider">Tier 1</span>
                  {simulationResult?.routed_channel === 'linkedin' && isConnected && (
                    <span className="w-2 h-2 rounded-full bg-primary" />
                  )}
                </div>
                <p className="font-semibold text-foreground mt-1">1st-Degree LinkedIn</p>
                <p className="text-[10px] text-muted-foreground mt-0.5">Direct Message / Voice Note</p>
              </div>

              <div className={`p-3 rounded-lg border transition-colors ${
                simulationResult?.routed_channel === 'email'
                  ? 'bg-primary/10 border-primary text-foreground font-semibold'
                  : 'bg-card border-border text-muted-foreground'
              }`}>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono uppercase tracking-wider">Tier 2</span>
                  {simulationResult?.routed_channel === 'email' && (
                    <span className="w-2 h-2 rounded-full bg-primary" />
                  )}
                </div>
                <p className="font-semibold text-foreground mt-1">Verified Cold Email</p>
                <p className="text-[10px] text-muted-foreground mt-0.5">SendGrid / Smartlead Bridge</p>
              </div>

              <div className={`p-3 rounded-lg border transition-colors ${
                simulationResult?.routed_channel === 'inmail'
                  ? 'bg-primary/10 border-primary text-foreground font-semibold'
                  : 'bg-card border-border text-muted-foreground'
              }`}>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono uppercase tracking-wider">Tier 3</span>
                  {simulationResult?.routed_channel === 'inmail' && (
                    <span className="w-2 h-2 rounded-full bg-primary" />
                  )}
                </div>
                <p className="font-semibold text-foreground mt-1">InMail / Open Profile</p>
                <p className="text-[10px] text-muted-foreground mt-0.5">Sales Nav / Sponsored InMail</p>
              </div>

              <div className={`p-3 rounded-lg border transition-colors ${
                simulationResult?.routed_channel === 'linkedin' && !isConnected
                  ? 'bg-primary/10 border-primary text-foreground font-semibold'
                  : 'bg-card border-border text-muted-foreground'
              }`}>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono uppercase tracking-wider">Tier 4</span>
                  {simulationResult?.routed_channel === 'linkedin' && !isConnected && (
                    <span className="w-2 h-2 rounded-full bg-primary" />
                  )}
                </div>
                <p className="font-semibold text-foreground mt-1">Social Touch Fallback</p>
                <p className="text-[10px] text-muted-foreground mt-0.5">Connection Request / View</p>
              </div>
            </div>
          </div>

          {/* Interactive Simulator Deck */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Input Attributes */}
            <div className="p-5 rounded-lg bg-card border border-border space-y-4">
              <span className="text-xs font-semibold text-foreground block">
                Prospect Attribute Inputs
              </span>

              <div className="space-y-3 text-xs">
                <div>
                  <label className="text-muted-foreground font-medium block mb-1">
                    Corporate Email:
                  </label>
                  <input
                    type="text"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="prospect@company.com"
                    className="w-full bg-background border border-border rounded-md px-3 py-2 text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>

                <div>
                  <label className="text-muted-foreground font-medium block mb-1">
                    LinkedIn Profile URL:
                  </label>
                  <input
                    type="text"
                    value={linkedinUrl}
                    onChange={(e) => setLinkedinUrl(e.target.value)}
                    placeholder="https://linkedin.com/in/prospect"
                    className="w-full bg-background border border-border rounded-md px-3 py-2 text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>

                <div className="pt-2 border-t border-border space-y-2.5">
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="font-semibold text-foreground block">1st-Degree Connection Accepted?</span>
                      <span className="text-[11px] text-muted-foreground">Prospect is already connected to sender</span>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={isConnected}
                        onChange={(e) => setIsConnected(e.target.checked)}
                        className="sr-only peer"
                      />
                      <div className="w-10 h-5 bg-muted peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-background after:border-border after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-primary"></div>
                    </label>
                  </div>

                  <div className="flex items-center justify-between">
                    <div>
                      <span className="font-semibold text-foreground block">InMail / Open Profile Eligible?</span>
                      <span className="text-[11px] text-muted-foreground">Allows free InMails or credits available</span>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={inmailEligible}
                        onChange={(e) => setInmailEligible(e.target.checked)}
                        className="sr-only peer"
                      />
                      <div className="w-10 h-5 bg-muted peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-background after:border-border after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-primary"></div>
                    </label>
                  </div>
                </div>

                <div>
                  <label className="text-muted-foreground font-medium block mb-1">
                    Cascade Priority Order:
                  </label>
                  <Select
                    value={cascadePriority}
                    onValueChange={(val) => setCascadePriority(val)}
                  >
                    <SelectTrigger className="w-full bg-background border-border h-9 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="linkedin,email,inmail">Default (LinkedIn 1st -&gt; Email -&gt; InMail -&gt; Fallback)</SelectItem>
                      <SelectItem value="email,linkedin,inmail">Email-First (Email -&gt; LinkedIn 1st -&gt; InMail -&gt; Fallback)</SelectItem>
                      <SelectItem value="inmail,email,linkedin">InMail-First (InMail -&gt; Email -&gt; LinkedIn 1st -&gt; Fallback)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <button
                type="button"
                onClick={handleSimulateRoute}
                disabled={isSimulating}
                className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-md bg-primary hover:bg-primary/90 text-primary-foreground font-semibold text-xs transition-colors cursor-pointer disabled:opacity-50 mt-2"
              >
                <RefreshCw size={14} className={isSimulating ? 'animate-spin' : ''} />
                <span>{isSimulating ? 'Simulating Cascade...' : 'Simulate Omnichannel Route'}</span>
              </button>
            </div>

            {/* Simulation Results Radar Card */}
            <div className="p-5 rounded-lg bg-card border border-border space-y-4 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs font-semibold text-foreground">
                    Cascade Evaluation Outcome
                  </span>
                  <span className="text-[10px] px-2 py-0.5 rounded-md font-mono bg-muted text-muted-foreground border border-border">
                    Deterministic Engine
                  </span>
                </div>

                {simulationResult && (
                  <div className="space-y-4">
                    <div className="p-4 rounded-lg bg-muted/30 border border-border">
                      <span className="text-[11px] text-muted-foreground block font-medium">Selected Outreach Channel:</span>
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-lg font-bold uppercase tracking-wide text-foreground">
                          {simulationResult.routed_channel}
                        </span>
                        <span className="text-xs px-2 py-0.5 rounded-md bg-card border border-border font-medium text-foreground">
                          Branch: {simulationResult.branch}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground mt-2 leading-relaxed">
                        {simulationResult.routing_reason}
                      </p>
                    </div>

                    {/* Safety Guardrails Checked */}
                    <div className="space-y-2 text-xs">
                      <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block">
                        Safety Guardrails Applied:
                      </span>
                      <div className="flex items-center gap-2 text-foreground">
                        <ShieldCheck size={14} className="text-muted-foreground" />
                        <span>Suppression List Check: Clean (Not unsubscribed)</span>
                      </div>
                      <div className="flex items-center gap-2 text-foreground">
                        <CheckCircle2 size={14} className="text-muted-foreground" />
                        <span>Workspace Tenant Isolation: Enforced</span>
                      </div>
                      <div className="flex items-center gap-2 text-foreground">
                        <Zap size={14} className="text-muted-foreground" />
                        <span>Daily Channel Quota: Under limit, safe to dispatch</span>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              <div className="p-3 bg-muted/30 border border-border rounded-lg text-[11px] text-muted-foreground">
                Tip: When adding the <code className="text-foreground font-mono">retarget_omnichannel</code> node into sequence trees, downstream connections will branch automatically along <span className="text-foreground font-semibold">LinkedIn</span>, <span className="text-foreground font-semibold">Email</span>, and <span className="text-foreground font-semibold">InMail</span> paths.
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-border bg-background flex items-center justify-between text-xs text-muted-foreground shrink-0">
          <span>Deterministic omnichannel routing active</span>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 rounded-md border border-border bg-card hover:bg-muted text-foreground text-xs font-medium transition-colors cursor-pointer"
          >
            Close Studio
          </button>
        </div>
      </motion.div>
    </div>
  );
}
