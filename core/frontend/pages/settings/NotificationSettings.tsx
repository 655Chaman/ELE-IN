import { useState, useEffect, useMemo } from "react";
import { 
  Bell, Lock, Smartphone, Mail, ShieldAlert, Activity, User, Zap, 
  Send, CheckCircle2, AlertTriangle, Loader2, Link2 
} from "lucide-react";
import useSWR from "swr";
import { toast } from "sonner";
import { friendlyToast } from "../../components/FriendlyError";
import { motion } from "motion/react";
import { fetcher, fetchWithAuth } from "@/lib/apiClient";
import { SettingsLoadingSkeleton } from "@/components/SettingsLoadingSkeleton";
import { EmptyState } from "@/components/EmptyState";
import { usePaywall } from "@/contexts/PaywallContext";
import { NotificationPrePermissionTeaser } from "@/components/notifications/NotificationPrePermissionTeaser";

export type EventTypeItem = {
  id: string;
  label: string;
  group: 'critical' | 'activity';
  desc: string;
  recommended: { in_app: boolean; email: boolean };
  isPro?: boolean;
};

const KNOWN_EVENT_TYPES: EventTypeItem[] = [
  { 
    id: "account_suspended", 
    label: "Account Suspended / Banned", 
    group: "critical", 
    desc: "Critical protection: alerts you immediately if LinkedIn restricts or suspends an account.",
    recommended: { in_app: true, email: true },
    isPro: false,
  },
  { 
    id: "account_needs_attention", 
    label: "Account Needs Attention", 
    group: "critical", 
    desc: "Alerts when an account hits rate ceilings, proxy disconnects, or manual activity is detected.",
    recommended: { in_app: true, email: true },
    isPro: false,
  },
  { 
    id: "campaign_anomaly", 
    label: "Campaign Anomaly & Health Spikes", 
    group: "critical", 
    desc: "Immediate warning if bounce rates spike or connection acceptance drops below safety thresholds.",
    recommended: { in_app: true, email: true },
    isPro: true,
  },
  { 
    id: "lead_replied_instant", 
    label: "Instant Prospect Reply Alerts", 
    group: "activity", 
    desc: "Real-time desktop push, synthesized audio chime, and email notification when a lead replies.",
    recommended: { in_app: true, email: true },
    isPro: false,
  },
  { 
    id: "approval_queue_pending", 
    label: "Approval Queue Pending", 
    group: "activity", 
    desc: "Notifies you when outgoing AI replies require operator approval before dispatch.",
    recommended: { in_app: true, email: false },
    isPro: false,
  },
  { 
    id: "campaign_completed", 
    label: "Campaign Completed", 
    group: "activity", 
    desc: "Notifies you when an outreach campaign finishes contacting all enrolled prospects.",
    recommended: { in_app: true, email: false },
    isPro: false,
  },
  { 
    id: "daily_digest", 
    label: "Morning Executive Digest", 
    group: "activity", 
    desc: "Consolidated morning summary of replies, sent messages, and booked meetings across accounts.",
    recommended: { in_app: false, email: true },
    isPro: true,
  },
];

function Toggle({
  enabled,
  locked,
  isProLocked,
  label,
  onClick,
}: {
  enabled: boolean;
  locked?: boolean;
  isProLocked?: boolean;
  label?: string;
  onClick: () => void;
}) {
  if (locked) {
    return (
      <div
        role="switch"
        aria-checked="true"
        aria-disabled="true"
        aria-label={label ? `${label} (Locked On)` : "Locked On"}
        title="This safety alert cannot be disabled."
        className="flex items-center justify-center gap-1 w-14 h-5 rounded-full bg-primary/10 text-primary border border-primary/20 font-semibold text-[10px] uppercase tracking-wider cursor-not-allowed select-none"
      >
        <Lock size={10} /> ON
      </div>
    );
  }

  return (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      aria-label={label || (enabled ? "Enabled" : "Disabled")}
      onClick={onClick}
      className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border border-border transition-colors duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
        enabled ? "bg-primary border-primary" : "bg-muted"
      }`}
    >
      <motion.span
        layout
        initial={false}
        animate={{
          x: enabled ? 16 : 2,
        }}
        transition={{ type: "spring", stiffness: 500, damping: 30 }}
        className="pointer-events-none inline-flex items-center justify-center h-3.5 w-3.5 rounded-full bg-background shadow-xs"
      >
        {isProLocked && !enabled && (
          <Lock size={8} className="text-muted-foreground" />
        )}
      </motion.span>
    </button>
  );
}

export function NotificationSettings({ workspaceId }: { workspaceId: string | null }) {
  const { data, mutate, isLoading } = useSWR(
    workspaceId ? `/api/workspaces/${workspaceId}/notification-preferences` : null,
    fetcher
  );
  const { data: webhooksData, mutate: mutateWebhooks } = useSWR(
    workspaceId ? `/api/workspaces/${workspaceId}/webhooks` : null,
    fetcher
  );
  const { data: billing } = useSWR<{ tier?: string; tier_limits?: { can_custom_notification_routing?: boolean } }>(
    workspaceId ? `/api/elein/workspaces/billing?workspace_id=${workspaceId}` : null,
    fetcher
  );
  const { openPaywall } = usePaywall();
  const isNotificationLocked = Boolean(billing && !billing.tier_limits?.can_custom_notification_routing);

  const [prefs, setPrefs] = useState<any[]>([]);
  const [inFlightKey, setInFlightKey] = useState<string | null>(null);

  // Webhook Test Bench & Alert Routing State
  const [webhookUrl, setWebhookUrl] = useState("");
  const [testingWebhook, setTestingWebhook] = useState(false);
  const [webhookTestResult, setWebhookTestResult] = useState<{
    success: boolean;
    statusCode?: number;
    latencyMs?: number;
    message?: string;
  } | null>(null);

  // Persistent Webhooks State
  const [slackUrl, setSlackUrl] = useState("");
  const [discordUrl, setDiscordUrl] = useState("");
  const [customWebhookUrl, setCustomWebhookUrl] = useState("");
  const [channelRouting, setChannelRouting] = useState<Record<string, Record<string, boolean>>>({
    account_suspended: { slack: true, discord: true, email: true },
    campaign_anomaly: { slack: true, discord: true, email: true },
    lead_replied_instant: { slack: true, discord: false, email: true },
    approval_queue_pending: { slack: true, discord: false, email: false },
    daily_digest: { slack: false, discord: false, email: true },
  });
  const [savingWebhooks, setSavingWebhooks] = useState(false);

  useEffect(() => {
    if (webhooksData) {
      setSlackUrl(webhooksData.slack_webhook_url || "");
      setDiscordUrl(webhooksData.discord_webhook_url || "");
      setCustomWebhookUrl(webhooksData.custom_webhook_url || "");
      if (webhooksData.channel_routing) {
        setChannelRouting(webhooksData.channel_routing);
      }
    }
  }, [webhooksData]);

  const handleSaveWebhooks = async () => {
    if (!workspaceId || savingWebhooks) return;
    setSavingWebhooks(true);
    try {
      const res = await fetchWithAuth(`/api/workspaces/${workspaceId}/webhooks`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          slack_webhook_url: slackUrl,
          discord_webhook_url: discordUrl,
          custom_webhook_url: customWebhookUrl,
          channel_routing: channelRouting,
        }),
      });
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText || "Failed to update webhook endpoints");
      }
      toast.success("Webhook endpoints & channel routing rules saved successfully!");
      mutateWebhooks();
    } catch (e: any) {
      friendlyToast("Failed to save webhooks", e);
    } finally {
      setSavingWebhooks(false);
    }
  };

  const handleTestSpecificWebhook = (targetUrl: string) => {
    if (!targetUrl.trim()) {
      toast.error("Please enter a valid webhook URL first.");
      return;
    }
    setWebhookUrl(targetUrl);
    // Trigger test
    handleTestWebhookWithUrl(targetUrl);
  };

  const handleTestWebhookWithUrl = async (urlToTest: string) => {
    if (!workspaceId || !urlToTest.trim() || testingWebhook) return;
    setTestingWebhook(true);
    setWebhookTestResult(null);
    try {
      const res = await fetchWithAuth(`/api/workspaces/${workspaceId}/notifications/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ webhook_url: urlToTest.trim() }),
      });
      const resData = await res.json().catch(() => ({}));
      if (res.ok && resData.status === "success") {
        setWebhookTestResult({
          success: true,
          statusCode: resData.status_code || 200,
          latencyMs: resData.latency_ms || 120,
          message: resData.message || "Webhook delivery verified successfully.",
        });
        toast.success("Webhook delivery verified successfully!");
      } else {
        setWebhookTestResult({
          success: false,
          statusCode: resData.status_code || res.status,
          message: resData.detail || resData.message || "Endpoint rejected test payload.",
        });
        toast.error("Webhook test delivery failed");
      }
    } catch (e: any) {
      setWebhookTestResult({
        success: false,
        message: e?.message || "Connection timed out or network error.",
      });
      friendlyToast("Webhook test failed", e);
    } finally {
      setTestingWebhook(false);
    }
  };

  const handleTestWebhook = () => {
    handleTestWebhookWithUrl(webhookUrl);
  };

  useEffect(() => {
    const rawPrefs = Array.isArray(data) ? data : data?.preferences;
    if (rawPrefs) {
      setPrefs(rawPrefs);
    }
  }, [data]);

  const displayEventTypes = useMemo(() => {
    const rawPrefs = Array.isArray(data) ? data : data?.preferences;
    if (!rawPrefs) return KNOWN_EVENT_TYPES;
    
    const backendTypes = new Set(rawPrefs.map((p: any) => p.event_type));
    const knownIds = new Set(KNOWN_EVENT_TYPES.map(e => e.id));
    
    // Find any unknown types from backend
    const unknownFromBackend = [...backendTypes]
      .filter(id => typeof id === 'string' && !knownIds.has(id))
      .map(id => ({
        id: id as string,
        label: (id as string).replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase()),
        desc: 'Notification from backend service',
        group: 'activity' as const,
        recommended: { in_app: false, email: false },
        isPro: false,
      }));
    
    return [...KNOWN_EVENT_TYPES, ...unknownFromBackend];
  }, [data]);

  const handleToggle = async (eventType: string, channel: string, currentEnabled: boolean) => {
    if (!workspaceId) return;
    
    // Paranoia Layer 1: Concurrency / debounce guard
    const flightKey = `${eventType}:${channel}`;
    if (inFlightKey === flightKey) return;

    // Paranoia Layer 2: physically enforce safety lock
    if (eventType === "account_suspended" && channel === "in_app") {
      toast.error("Critical safety alerts cannot be disabled.");
      return;
    }

    // Paranoia Layer 1: Pro-gated notifications interception
    const eventDef = displayEventTypes.find(e => e.id === eventType);
    if (eventDef?.isPro && isNotificationLocked && !currentEnabled) {
      openPaywall({ featureName: "Custom Notification Routing & Daily Digest" });
      return;
    }

    setInFlightKey(flightKey);
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
      if (!res.ok) {
        if (res.status === 402 || res.status === 403) {
          openPaywall({ featureName: "Custom Notification Routing & Daily Digest" });
          const rawPrefs = Array.isArray(data) ? data : data?.preferences;
          if (rawPrefs) setPrefs(rawPrefs);
          throw new Error("PRO_LOCKED");
        }
        throw new Error(await res.text());
      }
      mutate();
      return res;
    }).finally(() => {
      setInFlightKey(null);
    });

    toast.promise(updatePromise, {
      loading: 'Saving preference...',
      success: 'Preference updated successfully',
      error: (err) => {
        if (err?.message === "PRO_LOCKED") {
          return "Upgrade to Growth Pro to enable this notification.";
        }
        // Revert optimistic update on failure (Paranoia Layer 1)
        const rawPrefs = Array.isArray(data) ? data : data?.preferences;
        if (rawPrefs) {
          setPrefs(rawPrefs);
        }
        mutate(); 
        return "Failed to save preference — please try again.";
      }
    });
  };

  const getPref = (eventType: string, channel: string) => {
    // Paranoia Layer 1: Critical safety alerts cannot be disabled
    if (eventType === "account_suspended" && channel === "in_app") return true;

    const existing = prefs.find((p) => p.event_type === eventType && p.channel === channel);
    if (existing !== undefined) {
      return existing.enabled;
    }

    // Align with backend database schema DEFAULT true and recommended event settings
    const eventDef = displayEventTypes.find((e) => e.id === eventType);
    if (eventDef?.recommended) {
      return (eventDef.recommended as any)[channel] ?? true;
    }
    return true;
  };

  if (!workspaceId) {
    return <EmptyState title="No Workspace Selected" description="Please select a workspace to view notification settings." icon={Bell} />;
  }

  if (isLoading) {
    return <SettingsLoadingSkeleton />;
  }

  return (
    <div className="space-y-6 max-w-4xl text-foreground">
      <div className="p-6 rounded-xl border border-border bg-card shadow-xs">
        <div className="flex items-center gap-3.5 mb-6">
          <div className="p-2.5 bg-primary/10 rounded-xl text-primary border border-primary/20">
            <Bell size={20} />
          </div>
          <div>
            <h2 className="text-lg font-semibold tracking-tight text-foreground">Notification Preferences</h2>
            <div className="flex items-center gap-2 mt-1">
              <span className="inline-flex items-center gap-1 text-[10px] bg-muted text-muted-foreground px-2 py-0.5 rounded-full font-medium">
                <User size={10} /> Personal to you
              </span>
              <p className="text-xs text-muted-foreground">
                Configured independently per team member in this workspace.
              </p>
            </div>
          </div>
        </div>

        {/* High-Value Alert Teaser & Interactive Test Bench */}
        <div className="mb-6">
          <NotificationPrePermissionTeaser workspaceId={workspaceId} variant="compact" />
        </div>

        {/* In-Situ Pro Upgrade Banner (Minimal, token-aligned, zero gradient) */}
        {isNotificationLocked && (
          <div className="mb-6 p-4 rounded-xl bg-muted/30 border border-border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className="p-2 bg-primary/10 rounded-lg text-primary shrink-0 mt-0.5 border border-primary/20">
                <Lock size={16} />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-xs font-semibold text-foreground">
                    Growth Pro: Real-Time Lead Alerts & Executive Digest
                  </h3>
                  <span className="text-[9px] font-semibold uppercase px-1.5 py-0.5 bg-primary/10 text-primary rounded-full border border-primary/20">
                    Pro
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-0.5 max-w-xl leading-relaxed">
                  Upgrade to receive instant warm prospect reply alerts, campaign bounce anomaly triggers, and executive morning digest reports.
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => openPaywall({ featureName: "Custom Notification Routing & Daily Digest" })}
              className="px-3.5 py-1.5 bg-primary hover:bg-primary/90 text-primary-foreground rounded-lg text-xs font-medium shrink-0 flex items-center gap-1.5 transition-colors cursor-pointer shadow-xs"
            >
              <Zap size={12} className="fill-current" />
              Upgrade to Pro
            </button>
          </div>
        )}

        {/* Critical Alerts Section */}
        <div className="rounded-xl border border-border bg-card p-5 mb-5">
          <div className="flex items-center gap-2.5 mb-4">
            <div className="p-1.5 bg-primary/10 rounded-lg text-primary border border-primary/20">
              <ShieldAlert size={16} />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-foreground">Critical Alerts</h3>
              <p className="text-xs text-muted-foreground">Safety alerts that protect accounts and delivery health.</p>
            </div>
          </div>
          <div className="space-y-2">
            {displayEventTypes.filter(e => e.group === "critical").map(evt => (
              <EventRow 
                key={evt.id}
                evt={evt} 
                getPref={getPref} 
                handleToggle={handleToggle} 
                isNotificationLocked={isNotificationLocked}
              />
            ))}
          </div>
        </div>

        {/* Activity Updates Section */}
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center gap-2.5 mb-4">
            <div className="p-1.5 bg-primary/10 rounded-lg text-primary border border-primary/20">
              <Activity size={16} />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-foreground">Activity Updates</h3>
              <p className="text-xs text-muted-foreground">Inbound lead replies, completion milestones, and digests.</p>
            </div>
          </div>
          <div className="space-y-2">
            {displayEventTypes.filter(e => e.group === "activity").map(evt => (
              <EventRow 
                key={evt.id}
                evt={evt} 
                getPref={getPref} 
                handleToggle={handleToggle} 
                isNotificationLocked={isNotificationLocked}
              />
            ))}
          </div>
        </div>
      </div>

      {/* Real-time Multi-Channel Webhook & Live Test Station */}
      <div className="p-6 rounded-xl border border-border bg-card shadow-xs space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-border">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-foreground">
                Multi-Channel Real-time Alert Routing & Webhooks
              </h3>
              <span className="text-[9px] font-semibold uppercase px-1.5 py-0.5 bg-primary/10 text-primary rounded border border-primary/20">
                Persistent Dispatcher
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Stream prospect replies, campaign killswitch triggers, and account anomalies directly into Slack, Discord, or Zapier.
            </p>
          </div>
          <div className="flex items-center gap-2">
            {isNotificationLocked && (
              <button
                type="button"
                onClick={() => openPaywall({ featureName: "Multi-Channel Alert Dispatcher" })}
                className="px-3 py-1 bg-muted hover:bg-muted/80 text-foreground rounded-lg text-xs font-medium shrink-0 flex items-center gap-1.5 transition-colors self-start sm:self-auto cursor-pointer border border-border"
              >
                <Lock size={12} className="text-muted-foreground" />
                Unlock Multi-Channel
              </button>
            )}
            <button
              type="button"
              onClick={handleSaveWebhooks}
              disabled={savingWebhooks || isNotificationLocked}
              className="px-4 py-2 bg-primary text-primary-foreground font-semibold text-xs rounded-xl hover:bg-primary/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer flex items-center justify-center gap-1.5 shrink-0 shadow-xs"
            >
              {savingWebhooks ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle2 size={13} />}
              Save Webhook Integrations
            </button>
          </div>
        </div>

        {/* Webhook Endpoint Inputs */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Slack Webhook Input */}
          <div className="p-4 rounded-xl border border-border bg-muted/20 space-y-2.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-foreground">Slack Incoming Webhook</span>
                <span className="text-[9px] bg-primary/10 text-primary px-1.5 py-0.5 rounded font-medium border border-primary/20">Pro+</span>
              </div>
              {slackUrl && (
                <button
                  type="button"
                  onClick={() => handleTestSpecificWebhook(slackUrl)}
                  disabled={testingWebhook}
                  className="text-[11px] font-semibold text-primary hover:underline flex items-center gap-1 cursor-pointer"
                >
                  <Send size={11} /> Test Slack
                </button>
              )}
            </div>
            <div className="relative">
              <Link2 size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                type="url"
                placeholder="https://hooks.slack.com/services/T.../B.../..."
                value={slackUrl}
                onChange={(e) => setSlackUrl(e.target.value)}
                className="w-full bg-background border border-border rounded-xl pl-9 pr-3 py-2 text-xs font-mono text-foreground focus:outline-hidden focus:ring-2 focus:ring-primary/20"
              />
            </div>
            <p className="text-[10px] text-muted-foreground">Post instant notifications into your shared sales channel.</p>
          </div>

          {/* Discord Webhook Input */}
          <div className="p-4 rounded-xl border border-border bg-muted/20 space-y-2.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-foreground">Discord Webhook</span>
                <span className="text-[9px] bg-primary/10 text-primary px-1.5 py-0.5 rounded font-medium border border-primary/20">Pro+</span>
              </div>
              {discordUrl && (
                <button
                  type="button"
                  onClick={() => handleTestSpecificWebhook(discordUrl)}
                  disabled={testingWebhook}
                  className="text-[11px] font-semibold text-primary hover:underline flex items-center gap-1 cursor-pointer"
                >
                  <Send size={11} /> Test Discord
                </button>
              )}
            </div>
            <div className="relative">
              <Link2 size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                type="url"
                placeholder="https://discord.com/api/webhooks/.../..."
                value={discordUrl}
                onChange={(e) => setDiscordUrl(e.target.value)}
                className="w-full bg-background border border-border rounded-xl pl-9 pr-3 py-2 text-xs font-mono text-foreground focus:outline-hidden focus:ring-2 focus:ring-primary/20"
              />
            </div>
            <p className="text-[10px] text-muted-foreground">Stream account health events and quota warnings to Discord bots.</p>
          </div>
        </div>

        {/* Custom Webhook Endpoint */}
        <div className="p-4 rounded-xl border border-border bg-muted/20 space-y-2.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-foreground">Custom Automation Webhook (Zapier / Make / Internal API)</span>
              <span className="text-[9px] bg-purple-500/10 text-purple-500 px-1.5 py-0.5 rounded font-medium border border-purple-500/20">Enterprise</span>
            </div>
            {customWebhookUrl && (
              <button
                type="button"
                onClick={() => handleTestSpecificWebhook(customWebhookUrl)}
                disabled={testingWebhook}
                className="text-[11px] font-semibold text-primary hover:underline flex items-center gap-1 cursor-pointer"
              >
                <Send size={11} /> Test Custom
              </button>
            )}
          </div>
          <div className="relative">
            <Link2 size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              type="url"
              placeholder="https://api.yourcompany.com/webhooks/elein or https://hooks.zapier.com/..."
              value={customWebhookUrl}
              onChange={(e) => setCustomWebhookUrl(e.target.value)}
              className="w-full bg-background border border-border rounded-xl pl-9 pr-3 py-2 text-xs font-mono text-foreground focus:outline-hidden focus:ring-2 focus:ring-primary/20"
            />
          </div>
        </div>

        {/* Channel Routing Granular Matrix */}
        <div className="space-y-3 pt-2">
          <h4 className="text-xs font-bold text-foreground uppercase tracking-wider">
            Channel-Specific Alert Dispatch Matrix
          </h4>
          <div className="border border-border rounded-xl overflow-hidden bg-background">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-border bg-muted/40 font-semibold text-muted-foreground">
                  <th className="py-2.5 px-4">Event Category</th>
                  <th className="py-2.5 px-4 text-center">Slack Channel</th>
                  <th className="py-2.5 px-4 text-center">Discord Channel</th>
                  <th className="py-2.5 px-4 text-center">Email</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {[
                  { id: "account_suspended", label: "Account Suspended / Banned", desc: "Critical LinkedIn safety alerts" },
                  { id: "campaign_anomaly", label: "Campaign Anomaly & Health Spikes", desc: "Bounce spikes or spam alerts" },
                  { id: "lead_replied_instant", label: "Instant Prospect Reply", desc: "Real-time inbound lead responses" },
                  { id: "approval_queue_pending", label: "Approval Queue Pending", desc: "AI replies awaiting review" },
                  { id: "daily_digest", label: "Morning Executive Digest", desc: "Consolidated performance brief" },
                ].map((row) => {
                  const routing = channelRouting[row.id] || { slack: true, discord: false, email: true };
                  return (
                    <tr key={row.id} className="hover:bg-muted/20 transition-colors">
                      <td className="py-3 px-4">
                        <div className="font-semibold text-foreground">{row.label}</div>
                        <div className="text-[10px] text-muted-foreground">{row.desc}</div>
                      </td>
                      <td className="py-3 px-4 text-center">
                        <input
                          type="checkbox"
                          checked={Boolean(routing.slack)}
                          disabled={isNotificationLocked || !slackUrl}
                          onChange={(e) => {
                            setChannelRouting((prev) => ({
                              ...prev,
                              [row.id]: { ...(prev[row.id] || {}), slack: e.target.checked },
                            }));
                          }}
                          className="h-4 w-4 rounded border-border text-primary focus:ring-primary cursor-pointer disabled:opacity-40"
                        />
                      </td>
                      <td className="py-3 px-4 text-center">
                        <input
                          type="checkbox"
                          checked={Boolean(routing.discord)}
                          disabled={isNotificationLocked || !discordUrl}
                          onChange={(e) => {
                            setChannelRouting((prev) => ({
                              ...prev,
                              [row.id]: { ...(prev[row.id] || {}), discord: e.target.checked },
                            }));
                          }}
                          className="h-4 w-4 rounded border-border text-primary focus:ring-primary cursor-pointer disabled:opacity-40"
                        />
                      </td>
                      <td className="py-3 px-4 text-center">
                        <input
                          type="checkbox"
                          checked={Boolean(routing.email)}
                          disabled={isNotificationLocked}
                          onChange={(e) => {
                            setChannelRouting((prev) => ({
                              ...prev,
                              [row.id]: { ...(prev[row.id] || {}), email: e.target.checked },
                            }));
                          }}
                          className="h-4 w-4 rounded border-border text-primary focus:ring-primary cursor-pointer disabled:opacity-40"
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Live Test Station Input Bar */}
        <div className="space-y-3 pt-2">
          <label className="text-xs font-bold text-foreground block">
            Ad-hoc Endpoint Connectivity Test Bench
          </label>
          <div className="flex flex-col sm:flex-row gap-2">
            <div className="relative flex-1">
              <Link2 size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                type="url"
                placeholder="https://hooks.slack.com/services/... or https://discord.com/api/webhooks/..."
                value={webhookUrl}
                onChange={(e) => setWebhookUrl(e.target.value)}
                className="w-full bg-background border border-border rounded-xl pl-9 pr-4 py-2 text-xs font-mono text-foreground focus:outline-hidden focus:ring-2 focus:ring-primary/20"
              />
            </div>
            <button
              type="button"
              onClick={handleTestWebhook}
              disabled={testingWebhook || !webhookUrl.trim()}
              className="px-4 py-2 bg-primary text-primary-foreground font-semibold text-xs rounded-xl hover:bg-primary/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer flex items-center justify-center gap-1.5 shrink-0 shadow-xs"
            >
              {testingWebhook ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />}
              Test Webhook Delivery
            </button>
          </div>

          {/* Test Delivery Result Feedback */}
          {webhookTestResult && (
            <div className={`p-3.5 rounded-xl text-xs flex items-start gap-2.5 border ${
              webhookTestResult.success 
                ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-800 dark:text-emerald-400"
                : "bg-destructive/10 border-destructive/20 text-destructive"
            }`}>
              {webhookTestResult.success ? (
                <CheckCircle2 size={16} className="text-emerald-600 shrink-0 mt-0.5" />
              ) : (
                <AlertTriangle size={16} className="text-destructive shrink-0 mt-0.5" />
              )}
              <div className="flex-1">
                <div className="font-bold flex items-center gap-2">
                  <span>{webhookTestResult.success ? "HTTP 200 OK — Delivery Confirmed" : "Delivery Rejected"}</span>
                  {webhookTestResult.latencyMs && (
                    <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-background/50 border border-current">
                      {webhookTestResult.latencyMs}ms
                    </span>
                  )}
                </div>
                <p className="mt-0.5 leading-relaxed opacity-90">{webhookTestResult.message}</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function EventRow({ 
  evt, 
  getPref, 
  handleToggle, 
  isNotificationLocked,
}: { 
  evt: EventTypeItem, 
  getPref: (evt: string, ch: string) => boolean, 
  handleToggle: (evt: string, ch: string, enabled: boolean) => void,
  isNotificationLocked: boolean,
}) {
  const inAppEnabled = getPref(evt.id, "in_app");
  const emailEnabled = getPref(evt.id, "email");
  const isLockedInApp = evt.id === "account_suspended";
  const isProGated = Boolean(evt.isPro && isNotificationLocked);

  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between p-3.5 rounded-xl hover:bg-muted/30 transition-colors border border-border/40 group">
      <div className="flex-1 pr-4 mb-3 sm:mb-0">
        <div className="flex items-center gap-2">
          <h4 className="text-xs sm:text-sm font-medium text-foreground">{evt.label}</h4>
          {evt.isPro && (
            <span className={`text-[9px] font-semibold uppercase px-1.5 py-0.5 rounded ${
              isNotificationLocked 
                ? "bg-muted text-muted-foreground border border-border" 
                : "bg-primary/10 text-primary border border-primary/20"
            }`}>
              Pro
            </span>
          )}
        </div>
        <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
          {evt.desc}
        </p>
      </div>
      
      <div className="flex items-center gap-4 bg-muted/20 sm:bg-transparent p-2 sm:p-0 rounded-lg shrink-0">
        <div className="flex flex-col items-center gap-1.5 min-w-[64px]">
          <div className="flex items-center gap-1 text-[11px] font-normal text-muted-foreground">
            <Smartphone size={12} /> In-App
          </div>
          <Toggle 
            enabled={inAppEnabled} 
            locked={isLockedInApp} 
            isProLocked={isProGated}
            label={`${evt.label} in-app notification`}
            onClick={() => handleToggle(evt.id, "in_app", inAppEnabled)} 
          />
          <div className="h-3 flex items-center justify-center">
            {evt.recommended.in_app && !isLockedInApp && (
              <span className="text-[9px] text-muted-foreground/60">Rec</span>
            )}
          </div>
        </div>
        
        <div className="w-px h-8 bg-border/40" />
        
        <div className="flex flex-col items-center gap-1.5 min-w-[64px]">
          <div className="flex items-center gap-1 text-[11px] font-normal text-muted-foreground">
            <Mail size={12} /> Email
          </div>
          <Toggle 
            enabled={emailEnabled} 
            isProLocked={isProGated}
            label={`${evt.label} email notification`}
            onClick={() => handleToggle(evt.id, "email", emailEnabled)} 
          />
          <div className="h-3 flex items-center justify-center">
            {evt.recommended.email && (
              <span className="text-[9px] text-muted-foreground/60">Rec</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
