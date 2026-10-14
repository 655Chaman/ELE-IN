import { supabase } from './supabase'

// Layer 2: Extend RequestInit to carry a private retry flag to prevent infinite refresh loops
interface AuthRequestInit extends RequestInit {
  _isRetry?: boolean
}

let refreshPromise: Promise<string | null> | null = null

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

export async function fetchWithAuth(path: string, options: AuthRequestInit = {}) {
  const { data: { session } } = await supabase.auth.getSession()
  const headers = new Headers(options.headers || {})
  
  if (session?.access_token) {
    headers.set('Authorization', `Bearer ${session.access_token}`)
  }
  
  const activeWorkspace = localStorage.getItem('elein_active_workspace')
  if (activeWorkspace) {
    headers.set('X-Workspace-Id', activeWorkspace)
  }
  
  // Layer 0 + 1 + 2: URL Normalization
  // If absolute URL (http:// or https://), use as-is
  // Otherwise, prepend API_BASE (if defined) ensuring clean slash separation
  const resolvedUrl = (path.startsWith('http://') || path.startsWith('https://'))
    ? path
    : `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`

  const res = await fetch(resolvedUrl, { ...options, headers })

  // --- 401: Token expired — try a single silent refresh then retry ---
  if (res.status === 401 && !options._isRetry) {
    const newAccessToken = await refreshToken()
    if (newAccessToken) {
      // Retry once with the new token
      return fetchWithAuth(path, { ...options, _isRetry: true })
    } else {
      // Session is permanently dead — clear ghost state and redirect to login
      if (typeof window !== 'undefined') {
        localStorage.removeItem('elein_active_workspace')
        window.dispatchEvent(new CustomEvent('auth:redirect', { detail: { path: '/login' } }))
      }
      return res
    }
  }

  // --- 402: Payment Required / Out of Credits Interceptor ---
  if (res.status === 402) {
    if (typeof window !== 'undefined') {
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

    // Existing Ghost Workspace Lockout trap: plain-text "Not a member" 403
    try {
      const errText = await res.clone().text()
      if (errText.includes('Not a member')) {
        localStorage.removeItem('elein_active_workspace')
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new Event('elein-auth-error'))
        }
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
