import useSWR from "swr";
import { useState, useEffect } from "react";
import { 
  Info, Loader2, Save, Check, Clock, Hash, AlertTriangle,
  Globe, Palette, Image as ImageIcon, ShieldCheck, Lock, Sparkles, RefreshCw, ExternalLink 
} from "lucide-react";
import { toast } from "sonner";
import { friendlyToast } from "../../components/FriendlyError";
import { useWorkspaceData } from "./useWorkspaceData";
import { motion, AnimatePresence } from "motion/react";
import { format } from "date-fns";
import { fetcher, fetchWithAuth } from "@/lib/apiClient";
import { useWorkspace } from "../../contexts/WorkspaceContext";
import { SettingsLoadingSkeleton } from "@/components/SettingsLoadingSkeleton";
import { EmptyState } from "@/components/EmptyState";
import { usePaywall } from "../../contexts/PaywallContext";

const getGradient = (name: string) => {
  if (!name) return "from-muted to-muted-foreground";
  const hash = Array.from(name).reduce((acc, char) => acc + char.charCodeAt(0), 0);
  const gradients = [
    "from-primary to-primary/80",
    "from-primary to-primary/60",
    "from-primary/80 to-primary",
    "from-success to-success/80",
    "from-destructive to-destructive/80",
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
  const { openPaywall } = usePaywall();
  
  // Workspace Identity state
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [savedSuccess, setSavedSuccess] = useState(false);
  const [lastSaved, setLastSaved] = useState<Date | null>(null);

  // Agency White-Label & Custom Branding SWR
  const { data: branding, mutate: mutateBranding, isLoading: isBrandingLoading } = useSWR<{
    logo_url?: string | null;
    favicon_url?: string | null;
    primary_color?: string | null;
    custom_domain?: string | null;
    custom_domain_status?: string;
    hide_watermark?: boolean;
    cname_target?: string;
    tier?: string;
    can_custom_branding?: boolean;
    can_custom_domain?: boolean;
    can_remove_watermark?: boolean;
  }>(workspaceId ? `/api/workspaces/${workspaceId}/branding` : null, fetcher);

  const [logoUrl, setLogoUrl] = useState("");
  const [faviconUrl, setFaviconUrl] = useState("");
  const [primaryColor, setPrimaryColor] = useState("#4F46E5");
  const [customDomain, setCustomDomain] = useState("");
  const [hideWatermark, setHideWatermark] = useState(false);

  const [savingBranding, setSavingBranding] = useState(false);
  const [savedBrandingSuccess, setSavedBrandingSuccess] = useState(false);
  const [verifyingDomain, setVerifyingDomain] = useState(false);

  const isBrandingLocked = Boolean(branding && !branding.can_custom_branding);
  const isDomainLocked = Boolean(branding && !branding.can_custom_domain);
  const isWatermarkLocked = Boolean(branding && !branding.can_remove_watermark);
  const isWhiteLabelLocked = isBrandingLocked || isDomainLocked;

  const serverName = data?.name || "";
  const hasChanges = data?.name !== undefined && name !== data.name;
  const isTooLong = name.length > 50;
  const isEmpty = name.trim().length === 0;

  useEffect(() => {
    if (data?.name && !saving) {
      setName(data.name);
    }
  }, [data?.name, saving]);

  useEffect(() => {
    if (branding && !savingBranding) {
      setLogoUrl(branding.logo_url || "");
      setFaviconUrl(branding.favicon_url || "");
      setPrimaryColor(branding.primary_color || "#4F46E5");
      setCustomDomain(branding.custom_domain || "");
      setHideWatermark(Boolean(branding.hide_watermark));
    }
  }, [branding, savingBranding]);

  const hasBrandingChanges = branding !== undefined && (
    logoUrl !== (branding.logo_url || "") ||
    faviconUrl !== (branding.favicon_url || "") ||
    primaryColor !== (branding.primary_color || "#4F46E5") ||
    customDomain !== (branding.custom_domain || "") ||
    hideWatermark !== Boolean(branding.hide_watermark)
  );

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
      friendlyToast('Failed to save workspace profile — please try again.', e);
    } finally {
      setSaving(false);
    }
  };

  const handleSaveBranding = async () => {
    if (!workspaceId || savingBranding) return;
    if (isWhiteLabelLocked) {
      openPaywall({ featureName: "Agency White-Label Branding & Custom CNAME Domains" });
      return;
    }

    setSavingBranding(true);
    setSavedBrandingSuccess(false);

    try {
      const res = await fetchWithAuth(`/api/workspaces/${workspaceId}/branding`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          logo_url: logoUrl.trim() || null,
          favicon_url: faviconUrl.trim() || null,
          primary_color: primaryColor.trim() || "#4F46E5",
          custom_domain: customDomain.trim() || null,
          hide_watermark: hideWatermark,
        }),
      });

      if (!res.ok) {
        if (res.status === 402 || res.status === 403) {
          openPaywall({ featureName: "Agency White-Label Branding & Custom CNAME Domains" });
          return;
        }
        const errText = await res.text();
        throw new Error(errText || "Failed to update branding settings");
      }

      await mutateBranding();
      setSavedBrandingSuccess(true);
      toast.success("Agency branding updated successfully!");
      setTimeout(() => setSavedBrandingSuccess(false), 2500);
    } catch (e: any) {
      friendlyToast("Failed to save branding profile — please try again.", e);
    } finally {
      setSavingBranding(false);
    }
  };

  const handleVerifyDomain = async () => {
    if (!workspaceId || verifyingDomain) return;
    if (isDomainLocked) {
      openPaywall({ featureName: "Custom CNAME Domain Routing" });
      return;
    }
    if (!customDomain.trim()) {
      toast.info("Please enter a custom domain first before verifying DNS.");
      return;
    }

    setVerifyingDomain(true);
    try {
      const res = await fetchWithAuth(`/api/workspaces/${workspaceId}/branding/verify-domain`, {
        method: "POST",
      });
      if (!res.ok) {
        if (res.status === 402 || res.status === 403) {
          openPaywall({ featureName: "Custom CNAME Domain Routing" });
          return;
        }
        const errText = await res.text();
        throw new Error(errText || "Domain verification failed");
      }
      const respData = await res.json();
      toast.success(respData.message || "Domain verified successfully!");
      await mutateBranding();
    } catch (e: any) {
      friendlyToast("DNS verification failed — please ensure CNAME is propagated.", e);
    } finally {
      setVerifyingDomain(false);
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
    <div className="space-y-8">
      {/* SECTION 1: Workspace Identity */}
      <motion.div
        animate={{
          borderColor: savedSuccess ? "var(--success, #00FF00)" : "var(--color-border, #262626)",
          boxShadow: savedSuccess ? "0 0 15px -3px rgba(16, 185, 129, 0.3)" : "0 0 0px 0px rgba(0,0,0,0)",
        }}
        transition={{ duration: 0.5, ease: "easeOut" }}
        className="rounded-xl"
      >
        <div className="p-8 rounded-xl border border-border/60 bg-card relative overflow-hidden shadow-sm">
          <div className="flex flex-col md:flex-row items-start md:items-center gap-6 mb-8">
            <div className={`w-24 h-24 rounded-full shadow-lg flex items-center justify-center text-3xl font-bold text-white bg-gradient-to-br ${getGradient(name || serverName)} transition-all duration-500`}>
              {getInitials(name || serverName)}
            </div>
            <div className="flex-1 space-y-2">
              <h2 className="text-2xl font-bold tracking-tight text-foreground">Workspace Identity</h2>
              <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
                <span className="flex items-center gap-1.5 bg-muted/40 px-2.5 py-1 rounded-md border border-border/50">
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
                      type="button"
                      onClick={() => setName(serverName)}
                      className="px-3 py-1.5 text-xs font-semibold hover:bg-primary/20 text-primary rounded-md transition-colors"
                      disabled={saving}
                    >
                      Discard
                    </button>
                    <button
                      type="button"
                      onClick={handleSave}
                      className="px-3 py-1.5 text-xs font-semibold bg-primary text-white rounded-md hover:bg-primary/90 transition-colors shadow-sm"
                      disabled={saving || isEmpty || isTooLong}
                    >
                      Save
                    </button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            <div className="space-y-3 relative group">
              <label className="text-sm font-semibold flex justify-between text-foreground">
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
                
                {/* Progress bar for char count */}
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

            <div className="flex items-start gap-4 p-5 bg-muted/20 border border-primary/20 rounded-xl shadow-sm">
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
                    <Check size={14} className="text-success" /> Last saved {format(lastSaved, "HH:mm")}
                  </span>
                ) : (
                  <span>Data synced with server</span>
                )}
              </div>
              
              <div className="w-full sm:w-auto relative group">
                <button
                  type="button"
                  onClick={handleSave}
                  disabled={!hasChanges || saving || isEmpty || isTooLong}
                  className="w-full sm:w-auto relative overflow-hidden flex items-center justify-center gap-2 px-8 py-3 bg-primary text-primary-foreground font-semibold rounded-lg hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:bg-muted disabled:text-muted-foreground disabled:cursor-not-allowed shadow-md cursor-pointer"
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
                
                {!hasChanges && !saving && (
                  <div className="absolute -top-10 left-1/2 -translate-x-1/2 px-3 py-1.5 bg-popover text-popover-foreground text-xs rounded-md opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap border border-border shadow-md">
                    No changes to save
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </motion.div>

      {/* SECTION 2: In-Situ Pay Ramp Banner for Agency White-Label & Custom CNAME Domains */}
      {isWhiteLabelLocked && (
        <div className="p-5 rounded-xl bg-gradient-to-r from-amber-500/10 via-amber-500/5 to-transparent border border-amber-500/20 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 shadow-sm">
          <div className="flex items-center gap-3.5">
            <div className="p-2.5 rounded-xl bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20 shrink-0">
              <Lock className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-foreground">Agency White-Label Branding & Custom CNAME Domains</h3>
                <span className="text-[10px] font-bold tracking-wider uppercase px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
                  Growth Pro+
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Eliminate all Ele-in branding, use your own agency logo & colors across client views and reports, and map custom CNAME domains (e.g. outreach.youragency.com).
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => openPaywall({ featureName: "Agency White-Label Branding & Custom CNAME Domains" })}
            className="px-4 py-2 rounded-xl bg-amber-500 hover:bg-amber-600 text-white text-xs font-bold transition-all shadow-sm hover:shadow shrink-0 cursor-pointer flex items-center gap-1.5"
          >
            <Sparkles className="w-3.5 h-3.5" />
            Upgrade to Pro
          </button>
        </div>
      )}

      {/* SECTION 3: Agency White-Label & Custom Branding */}
      <div className="p-8 rounded-xl border border-border/60 bg-card relative overflow-hidden shadow-sm space-y-8">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 pb-6 border-b border-border/50">
          <div className="space-y-1">
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-xl bg-primary/10 text-primary border border-primary/20">
                <Globe className="w-5 h-5" />
              </div>
              <h2 className="text-xl font-bold tracking-tight text-foreground">White-Label & Custom CNAME</h2>
              {isWhiteLabelLocked && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
                  <Lock className="w-2.5 h-2.5" />
                  PRO
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              Customize portal visuals, client PDF reports, and custom outbound link tracking hostnames.
            </p>
          </div>

          {/* Live Status indicator */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-muted/40 border border-border/50 text-xs">
            <span className={`w-2 h-2 rounded-full ${
              branding?.custom_domain_status === 'active' ? 'bg-emerald-500 animate-pulse' :
              branding?.custom_domain_status === 'pending' ? 'bg-amber-500' : 'bg-muted-foreground/40'
            }`} />
            <span className="font-medium text-foreground">
              {branding?.custom_domain_status === 'active' ? 'Custom Domain SSL Active' :
               branding?.custom_domain_status === 'pending' ? 'DNS Propagation Pending' : 'Default Ele-in Domain'}
            </span>
          </div>
        </div>

        {/* Live Client Portal & Deliverable Preview */}
        <div className="p-5 rounded-xl bg-muted/20 border border-border/50 space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
              <Palette className="w-3.5 h-3.5 text-primary" /> Live Deliverable Preview
            </h4>
            <span className="text-[11px] text-muted-foreground font-mono">
              https://{customDomain.trim() || 'outreach.ele-in.com'}
            </span>
          </div>

          <div className="p-4 rounded-xl bg-background border border-border/60 shadow-xs flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              {logoUrl.trim() ? (
                <img
                  src={logoUrl.trim()}
                  alt="Agency Logo Preview"
                  className="w-10 h-10 rounded-xl object-contain border border-border/40 p-1 bg-card"
                  onError={(e) => {
                    // Fallback to placeholder on broken image
                    (e.target as HTMLElement).style.display = 'none';
                  }}
                />
              ) : (
                <div 
                  className="w-10 h-10 rounded-xl flex items-center justify-center font-bold text-sm text-white shadow-xs"
                  style={{ backgroundColor: primaryColor }}
                >
                  {getInitials(name || serverName)}
                </div>
              )}
              <div>
                <p className="text-xs font-bold text-foreground">{name || serverName || "Your Agency"}</p>
                <p className="text-[11px] text-muted-foreground">Executive Outreach & Lead Intelligence</p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <div 
                className="px-2.5 py-1 rounded-md text-[11px] font-semibold text-white shadow-2xs"
                style={{ backgroundColor: primaryColor }}
              >
                Client View Active
              </div>
              <div className="text-[10px] px-2 py-1 rounded-md bg-muted text-muted-foreground border border-border/40">
                {hideWatermark ? "Watermark Removed" : "Powered by Ele-in"}
              </div>
            </div>
          </div>
        </div>

        {/* Branding Form Controls */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* 1. Logo URL */}
          <div className="space-y-2">
            <label className="text-xs font-bold text-foreground flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                <ImageIcon className="w-3.5 h-3.5 text-primary" /> Company Logo URL
              </span>
              {isBrandingLocked && (
                <span className="text-[10px] font-bold text-amber-600 dark:text-amber-400 flex items-center gap-0.5">
                  <Lock className="w-2.5 h-2.5" /> PRO
                </span>
              )}
            </label>
            <div className="relative">
              <input
                type="text"
                value={logoUrl}
                onChange={(e) => setLogoUrl(e.target.value)}
                onClick={() => {
                  if (isBrandingLocked) openPaywall({ featureName: "Custom Agency Logo & Branding" });
                }}
                disabled={isBrandingLocked}
                placeholder="https://youragency.com/logo.png"
                className="w-full bg-background border border-border/80 rounded-xl px-3.5 py-2.5 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-primary/50 disabled:opacity-60 disabled:cursor-not-allowed"
              />
            </div>
            <p className="text-[11px] text-muted-foreground">PNG or SVG with transparent background recommended.</p>
          </div>

          {/* 2. Favicon URL */}
          <div className="space-y-2">
            <label className="text-xs font-bold text-foreground flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                <Globe className="w-3.5 h-3.5 text-primary" /> Browser Favicon URL
              </span>
              {isBrandingLocked && (
                <span className="text-[10px] font-bold text-amber-600 dark:text-amber-400 flex items-center gap-0.5">
                  <Lock className="w-2.5 h-2.5" /> PRO
                </span>
              )}
            </label>
            <div className="relative">
              <input
                type="text"
                value={faviconUrl}
                onChange={(e) => setFaviconUrl(e.target.value)}
                onClick={() => {
                  if (isBrandingLocked) openPaywall({ featureName: "Custom Agency Favicon" });
                }}
                disabled={isBrandingLocked}
                placeholder="https://youragency.com/favicon.ico"
                className="w-full bg-background border border-border/80 rounded-xl px-3.5 py-2.5 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-primary/50 disabled:opacity-60 disabled:cursor-not-allowed"
              />
            </div>
            <p className="text-[11px] text-muted-foreground">Appears in browser tabs and client bookmark bars.</p>
          </div>

          {/* 3. Primary Brand Accent Color */}
          <div className="space-y-2">
            <label className="text-xs font-bold text-foreground flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                <Palette className="w-3.5 h-3.5 text-primary" /> Primary Accent Color
              </span>
              {isBrandingLocked && (
                <span className="text-[10px] font-bold text-amber-600 dark:text-amber-400 flex items-center gap-0.5">
                  <Lock className="w-2.5 h-2.5" /> PRO
                </span>
              )}
            </label>
            <div className="flex items-center gap-3">
              <div className="relative shrink-0">
                <input
                  type="color"
                  value={primaryColor}
                  onChange={(e) => setPrimaryColor(e.target.value)}
                  onClick={() => {
                    if (isBrandingLocked) openPaywall({ featureName: "Custom Brand Color Theming" });
                  }}
                  disabled={isBrandingLocked}
                  className="w-10 h-10 rounded-xl border border-border/80 cursor-pointer p-0.5 bg-background disabled:cursor-not-allowed"
                />
              </div>
              <input
                type="text"
                value={primaryColor}
                onChange={(e) => setPrimaryColor(e.target.value)}
                onClick={() => {
                  if (isBrandingLocked) openPaywall({ featureName: "Custom Brand Color Theming" });
                }}
                disabled={isBrandingLocked}
                placeholder="#4F46E5"
                className="flex-1 bg-background border border-border/80 rounded-xl px-3.5 py-2.5 text-xs font-mono text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-primary/50 disabled:opacity-60 disabled:cursor-not-allowed uppercase"
              />
            </div>
            <p className="text-[11px] text-muted-foreground">Controls primary buttons, active tab indicators, and chart gradients.</p>
          </div>

          {/* 4. Custom Domain CNAME */}
          <div className="space-y-2">
            <label className="text-xs font-bold text-foreground flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                <Globe className="w-3.5 h-3.5 text-primary" /> Custom Domain CNAME
              </span>
              {isDomainLocked && (
                <span className="text-[10px] font-bold text-amber-600 dark:text-amber-400 flex items-center gap-0.5">
                  <Lock className="w-2.5 h-2.5" /> PRO
                </span>
              )}
            </label>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={customDomain}
                onChange={(e) => setCustomDomain(e.target.value)}
                onClick={() => {
                  if (isDomainLocked) openPaywall({ featureName: "Custom CNAME Domain Routing" });
                }}
                disabled={isDomainLocked}
                placeholder="outreach.acmeagency.com"
                className="flex-1 bg-background border border-border/80 rounded-xl px-3.5 py-2.5 text-xs font-mono text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-primary/50 disabled:opacity-60 disabled:cursor-not-allowed"
              />
              <button
                type="button"
                onClick={handleVerifyDomain}
                disabled={isDomainLocked || verifyingDomain || !customDomain.trim()}
                className="px-3.5 py-2.5 rounded-xl bg-muted/60 hover:bg-muted border border-border/60 text-xs font-bold text-foreground flex items-center gap-1.5 transition-colors disabled:opacity-50 cursor-pointer shrink-0"
              >
                {verifyingDomain ? <Loader2 size={13} className="animate-spin text-primary" /> : <RefreshCw size={13} className="text-primary" />}
                <span>Verify DNS</span>
              </button>
            </div>
            <p className="text-[11px] text-muted-foreground">Map an agency subdomain pointing to Ele-in edge servers.</p>
          </div>
        </div>

        {/* DNS Configuration Helper Card */}
        <div className="p-4 rounded-xl bg-muted/30 border border-border/50 text-xs space-y-2.5">
          <div className="flex items-center justify-between">
            <span className="font-bold text-foreground flex items-center gap-1.5">
              <ShieldCheck size={14} className="text-primary" /> DNS Record Configuration Guide
            </span>
            <span className="text-[11px] font-mono text-muted-foreground">Automatic SSL (Let's Encrypt)</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 font-mono text-[11px]">
            <div className="p-2.5 rounded-lg bg-background border border-border/40">
              <span className="text-[10px] text-muted-foreground block uppercase font-sans">Type</span>
              <span className="font-bold text-foreground">CNAME</span>
            </div>
            <div className="p-2.5 rounded-lg bg-background border border-border/40">
              <span className="text-[10px] text-muted-foreground block uppercase font-sans">Host / Subdomain</span>
              <span className="font-bold text-foreground">{customDomain ? customDomain.split('.')[0] : 'outreach'}</span>
            </div>
            <div className="p-2.5 rounded-lg bg-background border border-border/40">
              <span className="text-[10px] text-muted-foreground block uppercase font-sans">Points to / Target</span>
              <span className="font-bold text-primary">cname.ele-in.com</span>
            </div>
          </div>
        </div>

        {/* 5. Watermark Removal Toggle */}
        <div className="p-4 rounded-xl border border-border/50 bg-background flex items-center justify-between gap-4">
          <div className="space-y-0.5">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-foreground">Remove "Powered by Ele-in" Watermark</span>
              {isWatermarkLocked && (
                <span className="inline-flex items-center gap-0.5 text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
                  <Lock className="w-2.5 h-2.5" />
                  PRO
                </span>
              )}
            </div>
            <p className="text-[11px] text-muted-foreground">
              Completely hides the Ele-in brand attribution in client dashboards, exported reports, and email tracking redirects.
            </p>
          </div>

          <button
            type="button"
            role="switch"
            aria-checked={hideWatermark}
            onClick={() => {
              if (isWatermarkLocked) {
                openPaywall({ featureName: "Remove 'Powered by Ele-in' Watermark" });
                return;
              }
              setHideWatermark(!hideWatermark);
            }}
            className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
              hideWatermark ? 'bg-primary' : 'bg-muted'
            } ${isWatermarkLocked ? 'opacity-70' : ''}`}
          >
            <span
              className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                hideWatermark ? 'translate-x-5' : 'translate-x-0'
              }`}
            />
          </button>
        </div>

        {/* Save Branding Action Bar */}
        <div className="pt-4 flex flex-col sm:flex-row items-center justify-between gap-4 border-t border-border/50">
          <div className="text-xs text-muted-foreground">
            {savedBrandingSuccess ? (
              <span className="flex items-center gap-1 text-success">
                <Check size={14} /> White-label settings saved & propagated!
              </span>
            ) : (
              <span>Changes take effect immediately across all client touchpoints</span>
            )}
          </div>

          <div className="flex items-center gap-3 w-full sm:w-auto">
            {hasBrandingChanges && (
              <button
                type="button"
                onClick={() => {
                  if (branding) {
                    setLogoUrl(branding.logo_url || "");
                    setFaviconUrl(branding.favicon_url || "");
                    setPrimaryColor(branding.primary_color || "#4F46E5");
                    setCustomDomain(branding.custom_domain || "");
                    setHideWatermark(Boolean(branding.hide_watermark));
                  }
                }}
                disabled={savingBranding}
                className="px-4 py-2.5 text-xs font-semibold hover:bg-muted text-muted-foreground hover:text-foreground rounded-lg transition-colors cursor-pointer"
              >
                Discard
              </button>
            )}

            <button
              type="button"
              onClick={handleSaveBranding}
              disabled={(!hasBrandingChanges && !isWhiteLabelLocked) || savingBranding}
              className="w-full sm:w-auto flex items-center justify-center gap-2 px-6 py-2.5 bg-primary text-primary-foreground font-semibold text-xs rounded-xl hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm cursor-pointer"
            >
              {savingBranding ? (
                <>
                  <Loader2 size={14} className="animate-spin" /> Saving Branding...
                </>
              ) : savedBrandingSuccess ? (
                <>
                  <Check size={14} /> Saved!
                </>
              ) : isWhiteLabelLocked ? (
                <>
                  <Lock size={14} /> Unlock White-Labeling
                </>
              ) : (
                <>
                  <Save size={14} /> Save Branding Settings
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
