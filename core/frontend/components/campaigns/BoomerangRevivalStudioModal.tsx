import React, { useState } from 'react';
import useSWR from 'swr';
import {
  Repeat, Users, RotateCcw, RefreshCw, Copy, Check, ExternalLink,
  ArrowRight, ShieldAlert, Rocket, X, Plus, Briefcase, Award, DollarSign, GitBranch, TrendingUp
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

  const { data: jcData, mutate: mutateJc } = useSWR<{ success: boolean; job_changes: any[] }>(
    `/api/elein/boomerang/job-changes${relFilter !== 'all' ? `?relationship=${relFilter}` : ''}`,
    fetcher,
    { revalidateOnFocus: false }
  );

  // ── Tab 2: Warm Intro Graph State ──
  const [scriptMode, setScriptMode] = useState<Record<string, 'connector' | 'direct'>>({});
  const { data: wpData, mutate: mutateWp } = useSWR<{ success: boolean; warm_intros: any[] }>(
    '/api/elein/boomerang/warm-intros',
    fetcher,
    { revalidateOnFocus: false }
  );

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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-6xl h-[90vh] bg-card border border-border rounded-xl shadow-2xl flex flex-col overflow-hidden text-card-foreground">
        
        {/* Top Header */}
        <div className="px-6 py-4 border-b border-border bg-background flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-foreground">
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
              className="p-2 rounded-lg bg-muted/40 hover:bg-muted text-muted-foreground hover:text-foreground border border-border transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
            {onClose && (
              <button
                onClick={onClose}
                className="p-2 rounded-lg bg-muted/40 hover:bg-muted text-muted-foreground hover:text-foreground border border-border transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>

        {/* KPI Ribbon */}
        <div className="grid grid-cols-4 gap-4 px-6 py-3 border-b border-border bg-muted/40">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-background border border-border text-muted-foreground">
              <Award className="w-4 h-4" />
            </div>
            <div>
              <div className="text-xs text-muted-foreground">90-Day Boomerangs</div>
              <div className="text-sm font-semibold text-foreground">{jobChanges.length} Active Champions</div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-background border border-border text-muted-foreground">
              <GitBranch className="w-4 h-4" />
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Warm Intro Bridges</div>
              <div className="text-sm font-semibold text-foreground">{warmIntros.length} Verified Paths</div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-background border border-border text-muted-foreground">
              <DollarSign className="w-4 h-4" />
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Revivable Pipeline</div>
              <div className="text-sm font-semibold text-foreground">${totalRecoverablePipeline.toLocaleString()} ACV</div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-background border border-border text-muted-foreground">
              <TrendingUp className="w-4 h-4" />
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Alumni Reply Lift</div>
              <div className="text-sm font-semibold text-foreground">4.8x vs. Cold Outbound</div>
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="flex border-b border-border bg-background px-6">
          <button
            onClick={() => setActiveTab('boomerang')}
            className={`py-3 px-4 text-xs font-medium flex items-center gap-2 border-b-2 transition-all ${
              activeTab === 'boomerang'
                ? 'border-foreground text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Repeat className="w-4 h-4" />
            Champion Job-Change Boomerang ({jobChanges.length})
          </button>

          <button
            onClick={() => setActiveTab('warm_intros')}
            className={`py-3 px-4 text-xs font-medium flex items-center gap-2 border-b-2 transition-all ${
              activeTab === 'warm_intros'
                ? 'border-foreground text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <GitBranch className="w-4 h-4" />
            Mutual Connection & Alumni Graph ({warmIntros.length})
          </button>

          <button
            onClick={() => setActiveTab('revivals')}
            className={`py-3 px-4 text-xs font-medium flex items-center gap-2 border-b-2 transition-all ${
              activeTab === 'revivals'
                ? 'border-foreground text-foreground'
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
                          <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-muted/40 text-muted-foreground border border-border">
                            Internal Promotion Guard Active
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-2">
                        <span className="px-2.5 py-1 rounded-md text-xs font-medium bg-muted/40 text-foreground border border-border">
                          {jc.buying_window_score}/100 Buying Window (Day {jc.days_in_new_role})
                        </span>
                      </div>
                    </div>

                    {/* Visual Job Move Banner */}
                    <div className="flex flex-col sm:flex-row items-center gap-3 p-3 rounded-lg bg-muted/40 border border-border text-xs">
                      <div className="flex-1">
                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Previous Role</div>
                        <div className="font-medium text-muted-foreground mt-0.5">{jc.previous_title} @ <span className="text-foreground">{jc.previous_company}</span></div>
                      </div>
                      <ArrowRight className="w-4 h-4 text-muted-foreground shrink-0" />
                      <div className="flex-1">
                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">New Executive Role (First 90 Days)</div>
                        <div className="font-semibold text-foreground mt-0.5">{jc.new_title} @ <span className="text-foreground">{jc.new_company}</span></div>
                      </div>
                    </div>

                    {/* Playbook Message */}
                    <div className="space-y-1.5">
                      <div className="text-[11px] font-medium text-muted-foreground">Auto-Synthesized Boomerang Playbook Message:</div>
                      <div className="p-3.5 rounded-lg bg-background border border-border text-xs text-foreground whitespace-pre-line font-mono leading-relaxed">
                        {jc.playbook_message}
                      </div>
                    </div>

                    <div className="flex items-center justify-end gap-2 pt-1">
                      <button
                        onClick={() => copyToClipboard(jc.playbook_message, jc.id)}
                        className="px-3 py-1.5 rounded-lg bg-muted/40 hover:bg-muted border border-border text-foreground text-xs font-medium flex items-center gap-1.5"
                      >
                        {copiedId === jc.id ? <Check className="w-3.5 h-3.5 text-foreground" /> : <Copy className="w-3.5 h-3.5" />}
                        Copy Playbook
                      </button>

                      <button
                        onClick={() => handleEnroll(jc.id, 'job_change', jc.prospect_name)}
                        className="px-3.5 py-1.5 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-medium flex items-center gap-1.5"
                      >
                        <Rocket className="w-3.5 h-3.5" />
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

                      <span className="px-2.5 py-1 rounded-md text-xs font-medium bg-muted/40 text-foreground border border-border">
                        {wp.warmth_score}/100 Warmth Score
                      </span>
                    </div>

                    {/* Visual Referral Bridge */}
                    <div className="flex flex-col sm:flex-row items-center gap-3 p-3.5 rounded-lg bg-muted/40 border border-border text-xs">
                      <div className="px-3 py-1.5 rounded-md bg-background border border-border text-foreground font-medium">
                        You (Sender)
                      </div>
                      <ArrowRight className="w-4 h-4 text-muted-foreground" />
                      <div className="flex-1 p-2 rounded-md bg-background border border-border">
                        <div className="font-semibold text-foreground">{wp.connector_name} ({wp.connector_role})</div>
                        <div className="text-[11px] text-muted-foreground mt-0.5">{wp.overlap_context}</div>
                      </div>
                      <ArrowRight className="w-4 h-4 text-muted-foreground" />
                      <div className="px-3 py-1.5 rounded-md bg-background border border-border text-foreground font-semibold">
                        {wp.target_prospect_name} @ {wp.target_company}
                      </div>
                    </div>

                    {/* Dual Script Selector */}
                    <div className="flex items-center justify-between">
                      <div className="flex bg-muted/40 p-1 rounded-lg border border-border text-xs">
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
                          className="px-3 py-1.5 rounded-lg bg-muted/40 hover:bg-muted border border-border text-foreground text-xs font-medium flex items-center gap-1.5"
                        >
                          {copiedId === wp.id ? <Check className="w-3.5 h-3.5 text-foreground" /> : <Copy className="w-3.5 h-3.5" />}
                          Copy Script
                        </button>
                      </div>
                    </div>

                    <div className="p-3.5 rounded-lg bg-background border border-border text-xs text-foreground whitespace-pre-line font-mono leading-relaxed">
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
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-xs text-muted-foreground">Filter by Lost Reason:</span>
                  <Select
                    value={reasonFilter}
                    onValueChange={(val) => setReasonFilter(val)}
                  >
                    <SelectTrigger size="sm" className="w-[220px] bg-background border-border text-xs">
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
                  className="px-3.5 py-1.5 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground font-medium text-xs flex items-center gap-1.5 transition-colors cursor-pointer"
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
                          <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-muted/40 text-foreground border border-border">
                            ${Number(rev.original_deal_value).toLocaleString()} ACV
                          </span>
                        </div>
                        <div className="text-[11px] text-muted-foreground mt-1">
                          Revival Trigger: {rev.revival_trigger}
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <span className="px-2.5 py-1 rounded-md text-xs font-medium bg-muted/40 text-muted-foreground border border-border">
                          Lost {rev.days_since_lost}d ago ({rev.lost_reason.replace('_', ' ')})
                        </span>
                        <span className="px-2.5 py-1 rounded-md text-xs font-medium bg-muted/40 text-foreground border border-border">
                          {rev.revival_score}/100 Readiness
                        </span>
                      </div>
                    </div>

                    <div className="p-3.5 rounded-lg bg-background border border-border text-xs text-foreground whitespace-pre-line font-mono leading-relaxed">
                      {rev.resurrection_message}
                    </div>

                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => copyToClipboard(rev.resurrection_message, rev.id)}
                        className="px-3 py-1.5 rounded-lg bg-muted/40 hover:bg-muted border border-border text-foreground text-xs font-medium flex items-center gap-1.5"
                      >
                        {copiedId === rev.id ? <Check className="w-3.5 h-3.5 text-foreground" /> : <Copy className="w-3.5 h-3.5" />}
                        Copy Resurrection Message
                      </button>

                      <button
                        onClick={() => handleEnroll(rev.id, 'revival', rev.company_name)}
                        className="px-3.5 py-1.5 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-medium flex items-center gap-1.5 cursor-pointer"
                      >
                        <RotateCcw className="w-3.5 h-3.5" />
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
          <div className="fixed inset-0 z-60 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
            <div className="w-full max-w-lg bg-card border border-border rounded-lg p-6 shadow-2xl space-y-4 text-xs text-card-foreground">
              <div className="flex items-center justify-between border-b border-border pb-3">
                <h3 className="font-semibold text-foreground text-base">Track Champion Job Change</h3>
                <button onClick={() => setAddJobChangeOpen(false)} className="text-muted-foreground hover:text-foreground">
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
                    className="w-full mt-1 bg-background border border-border rounded-lg p-2 text-foreground"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-muted-foreground font-medium">Previous Company *</label>
                    <input
                      type="text"
                      value={jcPrevCompany}
                      onChange={(e) => setJcPrevCompany(e.target.value)}
                      placeholder="e.g. Snowflake"
                      className="w-full mt-1 bg-background border border-border rounded-lg p-2 text-foreground"
                    />
                  </div>
                  <div>
                    <label className="text-muted-foreground font-medium">Previous Title</label>
                    <input
                      type="text"
                      value={jcPrevTitle}
                      onChange={(e) => setJcPrevTitle(e.target.value)}
                      placeholder="e.g. VP Sales"
                      className="w-full mt-1 bg-background border border-border rounded-lg p-2 text-foreground"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-muted-foreground font-medium">New Company *</label>
                    <input
                      type="text"
                      value={jcNewCompany}
                      onChange={(e) => setJcNewCompany(e.target.value)}
                      placeholder="e.g. Databricks"
                      className="w-full mt-1 bg-background border border-border rounded-lg p-2 text-foreground"
                    />
                  </div>
                  <div>
                    <label className="text-muted-foreground font-medium">New Title</label>
                    <input
                      type="text"
                      value={jcNewTitle}
                      onChange={(e) => setJcNewTitle(e.target.value)}
                      placeholder="e.g. Chief Revenue Officer"
                      className="w-full mt-1 bg-background border border-border rounded-lg p-2 text-foreground"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-muted-foreground font-medium">Past Relationship</label>
                    <Select
                      value={jcRelType}
                      onValueChange={(val) => setJcRelType(val)}
                    >
                      <SelectTrigger className="w-full mt-1 bg-background border-border h-9 text-xs">
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
                      value={jcDays}
                      onChange={(e) => setJcDays(parseInt(e.target.value, 10) || 14)}
                      className="w-full mt-1 bg-background border border-border rounded-lg p-2 text-foreground"
                    />
                  </div>
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button onClick={() => setAddJobChangeOpen(false)} className="px-4 py-2 rounded-lg bg-muted/40 hover:bg-muted border border-border text-muted-foreground font-medium">
                  Cancel
                </button>
                <button
                  onClick={handleCreateJobChange}
                  disabled={isSavingJc}
                  className="px-4 py-2 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground font-medium"
                >
                  Generate Boomerang Playbook
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Modal: Add Closed-Lost Deal */}
        {addRevivalOpen && (
          <div className="fixed inset-0 z-60 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
            <div className="w-full max-w-lg bg-card border border-border rounded-lg p-6 shadow-2xl space-y-4 text-xs text-card-foreground">
              <div className="flex items-center justify-between border-b border-border pb-3">
                <h3 className="font-semibold text-foreground text-base">Add Closed-Lost Deal for Resurrection</h3>
                <button onClick={() => setAddRevivalOpen(false)} className="text-muted-foreground hover:text-foreground">
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-muted-foreground font-medium">Prospect Name *</label>
                    <input
                      type="text"
                      value={revName}
                      onChange={(e) => setRevName(e.target.value)}
                      placeholder="e.g. Lucas Graham"
                      className="w-full mt-1 bg-background border border-border rounded-lg p-2 text-foreground"
                    />
                  </div>
                  <div>
                    <label className="text-muted-foreground font-medium">Company Name *</label>
                    <input
                      type="text"
                      value={revCompany}
                      onChange={(e) => setRevCompany(e.target.value)}
                      placeholder="e.g. Notion"
                      className="w-full mt-1 bg-background border border-border rounded-lg p-2 text-foreground"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <label className="text-muted-foreground font-medium">Lost Reason</label>
                    <Select
                      value={revReason}
                      onValueChange={(val) => setRevReason(val)}
                    >
                      <SelectTrigger className="w-full mt-1 bg-background border-border h-9 text-xs">
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
                      value={revDays}
                      onChange={(e) => setRevDays(parseInt(e.target.value, 10) || 0)}
                      className="w-full mt-1 bg-background border border-border rounded-lg p-2 text-foreground"
                    />
                  </div>
                  <div>
                    <label className="text-muted-foreground font-medium">Deal Value ($)</label>
                    <input
                      type="number"
                      value={revValue}
                      onChange={(e) => setRevValue(parseInt(e.target.value, 10) || 25000)}
                      className="w-full mt-1 bg-background border border-border rounded-lg p-2 text-foreground"
                    />
                  </div>
                </div>

                {revDays < 14 && (
                  <div className="p-3 rounded-lg bg-muted/40 border border-border text-muted-foreground flex items-center gap-2">
                    <ShieldAlert className="w-4 h-4 shrink-0 text-foreground" />
                    <span>Paranoia Layer 2 Anti-Pestering Guard: Deals lost fewer than 14 days ago will be blocked to prevent prospect irritation.</span>
                  </div>
                )}
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button onClick={() => setAddRevivalOpen(false)} className="px-4 py-2 rounded-lg bg-muted/40 hover:bg-muted border border-border text-muted-foreground font-medium">
                  Cancel
                </button>
                <button
                  onClick={handleCreateRevival}
                  disabled={isSavingRev}
                  className="px-4 py-2 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground font-medium cursor-pointer transition-colors"
                >
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
