import React, { createContext, useContext, useState, useEffect } from 'react';
import { fetcher, fetchWithAuth } from "@/lib/apiClient";
import { mutate } from 'swr';

interface Workspace {
  id: string;
  name: string;
  account_count: number;
  status?: string;
}

interface WorkspaceContextType {
  workspaces: Workspace[];
  activeWorkspaceId: string | null;
  setActiveWorkspaceId: (id: string) => void;
  refreshWorkspaces: () => Promise<void>;
  createWorkspace: (name: string) => Promise<Workspace>;
  assignAccount: (accountId: string, targetWorkspaceId: string) => Promise<void>;
  isPendingDeletion: boolean;
}

const WorkspaceContext = createContext<WorkspaceContextType | undefined>(undefined);

export const WorkspaceProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [activeWorkspaceId, setActiveWorkspaceIdState] = useState<string | null>(
    localStorage.getItem('elein_active_workspace')
  );

  const fetchWorkspaces = async () => {
    try {
      const data = await fetcher('/api/workspaces');
      setWorkspaces(data);
      if (data.length > 0 && !activeWorkspaceId) {
        setActiveWorkspaceId(data[0].id);
      }
    } catch (error) {
      console.error("Failed to fetch workspaces:", error);
    }
  };

  useEffect(() => {
    fetchWorkspaces();
  }, []);

  const setActiveWorkspaceId = (id: string) => {
    setActiveWorkspaceIdState(id);
    localStorage.setItem('elein_active_workspace', id);
    // Reload after a short delay to ensure localStorage write flushes
    mutate(() => true, undefined, { revalidate: true });
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

  return (
    <WorkspaceContext.Provider value={{
      workspaces,
      activeWorkspaceId,
      setActiveWorkspaceId,
      refreshWorkspaces: fetchWorkspaces,
      createWorkspace,
      assignAccount,
      isPendingDeletion
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
