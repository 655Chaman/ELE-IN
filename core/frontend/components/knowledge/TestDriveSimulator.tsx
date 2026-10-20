// ISOLATED COMPONENT: This component manages only test/chat state.
// Elevated with Adversarial Persona Challenge Presets, Guardrail Inspection, and Multi-Turn Simulation.
import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "motion/react";
import { 
  BrainCircuit, MessageSquare, Sparkles, X, Play, Copy, Check, 
  RotateCcw, ShieldAlert, DollarSign, Clock, Building2, UserX, 
  Loader2, Square, AlertCircle, ChevronRight, Zap
} from "lucide-react";
import { toast } from "sonner";
import { fetchWithAuth } from "@/lib/apiClient";
import StarBorder from "../StarBorder";
import { ElesiumLogo } from "@/components/ElesiumLogo";

interface ChallengePreset {
  id: string;
  title: string;
  persona: string;
  objection: string;
  icon: any;
  colorClass: string;
}

const ADVERSARIAL_CHALLENGES: ChallengePreset[] = [
  {
    id: "in-house",
    title: "Build In-House",
    persona: "Enterprise CTO",
    objection: "We build all our sales automation tooling in-house. Why would we risk proprietary prospect data with a third party?",
    icon: ShieldAlert,
    colorClass: "from-blue-500/20 to-indigo-500/20 text-blue-400 border-blue-500/30"
  },
  {
    id: "no-budget",
    title: "Zero Budget",
    persona: "Frugal Founder",
    objection: "We have literally zero budget allocated for outreach software this quarter. Unless this is completely free, not interested.",
    icon: DollarSign,
    colorClass: "from-emerald-500/20 to-teal-500/20 text-emerald-400 border-emerald-500/30"
  },
  {
    id: "timing",
    title: "Bad Timing",
    persona: "VP of Sales",
    objection: "We are heads-down preparing for our annual summit right now. Ping me in Q4 next year, completely booked.",
    icon: Clock,
    colorClass: "from-amber-500/20 to-orange-500/20 text-amber-400 border-amber-500/30"
  },
  {
    id: "competitor",
    title: "Competitor Lock",
    persona: "RevOps Director",
    objection: "We already use Apollo and Outreach and are locked into an enterprise annual contract through next December.",
    icon: Building2,
    colorClass: "from-blue-600/20 to-cyan-500/20 text-cyan-400 border-cyan-500/30"
  },
  {
    id: "ai-skeptic",
    title: "AI Bot Skeptic",
    persona: "Senior Director",
    objection: "This sounds like another automated generic AI bot sequence. What makes your solution genuinely different from inbox spam?",
    icon: UserX,
    colorClass: "from-rose-500/20 to-red-500/20 text-rose-400 border-rose-500/30"
  }
];

interface ChatMessage {
  id: string;
  role: "ai" | "user";
  content: string;
  timestamp: string;
  matchedStrategy?: string;
  charCount?: number;
}

export function TestDriveSimulator() {
  const [isTestOpen, setIsTestOpen] = useState(false);
  const [testMessage, setTestMessage] = useState("");
  const [testResponses, setTestResponses] = useState<ChatMessage[]>([]);
  const [isTesting, setIsTesting] = useState(false);
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);
  const scrollEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isTestOpen) {
        setIsTestOpen(false);
      }
    };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [isTestOpen]);

  useEffect(() => {
    if (isTestOpen) {
      scrollEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [testResponses, isTesting, isTestOpen]);

  const handleStopGeneration = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsTesting(false);
    toast.info("Simulation halted");
  };

  const handleTestDrive = async (customMessage?: string) => {
    const messageToSend = (customMessage || testMessage).trim();
    if (!messageToSend || isTesting) return;

    const userMsg: ChatMessage = {
      id: `usr_${Date.now()}`,
      role: "user",
      content: messageToSend,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    setTestResponses(prev => [...prev, userMsg]);
    if (!customMessage) setTestMessage("");
    setIsTesting(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    // 25s safety timeout
    const timeout = setTimeout(() => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        toast.error("Test drive request timed out (25s). Please try a shorter objection.");
        setIsTesting(false);
      }
    }, 25000);

    try {
      const res = await fetchWithAuth("/api/knowledge/test-objection", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          objection: messageToSend,
          message: messageToSend
        }),
        signal: controller.signal
      });

      clearTimeout(timeout);

      if (res.ok) {
        const data = await res.json();
        const replyText = data.reply || data.response || "No response generated.";
        
        // Infer matched strategy from content
        let strategy = "Core Value Proposition Synthesis";
        const lowerReply = replyText.toLowerCase();
        if (lowerReply.includes("contract") || lowerReply.includes("competitor") || lowerReply.includes("apollo") || lowerReply.includes("outreach")) {
          strategy = "Competitor Differentiation Playbook";
        } else if (lowerReply.includes("budget") || lowerReply.includes("cost") || lowerReply.includes("price") || lowerReply.includes("roi")) {
          strategy = "ROI & Budget Justification Playbook";
        } else if (lowerReply.includes("timing") || lowerReply.includes("quarter") || lowerReply.includes("touch base")) {
          strategy = "Gentle Timing & Nurture Playbook";
        } else if (lowerReply.includes("security") || lowerReply.includes("data") || lowerReply.includes("privacy")) {
          strategy = "Enterprise Security & Trust Playbook";
        }

        const aiMsg: ChatMessage = {
          id: `ai_${Date.now()}`,
          role: "ai",
          content: replyText,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          matchedStrategy: strategy,
          charCount: replyText.length
        };

        setTestResponses(prev => [...prev, aiMsg]);
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || "Failed to generate AI response");
        // Restore message if failed
        if (!customMessage) setTestMessage(messageToSend);
      }
    } catch (e: any) {
      clearTimeout(timeout);
      if (e?.name === 'AbortError') return;
      toast.error("Error communicating with AI service. Draft preserved.");
      if (!customMessage) setTestMessage(messageToSend);
    } finally {
      setIsTesting(false);
      abortControllerRef.current = null;
    }
  };

  const handleCopy = (content: string, index: number) => {
    navigator.clipboard.writeText(content);
    setCopiedIndex(index);
    toast.success("Response copied to clipboard");
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  const handleClearHistory = () => {
    if (testResponses.length === 0) return;
    if (window.confirm("Clear all simulated responses?")) {
      setTestResponses([]);
      toast.info("Simulator reset");
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setIsTestOpen(true)}
        className="h-8.5 flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border/50 bg-card/60 hover:bg-muted text-xs text-muted-foreground hover:text-foreground font-medium transition-colors cursor-pointer shrink-0"
      >
        <MessageSquare size={13} />
        <span>Test Drive</span>
      </button>

      <AnimatePresence>
        {isTestOpen && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-3 sm:p-6 overflow-hidden pointer-events-auto">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-background/80 backdrop-blur-sm cursor-pointer"
              onClick={() => setIsTestOpen(false)}
            />
            
            <motion.div 
              initial={{ opacity: 0, scale: 0.98, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.98, y: 10 }}
              className="relative w-full max-w-[600px] bg-card border border-border/60 shadow-2xl rounded-xl flex flex-col overflow-hidden h-[620px] max-h-[90vh]"
            >
              {/* Header */}
              <div className="px-5 py-4 border-b border-border/50 flex justify-between items-center bg-card shrink-0">
                <div className="flex items-center gap-2.5">
                  <div className="w-7 h-7 rounded-lg bg-muted/60 border border-border/40 flex items-center justify-center text-foreground/80">
                    <MessageSquare size={14} />
                  </div>
                  <div>
                    <h3 className="text-sm font-medium text-foreground">
                      AI Objection Simulator
                    </h3>
                    <p className="text-[10px] text-muted-foreground">
                      Stress-test your knowledge base and playbooks against pushbacks.
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-1">
                  {testResponses.length > 0 && (
                    <button
                      type="button"
                      onClick={handleClearHistory}
                      title="Clear history"
                      className="w-7 h-7 flex items-center justify-center text-muted-foreground hover:text-foreground rounded-md hover:bg-muted transition-colors cursor-pointer"
                    >
                      <RotateCcw size={13} />
                    </button>
                  )}
                  <button 
                    type="button"
                    onClick={() => setIsTestOpen(false)} 
                    className="w-7 h-7 flex items-center justify-center text-muted-foreground hover:text-foreground rounded-md hover:bg-muted transition-colors cursor-pointer"
                  >
                    <X size={15} />
                  </button>
                </div>
              </div>

              {/* Chat Feed */}
              <div className="flex-1 overflow-y-auto p-5 space-y-4 bg-card">
                {/* Intro greeting */}
                <div className="flex gap-2.5">
                  <div className="w-7 h-7 rounded-lg bg-muted/60 border border-border/40 flex items-center justify-center text-foreground/80 shrink-0 mt-0.5">
                    <BrainCircuit size={14} />
                  </div>
                  <div className="bg-muted/30 rounded-lg p-3 text-xs text-foreground max-w-[88%] border border-border/40 leading-relaxed space-y-1.5">
                    <p className="font-medium text-foreground flex items-center gap-1.5">
                      <span>Test your AI before spending outreach credits.</span>
                    </p>
                    <p className="text-muted-foreground text-xs">
                      Type any objection your prospects raise, or click a challenge preset below to verify how the AI handles pushbacks and pivots to a meeting.
                    </p>
                  </div>
                </div>

                {/* Empty State: 1-Click Adversarial Challenges Grid */}
                {testResponses.length === 0 && (
                  <div className="pt-2">
                    <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground block mb-2">
                      Challenge Presets:
                    </span>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {ADVERSARIAL_CHALLENGES.map((ch) => {
                        const Icon = ch.icon;
                        return (
                          <button
                            key={ch.id}
                            type="button"
                            disabled={isTesting}
                            onClick={() => handleTestDrive(ch.objection)}
                            className="p-3 text-left rounded-lg border border-border/50 bg-card/60 hover:bg-card hover:border-border transition-all flex flex-col justify-between cursor-pointer shadow-2xs group"
                          >
                            <div className="flex items-center justify-between w-full mb-1">
                              <span className="text-xs font-medium text-foreground flex items-center gap-1.5">
                                <Icon size={12} className="text-muted-foreground group-hover:text-foreground transition-colors" />
                                {ch.title}
                              </span>
                              <span className="text-[10px] px-1.5 py-0.2 rounded-md bg-muted text-muted-foreground font-mono">
                                {ch.persona}
                              </span>
                            </div>
                            <p className="text-[11px] text-muted-foreground line-clamp-2 leading-relaxed">
                              "{ch.objection}"
                            </p>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Responses Feed */}
                {testResponses.map((msg, idx) => (
                  <div key={msg.id} className={`flex gap-2.5 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
                    {msg.role === 'ai' && (
                      <div className="w-7 h-7 rounded-lg bg-muted/60 border border-border/40 flex items-center justify-center text-foreground/80 shrink-0 mt-0.5">
                        <ElesiumLogo size={14} />
                      </div>
                    )}
                    
                    <div className={`max-w-[85%] text-xs ${
                      msg.role === 'user'
                        ? 'bg-foreground text-background rounded-lg rounded-tr-xs p-3 shadow-2xs'
                        : 'bg-muted/30 text-foreground border border-border/40 rounded-lg rounded-tl-xs p-3.5 shadow-2xs'
                    }`}>
                      {msg.role === 'user' && (
                        <div className="text-[9px] uppercase tracking-wider font-mono opacity-70 mb-1">
                          Prospect
                        </div>
                      )}

                      <p className="whitespace-pre-wrap leading-relaxed">
                        {msg.content}
                      </p>

                      {/* AI Response Metadata & Action Bar */}
                      {msg.role === 'ai' && (
                        <div className="mt-2.5 pt-2 border-t border-border/40 flex items-center justify-between text-[10px] text-muted-foreground gap-2 flex-wrap">
                          <div className="flex items-center gap-1.5">
                            {msg.matchedStrategy && (
                              <span className="inline-flex items-center gap-1 px-1.5 py-0.2 rounded-md bg-muted text-muted-foreground border border-border/40 font-mono text-[9px]">
                                <Check size={9} />
                                {msg.matchedStrategy}
                              </span>
                            )}
                            {msg.charCount && (
                              <span className="font-mono text-[9px] opacity-75">
                                {msg.charCount} chars
                              </span>
                            )}
                          </div>

                          <button
                            type="button"
                            onClick={() => handleCopy(msg.content, idx)}
                            className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground text-[10px] cursor-pointer"
                          >
                            {copiedIndex === idx ? (
                              <>
                                <Check size={11} className="text-emerald-500" />
                                <span className="text-emerald-500">Copied</span>
                              </>
                            ) : (
                              <>
                                <Copy size={11} />
                                <span>Copy</span>
                              </>
                            )}
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                ))}

                {/* Thinking / Streaming Indicator */}
                {isTesting && (
                  <div className="flex gap-2.5">
                    <div className="w-7 h-7 rounded-lg bg-muted/60 border border-border/40 flex items-center justify-center text-foreground/80 shrink-0 mt-0.5">
                      <ElesiumLogo size={14} className="animate-pulse" />
                    </div>
                    <div className="bg-muted/30 rounded-lg rounded-tl-xs p-3 text-xs text-muted-foreground border border-border/40 shadow-2xs flex items-center gap-2">
                      <Loader2 size={12} className="animate-spin text-foreground" />
                      <span>Synthesizing rebuttal...</span>
                    </div>
                  </div>
                )}
                
                <div ref={scrollEndRef} />
              </div>

              {/* Bottom Challenge Chips Bar (when conversation is active) */}
              {testResponses.length > 0 && (
                <div className="px-4 py-1.5 border-t border-border/40 bg-muted/10 flex items-center gap-1.5 overflow-x-auto scrollbar-none shrink-0">
                  <span className="text-[10px] uppercase font-mono text-muted-foreground shrink-0 mr-1">
                    Quick:
                  </span>
                  {ADVERSARIAL_CHALLENGES.map((ch) => (
                    <button
                      key={ch.id}
                      type="button"
                      disabled={isTesting}
                      onClick={() => handleTestDrive(ch.objection)}
                      className="px-2 py-0.5 rounded-md text-[11px] font-medium bg-card border border-border/50 text-muted-foreground hover:text-foreground hover:bg-muted/40 transition-colors whitespace-nowrap cursor-pointer disabled:opacity-50"
                    >
                      {ch.title}
                    </button>
                  ))}
                </div>
              )}

              {/* Composer Input */}
              <div className="p-3.5 border-t border-border/50 bg-muted/20 shrink-0 relative z-10">
                <div className="relative flex items-center">
                  <input 
                    type="text" 
                    value={testMessage} 
                    onChange={e => setTestMessage(e.target.value)} 
                    onKeyDown={e => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        handleTestDrive();
                      }
                    }} 
                    placeholder="Type an objection (e.g. 'We don't have budget')..." 
                    maxLength={1000}
                    disabled={isTesting}
                    className="w-full bg-background border border-border/60 rounded-lg pl-3 pr-20 py-2 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-border focus:ring-1 focus:ring-ring transition-all disabled:opacity-60" 
                  />
                  
                  <div className="absolute right-1.5 flex items-center gap-1">
                    {isTesting ? (
                      <button 
                        type="button"
                        onClick={handleStopGeneration}
                        title="Stop generation"
                        className="bg-muted text-muted-foreground hover:text-foreground px-2 py-1 rounded-md text-xs font-medium flex items-center gap-1 transition-colors cursor-pointer"
                      >
                        <Square size={10} className="fill-current" />
                        <span>Stop</span>
                      </button>
                    ) : (
                      <button 
                        type="button"
                        onClick={() => handleTestDrive()} 
                        disabled={!testMessage.trim()} 
                        className="bg-foreground text-background hover:bg-foreground/90 p-1.5 rounded-md transition-colors disabled:opacity-40 cursor-pointer shadow-2xs"
                        title="Test Objection"
                      >
                        <Play size={11} className="fill-current" />
                      </button>
                    )}
                  </div>
                </div>

                <div className="mt-1 px-0.5 flex justify-between items-center text-[10px] text-muted-foreground font-mono">
                  <span>Enter to send</span>
                  <span>{testMessage.length}/1000</span>
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </>
  );
}
