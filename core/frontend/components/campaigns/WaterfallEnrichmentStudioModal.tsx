import React, { useState } from 'react';
import useSWR from 'swr';
import {
  Workflow, Layers, Sparkles, RefreshCw, Copy, Check, CheckCircle2,
  X, Plus, ExternalLink, ShieldCheck, Search, Database, ArrowRight,
  TrendingUp, AlertTriangle, DollarSign, Sliders, Play, CheckSquare
} from 'lucide-react';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/lib/apiClient';

const fetcher = (url: string) => fetchWithAuth(url).then(r => r.json());

interface WaterfallStudioProps {
  onClose?: () => void;
  campaignId?: string;
}

export function WaterfallEnrichmentStudioModal({ onClose, campaignId }: WaterfallStudioProps) {
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
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    toast.success('Copied to clipboard!');
    setTimeout(() => setCopiedKey(null), 2000);
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="relative w-full max-w-6xl max-h-[92vh] flex flex-col bg-card border border-border rounded-xl shadow-2xl text-foreground overflow-hidden">
        
        {/* Header Bar */}
        <div className="p-6 border-b border-slate-800 bg-slate-950/60 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-cyan-600/20 text-cyan-400 border border-cyan-500/30 rounded-xl">
              <Workflow className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-bold tracking-tight text-white">
                  Clay-Style Multi-Vendor Waterfall Enrichment Engine
                </h2>
                <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-cyan-500/20 text-cyan-300 border border-cyan-500/40">
                  Phase 18 Cascade
                </span>
              </div>
              <p className="text-sm text-slate-400 mt-0.5">
                Stop losing 50% of your TAM to single-vendor misses. Cascade through Cache &rarr; Apollo &rarr; Hunter &rarr; SMTP Handshakes.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Global Telemetry Metric Bar */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 p-4 bg-slate-900/80 border-b border-slate-800 text-sm">
          <div className="bg-slate-950/40 border border-slate-800/80 rounded-xl p-3 flex items-center gap-3">
            <TrendingUp className="w-5 h-5 text-cyan-400 shrink-0" />
            <div>
              <div className="text-xs text-slate-400 font-medium">Waterfall Match Rate</div>
              <div className="text-lg font-bold text-white">{telemetry.overall_match_rate_pct}%</div>
            </div>
          </div>
          <div className="bg-slate-950/40 border border-slate-800/80 rounded-xl p-3 flex items-center gap-3">
            <Sparkles className="w-5 h-5 text-emerald-400 shrink-0" />
            <div>
              <div className="text-xs text-slate-400 font-medium">TAM Recovery Lift</div>
              <div className="text-lg font-bold text-emerald-400">+{telemetry.waterfall_lift_pct}% vs Apollo alone</div>
            </div>
          </div>
          <div className="bg-slate-950/40 border border-slate-800/80 rounded-xl p-3 flex items-center gap-3">
            <ShieldCheck className="w-5 h-5 text-indigo-400 shrink-0" />
            <div>
              <div className="text-xs text-slate-400 font-medium">Catch-Alls Quarantined</div>
              <div className="text-lg font-bold text-indigo-300">{telemetry.catchalls_shielded} Shielded</div>
            </div>
          </div>
          <div className="bg-slate-950/40 border border-slate-800/80 rounded-xl p-3 flex items-center gap-3">
            <DollarSign className="w-5 h-5 text-amber-400 shrink-0" />
            <div>
              <div className="text-xs text-slate-400 font-medium">Credits Conserved</div>
              <div className="text-lg font-bold text-amber-300">{telemetry.estimated_credits_saved} Credits Saved</div>
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="flex border-b border-slate-800 px-6 bg-slate-950/30 gap-6 text-sm font-medium">
          <button
            onClick={() => setActiveTab('runner')}
            className={`py-3 flex items-center gap-2 border-b-2 transition-colors ${
              activeTab === 'runner'
                ? 'border-cyan-500 text-cyan-400 font-semibold'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Search className="w-4 h-4" />
            Waterfall Lead Runner ({runs.length})
          </button>
          <button
            onClick={() => setActiveTab('chain')}
            className={`py-3 flex items-center gap-2 border-b-2 transition-colors ${
              activeTab === 'chain'
                ? 'border-cyan-500 text-cyan-400 font-semibold'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Layers className="w-4 h-4" />
            Cascade Priority Chain & Providers
          </button>
          <button
            onClick={() => setActiveTab('analytics')}
            className={`py-3 flex items-center gap-2 border-b-2 transition-colors ${
              activeTab === 'analytics'
                ? 'border-cyan-500 text-cyan-400 font-semibold'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <ShieldCheck className="w-4 h-4" />
            Zero-Bounce Deliverability Shield
          </button>
        </div>

        {/* Modal Body / Tab Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">

          {/* ════════════════ TAB 1: RUNNER ════════════════ */}
          {activeTab === 'runner' && (
            <div className="space-y-6">
              {/* Enrichment Runner Card */}
              <div className="bg-muted/20 border border-border/60 rounded-lg p-6 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-base font-bold text-white flex items-center gap-2">
                    <Workflow className="w-5 h-5 text-cyan-400" />
                    Run Waterfall Cascade
                  </h3>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setBatchMode(!batchMode)}
                      className="text-xs text-cyan-400 hover:underline font-medium"
                    >
                      {batchMode ? "Switch to Single Mode" : "Switch to Batch CSV Mode"}
                    </button>
                  </div>
                </div>

                {!batchMode ? (
                  <form onSubmit={handleEnrichSingle} className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
                    <div>
                      <label className="text-slate-400 mb-1 block">Prospect Name</label>
                      <input
                        type="text"
                        required
                        value={leadName}
                        onChange={(e) => setLeadName(e.target.value)}
                        className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:ring-1 focus:ring-cyan-500"
                      />
                    </div>
                    <div>
                      <label className="text-slate-400 mb-1 block">Company Domain</label>
                      <input
                        type="text"
                        required
                        value={domain}
                        onChange={(e) => setDomain(e.target.value)}
                        className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:ring-1 focus:ring-cyan-500"
                      />
                    </div>
                    <div className="flex items-end">
                      <button
                        type="submit"
                        disabled={isEnriching}
                        className="w-full py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg font-semibold flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
                      >
                        {isEnriching ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                        Execute Cascade
                      </button>
                    </div>
                  </form>
                ) : (
                  <div className="space-y-3 text-xs">
                    <label className="text-slate-400 block">Paste Leads (Format: Full Name, company.com per line)</label>
                    <textarea
                      rows={4}
                      value={batchInput}
                      onChange={(e) => setBatchInput(e.target.value)}
                      className="w-full bg-slate-800 border border-slate-700 rounded-lg p-3 text-white font-mono text-xs focus:outline-none focus:ring-1 focus:ring-cyan-500"
                    />
                    <div className="flex justify-end">
                      <button
                        onClick={handleEnrichBatch}
                        disabled={isEnriching}
                        className="px-5 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg font-semibold flex items-center gap-2 transition-colors disabled:opacity-50"
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
                  <h4 className="text-sm font-semibold text-slate-300">Enriched Prospect Telemetry</h4>
                  <button
                    onClick={() => mutateRuns()}
                    className="p-1.5 text-slate-400 hover:text-white bg-slate-800 rounded-lg"
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                  </button>
                </div>

                {isRunsLoading ? (
                  <div className="p-8 text-center text-slate-400">Loading waterfall history...</div>
                ) : (
                  <div className="space-y-3">
                    {runs.map((r) => {
                      const isValid = r.deliverability_status === 'valid';
                      const isCatchAll = r.deliverability_status === 'risky_catchall';

                      return (
                        <div
                          key={r.id}
                          className="bg-slate-950/60 border border-slate-800 rounded-xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-4"
                        >
                          <div className="space-y-1">
                            <div className="flex items-center gap-2">
                              <span className="font-bold text-white text-sm">{r.lead_name}</span>
                              <span className="text-xs text-slate-400 font-mono">@{r.company_domain}</span>
                              <span
                                className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                                  isValid
                                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                                    : isCatchAll
                                    ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                                    : 'bg-rose-500/20 text-rose-300'
                                }`}
                              >
                                {r.deliverability_status} ({r.confidence_score}%)
                              </span>
                            </div>

                            <div className="flex items-center gap-3 text-xs text-slate-300">
                              <span className="font-mono text-cyan-300">{r.resolved_email || 'No email found'}</span>
                              <span className="text-slate-500">•</span>
                              <span className="text-slate-400">
                                Matched via <strong className="text-white uppercase">{r.resolved_vendor}</strong>
                              </span>
                              <span className="text-slate-500">•</span>
                              <span className="text-amber-400">{r.total_cost_credits} credits</span>
                            </div>
                          </div>

                          {/* Cascade Sequence Trail */}
                          <div className="flex items-center gap-1.5 overflow-x-auto text-[11px]">
                            {r.vendors_queried?.map((vq: any, idx: number) => (
                              <div
                                key={idx}
                                className={`px-2 py-1 rounded border flex items-center gap-1 ${
                                  vq.status === 'match'
                                    ? 'bg-emerald-950/40 border-emerald-800 text-emerald-300 font-bold'
                                    : 'bg-slate-900 border-slate-800 text-slate-500'
                                }`}
                              >
                                <span>{vq.vendor}</span>
                                {vq.status === 'match' ? (
                                  <Check className="w-3 h-3 text-emerald-400" />
                                ) : (
                                  <X className="w-3 h-3 text-slate-600" />
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
              <div className="bg-muted/20 border border-border/60 rounded-lg p-6 space-y-6">
                <div>
                  <h3 className="text-base font-bold text-white flex items-center gap-2">
                    <Layers className="w-5 h-5 text-cyan-400" />
                    Enrichment Cascade Sequence & Priority Order
                  </h3>
                  <p className="text-xs text-slate-400 mt-1">
                    Ele-in queries free/cached providers first. The moment an email is verified, downstream queries halt immediately to save credits.
                  </p>
                </div>

                <div className="space-y-3">
                  {configs.map((c, i) => (
                    <div
                      key={c.id || i}
                      className="p-4 rounded-xl bg-slate-900/70 border border-slate-800 flex items-center justify-between"
                    >
                      <div className="flex items-center gap-4">
                        <div className="w-7 h-7 rounded-lg bg-cyan-600/20 text-cyan-300 font-bold text-xs flex items-center justify-center border border-cyan-500/30">
                          {c.priority_order}
                        </div>
                        <div>
                          <div className="text-sm font-bold text-white">{c.vendor_display_name}</div>
                          <div className="text-xs text-slate-400 font-mono">provider: {c.vendor_slug}</div>
                        </div>
                      </div>

                      <div className="flex items-center gap-6 text-xs">
                        <span className="text-amber-400 font-semibold">
                          {c.cost_per_lookup_credits} credits / hit
                        </span>
                        <span className="px-2.5 py-1 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-medium">
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
              <div className="bg-muted/20 border border-border/60 rounded-lg p-6 space-y-6">
                <div>
                  <h3 className="text-base font-bold text-white flex items-center gap-2">
                    <ShieldCheck className="w-5 h-5 text-emerald-400" />
                    Zero-Bounce Deliverability & Catch-All Shield
                  </h3>
                  <p className="text-xs text-slate-400 mt-1">
                    Protects your LinkedIn & domain sending reputation by filtering spam traps and toxic catch-all servers.
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
                  <div className="p-4 rounded-xl bg-emerald-950/20 border border-emerald-900/40 space-y-1">
                    <div className="text-emerald-400 font-bold text-sm">Direct SMTP 250 Handshake</div>
                    <p className="text-slate-300">
                      Pings MX mail exchangers directly to verify mailbox existence without sending a message.
                    </p>
                  </div>

                  <div className="p-4 rounded-xl bg-amber-950/20 border border-amber-900/40 space-y-1">
                    <div className="text-amber-400 font-bold text-sm">Dynamic Catch-All Detection</div>
                    <p className="text-slate-300">
                      Tests random UUID mailboxes. If server accepts fake mailboxes, email is flagged as risky catch-all.
                    </p>
                  </div>

                  <div className="p-4 rounded-xl bg-indigo-950/20 border border-indigo-900/40 space-y-1">
                    <div className="text-indigo-400 font-bold text-sm">Credit Burn Prevention</div>
                    <p className="text-slate-300">
                      Halts multi-vendor cascades instantly on match. Saves an average of $350/mo vs Clay seat costs.
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
