import { useState, useEffect, useMemo } from "react";
import { Bell, Lock, Smartphone, Mail, ShieldAlert, Activity, User } from "lucide-react";
import useSWR from "swr";
import { toast } from "sonner";
import { motion } from "motion/react";
import SpotlightCard from "@/components/SpotlightCard";
import { fetcher, fetchWithAuth } from "@/lib/apiClient";
import { SettingsLoadingSkeleton } from "@/components/SettingsLoadingSkeleton";
import { EmptyState } from "@/components/EmptyState";

const KNOWN_EVENT_TYPES = [
  { 
    id: "account_suspended", 
    label: "Account Suspended / Banned", 
    group: "critical", 
    desc: "Without this, you won't know when LinkedIn restricts an account.",
    recommended: { in_app: true, email: true }
  },
  { 
    id: "account_needs_attention", 
    label: "Account Needs Attention", 
    group: "critical", 
    desc: "If disabled, you'll miss rate-limit warnings and risk permanent bans.",
    recommended: { in_app: true, email: true }
  },
  { 
    id: "approval_queue_pending", 
    label: "Approval Queue Pending", 
    group: "activity", 
    desc: "Notifies you when messages need manual approval before sending.",
    recommended: { in_app: true, email: false }
  },
  { 
    id: "campaign_completed", 
    label: "Campaign Completed", 
    group: "activity", 
    desc: "Notifies you when a campaign finishes contacting all its leads.",
    recommended: { in_app: true, email: false }
  },
  { 
    id: "daily_digest", 
    label: "Daily Digest", 
    group: "activity", 
    desc: "Morning summary of your workspace's performance.",
    recommended: { in_app: false, email: true }
  },
];

function Toggle({
  enabled,
  locked,
  onClick,
}: {
  enabled: boolean;
  locked?: boolean;
  onClick: () => void;
}) {
  if (locked) {
    return (
      <div
        title="This alert cannot be disabled for your safety."
        className="flex items-center justify-center gap-1.5 w-[72px] h-6 rounded-full bg-success/10 text-success border border-success/20 font-bold text-[10px] uppercase tracking-wider cursor-not-allowed select-none"
      >
        <Lock size={10} /> ON
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors duration-300 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background ${
        enabled ? "bg-primary" : "bg-muted-foreground/30"
      }`}
    >
      <motion.span
        layout
        initial={false}
        animate={{
          x: enabled ? 20 : 0,
        }}
        transition={{ type: "spring", stiffness: 500, damping: 30 }}
        className="pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow-sm ring-0"
      />
    </button>
  );
}

export function NotificationSettings({ workspaceId }: { workspaceId: string | null }) {
  const { data, mutate, isLoading } = useSWR(
    workspaceId ? `/api/workspaces/${workspaceId}/notification-preferences` : null,
    fetcher
  );

  const [prefs, setPrefs] = useState<any[]>([]);

  useEffect(() => {
    if (data?.preferences) {
      setPrefs(data.preferences);
    }
  }, [data]);

  const displayEventTypes = useMemo(() => {
    if (!data?.preferences) return KNOWN_EVENT_TYPES;
    
    const backendTypes = new Set(data.preferences.map((p: any) => p.event_type));
    const knownIds = new Set(KNOWN_EVENT_TYPES.map(e => e.id));
    
    // Find any unknown types from backend
    const unknownFromBackend = [...backendTypes]
      .filter(id => typeof id === 'string' && !knownIds.has(id))
      .map(id => ({
        id: id as string,
        label: (id as string).replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase()),
        desc: 'Notification from backend',
        group: 'activity' as const,
        recommended: { in_app: false, email: false }
      }));
    
    return [...KNOWN_EVENT_TYPES, ...unknownFromBackend];
  }, [data?.preferences]);

  const handleToggle = async (eventType: string, channel: string, currentEnabled: boolean) => {
    if (!workspaceId) return;
    
    // Paranoia Layer 2: physically enforce lock, double-check logic
    if (eventType === "account_suspended" && channel === "in_app") {
      toast.error("Critical safety alerts cannot be disabled.");
      return;
    }

    const newEnabled = !currentEnabled;
    
    // Optimistic update
    const updatedPrefs = prefs.map(p => 
      (p.event_type === eventType && p.channel === channel) 
        ? { ...p, enabled: newEnabled }
        : p
    );
    if (!updatedPrefs.some(p => p.event_type === eventType && p.channel === channel)) {
      updatedPrefs.push({ event_type: eventType, channel, enabled: newEnabled });
    }
    setPrefs(updatedPrefs);

    const updatePromise = fetchWithAuth(`/api/workspaces/${workspaceId}/notification-preferences`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event_type: eventType,
        channel: channel,
        enabled: !currentEnabled
      }),
    }).then(async (res) => {
      if (!res.ok) throw new Error(await res.text());
      mutate();
      return res;
    });

    toast.promise(updatePromise, {
      loading: 'Saving preference...',
      success: 'Preference updated successfully',
      error: (err) => {
        // Revert optimistic update on failure (Paranoia Layer 1)
        if (data?.preferences) {
          setPrefs(data.preferences);
        }
        mutate(); 
        return err.message || "Failed to save preference";
      }
    });
  };

  const getPref = (eventType: string, channel: string) => {
    // Paranoia Layer 1: Empty preferences default to false safely, except suspended in-app which defaults true physically.
    if (eventType === "account_suspended" && channel === "in_app") return true;
    return prefs.find((p) => p.event_type === eventType && p.channel === channel)?.enabled ?? false;
  };

  if (!workspaceId) {
    return <EmptyState title="No Workspace Selected" description="Please select a workspace to view notification settings." icon={Bell} />;
  }

  if (isLoading) {
    return <SettingsLoadingSkeleton />;
  }

  return (
    <div className="space-y-8 max-w-4xl">
      <SpotlightCard className="p-8 rounded-2xl border border-border/50 bg-surface/50 backdrop-blur-md relative overflow-hidden">
        <div className="flex items-center gap-4 mb-8">
          <div className="p-3 bg-primary/10 rounded-xl">
            <Bell className="text-primary" size={24} />
          </div>
          <div>
            <h2 className="text-2xl font-bold tracking-tight text-foreground">Notification Preferences</h2>
            <span className="inline-flex items-center gap-1 text-xs bg-muted/50 text-muted-foreground px-2 py-0.5 rounded-full font-medium mt-2 mb-1">
              <User size={10} /> Personal to you
            </span>
            <p className="text-sm text-muted-foreground mt-1">
              Your personal notification preferences for this workspace. Each team member configures these independently.
            </p>
          </div>
        </div>

      {/* Critical Alerts Section */}
      <div className="relative overflow-hidden rounded-2xl border border-primary/30 bg-warning/5 shadow-sm">
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-primary to-destructive" />
        <div className="p-6">
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 bg-primary/10 rounded-xl text-primary">
              <ShieldAlert size={24} />
            </div>
            <div>
              <h3 className="text-lg font-bold tracking-tight text-foreground">Critical Alerts</h3>
              <p className="text-sm text-muted-foreground mt-1">Safety alerts that protect your accounts and campaigns.</p>
            </div>
          </div>
          <motion.div layout className="space-y-3">
            {displayEventTypes.filter(e => e.group === "critical").map(evt => (
              <motion.div key={evt.id} layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                <EventRow 
                  evt={evt} 
                  getPref={getPref} 
                  handleToggle={handleToggle} 
                />
              </motion.div>
            ))}
          </motion.div>
        </div>
      </div>

      {/* Activity Updates Section */}
      <div className="relative overflow-hidden rounded-2xl border border-border/50 bg-surface shadow-sm">
        <div className="absolute top-0 bottom-0 left-0 w-1 bg-gradient-to-b from-primary to-primary/80" />
        <div className="p-6">
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 bg-primary/10 rounded-xl text-primary">
              <Activity size={24} />
            </div>
            <div>
              <h3 className="text-lg font-bold tracking-tight text-foreground">Activity Updates</h3>
              <p className="text-sm text-muted-foreground mt-1">Stay informed about your workspace's progress and results.</p>
            </div>
          </div>
          <motion.div layout className="space-y-3">
            {displayEventTypes.filter(e => e.group === "activity").map(evt => (
              <motion.div key={evt.id} layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                <EventRow 
                  evt={evt} 
                  getPref={getPref} 
                  handleToggle={handleToggle} 
                />
              </motion.div>
            ))}
          </motion.div>
        </div>
      </div>
      </SpotlightCard>
    </div>
  );
}

function EventRow({ 
  evt, 
  getPref, 
  handleToggle 
}: { 
  evt: typeof KNOWN_EVENT_TYPES[0], 
  getPref: (evt: string, ch: string) => boolean, 
  handleToggle: (evt: string, ch: string, enabled: boolean) => void 
}) {
  const inAppEnabled = getPref(evt.id, "in_app");
  const emailEnabled = getPref(evt.id, "email");
  const isLockedInApp = evt.id === "account_suspended";

  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between p-4 rounded-xl hover:bg-muted/30 transition-colors border border-transparent hover:border-border/50 group bg-background/50 sm:bg-transparent">
      <div className="flex-1 pr-6 mb-4 sm:mb-0">
        <h4 className="font-semibold text-foreground">{evt.label}</h4>
        <p className="text-sm text-muted-foreground mt-1 leading-relaxed">
          {evt.desc}
        </p>
      </div>
      
      <div className="flex items-center gap-6 bg-surface sm:bg-background/50 p-3 rounded-lg border border-border/40 shadow-sm sm:shadow-none">
        <div className="flex flex-col items-center gap-2 min-w-[72px]">
          <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <Smartphone size={14} /> In-App
          </div>
          <Toggle 
            enabled={inAppEnabled} 
            locked={isLockedInApp} 
            onClick={() => handleToggle(evt.id, "in_app", inAppEnabled)} 
          />
          <div className="h-4 flex items-center justify-center">
            {evt.recommended.in_app && !isLockedInApp && (
              <span className="text-[10px] text-muted-foreground/70 font-medium">Recommended</span>
            )}
          </div>
        </div>
        
        <div className="w-px h-12 bg-border/50" />
        
        <div className="flex flex-col items-center gap-2 min-w-[72px]">
          <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <Mail size={14} /> Email
          </div>
          <Toggle 
            enabled={emailEnabled} 
            onClick={() => handleToggle(evt.id, "email", emailEnabled)} 
          />
          <div className="h-4 flex items-center justify-center">
            {evt.recommended.email && (
              <span className="text-[10px] text-muted-foreground/70 font-medium">Recommended</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
