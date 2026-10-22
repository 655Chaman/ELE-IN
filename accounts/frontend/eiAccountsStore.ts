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
  cookieExpiresAt?: string
  healthScore?: number
  autoHealStatus?: string
  tags?: string[]
}

interface EIAccountsState {
  accounts: LinkedInAccount[]
  error: string | null
  isTogglingManualMode: Record<string, boolean>
  fetchAccounts: () => Promise<void>
  cancelFetch: () => void
  clearAccounts: () => void
  addAccount: (account: Omit<LinkedInAccount, "id" | "status" | "accountStatus">) => Promise<void>
  removeAccount: (id: string, force?: boolean) => Promise<void>
  updateAccount: (id: string, updates: Partial<LinkedInAccount>) => Promise<void>
  toggleWarmup: (id: string, isWarmup: boolean) => Promise<void>
  toggleManualMode: (id: string, currentStatus: string) => Promise<void>
  bulkToggleManualMode: (ids: string[], targetStatus: "ACTIVE" | "MANUAL_MODE") => Promise<{ succeeded: string[]; failed: string[] }>
  clearManualSendWarning: (id: string) => Promise<void>
  autoHealAccount: (id: string) => Promise<any>
  fleetHeal: () => Promise<any>
  renewSession: (id: string, cookieJson: string) => Promise<any>
}

let fetchController: AbortController | null = null;

export const useHRAccountsStore = create<EIAccountsState>()(
  persist(
    (set, get) => ({
      accounts: [],
      error: null,
      isTogglingManualMode: {},
      cancelFetch: () => {
        if (fetchController) {
          fetchController.abort()
        }
      },
      clearAccounts: () => {
        set({ accounts: [], error: null })
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
              cookieJson: "",
              dailyLimit: acc.daily_connection_limit || 20,
              messageLimit: acc.daily_message_limit || 40,
              sent: acc.actions_today || 0,
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
              cookieExpiresAt: acc.cookie_expires_at,
              healthScore: acc.health_score,
              autoHealStatus: acc.auto_heal_status,
              tags: acc.tags || [],
            }))
            set({ accounts: mapped, error: null })
          } else {
            const err = await res.json().catch(() => null)
            set({ error: err?.detail || 'Failed to fetch accounts' })
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
            daily_connection_limit: account.dailyLimit || 20,
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
            set({ error: null })
            await get().fetchAccounts()
          } else {
            const err = await res.json().catch(() => null)
            const detail = err?.detail || err?.error || 'Failed to add account'
            set({ error: detail })
            throw new Error(detail)
          }
        } catch (e: any) {
          console.error("Failed to add account", e)
          set({ error: e.message || 'Failed to add account' })
          throw e
        }
      },
      removeAccount: async (id: string, force: boolean = false) => {
        try {
          const url = force ? `/api/elein/accounts/${id}?force=true` : `/api/elein/accounts/${id}`
          const res = await fetchWithAuth(url, {
            method: 'DELETE'
          })
          if (!res.ok) {
            const err = await res.json().catch(() => null)
            const detail = err?.detail || 'Failed to delete account'
            set({ error: detail })
            throw new Error(detail)
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
      updateAccount: async (id, updates) => {
        try {
          const payload: any = {}
          if (updates.name !== undefined) payload.name = updates.name
          if (updates.dailyLimit !== undefined) payload.daily_connection_limit = updates.dailyLimit
          if (updates.messageLimit !== undefined) payload.daily_message_limit = updates.messageLimit
          if (updates.proxyId !== undefined) payload.proxy_id = updates.proxyId

          const res = await fetchWithAuth(`/api/elein/accounts/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          })

          if (!res.ok) {
            const err = await res.json().catch(() => null)
            const detail = err?.detail || 'Failed to update account settings'
            set({ error: detail })
            throw new Error(detail)
          }

          set((state) => ({
            accounts: state.accounts.map((a) =>
              a.id === id ? { ...a, ...updates, proxyId: updates.proxyId === 'none' ? undefined : (updates.proxyId ?? a.proxyId) } : a
            ),
            error: null
          }))
          await get().fetchAccounts()
        } catch (e: any) {
          console.error("Failed to update account", e)
          set({ error: e.message || 'Failed to update account settings' })
          throw e
        }
      },
      toggleWarmup: async (id: string, isWarmup: boolean) => {
        try {
          const res = await fetchWithAuth(`/api/elein/accounts/${id}/warmup`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_warmup: isWarmup })
          });
          if (res.ok) {
            set((state) => ({
              accounts: state.accounts.map((a) =>
                a.id === id ? { ...a, isWarmup } : a
              ),
              error: null
            }));
          } else {
            const err = await res.json().catch(() => null);
            const detail = err?.detail || 'Failed to update warmup status';
            set({ error: detail });
            throw new Error(detail);
          }
        } catch (e: any) {
          console.error("Failed to toggle warmup", e);
          set({ error: e.message || 'Failed to toggle warmup' });
          throw e;
        }
      },
      toggleManualMode: async (id: string, currentStatus: string) => {
        if (currentStatus !== 'ACTIVE' && currentStatus !== 'MANUAL_MODE') {
            return;
        }
        if (get().isTogglingManualMode[id]) {
          return;
        }
        set((state) => ({
          isTogglingManualMode: { ...state.isTogglingManualMode, [id]: true }
        }));
        try {
          const newStatus = currentStatus === "MANUAL_MODE" ? "ACTIVE" : "MANUAL_MODE";
          const res = await fetchWithAuth(`/api/elein/accounts/${id}/status`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: newStatus })
          });
          if (res.ok) {
            set((state) => ({
              accounts: state.accounts.map((a) =>
                a.id === id ? { ...a, accountStatus: newStatus } : a
              ),
              error: null
            }))
            await get().fetchAccounts();
          } else {
            const err = await res.json().catch(() => null)
            const detail = err?.detail || 'Failed to toggle manual mode'
            set({ error: detail })
            throw new Error(detail)
          }
        } catch (e: any) {
          console.error("Failed to toggle manual mode", e);
          set({ error: e.message || 'Failed to toggle manual mode' })
          throw e
        } finally {
          set((state) => ({
            isTogglingManualMode: { ...state.isTogglingManualMode, [id]: false }
          }));
        }
      },
      bulkToggleManualMode: async (ids: string[], targetStatus: "ACTIVE" | "MANUAL_MODE") => {
        if (!ids || ids.length === 0) {
          return { succeeded: [], failed: [] };
        }

        const currentAccounts = get().accounts;
        const currentToggling = get().isTogglingManualMode;
        const eligibleIds = ids.filter((id) => {
          if (currentToggling[id]) return false;
          const acc = currentAccounts.find((a) => a.id === id);
          if (!acc) return false;
          if (targetStatus === "MANUAL_MODE") return acc.accountStatus === "ACTIVE";
          if (targetStatus === "ACTIVE") return acc.accountStatus === "MANUAL_MODE";
          return false;
        });

        if (eligibleIds.length === 0) {
          return { succeeded: [], failed: [] };
        }

        set((state) => {
          const nextToggling = { ...state.isTogglingManualMode };
          for (const id of eligibleIds) {
            nextToggling[id] = true;
          }
          return { isTogglingManualMode: nextToggling };
        });

        const succeeded: string[] = [];
        const failed: string[] = [];

        try {
          const results = await Promise.allSettled(
            eligibleIds.map(async (id) => {
              const res = await fetchWithAuth(`/api/elein/accounts/${id}/status`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ status: targetStatus })
              });
              if (!res.ok) {
                const err = await res.json().catch(() => null);
                throw new Error(err?.detail || `Failed to set status for ${id}`);
              }
              return id;
            })
          );

          results.forEach((res, idx) => {
            const id = eligibleIds[idx];
            if (res.status === "fulfilled") {
              succeeded.push(id);
            } else {
              failed.push(id);
              console.error(`Bulk status update failed for ${id}:`, res.reason);
            }
          });

          if (succeeded.length > 0) {
            set((state) => ({
              accounts: state.accounts.map((a) =>
                succeeded.includes(a.id) ? { ...a, accountStatus: targetStatus } : a
              ),
              error: null
            }));
            await get().fetchAccounts();
          }
        } catch (e: any) {
          console.error("Bulk toggle manual mode error", e);
          set({ error: e.message || "Failed bulk status update" });
        } finally {
          set((state) => {
            const nextToggling = { ...state.isTogglingManualMode };
            for (const id of eligibleIds) {
              delete nextToggling[id];
            }
            return { isTogglingManualMode: nextToggling };
          });
        }

        return { succeeded, failed };
      },
      clearManualSendWarning: async (id: string) => {
        try {
          const res = await fetchWithAuth(`/api/elein/accounts/${id}/clear-manual-send-warning`, {
            method: 'POST'
          });
          if (res.ok) {
            set({ error: null })
            await get().fetchAccounts();
          } else {
            const err = await res.json().catch(() => null)
            const detail = err?.detail || 'Failed to clear manual send warning'
            set({ error: detail })
            throw new Error(detail)
          }
        } catch (e: any) {
          console.error("Failed to clear manual send warning", e);
          set({ error: e.message || 'Failed to clear manual send warning' })
          throw e
        }
      },
      autoHealAccount: async (id: string) => {
        try {
          const res = await fetchWithAuth(`/api/elein/accounts/${id}/auto-heal`, {
            method: "POST"
          })
          if (res.ok) {
            const data = await res.json()
            get().fetchAccounts()
            return data
          } else {
            const err = await res.json().catch(() => null)
            throw new Error(err?.detail || "Auto-heal failed")
          }
        } catch (e: any) {
          console.error("Auto-heal error:", e)
          throw e
        }
      },
      fleetHeal: async () => {
        try {
          const res = await fetchWithAuth(`/api/elein/accounts/fleet-heal`, {
            method: "POST"
          })
          if (res.ok) {
            const data = await res.json()
            get().fetchAccounts()
            return data
          } else {
            const err = await res.json().catch(() => null)
            throw new Error(err?.detail || "Fleet heal failed")
          }
        } catch (e: any) {
          console.error("Fleet heal error:", e)
          throw e
        }
      },
      renewSession: async (id: string, cookieJson: string) => {
        try {
          const res = await fetchWithAuth(`/api/elein/accounts/${id}/renew-session`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_cookies_json: cookieJson })
          })
          if (res.ok) {
            const data = await res.json()
            get().fetchAccounts()
            return data
          } else {
            const err = await res.json().catch(() => null)
            throw new Error(err?.detail || "Failed to renew session")
          }
        } catch (e: any) {
          console.error("Renew session error:", e)
          throw e
        }
      }
    }),
    {
      name: "elein-accounts-storage",
      version: 1,
      partialize: () => ({
        // Paranoia Layer 0 & 1: Do not persist live sender accounts in un-scoped localStorage to prevent cross-workspace cache bleed.
        error: null
      }),
      migrate: (persistedState: any, version: number) => {
        if (version === 0) return { accounts: [], error: null }
        return persistedState
      }
    }
  )
)
