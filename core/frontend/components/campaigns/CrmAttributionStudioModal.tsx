import React, { useState } from 'react';
import useSWR from 'swr';
import {
  Link2, DollarSign, ShieldCheck, RefreshCw, Layers, Plus,
  CheckCircle2, AlertTriangle, ArrowRight, X, Play, Check,
  Radio, Sparkles, Building2, Workflow, Filter, Clock, Download, Trash2
} from 'lucide-react';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/lib/apiClient';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

const fetcher = (url: string) => fetchWithAuth(url).then(r => r.json());

interface CrmAttributionStudioProps {
  onClose?: () => void;
}

export function CrmAttributionStudioModal({ onClose }: CrmAttributionStudioProps) {
  const [activeTab, setActiveTab] = useState<'accounts' | 'attribution' | 'webhooks'>('accounts');

  // Account mapping form state
  const [showAddAccount, setShowAddAccount] = useState(false);
  const [newDomain, setNewDomain] = useState('');
  const [newCompanyName, setNewCompanyName] = useState('');
  const [newProvider, setNewProvider] = useState('hubspot');
  const [newCrmId, setNewCrmId] = useState('');
  const [newStage, setNewStage] = useState('opportunity');
  const [isSubmittingAccount, setIsSubmittingAccount] = useState(false);
  const [deletingAccountId, setDeletingAccountId] = useState<string | null>(null);

  // Attribution calculator state
  const [dealName, setDealName] = useState('Snowflake Enterprise Tier');
  const [dealAmount, setDealAmount] = useState(120000);
  const [attributionModel, setAttributionModel] = useState<'w_shaped' | 'first_touch' | 'last_touch' | 'linear'>('w_shaped');
  const [isCalculating, setIsCalculating] = useState(false);
  const [isExportingCsv, setIsExportingCsv] = useState(false);

  // Webhook test state
  const [isSimulatingWebhook, setIsSimulatingWebhook] = useState(false);
  const [webhookLogs, setWebhookLogs] = useState<any[]>([]);

  // SWR queries
  const { data: accountsData, mutate: mutateAccounts, isLoading: isAccountsLoading } = useSWR<{
    success: boolean;
    data: any[];
    count: number;
  }>('/api/elein/crm-sync/accounts', fetcher, { revalidateOnFocus: false });

  const { data: attributionsData, mutate: mutateAttributions } = useSWR<{
    success: boolean;
    data: any[];
    count: number;
  }>('/api/elein/crm-sync/attributions', fetcher, { revalidateOnFocus: false });

  const { data: telemetryData, mutate: mutateTelemetry } = useSWR<{
    success: boolean;
    data: any;
  }>('/api/elein/crm-sync/telemetry', fetcher, { revalidateOnFocus: false });

  const accounts = accountsData?.data || [];
  const attributions = attributionsData?.data || [];
  const telemetry = telemetryData?.data || {
    total_synced_accounts: 3,
    total_attributed_deals: 1,
    total_attributed_pipeline_arr: 75000.0,
    echoes_prevented_count: 1,
    sync_health_score: 99.8,
    primary_crm_connected: 'hubspot'
  };

  const handleExportCSV = async () => {
    setIsExportingCsv(true);
    try {
      const res = await fetchWithAuth('/api/elein/crm-sync/attributions/export-csv');
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail?.message || err.detail || 'Failed to export CRM attributions CSV');
      }
      const csvText = await res.text();
      const blob = new Blob([csvText], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `crm_attributions_${new Date().toISOString().slice(0, 10)}.csv`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      toast.success('CRM attribution ledger exported to CSV!');
    } catch (err: any) {
      toast.error(err.message || 'CSV export failed.');
    } finally {
      setIsExportingCsv(false);
    }
  };

  const handleDeleteAccount = async (accountId: string, companyName: string) => {
    setDeletingAccountId(accountId);
    try {
      const res = await fetchWithAuth(`/api/elein/crm-sync/accounts/${encodeURIComponent(accountId)}`, {
        method: 'DELETE'
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail?.message || err.detail || 'Failed to unlink CRM account');
      }
      toast.success(`Unlinked CRM mapping for ${companyName}.`);
      mutateAccounts();
      mutateTelemetry();
    } catch (err: any) {
      toast.error(err.message || 'Error unlinking account.');
    } finally {
      setDeletingAccountId(null);
    }
  };

  const handleCreateAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newDomain.trim() || !newCompanyName.trim()) {
      toast.error('Domain and company name are required.');
      return;
    }
    setIsSubmittingAccount(true);
    try {
      const res = await fetchWithAuth('/api/elein/crm-sync/accounts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          domain: newDomain.trim(),
          company_name: newCompanyName.trim(),
          crm_provider: newProvider,
          crm_company_id: newCrmId.trim() || `crm-${Date.now()}`,
          lifecycle_stage: newStage
        })
      });
      const data = await res.json();
      if (data.success) {
        toast.success(`Account ${data.data.company_name} mapped to ${data.data.crm_provider}!`);
        setShowAddAccount(false);
        setNewDomain('');
        setNewCompanyName('');
        setNewCrmId('');
        mutateAccounts();
        mutateTelemetry();
      } else {
        toast.error(data.detail || 'Failed to map account.');
      }
    } catch (err: any) {
      toast.error('Error mapping account: ' + err.message);
    } finally {
      setIsSubmittingAccount(false);
    }
  };

  const handleCalculateAttribution = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsCalculating(true);
    try {
      const res = await fetchWithAuth('/api/elein/crm-sync/calculate-attribution', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          deal_id: `deal-${Date.now()}`,
          deal_name: dealName.trim(),
          deal_amount: Number(dealAmount),
          model: attributionModel,
          touchpoints: [
            { channel: 'linkedin_inmail', campaign: 'Q4 Enterprise Target', step: 1 },
            { channel: 'personalized_email', campaign: 'Q4 Enterprise Target', step: 2 },
            { channel: 'calendar_concierge', campaign: 'Calendar Closer', step: 3 }
          ]
        })
      });
      const data = await res.json();
      if (data.success) {
        toast.success(`Attributed $${Number(dealAmount).toLocaleString()} using ${attributionModel} model!`);
        mutateAttributions();
        mutateTelemetry();
      } else {
        toast.error('Failed to compute attribution.');
      }
    } catch (err: any) {
      toast.error('Attribution calculation error: ' + err.message);
    } finally {
      setIsCalculating(false);
    }
  };

  const handleSimulateWebhook = async () => {
    setIsSimulatingWebhook(true);
    try {
      const res = await fetchWithAuth('/api/elein/crm-sync/webhook-inbound', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          event_type: 'deal.stage_change',
          payload: {
            deal_id: 'deal-9901',
            company_name: 'Acme Corporation',
            domain: 'acmecorp.com',
            deal_stage: 'closed_won',
            amount: 75000.0,
            timestamp: new Date().toISOString()
          }
        })
      });
      const data = await res.json();
      if (data.success) {
        toast.success(data.data.message || 'CRM webhook processed with echo defense!');
        setWebhookLogs(prev => [
          {
            timestamp: new Date().toLocaleTimeString(),
            status: data.data.status,
            message: data.data.message,
            halted: data.data.campaigns_halted || 0
          },
          ...prev
        ]);
        mutateAccounts();
        mutateTelemetry();
      } else {
        toast.error('Webhook simulation failed.');
      }
    } catch (err: any) {
      toast.error('Webhook test error: ' + err.message);
    } finally {
      setIsSimulatingWebhook(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="bg-card border border-border/80 rounded-xl w-full max-w-5xl shadow-2xl flex flex-col max-h-[90vh] overflow-hidden text-foreground">
        
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-border/60 bg-muted/20">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-cyan-500/10 border border-cyan-500/30 rounded-xl text-cyan-400">
              <Link2 className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-bold text-foreground tracking-tight">CRM Auto-Sync &amp; Deal Attribution</h2>
                <span className="px-2 py-0.5 text-xs font-semibold bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 rounded-full">
                  Phase 20 Bi-Directional
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Account-level entity resolution &bull; Multi-touch revenue attribution &bull; Echo-loop suppression defense
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleExportCSV}
              disabled={isExportingCsv}
              className="px-3 py-1.5 rounded-xl border border-border/80 bg-background hover:bg-muted/60 text-foreground text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer disabled:opacity-50"
            >
              <Download className="w-3.5 h-3.5 text-cyan-400" />
              <span>{isExportingCsv ? 'Exporting...' : 'Export Attribution CSV'}</span>
            </button>
            <button
              onClick={onClose}
              className="p-2 text-muted-foreground hover:text-foreground hover:bg-muted/60 rounded-lg transition-colors cursor-pointer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Telemetry Bar */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 p-4 bg-muted/20 border-b border-border/60">
          <div className="bg-card border border-border/60 rounded-xl p-3">
            <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
              <span>Synced Accounts</span>
              <Building2 className="w-4 h-4 text-cyan-400" />
            </div>
            <div className="text-xl font-bold text-foreground">
              {telemetry.total_synced_accounts} <span className="text-xs font-normal text-muted-foreground">mapped</span>
            </div>
          </div>

          <div className="bg-card border border-border/60 rounded-xl p-3">
            <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
              <span>Attributed ARR</span>
              <DollarSign className="w-4 h-4 text-emerald-400" />
            </div>
            <div className="text-xl font-bold text-emerald-400">
              ${Number(telemetry.total_attributed_pipeline_arr).toLocaleString()}
            </div>
          </div>

          <div className="bg-card border border-border/60 rounded-xl p-3">
            <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
              <span>Attributed Deals</span>
              <Workflow className="w-4 h-4 text-blue-400" />
            </div>
            <div className="text-xl font-bold text-blue-400">
              {telemetry.total_attributed_deals} <span className="text-xs font-normal text-muted-foreground">closed deals</span>
            </div>
          </div>

          <div className="bg-card border border-border/60 rounded-xl p-3">
            <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
              <span>Echo Defense</span>
              <ShieldCheck className="w-4 h-4 text-amber-400" />
            </div>
            <div className="text-xl font-bold text-amber-400">
              {telemetry.echoes_prevented_count} <span className="text-xs font-normal text-muted-foreground">loops blocked</span>
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="flex border-b border-border/60 px-6 bg-muted/10">
          <button
            onClick={() => setActiveTab('accounts')}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-all flex items-center gap-2 ${
              activeTab === 'accounts'
                ? 'border-cyan-500 text-cyan-400'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Building2 className="w-4 h-4" />
            Account Sync &amp; Mapping ({accounts.length})
          </button>
          <button
            onClick={() => setActiveTab('attribution')}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-all flex items-center gap-2 ${
              activeTab === 'attribution'
                ? 'border-emerald-500 text-emerald-400'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <DollarSign className="w-4 h-4" />
            Revenue Attribution ({attributions.length})
          </button>
          <button
            onClick={() => setActiveTab('webhooks')}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-all flex items-center gap-2 ${
              activeTab === 'webhooks'
                ? 'border-blue-500 text-blue-400'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <ShieldCheck className="w-4 h-4" />
            Webhooks &amp; Echo Defense
          </button>
        </div>

        {/* Tab Content */}
        <div className="p-6 overflow-y-auto flex-1 space-y-6">
          
          {/* TAB 1: ACCOUNT SYNC & MAPPING */}
          {activeTab === 'accounts' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-base font-semibold text-foreground">Account Entity Mappings</h3>
                  <p className="text-xs text-muted-foreground">
                    Accounts are synced bi-directionally between Ele-in and your CRM. Outbound sequences automatically halt when an account moves to Closed-Won or Opportunity.
                  </p>
                </div>
                <button
                  onClick={() => setShowAddAccount(!showAddAccount)}
                  className="px-3 py-1.5 bg-cyan-500 hover:bg-cyan-600 text-primary-foreground font-semibold text-xs rounded-lg flex items-center gap-1.5 transition-colors cursor-pointer"
                >
                  <Plus className="w-3.5 h-3.5" />
                  {showAddAccount ? 'Cancel' : 'Map New Account'}
                </button>
              </div>

              {/* Add Account Form */}
              {showAddAccount && (
                <form onSubmit={handleCreateAccount} className="p-4 bg-muted/20 border border-border/70 rounded-xl space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs text-muted-foreground block mb-1">Company Root Domain</label>
                      <input
                        type="text"
                        required
                        value={newDomain}
                        onChange={e => setNewDomain(e.target.value)}
                        placeholder="acmecorp.com"
                        className="w-full bg-background border border-border/80 rounded-lg px-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-cyan-500"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-muted-foreground block mb-1">Company Name</label>
                      <input
                        type="text"
                        required
                        value={newCompanyName}
                        onChange={e => setNewCompanyName(e.target.value)}
                        placeholder="Acme Corporation"
                        className="w-full bg-background border border-border/80 rounded-lg px-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-cyan-500"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <div>
                      <label className="text-xs text-muted-foreground block mb-1">CRM Provider</label>
                      <Select
                        value={newProvider}
                        onValueChange={val => setNewProvider(val)}
                      >
                        <SelectTrigger className="w-full bg-background border-border/80 h-9 text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="hubspot">HubSpot CRM</SelectItem>
                          <SelectItem value="salesforce">Salesforce</SelectItem>
                          <SelectItem value="pipedrive">Pipedrive</SelectItem>
                          <SelectItem value="zoho">Zoho CRM</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <div>
                      <label className="text-xs text-muted-foreground block mb-1">CRM Account/Company ID</label>
                      <input
                        type="text"
                        value={newCrmId}
                        onChange={e => setNewCrmId(e.target.value)}
                        placeholder="hs-comp-10294"
                        className="w-full bg-background border border-border/80 rounded-lg px-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-cyan-500"
                      />
                    </div>

                    <div>
                      <label className="text-xs text-muted-foreground block mb-1">Lifecycle Stage</label>
                      <Select
                        value={newStage}
                        onValueChange={val => setNewStage(val)}
                      >
                        <SelectTrigger className="w-full bg-background border-border/80 h-9 text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="lead">Lead</SelectItem>
                          <SelectItem value="marketingqualifiedlead">MQL</SelectItem>
                          <SelectItem value="salesqualifiedlead">SQL</SelectItem>
                          <SelectItem value="opportunity">Opportunity</SelectItem>
                          <SelectItem value="customer">Customer (Halt Outreach)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div className="flex justify-end gap-2 pt-2 border-t border-border/60">
                    <button
                      type="button"
                      onClick={() => setShowAddAccount(false)}
                      className="px-3 py-1 text-xs text-muted-foreground hover:text-foreground cursor-pointer"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={isSubmittingAccount}
                      className="px-4 py-1.5 bg-cyan-500 hover:bg-cyan-600 text-primary-foreground font-semibold text-xs rounded-lg flex items-center gap-1.5 disabled:opacity-50 cursor-pointer"
                    >
                      {isSubmittingAccount ? 'Mapping...' : 'Confirm Mapping'}
                    </button>
                  </div>
                </form>
              )}

              {/* Accounts List */}
              <div className="border border-border/70 rounded-xl divide-y divide-border/50 overflow-hidden bg-muted/10">
                {accounts.map((acc: any) => (
                  <div key={acc.id} className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-4 hover:bg-muted/30 transition-colors">
                    <div className="flex items-start gap-3">
                      <div className="p-2 bg-muted/50 rounded-lg text-muted-foreground mt-1">
                        <Building2 className="w-4 h-4" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-sm text-foreground">{acc.company_name}</span>
                          <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                            acc.lifecycle_stage === 'customer'
                              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                              : acc.lifecycle_stage === 'opportunity'
                              ? 'bg-blue-500/10 text-blue-400 border border-blue-500/30'
                              : 'bg-muted text-muted-foreground'
                          }`}>
                            {acc.lifecycle_stage.toUpperCase()}
                          </span>
                        </div>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          Domain: <span className="text-foreground font-medium">{acc.domain}</span> &bull; Provider: <span className="text-foreground/80 capitalize">{acc.crm_provider}</span> ({acc.crm_company_id})
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-3">
                      <div className="text-right text-xs">
                        <span className="text-emerald-400 flex items-center gap-1">
                          <CheckCircle2 className="w-3.5 h-3.5" /> Bi-Directional Synced
                        </span>
                        <span className="text-[11px] text-muted-foreground">
                          {new Date(acc.last_synced_at).toLocaleTimeString()}
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleDeleteAccount(acc.id, acc.company_name)}
                        disabled={deletingAccountId === acc.id}
                        className="p-1.5 rounded-lg border border-border/60 hover:bg-rose-500/10 hover:border-rose-500/30 text-muted-foreground hover:text-rose-400 transition-colors cursor-pointer disabled:opacity-50"
                        title="Unlink CRM Account Mapping"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                ))}

                {accounts.length === 0 && !isAccountsLoading && (
                  <div className="p-8 text-center text-xs text-muted-foreground">
                    No CRM accounts mapped yet. Click "Map New Account" to configure your first linkage.
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB 2: DEAL ATTRIBUTION */}
          {activeTab === 'attribution' && (
            <div className="space-y-6">
              {/* Attribution Simulator */}
              <form onSubmit={handleCalculateAttribution} className="p-4 bg-muted/20 border border-border/70 rounded-xl space-y-4">
                <div className="flex items-center justify-between pb-2 border-b border-border/60">
                  <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                    <Sparkles className="w-4 h-4 text-emerald-400" />
                    Deal Revenue Attribution Engine
                  </div>
                  <span className="text-xs text-muted-foreground">Compute multi-touch attribution credit</span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div>
                    <label className="text-xs text-muted-foreground block mb-1">Deal Title</label>
                    <input
                      type="text"
                      required
                      value={dealName}
                      onChange={e => setDealName(e.target.value)}
                      className="w-full bg-background border border-border/80 rounded-lg px-3 py-1.5 text-xs text-foreground focus:outline-none focus:border-emerald-500"
                    />
                  </div>

                  <div>
                    <label className="text-xs text-muted-foreground block mb-1">Deal Value ($ USD)</label>
                    <input
                      type="number"
                      required
                      value={dealAmount}
                      onChange={e => setDealAmount(Number(e.target.value))}
                      className="w-full bg-background border border-border/80 rounded-lg px-3 py-1.5 text-xs text-foreground focus:outline-none focus:border-emerald-500"
                    />
                  </div>

                  <div>
                    <label className="text-xs text-muted-foreground block mb-1">Attribution Model</label>
                    <Select
                      value={attributionModel}
                      onValueChange={val => setAttributionModel(val as any)}
                    >
                      <SelectTrigger className="w-full bg-background border-border/80 h-9 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="w_shaped">W-Shaped (40% First / 40% Meeting / 20% Nurture)</SelectItem>
                        <SelectItem value="first_touch">First-Touch (100% Creation)</SelectItem>
                        <SelectItem value="last_touch">Last-Touch (100% Closer)</SelectItem>
                        <SelectItem value="linear">Linear (Equal Distribution)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="flex justify-end pt-2">
                  <button
                    type="submit"
                    disabled={isCalculating}
                    className="px-4 py-1.5 bg-emerald-500 hover:bg-emerald-600 text-primary-foreground font-semibold text-xs rounded-lg flex items-center gap-1.5 disabled:opacity-50 cursor-pointer"
                  >
                    {isCalculating ? 'Computing...' : 'Calculate & Record Attribution'}
                  </button>
                </div>
              </form>

              {/* Attributed Deals List */}
              <div className="space-y-3">
                <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Attributed Closed Deals</h4>
                <div className="border border-border/70 rounded-xl divide-y divide-border/50 bg-muted/10 overflow-hidden">
                  {attributions.map((d: any) => (
                    <div key={d.id} className="p-4 space-y-3 hover:bg-muted/30 transition-colors">
                      <div className="flex items-center justify-between">
                        <div>
                          <span className="font-semibold text-sm text-foreground">{d.deal_name}</span>
                          <span className="ml-2 text-xs px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 font-medium">
                            ${Number(d.deal_amount).toLocaleString()}
                          </span>
                          <span className="ml-2 text-[10px] px-2 py-0.5 rounded-full bg-muted text-muted-foreground capitalize">
                            Model: {d.attribution_model.replace('_', '-')}
                          </span>
                        </div>
                        <span className="text-xs text-muted-foreground">
                          {new Date(d.created_at).toLocaleDateString()}
                        </span>
                      </div>

                      {/* Touchpoints pills */}
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs">
                        {(d.touchpoints || []).map((tp: any, idx: number) => (
                          <div key={idx} className="p-2.5 bg-card border border-border/60 rounded-lg flex flex-col justify-between">
                            <span className="text-muted-foreground text-[11px] capitalize">
                              {tp.channel?.replace('_', ' ') || `Step ${tp.step}`}
                            </span>
                            <div className="flex items-center justify-between mt-1">
                              <span className="font-semibold text-emerald-400">
                                ${(tp.attributed_amount || 0).toLocaleString()}
                              </span>
                              <span className="text-[10px] text-muted-foreground">
                                {Math.round((tp.weight || 0) * 100)}% credit
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: WEBHOOKS & ECHO DEFENSE */}
          {activeTab === 'webhooks' && (
            <div className="space-y-4">
              <div className="p-4 bg-blue-500/10 border border-blue-500/20 rounded-xl flex items-center justify-between">
                <div>
                  <h4 className="text-sm font-bold text-foreground flex items-center gap-2">
                    <ShieldCheck className="w-4 h-4 text-blue-500" />
                    Bi-Directional Echo Loop Suppression
                  </h4>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Prevents recursive ping-pong webhook loops by computing canonical SHA256 hashes of payloads with a 60-second debounce ledger.
                  </p>
                </div>
                <button
                  onClick={handleSimulateWebhook}
                  disabled={isSimulatingWebhook}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs rounded-xl flex items-center gap-2 transition-colors disabled:opacity-50 cursor-pointer"
                >
                  {isSimulatingWebhook ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                  Simulate Inbound Webhook
                </button>
              </div>

              {/* Webhook Feed */}
              <div className="space-y-2">
                <h5 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Sync Audit Trail</h5>
                <div className="border border-border/70 rounded-xl divide-y divide-border/50 bg-muted/10 max-h-72 overflow-y-auto">
                  {webhookLogs.length > 0 ? (
                    webhookLogs.map((log, idx) => (
                      <div key={idx} className="p-3 text-xs flex items-center justify-between">
                        <div className="flex items-center gap-2.5">
                          <span className={`p-1.5 rounded border ${
                            log.status === 'skipped_echo'
                              ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                              : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                          }`}>
                            <ShieldCheck className="w-3.5 h-3.5" />
                          </span>
                          <div>
                            <span className="font-semibold text-foreground">{log.message}</span>
                            {log.halted > 0 && (
                              <p className="text-[11px] text-emerald-400 mt-0.5">
                                Halted active outbound sequences for {log.halted} account lead(s).
                              </p>
                            )}
                          </div>
                        </div>
                        <span className="text-[11px] text-muted-foreground">{log.timestamp}</span>
                      </div>
                    ))
                  ) : (
                    <div className="p-6 text-center text-xs text-muted-foreground">
                      No recent inbound webhooks tested. Click "Simulate Inbound Webhook" above.
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

        </div>

        {/* Footer */}
        <div className="p-4 border-t border-border/60 bg-muted/20 flex items-center justify-between text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-emerald-500" />
            <span>Bi-Directional Auto-Sync Active &bull; Multi-Touch Revenue Credited</span>
          </div>
          <button
            onClick={onClose}
            className="px-4 py-1.5 bg-muted hover:bg-muted/80 text-foreground rounded-lg transition-colors font-medium cursor-pointer"
          >
            Close Studio
          </button>
        </div>

      </div>
    </div>
  );
}
