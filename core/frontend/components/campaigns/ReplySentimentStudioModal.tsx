import React, { useState, useEffect } from "react";
import {
  Bot,
  MessageSquare,
  Calendar,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ArrowRight,
  RefreshCw,
  X,
  Zap,
  Clock,
  UserCheck,
  Ban,
  Lock,
  Layers,
  Download,
  Save,
} from "lucide-react";
import { toast } from "sonner";
import { fetchWithAuth as apiFetch } from "../../lib/apiClient";
import { usePaywall } from "../../contexts/PaywallContext";

export interface ClassificationResult {
  sentiment: "positive" | "negative" | "neutral" | string;
  intent:
    | "meeting_requested"
    | "positive_interest"
    | "out_of_office"
    | "not_interested"
    | "objection"
    | "wrong_contact"
    | string;
  confidence: number;
  auto_action: string;
  requires_human_attention: boolean;
  ooo_data?: {
    has_return_date: boolean;
    return_date: string | null;
    snooze_days: number;
    date_source: string;
  };
  ooo_details?: {
    has_return_date: boolean;
    return_date: string | null;
    snooze_days: number;
    date_source: string;
  };
}

interface ReplySentimentStudioModalProps {
  isOpen: boolean;
  onClose: () => void;
  campaignId?: string;
}

const STORAGE_KEY_RULES = "elein_reply_sentiment_rules_v1";

function sanitizeCsvCell(val: any): string {
  if (val === null || val === undefined) return '""';
  let s = String(val).trim();
  if (s && ["=", "+", "-", "@", "\t", "\r"].includes(s[0])) {
    s = "'" + s;
  }
  return `"${s.replace(/"/g, '""')}"`;
}

export const ReplySentimentStudioModal: React.FC<ReplySentimentStudioModalProps> = ({
  isOpen,
  onClose,
  campaignId,
}) => {
  const { openPaywall } = usePaywall();
  const [activeTab, setActiveTab] = useState<"classifier" | "ooo_rules" | "actions">("classifier");

  // Classifier state
  const [testText, setTestText] = useState(
    "Hi Alex, I am currently out of the office on annual leave, returning October 28th. For urgent issues please reach out to support."
  );
  const [testSubject, setTestSubject] = useState("Re: Quick question regarding your pipeline");
  const [isClassifying, setIsClassifying] = useState(false);
  const [classification, setClassification] = useState<ClassificationResult | null>(null);
  const [classifyError, setClassifyError] = useState<string | null>(null);
  const [history, setHistory] = useState<
    Array<{
      subject: string;
      text: string;
      result: ClassificationResult;
      timestamp: string;
    }>
  >([]);

  // OOO Settings State
  const [autoSnoozeEnabled, setAutoSnoozeEnabled] = useState(true);
  const [fallbackSnoozeDays, setFallbackSnoozeDays] = useState(7);
  const [maxSnoozeDays, setMaxSnoozeDays] = useState(90);
  const [autoResumeWhenElapsed, setAutoResumeWhenElapsed] = useState(true);

  // Pipeline Action Rules
  const [autoHaltOnOptOut, setAutoHaltOnOptOut] = useState(true);
  const [tagHotOnMeetingRequest, setTagHotOnMeetingRequest] = useState(true);
  const [generateBattlecardOnObjection, setGenerateBattlecardOnObjection] = useState(true);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY_RULES);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (typeof parsed.autoSnoozeEnabled === "boolean") setAutoSnoozeEnabled(parsed.autoSnoozeEnabled);
        if (typeof parsed.fallbackSnoozeDays === "number") setFallbackSnoozeDays(parsed.fallbackSnoozeDays);
        if (typeof parsed.maxSnoozeDays === "number") setMaxSnoozeDays(parsed.maxSnoozeDays);
        if (typeof parsed.autoResumeWhenElapsed === "boolean") setAutoResumeWhenElapsed(parsed.autoResumeWhenElapsed);
        if (typeof parsed.autoHaltOnOptOut === "boolean") setAutoHaltOnOptOut(parsed.autoHaltOnOptOut);
        if (typeof parsed.tagHotOnMeetingRequest === "boolean") setTagHotOnMeetingRequest(parsed.tagHotOnMeetingRequest);
        if (typeof parsed.generateBattlecardOnObjection === "boolean") setGenerateBattlecardOnObjection(parsed.generateBattlecardOnObjection);
      }
    } catch {
      // Ignore storage read errors
    }
  }, []);

  if (!isOpen) return null;

  const handleSaveRules = () => {
    const clampedFallback = Math.max(1, Math.min(30, Number(fallbackSnoozeDays) || 7));
    const clampedMax = Math.max(14, Math.min(90, Number(maxSnoozeDays) || 90));
    setFallbackSnoozeDays(clampedFallback);
    setMaxSnoozeDays(clampedMax);
    try {
      localStorage.setItem(
        STORAGE_KEY_RULES,
        JSON.stringify({
          autoSnoozeEnabled,
          fallbackSnoozeDays: clampedFallback,
          maxSnoozeDays: clampedMax,
          autoResumeWhenElapsed,
          autoHaltOnOptOut,
          tagHotOnMeetingRequest,
          generateBattlecardOnObjection,
        })
      );
      toast.success("Autonomous sentiment & OOO snooze policy saved.");
    } catch {
      toast.error("Unable to persist policy in browser storage.");
    }
  };

  const handleExportCsv = () => {
    const rowsToExport = history.length > 0
      ? history
      : classification
      ? [{ subject: testSubject, text: testText, result: classification, timestamp: new Date().toISOString() }]
      : [];

    if (rowsToExport.length === 0) {
      toast.error("Run at least one classification to export an audit CSV.");
      return;
    }

    const headers = [
      "Timestamp",
      "Subject",
      "Message Snippet",
      "Intent",
      "Sentiment",
      "Confidence (%)",
      "Auto Action",
      "Requires Human Attention",
      "OOO Return Date",
      "Snooze Days",
    ];
    const lines = [headers.join(",")];
    for (const item of rowsToExport) {
      const ooo = item.result.ooo_data || item.result.ooo_details;
      lines.push(
        [
          sanitizeCsvCell(item.timestamp),
          sanitizeCsvCell(item.subject),
          sanitizeCsvCell(item.text.slice(0, 200)),
          sanitizeCsvCell(item.result.intent),
          sanitizeCsvCell(item.result.sentiment),
          sanitizeCsvCell(Math.round((item.result.confidence || 0) * 100)),
          sanitizeCsvCell(item.result.auto_action),
          sanitizeCsvCell(item.result.requires_human_attention ? "YES" : "NO"),
          sanitizeCsvCell(ooo?.return_date || ""),
          sanitizeCsvCell(ooo?.snooze_days ?? ""),
        ].join(",")
      );
    }

    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", `reply_sentiment_audit_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    toast.success("Sentiment classification audit exported to CSV!");
  };

  const handleRunClassification = async () => {
    setIsClassifying(true);
    setClassifyError(null);
    try {
      const res = await apiFetch("/api/elein/inbox/classify-reply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message_text: testText,
          subject: testSubject,
          campaign_id: campaignId,
          apply_actions: false,
        }),
      });

      if (res.status === 402) {
        openPaywall({
          featureName: "Inbound AI Reply Sentiment & Intent Classifier",
          minTier: "PRO",
        });
        setClassifyError("Growth Pro required: Inbound Sentiment Classification is locked on Free tier.");
        return;
      }

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail?.message || errData.detail || "Classification failed");
      }

      const data = await res.json();
      setClassification(data.classification);
      setHistory((prev) => [
        {
          subject: testSubject,
          text: testText,
          result: data.classification,
          timestamp: new Date().toISOString(),
        },
        ...prev.slice(0, 24),
      ]);
    } catch (err: any) {
      setClassifyError(err.message || "An unexpected error occurred during classification.");
    } finally {
      setIsClassifying(false);
    }
  };

  const loadSample = (type: "meeting" | "ooo" | "optout" | "objection" | "positive") => {
    switch (type) {
      case "meeting":
        setTestText("Hey Alex, sounds good! Are you free Thursday at 2pm? Or pick a slot at calendly.com/prospect/15min");
        setTestSubject("Re: Strategy Session");
        break;
      case "ooo":
        setTestText("Thank you for your email. I am out of the office on annual leave, returning October 28th. Contact my team in my absence.");
        setTestSubject("Automatic reply: Out of Office");
        break;
      case "optout":
        setTestText("Please remove me from your list and do not contact me again.");
        setTestSubject("Unsubscribe");
        break;
      case "objection":
        setTestText("We already use Apollo for our outbound pipeline and are locked into an annual contract through December.");
        setTestSubject("Re: Quick question");
        break;
      case "positive":
        setTestText("Sounds very interesting! Could you send over pricing and a quick deck?");
        setTestSubject("Re: Ele-in introduction");
        break;
    }
    setClassification(null);
    setClassifyError(null);
  };

  const getIntentBadge = (intent: string) => {
    switch (intent) {
      case "meeting_requested":
        return <span className="px-2.5 py-1 text-xs font-medium rounded-md bg-primary/10 text-primary flex items-center gap-1.5"><Calendar size={12} /> Meeting Requested</span>;
      case "positive_interest":
        return <span className="px-2.5 py-1 text-xs font-medium rounded-md bg-primary/10 text-primary flex items-center gap-1.5"><CheckCircle2 size={12} /> Positive Interest</span>;
      case "out_of_office":
        return <span className="px-2.5 py-1 text-xs font-medium rounded-md bg-muted text-muted-foreground border border-border flex items-center gap-1.5"><Clock size={12} /> Out of Office</span>;
      case "not_interested":
        return <span className="px-2.5 py-1 text-xs font-medium rounded-md bg-muted text-muted-foreground border border-border flex items-center gap-1.5"><Ban size={12} /> Opt-Out / Not Interested</span>;
      case "objection":
        return <span className="px-2.5 py-1 text-xs font-medium rounded-md bg-muted text-muted-foreground border border-border flex items-center gap-1.5"><ShieldCheck size={12} /> Objection Raised</span>;
      default:
        return <span className="px-2.5 py-1 text-xs font-medium rounded-md bg-muted text-muted-foreground border border-border flex items-center gap-1.5"><MessageSquare size={12} /> {intent}</span>;
    }
  };

  const oooInfo = classification?.ooo_data || classification?.ooo_details;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-4xl max-h-[90vh] bg-card border border-border rounded-xl shadow-lg flex flex-col overflow-hidden text-foreground">
        
        {/* Header */}
        <div className="px-6 py-4 border-b border-border bg-background flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold tracking-tight text-foreground">
              Inbound Reply Sentiment & OOO Snooze Studio
            </h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Zero-shot sentiment classification, auto-return date extraction, and campaign pause pacing.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleExportCsv}
              className="px-3 py-1.5 rounded-lg border border-border bg-card hover:bg-muted text-foreground text-xs font-medium flex items-center gap-1.5 transition-colors cursor-pointer"
            >
              <Download size={13} className="text-muted-foreground" />
              <span>Export Audit CSV</span>
            </button>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="flex items-center gap-1 px-6 pt-3 border-b border-border bg-background text-xs">
          <button
            type="button"
            onClick={() => setActiveTab("classifier")}
            className={`flex items-center gap-2 px-4 py-2.5 font-medium border-b-2 transition-all cursor-pointer ${
              activeTab === "classifier"
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <MessageSquare size={14} /> Zero-Shot Classifier Testbench
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("ooo_rules")}
            className={`flex items-center gap-2 px-4 py-2.5 font-medium border-b-2 transition-all cursor-pointer ${
              activeTab === "ooo_rules"
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <Clock size={14} /> OOO Auto-Snooze Rules
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("actions")}
            className={`flex items-center gap-2 px-4 py-2.5 font-medium border-b-2 transition-all cursor-pointer ${
              activeTab === "actions"
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <Zap size={14} /> Autonomous Intent Triggers
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {activeTab === "classifier" && (
            <div className="space-y-6">
              {/* Presets */}
              <div className="space-y-2">
                <span className="text-xs font-semibold text-muted-foreground">Quick Test Presets:</span>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => loadSample("ooo")}
                    className="px-3 py-1.5 text-xs font-medium rounded-lg bg-muted/30 border border-border hover:bg-muted transition-colors flex items-center gap-1.5 text-foreground cursor-pointer"
                  >
                    <Clock size={12} className="text-muted-foreground" /> Out of Office (With Date)
                  </button>
                  <button
                    type="button"
                    onClick={() => loadSample("meeting")}
                    className="px-3 py-1.5 text-xs font-medium rounded-lg bg-muted/30 border border-border hover:bg-muted transition-colors flex items-center gap-1.5 text-foreground cursor-pointer"
                  >
                    <Calendar size={12} className="text-muted-foreground" /> Meeting Requested
                  </button>
                  <button
                    type="button"
                    onClick={() => loadSample("positive")}
                    className="px-3 py-1.5 text-xs font-medium rounded-lg bg-muted/30 border border-border hover:bg-muted transition-colors flex items-center gap-1.5 text-foreground cursor-pointer"
                  >
                    <CheckCircle2 size={12} className="text-muted-foreground" /> Pricing / Deck Request
                  </button>
                  <button
                    type="button"
                    onClick={() => loadSample("objection")}
                    className="px-3 py-1.5 text-xs font-medium rounded-lg bg-muted/30 border border-border hover:bg-muted transition-colors flex items-center gap-1.5 text-foreground cursor-pointer"
                  >
                    <ShieldCheck size={12} className="text-muted-foreground" /> Competitor Objection
                  </button>
                  <button
                    type="button"
                    onClick={() => loadSample("optout")}
                    className="px-3 py-1.5 text-xs font-medium rounded-lg bg-muted/30 border border-border hover:bg-muted transition-colors flex items-center gap-1.5 text-foreground cursor-pointer"
                  >
                    <Ban size={12} className="text-muted-foreground" /> Unsubscribe / Opt-Out
                  </button>
                </div>
              </div>

              {/* Text Input */}
              <div className="space-y-3">
                <div>
                  <label className="text-xs font-medium text-muted-foreground mb-1 block">Inbound Subject Line (Optional)</label>
                  <input
                    type="text"
                    value={testSubject}
                    onChange={(e) => setTestSubject(e.target.value)}
                    className="w-full px-3.5 py-2 text-xs bg-background border border-border rounded-lg text-foreground focus:outline-none focus:border-primary transition-colors"
                    placeholder="e.g. Re: Outreach Subject"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground mb-1 block">Inbound Message Body</label>
                  <textarea
                    rows={4}
                    value={testText}
                    onChange={(e) => setTestText(e.target.value)}
                    className="w-full p-3.5 text-xs bg-background border border-border rounded-lg text-foreground focus:outline-none focus:border-primary transition-colors leading-relaxed font-mono"
                    placeholder="Paste email body or LinkedIn reply message..."
                  />
                </div>
              </div>

              {/* Classify Button */}
              <div className="flex items-center justify-between">
                <p className="text-xs text-muted-foreground">
                  Protected by prompt injection defense and tenant isolation guardrails.
                </p>
                <button
                  type="button"
                  onClick={handleRunClassification}
                  disabled={isClassifying || !testText.trim()}
                  className="px-4 py-2 text-xs font-semibold rounded-lg bg-primary hover:bg-primary/90 disabled:opacity-50 text-primary-foreground flex items-center gap-2 transition-all cursor-pointer"
                >
                  {isClassifying ? (
                    <>
                      <RefreshCw size={14} className="animate-spin" /> Classifying Inbound Intent...
                    </>
                  ) : (
                    <span>Classify Sentiment & Intent</span>
                  )}
                </button>
              </div>

              {/* Error Notice */}
              {classifyError && (
                <div className="p-3.5 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-xs flex items-center gap-3">
                  <AlertTriangle size={16} className="shrink-0" />
                  <span>{classifyError}</span>
                </div>
              )}

              {/* Results Breakdown */}
              {classification && (
                <div className="p-5 rounded-lg bg-muted/30 border border-border space-y-4 animate-in fade-in duration-200">
                  <div className="flex items-center justify-between border-b border-border pb-3">
                    <div className="flex items-center gap-3">
                      <span className="text-xs font-semibold text-muted-foreground">Classified Intent:</span>
                      {getIntentBadge(classification.intent)}
                    </div>
                    <div className="flex items-center gap-3 text-xs">
                      <span className="text-muted-foreground">Sentiment:</span>
                      <span
                        className={`font-semibold text-xs px-2 py-0.5 rounded-md ${
                          classification.sentiment === "positive"
                            ? "bg-primary/10 text-primary"
                            : "bg-muted text-muted-foreground border border-border"
                        }`}
                      >
                        {classification.sentiment}
                      </span>
                      <span className="text-border">|</span>
                      <span className="text-muted-foreground">Confidence:</span>
                      <span className="font-mono font-semibold text-foreground">
                        {Math.round(classification.confidence * 100)}%
                      </span>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                    <div className="p-3.5 rounded-lg bg-card border border-border space-y-2">
                      <span className="text-xs font-semibold text-muted-foreground block">Suggested Autonomous Action</span>
                      <div className="font-mono text-primary bg-primary/10 px-2.5 py-1.5 rounded-md">
                        {classification.auto_action}
                      </div>
                      <div className="flex items-center gap-2 pt-1 text-muted-foreground text-xs">
                        <UserCheck size={12} className="text-muted-foreground" />
                        <span>Requires Human Rep Attention: <strong className="text-foreground">{classification.requires_human_attention ? "YES" : "NO"}</strong></span>
                      </div>
                    </div>

                    <div className="p-3.5 rounded-lg bg-card border border-border space-y-2">
                      <span className="text-xs font-semibold text-muted-foreground block">Out-Of-Office Return Timing</span>
                      {oooInfo && (oooInfo.has_return_date || oooInfo.return_date) ? (
                        <div className="space-y-1">
                          <div className="flex items-center justify-between">
                            <span className="text-muted-foreground">Return Date:</span>
                            <span className="font-semibold text-foreground font-mono">{oooInfo.return_date}</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-muted-foreground">Calculated Snooze:</span>
                            <span className="font-semibold text-foreground font-mono">{oooInfo.snooze_days} Days</span>
                          </div>
                          <div className="text-xs text-muted-foreground pt-1">
                            Extraction Method: <code className="text-foreground">{oooInfo.date_source}</code>
                          </div>
                        </div>
                      ) : (
                        <p className="text-muted-foreground">No Out-Of-Office return date detected in this message.</p>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {activeTab === "ooo_rules" && (
            <div className="space-y-5 text-xs">
              <div className="p-4 rounded-lg bg-muted/30 border border-border space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="font-semibold text-foreground text-sm">Autonomous OOO Campaign Pause</h3>
                    <p className="text-muted-foreground text-xs">Automatically snooze active campaign DAG steps when an Out-Of-Office autoreply is detected.</p>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={autoSnoozeEnabled}
                      onChange={(e) => setAutoSnoozeEnabled(e.target.checked)}
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-muted peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-border after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary"></div>
                  </label>
                </div>

                <div className="border-t border-border pt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-foreground font-medium mb-1">Fallback Snooze (Days)</label>
                    <input
                      type="number"
                      min={1}
                      max={30}
                      value={fallbackSnoozeDays}
                      onChange={(e) => setFallbackSnoozeDays(parseInt(e.target.value) || 7)}
                      className="w-full px-3 py-2 bg-background border border-border rounded-lg text-foreground font-mono"
                    />
                    <span className="text-xs text-muted-foreground block mt-1">Used when autoreply does not state an explicit return date.</span>
                  </div>
                  <div>
                    <label className="block text-foreground font-medium mb-1">Maximum Snooze Cap (Days)</label>
                    <input
                      type="number"
                      min={14}
                      max={90}
                      value={maxSnoozeDays}
                      onChange={(e) => setMaxSnoozeDays(parseInt(e.target.value) || 90)}
                      className="w-full px-3 py-2 bg-background border border-border rounded-lg text-foreground font-mono"
                    />
                    <span className="text-xs text-muted-foreground block mt-1">Safety ceiling: clamps outlier replies ("out until 2099").</span>
                  </div>
                </div>

                <div className="border-t border-border pt-4 flex items-center justify-between">
                  <div>
                    <span className="font-medium text-foreground block">Automatic Sequence Resume</span>
                    <span className="text-muted-foreground text-xs">Orchestrator worker automatically wakes snoozed lead when date elapses.</span>
                  </div>
                  <input
                    type="checkbox"
                    checked={autoResumeWhenElapsed}
                    onChange={(e) => setAutoResumeWhenElapsed(e.target.checked)}
                    className="rounded bg-background border-border text-primary focus:ring-0"
                  />
                </div>

                <div className="border-t border-border pt-4 flex justify-end">
                  <button
                    type="button"
                    onClick={handleSaveRules}
                    className="px-4 py-2 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground font-semibold text-xs flex items-center gap-1.5 transition-colors cursor-pointer"
                  >
                    <Save size={13} /> Save OOO Snooze Policy
                  </button>
                </div>
              </div>
            </div>
          )}

          {activeTab === "actions" && (
            <div className="space-y-4 text-xs">
              <div className="p-4 rounded-lg bg-muted/30 border border-border space-y-4">
                <h3 className="font-semibold text-foreground text-sm">Autonomous Inbound Dispatch Triggers</h3>
                
                <div className="space-y-3">
                  <div className="flex items-center justify-between p-3 rounded-lg bg-card border border-border">
                    <div className="flex items-center gap-3">
                      <div className="p-2 rounded-md bg-muted text-muted-foreground border border-border">
                        <Ban size={16} />
                      </div>
                      <div>
                        <span className="font-semibold text-foreground block">Auto-Halt on Negative Opt-Out</span>
                        <span className="text-xs text-muted-foreground">Instantly halt outreach and add prospect to workspace suppression table.</span>
                      </div>
                    </div>
                    <input
                      type="checkbox"
                      checked={autoHaltOnOptOut}
                      onChange={(e) => setAutoHaltOnOptOut(e.target.checked)}
                      className="rounded bg-background border-border text-primary focus:ring-0"
                    />
                  </div>

                  <div className="flex items-center justify-between p-3 rounded-lg bg-card border border-border">
                    <div className="flex items-center gap-3">
                      <div className="p-2 rounded-md bg-muted text-muted-foreground border border-border">
                        <Calendar size={16} />
                      </div>
                      <div>
                        <span className="font-semibold text-foreground block">Tag & Alert on Meeting Request</span>
                        <span className="text-xs text-muted-foreground">Trigger immediate Slack/Email alert to account executive for handoff.</span>
                      </div>
                    </div>
                    <input
                      type="checkbox"
                      checked={tagHotOnMeetingRequest}
                      onChange={(e) => setTagHotOnMeetingRequest(e.target.checked)}
                      className="rounded bg-background border-border text-primary focus:ring-0"
                    />
                  </div>

                  <div className="flex items-center justify-between p-3 rounded-lg bg-card border border-border">
                    <div className="flex items-center gap-3">
                      <div className="p-2 rounded-md bg-muted text-muted-foreground border border-border">
                        <ShieldCheck size={16} />
                      </div>
                      <div>
                        <span className="font-semibold text-foreground block">Auto-Generate Objection Battlecard</span>
                        <span className="text-xs text-muted-foreground">Generate personalized competitive rebuttal when a competitor is named.</span>
                      </div>
                    </div>
                    <input
                      type="checkbox"
                      checked={generateBattlecardOnObjection}
                      onChange={(e) => setGenerateBattlecardOnObjection(e.target.checked)}
                      className="rounded bg-background border-border text-primary focus:ring-0"
                    />
                  </div>
                </div>

                <div className="border-t border-border pt-4 flex justify-end">
                  <button
                    type="button"
                    onClick={handleSaveRules}
                    className="px-4 py-2 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground font-semibold text-xs flex items-center gap-1.5 transition-colors cursor-pointer"
                  >
                    <Save size={13} /> Save Trigger Policy
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-border bg-background flex items-center justify-between text-xs">
          <span className="text-muted-foreground">Autonomous Inbound Routing</span>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 text-xs font-medium rounded-lg border border-border bg-card hover:bg-muted text-foreground transition-colors cursor-pointer"
          >
            Close Studio
          </button>
        </div>

      </div>
    </div>
  );
};
