import { supabase } from './supabase'

// Layer 2: Extend RequestInit to carry a private retry flag to prevent infinite refresh loops
interface AuthRequestInit extends RequestInit {
  _isRetry?: boolean
}

let refreshPromise: Promise<string | null> | null = null
let lastAuthRedirectTime = 0

async function refreshToken(): Promise<string | null> {
  if (refreshPromise) return refreshPromise
  refreshPromise = supabase.auth.refreshSession()
    .then(({ data }) => data.session?.access_token ?? null)
    .finally(() => { refreshPromise = null })
  return refreshPromise
}

// Layer 0 + Layer 1: Paranoia - Robust API Base URL normalization
const rawApiBase = (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_URL) ? String(import.meta.env.VITE_API_URL).trim() : ''
const API_BASE = rawApiBase ? rawApiBase.replace(/\/+$/, '') : ''

// Global browser network connectivity listeners
if (typeof window !== 'undefined') {
  window.addEventListener('online', () => {
    window.dispatchEvent(new CustomEvent('elein:network-status', { detail: { isOnline: true } }))
  })
  window.addEventListener('offline', () => {
    window.dispatchEvent(new CustomEvent('elein:network-status', { detail: { isOnline: false } }))
  })
}

export function getActiveWorkspaceId(): string | null {
  if (typeof window === 'undefined') return null
  // 1. Explicit URL parameter (highest precedence, allows opening 3 browser tabs locally with ?workspace_id=...)
  try {
    const urlParams = new URLSearchParams(window.location.search)
    const queryWs = urlParams.get('workspace_id')
    if (queryWs) {
      sessionStorage.setItem('elein_tab_workspace', queryWs)
      return queryWs
    }
  } catch (_) {}

  // 2. Tab-isolated sessionStorage
  try {
    const tabWs = sessionStorage.getItem('elein_tab_workspace')
    if (tabWs) return tabWs
  } catch (_) {}

  // 3. Fallback to origin-scoped localStorage
  try {
    return localStorage.getItem('elein_active_workspace')
  } catch (_) {
    return null
  }
}

export function setActiveWorkspaceStorage(workspaceId: string) {
  if (typeof window === 'undefined') return
  try {
    sessionStorage.setItem('elein_tab_workspace', workspaceId)
    localStorage.setItem('elein_active_workspace', workspaceId)
  } catch (_) {}
}

export function clearActiveWorkspaceStorage() {
  if (typeof window === 'undefined') return
  try {
    sessionStorage.removeItem('elein_tab_workspace')
    localStorage.removeItem('elein_active_workspace')
  } catch (_) {}
}

export async function fetchWithAuth(path: string, options: AuthRequestInit = {}) {
  const { data: { session } } = await supabase.auth.getSession()
  const headers = new Headers(options.headers || {})
  
  if (session?.access_token) {
    headers.set('Authorization', `Bearer ${session.access_token}`)
  }
  
  const activeWorkspace = getActiveWorkspaceId()
  if (activeWorkspace) {
    headers.set('X-Workspace-Id', activeWorkspace)
  }
  
  // Layer 0 + 1 + 2: URL Normalization
  // If absolute URL (http:// or https://), use as-is
  // Otherwise, prepend API_BASE (if defined) ensuring clean slash separation
  const resolvedUrl = (path.startsWith('http://') || path.startsWith('https://'))
    ? path
    : `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`

  // Paranoia Layer 1: Network drop and offline interception
  let res: Response
  try {
    res = await fetch(resolvedUrl, { ...options, headers })
  } catch (netErr: any) {
    if (netErr?.name === 'AbortError') {
      throw netErr
    }
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('elein:network-status', {
        detail: { isOnline: false, error: netErr?.message || 'Network unreachable' }
      }))
    }
    const isOffline = typeof navigator !== 'undefined' && !navigator.onLine
    const errMessage = isOffline
      ? "You are currently offline. Changes will resume once your network connection is restored."
      : "Failed to connect to Ele-in server. Please verify your connection or try again shortly."
    throw new Error(errMessage)
  }

  // --- 423: Locked (Workspace Scheduled for Deletion) ---
  if (res.status === 423) {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('elein:workspace-locked', {
        detail: { reason: 'Workspace is scheduled for deletion' }
      }))
    }
    return res
  }

  // --- 401: Token expired — try a single silent refresh then retry ---
  if (res.status === 401 && !options._isRetry) {
    const newAccessToken = await refreshToken()
    if (newAccessToken) {
      // Retry once with the new token
      return fetchWithAuth(path, { ...options, _isRetry: true })
    } else {
      // Session is dead only if Supabase genuinely reports no active session
      const { data: { session: checkSession } } = await supabase.auth.getSession()
      if (!checkSession && typeof window !== 'undefined') {
        const now = Date.now()
        if (now - lastAuthRedirectTime > 10000) {
          lastAuthRedirectTime = now
          clearActiveWorkspaceStorage()
          window.dispatchEvent(new CustomEvent('auth:redirect', { detail: { path: '/login' } }))
        }
      }
      return res
    }
  }

  // --- 402: Payment Required / Out of Credits or Tier-Gated Feature Interceptor ---
  if (res.status === 402) {
    if (typeof window !== 'undefined') {
      try {
        const errJson = await res.clone().json()
        const detail = errJson?.detail
        if (detail?.error === 'FEATURE_TIER_GATED' || detail?.required_tier) {
          window.dispatchEvent(new CustomEvent('elein:paywall-trigger', {
            detail: {
              type: 'tier',
              minTier: detail.required_tier || 'PRO',
              featureName: detail.message || 'Advanced Feature',
              reason: detail.message || 'Tier Upgrade Required'
            }
          }))
          return res
        }
      } catch (_e) {
        // Fall through to credit top-up if not JSON
      }
      window.dispatchEvent(new CustomEvent('elein:paywall-trigger', {
        detail: { type: 'credits', reason: 'Credit balance exhausted' }
      }))
    }
    return res
  }

  // --- 403: Check for structured MFA, Ghost Workspace, or Tier/Campaign Limits ---
  if (res.status === 403) {
    try {
      const errData = await res.clone().json()
      if (errData?.detail?.code === 'MFA_REQUIRED') {
        if (typeof window !== 'undefined') {
          const returnUrl = encodeURIComponent(window.location.pathname + window.location.search);
          window.dispatchEvent(new CustomEvent('auth:redirect', { detail: { path: `/mfa-setup?returnUrl=${returnUrl}` } }))
        }
        return res
      }

      // Paranoia Layer 1: Check for Tier Limits, Campaign Limits, or Credit Exhaustion
      const detailStr = (typeof errData?.detail === 'string' ? errData.detail : JSON.stringify(errData || '')).toLowerCase();
      const isCreditLimit = detailStr.includes('credit') || detailStr.includes('balance');
      const isTierLimit = detailStr.includes('tier') || 
                          detailStr.includes('growth') || 
                          detailStr.includes('pro') || 
                          detailStr.includes('campaign limit') || 
                          detailStr.includes('1 active campaign') ||
                          detailStr.includes('upgrade');

      if (isCreditLimit) {
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('elein:paywall-trigger', {
            detail: { type: 'credits', reason: errData?.detail || 'Credit balance exhausted' }
          }))
        }
        return res
      } else if (isTierLimit) {
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('elein:paywall-trigger', {
            detail: { type: 'tier', reason: errData?.detail || 'Upgrade required to continue' }
          }))
        }
        return res
      }
    } catch (_e) {
      // Response body is not JSON (e.g. plain-text 403 "Not a member") — fall through
    }

    // Paranoia Layer 1 & 2: Stale or Revoked Workspace Mismatch trap (plain-text "Not a member" 403)
    // Never dispatch elein-auth-error for workspace membership mismatches! 
    // Doing so kicks an authenticated user to /login, which detects the active session and bounces
    // back to /elein, causing an infinite auto-refresh redirect loop that wipes modals and state.
    try {
      const errText = await res.clone().text()
      if (errText.includes('Not a member')) {
        clearActiveWorkspaceStorage()
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('workspace:stale', { detail: { reason: 'membership_revoked' } }))
        }
        return res
      }
    } catch (_e) { /* ignore */ }
  }

  // --- 404: Check for Deleted or Non-Existent Workspace ---
  if (res.status === 404) {
    try {
      const errText = await res.clone().text()
      if (errText.includes('Workspace not found') || errText.includes('workspace not found')) {
        clearActiveWorkspaceStorage()
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('workspace:stale', { detail: { reason: 'workspace_not_found' } }))
        }
        return res
      }
    } catch (_e) { /* ignore */ }
  }
  
  return res
}

export const fetcher = (url: string) => fetchWithAuth(url).then(async res => {
  if (!res.ok) {
    const errText = await res.text()
    throw new Error(`API Error ${res.status}: ${errText}`)
  }
  return res.json()
})
