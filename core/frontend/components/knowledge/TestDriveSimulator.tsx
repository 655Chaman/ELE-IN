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
      <StarBorder
        as="button"
        type="button"
        onClick={() => setIsTestOpen(true)}
        className="group flex-shrink-0 cursor-pointer"
        innerClassName="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-foreground hover:bg-foreground/90 text-background text-sm font-bold transition-all shadow-lg cursor-pointer"
        speed="3s"
      >
        <ElesiumLogo size={16} />
        <span>Elesium Test Objection</span>
      </StarBorder>

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
              initial={{ opacity: 0, scale: 0.96, y: 12 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 12 }}
              className="relative w-full max-w-[660px] bg-white dark:bg-card border border-slate-200 dark:border-border/50 shadow-[0_16px_50px_rgb(0,0,0,0.2)] dark:shadow-2xl rounded-xl flex flex-col overflow-hidden h-[660px] max-h-[92vh]"
            >
              {/* Header */}
              <div className="p-5 border-b border-slate-100 dark:border-border/40 flex justify-between items-center bg-slate-50 dark:bg-muted/10 shrink-0">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-md bg-primary/10 border border-primary/20 flex items-center justify-center shadow-xs">
                    <ElesiumLogo size={20} />
                  </div>
                  <div>
                    <h3 className="font-bold text-sm text-foreground flex items-center gap-2">
                      <span>Elesium Objection Battle Simulator</span>
                      <a
                        href="https://elesium.online"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20 hover:underline"
                      >
                        elesium.online
                      </a>
                    </h3>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Stress-test your knowledge base and playbooks against adversarial prospect pushbacks with Elesium AI.
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-1.5">
                  {testResponses.length > 0 && (
                    <button
                      type="button"
                      onClick={handleClearHistory}
                      title="Clear chat history"
                      className="p-2 text-muted-foreground hover:text-foreground rounded-md hover:bg-slate-200 dark:hover:bg-muted transition-colors cursor-pointer"
                    >
                      <RotateCcw size={15} />
                    </button>
                  )}
                  <button 
                    type="button"
                    onClick={() => setIsTestOpen(false)} 
                    className="text-muted-foreground hover:text-foreground p-2 rounded-md hover:bg-slate-200 dark:hover:bg-muted transition-colors cursor-pointer"
                  >
                    <X size={16} />
                  </button>
                </div>
              </div>

              {/* Chat Feed */}
              <div className="flex-1 overflow-y-auto p-5 sm:p-6 space-y-5 bg-white dark:bg-background/50">
                {/* Intro greeting */}
                <div className="flex gap-3">
                  <div className="w-8 h-8 rounded-full bg-slate-100 dark:bg-muted border border-slate-200 dark:border-border/50 flex items-center justify-center shrink-0 mt-1">
                    <ElesiumLogo size={16} />
                  </div>
                  <div className="bg-slate-50 dark:bg-muted/30 rounded-lg rounded-tl-xs p-4 text-xs sm:text-sm text-foreground max-w-[88%] border border-slate-200 dark:border-border/40 shadow-xs leading-relaxed space-y-2">
                    <p className="font-semibold text-foreground flex items-center gap-1.5">
                      <ElesiumLogo size={14} />
                      <span>Welcome to the AI Battleground.</span>
                    </p>
                    <p className="text-muted-foreground">
                      Type any real objection your prospects throw at you, or click one of the battle-tested adversarial challenges below to test our rebuttal engine.
                    </p>
                  </div>
                </div>

                {/* Empty State: 1-Click Adversarial Challenges Grid */}
                {testResponses.length === 0 && (
                  <div className="pt-2 pb-2">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block mb-2.5">
                      Battle-Tested Adversarial Challenges (1-Click Test):
                    </span>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                      {ADVERSARIAL_CHALLENGES.map((ch) => {
                        const Icon = ch.icon;
                        return (
                          <button
                            key={ch.id}
                            type="button"
                            disabled={isTesting}
                            onClick={() => handleTestDrive(ch.objection)}
                            className="p-3 text-left rounded-lg border border-slate-200 dark:border-border/60 bg-slate-50/50 dark:bg-card/40 hover:bg-slate-100 dark:hover:bg-card hover:border-primary/40 transition-all group flex flex-col justify-between cursor-pointer shadow-2xs"
                          >
                            <div className="flex items-center justify-between w-full mb-1">
                              <span className="text-xs font-bold text-foreground group-hover:text-primary transition-colors flex items-center gap-1.5">
                                <Icon size={13} className="text-primary" />
                                {ch.title}
                              </span>
                              <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-muted text-muted-foreground font-medium">
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
                  <div key={msg.id} className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
                    {msg.role === 'ai' && (
                      <div className="w-8 h-8 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center shrink-0 mt-1">
                        <ElesiumLogo size={18} />
                      </div>
                    )}
                    
                    <div className={`max-w-[85%] ${
                      msg.role === 'user'
                        ? 'bg-primary text-white rounded-lg rounded-tr-xs p-3.5 shadow-xs'
                        : 'bg-slate-50 dark:bg-muted/30 text-foreground border border-slate-200 dark:border-border/40 rounded-lg rounded-tl-xs p-4 shadow-xs'
                    }`}>
                      {msg.role === 'user' && (
                        <div className="text-[10px] text-white/70 uppercase tracking-wider font-bold mb-1">
                          Prospect Objection
                        </div>
                      )}

                      <p className="whitespace-pre-wrap text-xs sm:text-sm leading-relaxed">
                        {msg.content}
                      </p>

                      {/* AI Response Metadata & Action Bar */}
                      {msg.role === 'ai' && (
                        <div className="mt-3 pt-2.5 border-t border-slate-200/60 dark:border-border/40 flex items-center justify-between text-[11px] text-muted-foreground gap-2 flex-wrap">
                          <div className="flex items-center gap-2">
                            {msg.matchedStrategy && (
                              <span className="inline-flex items-center gap-1 font-medium text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                                <Check size={10} />
                                {msg.matchedStrategy}
                              </span>
                            )}
                            {msg.charCount && (
                              <span className="font-mono text-[10px] opacity-75">
                                {msg.charCount} chars (~{Math.max(1, Math.round(msg.charCount / 25))}s read)
                              </span>
                            )}
                          </div>

                          <button
                            type="button"
                            onClick={() => handleCopy(msg.content, idx)}
                            className="inline-flex items-center gap-1 px-2 py-1 rounded-lg hover:bg-slate-200 dark:hover:bg-muted transition-colors font-medium text-[11px] cursor-pointer"
                          >
                            {copiedIndex === idx ? (
                              <>
                                <Check size={12} className="text-emerald-500" />
                                <span className="text-emerald-500">Copied</span>
                              </>
                            ) : (
                              <>
                                <Copy size={12} />
                                <span>Copy Rebuttal</span>
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
                  <div className="flex gap-3">
                    <div className="w-8 h-8 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center shrink-0 mt-1">
                      <ElesiumLogo size={18} className="animate-pulse" />
                    </div>
                    <div className="bg-slate-50 dark:bg-muted/30 rounded-lg rounded-tl-xs p-4 text-xs text-muted-foreground border border-slate-200 dark:border-border/40 shadow-xs flex items-center gap-2">
                      <Loader2 size={13} className="animate-spin text-primary" />
                      <span>Retrieving knowledge base differentiators & synthesizing rebuttal...</span>
                    </div>
                  </div>
                )}
                
                <div ref={scrollEndRef} />
              </div>

              {/* Bottom Challenge Chips Bar (when conversation is active) */}
              {testResponses.length > 0 && (
                <div className="px-5 py-2 border-t border-slate-100 dark:border-border/40 bg-slate-50/50 dark:bg-muted/5 flex items-center gap-1.5 overflow-x-auto scrollbar-none shrink-0">
                  <span className="text-[10px] uppercase font-bold text-muted-foreground shrink-0 mr-1">
                    Quick Test:
                  </span>
                  {ADVERSARIAL_CHALLENGES.map((ch) => (
                    <button
                      key={ch.id}
                      type="button"
                      disabled={isTesting}
                      onClick={() => handleTestDrive(ch.objection)}
                      className="px-2.5 py-1 rounded-lg text-[11px] font-medium bg-white dark:bg-card border border-slate-200 dark:border-border/50 text-foreground hover:border-primary/40 transition-colors whitespace-nowrap cursor-pointer disabled:opacity-50"
                    >
                      {ch.title}
                    </button>
                  ))}
                </div>
              )}

              {/* Composer Input */}
              <div className="p-4 border-t border-slate-100 dark:border-border/40 bg-slate-50 dark:bg-muted/10 shrink-0 relative z-10">
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
                    placeholder="Type a prospect objection (e.g. 'We don't have budget right now')..." 
                    maxLength={1000}
                    disabled={isTesting}
                    className="w-full bg-white dark:bg-background border border-slate-200 dark:border-border/60 rounded-xl pl-4 pr-24 py-3 text-xs sm:text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary transition-all shadow-xs disabled:opacity-60" 
                  />
                  
                  <div className="absolute right-2 flex items-center gap-1">
                    {isTesting ? (
                      <button 
                        type="button"
                        onClick={handleStopGeneration}
                        title="Stop generation"
                        className="bg-amber-500/20 text-amber-500 hover:bg-amber-500/30 px-2.5 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1 transition-colors cursor-pointer"
                      >
                        <Square size={12} className="fill-current" />
                        <span>Stop</span>
                      </button>
                    ) : (
                      <button 
                        type="button"
                        onClick={() => handleTestDrive()} 
                        disabled={!testMessage.trim()} 
                        className="bg-foreground text-background hover:bg-foreground/90 p-2 rounded-lg transition-colors disabled:opacity-40 cursor-pointer shadow-xs"
                        title="Test Objection"
                      >
                        <Play size={13} className="fill-current" />
                      </button>
                    )}
                  </div>
                </div>

                <div className="mt-1.5 px-1 flex justify-between items-center text-[10px] text-muted-foreground">
                  <span>Press Enter to simulate</span>
                  <span>{testMessage.length} / 1,000 chars</span>
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </>
  );
}
