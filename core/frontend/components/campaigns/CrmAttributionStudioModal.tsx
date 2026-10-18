import React, { useState, useEffect } from 'react';
import useSWR from 'swr';
import {
  Link2, DollarSign, ShieldCheck, RefreshCw, Layers, Plus,
  CheckCircle2, AlertTriangle, ArrowRight, X, Play, Check,
  Radio, Sparkles, Building2, Workflow, Filter, Clock, Download, Trash2, Lock
} from 'lucide-react';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/lib/apiClient';
import { usePaywall } from '@/contexts/PaywallContext';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

const fetcher = (url: string) => fetchWithAuth(url).then(r => r.json());

interface CrmAttributionStudioProps {
  onClose?: () => void;
  canCrmSync?: boolean;
}

export function CrmAttributionStudioModal({ onClose, canCrmSync = true }: CrmAttributionStudioProps) {
  const { openPaywall } = usePaywall();
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
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  // Attribution calculator state
  const [dealName, setDealName] = useState('Snowflake Enterprise Tier');
  const [dealAmount, setDealAmount] = useState(120000);
  const [dealAmountStr, setDealAmountStr] = useState('120000');
  const [attributionModel, setAttributionModel] = useState<'w_shaped' | 'first_touch' | 'last_touch' | 'linear'>('w_shaped');
  const [isCalculating, setIsCalculating] = useState(false);
  const [isExportingCsv, setIsExportingCsv] = useState(false);

  // Webhook test state
  const [isSimulatingWebhook, setIsSimulatingWebhook] = useState(false);
  const [testEchoMode, setTestEchoMode] = useState(false);
  const [webhookLogs, setWebhookLogs] = useState<any[]>([]);

  // Escape key dismiss
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && onClose) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

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
    total_synced_accounts: 0,
    total_attributed_deals: 0,
    total_attributed_pipeline_arr: 0,
    echoes_prevented_count: 0,
    sync_health_score: 100,
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
      setDeleteConfirmId(null);
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
          domain: newDomain.trim().toLowerCase().replace(/^https?:\/\//, '').replace(/^www\./, '').split('/')[0],
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
    if (!canCrmSync) {
      openPaywall({ featureName: "Multi-Touch CRM Attribution", minTier: "PRO" });
      return;
    }
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
            { channel: 'linkedin_inmail', campaign: 'Enterprise Target', step: 1 },
            { channel: 'personalized_email', campaign: 'Enterprise Target', step: 2 },
            { channel: 'calendar_concierge', campaign: 'Calendar Closer', step: 3 }
          ]
        })
      });
      const data = await res.json();
      if (data.success) {
        toast.success(`Attributed $${Number(dealAmount).toLocaleString()} using ${attributionModel.replace('_', '-')} model!`);
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
      // In echo test mode, use static timestamp to test the 60-second SHA256 debounce ledger
      const payloadTimestamp = testEchoMode ? "2026-10-18T12:00:00.000Z" : new Date().toISOString();
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
            timestamp: payloadTimestamp
          }
        })
      });
      const data = await res.json();
      if (data.success) {
        const isEcho = data.data.status === 'skipped_echo';
        if (isEcho) {
          toast.info(data.data.message || 'Duplicate webhook event suppressed by 60s echo defense.');
        } else {
          toast.success(data.data.message || 'CRM webhook processed with echo defense!');
        }
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

  const getLifecycleStageBadge = (stage: string) => {
    switch (stage.toLowerCase()) {
      case 'customer':
        return (
          <span className="text-[10px] px-2 py-0.5 rounded-full font-bold uppercase bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
            Customer (Halt)
          </span>
        );
      case 'opportunity':
        return (
          <span className="text-[10px] px-2 py-0.5 rounded-full font-bold uppercase bg-primary/10 text-primary border border-primary/20">
            Opportunity
          </span>
        );
      case 'salesqualifiedlead':
        return (
          <span className="text-[10px] px-2 py-0.5 rounded-full font-medium uppercase bg-cyan-500/10 text-cyan-600 dark:text-cyan-400 border border-cyan-500/20">
            SQL
          </span>
        );
      case 'marketingqualifiedlead':
        return (
          <span className="text-[10px] px-2 py-0.5 rounded-full font-medium uppercase bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
            MQL
          </span>
        );
      default:
        return (
          <span className="text-[10px] px-2 py-0.5 rounded-full font-medium uppercase bg-muted text-muted-foreground border border-border">
            {stage}
          </span>
        );
    }
  };

  return (
    <div 
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-background/80 backdrop-blur-sm overflow-hidden animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div 
        role="dialog"
        aria-modal="true"
        aria-labelledby="crm-studio-title"
        onClick={(e) => e.stopPropagation()}
        className="relative w-full max-w-5xl h-[90dvh] max-h-[90dvh] flex flex-col bg-card border border-border rounded-xl shadow-2xl overflow-hidden text-foreground"
      >
        
        {/* Header */}
        <div className="flex items-center justify-between p-5 sm:p-6 border-b border-border bg-card/60 shrink-0">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-primary/10 border border-primary/20 rounded-xl text-primary">
              <Link2 className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 id="crm-studio-title" className="text-lg sm:text-xl font-bold text-foreground tracking-tight">
                  CRM Auto-Sync &amp; Deal Attribution
                </h2>
                <span className="px-2.5 py-0.5 text-xs font-semibold bg-primary/10 border border-primary/20 text-primary rounded-full">
                  CRM Entity Sync
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
              onClick={onClose}
              aria-label="Close studio"
              className="p-2 text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors cursor-pointer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Telemetry Bar */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 p-4 bg-muted/20 border-b border-border shrink-0">
          <div className="bg-card border border-border rounded-xl p-3">
            <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
              <span>Attributed ARR</span>
              <DollarSign className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
            </div>
            <div className="text-xl font-bold text-emerald-600 dark:text-emerald-400">
              ${Number(telemetry.total_attributed_pipeline_arr || 0).toLocaleString()}
            </div>
          </div>

          <div className="bg-card border border-border rounded-xl p-3">
            <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
              <span>Synced Accounts</span>
              <Building2 className="w-4 h-4 text-primary" />
            </div>
            <div className="text-xl font-bold text-foreground">
              {telemetry.total_synced_accounts || accounts.length} <span className="text-xs font-normal text-muted-foreground">mapped</span>
            </div>
          </div>

          <div className="bg-card border border-border rounded-xl p-3">
            <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
              <span>Attributed Deals</span>
              <Workflow className="w-4 h-4 text-primary" />
            </div>
            <div className="text-xl font-bold text-foreground">
              {telemetry.total_attributed_deals || attributions.length} <span className="text-xs font-normal text-muted-foreground">closed deals</span>
            </div>
          </div>

          <div className="bg-card border border-border rounded-xl p-3">
            <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
              <span>Echo Defense</span>
              <ShieldCheck className="w-4 h-4 text-amber-600 dark:text-amber-400" />
            </div>
            <div className="text-xl font-bold text-amber-600 dark:text-amber-400">
              {telemetry.echoes_prevented_count || 0} <span className="text-xs font-normal text-muted-foreground">loops blocked</span>
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div role="tablist" aria-label="Attribution studio tabs" className="flex border-b border-border px-6 bg-card shrink-0 overflow-x-auto scrollbar-none">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'accounts'}
            onClick={() => setActiveTab('accounts')}
            className={`px-4 py-3 text-xs sm:text-sm font-medium border-b-2 transition-all flex items-center gap-2 whitespace-nowrap cursor-pointer ${
              activeTab === 'accounts'
                ? 'border-primary text-primary font-semibold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Building2 className="w-4 h-4" />
            Account Sync &amp; Mapping ({accounts.length})
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'attribution'}
            onClick={() => setActiveTab('attribution')}
            className={`px-4 py-3 text-xs sm:text-sm font-medium border-b-2 transition-all flex items-center gap-2 whitespace-nowrap cursor-pointer ${
              activeTab === 'attribution'
                ? 'border-primary text-primary font-semibold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <DollarSign className="w-4 h-4" />
            Revenue Attribution ({attributions.length})
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'webhooks'}
            onClick={() => setActiveTab('webhooks')}
            className={`px-4 py-3 text-xs sm:text-sm font-medium border-b-2 transition-all flex items-center gap-2 whitespace-nowrap cursor-pointer ${
              activeTab === 'webhooks'
                ? 'border-primary text-primary font-semibold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <ShieldCheck className="w-4 h-4" />
            Webhooks &amp; Echo Defense
          </button>
        </div>

        {/* Tab Content Body */}
        <div className="p-6 overflow-y-auto flex-1 space-y-6">

          {/* Proactive Free Tier Banner */}
          {!canCrmSync && (
            <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-amber-500/20 text-amber-500 flex items-center justify-center shrink-0">
                  <Lock className="w-5 h-5" />
                </div>
                <div>
                  <div className="text-sm font-semibold text-foreground flex items-center gap-2">
                    <span>Pro Growth Feature</span>
                    <span className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-600 dark:text-amber-400">Locked</span>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Multi-touch CRM attribution and bi-directional entity synchronization require a Pro or Enterprise plan. Upgrade to map accounts and attribute deal revenue.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => openPaywall({ featureName: "Multi-Touch CRM Attribution", minTier: "PRO" })}
                className="px-4 py-2 bg-primary text-primary-foreground text-xs font-semibold rounded-lg hover:bg-primary/90 transition-colors whitespace-nowrap"
              >
                Unlock Pro
              </button>
            </div>
          )}
          
          {/* ════════════════ TAB 1: ACCOUNT SYNC & MAPPING ════════════════ */}
          {activeTab === 'accounts' && (
            <div className="space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <h3 className="text-base font-semibold text-foreground">Account Entity Mappings</h3>
                  <p className="text-xs text-muted-foreground">
                    Accounts are synced bi-directionally between Ele-in and your CRM. Outbound sequences automatically halt when an account moves to Closed-Won or Opportunity.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setShowAddAccount(!showAddAccount)}
                  className="px-3.5 py-2 bg-primary hover:bg-primary/90 text-primary-foreground font-semibold text-xs rounded-lg flex items-center gap-1.5 transition-colors cursor-pointer shrink-0 self-start sm:self-auto"
                >
                  <Plus className="w-3.5 h-3.5" />
                  {showAddAccount ? 'Cancel' : 'Map New Account'}
                </button>
              </div>

              {/* Add Account Form */}
              {showAddAccount && (
                <form onSubmit={handleCreateAccount} className="p-4 bg-card border border-border rounded-xl space-y-4 animate-in fade-in duration-150">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div>
                      <label htmlFor="crm-domain" className="text-xs font-medium text-muted-foreground block mb-1">
                        Company Root Domain <span className="text-destructive">*</span>
                      </label>
                      <input
                        id="crm-domain"
                        type="text"
                        required
                        value={newDomain}
                        onChange={e => setNewDomain(e.target.value)}
                        placeholder="acmecorp.com"
                        className="w-full bg-background border border-border rounded-lg px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
                      />
                    </div>
                    <div>
                      <label htmlFor="crm-company-name" className="text-xs font-medium text-muted-foreground block mb-1">
                        Company Name <span className="text-destructive">*</span>
                      </label>
                      <input
                        id="crm-company-name"
                        type="text"
                        required
                        value={newCompanyName}
                        onChange={e => setNewCompanyName(e.target.value)}
                        placeholder="Acme Corporation"
                        className="w-full bg-background border border-border rounded-lg px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <div>
                      <label htmlFor="crm-provider" className="text-xs font-medium text-muted-foreground block mb-1">
                        CRM Provider
                      </label>
                      <Select
                        value={newProvider}
                        onValueChange={val => setNewProvider(val)}
                      >
                        <SelectTrigger id="crm-provider" className="w-full bg-background border-border h-9 text-xs">
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
                      <label htmlFor="crm-company-id" className="text-xs font-medium text-muted-foreground block mb-1">
                        CRM Company ID (Optional)
                      </label>
                      <input
                        id="crm-company-id"
                        type="text"
                        value={newCrmId}
                        onChange={e => setNewCrmId(e.target.value)}
                        placeholder="e.g. hs-comp-10294"
                        className="w-full bg-background border border-border rounded-lg px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
                      />
                    </div>

                    <div>
                      <label htmlFor="crm-stage" className="text-xs font-medium text-muted-foreground block mb-1">
                        Lifecycle Stage
                      </label>
                      <Select
                        value={newStage}
                        onValueChange={val => setNewStage(val)}
                      >
                        <SelectTrigger id="crm-stage" className="w-full bg-background border-border h-9 text-xs">
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

                  <div className="flex justify-end gap-2 pt-2 border-t border-border">
                    <button
                      type="button"
                      onClick={() => setShowAddAccount(false)}
                      className="px-3.5 py-1.5 text-xs text-muted-foreground hover:text-foreground cursor-pointer rounded-lg hover:bg-muted transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={isSubmittingAccount}
                      className="px-4 py-2 bg-primary hover:bg-primary/90 text-primary-foreground font-semibold text-xs rounded-lg flex items-center gap-1.5 disabled:opacity-50 cursor-pointer transition-colors"
                    >
                      {isSubmittingAccount ? (
                        <>
                          <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                          <span>Mapping...</span>
                        </>
                      ) : (
                        <span>Confirm Mapping</span>
                      )}
                    </button>
                  </div>
                </form>
              )}

              {/* Accounts List */}
              <div className="border border-border rounded-xl divide-y divide-border overflow-hidden bg-card">
                {isAccountsLoading ? (
                  <div className="p-8 text-center text-xs text-muted-foreground">
                    <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-muted-foreground" />
                    Loading mapped CRM accounts...
                  </div>
                ) : accounts.length > 0 ? (
                  accounts.map((acc: any) => (
                    <div key={acc.id} className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-4 hover:bg-muted/30 transition-colors">
                      <div className="flex items-start gap-3">
                        <div className="p-2 bg-muted rounded-lg text-muted-foreground mt-0.5">
                          <Building2 className="w-4 h-4" />
                        </div>
                        <div>
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-semibold text-sm text-foreground">{acc.company_name}</span>
                            {getLifecycleStageBadge(acc.lifecycle_stage)}
                          </div>
                          <p className="text-xs text-muted-foreground mt-0.5">
                            Domain: <span className="text-foreground font-medium">{acc.domain}</span> &bull; Provider: <span className="text-foreground/80 capitalize">{acc.crm_provider}</span> ({acc.crm_company_id})
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center gap-3">
                        <div className="text-right text-xs">
                          <span className="text-emerald-600 dark:text-emerald-400 flex items-center gap-1 font-medium">
                            <CheckCircle2 className="w-3.5 h-3.5" /> Bi-Directional Synced
                          </span>
                          <span className="text-[11px] text-muted-foreground">
                            {acc.last_synced_at ? new Date(acc.last_synced_at).toLocaleTimeString() : 'Active'}
                          </span>
                        </div>

                        {deleteConfirmId === acc.id ? (
                          <div className="flex items-center gap-1.5 p-1 rounded-lg bg-destructive/10 border border-destructive/20 text-xs">
                            <span className="text-[11px] text-destructive font-medium px-1">Unlink?</span>
                            <button
                              type="button"
                              disabled={deletingAccountId === acc.id}
                              onClick={() => handleDeleteAccount(acc.id, acc.company_name)}
                              className="px-2 py-0.5 bg-destructive text-destructive-foreground rounded text-[10px] font-bold hover:bg-destructive/90 transition-colors"
                            >
                              {deletingAccountId === acc.id ? '...' : 'Yes'}
                            </button>
                            <button
                              type="button"
                              disabled={deletingAccountId === acc.id}
                              onClick={() => setDeleteConfirmId(null)}
                              className="px-2 py-0.5 bg-muted text-muted-foreground rounded text-[10px] hover:text-foreground transition-colors"
                            >
                              No
                            </button>
                          </div>
                        ) : (
                          <button
                            type="button"
                            onClick={() => setDeleteConfirmId(acc.id)}
                            className="p-1.5 rounded-lg border border-border text-muted-foreground hover:text-destructive hover:bg-destructive/10 hover:border-destructive/20 transition-colors cursor-pointer"
                            title="Unlink CRM Account Mapping"
                            aria-label={`Unlink CRM account ${acc.company_name}`}
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="p-8 text-center space-y-2">
                    <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center mx-auto text-muted-foreground">
                      <Building2 className="w-5 h-5" />
                    </div>
                    <div className="text-sm font-semibold text-foreground">No CRM Accounts Mapped</div>
                    <p className="text-xs text-muted-foreground max-w-sm mx-auto">
                      Map company root domains to HubSpot or Salesforce to automatically suppress outbound outreach on active deals.
                    </p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ════════════════ TAB 2: DEAL ATTRIBUTION ════════════════ */}
          {activeTab === 'attribution' && (
            <div className="space-y-6">
              {/* Attribution Simulator */}
              <form onSubmit={handleCalculateAttribution} className="p-4 bg-card border border-border rounded-xl space-y-4">
                <div className="flex items-center justify-between pb-2 border-b border-border">
                  <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                    <Sparkles className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                    Deal Revenue Attribution Engine
                  </div>
                  <span className="text-xs text-muted-foreground">Compute multi-touch attribution credit</span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div>
                    <label htmlFor="crm-deal-title" className="text-xs font-medium text-muted-foreground block mb-1">
                      Deal Title
                    </label>
                    <input
                      id="crm-deal-title"
                      type="text"
                      required
                      value={dealName}
                      onChange={e => setDealName(e.target.value)}
                      placeholder="e.g. Snowflake Enterprise Tier"
                      className="w-full bg-background border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
                    />
                  </div>

                  <div>
                    <label htmlFor="crm-deal-amount" className="text-xs font-medium text-muted-foreground block mb-1">
                      Deal Value ($ USD)
                    </label>
                    <input
                      id="crm-deal-amount"
                      type="number"
                      required
                      min={1}
                      value={dealAmountStr}
                      onChange={e => {
                        const val = e.target.value;
                        setDealAmountStr(val);
                        const n = parseInt(val, 10);
                        if (!isNaN(n)) setDealAmount(n);
                      }}
                      onBlur={() => {
                        const n = Math.max(100, parseInt(dealAmountStr, 10) || 120000);
                        setDealAmount(n);
                        setDealAmountStr(String(n));
                      }}
                      className="w-full bg-background border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
                    />
                  </div>

                  <div>
                    <label htmlFor="crm-attribution-model" className="text-xs font-medium text-muted-foreground block mb-1">
                      Attribution Model
                    </label>
                    <Select
                      value={attributionModel}
                      onValueChange={val => setAttributionModel(val as any)}
                    >
                      <SelectTrigger id="crm-attribution-model" className="w-full bg-background border-border h-9 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="w_shaped">W-Shaped (40% First / 40% Closer / 20% Nurture)</SelectItem>
                        <SelectItem value="first_touch">First-Touch (100% Creation Touch)</SelectItem>
                        <SelectItem value="last_touch">Last-Touch (100% Opportunity Touch)</SelectItem>
                        <SelectItem value="linear">Linear (Equal Touchpoint Distribution)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="flex justify-end pt-2">
                  <button
                    type="submit"
                    disabled={isCalculating || !canCrmSync}
                    className="px-4 py-2 bg-primary hover:bg-primary/90 text-primary-foreground font-semibold text-xs rounded-lg flex items-center gap-1.5 disabled:opacity-50 cursor-pointer transition-colors"
                  >
                    {isCalculating ? (
                      <>
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        <span>Computing...</span>
                      </>
                    ) : (
                      <span>Calculate &amp; Record Attribution</span>
                    )}
                  </button>
                </div>
              </form>

              {/* Attributed Deals List */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <h4 className="text-sm font-semibold text-foreground">Attributed Closed Deals</h4>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground font-medium">
                      {attributions.length} deals
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={handleExportCSV}
                    disabled={isExportingCsv || attributions.length === 0}
                    className="px-3 py-1.5 rounded-lg border border-border bg-card hover:bg-muted text-foreground text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer disabled:opacity-50"
                  >
                    <Download className="w-3.5 h-3.5 text-primary" />
                    <span>{isExportingCsv ? 'Exporting...' : 'Export Attribution CSV'}</span>
                  </button>
                </div>

                <div className="border border-border rounded-xl divide-y divide-border bg-card overflow-hidden">
                  {attributions.length > 0 ? (
                    attributions.map((d: any) => (
                      <div key={d.id} className="p-4 space-y-3 hover:bg-muted/30 transition-colors">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-semibold text-sm text-foreground">{d.deal_name}</span>
                            <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 font-bold">
                              ${Number(d.deal_amount).toLocaleString()}
                            </span>
                            <span className="text-[10px] px-2 py-0.5 rounded-full bg-muted text-muted-foreground capitalize font-mono">
                              Model: {d.attribution_model.replace('_', '-')}
                            </span>
                          </div>
                          <span className="text-xs text-muted-foreground">
                            {d.created_at ? new Date(d.created_at).toLocaleDateString() : 'Recent'}
                          </span>
                        </div>

                        {/* Touchpoints pills with proportional weights */}
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5 text-xs">
                          {(d.touchpoints || []).map((tp: any, idx: number) => {
                            const pct = Math.round((tp.weight || 0) * 100);
                            return (
                              <div key={idx} className="p-3 bg-muted/30 border border-border rounded-lg flex flex-col justify-between space-y-2">
                                <div className="flex items-center justify-between">
                                  <span className="text-muted-foreground text-[11px] capitalize font-medium">
                                    {tp.channel?.replace('_', ' ') || `Step ${tp.step}`}
                                  </span>
                                  <span className="text-[10px] text-muted-foreground font-mono">
                                    {pct}% credit
                                  </span>
                                </div>
                                <div className="space-y-1">
                                  <div className="w-full bg-muted h-1.5 rounded-full overflow-hidden">
                                    <div 
                                      className="bg-emerald-500 h-full rounded-full transition-all duration-300" 
                                      style={{ width: `${pct}%` }} 
                                    />
                                  </div>
                                  <span className="font-bold text-xs text-emerald-600 dark:text-emerald-400 block text-right">
                                    ${(tp.attributed_amount || 0).toLocaleString()}
                                  </span>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="p-8 text-center space-y-2">
                      <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center mx-auto text-muted-foreground">
                        <DollarSign className="w-5 h-5" />
                      </div>
                      <div className="text-sm font-semibold text-foreground">No Attributed Deals Recorded</div>
                      <p className="text-xs text-muted-foreground max-w-sm mx-auto">
                        Use the Deal Revenue Attribution Engine above to compute touchpoint weights and record closed-won attribution into your ledger.
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* ════════════════ TAB 3: WEBHOOKS & ECHO DEFENSE ════════════════ */}
          {activeTab === 'webhooks' && (
            <div className="space-y-4">
              <div className="p-4 bg-card border border-border rounded-xl space-y-3">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div>
                    <h4 className="text-sm font-bold text-foreground flex items-center gap-2">
                      <ShieldCheck className="w-4 h-4 text-primary" />
                      Bi-Directional Echo Loop Suppression
                    </h4>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Prevents recursive ping-pong webhook loops by computing canonical SHA256 hashes of payloads with a 60-second debounce ledger.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={handleSimulateWebhook}
                    disabled={isSimulatingWebhook}
                    className="px-4 py-2 bg-primary hover:bg-primary/90 text-primary-foreground font-semibold text-xs rounded-lg flex items-center gap-2 transition-colors disabled:opacity-50 cursor-pointer shrink-0 self-start sm:self-auto"
                  >
                    {isSimulatingWebhook ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                    <span>Simulate Inbound Webhook</span>
                  </button>
                </div>

                <div className="flex items-center gap-2 pt-2 border-t border-border">
                  <input
                    id="test-echo-mode"
                    type="checkbox"
                    checked={testEchoMode}
                    onChange={e => setTestEchoMode(e.target.checked)}
                    className="rounded border-border text-primary focus:ring-primary/20 h-4 w-4"
                  />
                  <label htmlFor="test-echo-mode" className="text-xs text-muted-foreground cursor-pointer">
                    Simulate duplicate payload (tests the 60-second SHA256 debounce suppression ledger)
                  </label>
                </div>
              </div>

              {/* Webhook Feed */}
              <div className="space-y-2">
                <h5 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Sync Audit Trail</h5>
                <div className="border border-border rounded-xl divide-y divide-border bg-card overflow-hidden">
                  {webhookLogs.length > 0 ? (
                    webhookLogs.map((log, idx) => (
                      <div key={idx} className="p-3.5 text-xs flex items-center justify-between hover:bg-muted/30 transition-colors">
                        <div className="flex items-center gap-2.5">
                          <span className={`p-1.5 rounded-lg border ${
                            log.status === 'skipped_echo'
                              ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20'
                              : 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                          }`}>
                            <ShieldCheck className="w-3.5 h-3.5" />
                          </span>
                          <div>
                            <span className="font-semibold text-foreground">{log.message}</span>
                            {log.halted > 0 && (
                              <p className="text-[11px] text-emerald-600 dark:text-emerald-400 mt-0.5">
                                Halted active outbound sequences for {log.halted} account lead(s).
                              </p>
                            )}
                          </div>
                        </div>
                        <span className="text-[11px] text-muted-foreground font-mono">{log.timestamp}</span>
                      </div>
                    ))
                  ) : (
                    <div className="p-8 text-center text-xs text-muted-foreground space-y-1">
                      <ShieldCheck className="w-6 h-6 mx-auto mb-1 text-muted-foreground" />
                      <p>No recent inbound webhooks tested.</p>
                      <p className="text-[11px]">Click "Simulate Inbound Webhook" above to trigger a deal stage change event.</p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

        </div>

        {/* Footer */}
        <div className="p-4 border-t border-border bg-card/60 flex items-center justify-between text-xs text-muted-foreground shrink-0">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
            <span>Bi-Directional Auto-Sync Active &bull; Multi-Touch Revenue Credited</span>
          </div>
          <button
            type="button"
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
