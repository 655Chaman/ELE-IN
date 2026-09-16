import { fetcher } from './apiClient'
import useSWR from 'swr';

;
const API_BASE = "/api/pipelines";

export function useDynamicMarkets() {
  const { data: dynamicCategories, error, isLoading } = useSWR(`${API_BASE}/markets`, fetcher);

  const getMarketConfig = (marketId: string) => {
    if (!dynamicCategories) return null;
    for (const cat of dynamicCategories) {
      for (const m of cat.markets) {
        if (m.id === marketId) {
          return m;
        }
      }
    }
    return null;
  };

  const getMarketsList = () => {
    if (!dynamicCategories) return [];
    const markets: any[] = [];
    dynamicCategories.forEach((cat: any) => {
      cat.markets.forEach((m: any) => {
        markets.push({
          id: m.id,
          title: m.title,
          subtitle: m.sourceLabel,
          category: m.sourceCategory,
          demandTarget: m.demandTarget,
          supplyTarget: m.supplyTarget
        });
      });
    });
    return markets;
  };

  return {
    dynamicCategories,
    getMarketConfig,
    getMarketsList,
    isLoading,
    error
  };
}
