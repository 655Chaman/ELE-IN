import React, { useState, useEffect } from 'react';
import { useWorkspace } from '@/contexts/WorkspaceContext';
import { fetcher, fetchWithAuth } from '@/lib/apiClient';
import { toast } from 'sonner';
import { Plus, Trash2, Shield, UserPlus, Building2 } from 'lucide-react';

interface AgencyMember {
  id: string;
  user_id: string;
  display_name: string;
  role: string;
  access: string[];
}

interface AgencyClient {
  id: string;
  name: string;
}

export function EleInAgencySettings() {
  const { myAgencies, refreshWorkspaces } = useWorkspace();
  const [activeAgencyId, setActiveAgencyId] = useState<string | null>(null);
  const [members, setMembers] = useState<AgencyMember[]>([]);
  const [clients, setClients] = useState<AgencyClient[]>([]);
  
  const [newClientName, setNewClientName] = useState('');
  const [newMemberEmail, setNewMemberEmail] = useState('');
  const [newMemberRole, setNewMemberRole] = useState('member');

  useEffect(() => {
    if (myAgencies && myAgencies.length > 0 && !activeAgencyId) {
      // Find the first one where they are owner or admin
      const adminAgency = myAgencies.find(a => a.role === 'owner' || a.role === 'admin');
      if (adminAgency) setActiveAgencyId(adminAgency.id);
    }
  }, [myAgencies, activeAgencyId]);

  useEffect(() => {
    if (activeAgencyId) {
      loadAgencyData();
    }
  }, [activeAgencyId]);

  const loadAgencyData = async () => {
    if (!activeAgencyId) return;
    try {
      const [membersData, clientsData] = await Promise.all([
        fetcher(`/api/agencies/${activeAgencyId}/members`),
        fetcher(`/api/agencies/${activeAgencyId}/clients`)
      ]);
      setMembers(membersData);
      setClients(clientsData);
    } catch (e: any) {
      toast.error('Failed to load agency data');
    }
  };

  const handleCreateClient = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newClientName.trim() || !activeAgencyId) return;
    try {
      await fetchWithAuth(`/api/agencies/${activeAgencyId}/clients`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newClientName.trim() })
      });
      toast.success('Client workspace created');
      setNewClientName('');
      loadAgencyData();
      refreshWorkspaces(); // Refresh global workspaces so the switcher gets the new one
    } catch (e: any) {
      toast.error(e.message || 'Failed to create client');
    }
  };

  const handleInviteMember = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newMemberEmail.trim() || !activeAgencyId) return;
    try {
      await fetchWithAuth(`/api/agencies/${activeAgencyId}/members`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: newMemberEmail.trim(), role: newMemberRole })
      });
      toast.success('Member invited');
      setNewMemberEmail('');
      loadAgencyData();
    } catch (e: any) {
      toast.error(e.message || 'Failed to invite member');
    }
  };

  const handleToggleAccess = async (memberId: string, workspaceId: string, hasAccess: boolean) => {
    if (!activeAgencyId) return;
    try {
      if (hasAccess) {
        await fetchWithAuth(`/api/agencies/${activeAgencyId}/members/${memberId}/access`, {
          method: 'DELETE',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ workspace_id: workspaceId })
        });
      } else {
        await fetchWithAuth(`/api/agencies/${activeAgencyId}/members/${memberId}/access`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ workspace_id: workspaceId })
        });
      }
      toast.success('Access updated');
      loadAgencyData();
    } catch (e: any) {
      toast.error('Failed to update access');
    }
  };

  if (!myAgencies || myAgencies.length === 0) {
    return <div className="p-8 text-muted-foreground">You are not part of any agency.</div>;
  }

  const adminAgencies = myAgencies.filter(a => a.role === 'owner' || a.role === 'admin');
  if (adminAgencies.length === 0) {
    return <div className="p-8 text-muted-foreground">You do not have permission to manage this agency.</div>;
  }

  return (
    <div className="flex-1 overflow-y-auto p-8 bg-background">
      <div className="max-w-4xl mx-auto space-y-8">
        <div>
          <h1 className="text-2xl font-semibold flex items-center gap-2">
            <Building2 className="text-primary" /> Agency Management
          </h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Manage your agency clients and team member access.
          </p>
        </div>

        {adminAgencies.length > 1 && (
          <div className="flex items-center gap-4">
            <label className="text-sm font-medium">Select Agency:</label>
            <select
              className="bg-accent/50 border border-border rounded-md px-3 py-1.5 text-sm"
              value={activeAgencyId || ''}
              onChange={e => setActiveAgencyId(e.target.value)}
            >
              {adminAgencies.map(a => (
                <option key={a.id} value={a.id}>{a.name} ({a.role})</option>
              ))}
            </select>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          {/* CLIENTS PANEL */}
          <div className="space-y-4">
            <h2 className="text-lg font-medium flex items-center gap-2 border-b border-border pb-2">
              <Shield size={18} /> Client Workspaces
            </h2>
            
            <form onSubmit={handleCreateClient} className="flex gap-2">
              <input 
                type="text" 
                placeholder="New client name..."
                className="flex-1 bg-accent/30 border border-border rounded-md px-3 py-2 text-sm"
                value={newClientName}
                onChange={e => setNewClientName(e.target.value)}
              />
              <button 
                type="submit"
                disabled={!newClientName.trim()}
                className="bg-primary text-primary-foreground px-3 py-2 rounded-md text-sm font-medium flex items-center gap-1 disabled:opacity-50"
              >
                <Plus size={16} /> Create
              </button>
            </form>

            <div className="bg-accent/10 border border-border rounded-md divide-y divide-border">
              {clients.length === 0 ? (
                <div className="p-4 text-center text-muted-foreground text-sm">No clients yet</div>
              ) : (
                clients.map(c => (
                  <div key={c.id} className="p-3 flex justify-between items-center text-sm">
                    <span className="font-medium">{c.name}</span>
                    <span className="text-xs text-muted-foreground font-mono">{c.id.substring(0,8)}...</span>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* MEMBERS PANEL */}
          <div className="space-y-4">
            <h2 className="text-lg font-medium flex items-center gap-2 border-b border-border pb-2">
              <UserPlus size={18} /> Agency Team
            </h2>
            
            <form onSubmit={handleInviteMember} className="flex gap-2">
              <input 
                type="email" 
                placeholder="User email..."
                className="flex-1 bg-accent/30 border border-border rounded-md px-3 py-2 text-sm"
                value={newMemberEmail}
                onChange={e => setNewMemberEmail(e.target.value)}
              />
              <select 
                className="bg-accent/30 border border-border rounded-md px-2 py-2 text-sm"
                value={newMemberRole}
                onChange={e => setNewMemberRole(e.target.value)}
              >
                <option value="member">Member</option>
                <option value="admin">Admin</option>
                <option value="owner">Owner</option>
              </select>
              <button 
                type="submit"
                disabled={!newMemberEmail.trim()}
                className="bg-primary text-primary-foreground px-3 py-2 rounded-md text-sm font-medium disabled:opacity-50"
              >
                Invite
              </button>
            </form>

            <div className="bg-accent/10 border border-border rounded-md divide-y divide-border">
              {members.length === 0 ? (
                <div className="p-4 text-center text-muted-foreground text-sm">No members yet</div>
              ) : (
                members.map(m => (
                  <div key={m.id} className="p-3 space-y-2">
                    <div className="flex justify-between items-center">
                      <div>
                        <div className="text-sm font-medium">{m.display_name}</div>
                        <div className="text-xs text-muted-foreground capitalize">{m.role}</div>
                      </div>
                    </div>
                    {m.role === 'member' && clients.length > 0 && (
                      <div className="pt-2 border-t border-border/50">
                        <p className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2">Client Access</p>
                        <div className="flex flex-wrap gap-2">
                          {clients.map(c => {
                            const hasAccess = m.access.includes(c.id);
                            return (
                              <label key={c.id} className="flex items-center gap-1.5 text-xs bg-accent/30 px-2 py-1 rounded cursor-pointer hover:bg-accent/50 transition-colors">
                                <input 
                                  type="checkbox" 
                                  className="rounded border-border bg-background"
                                  checked={hasAccess}
                                  onChange={() => handleToggleAccess(m.id, c.id, hasAccess)}
                                />
                                {c.name}
                              </label>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
