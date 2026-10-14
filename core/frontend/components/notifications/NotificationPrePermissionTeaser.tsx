import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  Bell, Volume2, CheckCircle2, 
  AlertTriangle, X, RotateCw, Check
} from 'lucide-react';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/lib/apiClient';
import { useWorkspace } from '@/contexts/WorkspaceContext';
import { cn } from '@/lib/utils';
import { dispatchDesktopNotification } from '@/lib/desktopNotification';

// ── Synthesized High-Value Audio Chime (Zero External Asset Dependency) ──
// Layer 1 Paranoia: Web Audio API avoids broken CDN URLs, network drops, and 404s.
let lastChimeTimestamp = 0;
const CHIME_COOLDOWN_MS = 4000;

export function playNotificationChime(force: boolean = false) {
  const now = Date.now();
  if (!force && now - lastChimeTimestamp < CHIME_COOLDOWN_MS) {
    return; // Throttled to prevent audio spike when multiple notifications arrive
  }
  lastChimeTimestamp = now;

  try {
    const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
    if (!AudioContextClass) return;

    const ctx = new AudioContextClass();
    if (ctx.state === 'suspended') {
      ctx.resume().catch(() => {});
    }

    const ctxNow = ctx.currentTime;
    
    // First bell tone (D5 - 587.33 Hz)
    const osc1 = ctx.createOscillator();
    const gain1 = ctx.createGain();
    osc1.type = 'sine';
    osc1.frequency.setValueAtTime(587.33, ctxNow);
    gain1.gain.setValueAtTime(0, ctxNow);
    gain1.gain.linearRampToValueAtTime(0.18, ctxNow + 0.02);
    gain1.gain.exponentialRampToValueAtTime(0.001, ctxNow + 0.35);
    osc1.connect(gain1);
    gain1.connect(ctx.destination);
    osc1.start(ctxNow);
    osc1.stop(ctxNow + 0.35);

    // Second cheerful chime (A5 - 880 Hz)
    const osc2 = ctx.createOscillator();
    const gain2 = ctx.createGain();
    osc2.type = 'sine';
    osc2.frequency.setValueAtTime(880, ctxNow + 0.08);
    gain2.gain.setValueAtTime(0, ctxNow + 0.08);
    gain2.gain.linearRampToValueAtTime(0.22, ctxNow + 0.10);
    gain2.gain.exponentialRampToValueAtTime(0.001, ctxNow + 0.55);
    osc2.connect(gain2);
    gain2.connect(ctx.destination);
    osc2.start(ctxNow + 0.08);
    osc2.stop(ctxNow + 0.55);
  } catch (err) {
    // Audio block failure MUST NOT propagate or block UI
    console.debug('[Ele-in Audio] AudioContext suppressed by browser:', err);
  }
}

// ── Custom Hook: Notification Permission & Environmental State ──
export function useNotificationPermission() {
  const getPermission = (): NotificationPermission => {
    if (typeof window === 'undefined') return 'default';
    if (!('Notification' in window)) {
      return 'denied';
    }
    const localEnabled = localStorage.getItem('elein_notifications_enabled') === 'true';
    if (Notification.permission === 'granted' || localEnabled) {
      if (!localEnabled && Notification.permission === 'granted') {
        try {
          localStorage.setItem('elein_notifications_enabled', 'true');
        } catch {}
      }
      return 'granted';
    }
    return Notification.permission;
  };

  const checkDismissed = (): boolean => {
    if (typeof window === 'undefined') return false;
    if (localStorage.getItem('elein_notification_teaser_dismissed') === 'true') return true;
    const snoozedUntil = Number(localStorage.getItem('elein_notification_teaser_snoozed_until') || 0);
    return snoozedUntil > Date.now();
  };

  const [permission, setPermission] = useState<NotificationPermission>(getPermission);
  const [isDismissed, setIsDismissed] = useState<boolean>(checkDismissed);
  const [isSupported, setIsSupported] = useState<boolean>(() => {
    return typeof window !== 'undefined' && 'Notification' in window;
  });
  const [soundEnabled, setSoundEnabled] = useState<boolean>(() => {
    return typeof window !== 'undefined' && localStorage.getItem('elein_audio_chime_enabled') !== 'false';
  });

  const isGranted = permission === 'granted' ||
    (typeof window !== 'undefined' && (
      ('Notification' in window && Notification.permission === 'granted') ||
      localStorage.getItem('elein_notifications_enabled') === 'true'
    ));

  const recheckPermission = useCallback(() => {
    const current = getPermission();
    setPermission(current);
    setIsDismissed(checkDismissed());
    return current;
  }, []);

  const enableNotifications = useCallback(async (): Promise<NotificationPermission> => {
    try {
      localStorage.setItem('elein_notifications_enabled', 'true');
    } catch {}
    setPermission('granted');
    window.dispatchEvent(new CustomEvent('elein-notification-permission-change', { detail: { permission: 'granted' } }));

    if (typeof window !== 'undefined' && 'Notification' in window) {
      try {
        let res: NotificationPermission = 'default';
        if (typeof Notification.requestPermission === 'function') {
          const req = Notification.requestPermission();
          if (req && typeof req.then === 'function') {
            res = await req;
          } else {
            res = await new Promise<NotificationPermission>((resolve) => {
              Notification.requestPermission((p) => resolve(p));
            });
          }
        }
        if (res === 'granted') {
          dispatchDesktopNotification({
            title: "Ele-in Alerts Active",
            body: "Desktop alerts and sound chimes are active for incoming replies.",
            tag: "elein-activation-alert",
          });
        }
        return res;
      } catch (err) {
        console.debug('[Ele-in Notifications] Request permission non-fatal error:', err);
      }
    }
    return 'granted';
  }, []);

  const dismissTeaser = useCallback((dontShowAgain: boolean = true) => {
    try {
      if (dontShowAgain) {
        localStorage.setItem('elein_notification_teaser_dismissed', 'true');
      } else {
        localStorage.setItem('elein_notification_teaser_snoozed_until', String(Date.now() + 7 * 86400000));
      }
    } catch {}
    setIsDismissed(true);
    window.dispatchEvent(new CustomEvent('elein-notification-permission-change'));
  }, []);

  useEffect(() => {
    recheckPermission();

    // 1. Sync on window focus (e.g., returning from browser permission settings)
    const handleFocus = () => recheckPermission();
    window.addEventListener('focus', handleFocus);

    // 2. Sync across components when custom event is dispatched
    const handleCustomEvent = () => recheckPermission();
    window.addEventListener('elein-notification-permission-change', handleCustomEvent);

    // 3. Listen to navigator.permissions status change if supported
    let permissionStatus: PermissionStatus | null = null;
    if (typeof navigator !== 'undefined' && 'permissions' in navigator && navigator.permissions.query) {
      navigator.permissions.query({ name: 'notifications' as PermissionName })
        .then((status) => {
          permissionStatus = status;
          status.addEventListener('change', handleFocus);
        })
        .catch(() => {});
    }

    // 4. Cross-tab storage change sync
    const handleStorage = (e: StorageEvent) => {
      if (
        e.key === 'elein_notifications_enabled' || 
        e.key === 'elein_notification_teaser_dismissed' ||
        e.key === 'elein_notification_teaser_snoozed_until' ||
        e.key === 'elein_audio_chime_enabled'
      ) {
        recheckPermission();
        if (e.key === 'elein_audio_chime_enabled') {
          setSoundEnabled(e.newValue !== 'false');
        }
      }
    };
    window.addEventListener('storage', handleStorage);

    return () => {
      window.removeEventListener('focus', handleFocus);
      window.removeEventListener('elein-notification-permission-change', handleCustomEvent);
      window.removeEventListener('storage', handleStorage);
      if (permissionStatus) {
        permissionStatus.removeEventListener('change', handleFocus);
      }
    };
  }, [recheckPermission]);

  const toggleSound = (enabled: boolean) => {
    setSoundEnabled(enabled);
    localStorage.setItem('elein_audio_chime_enabled', enabled ? 'true' : 'false');
    if (enabled) {
      playNotificationChime();
      toast.success("Audio chime enabled for incoming replies");
    } else {
      toast.info("Audio chime muted");
    }
  };

  return {
    permission,
    isGranted,
    isDismissed,
    isSupported,
    soundEnabled,
    toggleSound,
    recheckPermission,
    enableNotifications,
    dismissTeaser,
    setPermission
  };
}

export interface NotificationTeaserProps {
  workspaceId?: string | null;
  onClose?: () => void;
  variant?: 'modal' | 'card' | 'compact';
}

export function NotificationPrePermissionTeaser({
  workspaceId: propWorkspaceId,
  onClose,
  variant = 'modal'
}: NotificationTeaserProps) {
  const wsContext = useWorkspace();
  const workspaceId = propWorkspaceId || wsContext?.activeWorkspaceId || (typeof window !== 'undefined' ? localStorage.getItem('elein_active_workspace') : null);

  const { 
    permission, 
    isGranted, 
    isSupported, 
    soundEnabled, 
    toggleSound, 
    recheckPermission, 
    enableNotifications,
    dismissTeaser 
  } = useNotificationPermission();
  const [isRequesting, setIsRequesting] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [showUnblockGuide, setShowUnblockGuide] = useState(false);
  const [testSuccess, setTestSuccess] = useState(false);

  // Close modal on Escape key press (Layer 2 Human Paranoia)
  useEffect(() => {
    if (variant !== 'modal') return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && onClose) {
        handleDismiss(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [variant, onClose]);

  // Detect browser for unblock directions
  const browserName = typeof navigator !== 'undefined'
    ? navigator.userAgent.includes('Firefox')
      ? 'Firefox'
      : navigator.userAgent.includes('Safari') && !navigator.userAgent.includes('Chrome')
      ? 'Safari'
      : navigator.userAgent.includes('Edg')
      ? 'Edge'
      : 'Chrome'
    : 'Chrome';

  // ── Send Test Alert (Layer 0, 1 & 2 Paranoia) ──
  const handleTestAlert = async () => {
    if (isTesting) return; // Prevent spamming
    setIsTesting(true);

    if (soundEnabled) {
      playNotificationChime();
    }

    try {
      // 1. Dispatch backend in-app notification if workspace available
      if (workspaceId) {
        await fetchWithAuth(`/api/elein/notifications/test?workspace_id=${workspaceId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ event_type: 'lead_replied_instant', channel: 'in_app' })
        }).catch(() => {});
      }

      // 2. Dispatch native desktop notification if permission is granted
      if (isSupported && isGranted) {
        dispatchDesktopNotification({
          title: "Sarah Lin replied",
          body: "Does your platform handle automatic HubSpot sync and proxy rotation?",
          tag: "elein-test-alert",
          link: "/elein/inbox",
        });
      }

      // 3. Always show interactive sonner toast fallback/confirmation
      toast.success("Test alert fired", {
        description: "Preview chime & notification delivered successfully.",
        duration: 2500
      });
      setTestSuccess(true);
      setTimeout(() => setTestSuccess(false), 2000);
    } catch (err) {
      console.error('[Notification Test Error]', err);
      toast.info("In-app preview chime delivered.");
    } finally {
      setTimeout(() => setIsTesting(false), 1000);
    }
  };

  // ── Request Native Browser Permission Safely (Layer 1 Paranoia) ──
  const handleRequestPermission = async () => {
    if (!isSupported) {
      toast.error("Browser push notifications are not supported in this environment.");
      await enableNotifications();
      return;
    }

    if (permission === 'denied' && typeof window !== 'undefined' && 'Notification' in window && Notification.permission === 'denied') {
      setShowUnblockGuide(true);
      return;
    }

    setIsRequesting(true);
    try {
      const res = await enableNotifications();

      if (res === 'granted' || isGranted) {
        if (soundEnabled) playNotificationChime();
        toast.success("Notifications enabled!", {
          description: "You'll be alerted immediately when prospects reply."
        });

        // Sync preference to workspace backend
        if (workspaceId) {
          fetchWithAuth(`/api/workspaces/${workspaceId}/notification-preferences`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              event_type: 'lead_replied_instant',
              channel: 'in_app',
              enabled: true
            })
          }).catch(() => {});
        }

        // Close teaser modal on success after brief pause
        setTimeout(() => {
          if (onClose) onClose();
        }, 800);
      } else if (res === 'denied') {
        setShowUnblockGuide(true);
      }
    } catch (err) {
      console.error('[Notification Permission Error]', err);
      await enableNotifications();
      if (onClose) onClose();
    } finally {
      setIsRequesting(false);
    }
  };

  const handleDismiss = (dontShowAgain: boolean = false) => {
    dismissTeaser(dontShowAgain);
    if (onClose) onClose();
  };

  // ── Compact Variant (Used in Dashboard & Settings) ──
  if (variant === 'compact') {
    return (
      <div className="flex flex-col gap-3 p-4 rounded-xl bg-card border border-border text-card-foreground">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center shrink-0">
              <Bell size={15} />
            </div>
            <div className="min-w-0">
              <div className="text-xs font-semibold text-foreground flex items-center gap-2">
                <span>Desktop Notifications</span>
              </div>
              <p className="text-[11px] text-muted-foreground truncate mt-0.5">
                Get notified the moment leads reply, even when Ele-in is minimized.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0 w-full sm:w-auto justify-end">
            {isGranted ? (
              <span className="text-xs text-primary flex items-center gap-1 font-medium bg-primary/10 px-2.5 py-1 rounded-lg">
                <CheckCircle2 size={13} />
                <span>Active</span>
              </span>
            ) : (
              <button
                type="button"
                onClick={handleRequestPermission}
                disabled={isRequesting}
                className="px-3 py-1.5 bg-primary hover:bg-primary/90 text-primary-foreground font-medium text-xs rounded-lg transition-colors cursor-pointer disabled:opacity-50"
              >
                {isRequesting ? "Prompting..." : "Enable"}
              </button>
            )}
            {onClose && (
              <button
                type="button"
                onClick={() => handleDismiss(false)}
                className="p-1.5 text-muted-foreground hover:text-foreground rounded-lg transition-colors cursor-pointer"
                title="Dismiss"
              >
                <X size={14} />
              </button>
            )}
          </div>
        </div>

        {/* Audio Chime Row */}
        <div className="flex items-center justify-between border-t border-border/50 pt-2.5 px-0.5">
          <div className="flex items-center gap-2">
            <Volume2 size={14} className="text-muted-foreground" />
            <span className="text-xs text-foreground font-medium">Audio chime on new replies</span>
            <button
              type="button"
              onClick={handleTestAlert}
              disabled={isTesting}
              className="text-[11px] text-muted-foreground hover:text-foreground transition-colors ml-1 cursor-pointer disabled:opacity-50"
              title="Play test chime"
            >
              {testSuccess ? (
                <span className="text-primary font-medium flex items-center gap-0.5"><Check size={11} /> Played</span>
              ) : isTesting ? (
                <span className="flex items-center gap-0.5"><RotateCw size={10} className="animate-spin" /> Playing...</span>
              ) : (
                <span>(Test sound)</span>
              )}
            </button>
          </div>

          <button
            type="button"
            role="switch"
            aria-checked={soundEnabled}
            onClick={() => toggleSound(!soundEnabled)}
            className={cn(
              "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none",
              soundEnabled ? "bg-primary" : "bg-muted-foreground/30"
            )}
            title={soundEnabled ? 'Disable sound' : 'Enable sound'}
          >
            <span
              className={cn(
                "pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-sm ring-0 transition duration-200 ease-in-out",
                soundEnabled ? "translate-x-4" : "translate-x-0"
              )}
            />
          </button>
        </div>
      </div>
    );
  }

  // ── Clean Minimal Modal & Card Content ──
  const content = (
    <div className="flex flex-col gap-4 text-card-foreground">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold tracking-tight text-foreground">
            Never miss an interested prospect reply
          </h2>
          <p className="text-xs text-muted-foreground mt-1 leading-normal">
            Get instant desktop alerts the moment leads respond to your outreach.
          </p>
        </div>
        {onClose && (
          <button 
            type="button" 
            onClick={() => handleDismiss(false)}
            className="p-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer shrink-0"
            title="Close"
          >
            <X size={16} />
          </button>
        )}
      </div>

      {/* Native Notification Preview */}
      <div className="rounded-xl bg-muted/30 border border-border/60 p-3 flex items-start gap-3 transition-colors">
        <div className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center shrink-0 mt-0.5">
          <Bell size={15} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-semibold text-foreground truncate">Sarah Lin replied</span>
            <span className="text-[10px] text-muted-foreground font-mono">Just now</span>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2 leading-relaxed">
            &quot;Hey! Does your platform handle automatic HubSpot sync and proxy rotation?&quot;
          </p>
        </div>
      </div>

      {/* Simple Option: Sound Chime */}
      <div className="flex items-center justify-between py-1 px-0.5">
        <div className="flex items-center gap-2">
          <Volume2 size={15} className="text-muted-foreground" />
          <span className="text-xs text-foreground font-medium">Play sound on new reply</span>
          <button
            type="button"
            onClick={handleTestAlert}
            disabled={isTesting}
            className="text-[11px] text-muted-foreground hover:text-foreground transition-colors ml-1 cursor-pointer disabled:opacity-50"
            title="Play test chime"
          >
            {testSuccess ? (
              <span className="text-primary font-medium flex items-center gap-0.5"><Check size={11} /> Played</span>
            ) : isTesting ? (
              <span className="flex items-center gap-0.5"><RotateCw size={10} className="animate-spin" /> Playing...</span>
            ) : (
              <span>(Test sound)</span>
            )}
          </button>
        </div>

        <button
          type="button"
          role="switch"
          aria-checked={soundEnabled}
          onClick={() => toggleSound(!soundEnabled)}
          className={cn(
            "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none",
            soundEnabled ? "bg-primary" : "bg-muted-foreground/30"
          )}
          title={soundEnabled ? 'Disable sound' : 'Enable sound'}
        >
          <span
            className={cn(
              "pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-sm ring-0 transition duration-200 ease-in-out",
              soundEnabled ? "translate-x-4" : "translate-x-0"
            )}
          />
        </button>
      </div>

      {/* Unblock Guide Popup (Only when permission was previously denied) */}
      <AnimatePresence>
        {showUnblockGuide && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="p-3 rounded-xl bg-destructive/10 border border-destructive/20 text-foreground text-xs space-y-1.5"
          >
            <div className="flex items-center justify-between font-semibold text-destructive">
              <span className="flex items-center gap-1.5">
                <AlertTriangle size={14} />
                Notifications Blocked in {browserName}
              </span>
              <button 
                type="button" 
                onClick={() => setShowUnblockGuide(false)}
                className="text-muted-foreground hover:text-foreground"
              >
                <X size={13} />
              </button>
            </div>
            <p className="text-[11px] text-muted-foreground leading-relaxed">
              Click the tune/padlock icon on your address bar, set <strong className="text-foreground">Notifications</strong> to &quot;Allow&quot;, then click below:
            </p>
            <div className="pt-1 flex items-center justify-end">
              <button
                type="button"
                onClick={recheckPermission}
                className="px-2.5 py-1 bg-destructive/20 hover:bg-destructive/30 text-destructive rounded-md text-[11px] font-medium transition-colors flex items-center gap-1 cursor-pointer"
              >
                <RotateCw size={11} />
                <span>Re-check Permission</span>
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Footer Actions */}
      <div className="flex items-center justify-end gap-2 pt-2 border-t border-border/50">
        {!isGranted && (
          <button
            type="button"
            onClick={() => handleDismiss(false)}
            className="px-3 py-2 rounded-lg text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
          >
            Remind Me Later
          </button>
        )}

        <button
          type="button"
          onClick={isGranted ? (onClose || (() => {})) : handleRequestPermission}
          disabled={isRequesting}
          className="px-4 py-2 bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-medium rounded-lg transition-colors flex items-center justify-center gap-1.5 cursor-pointer shadow-xs disabled:opacity-50"
        >
          {isGranted ? (
            <>
              <CheckCircle2 size={13} />
              <span>Done</span>
            </>
          ) : (
            <>
              <Bell size={13} />
              <span>{isRequesting ? "Prompting..." : "Enable Notifications"}</span>
            </>
          )}
        </button>
      </div>
    </div>
  );

  if (variant === 'card') {
    return (
      <div className="p-5 sm:p-6 rounded-2xl bg-card border border-border shadow-xl">
        {content}
      </div>
    );
  }

  // Default: Modal variant
  return (
    <div 
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in duration-200"
      onClick={(e) => {
        if (e.target === e.currentTarget && onClose) {
          handleDismiss(false);
        }
      }}
    >
      <motion.div 
        initial={{ opacity: 0, scale: 0.96, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 8 }}
        transition={{ duration: 0.15, ease: 'easeOut' }}
        className="w-full max-w-[420px] max-h-[90vh] overflow-y-auto p-5 sm:p-6 rounded-2xl bg-card border border-border shadow-2xl relative"
      >
        {content}
      </motion.div>
    </div>
  );
}
