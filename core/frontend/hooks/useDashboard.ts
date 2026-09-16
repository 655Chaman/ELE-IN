import { fetchWithAuth, fetcher } from "@/lib/apiClient"
import useSWR from 'swr'

export function useDashboard(activeMarket: string) {
  // Global status map
  const { 
    data: statuses, 
    error: statusError,
    isLoading: statusLoading 
  } = useSWR(`/api/pipelines/status`, fetcher, { refreshInterval: 3000 })

  // Demand data
  const { 
    data: demandLogsData,
    isLoading: demandLogsLoading
  } = useSWR(`/api/pipelines/logs/${activeMarket}_demand?tail=10`, fetcher, { refreshInterval: 3000 })
  
  const { 
    data: demandStats,
    isLoading: demandStatsLoading
  } = useSWR(`/api/pipelines/stats/${activeMarket}/demand`, fetcher, { refreshInterval: 3000 })

  // Supply data
  const { 
    data: supplyLogsData,
    isLoading: supplyLogsLoading
  } = useSWR(`/api/pipelines/logs/${activeMarket}_supply?tail=10`, fetcher, { refreshInterval: 3000 })
  
  const { 
    data: supplyStats,
    isLoading: supplyStatsLoading
  } = useSWR(`/api/pipelines/stats/${activeMarket}/supply`, fetcher, { refreshInterval: 3000 })

  const { 
    data: health,
    error: healthError
  } = useSWR(`/api/pipelines/health`, fetcher, { refreshInterval: 5000 })

  return {
    statuses: statuses || {},
    health: health || {},
    logs: {
      demand: demandLogsData?.lines || [],
      supply: supplyLogsData?.lines || []
    },
    stats: {
      demand: demandStats || null,
      supply: supplyStats || null
    },
    isLoading: statusLoading || demandLogsLoading || demandStatsLoading || supplyLogsLoading || supplyStatsLoading,
    isError: statusError || healthError
  }
}

export interface KeyConfig {
  api_key_apify?: string;
  api_key_mailsso?: string;
  api_key_openai?: string;
  llm_provider?: 'openai' | 'nvidia' | 'openrouter' | 'anthropic' | 'gemini';
  api_key_llm?: string;
  llm_model?: string;
}

export function useKeys() {
  const { data: keys, mutate } = useSWR(`/api/settings/`, fetcher)
  
  const saveKeys = async (newKeys: KeyConfig) => {
    await fetchWithAuth(`/api/settings/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(newKeys)
    })
    mutate(newKeys)
  }

  return {
    keys: (keys as KeyConfig) || { 
      api_key_apify: "", 
      api_key_mailsso: "", 
      api_key_openai: "",
      llm_provider: "openai", 
      api_key_llm: "", 
      llm_model: "" 
    },
    saveKeys
  }
}
