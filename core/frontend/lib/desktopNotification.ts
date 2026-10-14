/**
 * Ele-in Unified Desktop Notification & Service Worker Dispatcher
 *
 * Implements persistent OS notifications via Service Worker (`registration.showNotification`),
 * ensuring alerts stay active when tabs are minimized, backgrounded, or inactive.
 * Gracefully falls back to standard `new Notification` when Service Workers are unavailable.
 */

export interface DesktopNotificationOptions {
  title: string;
  body?: string;
  tag?: string;
  icon?: string;
  badge?: string;
  link?: string;
  onClick?: () => void;
}

let swRegistrationPromise: Promise<ServiceWorkerRegistration | null> | null = null;

/**
 * Registers the background Service Worker for OS desktop notifications and WebPush.
 * Safe to invoke multiple times (idempotent).
 */
export function registerNotificationServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (typeof window === 'undefined' || !('serviceWorker' in navigator)) {
    return Promise.resolve(null);
  }

  if (swRegistrationPromise) {
    return swRegistrationPromise;
  }

  swRegistrationPromise = navigator.serviceWorker
    .register('/sw.js', { scope: '/' })
    .then((reg) => {
      return reg;
    })
    .catch((err) => {
      console.debug('[Ele-in ServiceWorker] Registration non-fatal note:', err);
      return null;
    });

  return swRegistrationPromise;
}

/**
 * Dispatches a native desktop notification.
 * Prefers the Service Worker (`showNotification`) so notifications stay visible and
 * active even when the browser tab is minimized or running in the background.
 */
export async function dispatchDesktopNotification({
  title,
  body = '',
  tag,
  icon = '/logo-icon.png',
  badge = '/logo-icon.png',
  link = '/elein/inbox',
  onClick,
}: DesktopNotificationOptions): Promise<boolean> {
  if (typeof window === 'undefined' || !('Notification' in window)) {
    return false;
  }

  if (Notification.permission !== 'granted') {
    return false;
  }

  const notificationTag = tag || `elein-${Date.now()}`;

  // 1. Try Service Worker showNotification (works when tab is minimized/backgrounded)
  if ('serviceWorker' in navigator) {
    try {
      // Race getRegistration with a short 300ms timeout to avoid any async delay
      const reg = await Promise.race([
        navigator.serviceWorker.getRegistration('/'),
        new Promise<null>((resolve) => setTimeout(() => resolve(null), 300)),
      ]);

      if (reg && typeof reg.showNotification === 'function') {
        await reg.showNotification(title, {
          body,
          icon,
          badge,
          tag: notificationTag,
          renotify: true,
          data: { url: link },
        } as any);
        return true;
      }
    } catch (swErr) {
      console.debug('[Ele-in Notification SW fallback to window.Notification]', swErr);
    }
  }

  // 2. Fallback to standard window.Notification (for environments without SW or before SW is ready)
  try {
    const fallbackNotif = new Notification(title, {
      body,
      tag: notificationTag,
      icon,
    });

    fallbackNotif.onclick = () => {
      try {
        window.focus();
        if (onClick) {
          onClick();
        } else if (link) {
          window.location.assign(link);
        }
        fallbackNotif.close();
      } catch (clickErr) {
        console.debug('[Ele-in Notification click handler]', clickErr);
      }
    };
    return true;
  } catch (windowNotifErr) {
    console.debug('[Ele-in window.Notification error]', windowNotifErr);
    return false;
  }
}
