// ISOLATED COMPONENT: This component manages only test/chat state.
// Do NOT add synthesis or persona state here.
import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "motion/react";
import { BrainCircuit, MessageSquare, Sparkles, X, Play } from "lucide-react";
import { toast } from "sonner";
import { fetchWithAuth } from "@/lib/apiClient";
import StarBorder from "../StarBorder";

export function TestDriveSimulator() {
  const [isTestOpen, setIsTestOpen] = useState(false);
  const [testMessage, setTestMessage] = useState("");
  const [testResponses, setTestResponses] = useState<{role: "ai" | "user", content: string}[]>([]);
  const [isTesting, setIsTesting] = useState(false);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isTestOpen) {
        setIsTestOpen(false);
      }
    };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [isTestOpen]);

  const handleTestDrive = async () => {
    if (!testMessage.trim()) return;
    setTestResponses(prev => [...prev, { role: "user", content: testMessage }]);
    const currentMsg = testMessage;
    setTestMessage("");
    setIsTesting(true);
    try {
      const res = await fetchWithAuth("/api/knowledge/personas/test-drive", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: currentMsg })
      });
      if (res.ok) {
        const data = await res.json();
        setTestResponses(prev => [...prev, { role: "ai", content: data.response }]);
      } else {
         toast.error("Failed to generate response");
      }
    } catch (e) {
      toast.error("Error generating response");
    } finally {
      setIsTesting(false);
    }
  };

  return (
    <>
      <StarBorder
        as="button"
        onClick={() => setIsTestOpen(true)}
        className="group flex-shrink-0"
        innerClassName="flex items-center gap-2 px-4 py-2.5 rounded-[18px] bg-foreground hover:bg-foreground/90 text-background text-sm font-bold transition-all shadow-lg"
        speed="3s"
      >
        <MessageSquare size={14} /> Test AI
      </StarBorder>

      <AnimatePresence>
        {isTestOpen && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6 overflow-hidden pointer-events-auto">
             <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-background/80 backdrop-blur-sm cursor-pointer"
              onClick={() => setIsTestOpen(false)}
            />
            <motion.div 
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="relative w-full max-w-[400px] bg-white dark:bg-card border border-slate-200 dark:border-border/50 shadow-[0_8px_40px_rgb(0,0,0,0.12)] dark:shadow-2xl rounded-[32px] flex flex-col overflow-hidden h-[550px]"
            >
              <div className="p-6 border-b border-slate-100 dark:border-border/40 flex justify-between items-center bg-slate-50 dark:bg-muted/10">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-blue-50 dark:bg-blue-500/20 border border-blue-100 dark:border-blue-500/30 flex items-center justify-center">
                    <Sparkles className="w-4 h-4 text-blue-600 dark:text-blue-500" />
                  </div>
                  <h3 className="font-semibold text-sm">Test Your AI</h3>
                </div>
                <button onClick={() => setIsTestOpen(false)} className="text-muted-foreground hover:text-foreground p-2 rounded-xl hover:bg-slate-200 dark:hover:bg-muted"><X size={16} /></button>
              </div>
              
              <div className="flex-1 overflow-y-auto p-6 space-y-4 bg-white dark:bg-background/50">
                <div className="flex gap-4">
                  <div className="w-8 h-8 rounded-full bg-slate-100 dark:bg-muted border border-slate-200 dark:border-border/50 flex items-center justify-center shrink-0">
                    <BrainCircuit size={14} className="text-foreground" />
                  </div>
                  <div className="bg-slate-50 dark:bg-muted/30 rounded-2xl rounded-tl-sm p-4 text-sm text-foreground max-w-[85%] border border-slate-200 dark:border-border/40 shadow-sm leading-relaxed">
                    Hello! I'm your trained AI. Provide a sample prospect message or objection, and I'll generate a response based on your playbooks.
                  </div>
                </div>
                {testResponses.map((msg, i) => (
                  <div key={i} className={`flex gap-4 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
                    {msg.role === 'ai' && (
                      <div className="w-8 h-8 rounded-full bg-slate-100 dark:bg-muted border border-slate-200 dark:border-border/50 flex items-center justify-center shrink-0">
                        <BrainCircuit size={14} className="text-foreground" />
                      </div>
                    )}
                    <div className={`${msg.role === 'user' ? 'bg-blue-600 text-white rounded-2xl rounded-tr-sm' : 'bg-slate-50 dark:bg-muted/30 rounded-2xl rounded-tl-sm text-foreground border border-slate-200 dark:border-border/40 shadow-sm'} p-4 text-sm max-w-[85%] leading-relaxed`}>
                      {msg.content}
                    </div>
                  </div>
                ))}
                {isTesting && (
                  <div className="flex gap-4">
                     <div className="w-8 h-8 rounded-full bg-slate-100 dark:bg-muted border border-slate-200 dark:border-border/50 flex items-center justify-center shrink-0">
                        <BrainCircuit size={14} className="text-foreground" />
                      </div>
                      <div className="bg-slate-50 dark:bg-muted/30 rounded-2xl rounded-tl-sm p-4 text-sm text-muted-foreground animate-pulse">
                        Thinking...
                      </div>
                  </div>
                )}
              </div>
              
              <div className="p-4 border-t border-slate-100 dark:border-border/40 bg-slate-50 dark:bg-muted/10 relative z-10">
                <div className="relative">
                  <input type="text" value={testMessage} onChange={e => setTestMessage(e.target.value)} onKeyDown={e => e.key === "Enter" && handleTestDrive()} placeholder="Type a prospect objection..." className="w-full bg-white dark:bg-background border border-slate-200 dark:border-border/50 rounded-xl pl-4 pr-12 py-3 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 transition-all shadow-sm" />
                  <button onClick={handleTestDrive} disabled={isTesting || !testMessage.trim()} className="absolute right-2 top-1/2 -translate-y-1/2 bg-foreground text-background hover:bg-foreground/90 p-1.5 rounded-lg transition-colors disabled:opacity-50">
                    <Play size={14} className="fill-current" />
                  </button>
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </>
  );
}
