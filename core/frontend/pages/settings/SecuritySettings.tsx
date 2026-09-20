import { useState, useEffect } from "react";
import { Shield, ShieldAlert, ShieldCheck, Loader2, AlertTriangle, CheckCircle2, Lock, Unlock } from "lucide-react";
import { toast } from "sonner";
import { useWorkspaceData } from "./useWorkspaceData";
import { motion, AnimatePresence } from "motion/react";
import SpotlightCard from "@/components/SpotlightCard";
import { fetcher, fetchWithAuth } from "@/lib/apiClient";
import { SettingsLoadingSkeleton } from "@/components/SettingsLoadingSkeleton";
import { EmptyState } from "@/components/EmptyState";

export function SecuritySettings({ workspaceId }: { workspaceId: string | null }) {
  const { data, mutate, isLoading, error } = useWorkspaceData(workspaceId);

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
        const errText = await res.text();
        throw new Error(errText || "Failed to update security settings");
      }
      
      toast.success(newValue ? "2FA is now enforced" : "2FA enforcement disabled");
      
      if (newValue) {
        setJustEnabled(true);
      }
      
      mutate();
    } catch (e: any) {
      toast.error(e.message || "Failed to update security settings");
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
      <SpotlightCard className="p-8 rounded-2xl border border-border/50 bg-surface/50 backdrop-blur-md relative overflow-hidden">
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
                  className={require2fa ? "stroke-emerald-500" : "stroke-primary"}
                  strokeWidth="12"
                  fill="none"
                  strokeLinecap="round"
                  initial={{ strokeDashoffset: circumference }}
                  animate={{ strokeDashoffset }}
                  transition={{ duration: 1.5, ease: "easeOut" }}
                  style={{ strokeDasharray: circumference }}
                />
              </svg>
              
              {/* Center Content */}
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <motion.div
                  key={require2fa ? 'protected' : 'vulnerable'}
                  initial={{ opacity: 0, scale: 0.8 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ duration: 0.4 }}
                  className="flex flex-col items-center"
                >
                  {require2fa ? (
                    <>
                      <Lock className="w-8 h-8 text-emerald-500 mb-1" />
                      <span className="text-2xl font-bold text-emerald-500">{scorePercentage}%</span>
                      <span className="text-xs font-medium text-emerald-500/80 uppercase tracking-wider">Fully Secured</span>
                    </>
                  ) : (
                    <>
                      <Unlock className="w-8 h-8 text-primary mb-1" />
                      <span className="text-2xl font-bold text-primary">{scorePercentage}%</span>
                      <span className="text-xs font-medium text-primary/80 uppercase tracking-wider">Vulnerable</span>
                    </>
                  )}
                </motion.div>
              </div>
            </div>

            {/* Security Checklist */}
            <div className="flex flex-col gap-4 text-left bg-background/50 p-6 rounded-xl border border-border/50 w-full max-w-sm">
              <h3 className="text-lg font-bold tracking-tight text-foreground">Security Checklist</h3>
              <div className="flex items-center gap-3">
                <CheckCircle2 className="w-5 h-5 text-emerald-500 shrink-0" />
                <span className="text-sm font-medium text-foreground">Workspace Created</span>
              </div>
              <div className="flex items-center gap-3">
                <CheckCircle2 className="w-5 h-5 text-emerald-500 shrink-0" />
                <span className="text-sm font-medium text-foreground">Email Verified</span>
              </div>
              <div className="flex items-center gap-3">
                {require2fa ? (
                  <CheckCircle2 className="w-5 h-5 text-emerald-500 shrink-0" />
                ) : (
                  <div className="w-5 h-5 rounded-full border-2 border-muted-foreground/30 shrink-0" />
                )}
                <span className={`text-sm font-medium ${require2fa ? 'text-foreground' : 'text-muted-foreground'}`}>2FA Enforced</span>
              </div>
            </div>
          </div>
        </div>
      </SpotlightCard>

      {/* Main Action Card */}
      <SpotlightCard className="p-0 rounded-2xl border border-border/50 bg-surface/50 shadow-sm relative overflow-hidden">
        {/* Success Banner (Commitment & Consistency) */}
        <AnimatePresence>
          {require2fa && justEnabled && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="bg-emerald-500/10 border-b border-emerald-500/20 overflow-hidden"
            >
              <div className="p-4 flex items-start sm:items-center gap-3">
                <CheckCircle2 className="w-5 h-5 text-emerald-500 shrink-0 mt-0.5 sm:mt-0" />
                <p className="text-sm text-emerald-600 dark:text-emerald-400 font-medium">
                  Your workspace is now protected. Members without 2FA will be prompted to enroll on their next login.
                </p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="p-8">
          <div className="flex flex-col md:flex-row gap-6 md:gap-8 items-start justify-between">
            
            <div className="flex-1 space-y-4">
              <div className="flex items-center gap-3">
                <div className={`p-2.5 rounded-xl ${require2fa ? 'bg-emerald-500/10 text-emerald-500' : 'bg-muted text-muted-foreground'}`}>
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
                      <span className="px-2 py-0.5 text-xs bg-emerald-500/10 text-emerald-500 rounded font-bold uppercase tracking-wider">
                        Enforced
                      </span>
                    )}
                  </div>
                </div>
              </div>
              
              <p className="text-sm text-muted-foreground mt-1">
                When enabled, every member of this workspace will be forced to configure and use a TOTP authenticator app (like Google Authenticator or Authy) on their next login.
              </p>

              <div className="text-sm text-muted-foreground/80 italic border-l-2 border-border pl-3">
                "LinkedIn recommends 2FA for all automation platforms to prevent account takeovers."
              </div>

              {/* Loss Aversion Warning when OFF */}
              <AnimatePresence>
                {!require2fa && (
                  <motion.div
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    className="mt-4 p-4 rounded-xl border border-primary/30 bg-primary/5 flex gap-3"
                  >
                    <AlertTriangle className="w-5 h-5 text-primary shrink-0 mt-0.5" />
                    <p className="text-sm text-amber-600 dark:text-primary/80/90 leading-relaxed">
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
                onClick={handleToggleClick}
                disabled={saving || showConfirm}
                className={`relative inline-flex h-8 w-16 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-300 ease-in-out focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background disabled:opacity-50 disabled:cursor-not-allowed ${
                  require2fa ? "bg-emerald-500" : "bg-muted-foreground/30"
                }`}
                role="switch"
                aria-checked={require2fa}
              >
                <span className="sr-only">Toggle 2FA Enforcement</span>
                <span
                  aria-hidden="true"
                  className={`pointer-events-none inline-block h-7 w-7 transform rounded-full bg-white shadow-md ring-0 transition duration-300 ease-in-out ${
                    require2fa ? "translate-x-8" : "translate-x-0"
                  }`}
                />
              </button>
              <span className={`text-xs font-semibold mt-2 ${require2fa ? 'text-emerald-500' : 'text-muted-foreground'}`}>
                {require2fa ? 'SECURED' : 'UNSECURED'}
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
              className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex justify-end"
            >
              <motion.div
                initial={{ x: '100%' }}
                animate={{ x: 0 }}
                exit={{ x: '100%' }}
                transition={{ type: 'spring', damping: 25, stiffness: 200 }}
                className="bg-background border-l border-border shadow-2xl w-full max-w-md h-full p-8 flex flex-col rounded-l-2xl"
              >
                <div className="flex items-center gap-3 mb-8 mt-4">
                  <div className="p-3 bg-primary/10 rounded-2xl text-primary">
                    <Shield className="w-8 h-8" />
                  </div>
                  <h2 className="text-2xl font-bold tracking-tight text-foreground">Enforce Security</h2>
                </div>
                
                <p className="text-sm text-muted-foreground mt-1 mb-8 flex-1">
                  Turning this on will immediately require all workspace members to use 2FA. Anyone currently logged in without 2FA will be prompted to enroll on their next login or session renewal.
                </p>
                
                <div className="flex flex-col gap-3 pb-8">
                  <button
                    onClick={() => save2faPreference(true)}
                    disabled={confirmCountdown > 0 || saving}
                    className="w-full py-4 bg-primary text-primary-foreground text-base font-semibold rounded-xl hover:bg-primary/90 transition-colors flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
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
                    onClick={() => {
                      setShowConfirm(false);
                      setConfirmCountdown(0);
                    }}
                    disabled={saving}
                    className="w-full py-4 bg-muted text-muted-foreground text-base font-medium rounded-xl hover:bg-muted/80 transition-colors disabled:opacity-50"
                  >
                    Cancel
                  </button>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </SpotlightCard>
    </div>
  );
}
