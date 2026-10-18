import { useState, useEffect } from "react";
import { Shield, ShieldAlert, ShieldCheck, Loader2, AlertTriangle, CheckCircle2, Lock, Unlock, Zap } from "lucide-react";
import { toast } from "sonner";
import { friendlyToast } from "../../components/FriendlyError";
import { useWorkspaceData } from "./useWorkspaceData";
import { motion, AnimatePresence } from "motion/react";
import useSWR from "swr";
import { fetcher, fetchWithAuth } from "@/lib/apiClient";
import { SettingsLoadingSkeleton } from "@/components/SettingsLoadingSkeleton";
import { EmptyState } from "@/components/EmptyState";
import { usePaywall } from "@/contexts/PaywallContext";

export function SecuritySettings({ workspaceId }: { workspaceId: string | null }) {
  const { data, mutate, isLoading, error } = useWorkspaceData(workspaceId);
  const { data: billing } = useSWR<{ tier?: string; tier_limits?: { can_enforce_2fa?: boolean } }>(
    '/api/elein/workspaces/billing',
    fetcher
  );
  const { openPaywall } = usePaywall();
  const is2faLocked = Boolean(billing && !billing.tier_limits?.can_enforce_2fa);

  const [require2fa, setRequire2fa] = useState(false);
  const [saving, setSaving] = useState(false);
  
  // Modal / Confirm state
  const [showConfirm, setShowConfirm] = useState(false);
  const [confirmCountdown, setConfirmCountdown] = useState(0);

  // Track if we just turned it on to show the success banner
  const [justEnabled, setJustEnabled] = useState(false);

  useEffect(() => {
    if (!showConfirm) return;
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setShowConfirm(false);
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [showConfirm]);

  useEffect(() => {
    if (data !== undefined) {
      setRequire2fa(!!data?.require_2fa);
    }
  }, [data]);

  // Countdown logic for the confirmation modal
  useEffect(() => {
    if (showConfirm && confirmCountdown > 0) {
      const timer = setTimeout(() => {
        setConfirmCountdown((prev) => prev - 1);
      }, 1000);
      return () => clearTimeout(timer);
    }
  }, [showConfirm, confirmCountdown]);

  const handleToggleClick = () => {
    if (saving) return;

    if (!require2fa) {
      if (is2faLocked) {
        openPaywall({ featureName: "Mandatory Workspace 2FA Enforcement" });
        return;
      }
      // Turning ON: show confirm modal
      setConfirmCountdown(2);
      setShowConfirm(true);
    } else {
      // Turning OFF: just do it, but maybe no success banner afterwards
      setJustEnabled(false);
      save2faPreference(false);
    }
  };

  const save2faPreference = async (newValue: boolean) => {
    if (!workspaceId) return;
    setSaving(true);
    setShowConfirm(false);
    
    // Optimistic update
    const previousValue = require2fa;
    setRequire2fa(newValue);

    try {
      const res = await fetchWithAuth(`/api/workspaces/${workspaceId}/require-2fa`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ require_2fa: newValue }),
      });
      
      if (!res.ok) {
        if (res.status === 402 || res.status === 403) {
          openPaywall({ featureName: "Mandatory Workspace 2FA Enforcement" });
          setRequire2fa(previousValue);
          setSaving(false);
          return;
        }
        const errText = await res.text();
        throw new Error(errText || "Failed to update security settings");
      }
      
      toast.success(newValue ? "2FA is now enforced" : "2FA enforcement disabled");
      
      if (newValue) {
        setJustEnabled(true);
      }
      
      mutate();
    } catch (e: any) {
      friendlyToast('Failed to update security settings — please try again.', e);
      // Revert local state
      setRequire2fa(previousValue);
      if (newValue) {
        setJustEnabled(false);
      }
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
    return <EmptyState title="No Workspace Selected" description="Please select a workspace to view and manage its security settings." icon={ShieldAlert} />;
  }

  if (isLoading) {
    return <SettingsLoadingSkeleton />;
  }

  // Animation values for the circular progress
  const scorePercentage = require2fa ? 100 : 40;
  const radius = 80;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (scorePercentage / 100) * circumference;

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Hero Section: Security Command Center */}
      <div className="p-6 md:p-8 rounded-xl border border-border bg-card relative overflow-hidden shadow-sm">
        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-border to-transparent opacity-20" />
        
        <div className="flex flex-col items-center text-center">
          <h2 className="text-2xl font-bold tracking-tight text-foreground">Security Command Center</h2>
          <p className="text-sm text-muted-foreground mt-1 mb-8">
            Monitor and enforce security policies across your workspace to protect your data and connected accounts.
          </p>

          <div className="flex flex-col md:flex-row items-center justify-center gap-12 w-full max-w-2xl mb-4">
            {/* Radial Progress Score */}
            <div className="relative flex items-center justify-center w-48 h-48">
              {/* Background track */}
              <svg className="w-full h-full transform -rotate-90" viewBox="0 0 200 200">
                <circle
                  cx="100"
                  cy="100"
                  r={radius}
                  className="stroke-muted/30"
                  strokeWidth="12"
                  fill="none"
                />
                {/* Animated Progress */}
                <motion.circle
                  cx="100"
                  cy="100"
                  r={radius}
                  className={require2fa ? "stroke-success" : "stroke-primary"}
                  strokeWidth="12"
                  fill="none"
                  strokeLinecap="round"
                  initial={{ strokeDashoffset: circumference }}
                  animate={{ strokeDashoffset }}
                  transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                  style={{ strokeDasharray: circumference }}
                />
              </svg>
              
              {/* Center Content */}
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <motion.div
                  key={require2fa ? 'protected' : 'vulnerable'}
                  initial={{ opacity: 0, scale: 0.8 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                  className="flex flex-col items-center"
                >
                  {require2fa ? (
                    <>
                      <Lock className="w-8 h-8 text-success mb-1" />
                      <span className="text-2xl font-bold text-success">{scorePercentage}%</span>
                      <span className="text-xs font-medium text-success/80 uppercase tracking-wider">Fully Secured</span>
                    </>
                  ) : (
                    <>
                      <Unlock className="w-8 h-8 text-destructive mb-1" />
                      <span className="text-2xl font-bold text-destructive">{scorePercentage}%</span>
                      <span className="text-xs font-medium text-destructive/80 uppercase tracking-wider">Vulnerable</span>
                    </>
                  )}
                </motion.div>
              </div>
            </div>

            {/* Security Checklist */}
            <div className="flex flex-col gap-4 text-left bg-background/50 p-6 rounded-xl border border-border/60 w-full max-w-sm">
              <h3 className="text-lg font-bold tracking-tight text-foreground">Security Checklist</h3>
              <div className="flex items-center gap-3">
                <CheckCircle2 className="w-5 h-5 text-success shrink-0" />
                <span className="text-sm font-medium text-foreground">Workspace Created</span>
              </div>
              <div className="flex items-center gap-3">
                <CheckCircle2 className="w-5 h-5 text-success shrink-0" />
                <span className="text-sm font-medium text-foreground">Email Verified</span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  {require2fa ? (
                    <CheckCircle2 className="w-5 h-5 text-success shrink-0" />
                  ) : (
                    <div className="w-5 h-5 rounded-full border-2 border-muted-foreground/30 shrink-0" />
                  )}
                  <span className={`text-sm font-medium ${require2fa ? 'text-foreground' : 'text-muted-foreground'}`}>2FA Enforced</span>
                </div>
                {is2faLocked && !require2fa && (
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-500 border border-amber-500/20">
                    Pro
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Main Action Card */}
      <div className="p-0 rounded-xl border border-border bg-card shadow-sm relative overflow-hidden">
        {/* In-Situ Pay Ramp Banner */}
        {is2faLocked && (
          <div className="m-6 sm:m-8 mb-0 p-5 rounded-xl bg-gradient-to-r from-amber-500/10 via-primary/10 to-amber-500/5 border border-amber-500/30 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div className="flex items-start gap-3.5">
              <div className="p-2.5 bg-amber-500/10 rounded-xl text-amber-600 dark:text-amber-400 shrink-0 mt-0.5">
                <Lock size={20} />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100">
                    Growth Pro Feature: Mandatory Workspace-wide 2FA Enforcement
                  </h3>
                  <span className="text-[10px] font-extrabold uppercase px-2 py-0.5 bg-amber-500/20 text-amber-600 dark:text-amber-400 rounded-full border border-amber-500/30">
                    Pro Gated
                  </span>
                </div>
                <p className="text-xs text-gray-600 dark:text-gray-400 mt-1 max-w-xl leading-relaxed">
                  Individual account 2FA is always available for personal profiles. Mandatory workspace-wide 2FA enforcement across all team members, automated session termination, and compliance governance require Growth Pro or Enterprise.
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => openPaywall({ featureName: "Mandatory Workspace 2FA Enforcement" })}
              className="px-4 py-2 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-600 hover:to-amber-700 text-white rounded-xl text-xs font-bold shadow-sm shadow-amber-500/25 shrink-0 flex items-center gap-1.5 transition-all cursor-pointer"
            >
              <Zap size={13} className="fill-current" />
              Upgrade to Growth Pro
            </button>
          </div>
        )}

        {/* Success Banner (Commitment & Consistency) */}
        <AnimatePresence>
          {require2fa && justEnabled && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="bg-success/10 border-b border-success/20 overflow-hidden"
            >
              <div className="p-4 flex items-start sm:items-center gap-3">
                <CheckCircle2 className="w-5 h-5 text-success shrink-0 mt-0.5 sm:mt-0" />
                <p className="text-sm text-success dark:text-success font-medium">
                  Your workspace is now protected. Members without 2FA will be prompted to enroll on their next login.
                </p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="p-6 md:p-8">
          <div className="flex flex-col md:flex-row gap-6 md:gap-8 items-start justify-between">
            
            <div className="flex-1 space-y-4">
              <div className="flex items-center gap-3">
                <div className={`p-2.5 rounded-xl ${require2fa ? 'bg-success/10 text-success' : 'bg-muted text-muted-foreground'}`}>
                  {require2fa ? <ShieldCheck size={24} /> : <ShieldAlert size={24} />}
                </div>
                <div>
                  <h3 className="text-lg font-bold tracking-tight text-foreground flex items-center gap-2">
                    Enforce Two-Factor Authentication
                  </h3>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="inline-flex items-center gap-1 text-xs font-medium bg-muted px-2 py-0.5 rounded text-muted-foreground">
                      <CheckCircle2 className="w-3 h-3" />
                      Industry Standard
                    </span>
                    {require2fa && (
                      <span className="px-2 py-0.5 text-xs bg-success/10 text-success rounded font-bold uppercase tracking-wider">
                        Enforced
                      </span>
                    )}
                  </div>
                </div>
              </div>
              
              <p className="text-sm text-muted-foreground mt-1">
                When enabled, every member of this workspace will be forced to configure and use a TOTP authenticator app (like Google Authenticator or Authy) on their next login.
              </p>

              <div className="text-sm text-muted-foreground/80 italic border border-border/60 bg-muted/20 p-3 rounded-lg">
                "LinkedIn recommends 2FA for all automation platforms to prevent account takeovers."
              </div>

              {/* Loss Aversion Warning when OFF */}
              <AnimatePresence>
                {!require2fa && (
                  <motion.div
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    className="mt-4 p-4 rounded-xl border border-destructive/30 bg-destructive/5 flex gap-3"
                  >
                    <AlertTriangle className="w-5 h-5 text-destructive shrink-0 mt-0.5" />
                    <p className="text-sm text-destructive dark:text-destructive/90 leading-relaxed">
                      <strong className="font-semibold block mb-1">High Risk Exposure</strong>
                      Without 2FA enforcement, any compromised password can give an attacker full access to all LinkedIn accounts connected to this workspace.
                    </p>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* Oversized Toggle */}
            <div className="shrink-0 pt-2 flex flex-col items-center">
              <button
                type="button"
                onClick={handleToggleClick}
                disabled={saving || showConfirm}
                className={`relative inline-flex h-8 w-16 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-300 ease-in-out focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background disabled:opacity-50 disabled:cursor-not-allowed ${
                  require2fa ? "bg-success" : is2faLocked ? "bg-muted border border-border" : "bg-muted"
                }`}
                role="switch"
                aria-checked={require2fa}
              >
                <span className="sr-only">Toggle 2FA Enforcement</span>
                <span
                  aria-hidden="true"
                  className={`pointer-events-none inline-flex items-center justify-center h-7 w-7 transform rounded-full bg-white shadow-md ring-0 transition duration-300 ease-in-out ${
                    require2fa ? "translate-x-8" : "translate-x-0"
                  }`}
                >
                  {is2faLocked && !require2fa && (
                    <Lock className="w-3.5 h-3.5 text-amber-500" />
                  )}
                </span>
              </button>
              <span className={`text-xs font-semibold mt-2 flex items-center gap-1 ${
                require2fa ? 'text-success' : is2faLocked ? 'text-amber-500' : 'text-muted-foreground'
              }`}>
                {require2fa ? 'SECURED' : is2faLocked ? 'PRO GATED' : 'UNSECURED'}
              </span>
            </div>
          </div>
        </div>

        {/* Confirmation Modal Drawer (Layer 2) */}
        <AnimatePresence>
          {showConfirm && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-50 bg-background/80 flex justify-end backdrop-blur-xs"
            >
              <motion.div
                initial={{ x: '100%' }}
                animate={{ x: 0 }}
                exit={{ x: '100%' }}
                transition={{ type: 'spring', damping: 25, stiffness: 200 }}
                className="bg-card border-l border-border shadow-2xl w-full max-w-md h-full p-8 flex flex-col rounded-l-xl text-foreground"
              >
                <div className="flex items-center gap-3 mb-8 mt-4">
                  <div className="p-3 bg-primary/10 rounded-xl text-primary">
                    <Shield className="w-8 h-8" />
                  </div>
                  <h2 className="text-2xl font-bold tracking-tight text-foreground">Enforce Security</h2>
                </div>
                
                <p className="text-sm text-muted-foreground mt-1 mb-8 flex-1 leading-relaxed">
                  Turning this on will immediately require all workspace members to use 2FA. Anyone currently logged in without 2FA will be prompted to enroll on their next login or session renewal.
                </p>
                
                <div className="flex flex-col gap-3 pb-8">
                  <button
                    type="button"
                    onClick={() => save2faPreference(true)}
                    disabled={confirmCountdown > 0 || saving}
                    className="w-full py-4 bg-primary text-primary-foreground text-base font-semibold rounded-xl hover:bg-primary/90 transition-colors flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                  >
                    {saving ? (
                      <Loader2 className="w-5 h-5 animate-spin" />
                    ) : confirmCountdown > 0 ? (
                      `Enforce (${confirmCountdown})`
                    ) : (
                      "Yes, Enforce 2FA"
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setShowConfirm(false);
                      setConfirmCountdown(0);
                    }}
                    disabled={saving}
                    className="w-full py-4 bg-muted text-muted-foreground text-base font-medium rounded-xl hover:bg-muted/80 hover:text-foreground transition-colors disabled:opacity-50 cursor-pointer"
                  >
                    Cancel
                  </button>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Enterprise Security & Compliance Suite Preview */}
      <div className="p-8 rounded-xl border border-border bg-card shadow-sm relative overflow-hidden">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-lg font-bold tracking-tight text-foreground">
                Enterprise Compliance & Security Suite
              </h3>
              <span className="text-[10px] font-extrabold uppercase px-2 py-0.5 bg-amber-500/20 text-amber-600 dark:text-amber-400 rounded-full border border-amber-500/30">
                Pro & Enterprise
              </span>
            </div>
            <p className="text-sm text-muted-foreground mt-1">
              Advanced access control, governance policies, and dedicated security infrastructure for scaling teams.
            </p>
          </div>
          {is2faLocked && (
            <button
              type="button"
              onClick={() => openPaywall({ featureName: "Enterprise Security & Compliance Pack" })}
              className="px-3.5 py-1.5 bg-muted hover:bg-muted/80 text-foreground rounded-xl text-xs font-semibold shrink-0 flex items-center gap-1.5 transition-all self-start sm:self-auto cursor-pointer border border-border"
            >
              <Lock size={12} className="text-amber-500" />
              View Security Tiers
            </button>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="p-5 rounded-xl border border-border bg-muted/40 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-bold text-foreground">Session Inactivity Timeout</span>
                <span className="text-[10px] bg-primary/10 text-primary px-1.5 py-0.5 rounded font-bold">Pro+</span>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">
                Automated session termination after 15m, 1h, or 8h of inactivity to protect corporate workstations.
              </p>
            </div>
            <div className="mt-4 pt-3 border-t border-border flex items-center justify-between text-[11px] text-muted-foreground">
              <span>Policy Status</span>
              <span className="font-semibold text-foreground">{is2faLocked ? "Locked (Default: 7d)" : "Configurable"}</span>
            </div>
          </div>

          <div className="p-5 rounded-xl border border-border bg-muted/40 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-bold text-foreground">IP & Geo Allowlisting</span>
                <span className="text-[10px] bg-primary/10 text-primary px-1.5 py-0.5 rounded font-bold">Enterprise</span>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">
                Restrict campaign creation, lead downloads, and LinkedIn credential changes to designated office CIDRs.
              </p>
            </div>
            <div className="mt-4 pt-3 border-t border-border flex items-center justify-between text-[11px] text-muted-foreground">
              <span>Policy Status</span>
              <span className="font-semibold text-foreground">{is2faLocked ? "Available on Enterprise" : "Enterprise"}</span>
            </div>
          </div>

          <div className="p-5 rounded-xl border border-border bg-muted/40 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-bold text-foreground">SOC 2 / HIPAA Data Retention</span>
                <span className="text-[10px] bg-primary/10 text-primary px-1.5 py-0.5 rounded font-bold">Enterprise</span>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">
                Automated lead scrubbing schedules and permanent tamper-proof audit trails for external auditors.
              </p>
            </div>
            <div className="mt-4 pt-3 border-t border-border flex items-center justify-between text-[11px] text-muted-foreground">
              <span>Policy Status</span>
              <span className="font-semibold text-foreground">{is2faLocked ? "Available on Enterprise" : "Enterprise"}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
