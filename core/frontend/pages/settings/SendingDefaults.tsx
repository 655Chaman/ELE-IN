import { useState, useEffect, useRef } from "react";
import { 
  Send, Info, Loader2, AlertCircle, AlertTriangle, ChevronDown, ChevronUp, 
  CheckCircle2, Lock, Zap, Clock, Globe, ShieldCheck, ShieldAlert, Calendar, 
  RotateCcw, Sliders, Moon, Sun, Sparkles 
} from "lucide-react";
import useSWR from "swr";
import { toast } from "sonner";
import { friendlyToast } from "../../components/FriendlyError";
import { motion, AnimatePresence } from "motion/react";
import { fetcher, fetchWithAuth } from "@/lib/apiClient";
import { SettingsLoadingSkeleton } from "@/components/SettingsLoadingSkeleton";
import { EmptyState } from "@/components/EmptyState";
import { usePaywall } from "@/contexts/PaywallContext";

const COMMON_TIMEZONES = [
  { value: "UTC", label: "UTC (Coordinated Universal Time)", region: "Global" },
  { value: "America/New_York", label: "Eastern Time (US & Canada, UTC-5)", region: "North America" },
  { value: "America/Chicago", label: "Central Time (US & Canada, UTC-6)", region: "North America" },
  { value: "America/Denver", label: "Mountain Time (US & Canada, UTC-7)", region: "North America" },
  { value: "America/Los_Angeles", label: "Pacific Time (US & Canada, UTC-8)", region: "North America" },
  { value: "Europe/London", label: "London / GMT (UTC+0)", region: "Europe" },
  { value: "Europe/Paris", label: "Central European Time (Paris, Berlin, UTC+1)", region: "Europe" },
  { value: "Asia/Dubai", label: "Gulf Standard Time (Dubai, UTC+4)", region: "Middle East" },
  { value: "Asia/Kolkata", label: "India Standard Time (IST, UTC+5:30)", region: "Asia" },
  { value: "Asia/Singapore", label: "Singapore Standard Time (SGT, UTC+8)", region: "Asia" },
  { value: "Asia/Tokyo", label: "Japan Standard Time (JST, UTC+9)", region: "Asia" },
  { value: "Australia/Sydney", label: "Australian Eastern Time (AEST, UTC+10)", region: "Pacific" },
];

function formatTimeDisplay(timeStr: string) {
  if (!timeStr) return "08:00";
  const parts = timeStr.split(":");
  return `${parts[0] || "08"}:${parts[1] || "00"}`;
}

function normalizeTimeForApi(timeStr: string) {
  if (!timeStr) return "08:00:00";
  const parts = timeStr.split(":");
  const h = parts[0] || "08";
  const m = parts[1] || "00";
  return `${h.padStart(2, "0")}:${m.padStart(2, "0")}:00`;
}

export function SendingDefaults({ workspaceId }: { workspaceId: string | null }) {
  const { data, mutate, isLoading } = useSWR(
    workspaceId ? `/api/workspaces/${workspaceId}/sending-defaults` : null,
    fetcher
  );

  const { data: billing } = useSWR<{ plan?: string; tier?: string; tier_limits?: { can_custom_sending_defaults?: boolean } }>(
    '/api/elein/workspaces/billing',
    fetcher
  );
  const { openPaywall } = usePaywall();
  const isCustomSendingLocked = Boolean(billing && !billing.tier_limits?.can_custom_sending_defaults);

  // Core limits
  const [connLimit, setConnLimit] = useState(20);
  const [msgLimit, setMsgLimit] = useState(40);
  const [warmupDays, setWarmupDays] = useState(14);
  
  // Operating schedule & safety guardrails
  const [workStart, setWorkStart] = useState("08:00");
  const [workEnd, setWorkEnd] = useState("18:00");
  const [timezone, setTimezone] = useState("UTC");
  const [weekendSending, setWeekendSending] = useState(false);
  const [minJitterSec, setMinJitterSec] = useState(45);
  const [maxJitterSec, setMaxJitterSec] = useState(180);

  // Human Paranoia & Validation state
  const [dangerAcknowledged, setDangerAcknowledged] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showChart, setShowChart] = useState(false);
  const [showSuccess, setShowSuccess] = useState(false);
  const [currentTimeInTz, setCurrentTimeInTz] = useState<string>("");
  const [isWithinWindow, setIsWithinWindow] = useState<boolean>(true);
  
  const successTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (successTimerRef.current) clearTimeout(successTimerRef.current);
    };
  }, []);

  useEffect(() => {
    if (data) {
      setConnLimit(data.daily_connection_limit ?? data.default_daily_connection_limit ?? 20);
      setMsgLimit(data.daily_message_limit ?? data.default_daily_message_limit ?? 40);
      setWarmupDays(data.warmup_days ?? data.default_warmup_target_days ?? 14);
      setWorkStart(formatTimeDisplay(data.default_working_hours_start || "08:00:00"));
      setWorkEnd(formatTimeDisplay(data.default_working_hours_end || "18:00:00"));
      setTimezone(data.default_timezone || "UTC");
      setWeekendSending(Boolean(data.weekend_sending_enabled));
    }
  }, [data]);

  // Live Timezone Clock and Window Status
  useEffect(() => {
    const updateTzClock = () => {
      try {
        const now = new Date();
        const formatter = new Intl.DateTimeFormat("en-US", {
          timeZone: timezone,
          hour: "numeric",
          minute: "2-digit",
          hour12: true,
          weekday: "short"
        });
        const hourFormatter = new Intl.DateTimeFormat("en-US", {
          timeZone: timezone,
          hour: "numeric",
          minute: "numeric",
          hour12: false
        });
        
        setCurrentTimeInTz(formatter.format(now));

        // Evaluate if currently within window
        const timeParts = hourFormatter.format(now).split(":");
        const currentH = parseInt(timeParts[0] || "0", 10);
        const currentM = parseInt(timeParts[1] || "0", 10);
        const currentMins = currentH * 60 + currentM;

        const startParts = workStart.split(":");
        const startMins = parseInt(startParts[0] || "8", 10) * 60 + parseInt(startParts[1] || "0", 10);

        const endParts = workEnd.split(":");
        const endMins = parseInt(endParts[0] || "18", 10) * 60 + parseInt(endParts[1] || "0", 10);

        const dayFormatter = new Intl.DateTimeFormat("en-US", { timeZone: timezone, weekday: "short" });
        const dayStr = dayFormatter.format(now);
        const isWeekend = dayStr === "Sat" || dayStr === "Sun";

        if (isWeekend && !weekendSending) {
          setIsWithinWindow(false);
        } else {
          setIsWithinWindow(currentMins >= startMins && currentMins < endMins);
        }
      } catch {
        setCurrentTimeInTz("Current Time (Active)");
        setIsWithinWindow(true);
      }
    };

    updateTzClock();
    const interval = setInterval(updateTzClock, 10000);
    return () => clearInterval(interval);
  }, [timezone, workStart, workEnd, weekendSending]);

  // Environmental Validation: Check for time window inversion
  const isTimeWindowInverted = (() => {
    try {
      const [sh, sm] = workStart.split(":").map(Number);
      const [eh, em] = workEnd.split(":").map(Number);
      const startMins = (sh ?? 8) * 60 + (sm ?? 0);
      const endMins = (eh ?? 18) * 60 + (em ?? 0);
      return startMins >= endMins;
    } catch {
      return false;
    }
  })();

  const isExtremeVolume = connLimit > 30 || msgLimit > 80;

  const hasChanges = Boolean(
    data &&
    (connLimit !== (data.daily_connection_limit ?? data.default_daily_connection_limit ?? 20) ||
      msgLimit !== (data.daily_message_limit ?? data.default_daily_message_limit ?? 40) ||
      warmupDays !== (data.warmup_days ?? data.default_warmup_target_days ?? 14) ||
      workStart !== formatTimeDisplay(data.default_working_hours_start || "08:00:00") ||
      workEnd !== formatTimeDisplay(data.default_working_hours_end || "18:00:00") ||
      timezone !== (data.default_timezone || "UTC") ||
      weekendSending !== Boolean(data.weekend_sending_enabled))
  );

  const isSaveBlocked = 
    !hasChanges || 
    saving || 
    isTimeWindowInverted || 
    (isExtremeVolume && !dangerAcknowledged);

  const handleResetToSafeBaseline = () => {
    setConnLimit(20);
    setMsgLimit(40);
    setWarmupDays(14);
    setWorkStart("08:00");
    setWorkEnd("18:00");
    setWeekendSending(false);
    setDangerAcknowledged(false);
    toast.success("Reset parameters to LinkedIn Safe Baseline (20 conns, 40 msgs, 14d warmup)");
  };

  const handleSave = async () => {
    if (!workspaceId || saving) return;
    if (isCustomSendingLocked) {
      openPaywall({ featureName: "Custom Sending Schedules & Ramp Pacing" });
      return;
    }
    if (isTimeWindowInverted) {
      toast.error("Operating start time must precede end time");
      return;
    }
    if (isExtremeVolume && !dangerAcknowledged) {
      toast.error("Please acknowledge high-volume risk before proceeding");
      return;
    }
    if (!hasChanges) return;

    setSaving(true);
    setShowSuccess(false);

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 15000);

      const res = await fetchWithAuth(`/api/workspaces/${workspaceId}/sending-defaults`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          daily_connection_limit: connLimit,
          daily_message_limit: msgLimit,
          warmup_days: warmupDays,
          default_daily_connection_limit: connLimit,
          default_daily_message_limit: msgLimit,
          default_warmup_target_days: warmupDays,
          default_working_hours_start: normalizeTimeForApi(workStart),
          default_working_hours_end: normalizeTimeForApi(workEnd),
          default_timezone: timezone,
          weekend_sending_enabled: weekendSending
        }),
      });

      clearTimeout(timeoutId);

      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText || "Failed to update defaults");
      }

      toast.success("Sending guardrails & safety defaults saved successfully");
      mutate();
      if (successTimerRef.current) clearTimeout(successTimerRef.current);
      setShowSuccess(true);
      successTimerRef.current = setTimeout(() => setShowSuccess(false), 5000);
    } catch (e: any) {
      friendlyToast('Failed to save sending defaults — please try again.', e);
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
  const chartHeight = 150;
  const chartWidth = 560;

  const generateRampPath = () => {
    if (warmupDays === 0) return `M 0,0 L ${chartWidth},0`;
    let path = `M 0,${chartHeight - (chartHeight * 0.1)}`;
    for (let i = 1; i <= Math.max(warmupDays, 1); i++) {
      const x = (i / warmupDays) * chartWidth;
      const progress = Math.min(1, i / warmupDays);
      const y = chartHeight - (chartHeight * (0.1 + (0.9 * progress)));
      path += ` L ${x},${y}`;
    }
    return path;
  };

  const handleNumInput = (val: string, setter: (n: number) => void, max: number) => {
    if (isCustomSendingLocked) {
      openPaywall({ featureName: "Custom Sending Schedules & Ramp Pacing" });
      return;
    }
    if (val === "") { setter(1); return; }
    const num = parseInt(val, 10);
    if (isNaN(num)) return;
    setter(Math.max(1, Math.min(num, max)));
  };

  // Operational Window Calculation
  const workingHoursSpan = (() => {
    try {
      const [sh] = workStart.split(":").map(Number);
      const [eh] = workEnd.split(":").map(Number);
      return Math.max(1, (eh ?? 18) - (sh ?? 8));
    } catch {
      return 9;
    }
  })();

  const estimatedDispatchIntervalMin = Math.max(
    1,
    Math.round((workingHoursSpan * 60) / Math.max(1, maxActions))
  );

  return (
    <div className="space-y-6 max-w-4xl font-sans">
      <div className="p-8 rounded-[24px] border border-gray-100 bg-white relative overflow-hidden shadow-sm">
        <div className="absolute top-0 left-0 w-1.5 h-full bg-primary/60"></div>
        
        {/* Header Station */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-primary/10 rounded-2xl text-primary shadow-xs">
              <ShieldCheck size={26} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-2xl font-bold tracking-tight text-gray-900">Sending Safety & Operating Guardrails</h2>
                <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 border border-emerald-500/20">
                  Fleet Protected
                </span>
              </div>
              <p className="text-sm text-gray-500 mt-1">Configure default throttling, working hours, and warmup curves for newly attached LinkedIn senders.</p>
            </div>
          </div>

          <button
            type="button"
            onClick={handleResetToSafeBaseline}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-gray-600 hover:text-gray-900 bg-gray-100 hover:bg-gray-200/80 rounded-xl transition-all self-start sm:self-auto cursor-pointer"
            title="Reset parameters to recommended safe limits"
          >
            <RotateCcw size={13} />
            <span>Reset Safe Baseline</span>
          </button>
        </div>

        {/* Global Template Advisory */}
        <div className="mb-6 p-4 bg-primary/5 border border-primary/20 rounded-2xl flex gap-3.5 items-start">
          <Info className="text-primary shrink-0 mt-0.5" size={19} />
          <div className="text-xs text-gray-700 leading-relaxed">
            <strong className="text-primary font-bold">Template Inheritance Model:</strong> Changing these values establishes the baseline parameters for <strong>newly connected accounts</strong>. Existing sender profiles preserve their individual custom calibrations unless manually synced in the LinkedIn Accounts Command Center.
          </div>
        </div>

        {/* Pro Paywall Teaser */}
        {isCustomSendingLocked && (
          <div className="mb-8 p-4 rounded-2xl bg-gradient-to-r from-amber-500/10 via-primary/10 to-amber-500/5 border border-amber-500/30 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className="p-2 bg-amber-500/10 rounded-xl text-amber-600 dark:text-amber-400 shrink-0 mt-0.5">
                <Lock size={18} />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100">
                    Growth Pro Feature: Custom Daily Schedules & Ramp Pacing
                  </h3>
                  <span className="text-[10px] font-extrabold uppercase px-2 py-0.5 bg-amber-500/20 text-amber-600 dark:text-amber-400 rounded-full border border-amber-500/30">
                    Pro Gated
                  </span>
                </div>
                <p className="text-xs text-gray-600 dark:text-gray-400 mt-1 leading-relaxed">
                  Your workspace is currently operating on safe automated baseline defaults (20 connects/day, 40 messages/day, 14-day warmup). Upgrade to Growth Pro to customize high-velocity outreach, custom warmups, and weekend pacing.
                </p>
              </div>
            </div>
            <button
              onClick={() => openPaywall({ featureName: "Custom Sending Schedules & Ramp Pacing" })}
              className="px-4 py-2 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-600 hover:to-amber-700 text-white rounded-xl text-xs font-bold shadow-sm shadow-amber-500/25 shrink-0 flex items-center gap-1.5 transition-all active:scale-95 cursor-pointer"
            >
              <Zap size={13} className="fill-current" />
              Upgrade to Growth Pro
            </button>
          </div>
        )}

        <div className="space-y-6">
          {/* Section 1: Calibrated Safety Profiles */}
          <div className="p-5 rounded-2xl border border-gray-200/80 bg-gray-50/50">
            <div className="flex items-center justify-between mb-3">
              <div>
                <h3 className="text-sm font-bold text-gray-900 flex items-center gap-1.5">
                  <Sparkles size={16} className="text-primary" />
                  Calibrated Safety Profiles
                </h3>
                <p className="text-xs text-gray-500 mt-0.5">Select a pre-calibrated safety profile matched to your account maturity:</p>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {[
                {
                  id: 'max_safety',
                  title: 'Maximum Safety',
                  desc: 'For accounts < 3 months old or newly active',
                  conns: 15,
                  msgs: 25,
                  warmup: 21,
                  start: "09:00",
                  end: "17:00",
                  tag: '100% Safe Zone',
                  isPro: false
                },
                {
                  id: 'balanced',
                  title: 'Balanced Scale',
                  desc: 'Recommended for standard established profiles',
                  conns: 20,
                  msgs: 40,
                  warmup: 14,
                  start: "08:00",
                  end: "18:00",
                  tag: 'Safe Baseline',
                  isPro: false
                },
                {
                  id: 'nav_scale',
                  title: 'Sales Navigator',
                  desc: 'For paid Sales Nav subscriptions with high SSI',
                  conns: 25,
                  msgs: 60,
                  warmup: 10,
                  start: "08:00",
                  end: "19:00",
                  tag: 'High Velocity',
                  isPro: true
                }
              ].map(profile => {
                const isSelected = connLimit === profile.conns && msgLimit === profile.msgs && warmupDays === profile.warmup;
                return (
                  <div
                    key={profile.id}
                    onClick={() => {
                      if (isCustomSendingLocked && profile.isPro) {
                        openPaywall({ featureName: "Custom Sending Schedules & Ramp Pacing" });
                        return;
                      }
                      setConnLimit(profile.conns);
                      setMsgLimit(profile.msgs);
                      setWarmupDays(profile.warmup);
                      setWorkStart(profile.start);
                      setWorkEnd(profile.end);
                      toast.info(`Loaded "${profile.title}" profile`);
                    }}
                    className={`p-3.5 rounded-xl border transition-all cursor-pointer flex flex-col justify-between ${
                      isSelected 
                        ? 'border-primary bg-primary/5 ring-1 ring-primary/20 shadow-xs' 
                        : 'border-gray-200 bg-white hover:border-primary/40 hover:bg-gray-50'
                    }`}
                  >
                    <div>
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="text-xs font-bold text-gray-900 flex items-center gap-1.5">
                          {profile.title}
                          {isCustomSendingLocked && profile.isPro && (
                            <Lock size={11} className="text-amber-500 shrink-0" />
                          )}
                        </span>
                        <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${
                          isSelected ? 'bg-primary text-primary-foreground' : 'bg-gray-100 text-gray-600'
                        }`}>
                          {profile.tag}
                        </span>
                      </div>
                      <p className="text-[11px] text-gray-500 leading-relaxed">{profile.desc}</p>
                    </div>
                    <div className="mt-3 pt-2 border-t border-gray-100 flex items-center justify-between text-[11px] font-semibold text-gray-700">
                      <span>{profile.conns} conns/d</span>
                      <span className="text-gray-300">•</span>
                      <span>{profile.msgs} msgs/d</span>
                      <span className="text-gray-300">•</span>
                      <span>{profile.warmup}d ramp</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Section 2: Working Hours & Timezone Pacing Station (Layer 0 & 1) */}
          <div className="border border-gray-200 bg-white rounded-2xl p-6 shadow-xs">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6 pb-4 border-b border-gray-100">
              <div>
                <h3 className="text-base font-bold tracking-tight text-gray-900 flex items-center gap-2">
                  <Clock size={18} className="text-primary" />
                  Working Hours & Timezone Pacing Station
                </h3>
                <p className="text-xs text-gray-500 mt-0.5">Restrict outbound actions to natural business hours in the recipient's timezone.</p>
              </div>

              {/* Live Timezone Radar Badge */}
              <div className={`px-3 py-1.5 rounded-xl text-xs font-semibold border flex items-center gap-2 self-start sm:self-auto ${
                isWithinWindow 
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200' 
                  : 'bg-amber-50 text-amber-700 border-amber-200'
              }`}>
                <span className={`w-2 h-2 rounded-full ${isWithinWindow ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500'}`} />
                <span>{currentTimeInTz || "Loading Timezone..."}</span>
                <span className="text-[10px] font-bold uppercase opacity-80">
                  {isWithinWindow ? "• Window Active" : "• Quiet Hours"}
                </span>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-5">
              {/* Operating Timezone */}
              <div 
                className="relative"
                onClick={() => {
                  if (isCustomSendingLocked) {
                    openPaywall({ featureName: "Custom Sending Schedules & Working Hours" });
                  }
                }}
              >
                <label className="text-xs font-bold text-gray-700 block mb-1.5 flex items-center justify-between">
                  <span className="flex items-center gap-1.5">
                    <Globe size={13} className="text-primary" />
                    Primary Operating Timezone
                  </span>
                  {isCustomSendingLocked && (
                    <span className="flex items-center gap-1 text-[10px] font-bold text-amber-600 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/20">
                      <Lock size={10} /> Pro
                    </span>
                  )}
                </label>
                <select
                  value={timezone}
                  disabled={isCustomSendingLocked}
                  onChange={(e) => setTimezone(e.target.value)}
                  className="w-full px-3 py-2 bg-gray-50 border border-gray-200 rounded-xl text-xs font-semibold text-gray-900 focus:ring-2 ring-primary outline-none disabled:opacity-60 disabled:cursor-pointer"
                >
                  {COMMON_TIMEZONES.map(tz => (
                    <option key={tz.value} value={tz.value}>
                      {tz.label}
                    </option>
                  ))}
                </select>
                <p className="text-[11px] text-gray-400 mt-1">Actions are scheduled relative to this clock.</p>
              </div>

              {/* Start Time */}
              <div
                className="relative"
                onClick={() => {
                  if (isCustomSendingLocked) {
                    openPaywall({ featureName: "Dedicated Schedule Curfews & Working Hours" });
                  }
                }}
              >
                <label className="text-xs font-bold text-gray-700 block mb-1.5 flex items-center justify-between">
                  <span className="flex items-center gap-1.5">
                    <Sun size={13} className="text-amber-500" />
                    Window Start Time
                  </span>
                  {isCustomSendingLocked && (
                    <span className="flex items-center gap-1 text-[10px] font-bold text-amber-600 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/20">
                      <Lock size={10} /> Pro
                    </span>
                  )}
                </label>
                <input
                  type="time"
                  value={workStart}
                  disabled={isCustomSendingLocked}
                  onChange={(e) => setWorkStart(e.target.value)}
                  className="w-full px-3 py-2 bg-gray-50 border border-gray-200 rounded-xl text-xs font-mono font-bold text-gray-900 focus:ring-2 ring-primary outline-none disabled:opacity-60 disabled:cursor-pointer"
                />
                <p className="text-[11px] text-gray-400 mt-1">Automation wakes up at this local hour.</p>
              </div>

              {/* End Time */}
              <div
                className="relative"
                onClick={() => {
                  if (isCustomSendingLocked) {
                    openPaywall({ featureName: "Dedicated Schedule Curfews & Working Hours" });
                  }
                }}
              >
                <label className="text-xs font-bold text-gray-700 block mb-1.5 flex items-center justify-between">
                  <span className="flex items-center gap-1.5">
                    <Moon size={13} className="text-indigo-500" />
                    Window End Time
                  </span>
                  {isCustomSendingLocked && (
                    <span className="flex items-center gap-1 text-[10px] font-bold text-amber-600 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/20">
                      <Lock size={10} /> Pro
                    </span>
                  )}
                </label>
                <input
                  type="time"
                  value={workEnd}
                  disabled={isCustomSendingLocked}
                  onChange={(e) => setWorkEnd(e.target.value)}
                  className="w-full px-3 py-2 bg-gray-50 border border-gray-200 rounded-xl text-xs font-mono font-bold text-gray-900 focus:ring-2 ring-primary outline-none disabled:opacity-60 disabled:cursor-pointer"
                />
                <p className="text-[11px] text-gray-400 mt-1">Outreach pauses until the next business morning.</p>
              </div>
            </div>

            {/* Environmental Failure Guard: Time Inversion */}
            <AnimatePresence>
              {isTimeWindowInverted && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="mb-5 p-3.5 bg-destructive/10 border border-destructive/20 rounded-xl flex items-start gap-2.5 text-xs text-destructive font-medium"
                >
                  <AlertCircle size={16} className="shrink-0 mt-0.5" />
                  <div>
                    <strong>Inverted Operating Window:</strong> The window start time ({workStart}) is set equal to or after the end time ({workEnd}). Overnight automation across midnight is disabled to protect accounts from sleep-deprived prospect complaints.
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Weekend Sending Toggle with Friction Gate (Layer 2) */}
            <div className="pt-4 border-t border-gray-100 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="flex items-start gap-3">
                <div className="p-2 bg-gray-100 rounded-xl text-gray-600 mt-0.5">
                  <Calendar size={16} />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-gray-900">Weekend Outreach (Saturday & Sunday)</span>
                    <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${weekendSending ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'}`}>
                      {weekendSending ? 'High Risk' : 'Quiet Mode (Safe)'}
                    </span>
                  </div>
                  <p className="text-[11px] text-gray-500 mt-0.5">
                    When quiet mode is on, all campaigns automatically sleep on weekends and resume Monday morning.
                  </p>
                </div>
              </div>

              <label className="relative inline-flex items-center cursor-pointer shrink-0">
                <input
                  type="checkbox"
                  checked={weekendSending}
                  disabled={isCustomSendingLocked}
                  onChange={(e) => {
                    if (isCustomSendingLocked) {
                      openPaywall({ featureName: "Custom Sending Schedules & Ramp Pacing" });
                      return;
                    }
                    setWeekendSending(e.target.checked);
                  }}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-amber-500"></div>
              </label>
            </div>

            {weekendSending && (
              <div className="mt-3 p-3 bg-amber-50 border border-amber-200/80 rounded-xl flex items-start gap-2.5 text-xs text-amber-800 leading-relaxed">
                <AlertTriangle size={15} className="shrink-0 mt-0.5 text-amber-600" />
                <span>
                  <strong>Caution:</strong> LinkedIn telemetry flags high-volume connection requests and DMs sent on Saturdays and Sundays. We strongly advise keeping weekend outreach disabled unless running a specific weekend-targeted event sequence.
                </span>
              </div>
            )}
          </div>

          {/* Section 3: Daily Limits Card (Layer 0 & Layer 2) */}
          <div className="border border-gray-200 bg-white rounded-2xl p-6 shadow-xs">
            <div className="flex items-center justify-between mb-6 pb-4 border-b border-gray-100">
              <div>
                <h3 className="text-base font-bold tracking-tight text-gray-900 flex items-center gap-2">
                  <Sliders size={18} className="text-primary" />
                  Daily Capacity Limits
                </h3>
                <p className="text-xs text-gray-500 mt-0.5">Define maximum daily invitation and messaging envelopes per sender.</p>
              </div>

              {/* Dynamic Envelope Indicator */}
              <div className="px-3 py-1 bg-gray-100 text-gray-700 rounded-xl text-xs font-semibold flex items-center gap-1.5">
                <span>Total Actions:</span>
                <span className="font-mono font-bold text-primary">{maxActions} / day</span>
                <span className="text-gray-400">• (~1 every {estimatedDispatchIntervalMin}m)</span>
              </div>
            </div>

            <div className="space-y-8">
              {/* Connection Limit */}
              <div>
                <div className="flex justify-between items-center mb-3">
                  <div>
                    <label className="text-sm font-bold text-gray-900">Daily Connection Request Limit</label>
                    <p className="text-xs text-gray-500">Safe maximum connection requests dispatched per day per account</p>
                  </div>
                  <input 
                    type="number" 
                    value={connLimit} 
                    onChange={(e) => handleNumInput(e.target.value, setConnLimit, 100)}
                    className="w-20 px-3 py-1.5 bg-gray-50 border border-gray-200 rounded-xl text-right font-mono text-base font-bold text-gray-900 focus:ring-2 ring-primary outline-none"
                  />
                </div>
                
                <div className="relative pt-6 pb-2">
                  <div className="absolute top-0 left-[20%] -ml-px w-px h-full bg-emerald-500/30 z-0"></div>
                  <div className="absolute top-0 left-[20%] -ml-6 text-[10px] text-emerald-600 font-bold">Safe (20/d)</div>

                  <div className="absolute top-0 left-[30%] -ml-px w-px h-full bg-amber-500/30 z-0"></div>
                  <div className="absolute top-0 left-[30%] -ml-6 text-[10px] text-amber-600 font-bold">Caution (30/d)</div>
                  
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={connLimit}
                    onChange={(e) => {
                      if (isCustomSendingLocked) {
                        openPaywall({ featureName: "Custom Sending Schedules & Ramp Pacing" });
                        return;
                      }
                      setConnLimit(parseInt(e.target.value));
                    }}
                    className="w-full appearance-none bg-gray-200 h-2 rounded-full outline-none z-10 relative cursor-pointer"
                    style={{
                      background: `linear-gradient(to right, 
                        ${connLimit <= 20 ? '#22c55e' : connLimit <= 30 ? '#eab308' : '#ef4444'} ${connLimit}%, 
                        #e5e7eb ${connLimit}%)`
                    }}
                  />
                </div>
                <AnimatePresence>
                  {connLimit > 20 && (
                    <motion.div 
                      initial={{ opacity: 0, height: 0 }} 
                      animate={{ opacity: 1, height: 'auto' }} 
                      exit={{ opacity: 0, height: 0 }}
                      className="mt-3 flex items-center gap-2 text-xs text-amber-700 bg-amber-50 p-2.5 rounded-xl border border-amber-200"
                    >
                      <AlertTriangle size={15} className="shrink-0" />
                      <span>{connLimit > 30 ? 'High risk! Sending > 30 invites/day triggers automated LinkedIn security audits and temporary invitation bans.' : 'Caution: Exceeding LinkedIn recommended safe limit (20/day).'}</span>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              {/* Message Limit */}
              <div>
                <div className="flex justify-between items-center mb-3">
                  <div>
                    <label className="text-sm font-bold text-gray-900">Daily Message Limit</label>
                    <p className="text-xs text-gray-500">Number of follow-up messages, InMails, and replies per day</p>
                  </div>
                  <input 
                    type="number" 
                    value={msgLimit} 
                    onChange={(e) => handleNumInput(e.target.value, setMsgLimit, 150)}
                    className="w-20 px-3 py-1.5 bg-gray-50 border border-gray-200 rounded-xl text-right font-mono text-base font-bold text-gray-900 focus:ring-2 ring-primary outline-none"
                  />
                </div>
                
                <div className="relative pt-6 pb-2">
                  <div className="absolute top-0 left-[26.6%] -ml-px w-px h-full bg-emerald-500/30 z-0"></div>
                  <div className="absolute top-0 left-[26.6%] -ml-6 text-[10px] text-emerald-600 font-bold">Safe (40/d)</div>

                  <div className="absolute top-0 left-[53.3%] -ml-px w-px h-full bg-amber-500/30 z-0"></div>
                  <div className="absolute top-0 left-[53.3%] -ml-6 text-[10px] text-amber-600 font-bold">Max (80/d)</div>
                  
                  <input
                    type="range"
                    min="0"
                    max="150"
                    value={msgLimit}
                    onChange={(e) => {
                      if (isCustomSendingLocked) {
                        openPaywall({ featureName: "Custom Sending Schedules & Ramp Pacing" });
                        return;
                      }
                      setMsgLimit(parseInt(e.target.value));
                    }}
                    className="w-full appearance-none bg-gray-200 h-2 rounded-full outline-none z-10 relative cursor-pointer"
                    style={{
                      background: `linear-gradient(to right, 
                        ${msgLimit <= 50 ? '#3b82f6' : msgLimit <= 80 ? '#eab308' : '#ef4444'} ${(msgLimit/150)*100}%, 
                        #e5e7eb ${(msgLimit/150)*100}%)`
                    }}
                  />
                </div>
                <AnimatePresence>
                  {msgLimit > 50 && (
                    <motion.div 
                      initial={{ opacity: 0, height: 0 }} 
                      animate={{ opacity: 1, height: 'auto' }} 
                      exit={{ opacity: 0, height: 0 }}
                      className="mt-3 flex items-center gap-2 text-xs text-amber-700 bg-amber-50 p-2.5 rounded-xl border border-amber-200"
                    >
                      <AlertTriangle size={15} className="shrink-0" />
                      <span>{msgLimit > 80 ? 'High risk! Messaging at > 80/day volume triggers spam classifiers.' : 'Caution: Above typical safe baseline (50/day).'}</span>
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
                    className="p-3 bg-amber-50 border border-amber-200 rounded-xl flex items-start gap-2 text-xs text-amber-800"
                  >
                    <AlertTriangle size={15} className="mt-0.5 shrink-0 text-amber-600" />
                    <span>Warning: Connection limit ({connLimit}) is set higher than message limit ({msgLimit}). Connected leads may stall in queues without timely follow-ups.</span>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Extreme Volume Paranoia Checkbox (Layer 2) */}
              {isExtremeVolume && (
                <div className="p-4 bg-red-50 border border-red-200 rounded-2xl flex items-start gap-3">
                  <ShieldAlert size={18} className="text-red-600 shrink-0 mt-0.5" />
                  <div className="flex-1">
                    <h4 className="text-xs font-bold text-red-900">High Volume Acknowledgment Required</h4>
                    <p className="text-[11px] text-red-700 mt-0.5 leading-relaxed">
                      You have configured aggressive sending thresholds exceeding platform recommendations. This increases the probability of LinkedIn account verification checkpoints.
                    </p>
                    <label className="flex items-center gap-2 mt-2.5 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={dangerAcknowledged}
                        onChange={(e) => setDangerAcknowledged(e.target.checked)}
                        className="rounded border-red-300 text-red-600 focus:ring-red-500"
                      />
                      <span className="text-xs font-bold text-red-900">
                        I acknowledge the operational risks and verify these accounts possess high Social Selling Index (SSI)
                      </span>
                    </label>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Section 4: Warmup Ramp Configuration */}
          <div className="border border-gray-200 bg-white rounded-2xl p-6 shadow-xs">
            <div className="flex items-center justify-between mb-6 pb-4 border-b border-gray-100">
              <div>
                <h3 className="text-base font-bold tracking-tight text-gray-900 flex items-center gap-2">
                  <Zap size={18} className="text-blue-600" />
                  Warmup Ramp Configuration
                </h3>
                <p className="text-xs text-gray-500 mt-0.5">Control how smoothly newly connected accounts scale up to their full daily limits.</p>
              </div>

              <span className="text-xs font-bold px-2.5 py-1 rounded-xl bg-blue-50 text-blue-700 border border-blue-200">
                {warmupDays} Days Ramp Duration
              </span>
            </div>
            
            <div>
              <div className="mb-6">
                <div className="flex justify-between items-center mb-3">
                  <div>
                    <label className="text-sm font-bold text-gray-900">Gradual Warmup Duration</label>
                    <p className="text-xs text-gray-500">Days over which actions linearly ramp from 10% to 100%</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <input 
                      type="number" 
                      value={warmupDays} 
                      onChange={(e) => handleNumInput(e.target.value, setWarmupDays, 30)}
                      className="w-20 px-3 py-1.5 bg-gray-50 border border-gray-200 rounded-xl text-right font-mono text-base font-bold text-gray-900 focus:ring-2 ring-primary outline-none"
                    />
                    <span className="text-xs font-semibold text-gray-500">days</span>
                  </div>
                </div>
                
                <div className="relative pt-6 pb-2">
                  <input
                    type="range"
                    min="0"
                    max="30"
                    value={warmupDays}
                    onChange={(e) => {
                      if (isCustomSendingLocked) {
                        openPaywall({ featureName: "Custom Sending Schedules & Ramp Pacing" });
                        return;
                      }
                      setWarmupDays(parseInt(e.target.value));
                    }}
                    className="w-full appearance-none bg-gray-200 h-2 rounded-full outline-none z-10 relative cursor-pointer"
                    style={{
                      background: `linear-gradient(to right, 
                        #2563eb ${(warmupDays/30)*100}%, 
                        #e5e7eb ${(warmupDays/30)*100}%)`
                    }}
                  />
                  <div className="flex justify-between mt-2 text-[10px] text-gray-400 font-medium px-1">
                    <span>0d (Instant Full)</span>
                    <span>7d (Fast)</span>
                    <span>14d (Recommended)</span>
                    <span>21d (Cautious)</span>
                    <span>30d (Maximum)</span>
                  </div>
                </div>
              </div>

              {/* 30-Day Warmup Projection SVG */}
              <div className="border border-gray-200 rounded-2xl overflow-hidden bg-gray-50/50">
                <button 
                  type="button"
                  onClick={() => setShowChart(!showChart)}
                  className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-100/50 transition-colors cursor-pointer"
                >
                  <span className="font-bold text-xs text-gray-800 flex items-center gap-2">
                    <Zap size={14} className="text-blue-600" />
                    Inspect Warmup Scaling Projection Curve
                  </span>
                  {showChart ? <ChevronUp size={16} className="text-gray-500" /> : <ChevronDown size={16} className="text-gray-500" />}
                </button>
                
                <AnimatePresence>
                  {showChart && (
                    <motion.div 
                      initial={{ height: 0 }}
                      animate={{ height: 'auto' }}
                      exit={{ height: 0 }}
                      className="overflow-hidden"
                    >
                      <div className="p-5 pt-2 border-t border-gray-200/60">
                        <p className="text-xs text-gray-600 mb-4 leading-relaxed">
                          New senders begin at ~10% daily volume (~{Math.max(1, Math.round(maxActions * 0.1))} actions/day) on Day 1, ramping linearly to 100% ({maxActions} actions/day) on Day {warmupDays || 1}.
                        </p>
                        <div className="relative w-full overflow-x-auto pb-4">
                          <div className="min-w-[500px]">
                            <svg viewBox={`0 0 ${chartWidth} ${chartHeight + 25}`} width="100%" height={chartHeight + 25} className="overflow-visible">
                              <defs>
                                <linearGradient id="warmupGradient" x1="0" y1="0" x2="0" y2="1">
                                  <stop offset="0%" stopColor="#2563eb" stopOpacity="0.4" />
                                  <stop offset="100%" stopColor="#2563eb" stopOpacity="0.0" />
                                </linearGradient>
                              </defs>
                              
                              <line x1="0" y1="0" x2={chartWidth} y2="0" stroke="#9ca3af" strokeOpacity="0.2" strokeDasharray="4 4" />
                              <line x1="0" y1={chartHeight/2} x2={chartWidth} y2={chartHeight/2} stroke="#9ca3af" strokeOpacity="0.2" strokeDasharray="4 4" />
                              <line x1="0" y1={chartHeight} x2={chartWidth} y2={chartHeight} stroke="#9ca3af" strokeOpacity="0.4" />
                              
                              <motion.path
                                initial={{ pathLength: 0, opacity: 0 }}
                                animate={{ pathLength: 1, opacity: 1 }}
                                transition={{ duration: 0.8, ease: "easeInOut" }}
                                d={`${generateRampPath()} L ${chartWidth} ${chartHeight} L 0 ${chartHeight} Z`}
                                fill="url(#warmupGradient)"
                              />
                              
                              <motion.path
                                initial={{ pathLength: 0 }}
                                animate={{ pathLength: 1 }}
                                transition={{ duration: 0.8, ease: "easeInOut" }}
                                d={generateRampPath()}
                                fill="none"
                                stroke="#2563eb"
                                strokeWidth="3"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                              />
                              
                              <circle cx="0" cy={chartHeight - (chartHeight * 0.1)} r="4" fill="#2563eb" />
                              {warmupDays > 0 && (
                                <circle cx={(Math.min(warmupDays, 30)/30)*chartWidth} cy={warmupDays === 0 ? chartHeight : 0} r="4" fill="#2563eb" />
                              )}
                              
                              <text x="0" y={chartHeight + 18} fontSize="10" fill="#6b7280" fontWeight="bold">Day 1 ({Math.max(1, Math.round(maxActions * 0.1))} acts)</text>
                              <text x={chartWidth/2} y={chartHeight + 18} fontSize="10" fill="#6b7280" textAnchor="middle">Day 15</text>
                              <text x={chartWidth} y={chartHeight + 18} fontSize="10" fill="#6b7280" textAnchor="end" fontWeight="bold">Day 30 ({maxActions} acts)</text>
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
          
          {/* Success Banner */}
          <AnimatePresence>
            {showSuccess && (
              <motion.div 
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className="bg-emerald-50 border border-emerald-200 text-emerald-800 p-4 rounded-2xl flex items-start gap-3 shadow-xs"
              >
                <CheckCircle2 className="shrink-0 mt-0.5 text-emerald-600" size={20} />
                <div>
                  <p className="font-bold text-sm">Defaults & Guardrails Successfully Saved!</p>
                  <p className="text-xs mt-0.5 text-emerald-700 leading-relaxed">
                    Newly connected senders will operate between {workStart}–{workEnd} ({timezone}), respecting {connLimit} connections and {msgLimit} messages daily with a {warmupDays}-day warmup ramp.
                  </p>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Action Footer & Physical Save Gate (Layer 2) */}
          <div className="pt-2 flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="text-xs text-gray-500">
              {hasChanges ? (
                <span className="text-amber-600 font-semibold flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-amber-500 animate-ping" />
                  Unsaved modifications in sending defaults
                </span>
              ) : (
                <span className="text-gray-400">Settings synchronized with cloud registry.</span>
              )}
            </div>

            {isCustomSendingLocked ? (
              <button
                type="button"
                onClick={() => openPaywall({ featureName: "Custom Sending Schedules & Ramp Pacing" })}
                className="flex items-center gap-2 px-8 py-3 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-600 hover:to-amber-700 text-white font-bold rounded-xl transition-all shadow-md shadow-amber-500/20 active:scale-95 cursor-pointer text-xs"
              >
                <Lock size={16} />
                <span>Upgrade to Customize Defaults</span>
              </button>
            ) : (
              <button
                type="button"
                onClick={handleSave}
                disabled={isSaveBlocked}
                className="flex items-center gap-2 px-8 py-3 bg-primary text-primary-foreground font-bold rounded-xl hover:bg-primary/90 transition-all disabled:opacity-40 disabled:cursor-not-allowed shadow-md shadow-primary/20 active:scale-95 text-xs cursor-pointer"
              >
                {saving ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
                {saving ? "Saving Defaults..." : "Save Guardrails & Defaults"}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
