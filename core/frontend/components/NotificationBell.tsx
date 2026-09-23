import { useState, useRef, useEffect } from 'react';
import useSWR from 'swr';
import { Bell, Check } from 'lucide-react';
import { fetcher, fetchWithAuth } from '@/lib/apiClient';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';

export function NotificationBell() {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  const { data: notifications, mutate } = useSWR('/api/elein/notifications', fetcher, {
    refreshInterval: 30000
  });

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
      mutate();
    }
  };

  const markReadAndNavigate = async (notif: any) => {
    if (!notif.read_at) {
      await fetchWithAuth(`/api/elein/notifications/${notif.id}/read`, { method: "POST" });
      mutate();
    }
    setIsOpen(false);
    if (notif.link) {
      navigate(notif.link);
    }
  };

  return (
    <div className="relative" ref={dropdownRef}>
      <button 
        onClick={handleOpen}
        className="relative p-2 rounded-full hover:bg-muted/50 transition-colors"
      >
        <Bell size={20} className="text-foreground/80" />
        {unreadCount > 0 && (
          <span className="absolute top-1 right-1 w-2.5 h-2.5 bg-destructive rounded-full border-2 border-background" />
        )}
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div 
            initial={{ opacity: 0, y: 10, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.95 }}
            className="absolute right-0 mt-2 w-80 bg-background border border-border rounded-xl shadow-xl z-50 overflow-hidden"
          >
            <div className="p-3 border-b border-border bg-muted/20 flex items-center justify-between">
              <h3 className="font-semibold text-sm">Notifications</h3>
              {unreadCount > 0 && (
                <span className="text-xs text-muted-foreground">{unreadCount} unread</span>
              )}
            </div>
            <div className="max-h-96 overflow-y-auto">
              {(!notifications || notifications.length === 0) ? (
                <div className="p-6 text-center text-sm text-muted-foreground">
                  No notifications yet.
                </div>
              ) : (
                <div className="flex flex-col">
                  {notifications.map((notif: any) => (
                    <button
                      key={notif.id}
                      onClick={() => markReadAndNavigate(notif)}
                      className={`text-left p-4 border-b border-border/50 hover:bg-muted/30 transition-colors flex gap-3 ${!notif.read_at ? 'bg-primary/5' : ''}`}
                    >
                      <div className="flex-1 space-y-1">
                        <p className={`text-sm ${!notif.read_at ? 'font-semibold text-foreground' : 'text-foreground/80'}`}>
                          {notif.title}
                        </p>
                        <p className="text-xs text-muted-foreground line-clamp-2">
                          {notif.body}
                        </p>
                        <p className="text-[10px] text-muted-foreground/60 pt-1">
                          {new Date(notif.created_at).toLocaleString()}
                        </p>
                      </div>
                      {!notif.read_at && (
                        <div className="shrink-0 mt-1">
                          <div className="w-2 h-2 bg-primary rounded-full" />
                        </div>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
