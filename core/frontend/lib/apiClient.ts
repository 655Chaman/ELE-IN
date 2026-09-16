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
  
  const res = await fetch(path, { ...options, headers })

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

  // --- 403: Check for structured MFA_REQUIRED code so we can redirect to setup ---
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
