import React, { createContext, useContext, useState, useEffect } from 'react';
import { fetcher, fetchWithAuth, getActiveWorkspaceId, setActiveWorkspaceStorage, clearActiveWorkspaceStorage } from "@/lib/apiClient";
import { mutate } from 'swr';
import { useAuth } from '@/lib/AuthContext';
import { setTelemetryWorkspaceContext } from '@/lib/telemetry';

interface Workspace {
  id: string;
  name: string;
  account_count: number;
  status?: string;
  tier?: string;
  is_platform_owner?: boolean;
}

interface AgencyInfo {
  id: string;
  name: string;
  role: string;
}

interface WorkspaceContextType {
  workspaces: Workspace[];
  activeWorkspaceId: string | null;
  activeWorkspace: Workspace | null;
  activeWorkspaceTier: string;
  isFree: boolean;
  isPro: boolean;
  isEnterprise: boolean;
  setActiveWorkspaceId: (id: string) => void;
  refreshWorkspaces: () => Promise<void>;
  createWorkspace: (name: string) => Promise<Workspace>;
  assignAccount: (accountId: string, targetWorkspaceId: string) => Promise<void>;
  isPendingDeletion: boolean;
  myAgencies: AgencyInfo[];
}

export const WorkspaceContext = createContext<WorkspaceContextType | undefined>(undefined);

export const WorkspaceProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { session } = useAuth();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [myAgencies, setMyAgencies] = useState<AgencyInfo[]>([]);
  const [activeWorkspaceId, setActiveWorkspaceIdState] = useState<string | null>(
    getActiveWorkspaceId()
  );

  const fetchWorkspaces = async () => {
    try {
      const data = await fetcher('/api/workspaces');
      setWorkspaces(data);
      if (data.length > 0) {
        const currentId = getActiveWorkspaceId();
        if (currentId && data.some((w: any) => w.id === currentId)) {
          if (currentId !== activeWorkspaceId) {
            setActiveWorkspaceIdState(currentId);
          }
        } else if (currentId) {
          // Paranoia Layer 1 & 2 (FLAW-10): Verify if currentId is an Agency client workspace before resetting
          try {
            const checkWs = await fetcher(`/api/workspaces/${currentId}`);
            if (checkWs && checkWs.id === currentId) {
              if (currentId !== activeWorkspaceId) {
                setActiveWorkspaceIdState(currentId);
              }
              return;
            }
          } catch (e) {
            // Accessible verification failed, proceed to fallback reset
          }
          setActiveWorkspaceId(data[0].id, false);
        } else {
          setActiveWorkspaceId(data[0].id, false);
        }
      } else {
        // Fallback: Hard clear if the user somehow has 0 workspaces (e.g. network drop during signup)
        setActiveWorkspaceIdState(null);
        clearActiveWorkspaceStorage();
      }
    } catch (error) {
      console.error("Failed to fetch workspaces:", error);
    }
  };

  useEffect(() => {
    if (session) {
      fetchWorkspaces();
      fetcher('/api/agencies').then(setMyAgencies).catch(console.error);
    } else {
      setWorkspaces([]);
      setMyAgencies([]);
      clearActiveWorkspaceStorage();
    }
  }, [session]);

  // Paranoia Layer 1 & 2: Listen for workspace:stale from apiClient to recover smoothly without page reloads
  useEffect(() => {
    const handleStaleWorkspace = () => {
      clearActiveWorkspaceStorage();
      if (workspaces.length > 0) {
        setActiveWorkspaceId(workspaces[0].id, true);
      } else {
        fetchWorkspaces();
      }
    };
    window.addEventListener('workspace:stale', handleStaleWorkspace);
    return () => window.removeEventListener('workspace:stale', handleStaleWorkspace);
  }, [workspaces]);

  useEffect(() => {
    setTelemetryWorkspaceContext(activeWorkspaceId);
  }, [activeWorkspaceId]);

  const setActiveWorkspaceId = (id: string, shouldRevalidate: boolean = true) => {
    setActiveWorkspaceIdState(id);
    setActiveWorkspaceStorage(id);
    setTelemetryWorkspaceContext(id);
    if (shouldRevalidate) {
      // Revalidate tenant-scoped queries without aggressively flushing all global keys
      mutate((key: any) => typeof key === 'string' && key.startsWith('/api/elein'), undefined, { revalidate: true });
    }
  };

  const createWorkspace = async (name: string) => {
    const res = await fetchWithAuth('/api/workspaces', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ name })
    });
    const newWs = await res.json();
    await fetchWorkspaces();
    // Automatically switch to the newly created workspace
    setActiveWorkspaceId(newWs.id);
    return newWs;
  };
  
  const assignAccount = async (accountId: string, targetWorkspaceId: string) => {
    await fetchWithAuth('/api/workspaces/assign-account', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ account_id: accountId, target_workspace_id: targetWorkspaceId })
    });
    await fetchWorkspaces();
  };

  const activeWorkspace = workspaces.find(w => w.id === activeWorkspaceId) || null;
  const isPendingDeletion = activeWorkspace?.status === 'pending_deletion';
  const rawTier = (activeWorkspace?.tier || 'FREE').toUpperCase();
  const activeWorkspaceTier = rawTier;
  const isFree = activeWorkspaceTier === 'FREE' || activeWorkspaceTier === 'STARTER' || activeWorkspaceTier === 'BASIC';
  const isEnterprise = activeWorkspaceTier === 'ENTERPRISE' || activeWorkspaceTier === 'AGENCY' || Boolean(activeWorkspace?.is_platform_owner);
  const isPro = activeWorkspaceTier === 'PRO' || activeWorkspaceTier === 'GROWTH' || isEnterprise;

  return (
    <WorkspaceContext.Provider value={{
      workspaces,
      activeWorkspaceId,
      activeWorkspace,
      activeWorkspaceTier,
      isFree,
      isPro,
      isEnterprise,
      setActiveWorkspaceId,
      refreshWorkspaces: fetchWorkspaces,
      createWorkspace,
      assignAccount,
      isPendingDeletion,
      myAgencies
    }}>
      {children}
    </WorkspaceContext.Provider>
  );
};

export const useWorkspace = () => {
  const context = useContext(WorkspaceContext);
  if (context === undefined) {
    throw new Error('useWorkspace must be used within a WorkspaceProvider');
  }
  return context;
};
