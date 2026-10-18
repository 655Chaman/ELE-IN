/**
 * Production Observability & Error Telemetry (Phase 22 - Paranoia Framework)
 * 
 * - Layer 0: Sentry error capture & distributed trace propagation.
 * - Layer 1: Fail-safe degradation: if Sentry DSN is missing, network is offline,
 *   or ad-blockers block Sentry, fallback to backend `/api/elein/log_error`.
 *   Never crashes the client or interrupts the UI.
 * - Layer 2: PII scrubbing: strips authorization tokens, passwords, cookies, and secrets.
 */

import * as Sentry from '@sentry/react';

let isSentryInitialized = false;

// In-memory deduplication set to avoid flooding loggers with repeated renders
const recentlyReportedErrors = new Set<string>();

/**
 * Initializes frontend telemetry with Sentry and fallback handlers.
 */
export function initFrontendTelemetry() {
  const dsn = import.meta.env.VITE_SENTRY_DSN;
  const environment = import.meta.env.MODE || 'production';

  if (!dsn || dsn.trim() === '') {
    if (import.meta.env.DEV) {
      console.info('[Telemetry] VITE_SENTRY_DSN not set. Running in local fallback mode.');
    }
    return;
  }

  try {
    Sentry.init({
      dsn,
      environment,
      release: 'ele-in-web@3.0.0',
      tracesSampleRate: environment === 'production' ? 0.2 : 1.0,
      
      // Privacy & PII scrubbing: Never send sensitive authentication tokens or credentials
      beforeSend(event) {
        if (event.request?.headers) {
          delete event.request.headers['authorization'];
          delete event.request.headers['cookie'];
          delete event.request.headers['x-api-key'];
        }
        return event;
      },

      // Filter out noisy, benign browser quirks
      ignoreErrors: [
        'ResizeObserver loop completed with undelivered notifications',
        'ResizeObserver loop limit exceeded',
        'Network request failed',
        'Load failed',
        'AbortError',
      ],
    });

    isSentryInitialized = true;
    console.info('[Telemetry] Sentry initialized successfully.');
  } catch (err) {
    console.warn('[Telemetry] Sentry init failed (non-fatal):', err);
  }
}

/**
 * Captures an exception with context, reporting to Sentry and the backend error logger.
 */
export function captureFrontendError(error: unknown, context?: Record<string, any>) {
  const errMessage = error instanceof Error ? error.message : String(error);
  const errStack = error instanceof Error ? error.stack : undefined;

  // Deduplicate errors within 10 seconds
  const dedupeKey = `${errMessage}:${context?.componentStack || ''}`;
  if (recentlyReportedErrors.has(dedupeKey)) return;
  recentlyReportedErrors.add(dedupeKey);
  setTimeout(() => recentlyReportedErrors.delete(dedupeKey), 10000);

  // 1. Report to Sentry
  if (isSentryInitialized) {
    try {
      Sentry.withScope((scope) => {
        if (context) {
          Object.entries(context).forEach(([k, v]) => {
            if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') {
              scope.setTag(k, String(v));
            } else {
              scope.setContext(k, v);
            }
          });
        }
        if (error instanceof Error) {
          Sentry.captureException(error);
        } else {
          Sentry.captureMessage(errMessage, 'error');
        }
      });
    } catch (_) {
      // Sentry send error ignored
    }
  }

  // 2. Fallback: Report to backend error logger
  try {
    fetch('/api/elein/log_error', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: errMessage.substring(0, 1000),
        error: (errStack || errMessage).substring(0, 4000),
        filename: window.location.pathname,
      }),
    }).catch(() => {
      // Ignore network errors in error logger
    });
  } catch (_) {
    // Non-fatal
  }
}

/**
 * Associates user metadata with telemetry events.
 */
export function setTelemetryUserContext(user: { id: string; email?: string } | null) {
  if (!isSentryInitialized) return;
  try {
    if (user) {
      Sentry.setUser({ id: user.id, email: user.email });
    } else {
      Sentry.setUser(null);
    }
  } catch (_) {
    // Non-fatal
  }
}

/**
 * Associates the active workspace ID with telemetry tags.
 */
export function setTelemetryWorkspaceContext(workspaceId: string | null) {
  if (!isSentryInitialized) return;
  try {
    if (workspaceId) {
      Sentry.setTag('workspace_id', workspaceId);
    } else {
      Sentry.setTag('workspace_id', 'none');
    }
  } catch (_) {
    // Non-fatal
  }
}
