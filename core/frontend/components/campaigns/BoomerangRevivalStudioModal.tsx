import React, { useState, useEffect } from 'react';
import useSWR from 'swr';
import {
  Repeat, Users, RotateCcw, RefreshCw, Copy, Check,
  ArrowRight, ShieldAlert, Rocket, X, Plus, Award, DollarSign, GitBranch, TrendingUp
} from 'lucide-react';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/lib/apiClient';
import { usePaywall } from '@/contexts/PaywallContext';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

const fetcher = (url: string) => fetchWithAuth(url).then(r => r.json());

interface BoomerangRevivalStudioProps {
  onClose?: () => void;
  campaignId?: string;
}

export function BoomerangRevivalStudioModal({ onClose, campaignId }: BoomerangRevivalStudioProps) {
  const { openPaywall } = usePaywall();
  const [activeTab, setActiveTab] = useState<'boomerang' | 'warm_intros' | 'revivals'>('boomerang');
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [enrollingId, setEnrollingId] = useState<string | null>(null);

  // ── Tab 1: Job-Change Boomerang State ──
  const [relFilter, setRelFilter] = useState<string>('all');
  const [addJobChangeOpen, setAddJobChangeOpen] = useState(false);
  const [jcName, setJcName] = useState('');
  const [jcPrevCompany, setJcPrevCompany] = useState('');
  const [jcPrevTitle, setJcPrevTitle] = useState('');
  const [jcNewCompany, setJcNewCompany] = useState('');
  const [jcNewTitle, setJcNewTitle] = useState('');
  const [jcRelType, setJcRelType] = useState('past_customer');
  const [jcDays, setJcDays] = useState(21);
  const [isSavingJc, setIsSavingJc] = useState(false);

  // ── Tab 2: Warm Intro Graph State ──
  const [scriptMode, setScriptMode] = useState<Record<string, 'connector' | 'direct'>>({});

  // ── Tab 3: Closed-Lost Revival State ──
  const [reasonFilter, setReasonFilter] = useState<string>('all');
  const [addRevivalOpen, setAddRevivalOpen] = useState(false);
  const [revName, setRevName] = useState('');
  const [revCompany, setRevCompany] = useState('');
  const [revTitle, setRevTitle] = useState('');
  const [revReason, setRevReason] = useState('missing_feature');
  const [revDays, setRevDays] = useState(120);
  const [revValue, setRevValue] = useState(35000);
  const [revTrigger, setRevTrigger] = useState('Shipped Autonomous ABM Multithreading & Buying Committee Studio');
  const [isSavingRev, setIsSavingRev] = useState(false);

  // Keyboard navigation & Escape dismiss
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (addJobChangeOpen) {
          setAddJobChangeOpen(false);
        } else if (addRevivalOpen) {
          setAddRevivalOpen(false);
        } else if (onClose) {
          onClose();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [addJobChangeOpen, addRevivalOpen, onClose]);

  const { data: jcData, mutate: mutateJc } = useSWR<{ success: boolean; job_changes: any[] }>(
    `/api/elein/boomerang/job-changes${relFilter !== 'all' ? `?relationship=${relFilter}` : ''}`,
    fetcher,
    { revalidateOnFocus: false }
  );

  const { data: wpData, mutate: mutateWp } = useSWR<{ success: boolean; warm_intros: any[] }>(
    '/api/elein/boomerang/warm-intros',
    fetcher,
    { revalidateOnFocus: false }
  );

  const { data: revData, mutate: mutateRev } = useSWR<{ success: boolean; revivals: any[] }>(
    `/api/elein/boomerang/revivals${reasonFilter !== 'all' ? `?reason=${reasonFilter}` : ''}`,
    fetcher,
    { revalidateOnFocus: false }
  );

  const jobChanges = jcData?.job_changes || [];
  const warmIntros = wpData?.warm_intros || [];
  const revivals = revData?.revivals || [];

  const totalRecoverablePipeline = revivals.reduce((sum, r) => sum + (Number(r.original_deal_value) || 0), 0);

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    toast.success('Copied to clipboard!');
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleEnroll = async (itemId: string, itemType: 'job_change' | 'warm_intro' | 'revival', label: string) => {
    setEnrollingId(itemId);
    try {
      const res = await fetchWithAuth('/api/elein/boomerang/enroll', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          item_id: itemId,
          item_type: itemType,
          campaign_id: campaignId || null
        })
      });
      if (res.status === 402) {
        openPaywall('Champion Job-Change Tracker & Boomerang Deal Revival Engine');
        return;
      }
      const data = await res.json();
      if (data.success) {
        toast.success(`Launched sequence for ${label}!`);
        mutateJc();
        mutateWp();
        mutateRev();
      } else {
        toast.error(data.detail || 'Enrollment failed.');
      }
    } catch (e: any) {
      toast.error('Error enrolling: ' + e.message);
    } finally {
      setEnrollingId(null);
    }
  };

  const handleCreateJobChange = async () => {
    if (!jcName.trim() || !jcPrevCompany.trim() || !jcNewCompany.trim()) {
      toast.error('Please fill in Executive Name, Previous Company, and New Company.');
      return;
    }
    setIsSavingJc(true);
    try {
      const res = await fetchWithAuth('/api/elein/boomerang/job-changes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prospect_name: jcName.trim(),
          previous_company: jcPrevCompany.trim(),
          previous_title: jcPrevTitle.trim() || 'Director of Sales',
          new_company: jcNewCompany.trim(),
          new_title: jcNewTitle.trim() || 'VP of Revenue',
          relationship_type: jcRelType,
          days_in_new_role: jcDays
        })
      });
      if (res.status === 402) {
        openPaywall('Champion Job-Change Tracker & Boomerang Deal Revival Engine');
        return;
      }
      const data = await res.json();
      if (data.success) {
        toast.success(`Tracked job change for ${jcName}! Buying Window Score: ${data.data.buying_window_score}/100`);
        setAddJobChangeOpen(false);
        setJcName('');
        setJcPrevCompany('');
        setJcNewCompany('');
        mutateJc();
      } else {
        toast.error(data.detail || 'Failed to track job change.');
      }
    } catch (e: any) {
      toast.error('Error: ' + e.message);
    } finally {
      setIsSavingJc(false);
    }
  };

  const handleCreateRevival = async () => {
    if (!revName.trim() || !revCompany.trim()) {
      toast.error('Please specify Prospect Name and Company Name.');
      return;
    }
    setIsSavingRev(true);
    try {
      const res = await fetchWithAuth('/api/elein/boomerang/revivals', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prospect_name: revName.trim(),
          company_name: revCompany.trim(),
          title: revTitle.trim() || 'VP of Sales',
          lost_reason: revReason,
          days_since_lost: revDays,
          original_deal_value: revValue,
          revival_trigger: revTrigger
        })
      });
      if (res.status === 402) {
        openPaywall('Champion Job-Change Tracker & Boomerang Deal Revival Engine');
        return;
      }
      const data = await res.json();
      if (res.ok && data.success) {
        toast.success(`Deal Resurrection playbook created for ${revCompany}!`);
        setAddRevivalOpen(false);
        setRevName('');
        setRevCompany('');
        mutateRev();
      } else {
        toast.error(data.detail || 'Blocked by Anti-Pestering Guard.');
      }
    } catch (e: any) {
      toast.error('Error: ' + e.message);
    } finally {
      setIsSavingRev(false);
    }
  };

  const getRelBadge = (rel: string) => {
    switch (rel) {
      case 'past_customer':
        return <span className="px-2 py-0.5 rounded-md text-[11px] font-medium bg-muted/40 text-foreground border border-border">Past Customer</span>;
      case 'former_champion':
        return <span className="px-2 py-0.5 rounded-md text-[11px] font-medium bg-muted/40 text-foreground border border-border">Former Champion</span>;
      case 'power_user':
        return <span className="px-2 py-0.5 rounded-md text-[11px] font-medium bg-muted/40 text-foreground border border-border">Power User</span>;
      default:
        return <span className="px-2 py-0.5 rounded-md text-[11px] font-medium bg-muted/40 text-foreground border border-border">Closed-Lost Contact</span>;
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="boomerang-modal-title"
        className="relative w-full max-w-6xl max-h-[90vh] max-h-[90dvh] bg-card border border-border rounded-xl shadow-2xl flex flex-col overflow-hidden text-foreground my-auto"
        onClick={(e) => e.stopPropagation()}
      >
        
        {/* Top Header */}
        <div className="px-6 py-4 border-b border-border bg-background flex items-center justify-between">
          <div>
            <h2 id="boomerang-modal-title" className="text-lg sm:text-xl font-bold tracking-tight text-foreground">
              Champion Boomerang, Warm Intro Graph & Deal Revival Studio
            </h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Convert past champions in their first 90 days at a new company, unlock mutual alumni warm intros, and resurrect closed-lost pipeline.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                mutateJc();
                mutateWp();
                mutateRev();
                toast.success('Boomerang & Revival telemetry synced!');
              }}
              aria-label="Sync telemetry"
              className="p-2 rounded-lg bg-muted/60 hover:bg-muted text-muted-foreground hover:text-foreground border border-border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
            {onClose && (
              <button
                onClick={onClose}
                aria-label="Close studio"
                className="p-2 rounded-lg bg-muted/60 hover:bg-muted text-muted-foreground hover:text-foreground border border-border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>

        {/* KPI Ribbon */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 px-4 sm:px-6 py-3 border-b border-border bg-muted/60 text-xs">
          <div className="bg-background border border-border rounded-lg p-2.5 flex items-center gap-3">
            <div className="p-2 rounded-lg bg-muted/60 border border-border text-muted-foreground">
              <Award className="w-4 h-4" />
            </div>
            <div>
              <div className="text-xs text-muted-foreground">90-Day Boomerangs</div>
              <div className="text-sm font-semibold text-foreground">{jobChanges.length} Active Champions</div>
            </div>
          </div>

          <div className="bg-background border border-border rounded-lg p-2.5 flex items-center gap-3">
            <div className="p-2 rounded-lg bg-muted/60 border border-border text-muted-foreground">
              <GitBranch className="w-4 h-4" />
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Warm Intro Bridges</div>
              <div className="text-sm font-semibold text-foreground">{warmIntros.length} Verified Paths</div>
            </div>
          </div>

          {/* Leading Financial Metric */}
          <div className="bg-primary/10 border border-primary/20 rounded-lg p-2.5 flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary/20 text-primary">
              <DollarSign className="w-4 h-4" />
            </div>
            <div>
              <div className="text-xs text-primary/80 font-medium">Revivable Pipeline</div>
              <div className="text-sm font-bold text-primary">${totalRecoverablePipeline.toLocaleString()} ACV</div>
            </div>
          </div>

          <div className="bg-background border border-border rounded-lg p-2.5 flex items-center gap-3">
            <div className="p-2 rounded-lg bg-muted/60 border border-border text-muted-foreground">
              <TrendingUp className="w-4 h-4" />
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Alumni Reply Lift</div>
              <div className="text-sm font-semibold text-foreground">4.8x vs. Cold Outbound</div>
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div
          role="tablist"
          aria-label="Boomerang Revival Sections"
          className="flex border-b border-border bg-background px-6 overflow-x-auto scrollbar-none whitespace-nowrap shrink-0"
        >
          <button
            role="tab"
            aria-selected={activeTab === 'boomerang'}
            onClick={() => setActiveTab('boomerang')}
            className={`py-3 px-4 text-xs font-medium flex items-center gap-2 border-b-2 transition-all shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
              activeTab === 'boomerang'
                ? 'border-primary text-primary font-semibold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Repeat className="w-4 h-4" />
            Champion Job-Change Boomerang ({jobChanges.length})
          </button>

          <button
            role="tab"
            aria-selected={activeTab === 'warm_intros'}
            onClick={() => setActiveTab('warm_intros')}
            className={`py-3 px-4 text-xs font-medium flex items-center gap-2 border-b-2 transition-all shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
              activeTab === 'warm_intros'
                ? 'border-primary text-primary font-semibold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <GitBranch className="w-4 h-4" />
            Mutual Connection & Alumni Graph ({warmIntros.length})
          </button>

          <button
            role="tab"
            aria-selected={activeTab === 'revivals'}
            onClick={() => setActiveTab('revivals')}
            className={`py-3 px-4 text-xs font-medium flex items-center gap-2 border-b-2 transition-all shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
              activeTab === 'revivals'
                ? 'border-primary text-primary font-semibold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <RotateCcw className="w-4 h-4" />
            Closed-Lost Deal Resurrection ({revivals.length})
          </button>
        </div>

        {/* Main Content Area */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">

          {/* TAB 1: CHAMPION JOB-CHANGE BOOMERANG */}
          {activeTab === 'boomerang' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-xs text-muted-foreground">Relationship Filter:</span>
                  <Select
                    value={relFilter}
                    onValueChange={(val) => setRelFilter(val)}
                  >
                    <SelectTrigger size="sm" className="w-[180px] bg-background border-border text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Past Relationships</SelectItem>
                      <SelectItem value="past_customer">Past Customers</SelectItem>
                      <SelectItem value="former_champion">Former Champions</SelectItem>
                      <SelectItem value="power_user">Power Users</SelectItem>
                      <SelectItem value="closed_lost_contact">Closed-Lost Contacts</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <button
                  onClick={() => setAddJobChangeOpen(true)}
                  className="px-3.5 py-1.5 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground font-medium text-xs flex items-center gap-1.5 transition-colors"
                >
                  <Plus className="w-4 h-4" />
                  Track Champion Job Change
                </button>
              </div>

              <div className="space-y-4">
                {jobChanges.map((jc) => (
                  <div key={jc.id} className="p-5 rounded-lg bg-card border border-border space-y-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="flex items-center gap-3">
                        <div className="font-semibold text-foreground text-sm">{jc.prospect_name}</div>
                        {getRelBadge(jc.relationship_type)}
                        {jc.is_internal_promotion && (
                          <span className="px-2 py-0.5 rounded text-xs font-medium bg-muted/60 text-muted-foreground border border-border">
                            Internal Promotion Guard Active
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-2">
                        <span className="px-2.5 py-1 rounded-md text-xs font-medium bg-muted/60 text-foreground border border-border">
                          {jc.buying_window_score}/100 Buying Window (Day {jc.days_in_new_role})
                        </span>
                      </div>
                    </div>

                    {/* Visual Job Move Banner */}
                    <div className="flex flex-col sm:flex-row items-center gap-3 p-3 rounded-lg bg-muted/60 border border-border text-xs">
                      <div className="flex-1 w-full sm:w-auto">
                        <div className="text-xs uppercase tracking-wider text-muted-foreground">Previous Role</div>
                        <div className="font-medium text-muted-foreground mt-0.5">{jc.previous_title} @ <span className="text-foreground">{jc.previous_company}</span></div>
                      </div>
                      <ArrowRight className="w-4 h-4 text-muted-foreground shrink-0 rotate-90 sm:rotate-0 transition-transform" />
                      <div className="flex-1 w-full sm:w-auto">
                        <div className="text-xs uppercase tracking-wider text-muted-foreground font-medium">New Executive Role (First 90 Days)</div>
                        <div className="font-semibold text-foreground mt-0.5">{jc.new_title} @ <span className="text-foreground">{jc.new_company}</span></div>
                      </div>
                    </div>

                    {/* Playbook Message */}
                    <div className="space-y-1.5">
                      <div className="text-xs font-medium text-muted-foreground">Auto-Synthesized Boomerang Playbook Message:</div>
                      <div className="p-3.5 rounded-lg bg-background border border-border text-xs text-foreground whitespace-pre-line font-sans leading-relaxed">
                        {jc.playbook_message}
                      </div>
                    </div>

                    <div className="flex items-center justify-end gap-2 pt-1">
                      <button
                        onClick={() => copyToClipboard(jc.playbook_message, jc.id)}
                        aria-label="Copy playbook message"
                        className="px-3 py-1.5 rounded-lg bg-muted/60 hover:bg-muted border border-border text-foreground text-xs font-medium flex items-center gap-1.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        {copiedId === jc.id ? <Check className="w-3.5 h-3.5 text-foreground" /> : <Copy className="w-3.5 h-3.5" />}
                        Copy Playbook
                      </button>

                      <button
                        onClick={() => handleEnroll(jc.id, 'job_change', jc.prospect_name)}
                        disabled={enrollingId === jc.id || jc.status === 'enrolled'}
                        className={`px-3.5 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                          jc.status === 'enrolled'
                            ? 'bg-muted text-muted-foreground border border-border cursor-not-allowed opacity-60'
                            : 'bg-primary hover:bg-primary/90 text-primary-foreground active:scale-[0.98]'
                        }`}
                      >
                        {enrollingId === jc.id ? (
                          <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <Rocket className="w-3.5 h-3.5" />
                        )}
                        {jc.status === 'enrolled' ? 'Enrolled in Sequence' : 'Launch Boomerang Sequence'}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* TAB 2: MUTUAL CONNECTION & ALUMNI REFERRAL GRAPH */}
          {activeTab === 'warm_intros' && (
            <div className="space-y-4">
              {warmIntros.map((wp) => {
                const mode = scriptMode[wp.id] || 'direct';
                const activeDraft = mode === 'connector' ? wp.intro_request_draft : wp.direct_bridge_draft;

                return (
                  <div key={wp.id} className="p-5 rounded-lg bg-card border border-border space-y-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-foreground text-sm">{wp.target_prospect_name}</span>
                        <span className="text-xs text-muted-foreground">({wp.target_title} @ {wp.target_company})</span>
                      </div>

                      <span className="px-2.5 py-1 rounded-md text-xs font-medium bg-muted/60 text-foreground border border-border">
                        {wp.warmth_score}/100 Warmth Score
                      </span>
                    </div>

                    {/* Visual Referral Bridge */}
                    <div className="flex flex-col sm:flex-row items-center gap-3 p-3.5 rounded-lg bg-muted/60 border border-border text-xs">
                      <div className="px-3 py-1.5 rounded-md bg-background border border-border text-foreground font-medium w-full sm:w-auto text-center">
                        You (Sender)
                      </div>
                      <ArrowRight className="w-4 h-4 text-muted-foreground shrink-0 rotate-90 sm:rotate-0 transition-transform" />
                      <div className="flex-1 p-2 rounded-md bg-background border border-border w-full sm:w-auto">
                        <div className="font-semibold text-foreground">{wp.connector_name} ({wp.connector_role})</div>
                        <div className="text-xs text-muted-foreground mt-0.5">{wp.overlap_context}</div>
                      </div>
                      <ArrowRight className="w-4 h-4 text-muted-foreground shrink-0 rotate-90 sm:rotate-0 transition-transform" />
                      <div className="px-3 py-1.5 rounded-md bg-background border border-border text-foreground font-semibold w-full sm:w-auto text-center">
                        {wp.target_prospect_name} @ {wp.target_company}
                      </div>
                    </div>

                    {/* Dual Script Selector */}
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      <div className="flex bg-muted/60 p-1 rounded-lg border border-border text-xs overflow-x-auto scrollbar-none whitespace-nowrap">
                        <button
                          onClick={() => setScriptMode({ ...scriptMode, [wp.id]: 'direct' })}
                          className={`px-3 py-1 rounded-md font-medium transition-all ${
                            mode === 'direct' ? 'bg-background text-foreground border border-border' : 'text-muted-foreground hover:text-foreground'
                          }`}
                        >
                          Direct Shared-Alumni Hook (To {wp.target_prospect_name.split(' ')[0]})
                        </button>
                        <button
                          onClick={() => setScriptMode({ ...scriptMode, [wp.id]: 'connector' })}
                          className={`px-3 py-1 rounded-md font-medium transition-all ${
                            mode === 'connector' ? 'bg-background text-foreground border border-border' : 'text-muted-foreground hover:text-foreground'
                          }`}
                        >
                          Ask Connector for Intro (To {wp.connector_name.split(' ')[0]})
                        </button>
                      </div>

                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => copyToClipboard(activeDraft, wp.id)}
                          aria-label="Copy intro script"
                          className="px-3 py-1.5 rounded-lg bg-muted/60 hover:bg-muted border border-border text-foreground text-xs font-medium flex items-center gap-1.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        >
                          {copiedId === wp.id ? <Check className="w-3.5 h-3.5 text-foreground" /> : <Copy className="w-3.5 h-3.5" />}
                          Copy Script
                        </button>
                        <button
                          onClick={() => handleEnroll(wp.id, 'warm_intro', wp.target_prospect_name)}
                          disabled={enrollingId === wp.id || wp.status === 'enrolled'}
                          className={`px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                            wp.status === 'enrolled'
                              ? 'bg-muted text-muted-foreground border border-border cursor-not-allowed opacity-60'
                              : 'bg-primary hover:bg-primary/90 text-primary-foreground active:scale-[0.98]'
                          }`}
                        >
                          {enrollingId === wp.id ? (
                            <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <Rocket className="w-3.5 h-3.5" />
                          )}
                          {wp.status === 'enrolled' ? 'Enrolled' : 'Launch Warm Intro'}
                        </button>
                      </div>
                    </div>

                    <div className="p-3.5 rounded-lg bg-background border border-border text-xs text-foreground whitespace-pre-line font-sans leading-relaxed">
                      {activeDraft}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* TAB 3: CLOSED-LOST DEAL RESURRECTION ENGINE */}
          {activeTab === 'revivals' && (
            <div className="space-y-4">
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <span className="text-xs text-muted-foreground font-medium">Filter by Lost Reason:</span>
                  <Select
                    value={reasonFilter}
                    onValueChange={(val) => setReasonFilter(val)}
                  >
                    <SelectTrigger size="sm" className="w-[220px] bg-background border-border text-xs focus-visible:ring-2 focus-visible:ring-ring">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Lost Reasons</SelectItem>
                      <SelectItem value="missing_feature">Missing Feature (Now Shipped)</SelectItem>
                      <SelectItem value="budget_freeze">Budget Freeze (New Fiscal Window)</SelectItem>
                      <SelectItem value="competitor_chosen">Went With Competitor (6M Renewal)</SelectItem>
                      <SelectItem value="bad_timing">Bad Timing / Competing Priorities</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <button
                  onClick={() => setAddRevivalOpen(true)}
                  className="px-3.5 py-1.5 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground font-medium text-xs flex items-center gap-1.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:scale-[0.98]"
                >
                  <Plus className="w-4 h-4" />
                  Add Closed-Lost Deal to Revive
                </button>
              </div>

              <div className="space-y-4">
                {revivals.map((rev) => (
                  <div key={rev.id} className="p-5 rounded-lg bg-card border border-border space-y-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2.5">
                          <span className="font-semibold text-foreground text-sm">{rev.company_name}</span>
                          <span className="text-xs text-muted-foreground">- {rev.prospect_name} ({rev.title})</span>
                          <span className="px-2 py-0.5 rounded text-xs font-medium bg-muted/60 text-foreground border border-border">
                            ${Number(rev.original_deal_value).toLocaleString()} ACV
                          </span>
                        </div>
                        <div className="text-xs text-muted-foreground mt-1">
                          Revival Trigger: {rev.revival_trigger}
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <span className="px-2.5 py-1 rounded-md text-xs font-medium bg-muted/60 text-muted-foreground border border-border">
                          Lost {rev.days_since_lost}d ago ({rev.lost_reason.replace('_', ' ')})
                        </span>
                        <span className="px-2.5 py-1 rounded-md text-xs font-medium bg-muted/60 text-foreground border border-border">
                          {rev.revival_score}/100 Readiness
                        </span>
                      </div>
                    </div>

                    <div className="p-3.5 rounded-lg bg-background border border-border text-xs text-foreground whitespace-pre-line font-sans leading-relaxed">
                      {rev.resurrection_message}
                    </div>

                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => copyToClipboard(rev.resurrection_message, rev.id)}
                        aria-label="Copy resurrection message"
                        className="px-3 py-1.5 rounded-lg bg-muted/60 hover:bg-muted border border-border text-foreground text-xs font-medium flex items-center gap-1.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        {copiedId === rev.id ? <Check className="w-3.5 h-3.5 text-foreground" /> : <Copy className="w-3.5 h-3.5" />}
                        Copy Resurrection Message
                      </button>

                      <button
                        onClick={() => handleEnroll(rev.id, 'revival', rev.company_name)}
                        disabled={enrollingId === rev.id || rev.status === 'revival_sent'}
                        className={`px-3.5 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                          rev.status === 'revival_sent'
                            ? 'bg-muted text-muted-foreground border border-border cursor-not-allowed opacity-60'
                            : 'bg-primary hover:bg-primary/90 text-primary-foreground active:scale-[0.98]'
                        }`}
                      >
                        {enrollingId === rev.id ? (
                          <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <RotateCcw className="w-3.5 h-3.5" />
                        )}
                        {rev.status === 'revival_sent' ? 'Resurrection Active' : 'Resurrect Deal Sequence'}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

        </div>

        {/* Modal: Track Champion Job Change */}
        {addJobChangeOpen && (
          <div
            className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm overflow-y-auto"
            onClick={() => setAddJobChangeOpen(false)}
          >
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="track-jobchange-title"
              className="w-full max-w-lg max-h-[90vh] overflow-y-auto bg-card border border-border rounded-xl p-6 shadow-2xl space-y-4 text-xs text-foreground my-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between border-b border-border pb-3">
                <h3 id="track-jobchange-title" className="font-semibold text-foreground text-base">Track Champion Job Change</h3>
                <button
                  onClick={() => setAddJobChangeOpen(false)}
                  aria-label="Close dialog"
                  className="p-1.5 text-muted-foreground hover:text-foreground bg-muted/60 hover:bg-muted border border-border rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="space-y-3">
                <div>
                  <label className="text-muted-foreground font-medium">Executive Full Name *</label>
                  <input
                    type="text"
                    value={jcName}
                    onChange={(e) => setJcName(e.target.value)}
                    placeholder="e.g. Claire Underwood"
                    className="w-full mt-1 bg-background border border-border rounded-lg p-2 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  />
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="text-muted-foreground font-medium">Previous Company *</label>
                    <input
                      type="text"
                      value={jcPrevCompany}
                      onChange={(e) => setJcPrevCompany(e.target.value)}
                      placeholder="e.g. Snowflake"
                      className="w-full mt-1 bg-background border border-border rounded-lg p-2 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    />
                  </div>
                  <div>
                    <label className="text-muted-foreground font-medium">Previous Title</label>
                    <input
                      type="text"
                      value={jcPrevTitle}
                      onChange={(e) => setJcPrevTitle(e.target.value)}
                      placeholder="e.g. VP Sales"
                      className="w-full mt-1 bg-background border border-border rounded-lg p-2 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="text-muted-foreground font-medium">New Company *</label>
                    <input
                      type="text"
                      value={jcNewCompany}
                      onChange={(e) => setJcNewCompany(e.target.value)}
                      placeholder="e.g. Databricks"
                      className="w-full mt-1 bg-background border border-border rounded-lg p-2 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    />
                  </div>
                  <div>
                    <label className="text-muted-foreground font-medium">New Title</label>
                    <input
                      type="text"
                      value={jcNewTitle}
                      onChange={(e) => setJcNewTitle(e.target.value)}
                      placeholder="e.g. Chief Revenue Officer"
                      className="w-full mt-1 bg-background border border-border rounded-lg p-2 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="text-muted-foreground font-medium">Past Relationship</label>
                    <Select
                      value={jcRelType}
                      onValueChange={(val) => setJcRelType(val)}
                    >
                      <SelectTrigger className="w-full mt-1 bg-background border-border h-9 text-xs focus-visible:ring-2 focus-visible:ring-ring">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="past_customer">Past Customer</SelectItem>
                        <SelectItem value="former_champion">Former Champion</SelectItem>
                        <SelectItem value="power_user">Power User</SelectItem>
                        <SelectItem value="closed_lost_contact">Closed-Lost Contact</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <label className="text-muted-foreground font-medium">Days in New Role</label>
                    <input
                      type="number"
                      min={0}
                      value={jcDays}
                      onChange={(e) => setJcDays(Number(e.target.value) || 0)}
                      className="w-full mt-1 bg-background border border-border rounded-lg p-2 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    />
                  </div>
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  onClick={() => setAddJobChangeOpen(false)}
                  className="px-4 py-2 rounded-lg bg-muted/60 hover:bg-muted border border-border text-muted-foreground hover:text-foreground font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  Cancel
                </button>
                <button
                  onClick={handleCreateJobChange}
                  disabled={isSavingJc}
                  className="px-4 py-2 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground font-medium flex items-center gap-1.5 transition-colors disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:scale-[0.98]"
                >
                  {isSavingJc && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                  Generate Boomerang Playbook
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Modal: Add Closed-Lost Deal */}
        {addRevivalOpen && (
          <div
            className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm overflow-y-auto"
            onClick={() => setAddRevivalOpen(false)}
          >
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="add-revival-title"
              className="w-full max-w-lg max-h-[90vh] overflow-y-auto bg-card border border-border rounded-xl p-6 shadow-2xl space-y-4 text-xs text-foreground my-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between border-b border-border pb-3">
                <h3 id="add-revival-title" className="font-semibold text-foreground text-base">Add Closed-Lost Deal for Resurrection</h3>
                <button
                  onClick={() => setAddRevivalOpen(false)}
                  aria-label="Close dialog"
                  className="p-1.5 text-muted-foreground hover:text-foreground bg-muted/60 hover:bg-muted border border-border rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="text-muted-foreground font-medium">Prospect Name *</label>
                    <input
                      type="text"
                      value={revName}
                      onChange={(e) => setRevName(e.target.value)}
                      placeholder="e.g. Lucas Graham"
                      className="w-full mt-1 bg-background border border-border rounded-lg p-2 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    />
                  </div>
                  <div>
                    <label className="text-muted-foreground font-medium">Company Name *</label>
                    <input
                      type="text"
                      value={revCompany}
                      onChange={(e) => setRevCompany(e.target.value)}
                      placeholder="e.g. Notion"
                      className="w-full mt-1 bg-background border border-border rounded-lg p-2 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div>
                    <label className="text-muted-foreground font-medium">Lost Reason</label>
                    <Select
                      value={revReason}
                      onValueChange={(val) => setRevReason(val)}
                    >
                      <SelectTrigger className="w-full mt-1 bg-background border-border h-9 text-xs focus-visible:ring-2 focus-visible:ring-ring">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="missing_feature">Missing Feature</SelectItem>
                        <SelectItem value="budget_freeze">Budget Freeze</SelectItem>
                        <SelectItem value="competitor_chosen">Competitor Chosen</SelectItem>
                        <SelectItem value="bad_timing">Bad Timing</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <label className="text-muted-foreground font-medium">Days Since Lost</label>
                    <input
                      type="number"
                      min={0}
                      value={revDays}
                      onChange={(e) => setRevDays(Number(e.target.value) || 0)}
                      className="w-full mt-1 bg-background border border-border rounded-lg p-2 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    />
                  </div>
                  <div>
                    <label className="text-muted-foreground font-medium">Deal Value ($)</label>
                    <input
                      type="number"
                      min={0}
                      value={revValue}
                      onChange={(e) => setRevValue(Number(e.target.value) || 0)}
                      className="w-full mt-1 bg-background border border-border rounded-lg p-2 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    />
                  </div>
                </div>

                <div>
                  <label className="text-muted-foreground font-medium">Resurrection Trigger / Product Update</label>
                  <input
                    type="text"
                    value={revTrigger}
                    onChange={(e) => setRevTrigger(e.target.value)}
                    placeholder="e.g. Shipped Autonomous ABM Multithreading & Buying Committee Studio"
                    className="w-full mt-1 bg-background border border-border rounded-lg p-2 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  />
                </div>

                {revDays < 14 && (
                  <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-600 dark:text-amber-400 flex items-center gap-2">
                    <ShieldAlert className="w-4 h-4 shrink-0" />
                    <span>Paranoia Layer 2 Anti-Pestering Guard: Deals lost fewer than 14 days ago are blocked from resurrection outreach to prevent prospect annoyance.</span>
                  </div>
                )}
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  onClick={() => setAddRevivalOpen(false)}
                  className="px-4 py-2 rounded-lg bg-muted/60 hover:bg-muted border border-border text-muted-foreground hover:text-foreground font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  Cancel
                </button>
                <button
                  onClick={handleCreateRevival}
                  disabled={isSavingRev || revDays < 14}
                  title={revDays < 14 ? 'Deals lost fewer than 14 days ago are blocked by Anti-Pestering Guard.' : undefined}
                  className="px-4 py-2 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground font-medium flex items-center gap-1.5 transition-colors disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:scale-[0.98]"
                >
                  {isSavingRev && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                  Create Resurrection Playbook
                </button>
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
