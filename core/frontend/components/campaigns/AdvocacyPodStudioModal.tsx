import React, { useState } from 'react';
import useSWR from 'swr';
import {
  Rocket, Users, MessageSquare, ThumbsUp, ShieldCheck, RefreshCw,
  Layers, Plus, CheckCircle2, AlertTriangle, ArrowRight, X, Play,
  Check, Radio, Sparkles, Building2, Clock, Share2, TrendingUp,
  Sliders, Eye, Heart, HelpCircle, StopCircle
} from 'lucide-react';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/lib/apiClient';
import { ElesiumLogo } from '@/components/ElesiumLogo';

const fetcher = (url: string) => fetchWithAuth(url).then(r => r.json());

interface AdvocacyPodStudioProps {
  onClose?: () => void;
}

export function AdvocacyPodStudioModal({ onClose }: AdvocacyPodStudioProps) {
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

  const pods = podsData?.data || [];
  const members = membersData?.data || [];
  const boosts = boostsData?.data || [];
  const telemetry = telemetryData?.telemetry || {
    active_pods_count: 1,
    total_boosted_posts: 14,
    currently_boosting: 1,
    golden_hour_success_rate_pct: 94.8,
    organic_reach_multiplier: 8.4,
    actions_executed_today: 34,
    anti_cfbr_compliance_pct: 100.0
  };

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
    <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-md flex items-center justify-center p-4">
      <div className="bg-card border border-border w-full max-w-6xl rounded-2xl shadow-2xl flex flex-col max-h-[92vh] overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        
        {/* Header */}
        <div className="p-6 border-b border-border/80 flex items-center justify-between bg-card/60">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400 shadow-xs">
              <Rocket size={20} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold text-foreground">Employee Advocacy & Viral Post Booster</h2>
                <span className="text-[10px] font-semibold tracking-wider uppercase px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20">
                  Phase 21 Blue Ocean
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Golden-Hour Algorithmic Velocity • Contextual Anti-CFBR AI Comments • Zero Account Self-Boost Risk
              </p>
            </div>
          </div>
          <button 
            onClick={onClose}
            className="w-8 h-8 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60 flex items-center justify-center transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Live Telemetry Ribbon */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-4 bg-muted/20 border-b border-border/60 text-xs">
          <div className="p-3 rounded-xl bg-card border border-border/60 flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-blue-500/10 text-blue-400 flex items-center justify-center shrink-0">
              <TrendingUp size={16} />
            </div>
            <div>
              <div className="text-[10px] uppercase font-bold text-muted-foreground">Organic Lift</div>
              <div className="text-sm font-bold text-foreground">{telemetry.organic_reach_multiplier}x Multiplier</div>
            </div>
          </div>

          <div className="p-3 rounded-xl bg-card border border-border/60 flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-400 flex items-center justify-center shrink-0">
              <Clock size={16} />
            </div>
            <div>
              <div className="text-[10px] uppercase font-bold text-muted-foreground">Golden Hour Win Rate</div>
              <div className="text-sm font-bold text-emerald-400">{telemetry.golden_hour_success_rate_pct}%</div>
            </div>
          </div>

          <div className="p-3 rounded-xl bg-card border border-border/60 flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-cyan-500/10 text-cyan-400 flex items-center justify-center shrink-0">
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

          <div className="p-3 rounded-xl bg-card border border-border/60 flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-amber-500/10 text-amber-400 flex items-center justify-center shrink-0">
              <ThumbsUp size={16} />
            </div>
            <div>
              <div className="text-[10px] uppercase font-bold text-muted-foreground">Swarm Actions Today</div>
              <div className="text-sm font-bold text-foreground">{telemetry.actions_executed_today} Executed</div>
            </div>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="flex border-b border-border px-6 gap-6 text-xs font-medium">
          <button
            onClick={() => setActiveTab('launcher')}
            className={`py-3 flex items-center gap-2 border-b-2 transition-all ${
              activeTab === 'launcher' 
                ? 'border-blue-500 text-blue-400 font-semibold' 
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Rocket size={14} />
            Post Booster Launchpad
          </button>
          <button
            onClick={() => setActiveTab('members')}
            className={`py-3 flex items-center gap-2 border-b-2 transition-all ${
              activeTab === 'members' 
                ? 'border-blue-500 text-blue-400 font-semibold' 
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Users size={14} />
            Pod Fleet & Quotas ({members.length})
          </button>
          <button
            onClick={() => setActiveTab('feed')}
            className={`py-3 flex items-center gap-2 border-b-2 transition-all ${
              activeTab === 'feed' 
                ? 'border-blue-500 text-blue-400 font-semibold' 
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Share2 size={14} />
            Boost Ledger & Velocity ({boosts.length})
          </button>
        </div>

        {/* Tab Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          
          {/* TAB 1: LAUNCHPAD */}
          {activeTab === 'launcher' && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              
              {/* Form Column */}
              <div className="lg:col-span-2 space-y-4">
                <div className="p-5 rounded-xl bg-card border border-border/80 space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-bold text-foreground flex items-center gap-2">
                      <Sparkles size={16} className="text-blue-400" />
                      Submit LinkedIn Post for Velocity Boost
                    </h3>
                    <span className="text-[11px] text-muted-foreground">Staggered across 60 min window</span>
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-muted-foreground">LinkedIn Post URL</label>
                    <input 
                      type="text"
                      value={postUrl}
                      onChange={(e) => setPostUrl(e.target.value)}
                      placeholder="https://www.linkedin.com/posts/username_post-title-activity-..."
                      className="w-full px-3.5 py-2.5 rounded-xl bg-background border border-border text-xs focus:outline-none focus:border-blue-500 font-mono"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-muted-foreground">Post Content / Core Topic</label>
                    <textarea 
                      rows={3}
                      value={postContent}
                      onChange={(e) => setPostContent(e.target.value)}
                      placeholder="Paste post copy or key topics so the AI generates tailored, authentic comments..."
                      className="w-full px-3.5 py-2.5 rounded-xl bg-background border border-border text-xs focus:outline-none focus:border-blue-500"
                    />
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                      <label className="text-xs font-semibold text-muted-foreground">Post Author Account</label>
                      <select 
                        value={authorAccountId}
                        onChange={(e) => setAuthorAccountId(e.target.value)}
                        className="w-full px-3 py-2 rounded-xl bg-background border border-border text-xs focus:outline-none focus:border-blue-500"
                      >
                        <option value="acc-founder-01">Sarah Chen (Founder) - Auto Excluded</option>
                        <option value="acc-sdr-02">Marcus Vance (Senior SDR)</option>
                        <option value="acc-ae-03">Elena Rostova (Account Exec)</option>
                      </select>
                      <p className="text-[10px] text-emerald-400 font-medium flex items-center gap-1">
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
                            className={`flex-1 py-2 rounded-xl text-xs font-semibold border transition-all ${
                              windowMinutes === mins
                                ? 'bg-blue-500/10 border-blue-500/40 text-blue-300'
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
                    <div className="p-3.5 rounded-xl bg-background border border-border/80 space-y-2">
                      <div className="flex justify-between items-center text-xs">
                        <span className="font-semibold text-foreground flex items-center gap-1.5">
                          <ThumbsUp size={12} className="text-cyan-400" />
                          Target Swarm Likes
                        </span>
                        <span className="font-bold text-blue-400">{targetLikes}</span>
                      </div>
                      <input 
                        type="range"
                        min={2}
                        max={25}
                        value={targetLikes}
                        onChange={(e) => setTargetLikes(Number(e.target.value))}
                        className="w-full accent-blue-500 cursor-pointer"
                      />
                    </div>

                    <div className="p-3.5 rounded-xl bg-background border border-border/80 space-y-2">
                      <div className="flex justify-between items-center text-xs">
                        <span className="font-semibold text-foreground flex items-center gap-1.5">
                          <ElesiumLogo size={13} />
                          Target AI Comments
                        </span>
                        <span className="font-bold text-blue-400">{targetComments}</span>
                      </div>
                      <input 
                        type="range"
                        min={1}
                        max={10}
                        value={targetComments}
                        onChange={(e) => setTargetComments(Number(e.target.value))}
                        className="w-full accent-blue-500 cursor-pointer"
                      />
                    </div>
                  </div>

                  <button
                    onClick={handleLaunchBoost}
                    disabled={isLaunchingBoost}
                    className="w-full py-3 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs transition-all shadow-md flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
                  >
                    {isLaunchingBoost ? (
                      <RefreshCw size={14} className="animate-spin" />
                    ) : (
                      <Rocket size={14} />
                    )}
                    Launch Golden Hour Algorithmic Boost
                  </button>
                </div>
              </div>

              {/* Explainer & Safety Sidebar */}
              <div className="space-y-4">
                <div className="p-5 rounded-xl bg-card border border-border/80 space-y-3">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                    <ShieldCheck size={14} className="text-emerald-400" />
                    Algorithmic Velocity Rules
                  </h4>
                  <ul className="space-y-2.5 text-xs text-muted-foreground">
                    <li className="flex items-start gap-2">
                      <div className="w-1.5 h-1.5 rounded-full bg-blue-400 mt-1.5 shrink-0" />
                      <span><strong>The 60-Minute Golden Hour:</strong> LinkedIn scores post engagement velocity within the first hour to determine wider feed distribution.</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 mt-1.5 shrink-0" />
                      <span><strong>Anti-CFBR Policy:</strong> LinkedIn suppresses repetitive spam ("CFBR", "Great post!"). All pod comments are dynamically generated with &gt;15 words of authentic industry nuance.</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <div className="w-1.5 h-1.5 rounded-full bg-cyan-400 mt-1.5 shrink-0" />
                      <span><strong>Natural Jitter Staggering:</strong> Actions are spaced 2 to 7 minutes apart with randomized delays to emulate human behavior.</span>
                    </li>
                  </ul>
                </div>

                <div className="p-4 rounded-xl bg-blue-500/5 border border-blue-500/20 space-y-2">
                  <div className="text-xs font-bold text-blue-300 flex items-center gap-1.5">
                    <ElesiumLogo size={13} />
                    Live AI Comment Preview
                  </div>
                  <p className="text-xs text-muted-foreground italic leading-relaxed">
                    &quot;Spot-on perspective on outbound deliverability. Multi-threading conversations across buying committees before pitching makes all the difference compared to traditional single-threaded outbound.&quot;
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
                  onClick={() => setShowAddMember(true)}
                  className="px-3.5 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs flex items-center gap-1.5 cursor-pointer"
                >
                  <Plus size={14} /> Enroll Sender Account
                </button>
              </div>

              {showAddMember && (
                <form onSubmit={handleAddMember} className="p-4 rounded-xl bg-card border border-blue-500/30 space-y-3">
                  <div className="font-semibold text-xs text-foreground">Enroll New Sender Account in Pod</div>
                  <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                    <input 
                      type="text" 
                      placeholder="Account ID (e.g. acc-sdr-04)"
                      value={newAccountId}
                      onChange={(e) => setNewAccountId(e.target.value)}
                      className="px-3 py-2 rounded-xl bg-background border border-border text-xs focus:outline-none focus:border-blue-500"
                    />
                    <input 
                      type="text" 
                      placeholder="Account Name (e.g. Jordan Lee)"
                      value={newAccountName}
                      onChange={(e) => setNewAccountName(e.target.value)}
                      className="px-3 py-2 rounded-xl bg-background border border-border text-xs focus:outline-none focus:border-blue-500"
                    />
                    <input 
                      type="number" 
                      placeholder="Daily Like Cap (Max 30)"
                      value={newLikeCap}
                      onChange={(e) => setNewLikeCap(Number(e.target.value))}
                      className="px-3 py-2 rounded-xl bg-background border border-border text-xs focus:outline-none focus:border-blue-500"
                    />
                    <input 
                      type="number" 
                      placeholder="Daily Comment Cap (Max 15)"
                      value={newCommentCap}
                      onChange={(e) => setNewCommentCap(Number(e.target.value))}
                      className="px-3 py-2 rounded-xl bg-background border border-border text-xs focus:outline-none focus:border-blue-500"
                    />
                  </div>
                  <div className="flex justify-end gap-2">
                    <button 
                      type="button" 
                      onClick={() => setShowAddMember(false)}
                      className="px-3 py-1.5 rounded-lg text-xs text-muted-foreground hover:text-foreground"
                    >
                      Cancel
                    </button>
                    <button 
                      type="submit" 
                      disabled={isSubmittingMember}
                      className="px-4 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold"
                    >
                      Enroll
                    </button>
                  </div>
                </form>
              )}

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {members.map((member: any) => (
                  <div key={member.id} className="p-4 rounded-xl bg-card border border-border/80 space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div className="w-8 h-8 rounded-full bg-blue-500/10 text-blue-400 font-bold flex items-center justify-center text-xs">
                          {member.account_name?.charAt(0) || 'U'}
                        </div>
                        <div>
                          <div className="text-xs font-bold text-foreground">{member.account_name}</div>
                          <div className="text-[10px] text-muted-foreground">{member.account_id}</div>
                        </div>
                      </div>
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                        member.role === 'admin' ? 'bg-amber-500/10 text-amber-400' : 'bg-muted text-muted-foreground'
                      }`}>
                        {member.role}
                      </span>
                    </div>

                    <div className="space-y-1.5 text-xs text-muted-foreground">
                      <div className="flex justify-between text-[11px]">
                        <span>Daily Like Budget</span>
                        <span className="font-semibold text-foreground">{member.daily_like_cap} / day</span>
                      </div>
                      <div className="w-full bg-muted rounded-full h-1.5 overflow-hidden">
                        <div className="bg-cyan-400 h-1.5 rounded-full" style={{ width: '45%' }} />
                      </div>
                    </div>

                    <div className="space-y-1.5 text-xs text-muted-foreground">
                      <div className="flex justify-between text-[11px]">
                        <span>Daily Comment Budget</span>
                        <span className="font-semibold text-foreground">{member.daily_comment_cap} / day</span>
                      </div>
                      <div className="w-full bg-muted rounded-full h-1.5 overflow-hidden">
                        <div className="bg-emerald-400 h-1.5 rounded-full" style={{ width: '60%' }} />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
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
                  onClick={() => mutateBoosts()}
                  className="px-3 py-1.5 rounded-lg border border-border text-xs text-muted-foreground hover:text-foreground flex items-center gap-1.5"
                >
                  <RefreshCw size={12} /> Refresh
                </button>
              </div>

              <div className="space-y-3">
                {boosts.map((boost: any) => (
                  <div key={boost.id} className="p-4 rounded-xl bg-card border border-border/80 flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div className="space-y-1 max-w-xl">
                      <div className="flex items-center gap-2">
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                          boost.status === 'boosting' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                          boost.status === 'completed' ? 'bg-cyan-500/10 text-cyan-400' : 'bg-muted text-muted-foreground'
                        }`}>
                          {boost.status?.toUpperCase()}
                        </span>
                        <a 
                          href={boost.post_url} 
                          target="_blank" 
                          rel="noreferrer"
                          className="text-xs font-semibold text-foreground hover:text-blue-400 truncate max-w-sm"
                        >
                          {boost.post_url}
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
                          onClick={() => handleCancelBoost(boost.id)}
                          className="px-3 py-1.5 rounded-lg border border-rose-500/30 text-rose-400 hover:bg-rose-500/10 text-xs font-semibold flex items-center gap-1 cursor-pointer"
                        >
                          <StopCircle size={13} /> Pause Boost
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

        </div>

      </div>
    </div>
  );
}
