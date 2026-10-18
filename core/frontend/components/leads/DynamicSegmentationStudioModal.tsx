import React, { useState, useEffect, useMemo } from 'react';
import useSWR from 'swr';
import { 
  Filter, Layers, Sparkles, Plus, Trash2, Play, CheckCircle2, RefreshCw, 
  Sliders, X, ShieldCheck, AlertCircle, ArrowRight, Zap, Users, Target, 
  Compass, Lock, Building, UserCheck, Flame, Radio, Award, Check, ExternalLink, Download
} from 'lucide-react';
import { toast } from 'sonner';
import { motion, AnimatePresence } from 'motion/react';
import { fetchWithAuth } from '@/lib/apiClient';
import { usePaywall } from '@/contexts/PaywallContext';
import type { LeadList } from './leads.types';
import { CustomSelect } from '@/components/ui/select';

const fetcher = (url: string) => fetchWithAuth(url).then(r => r.json());

interface DynamicSegmentationStudioProps {
  initialListId?: string;
  onClose?: () => void;
  onRulesSaved?: () => void;
}

interface RuleCondition {
  id: string;
  field: string;
  operator: string;
  value: any;
}

const SENIORITY_OPTIONS = [
  { value: 'c_suite', label: 'C-Suite (CEO, CTO, CMO, CRO, COO)' },
  { value: 'founder', label: 'Founders & Co-Founders / Owners' },
  { value: 'vp', label: 'Vice Presidents (VP)' },
  { value: 'director', label: 'Directors & Heads' },
  { value: 'manager', label: 'Managers & Leads' },
  { value: 'contributor', label: 'Individual Contributors / Specialists' }
];

const COMPANY_SIZE_OPTIONS = [
  { value: '1-10', label: '1 - 10 employees (Micro)' },
  { value: '11-50', label: '11 - 50 employees (Early Growth)' },
  { value: '51-200', label: '51 - 200 employees (Mid-Market)' },
  { value: '201-500', label: '201 - 500 employees (Scale-Up)' },
  { value: '501-1000', label: '501 - 1,000 employees (Enterprise Tier 1)' },
  { value: '1001-5000', label: '1,001 - 5,000 employees (Large Enterprise)' },
  { value: '5001+', label: '5,001+ employees (Mega Enterprise)' }
];

const INTENT_TIER_OPTIONS = [
  { value: 'HOT', label: 'HOT — Active Buying Trigger / Recent Move' },
  { value: 'WARM', label: 'WARM — High Engagement / Frequent Poster' },
  { value: 'COLD', label: 'COLD — Baseline ICP Profile' }
];

const CONNECTION_DEGREE_OPTIONS = [
  { value: '1st', label: '1st Degree Connections' },
  { value: '2nd', label: '2nd Degree Connections' },
  { value: '3rd+', label: '3rd+ Degree Connections' }
];

const EMAIL_VERIFICATION_OPTIONS = [
  { value: 'valid', label: 'Valid & Verified' },
  { value: 'catch_all', label: 'Accept-All / Catch-All' },
  { value: 'unverified', label: 'Unverified / Raw' }
];

export function DynamicSegmentationStudioModal({ initialListId, onClose, onRulesSaved }: DynamicSegmentationStudioProps) {
  const { openPaywall } = usePaywall();
  const { data: billingData } = useSWR<{ tier?: string }>('/api/elein/workspaces/billing', fetcher);
  const isPro = billingData?.tier === 'PRO' || billingData?.tier === 'ENTERPRISE';

  // Data fetching for lists and campaigns
  const { data: listsData, mutate: mutateLists } = useSWR<LeadList[]>('/api/elein/leads/lists', fetcher);
  const { data: campaignsData } = useSWR<any[]>('/api/elein/campaigns', fetcher);

  const lists = Array.isArray(listsData) ? listsData : [];
  const campaigns = Array.isArray(campaignsData) ? campaignsData : [];

  const [selectedListId, setSelectedListId] = useState<string>(initialListId || (lists[0]?.id || ''));
  const [activeTab, setActiveTab] = useState<'rules' | 'auto_enroll' | 'preview'>('rules');

  // Rules State
  const [matchType, setMatchType] = useState<'ALL' | 'ANY'>('ALL');
  const [conditions, setConditions] = useState<RuleCondition[]>([
    { id: 'cond-1', field: 'seniority', operator: 'in', value: ['c_suite', 'founder', 'vp'] },
    { id: 'cond-2', field: 'company_size', operator: 'in', value: ['11-50', '51-200', '201-500'] },
    { id: 'cond-3', field: 'intent_tier', operator: 'equals', value: 'HOT' }
  ]);

  // Auto-Enrollment State
  const [autoEnrollEnabled, setAutoEnrollEnabled] = useState(true);
  const [targetCampaignId, setTargetCampaignId] = useState<string>('');
  const [allowReEnrollment, setAllowReEnrollment] = useState(false);

  // Evaluation & Sync State
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);

  const [previewData, setPreviewData] = useState<any>(null);

  // Keep selected list in sync if initialListId changes
  useEffect(() => {
    if (initialListId) {
      setSelectedListId(initialListId);
    } else if (lists.length > 0 && !selectedListId) {
      setSelectedListId(lists[0].id);
    }
  }, [initialListId, lists]);

  // Load existing rules for selected list
  useEffect(() => {
    if (!selectedListId) return;
    const fetchRules = async () => {
      try {
        const res = await fetchWithAuth(`/api/leads/lists/${selectedListId}/dynamic-rules`);
        if (res.ok) {
          const data = await res.json();
          if (data.dynamic_rules && data.dynamic_rules.conditions) {
            setMatchType(data.dynamic_rules.match_type || 'ALL');
            setConditions(data.dynamic_rules.conditions.map((c: any, idx: number) => ({
              id: `cond-saved-${idx}`,
              field: c.field,
              operator: c.operator,
              value: c.value
            })));
            if (data.dynamic_rules.auto_enroll_campaign_id) {
              setTargetCampaignId(data.dynamic_rules.auto_enroll_campaign_id);
              setAutoEnrollEnabled(true);
            }
            if (data.dynamic_rules.allow_re_enrollment !== undefined) {
              setAllowReEnrollment(data.dynamic_rules.allow_re_enrollment);
            }
          }
        }
      } catch (err) {
        // Fallback to defaults silently
      }
    };
    fetchRules();
  }, [selectedListId]);

  // Handler: Add condition
  const handleAddCondition = () => {
    const newCond: RuleCondition = {
      id: `cond-${Date.now()}`,
      field: 'seniority',
      operator: 'in',
      value: ['c_suite']
    };
    setConditions(prev => [...prev, newCond]);
  };

  // Handler: Remove condition
  const handleRemoveCondition = (id: string) => {
    if (conditions.length <= 1) {
      toast.error('You must maintain at least one condition in the segment.');
      return;
    }
    setConditions(prev => prev.filter(c => c.id !== id));
  };

  // Handler: Update condition field
  const handleUpdateCondition = (id: string, updates: Partial<RuleCondition>) => {
    setConditions(prev => prev.map(c => {
      if (c.id !== id) return c;
      const updated = { ...c, ...updates };
      // Reset values appropriately if field changed
      if (updates.field && updates.field !== c.field) {
        if (updates.field === 'seniority') {
          updated.operator = 'in';
          updated.value = ['c_suite', 'founder', 'vp'];
        } else if (updates.field === 'company_size') {
          updated.operator = 'in';
          updated.value = ['11-50', '51-200'];
        } else if (updates.field === 'intent_tier') {
          updated.operator = 'equals';
          updated.value = 'HOT';
        } else if (updates.field === 'connection_degree') {
          updated.operator = 'in';
          updated.value = ['2nd'];
        } else if (updates.field === 'email_verification') {
          updated.operator = 'equals';
          updated.value = 'valid';
        } else {
          updated.operator = 'contains';
          updated.value = '';
        }
      }
      return updated;
    }));
  };

  // Dry-Run Evaluation
  const handleRunEvaluation = async () => {
    if (!isPro) {
      openPaywall({
        featureName: "Dynamic Lead Segmentation & Rule Radar",
        minTier: "PRO",
        description: "Preview dynamic audience qualification, multi-attribute filtering, and real-time lead counts."
      });
      return;
    }

    if (!selectedListId) {
      toast.error('Please select a target lead list first.');
      return;
    }

    setIsEvaluating(true);
    try {
      const payload = {
        rules: {
          match_type: matchType,
          conditions: conditions.map(c => ({
            field: c.field,
            operator: c.operator,
            value: c.value
          }))
        },
        limit: 500
      };

      const res = await fetchWithAuth(`/api/leads/lists/${selectedListId}/evaluate-rules`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail?.message || err.detail || 'Failed to evaluate rules.');
      }

      const data = await res.json();
      setPreviewData(data);
      toast.success(`Evaluated ${data.total_workspace_leads.toLocaleString()} leads — ${data.matching_count.toLocaleString()} qualify!`);
    } catch (err: any) {
      toast.error(err.message || 'Evaluation failed. Checking defensive fallbacks.');
    } finally {
      setIsEvaluating(false);
    }
  };

  // Save Dynamic Rules
  const handleSaveRules = async () => {
    if (!isPro) {
      openPaywall({
        featureName: "Smart Dynamic Audience Auto-Enrollment",
        minTier: "PRO",
        description: "Unlock automatic real-time lead qualification, CollisionGuard cross-campaign protection, and continuous audience sync."
      });
      return;
    }

    if (!selectedListId) {
      toast.error('Please select a target lead list.');
      return;
    }

    setIsSaving(true);
    try {
      const payload = {
        match_type: matchType,
        conditions: conditions.map(c => ({
          field: c.field,
          operator: c.operator,
          value: c.value
        })),
        auto_enroll_campaign_id: autoEnrollEnabled && targetCampaignId ? targetCampaignId : null,
        allow_re_enrollment: allowReEnrollment
      };

      const res = await fetchWithAuth(`/api/leads/lists/${selectedListId}/dynamic-rules`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail?.message || err.detail || 'Failed to save dynamic rules.');
      }

      toast.success('Dynamic segmentation rules successfully saved!');
      if (mutateLists) mutateLists();
      if (onRulesSaved) onRulesSaved();
    } catch (err: any) {
      toast.error(err.message || 'Error saving rules.');
    } finally {
      setIsSaving(false);
    }
  };

  // Sync Segment Members Immediately
  const handleSyncNow = async () => {
    if (!isPro) {
      openPaywall({
        featureName: "Smart Dynamic Audience Auto-Enrollment",
        minTier: "PRO",
        description: "Execute immediate real-time sync of qualifying leads and trigger automated outreach workflows."
      });
      return;
    }

    if (!selectedListId) {
      toast.error('Please select a target lead list.');
      return;
    }

    setIsSyncing(true);
    try {
      // First ensure rules are saved
      await handleSaveRules();

      const res = await fetchWithAuth(`/api/leads/lists/${selectedListId}/sync-members`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          auto_enroll: autoEnrollEnabled,
          custom_rules: {
            match_type: matchType,
            conditions: conditions.map(c => ({
              field: c.field,
              operator: c.operator,
              value: c.value
            })),
            auto_enroll_campaign_id: autoEnrollEnabled && targetCampaignId ? targetCampaignId : null,
            allow_re_enrollment: allowReEnrollment
          }
        })
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail?.message || err.detail || 'Failed to sync segment members.');
      }

      const result = await res.json();
      toast.success(
        `Sync Complete: ${result.added_to_list || 0} leads added, ${result.disqualified_from_list || 0} removed, ${result.auto_enrolled_count || 0} enrolled into campaign!`,
        { duration: 6000 }
      );
      if (mutateLists) mutateLists();
    } catch (err: any) {
      toast.error(err.message || 'Error during member synchronization.');
    } finally {
      setIsSyncing(false);
    }
  };

  const selectedList = lists.find(l => l.id === selectedListId);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-background/80 backdrop-blur-md overflow-y-auto">
      <motion.div 
        initial={{ opacity: 0, scale: 0.98, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.98, y: 8 }}
        className="w-full max-w-5xl bg-card border border-border/80 rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[92vh]"
      >
        {/* Modal Header */}
        <div className="px-6 py-5 border-b border-border/60 flex items-center justify-between bg-muted/20 shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center text-primary shadow-xs">
              <Sliders size={20} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold text-foreground">Dynamic Lead Segmentation Studio</h2>
                <span className="text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider bg-primary/15 text-primary border border-primary/25">
                  Phase 14 · Horizon 26
                </span>
                {isPro ? (
                  <span className="text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 flex items-center gap-1">
                    <Sparkles size={10} /> Pro Enabled
                  </span>
                ) : (
                  <button 
                    type="button"
                    onClick={() => openPaywall({ featureName: "Dynamic Segmentation Studio", minTier: "PRO" })}
                    className="text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider bg-amber-500/15 text-amber-300 border border-amber-500/30 flex items-center gap-1 hover:bg-amber-500/25 transition-all cursor-pointer"
                  >
                    <Lock size={10} /> PRO Required
                  </button>
                )}
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Automatically segment qualified prospects based on Seniority, Headcount & Intent, with real-time CollisionGuard auto-enrollment.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {onClose && (
              <button 
                type="button"
                onClick={onClose}
                aria-label="Close dialog"
                className="w-9 h-9 rounded-lg border border-border/60 hover:bg-muted/60 text-muted-foreground hover:text-foreground flex items-center justify-center transition-colors cursor-pointer"
              >
                <X size={16} />
              </button>
            )}
          </div>
        </div>

        {/* In-Situ Pro Upgrade Banner for Free Users */}
        {!isPro && (
          <div className="mx-6 my-3 p-3.5 rounded-lg border border-border/60 bg-muted/30 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs shrink-0">
            <div className="flex items-center gap-3">
              <div className="w-7 h-7 rounded-md bg-primary/10 border border-primary/20 flex items-center justify-center text-primary shrink-0">
                <Sparkles size={14} />
              </div>
              <div>
                <span className="font-semibold text-foreground block">
                  Automate Real-Time Audience Growth with Growth Pro
                </span>
                <span className="text-[11px] text-muted-foreground">
                  Free plans include manual static lists. Upgrade to automate continuous lead qualification and CollisionGuard sequence enrollment.
                </span>
              </div>
            </div>
            <button
              type="button"
              onClick={() => openPaywall({ featureName: "Smart Dynamic Segmentation & Auto-Enrollment" })}
              className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground font-semibold text-xs transition-all shadow-xs shrink-0 self-start sm:self-auto cursor-pointer"
            >
              <Zap size={13} className="fill-current" />
              <span>Unlock Dynamic Studio</span>
              <ArrowRight size={13} />
            </button>
          </div>
        )}

        {/* Studio Sub-Header: Target List Picker & Tab Switcher */}
        <div className="px-6 py-3 bg-muted/10 border-b border-border/50 flex flex-col md:flex-row md:items-center justify-between gap-4 shrink-0">
          <div className="flex items-center gap-3">
            <label className="text-xs font-semibold text-muted-foreground whitespace-nowrap">
              Target Lead List:
            </label>
            <CustomSelect
              value={selectedListId}
              onValueChange={setSelectedListId}
              size="sm"
              className="w-auto"
              triggerClassName="text-xs font-semibold bg-background border-border/80 min-w-[240px]"
              options={lists.map(l => ({
                value: l.id,
                label: `${l.name} (${l.row_count >= 0 ? `${l.row_count.toLocaleString()} leads` : 'Processing'})${l.type === 'dynamic' ? ' · [Dynamic]' : ''}`,
              }))}
            />

            {selectedList && (
              <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider ${
                selectedList.type === 'dynamic' 
                  ? 'bg-blue-500/15 text-blue-400 border border-blue-500/30' 
                  : 'bg-muted text-muted-foreground'
              }`}>
                {selectedList.type === 'dynamic' ? 'Active Dynamic Segment' : 'Static List'}
              </span>
            )}
          </div>

          {/* Navigation Tabs */}
          <div className="flex items-center gap-1.5 bg-muted/40 p-1 rounded-lg border border-border/50 self-start md:self-auto">
            <button
              type="button"
              onClick={() => setActiveTab('rules')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                activeTab === 'rules'
                  ? 'bg-card text-foreground shadow-xs border border-border/60'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <Sliders size={13} className={activeTab === 'rules' ? 'text-primary' : ''} />
              <span>Rule Filter Engine</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('auto_enroll')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                activeTab === 'auto_enroll'
                  ? 'bg-card text-foreground shadow-xs border border-border/60'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <Target size={13} className={activeTab === 'auto_enroll' ? 'text-emerald-400' : ''} />
              <span>Auto-Enrollment & Safety</span>
              {autoEnrollEnabled && targetCampaignId && (
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              )}
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('preview')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                activeTab === 'preview'
                  ? 'bg-card text-foreground shadow-xs border border-border/60'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <Users size={13} className={activeTab === 'preview' ? 'text-blue-400' : ''} />
              <span>Audience Radar ({previewData?.matching_count || 0})</span>
            </button>
          </div>
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto flex-1 space-y-6">
          {activeTab === 'rules' && (
            <div className="space-y-6">
              {/* Match Mode Selector */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between p-4 rounded-lg bg-muted/20 border border-border/60 gap-3">
                <div>
                  <span className="text-xs font-bold text-foreground block">
                    Logic Gate Matching Mode
                  </span>
                  <span className="text-[11px] text-muted-foreground">
                    Define whether leads must satisfy every condition simultaneously or any single condition.
                  </span>
                </div>

                <div className="flex items-center gap-1 bg-background/80 p-1 rounded-lg border border-border/70 self-start sm:self-auto">
                  <button
                    type="button"
                    onClick={() => setMatchType('ALL')}
                    className={`px-3 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                      matchType === 'ALL'
                        ? 'bg-primary text-primary-foreground shadow-xs'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    Match ALL (AND)
                  </button>
                  <button
                    type="button"
                    onClick={() => setMatchType('ANY')}
                    className={`px-3 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                      matchType === 'ANY'
                        ? 'bg-primary text-primary-foreground shadow-xs'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    Match ANY (OR)
                  </button>
                </div>
              </div>

              {/* Condition Rows */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-foreground flex items-center gap-2">
                    <Filter size={14} className="text-primary" />
                    <span>Active Segmentation Conditions ({conditions.length})</span>
                  </span>
                  <button
                    type="button"
                    onClick={handleAddCondition}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-primary/30 bg-primary/10 hover:bg-primary/20 text-primary text-xs font-semibold transition-all cursor-pointer"
                  >
                    <Plus size={13} />
                    <span>Add Filter Condition</span>
                  </button>
                </div>

                <div className="space-y-2.5">
                  {conditions.map((cond, index) => (
                    <motion.div
                      key={cond.id}
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="p-3.5 rounded-lg border border-border/70 bg-card hover:border-primary/30 transition-all flex flex-col md:flex-row md:items-center gap-3 shadow-xs"
                    >
                      <div className="flex items-center gap-2 text-xs font-bold text-muted-foreground w-16 shrink-0">
                        {index === 0 ? 'Where' : matchType === 'ALL' ? 'AND' : 'OR'}
                      </div>

                      {/* Field Selector */}
                      <CustomSelect
                        value={cond.field}
                        onValueChange={(val) => handleUpdateCondition(cond.id, { field: val })}
                        size="sm"
                        className="md:w-48 shrink-0"
                        triggerClassName="text-xs font-semibold bg-background border-border/80"
                        options={[
                          { value: "seniority", label: "Seniority Level" },
                          { value: "company_size", label: "Company Headcount" },
                          { value: "intent_tier", label: "Intent & Social Radar" },
                          { value: "connection_degree", label: "LinkedIn Connection" },
                          { value: "email_verification", label: "Email Verification" },
                          { value: "job_title", label: "Job Title (Text)" },
                          { value: "company_name", label: "Company Name (Text)" },
                        ]}
                      />

                      {/* Operator Selector */}
                      <CustomSelect
                        value={cond.operator}
                        onValueChange={(val) => handleUpdateCondition(cond.id, { operator: val })}
                        size="sm"
                        className="md:w-36 shrink-0"
                        triggerClassName="text-xs font-medium bg-background border-border/80"
                        options={
                          cond.field === 'job_title' || cond.field === 'company_name'
                            ? [
                                { value: "contains", label: "contains" },
                                { value: "equals", label: "equals" },
                                { value: "not_contains", label: "does not contain" },
                              ]
                            : [
                                { value: "in", label: "is one of" },
                                { value: "equals", label: "equals" },
                                { value: "not_equals", label: "is not" },
                              ]
                        }
                      />

                      {/* Value Input / Multi-Select */}
                      <div className="flex-1 min-w-0">
                        {cond.field === 'seniority' ? (
                          <div className="flex flex-wrap gap-1.5">
                            {SENIORITY_OPTIONS.map(opt => {
                              const isChecked = Array.isArray(cond.value) 
                                ? cond.value.includes(opt.value) 
                                : cond.value === opt.value;
                              return (
                                <button
                                  key={opt.value}
                                  type="button"
                                  onClick={() => {
                                    if (cond.operator === 'in') {
                                      const current = Array.isArray(cond.value) ? [...cond.value] : [cond.value];
                                      const next = current.includes(opt.value)
                                        ? current.filter(v => v !== opt.value)
                                        : [...current, opt.value];
                                      handleUpdateCondition(cond.id, { value: next });
                                    } else {
                                      handleUpdateCondition(cond.id, { value: opt.value });
                                    }
                                  }}
                                  className={`text-[11px] px-2.5 py-1 rounded-lg border font-medium transition-all cursor-pointer ${
                                    isChecked
                                      ? 'bg-primary/15 text-primary border-primary/30 font-bold'
                                      : 'bg-muted/30 text-muted-foreground border-border/50 hover:bg-muted/60'
                                  }`}
                                >
                                  {opt.label.split(' (')[0]}
                                </button>
                              );
                            })}
                          </div>
                        ) : cond.field === 'company_size' ? (
                          <div className="flex flex-wrap gap-1.5">
                            {COMPANY_SIZE_OPTIONS.map(opt => {
                              const isChecked = Array.isArray(cond.value) 
                                ? cond.value.includes(opt.value) 
                                : cond.value === opt.value;
                              return (
                                <button
                                  key={opt.value}
                                  type="button"
                                  onClick={() => {
                                    if (cond.operator === 'in') {
                                      const current = Array.isArray(cond.value) ? [...cond.value] : [cond.value];
                                      const next = current.includes(opt.value)
                                        ? current.filter(v => v !== opt.value)
                                        : [...current, opt.value];
                                      handleUpdateCondition(cond.id, { value: next });
                                    } else {
                                      handleUpdateCondition(cond.id, { value: opt.value });
                                    }
                                  }}
                                  className={`text-[11px] px-2.5 py-1 rounded-lg border font-medium transition-all cursor-pointer ${
                                    isChecked
                                      ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30 font-bold'
                                      : 'bg-muted/30 text-muted-foreground border-border/50 hover:bg-muted/60'
                                  }`}
                                >
                                  {opt.value}
                                </button>
                              );
                            })}
                          </div>
                        ) : cond.field === 'intent_tier' ? (
                          <div className="flex items-center gap-1.5">
                            {INTENT_TIER_OPTIONS.map(opt => (
                              <button
                                key={opt.value}
                                type="button"
                                onClick={() => handleUpdateCondition(cond.id, { value: opt.value })}
                                className={`text-[11px] px-2.5 py-1 rounded-lg border font-medium transition-all cursor-pointer ${
                                  cond.value === opt.value
                                    ? opt.value === 'HOT' 
                                      ? 'bg-red-500/20 text-red-400 border-red-500/40 font-bold'
                                      : opt.value === 'WARM'
                                      ? 'bg-amber-500/20 text-amber-300 border-amber-500/40 font-bold'
                                      : 'bg-blue-500/20 text-blue-300 border-blue-500/40 font-bold'
                                    : 'bg-muted/30 text-muted-foreground border-border/50 hover:bg-muted/60'
                                }`}
                              >
                                {opt.value}
                              </button>
                            ))}
                          </div>
                        ) : cond.field === 'connection_degree' ? (
                          <div className="flex items-center gap-1.5">
                            {CONNECTION_DEGREE_OPTIONS.map(opt => (
                              <button
                                key={opt.value}
                                type="button"
                                onClick={() => handleUpdateCondition(cond.id, { value: opt.value })}
                                className={`text-[11px] px-2.5 py-1 rounded-lg border font-medium transition-all cursor-pointer ${
                                  cond.value === opt.value
                                    ? 'bg-indigo-500/20 text-indigo-300 border-indigo-500/40 font-bold'
                                    : 'bg-muted/30 text-muted-foreground border-border/50 hover:bg-muted/60'
                                }`}
                              >
                                {opt.label}
                              </button>
                            ))}
                          </div>
                        ) : cond.field === 'email_verification' ? (
                          <div className="flex items-center gap-1.5">
                            {EMAIL_VERIFICATION_OPTIONS.map(opt => (
                              <button
                                key={opt.value}
                                type="button"
                                onClick={() => handleUpdateCondition(cond.id, { value: opt.value })}
                                className={`text-[11px] px-2.5 py-1 rounded-lg border font-medium transition-all cursor-pointer ${
                                  cond.value === opt.value
                                    ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40 font-bold'
                                    : 'bg-muted/30 text-muted-foreground border-border/50 hover:bg-muted/60'
                                }`}
                              >
                                {opt.label}
                              </button>
                            ))}
                          </div>
                        ) : (
                          <input
                            type="text"
                            value={cond.value || ''}
                            onChange={(e) => handleUpdateCondition(cond.id, { value: e.target.value })}
                            placeholder={cond.field === 'job_title' ? 'e.g., VP Sales, Founder, Head of Growth' : 'e.g., Google, Stripe, Datadog'}
                            className="w-full text-xs bg-background border border-border/80 rounded-lg px-3 py-2 text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                          />
                        )}
                      </div>

                      {/* Remove Button */}
                      <button
                        type="button"
                        onClick={() => handleRemoveCondition(cond.id)}
                        className="p-2 text-muted-foreground hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition-colors cursor-pointer shrink-0"
                        title="Remove condition"
                      >
                        <Trash2 size={15} />
                      </button>
                    </motion.div>
                  ))}
                </div>
              </div>

              {/* Evaluation Quick Radar Widget */}
              <div className="p-4 rounded-lg bg-card border border-border/70 flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400 shrink-0">
                    <Radio size={18} className={isEvaluating ? 'animate-pulse' : ''} />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-foreground">
                        Real-Time Segment Radar:
                      </span>
                      {previewData ? (
                        <>
                          <span className="text-xs font-extrabold text-primary">
                            {previewData.matching_count?.toLocaleString() || 0} qualifying leads
                          </span>
                          <span className="text-[11px] text-muted-foreground">
                            ({previewData.match_percentage || 0}% of {previewData.total_workspace_leads?.toLocaleString() || 0} total leads)
                          </span>
                        </>
                      ) : (
                        <span className="text-xs text-muted-foreground font-medium">
                          Pre-flight dry-run not yet executed
                        </span>
                      )}
                    </div>
                    {previewData && (
                      <div className="flex items-center gap-3 mt-1 text-[11px] text-muted-foreground">
                        <span>C-Suite / Founders: {((previewData?.seniority_distribution?.c_suite || 0) + (previewData?.seniority_distribution?.founder || 0))}</span>
                        <span>•</span>
                        <span>HOT Intent: {previewData?.intent_distribution?.HOT || 0}</span>
                        <span>•</span>
                        <span>Mid-Market: {previewData?.company_size_distribution?.['51-200'] || 0}</span>
                      </div>
                    )}
                  </div>
                </div>

                <button
                  type="button"
                  onClick={handleRunEvaluation}
                  disabled={isEvaluating}
                  className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg border border-primary/40 bg-primary/10 hover:bg-primary/20 text-primary text-xs font-bold transition-all cursor-pointer whitespace-nowrap self-start md:self-auto shadow-xs"
                >
                  <RefreshCw size={13} className={isEvaluating ? 'animate-spin' : ''} />
                  <span>{isEvaluating ? 'Simulating Radar...' : 'Run Live Dry-Run Preview'}</span>
                </button>
              </div>
            </div>
          )}

          {activeTab === 'auto_enroll' && (
            <div className="space-y-6">
              {/* Auto-Enrollment Switch */}
              <div className="p-5 rounded-lg bg-card border border-border/70 space-y-4 shadow-xs">
                <div className="flex items-start justify-between gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <Target size={18} className="text-emerald-400" />
                      <span className="text-sm font-bold text-foreground">
                        Continuous Campaign Auto-Enrollment
                      </span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                        Zero Manual Work
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground max-w-2xl">
                      When enabled, any prospect newly entering this workspace that matches this segment's rules will be immediately queued into your selected outreach campaign.
                    </p>
                  </div>

                  <label className="relative inline-flex items-center cursor-pointer shrink-0 mt-1">
                    <input
                      type="checkbox"
                      checked={autoEnrollEnabled}
                      onChange={(e) => setAutoEnrollEnabled(e.target.checked)}
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-muted peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-500"></div>
                  </label>
                </div>

                {autoEnrollEnabled && (
                  <div className="pt-3 border-t border-border/50 flex flex-col sm:flex-row sm:items-center gap-3">
                    <label className="text-xs font-semibold text-muted-foreground whitespace-nowrap">
                      Target Campaign:
                    </label>
                    <CustomSelect
                      value={targetCampaignId}
                      onValueChange={setTargetCampaignId}
                      size="sm"
                      className="flex-1 max-w-md"
                      triggerClassName="text-xs font-semibold bg-background border-border/80"
                      placeholder="— Select Target Campaign for Auto-Enrollment —"
                      options={[
                        { value: "", label: "— Select Target Campaign for Auto-Enrollment —" },
                        ...campaigns.map(camp => ({
                          value: camp.id,
                          label: `${camp.name} (${camp.status || 'draft'})`,
                        })),
                      ]}
                    />
                  </div>
                )}
              </div>

              {/* Safety & CollisionGuard Architecture Cards */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* CollisionGuard Card */}
                <div className="p-4 rounded-lg bg-card border border-emerald-500/25 space-y-2.5 shadow-xs">
                  <div className="flex items-center gap-2">
                    <ShieldCheck size={16} className="text-emerald-400" />
                    <span className="text-xs font-bold text-foreground">
                      CollisionGuard™ Protection Active
                    </span>
                  </div>
                  <p className="text-[11px] text-muted-foreground leading-relaxed">
                    Prospects already active in another campaign, currently connected, or engaged in an active deal conversation will be safely bypassed to eliminate double-messaging across LinkedIn and Email.
                  </p>
                </div>

                {/* Disqualification Pause Guard Card */}
                <div className="p-4 rounded-lg bg-card border border-amber-500/25 space-y-2.5 shadow-xs">
                  <div className="flex items-center gap-2">
                    <AlertCircle size={16} className="text-amber-400" />
                    <span className="text-xs font-bold text-foreground">
                      Disqualification Pause Guard
                    </span>
                  </div>
                  <p className="text-[11px] text-muted-foreground leading-relaxed">
                    If an enrolled prospect changes job titles or switches companies such that they no longer meet these rules, outreach steps are automatically frozen with status <code className="text-[10px] text-amber-300">paused_disqualified</code>.
                  </p>
                </div>
              </div>

              {/* Re-Enrollment Guard */}
              <div className="p-4 rounded-lg bg-muted/20 border border-border/60 flex items-center justify-between gap-4">
                <div>
                  <span className="text-xs font-bold text-foreground block">
                    Allow Re-Enrollment for Completed Prospects
                  </span>
                  <span className="text-[11px] text-muted-foreground">
                    By default (recommended), prospects who previously completed this sequence are never re-enrolled to prevent spamming.
                  </span>
                </div>
                <label className="relative inline-flex items-center cursor-pointer shrink-0">
                  <input
                    type="checkbox"
                    checked={allowReEnrollment}
                    onChange={(e) => setAllowReEnrollment(e.target.checked)}
                    className="sr-only peer"
                  />
                  <div className="w-11 h-6 bg-muted peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary"></div>
                </label>
              </div>
            </div>
          )}

          {activeTab === 'preview' && (
            previewData === null ? (
              <div className="p-12 rounded-lg border border-dashed border-border/70 text-center space-y-4 bg-card/20">
                <div className="w-12 h-12 rounded-md bg-primary/10 border border-primary/20 flex items-center justify-center text-primary mx-auto">
                  <Radio size={24} />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-foreground">Pre-Flight Dry Run Idle</h3>
                  <p className="text-xs text-muted-foreground max-w-md mx-auto mt-1 leading-relaxed">
                    Configure rules above and click 'Run Pre-Flight Dry Run' to evaluate matching prospects across your workspace.
                  </p>
                </div>
                <div className="flex items-center justify-center gap-3 pt-2">
                  <button
                    type="button"
                    onClick={handleRunEvaluation}
                    disabled={isEvaluating}
                    className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold transition-all cursor-pointer shadow-xs disabled:opacity-50"
                  >
                    <RefreshCw size={13} className={isEvaluating ? 'animate-spin' : ''} />
                    <span>{isEvaluating ? 'Evaluating Workspace...' : 'Run Pre-Flight Dry Run'}</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setActiveTab('rules')}
                    className="px-4 py-2 rounded-lg bg-background border border-border/80 text-foreground hover:bg-muted/40 text-xs font-semibold transition-all cursor-pointer"
                  >
                    Configure Segment Rules
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-6">
                {/* Distribution Stats Pills */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="p-3.5 rounded-lg bg-card border border-border/70 text-center">
                    <span className="text-[11px] text-muted-foreground block font-medium">Qualifying Leads</span>
                    <span className="text-xl font-black text-primary mt-0.5 block">
                      {previewData?.matching_count?.toLocaleString() || 0}
                    </span>
                  </div>
                  <div className="p-3.5 rounded-lg bg-card border border-border/70 text-center">
                    <span className="text-[11px] text-muted-foreground block font-medium">Workspace ICP Match</span>
                    <span className="text-xl font-black text-emerald-400 mt-0.5 block">
                      {previewData?.match_percentage || 0}%
                    </span>
                  </div>
                  <div className="p-3.5 rounded-lg bg-card border border-border/70 text-center">
                    <span className="text-[11px] text-muted-foreground block font-medium">HOT Intent Leads</span>
                    <span className="text-xl font-black text-red-400 mt-0.5 block">
                      {previewData?.intent_distribution?.HOT || 0}
                    </span>
                  </div>
                  <div className="p-3.5 rounded-lg bg-card border border-border/70 text-center">
                    <span className="text-[11px] text-muted-foreground block font-medium">Total Database Scanned</span>
                    <span className="text-xl font-black text-muted-foreground mt-0.5 block">
                      {previewData?.total_workspace_leads?.toLocaleString() || 0}
                    </span>
                  </div>
                </div>

                {/* Sample Matching Prospects Table */}
                <div className="space-y-2.5">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-foreground flex items-center gap-2">
                      <Users size={14} className="text-primary" />
                      <span>Sample Qualifying Prospects Preview</span>
                    </span>
                    <div className="flex items-center gap-3">
                      <span className="text-[11px] text-muted-foreground hidden sm:inline">
                        Showing top matching sample profiles
                      </span>
                      <button
                        type="button"
                        onClick={async () => {
                          if (!selectedListId) {
                            toast.error('Please select a lead list first.');
                            return;
                          }
                          try {
                            const res = await fetchWithAuth(`/api/leads/lists/${encodeURIComponent(selectedListId)}/dynamic-segment/export-csv`);
                            if (res.status === 402) {
                              openPaywall({ featureName: "Dynamic Segment CSV Export", minTier: "PRO" });
                              return;
                            }
                            if (!res.ok) throw new Error('Failed to export dynamic segment CSV');
                            const blob = await res.blob();
                            const url = window.URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = `dynamic_segment_${selectedListId}_${Date.now()}.csv`;
                            document.body.appendChild(a);
                            a.click();
                            a.remove();
                            window.URL.revokeObjectURL(url);
                            toast.success('Qualifying segment prospects exported to CSV!');
                          } catch (e: any) {
                            toast.error(e.message || 'Failed to export CSV');
                          }
                        }}
                        className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg border border-border/80 bg-muted hover:bg-muted/80 text-foreground text-xs font-semibold transition-colors cursor-pointer"
                      >
                        <Download size={12} />
                        <span>Export Qualifying CSV</span>
                      </button>
                    </div>
                  </div>

                  <div className="border border-border/70 rounded-lg overflow-hidden bg-card shadow-xs">
                    <table className="w-full text-left border-collapse">
                      <thead>
                        <tr className="border-b border-border/60 bg-muted/20 text-[11px] font-bold text-muted-foreground">
                          <th className="py-2.5 px-4">Prospect</th>
                          <th className="py-2.5 px-4">Title & Seniority</th>
                          <th className="py-2.5 px-4">Company & Size</th>
                          <th className="py-2.5 px-4">Intent Tier</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/40 text-xs">
                        {(previewData?.sample_leads || []).length === 0 ? (
                          <tr>
                            <td colSpan={4} className="py-8 text-center text-xs text-muted-foreground">
                              No prospects in your workspace currently match these criteria.
                            </td>
                          </tr>
                        ) : (
                          (previewData?.sample_leads || []).map((lead: any, i: number) => (
                            <tr key={lead.id || i} className="hover:bg-muted/30 transition-colors">
                              <td className="py-3 px-4">
                                <span className="font-bold text-foreground block">
                                  {lead.first_name} {lead.last_name}
                                </span>
                                <span className="text-[11px] text-muted-foreground">
                                  {lead.email || 'Contact verified'}
                                </span>
                              </td>
                              <td className="py-3 px-4">
                                <span className="font-medium text-foreground block">{lead.job_title}</span>
                                <span className="text-[10px] px-1.5 py-0.5 rounded-md font-bold uppercase bg-primary/10 text-primary">
                                  {lead.seniority || 'verified'}
                                </span>
                              </td>
                              <td className="py-3 px-4">
                                <span className="font-medium text-foreground block">{lead.company_name}</span>
                                <span className="text-[10px] text-muted-foreground">
                                  {lead.company_size ? `${lead.company_size} employees` : 'Headcount normal'}
                                </span>
                              </td>
                              <td className="py-3 px-4">
                                <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold uppercase ${
                                  lead.intent_tier === 'HOT'
                                    ? 'bg-red-500/15 text-red-400 border border-red-500/30'
                                    : lead.intent_tier === 'WARM'
                                    ? 'bg-amber-500/15 text-amber-300 border border-amber-500/30'
                                    : 'bg-blue-500/15 text-blue-300 border border-blue-500/30'
                                }`}>
                                  {lead.intent_tier || 'HOT'}
                                </span>
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )
          )}
        </div>

        {/* Modal Footer Controls */}
        <div className="px-6 py-4 border-t border-border/60 bg-muted/20 flex flex-col sm:flex-row items-center justify-between gap-3 shrink-0">
          <div className="text-xs text-muted-foreground flex items-center gap-2">
            <CheckCircle2 size={14} className="text-emerald-400" />
            <span>
              {conditions.length} rule conditions active · {matchType === 'ALL' ? 'Strict AND matching' : 'Permissive OR matching'}
            </span>
          </div>

          <div className="flex items-center gap-2.5 w-full sm:w-auto">
            <button
              type="button"
              onClick={handleSaveRules}
              disabled={isSaving}
              className="flex-1 sm:flex-none px-4 py-2 rounded-lg border border-border/80 hover:bg-muted/60 text-foreground text-xs font-semibold transition-all cursor-pointer shadow-xs disabled:opacity-50"
            >
              {isSaving ? 'Saving Rules...' : 'Save Rules'}
            </button>

            <button
              type="button"
              onClick={handleSyncNow}
              disabled={isSyncing}
              className="flex-1 sm:flex-none inline-flex items-center justify-center gap-2 px-5 py-2 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-bold transition-all cursor-pointer shadow-sm disabled:opacity-50"
            >
              <RefreshCw size={14} className={isSyncing ? 'animate-spin' : ''} />
              <span>{isSyncing ? 'Syncing Segment...' : 'Save & Sync Segment Now'}</span>
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
