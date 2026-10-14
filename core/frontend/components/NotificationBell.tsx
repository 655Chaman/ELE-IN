import { useState, useRef, useEffect } from 'react';
import useSWR from 'swr';
import { Bell, CheckCheck, Check, Settings, X } from 'lucide-react';
import { fetcher, fetchWithAuth } from '@/lib/apiClient';
import { supabase } from '@/lib/supabase';
import { useAuth } from '@/lib/AuthContext';
import { useWorkspace } from '@/contexts/WorkspaceContext';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import { toast } from 'sonner';
import { formatDistanceToNow } from 'date-fns';
import { 
  NotificationPrePermissionTeaser, 
  useNotificationPermission,
  playNotificationChime 
} from '@/components/notifications/NotificationPrePermissionTeaser';
import { dispatchDesktopNotification } from '@/lib/desktopNotification';

function formatRelativeTime(isoString?: string): string {
  if (!isoString) return '';
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return '';
    return formatDistanceToNow(d, { addSuffix: true });
  } catch {
    return '';
  }
}

export function NotificationBell() {
  const [isOpen, setIsOpen] = useState(false);
  const [showTeaserModal, setShowTeaserModal] = useState(false);
  const [filter, setFilter] = useState<'all' | 'unread'>('all');
  const dropdownRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const { user } = useAuth();
  const { activeWorkspaceId } = useWorkspace();

  const { 
    isGranted, 
    isDismissed, 
    soundEnabled,
    recheckPermission, 
    enableNotifications, 
    dismissTeaser 
  } = useNotificationPermission();

  const showBanner = !isGranted && !isDismissed;

  // ── Flaw 13: SWR Cache Key isolated per workspace ──
  const swrKey = activeWorkspaceId 
    ? `/api/elein/notifications?workspace_id=${activeWorkspaceId}` 
    : '/api/elein/notifications';

  const { data: notifications, mutate } = useSWR(swrKey, fetcher, {
    refreshInterval: 30000,
    revalidateOnFocus: true
  });

  // Track known notification IDs keyed by workspace to prevent false alarms on workspace switch
  const prevNotificationIdsRef = useRef<Map<string, Set<string>>>(new Map());

  // ── Flaw 1, 11 & 13: Polling Delta Audio Chimes & Desktop Alerts ──
  useEffect(() => {
    if (!notifications || !Array.isArray(notifications)) return;
    const currentWsKey = activeWorkspaceId || 'default';

    // First mount for this workspace: populate set silently so pre-existing alerts do not chime
    if (!prevNotificationIdsRef.current.has(currentWsKey)) {
      prevNotificationIdsRef.current.set(currentWsKey, new Set(notifications.map((n: any) => n.id)));
      return;
    }

    const knownSet = prevNotificationIdsRef.current.get(currentWsKey)!;
    const incomingNew = notifications.filter(
      (n: any) => !n.read_at && !knownSet.has(n.id)
    );

    // Register all current IDs in known set
    notifications.forEach((n: any) => knownSet.add(n.id));

    if (incomingNew.length > 0) {
      if (soundEnabled) {
        playNotificationChime();
      }

      if (isGranted) {
        const newest = incomingNew[0];
        dispatchDesktopNotification({
          title: newest.title || "New Prospect Reply",
          body: newest.body || "A lead has responded to your outreach.",
          tag: `elein-${newest.id}`,
          link: newest.link || '/elein/inbox',
          onClick: () => markReadAndNavigate(newest),
        });
      }
    }
  }, [notifications, activeWorkspaceId, isGranted, soundEnabled]);

  // ── Flaw 2: Low-Latency Supabase Realtime Push (<1s) ──
  useEffect(() => {
    if (!activeWorkspaceId) return;

    const channelName = `realtime:notifications:${activeWorkspaceId}`;
    const channel = supabase
      .channel(channelName)
      .on(
        'postgres_changes',
        {
          event: '*',
          schema: 'public',
          table: 'notifications',
          filter: `workspace_id=eq.${activeWorkspaceId}`
        },
        (payload) => {
          if (payload.eventType === 'INSERT') {
            const newNotif = payload.new as any;
            if (!newNotif) return;
            // Ignore if notification is designated for a different user in the workspace
            if (user?.id && newNotif.user_id && newNotif.user_id !== user.id) {
              return;
            }

            const currentWsKey = activeWorkspaceId || 'default';
            let knownSet = prevNotificationIdsRef.current.get(currentWsKey);
            if (!knownSet) {
              knownSet = new Set<string>();
              prevNotificationIdsRef.current.set(currentWsKey, knownSet);
            }

            if (knownSet.has(newNotif.id)) return;
            knownSet.add(newNotif.id);

            // Optimistically prepend to SWR list
            mutate((current: any[] = []) => {
              if (current.some(n => n.id === newNotif.id)) return current;
              return [newNotif, ...current];
            }, false);

            if (soundEnabled) {
              playNotificationChime();
            }

            if (isGranted) {
              dispatchDesktopNotification({
                title: newNotif.title || "New Prospect Reply",
                body: newNotif.body || "A lead has responded to your outreach.",
                tag: `elein-${newNotif.id}`,
                link: newNotif.link || '/elein/inbox',
                onClick: () => markReadAndNavigate(newNotif),
              });
            }
          } else if (payload.eventType === 'UPDATE') {
            const updated = payload.new as any;
            if (!updated) return;
            mutate((current: any[] = []) => {
              return current.map(n => n.id === updated.id ? { ...n, ...updated } : n);
            }, false);
          }
        }
      )
      .subscribe((status) => {
        if (status === 'CHANNEL_ERROR') {
          console.warn('[Supabase Realtime Notifications] Channel error, falling back to 30s SWR polling');
        }
      });

    return () => {
      supabase.removeChannel(channel);
    };
  }, [activeWorkspaceId, user?.id, isGranted, soundEnabled, mutate]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const unreadCount = notifications?.filter((n: any) => !n.read_at).length || 0;

  const handleOpen = () => {
    setIsOpen(!isOpen);
    if (!isOpen) {
      recheckPermission();
      mutate();
    }
  };

  const handleEnableFromBanner = async () => {
    await enableNotifications();
    toast.success("Desktop alerts enabled!");
  };

  // ── Flaw 9: Instant Optimistic "Read All" ──
  const markAllRead = async () => {
    if (!notifications || unreadCount === 0) return;

    const nowIso = new Date().toISOString();
    const updated = notifications.map((n: any) => ({ ...n, read_at: n.read_at || nowIso }));
    
    // Instantly zero out badges and unread highlights in the UI
    mutate(updated, false);

    try {
      const readAllUrl = '/api/elein/notifications/read-all' + (activeWorkspaceId ? `?workspace_id=${activeWorkspaceId}` : '');
      await fetchWithAuth(readAllUrl, { method: 'POST' });
    } catch (err) {
      console.error('[Notification Read All Error]', err);
      mutate(); // Revalidate from backend if failed
    }
  };

  // ── Flaw 14: Inline Single Notification "Mark Read" Action ──
  const markSingleRead = async (e: React.MouseEvent, notif: any) => {
    e.stopPropagation();
    e.preventDefault();
    if (notif.read_at) return;

    const nowIso = new Date().toISOString();
    mutate(
      (current: any[] = []) => current.map(n => n.id === notif.id ? { ...n, read_at: nowIso } : n),
      false
    );

    try {
      const wsParam = activeWorkspaceId || notif.workspace_id;
      const readUrl = `/api/elein/notifications/${notif.id}/read` + (wsParam ? `?workspace_id=${wsParam}` : '');
      await fetchWithAuth(readUrl, { method: "POST" });
    } catch (err) {
      console.debug('[Notification Mark Single Read Error]', err);
      mutate();
    }
  };

  // ── Flaw 7 & 8: Non-blocking Optimistic Navigation & Safe URL Routing ──
  const markReadAndNavigate = (notif: any) => {
    if (!notif.read_at && notifications) {
      const nowIso = new Date().toISOString();
      mutate(
        notifications.map((n: any) => n.id === notif.id ? { ...n, read_at: nowIso } : n),
        false
      );
      const wsParam = activeWorkspaceId || notif.workspace_id;
      const readUrl = `/api/elein/notifications/${notif.id}/read` + (wsParam ? `?workspace_id=${wsParam}` : '');
      fetchWithAuth(readUrl, { method: "POST" })
        .catch(err => console.debug('[Notification Mark Read Error]', err));
    }

    setIsOpen(false);

    const link = notif.link;
    if (link) {
      if (link.startsWith('http://') || link.startsWith('https://')) {
        window.open(link, '_blank', 'noopener,noreferrer');
      } else {
        navigate(link);
      }
    } else {
      navigate('/elein/inbox');
    }
  };

  const displayedNotifications = (notifications || []).filter((n: any) => {
    if (filter === 'unread') return !n.read_at;
    return true;
  });

  return (
    <>
      <div className="relative" ref={dropdownRef}>
        <button 
          onClick={handleOpen}
          className="relative p-2 rounded-full hover:bg-muted/50 transition-colors cursor-pointer text-foreground/80 hover:text-foreground"
          title="Notifications"
        >
          <Bell size={20} />
          {unreadCount > 0 && (
            <span className="absolute top-1 right-1 w-2.5 h-2.5 bg-destructive rounded-full border-2 border-background animate-pulse" />
          )}
        </button>

        <AnimatePresence>
          {isOpen && (
            <motion.div 
              initial={{ opacity: 0, y: 10, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 10, scale: 0.95 }}
              className="absolute right-0 mt-2 w-84 sm:w-96 max-w-[calc(100vw-1.5rem)] bg-card border border-border rounded-2xl shadow-2xl z-50 overflow-hidden text-card-foreground"
            >
              {/* Header */}
              <div className="p-3.5 border-b border-border bg-card flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <h3 className="font-semibold text-sm text-foreground">Notifications</h3>
                  {unreadCount > 0 && (
                    <span className="text-[10px] font-medium bg-primary/10 text-primary border border-primary/20 px-2 py-0.5 rounded-full">
                      {unreadCount} unread
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1.5">
                  {unreadCount > 0 && (
                    <button
                      type="button"
                      onClick={markAllRead}
                      className="text-[11px] text-muted-foreground hover:text-foreground flex items-center gap-1 px-2 py-1 rounded hover:bg-muted/50 transition-colors cursor-pointer"
                      title="Mark all as read"
                    >
                      <CheckCheck size={12} />
                      <span>Read All</span>
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => {
                      setIsOpen(false);
                      setShowTeaserModal(true);
                    }}
                    className="p-1 text-muted-foreground hover:text-foreground hover:bg-muted/50 rounded transition-colors cursor-pointer"
                    title="Configure notification channels & test alerts"
                  >
                    <Settings size={14} />
                  </button>
                </div>
              </div>

              {/* Sub-header Filter Tabs (All / Unread) */}
              {notifications && notifications.length > 0 && (
                <div className="px-3.5 py-1.5 border-b border-border/40 bg-muted/20 flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => setFilter('all')}
                    className={`text-[11px] font-medium px-2 py-0.5 rounded-md transition-colors cursor-pointer ${
                      filter === 'all'
                        ? 'bg-background text-foreground shadow-xs border border-border/50'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    All ({notifications.length})
                  </button>
                  <button
                    type="button"
                    onClick={() => setFilter('unread')}
                    className={`text-[11px] font-medium px-2 py-0.5 rounded-md transition-colors cursor-pointer flex items-center gap-1 ${
                      filter === 'unread'
                        ? 'bg-background text-foreground shadow-xs border border-border/50'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    <span>Unread</span>
                    {unreadCount > 0 && (
                      <span className="text-[9px] px-1 py-0.2 bg-primary/10 text-primary font-semibold rounded">
                        {unreadCount}
                      </span>
                    )}
                  </button>
                </div>
              )}

              {/* Pre-Permission Teaser Banner (Only shown if ungranted and not dismissed) */}
              {showBanner && (
                <div className="px-3.5 py-2.5 bg-muted/40 border-b border-border flex items-center justify-between gap-3 transition-colors">
                  <div className="flex items-center gap-2.5 min-w-0 flex-1">
                    <div className="w-6 h-6 rounded-md bg-primary/10 text-primary flex items-center justify-center shrink-0 border border-primary/20">
                      <Bell size={12} />
                    </div>
                    <p className="text-xs text-muted-foreground truncate font-normal">
                      Get desktop alerts when prospects reply
                    </p>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <button
                      type="button"
                      onClick={handleEnableFromBanner}
                      className="px-2.5 py-1 bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-medium rounded-lg transition-colors cursor-pointer shadow-xs"
                    >
                      Enable
                    </button>
                    <button
                      type="button"
                      onClick={() => dismissTeaser(true)}
                      className="p-1 text-muted-foreground hover:text-foreground rounded transition-colors cursor-pointer"
                      title="Dismiss"
                    >
                      <X size={13} />
                    </button>
                  </div>
                </div>
              )}

              {/* Notifications List */}
              <div className="max-h-96 overflow-y-auto">
                {(!notifications || notifications.length === 0) ? (
                  <div className="p-6 text-center text-xs text-muted-foreground">
                    No notifications yet.
                  </div>
                ) : displayedNotifications.length === 0 ? (
                  <div className="p-6 text-center text-xs text-muted-foreground">
                    No unread notifications.
                  </div>
                ) : (
                  <div className="flex flex-col">
                    {displayedNotifications.map((notif: any) => (
                      <div
                        key={notif.id}
                        role="button"
                        tabIndex={0}
                        onClick={() => markReadAndNavigate(notif)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            markReadAndNavigate(notif);
                          }
                        }}
                        className={`group relative text-left p-3.5 border-b border-border/50 hover:bg-muted/40 transition-colors flex items-start gap-3 cursor-pointer ${
                          !notif.read_at ? 'bg-primary/5' : ''
                        }`}
                      >
                        <div className="flex-1 space-y-1 min-w-0">
                          <p className={`text-xs sm:text-sm truncate ${!notif.read_at ? 'font-semibold text-foreground' : 'text-foreground/80'}`}>
                            {notif.title}
                          </p>
                          <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
                            {notif.body}
                          </p>
                          <div className="flex items-center gap-2 pt-0.5">
                            <span className="text-[10px] text-muted-foreground/70 font-mono">
                              {formatRelativeTime(notif.created_at)}
                            </span>
                            {notif.event_type && (
                              <span className="text-[9px] uppercase tracking-wider font-mono text-muted-foreground/50">
                                • {notif.event_type.replace(/_/g, ' ')}
                              </span>
                            )}
                          </div>
                        </div>

                        <div className="shrink-0 flex items-center gap-1.5 mt-0.5">
                          {!notif.read_at ? (
                            <>
                              <button
                                type="button"
                                onClick={(e) => markSingleRead(e, notif)}
                                className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded-md hover:bg-background text-muted-foreground hover:text-foreground cursor-pointer shadow-xs border border-transparent hover:border-border"
                                title="Mark as read"
                              >
                                <Check size={12} strokeWidth={2.5} />
                              </button>
                              <div className="group-hover:hidden w-2 h-2 bg-primary rounded-full" />
                            </>
                          ) : null}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {showTeaserModal && (
        <NotificationPrePermissionTeaser 
          onClose={() => setShowTeaserModal(false)} 
          variant="modal" 
          workspaceId={activeWorkspaceId}
        />
      )}
    </>
  );
}
