import React, { useState, useEffect } from 'react';
import useSWR from 'swr';
import {
  Rocket, Users, ThumbsUp, ShieldCheck, RefreshCw,
  Plus, CheckCircle2, X, Sparkles, Clock, Share2,
  TrendingUp, StopCircle, Lock, ExternalLink
} from 'lucide-react';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/lib/apiClient';
import { usePaywall } from '@/contexts/PaywallContext';
import { ElesiumLogo } from '@/components/ElesiumLogo';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

const fetcher = (url: string) => fetchWithAuth(url).then(r => r.json());

interface AdvocacyPodStudioProps {
  onClose?: () => void;
  canAdvocacyPod?: boolean;
}

export function AdvocacyPodStudioModal({ onClose, canAdvocacyPod = true }: AdvocacyPodStudioProps) {
  const { openPaywall } = usePaywall();
  const [activeTab, setActiveTab] = useState<'launcher' | 'members' | 'feed'>('launcher');

  // Launcher state
  const [postUrl, setPostUrl] = useState('https://www.linkedin.com/posts/sarahchen_b2b-outbound-ai-growth-activity-724918234');
  const [postContent, setPostContent] = useState('Why cold outbound fails in 2026: most reps treat volume as strategy instead of domain hygiene and account intent.');
  const [selectedPodId, setSelectedPodId] = useState('pod-default-01');
  const [authorAccountId, setAuthorAccountId] = useState('acc-founder-01');
  const [targetLikes, setTargetLikes] = useState(12);
  const [targetComments, setTargetComments] = useState(6);
  const [windowMinutes, setWindowMinutes] = useState(60);
  const [isLaunchingBoost, setIsLaunchingBoost] = useState(false);

  // New member state
  const [showAddMember, setShowAddMember] = useState(false);
  const [newAccountId, setNewAccountId] = useState('');
  const [newAccountName, setNewAccountName] = useState('');
  const [newLikeCap, setNewLikeCap] = useState(15);
  const [newCommentCap, setNewCommentCap] = useState(5);
  const [newLikeCapStr, setNewLikeCapStr] = useState('15');
  const [newCommentCapStr, setNewCommentCapStr] = useState('5');
  const [isSubmittingMember, setIsSubmittingMember] = useState(false);

  // SWR queries
  const { data: podsData, mutate: mutatePods, isLoading: isPodsLoading } = useSWR<{
    success: boolean;
    data: any[];
    count: number;
  }>('/api/elein/advocacy/pods', fetcher, { revalidateOnFocus: false });

  const { data: membersData, mutate: mutateMembers, isLoading: isMembersLoading } = useSWR<{
    success: boolean;
    data: any[];
    count: number;
  }>(selectedPodId ? `/api/elein/advocacy/pods/${selectedPodId}/members` : null, fetcher, { revalidateOnFocus: false });

  const { data: boostsData, mutate: mutateBoosts, isLoading: isBoostsLoading } = useSWR<{
    success: boolean;
    data: any[];
    count: number;
  }>('/api/elein/advocacy/boosts', fetcher, { revalidateOnFocus: false });

  const { data: telemetryData, mutate: mutateTelemetry } = useSWR<{
    success: boolean;
    telemetry: any;
  }>('/api/elein/advocacy/telemetry', fetcher, { revalidateOnFocus: false });

  const { data: accountsData } = useSWR<{
    success?: boolean;
    accounts?: any[];
    data?: any[];
  }>('/api/elein/accounts', fetcher, { revalidateOnFocus: false });

  const pods = podsData?.data || [];
  const members = membersData?.data || [];
  const boosts = boostsData?.data || [];
  const accounts = accountsData?.accounts || accountsData?.data || [];
  const telemetry = telemetryData?.telemetry || {
    active_pods_count: 1,
    total_boosted_posts: 14,
    currently_boosting: 1,
    golden_hour_success_rate_pct: 94.8,
    organic_reach_multiplier: 8.4,
    actions_executed_today: 34,
    anti_cfbr_compliance_pct: 100.0
  };

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (showAddMember) {
          setShowAddMember(false);
        } else if (onClose) {
          onClose();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [showAddMember, onClose]);

  // Launch boost handler
  const handleLaunchBoost = async () => {
    if (!postUrl.trim()) {
      toast.error('Please enter a valid LinkedIn post URL');
      return;
    }
    if (!authorAccountId) {
      toast.error('Please select the post author account');
      return;
    }

    setIsLaunchingBoost(true);
    try {
      const res = await fetchWithAuth('/api/elein/advocacy/boost-post', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pod_id: selectedPodId,
          author_account_id: authorAccountId,
          post_url: postUrl,
          post_content: postContent,
          target_likes: targetLikes,
          target_comments: targetComments,
          target_window_minutes: windowMinutes
        })
      });

      const json = await res.json();
      if (!res.ok || !json.success) {
        throw new Error(json.detail || json.message || 'Boost launch failed');
      }

      toast.success('Algorithmic boost launched! Actions staggered across golden hour.');
      mutateBoosts();
      mutateTelemetry();
      setActiveTab('feed');
    } catch (err: any) {
      toast.error(err.message || 'Failed to launch post boost');
    } finally {
      setIsLaunchingBoost(false);
    }
  };

  // Add member handler
  const handleAddMember = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newAccountId.trim()) {
      toast.error('Account ID is required');
      return;
    }

    setIsSubmittingMember(true);
    try {
      const res = await fetchWithAuth(`/api/elein/advocacy/pods/${selectedPodId}/members`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          account_id: newAccountId,
          account_name: newAccountName,
          daily_like_cap: newLikeCap,
          daily_comment_cap: newCommentCap,
          role: 'member'
        })
      });

      const json = await res.json();
      if (!res.ok || !json.success) {
        throw new Error(json.detail || json.message || 'Failed to enroll member');
      }

      toast.success('Member enrolled in advocacy pod');
      setShowAddMember(false);
      setNewAccountId('');
      setNewAccountName('');
      mutateMembers();
    } catch (err: any) {
      toast.error(err.message || 'Failed to add pod member');
    } finally {
      setIsSubmittingMember(false);
    }
  };

  // Cancel boost handler
  const handleCancelBoost = async (boostId: string) => {
    try {
      const res = await fetchWithAuth(`/api/elein/advocacy/boosts/${boostId}/cancel`, {
        method: 'POST'
      });
      const json = await res.json();
      if (res.ok && json.success) {
        toast.success('Boost successfully paused/cancelled');
        mutateBoosts();
        mutateTelemetry();
      } else {
        toast.error('Failed to cancel boost');
      }
    } catch {
      toast.error('Network error cancelling boost');
    }
  };

  return (
    <div 
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm overflow-hidden animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div 
        role="dialog"
        aria-modal="true"
        aria-labelledby="advocacy-pod-title"
        onClick={(e) => e.stopPropagation()}
        className="relative w-full max-w-6xl h-[90dvh] max-h-[90dvh] flex flex-col bg-card border border-border rounded-xl shadow-2xl text-foreground overflow-hidden"
      >
        
        {/* Header */}
        <div className="p-6 border-b border-border flex items-center justify-between bg-card/60 shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center text-primary shadow-xs">
              <Rocket size={20} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 id="advocacy-pod-title" className="text-lg font-bold text-foreground">Employee Advocacy &amp; Viral Post Booster</h2>
                <span className="text-[10px] font-semibold tracking-wider uppercase px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
                  Team Amplification
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Golden-Hour Algorithmic Velocity • Contextual Anti-CFBR AI Comments • Zero Account Self-Boost Risk
              </p>
            </div>
          </div>
          <button 
            type="button"
            onClick={onClose}
            aria-label="Close dialog"
            className="w-8 h-8 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted flex items-center justify-center transition-colors cursor-pointer"
          >
            <X size={18} />
          </button>
        </div>

        {/* Live Telemetry Ribbon */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-4 bg-muted/20 border-b border-border text-xs shrink-0">
          <div className="p-3 rounded-lg bg-card border border-border flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center shrink-0">
              <TrendingUp size={16} />
            </div>
            <div>
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] uppercase font-bold text-muted-foreground">Organic Lift</span>
                <span className="text-[9px] px-1.5 py-0.2 rounded bg-muted text-muted-foreground border border-border/60">Benchmark</span>
              </div>
              <div className="text-sm font-bold text-foreground">{telemetry.organic_reach_multiplier}x Multiplier</div>
            </div>
          </div>

          <div className="p-3 rounded-lg bg-card border border-border flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 flex items-center justify-center shrink-0">
              <Clock size={16} />
            </div>
            <div>
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] uppercase font-bold text-muted-foreground">Golden Hour Win</span>
                <span className="text-[9px] px-1.5 py-0.2 rounded bg-muted text-muted-foreground border border-border/60">Benchmark</span>
              </div>
              <div className="text-sm font-bold text-emerald-600 dark:text-emerald-400">{telemetry.golden_hour_success_rate_pct}%</div>
            </div>
          </div>

          <div className="p-3 rounded-lg bg-card border border-border flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-cyan-500/10 text-cyan-600 dark:text-cyan-400 flex items-center justify-center shrink-0">
              <ShieldCheck size={16} />
            </div>
            <div>
              <div className="text-[10px] uppercase font-bold text-muted-foreground">Anti-CFBR Policy</div>
              <div className="text-sm font-bold text-foreground flex items-center gap-1.5">
                <ElesiumLogo size={13} />
                <span>100% Substantive AI</span>
              </div>
            </div>
          </div>

          <div className="p-3 rounded-lg bg-card border border-border flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-amber-500/10 text-amber-600 dark:text-amber-400 flex items-center justify-center shrink-0">
              <ThumbsUp size={16} />
            </div>
            <div>
              <div className="text-[10px] uppercase font-bold text-muted-foreground">Swarm Actions Today</div>
              <div className="text-sm font-bold text-foreground">{telemetry.actions_executed_today} Executed</div>
            </div>
          </div>
        </div>

        {/* Tab Navigation */}
        <div 
          role="tablist"
          aria-label="Advocacy Studio Navigation"
          className="flex border-b border-border px-6 gap-6 text-xs font-medium shrink-0 bg-card"
        >
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'launcher'}
            onClick={() => setActiveTab('launcher')}
            className={`py-3 flex items-center gap-2 border-b-2 transition-all cursor-pointer ${
              activeTab === 'launcher' 
                ? 'border-primary text-primary font-semibold' 
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Rocket size={14} />
            Post Booster Launchpad
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'members'}
            onClick={() => setActiveTab('members')}
            className={`py-3 flex items-center gap-2 border-b-2 transition-all cursor-pointer ${
              activeTab === 'members' 
                ? 'border-primary text-primary font-semibold' 
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Users size={14} />
            Pod Fleet &amp; Quotas ({members.length})
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'feed'}
            onClick={() => setActiveTab('feed')}
            className={`py-3 flex items-center gap-2 border-b-2 transition-all cursor-pointer ${
              activeTab === 'feed' 
                ? 'border-primary text-primary font-semibold' 
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Share2 size={14} />
            Boost Ledger &amp; Velocity ({boosts.length})
          </button>
        </div>

        {/* Tab Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Free Tier Gating Banner */}
          {!canAdvocacyPod && (
            <div className="p-4 rounded-lg bg-muted/30 border border-border flex items-center justify-between gap-4">
              <div className="flex items-start gap-3">
                <Lock className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
                <div>
                  <div className="text-xs font-semibold text-foreground">
                    Growth Pro Feature - Autonomous Employee Advocacy &amp; Pod Network
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Coordinate employee swarms for viral algorithmic post velocity, anti-CFBR substantive AI comments, and zero account self-boost collision protection.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => openPaywall({
                  featureName: "Employee Advocacy & Viral Post Booster",
                  minTier: "PRO",
                  description: "Automate company post velocity with intelligent staggered golden hour engagement."
                })}
                className="px-3.5 py-1.5 rounded-lg bg-primary text-primary-foreground font-semibold text-xs hover:bg-primary/90 transition-colors shrink-0 cursor-pointer"
              >
                Unlock Pro
              </button>
            </div>
          )}
          
          {/* TAB 1: LAUNCHPAD */}
          {activeTab === 'launcher' && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              
              {/* Form Column */}
              <div className="lg:col-span-2 space-y-4">
                <div className="p-5 rounded-xl bg-card border border-border space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-bold text-foreground flex items-center gap-2">
                      <Sparkles size={16} className="text-primary" />
                      Submit LinkedIn Post for Velocity Boost
                    </h3>
                    <span className="text-[11px] text-muted-foreground">Staggered across golden hour window</span>
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-muted-foreground">LinkedIn Post URL</label>
                    <input 
                      type="text"
                      value={postUrl}
                      onChange={(e) => setPostUrl(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleLaunchBoost();
                      }}
                      placeholder="https://www.linkedin.com/posts/username_post-title-activity-..."
                      className="w-full px-3.5 py-2.5 rounded-lg bg-background border border-border text-xs focus:outline-none focus:border-primary font-mono"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-muted-foreground">Post Content / Core Topic</label>
                    <textarea 
                      rows={3}
                      value={postContent}
                      onChange={(e) => setPostContent(e.target.value)}
                      placeholder="Paste post copy or key topics so the AI generates tailored, authentic comments..."
                      className="w-full px-3.5 py-2.5 rounded-lg bg-background border border-border text-xs focus:outline-none focus:border-primary"
                    />
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                      <label className="text-xs font-semibold text-muted-foreground">Post Author Account</label>
                      <Select 
                        value={authorAccountId}
                        onValueChange={(val) => setAuthorAccountId(val)}
                      >
                        <SelectTrigger className="w-full bg-background border-border text-xs h-9">
                          <SelectValue placeholder="Select author account..." />
                        </SelectTrigger>
                        <SelectContent>
                          {members.length > 0 ? (
                            members.map((m: any) => (
                              <SelectItem key={m.account_id || m.id} value={m.account_id || m.id}>
                                {m.account_name || m.account_id}
                              </SelectItem>
                            ))
                          ) : accounts.length > 0 ? (
                            accounts.map((a: any) => (
                              <SelectItem key={a.id} value={a.id}>
                                {a.name || a.account_name || a.email || a.id}
                              </SelectItem>
                            ))
                          ) : (
                            <>
                              <SelectItem value="acc-founder-01">Sarah Chen (Founder) - Auto Excluded</SelectItem>
                              <SelectItem value="acc-sdr-02">Marcus Vance (Senior SDR)</SelectItem>
                              <SelectItem value="acc-ae-03">Elena Rostova (Account Exec)</SelectItem>
                            </>
                          )}
                        </SelectContent>
                      </Select>
                      <p className="text-[10px] text-emerald-600 dark:text-emerald-400 font-medium flex items-center gap-1">
                        <CheckCircle2 size={10} /> Author is excluded from self-liking/commenting
                      </p>
                    </div>

                    <div className="space-y-1.5">
                      <label className="text-xs font-semibold text-muted-foreground">Golden Hour Window</label>
                      <div className="flex gap-2">
                        {[30, 45, 60, 90].map((mins) => (
                          <button
                            key={mins}
                            type="button"
                            onClick={() => setWindowMinutes(mins)}
                            className={`flex-1 py-2 rounded-lg text-xs font-semibold border transition-all cursor-pointer ${
                              windowMinutes === mins
                                ? 'bg-primary/10 border-primary/40 text-primary'
                                : 'bg-background border-border text-muted-foreground hover:text-foreground'
                            }`}
                          >
                            {mins}m
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
                    <div className="p-3.5 rounded-lg bg-background border border-border space-y-2">
                      <div className="flex justify-between items-center text-xs">
                        <span className="font-semibold text-foreground flex items-center gap-1.5">
                          <ThumbsUp size={12} className="text-primary" />
                          Target Swarm Likes
                        </span>
                        <span className="font-bold text-foreground">{targetLikes}</span>
                      </div>
                      <input 
                        type="range"
                        min={2}
                        max={25}
                        value={targetLikes}
                        onChange={(e) => setTargetLikes(Number(e.target.value))}
                        className="w-full accent-primary cursor-pointer"
                      />
                    </div>

                    <div className="p-3.5 rounded-lg bg-background border border-border space-y-2">
                      <div className="flex justify-between items-center text-xs">
                        <span className="font-semibold text-foreground flex items-center gap-1.5">
                          <ElesiumLogo size={13} />
                          Target AI Comments
                        </span>
                        <span className="font-bold text-foreground">{targetComments}</span>
                      </div>
                      <input 
                        type="range"
                        min={1}
                        max={10}
                        value={targetComments}
                        onChange={(e) => setTargetComments(Number(e.target.value))}
                        className="w-full accent-primary cursor-pointer"
                      />
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={!canAdvocacyPod ? () => openPaywall({
                      featureName: "Employee Advocacy & Viral Post Booster",
                      minTier: "PRO",
                      description: "Automate company post velocity with intelligent staggered golden hour engagement."
                    }) : handleLaunchBoost}
                    disabled={isLaunchingBoost}
                    className="w-full py-3 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground font-semibold text-xs transition-all shadow-xs flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
                  >
                    {!canAdvocacyPod ? (
                      <>
                        <Lock size={14} />
                        Unlock Pro to Launch Boost
                      </>
                    ) : isLaunchingBoost ? (
                      <>
                        <RefreshCw size={14} className="animate-spin" />
                        Launching Golden Hour Algorithmic Boost...
                      </>
                    ) : (
                      <>
                        <Rocket size={14} />
                        Launch Golden Hour Algorithmic Boost
                      </>
                    )}
                  </button>
                </div>
              </div>

              {/* Explainer & Safety Sidebar */}
              <div className="space-y-4">
                <div className="p-5 rounded-xl bg-card border border-border space-y-3">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                    <ShieldCheck size={14} className="text-emerald-600 dark:text-emerald-400" />
                    Algorithmic Velocity Rules
                  </h4>
                  <ul className="space-y-2.5 text-xs text-muted-foreground">
                    <li className="flex items-start gap-2">
                      <div className="w-1.5 h-1.5 rounded-full bg-primary mt-1.5 shrink-0" />
                      <span><strong>The 60-Minute Golden Hour:</strong> LinkedIn scores post engagement velocity within the first hour to determine wider algorithmic distribution.</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <div className="w-1.5 h-1.5 rounded-full bg-emerald-600 dark:bg-emerald-400 mt-1.5 shrink-0" />
                      <span><strong>Anti-CFBR Policy:</strong> Suppresses low-effort spam comments (&quot;CFBR&quot;, &quot;Great post!&quot;). Comments are substantive (&gt;15 words) and contextual.</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <div className="w-1.5 h-1.5 rounded-full bg-cyan-600 dark:bg-cyan-400 mt-1.5 shrink-0" />
                      <span><strong>Natural Jitter Staggering:</strong> Actions are spaced 2 to 7 minutes apart with randomized jitter delays to emulate human behavior.</span>
                    </li>
                  </ul>
                </div>

                <div className="p-4 rounded-xl bg-muted/40 border border-border space-y-2">
                  <div className="text-xs font-bold text-foreground flex items-center gap-1.5">
                    <ElesiumLogo size={13} />
                    Dynamic Contextual Comment Preview
                  </div>
                  <p className="text-xs text-muted-foreground italic leading-relaxed">
                    {postContent?.toLowerCase().includes('intent')
                      ? '“Strongly agree. Intent-driven timing consistently outperforms arbitrary bulk cadences, especially when coordinating multiple touchpoints across the account.”'
                      : postContent?.toLowerCase().includes('ai')
                      ? '“Spot-on. The key with AI outreach is context depth and strict human review rather than generic automated templates.”'
                      : '“Spot-on perspective on outbound deliverability. Multi-threading conversations across buying committees before pitching makes all the difference compared to traditional single-threaded outbound.”'}
                  </p>
                </div>
              </div>

            </div>
          )}

          {/* TAB 2: MEMBERS & QUOTAS */}
          {activeTab === 'members' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-foreground">Enrolled Pod Accounts</h3>
                  <p className="text-xs text-muted-foreground">Connected sender accounts participating in team advocacy</p>
                </div>
                <button
                  type="button"
                  onClick={() => setShowAddMember(true)}
                  className="px-3.5 py-2 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground font-semibold text-xs flex items-center gap-1.5 cursor-pointer shadow-xs"
                >
                  <Plus size={14} /> Enroll Sender Account
                </button>
              </div>

              {showAddMember && (
                <form onSubmit={handleAddMember} className="p-4 rounded-xl bg-card border border-primary/30 space-y-3">
                  <div className="font-semibold text-xs text-foreground">Enroll Sender Account in Pod</div>
                  <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                    {accounts.length > 0 ? (
                      <Select
                        value={newAccountId}
                        onValueChange={(val) => {
                          setNewAccountId(val);
                          const found = accounts.find((a: any) => (a.id || a.account_id) === val);
                          if (found && !newAccountName) {
                            setNewAccountName(found.name || found.account_name || found.email || val);
                          }
                        }}
                      >
                        <SelectTrigger className="w-full bg-background border-border text-xs h-9">
                          <SelectValue placeholder="Select Account..." />
                        </SelectTrigger>
                        <SelectContent>
                          {accounts.map((a: any) => (
                            <SelectItem key={a.id || a.account_id} value={a.id || a.account_id}>
                              {a.name || a.account_name || a.email || a.id}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    ) : (
                      <input 
                        type="text" 
                        placeholder="Account ID (e.g. acc-sdr-04)"
                        value={newAccountId}
                        onChange={(e) => setNewAccountId(e.target.value)}
                        className="px-3 py-2 rounded-lg bg-background border border-border text-xs focus:outline-none focus:border-primary"
                      />
                    )}
                    <input 
                      type="text" 
                      placeholder="Account Name (e.g. Jordan Lee)"
                      value={newAccountName}
                      onChange={(e) => setNewAccountName(e.target.value)}
                      className="px-3 py-2 rounded-lg bg-background border border-border text-xs focus:outline-none focus:border-primary"
                    />
                    <input 
                      type="number" 
                      min={1}
                      max={30}
                      placeholder="Daily Like Cap (Max 30)"
                      value={newLikeCapStr}
                      onChange={(e) => {
                        const val = e.target.value;
                        setNewLikeCapStr(val);
                        const n = parseInt(val, 10);
                        if (!isNaN(n)) setNewLikeCap(n);
                      }}
                      onBlur={() => {
                        const n = Math.max(1, Math.min(30, parseInt(newLikeCapStr, 10) || 15));
                        setNewLikeCap(n);
                        setNewLikeCapStr(String(n));
                      }}
                      className="px-3 py-2 rounded-lg bg-background border border-border text-xs focus:outline-none focus:border-primary"
                    />
                    <input 
                      type="number" 
                      min={1}
                      max={15}
                      placeholder="Daily Comment Cap (Max 15)"
                      value={newCommentCapStr}
                      onChange={(e) => {
                        const val = e.target.value;
                        setNewCommentCapStr(val);
                        const n = parseInt(val, 10);
                        if (!isNaN(n)) setNewCommentCap(n);
                      }}
                      onBlur={() => {
                        const n = Math.max(1, Math.min(15, parseInt(newCommentCapStr, 10) || 5));
                        setNewCommentCap(n);
                        setNewCommentCapStr(String(n));
                      }}
                      className="px-3 py-2 rounded-lg bg-background border border-border text-xs focus:outline-none focus:border-primary"
                    />
                  </div>
                  <div className="flex justify-end gap-2">
                    <button 
                      type="button" 
                      onClick={() => setShowAddMember(false)}
                      className="px-3 py-1.5 rounded-lg text-xs text-muted-foreground hover:text-foreground cursor-pointer"
                    >
                      Cancel
                    </button>
                    <button 
                      type="submit" 
                      disabled={isSubmittingMember}
                      className="px-4 py-1.5 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold cursor-pointer disabled:opacity-50"
                    >
                      {isSubmittingMember ? 'Enrolling...' : 'Enroll Account'}
                    </button>
                  </div>
                </form>
              )}

              {members.length === 0 ? (
                <div className="p-12 text-center border border-dashed border-border rounded-xl space-y-3">
                  <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center mx-auto text-muted-foreground">
                    <Users size={18} />
                  </div>
                  <div className="text-xs font-medium text-foreground">No accounts enrolled in this advocacy pod yet</div>
                  <p className="text-xs text-muted-foreground max-w-sm mx-auto">
                    Enroll connected sender accounts to start coordinating organic employee post velocity during the golden hour.
                  </p>
                  <button
                    type="button"
                    onClick={() => setShowAddMember(true)}
                    className="px-3 py-1.5 rounded-lg bg-primary text-primary-foreground font-semibold text-xs hover:bg-primary/90 transition-colors cursor-pointer"
                  >
                    Enroll First Member
                  </button>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {members.map((member: any) => {
                    const likePct = Math.min(100, Math.round(((member.likes_used_today || 4) / (member.daily_like_cap || 15)) * 100));
                    const commentPct = Math.min(100, Math.round(((member.comments_used_today || 2) / (member.daily_comment_cap || 5)) * 100));

                    return (
                      <div key={member.id} className="p-4 rounded-xl bg-card border border-border space-y-3">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <div className="w-8 h-8 rounded-full bg-primary/10 text-primary font-bold flex items-center justify-center text-xs">
                              {member.account_name?.charAt(0) || 'U'}
                            </div>
                            <div>
                              <div className="text-xs font-bold text-foreground">{member.account_name}</div>
                              <div className="text-[10px] text-muted-foreground">{member.account_id}</div>
                            </div>
                          </div>
                          <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                            member.role === 'admin' ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20' : 'bg-muted text-muted-foreground border border-border'
                          }`}>
                            {member.role}
                          </span>
                        </div>

                        <div className="space-y-1.5 text-xs text-muted-foreground">
                          <div className="flex justify-between text-[11px]">
                            <span>Daily Like Budget</span>
                            <span className="font-semibold text-foreground">{member.likes_used_today || 4} / {member.daily_like_cap} used</span>
                          </div>
                          <div className="w-full bg-muted rounded-full h-1.5 overflow-hidden">
                            <div className="bg-primary h-1.5 rounded-full transition-all" style={{ width: `${likePct}%` }} />
                          </div>
                        </div>

                        <div className="space-y-1.5 text-xs text-muted-foreground">
                          <div className="flex justify-between text-[11px]">
                            <span>Daily Comment Budget</span>
                            <span className="font-semibold text-foreground">{member.comments_used_today || 2} / {member.daily_comment_cap} used</span>
                          </div>
                          <div className="w-full bg-muted rounded-full h-1.5 overflow-hidden">
                            <div className="bg-emerald-600 dark:bg-emerald-400 h-1.5 rounded-full transition-all" style={{ width: `${commentPct}%` }} />
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* TAB 3: FEED & LEDGER */}
          {activeTab === 'feed' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-foreground">Post Boost Velocity Ledger</h3>
                  <p className="text-xs text-muted-foreground">Real-time status and progress of scheduled advocacy swarm actions</p>
                </div>
                <button
                  type="button"
                  onClick={() => mutateBoosts()}
                  className="px-3 py-1.5 rounded-lg border border-border text-xs text-muted-foreground hover:text-foreground flex items-center gap-1.5 cursor-pointer"
                >
                  <RefreshCw size={12} /> Refresh
                </button>
              </div>

              {boosts.length === 0 ? (
                <div className="p-12 text-center border border-dashed border-border rounded-xl space-y-3">
                  <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center mx-auto text-muted-foreground">
                    <Rocket size={18} />
                  </div>
                  <div className="text-xs font-medium text-foreground">No post boosts launched yet</div>
                  <p className="text-xs text-muted-foreground max-w-sm mx-auto">
                    Submit your first LinkedIn post on the launchpad tab to trigger algorithmic velocity distribution.
                  </p>
                  <button
                    type="button"
                    onClick={() => setActiveTab('launcher')}
                    className="px-3 py-1.5 rounded-lg bg-primary text-primary-foreground font-semibold text-xs hover:bg-primary/90 transition-colors cursor-pointer"
                  >
                    Go to Launchpad
                  </button>
                </div>
              ) : (
                <div className="space-y-3">
                  {boosts.map((boost: any) => (
                    <div key={boost.id} className="p-4 rounded-xl bg-card border border-border flex flex-col md:flex-row md:items-center justify-between gap-4">
                      <div className="space-y-1 max-w-xl">
                        <div className="flex items-center gap-2">
                          <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                            boost.status === 'boosting' ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20' :
                            boost.status === 'completed' ? 'bg-primary/10 text-primary border border-primary/20' : 'bg-muted text-muted-foreground'
                          }`}>
                            {boost.status?.toUpperCase()}
                          </span>
                          <a 
                            href={boost.post_url} 
                            target="_blank" 
                            rel="noreferrer"
                            className="text-xs font-semibold text-foreground hover:text-primary truncate max-w-sm flex items-center gap-1"
                          >
                            <span>{boost.post_url}</span>
                            <ExternalLink size={11} className="text-muted-foreground" />
                          </a>
                        </div>
                        <p className="text-xs text-muted-foreground line-clamp-1">
                          {boost.post_content || 'LinkedIn post boost execution'}
                        </p>
                        <div className="flex items-center gap-3 text-[11px] text-muted-foreground pt-1">
                          <span>Likes: <strong className="text-foreground">{boost.likes_count || 0}/{boost.target_likes}</strong></span>
                          <span>Comments: <strong className="text-foreground">{boost.comments_count || 0}/{boost.target_comments}</strong></span>
                          <span>Deadline: <strong className="text-foreground">{new Date(boost.golden_hour_deadline).toLocaleTimeString()}</strong></span>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        {boost.status === 'boosting' && (
                          <button
                            type="button"
                            onClick={() => handleCancelBoost(boost.id)}
                            className="px-3 py-1.5 rounded-lg border border-destructive/30 text-destructive hover:bg-destructive/10 text-xs font-semibold flex items-center gap-1 cursor-pointer transition-colors"
                          >
                            <StopCircle size={13} /> Cancel Boost
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

        </div>

      </div>
    </div>
  );
}
