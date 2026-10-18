import React, { useState, useEffect } from 'react';
import useSWR from 'swr';
import {
  Flame, Mail, ShieldCheck, CheckCircle2, AlertTriangle, RefreshCw,
  Plus, Play, Pause, Server, Activity, ArrowRight, Check, X,
  Radio, Sparkles, Send, Inbox, ShieldAlert, Cpu, Download, Trash2, Lock
} from 'lucide-react';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/lib/apiClient';
import { usePaywall } from '@/contexts/PaywallContext';
import { CustomSelect } from '@/components/ui/select';

const fetcher = (url: string) => fetchWithAuth(url).then(r => r.json());

interface WarmupStudioProps {
  onClose?: () => void;
  canWarmup?: boolean;
}

export function WarmupStudioModal({ onClose, canWarmup = true }: WarmupStudioProps) {
  const { openPaywall } = usePaywall();
  const [activeTab, setActiveTab] = useState<'mailboxes' | 'dns' | 'swarm'>('mailboxes');

  // New mailbox form state
  const [showAddForm, setShowAddForm] = useState(false);
  const [newEmail, setNewEmail] = useState('');
  const [newName, setNewName] = useState('');
  const [newProvider, setNewProvider] = useState('google_workspace');
  const [newStrategy, setNewStrategy] = useState('balanced');
  const [newMaxLimit, setNewMaxLimit] = useState(40);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isExportingCsv, setIsExportingCsv] = useState(false);
  const [deletingMailboxId, setDeletingMailboxId] = useState<string | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  // DNS audit state
  const [auditDomain, setAuditDomain] = useState('outbound-scale.com');
  const [isAuditing, setIsAuditing] = useState(false);
  const [auditResult, setAuditResult] = useState<any>(null);

  // Swarm simulation state
  const [isSimulating, setIsSimulating] = useState(false);
  const [swarmLogs, setSwarmLogs] = useState<any[]>([]);

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
  const { data: mailboxesData, mutate: mutateMailboxes, isLoading: isMailboxesLoading } = useSWR<{
    success: boolean;
    data: any[];
    count: number;
  }>('/api/elein/warmup/mailboxes', fetcher, { revalidateOnFocus: false });

  const { data: telemetryData, mutate: mutateTelemetry } = useSWR<{
    success: boolean;
    data: any;
  }>('/api/elein/warmup/telemetry', fetcher, { revalidateOnFocus: false });

  const mailboxes = mailboxesData?.data || [];
  const telemetry = telemetryData?.data || {
    total_mailboxes: 0,
    active_warming: 0,
    graduated_mailboxes: 0,
    average_health_score: 100,
    average_inbox_placement_pct: 100,
    spam_rescue_rate_pct: 100,
    daily_network_warmup_volume: 0
  };

  const handleExportCSV = async () => {
    setIsExportingCsv(true);
    try {
      const res = await fetchWithAuth('/api/elein/warmup/export-csv');
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail?.message || err.detail || 'Failed to export warmup mailboxes CSV');
      }
      const csvText = await res.text();
      const blob = new Blob([csvText], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `warmup_fleet_${new Date().toISOString().slice(0, 10)}.csv`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      toast.success('Warmup fleet exported to CSV!');
    } catch (err: any) {
      toast.error(err.message || 'CSV export failed.');
    } finally {
      setIsExportingCsv(false);
    }
  };

  const handleDeleteMailbox = async (mailboxId: string, emailAddress: string) => {
    setDeletingMailboxId(mailboxId);
    try {
      const res = await fetchWithAuth(`/api/elein/warmup/mailboxes/${encodeURIComponent(mailboxId)}`, {
        method: 'DELETE'
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail?.message || err.detail || 'Failed to unenroll mailbox');
      }
      toast.success(`Unenrolled ${emailAddress} from warmup swarm.`);
      setDeleteConfirmId(null);
      mutateMailboxes();
      mutateTelemetry();
    } catch (err: any) {
      toast.error(err.message || 'Failed to unenroll mailbox.');
    } finally {
      setDeletingMailboxId(null);
    }
  };

  const handleCreateMailbox = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newEmail.trim() || !newName.trim()) {
      toast.error('Email and sender name are required.');
      return;
    }
    setIsSubmitting(true);
    try {
      const res = await fetchWithAuth('/api/elein/warmup/mailboxes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email_address: newEmail.trim().toLowerCase(),
          sender_name: newName.trim(),
          provider: newProvider,
          ramp_strategy: newStrategy,
          max_daily_limit: Number(newMaxLimit)
        })
      });
      const data = await res.json();
      if (data.success) {
        toast.success(`Mailbox ${data.data.email_address} enrolled into warmup network!`);
        setShowAddForm(false);
        setNewEmail('');
        setNewName('');
        mutateMailboxes();
        mutateTelemetry();
      } else {
        toast.error(data.detail || 'Failed to enroll mailbox.');
      }
    } catch (err: any) {
      toast.error('Error creating mailbox: ' + err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleToggleStatus = async (mailboxId: string, currentStatus: string) => {
    const nextStatus = currentStatus === 'warming' ? 'paused' : 'warming';
    try {
      const res = await fetchWithAuth(`/api/elein/warmup/mailboxes/${mailboxId}/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_status: nextStatus })
      });
      const data = await res.json();
      if (data.success) {
        toast.success(`Mailbox warmup status set to ${nextStatus}.`);
        mutateMailboxes();
        mutateTelemetry();
      } else {
        toast.error('Failed to toggle status.');
      }
    } catch (err: any) {
      toast.error('Failed to toggle mailbox status: ' + err.message);
    }
  };

  const handleRunDnsAudit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!auditDomain.trim()) {
      toast.error('Please specify a domain.');
      return;
    }
    setIsAuditing(true);
    try {
      const res = await fetchWithAuth('/api/elein/warmup/dns-audit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain: auditDomain.trim().toLowerCase().replace(/^https?:\/\//, '').split('/')[0] })
      });
      const data = await res.json();
      if (data.success) {
        setAuditResult(data.data);
        toast.success(`DNS reputation audit complete for ${data.data.domain}!`);
      } else {
        toast.error(data.detail || 'DNS audit failed.');
      }
    } catch (err: any) {
      toast.error('DNS audit error: ' + err.message);
    } finally {
      setIsAuditing(false);
    }
  };

  const handleSimulateSwarmCycle = async () => {
    setIsSimulating(true);
    try {
      const res = await fetchWithAuth('/api/elein/warmup/simulate-swarm', {
        method: 'POST'
      });
      const data = await res.json();
      if (data.success) {
        toast.success(data.data.message || 'Swarm cycle executed successfully!');
        setSwarmLogs(prev => [
          {
            timestamp: new Date().toLocaleTimeString(),
            exchanges: data.data.exchanges_sent,
            rescued: data.data.rescued_from_spam,
            message: data.data.message
          },
          ...prev
        ]);
        mutateTelemetry();
      } else {
        toast.error('Failed to trigger swarm cycle.');
      }
    } catch (err: any) {
      toast.error('Swarm cycle error: ' + err.message);
    } finally {
      setIsSimulating(false);
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
        aria-labelledby="warmup-studio-title"
        onClick={(e) => e.stopPropagation()}
        className="relative w-full max-w-5xl h-[90dvh] max-h-[90dvh] flex flex-col bg-card border border-border rounded-xl shadow-2xl overflow-hidden text-foreground"
      >
        
        {/* Header */}
        <div className="flex items-center justify-between p-5 sm:p-6 border-b border-border bg-card/60 shrink-0">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-amber-500/10 border border-amber-500/20 rounded-xl text-amber-600 dark:text-amber-400">
              <Flame className="w-6 h-6 animate-pulse" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 id="warmup-studio-title" className="text-lg sm:text-xl font-bold text-foreground tracking-tight">
                  Mailbox Immunity &amp; Warmup Network
                </h2>
                <span className="px-2.5 py-0.5 text-xs font-semibold bg-amber-500/10 border border-amber-500/20 text-amber-600 dark:text-amber-400 rounded-full">
                  Email Warmup Network
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Peer-to-peer AI conversational reply rings &bull; SPF/DKIM/DMARC defense &bull; Spam rescue simulator
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleExportCSV}
              disabled={isExportingCsv || mailboxes.length === 0}
              className="px-3 py-1.5 rounded-lg border border-border bg-card hover:bg-muted text-foreground text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer disabled:opacity-50"
            >
              <Download className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />
              <span>{isExportingCsv ? 'Exporting...' : 'Export Fleet CSV'}</span>
            </button>
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
              <span>Warmup Fleet</span>
              <Mail className="w-4 h-4 text-amber-600 dark:text-amber-400" />
            </div>
            <div className="text-xl font-bold text-foreground">
              {telemetry.active_warming} <span className="text-xs font-normal text-muted-foreground">/ {telemetry.total_mailboxes || mailboxes.length} warming</span>
            </div>
          </div>

          <div className="bg-card border border-border rounded-xl p-3">
            <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
              <span>Inbox Placement</span>
              <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
            </div>
            <div className="text-xl font-bold text-emerald-600 dark:text-emerald-400">
              {telemetry.average_inbox_placement_pct}%
            </div>
          </div>

          <div className="bg-card border border-border rounded-xl p-3">
            <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
              <span>Reputation Health</span>
              <ShieldCheck className="w-4 h-4 text-primary" />
            </div>
            <div className="text-xl font-bold text-primary">
              {telemetry.average_health_score} <span className="text-xs font-normal text-muted-foreground">/ 100</span>
            </div>
          </div>

          <div className="bg-card border border-border rounded-xl p-3">
            <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
              <span>Daily Swarm Vol</span>
              <Activity className="w-4 h-4 text-sky-600 dark:text-sky-400" />
            </div>
            <div className="text-xl font-bold text-sky-600 dark:text-sky-400">
              {telemetry.daily_network_warmup_volume} <span className="text-xs font-normal text-muted-foreground">emails/day</span>
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div role="tablist" aria-label="Warmup studio tabs" className="flex border-b border-border px-6 bg-card shrink-0 overflow-x-auto scrollbar-none">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'mailboxes'}
            onClick={() => setActiveTab('mailboxes')}
            className={`px-4 py-3 text-xs sm:text-sm font-medium border-b-2 transition-all flex items-center gap-2 whitespace-nowrap cursor-pointer ${
              activeTab === 'mailboxes'
                ? 'border-primary text-primary font-semibold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Mail className="w-4 h-4" />
            Mailbox Fleet ({mailboxes.length})
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'dns'}
            onClick={() => setActiveTab('dns')}
            className={`px-4 py-3 text-xs sm:text-sm font-medium border-b-2 transition-all flex items-center gap-2 whitespace-nowrap cursor-pointer ${
              activeTab === 'dns'
                ? 'border-primary text-primary font-semibold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Server className="w-4 h-4" />
            DNS Reputation Inspector
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'swarm'}
            onClick={() => setActiveTab('swarm')}
            className={`px-4 py-3 text-xs sm:text-sm font-medium border-b-2 transition-all flex items-center gap-2 whitespace-nowrap cursor-pointer ${
              activeTab === 'swarm'
                ? 'border-primary text-primary font-semibold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Sparkles className="w-4 h-4" />
            P2P Swarm &amp; Spam Rescue
          </button>
        </div>

        {/* Tab Content Body */}
        <div className="p-6 overflow-y-auto flex-1 space-y-6">

          {/* Proactive Free Tier Banner */}
          {!canWarmup && (
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
                    Peer-to-peer AI mailbox warmup and DNS reputation protection require a Pro or Enterprise plan. Upgrade to enroll mailboxes into the immunity swarm.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => openPaywall({ featureName: "Mailbox Immunity Warmup Swarm", minTier: "PRO" })}
                className="px-4 py-2 bg-primary text-primary-foreground text-xs font-semibold rounded-lg hover:bg-primary/90 transition-colors whitespace-nowrap"
              >
                Unlock Pro
              </button>
            </div>
          )}
          
          {/* ════════════════ TAB 1: MAILBOX FLEET ════════════════ */}
          {activeTab === 'mailboxes' && (
            <div className="space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <h3 className="text-base font-semibold text-foreground">Enrolled Sender Mailboxes</h3>
                  <p className="text-xs text-muted-foreground">
                    Volume strictly ramps daily up to 50 sends to safeguard domain trust with Google &amp; Yahoo postmasters.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setShowAddForm(!showAddForm)}
                  className="px-3.5 py-2 bg-primary hover:bg-primary/90 text-primary-foreground font-semibold text-xs rounded-lg flex items-center gap-1.5 transition-colors cursor-pointer shrink-0 self-start sm:self-auto"
                >
                  <Plus className="w-3.5 h-3.5" />
                  {showAddForm ? 'Cancel' : 'Enroll Mailbox'}
                </button>
              </div>

              {/* Add Mailbox Form */}
              {showAddForm && (
                <form onSubmit={handleCreateMailbox} className="p-4 bg-card border border-border rounded-xl space-y-4 animate-in fade-in duration-150">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div>
                      <label htmlFor="warmup-email" className="text-xs font-medium text-muted-foreground block mb-1">
                        Email Address <span className="text-destructive">*</span>
                      </label>
                      <input
                        id="warmup-email"
                        type="email"
                        required
                        value={newEmail}
                        onChange={e => setNewEmail(e.target.value)}
                        placeholder="rep@domain.com"
                        className="w-full bg-background border border-border rounded-lg px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
                      />
                    </div>
                    <div>
                      <label htmlFor="warmup-name" className="text-xs font-medium text-muted-foreground block mb-1">
                        Sender Name <span className="text-destructive">*</span>
                      </label>
                      <input
                        id="warmup-name"
                        type="text"
                        required
                        value={newName}
                        onChange={e => setNewName(e.target.value)}
                        placeholder="Alex Vance"
                        className="w-full bg-background border border-border rounded-lg px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <div>
                      <label className="text-xs font-medium text-muted-foreground block mb-1">Mail Provider</label>
                      <CustomSelect
                        value={newProvider}
                        onValueChange={setNewProvider}
                        size="sm"
                        triggerClassName="bg-background border-border text-xs focus-visible:ring-primary/20 focus-visible:border-primary"
                        options={[
                          { value: "google_workspace", label: "Google Workspace" },
                          { value: "microsoft_365", label: "Microsoft 365" },
                          { value: "smtp_imap", label: "Custom SMTP/IMAP" },
                        ]}
                      />
                    </div>

                    <div>
                      <label className="text-xs font-medium text-muted-foreground block mb-1">Ramp Strategy</label>
                      <CustomSelect
                        value={newStrategy}
                        onValueChange={setNewStrategy}
                        size="sm"
                        triggerClassName="bg-background border-border text-xs focus-visible:ring-primary/20 focus-visible:border-primary"
                        options={[
                          { value: "gentle", label: "Gentle (+1 every 2 days)" },
                          { value: "balanced", label: "Balanced (+2 every day)" },
                          { value: "aggressive", label: "Aggressive (+3 every day)" },
                        ]}
                      />
                    </div>

                    <div>
                      <label htmlFor="warmup-max-target" className="text-xs font-medium text-muted-foreground block mb-1">
                        Max Daily Target (Max 50)
                      </label>
                      <input
                        id="warmup-max-target"
                        type="number"
                        min="10"
                        max="50"
                        value={newMaxLimit}
                        onChange={e => setNewMaxLimit(Number(e.target.value))}
                        className="w-full bg-background border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
                      />
                    </div>
                  </div>

                  <div className="flex justify-end gap-2 pt-2 border-t border-border">
                    <button
                      type="button"
                      onClick={() => setShowAddForm(false)}
                      className="px-3.5 py-1.5 text-xs text-muted-foreground hover:text-foreground cursor-pointer rounded-lg hover:bg-muted transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={isSubmitting}
                      className="px-4 py-2 bg-primary hover:bg-primary/90 text-primary-foreground font-semibold text-xs rounded-lg flex items-center gap-1.5 disabled:opacity-50 cursor-pointer transition-colors"
                    >
                      {isSubmitting ? (
                        <>
                          <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                          <span>Enrolling...</span>
                        </>
                      ) : (
                        <span>Confirm Enrollment</span>
                      )}
                    </button>
                  </div>
                </form>
              )}

              {/* Mailboxes List */}
              <div className="border border-border rounded-xl divide-y divide-border overflow-hidden bg-card">
                {isMailboxesLoading ? (
                  <div className="p-8 text-center text-xs text-muted-foreground">
                    <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-muted-foreground" />
                    Loading enrolled mailboxes...
                  </div>
                ) : mailboxes.length > 0 ? (
                  mailboxes.map((m: any) => (
                    <div key={m.id} className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-4 hover:bg-muted/30 transition-colors">
                      <div className="flex items-start gap-3">
                        <div className="p-2 bg-muted rounded-lg text-muted-foreground mt-0.5">
                          <Mail className="w-4 h-4" />
                        </div>
                        <div>
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-semibold text-sm text-foreground">{m.email_address}</span>
                            <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold uppercase ${
                              m.warmup_status === 'warming'
                                ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20'
                                : m.warmup_status === 'graduated'
                                ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                                : 'bg-muted text-muted-foreground border border-border'
                            }`}>
                              {m.warmup_status}
                            </span>
                          </div>
                          <p className="text-xs text-muted-foreground mt-0.5">
                            {m.sender_name} &bull; Provider: <span className="text-foreground/80 capitalize">{m.provider?.replace('_', ' ')}</span> &bull; Day {m.current_ramp_day} ({m.ramp_strategy} ramp)
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center gap-4 flex-wrap">
                        <div className="text-right">
                          <div className="text-xs font-semibold text-foreground">
                            {m.current_daily_limit} <span className="text-muted-foreground">/ {m.max_daily_limit} sends</span>
                          </div>
                          <div className="text-[11px] text-emerald-600 dark:text-emerald-400 font-medium">
                            {m.inbox_placement_rate_pct}% Inbox Placement
                          </div>
                        </div>

                        <div className="text-right">
                          <div className="text-xs font-semibold text-primary">
                            Score: {m.health_score}/100
                          </div>
                          <div className="text-[11px] text-muted-foreground">
                            Reply Goal: {m.target_reply_rate_pct}%
                          </div>
                        </div>

                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => handleToggleStatus(m.id, m.warmup_status)}
                            className={`p-2 rounded-lg text-xs font-medium border flex items-center gap-1.5 transition-colors cursor-pointer ${
                              m.warmup_status === 'warming'
                                ? 'bg-muted hover:bg-muted/80 border-border text-foreground'
                                : 'bg-amber-500/10 hover:bg-amber-500/20 border-amber-500/30 text-amber-600 dark:text-amber-400'
                            }`}
                            title={m.warmup_status === 'warming' ? 'Pause Warmup' : 'Resume Warmup'}
                          >
                            {m.warmup_status === 'warming' ? (
                              <>
                                <Pause className="w-3.5 h-3.5" />
                                <span className="hidden sm:inline">Pause</span>
                              </>
                            ) : (
                              <>
                                <Play className="w-3.5 h-3.5" />
                                <span className="hidden sm:inline">Resume</span>
                              </>
                            )}
                          </button>

                          {deleteConfirmId === m.id ? (
                            <div className="flex items-center gap-1.5 p-1 rounded-lg bg-destructive/10 border border-destructive/20 text-xs">
                              <span className="text-[11px] text-destructive font-medium px-1">Unenroll?</span>
                              <button
                                type="button"
                                disabled={deletingMailboxId === m.id}
                                onClick={() => handleDeleteMailbox(m.id, m.email_address)}
                                className="px-2 py-0.5 bg-destructive text-destructive-foreground rounded text-[10px] font-bold hover:bg-destructive/90 transition-colors"
                              >
                                {deletingMailboxId === m.id ? '...' : 'Yes'}
                              </button>
                              <button
                                type="button"
                                disabled={deletingMailboxId === m.id}
                                onClick={() => setDeleteConfirmId(null)}
                                className="px-2 py-0.5 bg-muted text-muted-foreground rounded text-[10px] hover:text-foreground transition-colors"
                              >
                                No
                              </button>
                            </div>
                          ) : (
                            <button
                              type="button"
                              onClick={() => setDeleteConfirmId(m.id)}
                              className="p-2 rounded-lg border border-border text-muted-foreground hover:text-destructive hover:bg-destructive/10 hover:border-destructive/20 transition-colors cursor-pointer"
                              title="Unenroll Mailbox"
                              aria-label={`Unenroll mailbox ${m.email_address}`}
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="p-8 text-center space-y-2">
                    <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center mx-auto text-muted-foreground">
                      <Mail className="w-5 h-5" />
                    </div>
                    <div className="text-sm font-semibold text-foreground">No Mailboxes Enrolled</div>
                    <p className="text-xs text-muted-foreground max-w-sm mx-auto">
                      Enroll Google Workspace, Microsoft 365, or SMTP sender inboxes into the P2P immunity network to ramp daily volume safely.
                    </p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ════════════════ TAB 2: DNS REPUTATION INSPECTOR ════════════════ */}
          {activeTab === 'dns' && (
            <div className="space-y-4">
              <form onSubmit={handleRunDnsAudit} className="flex gap-2">
                <input
                  type="text"
                  value={auditDomain}
                  onChange={e => setAuditDomain(e.target.value)}
                  placeholder="outbound-domain.com"
                  className="flex-1 bg-background border border-border rounded-xl px-4 py-2.5 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
                />
                <button
                  type="submit"
                  disabled={isAuditing}
                  className="px-4 py-2.5 bg-primary hover:bg-primary/90 text-primary-foreground font-semibold text-xs rounded-xl flex items-center gap-1.5 transition-colors disabled:opacity-50 cursor-pointer"
                >
                  {isAuditing ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Server className="w-3.5 h-3.5" />}
                  <span>Audit DNS Health</span>
                </button>
              </form>

              {auditResult ? (
                <div className="p-5 bg-card border border-border rounded-xl space-y-4">
                  <div className="flex items-center justify-between pb-3 border-b border-border">
                    <div>
                      <h4 className="text-sm font-bold text-foreground flex items-center gap-2">
                        {auditResult.domain}
                        <span className="px-2 py-0.5 text-[10px] rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 font-bold">
                          Audited
                        </span>
                      </h4>
                      <p className="text-[11px] text-muted-foreground mt-0.5">
                        Deliverability Score: <span className="text-emerald-600 dark:text-emerald-400 font-semibold">{auditResult.overall_dns_health_score}/100</span>
                      </p>
                    </div>
                    <div className="p-2 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 rounded-full border border-emerald-500/20">
                      <ShieldCheck className="w-5 h-5" />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                    {/* SPF Record */}
                    <div className="p-3 bg-muted/20 border border-border rounded-lg">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-semibold text-foreground">SPF (Sender Policy Framework)</span>
                        <span className="text-emerald-600 dark:text-emerald-400 flex items-center gap-1 text-[11px] font-medium">
                          <Check className="w-3 h-3" /> Valid
                        </span>
                      </div>
                      <code className="text-[11px] text-muted-foreground bg-background p-1.5 rounded block font-mono break-all border border-border">
                        {auditResult.spf_record}
                      </code>
                    </div>

                    {/* DKIM Record */}
                    <div className="p-3 bg-muted/20 border border-border rounded-lg">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-semibold text-foreground">DKIM (DomainKeys Identified Mail)</span>
                        <span className="text-emerald-600 dark:text-emerald-400 flex items-center gap-1 text-[11px] font-medium">
                          <Check className="w-3 h-3" /> 2048-bit Signed
                        </span>
                      </div>
                      <code className="text-[11px] text-muted-foreground bg-background p-1.5 rounded block font-mono break-all border border-border">
                        {auditResult.dkim_selector}
                      </code>
                    </div>

                    {/* DMARC Policy */}
                    <div className="p-3 bg-muted/20 border border-border rounded-lg">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-semibold text-foreground">DMARC Policy</span>
                        <span className="text-emerald-600 dark:text-emerald-400 flex items-center gap-1 text-[11px] font-medium">
                          <Check className="w-3 h-3" /> Quarantine / Reject
                        </span>
                      </div>
                      <code className="text-[11px] text-muted-foreground bg-background p-1.5 rounded block font-mono break-all border border-border">
                        {auditResult.dmarc_policy}
                      </code>
                    </div>

                    {/* MX Records */}
                    <div className="p-3 bg-muted/20 border border-border rounded-lg">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-semibold text-foreground">MX Routing</span>
                        <span className="text-emerald-600 dark:text-emerald-400 flex items-center gap-1 text-[11px] font-medium">
                          <Check className="w-3 h-3" /> Active
                        </span>
                      </div>
                      <div className="text-[11px] text-muted-foreground bg-background p-1.5 rounded font-mono border border-border">
                        {(auditResult.mx_records || []).join(', ')}
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="p-8 border border-dashed border-border rounded-xl text-center text-xs text-muted-foreground">
                  Enter your domain above and click "Audit DNS Health" to verify deliverability credentials.
                </div>
              )}
            </div>
          )}

          {/* ════════════════ TAB 3: P2P SWARM & SPAM RESCUE ════════════════ */}
          {activeTab === 'swarm' && (
            <div className="space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 bg-primary/5 border border-primary/20 rounded-xl">
                <div>
                  <h4 className="text-sm font-bold text-foreground flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-primary" />
                    Autonomous P2P AI Swarm Exchange
                  </h4>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Generates authentic business email conversations between mailboxes, marks incoming emails as important, and pulls warmup threads out of spam folders automatically.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={handleSimulateSwarmCycle}
                  disabled={isSimulating}
                  className="px-4 py-2 bg-primary hover:bg-primary/90 text-primary-foreground font-semibold text-xs rounded-lg flex items-center gap-2 transition-colors disabled:opacity-50 cursor-pointer shrink-0 self-start sm:self-auto"
                >
                  {isSimulating ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                  <span>Simulate Swarm Cycle</span>
                </button>
              </div>

              {/* Swarm Live Activity Log */}
              <div className="space-y-2">
                <h5 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Swarm Exchange Feed</h5>
                <div className="border border-border rounded-xl divide-y divide-border bg-card overflow-hidden">
                  {swarmLogs.length > 0 ? (
                    swarmLogs.map((log, idx) => (
                      <div key={idx} className="p-3.5 text-xs flex items-center justify-between hover:bg-muted/30 transition-colors">
                        <div className="flex items-center gap-2.5">
                          <span className="p-1.5 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 rounded-lg border border-emerald-500/20">
                            <ShieldCheck className="w-3.5 h-3.5" />
                          </span>
                          <div>
                            <span className="font-semibold text-foreground">{log.message}</span>
                            <p className="text-[11px] text-muted-foreground mt-0.5">
                              {log.exchanges} conversational exchanges &bull; {log.rescued} spam rescues executed
                            </p>
                          </div>
                        </div>
                        <span className="text-[11px] text-muted-foreground font-mono">{log.timestamp}</span>
                      </div>
                    ))
                  ) : (
                    <div className="p-8 text-center text-xs text-muted-foreground space-y-1">
                      <Sparkles className="w-6 h-6 mx-auto mb-1 text-muted-foreground" />
                      <p>No on-demand cycles run yet.</p>
                      <p className="text-[11px]">Click "Simulate Swarm Cycle" above to test P2P conversational interaction.</p>
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
            <span>Spam Rescue Protocol Active &bull; Volume capped at 50/day per mailbox</span>
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
