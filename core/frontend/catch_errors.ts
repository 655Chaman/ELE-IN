import { captureFrontendError } from './lib/telemetry';

if (typeof window !== 'undefined') {
  window.addEventListener('error', (e) => {
    captureFrontendError(e.error || e.message, {
      filename: e.filename,
      lineno: e.lineno,
      colno: e.colno,
      source: 'window.onerror',
    });
  });

  window.addEventListener('unhandledrejection', (e) => {
    captureFrontendError(e.reason, {
      source: 'window.onunhandledrejection',
    });
  });
}
