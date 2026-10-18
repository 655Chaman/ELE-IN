import React, { useState, useEffect, useMemo } from 'react';
import { useWorkspace } from '@/contexts/WorkspaceContext';
import { fetcher, fetchWithAuth } from '@/lib/apiClient';
import { toast } from 'sonner';
import { friendlyToast } from '../../core/frontend/components/FriendlyError';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import { 
  Building2, Plus, Trash2, Shield, UserPlus, Users, CheckCircle2, 
  ArrowRight, ExternalLink, Lock, Search, Sparkles, Globe, Palette, 
  Layers, AlertCircle, AlertTriangle, Check, Copy, Briefcase, 
  Loader2, Radio, RotateCcw, X, ShieldCheck, ChevronRight,
  Coins, ArrowUpRight, ArrowDownLeft, Settings2, Sliders,
  Receipt, FileText, Printer, Download, Calendar
} from 'lucide-react';
import ShinyText from "@/components/ShinyText";
import SpotlightCard from "@/components/SpotlightCard";
import { usePaywall } from "@/contexts/PaywallContext";
import { CustomSelect } from "@/components/ui/select";

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
  created_at?: string;
  campaigns_count?: number;
  active_campaigns_count?: number;
  leads_count?: number;
  senders_count?: number;
  credits_balance?: number;
  allocated_budget?: number;
  consumed_credits?: number;
}

interface AgencyCreditsOverview {
  master_workspace: {
    id: string;
    name: string;
    balance: number;
  };
  total_agency_balance: number;
  total_delegated_credits: number;
  total_consumed_credits: number;
  clients: Array<{
    id: string;
    name: string;
    created_at?: string;
    balance: number;
    allocated_budget: number;
    consumed_credits: number;
    monthly_quota: number;
    exhaustion_alert_threshold: number;
    status: 'healthy' | 'low' | 'overdraft';
  }>;
  recent_allocations: Array<{
    id: string;
    client_workspace_id: string;
    from_workspace_id?: string;
    amount: number;
    action_type: string;
    note?: string;
    created_at: string;
  }>;
}

interface AgencyStatement {
  id: string;
  agency_id: string;
  client_workspace_id: string | null;
  invoice_number: string;
  status: 'draft' | 'issued' | 'paid' | 'void';
  period_start: string;
  period_end: string;
  currency: string;
  subtotal_cents: number;
  markup_cents: number;
  tax_cents: number;
  total_cents: number;
  breakdown_data: {
    target_type?: string;
    tax_percent?: number;
    total_billable_credits?: number;
    clients?: Array<{
      client_workspace_id: string;
      client_name: string;
      campaigns_count: number;
      billable_credits: number;
      unit_credit_rate_cents: number;
      credit_charge_cents: number;
      platform_base_fee_cents: number;
      subtotal_cents: number;
      current_balance: number;
    }>;
  };
  notes?: string;
  created_at: string;
  updated_at: string;
}

export function EleInAgencySettings() {
  const navigate = useNavigate();
  const { openPaywall } = usePaywall();
  const { myAgencies, refreshWorkspaces, setActiveWorkspaceId } = useWorkspace();
  
  const [activeAgencyId, setActiveAgencyId] = useState<string | null>(null);
  const [members, setMembers] = useState<AgencyMember[]>([]);
  const [clients, setClients] = useState<AgencyClient[]>([]);
  const [isLoadingData, setIsLoadingData] = useState<boolean>(false);

  // Active view tab
  const [activeTab, setActiveTab] = useState<'clients' | 'team' | 'whitelabel' | 'credits' | 'statements'>('clients');

  // Client search and creation
  const [clientSearch, setClientSearch] = useState('');
  const [newClientName, setNewClientName] = useState('');
  const [isCreatingClient, setIsCreatingClient] = useState(false);

  // Member invitation
  const [newMemberEmail, setNewMemberEmail] = useState('');
  const [newMemberRole, setNewMemberRole] = useState<'member' | 'admin' | 'owner'>('member');
  const [isInvitingMember, setIsInvitingMember] = useState(false);
  const [inviteErrorNotice, setInviteErrorNotice] = useState<string | null>(null);

  // New Agency Creation (Zero-State Cockpit)
  const [newAgencyName, setNewAgencyName] = useState('');
  const [isCreatingAgency, setIsCreatingAgency] = useState(false);

  // White-label settings persistence
  const [whitelabelBrand, setWhitelabelBrand] = useState('Apex Outbound Group');
  const [whitelabelDomain, setWhitelabelDomain] = useState('app.apexoutbound.com');
  const [whitelabelColor, setWhitelabelColor] = useState('#6366f1');
  const [isSavingWhitelabel, setIsSavingWhitelabel] = useState(false);
  const [isCopiedPortalLink, setIsCopiedPortalLink] = useState(false);

  // Member Access Drawer / Modal
  const [managingMember, setManagingMember] = useState<AgencyMember | null>(null);

  // Credit Delegation State (Stage 27)
  const [creditsOverview, setCreditsOverview] = useState<AgencyCreditsOverview | null>(null);
  const [allocationModal, setAllocationModal] = useState<{
    isOpen: boolean;
    type: 'allocate' | 'reclaim';
    clientWorkspaceId: string;
    clientName: string;
    currentBalance: number;
  }>({
    isOpen: false,
    type: 'allocate',
    clientWorkspaceId: '',
    clientName: '',
    currentBalance: 0,
  });
  const [allocationAmount, setAllocationAmount] = useState<number>(1000);
  const [allocationNote, setAllocationNote] = useState<string>('');
  const [isSubmittingTransfer, setIsSubmittingTransfer] = useState(false);

  // Quota Settings Modal State
  const [quotaModal, setQuotaModal] = useState<{
    isOpen: boolean;
    clientWorkspaceId: string;
    clientName: string;
    monthlyQuota: number;
    exhaustionThreshold: number;
  }>({
    isOpen: false,
    clientWorkspaceId: '',
    clientName: '',
    monthlyQuota: 0,
    exhaustionThreshold: 100,
  });
  const [isSavingQuota, setIsSavingQuota] = useState(false);

  // Invoicing & Billing Statements State (Stage 28)
  const getMonthStart = () => {
    const d = new Date();
    return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().split('T')[0];
  };
  const getMonthEnd = () => {
    const d = new Date();
    return new Date(d.getFullYear(), d.getMonth() + 1, 0).toISOString().split('T')[0];
  };

  const [statements, setStatements] = useState<AgencyStatement[]>([]);
  const [statementFilterStatus, setStatementFilterStatus] = useState<'all' | 'draft' | 'issued' | 'paid' | 'void'>('all');
  const [statementFilterClient, setStatementFilterClient] = useState<string>('all');
  const [generateModal, setGenerateModal] = useState<{
    isOpen: boolean;
    clientWorkspaceId: string;
    periodStart: string;
    periodEnd: string;
    currency: string;
    unitCreditRateCents: number;
    platformBaseFeeCents: number;
    taxPercent: number;
    notes: string;
  }>({
    isOpen: false,
    clientWorkspaceId: '',
    periodStart: getMonthStart(),
    periodEnd: getMonthEnd(),
    currency: 'INR',
    unitCreditRateCents: 150,
    platformBaseFeeCents: 499900,
    taxPercent: 18,
    notes: 'Net 15 payment terms. Thank you for your partnership.'
  });
  const [isGeneratingStatement, setIsGeneratingStatement] = useState(false);
  const [viewingStatement, setViewingStatement] = useState<AgencyStatement | null>(null);
  const [isUpdatingStatus, setIsUpdatingStatus] = useState(false);

  useEffect(() => {
    if (myAgencies && myAgencies.length > 0 && !activeAgencyId) {
      const adminAgency = myAgencies.find(a => a.role === 'owner' || a.role === 'admin') || myAgencies[0];
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
    setIsLoadingData(true);
    try {
      const [membersData, clientsData, whitelabelData, creditsData, statementsData] = await Promise.all([
        fetcher(`/api/agencies/${activeAgencyId}/members`),
        fetcher(`/api/agencies/${activeAgencyId}/clients`),
        fetcher(`/api/agencies/${activeAgencyId}/whitelabel`).catch(() => null),
        fetcher(`/api/agencies/${activeAgencyId}/credits`).catch(() => null),
        fetcher(`/api/agencies/${activeAgencyId}/statements`).catch(() => [])
      ]);
      setMembers(Array.isArray(membersData) ? membersData : []);
      setClients(Array.isArray(clientsData) ? clientsData : []);
      if (creditsData) setCreditsOverview(creditsData);
      if (Array.isArray(statementsData)) setStatements(statementsData);
      if (whitelabelData) {
        if (whitelabelData.brand_name) setWhitelabelBrand(whitelabelData.brand_name);
        if (whitelabelData.custom_domain !== undefined) setWhitelabelDomain(whitelabelData.custom_domain || '');
        if (whitelabelData.accent_color) setWhitelabelColor(whitelabelData.accent_color);
      }
    } catch (e: any) {
      toast.error('Failed to load agency data');
    } finally {
      setIsLoadingData(false);
    }
  };

  const handleGenerateStatement = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeAgencyId) return;
    setIsGeneratingStatement(true);
    try {
      const res = await fetchWithAuth(`/api/agencies/${activeAgencyId}/statements/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_workspace_id: generateModal.clientWorkspaceId || null,
          period_start: generateModal.periodStart,
          period_end: generateModal.periodEnd,
          currency: generateModal.currency,
          unit_credit_rate_cents: generateModal.unitCreditRateCents,
          platform_base_fee_cents: generateModal.platformBaseFeeCents,
          tax_percent: generateModal.taxPercent,
          notes: generateModal.notes
        })
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to generate statement");
      }

      const stmt = await res.json();
      toast.success(`Generated Statement ${stmt.invoice_number}`);
      setGenerateModal(prev => ({ ...prev, isOpen: false }));
      setStatements(prev => [stmt, ...prev]);
      setViewingStatement(stmt);
      await loadAgencyData();
    } catch (err: any) {
      friendlyToast("Statement generation failed", err);
    } finally {
      setIsGeneratingStatement(false);
    }
  };

  const handleUpdateStatementStatus = async (statementId: string, newStatus: 'draft' | 'issued' | 'paid' | 'void') => {
    if (!activeAgencyId) return;
    setIsUpdatingStatus(true);
    try {
      const res = await fetchWithAuth(`/api/agencies/${activeAgencyId}/statements/${statementId}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus })
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to update statement status");
      }

      toast.success(`Statement marked as ${newStatus.toUpperCase()}`);
      setStatements(prev => prev.map(s => s.id === statementId ? { ...s, status: newStatus } : s));
      if (viewingStatement && viewingStatement.id === statementId) {
        setViewingStatement(prev => prev ? { ...prev, status: newStatus } : null);
      }
    } catch (err: any) {
      friendlyToast("Failed to update status", err);
    } finally {
      setIsUpdatingStatus(false);
    }
  };

  const handleExportStatement = (statementId: string) => {
    if (!activeAgencyId) return;
    window.open(`/api/agencies/${activeAgencyId}/statements/${statementId}/export`, '_blank');
  };

  const handleExecuteCreditTransfer = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeAgencyId || !allocationModal.clientWorkspaceId) return;
    if (allocationAmount <= 0) {
      toast.error("Please enter a valid credit amount");
      return;
    }

    setIsSubmittingTransfer(true);
    try {
      const endpoint = allocationModal.type === 'allocate' 
        ? `/api/agencies/${activeAgencyId}/credits/allocate`
        : `/api/agencies/${activeAgencyId}/credits/reclaim`;

      const res = await fetchWithAuth(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_workspace_id: allocationModal.clientWorkspaceId,
          amount: allocationAmount,
          note: allocationNote || (allocationModal.type === 'allocate' ? 'Manual credit delegation' : 'Reclaimed credits to master pool')
        })
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Credit transfer failed");
      }

      toast.success(
        allocationModal.type === 'allocate'
          ? `Successfully allocated ${allocationAmount.toLocaleString()} credits to ${allocationModal.clientName}`
          : `Successfully reclaimed ${allocationAmount.toLocaleString()} credits back to master pool`
      );

      setAllocationModal(prev => ({ ...prev, isOpen: false }));
      setAllocationAmount(1000);
      setAllocationNote('');
      await loadAgencyData();
    } catch (err: any) {
      friendlyToast("Credit transfer failed", err);
    } finally {
      setIsSubmittingTransfer(false);
    }
  };

  const handleSaveClientQuota = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeAgencyId || !quotaModal.clientWorkspaceId) return;

    setIsSavingQuota(true);
    try {
      const res = await fetchWithAuth(`/api/agencies/${activeAgencyId}/credits/client-quota`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_workspace_id: quotaModal.clientWorkspaceId,
          monthly_credit_quota: quotaModal.monthlyQuota,
          exhaustion_alert_threshold: quotaModal.exhaustionThreshold
        })
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to update quota settings");
      }

      toast.success(`Updated quota & alert parameters for ${quotaModal.clientName}`);
      setQuotaModal(prev => ({ ...prev, isOpen: false }));
      await loadAgencyData();
    } catch (err: any) {
      friendlyToast("Failed to update client quota", err);
    } finally {
      setIsSavingQuota(false);
    }
  };

  // Create new Agency from Zero-State (Layer 0)
  const handleCreateAgency = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanName = newAgencyName.trim();
    if (!cleanName) return;

    setIsCreatingAgency(true);
    try {
      const res = await fetchWithAuth('/api/agencies', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: cleanName })
      });
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText || 'Failed to create agency');
      }
      const data = await res.json();
      toast.success(`Agency "${cleanName}" created successfully!`);
      setNewAgencyName('');
      await refreshWorkspaces();
      if (data?.agency?.id) {
        setActiveAgencyId(data.agency.id);
      }
    } catch (e: any) {
      friendlyToast('Failed to create agency hub.', e);
    } finally {
      setIsCreatingAgency(false);
    }
  };

  // Create new Client Workspace (Layer 0 & 1)
  const handleCreateClient = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanName = newClientName.trim();
    if (!cleanName || !activeAgencyId) return;

    // Check duplicate name in client portfolio (Layer 1 Paranoia)
    if (clients.some(c => c.name.toLowerCase() === cleanName.toLowerCase())) {
      toast.error(`A client workspace named "${cleanName}" already exists in this agency.`);
      return;
    }

    setIsCreatingClient(true);
    try {
      const res = await fetchWithAuth(`/api/agencies/${activeAgencyId}/clients`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: cleanName })
      });
      if (!res.ok) throw new Error('Failed to create client workspace');
      toast.success(`Client workspace "${cleanName}" created!`);
      setNewClientName('');
      loadAgencyData();
      refreshWorkspaces();
    } catch (e: any) {
      friendlyToast('Failed to create client workspace.', e);
    } finally {
      setIsCreatingClient(false);
    }
  };

  // Invite Agency Team Member (Layer 1 Paranoia: Pre-existence checks)
  const handleInviteMember = async (e: React.FormEvent) => {
    e.preventDefault();
    setInviteErrorNotice(null);
    const cleanEmail = newMemberEmail.trim().toLowerCase();
    if (!cleanEmail || !activeAgencyId) return;

    setIsInvitingMember(true);
    try {
      const res = await fetchWithAuth(`/api/agencies/${activeAgencyId}/members`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: cleanEmail, role: newMemberRole })
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        if (res.status === 404 || errJson.detail?.includes("must have an account")) {
          setInviteErrorNotice(
            `User "${cleanEmail}" does not have an Ele-in account yet. Ask them to register or sign up first, then invite them to your agency.`
          );
          return;
        }
        throw new Error(errJson.detail || 'Failed to invite agency member');
      }

      toast.success(`Invitation sent to ${cleanEmail}`);
      setNewMemberEmail('');
      loadAgencyData();
    } catch (e: any) {
      friendlyToast('Failed to invite team member.', e);
    } finally {
      setIsInvitingMember(false);
    }
  };

  // Toggle Access for Member across Client Workspaces
  const handleToggleAccess = async (memberId: string, workspaceId: string, hasAccess: boolean) => {
    if (!activeAgencyId) return;
    try {
      if (hasAccess) {
        await fetchWithAuth(`/api/agencies/${activeAgencyId}/members/${memberId}/access`, {
          method: 'DELETE',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ workspace_id: workspaceId })
        });
        toast.info("Access revoked");
      } else {
        await fetchWithAuth(`/api/agencies/${activeAgencyId}/members/${memberId}/access`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ workspace_id: workspaceId })
        });
        toast.success("Access granted");
      }
      loadAgencyData();
    } catch {
      toast.error('Failed to update client workspace access');
    }
  };

  // Batch Grant All or Revoke All for Member
  const handleBatchGrantAll = async (member: AgencyMember) => {
    if (!activeAgencyId) return;
    const missingWorkspaces = clients.filter(c => !member.access.includes(c.id));
    for (const c of missingWorkspaces) {
      try {
        await fetchWithAuth(`/api/agencies/${activeAgencyId}/members/${member.id}/access`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ workspace_id: c.id })
        });
      } catch (_) {}
    }
    toast.success(`Granted ${member.display_name} access to all client workspaces`);
    loadAgencyData();
  };

  const handleBatchRevokeAll = async (member: AgencyMember) => {
    if (!activeAgencyId) return;
    for (const wsId of member.access) {
      try {
        await fetchWithAuth(`/api/agencies/${activeAgencyId}/members/${member.id}/access`, {
          method: 'DELETE',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ workspace_id: wsId })
        });
      } catch (_) {}
    }
    toast.info(`Revoked all client access for ${member.display_name}`);
    loadAgencyData();
  };

  // 1-Click Switch to Client Workspace (Layer 0 & 2)
  const handleSwitchToClientWorkspace = (clientId: string, clientName: string) => {
    setActiveWorkspaceId(clientId);
    toast.success(`Switched active context to "${clientName}"`, {
      description: "All campaigns, leads, and analytics are strictly isolated to this client.",
      action: {
        label: "Go to Dashboard",
        onClick: () => navigate('/elein')
      }
    });
  };

  // Save White-Label Configurations to Database (Layer 0 & 1 Paranoia)
  const handleSaveWhitelabel = async () => {
    if (!activeAgencyId) return;
    const cleanBrand = whitelabelBrand.trim();
    if (!cleanBrand) {
      toast.error('Agency Brand Title cannot be empty');
      return;
    }

    setIsSavingWhitelabel(true);
    try {
      const res = await fetchWithAuth(`/api/agencies/${activeAgencyId}/whitelabel`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          brand_name: cleanBrand,
          custom_domain: whitelabelDomain.trim(),
          accent_color: whitelabelColor.trim() || '#6366f1',
          enabled: true
        })
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || 'Failed to update white-label settings');
      }

      toast.success('White-label branding parameters saved to database!');
    } catch (err: any) {
      friendlyToast('Failed to save white-label branding', err);
    } finally {
      setIsSavingWhitelabel(false);
    }
  };

  // Filter clients by search
  const filteredClients = useMemo(() => {
    return clients.filter(c => 
      c.name.toLowerCase().includes(clientSearch.toLowerCase()) ||
      c.id.toLowerCase().includes(clientSearch.toLowerCase())
    );
  }, [clients, clientSearch]);

  const adminAgencies = (myAgencies || []).filter(a => a.role === 'owner' || a.role === 'admin');

  // ─── ZERO-STATE: NO AGENCY REGISTERED ─────────────────────────────────────
  if (!myAgencies || myAgencies.length === 0) {
    return (
      <div className="flex-1 overflow-y-auto p-6 sm:p-10 bg-background font-sans">
        <div className="max-w-3xl mx-auto py-12">
          <SpotlightCard className="p-8 sm:p-10 rounded-xl border border-border/80 bg-card shadow-lg text-center flex flex-col items-center">
            <div className="w-16 h-16 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary mb-6 shadow-xs">
              <Building2 size={32} />
            </div>

            <h1 className="text-2xl font-bold tracking-tight text-foreground mb-2">
              <ShinyText text="Launch Your Agency Command Deck" speed={3} className="text-foreground" />
            </h1>
            <p className="text-xs text-muted-foreground max-w-lg mb-8 leading-relaxed">
              Manage dozens of client LinkedIn outreach campaigns from one unified roof. Strict workspace isolation guarantees client leads and sender accounts never collide.
            </p>

            <form onSubmit={handleCreateAgency} className="w-full max-w-md space-y-4">
              <div className="text-left">
                <label className="text-xs font-bold text-foreground block mb-1.5">Agency Organization Name</label>
                <input 
                  type="text"
                  placeholder="e.g. Apex Outbound & Growth Partners"
                  value={newAgencyName}
                  onChange={e => setNewAgencyName(e.target.value)}
                  className="w-full bg-background border border-border/80 rounded-xl px-4 py-3 text-xs font-semibold text-foreground focus:outline-none focus:border-primary focus:ring-1 ring-primary shadow-xs"
                />
              </div>

              <button
                type="submit"
                disabled={isCreatingAgency || !newAgencyName.trim()}
                className="w-full py-3 bg-primary text-primary-foreground font-bold text-xs rounded-xl hover:bg-primary/90 transition-colors shadow-xs disabled:opacity-50 cursor-pointer flex items-center justify-center gap-2"
              >
                {isCreatingAgency ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
                <span>Create Agency & Initialize Clients</span>
              </button>
            </form>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 w-full mt-10 pt-8 border-t border-border/60 text-left">
              <div className="p-3 bg-muted/30 rounded-xl border border-border/40">
                <ShieldCheck size={16} className="text-emerald-500 mb-1" />
                <h4 className="text-xs font-bold text-foreground">Zero Collision</h4>
                <p className="text-[11px] text-muted-foreground mt-0.5">Strict database partitions between clients.</p>
              </div>
              <div className="p-3 bg-muted/30 rounded-xl border border-border/40">
                <Users size={16} className="text-primary mb-1" />
                <h4 className="text-xs font-bold text-foreground">Granular RBAC</h4>
                <p className="text-[11px] text-muted-foreground mt-0.5">Assign managers to specific client accounts.</p>
              </div>
              <div className="p-3 bg-muted/30 rounded-xl border border-border/40">
                <Palette size={16} className="text-purple-500 mb-1" />
                <h4 className="text-xs font-bold text-foreground">White-Label Ready</h4>
                <p className="text-[11px] text-muted-foreground mt-0.5">Client portals with custom agency branding.</p>
              </div>
            </div>
          </SpotlightCard>
        </div>
      </div>
    );
  }

  // ─── PERMISSION CHECK ─────────────────────────────────────────────────────
  if (adminAgencies.length === 0) {
    return (
      <div className="flex-1 p-10 text-center flex flex-col items-center justify-center font-sans">
        <Lock size={32} className="text-muted-foreground mb-3" />
        <h3 className="text-base font-bold text-foreground">Restricted Agency Access</h3>
        <p className="text-xs text-muted-foreground max-w-sm mt-1">
          You are a member of an agency but do not hold Administrator or Owner privileges to manage client workspaces.
        </p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-6 sm:p-10 bg-background font-sans">
      <div className="max-w-6xl mx-auto space-y-8">
        {/* ─── HEADER COMMAND DECK ──────────────────────────────────────────── */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 mb-1.5 flex-wrap">
              <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2.5">
                <Building2 className="text-primary" size={24} />
                <ShinyText text="Agency Multi-Client Command Deck" speed={3} className="text-foreground" />
              </h1>
              <span className="text-[10px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
                Agency Portal
              </span>
            </div>
            <p className="text-xs text-muted-foreground">
              Manage isolated client brand workspaces, configure account manager permissions, and white-label client reports.
            </p>
          </div>

          {/* Agency Switcher if multiple */}
          {adminAgencies.length > 1 && (
            <div className="flex items-center gap-2 bg-card p-1.5 rounded-xl border border-border/60 shadow-xs">
              <label className="text-xs font-bold text-muted-foreground pl-2 whitespace-nowrap">Agency:</label>
              <CustomSelect
                value={activeAgencyId || ''}
                onValueChange={setActiveAgencyId}
                size="sm"
                className="w-auto"
                triggerClassName="bg-transparent border-0 shadow-none text-xs font-bold text-foreground h-7 px-2"
                options={adminAgencies.map(a => ({
                  value: a.id,
                  label: `${a.name} (${a.role})`,
                }))}
              />
            </div>
          )}
        </div>

        {/* ─── AGENCY VITAL STATISTICS RIBBON (Layer 0) ─────────────────────── */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5">
          <div className="p-4 rounded-xl bg-card border border-border/60 shadow-xs flex items-center justify-between">
            <div>
              <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Managed Clients</p>
              <div className="flex items-baseline gap-2 mt-1">
                <span className="text-xl font-bold text-foreground font-mono">{clients.length}</span>
                <span className="text-[10px] text-primary font-bold">Workspaces</span>
              </div>
            </div>
            <div className="w-9 h-9 rounded-lg bg-primary/10 text-primary flex items-center justify-center shrink-0">
              <Briefcase size={18} />
            </div>
          </div>

          <div className="p-4 rounded-xl bg-card border border-border/60 shadow-xs flex items-center justify-between">
            <div>
              <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Agency Team</p>
              <div className="flex items-baseline gap-2 mt-1">
                <span className="text-xl font-bold text-foreground font-mono">{members.length}</span>
                <span className="text-[10px] text-emerald-600 font-bold">Operators</span>
              </div>
            </div>
            <div className="w-9 h-9 rounded-lg bg-emerald-500/10 text-emerald-600 flex items-center justify-center shrink-0">
              <Users size={18} />
            </div>
          </div>

          <div className="p-4 rounded-xl bg-card border border-border/60 shadow-xs flex items-center justify-between">
            <div>
              <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Data Boundary</p>
              <div className="flex items-baseline gap-2 mt-1">
                <span className="text-xs font-bold text-emerald-600 flex items-center gap-1">
                  <ShieldCheck size={14} /> 100% Isolated
                </span>
              </div>
              <p className="text-[10px] text-muted-foreground mt-0.5">Strict client zero-collision</p>
            </div>
            <div className="w-9 h-9 rounded-lg bg-muted text-muted-foreground flex items-center justify-center shrink-0">
              <Shield size={18} />
            </div>
          </div>

          <div className="p-4 rounded-xl bg-card border border-border/60 shadow-xs flex items-center justify-between">
            <div>
              <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Branding Mode</p>
              <div className="flex items-baseline gap-2 mt-1">
                <span className="text-xs font-bold text-purple-600 flex items-center gap-1">
                  <Sparkles size={14} /> White-Label Active
                </span>
              </div>
              <p className="text-[10px] text-muted-foreground mt-0.5">Custom client views</p>
            </div>
            <div className="w-9 h-9 rounded-xl bg-purple-500/10 text-purple-600 flex items-center justify-center shrink-0">
              <Palette size={18} />
            </div>
          </div>
        </div>

        {/* ─── TABS NAVIGATION ──────────────────────────────────────────────── */}
        <div className="flex items-center gap-2 border-b border-border/60 pb-3 overflow-x-auto">
          <button
            onClick={() => setActiveTab('clients')}
            className={`flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-xl transition-all cursor-pointer whitespace-nowrap ${
              activeTab === 'clients' 
                ? 'bg-primary text-primary-foreground shadow-sm shadow-primary/20' 
                : 'text-muted-foreground hover:text-foreground hover:bg-muted'
            }`}
          >
            <Briefcase size={14} />
            <span>Client Workspaces ({clients.length})</span>
          </button>

          <button
            onClick={() => setActiveTab('team')}
            className={`flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-xl transition-all cursor-pointer whitespace-nowrap ${
              activeTab === 'team' 
                ? 'bg-primary text-primary-foreground shadow-sm shadow-primary/20' 
                : 'text-muted-foreground hover:text-foreground hover:bg-muted'
            }`}
          >
            <UserPlus size={14} />
            <span>Agency Team & RBAC ({members.length})</span>
          </button>

          <button
            onClick={() => setActiveTab('whitelabel')}
            className={`flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-xl transition-all cursor-pointer whitespace-nowrap ${
              activeTab === 'whitelabel' 
                ? 'bg-primary text-primary-foreground shadow-sm shadow-primary/20' 
                : 'text-muted-foreground hover:text-foreground hover:bg-muted'
            }`}
          >
            <Palette size={14} />
            <span>White-Label Portal & Branding</span>
          </button>

          <button
            onClick={() => setActiveTab('credits')}
            className={`flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-xl transition-all cursor-pointer whitespace-nowrap ${
              activeTab === 'credits' 
                ? 'bg-primary text-primary-foreground shadow-sm shadow-primary/20' 
                : 'text-muted-foreground hover:text-foreground hover:bg-muted'
            }`}
          >
            <Coins size={14} />
            <span>Credit Delegations & Quotas</span>
          </button>

          <button
            onClick={() => setActiveTab('statements')}
            className={`flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-xl transition-all cursor-pointer whitespace-nowrap ${
              activeTab === 'statements' 
                ? 'bg-primary text-primary-foreground shadow-sm shadow-primary/20' 
                : 'text-muted-foreground hover:text-foreground hover:bg-muted'
            }`}
          >
            <Receipt size={14} />
            <span>Invoicing & Statements ({statements.length})</span>
          </button>
        </div>

        {/* ─── TAB 1: CLIENT WORKSPACES MATRIX ───────────────────────────────── */}
        {activeTab === 'clients' && (
          <div className="space-y-6">
            {/* Create Client Form */}
            <div className="p-6 rounded-xl border border-border/60 bg-card shadow-xs">
              <h3 className="text-sm font-bold text-foreground mb-1 flex items-center gap-2">
                <Plus size={16} className="text-primary" />
                Add New Client Brand Workspace
              </h3>
              <p className="text-xs text-muted-foreground mb-4">
                Creates a partitioned workspace with its own dedicated campaign builder, lead hub, and sender rotations.
              </p>

              <form onSubmit={handleCreateClient} className="flex flex-col sm:flex-row gap-3">
                <input 
                  type="text" 
                  placeholder="Client company or project name (e.g. Acme Healthtech)..."
                  className="flex-1 bg-background border border-border/60 rounded-xl px-4 py-2.5 text-xs text-foreground focus:outline-none focus:border-primary focus:ring-1 ring-primary shadow-xs"
                  value={newClientName}
                  onChange={e => setNewClientName(e.target.value)}
                />
                <button 
                  type="submit"
                  disabled={isCreatingClient || !newClientName.trim()}
                  className="flex items-center justify-center gap-2 px-5 py-2.5 bg-primary text-primary-foreground text-xs font-bold rounded-xl hover:bg-primary/90 transition-colors disabled:opacity-50 shadow-xs cursor-pointer whitespace-nowrap"
                >
                  {isCreatingClient ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
                  <span>Create Client Workspace</span>
                </button>
              </form>
            </div>

            {/* Clients List & Matrix */}
            <div className="space-y-3">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <h3 className="text-sm font-bold text-foreground">Client Portfolio ({clients.length})</h3>
                
                {/* Search Box */}
                <div className="flex items-center gap-2 px-3 py-1.5 bg-card border border-border/60 rounded-xl shadow-xs w-full sm:w-60">
                  <Search size={13} className="text-muted-foreground" />
                  <input
                    value={clientSearch}
                    onChange={e => setClientSearch(e.target.value)}
                    placeholder="Search client brands…"
                    className="flex-1 bg-transparent text-xs text-foreground placeholder-muted-foreground focus:outline-none"
                  />
                  {clientSearch && (
                    <button onClick={() => setClientSearch("")} className="text-muted-foreground hover:text-foreground">
                      <X size={12} />
                    </button>
                  )}
                </div>
              </div>

              {filteredClients.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {filteredClients.map(c => {
                    const assignedMembers = members.filter(m => m.role === 'owner' || m.role === 'admin' || m.access.includes(c.id));

                    return (
                      <div key={c.id} className="p-5 rounded-xl border border-border/60 bg-card hover:border-primary/40 transition-all shadow-xs flex flex-col justify-between group">
                        <div>
                          <div className="flex items-start justify-between gap-3 mb-2">
                            <div className="flex items-center gap-3">
                              <div className="w-10 h-10 rounded-lg bg-primary/10 border border-primary/20 text-primary flex items-center justify-center font-bold text-xs shadow-xs">
                                {c.name.substring(0, 2).toUpperCase()}
                              </div>
                              <div>
                                <h4 className="text-sm font-bold text-foreground group-hover:text-primary transition-colors">
                                  {c.name}
                                </h4>
                                <p className="text-[11px] text-muted-foreground font-mono mt-0.5">
                                  ID: {c.id.substring(0, 14)}...
                                </p>
                              </div>
                            </div>

                            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 border border-emerald-500/20">
                              Active
                            </span>
                          </div>

                          {/* Client Telemetry Ribbon */}
                          <div className="grid grid-cols-4 gap-2 mt-3 pt-3 border-t border-border/40">
                            <div className="bg-muted/30 rounded-lg p-2 text-center">
                              <span className="text-[10px] text-muted-foreground block font-semibold">Campaigns</span>
                              <span className="text-xs font-bold text-foreground font-mono">
                                {c.campaigns_count ?? 0}
                                {c.active_campaigns_count ? (
                                  <span className="text-[10px] text-emerald-600 font-normal ml-1">({c.active_campaigns_count})</span>
                                ) : null}
                              </span>
                            </div>
                            <div className="bg-muted/30 rounded-lg p-2 text-center">
                              <span className="text-[10px] text-muted-foreground block font-semibold">Leads</span>
                              <span className="text-xs font-bold text-foreground font-mono">
                                {c.leads_count !== undefined ? c.leads_count.toLocaleString() : 0}
                              </span>
                            </div>
                            <div className="bg-muted/30 rounded-lg p-2 text-center">
                              <span className="text-[10px] text-muted-foreground block font-semibold">Senders</span>
                              <span className="text-xs font-bold text-foreground font-mono">
                                {c.senders_count ?? 0}
                              </span>
                            </div>
                            <div className="bg-muted/30 rounded-lg p-2 text-center">
                              <span className="text-[10px] text-muted-foreground block font-semibold">Credits</span>
                              <span className={`text-xs font-bold font-mono ${
                                (creditsOverview?.clients.find(x => x.id === c.id)?.balance ?? 0) < 100 
                                  ? 'text-amber-500' 
                                  : 'text-emerald-500'
                              }`}>
                                {(creditsOverview?.clients.find(x => x.id === c.id)?.balance ?? 0).toLocaleString()}
                              </span>
                            </div>
                          </div>

                          <div className="mt-3 pt-3 border-t border-border/40 flex items-center justify-between text-xs text-muted-foreground">
                            <span>Assigned Operators:</span>
                            <div className="flex -space-x-1.5 overflow-hidden">
                              {assignedMembers.slice(0, 3).map(m => (
                                <div key={m.id} className="w-6 h-6 rounded-full bg-muted border border-background text-[10px] font-bold flex items-center justify-center" title={m.display_name}>
                                  {m.display_name.substring(0, 2).toUpperCase()}
                                </div>
                              ))}
                              {assignedMembers.length > 3 && (
                                <div className="w-6 h-6 rounded-full bg-primary/20 text-primary text-[9px] font-bold flex items-center justify-center">
                                  +{assignedMembers.length - 3}
                                </div>
                              )}
                            </div>
                          </div>
                        </div>

                        <div className="mt-4 pt-3 border-t border-border/40 flex items-center justify-between gap-2">
                          <button
                            type="button"
                            onClick={() => setAllocationModal({
                              isOpen: true,
                              type: 'allocate',
                              clientWorkspaceId: c.id,
                              clientName: c.name,
                              currentBalance: creditsOverview?.clients.find(x => x.id === c.id)?.balance ?? 0
                            })}
                            className="flex items-center gap-1.5 px-3 py-1.5 bg-muted hover:bg-muted/80 text-foreground rounded-xl text-xs font-semibold transition-all cursor-pointer"
                          >
                            <Coins size={12} className="text-amber-500" />
                            <span>Allocate Credits</span>
                          </button>

                          <button
                            type="button"
                            onClick={() => handleSwitchToClientWorkspace(c.id, c.name)}
                            className="flex items-center gap-1.5 px-3 py-1.5 bg-primary/10 hover:bg-primary/20 text-primary rounded-xl text-xs font-bold transition-all cursor-pointer"
                          >
                            <span>Switch Context</span>
                            <ArrowRight size={12} />
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="py-12 text-center flex flex-col items-center bg-card rounded-xl border border-dashed border-border/60">
                  <Briefcase size={28} className="text-muted-foreground/40 mb-2" />
                  <h4 className="text-sm font-bold text-foreground mb-1">
                    {clientSearch ? "No matching clients found" : "No client workspaces created yet"}
                  </h4>
                  <p className="text-xs text-muted-foreground max-w-sm mb-4">
                    {clientSearch ? "Try adjusting your search query." : "Add your first client brand using the form above."}
                  </p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ─── TAB 2: AGENCY TEAM & GRANULAR RBAC ───────────────────────────── */}
        {activeTab === 'team' && (
          <div className="space-y-6">
            {/* Invite Form */}
            <div className="p-6 rounded-xl border border-border/60 bg-card shadow-xs">
              <h3 className="text-sm font-bold text-foreground mb-1 flex items-center gap-2">
                <UserPlus size={16} className="text-primary" />
                Invite Agency Operator or Account Manager
              </h3>
              <p className="text-xs text-muted-foreground mb-4">
                Grant agency members access to manage campaigns across designated client portfolios.
              </p>

              <form onSubmit={handleInviteMember} className="flex flex-col sm:flex-row gap-3">
                <input 
                  type="email" 
                  placeholder="operator@agency.com..."
                  className="flex-1 bg-background border border-border/60 rounded-xl px-4 py-2.5 text-xs text-foreground focus:outline-none focus:border-primary focus:ring-1 ring-primary shadow-xs"
                  value={newMemberEmail}
                  onChange={e => setNewMemberEmail(e.target.value)}
                />
                <CustomSelect 
                  className="w-full sm:w-64"
                  triggerClassName="bg-background border-border/60 rounded-xl px-3 py-2.5 text-xs font-semibold text-foreground h-10"
                  value={newMemberRole}
                  onValueChange={val => setNewMemberRole(val as any)}
                  options={[
                    { value: "member", label: "Member (Explicit Client Access)" },
                    { value: "admin", label: "Admin (All Clients + Invites)" },
                    { value: "owner", label: "Owner (Full Agency Control)" }
                  ]}
                />
                <button 
                  type="submit"
                  disabled={isInvitingMember || !newMemberEmail.trim()}
                  className="flex items-center justify-center gap-2 px-5 py-2.5 bg-primary text-primary-foreground text-xs font-bold rounded-xl hover:bg-primary/90 transition-colors disabled:opacity-50 shadow-xs cursor-pointer whitespace-nowrap"
                >
                  {isInvitingMember ? <Loader2 size={14} className="animate-spin" /> : <UserPlus size={14} />}
                  <span>Invite to Agency</span>
                </button>
              </form>

              {/* Environmental Failure Feedback (Layer 1 Paranoia) */}
              <AnimatePresence>
                {inviteErrorNotice && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className="mt-3 p-3 bg-amber-500/10 border border-amber-500/30 rounded-xl flex items-start gap-2.5 text-xs text-amber-800 dark:text-amber-200"
                  >
                    <AlertTriangle size={15} className="shrink-0 mt-0.5 text-amber-600" />
                    <span>{inviteErrorNotice}</span>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* Team Members List */}
            <div className="space-y-3">
              <h3 className="text-sm font-bold text-foreground">Agency Team Members ({members.length})</h3>

              <div className="divide-y divide-border/60 rounded-xl border border-border/60 bg-card overflow-hidden shadow-xs">
                {members.map(m => {
                  const isOwnerOrAdmin = m.role === 'owner' || m.role === 'admin';

                  return (
                    <div key={m.id} className="p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
                      <div>
                        <div className="flex items-center gap-2.5 mb-1">
                          <h4 className="text-sm font-bold text-foreground">{m.display_name}</h4>
                          <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full capitalize ${
                            m.role === 'owner' 
                              ? 'bg-purple-500/10 text-purple-600 border border-purple-500/20' 
                              : m.role === 'admin' 
                              ? 'bg-primary/10 text-primary border border-primary/20' 
                              : 'bg-muted text-muted-foreground'
                          }`}>
                            {m.role}
                          </span>
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {isOwnerOrAdmin ? (
                            <span className="text-emerald-600 font-semibold flex items-center gap-1">
                              <ShieldCheck size={13} /> Full Access to All {clients.length} Client Workspaces
                            </span>
                          ) : (
                            <span>Assigned to {m.access.length} of {clients.length} Client Workspaces</span>
                          )}
                        </p>
                      </div>

                      {/* Client delegation controls */}
                      {!isOwnerOrAdmin && clients.length > 0 && (
                        <div className="flex items-center gap-2 self-start md:self-auto">
                          <button
                            type="button"
                            onClick={() => setManagingMember(m)}
                            className="flex items-center gap-1.5 px-3 py-1.5 bg-muted hover:bg-muted/80 rounded-xl text-xs font-semibold text-foreground transition-colors cursor-pointer"
                          >
                            <Shield size={13} className="text-primary" />
                            <span>Manage Client Access ({m.access.length})</span>
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* ─── TAB 3: WHITE-LABEL BRANDING & PORTAL CONFIGURATION ────────────── */}
        {activeTab === 'whitelabel' && (
          <div className="space-y-6">
            <div className="p-6 rounded-xl border border-border/60 bg-card shadow-xs">
              <div className="flex items-center gap-2.5 mb-2">
                <Palette size={20} className="text-primary" />
                <h3 className="text-base font-bold text-foreground">Agency White-Label Branding Studio</h3>
              </div>
              <p className="text-xs text-muted-foreground mb-6">
                Deliver client-facing campaign reporting under your own agency identity, custom logo, and domain.
              </p>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-4">
                  <div>
                    <label className="text-xs font-bold text-foreground block mb-1.5">Agency Brand Title</label>
                    <input 
                      type="text" 
                      value={whitelabelBrand}
                      onChange={e => setWhitelabelBrand(e.target.value)}
                      className="w-full bg-background border border-border/60 rounded-xl px-3.5 py-2 text-xs font-semibold text-foreground focus:outline-none focus:border-primary"
                    />
                  </div>

                  <div>
                    <label className="text-xs font-bold text-foreground block mb-1.5 flex items-center gap-1.5">
                      <Globe size={13} className="text-primary" />
                      Custom CNAME Portal Domain
                    </label>
                    <input 
                      type="text" 
                      value={whitelabelDomain}
                      onChange={e => setWhitelabelDomain(e.target.value)}
                      className="w-full bg-background border border-border/60 rounded-xl px-3.5 py-2 text-xs font-mono text-foreground focus:outline-none focus:border-primary"
                    />
                    <p className="text-[11px] text-muted-foreground mt-1">Point your DNS CNAME record to cname.elein.ai</p>
                  </div>

                  <div>
                    <label className="text-xs font-bold text-foreground block mb-1.5">Brand Accent Color</label>
                    <div className="flex items-center gap-3">
                      <input 
                        type="color" 
                        value={whitelabelColor}
                        onChange={e => setWhitelabelColor(e.target.value)}
                        className="w-8 h-8 rounded-lg cursor-pointer bg-transparent border-0"
                      />
                      <span className="text-xs font-mono font-bold text-muted-foreground">{whitelabelColor}</span>
                    </div>
                  </div>

                  <button
                    type="button"
                    disabled={isSavingWhitelabel}
                    onClick={handleSaveWhitelabel}
                    className="flex items-center gap-2 px-5 py-2.5 bg-primary text-primary-foreground text-xs font-bold rounded-xl hover:bg-primary/90 transition-all shadow-xs cursor-pointer disabled:opacity-50"
                  >
                    {isSavingWhitelabel ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                    <span>{isSavingWhitelabel ? 'Saving Settings...' : 'Save Branding Configurations'}</span>
                  </button>
                </div>

                {/* Live Client Portal Preview Card */}
                <div className="p-5 rounded-xl bg-muted/30 border border-border/60 flex flex-col justify-between">
                  <div>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block mb-3">
                      Live Client Portal Mockup Preview
                    </span>
                    <div className="p-4 rounded-xl bg-background border border-border/60 shadow-xs">
                      <div className="flex items-center justify-between pb-3 border-b border-border/40">
                        <div className="flex items-center gap-2">
                          <div className="w-6 h-6 rounded-md bg-primary text-primary-foreground flex items-center justify-center font-bold text-[10px]" style={{ backgroundColor: whitelabelColor }}>
                            {whitelabelBrand.substring(0, 2).toUpperCase()}
                          </div>
                          <span className="text-xs font-bold text-foreground">{whitelabelBrand}</span>
                        </div>
                        <span className="text-[10px] font-mono text-muted-foreground">{whitelabelDomain}</span>
                      </div>
                      <div className="mt-4 space-y-2">
                        <div className="h-4 bg-muted/60 rounded-md w-3/4" />
                        <div className="h-8 bg-muted/40 rounded-md w-full" />
                        <div className="flex gap-2 pt-2">
                          <div className="h-12 bg-muted/50 rounded-lg flex-1" />
                          <div className="h-12 bg-muted/50 rounded-lg flex-1" />
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="mt-4 pt-3 border-t border-border/40 flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Client View Link:</span>
                    <button
                      type="button"
                      onClick={() => {
                        navigator.clipboard.writeText(`https://${whitelabelDomain}/portal`);
                        setIsCopiedPortalLink(true);
                        toast.success("Portal link copied to clipboard");
                        setTimeout(() => setIsCopiedPortalLink(false), 3000);
                      }}
                      className="flex items-center gap-1.5 px-3 py-1 bg-card hover:bg-muted border border-border/60 rounded-lg text-xs font-semibold text-foreground transition-all cursor-pointer"
                    >
                      {isCopiedPortalLink ? <Check size={12} className="text-emerald-500" /> : <Copy size={12} />}
                      <span>{isCopiedPortalLink ? "Copied" : "Copy Portal URL"}</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ─── TAB 4: CREDIT DELEGATIONS & SUB-ACCOUNT QUOTAS (STAGE 27) ────── */}
        {activeTab === 'credits' && (
          <div className="space-y-6">
            {/* 4-KPI Overview Bar */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <SpotlightCard className="p-5 rounded-xl border border-border/70 bg-card shadow-xs">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">Master Credit Pool</span>
                  <div className="p-2 bg-amber-500/10 text-amber-500 rounded-lg">
                    <Coins size={16} />
                  </div>
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-extrabold text-foreground font-mono">
                    {(creditsOverview?.total_agency_balance ?? 0).toLocaleString()}
                  </span>
                  <span className="text-[11px] font-semibold text-emerald-500">Available</span>
                </div>
                <p className="text-[11px] text-muted-foreground mt-1">Ready for sub-account delegation</p>
                <div className="mt-3 pt-3 border-t border-border/40">
                  <button
                    type="button"
                    onClick={() => navigate('/billing')}
                    className="text-xs text-primary font-bold hover:underline flex items-center gap-1 cursor-pointer"
                  >
                    <span>Top Up Master Pool</span>
                    <ArrowUpRight size={12} />
                  </button>
                </div>
              </SpotlightCard>

              <SpotlightCard className="p-5 rounded-xl border border-border/70 bg-card shadow-xs">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">Total Delegated</span>
                  <div className="p-2 bg-primary/10 text-primary rounded-lg">
                    <ArrowUpRight size={16} />
                  </div>
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-extrabold text-foreground font-mono">
                    {(creditsOverview?.total_delegated_credits ?? 0).toLocaleString()}
                  </span>
                  <span className="text-[11px] font-semibold text-muted-foreground">Credits</span>
                </div>
                <p className="text-[11px] text-muted-foreground mt-1">Distributed across {clients.length} clients</p>
              </SpotlightCard>

              <SpotlightCard className="p-5 rounded-xl border border-border/70 bg-card shadow-xs">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">Total Consumed</span>
                  <div className="p-2 bg-purple-500/10 text-purple-500 rounded-lg">
                    <Sparkles size={16} />
                  </div>
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-extrabold text-foreground font-mono">
                    {(creditsOverview?.total_consumed_credits ?? 0).toLocaleString()}
                  </span>
                  <span className="text-[11px] font-semibold text-muted-foreground">Credits</span>
                </div>
                <p className="text-[11px] text-muted-foreground mt-1">Consumed in outreach & AI tasks</p>
              </SpotlightCard>

              <SpotlightCard className="p-5 rounded-xl border border-border/70 bg-card shadow-xs">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">Exhaustion Alerts</span>
                  <div className={`p-2 rounded-lg ${
                    (creditsOverview?.clients.filter(c => c.status !== 'healthy').length ?? 0) > 0
                      ? 'bg-destructive/10 text-destructive'
                      : 'bg-emerald-500/10 text-emerald-500'
                  }`}>
                    <AlertTriangle size={16} />
                  </div>
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-extrabold text-foreground font-mono">
                    {creditsOverview?.clients.filter(c => c.status !== 'healthy').length ?? 0}
                  </span>
                  <span className="text-[11px] font-semibold text-muted-foreground">Workspaces</span>
                </div>
                <p className="text-[11px] text-muted-foreground mt-1">
                  {(creditsOverview?.clients.filter(c => c.status !== 'healthy').length ?? 0) > 0
                    ? 'Require credit replenishment'
                    : 'All client quotas healthy'}
                </p>
              </SpotlightCard>
            </div>

            {/* Sub-Accounts Allocation & Quota Table */}
            <div className="bg-card border border-border/60 rounded-xl overflow-hidden shadow-xs">
              <div className="p-5 border-b border-border/60 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-bold text-foreground flex items-center gap-2">
                    <Coins size={16} className="text-primary" />
                    Sub-Account Credit Delegations & Quotas
                  </h3>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Allocate dedicated token budgets to client accounts. When client credits deplete, campaigns halt or overdraft protection applies.
                  </p>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="bg-muted/30 border-b border-border/60 text-[11px] text-muted-foreground uppercase tracking-wider font-semibold">
                      <th className="py-3 px-5">Client Workspace</th>
                      <th className="py-3 px-5">Credit Balance</th>
                      <th className="py-3 px-5">Total Delegated</th>
                      <th className="py-3 px-5">Total Consumed</th>
                      <th className="py-3 px-5">Monthly Auto-Refill</th>
                      <th className="py-3 px-5 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/40 font-medium">
                    {creditsOverview?.clients && creditsOverview.clients.length > 0 ? (
                      creditsOverview.clients.map((client) => {
                        const statusBadge = 
                          client.status === 'overdraft' ? (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-destructive/10 text-destructive border border-destructive/20 flex items-center gap-1">
                              <AlertCircle size={10} /> Overdraft
                            </span>
                          ) : client.status === 'low' ? (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-amber-500/10 text-amber-500 border border-amber-500/20 flex items-center gap-1">
                              <AlertTriangle size={10} /> Low Balance
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 flex items-center gap-1">
                              <CheckCircle2 size={10} /> Healthy
                            </span>
                          );

                        return (
                          <tr key={client.id} className="hover:bg-muted/20 transition-colors">
                            <td className="py-3.5 px-5">
                              <div>
                                <span className="font-bold text-foreground block">{client.name}</span>
                                <span className="text-[10px] text-muted-foreground font-mono">{client.id.substring(0, 8)}...</span>
                              </div>
                            </td>
                            <td className="py-3.5 px-5">
                              <div className="flex items-center gap-2">
                                <span className="font-mono font-bold text-foreground">
                                  {client.balance.toLocaleString()}
                                </span>
                                {statusBadge}
                              </div>
                            </td>
                            <td className="py-3.5 px-5 font-mono text-muted-foreground">
                              {client.allocated_budget.toLocaleString()}
                            </td>
                            <td className="py-3.5 px-5 font-mono text-destructive">
                              -{client.consumed_credits.toLocaleString()}
                            </td>
                            <td className="py-3.5 px-5">
                              {client.monthly_quota > 0 ? (
                                <span className="font-mono text-primary font-bold">
                                  +{client.monthly_quota.toLocaleString()} / mo
                                </span>
                              ) : (
                                <span className="text-muted-foreground italic">None (Manual)</span>
                              )}
                            </td>
                            <td className="py-3.5 px-5 text-right">
                              <div className="flex items-center justify-end gap-1.5">
                                <button
                                  type="button"
                                  onClick={() => setAllocationModal({
                                    isOpen: true,
                                    type: 'allocate',
                                    clientWorkspaceId: client.id,
                                    clientName: client.name,
                                    currentBalance: client.balance
                                  })}
                                  className="px-2.5 py-1 rounded-lg bg-primary/10 hover:bg-primary/20 text-primary font-bold text-[11px] transition-colors cursor-pointer flex items-center gap-1"
                                >
                                  <Plus size={11} /> Allocate
                                </button>
                                <button
                                  type="button"
                                  disabled={client.balance <= 0}
                                  onClick={() => setAllocationModal({
                                    isOpen: true,
                                    type: 'reclaim',
                                    clientWorkspaceId: client.id,
                                    clientName: client.name,
                                    currentBalance: client.balance
                                  })}
                                  className="px-2.5 py-1 rounded-lg border border-border/60 hover:bg-muted text-muted-foreground hover:text-foreground font-semibold text-[11px] transition-colors cursor-pointer disabled:opacity-40 flex items-center gap-1"
                                >
                                  <ArrowDownLeft size={11} /> Reclaim
                                </button>
                                <button
                                  type="button"
                                  onClick={() => setQuotaModal({
                                    isOpen: true,
                                    clientWorkspaceId: client.id,
                                    clientName: client.name,
                                    monthlyQuota: client.monthly_quota,
                                    exhaustionThreshold: client.exhaustion_alert_threshold
                                  })}
                                  className="p-1 rounded-lg border border-border/60 hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                                  title="Configure Quota & Alert Threshold"
                                >
                                  <Settings2 size={13} />
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })
                    ) : (
                      <tr>
                        <td colSpan={6} className="py-8 px-5 text-center text-muted-foreground">
                          No client sub-accounts created yet. Add a client workspace first.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Recent Delegations Audit Ledger */}
            {creditsOverview?.recent_allocations && creditsOverview.recent_allocations.length > 0 && (
              <div className="bg-card border border-border/60 rounded-xl p-5 shadow-xs space-y-3">
                <h4 className="text-sm font-bold text-foreground flex items-center gap-2">
                  <Sliders size={15} className="text-primary" />
                  Recent Delegations Audit Ledger
                </h4>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className="border-b border-border/40 text-[10px] text-muted-foreground uppercase font-semibold">
                        <th className="py-2 px-3">Date</th>
                        <th className="py-2 px-3">Action</th>
                        <th className="py-2 px-3">Amount</th>
                        <th className="py-2 px-3">Client</th>
                        <th className="py-2 px-3">Note</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/30">
                      {creditsOverview.recent_allocations.map((alloc) => (
                        <tr key={alloc.id} className="text-muted-foreground">
                          <td className="py-2.5 px-3 whitespace-nowrap">
                            {new Date(alloc.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                          </td>
                          <td className="py-2.5 px-3">
                            <span className="capitalize font-medium text-foreground">
                              {alloc.action_type.replace(/_/g, ' ')}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 font-mono font-bold">
                            <span className={alloc.amount > 0 ? "text-emerald-500" : "text-amber-500"}>
                              {alloc.amount > 0 ? `+${alloc.amount.toLocaleString()}` : alloc.amount.toLocaleString()}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 font-mono text-[11px]">
                            {creditsOverview.clients.find(c => c.id === alloc.client_workspace_id)?.name || alloc.client_workspace_id.substring(0, 8)}
                          </td>
                          <td className="py-2.5 px-3 italic text-[11px]">
                            {alloc.note || "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ─── TAB 5: INVOICING & STATEMENTS (Stage 28) ────────────────────────── */}
        {activeTab === 'statements' && (
          <div className="space-y-6">
            {/* Header & Generate Button */}
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-5 rounded-xl bg-gradient-to-r from-card via-card to-primary/5 border border-border/60 shadow-xs">
              <div>
                <div className="flex items-center gap-2">
                  <span className="p-1.5 rounded-lg bg-primary/10 text-primary">
                    <Receipt size={16} />
                  </span>
                  <h3 className="text-base font-bold text-foreground">
                    Client Invoicing & Billing Statements
                  </h3>
                </div>
                <p className="text-xs text-muted-foreground mt-1 max-w-2xl">
                  Consolidate multi-workspace platform retainers, track credit overdraft usage, generate branded client invoice statements, and export publication-ready tax PDFs.
                </p>
              </div>

              <button
                type="button"
                onClick={() => setGenerateModal(prev => ({ ...prev, isOpen: true }))}
                className="px-4 py-2.5 bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-bold rounded-xl flex items-center gap-2 transition-all cursor-pointer shadow-xs shrink-0"
              >
                <Plus size={14} />
                Generate Statement
              </button>
            </div>

            {/* 4-KPI Metric Ribbon */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="p-4 rounded-xl bg-card border border-border/60 shadow-xs">
                <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Total Invoiced</p>
                <div className="text-xl font-bold font-mono text-foreground mt-1">
                  ₹{((statements.reduce((acc, s) => acc + (s.total_cents || 0), 0)) / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
                <p className="text-[10px] text-muted-foreground mt-0.5">Cumulative billing gross</p>
              </div>

              <div className="p-4 rounded-xl bg-card border border-border/60 shadow-xs">
                <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Paid / Settled</p>
                <div className="text-xl font-bold font-mono text-emerald-600 mt-1">
                  ₹{((statements.filter(s => s.status === 'paid').reduce((acc, s) => acc + (s.total_cents || 0), 0)) / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
                <p className="text-[10px] text-muted-foreground mt-0.5">Reconciled payments</p>
              </div>

              <div className="p-4 rounded-xl bg-card border border-border/60 shadow-xs">
                <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Outstanding (Issued)</p>
                <div className="text-xl font-bold font-mono text-indigo-600 mt-1">
                  ₹{((statements.filter(s => s.status === 'issued').reduce((acc, s) => acc + (s.total_cents || 0), 0)) / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
                <p className="text-[10px] text-muted-foreground mt-0.5">Pending client remittance</p>
              </div>

              <div className="p-4 rounded-xl bg-card border border-border/60 shadow-xs">
                <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Statements Drafted</p>
                <div className="text-xl font-bold font-mono text-foreground mt-1">
                  {statements.length}
                </div>
                <p className="text-[10px] text-muted-foreground mt-0.5">Total invoice receipts</p>
              </div>
            </div>

            {/* Filter Ribbon & Client Selector */}
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-3 rounded-xl bg-card border border-border/60">
              <div className="flex items-center gap-2 overflow-x-auto">
                <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mr-1">Status:</span>
                {(['all', 'draft', 'issued', 'paid', 'void'] as const).map((st) => (
                  <button
                    key={st}
                    type="button"
                    onClick={() => setStatementFilterStatus(st)}
                    className={`px-2.5 py-1 text-xs font-semibold rounded-lg capitalize transition-colors cursor-pointer ${
                      statementFilterStatus === st
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground'
                    }`}
                  >
                    {st}
                  </button>
                ))}
              </div>

              <div className="flex items-center gap-2">
                <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider shrink-0">Client:</span>
                <CustomSelect
                  value={statementFilterClient}
                  onValueChange={setStatementFilterClient}
                  size="sm"
                  className="w-48"
                  triggerClassName="bg-background border-border rounded-lg px-2.5 py-1 text-xs text-foreground h-8"
                  options={[
                    { value: "all", label: "All Client Accounts" },
                    ...clients.map(c => ({ value: c.id, label: c.name })),
                  ]}
                />
              </div>
            </div>

            {/* Statements List Table */}
            {(() => {
              const filteredStatements = statements.filter(s => {
                if (statementFilterStatus !== 'all' && s.status !== statementFilterStatus) return false;
                if (statementFilterClient !== 'all' && s.client_workspace_id !== statementFilterClient) return false;
                return true;
              });

              if (filteredStatements.length === 0) {
                return (
                  <div className="p-12 text-center rounded-xl bg-card border border-border/60 space-y-3">
                    <div className="w-12 h-12 rounded-lg bg-muted flex items-center justify-center mx-auto text-muted-foreground">
                      <Receipt size={22} />
                    </div>
                    <h4 className="text-sm font-bold text-foreground">No Billing Statements Found</h4>
                    <p className="text-xs text-muted-foreground max-w-sm mx-auto">
                      {statements.length === 0
                        ? "Generate your first consolidated agency or client invoice statement to begin billing multi-account usage."
                        : "No statements match the selected status or client filter criteria."}
                    </p>
                    {statements.length === 0 && (
                      <button
                        type="button"
                        onClick={() => setGenerateModal(prev => ({ ...prev, isOpen: true }))}
                        className="px-4 py-2 bg-primary text-primary-foreground text-xs font-bold rounded-xl hover:bg-primary/90 transition-all cursor-pointer inline-flex items-center gap-2 mt-2"
                      >
                        <Plus size={13} />
                        Generate First Statement
                      </button>
                    )}
                  </div>
                );
              }

              return (
                <div className="rounded-xl bg-card border border-border/60 shadow-xs overflow-hidden">
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs text-left">
                      <thead className="bg-muted/40 text-muted-foreground font-semibold border-b border-border/60">
                        <tr>
                          <th className="py-3 px-4">Invoice #</th>
                          <th className="py-3 px-4">Target Scope</th>
                          <th className="py-3 px-4">Billing Period</th>
                          <th className="py-3 px-4 text-right">Billable Credits</th>
                          <th className="py-3 px-4 text-right">Total Due</th>
                          <th className="py-3 px-4">Status</th>
                          <th className="py-3 px-4 text-right">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/30">
                        {filteredStatements.map((stmt) => {
                          const clientName = stmt.client_workspace_id
                            ? (clients.find(c => c.id === stmt.client_workspace_id)?.name || stmt.client_workspace_id.substring(0, 8))
                            : 'Consolidated (All Clients)';
                          const currSym = stmt.currency === 'INR' ? '₹' : '$';

                          return (
                            <tr key={stmt.id} className="hover:bg-muted/20 transition-colors">
                              <td className="py-3.5 px-4 font-mono font-bold text-foreground whitespace-nowrap">
                                {stmt.invoice_number}
                              </td>
                              <td className="py-3.5 px-4">
                                <span className="font-semibold text-foreground">{clientName}</span>
                                {stmt.breakdown_data?.clients && (
                                  <span className="block text-[10px] text-muted-foreground">
                                    {stmt.breakdown_data.clients.length} client workspace{stmt.breakdown_data.clients.length === 1 ? '' : 's'} itemized
                                  </span>
                                )}
                              </td>
                              <td className="py-3.5 px-4 text-muted-foreground whitespace-nowrap">
                                {stmt.period_start} &rarr; {stmt.period_end}
                              </td>
                              <td className="py-3.5 px-4 text-right font-mono font-bold text-foreground">
                                {(stmt.breakdown_data?.total_billable_credits || 0).toLocaleString()}
                              </td>
                              <td className="py-3.5 px-4 text-right font-mono font-bold text-foreground whitespace-nowrap">
                                {currSym}{(stmt.total_cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                              </td>
                              <td className="py-3.5 px-4">
                                <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                                  stmt.status === 'paid'
                                    ? 'bg-emerald-500/10 text-emerald-600 border border-emerald-500/20'
                                    : stmt.status === 'issued'
                                    ? 'bg-indigo-500/10 text-indigo-600 border border-indigo-500/20'
                                    : stmt.status === 'void'
                                    ? 'bg-destructive/10 text-destructive border border-destructive/20'
                                    : 'bg-muted text-muted-foreground border border-border'
                                }`}>
                                  {stmt.status}
                                </span>
                              </td>
                              <td className="py-3.5 px-4 text-right">
                                <div className="flex items-center justify-end gap-1.5">
                                  <button
                                    type="button"
                                    onClick={() => setViewingStatement(stmt)}
                                    className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors cursor-pointer"
                                    title="View Statement Details"
                                  >
                                    <FileText size={14} />
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => handleExportStatement(stmt.id)}
                                    className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors cursor-pointer"
                                    title="Print or Export PDF"
                                  >
                                    <Printer size={14} />
                                  </button>
                                  {stmt.status === 'draft' && (
                                    <button
                                      type="button"
                                      onClick={() => handleUpdateStatementStatus(stmt.id, 'issued')}
                                      className="px-2 py-1 text-[11px] font-semibold text-indigo-600 bg-indigo-500/10 hover:bg-indigo-500/20 rounded-lg transition-colors cursor-pointer whitespace-nowrap"
                                    >
                                      Issue
                                    </button>
                                  )}
                                  {stmt.status === 'issued' && (
                                    <button
                                      type="button"
                                      onClick={() => handleUpdateStatementStatus(stmt.id, 'paid')}
                                      className="px-2 py-1 text-[11px] font-semibold text-emerald-600 bg-emerald-500/10 hover:bg-emerald-500/20 rounded-lg transition-colors cursor-pointer whitespace-nowrap"
                                    >
                                      Mark Paid
                                    </button>
                                  )}
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              );
            })()}
          </div>
        )}
      </div>

      {/* ─── MODAL: MANAGE CLIENT ACCESS (Layer 0 & 2) ────────────────────────── */}
      <AnimatePresence>
        {managingMember && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-lg bg-card rounded-xl shadow-2xl border border-border p-6 flex flex-col max-h-[85vh] overflow-hidden"
            >
              <div className="flex items-start justify-between pb-4 border-b border-border/60 mb-4">
                <div>
                  <h3 className="text-base font-bold text-foreground">
                    Client Access Delegation: {managingMember.display_name}
                  </h3>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Select which client workspaces this operator has permission to view and manage.
                  </p>
                </div>
                <button 
                  onClick={() => setManagingMember(null)}
                  className="text-muted-foreground hover:text-foreground cursor-pointer"
                >
                  <X size={16} />
                </button>
              </div>

              {/* Quick Batch Actions */}
              <div className="flex items-center gap-2 mb-4">
                <button
                  type="button"
                  onClick={() => handleBatchGrantAll(managingMember)}
                  className="px-2.5 py-1 bg-muted hover:bg-muted/80 text-foreground text-xs font-semibold rounded-lg transition-colors cursor-pointer"
                >
                  Grant All ({clients.length})
                </button>
                <button
                  type="button"
                  onClick={() => handleBatchRevokeAll(managingMember)}
                  className="px-2.5 py-1 text-destructive hover:bg-destructive/10 text-xs font-semibold rounded-lg transition-colors cursor-pointer"
                >
                  Revoke All
                </button>
              </div>

              {/* Checkboxes List */}
              <div className="flex-1 overflow-y-auto space-y-2 mb-5 pr-1">
                {clients.map(c => {
                  const hasAccess = managingMember.access.includes(c.id);

                  return (
                    <label 
                      key={c.id} 
                      className={`flex items-center justify-between p-3 rounded-xl border transition-all cursor-pointer ${
                        hasAccess 
                          ? 'border-primary/40 bg-primary/5' 
                          : 'border-border/60 bg-background hover:bg-muted/40'
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <input 
                          type="checkbox" 
                          checked={hasAccess}
                          onChange={() => handleToggleAccess(managingMember.id, c.id, hasAccess)}
                          className="rounded border-border text-primary focus:ring-primary w-4 h-4 cursor-pointer"
                        />
                        <span className="text-xs font-bold text-foreground">{c.name}</span>
                      </div>
                      <span className="text-[10px] font-mono text-muted-foreground">{c.id.substring(0, 8)}...</span>
                    </label>
                  );
                })}
              </div>

              <div className="flex items-center justify-end pt-3 border-t border-border/60">
                <button
                  type="button"
                  onClick={() => setManagingMember(null)}
                  className="px-4 py-2 bg-primary text-primary-foreground text-xs font-bold rounded-xl hover:bg-primary/90 transition-all cursor-pointer"
                >
                  Done
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* ─── MODAL: ALLOCATE / RECLAIM CREDITS (Layer 0, 1 & 2) ────────────────── */}
      <AnimatePresence>
        {allocationModal.isOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-lg bg-card rounded-xl shadow-2xl border border-border p-6 flex flex-col max-h-[90vh] overflow-hidden"
            >
              <div className="flex items-start justify-between pb-4 border-b border-border/60 mb-4">
                <div className="flex items-center gap-3">
                  <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${
                    allocationModal.type === 'allocate' 
                      ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20' 
                      : 'bg-amber-500/10 text-amber-500 border border-amber-500/20'
                  }`}>
                    {allocationModal.type === 'allocate' ? <ArrowUpRight size={18} /> : <ArrowDownLeft size={18} />}
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-foreground">
                      {allocationModal.type === 'allocate' ? 'Delegate Credits to Client' : 'Reclaim Client Credits'}
                    </h3>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Client Workspace: <span className="font-semibold text-foreground">{allocationModal.clientName}</span>
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setAllocationModal(prev => ({ ...prev, isOpen: false }))}
                  className="text-muted-foreground hover:text-foreground cursor-pointer p-1"
                >
                  <X size={16} />
                </button>
              </div>

              <form onSubmit={handleExecuteCreditTransfer} className="space-y-4">
                {/* Balance Impact Cards */}
                <div className="grid grid-cols-2 gap-3 p-3 rounded-xl bg-muted/40 border border-border/60">
                  <div>
                    <span className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider block">Master Agency Pool</span>
                    <div className="text-sm font-bold font-mono text-foreground mt-0.5">
                      {(creditsOverview?.master_workspace.balance ?? 0).toLocaleString()}
                      <span className="text-xs font-normal text-muted-foreground"> credits</span>
                    </div>
                    <div className="text-[11px] text-muted-foreground mt-1">
                      After: <span className="font-semibold text-foreground font-mono">
                        {allocationModal.type === 'allocate'
                          ? Math.max(0, (creditsOverview?.master_workspace.balance ?? 0) - (allocationAmount || 0)).toLocaleString()
                          : ((creditsOverview?.master_workspace.balance ?? 0) + (allocationAmount || 0)).toLocaleString()}
                      </span>
                    </div>
                  </div>
                  <div>
                    <span className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider block">Client Current Balance</span>
                    <div className="text-sm font-bold font-mono text-foreground mt-0.5">
                      {allocationModal.currentBalance.toLocaleString()}
                      <span className="text-xs font-normal text-muted-foreground"> credits</span>
                    </div>
                    <div className="text-[11px] text-muted-foreground mt-1">
                      After: <span className={`font-semibold font-mono ${
                        allocationModal.type === 'reclaim' && (allocationModal.currentBalance - (allocationAmount || 0)) <= 0
                          ? 'text-amber-500'
                          : 'text-foreground'
                      }`}>
                        {allocationModal.type === 'allocate'
                          ? (allocationModal.currentBalance + (allocationAmount || 0)).toLocaleString()
                          : Math.max(0, allocationModal.currentBalance - (allocationAmount || 0)).toLocaleString()}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Amount Input */}
                <div>
                  <label className="text-xs font-semibold text-foreground block mb-1.5">
                    Credit Amount to {allocationModal.type === 'allocate' ? 'Delegate' : 'Reclaim'}
                  </label>
                  <div className="relative">
                    <input
                      type="number"
                      min={1}
                      max={allocationModal.type === 'allocate' 
                        ? (creditsOverview?.master_workspace.balance ?? 999999) 
                        : allocationModal.currentBalance}
                      step={50}
                      value={allocationAmount || ''}
                      onChange={(e) => setAllocationAmount(Math.max(0, parseInt(e.target.value) || 0))}
                      className="w-full bg-background border border-border rounded-xl px-3.5 py-2.5 text-sm font-mono font-bold text-foreground focus:outline-hidden focus:border-primary"
                      placeholder="e.g. 1000"
                      required
                    />
                    <span className="absolute right-3.5 top-2.5 text-xs text-muted-foreground font-semibold">credits</span>
                  </div>

                  {/* Preset Chips (Layer 2 Paranoia) */}
                  <div className="flex items-center gap-1.5 mt-2 flex-wrap">
                    {[500, 1000, 2500, 5000].map((preset) => (
                      <button
                        key={preset}
                        type="button"
                        onClick={() => setAllocationAmount(preset)}
                        className={`px-2.5 py-1 text-xs rounded-lg font-mono font-medium border transition-colors cursor-pointer ${
                          allocationAmount === preset
                            ? 'bg-primary/10 border-primary text-primary'
                            : 'bg-muted/30 border-border/60 hover:bg-muted text-muted-foreground hover:text-foreground'
                        }`}
                      >
                        +{preset.toLocaleString()}
                      </button>
                    ))}
                    {allocationModal.type === 'reclaim' && allocationModal.currentBalance > 0 && (
                      <button
                        type="button"
                        onClick={() => setAllocationAmount(allocationModal.currentBalance)}
                        className="px-2.5 py-1 text-xs rounded-lg font-mono font-medium border bg-amber-500/10 border-amber-500/30 text-amber-500 hover:bg-amber-500/20 transition-colors cursor-pointer"
                      >
                        Reclaim All ({allocationModal.currentBalance.toLocaleString()})
                      </button>
                    )}
                  </div>
                </div>

                {/* Audit Note (Layer 0) */}
                <div>
                  <label className="text-xs font-semibold text-foreground block mb-1.5">
                    Audit Log Note <span className="text-muted-foreground font-normal">(optional)</span>
                  </label>
                  <input
                    type="text"
                    value={allocationNote}
                    onChange={(e) => setAllocationNote(e.target.value)}
                    placeholder={allocationModal.type === 'allocate' ? 'e.g. Monthly retainer Q4 allocation' : 'e.g. Surplus credit balance recall'}
                    className="w-full bg-background border border-border rounded-xl px-3.5 py-2 text-xs text-foreground focus:outline-hidden focus:border-primary"
                    maxLength={140}
                  />
                </div>

                {/* Warning message for reclaim or limit exceeded (Layer 1 & 2 Paranoia) */}
                {allocationModal.type === 'allocate' && (allocationAmount > (creditsOverview?.master_workspace.balance ?? 0)) && (
                  <div className="p-2.5 rounded-lg bg-destructive/10 border border-destructive/30 flex items-center gap-2 text-destructive text-xs">
                    <AlertTriangle size={14} className="shrink-0" />
                    <span>Requested amount exceeds Master Agency Pool balance ({(creditsOverview?.master_workspace.balance ?? 0).toLocaleString()} available).</span>
                  </div>
                )}

                {allocationModal.type === 'reclaim' && (allocationAmount > allocationModal.currentBalance) && (
                  <div className="p-2.5 rounded-lg bg-destructive/10 border border-destructive/30 flex items-center gap-2 text-destructive text-xs">
                    <AlertTriangle size={14} className="shrink-0" />
                    <span>Cannot reclaim more than client's active balance ({allocationModal.currentBalance.toLocaleString()} available).</span>
                  </div>
                )}

                {/* Form Actions */}
                <div className="flex items-center justify-end gap-2.5 pt-3 border-t border-border/60">
                  <button
                    type="button"
                    onClick={() => setAllocationModal(prev => ({ ...prev, isOpen: false }))}
                    className="px-4 py-2 text-xs font-semibold text-muted-foreground hover:text-foreground cursor-pointer transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={
                      isSubmittingTransfer || 
                      allocationAmount <= 0 ||
                      (allocationModal.type === 'allocate' && allocationAmount > (creditsOverview?.master_workspace.balance ?? 0)) ||
                      (allocationModal.type === 'reclaim' && allocationAmount > allocationModal.currentBalance)
                    }
                    className={`px-4 py-2 text-xs font-bold rounded-xl flex items-center gap-2 transition-all cursor-pointer shadow-sm ${
                      allocationModal.type === 'allocate'
                        ? 'bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-50'
                        : 'bg-amber-600 hover:bg-amber-500 text-white disabled:opacity-50'
                    }`}
                  >
                    {isSubmittingTransfer ? (
                      <>
                        <Loader2 size={13} className="animate-spin" />
                        Transferring...
                      </>
                    ) : (
                      <>
                        <Coins size={13} />
                        {allocationModal.type === 'allocate' ? 'Confirm Delegation' : 'Confirm Reclaim'}
                      </>
                    )}
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* ─── MODAL: CLIENT QUOTA & ALERT SETTINGS (Layer 0, 1 & 2) ────────────── */}
      <AnimatePresence>
        {quotaModal.isOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-md bg-card rounded-xl shadow-2xl border border-border p-6 flex flex-col max-h-[90vh] overflow-hidden"
            >
              <div className="flex items-start justify-between pb-4 border-b border-border/60 mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-lg flex items-center justify-center bg-primary/10 text-primary border border-primary/20">
                    <Sliders size={18} />
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-foreground">
                      Quota & Alert Controls
                    </h3>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Client Workspace: <span className="font-semibold text-foreground">{quotaModal.clientName}</span>
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setQuotaModal(prev => ({ ...prev, isOpen: false }))}
                  className="text-muted-foreground hover:text-foreground cursor-pointer p-1"
                >
                  <X size={16} />
                </button>
              </div>

              <form onSubmit={handleSaveClientQuota} className="space-y-4">
                <div>
                  <label className="text-xs font-semibold text-foreground block mb-1">
                    Monthly Recurring Quota (Credits)
                  </label>
                  <p className="text-[11px] text-muted-foreground mb-2">
                    Credits automatically replenished from Master Pool at the start of each monthly billing cycle. Set to 0 for purely manual credit grants.
                  </p>
                  <div className="relative">
                    <input
                      type="number"
                      min={0}
                      step={100}
                      value={quotaModal.monthlyQuota || 0}
                      onChange={(e) => setQuotaModal(prev => ({ ...prev, monthlyQuota: Math.max(0, parseInt(e.target.value) || 0) }))}
                      className="w-full bg-background border border-border rounded-xl px-3.5 py-2.5 text-sm font-mono font-bold text-foreground focus:outline-hidden focus:border-primary"
                    />
                    <span className="absolute right-3.5 top-2.5 text-xs text-muted-foreground font-semibold">credits / mo</span>
                  </div>
                </div>

                <div>
                  <label className="text-xs font-semibold text-foreground block mb-1">
                    Exhaustion Alert Threshold
                  </label>
                  <p className="text-[11px] text-muted-foreground mb-2">
                    Flags an alert badge and notifies agency admins when this sub-account's balance dips below this floor.
                  </p>
                  <div className="relative">
                    <input
                      type="number"
                      min={0}
                      step={50}
                      value={quotaModal.exhaustionThreshold || 0}
                      onChange={(e) => setQuotaModal(prev => ({ ...prev, exhaustionThreshold: Math.max(0, parseInt(e.target.value) || 0) }))}
                      className="w-full bg-background border border-border rounded-xl px-3.5 py-2.5 text-sm font-mono font-bold text-foreground focus:outline-hidden focus:border-primary"
                    />
                    <span className="absolute right-3.5 top-2.5 text-xs text-muted-foreground font-semibold">credits</span>
                  </div>
                </div>

                <div className="flex items-center justify-end gap-2.5 pt-3 border-t border-border/60">
                  <button
                    type="button"
                    onClick={() => setQuotaModal(prev => ({ ...prev, isOpen: false }))}
                    className="px-4 py-2 text-xs font-semibold text-muted-foreground hover:text-foreground cursor-pointer transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isSavingQuota}
                    className="px-4 py-2 bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-bold rounded-xl flex items-center gap-2 transition-all cursor-pointer shadow-sm disabled:opacity-50"
                  >
                    {isSavingQuota ? (
                      <>
                        <Loader2 size={13} className="animate-spin" />
                        Saving Rules...
                      </>
                    ) : (
                      <>
                        <CheckCircle2 size={13} />
                        Save Parameters
                      </>
                    )}
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* ─── MODAL: GENERATE STATEMENT (Layer 0, 1 & 2) ────────────────────────── */}
      <AnimatePresence>
        {generateModal.isOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-xl bg-card rounded-xl shadow-2xl border border-border p-6 flex flex-col max-h-[90vh] overflow-hidden"
            >
              <div className="flex items-start justify-between pb-4 border-b border-border/60 mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-lg flex items-center justify-center bg-primary/10 text-primary border border-primary/20">
                    <Receipt size={18} />
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-foreground">
                      Generate Billing Statement
                    </h3>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Calculate usage fees, credit overages, and assemble itemized client invoice.
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setGenerateModal(prev => ({ ...prev, isOpen: false }))}
                  className="text-muted-foreground hover:text-foreground cursor-pointer p-1"
                >
                  <X size={16} />
                </button>
              </div>

              <form onSubmit={handleGenerateStatement} className="space-y-4 overflow-y-auto pr-1">
                {/* Target Scope */}
                <div>
                  <label className="text-xs font-semibold text-foreground block mb-1">
                    Target Billing Scope
                  </label>
                  <CustomSelect
                    value={generateModal.clientWorkspaceId}
                    onValueChange={(val) => setGenerateModal(prev => ({ ...prev, clientWorkspaceId: val }))}
                    size="sm"
                    triggerClassName="w-full bg-background border-border rounded-xl px-3.5 py-2 text-xs text-foreground"
                    placeholder={`Consolidated Roll-Up (All ${clients.length} Client Workspaces)`}
                    options={[
                      { value: "", label: `Consolidated Roll-Up (All ${clients.length} Client Workspaces)` },
                      ...clients.map(c => ({ value: c.id, label: `Single Client: ${c.name}` })),
                    ]}
                  />
                </div>

                {/* Period Dates */}
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs font-semibold text-foreground block mb-1">
                      Period Start Date
                    </label>
                    <input
                      type="date"
                      value={generateModal.periodStart}
                      onChange={(e) => setGenerateModal(prev => ({ ...prev, periodStart: e.target.value }))}
                      required
                      className="w-full bg-background border border-border rounded-xl px-3.5 py-2 text-xs font-mono text-foreground focus:outline-hidden focus:border-primary"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-semibold text-foreground block mb-1">
                      Period End Date
                    </label>
                    <input
                      type="date"
                      value={generateModal.periodEnd}
                      onChange={(e) => setGenerateModal(prev => ({ ...prev, periodEnd: e.target.value }))}
                      required
                      className="w-full bg-background border border-border rounded-xl px-3.5 py-2 text-xs font-mono text-foreground focus:outline-hidden focus:border-primary"
                    />
                  </div>
                </div>

                {/* Pricing Parameters Grid */}
                <div className="grid grid-cols-3 gap-3 p-3.5 rounded-xl bg-muted/40 border border-border/60">
                  <div>
                    <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1">
                      Credit Rate
                    </label>
                    <div className="relative">
                      <input
                        type="number"
                        min={1}
                        step={10}
                        value={generateModal.unitCreditRateCents}
                        onChange={(e) => setGenerateModal(prev => ({ ...prev, unitCreditRateCents: Math.max(1, parseInt(e.target.value) || 1) }))}
                        className="w-full bg-background border border-border rounded-lg px-2.5 py-1.5 text-xs font-mono font-bold text-foreground"
                      />
                      <span className="absolute right-2 top-1.5 text-[10px] text-muted-foreground">paise</span>
                    </div>
                    <span className="text-[10px] text-muted-foreground mt-0.5 block">₹{(generateModal.unitCreditRateCents / 100).toFixed(2)}/cr</span>
                  </div>

                  <div>
                    <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1">
                      Base Retainer
                    </label>
                    <div className="relative">
                      <input
                        type="number"
                        min={0}
                        step={500}
                        value={generateModal.platformBaseFeeCents / 100}
                        onChange={(e) => setGenerateModal(prev => ({ ...prev, platformBaseFeeCents: Math.max(0, parseInt(e.target.value) || 0) * 100 }))}
                        className="w-full bg-background border border-border rounded-lg px-2.5 py-1.5 text-xs font-mono font-bold text-foreground"
                      />
                      <span className="absolute right-2 top-1.5 text-[10px] text-muted-foreground">₹/client</span>
                    </div>
                    <span className="text-[10px] text-muted-foreground mt-0.5 block">per client/mo</span>
                  </div>

                  <div>
                    <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1">
                      Tax (GST/VAT)
                    </label>
                    <div className="relative">
                      <input
                        type="number"
                        min={0}
                        max={100}
                        step={1}
                        value={generateModal.taxPercent}
                        onChange={(e) => setGenerateModal(prev => ({ ...prev, taxPercent: Math.max(0, parseFloat(e.target.value) || 0) }))}
                        className="w-full bg-background border border-border rounded-lg px-2.5 py-1.5 text-xs font-mono font-bold text-foreground"
                      />
                      <span className="absolute right-2 top-1.5 text-[10px] text-muted-foreground">%</span>
                    </div>
                    <span className="text-[10px] text-muted-foreground mt-0.5 block">standard GST</span>
                  </div>
                </div>

                {/* Notes */}
                <div>
                  <label className="text-xs font-semibold text-foreground block mb-1">
                    Invoice Notes & Payment Terms
                  </label>
                  <textarea
                    rows={2}
                    value={generateModal.notes}
                    onChange={(e) => setGenerateModal(prev => ({ ...prev, notes: e.target.value }))}
                    className="w-full bg-background border border-border rounded-xl px-3.5 py-2 text-xs text-foreground focus:outline-hidden focus:border-primary resize-none"
                    placeholder="e.g. Net 15 days payment terms. Wire transfer instructions..."
                  />
                </div>

                {/* Actions */}
                <div className="flex items-center justify-end gap-2.5 pt-3 border-t border-border/60">
                  <button
                    type="button"
                    onClick={() => setGenerateModal(prev => ({ ...prev, isOpen: false }))}
                    className="px-4 py-2 text-xs font-semibold text-muted-foreground hover:text-foreground cursor-pointer transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isGeneratingStatement}
                    className="px-4 py-2 bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-bold rounded-xl flex items-center gap-2 transition-all cursor-pointer shadow-sm disabled:opacity-50"
                  >
                    {isGeneratingStatement ? (
                      <>
                        <Loader2 size={13} className="animate-spin" />
                        Generating Statement...
                      </>
                    ) : (
                      <>
                        <Receipt size={13} />
                        Assemble & Issue Draft
                      </>
                    )}
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* ─── MODAL: VIEW / INSPECT STATEMENT (Layer 0, 1 & 2) ─────────────────── */}
      <AnimatePresence>
        {viewingStatement && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-2xl bg-card rounded-xl shadow-2xl border border-border p-6 flex flex-col max-h-[90vh] overflow-hidden"
            >
              {/* Header */}
              <div className="flex items-start justify-between pb-4 border-b border-border/60 mb-4">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-base font-bold text-foreground font-mono">
                      {viewingStatement.invoice_number}
                    </h3>
                    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                      viewingStatement.status === 'paid'
                        ? 'bg-emerald-500/10 text-emerald-600 border border-emerald-500/20'
                        : viewingStatement.status === 'issued'
                        ? 'bg-indigo-500/10 text-indigo-600 border border-indigo-500/20'
                        : viewingStatement.status === 'void'
                        ? 'bg-destructive/10 text-destructive border border-destructive/20'
                        : 'bg-muted text-muted-foreground border border-border'
                    }`}>
                      {viewingStatement.status}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Period: <span className="font-semibold text-foreground">{viewingStatement.period_start} &rarr; {viewingStatement.period_end}</span>
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setViewingStatement(null)}
                  className="text-muted-foreground hover:text-foreground cursor-pointer p-1"
                >
                  <X size={16} />
                </button>
              </div>

              {/* Statement Content */}
              <div className="flex-1 overflow-y-auto space-y-4 pr-1">
                {/* Brand / Scope Info Box */}
                <div className="p-3.5 rounded-xl bg-muted/40 border border-border/60 flex items-center justify-between">
                  <div>
                    <span className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider block">Billed To</span>
                    <span className="text-xs font-bold text-foreground mt-0.5 block">
                      {viewingStatement.client_workspace_id
                        ? (clients.find(c => c.id === viewingStatement.client_workspace_id)?.name || viewingStatement.client_workspace_id)
                        : `All Agency Clients (${viewingStatement.breakdown_data?.clients?.length || 0} Accounts)`}
                    </span>
                  </div>
                  <div className="text-right">
                    <span className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider block">Total Billed</span>
                    <span className="text-sm font-bold font-mono text-foreground mt-0.5 block">
                      ₹{(viewingStatement.total_cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </span>
                  </div>
                </div>

                {/* Line Items Table */}
                <div className="rounded-xl border border-border/60 overflow-hidden">
                  <table className="w-full text-xs text-left">
                    <thead className="bg-muted/40 text-muted-foreground font-semibold border-b border-border/60">
                      <tr>
                        <th className="py-2.5 px-3">Client Workspace</th>
                        <th className="py-2.5 px-3 text-right">Retainer</th>
                        <th className="py-2.5 px-3 text-right">Credits</th>
                        <th className="py-2.5 px-3 text-right">Credit Fee</th>
                        <th className="py-2.5 px-3 text-right">Subtotal</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/30">
                      {(viewingStatement.breakdown_data?.clients || []).map((c) => (
                        <tr key={c.client_workspace_id} className="text-foreground">
                          <td className="py-2 px-3 font-medium">
                            {c.client_name}
                            <span className="block text-[10px] text-muted-foreground">
                              {c.campaigns_count} active campaign{c.campaigns_count === 1 ? '' : 's'}
                            </span>
                          </td>
                          <td className="py-2 px-3 text-right font-mono text-muted-foreground">
                            ₹{(c.platform_base_fee_cents / 100).toLocaleString()}
                          </td>
                          <td className="py-2 px-3 text-right font-mono text-muted-foreground">
                            {c.billable_credits.toLocaleString()} cr
                          </td>
                          <td className="py-2 px-3 text-right font-mono text-muted-foreground">
                            ₹{(c.credit_charge_cents / 100).toLocaleString()}
                          </td>
                          <td className="py-2 px-3 text-right font-mono font-bold">
                            ₹{(c.subtotal_cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Totals Summary */}
                <div className="flex justify-end pt-2">
                  <div className="w-64 space-y-1.5 text-xs">
                    <div className="flex justify-between text-muted-foreground">
                      <span>Subtotal:</span>
                      <span className="font-mono font-semibold text-foreground">
                        ₹{(viewingStatement.subtotal_cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </span>
                    </div>
                    <div className="flex justify-between text-muted-foreground">
                      <span>GST/VAT ({viewingStatement.breakdown_data?.tax_percent || 18}%):</span>
                      <span className="font-mono font-semibold text-foreground">
                        ₹{(viewingStatement.tax_cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </span>
                    </div>
                    <div className="flex justify-between border-t border-border pt-1.5 text-sm font-bold text-foreground">
                      <span>Total Due:</span>
                      <span className="font-mono">
                        ₹{(viewingStatement.total_cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </span>
                    </div>
                  </div>
                </div>

                {viewingStatement.notes && (
                  <div className="p-3 rounded-lg bg-muted/30 border border-border/50 text-[11px] text-muted-foreground">
                    <span className="font-bold text-foreground block mb-0.5">Notes & Remittance:</span>
                    {viewingStatement.notes}
                  </div>
                )}
              </div>

              {/* Footer Actions */}
              <div className="flex items-center justify-between pt-4 border-t border-border/60 mt-4">
                <button
                  type="button"
                  onClick={() => handleExportStatement(viewingStatement.id)}
                  className="px-3.5 py-2 bg-muted hover:bg-muted/80 text-foreground text-xs font-semibold rounded-xl flex items-center gap-2 transition-colors cursor-pointer"
                >
                  <Printer size={13} />
                  Print / Save PDF
                </button>

                <div className="flex items-center gap-2">
                  {viewingStatement.status !== 'issued' && viewingStatement.status !== 'paid' && (
                    <button
                      type="button"
                      disabled={isUpdatingStatus}
                      onClick={() => handleUpdateStatementStatus(viewingStatement.id, 'issued')}
                      className="px-3 py-1.5 text-xs font-semibold text-indigo-600 bg-indigo-500/10 hover:bg-indigo-500/20 rounded-xl transition-colors cursor-pointer"
                    >
                      Mark Issued
                    </button>
                  )}
                  {viewingStatement.status !== 'paid' && (
                    <button
                      type="button"
                      disabled={isUpdatingStatus}
                      onClick={() => handleUpdateStatementStatus(viewingStatement.id, 'paid')}
                      className="px-3 py-1.5 text-xs font-semibold text-emerald-600 bg-emerald-500/10 hover:bg-emerald-500/20 rounded-xl transition-colors cursor-pointer"
                    >
                      Mark Paid
                    </button>
                  )}
                  {viewingStatement.status !== 'void' && (
                    <button
                      type="button"
                      disabled={isUpdatingStatus}
                      onClick={() => handleUpdateStatementStatus(viewingStatement.id, 'void')}
                      className="px-3 py-1.5 text-xs font-semibold text-destructive hover:bg-destructive/10 rounded-xl transition-colors cursor-pointer"
                    >
                      Void
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => setViewingStatement(null)}
                    className="px-4 py-2 bg-primary text-primary-foreground text-xs font-bold rounded-xl hover:bg-primary/90 transition-all cursor-pointer"
                  >
                    Done
                  </button>
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
