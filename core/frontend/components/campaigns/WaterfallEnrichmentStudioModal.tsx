import React, { useState, useEffect } from 'react';
import useSWR from 'swr';
import {
  Workflow, Layers, Sparkles, RefreshCw, Copy, Check, CheckCircle2,
  X, Plus, ExternalLink, ShieldCheck, Search, ArrowRight,
  TrendingUp, AlertTriangle, DollarSign, Play, Lock, Download
} from 'lucide-react';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/lib/apiClient';
import { usePaywall } from '@/contexts/PaywallContext';

const fetcher = (url: string) => fetchWithAuth(url).then(r => r.json());

interface WaterfallStudioProps {
  onClose?: () => void;
  campaignId?: string;
  canWaterfallEnrichment?: boolean;
}

export function WaterfallEnrichmentStudioModal({ 
  onClose, 
  campaignId,
  canWaterfallEnrichment = true 
}: WaterfallStudioProps) {
  const { openPaywall } = usePaywall();
  const [activeTab, setActiveTab] = useState<'runner' | 'chain' | 'analytics'>('runner');
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // ── Tab 1: Runner State ──
  const [leadName, setLeadName] = useState('Guillermo Rauch');
  const [domain, setDomain] = useState('vercel.com');
  const [isEnriching, setIsEnriching] = useState(false);
  const [batchMode, setBatchMode] = useState(false);
  const [batchInput, setBatchInput] = useState(
    "Dylan Field, figma.com\nBrian Chesky, airbnb.com\nShiva Rajaraman, uber.com"
  );

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

  const { data: runsData, mutate: mutateRuns, isLoading: isRunsLoading } = useSWR<{
    success: boolean;
    runs: any[];
    total: number;
  }>('/api/elein/waterfall/runs', fetcher, { revalidateOnFocus: false });

  const { data: configsData } = useSWR<{
    success: boolean;
    configs: any[];
  }>('/api/elein/waterfall/configs', fetcher, { revalidateOnFocus: false });

  const { data: telemetryData } = useSWR<{
    success: boolean;
    telemetry: any;
  }>('/api/elein/waterfall/telemetry', fetcher, { revalidateOnFocus: false });

  const telemetry = telemetryData?.telemetry || {
    overall_match_rate_pct: 88.5,
    waterfall_lift_pct: 36.5,
    valid_verified: 24,
    catchalls_shielded: 5,
    estimated_credits_saved: 42.0
  };

  const copyToClipboard = (text: string, key: string) => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    toast.success('Copied email to clipboard!');
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const handleExportCsv = () => {
    const runsList = runsData?.runs || [];
    if (runsList.length === 0) {
      toast.error('No enriched runs to export.');
      return;
    }
    const headers = 'Name,Domain,Resolved Email,Vendor,Status,Confidence,Credits Cost\n';
    const rows = runsList
      .map(
        (r) =>
          `"${r.lead_name || ''}","${r.company_domain || ''}","${r.resolved_email || ''}","${r.resolved_vendor || ''}","${r.deliverability_status || ''}","${r.confidence_score || 0}","${r.total_cost_credits || 0}"`
      )
      .join('\n');
    const blob = new Blob([headers + rows], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `waterfall_enrichment_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success('Exported enriched leads to CSV');
  };

  const handleEnrichSingle = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!leadName.trim() || !domain.trim()) {
      toast.error('Please specify lead name and company domain.');
      return;
    }
    setIsEnriching(true);
    try {
      const res = await fetchWithAuth('/api/elein/waterfall/enrich-single', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          lead_name: leadName.trim(),
          company_domain: domain.trim()
        })
      });
      const data = await res.json();
      if (data.success) {
        toast.success(`Resolved ${data.data.resolved_email} via ${data.data.resolved_vendor}!`);
        mutateRuns();
      } else {
        toast.error(data.detail || 'Enrichment failed.');
      }
    } catch (err: any) {
      toast.error('Error in waterfall cascade: ' + err.message);
    } finally {
      setIsEnriching(false);
    }
  };

  const handleEnrichBatch = async () => {
    const lines = batchInput.split('\n').map(l => l.trim()).filter(Boolean);
    if (lines.length === 0) {
      toast.error('Please enter at least one lead (Name, Domain).');
      return;
    }
    setIsEnriching(true);
    try {
      const leads = lines.map(line => {
        const parts = line.split(',');
        return {
          name: parts[0]?.trim() || 'Executive',
          domain: parts[1]?.trim() || 'company.com'
        };
      });

      const res = await fetchWithAuth('/api/elein/waterfall/enrich-batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ leads })
      });
      const data = await res.json();
      if (data.success) {
        toast.success(`Batch enriched ${data.matched_count} / ${data.total_processed} leads!`);
        mutateRuns();
      } else {
        toast.error(data.detail || 'Batch enrichment failed.');
      }
    } catch (err: any) {
      toast.error('Error running batch: ' + err.message);
    } finally {
      setIsEnriching(false);
    }
  };

  const runs = runsData?.runs || [];
  const configs = configsData?.configs || [];

  return (
    <div 
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm overflow-hidden animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div 
        role="dialog"
        aria-modal="true"
        aria-labelledby="waterfall-studio-title"
        onClick={(e) => e.stopPropagation()}
        className="relative w-full max-w-6xl h-[90dvh] max-h-[90dvh] flex flex-col bg-card border border-border rounded-xl shadow-2xl text-foreground overflow-hidden"
      >
        
        {/* Header Bar */}
        <div className="p-6 border-b border-border bg-card/60 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-primary/10 text-primary border border-primary/20 rounded-xl">
              <Workflow className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 id="waterfall-studio-title" className="text-xl font-bold tracking-tight text-foreground">
                  Multi-Vendor Waterfall Enrichment Engine
                </h2>
                <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-primary/10 text-primary border border-primary/20">
                  Cascade Recovery
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Cascade through Cache &rarr; Apollo &rarr; Hunter &rarr; SMTP 250 Handshakes to recover up to 50% lost TAM with zero credit burn on misses.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close dialog"
            className="p-2 text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Global Telemetry Metric Bar */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 p-4 bg-muted/20 border-b border-border text-sm shrink-0">
          <div className="bg-card border border-border rounded-xl p-3 flex items-center gap-3">
            <TrendingUp className="w-5 h-5 text-primary shrink-0" />
            <div>
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-muted-foreground font-medium">Waterfall Match Rate</span>
                <span className="text-[9px] px-1.5 py-0.2 rounded bg-muted text-muted-foreground border border-border/60">Benchmark</span>
              </div>
              <div className="text-lg font-bold text-foreground">{telemetry.overall_match_rate_pct}%</div>
            </div>
          </div>
          <div className="bg-card border border-border rounded-xl p-3 flex items-center gap-3">
            <Sparkles className="w-5 h-5 text-emerald-600 dark:text-emerald-400 shrink-0" />
            <div>
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-muted-foreground font-medium">TAM Recovery Lift</span>
                <span className="text-[9px] px-1.5 py-0.2 rounded bg-muted text-muted-foreground border border-border/60">Benchmark</span>
              </div>
              <div className="text-lg font-bold text-emerald-600 dark:text-emerald-400">+{telemetry.waterfall_lift_pct}% vs Apollo</div>
            </div>
          </div>
          <div className="bg-card border border-border rounded-xl p-3 flex items-center gap-3">
            <ShieldCheck className="w-5 h-5 text-indigo-600 dark:text-indigo-400 shrink-0" />
            <div>
              <div className="text-xs text-muted-foreground font-medium">Catch-Alls Quarantined</div>
              <div className="text-lg font-bold text-foreground">{telemetry.catchalls_shielded} Shielded</div>
            </div>
          </div>
          <div className="bg-card border border-border rounded-xl p-3 flex items-center gap-3">
            <DollarSign className="w-5 h-5 text-amber-600 dark:text-amber-400 shrink-0" />
            <div>
              <div className="text-xs text-muted-foreground font-medium">Credits Conserved</div>
              <div className="text-lg font-bold text-foreground">{telemetry.estimated_credits_saved} Credits Saved</div>
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div 
          role="tablist"
          aria-label="Waterfall Studio Sections"
          className="flex border-b border-border px-6 bg-card gap-6 text-sm font-medium overflow-x-auto scrollbar-none whitespace-nowrap shrink-0"
        >
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'runner'}
            onClick={() => setActiveTab('runner')}
            className={`py-3 flex items-center gap-2 border-b-2 transition-colors cursor-pointer ${
              activeTab === 'runner'
                ? 'border-primary text-primary font-semibold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Search className="w-4 h-4" />
            Waterfall Lead Runner ({runs.length})
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'chain'}
            onClick={() => setActiveTab('chain')}
            className={`py-3 flex items-center gap-2 border-b-2 transition-colors cursor-pointer ${
              activeTab === 'chain'
                ? 'border-primary text-primary font-semibold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Layers className="w-4 h-4" />
            Cascade Priority Chain &amp; Providers
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'analytics'}
            onClick={() => setActiveTab('analytics')}
            className={`py-3 flex items-center gap-2 border-b-2 transition-colors cursor-pointer ${
              activeTab === 'analytics'
                ? 'border-primary text-primary font-semibold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <ShieldCheck className="w-4 h-4" />
            Zero-Bounce Deliverability Shield
          </button>
        </div>

        {/* Modal Body / Tab Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">

          {/* Proactive Free Tier Banner */}
          {!canWaterfallEnrichment && (
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
                    Waterfall Multi-Vendor Enrichment requires a Pro or Enterprise plan. Upgrade to cascade through cache, Apollo, Hunter, and SMTP handshakes.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => openPaywall({ featureName: "Waterfall Multi-Vendor Enrichment", minTier: "PRO" })}
                className="px-4 py-2 bg-primary text-primary-foreground text-xs font-semibold rounded-lg hover:bg-primary/90 transition-colors whitespace-nowrap"
              >
                Unlock Pro
              </button>
            </div>
          )}

          {/* ════════════════ TAB 1: RUNNER ════════════════ */}
          {activeTab === 'runner' && (
            <div className="space-y-6">
              {/* Enrichment Runner Card */}
              <div className="bg-card border border-border rounded-xl p-5 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-base font-bold text-foreground flex items-center gap-2">
                    <Workflow className="w-5 h-5 text-primary" />
                    Run Waterfall Cascade
                  </h3>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setBatchMode(!batchMode)}
                      className="text-xs text-primary hover:underline font-medium"
                    >
                      {batchMode ? "Switch to Single Mode" : "Switch to Batch CSV Mode"}
                    </button>
                  </div>
                </div>

                {!batchMode ? (
                  <form onSubmit={handleEnrichSingle} className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
                    <div>
                      <label className="text-xs font-medium text-muted-foreground mb-1 block">Prospect Name</label>
                      <input
                        type="text"
                        required
                        value={leadName}
                        onChange={(e) => setLeadName(e.target.value)}
                        placeholder="e.g. Guillermo Rauch"
                        className="w-full bg-background border border-border rounded-lg px-3 py-2 text-foreground text-xs focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
                      />
                    </div>
                    <div>
                      <label className="text-xs font-medium text-muted-foreground mb-1 block">Company Domain</label>
                      <input
                        type="text"
                        required
                        value={domain}
                        onChange={(e) => setDomain(e.target.value)}
                        placeholder="e.g. vercel.com"
                        className="w-full bg-background border border-border rounded-lg px-3 py-2 text-foreground text-xs focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
                      />
                    </div>
                    <div className="flex items-end">
                      <button
                        type="submit"
                        disabled={isEnriching || !canWaterfallEnrichment}
                        className="w-full py-2 bg-primary text-primary-foreground rounded-lg font-semibold flex items-center justify-center gap-2 transition-colors disabled:opacity-50 hover:bg-primary/90"
                      >
                        {isEnriching ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                        Execute Cascade
                      </button>
                    </div>
                  </form>
                ) : (
                  <div className="space-y-3 text-xs">
                    <label className="text-xs font-medium text-muted-foreground block">
                      Paste Leads (Format: Full Name, company.com per line)
                    </label>
                    <textarea
                      rows={4}
                      value={batchInput}
                      onChange={(e) => setBatchInput(e.target.value)}
                      placeholder="Dylan Field, figma.com&#10;Brian Chesky, airbnb.com"
                      className="w-full bg-background border border-border rounded-lg p-3 text-foreground font-mono text-xs focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
                    />
                    {batchInput.trim() && (
                      <div className="flex items-center justify-between text-xs text-muted-foreground px-1">
                        <span>
                          Detected: <strong className="text-foreground">{batchInput.split('\n').filter(l => l.trim()).length}</strong> leads
                        </span>
                        {batchInput.split('\n').filter(l => l.trim()).length > 50 && (
                          <span className="text-amber-600 dark:text-amber-400 font-medium flex items-center gap-1">
                            <AlertTriangle className="w-3.5 h-3.5" />
                            Batch capped at 50 leads per run
                          </span>
                        )}
                      </div>
                    )}
                    <div className="flex justify-end">
                      <button
                        type="button"
                        onClick={handleEnrichBatch}
                        disabled={isEnriching || !canWaterfallEnrichment}
                        className="px-5 py-2 bg-primary text-primary-foreground rounded-lg font-semibold flex items-center gap-2 transition-colors disabled:opacity-50 hover:bg-primary/90"
                      >
                        {isEnriching ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                        Batch Waterfall Enrich
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* Waterfall History Cards */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <h4 className="text-sm font-semibold text-foreground">Enriched Prospect Telemetry</h4>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground font-medium">
                      {runs.length} records
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={handleExportCsv}
                      disabled={runs.length === 0}
                      className="px-2.5 py-1.5 text-xs text-muted-foreground hover:text-foreground bg-muted/60 hover:bg-muted border border-border rounded-lg flex items-center gap-1.5 transition-colors disabled:opacity-50"
                      title="Export Enriched Runs to CSV"
                    >
                      <Download className="w-3.5 h-3.5" />
                      <span>Export CSV</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => mutateRuns()}
                      className="p-1.5 text-muted-foreground hover:text-foreground bg-muted/60 hover:bg-muted border border-border rounded-lg transition-colors"
                      title="Refresh History"
                    >
                      <RefreshCw className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                {isRunsLoading ? (
                  <div className="p-8 text-center text-muted-foreground">Loading waterfall history...</div>
                ) : runs.length === 0 ? (
                  <div className="p-8 text-center border border-dashed border-border rounded-xl space-y-2">
                    <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center mx-auto text-muted-foreground">
                      <Search className="w-5 h-5" />
                    </div>
                    <div className="text-sm font-semibold text-foreground">No Waterfall Runs Yet</div>
                    <p className="text-xs text-muted-foreground max-w-sm mx-auto">
                      Run a single prospect or batch CSV cascade above to discover verified business emails and deliverability status.
                    </p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {runs.map((r) => {
                      const isValid = r.deliverability_status === 'valid';
                      const isCatchAll = r.deliverability_status === 'risky_catchall';

                      return (
                        <div
                          key={r.id}
                          className="bg-card border border-border rounded-xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-4"
                        >
                          <div className="space-y-1">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="font-bold text-foreground text-sm">{r.lead_name}</span>
                              <span className="text-xs text-muted-foreground font-mono">@{r.company_domain}</span>
                              <span
                                className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                                  isValid
                                    ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                                    : isCatchAll
                                    ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20'
                                    : 'bg-destructive/10 text-destructive border border-destructive/20'
                                }`}
                              >
                                {r.deliverability_status} ({r.confidence_score}%)
                              </span>
                            </div>

                            <div className="flex items-center gap-3 text-xs text-muted-foreground flex-wrap">
                              {r.resolved_email ? (
                                <div className="flex items-center gap-1.5">
                                  <span className="font-mono text-primary font-medium">{r.resolved_email}</span>
                                  <button
                                    type="button"
                                    onClick={() => copyToClipboard(r.resolved_email, `email-${r.id}`)}
                                    className="p-1 hover:bg-muted rounded text-muted-foreground hover:text-foreground transition-colors"
                                    title="Copy email to clipboard"
                                  >
                                    {copiedKey === `email-${r.id}` ? (
                                      <Check className="w-3 h-3 text-emerald-500" />
                                    ) : (
                                      <Copy className="w-3 h-3" />
                                    )}
                                  </button>
                                </div>
                              ) : (
                                <span className="font-mono text-muted-foreground">No email found</span>
                              )}
                              <span>•</span>
                              <span>
                                Matched via <strong className="text-foreground uppercase">{r.resolved_vendor}</strong>
                              </span>
                              <span>•</span>
                              <span className="text-amber-600 dark:text-amber-400 font-medium">{r.total_cost_credits} credits</span>
                            </div>
                          </div>

                          {/* Cascade Sequence Trail */}
                          <div className="flex items-center gap-1.5 overflow-x-auto text-[11px]">
                            {(Array.isArray(r.vendors_queried) ? r.vendors_queried : []).map((vq: any, idx: number) => (
                              <div
                                key={idx}
                                className={`px-2 py-1 rounded border flex items-center gap-1 shrink-0 ${
                                  vq.status === 'match'
                                    ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400 font-bold'
                                    : 'bg-muted/50 border-border text-muted-foreground'
                                }`}
                              >
                                <span>{vq.vendor}</span>
                                {vq.status === 'match' ? (
                                  <Check className="w-3 h-3 text-emerald-500" />
                                ) : (
                                  <X className="w-3 h-3 text-muted-foreground" />
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ════════════════ TAB 2: CASCADE CHAIN ════════════════ */}
          {activeTab === 'chain' && (
            <div className="space-y-6">
              <div className="bg-card border border-border rounded-xl p-6 space-y-6">
                <div>
                  <h3 className="text-base font-bold text-foreground flex items-center gap-2">
                    <Layers className="w-5 h-5 text-primary" />
                    Enrichment Cascade Sequence &amp; Priority Order
                  </h3>
                  <p className="text-xs text-muted-foreground mt-1">
                    Ele-in queries free/cached providers first. The moment an email is verified, downstream queries halt immediately to save credits.
                  </p>
                </div>

                <div className="space-y-3">
                  {configs.map((c, i) => (
                    <div
                      key={c.id || i}
                      className="p-4 rounded-xl bg-muted/30 border border-border flex items-center justify-between"
                    >
                      <div className="flex items-center gap-4">
                        <div className="w-7 h-7 rounded-lg bg-primary/10 text-primary font-bold text-xs flex items-center justify-center border border-primary/20">
                          {c.priority_order}
                        </div>
                        <div>
                          <div className="text-sm font-bold text-foreground">{c.vendor_display_name}</div>
                          <div className="text-xs text-muted-foreground font-mono">provider: {c.vendor_slug}</div>
                        </div>
                      </div>

                      <div className="flex items-center gap-4 text-xs">
                        <span className="text-amber-600 dark:text-amber-400 font-semibold">
                          {c.cost_per_lookup_credits} credits / hit
                        </span>
                        <span className="px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 font-medium">
                          Active in Chain
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* ════════════════ TAB 3: DELIVERABILITY SHIELD ════════════════ */}
          {activeTab === 'analytics' && (
            <div className="space-y-6">
              <div className="bg-card border border-border rounded-xl p-6 space-y-6">
                <div>
                  <h3 className="text-base font-bold text-foreground flex items-center gap-2">
                    <ShieldCheck className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
                    Zero-Bounce Deliverability &amp; Catch-All Shield
                  </h3>
                  <p className="text-xs text-muted-foreground mt-1">
                    Protects your domain sending reputation by filtering spam traps and toxic catch-all servers before email dispatch.
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
                  <div className="p-4 rounded-xl bg-emerald-500/5 border border-emerald-500/20 space-y-1">
                    <div className="text-emerald-600 dark:text-emerald-400 font-bold text-sm">Direct SMTP 250 Handshake</div>
                    <p className="text-muted-foreground">
                      Pings MX mail exchangers directly to verify mailbox existence without sending a message.
                    </p>
                  </div>

                  <div className="p-4 rounded-xl bg-amber-500/5 border border-amber-500/20 space-y-1">
                    <div className="text-amber-600 dark:text-amber-400 font-bold text-sm">Dynamic Catch-All Detection</div>
                    <p className="text-muted-foreground">
                      Tests random UUID mailboxes. If server accepts fake mailboxes, email is flagged as risky catch-all.
                    </p>
                  </div>

                  <div className="p-4 rounded-xl bg-primary/5 border border-primary/20 space-y-1">
                    <div className="text-primary font-bold text-sm">Credit Burn Prevention</div>
                    <p className="text-muted-foreground">
                      Halts multi-vendor cascades instantly on match. Saves credits by eliminating redundant queries.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}

        </div>

      </div>
    </div>
  );
}
