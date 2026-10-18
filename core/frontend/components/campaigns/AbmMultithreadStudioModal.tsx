import React, { useState } from 'react';
import useSWR from 'swr';
import { 
  Building2, Users, RefreshCw, CheckCircle2, Copy, Check, 
  ExternalLink, Layers, ShieldCheck, Rocket, X, ChevronRight, Filter, 
  TrendingUp, Clock, Plus, Target, Briefcase, Lock, UserCheck, MessageSquare, Download, UserPlus
} from 'lucide-react';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/lib/apiClient';
import { usePaywall } from '@/contexts/PaywallContext';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

const fetcher = (url: string) => fetchWithAuth(url).then(r => r.json());

interface AbmMultithreadStudioProps {
  onClose?: () => void;
  campaignId?: string;
}

interface TargetAccount {
  id: string;
  company_name: string;
  domain: string;
  tier: 'tier_1' | 'tier_2' | 'tier_3';
  employee_count: number;
  industry: string;
  account_heat_score: number;
  stage: 'discovery' | 'multithreaded' | 'consensus_building' | 'opportunity';
  committee_count?: number;
  engaged_count?: number;
  replied_count?: number;
  meetings_count?: number;
}

interface CommitteeMember {
  id: string;
  account_id: string;
  prospect_name: string;
  title: string;
  email?: string;
  linkedin_url?: string;
  role_archetype: 'economic_buyer' | 'champion' | 'technical_evaluator' | 'end_user';
  status: 'uncontacted' | 'engaged' | 'replied' | 'meeting_booked';
}

interface CopyMatrixItem {
  archetype: string;
  sample_title: string;
  sample_name: string;
  copy: {
    role_archetype: string;
    angle: string;
    hook: string;
    subject: string;
    body: string;
    character_count: number;
    cross_thread_aware: boolean;
  };
}

export function AbmMultithreadStudioModal({ onClose, campaignId }: AbmMultithreadStudioProps) {
  const { openPaywall } = usePaywall();
  const { data: billingData } = useSWR<{ tier?: string }>('/api/elein/workspaces/billing', fetcher);
  const isPro = billingData?.tier === 'PRO' || billingData?.tier === 'ENTERPRISE';

  const [activeTab, setActiveTab] = useState<'accounts' | 'committee' | 'copy_studio'>('accounts');

  // ── Tab 1: Target Accounts State ──
  const [tierFilter, setTierFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedAccountId, setSelectedAccountId] = useState<string>('acc-stripe');
  const [isExportingAccounts, setIsExportingAccounts] = useState(false);
  const [isExportingCommittee, setIsExportingCommittee] = useState(false);

  // Fallback initial accounts
  const [accounts] = useState<TargetAccount[]>([
    {
      id: "acc-stripe",
      company_name: "Stripe, Inc.",
      domain: "stripe.com",
      tier: "tier_1",
      employee_count: 8000,
      industry: "Financial Infrastructure",
      account_heat_score: 75,
      stage: "consensus_building",
      committee_count: 4,
      engaged_count: 3,
      replied_count: 1,
      meetings_count: 0
    },
    {
      id: "acc-datadog",
      company_name: "Datadog",
      domain: "datadoghq.com",
      tier: "tier_1",
      employee_count: 5200,
      industry: "Cloud Observability & Security",
      account_heat_score: 45,
      stage: "multithreaded",
      committee_count: 2,
      engaged_count: 1,
      replied_count: 0,
      meetings_count: 0
    },
    {
      id: "acc-snowflake",
      company_name: "Snowflake",
      domain: "snowflake.com",
      tier: "tier_2",
      employee_count: 6800,
      industry: "Cloud Data Warehousing",
      account_heat_score: 15,
      stage: "discovery",
      committee_count: 3,
      engaged_count: 0,
      replied_count: 0,
      meetings_count: 0
    }
  ]);

  // SWR for live target accounts
  const { data: serverAccounts, mutate: mutateAccounts } = useSWR<{ success: boolean; accounts: TargetAccount[] }>(
    `/api/elein/abm/accounts${tierFilter !== 'all' ? `?tier=${tierFilter}` : ''}`,
    fetcher,
    { revalidateOnFocus: false }
  );

  const displayAccounts = serverAccounts?.accounts || accounts;

  // ── Tab 2: Committee Members State ──
  const [committeeMembers, setCommitteeMembers] = useState<CommitteeMember[]>([
    {
      id: "mem-1",
      account_id: "acc-stripe",
      prospect_name: "Marcus Vance",
      title: "Chief Financial Officer",
      email: "marcus.v@stripe.com",
      linkedin_url: "https://linkedin.com/in/marcus-vance-cfo",
      role_archetype: "economic_buyer",
      status: "engaged"
    },
    {
      id: "mem-2",
      account_id: "acc-stripe",
      prospect_name: "Elena Rostova",
      title: "VP of Revenue Operations & Sales",
      email: "elena.r@stripe.com",
      linkedin_url: "https://linkedin.com/in/elena-rostova-revops",
      role_archetype: "champion",
      status: "replied"
    },
    {
      id: "mem-3",
      account_id: "acc-stripe",
      prospect_name: "Devon Miller",
      title: "Head of Enterprise IT & Security",
      email: "devon.m@stripe.com",
      linkedin_url: "https://linkedin.com/in/devon-miller-security",
      role_archetype: "technical_evaluator",
      status: "engaged"
    },
    {
      id: "mem-4",
      account_id: "acc-stripe",
      prospect_name: "Jordan Lee",
      title: "Senior Strategic Account Executive",
      email: "jordan.l@stripe.com",
      linkedin_url: "https://linkedin.com/in/jordan-lee-ae",
      role_archetype: "end_user",
      status: "uncontacted"
    }
  ]);

  const { data: serverCommittee, mutate: mutateCommittee } = useSWR<{ success: boolean; members: CommitteeMember[] }>(
    selectedAccountId ? `/api/elein/abm/accounts/${selectedAccountId}/committee` : null,
    fetcher
  );

  const activeMembers = serverCommittee?.members || committeeMembers.filter(m => m.account_id === selectedAccountId);

  // ── Tab 3: Copy Matrix State ──
  const [copyCompany, setCopyCompany] = useState("Stripe");
  const [selectedRoleTab, setSelectedRoleTab] = useState<'economic_buyer' | 'champion' | 'technical_evaluator' | 'end_user'>('champion');
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const { data: matrixData } = useSWR<{ success: boolean; matrix: CopyMatrixItem[] }>(
    `/api/elein/abm/copy-matrix?company_name=${encodeURIComponent(copyCompany)}`,
    fetcher
  );

  // ── Modal Launch Staggered Sequence State ──
  const [launchModalOpen, setLaunchModalOpen] = useState(false);
  const [targetLaunchAccount, setTargetLaunchAccount] = useState<TargetAccount | null>(null);
  const [staggerInterval, setStaggerInterval] = useState<number>(4);
  const [isLaunching, setIsLaunching] = useState(false);

  // ── Modal Quick Add Account State ──
  const [addAccountOpen, setAddAccountOpen] = useState(false);
  const [newCompanyName, setNewCompanyName] = useState('');
  const [newDomain, setNewDomain] = useState('');
  const [newTier, setNewTier] = useState<'tier_1' | 'tier_2' | 'tier_3'>('tier_1');
  const [newEmployees, setNewEmployees] = useState(500);
  const [newIndustry, setNewIndustry] = useState('Enterprise Software');
  const [isSubmittingAccount, setIsSubmittingAccount] = useState(false);

  // ── Modal Add Stakeholder State ──
  const [addMemberOpen, setAddMemberOpen] = useState(false);
  const [newMemberName, setNewMemberName] = useState('');
  const [newMemberTitle, setNewMemberTitle] = useState('');
  const [newMemberEmail, setNewMemberEmail] = useState('');
  const [newMemberLinkedin, setNewMemberLinkedin] = useState('');
  const [newMemberRole, setNewMemberRole] = useState<string>('auto');
  const [isSubmittingMember, setIsSubmittingMember] = useState(false);
  const [updatingMemberId, setUpdatingMemberId] = useState<string | null>(null);

  const handleExportAccountsCsv = async () => {
    if (isExportingAccounts) return;
    setIsExportingAccounts(true);
    try {
      const res = await fetchWithAuth(
        `/api/elein/abm/accounts/export-csv${tierFilter !== 'all' ? `?tier=${encodeURIComponent(tierFilter)}` : ''}`
      );
      if (res.status === 402) {
        openPaywall('ABM Multithreading Orchestrator');
        return;
      }
      if (!res.ok) throw new Error('Failed to export target accounts CSV');
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `abm_target_accounts_${Date.now()}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      toast.success('Target accounts CSV exported!');
    } catch (e: any) {
      toast.error(e.message || 'Failed to export target accounts CSV');
    } finally {
      setIsExportingAccounts(false);
    }
  };

  const handleExportCommitteeCsv = async () => {
    if (!selectedAccountId || isExportingCommittee) return;
    setIsExportingCommittee(true);
    try {
      const res = await fetchWithAuth(`/api/elein/abm/accounts/${encodeURIComponent(selectedAccountId)}/committee/export-csv`);
      if (res.status === 402) {
        openPaywall('ABM Multithreading Orchestrator');
        return;
      }
      if (!res.ok) throw new Error('Failed to export buying committee CSV');
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `abm_committee_${selectedAccountId}_${Date.now()}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      toast.success('Buying committee CSV exported!');
    } catch (e: any) {
      toast.error(e.message || 'Failed to export buying committee CSV');
    } finally {
      setIsExportingCommittee(false);
    }
  };

  const handleAddMember = async () => {
    if (!newMemberName.trim() || !newMemberTitle.trim()) {
      toast.error('Please enter both stakeholder name and job title.');
      return;
    }
    setIsSubmittingMember(true);
    try {
      const res = await fetchWithAuth(`/api/elein/abm/accounts/${encodeURIComponent(selectedAccountId)}/committee/add`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prospect_name: newMemberName.trim(),
          title: newMemberTitle.trim(),
          email: newMemberEmail.trim() || undefined,
          linkedin_url: newMemberLinkedin.trim() || undefined,
          role_archetype: newMemberRole !== 'auto' ? newMemberRole : undefined
        })
      });
      if (res.status === 402) {
        openPaywall('ABM Multithreading Orchestrator');
        return;
      }
      const data = await res.json();
      if (res.ok && data.success) {
        toast.success(
          data.data?.deduplicated
            ? 'Stakeholder already in committee (deduplicated).'
            : `Added ${data.data?.member?.prospect_name} as ${data.data?.member?.role_archetype?.replace('_', ' ')}!`
        );
        setAddMemberOpen(false);
        setNewMemberName('');
        setNewMemberTitle('');
        setNewMemberEmail('');
        setNewMemberLinkedin('');
        setNewMemberRole('auto');
        mutateCommittee();
        mutateAccounts();
      } else {
        toast.error(data.detail || 'Failed to add buying committee stakeholder.');
      }
    } catch (e: any) {
      toast.error('Error adding stakeholder: ' + (e.message || 'Network error'));
    } finally {
      setIsSubmittingMember(false);
    }
  };

  const handleUpdateMemberStatus = async (memberId: string, newStatus: CommitteeMember['status']) => {
    if (updatingMemberId === memberId) return;
    setUpdatingMemberId(memberId);
    try {
      const res = await fetchWithAuth(`/api/elein/abm/committee/${encodeURIComponent(memberId)}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus })
      });
      if (res.status === 402) {
        openPaywall('ABM Multithreading Orchestrator');
        return;
      }
      const data = await res.json();
      if (res.ok && data.success) {
        const heat = data.data?.heat_summary?.heat_score;
        toast.success(`Status updated to ${newStatus.replace('_', ' ')}! Account Heat Score: ${heat ?? '--'}/100`);
        setCommitteeMembers(prev => prev.map(m => (m.id === memberId ? { ...m, status: newStatus } : m)));
        mutateCommittee();
        mutateAccounts();
      } else {
        toast.error(data.detail || 'Failed to update member status.');
      }
    } catch (e: any) {
      toast.error('Error updating status: ' + (e.message || 'Network error'));
    } finally {
      setUpdatingMemberId(null);
    }
  };

  const handleLaunchMultithread = async () => {
    if (!targetLaunchAccount || isLaunching) return;
    setIsLaunching(true);
    try {
      const res = await fetchWithAuth('/api/elein/abm/launch-multithread', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          account_id: targetLaunchAccount.id,
          campaign_id: campaignId || null,
          staggered_interval_hours: staggerInterval
        })
      });
      if (res.status === 402) {
        openPaywall('ABM Multithreading Orchestrator');
        return;
      }
      const data = await res.json();
      if (res.ok && data.success) {
        toast.success(`Multithreading cascade launched for ${targetLaunchAccount.company_name}! Staggered every ${staggerInterval}h.`);
        setLaunchModalOpen(false);
        mutateAccounts();
        mutateCommittee();
      } else {
        toast.error(data.detail || 'Failed to launch multithreaded cascade.');
      }
    } catch (e: any) {
      toast.error('Error launching sequence: ' + e.message);
    } finally {
      setIsLaunching(false);
    }
  };

  const handleCreateAccount = async () => {
    if (!newCompanyName.trim()) {
      toast.error('Please specify a company name.');
      return;
    }
    if (isSubmittingAccount) return;
    setIsSubmittingAccount(true);
    try {
      const res = await fetchWithAuth('/api/elein/abm/accounts/create-or-map', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          company_name: newCompanyName.trim(),
          domain: newDomain.trim() || undefined,
          tier: newTier,
          employee_count: newEmployees,
          industry: newIndustry
        })
      });
      if (res.status === 402) {
        openPaywall('ABM Multithreading Orchestrator');
        return;
      }
      const data = await res.json();
      if (res.ok && data.success) {
        toast.success(`Account mapped! Auto-generated 3-person Buying Committee.`);
        setAddAccountOpen(false);
        setNewCompanyName('');
        setNewDomain('');
        mutateAccounts();
      } else {
        toast.error(data.detail || 'Failed to map account.');
      }
    } catch (e: any) {
      toast.error('Error creating account: ' + e.message);
    } finally {
      setIsSubmittingAccount(false);
    }
  };

  const copyToClipboard = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    toast.success('Copied to clipboard!');
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const getHeatColor = (score: number) => {
    if (score >= 75) return 'bg-foreground';
    if (score >= 50) return 'bg-foreground/80';
    if (score >= 25) return 'bg-foreground/60';
    return 'bg-muted-foreground/50';
  };

  const getStageBadge = (stage: string) => {
    switch (stage) {
      case 'opportunity':
        return <span className="px-2 py-0.5 rounded-md text-[11px] font-medium bg-muted text-foreground border border-border">Opportunity Ready</span>;
      case 'consensus_building':
        return <span className="px-2 py-0.5 rounded-md text-[11px] font-medium bg-muted/60 text-foreground border border-border">Consensus Building</span>;
      case 'multithreaded':
        return <span className="px-2 py-0.5 rounded-md text-[11px] font-medium bg-muted/40 text-muted-foreground border border-border">Multithreaded</span>;
      default:
        return <span className="px-2 py-0.5 rounded-md text-[11px] font-medium bg-muted/40 text-muted-foreground border border-border">Discovery</span>;
    }
  };

  const getRoleBadge = (role: string) => {
    switch (role) {
      case 'economic_buyer':
        return <span className="px-2 py-0.5 rounded-md text-[11px] font-medium bg-muted/40 text-foreground border border-border">Economic Buyer (Budget)</span>;
      case 'champion':
        return <span className="px-2 py-0.5 rounded-md text-[11px] font-medium bg-muted/40 text-foreground border border-border">Champion (Pain Owner)</span>;
      case 'technical_evaluator':
        return <span className="px-2 py-0.5 rounded-md text-[11px] font-medium bg-muted/40 text-foreground border border-border">Technical Evaluator (Infra)</span>;
      default:
        return <span className="px-2 py-0.5 rounded-md text-[11px] font-medium bg-muted/40 text-foreground border border-border">End User (Operator)</span>;
    }
  };

  const filteredAccounts = displayAccounts.filter(acc => {
    const matchesSearch = acc.company_name.toLowerCase().includes(searchQuery.toLowerCase()) || 
                          acc.domain.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesTier = tierFilter === 'all' || acc.tier === tierFilter;
    return matchesSearch && matchesTier;
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-6xl h-[90vh] bg-card border border-border rounded-xl shadow-2xl flex flex-col overflow-hidden text-card-foreground">
        
        {/* Top Header */}
        <div className="px-6 py-4 border-b border-border bg-background flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-foreground">ABM Buying Committee & Multithreading Orchestrator</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Synchronize role-differentiated touches across economic buyers, champions, and technical evaluators.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                mutateAccounts();
                mutateCommittee();
                toast.success('Telemetry refreshed!');
              }}
              className="p-2 rounded-lg bg-muted/40 hover:bg-muted text-muted-foreground hover:text-foreground border border-border transition-colors"
              title="Refresh Account Data"
              aria-label="Refresh Account Data"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
            {onClose && (
              <button
                type="button"
                onClick={onClose}
                className="p-2 rounded-lg bg-muted/40 hover:bg-muted text-muted-foreground hover:text-foreground border border-border transition-colors"
                aria-label="Close dialog"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>

        {/* Key Performance Metric Ribbon */}
        <div className="grid grid-cols-4 gap-4 px-6 py-3 border-b border-border bg-muted/40">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-background border border-border text-muted-foreground">
              <Building2 className="w-4 h-4" />
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Active Accounts</div>
              <div className="text-sm font-semibold text-foreground">{displayAccounts.length} Enterprise Targets</div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-background border border-border text-muted-foreground">
              <Users className="w-4 h-4" />
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Committee Mapped</div>
              <div className="text-sm font-semibold text-foreground">
                {displayAccounts.reduce((acc, a) => acc + (a.committee_count || 3), 0)} Decision Makers
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-background border border-border text-muted-foreground">
              <Target className="w-4 h-4" />
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Average Heat Score</div>
              <div className="text-sm font-semibold text-foreground">
                {Math.round(displayAccounts.reduce((acc, a) => acc + a.account_heat_score, 0) / (displayAccounts.length || 1))}/100 Penetration
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-background border border-border text-muted-foreground">
              <TrendingUp className="w-4 h-4" />
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Consensus Velocity</div>
              <div className="text-sm font-semibold text-foreground">3.4x Pipeline Conversion</div>
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="flex border-b border-border bg-background px-6">
          <button
            onClick={() => setActiveTab('accounts')}
            className={`py-3 px-4 text-xs font-medium flex items-center gap-2 border-b-2 transition-all ${
              activeTab === 'accounts'
                ? 'border-foreground text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Building2 className="w-4 h-4" />
            Target Accounts & Heatmap
          </button>

          <button
            onClick={() => setActiveTab('committee')}
            className={`py-3 px-4 text-xs font-medium flex items-center gap-2 border-b-2 transition-all ${
              activeTab === 'committee'
                ? 'border-foreground text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Users className="w-4 h-4" />
            Buying Committee Matrix
          </button>

          <button
            onClick={() => setActiveTab('copy_studio')}
            className={`py-3 px-4 text-xs font-medium flex items-center gap-2 border-b-2 transition-all ${
              activeTab === 'copy_studio'
                ? 'border-foreground text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <MessageSquare className="w-4 h-4" />
            Role-Differentiated Copy Studio
          </button>
        </div>

        {/* Main Tab Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          
          {/* TAB 1: TARGET ACCOUNTS & PENETRATION HEATMAP */}
          {activeTab === 'accounts' && (
            <div className="space-y-4">
              <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
                <div className="flex items-center gap-3 w-full sm:w-auto">
                  <div className="relative flex-1 sm:w-64">
                    <input
                      type="text"
                      placeholder="Filter accounts by name or domain..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="w-full bg-background border border-border rounded-lg px-3 py-1.5 text-xs text-foreground placeholder-muted-foreground focus:outline-none focus:border-foreground"
                    />
                  </div>

                  <Select
                    value={tierFilter}
                    onValueChange={(val) => setTierFilter(val)}
                  >
                    <SelectTrigger size="sm" className="w-[140px] bg-background border-border text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Tiers</SelectItem>
                      <SelectItem value="tier_1">Tier 1 Strategic</SelectItem>
                      <SelectItem value="tier_2">Tier 2 Mid-Market</SelectItem>
                      <SelectItem value="tier_3">Tier 3 Growth</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="flex items-center gap-2 w-full sm:w-auto">
                  <button
                    onClick={handleExportAccountsCsv}
                    disabled={isExportingAccounts}
                    className="px-3 py-1.5 rounded-lg bg-muted/40 hover:bg-muted border border-border text-foreground font-medium text-xs flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50"
                  >
                    <Download className="w-3.5 h-3.5" />
                    {isExportingAccounts ? 'Exporting...' : 'Export Accounts CSV'}
                  </button>
                  <button
                    onClick={() => setAddAccountOpen(true)}
                    className="px-3.5 py-1.5 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground font-medium text-xs flex items-center justify-center gap-2 transition-colors"
                  >
                    <Plus className="w-4 h-4" />
                    Add Enterprise Account
                  </button>
                </div>
              </div>

              {/* Accounts Table */}
              <div className="border border-border rounded-lg overflow-hidden bg-card">
                <table className="w-full text-left text-xs">
                  <thead className="bg-muted/40 border-b border-border text-muted-foreground font-medium">
                    <tr>
                      <th className="py-3 px-4">Company & Domain</th>
                      <th className="py-3 px-3">Tier</th>
                      <th className="py-3 px-3">Headcount</th>
                      <th className="py-3 px-4">Account Heat Score</th>
                      <th className="py-3 px-3">Stage</th>
                      <th className="py-3 px-3">Committee</th>
                      <th className="py-3 px-4 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {filteredAccounts.map((acc) => (
                      <tr key={acc.id} className="hover:bg-muted/40 transition-colors">
                        <td className="py-3 px-4">
                          <div className="font-semibold text-foreground">{acc.company_name}</div>
                          <a
                            href={`https://${acc.domain}`}
                            target="_blank"
                            rel="noreferrer"
                            className="text-[11px] text-muted-foreground hover:text-foreground flex items-center gap-1 mt-0.5"
                          >
                            {acc.domain} <ExternalLink className="w-2.5 h-2.5" />
                          </a>
                        </td>

                        <td className="py-3 px-3">
                          <span className="px-2 py-0.5 rounded text-[10px] font-medium uppercase tracking-wider bg-muted/40 text-foreground border border-border">
                            {acc.tier.replace('_', ' ')}
                          </span>
                        </td>

                        <td className="py-3 px-3 text-muted-foreground">
                          {acc.employee_count.toLocaleString()} reps
                        </td>

                        <td className="py-3 px-4">
                          <div className="w-48 space-y-1">
                            <div className="flex justify-between items-center text-[10px]">
                              <span className="font-semibold text-foreground">{acc.account_heat_score}/100</span>
                              <span className="text-muted-foreground">
                                {acc.account_heat_score >= 75 ? 'High Heat' : acc.account_heat_score >= 40 ? 'Warming' : 'Cold'}
                              </span>
                            </div>
                            <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
                              <div
                                className={`h-full rounded-full ${getHeatColor(acc.account_heat_score)}`}
                                style={{ width: `${acc.account_heat_score}%` }}
                              />
                            </div>
                          </div>
                        </td>

                        <td className="py-3 px-3">
                          {getStageBadge(acc.stage)}
                        </td>

                        <td className="py-3 px-3">
                          <div className="text-foreground font-medium">{acc.committee_count || 3} members</div>
                          <div className="text-[10px] text-muted-foreground">
                            {acc.engaged_count || 0} engaged - {acc.replied_count || 0} replied
                          </div>
                        </td>

                        <td className="py-3 px-4 text-right">
                          <div className="flex items-center justify-end gap-2">
                            <button
                              onClick={() => {
                                setSelectedAccountId(acc.id);
                                setCopyCompany(acc.company_name);
                                setActiveTab('committee');
                              }}
                              className="px-2.5 py-1 rounded-lg bg-muted/40 hover:bg-muted border border-border text-foreground text-[11px] font-medium transition-colors"
                            >
                              Committee
                            </button>

                            <button
                              onClick={() => {
                                setTargetLaunchAccount(acc);
                                setLaunchModalOpen(true);
                              }}
                              className="px-2.5 py-1 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-[11px] font-medium flex items-center gap-1 transition-colors"
                            >
                              <Rocket className="w-3 h-3" />
                              Launch ABM
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* TAB 2: BUYING COMMITTEE MATRIX */}
          {activeTab === 'committee' && (
            <div className="space-y-6">
              <div className="flex flex-wrap items-center justify-between gap-3 bg-muted/40 p-4 border border-border rounded-lg">
                <div className="flex items-center gap-3">
                  <span className="text-xs text-muted-foreground">Viewing Account:</span>
                  <Select
                    value={selectedAccountId}
                    onValueChange={(val) => {
                      setSelectedAccountId(val);
                      const acc = displayAccounts.find(a => a.id === val);
                      if (acc) setCopyCompany(acc.company_name);
                    }}
                  >
                    <SelectTrigger size="sm" className="w-[240px] bg-background border-border text-xs font-medium">
                      <SelectValue placeholder="Select account..." />
                    </SelectTrigger>
                    <SelectContent>
                      {displayAccounts.map(a => (
                        <SelectItem key={a.id} value={a.id}>{a.company_name} ({a.domain})</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={handleExportCommitteeCsv}
                    disabled={isExportingCommittee}
                    className="px-3 py-1.5 rounded-lg bg-background hover:bg-muted border border-border text-foreground font-medium text-xs flex items-center gap-1.5 transition-colors disabled:opacity-50"
                  >
                    <Download className="w-3.5 h-3.5" />
                    {isExportingCommittee ? 'Exporting...' : 'Export Committee CSV'}
                  </button>

                  <button
                    onClick={() => setAddMemberOpen(true)}
                    className="px-3 py-1.5 rounded-lg bg-background hover:bg-muted border border-border text-foreground font-medium text-xs flex items-center gap-1.5 transition-colors"
                  >
                    <UserPlus className="w-3.5 h-3.5 text-muted-foreground" />
                    Add Stakeholder
                  </button>

                  <button
                    onClick={() => {
                      const acc = displayAccounts.find(a => a.id === selectedAccountId);
                      if (acc) {
                        setTargetLaunchAccount(acc);
                        setLaunchModalOpen(true);
                      }
                    }}
                    className="px-3.5 py-1.5 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground font-medium text-xs flex items-center gap-1.5 transition-colors"
                  >
                    <Rocket className="w-3.5 h-3.5" />
                    Launch Staggered Cascade
                  </button>
                </div>
              </div>

              {/* Committee Role Archetypes Guide */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs">
                <div className="p-3 bg-muted/40 border border-border rounded-lg space-y-1">
                  <div className="font-semibold text-foreground">
                    Economic Buyer
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    CFO / CRO / CEO. Owns budget & approvals. Driven by CAC payback, revenue predictability, and quantifiable ROI.
                  </p>
                </div>

                <div className="p-3 bg-muted/40 border border-border rounded-lg space-y-1">
                  <div className="font-semibold text-foreground">
                    Champion
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    VP Sales / Growth Director. Owns quota & SDR burnout. Driven by pipeline velocity and team ramp efficiency.
                  </p>
                </div>

                <div className="p-3 bg-muted/40 border border-border rounded-lg space-y-1">
                  <div className="font-semibold text-foreground">
                    Technical Evaluator
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    CTO / CISO / Head of IT. Owns security & infra. Driven by SOC2 compliance, proxy IP isolation, and data privacy.
                  </p>
                </div>

                <div className="p-3 bg-muted/40 border border-border rounded-lg space-y-1">
                  <div className="font-semibold text-foreground">
                    End User Operator
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    Senior AE / SDR / Rep. Daily tool operator. Driven by eliminating repetitive LinkedIn research & intuitive UX.
                  </p>
                </div>
              </div>

              {/* Committee Members Table */}
              <div className="border border-border rounded-lg overflow-hidden bg-card">
                <table className="w-full text-left text-xs">
                  <thead className="bg-muted/40 border-b border-border text-muted-foreground font-medium">
                    <tr>
                      <th className="py-3 px-4">Executive Name & Title</th>
                      <th className="py-3 px-3">Role Archetype</th>
                      <th className="py-3 px-3">Contact Channels</th>
                      <th className="py-3 px-3">Engagement Status (Live Heat Sync)</th>
                      <th className="py-3 px-4 text-right">Role Copy Angle</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {activeMembers.map((m) => (
                      <tr key={m.id} className="hover:bg-muted/40 transition-colors">
                        <td className="py-3.5 px-4">
                          <div className="font-semibold text-foreground text-sm">{m.prospect_name}</div>
                          <div className="text-muted-foreground text-xs mt-0.5">{m.title}</div>
                        </td>

                        <td className="py-3.5 px-3">
                          {getRoleBadge(m.role_archetype)}
                        </td>

                        <td className="py-3.5 px-3 space-y-1">
                          {m.email && <div className="text-[11px] text-foreground/80 font-mono">{m.email}</div>}
                          {m.linkedin_url && (
                            <a
                              href={m.linkedin_url}
                              target="_blank"
                              rel="noreferrer"
                              className="text-[10px] text-muted-foreground hover:text-foreground hover:underline flex items-center gap-1"
                            >
                              LinkedIn Profile <ExternalLink className="w-2.5 h-2.5" />
                            </a>
                          )}
                        </td>

                        <td className="py-3.5 px-3">
                          <Select
                            value={m.status}
                            disabled={updatingMemberId === m.id}
                            onValueChange={(val) => handleUpdateMemberStatus(m.id, val as CommitteeMember['status'])}
                          >
                            <SelectTrigger size="sm" className="w-[170px] bg-background border-border text-[11px] font-medium h-7">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="uncontacted">Uncontacted (+0 pts)</SelectItem>
                              <SelectItem value="engaged">Engaged (+10 pts)</SelectItem>
                              <SelectItem value="replied">Replied (+25 pts)</SelectItem>
                              <SelectItem value="meeting_booked">Meeting Booked (+40 pts)</SelectItem>
                            </SelectContent>
                          </Select>
                        </td>

                        <td className="py-3.5 px-4 text-right">
                          <button
                            onClick={() => {
                              setSelectedRoleTab(m.role_archetype);
                              setActiveTab('copy_studio');
                            }}
                            className="px-3 py-1 rounded-lg bg-muted/40 hover:bg-muted text-foreground border border-border text-xs font-medium transition-colors"
                          >
                            Preview Angle
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* TAB 3: ROLE-DIFFERENTIATED COPY STUDIO */}
          {activeTab === 'copy_studio' && (
            <div className="space-y-6">
              <div className="flex flex-col sm:flex-row items-center justify-between gap-4 bg-muted/40 p-4 border border-border rounded-lg">
                <div className="flex items-center gap-3">
                  <span className="text-xs text-muted-foreground">Target Company:</span>
                  <input
                    type="text"
                    value={copyCompany}
                    onChange={(e) => setCopyCompany(e.target.value)}
                    className="bg-background border border-border rounded-lg px-3 py-1.5 text-xs text-foreground font-medium focus:outline-none focus:border-foreground w-44"
                  />
                </div>

                {/* Archetype Selector Tabs */}
                <div className="flex bg-background p-1 rounded-lg border border-border">
                  <button
                    onClick={() => setSelectedRoleTab('economic_buyer')}
                    className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                      selectedRoleTab === 'economic_buyer'
                        ? 'bg-muted text-foreground'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    Economic Buyer
                  </button>

                  <button
                    onClick={() => setSelectedRoleTab('champion')}
                    className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                      selectedRoleTab === 'champion'
                        ? 'bg-muted text-foreground'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    Champion
                  </button>

                  <button
                    onClick={() => setSelectedRoleTab('technical_evaluator')}
                    className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                      selectedRoleTab === 'technical_evaluator'
                        ? 'bg-muted text-foreground'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    Technical Evaluator
                  </button>

                  <button
                    onClick={() => setSelectedRoleTab('end_user')}
                    className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                      selectedRoleTab === 'end_user'
                        ? 'bg-muted text-foreground'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    End User
                  </button>
                </div>
              </div>

              {/* Active Copy Card */}
              {(() => {
                const matrixItem = matrixData?.matrix?.find(m => m.archetype === selectedRoleTab) || {
                  archetype: selectedRoleTab,
                  sample_title: selectedRoleTab === 'economic_buyer' ? 'CFO' : selectedRoleTab === 'champion' ? 'VP Sales' : selectedRoleTab === 'technical_evaluator' ? 'CISO' : 'Account Executive',
                  sample_name: selectedRoleTab === 'economic_buyer' ? 'Marcus Vance' : selectedRoleTab === 'champion' ? 'Elena Rostova' : selectedRoleTab === 'technical_evaluator' ? 'Devon Miller' : 'Jordan Lee',
                  copy: {
                    role_archetype: selectedRoleTab,
                    angle: selectedRoleTab === 'economic_buyer' ? 'Financial ROI & CAC Efficiency' : selectedRoleTab === 'champion' ? 'Pipeline Velocity & Multithreaded Consensus' : selectedRoleTab === 'technical_evaluator' ? 'Enterprise Security & Infrastructure Isolation' : 'Daily Workflow Automation & Rep Bandwidth',
                    hook: selectedRoleTab === 'economic_buyer' ? '42% reduction in Cost-Per-Opportunity with verifiable pipeline attribution.' : 'Eliminates single-threaded deal stalls by orchestrating synchronized committee touchpoints.',
                    subject: `ROI & Outbound CAC Efficiency at ${copyCompany}`,
                    body: `Hi Marcus,\n\nWhen evaluating enterprise GTM efficiency at ${copyCompany}, pipeline acquisition cost and ramp predictability are paramount.\n\nEle-in replaces fragmented SDR tooling with an autonomous multithreading outreach engine - delivering 3.4x higher meeting conversion rates while reducing overall cost-per-qualified-opportunity by 42%.\n\nWould you be open to a 10-minute briefing on the financial modeling and payback framework we see across Tier-1 teams?`,
                    character_count: 420,
                    cross_thread_aware: true
                  }
                };

                const copy = matrixItem.copy;

                return (
                  <div className="bg-card border border-border rounded-lg p-6 space-y-6">
                    <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border pb-4">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-muted-foreground">Strategic Angle:</span>
                          <span className="font-semibold text-foreground text-sm">{copy.angle}</span>
                        </div>
                        <div className="text-xs text-muted-foreground">
                          Hook: {copy.hook}
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <span className="px-2.5 py-1 rounded-md text-[11px] font-medium bg-muted/40 text-muted-foreground border border-border">
                          {copy.character_count} characters (~45s read)
                        </span>
                        <span className="px-2.5 py-1 rounded-md text-[11px] font-medium bg-muted/40 text-foreground border border-border">
                          Cross-Thread Aware
                        </span>
                      </div>
                    </div>

                    {/* Subject Line */}
                    <div className="space-y-1.5">
                      <label className="text-xs font-medium text-muted-foreground">Subject Line</label>
                      <div className="flex items-center gap-2">
                        <input
                          type="text"
                          readOnly
                          value={copy.subject}
                          className="flex-1 bg-background border border-border rounded-lg px-3.5 py-2 text-xs text-foreground font-medium select-all"
                        />
                        <button
                          onClick={() => copyToClipboard(copy.subject, 'subj')}
                          className="px-3 py-2 rounded-lg bg-muted/40 hover:bg-muted border border-border text-foreground text-xs font-medium flex items-center gap-1.5 transition-colors"
                        >
                          {copiedKey === 'subj' ? <Check className="w-3.5 h-3.5 text-foreground" /> : <Copy className="w-3.5 h-3.5" />}
                          Copy
                        </button>
                      </div>
                    </div>

                    {/* Message Body */}
                    <div className="space-y-1.5">
                      <label className="text-xs font-medium text-muted-foreground">Message Body (Personalized & Role-Tailored)</label>
                      <div className="relative">
                        <textarea
                          readOnly
                          rows={8}
                          value={copy.body}
                          className="w-full bg-background border border-border rounded-lg p-4 text-xs text-foreground leading-relaxed font-mono select-all focus:outline-none"
                        />
                        <button
                          onClick={() => copyToClipboard(copy.body, 'body')}
                          className="absolute top-3 right-3 px-3 py-1.5 rounded-lg bg-muted/90 hover:bg-muted text-foreground text-xs font-medium flex items-center gap-1.5 transition-colors border border-border"
                        >
                          {copiedKey === 'body' ? <Check className="w-3.5 h-3.5 text-foreground" /> : <Copy className="w-3.5 h-3.5" />}
                          Copy Message
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })()}
            </div>
          )}
        </div>

        {/* Launch Staggered Sequence Modal */}
        {launchModalOpen && targetLaunchAccount && (
          <div className="fixed inset-0 z-60 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-150">
            <div className="w-full max-w-lg bg-card border border-border rounded-lg p-6 shadow-2xl space-y-5 text-card-foreground">
              <div className="flex items-center justify-between border-b border-border pb-3">
                <div className="flex items-center gap-2">
                  <Rocket className="w-4 h-4 text-muted-foreground" />
                  <h3 className="font-semibold text-foreground text-base">Launch Multithreaded Cascade</h3>
                </div>
                <button type="button" onClick={() => setLaunchModalOpen(false)} aria-label="Close dialog" className="text-muted-foreground hover:text-foreground">
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="space-y-3 text-xs">
                <div>
                  <div className="text-muted-foreground">Target Account:</div>
                  <div className="text-sm font-semibold text-foreground">{targetLaunchAccount.company_name} ({targetLaunchAccount.domain})</div>
                </div>

                <div className="space-y-1.5">
                  <label className="font-medium text-muted-foreground">Staggered Delay Interval (Hours):</label>
                  <Select
                    value={String(staggerInterval)}
                    onValueChange={(val) => setStaggerInterval(parseInt(val, 10))}
                  >
                    <SelectTrigger className="w-full bg-background border-border h-9 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="1">1 Hour (Fast-Paced)</SelectItem>
                      <SelectItem value="2">2 Hours</SelectItem>
                      <SelectItem value="4">4 Hours (Recommended - Optimal Enterprise Spacing)</SelectItem>
                      <SelectItem value="8">8 Hours</SelectItem>
                      <SelectItem value="12">12 Hours</SelectItem>
                      <SelectItem value="24">24 Hours (Conservative 1 touch per day)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="p-3 bg-muted/40 border border-border rounded-lg space-y-1">
                  <div className="font-semibold text-foreground flex items-center gap-1.5">
                    <ShieldCheck className="w-4 h-4 text-muted-foreground" /> Domain Reputation Protection
                  </div>
                  <p className="text-[11px] text-muted-foreground leading-relaxed">
                    Staggering messages by {staggerInterval} hours prevents LinkedIn burst velocity penalties and corporate mail server firewalls from blacklisting your sending pod.
                  </p>
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  onClick={() => setLaunchModalOpen(false)}
                  className="px-4 py-2 rounded-lg bg-muted/40 hover:bg-muted border border-border text-muted-foreground text-xs font-medium"
                >
                  Cancel
                </button>
                <button
                  onClick={handleLaunchMultithread}
                  disabled={isLaunching}
                  className="px-4 py-2 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-medium flex items-center gap-2"
                >
                  {isLaunching ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Rocket className="w-4 h-4" />}
                  Confirm & Launch Cascade
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Add Enterprise Account Modal */}
        {addAccountOpen && (
          <div className="fixed inset-0 z-60 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-150">
            <div className="w-full max-w-lg bg-card border border-border rounded-lg p-6 shadow-2xl space-y-4 text-card-foreground">
              <div className="flex items-center justify-between border-b border-border pb-3">
                <div className="flex items-center gap-2">
                  <Building2 className="w-4 h-4 text-muted-foreground" />
                  <h3 className="font-semibold text-foreground text-base">Add Enterprise Target Account</h3>
                </div>
                <button type="button" onClick={() => setAddAccountOpen(false)} aria-label="Close dialog" className="text-muted-foreground hover:text-foreground">
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="space-y-3 text-xs">
                <div className="space-y-1">
                  <label className="font-medium text-muted-foreground">Company Name *</label>
                  <input
                    type="text"
                    placeholder="e.g. Acme Corporation"
                    value={newCompanyName}
                    onChange={(e) => setNewCompanyName(e.target.value)}
                    className="w-full bg-background border border-border rounded-lg p-2 text-foreground focus:outline-none focus:border-foreground"
                  />
                </div>

                <div className="space-y-1">
                  <label className="font-medium text-muted-foreground">Corporate Domain (Optional)</label>
                  <input
                    type="text"
                    placeholder="e.g. acme.com"
                    value={newDomain}
                    onChange={(e) => setNewDomain(e.target.value)}
                    className="w-full bg-background border border-border rounded-lg p-2 text-foreground focus:outline-none focus:border-foreground"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label className="font-medium text-muted-foreground">Account Tier</label>
                    <Select
                      value={newTier}
                      onValueChange={(val) => setNewTier(val as any)}
                    >
                      <SelectTrigger className="w-full bg-background border-border h-9 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="tier_1">Tier 1 Strategic</SelectItem>
                        <SelectItem value="tier_2">Tier 2 Mid-Market</SelectItem>
                        <SelectItem value="tier_3">Tier 3 Growth</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-1">
                    <label className="font-medium text-muted-foreground">Employee Headcount</label>
                    <input
                      type="number"
                      value={newEmployees}
                      onChange={(e) => setNewEmployees(parseInt(e.target.value, 10) || 100)}
                      className="w-full bg-background border border-border rounded-lg p-2 text-foreground focus:outline-none focus:border-foreground"
                    />
                  </div>
                </div>

                <div className="p-3 bg-muted/40 border border-border rounded-lg text-[11px] text-muted-foreground">
                  Ele-in will automatically synthesize and assign a 3-person Buying Committee (CFO, VP Sales, and IT Security) mapped to this domain.
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setAddAccountOpen(false)}
                  className="px-4 py-2 rounded-lg bg-muted/40 hover:bg-muted border border-border text-muted-foreground text-xs font-medium"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleCreateAccount}
                  disabled={isSubmittingAccount}
                  className="px-4 py-2 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-medium flex items-center gap-2"
                >
                  {isSubmittingAccount ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                  Create & Map Committee
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Add Buying Committee Stakeholder Modal */}
        {addMemberOpen && (
          <div className="fixed inset-0 z-60 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-150">
            <div className="w-full max-w-lg bg-card border border-border rounded-lg p-6 shadow-2xl space-y-4 text-card-foreground">
              <div className="flex items-center justify-between border-b border-border pb-3">
                <div className="flex items-center gap-2">
                  <UserPlus className="w-4 h-4 text-muted-foreground" />
                  <h3 className="font-semibold text-foreground text-base">Add Buying Committee Stakeholder</h3>
                </div>
                <button type="button" onClick={() => setAddMemberOpen(false)} aria-label="Close dialog" className="text-muted-foreground hover:text-foreground">
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="space-y-3 text-xs">
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label className="font-medium text-muted-foreground">Full Name *</label>
                    <input
                      type="text"
                      placeholder="e.g. Claire Sterling"
                      value={newMemberName}
                      onChange={(e) => setNewMemberName(e.target.value)}
                      className="w-full bg-background border border-border rounded-lg p-2 text-foreground focus:outline-none focus:border-foreground"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="font-medium text-muted-foreground">Job Title *</label>
                    <input
                      type="text"
                      placeholder="e.g. Chief Security Officer"
                      value={newMemberTitle}
                      onChange={(e) => setNewMemberTitle(e.target.value)}
                      className="w-full bg-background border border-border rounded-lg p-2 text-foreground focus:outline-none focus:border-foreground"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label className="font-medium text-muted-foreground">Work Email</label>
                    <input
                      type="email"
                      placeholder="e.g. claire@company.com"
                      value={newMemberEmail}
                      onChange={(e) => setNewMemberEmail(e.target.value)}
                      className="w-full bg-background border border-border rounded-lg p-2 text-foreground focus:outline-none focus:border-foreground"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="font-medium text-muted-foreground">Role Archetype</label>
                    <Select
                      value={newMemberRole}
                      onValueChange={(val) => setNewMemberRole(val)}
                    >
                      <SelectTrigger className="w-full bg-background border-border h-9 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="auto">Auto-Detect from Title</SelectItem>
                        <SelectItem value="economic_buyer">Economic Buyer</SelectItem>
                        <SelectItem value="champion">Champion</SelectItem>
                        <SelectItem value="technical_evaluator">Technical Evaluator</SelectItem>
                        <SelectItem value="end_user">End User Operator</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="space-y-1">
                  <label className="font-medium text-muted-foreground">LinkedIn Profile URL (Optional)</label>
                  <input
                    type="url"
                    placeholder="https://linkedin.com/in/..."
                    value={newMemberLinkedin}
                    onChange={(e) => setNewMemberLinkedin(e.target.value)}
                    className="w-full bg-background border border-border rounded-lg p-2 text-foreground focus:outline-none focus:border-foreground"
                  />
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setAddMemberOpen(false)}
                  className="px-4 py-2 rounded-lg bg-muted/40 hover:bg-muted border border-border text-muted-foreground text-xs font-medium"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleAddMember}
                  disabled={isSubmittingMember}
                  className="px-4 py-2 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-medium flex items-center gap-2"
                >
                  {isSubmittingMember ? <RefreshCw className="w-4 h-4 animate-spin" /> : <UserPlus className="w-4 h-4" />}
                  Add to Committee
                </button>
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}

