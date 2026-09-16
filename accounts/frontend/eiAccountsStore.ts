import { fetchWithAuth } from "@/lib/apiClient"
import { create } from "zustand"
import { persist } from "zustand/middleware"

export interface LinkedInAccount {
  id: string
  name: string
  profileUrl: string
  cookieJson: string
  accountStatus: string
  dailyLimit: number
  messageLimit: number
  sent: number
  isWarmup?: boolean
  warmupStartDate?: string
  warmupTargetDays?: number
  warmupMaxConnections?: number
  warmupMaxMessages?: number
  proxyId?: string
  lastHealthCheckAt?: string
  updatedAt?: string
  manualSendSuspected?: boolean
}

interface EIAccountsState {
  accounts: LinkedInAccount[]
  error: string | null
  fetchAccounts: () => Promise<void>
  cancelFetch: () => void
  addAccount: (account: Omit<LinkedInAccount, "id" | "status" | "accountStatus">) => Promise<void>
  removeAccount: (id: string) => Promise<void>
  updateAccount: (id: string, updates: Partial<LinkedInAccount>) => void
  toggleManualMode: (id: string, currentStatus: string) => Promise<void>
  clearManualSendWarning: (id: string) => Promise<void>
}

let fetchController: AbortController | null = null;

export const useHRAccountsStore = create<EIAccountsState>()(
  persist(
    (set, get) => ({
      accounts: [],
      error: null,
      cancelFetch: () => {
        if (fetchController) {
          fetchController.abort()
        }
      },
      fetchAccounts: async () => {
        if (fetchController) {
          fetchController.abort()
        }
        fetchController = new AbortController()
        try {
          const res = await fetchWithAuth("/api/elein/accounts", {
            signal: fetchController.signal
          })
          if (res.ok) {
            const data = await res.json()
            const mapped = data.map((acc: any) => ({
              id: acc.id,
              name: acc.name,
              profileUrl: acc.linkedin_profile_url || "",
              cookieJson: acc.session_cookies_json || "",
              messageLimit: acc.daily_message_limit || 40,
              isWarmup: acc.is_warmup,
              warmupStartDate: acc.warmup_start_date,
              warmupTargetDays: acc.warmup_target_days,
              warmupMaxConnections: acc.warmup_max_connections,
              warmupMaxMessages: acc.warmup_max_messages,
              accountStatus: acc.status,
              proxyId: acc.proxy_id,
              lastHealthCheckAt: acc.last_health_check_at,
              updatedAt: acc.updated_at,
              manualSendSuspected: acc.manual_send_suspected,
            }))
            set({ accounts: mapped, error: null })
          } else {
            set({ error: 'Failed to fetch accounts' })
          }
        } catch (e: any) {
          if (e.name === 'AbortError') return;
          console.error("Failed to fetch accounts", e)
          set({ error: e.message || 'Failed to fetch accounts' })
        }
      },
      addAccount: async (account) => {
        try {
          const payload = {
            name: account.name,
            linkedin_profile_url: account.profileUrl,
            session_cookies_json: account.cookieJson,
            daily_message_limit: account.messageLimit || 40,
            is_warmup: account.isWarmup,
            warmup_target_days: account.warmupTargetDays || 30,
            warmup_max_connections: account.warmupMaxConnections || 20,
            warmup_max_messages: account.warmupMaxMessages || 40,
            proxy_id: account.proxyId,
          }
          const res = await fetchWithAuth("/api/elein/accounts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
          })
          if (res.ok) {
            const data = await res.json()
            set((state) => ({
              accounts: [...state.accounts, { ...account, id: data.id, accountStatus: "ACTIVE", dailyLimit: 20, sent: 0 } as LinkedInAccount],
              error: null
            }))
          } else {
            set({ error: 'Failed to add account' })
          }
        } catch (e: any) {
          console.error("Failed to add account", e)
          set({ error: e.message || 'Failed to add account' })
        }
      },
      removeAccount: async (id) => {
        try {
          const res = await fetchWithAuth(`/api/elein/accounts/${id}`, {
            method: 'DELETE'
          })
          if (!res.ok) {
            throw new Error('Failed to delete account')
          }
          set((state) => ({
            accounts: state.accounts.filter((a) => a.id !== id),
            error: null
          }))
        } catch (e: any) {
          console.error("Failed to remove account", e)
          set({ error: e.message || 'Failed to delete account' })
          throw e
        }
      },
      updateAccount: (id, updates) =>
        set((state) => ({
          accounts: state.accounts.map((a) =>
            a.id === id ? { ...a, ...updates } : a
          ),
        })),
      toggleManualMode: async (id: string, currentStatus: string) => {
        if (currentStatus !== 'ACTIVE' && currentStatus !== 'MANUAL_MODE') {
            return;
        }
        try {
          const newStatus = currentStatus === "MANUAL_MODE" ? "ACTIVE" : "MANUAL_MODE";
          const res = await fetchWithAuth(`/api/elein/accounts/${id}/status`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: newStatus })
          });
          if (res.ok) {
            set({ error: null })
            get().fetchAccounts();
          } else {
            set({ error: 'Failed to toggle manual mode' })
          }
        } catch (e: any) {
          console.error("Failed to toggle manual mode", e);
          set({ error: e.message || 'Failed to toggle manual mode' })
        }
      },
      clearManualSendWarning: async (id: string) => {
        try {
          const res = await fetchWithAuth(`/api/elein/accounts/${id}/clear-manual-send-warning`, {
            method: 'POST'
          });
          if (res.ok) {
            set({ error: null })
            get().fetchAccounts();
          } else {
             set({ error: 'Failed to clear manual send warning' })
          }
        } catch (e: any) {
          console.error("Failed to clear manual send warning", e);
          set({ error: e.message || 'Failed to clear manual send warning' })
        }
      }
    }),
    {
      name: "elein-accounts-storage",
      version: 1,
      migrate: (persistedState: any, version: number) => {
        if (version === 0) return { accounts: [], error: null }
        return persistedState
      }
    }
  )
)
