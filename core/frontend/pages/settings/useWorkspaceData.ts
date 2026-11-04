import useSWR from "swr";
import { fetcher } from "@/lib/apiClient";

export interface WorkspaceData {
  id: string;
  name: string;
  status: string;
  require_2fa: boolean;
  created_at: string;
  deletion_requested_at?: string | null;
  tier?: string;
  role?: string;
  is_owner?: boolean;
}

export function useWorkspaceData(workspaceId: string | null) {
  const { data, error, mutate, isLoading } = useSWR<WorkspaceData>(
    workspaceId ? `/api/elein/workspaces/me?workspace_id=${workspaceId}` : null,
    fetcher,
    {
      revalidateOnFocus: false,
      shouldRetryOnError: true,
      errorRetryCount: 3,
    }
  );
  
  return {
    data,
    error,
    mutate,
    isLoading
  };
}
