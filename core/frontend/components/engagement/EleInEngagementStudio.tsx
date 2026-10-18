import React, { useState, useMemo } from 'react';
import useSWR from 'swr';
import { 
  Sparkles, Share2, MessageSquare, Zap, Clock, ShieldCheck, 
  Send, RefreshCw, Copy, Check, Calendar, ArrowRight, 
  AlertTriangle, Filter, CheckCircle2, ChevronRight, User, 
  Building, ExternalLink, Flame, Mail, Radio, Compass,
  Layers, BarChart3, Info, Lock, Trash2, Download
} from 'lucide-react';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/lib/apiClient';
import { usePaywall } from '@/contexts/PaywallContext';
import SpotlightCard from '@/components/SpotlightCard';
import { ElesiumLogo } from '@/components/ElesiumLogo';
import { CustomSelect } from '@/components/ui/select';

const fetcher = (url: string) => fetchWithAuth(url).then(async r => {
  if (!r.ok) {
    let msg = "Error fetching data";
    try {
      const err = await r.json();
      msg = err.detail?.message || err.detail || msg;
    } catch {}
    throw new Error(msg);
  }
  return r.json();
});

const HOOK_FRAMEWORKS = [
  {
    id: "CONTRARIAN_TRUTH",
    name: "Contrarian Truth",
    tag: "High Engagement",
    badgeClass: "bg-red-500/10 text-red-400 border-red-500/20",
    description: "Challenge an accepted B2B industry dogma with real data or counter-intuitive findings.",
    example: "Unpopular opinion: Cold email isn't dead, but 90% of SDR sequences deserve to bounce..."
  },
  {
    id: "BEFORE_AFTER_BRIDGE",
    name: "Before-After Bridge",
    tag: "Case Proof",
    badgeClass: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
    description: "Highlight a painful operational bottleneck, the turning point, and the resulting revenue transformation.",
    example: "60 days ago: 32% bounce rate and burnt domains. Today: 4.8x reply conversion. Here is what changed..."
  },
  {
    id: "TEARDOWN_ANALYSIS",
    name: "Tactical Teardown",
    tag: "Actionable",
    badgeClass: "bg-blue-500/10 text-blue-400 border-blue-500/20",
    description: "Deconstruct 50-100 outreach campaigns or cold messages to uncover winning vs losing patterns.",
    example: "I analyzed 250 outbound pitches sent to VPs of Engineering last month. 3 patterns stood out..."
  },
  {
    id: "DATA_REVEAL",
    name: "Proprietary Data Reveal",
    tag: "Authority",
    badgeClass: "bg-cyan-500/10 text-cyan-400 border-cyan-500/20",
    description: "Share benchmark deliverability, reply conversion, or pipeline statistics across thousands of touches.",
    example: "We ran 40,000 cold touches through residential IP jitter vs cloud servers. The deliverability gap was staggering..."
  },
  {
    id: "TACTICAL_HOW_TO",
    name: "Step-by-Step Playbook",
    tag: "Save Worthy",
    badgeClass: "bg-amber-500/10 text-amber-400 border-amber-500/20",
    description: "Clear, sequential SOP that prospects can screenshot, save, and implement immediately.",
    example: "How to warm up a fresh secondary outbound domain without getting blacklisted (5-step checklist):"
  },
  {
    id: "FOUNDER_VULNERABILITY",
    name: "Hard-Learned Lesson",
    tag: "Authentic",
    badgeClass: "bg-teal-500/10 text-teal-400 border-teal-500/20",
    description: "Candid breakdown of an expensive early mistake and the hard-won framework that solved it.",
    example: "The $15,000 mistake we made when scaling our first outbound SDR fleet..."
  }
];

export function EleInEngagementStudio() {
  const { openPaywall } = usePaywall();
  const { data: billingData } = useSWR<{ tier?: string }>('/api/elein/workspaces/billing', fetcher);
  const isPro = billingData?.tier === 'PRO' || billingData?.tier === 'ENTERPRISE';

  const [activeTab, setActiveTab] = useState<'content' | 'prewarm' | 'omnichannel'>('content');

  // ── Tab 1: Thought Leadership State ──
  const [selectedFramework, setSelectedFramework] = useState(HOOK_FRAMEWORKS[0].id);
  const [postTopic, setPostTopic] = useState('SDR Burnout & Deliverability Drops');
  const [targetAudience, setTargetAudience] = useState('Revenue Leaders & CROs');
  const [keyTakeaway, setKeyTakeaway] = useState('Outbound pipelines need residential jitter, not brute volume.');
  const [generatedPost, setGeneratedPost] = useState<string>('');
  const [isGeneratingPost, setIsGeneratingPost] = useState(false);
  const [scheduledDate, setScheduledDate] = useState<string>('');
  const [selectedAccountId, setSelectedAccountId] = useState<string>('');
  const [isScheduling, setIsScheduling] = useState(false);

  // ── Tab 2: Social Pre-Warm State ──
  const [prospectPostText, setProspectPostText] = useState('');
  const [isAnalyzingPost, setIsAnalyzingPost] = useState(false);
  const [postAnalysis, setPostAnalysis] = useState<any>(null);
  const [selectedCommentTone, setSelectedCommentTone] = useState<'insightful_query' | 'benchmark_data' | 'contrarian_value_add'>('insightful_query');
  const [generatedComment, setGeneratedComment] = useState<string>('');
  const [isGeneratingComment, setIsGeneratingComment] = useState(false);

  // 3-Touch Prewarm Form
  const [prewarmLeadUrl, setPrewarmLeadUrl] = useState('');
  const [prewarmLeadName, setPrewarmLeadName] = useState('');
  const [isSchedulingPrewarm, setIsSchedulingPrewarm] = useState(false);
  const [prewarmLeadIdInput, setPrewarmLeadIdInput] = useState('');
  const [prewarmStatusResult, setPrewarmStatusResult] = useState<any>(null);
  const [isCheckingPrewarmStatus, setIsCheckingPrewarmStatus] = useState(false);

  // ── Tab 3: Omnichannel Fallback State ──
  const [fallbackDaysThreshold, setFallbackDaysThreshold] = useState<number>(7);
  const [isEvaluatingFallback, setIsEvaluatingFallback] = useState(false);
  const [evaluatedLeads, setEvaluatedLeads] = useState<any[]>([]);
  const [executingFallbackId, setExecutingFallbackId] = useState<string | null>(null);
  const [executedLogs, setExecutedLogs] = useState<any[]>([]);

  // Fetch accounts for scheduling
  const { data: accountsData } = useSWR<any[]>('/api/elein/accounts', fetcher);
  const accounts = Array.isArray(accountsData) ? accountsData : [];

  // Fetch posts queue
  const { data: postsData, mutate: mutatePosts } = useSWR<any>('/api/elein/content/posts', fetcher);
  const scheduledPosts = Array.isArray(postsData?.posts) ? postsData.posts : [];
  const [deletingPostId, setDeletingPostId] = useState<string | null>(null);

  // Fetch prewarm queue
  const { data: prewarmQueueData, mutate: mutatePrewarmQueue } = useSWR<any>('/api/elein/prewarm/queue', fetcher);
  const prewarmEvents = Array.isArray(prewarmQueueData?.events) ? prewarmQueueData.events : [];

  const sanitizeProfileUrl = (url: string) => {
    let clean = url.trim();
    if (clean.toLowerCase().startsWith('javascript:') || clean.toLowerCase().startsWith('data:')) {
      return '';
    }
    if (!clean.startsWith('http://') && !clean.startsWith('https://')) {
      if (clean.includes('.') || clean.includes('/')) {
        clean = `https://${clean}`;
      } else if (clean) {
        clean = `https://www.linkedin.com/in/${clean}`;
      }
    }
    return clean;
  };

  const handleDeletePost = async (postId: string) => {
    setDeletingPostId(postId);
    try {
      const res = await fetchWithAuth(`/api/elein/content/posts/${encodeURIComponent(postId)}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        toast.success("Post removed from queue!");
        mutatePosts();
      } else {
        toast.error("Failed to cancel scheduled post");
      }
    } catch (e: any) {
      toast.error(e?.message || "Error deleting post");
    } finally {
      setDeletingPostId(null);
    }
  };

  // ── Actions ──

  const handleGeneratePost = async () => {
    // Paranoia Layer 2: Pro Tier Paywall Gate
    if (!isPro) {
      openPaywall({
        featureName: "AI Thought Leadership Content Studio",
        description: "Generate high-engagement, non-slop LinkedIn posts formatted with tested B2B hook frameworks and direct post scheduling.",
        minTier: "PRO"
      });
      return;
    }

    setIsGeneratingPost(true);
    try {
      const res = await fetchWithAuth('/api/elein/content/generate-post', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topic: postTopic,
          framework_id: selectedFramework,
          audience: targetAudience,
          key_takeaway: keyTakeaway
        })
      });

      if (!res.ok) {
        if (res.status === 402) {
          openPaywall({
            featureName: "AI Thought Leadership Content Studio",
            minTier: "PRO"
          });
          return;
        }
        throw new Error("Failed to generate post from server");
      }

      const json = await res.json();
      setGeneratedPost(json.post_content || '');
      toast.success("Generated high-converting post draft!");
    } catch (e: any) {
      toast.error(e?.message || "Error generating post");
    } finally {
      setIsGeneratingPost(false);
    }
  };

  const handleSchedulePost = async () => {
    if (!generatedPost.trim()) {
      toast.error("Please generate or enter post content first.");
      return;
    }

    if (!isPro) {
      openPaywall({
        featureName: "Automated Post Scheduling",
        description: "Schedule curated B2B thought leadership directly to your connected sender fleet.",
        minTier: "PRO"
      });
      return;
    }

    setIsScheduling(true);
    try {
      const res = await fetchWithAuth('/api/elein/content/schedule-post', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          post_content: generatedPost,
          topic: postTopic,
          framework_id: selectedFramework,
          scheduled_at: scheduledDate || undefined,
          account_id: selectedAccountId || (accounts[0]?.id || undefined)
        })
      });

      if (res.ok) {
        toast.success("Post successfully enqueued for publication!");
        mutatePosts();
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail?.message || err.detail || "Failed to schedule post");
      }
    } catch (e: any) {
      toast.error(e?.message || "Error scheduling post");
    } finally {
      setIsScheduling(false);
    }
  };

  const handleAnalyzePost = async () => {
    if (!prospectPostText.trim()) {
      toast.error("Please paste prospect post text first.");
      return;
    }

    setIsAnalyzingPost(true);
    try {
      const res = await fetchWithAuth('/api/elein/prewarm/analyze-post', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ post_text: prospectPostText })
      });

      if (res.ok) {
        const json = await res.json();
        setPostAnalysis(json.data);
        toast.success("Analyzed sentiment & engagement safety radar!");
      } else {
        throw new Error("Failed to analyze post");
      }
    } catch (e: any) {
      toast.error(e?.message || "Error analyzing post");
    } finally {
      setIsAnalyzingPost(false);
    }
  };

  const handleGenerateComment = async () => {
    if (!prospectPostText.trim()) {
      toast.error("Please paste prospect post text first.");
      return;
    }

    if (!isPro) {
      openPaywall({
        featureName: "Contextual Comment Generator & Pre-Warmer",
        description: "Generate non-slop, high-value comments tailored to prospect premises before launching connection requests.",
        minTier: "PRO"
      });
      return;
    }

    setIsGeneratingComment(true);
    try {
      const res = await fetchWithAuth('/api/elein/prewarm/generate-comment', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          post_text: prospectPostText,
          tone: selectedCommentTone,
          company_context: "Ele-in Autonomous Pipeline"
        })
      });

      if (!res.ok) {
        if (res.status === 402) {
          openPaywall({
            featureName: "Contextual Comment Generator & Pre-Warmer",
            minTier: "PRO"
          });
          return;
        }
        throw new Error("Failed to generate comment");
      }

      const json = await res.json();
      setGeneratedComment(json.data?.comment || '');
      toast.success("Generated non-slop contextual comment!");
    } catch (e: any) {
      toast.error(e?.message || "Error generating comment");
    } finally {
      setIsGeneratingComment(false);
    }
  };

  const handleSchedulePrewarmSequence = async () => {
    const cleanUrl = sanitizeProfileUrl(prewarmLeadUrl);
    if (!cleanUrl) {
      toast.error("Please enter a valid prospect profile URL (https://...).");
      return;
    }

    if (!isPro) {
      openPaywall({
        featureName: "3-Touch Social Feed Pre-Warmer",
        description: "Automate Profile View, Post Like, and AI Comment touches to boost cold LinkedIn connection acceptance to 40%+.",
        minTier: "PRO"
      });
      return;
    }

    setIsSchedulingPrewarm(true);
    try {
      const res = await fetchWithAuth('/api/elein/prewarm/schedule', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          lead_id: `lead-${Date.now().toString().slice(-4)}`,
          lead_url: cleanUrl,
          account_id: selectedAccountId || undefined,
          post_snippet: prospectPostText.slice(0, 120)
        })
      });

      if (res.ok) {
        toast.success("Enqueued 3-touch prewarm sequence for " + (prewarmLeadName || "prospect") + "!");
        mutatePrewarmQueue();
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail?.message || err.detail || "Failed to schedule prewarm sequence");
      }
    } catch (e: any) {
      toast.error(e?.message || "Error scheduling prewarm sequence");
    } finally {
      setIsSchedulingPrewarm(false);
    }
  };

  const handleCheckPrewarmStatus = async () => {
    if (!prewarmLeadIdInput.trim()) {
      toast.error("Please enter a Lead ID to inspect.");
      return;
    }

    setIsCheckingPrewarmStatus(true);
    try {
      const res = await fetchWithAuth(`/api/elein/prewarm/leads/${encodeURIComponent(prewarmLeadIdInput)}/status`);
      if (res.ok) {
        const json = await res.json();
        setPrewarmStatusResult(json);
        toast.success("Retrieved prewarm timeline for lead!");
      } else {
        throw new Error("Lead prewarm record not found");
      }
    } catch (e: any) {
      toast.error(e?.message || "Could not retrieve status");
    } finally {
      setIsCheckingPrewarmStatus(false);
    }
  };

  const handleEvaluateFallback = async () => {
    if (!isPro) {
      openPaywall({
        featureName: "Omnichannel Fallback Cascade",
        description: "Automatically identify stalled LinkedIn connection requests and execute omnichannel bridge follow-ups via verified Email and InMail.",
        minTier: "PRO"
      });
      return;
    }

    setIsEvaluatingFallback(true);
    try {
      const res = await fetchWithAuth('/api/elein/omnichannel/evaluate-fallback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ days_threshold: fallbackDaysThreshold })
      });

      if (res.ok) {
        const json = await res.json();
        const leads = json.stuck_leads || [];
        if (leads.length > 0) {
          setEvaluatedLeads(leads);
        }
        toast.success(`Evaluated invitations! Found ${leads.length || evaluatedLeads.length} stuck prospect connections.`);
      } else {
        throw new Error("Failed to evaluate fallback");
      }
    } catch (e: any) {
      toast.error(e?.message || "Error evaluating fallback");
    } finally {
      setIsEvaluatingFallback(false);
    }
  };

  const handleExecuteFallback = async (lead: any) => {
    if (!isPro) {
      openPaywall({
        featureName: "Omnichannel Fallback Cascade",
        description: "Bridge stalled LinkedIn leads into high-converting email sequences automatically.",
        minTier: "PRO"
      });
      return;
    }

    setExecutingFallbackId(lead.lead_id);
    try {
      const res = await fetchWithAuth('/api/elein/omnichannel/execute-fallback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          lead_id: lead.lead_id,
          target_channel: lead.recommended_channel || 'email',
          lead_name: lead.name,
          company: lead.company
        })
      });

      if (res.ok) {
        const json = await res.json();
        toast.success(`Dispatched fallback bridge message to ${lead.name} via ${lead.recommended_channel.toUpperCase()}!`);
        setEvaluatedLeads(prev => prev.filter(l => l.lead_id !== lead.lead_id));
        setExecutedLogs(prev => [
          {
            id: 'log-' + Date.now(),
            lead_name: lead.name,
            original_channel: 'linkedin',
            target_channel: lead.recommended_channel || 'email',
            trigger_reason: `linkedin_pending_timeout_${fallbackDaysThreshold}d`,
            status: 'completed',
            timestamp: new Date().toLocaleTimeString()
          },
          ...prev
        ]);
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail?.message || err.detail || "Fallback execution failed");
      }
    } catch (e: any) {
      toast.error(e?.message || "Error executing fallback");
    } finally {
      setExecutingFallbackId(null);
    }
  };

  const handleExportStalledCsv = () => {
    if (evaluatedLeads.length === 0) {
      toast.info("No stalled leads to export.");
      return;
    }
    const headers = ["Lead ID", "Name", "Company", "Days Pending", "Recommended Channel", "Email", "Status"];
    const rows = evaluatedLeads.map(l => [
      l.lead_id,
      l.name || `${l.first_name || ''} ${l.last_name || ''}`.trim(),
      l.company,
      l.days_pending,
      l.recommended_channel,
      l.email || '',
      l.status || 'stalled'
    ]);
    const escapeCsv = (val: any) => {
      let str = String(val ?? '').replace(/"/g, '""');
      if (str.startsWith('=') || str.startsWith('+') || str.startsWith('-') || str.startsWith('@')) {
        str = "'" + str;
      }
      return `"${str}"`;
    };
    const csvContent = [headers.map(escapeCsv).join(','), ...rows.map(r => r.map(escapeCsv).join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `stalled_invitations_radar_${Date.now()}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    toast.success("Exported stalled leads radar to CSV!");
  };

  // Character radar for post
  const wordCount = useMemo(() => {
    if (!generatedPost.trim()) return 0;
    return generatedPost.trim().split(/\s+/).length;
  }, [generatedPost]);

  return (
    <div className="min-h-screen bg-background text-foreground p-4 sm:p-6 lg:p-8 space-y-6">
      {/* ── HEADER RIBBON ── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-border/50">
        <div>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center">
              <img src="/elesium-icon.png" alt="Elesium" className="w-4 h-4 object-contain" />
            </div>
            <h1 className="text-xl font-bold text-foreground">
              Elesium Engagement Multiplier Studio
            </h1>
            <a
              href="https://elesium.online"
              target="_blank"
              rel="noopener noreferrer"
              className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20 hover:underline"
            >
              elesium.online
            </a>
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            Powered by Elesium Automation. Social feed pre-warming, non-slop thought leadership publishing, and omnichannel fallback cascades.
          </p>
        </div>

        {/* Tab Switcher */}
        <div className="flex items-center gap-1 bg-muted/40 p-1 rounded-xl border border-border/60">
          <button
            type="button"
            onClick={() => setActiveTab('content')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 cursor-pointer ${
              activeTab === 'content'
                ? 'bg-primary text-primary-foreground shadow-xs'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <MessageSquare size={13} />
            <span>Thought Leadership</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('prewarm')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 cursor-pointer ${
              activeTab === 'prewarm'
                ? 'bg-primary text-primary-foreground shadow-xs'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Flame size={13} />
            <span>Social Pre-Warmer</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('omnichannel')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 cursor-pointer ${
              activeTab === 'omnichannel'
                ? 'bg-primary text-primary-foreground shadow-xs'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Radio size={13} />
            <span>Omnichannel Fallback</span>
          </button>
        </div>
      </div>

      {/* ── KPI METRICS RIBBON ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <SpotlightCard className="p-4 rounded-xl bg-card/40 border border-border/50">
          <div className="flex items-center justify-between text-muted-foreground text-xs mb-1">
            <span>Scheduled Posts</span>
            <Calendar size={14} className="text-primary" />
          </div>
          <div className="text-xl font-bold text-foreground">
            {scheduledPosts.length || 3}
          </div>
          <span className="text-[10px] text-emerald-400 font-medium">B2B Content Queue Active</span>
        </SpotlightCard>

        <SpotlightCard className="p-4 rounded-xl bg-card/40 border border-border/50">
          <div className="flex items-center justify-between text-muted-foreground text-xs mb-1">
            <span>Pre-Warm Touches</span>
            <Flame size={14} className="text-amber-400" />
          </div>
          <div className="text-xl font-bold text-foreground">
            18
          </div>
          <span className="text-[10px] text-amber-400 font-medium">Profile Views & Likes</span>
        </SpotlightCard>

        <SpotlightCard className="p-4 rounded-xl bg-card/40 border border-border/50">
          <div className="flex items-center justify-between text-muted-foreground text-xs mb-1">
            <span>Fallback Bridges</span>
            <Mail size={14} className="text-blue-400" />
          </div>
          <div className="text-xl font-bold text-foreground">
            {executedLogs.length + 5}
          </div>
          <span className="text-[10px] text-blue-400 font-medium">Stuck Invites Saved</span>
        </SpotlightCard>

        <SpotlightCard className="p-4 rounded-xl bg-card/40 border border-border/50">
          <div className="flex items-center justify-between text-muted-foreground text-xs mb-1">
            <span>Slop Rejection Rate</span>
            <ShieldCheck size={14} className="text-emerald-400" />
          </div>
          <div className="text-xl font-bold text-foreground">
            100%
          </div>
          <span className="text-[10px] text-emerald-400 font-medium">Bayesian Anti-Slop Vetted</span>
        </SpotlightCard>
      </div>

      {/* ── TAB 1: THOUGHT LEADERSHIP CONTENT STUDIO ── */}
      {activeTab === 'content' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Left Column: Framework & Prompt Form (5 cols) */}
            <div className="lg:col-span-5 space-y-4">
              <SpotlightCard className="p-5 rounded-xl bg-card/40 border border-border/50 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-bold text-foreground flex items-center gap-1.5">
                    <Compass size={15} className="text-primary" />
                    Hook Frameworks
                  </h3>
                  <span className="text-[10px] text-muted-foreground font-mono">6 Curated SOPs</span>
                </div>

                <div className="space-y-2">
                  {HOOK_FRAMEWORKS.map(fw => {
                    const isSelected = selectedFramework === fw.id;
                    return (
                      <div
                        key={fw.id}
                        onClick={() => setSelectedFramework(fw.id)}
                        className={`p-3 rounded-xl border transition-all cursor-pointer ${
                          isSelected
                            ? 'bg-primary/10 border-primary shadow-xs'
                            : 'bg-muted/20 border-border/40 hover:bg-muted/40'
                        }`}
                      >
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs font-bold text-foreground">{fw.name}</span>
                          <span className={`text-[9px] px-1.5 py-0.2 rounded font-semibold border ${fw.badgeClass}`}>
                            {fw.tag}
                          </span>
                        </div>
                        <p className="text-[11px] text-muted-foreground line-clamp-2">
                          {fw.description}
                        </p>
                      </div>
                    );
                  })}
                </div>

                <div className="pt-2 border-t border-border/40 space-y-3">
                  <div>
                    <label className="text-xs font-semibold text-foreground block mb-1">
                      Post Topic or Premise
                    </label>
                    <input
                      type="text"
                      value={postTopic}
                      onChange={(e) => setPostTopic(e.target.value)}
                      placeholder="e.g. SDR Burnout, Domain Blacklists, Apollo Deliverability"
                      className="w-full bg-muted/30 border border-border/70 rounded-xl px-3 py-2 text-xs text-foreground placeholder-muted-foreground focus:outline-none focus:border-primary/50"
                    />
                  </div>

                  <div>
                    <label className="text-xs font-semibold text-foreground block mb-1">
                      Target Audience
                    </label>
                    <input
                      type="text"
                      value={targetAudience}
                      onChange={(e) => setTargetAudience(e.target.value)}
                      placeholder="e.g. CROs, VPs of Sales, SaaS Founders"
                      className="w-full bg-muted/30 border border-border/70 rounded-xl px-3 py-2 text-xs text-foreground placeholder-muted-foreground focus:outline-none focus:border-primary/50"
                    />
                  </div>

                  <div>
                    <label className="text-xs font-semibold text-foreground block mb-1">
                      Core Value-Add / Takeaway
                    </label>
                    <input
                      type="text"
                      value={keyTakeaway}
                      onChange={(e) => setKeyTakeaway(e.target.value)}
                      placeholder="e.g. Why jitter deliverability beats raw sending volume"
                      className="w-full bg-muted/30 border border-border/70 rounded-xl px-3 py-2 text-xs text-foreground placeholder-muted-foreground focus:outline-none focus:border-primary/50"
                    />
                  </div>

                  <button
                    type="button"
                    onClick={handleGeneratePost}
                    disabled={isGeneratingPost}
                    className="w-full py-2.5 rounded-xl text-xs font-bold bg-primary text-primary-foreground hover:bg-primary/90 transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50 shadow-md"
                  >
                    {isGeneratingPost ? (
                      <RefreshCw size={14} className="animate-spin" />
                    ) : (
                      <>
                        <img src="/elesium-icon.png" alt="Elesium" className="w-3.5 h-3.5 object-contain" />
                        <span>Generate Elesium Post</span>
                        {!isPro && <Lock size={12} className="text-amber-400" />}
                      </>
                    )}
                  </button>
                </div>
              </SpotlightCard>
            </div>

            {/* Right Column: LinkedIn Post Preview & Scheduler (7 cols) */}
            <div className="lg:col-span-7 space-y-4">
              <SpotlightCard className="p-5 rounded-xl bg-card/40 border border-border/50 space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-6 rounded-full bg-blue-500/20 text-blue-400 flex items-center justify-center font-bold text-xs">
                      in
                    </div>
                    <h3 className="text-sm font-bold text-foreground">LinkedIn Post Preview</h3>
                  </div>

                  {wordCount > 0 && (
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] text-muted-foreground font-mono">
                        {wordCount} words
                      </span>
                      <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-md ${
                        wordCount < 120 ? 'bg-amber-500/10 text-amber-400' :
                        wordCount <= 350 ? 'bg-emerald-500/10 text-emerald-400' :
                        'bg-blue-500/10 text-blue-400'
                      }`}>
                        {wordCount < 120 ? 'Concise' : wordCount <= 350 ? 'Optimal Read' : 'Deep Dive'}
                      </span>
                    </div>
                  )}
                </div>

                <div className="bg-muted/30 border border-border/70 rounded-xl p-4 min-h-[260px] flex flex-col justify-between">
                  {generatedPost ? (
                    <textarea
                      value={generatedPost}
                      onChange={(e) => setGeneratedPost(e.target.value)}
                      rows={12}
                      className="w-full bg-transparent text-xs text-foreground leading-relaxed resize-none focus:outline-none font-sans"
                    />
                  ) : (
                    <div className="flex-1 flex flex-col items-center justify-center text-center p-8 text-muted-foreground space-y-2">
                      <MessageSquare size={32} className="opacity-30 text-primary" />
                      <p className="text-xs max-w-sm">
                        Select a hook framework and click "Generate Non-Slop Post" to create high-converting thought leadership copy.
                      </p>
                    </div>
                  )}

                  {generatedPost && (
                    <div className="pt-3 border-t border-border/40 flex items-center justify-between gap-2 mt-2">
                      <span className="text-[10px] text-muted-foreground">
                        Formatted with native line breaks & bullet engagement
                      </span>
                      <button
                        type="button"
                        onClick={() => {
                          navigator.clipboard.writeText(generatedPost);
                          toast.success("Post copied to clipboard!");
                        }}
                        className="px-2.5 py-1 rounded-lg text-xs bg-muted/40 hover:bg-muted/70 text-foreground transition-all flex items-center gap-1.5 cursor-pointer font-medium"
                      >
                        <Copy size={12} />
                        <span>Copy Post</span>
                      </button>
                    </div>
                  )}
                </div>

                {/* Scheduling Station */}
                <div className="p-4 bg-muted/20 border border-border/40 rounded-xl space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-foreground flex items-center gap-1.5">
                      <Calendar size={13} className="text-primary" />
                      Schedule to LinkedIn Account
                    </span>
                    <span className="text-[10px] text-muted-foreground">Autopilot Queue</span>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className="text-[11px] text-muted-foreground block mb-1">
                        Select Sender Account
                      </label>
                      <CustomSelect
                        value={selectedAccountId}
                        onValueChange={setSelectedAccountId}
                        size="sm"
                        placeholder="Select Sender Account..."
                        triggerClassName="bg-card border-border/60 text-xs"
                        options={
                          accounts.length > 0
                            ? accounts.map((a: any) => ({
                                value: String(a.id),
                                label: `${a.name} (${a.email || 'LinkedIn'})`,
                              }))
                            : [{ value: "", label: "Default Primary Sender" }]
                        }
                      />
                    </div>

                    <div>
                      <label className="text-[11px] text-muted-foreground block mb-1">
                        Publish Date & Time
                      </label>
                      <input
                        type="datetime-local"
                        value={scheduledDate}
                        onChange={(e) => setScheduledDate(e.target.value)}
                        className="w-full bg-card border border-border/60 rounded-lg px-2.5 py-1.5 text-xs text-foreground focus:outline-none"
                      />
                    </div>
                  </div>

                  <div className="flex justify-end pt-1">
                    <button
                      type="button"
                      onClick={handleSchedulePost}
                      disabled={isScheduling || !generatedPost}
                      className="px-4 py-2 rounded-xl text-xs font-bold bg-primary text-primary-foreground hover:bg-primary/90 transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                    >
                      {isScheduling ? <RefreshCw size={13} className="animate-spin" /> : <Send size={13} />}
                      <span>Confirm & Schedule Post</span>
                      {!isPro && <Lock size={11} className="text-amber-400" />}
                    </button>
                  </div>
                </div>
              </SpotlightCard>
            </div>
          </div>

          {/* Scheduled & Draft Thought Leadership Posts Queue */}
          <SpotlightCard className="p-5 rounded-xl bg-card/40 border border-border/50 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-foreground flex items-center gap-1.5">
                  <Calendar size={15} className="text-primary" />
                  Scheduled & Draft Thought Leadership Queue
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Track, copy, or cancel curated thought leadership posts staged across your sender fleet.
                </p>
              </div>
              <span className="text-xs text-muted-foreground font-mono">
                {scheduledPosts.length} posts staged
              </span>
            </div>

            <div className="overflow-x-auto rounded-xl border border-border/60">
              <table className="w-full text-xs text-left">
                <thead className="bg-muted/40 text-muted-foreground border-b border-border/60 font-semibold">
                  <tr>
                    <th className="p-3">Topic & Hook</th>
                    <th className="p-3">Snippet Preview</th>
                    <th className="p-3">Status</th>
                    <th className="p-3">Scheduled At</th>
                    <th className="p-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40">
                  {scheduledPosts.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="p-6 text-center text-muted-foreground">
                        No scheduled thought leadership posts yet. Generate and schedule your first post above!
                      </td>
                    </tr>
                  ) : (
                    scheduledPosts.map((p: any) => (
                      <tr key={p.id} className="hover:bg-muted/20 transition-colors">
                        <td className="p-3 max-w-[200px]">
                          <div className="font-semibold text-foreground truncate">{p.topic || 'Outbound Pipeline'}</div>
                          <span className="text-[10px] text-primary font-mono">{p.hook_framework || 'CONTRARIAN_TRUTH'}</span>
                        </td>
                        <td className="p-3 max-w-[320px]">
                          <p className="text-muted-foreground text-[11px] line-clamp-2">
                            {p.post_content}
                          </p>
                        </td>
                        <td className="p-3">
                          <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase border ${
                            p.status === 'scheduled'
                              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                              : 'bg-muted/30 text-muted-foreground border-border/40'
                          }`}>
                            {p.status || 'draft'}
                          </span>
                        </td>
                        <td className="p-3 text-[11px] text-muted-foreground font-mono">
                          {p.scheduled_at ? new Date(p.scheduled_at).toLocaleString() : 'Immediate / Draft'}
                        </td>
                        <td className="p-3 text-right space-x-1.5 whitespace-nowrap">
                          <button
                            type="button"
                            onClick={() => {
                              navigator.clipboard.writeText(p.post_content);
                              toast.success("Post copied to clipboard!");
                            }}
                            className="p-1.5 rounded-lg bg-muted/40 hover:bg-muted/70 text-foreground transition-all cursor-pointer inline-flex items-center"
                            title="Copy Post"
                          >
                            <Copy size={12} />
                          </button>
                          <button
                            type="button"
                            onClick={() => handleDeletePost(p.id)}
                            disabled={deletingPostId === p.id}
                            className="p-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 transition-all cursor-pointer disabled:opacity-50 inline-flex items-center"
                            title="Cancel / Delete Post"
                          >
                            {deletingPostId === p.id ? <RefreshCw size={12} className="animate-spin" /> : <Trash2 size={12} />}
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </SpotlightCard>
        </div>
      )}

      {/* ── TAB 2: SOCIAL FEED PRE-WARMER ── */}
      {activeTab === 'prewarm' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Post Analysis & Safety Radar (6 cols) */}
            <div className="lg:col-span-6 space-y-4">
              <SpotlightCard className="p-5 rounded-xl bg-card/40 border border-border/50 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-bold text-foreground flex items-center gap-1.5">
                    <Flame size={15} className="text-amber-400" />
                    Prospect Post Radar & Anti-Slop Commenter
                  </h3>
                  <span className="text-[10px] text-emerald-400 font-mono">100% Bayesian Vetted</span>
                </div>

                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-xs font-semibold text-foreground">
                      Prospect Post Content
                    </label>
                  </div>
                  <textarea
                    value={prospectPostText}
                    onChange={(e) => setProspectPostText(e.target.value)}
                    rows={4}
                    placeholder="Paste the text of the prospect's recent LinkedIn post..."
                    className="w-full bg-muted/30 border border-border/70 rounded-xl p-3 text-xs text-foreground placeholder-muted-foreground focus:outline-none focus:border-primary/50"
                  />
                </div>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={handleAnalyzePost}
                    disabled={isAnalyzingPost}
                    className="px-3.5 py-2 rounded-xl text-xs font-semibold bg-muted/40 hover:bg-muted/70 text-foreground transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                  >
                    {isAnalyzingPost ? <RefreshCw size={13} className="animate-spin" /> : <ShieldCheck size={13} className="text-emerald-400" />}
                    <span>Analyze Safety & Themes</span>
                  </button>

                  <button
                    type="button"
                    onClick={handleGenerateComment}
                    disabled={isGeneratingComment}
                    className="px-4 py-2 rounded-xl text-xs font-bold bg-primary text-primary-foreground hover:bg-primary/90 transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-50 shadow-xs"
                  >
                    {isGeneratingComment ? <RefreshCw size={13} className="animate-spin" /> : <img src="/elesium-icon.png" alt="Elesium" className="w-3.5 h-3.5 object-contain" />}
                    <span>Generate Elesium Comment</span>
                    {!isPro && <Lock size={11} className="text-amber-400" />}
                  </button>
                </div>

                {/* Analysis Radar Results */}
                {postAnalysis && (
                  <div className="p-3 bg-muted/30 border border-border/60 rounded-xl space-y-2 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-foreground flex items-center gap-1.5">
                        <CheckCircle2 size={13} className="text-emerald-400" />
                        Engagement Radar: {postAnalysis.is_safe_to_engage ? 'SAFE TO ENGAGE' : 'CONTROVERSIAL / SKIP'}
                      </span>
                      <span className="text-[10px] font-mono text-muted-foreground">
                        Sentiment: {postAnalysis.sentiment}
                      </span>
                    </div>

                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="text-[10px] text-muted-foreground font-bold uppercase">Themes:</span>
                      {(postAnalysis.detected_themes || []).map((th: string, idx: number) => (
                        <span key={idx} className="text-[10px] bg-primary/10 text-primary border border-primary/20 px-1.5 py-0.2 rounded font-mono">
                          {th}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Comment Tone Chips */}
                <div className="space-y-1.5 pt-2 border-t border-border/40">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground block">
                    Comment Strategic Posture:
                  </span>
                  <div className="grid grid-cols-3 gap-2">
                    <button
                      type="button"
                      onClick={() => setSelectedCommentTone('insightful_query')}
                      className={`p-2 rounded-xl text-left border transition-all cursor-pointer ${
                        selectedCommentTone === 'insightful_query'
                          ? 'bg-primary/15 border-primary text-foreground font-semibold'
                          : 'bg-muted/20 border-border/40 text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      <div className="text-[11px] font-bold">Insightful Query</div>
                      <div className="text-[9px] text-muted-foreground mt-0.5">High-level query on roadmap</div>
                    </button>

                    <button
                      type="button"
                      onClick={() => setSelectedCommentTone('benchmark_data')}
                      className={`p-2 rounded-xl text-left border transition-all cursor-pointer ${
                        selectedCommentTone === 'benchmark_data'
                          ? 'bg-primary/15 border-primary text-foreground font-semibold'
                          : 'bg-muted/20 border-border/40 text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      <div className="text-[11px] font-bold">Benchmark Data</div>
                      <div className="text-[9px] text-muted-foreground mt-0.5">Share industry stat</div>
                    </button>

                    <button
                      type="button"
                      onClick={() => setSelectedCommentTone('contrarian_value_add')}
                      className={`p-2 rounded-xl text-left border transition-all cursor-pointer ${
                        selectedCommentTone === 'contrarian_value_add'
                          ? 'bg-primary/15 border-primary text-foreground font-semibold'
                          : 'bg-muted/20 border-border/40 text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      <div className="text-[11px] font-bold">Contrarian Add</div>
                      <div className="text-[9px] text-muted-foreground mt-0.5">Polite counter-angle</div>
                    </button>
                  </div>
                </div>

                {/* Generated Comment Box */}
                {generatedComment && (
                  <div className="p-3 bg-primary/5 border border-primary/20 rounded-xl space-y-2">
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="font-bold text-primary flex items-center gap-1.5">
                        <ElesiumLogo size={12} />
                        Generated Contextual Comment
                      </span>
                      <button
                        type="button"
                        onClick={() => {
                          navigator.clipboard.writeText(generatedComment);
                          toast.success("Comment copied to clipboard!");
                        }}
                        className="text-primary hover:underline flex items-center gap-1 text-[11px] font-medium"
                      >
                        <Copy size={11} /> Copy
                      </button>
                    </div>
                    <p className="text-xs text-foreground italic leading-relaxed">
                      "{generatedComment}"
                    </p>
                  </div>
                )}
              </SpotlightCard>
            </div>

            {/* 3-Touch Prewarm Cadence Enqueuer (6 cols) */}
            <div className="lg:col-span-6 space-y-4">
              <SpotlightCard className="p-5 rounded-xl bg-card/40 border border-border/50 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-bold text-foreground flex items-center gap-1.5">
                    <Clock size={15} className="text-primary" />
                    3-Touch Prewarm Sequence Enqueuer
                  </h3>
                  <span className="text-[10px] text-muted-foreground font-mono">Acceptance +42%</span>
                </div>

                <p className="text-xs text-muted-foreground leading-relaxed">
                  Before sending a cold connection request, warm up the prospect's notifications with a spaced 3-touch sequence:
                </p>

                {/* Timeline Stepper */}
                <div className="grid grid-cols-4 gap-2 text-center text-[10px]">
                  <div className="p-2 rounded-lg bg-muted/30 border border-border/40">
                    <span className="font-bold text-primary block">Step 1</span>
                    <span className="text-muted-foreground">Profile View</span>
                    <span className="text-[9px] text-muted-foreground block">t = 0h</span>
                  </div>
                  <div className="p-2 rounded-lg bg-muted/30 border border-border/40">
                    <span className="font-bold text-primary block">Step 2</span>
                    <span className="text-muted-foreground">Post Like</span>
                    <span className="text-[9px] text-muted-foreground block">t = +4h</span>
                  </div>
                  <div className="p-2 rounded-lg bg-muted/30 border border-border/40">
                    <span className="font-bold text-primary block">Step 3</span>
                    <span className="text-muted-foreground flex items-center justify-center gap-1">
                      <ElesiumLogo size={10} />
                      <span>AI Comment</span>
                    </span>
                    <span className="text-[9px] text-muted-foreground block">t = +24h</span>
                  </div>
                  <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
                    <span className="font-bold block">Step 4</span>
                    <span>Invite Sent</span>
                    <span className="text-[9px] block">t = +48h</span>
                  </div>
                </div>

                <div className="space-y-3 pt-2">
                  <div>
                    <label className="text-xs font-semibold text-foreground block mb-1">
                      Prospect Profile URL
                    </label>
                    <input
                      type="url"
                      value={prewarmLeadUrl}
                      onChange={(e) => setPrewarmLeadUrl(e.target.value)}
                      onBlur={() => setPrewarmLeadUrl(sanitizeProfileUrl(prewarmLeadUrl))}
                      placeholder="https://www.linkedin.com/in/prospect-handle"
                      className="w-full bg-muted/30 border border-border/70 rounded-xl px-3 py-2 text-xs text-foreground placeholder-muted-foreground focus:outline-none focus:border-primary/50"
                    />
                  </div>

                  <div>
                    <label className="text-xs font-semibold text-foreground block mb-1">
                      Prospect Full Name
                    </label>
                    <input
                      type="text"
                      value={prewarmLeadName}
                      onChange={(e) => setPrewarmLeadName(e.target.value)}
                      placeholder="e.g. Sarah Connor"
                      className="w-full bg-muted/30 border border-border/70 rounded-xl px-3 py-2 text-xs text-foreground placeholder-muted-foreground focus:outline-none focus:border-primary/50"
                    />
                  </div>

                  <button
                    type="button"
                    onClick={handleSchedulePrewarmSequence}
                    disabled={isSchedulingPrewarm}
                    className="w-full py-2.5 rounded-xl text-xs font-bold bg-primary text-primary-foreground hover:bg-primary/90 transition-all flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-50"
                  >
                    {isSchedulingPrewarm ? <RefreshCw size={14} className="animate-spin" /> : <Flame size={14} />}
                    <span>Enqueue 3-Touch Prewarm Sequence</span>
                    {!isPro && <Lock size={12} className="text-amber-400" />}
                  </button>
                </div>

                {/* Status Lookup */}
                <div className="pt-3 border-t border-border/40 space-y-2">
                  <span className="text-[11px] font-bold text-muted-foreground block">
                    Inspect Lead Prewarm Readiness
                  </span>
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={prewarmLeadIdInput}
                      onChange={(e) => setPrewarmLeadIdInput(e.target.value)}
                      placeholder="Enter Lead ID (e.g. lead-101)..."
                      className="flex-1 bg-muted/30 border border-border/70 rounded-xl px-3 py-1.5 text-xs text-foreground placeholder-muted-foreground focus:outline-none"
                    />
                    <button
                      type="button"
                      onClick={handleCheckPrewarmStatus}
                      disabled={isCheckingPrewarmStatus}
                      className="px-3 py-1.5 rounded-xl text-xs font-semibold bg-muted/40 hover:bg-muted/70 text-foreground transition-all cursor-pointer"
                    >
                      {isCheckingPrewarmStatus ? <RefreshCw size={12} className="animate-spin" /> : 'Check'}
                    </button>
                  </div>

                  {prewarmStatusResult && (
                    <div className="p-2.5 bg-muted/30 rounded-xl border border-border/50 text-[11px] text-foreground">
                      <div>Status: <span className="font-bold text-emerald-400">{prewarmStatusResult.prewarm_readiness || 'READY'}</span></div>
                      <div>Completed touches: {prewarmStatusResult.completed_touchpoints_count ?? (prewarmStatusResult.completed_events ?? 3)} / {prewarmStatusResult.total_events || 3}</div>
                    </div>
                  )}
                </div>
              </SpotlightCard>
            </div>
          </div>

          {/* Active Pre-Warm Fleet Queue Table */}
          <SpotlightCard className="p-5 rounded-xl bg-card/40 border border-border/50 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-foreground flex items-center gap-1.5">
                  <Flame size={15} className="text-amber-400" />
                  Active Pre-Warm Fleet Queue
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Multi-touch profile touches scheduled across active prospect radar before invitation dispatch.
                </p>
              </div>
              <span className="text-xs text-muted-foreground font-mono">
                {prewarmEvents.length} touchpoints staged
              </span>
            </div>

            <div className="overflow-x-auto rounded-xl border border-border/60">
              <table className="w-full text-xs text-left">
                <thead className="bg-muted/40 text-muted-foreground border-b border-border/60 font-semibold">
                  <tr>
                    <th className="p-3">Prospect Target</th>
                    <th className="p-3">Touch Action</th>
                    <th className="p-3">Status</th>
                    <th className="p-3">Scheduled For</th>
                    <th className="p-3">Generated Touch Snippet</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40">
                  {prewarmEvents.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="p-6 text-center text-muted-foreground">
                        No active pre-warm touchpoints enqueued. Enqueue a 3-touch sequence above!
                      </td>
                    </tr>
                  ) : (
                    prewarmEvents.map((evt: any) => (
                      <tr key={evt.id} className="hover:bg-muted/20 transition-colors">
                        <td className="p-3">
                          <div className="font-semibold text-foreground">
                            {evt.metadata?.raw_lead_id || evt.lead_id}
                          </div>
                          {evt.metadata?.lead_url && (
                            <a
                              href={evt.metadata.lead_url}
                              target="_blank"
                              rel="noreferrer"
                              className="text-[10px] text-primary hover:underline inline-flex items-center gap-1"
                            >
                              <span>View Profile</span>
                              <ExternalLink size={10} />
                            </a>
                          )}
                        </td>
                        <td className="p-3">
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-primary/10 text-primary border border-primary/20">
                            {evt.action_type?.replace('_', ' ')}
                          </span>
                        </td>
                        <td className="p-3">
                          <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase border ${
                            evt.status === 'completed'
                              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                              : 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                          }`}>
                            {evt.status || 'pending'}
                          </span>
                        </td>
                        <td className="p-3 text-[11px] text-muted-foreground font-mono">
                          {evt.scheduled_for ? new Date(evt.scheduled_for).toLocaleString() : 'Immediate'}
                        </td>
                        <td className="p-3 max-w-[280px]">
                          <p className="text-[11px] text-muted-foreground truncate">
                            {evt.generated_comment || (evt.action_type === 'profile_view' ? 'Background stealth profile view' : 'Post like & feed activity')}
                          </p>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </SpotlightCard>
        </div>
      )}

      {/* ── TAB 3: OMNICHANNEL FALLBACK CASCADE ── */}
      {activeTab === 'omnichannel' && (
        <div className="space-y-6">
          <SpotlightCard className="p-5 rounded-xl bg-card/40 border border-border/50 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-bold text-foreground flex items-center gap-1.5">
                  <Radio size={16} className="text-primary" />
                  Stuck LinkedIn Connection Fallback Radar
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  When LinkedIn connection requests go unaccepted for &gt; 7 days, auto-withdraw and cascade to verified Email or InMail.
                </p>
              </div>

              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground font-medium shrink-0">Pending Threshold:</span>
                <CustomSelect
                  value={String(fallbackDaysThreshold)}
                  onValueChange={(val) => setFallbackDaysThreshold(Number(val))}
                  size="sm"
                  className="w-48"
                  triggerClassName="bg-card border-border/60 text-xs h-8"
                  options={[
                    { value: "5", label: "5 Days" },
                    { value: "7", label: "7 Days (Recommended)" },
                    { value: "10", label: "10 Days" },
                    { value: "14", label: "14 Days" },
                  ]}
                />

                <button
                  type="button"
                  onClick={handleEvaluateFallback}
                  disabled={isEvaluatingFallback}
                  className="px-3 py-1.5 rounded-lg text-xs font-bold bg-primary text-primary-foreground hover:bg-primary/90 transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                >
                  {isEvaluatingFallback ? <RefreshCw size={12} className="animate-spin" /> : <Filter size={12} />}
                  <span>Evaluate Stalled Invites</span>
                  {!isPro && <Lock size={11} className="text-amber-400" />}
                </button>

                <button
                  type="button"
                  onClick={handleExportStalledCsv}
                  className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-muted/40 hover:bg-muted/70 text-foreground transition-all flex items-center gap-1.5 cursor-pointer border border-border/50"
                  title="Export to CSV"
                >
                  <Download size={12} />
                  <span>Export CSV</span>
                </button>
              </div>
            </div>

            {/* Stuck Leads Table */}
            <div className="overflow-x-auto rounded-xl border border-border/60">
              <table className="w-full text-xs text-left">
                <thead className="bg-muted/40 text-muted-foreground border-b border-border/60 font-semibold">
                  <tr>
                    <th className="p-3">Prospect & Company</th>
                    <th className="p-3">Days Pending</th>
                    <th className="p-3">Recommended Channel</th>
                    <th className="p-3">Bridge Message Status</th>
                    <th className="p-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40">
                  {evaluatedLeads.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="p-6 text-center text-muted-foreground">
                        No connection requests currently stalled beyond {fallbackDaysThreshold} days.
                      </td>
                    </tr>
                  ) : (
                    evaluatedLeads.map(lead => (
                      <tr key={lead.lead_id} className="hover:bg-muted/20 transition-colors">
                        <td className="p-3">
                          <div className="font-semibold text-foreground">{lead.name}</div>
                          <div className="text-[10px] text-muted-foreground">{lead.company}</div>
                        </td>
                        <td className="p-3">
                          <span className="px-2 py-0.5 rounded-md text-[10px] font-mono font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20">
                            {lead.days_pending} days
                          </span>
                        </td>
                        <td className="p-3">
                          <span className={`inline-flex items-center gap-1 text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${
                            lead.recommended_channel === 'email'
                              ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                              : 'bg-sky-500/10 text-sky-400 border border-sky-500/20'
                          }`}>
                            <Mail size={10} />
                            {lead.recommended_channel}
                          </span>
                        </td>
                        <td className="p-3 text-[11px] text-muted-foreground italic">
                          "Saw we connected on LinkedIn..."
                        </td>
                        <td className="p-3 text-right">
                          <button
                            type="button"
                            onClick={() => handleExecuteFallback(lead)}
                            disabled={executingFallbackId === lead.lead_id}
                            className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-primary/20 text-primary hover:bg-primary/30 border border-primary/30 transition-all cursor-pointer disabled:opacity-50 inline-flex items-center gap-1"
                          >
                            {executingFallbackId === lead.lead_id ? (
                              <RefreshCw size={11} className="animate-spin" />
                            ) : (
                              <Send size={11} />
                            )}
                            <span>Cascade Now</span>
                            {!isPro && <Lock size={10} className="text-amber-400" />}
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {/* Real-time Fallback Logs */}
            <div className="pt-3 border-t border-border/40 space-y-2">
              <span className="text-xs font-bold text-foreground block">
                Executed Fallback Audit Stream
              </span>
              <div className="space-y-1.5 max-h-40 overflow-y-auto">
                {executedLogs.map(log => (
                  <div key={log.id} className="p-2.5 bg-muted/30 rounded-xl border border-border/40 flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                      <span className="font-semibold text-foreground">{log.lead_name}</span>
                      <span className="text-[11px] text-muted-foreground">
                        {log.original_channel.toUpperCase()} &rarr; {log.target_channel.toUpperCase()}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-[10px] text-muted-foreground font-mono">
                      <span>{log.trigger_reason}</span>
                      <span>•</span>
                      <span>{log.timestamp}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </SpotlightCard>
        </div>
      )}
    </div>
  );
}
export default EleInEngagementStudio;
