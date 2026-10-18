import React, { useState, useEffect } from 'react';
import useSWR from 'swr';
import {
  Target, ShieldAlert, DollarSign, Calculator, RefreshCw, Copy, Check,
  Rocket, X, Plus, Clock, Building2, User, AlertTriangle, CheckCircle2, MessageSquare
} from 'lucide-react';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/lib/apiClient';
import { usePaywall } from '@/contexts/PaywallContext';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

const fetcher = (url: string) => fetchWithAuth(url).then(r => r.json());

interface DisplacementStudioModalProps {
  onClose?: () => void;
  campaignId?: string;
}

export function DisplacementStudioModal({ onClose, campaignId }: DisplacementStudioModalProps) {
  const { openPaywall } = usePaywall();
  const [activeTab, setActiveTab] = useState<'radar' | 'battlecards' | 'pitch_studio'>('radar');
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // ── Tab 1: Displacement Radar State ──
  const [vendorFilter, setVendorFilter] = useState<string>('all');
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [targetCompany, setTargetCompany] = useState('');
  const [targetContactName, setTargetContactName] = useState('');
  const [targetContactTitle, setTargetContactTitle] = useState('');
  const [incumbentVendor, setIncumbentVendor] = useState('apollo');
  const [domain, setDomain] = useState('');
  const [seatCount, setSeatCount] = useState(10);
  const [seatCountStr, setSeatCountStr] = useState('10');
  const [renewalDays, setRenewalDays] = useState(60);
  const [renewalDaysStr, setRenewalDaysStr] = useState('60');
  const [isCreating, setIsCreating] = useState(false);
  const [launchingId, setLaunchingId] = useState<string | null>(null);

  // Keyboard navigation & Escape dismiss
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (addModalOpen) {
          setAddModalOpen(false);
        } else if (onClose) {
          onClose();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [addModalOpen, onClose]);

  const { data: oppData, mutate: mutateOpps, isLoading: isOppsLoading } = useSWR<{
    success: boolean;
    displacements: any[];
    total: number;
  }>(
    `/api/elein/displacement/opportunities${vendorFilter !== 'all' ? `?vendor=${vendorFilter}` : ''}`,
    fetcher,
    { revalidateOnFocus: false }
  );

  // ── Tab 2: Battlecards & Calculator State ──
  const [selectedVendorSlug, setSelectedVendorSlug] = useState<string>('apollo');
  const [calcSeats, setCalcSeats] = useState<number>(15);
  const [customMonthlyCost, setCustomMonthlyCost] = useState<string>('');

  const { data: battlecardsData } = useSWR<{
    success: boolean;
    battlecards: any[];
  }>(
    '/api/elein/displacement/battlecards',
    fetcher,
    { revalidateOnFocus: false }
  );

  const battlecards = battlecardsData?.battlecards || [];
  const currentBattlecard = battlecards.find(b => b.vendor_slug === selectedVendorSlug) || battlecards[0];

  // Live calculator calculation
  const getIncumbentRate = () => {
    if (customMonthlyCost && !isNaN(Number(customMonthlyCost))) {
      return Number(customMonthlyCost);
    }
    const defaultRates: Record<string, number> = {
      apollo: 99,
      outreach: 140,
      salesloft: 135,
      lemlist: 69,
      expandi: 99,
      heyreach: 89,
      other: 99
    };
    return defaultRates[selectedVendorSlug] || 99;
  };

  const incumbentRate = getIncumbentRate();
  const eleinRate = 49;
  const incumbentAnnual = incumbentRate * calcSeats * 12;
  const eleinAnnual = eleinRate * calcSeats * 12;
  const annualSavings = Math.max(0, incumbentAnnual - eleinAnnual);
  const savingsPct = incumbentAnnual > 0 ? Math.round((annualSavings / incumbentAnnual) * 100) : 0;

  // ── Tab 3: Pitch Studio State ──
  const [pitchCompany, setPitchCompany] = useState('Acme Corp');
  const [pitchContact, setPitchContact] = useState('Sarah Jenkins');
  const [pitchTitle, setPitchTitle] = useState('VP of Sales');
  const [pitchVendor, setPitchVendor] = useState('apollo');
  const [pitchSeats, setPitchSeats] = useState(12);
  const [pitchSeatsStr, setPitchSeatsStr] = useState('12');
  const [pitchDays, setPitchDays] = useState(60);
  const [pitchDaysStr, setPitchDaysStr] = useState('60');
  const [isGeneratingPitch, setIsGeneratingPitch] = useState(false);
  const [generatedPitch, setGeneratedPitch] = useState<{
    linkedin_pitch?: string;
    executive_email_pitch?: string;
    buyout_clause?: string;
    annual_savings?: number;
    recommended_angle?: string;
    subject?: string;
    body?: string;
    displacement_hook?: string;
    contract_buyout_offer?: string;
  } | null>(null);

  const copyToClipboard = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    toast.success('Copied to clipboard!');
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const handleCreateDisplacement = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!targetCompany.trim() || !targetContactName.trim()) {
      toast.error('Please specify target company and contact name.');
      return;
    }
    setIsCreating(true);
    try {
      const res = await fetchWithAuth('/api/elein/displacement/opportunities', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_company: targetCompany.trim(),
          target_contact_name: targetContactName.trim(),
          target_contact_title: targetContactTitle.trim() || 'Sales Leadership',
          incumbent_vendor: incumbentVendor,
          domain: domain.trim() || undefined,
          seat_count: Number(seatCount) || 10,
          contract_renewal_days: Number(renewalDays) || 60
        })
      });
      if (res.status === 402) {
        openPaywall('Autonomous Competitive Displacement & Tech Takeover Engine');
        return;
      }
      const data = await res.json();
      if (data.success) {
        toast.success(`Tracked ${targetCompany} (${incumbentVendor.toUpperCase()}) successfully!`);
        setAddModalOpen(false);
        setTargetCompany('');
        setTargetContactName('');
        setTargetContactTitle('');
        setDomain('');
        setSeatCount(10);
        setSeatCountStr('10');
        setRenewalDays(60);
        setRenewalDaysStr('60');
        mutateOpps();
      } else {
        toast.error(data.detail || 'Failed to track competitor target.');
      }
    } catch (err: any) {
      toast.error('Network error tracking competitor: ' + err.message);
    } finally {
      setIsCreating(false);
    }
  };

  const handleLaunchSequence = async (id: string, company: string) => {
    setLaunchingId(id);
    try {
      const res = await fetchWithAuth('/api/elein/displacement/launch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          displacement_id: id,
          campaign_id: campaignId || null
        })
      });
      if (res.status === 402) {
        openPaywall('Autonomous Competitive Displacement & Tech Takeover Engine');
        return;
      }
      const data = await res.json();
      if (data.success) {
        toast.success(`Displacement sequence launched for ${company}!`);
        mutateOpps();
      } else {
        toast.error(data.detail || 'Failed to launch sequence.');
      }
    } catch (err: any) {
      toast.error('Failed to launch: ' + err.message);
    } finally {
      setLaunchingId(null);
    }
  };

  const handleGeneratePitch = async () => {
    setIsGeneratingPitch(true);
    try {
      const res = await fetchWithAuth('/api/elein/displacement/generate-pitch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          incumbent_vendor: pitchVendor,
          target_company: pitchCompany,
          target_contact_name: pitchContact,
          target_contact_title: pitchTitle,
          seat_count: Number(pitchSeats),
          renewal_days: Number(pitchDays)
        })
      });
      if (res.status === 402) {
        openPaywall('Autonomous Competitive Displacement & Tech Takeover Engine');
        return;
      }
      const data = await res.json();
      if (data.success) {
        setGeneratedPitch(data.data);
        toast.success('Generated diplomatic displacement pitch!');
      } else {
        toast.error(data.detail || 'Failed to generate pitch.');
      }
    } catch (err: any) {
      toast.error('Error generating pitch: ' + err.message);
    } finally {
      setIsGeneratingPitch(false);
    }
  };

  const displacements = oppData?.displacements || [];
  const totalAnnualSavings = displacements.reduce((sum, d) => sum + (Number(d.annual_potential_savings) || 0), 0);
  const peakWindowCount = displacements.filter(d => (d.contract_renewal_days || 0) >= 45 && (d.contract_renewal_days || 0) <= 90).length;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4 overflow-hidden"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="displacement-modal-title"
        className="relative w-full max-w-6xl max-h-[92vh] max-h-[92dvh] flex flex-col bg-card border border-border rounded-xl shadow-2xl text-foreground overflow-hidden my-auto"
        onClick={(e) => e.stopPropagation()}
      >
        
        {/* Header Bar */}
        <div className="px-6 py-4 border-b border-border bg-background flex items-center justify-between">
          <div>
            <h2 id="displacement-modal-title" className="text-lg sm:text-xl font-bold tracking-tight text-foreground">
              Autonomous Competitive Takeover & Tech-Stack Displacement
            </h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Detect competitor incumbent contracts (Apollo, Outreach, Salesloft), score peak renewal windows, and calculate buyouts.
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close studio"
            className="p-2 text-muted-foreground hover:text-foreground bg-muted/60 hover:bg-muted border border-border rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Global Telemetry Metric Bar */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 px-6 py-3 bg-muted/60 border-b border-border text-xs">
          <div className="bg-background border border-border rounded-lg p-3 flex items-center gap-3">
            <Building2 className="w-4 h-4 text-muted-foreground shrink-0" />
            <div>
              <div className="text-xs text-muted-foreground">Tracked Incumbents</div>
              <div className="text-sm font-semibold text-foreground">{displacements.length} Accounts</div>
            </div>
          </div>
          <div className="bg-background border border-border rounded-lg p-3 flex items-center gap-3">
            <Clock className="w-4 h-4 text-muted-foreground shrink-0" />
            <div>
              <div className="text-xs text-muted-foreground">Peak Renewal Window</div>
              <div className="text-sm font-semibold text-foreground">{peakWindowCount} Accounts (45-90d)</div>
            </div>
          </div>
          {/* Leading Metric */}
          <div className="bg-primary/10 border border-primary/20 rounded-lg p-3 flex items-center gap-3">
            <DollarSign className="w-4 h-4 text-primary shrink-0" />
            <div>
              <div className="text-xs text-primary/80 font-medium">Identified Savings Pool</div>
              <div className="text-sm font-bold text-primary">${totalAnnualSavings.toLocaleString()}/yr</div>
            </div>
          </div>
          <div className="bg-background border border-border rounded-lg p-3 flex items-center gap-3">
            <ShieldAlert className="w-4 h-4 text-muted-foreground shrink-0" />
            <div>
              <div className="text-xs text-muted-foreground">Ele-in Consolidated Rate</div>
              <div className="text-sm font-semibold text-foreground">$49/seat/mo Flat</div>
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div
          role="tablist"
          aria-label="Displacement Studio Sections"
          className="flex border-b border-border px-6 bg-background gap-6 text-xs font-medium overflow-x-auto scrollbar-none whitespace-nowrap shrink-0"
        >
          <button
            role="tab"
            aria-selected={activeTab === 'radar'}
            onClick={() => setActiveTab('radar')}
            className={`py-3 flex items-center gap-2 border-b-2 transition-colors shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
              activeTab === 'radar'
                ? 'border-primary text-primary font-semibold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Target className="w-4 h-4" />
            Displacement Radar & Renewals ({displacements.length})
          </button>
          <button
            role="tab"
            aria-selected={activeTab === 'battlecards'}
            onClick={() => setActiveTab('battlecards')}
            className={`py-3 flex items-center gap-2 border-b-2 transition-colors shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
              activeTab === 'battlecards'
                ? 'border-primary text-primary font-semibold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Calculator className="w-4 h-4" />
            Vendor Battlecards & Buyout Calculator
          </button>
          <button
            role="tab"
            aria-selected={activeTab === 'pitch_studio'}
            onClick={() => setActiveTab('pitch_studio')}
            className={`py-3 flex items-center gap-2 border-b-2 transition-colors shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
              activeTab === 'pitch_studio'
                ? 'border-primary text-primary font-semibold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <MessageSquare className="w-4 h-4" />
            Diplomatic Pitch Studio
          </button>
        </div>

        {/* Modal Body / Tab Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">

          {/* TAB 1: RADAR & RENEWALS */}
          {activeTab === 'radar' && (
            <div className="space-y-6">
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground font-medium uppercase tracking-wider">Filter Vendor:</span>
                  <Select
                    value={vendorFilter}
                    onValueChange={(val) => setVendorFilter(val)}
                  >
                    <SelectTrigger size="sm" className="w-[150px] bg-background border-border text-xs focus-visible:ring-2 focus-visible:ring-ring">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Vendors</SelectItem>
                      <SelectItem value="apollo">Apollo.io</SelectItem>
                      <SelectItem value="outreach">Outreach.io</SelectItem>
                      <SelectItem value="salesloft">Salesloft</SelectItem>
                      <SelectItem value="lemlist">Lemlist</SelectItem>
                      <SelectItem value="expandi">Expandi</SelectItem>
                      <SelectItem value="heyreach">HeyReach</SelectItem>
                      <SelectItem value="other">Other</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => mutateOpps()}
                    aria-label="Refresh opportunities"
                    className="p-2 text-muted-foreground hover:text-foreground bg-muted/60 hover:bg-muted border border-border rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    title="Refresh Opportunities"
                  >
                    <RefreshCw className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => setAddModalOpen(true)}
                    className="flex items-center gap-2 px-3.5 py-1.5 bg-primary hover:bg-primary/90 text-primary-foreground rounded-lg text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:scale-[0.98]"
                  >
                    <Plus className="w-4 h-4" />
                    Track Incumbent Target
                  </button>
                </div>
              </div>

              {/* Displacement Target Cards */}
              {isOppsLoading ? (
                <div className="p-12 text-center text-muted-foreground flex items-center justify-center gap-3 text-xs">
                  <RefreshCw className="w-4 h-4 animate-spin text-muted-foreground" />
                  Scanning competitor tech stacks...
                </div>
              ) : displacements.length === 0 ? (
                <div className="p-12 text-center bg-muted/40 border border-dashed border-border rounded-lg">
                  <Target className="w-8 h-8 text-muted-foreground mx-auto mb-3" />
                  <h3 className="text-sm font-semibold text-foreground">No Competitor Targets Found</h3>
                  <p className="text-xs text-muted-foreground max-w-md mx-auto mt-1 mb-4">
                    Add companies currently using Apollo, Outreach, or Salesloft to monitor their renewal countdown and launch migration offers.
                  </p>
                  <button
                    onClick={() => setAddModalOpen(true)}
                    className="px-4 py-2 bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-medium rounded-lg transition-colors"
                  >
                    Track First Competitor Target
                  </button>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {displacements.map((item) => {
                    const renewalDaysVal = item.contract_renewal_days || 60;
                    const isPeak = renewalDaysVal >= 45 && renewalDaysVal <= 90;
                    const isUrgent = renewalDaysVal < 45;
                    const vulnScore = item.displacement_vulnerability_score || 75;

                    return (
                      <div
                        key={item.id}
                        className="bg-card border border-border rounded-lg p-4 flex flex-col justify-between hover:bg-muted/20 transition-colors"
                      >
                        <div>
                          {/* Card Top: Company & Vendor */}
                          <div className="flex items-start justify-between gap-2 mb-2">
                            <div>
                              <h4 className="text-sm font-semibold text-foreground">
                                {item.target_company}
                              </h4>
                              <p className="text-xs text-muted-foreground flex items-center gap-1.5 mt-0.5">
                                <User className="w-3.5 h-3.5 text-muted-foreground" />
                                {item.target_contact_name} ({item.target_contact_title})
                              </p>
                            </div>
                            <div className="flex items-center gap-1.5">
                              {Boolean(item.simulated || item.is_simulated || item.id?.startsWith('mock-') || ['NorthStar Logistics', 'CloudMetric Labs', 'SaaSFlow Solutions'].includes(item.target_company)) && (
                                <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-medium bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-500/20">
                                  Simulated Demo
                                </span>
                              )}
                              <span className="px-2 py-0.5 rounded text-[10px] font-medium uppercase tracking-wider bg-muted/40 text-foreground border border-border">
                                {item.incumbent_vendor}
                              </span>
                            </div>
                          </div>

                          {/* Renewal Status & Vulnerability Metric */}
                          <div className="grid grid-cols-2 gap-2 my-3 p-2.5 rounded-lg bg-muted/40 border border-border text-xs">
                            <div>
                              <div className="text-[10px] text-muted-foreground font-medium">Renewal In</div>
                              <div className="flex items-center gap-1.5 mt-0.5">
                                {isPeak ? (
                                  <span className="px-2 py-0.5 rounded font-medium text-[11px] bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-500/20">
                                    {renewalDaysVal}d (Peak Window)
                                  </span>
                                ) : isUrgent ? (
                                  <span className="px-2 py-0.5 rounded font-medium text-[11px] bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-500/20">
                                    {renewalDaysVal}d (Urgent)
                                  </span>
                                ) : (
                                  <span className="px-2 py-0.5 rounded font-medium text-[11px] bg-muted text-muted-foreground border border-border">
                                    {renewalDaysVal}d
                                  </span>
                                )}
                              </div>
                            </div>
                            <div>
                              <div className="text-[10px] text-muted-foreground font-medium">Vulnerability</div>
                              <div className="flex items-center gap-1.5 mt-0.5">
                                <div className="text-xs font-semibold text-foreground">{vulnScore}/100</div>
                                <div className="flex-1 bg-muted h-1.5 rounded-full overflow-hidden">
                                  <div
                                    className={`h-full rounded-full transition-all ${
                                      vulnScore >= 80 ? 'bg-emerald-500' : vulnScore >= 60 ? 'bg-amber-500' : 'bg-primary'
                                    }`}
                                    style={{ width: `${Math.min(100, vulnScore)}%` }}
                                  />
                                </div>
                              </div>
                            </div>
                          </div>

                          {/* Seat count & Savings */}
                          <div className="flex items-center justify-between text-xs text-muted-foreground mb-4 px-1">
                            <span>{item.seat_count || 10} Sales Seats</span>
                            <span className="text-foreground font-semibold">
                              +${Number(item.annual_potential_savings || 0).toLocaleString()}/yr savings
                            </span>
                          </div>
                        </div>

                        {/* Card Actions */}
                        <div className="flex items-center gap-2 pt-2 border-t border-border">
                          <button
                            onClick={() => {
                              setPitchCompany(item.target_company);
                              setPitchContact(item.target_contact_name);
                              setPitchTitle(item.target_contact_title);
                              setPitchVendor(item.incumbent_vendor);
                              setPitchSeats(item.seat_count || 10);
                              setPitchSeatsStr(String(item.seat_count || 10));
                              setPitchDays(item.contract_renewal_days || 60);
                              setPitchDaysStr(String(item.contract_renewal_days || 60));
                              setActiveTab('pitch_studio');
                            }}
                            className="flex-1 py-1.5 px-2 bg-muted/40 hover:bg-muted border border-border text-foreground rounded-lg text-xs font-medium transition-colors text-center"
                          >
                            Craft Pitch
                          </button>
                          <button
                            onClick={() => handleLaunchSequence(item.id, item.target_company)}
                            disabled={launchingId === item.id || item.status === 'displacement_pitched'}
                            className={`flex-1 py-1.5 px-2 rounded-lg text-xs font-medium flex items-center justify-center gap-1.5 transition-colors ${
                              item.status === 'displacement_pitched'
                                ? 'bg-muted text-muted-foreground border border-border'
                                : 'bg-primary hover:bg-primary/90 text-primary-foreground'
                            }`}
                          >
                            {launchingId === item.id ? (
                              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                            ) : item.status === 'displacement_pitched' ? (
                              <>
                                <CheckCircle2 className="w-3.5 h-3.5" />
                                Pitched
                              </>
                            ) : (
                              <>
                                <Rocket className="w-3.5 h-3.5" />
                                Launch
                              </>
                            )}
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* TAB 2: BATTLECARDS & CALCULATOR */}
          {activeTab === 'battlecards' && (
            <div className="space-y-6">
              {/* Vendor Selector Pills */}
              <div className="flex items-center gap-2 overflow-x-auto pb-2 border-b border-border">
                {['apollo', 'outreach', 'salesloft', 'lemlist', 'expandi', 'heyreach'].map((vSlug) => (
                  <button
                    key={vSlug}
                    onClick={() => setSelectedVendorSlug(vSlug)}
                    className={`px-3.5 py-1.5 rounded-lg text-xs font-medium uppercase tracking-wider transition-all ${
                      selectedVendorSlug === vSlug
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-muted/40 border border-border text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    {vSlug === 'apollo' ? 'Apollo.io' : vSlug === 'outreach' ? 'Outreach.io' : vSlug.toUpperCase()}
                  </button>
                ))}
              </div>

              {/* Vendor Battlecard Deep-Dive */}
              {currentBattlecard && (
                <div className="bg-card border border-border rounded-lg p-6 space-y-5">
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
                        {currentBattlecard.vendor_display_name} Displacement Playbook
                      </h3>
                      <p className="text-xs text-muted-foreground mt-1">
                        High-converting objection handling, feature killer points, and zero-risk buyout clauses.
                      </p>
                    </div>
                    <span className="px-2.5 py-1 rounded-md text-xs font-medium bg-muted/40 text-foreground border border-border">
                      Displacement Playbook
                    </span>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="p-4 rounded-lg bg-muted/40 border border-border space-y-2">
                      <div className="flex items-center gap-2 text-foreground font-semibold text-xs uppercase tracking-wider">
                        <AlertTriangle className="w-4 h-4 text-muted-foreground" />
                        Incumbent Technical Vulnerability
                      </div>
                      <p className="text-xs text-muted-foreground leading-relaxed">
                        {currentBattlecard.primary_vulnerability}
                      </p>
                    </div>

                    <div className="p-4 rounded-lg bg-muted/40 border border-border space-y-2">
                      <div className="flex items-center gap-2 text-foreground font-semibold text-xs uppercase tracking-wider">
                        <CheckCircle2 className="w-4 h-4 text-muted-foreground" />
                        Ele-in Killer Advantage
                      </div>
                      <p className="text-xs text-muted-foreground leading-relaxed">
                        {currentBattlecard.elein_killer_advantage}
                      </p>
                    </div>
                  </div>

                  {/* Buyout Clause Card */}
                  <div className="p-4 rounded-lg bg-muted/40 border border-border space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 text-foreground font-semibold text-xs uppercase tracking-wider">
                        <ShieldAlert className="w-4 h-4 text-muted-foreground" />
                        Contract Buyout Credit Offer
                      </div>
                      <button
                        onClick={() => copyToClipboard(currentBattlecard.contract_buyout_offer, 'buyout')}
                        className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors"
                      >
                        {copiedKey === 'buyout' ? <Check className="w-3.5 h-3.5 text-foreground" /> : <Copy className="w-3.5 h-3.5" />}
                        Copy Clause
                      </button>
                    </div>
                    <p className="text-xs text-foreground italic">
                      "{currentBattlecard.contract_buyout_offer}"
                    </p>
                  </div>
                </div>
              )}

              {/* Migration ROI Calculator */}
              <div className="bg-card border border-border rounded-lg p-6 space-y-5">
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="text-sm font-semibold text-foreground">Migration ROI & Budget Savings Calculator</h4>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Compare incumbent license overhead against Ele-in's consolidated $49/seat platform.
                    </p>
                  </div>
                  <button
                    onClick={() => {
                      const text = `Switching from ${selectedVendorSlug.toUpperCase()} to Ele-in saves $${annualSavings.toLocaleString()}/year (${savingsPct}% budget reduction) for a team of ${calcSeats} reps. Ele-in provides 100% contract buyout credits for remaining months.`;
                      copyToClipboard(text, 'calc-summary');
                    }}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-muted/40 hover:bg-muted border border-border text-foreground text-xs font-medium rounded-lg transition-colors"
                  >
                    {copiedKey === 'calc-summary' ? <Check className="w-3.5 h-3.5 text-foreground" /> : <Copy className="w-3.5 h-3.5" />}
                    Copy Pitch Summary
                  </button>
                </div>

                {/* Slider and inputs */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 bg-muted/60 p-4 rounded-lg border border-border">
                  <div className="space-y-2">
                    <div className="flex justify-between text-xs font-medium">
                      <span className="text-muted-foreground">Sales Rep Seats</span>
                      <span className="text-foreground font-semibold">{calcSeats} seats</span>
                    </div>
                    <input
                      type="range"
                      min={1}
                      max={100}
                      value={calcSeats}
                      onChange={(e) => setCalcSeats(Number(e.target.value))}
                      className="w-full accent-primary cursor-pointer"
                    />
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>1 seat</span>
                      <span>50 seats</span>
                      <span>100 seats</span>
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-xs text-muted-foreground font-medium">
                      Incumbent Monthly Price / Seat ($) <span className="text-muted-foreground">(Default: ${incumbentRate}/mo)</span>
                    </label>
                    <input
                      type="number"
                      min={1}
                      placeholder={`$${incumbentRate}`}
                      value={customMonthlyCost}
                      onChange={(e) => setCustomMonthlyCost(e.target.value)}
                      className="w-full bg-background border border-border rounded-lg px-3 py-1.5 text-xs text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    />
                  </div>
                </div>

                {/* Savings Metrics Result Cards */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="p-3.5 rounded-lg bg-muted/60 border border-border">
                    <div className="text-xs text-muted-foreground">Current Tooling Spend</div>
                    <div className="text-base font-semibold text-foreground mt-1">${incumbentAnnual.toLocaleString()} / yr</div>
                    <div className="text-xs text-muted-foreground mt-0.5">${incumbentRate}/seat/mo</div>
                  </div>

                  <div className="p-3.5 rounded-lg bg-muted/60 border border-border">
                    <div className="text-xs text-muted-foreground">Ele-in Consolidated Spend</div>
                    <div className="text-base font-semibold text-foreground mt-1">${eleinAnnual.toLocaleString()} / yr</div>
                    <div className="text-xs text-muted-foreground mt-0.5">$49/seat/mo Flat</div>
                  </div>

                  <div className="p-3.5 rounded-lg bg-muted/60 border border-border">
                    <div className="text-xs text-muted-foreground font-medium">Net Annual Cashflow Saved</div>
                    <div className="text-base font-semibold text-foreground mt-1">+${annualSavings.toLocaleString()} / yr</div>
                    <div className="text-xs text-muted-foreground mt-0.5">{savingsPct}% Budget Reduction</div>
                  </div>

                  <div className="p-3.5 rounded-lg bg-muted/60 border border-border">
                    <div className="text-xs text-muted-foreground font-medium">Contract Buyout Value</div>
                    <div className="text-base font-semibold text-foreground mt-1">${(incumbentRate * calcSeats * 3).toLocaleString()}</div>
                    <div className="text-xs text-muted-foreground mt-0.5">Up to 90 Days Free Credit</div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: PITCH STUDIO */}
          {activeTab === 'pitch_studio' && (
            <div className="space-y-6">
              {/* Pitch Generation Form */}
              <div className="bg-card border border-border rounded-lg p-6 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                    <MessageSquare className="w-4 h-4 text-muted-foreground" />
                    AI Diplomatic Displacement Copywriter
                  </h3>
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground font-medium bg-muted/60 px-2.5 py-1 rounded-md border border-border">
                    <ShieldAlert className="w-3.5 h-3.5" />
                    Layer 2 Libel & Smear Guard Active
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4 text-xs">
                  <div>
                    <label className="text-muted-foreground mb-1 block">Target Company</label>
                    <input
                      type="text"
                      value={pitchCompany}
                      onChange={(e) => setPitchCompany(e.target.value)}
                      className="w-full bg-background border border-border rounded-lg px-3 py-2 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    />
                  </div>
                  <div>
                    <label className="text-muted-foreground mb-1 block">Decision Maker Full Name</label>
                    <input
                      type="text"
                      value={pitchContact}
                      onChange={(e) => setPitchContact(e.target.value)}
                      className="w-full bg-background border border-border rounded-lg px-3 py-2 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    />
                  </div>
                  <div>
                    <label className="text-muted-foreground mb-1 block">Executive Title</label>
                    <input
                      type="text"
                      value={pitchTitle}
                      onChange={(e) => setPitchTitle(e.target.value)}
                      className="w-full bg-background border border-border rounded-lg px-3 py-2 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    />
                  </div>
                  <div>
                    <label className="text-muted-foreground mb-1 block">Incumbent Vendor</label>
                    <Select
                      value={pitchVendor}
                      onValueChange={(val) => setPitchVendor(val)}
                    >
                      <SelectTrigger className="w-full bg-background border-border h-9 text-xs focus-visible:ring-2 focus-visible:ring-ring">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="apollo">Apollo.io</SelectItem>
                        <SelectItem value="outreach">Outreach.io</SelectItem>
                        <SelectItem value="salesloft">Salesloft</SelectItem>
                        <SelectItem value="lemlist">Lemlist</SelectItem>
                        <SelectItem value="expandi">Expandi</SelectItem>
                        <SelectItem value="heyreach">HeyReach</SelectItem>
                        <SelectItem value="other">Other</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <label className="text-muted-foreground mb-1 block">Seat Count</label>
                    <input
                      type="number"
                      min={1}
                      max={5000}
                      value={pitchSeatsStr}
                      onChange={(e) => setPitchSeatsStr(e.target.value)}
                      onBlur={() => {
                        const val = Math.max(1, Math.min(5000, parseInt(pitchSeatsStr, 10) || 1));
                        setPitchSeats(val);
                        setPitchSeatsStr(String(val));
                      }}
                      className="w-full bg-background border border-border rounded-lg px-3 py-2 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    />
                  </div>
                  <div>
                    <label className="text-muted-foreground mb-1 block">Days to Contract Renewal</label>
                    <input
                      type="number"
                      min={1}
                      max={365}
                      value={pitchDaysStr}
                      onChange={(e) => setPitchDaysStr(e.target.value)}
                      onBlur={() => {
                        const val = Math.max(1, Math.min(365, parseInt(pitchDaysStr, 10) || 1));
                        setPitchDays(val);
                        setPitchDaysStr(String(val));
                      }}
                      className="w-full bg-background border border-border rounded-lg px-3 py-2 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    />
                  </div>
                </div>

                <div className="flex justify-end pt-2">
                  <button
                    onClick={handleGeneratePitch}
                    disabled={isGeneratingPitch}
                    className="flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary/90 text-primary-foreground rounded-lg text-xs font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:scale-[0.98]"
                  >
                    {isGeneratingPitch ? (
                      <RefreshCw className="w-4 h-4 animate-spin" />
                    ) : (
                      <MessageSquare className="w-4 h-4" />
                    )}
                    Generate Diplomatic Pitch & Buyout Offer
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary-foreground/20 text-primary-foreground font-semibold">2 Credits</span>
                  </button>
                </div>
              </div>

              {/* Pitch Outputs */}
              {generatedPitch && (() => {
                const liPitch = generatedPitch.linkedin_pitch || generatedPitch.displacement_hook || '';
                const emailPitch = generatedPitch.executive_email_pitch || (
                  generatedPitch.subject
                    ? `Subject: ${generatedPitch.subject}\n\n${generatedPitch.body || ''}`
                    : generatedPitch.body || ''
                );

                return (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* LinkedIn InMail / DM Pitch */}
                    <div className="bg-card border border-border rounded-lg p-5 space-y-3 flex flex-col justify-between">
                      <div>
                        <div className="flex items-center justify-between mb-3">
                          <span className="text-xs font-semibold text-foreground uppercase tracking-wider flex items-center gap-1.5">
                            <Target className="w-4 h-4 text-muted-foreground" />
                            LinkedIn InMail / DM Sequence
                          </span>
                          <div className="flex items-center gap-2">
                            <span className={`text-[11px] font-medium px-2 py-0.5 rounded border ${
                              liPitch.length > 300
                                ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20'
                                : 'bg-muted/60 text-muted-foreground border-border'
                            }`}>
                              {liPitch.length} chars (InMail/DM)
                            </span>
                            <button
                              onClick={() => copyToClipboard(liPitch, 'pitch-li')}
                              aria-label="Copy LinkedIn pitch"
                              className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors p-1 rounded hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            >
                              {copiedKey === 'pitch-li' ? <Check className="w-3.5 h-3.5 text-foreground" /> : <Copy className="w-3.5 h-3.5" />}
                              Copy
                            </button>
                          </div>
                        </div>
                        <div className="bg-background p-4 rounded-lg border border-border text-xs text-foreground leading-relaxed whitespace-pre-wrap font-sans">
                          {liPitch || 'Generating targeted LinkedIn displacement hook...'}
                        </div>
                      </div>
                    </div>

                    {/* Executive Email & Proposal */}
                    <div className="bg-card border border-border rounded-lg p-5 space-y-3 flex flex-col justify-between">
                      <div>
                        <div className="flex items-center justify-between mb-3">
                          <span className="text-xs font-semibold text-foreground uppercase tracking-wider flex items-center gap-1.5">
                            <ShieldAlert className="w-4 h-4 text-muted-foreground" />
                            Executive Buyout Proposal Email
                          </span>
                          <div className="flex items-center gap-2">
                            <span className="text-[11px] font-medium px-2 py-0.5 rounded bg-muted/60 text-muted-foreground border border-border">
                              {emailPitch.split(/\s+/).filter(Boolean).length} words
                            </span>
                            <button
                              onClick={() => copyToClipboard(emailPitch, 'pitch-email')}
                              aria-label="Copy executive proposal email"
                              className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors p-1 rounded hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            >
                              {copiedKey === 'pitch-email' ? <Check className="w-3.5 h-3.5 text-foreground" /> : <Copy className="w-3.5 h-3.5" />}
                              Copy
                            </button>
                          </div>
                        </div>
                        <div className="bg-background p-4 rounded-lg border border-border text-xs text-foreground leading-relaxed whitespace-pre-wrap font-sans">
                          {emailPitch || 'Generating executive buyout proposal email...'}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })()}
            </div>
          )}

        </div>

        {/* ADD COMPETITOR TARGET MODAL */}
        {addModalOpen && (
          <div
            className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm overflow-y-auto"
            onClick={() => setAddModalOpen(false)}
          >
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="track-target-title"
              className="bg-card border border-border rounded-xl max-w-md w-full max-h-[90vh] overflow-y-auto p-6 text-foreground shadow-2xl space-y-4 my-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between border-b border-border pb-3">
                <h3 id="track-target-title" className="text-base font-semibold text-foreground flex items-center gap-2">
                  <Target className="w-4 h-4 text-muted-foreground" />
                  Track Competitor Incumbent Target
                </h3>
                <button
                  onClick={() => setAddModalOpen(false)}
                  aria-label="Close track target dialog"
                  className="p-1.5 text-muted-foreground hover:text-foreground bg-muted/60 hover:bg-muted border border-border rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <form onSubmit={handleCreateDisplacement} className="space-y-3 text-xs">
                <div>
                  <label className="text-muted-foreground mb-1 block font-medium">Company Name *</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Ramp, Gusto, Notion"
                    value={targetCompany}
                    onChange={(e) => setTargetCompany(e.target.value)}
                    className="w-full bg-background border border-border rounded-lg px-3 py-2 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-muted-foreground mb-1 block font-medium">Contact Full Name *</label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. Alex Morgan"
                      value={targetContactName}
                      onChange={(e) => setTargetContactName(e.target.value)}
                      className="w-full bg-background border border-border rounded-lg px-3 py-2 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    />
                  </div>
                  <div>
                    <label className="text-muted-foreground mb-1 block font-medium">Job Title</label>
                    <input
                      type="text"
                      placeholder="e.g. VP Sales, RevOps"
                      value={targetContactTitle}
                      onChange={(e) => setTargetContactTitle(e.target.value)}
                      className="w-full bg-background border border-border rounded-lg px-3 py-2 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-muted-foreground mb-1 block font-medium">Incumbent Vendor</label>
                    <Select
                      value={incumbentVendor}
                      onValueChange={(val) => setIncumbentVendor(val)}
                    >
                      <SelectTrigger className="w-full bg-background border-border h-9 text-xs focus-visible:ring-2 focus-visible:ring-ring">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="apollo">Apollo.io</SelectItem>
                        <SelectItem value="outreach">Outreach.io</SelectItem>
                        <SelectItem value="salesloft">Salesloft</SelectItem>
                        <SelectItem value="lemlist">Lemlist</SelectItem>
                        <SelectItem value="expandi">Expandi</SelectItem>
                        <SelectItem value="heyreach">HeyReach</SelectItem>
                        <SelectItem value="other">Other</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <label className="text-muted-foreground mb-1 block font-medium">Domain</label>
                    <input
                      type="text"
                      placeholder="e.g. company.com"
                      value={domain}
                      onChange={(e) => setDomain(e.target.value)}
                      className="w-full bg-background border border-border rounded-lg px-3 py-2 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-muted-foreground mb-1 block font-medium">Seat Count</label>
                    <input
                      type="number"
                      min={1}
                      max={5000}
                      value={seatCountStr}
                      onChange={(e) => setSeatCountStr(e.target.value)}
                      onBlur={() => {
                        const val = Math.max(1, Math.min(5000, parseInt(seatCountStr, 10) || 1));
                        setSeatCount(val);
                        setSeatCountStr(String(val));
                      }}
                      className="w-full bg-background border border-border rounded-lg px-3 py-2 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    />
                  </div>
                  <div>
                    <label className="text-muted-foreground mb-1 block font-medium">Days to Contract Renewal</label>
                    <input
                      type="number"
                      min={1}
                      max={365}
                      value={renewalDaysStr}
                      onChange={(e) => setRenewalDaysStr(e.target.value)}
                      onBlur={() => {
                        const val = Math.max(1, Math.min(365, parseInt(renewalDaysStr, 10) || 1));
                        setRenewalDays(val);
                        setRenewalDaysStr(String(val));
                      }}
                      className="w-full bg-background border border-border rounded-lg px-3 py-2 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    />
                  </div>
                </div>

                <div className="flex justify-end gap-2 pt-3">
                  <button
                    type="button"
                    onClick={() => setAddModalOpen(false)}
                    className="px-4 py-2 bg-muted/60 hover:bg-muted border border-border text-muted-foreground hover:text-foreground rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isCreating}
                    className="px-4 py-2 bg-primary hover:bg-primary/90 text-primary-foreground rounded-lg font-medium flex items-center gap-1.5 transition-colors disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:scale-[0.98]"
                  >
                    {isCreating ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
                    Track Target
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
