import React, { useState } from 'react';
import { 
  MessageSquare, ShieldCheck, Send, Copy, Check, 
  Clock, ArrowRight, RefreshCw, AlertTriangle, Zap, CheckCircle2, 
  ExternalLink, Calendar, Layers, Radio, Compass, Swords, FileText, ChevronRight, Download, X
} from 'lucide-react';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/lib/apiClient';
import { OmnichannelRetargetingStudioModal } from './OmnichannelRetargetingStudioModal';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

interface PreWarmStudioProps {
  onClose?: () => void;
  initialLeadId?: string;
  initialLeadName?: string;
}

const SAMPLE_POSTS = [
  {
    title: "SDR Deliverability Bottleneck",
    snippet: "Cold outreach is completely broken in 2026. SDR teams are sending 100+ invites a day and seeing 10% acceptance because their data is stale and their copy sounds like a generic robot. We need to rethink outbound pipeline from first principles."
  },
  {
    title: "AI Agents in Sales Pipeline",
    snippet: "We just rolled out an AI agent workflow for lead qualification. Finding that LLMs excel at initial intent harvesting, but reps still need human judgment for objection handling and executive contract negotiation."
  },
  {
    title: "Scaling SDR Pods",
    snippet: "Hiring 6 new SDRs this quarter. The biggest challenge isn't finding talent - it's onboarding speed. How do teams standardize playbook qualification without burying new reps in 40 hours of process meetings?"
  }
];

export function PreWarmStudioModal({ onClose, initialLeadId, initialLeadName }: PreWarmStudioProps) {
  const [activeTab, setActiveTab] = useState<'prewarm' | 'omnichannel' | 'content'>('prewarm');

  // Tab 1: Pre-Warm & Comment Generator State
  const [postText, setPostText] = useState(SAMPLE_POSTS[0].snippet);
  const [commentTone, setCommentTone] = useState<'insightful_query' | 'benchmark_data' | 'contrarian_value_add'>('insightful_query');
  const [isGeneratingComment, setIsGeneratingComment] = useState(false);
  const [generatedComment, setGeneratedComment] = useState<string | null>(null);
  const [sentimentAnalysis, setSentimentAnalysis] = useState<any>(null);
  const [copiedComment, setCopiedComment] = useState(false);
  const [isSchedulingPrewarm, setIsSchedulingPrewarm] = useState(false);
  const [isExportingPrewarm, setIsExportingPrewarm] = useState(false);
  const [showOmnichannelModal, setShowOmnichannelModal] = useState(false);

  // Tab 2: Omnichannel Fallback State
  const [daysThreshold, setDaysThreshold] = useState(7);
  const [isScanningFallback, setIsScanningFallback] = useState(false);
  const [stuckLeads, setStuckLeads] = useState<any[]>([
    {
      lead_id: "lead-sim-1",
      first_name: "Marcus",
      last_name: "Vance",
      company: "DataStack Corp",
      email: "marcus.v@datastack.io",
      days_pending: 9,
      recommended_channel: "email"
    },
    {
      lead_id: "lead-sim-2",
      first_name: "Sarah",
      last_name: "Lin",
      company: "FinScale Labs",
      email: null,
      days_pending: 11,
      recommended_channel: "inmail"
    }
  ]);
  const [executingLeadId, setExecutingLeadId] = useState<string | null>(null);

  // Tab 3: Thought Leadership Content State
  const [frameworkId, setFrameworkId] = useState('CONTRARIAN_TRUTH');
  const [topic, setTopic] = useState('B2B Outbound Deliverability');
  const [audience, setAudience] = useState('sales ops leaders');
  const [takeaway, setTakeaway] = useState('Pre-warming and residential jitter beat sheer spam volume every single time.');
  const [isGeneratingPost, setIsGeneratingPost] = useState(false);
  const [generatedPost, setGeneratedPost] = useState<string | null>(null);
  const [copiedPost, setCopiedPost] = useState(false);
  const [isSchedulingPost, setIsSchedulingPost] = useState(false);

  // Handle Exporting Prewarm Queue CSV
  const handleExportPrewarmCSV = async () => {
    if (isExportingPrewarm) return;
    setIsExportingPrewarm(true);
    try {
      const res = await fetchWithAuth("/api/elein/prewarm/queue/export-csv");
      if (!res.ok) throw new Error("Failed to export prewarm queue CSV");
      const csvText = await res.text();
      const blob = new Blob([csvText], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `elein-prewarm-queue-${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      toast.success("Exported 3-Touch Pre-Warm Queue as CSV!");
    } catch (e: any) {
      toast.error(e?.message || "Failed to export pre-warm queue CSV.");
    } finally {
      setIsExportingPrewarm(false);
    }
  };

  // Handle Comment Generation
  const handleGenerateComment = async () => {
    if (!postText.trim()) {
      toast.error("Please paste or select a prospect post first.");
    } else {
      setIsGeneratingComment(true);
      try {
        // 1. Analyze sentiment & safety
        const analyzeRes = await fetchWithAuth("/api/elein/prewarm/analyze-post", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ post_text: postText })
        });
        const analyzeData = await analyzeRes.json();
        setSentimentAnalysis(analyzeData.data || null);

        if (analyzeData.data && !analyzeData.data.is_safe_to_engage) {
          toast.warning(`Safety Alert: ${analyzeData.data.safety_reason}`);
        }

        // 2. Generate comment
        const commentRes = await fetchWithAuth("/api/elein/prewarm/generate-comment", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ post_text: postText, tone: commentTone })
        });
        if (!commentRes.ok) {
          const err = await commentRes.json().catch(() => ({}));
          throw new Error(err?.detail?.message || err?.detail || "Failed to generate comment");
        }
        const commentData = await commentRes.json();
        setGeneratedComment(commentData.data?.comment || null);
        toast.success("Generated contextual comment!");
      } catch (e: any) {
        toast.error("Error generating comment: " + (e?.message || 'Network error'));
      } finally {
        setIsGeneratingComment(false);
      }
    }
  };

  // Handle Scheduling Prewarm Sequence
  const handleSchedulePrewarm = async () => {
    setIsSchedulingPrewarm(true);
    try {
      const res = await fetchWithAuth("/api/elein/prewarm/schedule", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lead_id: initialLeadId || "sample-lead-id",
          lead_url: "https://linkedin.com/in/prospect",
          post_snippet: postText
        })
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err?.detail?.message || err?.detail || "Failed to enqueue pre-warm sequence");
      }
      toast.success("Enqueued 3-touch prewarm sequence (Profile View -> Like -> AI Comment)!");
    } catch (e: any) {
      toast.error(e?.message || "Failed to schedule pre-warm sequence.");
    } finally {
      setIsSchedulingPrewarm(false);
    }
  };

  // Handle Scanning Stuck Fallbacks
  const handleScanFallbacks = async () => {
    setIsScanningFallback(true);
    try {
      const res = await fetchWithAuth("/api/elein/omnichannel/evaluate-fallback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ days_threshold: daysThreshold })
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err?.detail?.message || err?.detail || "Failed to scan stuck invitations");
      }
      const data = await res.json();
      if (data.stuck_leads && data.stuck_leads.length > 0) {
        setStuckLeads(data.stuck_leads);
      }
      toast.success(`Scanned invitations pending > ${daysThreshold} days.`);
    } catch (e: any) {
      toast.error(e?.message || "Failed to scan stuck invitations.");
    } finally {
      setIsScanningFallback(false);
    }
  };

  // Handle Executing Omnichannel Cascade
  const handleExecuteCascade = async (lead: any) => {
    setExecutingLeadId(lead.lead_id);
    try {
      const res = await fetchWithAuth("/api/elein/omnichannel/execute-fallback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lead_id: lead.lead_id,
          target_channel: lead.recommended_channel,
          lead_name: `${lead.first_name} ${lead.last_name || ''}`.trim() || lead.first_name,
          company: lead.company
        })
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err?.detail?.message || err?.detail || "Failed to execute omnichannel cascade");
      }
      toast.success(`Cascaded ${lead.first_name} to ${lead.recommended_channel.toUpperCase()} with bridge copy!`);
      setStuckLeads(prev => prev.filter(l => l.lead_id !== lead.lead_id));
    } catch (e: any) {
      toast.error(e?.message || `Failed to cascade ${lead.first_name}.`);
    } finally {
      setExecutingLeadId(null);
    }
  };

  // Handle Generating Thought Leadership Post
  const handleGeneratePost = async () => {
    setIsGeneratingPost(true);
    try {
      const res = await fetchWithAuth("/api/elein/content/generate-post", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic,
          framework_id: frameworkId,
          audience,
          key_takeaway: takeaway
        })
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err?.detail?.message || err?.detail || "Failed to generate post");
      }
      const data = await res.json();
      setGeneratedPost(data.post_content || null);
      toast.success("Generated LinkedIn post!");
    } catch (e: any) {
      toast.error("Error generating post: " + (e?.message || ''));
    } finally {
      setIsGeneratingPost(false);
    }
  };

  // Handle Scheduling Post
  const handleSchedulePost = async () => {
    if (!generatedPost) return;
    setIsSchedulingPost(true);
    try {
      const res = await fetchWithAuth("/api/elein/content/schedule-post", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          post_content: generatedPost,
          topic,
          framework_id: frameworkId
        })
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err?.detail?.message || err?.detail || "Failed to schedule post");
      }
      toast.success("Thought leadership post scheduled for auto-publication!");
    } catch (e: any) {
      toast.error(e?.message || "Failed to schedule thought leadership post.");
    } finally {
      setIsSchedulingPost(false);
    }
  };

  return (
    <div className="bg-card border border-border rounded-xl text-foreground shadow-lg max-w-4xl w-full mx-auto overflow-hidden animate-in fade-in duration-200">
      {/* Studio Header */}
      <div className="px-6 py-4 border-b border-border bg-background flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold tracking-tight text-foreground">
            Autonomous Pre-Warmer & Omnichannel Studio
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Lift connection acceptance by algorithmically pre-warming prospects before outreach.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleExportPrewarmCSV}
            disabled={isExportingPrewarm}
            className="px-3 py-1.5 rounded-lg bg-card hover:bg-muted border border-border text-xs font-medium text-foreground flex items-center gap-1.5 transition-colors cursor-pointer disabled:opacity-50"
          >
            <Download size={13} className="text-muted-foreground" />
            <span>Export Queue CSV</span>
          </button>
          {onClose && (
            <button 
              type="button" 
              onClick={onClose}
              className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      <div className="p-6 space-y-6">
        {/* Navigation Sub-Tabs */}
        <div className="flex items-center gap-1 p-1 bg-muted/30 border border-border rounded-lg w-fit">
          <button
            type="button"
            onClick={() => setActiveTab('prewarm')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all cursor-pointer ${
              activeTab === 'prewarm'
                ? 'bg-primary/10 text-primary font-semibold'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <MessageSquare size={13} />
            <span>3-Touch Pre-Warmer & Comments</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('omnichannel')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all cursor-pointer ${
              activeTab === 'omnichannel'
                ? 'bg-primary/10 text-primary font-semibold'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Layers size={13} />
            <span>Omnichannel Fallback Matrix</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('content')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all cursor-pointer ${
              activeTab === 'content'
                ? 'bg-primary/10 text-primary font-semibold'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <FileText size={13} />
            <span>Thought Leadership Studio</span>
          </button>
        </div>

        {/* Tab 1: Pre-Warm & Comment Engine */}
        {activeTab === 'prewarm' && (
          <div className="space-y-5">
            {/* Visual 3-Touch Pre-Warm Cadence Banner */}
            <div className="p-4 bg-muted/30 border border-border rounded-lg">
              <span className="text-xs font-semibold text-foreground block mb-2.5">
                3-Touch Algorithmic Pre-Warm Cadence
              </span>
              <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs">
                <div className="p-2.5 rounded-lg bg-card border border-border">
                  <span className="text-muted-foreground font-mono text-xs">Day 1 (Instant)</span>
                  <p className="font-semibold text-foreground mt-0.5">Profile View</p>
                  <p className="text-xs text-muted-foreground">Triggers prospect profile view notification.</p>
                </div>
                <div className="p-2.5 rounded-lg bg-card border border-border">
                  <span className="text-muted-foreground font-mono text-xs">Day 2 (+24h)</span>
                  <p className="font-semibold text-foreground mt-0.5">Post Reaction</p>
                  <p className="text-xs text-muted-foreground">Likes recent post after passing sentiment check.</p>
                </div>
                <div className="p-2.5 rounded-lg bg-card border border-border">
                  <span className="text-muted-foreground font-mono text-xs">Day 3 (+48h)</span>
                  <p className="font-semibold text-foreground mt-0.5">Contextual Comment</p>
                  <p className="text-xs text-muted-foreground">Leaves value-add comment on author premise.</p>
                </div>
                <div className="p-2.5 rounded-lg bg-primary/10 border border-primary/20 text-foreground">
                  <span className="font-mono text-xs text-primary">Day 4 (+72h)</span>
                  <p className="font-semibold text-foreground mt-0.5">Connection Request</p>
                  <p className="text-xs text-muted-foreground">Warm familiarity drives higher acceptance rate.</p>
                </div>
              </div>
            </div>

            {/* Interactive Comment Generator Testing Deck */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-foreground">
                  Prospect Post Text (Paste from LinkedIn):
                </label>
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-muted-foreground">Sample Posts:</span>
                  {SAMPLE_POSTS.map((sp, idx) => (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => { setPostText(sp.snippet); setGeneratedComment(null); }}
                      className="text-xs px-2 py-0.5 rounded bg-muted hover:bg-muted/80 text-foreground border border-border cursor-pointer"
                    >
                      #{idx + 1}
                    </button>
                  ))}
                </div>
              </div>

              <textarea
                value={postText}
                onChange={(e) => setPostText(e.target.value)}
                rows={3}
                className="w-full bg-background border border-border rounded-lg p-3 text-xs text-foreground placeholder-muted-foreground outline-none focus:border-primary resize-none leading-relaxed"
                placeholder="Paste prospect's recent LinkedIn post..."
              />

              {/* Tone Selector & Action Bar */}
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-medium text-muted-foreground mr-1">Comment Tone:</span>
                  <button
                    type="button"
                    onClick={() => setCommentTone('insightful_query')}
                    className={`px-2.5 py-1 rounded-lg text-xs font-medium border cursor-pointer ${
                      commentTone === 'insightful_query'
                        ? 'bg-primary/10 text-primary border-primary'
                        : 'bg-muted text-muted-foreground border-border hover:text-foreground'
                    }`}
                  >
                    Insightful Query
                  </button>
                  <button
                    type="button"
                    onClick={() => setCommentTone('benchmark_data')}
                    className={`px-2.5 py-1 rounded-lg text-xs font-medium border cursor-pointer ${
                      commentTone === 'benchmark_data'
                        ? 'bg-primary/10 text-primary border-primary'
                        : 'bg-muted text-muted-foreground border-border hover:text-foreground'
                    }`}
                  >
                    Benchmark Metric
                  </button>
                  <button
                    type="button"
                    onClick={() => setCommentTone('contrarian_value_add')}
                    className={`px-2.5 py-1 rounded-lg text-xs font-medium border cursor-pointer ${
                      commentTone === 'contrarian_value_add'
                        ? 'bg-primary/10 text-primary border-primary'
                        : 'bg-muted text-muted-foreground border-border hover:text-foreground'
                    }`}
                  >
                    Contrarian Tradeoff
                  </button>
                </div>

                <button
                  type="button"
                  onClick={handleGenerateComment}
                  disabled={isGeneratingComment}
                  className="px-4 py-1.5 bg-primary hover:bg-primary/90 text-primary-foreground rounded-lg text-xs font-semibold flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                >
                  {isGeneratingComment && <RefreshCw size={13} className="animate-spin" />}
                  <span>Generate Comment</span>
                </button>
              </div>

              {/* Generated Comment Result Box */}
              {generatedComment && (
                <div className="p-3.5 bg-muted/30 rounded-lg border border-border space-y-2 animate-in fade-in duration-200">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                      <CheckCircle2 size={12} className="text-primary" />
                      Verified Contextual Comment
                    </span>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-mono text-muted-foreground">{generatedComment.length} chars</span>
                      <button
                        type="button"
                        onClick={() => {
                          navigator.clipboard.writeText(generatedComment);
                          setCopiedComment(true);
                          toast.success("Comment copied!");
                          setTimeout(() => setCopiedComment(false), 2000);
                        }}
                        className="p-1 text-muted-foreground hover:text-foreground hover:bg-muted rounded cursor-pointer"
                        title="Copy comment"
                      >
                        {copiedComment ? <Check size={12} className="text-primary" /> : <Copy size={12} />}
                      </button>
                    </div>
                  </div>
                  <p className="text-xs text-foreground leading-relaxed bg-background p-2.5 rounded-lg border border-border">
                    "{generatedComment}"
                  </p>
                  <div className="flex justify-end pt-1">
                    <button
                      type="button"
                      onClick={handleSchedulePrewarm}
                      disabled={isSchedulingPrewarm}
                      className="px-3 py-1.5 bg-primary/10 text-primary hover:bg-primary/20 rounded-lg text-xs font-semibold flex items-center gap-1.5 cursor-pointer"
                    >
                      <Calendar size={12} />
                      <span>Enqueue 3-Touch Pre-Warm For Lead</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Tab 2: Omnichannel Fallback Cascade */}
        {activeTab === 'omnichannel' && (
          <div className="space-y-5">
            {/* Fallback Matrix Architecture Diagram */}
            <div className="p-4 bg-muted/30 border border-border rounded-lg">
              <span className="text-xs font-semibold text-foreground block mb-2.5">
                Omnichannel Waterfall Cascade Architecture
              </span>
              <div className="flex items-center gap-2 text-xs flex-wrap">
                <div className="p-2 rounded-lg bg-card border border-border font-medium text-foreground">
                  1. LinkedIn Pending &gt; {daysThreshold}d
                </div>
                <ArrowRight size={13} className="text-muted-foreground" />
                <div className="p-2 rounded-lg bg-card border border-border font-medium text-foreground">
                  2. Auto-Withdraw Invite
                </div>
                <ArrowRight size={13} className="text-muted-foreground" />
                <div className="p-2 rounded-lg bg-card border border-border font-medium text-foreground">
                  3. Waterfall Email Bridge
                </div>
                <ArrowRight size={13} className="text-muted-foreground" />
                <div className="p-2 rounded-lg bg-card border border-border font-medium text-foreground">
                  4. InMail Fallback
                </div>
              </div>
            </div>

            {/* Scanner Controls */}
            <div className="flex items-center justify-between gap-3 p-3 bg-muted/30 border border-border rounded-lg">
              <div className="flex items-center gap-3">
                <span className="text-xs text-muted-foreground">Timeout Threshold:</span>
                <Select
                  value={String(daysThreshold)}
                  onValueChange={(val) => setDaysThreshold(Number(val))}
                >
                  <SelectTrigger size="sm" className="w-[190px] bg-background border-border text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="5">5 Days Pending</SelectItem>
                    <SelectItem value="7">7 Days Pending (Recommended)</SelectItem>
                    <SelectItem value="10">10 Days Pending</SelectItem>
                    <SelectItem value="14">14 Days Pending</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setShowOmnichannelModal(true)}
                  className="px-3 py-1.5 bg-card hover:bg-muted text-foreground border border-border rounded-lg text-xs font-medium flex items-center gap-1.5 cursor-pointer"
                >
                  <Compass size={12} />
                  <span>Simulate Custom Route</span>
                </button>
                <button
                  type="button"
                  onClick={handleScanFallbacks}
                  disabled={isScanningFallback}
                  className="px-3 py-1.5 bg-primary hover:bg-primary/90 text-primary-foreground rounded-lg text-xs font-semibold flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                >
                  {isScanningFallback ? <RefreshCw size={12} className="animate-spin" /> : <Layers size={12} />}
                  <span>Scan Stuck Invitations ({stuckLeads.length})</span>
                </button>
              </div>
            </div>

            {/* Stuck Invitations Table */}
            <div className="space-y-2">
              <span className="text-xs font-semibold text-foreground">
                Stuck Prospects Ready for Automated Channel Transition:
              </span>
              {stuckLeads.map((lead) => (
                <div key={lead.lead_id} className="p-3 bg-card border border-border rounded-lg flex items-center justify-between gap-3 text-xs">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-foreground">{lead.first_name} {lead.last_name}</span>
                      <span className="text-muted-foreground">@ {lead.company}</span>
                      <span className="text-xs px-2 py-0.5 rounded-md bg-muted text-muted-foreground border border-border font-mono">
                        {lead.days_pending}d pending
                      </span>
                    </div>
                    <div className="text-xs text-muted-foreground mt-0.5">
                      Recommended: <strong className="text-primary uppercase">{lead.recommended_channel}</strong>
                      {lead.email ? ` - Verified: ${lead.email}` : ' - InMail Credits available'}
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => handleExecuteCascade(lead)}
                    disabled={executingLeadId === lead.lead_id}
                    className="px-3 py-1.5 bg-primary hover:bg-primary/90 text-primary-foreground rounded-lg text-xs font-semibold flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                  >
                    {executingLeadId === lead.lead_id ? <RefreshCw size={12} className="animate-spin" /> : <Send size={12} />}
                    <span>Cascade to {lead.recommended_channel.toUpperCase()}</span>
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tab 3: Thought Leadership Studio */}
        {activeTab === 'content' && (
          <div className="space-y-4">
            {/* Hook Framework Selector */}
            <div>
              <label className="text-xs font-semibold text-foreground block mb-1.5">
                Select B2B Hook Framework:
              </label>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {[
                  { id: 'CONTRARIAN_TRUTH', label: 'Contrarian Truth' },
                  { id: 'CASE_STUDY_METRIC', label: 'Case Study Metric' },
                  { id: 'UNPOPULAR_OPINION', label: 'Unpopular Opinion' },
                  { id: 'MISTAKE_AUDIT', label: 'The 3 Mistakes' },
                  { id: 'FRAMEWORK_TEARDOWN', label: 'Framework Teardown' },
                  { id: 'BEHIND_THE_CURTAIN', label: 'Lab Experiment' }
                ].map((fw) => (
                  <button
                    key={fw.id}
                    type="button"
                    onClick={() => setFrameworkId(fw.id)}
                    className={`p-2.5 rounded-lg text-xs font-medium border text-left cursor-pointer transition-all ${
                      frameworkId === fw.id
                        ? 'bg-primary/10 text-primary border-primary font-semibold'
                        : 'bg-card text-muted-foreground border-border hover:text-foreground hover:bg-muted/30'
                    }`}
                  >
                    {fw.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Configuration Inputs */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              <div>
                <label className="text-muted-foreground font-medium block mb-1">Topic:</label>
                <input
                  type="text"
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  className="w-full bg-background border border-border rounded-lg px-3 py-2 text-foreground outline-none focus:border-primary"
                  placeholder="e.g. SDR Deliverability"
                />
              </div>
              <div>
                <label className="text-muted-foreground font-medium block mb-1">Audience:</label>
                <input
                  type="text"
                  value={audience}
                  onChange={(e) => setAudience(e.target.value)}
                  className="w-full bg-background border border-border rounded-lg px-3 py-2 text-foreground outline-none focus:border-primary"
                  placeholder="e.g. Sales Ops Leaders"
                />
              </div>
            </div>

            <div className="flex justify-end">
              <button
                type="button"
                onClick={handleGeneratePost}
                disabled={isGeneratingPost}
                className="px-4 py-1.5 bg-primary hover:bg-primary/90 text-primary-foreground rounded-lg text-xs font-semibold flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
              >
                {isGeneratingPost && <RefreshCw size={13} className="animate-spin" />}
                <span>Generate LinkedIn Thought Leadership Post</span>
              </button>
            </div>

            {/* Generated Post Preview */}
            {generatedPost && (
              <div className="p-4 bg-muted/30 rounded-lg border border-border space-y-3 animate-in fade-in duration-200">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                    <FileText size={13} className="text-primary" />
                    Formatted LinkedIn Post Preview
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        navigator.clipboard.writeText(generatedPost);
                        setCopiedPost(true);
                        toast.success("Post copied to clipboard!");
                        setTimeout(() => setCopiedPost(false), 2000);
                      }}
                      className="p-1 text-muted-foreground hover:text-foreground hover:bg-muted rounded cursor-pointer"
                      title="Copy post"
                    >
                      {copiedPost ? <Check size={13} className="text-primary" /> : <Copy size={13} />}
                    </button>
                  </div>
                </div>

                <div className="p-3 bg-background rounded-lg border border-border text-xs text-foreground whitespace-pre-wrap leading-relaxed max-h-60 overflow-y-auto">
                  {generatedPost}
                </div>

                <div className="flex justify-end gap-2 pt-1">
                  <button
                    type="button"
                    onClick={handleSchedulePost}
                    disabled={isSchedulingPost}
                    className="px-4 py-1.5 bg-primary/10 text-primary hover:bg-primary/20 rounded-lg text-xs font-semibold flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                  >
                    <Calendar size={13} />
                    <span>Schedule For Auto-Publish</span>
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {showOmnichannelModal && (
        <OmnichannelRetargetingStudioModal
          initialLeadId={initialLeadId}
          onClose={() => setShowOmnichannelModal(false)}
        />
      )}
    </div>
  );
}
