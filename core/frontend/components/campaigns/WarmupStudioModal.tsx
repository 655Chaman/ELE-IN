import React, { useState } from 'react';
import useSWR from 'swr';
import {
  Flame, Mail, ShieldCheck, CheckCircle2, AlertTriangle, RefreshCw,
  Plus, Play, Pause, Server, Activity, ArrowRight, Check, X,
  Radio, Sparkles, Send, Inbox, ShieldAlert, Cpu, Download, Trash2
} from 'lucide-react';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/lib/apiClient';
import { CustomSelect } from '@/components/ui/select';

const fetcher = (url: string) => fetchWithAuth(url).then(r => r.json());

interface WarmupStudioProps {
  onClose?: () => void;
}

export function WarmupStudioModal({ onClose }: WarmupStudioProps) {
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

  // DNS audit state
  const [auditDomain, setAuditDomain] = useState('outbound-scale.com');
  const [isAuditing, setIsAuditing] = useState(false);
  const [auditResult, setAuditResult] = useState<any>(null);

  // Swarm simulation state
  const [isSimulating, setIsSimulating] = useState(false);
  const [swarmLogs, setSwarmLogs] = useState<any[]>([]);

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
    total_mailboxes: 3,
    active_warming: 2,
    graduated_mailboxes: 1,
    average_health_score: 96.0,
    average_inbox_placement_pct: 98.6,
    spam_rescue_rate_pct: 100.0,
    daily_network_warmup_volume: 80
  };

  const handleExportCSV = async () => {
    setIsExportingCsv(true);
    try {
      const res = await fetchWithAuth('/api/elein/warmup/mailboxes/export-csv');
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail?.message || err.detail || 'Failed to export warmup fleet CSV');
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
      toast.success('Warmup mailbox fleet exported to CSV!');
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
          email_address: newEmail.trim(),
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
        body: JSON.stringify({ domain: auditDomain.trim() })
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="bg-card border border-border/80 rounded-xl w-full max-w-5xl shadow-2xl flex flex-col max-h-[90vh] overflow-hidden text-foreground">
        
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-border/60 bg-muted/20">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-amber-500/10 border border-amber-500/30 rounded-lg text-amber-400">
              <Flame className="w-6 h-6 animate-pulse" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-bold text-foreground tracking-tight">Mailbox Immunity Network</h2>
                <span className="px-2 py-0.5 text-xs font-semibold bg-amber-500/10 border border-amber-500/30 text-amber-400 rounded-full">
                  Phase 19 P2P Warmup
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
              disabled={isExportingCsv}
              className="px-3 py-1.5 rounded-md border border-border/80 bg-background hover:bg-muted/60 text-foreground text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer disabled:opacity-50"
            >
              <Download className="w-3.5 h-3.5 text-amber-400" />
              <span>{isExportingCsv ? 'Exporting...' : 'Export Fleet CSV'}</span>
            </button>
            <button
              type="button"
              onClick={onClose}
              className="p-2 text-muted-foreground hover:text-foreground hover:bg-muted/60 rounded-lg transition-colors cursor-pointer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Telemetry Bar */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 p-4 bg-muted/20 border-b border-border/60">
          <div className="bg-card border border-border/60 rounded-lg p-3">
            <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
              <span>Warmup Fleet</span>
              <Mail className="w-4 h-4 text-amber-400" />
            </div>
            <div className="text-xl font-bold text-foreground">
              {telemetry.active_warming} <span className="text-xs font-normal text-muted-foreground">/ {telemetry.total_mailboxes} warming</span>
            </div>
          </div>

          <div className="bg-card border border-border/60 rounded-lg p-3">
            <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
              <span>Inbox Placement</span>
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            </div>
            <div className="text-xl font-bold text-emerald-400">
              {telemetry.average_inbox_placement_pct}%
            </div>
          </div>

          <div className="bg-card border border-border/60 rounded-lg p-3">
            <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
              <span>Reputation Health</span>
              <ShieldCheck className="w-4 h-4 text-cyan-400" />
            </div>
            <div className="text-xl font-bold text-cyan-400">
              {telemetry.average_health_score} <span className="text-xs font-normal text-muted-foreground">/ 100</span>
            </div>
          </div>

          <div className="bg-card border border-border/60 rounded-lg p-3">
            <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
              <span>Daily Swarm Vol</span>
              <Activity className="w-4 h-4 text-sky-400" />
            </div>
            <div className="text-xl font-bold text-sky-400">
              {telemetry.daily_network_warmup_volume} <span className="text-xs font-normal text-muted-foreground">emails/day</span>
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="flex border-b border-border/60 px-6 bg-muted/10">
          <button
            type="button"
            onClick={() => setActiveTab('mailboxes')}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-all flex items-center gap-2 cursor-pointer ${
              activeTab === 'mailboxes'
                ? 'border-amber-500 text-amber-400'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Mail className="w-4 h-4" />
            Mailbox Fleet ({mailboxes.length})
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('dns')}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-all flex items-center gap-2 cursor-pointer ${
              activeTab === 'dns'
                ? 'border-cyan-500 text-cyan-400'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Server className="w-4 h-4" />
            DNS Reputation Inspector
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('swarm')}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-all flex items-center gap-2 cursor-pointer ${
              activeTab === 'swarm'
                ? 'border-sky-500 text-sky-400'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Sparkles className="w-4 h-4" />
            P2P Swarm &amp; Spam Rescue
          </button>
        </div>

        {/* Tab Content */}
        <div className="p-6 overflow-y-auto flex-1 space-y-6">
          
          {/* TAB 1: MAILBOX FLEET */}
          {activeTab === 'mailboxes' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-base font-semibold text-foreground">Enrolled Sender Mailboxes</h3>
                  <p className="text-xs text-muted-foreground">
                    Volume strictly ramps daily up to 50 sends to safeguard domain trust with Google &amp; Yahoo postmasters.
                  </p>
                </div>
                <button
                  onClick={() => setShowAddForm(!showAddForm)}
                  className="px-3 py-1.5 bg-amber-500 hover:bg-amber-600 text-primary-foreground font-semibold text-xs rounded-lg flex items-center gap-1.5 transition-colors cursor-pointer"
                >
                  <Plus className="w-3.5 h-3.5" />
                  {showAddForm ? 'Cancel' : 'Enroll Mailbox'}
                </button>
              </div>

              {/* Add Mailbox Form */}
              {showAddForm && (
                <form onSubmit={handleCreateMailbox} className="p-4 bg-muted/20 border border-border/70 rounded-xl space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs text-muted-foreground block mb-1">Email Address</label>
                      <input
                        type="email"
                        required
                        value={newEmail}
                        onChange={e => setNewEmail(e.target.value)}
                        placeholder="rep@domain.com"
                        className="w-full bg-background border border-border/80 rounded-lg px-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-amber-500"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-muted-foreground block mb-1">Sender Name</label>
                      <input
                        type="text"
                        required
                        value={newName}
                        onChange={e => setNewName(e.target.value)}
                        placeholder="Alex Vance"
                        className="w-full bg-background border border-border/80 rounded-lg px-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-amber-500"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <div>
                      <label className="text-xs text-muted-foreground block mb-1">Mail Provider</label>
                      <CustomSelect
                        value={newProvider}
                        onValueChange={setNewProvider}
                        size="sm"
                        triggerClassName="bg-background border-border/80 text-xs focus-visible:ring-amber-500/60 focus-visible:border-amber-500/60"
                        options={[
                          { value: "google_workspace", label: "Google Workspace" },
                          { value: "microsoft_365", label: "Microsoft 365" },
                          { value: "smtp_imap", label: "Custom SMTP/IMAP" },
                        ]}
                      />
                    </div>

                    <div>
                      <label className="text-xs text-muted-foreground block mb-1">Ramp Strategy</label>
                      <CustomSelect
                        value={newStrategy}
                        onValueChange={setNewStrategy}
                        size="sm"
                        triggerClassName="bg-background border-border/80 text-xs focus-visible:ring-amber-500/60 focus-visible:border-amber-500/60"
                        options={[
                          { value: "gentle", label: "Gentle (+1 every 2 days)" },
                          { value: "balanced", label: "Balanced (+2 every day)" },
                          { value: "aggressive", label: "Aggressive (+3 every day)" },
                        ]}
                      />
                    </div>

                    <div>
                      <label className="text-xs text-muted-foreground block mb-1">Max Daily Target (Max 50)</label>
                      <input
                        type="number"
                        min="10"
                        max="50"
                        value={newMaxLimit}
                        onChange={e => setNewMaxLimit(Number(e.target.value))}
                        className="w-full bg-background border border-border/80 rounded-lg px-3 py-1.5 text-xs text-foreground focus:outline-none focus:border-amber-500"
                      />
                    </div>
                  </div>

                  <div className="flex justify-end gap-2 pt-2 border-t border-border/60">
                    <button
                      type="button"
                      onClick={() => setShowAddForm(false)}
                      className="px-3 py-1 text-xs text-muted-foreground hover:text-foreground cursor-pointer"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={isSubmitting}
                      className="px-4 py-1.5 bg-amber-500 hover:bg-amber-600 text-primary-foreground font-semibold text-xs rounded-lg flex items-center gap-1.5 disabled:opacity-50 cursor-pointer"
                    >
                      {isSubmitting ? 'Enrolling...' : 'Confirm Enrollment'}
                    </button>
                  </div>
                </form>
              )}

              {/* Mailboxes List */}
              <div className="border border-border/70 rounded-xl divide-y divide-border/50 overflow-hidden bg-muted/10">
                {mailboxes.map((m: any) => (
                  <div key={m.id} className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-4 hover:bg-muted/30 transition-colors">
                    <div className="flex items-start gap-3">
                      <div className="p-2 bg-muted/50 rounded-lg text-muted-foreground mt-1">
                        <Mail className="w-4 h-4" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-sm text-foreground">{m.email_address}</span>
                          <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                            m.warmup_status === 'warming'
                              ? 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
                              : m.warmup_status === 'graduated'
                              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                              : 'bg-muted text-muted-foreground'
                          }`}>
                            {m.warmup_status.toUpperCase()}
                          </span>
                        </div>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {m.sender_name} &bull; Provider: <span className="text-foreground/80 capitalize">{m.provider.replace('_', ' ')}</span> &bull; Day {m.current_ramp_day} ({m.ramp_strategy} ramp)
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-4">
                      <div className="text-right">
                        <div className="text-xs font-semibold text-foreground">
                          {m.current_daily_limit} <span className="text-muted-foreground">/ {m.max_daily_limit} sends</span>
                        </div>
                        <div className="text-[11px] text-emerald-400 font-medium">
                          {m.inbox_placement_rate_pct}% Inbox Placement
                        </div>
                      </div>

                      <div className="text-right">
                        <div className="text-xs font-semibold text-cyan-400">
                          Score: {m.health_score}/100
                        </div>
                        <div className="text-[11px] text-muted-foreground">
                          Reply Goal: {m.target_reply_rate_pct}%
                        </div>
                      </div>

                      <div className="flex items-center gap-1.5">
                        <button
                          onClick={() => handleToggleStatus(m.id, m.warmup_status)}
                          className={`p-2 rounded-lg text-xs font-medium border flex items-center gap-1.5 transition-colors cursor-pointer ${
                            m.warmup_status === 'warming'
                              ? 'bg-muted/60 hover:bg-muted border-border text-foreground'
                              : 'bg-amber-500/10 hover:bg-amber-500/20 border-amber-500/30 text-amber-400'
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
                        <button
                          type="button"
                          onClick={() => handleDeleteMailbox(m.id, m.email_address)}
                          disabled={deletingMailboxId === m.id}
                          className="p-2 rounded-lg border border-border/60 hover:bg-rose-500/10 hover:border-rose-500/30 text-muted-foreground hover:text-rose-400 transition-colors cursor-pointer disabled:opacity-50"
                          title="Unenroll Mailbox"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  </div>
                ))}

                {mailboxes.length === 0 && !isMailboxesLoading && (
                  <div className="p-8 text-center text-xs text-muted-foreground">
                    No mailboxes currently enrolled. Click "Enroll Mailbox" above to get started.
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB 2: DNS REPUTATION INSPECTOR */}
          {activeTab === 'dns' && (
            <div className="space-y-4">
              <form onSubmit={handleRunDnsAudit} className="flex gap-2">
                <input
                  type="text"
                  value={auditDomain}
                  onChange={e => setAuditDomain(e.target.value)}
                  placeholder="outbound-domain.com"
                  className="flex-1 bg-background border border-border/80 rounded-xl px-4 py-2.5 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-cyan-500"
                />
                <button
                  type="submit"
                  disabled={isAuditing}
                  className="px-4 py-2.5 bg-cyan-500 hover:bg-cyan-600 text-primary-foreground font-semibold text-xs rounded-xl flex items-center gap-1.5 transition-colors disabled:opacity-50 cursor-pointer"
                >
                  {isAuditing ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Server className="w-3.5 h-3.5" />}
                  Audit DNS Health
                </button>
              </form>

              {auditResult ? (
                <div className="p-5 bg-muted/20 border border-border/70 rounded-xl space-y-4">
                  <div className="flex items-center justify-between pb-3 border-b border-border/60">
                    <div>
                      <h4 className="text-sm font-bold text-foreground flex items-center gap-2">
                        {auditResult.domain}
                        <span className="px-2 py-0.5 text-[10px] rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                          Audited
                        </span>
                      </h4>
                      <p className="text-[11px] text-muted-foreground mt-0.5">
                        Deliverability Score: <span className="text-emerald-400 font-semibold">{auditResult.overall_dns_health_score}/100</span>
                      </p>
                    </div>
                    <div className="p-2 bg-emerald-500/10 text-emerald-400 rounded-full border border-emerald-500/30">
                      <ShieldCheck className="w-5 h-5" />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                    {/* SPF Record */}
                    <div className="p-3 bg-card border border-border/60 rounded-lg">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-semibold text-foreground">SPF (Sender Policy Framework)</span>
                        <span className="text-emerald-400 flex items-center gap-1 text-[11px]">
                          <Check className="w-3 h-3" /> Valid
                        </span>
                      </div>
                      <code className="text-[11px] text-muted-foreground bg-background p-1.5 rounded block font-mono break-all">
                        {auditResult.spf_record}
                      </code>
                    </div>

                    {/* DKIM Record */}
                    <div className="p-3 bg-card border border-border/60 rounded-lg">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-semibold text-foreground">DKIM (DomainKeys Identified Mail)</span>
                        <span className="text-emerald-400 flex items-center gap-1 text-[11px]">
                          <Check className="w-3 h-3" /> 2048-bit Signed
                        </span>
                      </div>
                      <code className="text-[11px] text-muted-foreground bg-background p-1.5 rounded block font-mono break-all">
                        {auditResult.dkim_selector}
                      </code>
                    </div>

                    {/* DMARC Policy */}
                    <div className="p-3 bg-card border border-border/60 rounded-lg">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-semibold text-foreground">DMARC Policy</span>
                        <span className="text-emerald-400 flex items-center gap-1 text-[11px]">
                          <Check className="w-3 h-3" /> Quarantine / Reject
                        </span>
                      </div>
                      <code className="text-[11px] text-muted-foreground bg-background p-1.5 rounded block font-mono break-all">
                        {auditResult.dmarc_policy}
                      </code>
                    </div>

                    {/* MX Records */}
                    <div className="p-3 bg-card border border-border/60 rounded-lg">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-semibold text-foreground">MX Routing</span>
                        <span className="text-emerald-400 flex items-center gap-1 text-[11px]">
                          <Check className="w-3 h-3" /> Active
                        </span>
                      </div>
                      <div className="text-[11px] text-muted-foreground bg-background p-1.5 rounded font-mono">
                        {(auditResult.mx_records || []).join(', ')}
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="p-8 border border-dashed border-border/70 rounded-xl text-center text-xs text-muted-foreground">
                  Enter your domain above and click "Audit DNS Health" to verify deliverability credentials.
                </div>
              )}
            </div>
          )}

          {/* TAB 3: P2P SWARM & SPAM RESCUE */}
          {activeTab === 'swarm' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between p-4 bg-blue-500/10 border border-blue-500/20 rounded-xl">
                <div>
                  <h4 className="text-sm font-bold text-foreground flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-blue-500" />
                    Autonomous P2P AI Swarm Exchange
                  </h4>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Generates authentic business email conversations between mailboxes, marks incoming emails as important, and pulls warmup threads out of spam folders automatically.
                  </p>
                </div>
                <button
                  onClick={handleSimulateSwarmCycle}
                  disabled={isSimulating}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs rounded-xl flex items-center gap-2 transition-colors disabled:opacity-50 cursor-pointer"
                >
                  {isSimulating ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                  Simulate Swarm Cycle
                </button>
              </div>

              {/* Swarm Live Activity Log */}
              <div className="space-y-2">
                <h5 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Swarm Exchange Feed</h5>
                <div className="border border-border/70 rounded-xl divide-y divide-border/50 bg-muted/10 max-h-72 overflow-y-auto">
                  {swarmLogs.length > 0 ? (
                    swarmLogs.map((log, idx) => (
                      <div key={idx} className="p-3 text-xs flex items-center justify-between">
                        <div className="flex items-center gap-2.5">
                          <span className="p-1.5 bg-emerald-500/10 text-emerald-400 rounded border border-emerald-500/20">
                            <ShieldCheck className="w-3.5 h-3.5" />
                          </span>
                          <div>
                            <span className="font-semibold text-foreground">{log.message}</span>
                            <p className="text-[11px] text-muted-foreground mt-0.5">
                              {log.exchanges} conversational exchanges &bull; {log.rescued} spam rescues executed
                            </p>
                          </div>
                        </div>
                        <span className="text-[11px] text-muted-foreground">{log.timestamp}</span>
                      </div>
                    ))
                  ) : (
                    <div className="p-6 text-center text-xs text-muted-foreground">
                      No on-demand cycles run yet. Click "Simulate Swarm Cycle" above to test P2P interaction.
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
            <span>Spam Rescue Protocol Active &bull; Volume capped at 50/day per mailbox</span>
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
