import useSWR from "swr";
import { fetcher } from "@/lib/apiClient";

export function useWorkspaceData(workspaceId: string | null) {
  const { data, error, mutate, isLoading } = useSWR(
    workspaceId ? `/api/elein/workspaces/me?ws=${workspaceId}` : null,
    fetcher
  );
  
  return {
    data,
    error,
    mutate,
    isLoading
  };
}
