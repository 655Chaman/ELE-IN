import { useState, useEffect } from "react";
import { 
  Shield, ShieldAlert, ShieldCheck, Loader2, AlertTriangle, CheckCircle2, 
  Lock, Unlock, Zap, Key, Laptop, Smartphone, Trash2, Plus, Copy, Check, 
  Globe, RefreshCw, X, Clock 
} from "lucide-react";
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
    workspaceId ? `/api/elein/workspaces/billing?workspace_id=${workspaceId}` : null,
    fetcher
  );
  const { openPaywall } = usePaywall();
  const is2faLocked = Boolean(billing && !billing.tier_limits?.can_enforce_2fa);
  const isAuthorized = !data?.role || data.role === 'owner' || data.role === 'admin';

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

    if (!isAuthorized) {
      toast.error("Only workspace owners and administrators can configure 2FA enforcement.");
      return;
    }

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

  // Active Sessions Management
  const { data: sessionsData, mutate: mutateSessions, isLoading: loadingSessions } = useSWR(
    workspaceId ? `/api/workspaces/${workspaceId}/sessions` : null,
    fetcher
  );
  const [revokingSessionId, setRevokingSessionId] = useState<string | null>(null);
  const [revokingAllSessions, setRevokingAllSessions] = useState(false);

  // Session Inactivity Timeout Policy
  const { data: sessionTimeoutData, mutate: mutateSessionTimeout } = useSWR(
    workspaceId ? `/api/workspaces/${workspaceId}/session-timeout` : null,
    fetcher
  );
  const [idleTimeoutMinutes, setIdleTimeoutMinutes] = useState(60);
  const [enforceDeviceFingerprint, setEnforceDeviceFingerprint] = useState(false);
  const [savingTimeout, setSavingTimeout] = useState(false);

  useEffect(() => {
    if (sessionTimeoutData) {
      setIdleTimeoutMinutes(sessionTimeoutData.session_inactivity_timeout_minutes ?? 60);
      setEnforceDeviceFingerprint(Boolean(sessionTimeoutData.enforce_device_fingerprint));
    }
  }, [sessionTimeoutData]);

  const handleUpdateTimeout = async (newTimeout: number, newFingerprint?: boolean) => {
    if (!workspaceId) return;
    setSavingTimeout(true);
    setIdleTimeoutMinutes(newTimeout);
    if (newFingerprint !== undefined) {
      setEnforceDeviceFingerprint(newFingerprint);
    }
    try {
      const res = await fetchWithAuth(`/api/workspaces/${workspaceId}/session-timeout`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          timeout_minutes: newTimeout,
          enforce_device_fingerprint: newFingerprint !== undefined ? newFingerprint : enforceDeviceFingerprint,
        }),
      });
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText || "Failed to update timeout policy");
      }
      toast.success("Session idle timeout policy updated successfully");
      mutateSessionTimeout();
    } catch (e: any) {
      friendlyToast("Failed to update session timeout", e);
    } finally {
      setSavingTimeout(false);
    }
  };

  const handleRevokeSession = async (sessionId: string) => {
    if (!workspaceId || revokingSessionId) return;
    setRevokingSessionId(sessionId);
    try {
      const res = await fetchWithAuth(`/api/workspaces/${workspaceId}/sessions/${sessionId}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error("Failed to revoke session");
      toast.success("Session revoked successfully");
      mutateSessions();
    } catch (e: any) {
      friendlyToast("Failed to revoke session", e);
    } finally {
      setRevokingSessionId(null);
    }
  };

  const handleRevokeAllOtherSessions = async () => {
    if (!workspaceId || revokingAllSessions) return;
    setRevokingAllSessions(true);
    try {
      const res = await fetchWithAuth(`/api/workspaces/${workspaceId}/sessions/revoke-all`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error("Failed to revoke other sessions");
      toast.success("All other sessions revoked successfully");
      mutateSessions();
    } catch (e: any) {
      friendlyToast("Failed to revoke sessions", e);
    } finally {
      setRevokingAllSessions(false);
    }
  };

  // Developer API Keys Management
  const { data: apiKeysData, mutate: mutateApiKeys, isLoading: loadingApiKeys } = useSWR(
    workspaceId ? `/api/workspaces/${workspaceId}/api-keys` : null,
    fetcher
  );
  const [showCreateKeyModal, setShowCreateKeyModal] = useState(false);
  const [newKeyName, setNewKeyName] = useState("");
  const [newKeyScopes, setNewKeyScopes] = useState<string[]>([
    "campaigns:read", "campaigns:write", "leads:read"
  ]);
  const [createdKeySecret, setCreatedKeySecret] = useState<string | null>(null);
  const [copiedKey, setCopiedKey] = useState(false);
  const [creatingKey, setCreatingKey] = useState(false);
  const [revokingKeyId, setRevokingKeyId] = useState<string | null>(null);

  const AVAILABLE_SCOPES = [
    { id: "campaigns:read", label: "Campaigns: Read", desc: "View campaigns and metrics" },
    { id: "campaigns:write", label: "Campaigns: Write", desc: "Create, pause, or edit campaigns" },
    { id: "leads:read", label: "Leads: Read", desc: "Query and inspect prospect lists" },
    { id: "leads:write", label: "Leads: Write", desc: "Add leads and update statuses" },
    { id: "inbox:read", label: "Inbox: Read", desc: "Read prospect conversation threads" },
    { id: "inbox:write", label: "Inbox: Write", desc: "Send manual messages from inbox" },
  ];

  const handleCreateApiKey = async () => {
    if (!workspaceId || !newKeyName.trim() || creatingKey) return;
    setCreatingKey(true);
    try {
      const res = await fetchWithAuth(`/api/workspaces/${workspaceId}/api-keys`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newKeyName.trim(),
          scopes: newKeyScopes,
        }),
      });
      if (!res.ok) throw new Error("Failed to generate API key");
      const result = await res.json();
      setCreatedKeySecret(result.token);
      toast.success("API key generated successfully");
      mutateApiKeys();
      setNewKeyName("");
    } catch (e: any) {
      friendlyToast("Failed to generate API key", e);
    } finally {
      setCreatingKey(false);
    }
  };

  const handleRevokeApiKey = async (keyId: string) => {
    if (!workspaceId || revokingKeyId) return;
    setRevokingKeyId(keyId);
    try {
      const res = await fetchWithAuth(`/api/workspaces/${workspaceId}/api-keys/${keyId}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error("Failed to revoke API key");
      toast.success("API key revoked");
      mutateApiKeys();
    } catch (e: any) {
      friendlyToast("Failed to revoke API key", e);
    } finally {
      setRevokingKeyId(null);
    }
  };

  // Enterprise IP Allowlisting
  const { data: ipAllowlistData, mutate: mutateIpAllowlist, isLoading: loadingIpAllowlist } = useSWR(
    workspaceId ? `/api/workspaces/${workspaceId}/ip-allowlist` : null,
    fetcher
  );
  const [ipAllowlistEnabled, setIpAllowlistEnabled] = useState(false);
  const [allowedCidrs, setAllowedCidrs] = useState<string[]>([]);
  const [newCidrInput, setNewCidrInput] = useState("");
  const [savingIpAllowlist, setSavingIpAllowlist] = useState(false);

  useEffect(() => {
    if (ipAllowlistData) {
      setIpAllowlistEnabled(Boolean(ipAllowlistData.enabled));
      setAllowedCidrs(Array.isArray(ipAllowlistData.allowed_cidrs) ? ipAllowlistData.allowed_cidrs : []);
    }
  }, [ipAllowlistData]);

  const handleAddCidr = () => {
    const trimmed = newCidrInput.trim();
    if (!trimmed) return;
    const ipPattern = /^(\d{1,3}\.){3}\d{1,3}(\/([0-9]|[1-2][0-9]|3[0-2]))?$/;
    if (!ipPattern.test(trimmed)) {
      toast.error("Invalid IP or CIDR notation (e.g. 192.168.1.1 or 10.0.0.0/24)");
      return;
    }
    if (allowedCidrs.includes(trimmed)) {
      toast.error("This CIDR is already in your allowlist");
      return;
    }
    setAllowedCidrs([...allowedCidrs, trimmed]);
    setNewCidrInput("");
  };

  const handleRemoveCidr = (cidr: string) => {
    setAllowedCidrs(allowedCidrs.filter(c => c !== cidr));
  };

  const handleSaveIpAllowlist = async () => {
    if (!workspaceId || savingIpAllowlist) return;
    setSavingIpAllowlist(true);
    try {
      const res = await fetchWithAuth(`/api/workspaces/${workspaceId}/ip-allowlist`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          enabled: ipAllowlistEnabled,
          allowed_cidrs: allowedCidrs,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || "Failed to update IP allowlist");
      }
      toast.success("IP allowlist policies updated successfully");
      mutateIpAllowlist();
    } catch (e: any) {
      friendlyToast("Failed to save IP allowlist", e);
    } finally {
      setSavingIpAllowlist(false);
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
                  <h3 className="text-sm font-bold text-foreground">
                    Growth Pro Feature: Mandatory Workspace-wide 2FA Enforcement
                  </h3>
                  <span className="text-[10px] font-extrabold uppercase px-2 py-0.5 bg-amber-500/20 text-amber-600 dark:text-amber-400 rounded-full border border-amber-500/30">
                    Pro Gated
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-1 max-w-xl leading-relaxed">
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
                disabled={saving || showConfirm || !isAuthorized}
                title={!isAuthorized ? "Only workspace owners and administrators can configure 2FA enforcement." : undefined}
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
                {require2fa ? 'SECURED' : is2faLocked ? 'PRO GATED' : !isAuthorized ? 'READ ONLY' : 'UNSECURED'}
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
              onClick={(e) => {
                if (e.target === e.currentTarget && !saving) {
                  setShowConfirm(false);
                  setConfirmCountdown(0);
                }
              }}
            >
              <motion.div
                role="dialog"
                aria-modal="true"
                aria-labelledby="enforce-2fa-title"
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
                  <h2 id="enforce-2fa-title" className="text-2xl font-bold tracking-tight text-foreground">Enforce Security</h2>
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

      {/* Session Inactivity Idle Timeout & Device Security Policy */}
      <div className="p-6 md:p-8 rounded-xl border border-border bg-card shadow-sm space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-border">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-primary/10 text-primary rounded-xl">
              <Clock size={22} />
            </div>
            <div>
              <h3 className="text-base font-bold text-foreground flex items-center gap-2">
                Session Inactivity Idle Timeout Policy
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-primary/10 text-primary">
                  Governance
                </span>
              </h3>
              <p className="text-xs text-muted-foreground mt-0.5">
                Automatically invalidate unattended sessions across all team member devices after inactivity.
              </p>
            </div>
          </div>
          {savingTimeout && (
            <div className="flex items-center gap-1.5 text-xs text-primary font-medium">
              <Loader2 size={13} className="animate-spin" />
              <span>Saving policy...</span>
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {/* Timeout Duration Selector */}
          <div className="p-4 rounded-xl border border-border bg-muted/20 space-y-2">
            <label className="text-xs font-bold text-foreground block">
              Inactivity Idle Timeout Threshold
            </label>
            <select
              value={idleTimeoutMinutes}
              disabled={!isAuthorized || savingTimeout}
              onChange={(e) => handleUpdateTimeout(parseInt(e.target.value, 10))}
              className="w-full px-3 py-2 bg-background border border-border rounded-xl text-xs font-semibold text-foreground focus:ring-2 focus:ring-primary/20 outline-none"
            >
              <option value={15}>15 Minutes (Strict Security / Compliance)</option>
              <option value={30}>30 Minutes (Elevated Security)</option>
              <option value={60}>1 Hour (Recommended Standard)</option>
              <option value={240}>4 Hours (Half Workday)</option>
              <option value={480}>8 Hours (Full Workday)</option>
              <option value={1440}>24 Hours (Relaxed Session)</option>
              <option value={10080}>7 Days (Persistent Workstation)</option>
            </select>
            <p className="text-[11px] text-muted-foreground leading-relaxed">
              When inactive for this duration, workstations must re-authenticate before executing campaigns or viewing leads.
            </p>
          </div>

          {/* Device Fingerprint Binding Toggle */}
          <div className="p-4 rounded-xl border border-border bg-muted/20 flex flex-col justify-between space-y-2">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-xs font-bold text-foreground block">Hardware Fingerprint Binding</span>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  Terminates sessions immediately if browser fingerprint or user agent changes mid-session.
                </p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={enforceDeviceFingerprint}
                disabled={!isAuthorized || savingTimeout}
                onClick={() => handleUpdateTimeout(idleTimeoutMinutes, !enforceDeviceFingerprint)}
                className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border border-border transition-colors duration-200 ${
                  enforceDeviceFingerprint ? "bg-primary border-primary" : "bg-muted"
                }`}
              >
                <span
                  className={`pointer-events-none inline-block h-3.5 w-3.5 transform rounded-full bg-background shadow-xs transition duration-200 ${
                    enforceDeviceFingerprint ? "translate-x-4" : "translate-x-0.5"
                  }`}
                />
              </button>
            </div>
            <div className="text-[10px] text-muted-foreground pt-1 border-t border-border/40 flex items-center gap-1.5">
              <ShieldCheck size={12} className="text-emerald-500" />
              <span>Protects against session token hijacking and man-in-the-middle attacks.</span>
            </div>
          </div>
        </div>
      </div>

      {/* Active Device Sessions & Revocation Center */}
      <div className="p-6 md:p-8 rounded-xl border border-border bg-card shadow-sm space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-border">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-primary/10 text-primary rounded-xl">
              <Laptop size={22} />
            </div>
            <div>
              <h3 className="text-base font-bold text-foreground flex items-center gap-2">
                Active Device Sessions & Devices
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-primary/10 text-primary">
                  {sessionsData?.sessions?.length || 1} Active
                </span>
              </h3>
              <p className="text-xs text-muted-foreground mt-0.5">
                Manage authenticated sessions across web browsers and workstations.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => mutateSessions()}
              className="p-2 hover:bg-muted text-muted-foreground rounded-lg transition-colors cursor-pointer"
              title="Refresh sessions"
            >
              <RefreshCw size={15} />
            </button>
            <button
              type="button"
              onClick={handleRevokeAllOtherSessions}
              disabled={revokingAllSessions || !sessionsData?.sessions || sessionsData.sessions.length <= 1}
              className="px-3.5 py-1.5 bg-destructive/10 hover:bg-destructive/20 text-destructive text-xs font-semibold rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer flex items-center gap-1.5"
            >
              {revokingAllSessions ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
              Revoke All Other Sessions
            </button>
          </div>
        </div>

        {/* Sessions List */}
        <div className="space-y-3">
          {loadingSessions ? (
            <div className="py-6 flex items-center justify-center text-muted-foreground gap-2 text-xs">
              <Loader2 size={16} className="animate-spin" />
              Scanning active session endpoints...
            </div>
          ) : !sessionsData?.sessions || sessionsData.sessions.length === 0 ? (
            <div className="p-4 rounded-xl border border-border bg-muted/20 text-center text-xs text-muted-foreground">
              No remote sessions detected. Current session is authenticated.
            </div>
          ) : (
            sessionsData.sessions.map((sess: any) => (
              <div 
                key={sess.id}
                className="p-4 rounded-xl border border-border bg-muted/30 flex flex-col sm:flex-row sm:items-center justify-between gap-4"
              >
                <div className="flex items-start sm:items-center gap-3.5">
                  <div className="p-2.5 bg-background rounded-lg text-foreground border border-border shrink-0">
                    {sess.os?.toLowerCase().includes("ios") || sess.os?.toLowerCase().includes("android") ? (
                      <Smartphone size={18} />
                    ) : (
                      <Laptop size={18} />
                    )}
                  </div>
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-bold text-foreground">
                        {sess.browser || "Unknown Browser"} on {sess.os || "Desktop Device"}
                      </span>
                      {sess.is_current && (
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 border border-emerald-500/20">
                          Current Session
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 text-xs text-muted-foreground mt-1 flex-wrap">
                      <span>IP: {sess.ip_address || "Local Session"}</span>
                      <span>•</span>
                      <span>{sess.location || "Authenticated Region"}</span>
                      <span>•</span>
                      <span>Last seen: {new Date(sess.last_active || Date.now()).toLocaleTimeString()}</span>
                    </div>
                  </div>
                </div>

                {!sess.is_current && (
                  <button
                    type="button"
                    onClick={() => handleRevokeSession(sess.id)}
                    disabled={revokingSessionId === sess.id}
                    className="self-end sm:self-auto px-3 py-1 bg-destructive/10 hover:bg-destructive/20 text-destructive text-xs font-semibold rounded-lg transition-colors cursor-pointer flex items-center gap-1"
                  >
                    {revokingSessionId === sess.id ? <Loader2 size={12} className="animate-spin" /> : null}
                    Revoke
                  </button>
                )}
              </div>
            ))
          )}
        </div>
      </div>

      {/* Developer API Keys Center */}
      <div className="p-6 md:p-8 rounded-xl border border-border bg-card shadow-sm space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-border">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-primary/10 text-primary rounded-xl">
              <Key size={22} />
            </div>
            <div>
              <h3 className="text-base font-bold text-foreground flex items-center gap-2">
                Workspace Developer API Keys
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-primary/10 text-primary">
                  REST v1
                </span>
              </h3>
              <p className="text-xs text-muted-foreground mt-0.5">
                Programmatic API keys for webhooks, automation scripts, and custom CRM integrations.
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={() => setShowCreateKeyModal(true)}
            className="px-4 py-2 bg-primary text-primary-foreground text-xs font-semibold rounded-xl hover:bg-primary/90 transition-colors cursor-pointer flex items-center gap-1.5 shadow-sm"
          >
            <Plus size={14} />
            Create API Key
          </button>
        </div>

        {/* API Keys Table */}
        <div className="space-y-3">
          {loadingApiKeys ? (
            <div className="py-6 flex items-center justify-center text-muted-foreground gap-2 text-xs">
              <Loader2 size={16} className="animate-spin" />
              Loading developer keys...
            </div>
          ) : !apiKeysData?.api_keys || apiKeysData.api_keys.length === 0 ? (
            <div className="p-8 rounded-xl border border-border bg-muted/20 text-center">
              <Key size={24} className="mx-auto text-muted-foreground mb-2" />
              <p className="text-sm font-semibold text-foreground">No Developer API Keys Created</p>
              <p className="text-xs text-muted-foreground mt-1 max-w-sm mx-auto">
                Generate a scoped API key to authenticate custom integrations and sync leads directly.
              </p>
            </div>
          ) : (
            apiKeysData.api_keys.map((k: any) => (
              <div 
                key={k.id}
                className="p-4 rounded-xl border border-border bg-muted/30 flex flex-col sm:flex-row sm:items-center justify-between gap-4"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold text-foreground">{k.name}</span>
                    <span className="font-mono text-xs px-2 py-0.5 rounded-md bg-background border border-border text-muted-foreground">
                      {k.prefix || "sk_live_"}...
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 mt-2 flex-wrap">
                    {(k.scopes || []).map((scope: string) => (
                      <span 
                        key={scope} 
                        className="text-[10px] font-mono px-2 py-0.5 rounded bg-primary/10 text-primary border border-primary/20"
                      >
                        {scope}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="flex items-center gap-4 self-end sm:self-auto">
                  <div className="text-right text-[11px] text-muted-foreground">
                    <div>Created {new Date(k.created_at).toLocaleDateString()}</div>
                    {k.last_used_at ? (
                      <div>Used {new Date(k.last_used_at).toLocaleDateString()}</div>
                    ) : (
                      <span className="text-amber-500 font-medium">Never used</span>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => handleRevokeApiKey(k.id)}
                    disabled={revokingKeyId === k.id}
                    className="p-2 hover:bg-destructive/10 text-destructive rounded-lg transition-colors cursor-pointer"
                    title="Revoke API key"
                  >
                    {revokingKeyId === k.id ? <Loader2 size={15} className="animate-spin" /> : <Trash2 size={15} />}
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Enterprise IP & Network Allowlisting */}
      <div className="p-6 md:p-8 rounded-xl border border-border bg-card shadow-sm space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4 pb-4 border-b border-border">
          <div className="flex items-start gap-3">
            <div className="p-2.5 bg-primary/10 text-primary rounded-xl mt-0.5">
              <Globe size={22} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-bold text-foreground">
                  Enterprise IP & Network Allowlisting
                </h3>
                <span className="text-[10px] font-extrabold uppercase px-2 py-0.5 bg-amber-500/20 text-amber-600 dark:text-amber-400 rounded-full border border-amber-500/30">
                  Enterprise
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                Restrict workspace actions, campaign edits, and export requests strictly to approved corporate IP CIDR ranges.
              </p>
            </div>
          </div>

          <button
            type="button"
            role="switch"
            aria-checked={ipAllowlistEnabled}
            onClick={() => setIpAllowlistEnabled(!ipAllowlistEnabled)}
            className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-hidden ${
              ipAllowlistEnabled ? "bg-primary" : "bg-muted"
            }`}
          >
            <span
              className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                ipAllowlistEnabled ? "translate-x-5" : "translate-x-0"
              }`}
            />
          </button>
        </div>

        {ipAllowlistEnabled && (
          <div className="space-y-4">
            <div className="flex gap-2">
              <input
                type="text"
                placeholder="Enter IP or CIDR (e.g. 198.51.100.0/24 or 203.0.113.1)"
                value={newCidrInput}
                onChange={(e) => setNewCidrInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleAddCidr(); }}
                className="flex-1 px-4 py-2 bg-background border border-border rounded-xl text-xs font-mono text-foreground focus:outline-hidden focus:ring-2 focus:ring-primary/20"
              />
              <button
                type="button"
                onClick={handleAddCidr}
                className="px-4 py-2 bg-muted hover:bg-muted/80 text-foreground text-xs font-semibold rounded-xl transition-colors cursor-pointer"
              >
                Add CIDR
              </button>
            </div>

            {/* Allowed CIDRs Badges */}
            <div className="flex flex-wrap gap-2 pt-2">
              {allowedCidrs.length === 0 ? (
                <p className="text-xs text-amber-600 flex items-center gap-1.5">
                  <AlertTriangle size={13} />
                  No CIDR rules defined. Allowlist enforcement will take effect once at least one CIDR is specified.
                </p>
              ) : (
                allowedCidrs.map((cidr) => (
                  <span
                    key={cidr}
                    className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-muted text-xs font-mono text-foreground border border-border"
                  >
                    {cidr}
                    <button
                      type="button"
                      onClick={() => handleRemoveCidr(cidr)}
                      className="text-muted-foreground hover:text-destructive cursor-pointer"
                    >
                      <X size={13} />
                    </button>
                  </span>
                ))
              )}
            </div>

            <div className="pt-2 flex justify-end">
              <button
                type="button"
                onClick={handleSaveIpAllowlist}
                disabled={savingIpAllowlist}
                className="px-5 py-2 bg-primary text-primary-foreground text-xs font-semibold rounded-xl hover:bg-primary/90 transition-colors disabled:opacity-40 cursor-pointer flex items-center gap-2"
              >
                {savingIpAllowlist ? <Loader2 size={14} className="animate-spin" /> : null}
                Save IP Allowlist Policies
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Create Key Modal */}
      <AnimatePresence>
        {showCreateKeyModal && (
          <div className="fixed inset-0 z-50 bg-background/80 flex items-center justify-center p-4 backdrop-blur-xs">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="bg-card border border-border shadow-2xl rounded-2xl w-full max-w-lg p-6 space-y-5 text-foreground"
            >
              <div className="flex items-center justify-between">
                <h3 className="text-base font-bold text-foreground flex items-center gap-2">
                  <Key size={18} className="text-primary" />
                  Generate Developer API Key
                </h3>
                <button
                  type="button"
                  onClick={() => { setShowCreateKeyModal(false); setCreatedKeySecret(null); }}
                  className="text-muted-foreground hover:text-foreground cursor-pointer"
                >
                  <X size={18} />
                </button>
              </div>

              {createdKeySecret ? (
                <div className="space-y-4">
                  <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-700 dark:text-amber-400 text-xs leading-relaxed space-y-1">
                    <div className="font-bold flex items-center gap-1.5">
                      <AlertTriangle size={14} />
                      Save your secret key immediately
                    </div>
                    <p>
                      For security reasons, this token will never be displayed again. If you lose this key, you will need to revoke it and generate a new one.
                    </p>
                  </div>

                  <div className="p-3 bg-muted rounded-xl border border-border flex items-center justify-between gap-3">
                    <span className="font-mono text-xs break-all text-foreground select-all font-semibold">
                      {createdKeySecret}
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        navigator.clipboard.writeText(createdKeySecret);
                        setCopiedKey(true);
                        setTimeout(() => setCopiedKey(false), 2000);
                        toast.success("API key copied to clipboard");
                      }}
                      className="px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-xs font-semibold shrink-0 cursor-pointer flex items-center gap-1"
                    >
                      {copiedKey ? <Check size={13} /> : <Copy size={13} />}
                      {copiedKey ? "Copied" : "Copy"}
                    </button>
                  </div>

                  <button
                    type="button"
                    onClick={() => { setShowCreateKeyModal(false); setCreatedKeySecret(null); }}
                    className="w-full py-2.5 bg-muted text-foreground text-xs font-semibold rounded-xl hover:bg-muted/80 transition-colors cursor-pointer"
                  >
                    Done
                  </button>
                </div>
              ) : (
                <div className="space-y-4">
                  <div>
                    <label className="text-xs font-bold text-foreground block mb-1.5">
                      Key Name / Purpose
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. Zapier Production Sync or Custom Webhook Dispatcher"
                      value={newKeyName}
                      onChange={(e) => setNewKeyName(e.target.value)}
                      className="w-full px-3.5 py-2.5 bg-background border border-border rounded-xl text-xs text-foreground focus:outline-hidden focus:ring-2 focus:ring-primary/20"
                    />
                  </div>

                  <div>
                    <label className="text-xs font-bold text-foreground block mb-2">
                      Permissions & Scopes
                    </label>
                    <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                      {AVAILABLE_SCOPES.map((sc) => (
                        <label 
                          key={sc.id}
                          className="flex items-start gap-2.5 p-2 rounded-lg hover:bg-muted/50 cursor-pointer"
                        >
                          <input
                            type="checkbox"
                            checked={newKeyScopes.includes(sc.id)}
                            onChange={(e) => {
                              if (e.target.checked) {
                                setNewKeyScopes([...newKeyScopes, sc.id]);
                              } else {
                                setNewKeyScopes(newKeyScopes.filter(s => s !== sc.id));
                              }
                            }}
                            className="mt-0.5 rounded border-border text-primary focus:ring-primary"
                          />
                          <div>
                            <span className="text-xs font-bold text-foreground block">{sc.label}</span>
                            <span className="text-[11px] text-muted-foreground">{sc.desc}</span>
                          </div>
                        </label>
                      ))}
                    </div>
                  </div>

                  <div className="pt-2 flex justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => setShowCreateKeyModal(false)}
                      className="px-4 py-2 bg-muted text-muted-foreground text-xs font-semibold rounded-xl hover:bg-muted/80 hover:text-foreground cursor-pointer"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={handleCreateApiKey}
                      disabled={!newKeyName.trim() || creatingKey}
                      className="px-5 py-2 bg-primary text-primary-foreground text-xs font-semibold rounded-xl hover:bg-primary/90 transition-colors disabled:opacity-40 cursor-pointer flex items-center gap-1.5"
                    >
                      {creatingKey ? <Loader2 size={13} className="animate-spin" /> : null}
                      Generate Key
                    </button>
                  </div>
                </div>
              )}
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
