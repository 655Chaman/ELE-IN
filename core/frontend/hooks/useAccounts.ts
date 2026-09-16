import useSWR from 'swr'
import { fetcher } from "@/lib/apiClient"
import type { LinkedInAccount } from "@accounts/eiAccountsStore"

export interface UsageData {
  account_id: string
  action_type: string
  count: number
}

export interface WarmupPhase {
  name: string
  [key: string]: any
}

export interface WarmupData {
  phases: WarmupPhase[]
  phase: string
  safety_score: number
  day: number
  daily_limit: number
  allowed_actions: string[]
}

export interface HealthData {
  status: string
  [key: string]: any
}

export interface AccountLimits {
  effective_limit: number
  used_today: number
  is_clamped_by_warmup: boolean
  has_manual_override: boolean
}

/**
 * useAccounts is a standalone hook for components that do NOT use the Zustand store.
 * For the main accounts page, use useHRAccountsStore instead.
 */
export function useAccounts() {
  const { data, error, isLoading, mutate } = useSWR<LinkedInAccount[]>('/api/elein/accounts', fetcher)
  return { accounts: data, isLoading, error, mutate }
}

export function useAccountUsage(accountId?: string) {
  const { data, error, isLoading, mutate } = useSWR<UsageData[]>('/api/elein/accounts/usage', fetcher)
  return { usageData: data, isLoading, error, mutate }
}

export function useWarmupTimeline(accountId: string) {
  const { data, error, isLoading, mutate } = useSWR<WarmupData>(
    accountId ? `/api/elein/accounts/${accountId}/warmup` : null,
    fetcher,
    { refreshInterval: 60000 }
  )
  return { warmupData: data, isLoading, error, mutate }
}

export function useAccountHealth(accountId: string) {
  const { data, error, isLoading, mutate } = useSWR<HealthData>(
    accountId ? `/api/elein/accounts/${accountId}/health` : null,
    fetcher
  )
  return { healthData: data, isLoading, error, mutate }
}

export function useAccountLimits(accountId: string, actionType: string = 'connection_request') {
  const { data, error, isLoading, mutate } = useSWR<AccountLimits>(
    accountId ? `/api/elein/accounts/${accountId}/limits?action_type=${actionType}` : null,
    fetcher
  )
  return { limits: data, isLoading, error, mutate }
}
