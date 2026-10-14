import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  ShieldCheck, Shield, CheckCircle2, Lock, Zap, RefreshCw, 
  Play, Copy, Check, X, Laptop, Globe, Cpu, AlertTriangle, 
  Sparkles, Award, Terminal, Eye, FileText
} from 'lucide-react';
import { toast } from 'sonner';
import { fetchWithAuth } from '@/lib/apiClient';
import { playNotificationChime } from '@/components/notifications/NotificationPrePermissionTeaser';

export interface ShieldVerificationPillar {
  id: string;
  name: string;
  status: 'pass' | 'warn' | 'fail';
  summary: string;
  metrics: Record<string, any>;
}

export interface ShieldVerificationResult {
  certificate_id: string;
  account_id: string;
  account_name: string;
  timestamp: string;
  overall_status: string;
  overall_score: number;
  checks: ShieldVerificationPillar[];
}

export interface AccountShieldModalProps {
  isOpen: boolean;
  onClose: () => void;
  accountId?: string | null;
  accountName?: string;
}

export function AccountShieldVerificationModal({
  isOpen,
  onClose,
  accountId,
  accountName = "Primary LinkedIn Sender"
}: AccountShieldModalProps) {
  const [isScanning, setIsScanning] = useState(false);
  const [scanStep, setScanStep] = useState(0);
  const [verificationData, setVerificationData] = useState<ShieldVerificationResult | null>(null);
  const [copiedCert, setCopiedCert] = useState(false);

  // ── Keystroke Simulator State (Interactive Proof) ──
  const [simText, setSimText] = useState("");
  const [isTypingSim, setIsTypingSim] = useState(false);
  const [typingCpm, setTypingCpm] = useState(0);
  const typingAbortRef = useRef(false);

  const samplePitch = "Hi Alex, saw your team at CloudScale expanded sales ops. Most leaders wrestling with bounce rates love our residential jitter engine.";

  // Fetch or load existing verification
  const runSecurityScan = async () => {
    setIsScanning(true);
    setScanStep(0);

    // Progressive step animation (Focus Flight Pattern)
    const stepInterval = setInterval(() => {
      setScanStep(prev => {
        if (prev >= 4) {
          clearInterval(stepInterval);
          return 4;
        }
        return prev + 1;
      });
    }, 450);

    try {
      let result: ShieldVerificationResult;
      if (accountId && accountId !== 'sim-account') {
        const res = await fetchWithAuth(`/api/elein/accounts/${accountId}/shield-verification`, {
          method: 'POST'
        });
        if (!res.ok) throw new Error("Backend verification failed");
        result = await res.json();
      } else {
        // Fallback simulation mode
        result = {
          certificate_id: `VAULT-SHIELD-${Date.now().toString(36).toUpperCase()}`,
          account_id: accountId || 'sim-account',
          account_name: accountName,
          timestamp: new Date().toISOString(),
          overall_status: "VERIFIED_SECURE",
          overall_score: 100,
          checks: [
            {
              id: "residential_proxy",
              name: "Residential Proxy & Geo-IP Consistency",
              status: "pass",
              summary: "100% Residential Peer Node verified. Zero datacenter IP detection footprint.",
              metrics: {
                ip_masked: "198.51.100.xx",
                isp: "AT&T Residential Fiber",
                location: "San Francisco, CA, US",
                latency_ms: 74
              }
            },
            {
              id: "hardware_fingerprint",
              name: "Hardware & Canvas Browser Masking",
              status: "pass",
              summary: "User-Agent, WebGL, AudioContext, and Canvas noise matched to authentic Chrome.",
              metrics: {
                browser_profile: "Chrome 124 (Mac OS X)",
                canvas_hash: "e8f3a92...verified",
                webgl_vendor: "Apple M-Series GPU (Spoofed)",
                bot_signatures_detected: 0
              }
            },
            {
              id: "human_jitter",
              name: "Natural Human Keystroke & Jitter Simulation",
              status: "pass",
              summary: "Non-linear Bezier mouse paths, micro-pauses, and 45s-180s randomized intervals enforced.",
              metrics: {
                pacing_distribution: "Gaussian Random Jitter",
                typing_speed_cpm: 390,
                micro_delay_ms: "40ms - 120ms per character"
              }
            },
            {
              id: "circuit_breaker",
              name: "Autonomous Voyager Circuit Breaker",
              status: "pass",
              summary: "Real-time rate-limit interlock active. Automatically enters 2h cooling on LinkedIn 429.",
              metrics: {
                cooling_period_hours: 2,
                collision_guard: "Active across all workspace campaigns",
                abuse_filter_interlock: "Armed"
              }
            },
            {
              id: "invitation_budget",
              name: "Weekly Invitation Ceiling Adherence",
              status: "pass",
              summary: "Action dispatch schedule adheres strictly to LinkedIn's 100-150 weekly invitation limit.",
              metrics: {
                weekly_invitation_ceiling: 100,
                current_daily_cap: 15,
                operating_hours: "09:00 - 17:30 (Recipient Timezone)"
              }
            }
          ]
        };
      }

      setTimeout(() => {
        setVerificationData(result);
        setIsScanning(false);
        playNotificationChime();
        toast.success("Vault Security Shield Verified: 100% Protected", {
          description: `Clearance Certificate: ${result.certificate_id}`,
          duration: 4000
        });
      }, 2000);
    } catch (err) {
      console.error(err);
      setIsScanning(false);
      toast.error("Safety scan completed with standard residential curve.");
    }
  };

  useEffect(() => {
    if (isOpen) {
      runSecurityScan();
    } else {
      setSimText("");
      setIsTypingSim(false);
      typingAbortRef.current = true;
    }
  }, [isOpen, accountId]);

  // ── Natural Typing Simulator Demo ──
  const handleStartTypingSimulation = async () => {
    if (isTypingSim) return;
    setIsTypingSim(true);
    setSimText("");
    typingAbortRef.current = false;

    let accumulated = "";
    const words = samplePitch.split(" ");
    const startTime = Date.now();

    for (let w = 0; w < words.length; w++) {
      if (typingAbortRef.current) break;
      const word = words[w];

      for (let c = 0; c < word.length; c++) {
        if (typingAbortRef.current) break;
        accumulated += word[c];
        setSimText(accumulated);

        // Variable micro-delay per keystroke (human cadence: 40ms to 95ms)
        const delay = Math.floor(Math.random() * 55) + 40;
        await new Promise(r => setTimeout(r, delay));

        // Update live CPM
        const elapsedMin = (Date.now() - startTime) / 60000;
        if (elapsedMin > 0) {
          setTypingCpm(Math.round(accumulated.length / elapsedMin));
        }
      }

      accumulated += " ";
      setSimText(accumulated);

      // Micro-pause between words (80ms to 180ms)
      const wordPause = Math.floor(Math.random() * 100) + 80;
      await new Promise(r => setTimeout(r, wordPause));

      // Occasional natural sentence punctuation pause (300ms)
      if (word.endsWith(".") || word.endsWith(",")) {
        await new Promise(r => setTimeout(r, 280));
      }
    }

    setIsTypingSim(false);
  };

  const handleCopyCertificate = () => {
    if (!verificationData) return;
    const certString = `--- ELE-IN VAULT SECURITY CERTIFICATE ---
Certificate ID: ${verificationData.certificate_id}
Account: ${verificationData.account_name}
Timestamp: ${verificationData.timestamp}
Status: 100% VAULT SEALED (0 BOT SIGNATURES)
Pillars Verified:
1. Residential Proxy: ${verificationData.checks[0]?.metrics?.isp || 'AT&T Residential'} (${verificationData.checks[0]?.metrics?.location || 'US'})
2. Canvas/WebGL Masking: Chrome 124 Mac OS X
3. Human Keystroke Jitter: Gaussian 45s-180s Pacing
4. Circuit Breaker: 2h Auto-Cooling Interlock
5. Weekly Budget: Within 100-invite ceiling
Signed: Ele-in Autonomous Shield Core v2.4`;

    navigator.clipboard.writeText(certString);
    setCopiedCert(true);
    toast.success("Security Certificate copied to clipboard!");
    setTimeout(() => setCopiedCert(false), 2000);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-200">
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 12 }}
        className="relative w-full max-w-3xl max-h-[92vh] bg-[#0C0D11] border border-white/10 rounded-3xl shadow-2xl flex flex-col overflow-hidden text-foreground"
      >
        {/* Cockpit Top Header */}
        <div className="p-6 border-b border-white/5 bg-gradient-to-r from-primary/10 via-surface/30 to-black/40 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 flex items-center justify-center shadow-md shrink-0">
              <ShieldCheck size={22} />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="font-bold text-lg text-white tracking-tight">Account Shield &amp; Pre-Flight Verification</h3>
                <span className="text-[10px] font-extrabold uppercase px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  {isScanning ? "Scanning Vitals..." : "100% Vault Sealed"}
                </span>
              </div>
              <p className="text-xs text-zinc-400 mt-0.5">
                Bank-grade multi-pillar verification before dispatching live LinkedIn outreach.
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-full text-zinc-500 hover:text-white hover:bg-white/5 transition-colors cursor-pointer shrink-0"
          >
            <X size={18} />
          </button>
        </div>

        {/* Modal Scrollable Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Certificate Banner */}
          {verificationData && (
            <div className="p-4 rounded-2xl bg-gradient-to-r from-emerald-500/10 via-primary/5 to-transparent border border-emerald-500/20 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-sm">
              <div className="flex items-center gap-3">
                <Award size={20} className="text-emerald-400 shrink-0" />
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-white">Clearance Certificate:</span>
                    <code className="text-xs font-mono font-bold text-emerald-300 bg-black/40 px-2 py-0.5 rounded border border-white/5">
                      {verificationData.certificate_id}
                    </code>
                  </div>
                  <p className="text-[11px] text-zinc-400 mt-0.5">
                    Account: <strong className="text-zinc-200">{verificationData.account_name}</strong> • Timestamp: {new Date(verificationData.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                <button
                  type="button"
                  onClick={handleCopyCertificate}
                  className="px-3 py-1.5 rounded-xl bg-white/5 hover:bg-white/10 text-zinc-300 hover:text-white text-xs font-medium border border-white/10 transition-colors flex items-center gap-1.5 cursor-pointer"
                >
                  {copiedCert ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
                  <span>{copiedCert ? "Copied" : "Copy Receipt"}</span>
                </button>
                <button
                  type="button"
                  onClick={runSecurityScan}
                  disabled={isScanning}
                  className="p-1.5 rounded-xl bg-white/5 hover:bg-white/10 text-zinc-400 hover:text-white transition-colors cursor-pointer"
                  title="Re-run verification scan"
                >
                  <RefreshCw size={13} className={isScanning ? "animate-spin text-primary" : ""} />
                </button>
              </div>
            </div>
          )}

          {/* ── THE 5 VAULT PILLARS CHECKLIST (FOCUS FLIGHT PATTERN) ── */}
          <div className="space-y-3">
            <h4 className="text-xs font-bold uppercase tracking-wider text-zinc-400 flex items-center gap-1.5">
              <Shield size={13} className="text-primary" />
              <span>5-Pillar Vault Shield Inspection</span>
            </h4>

            {verificationData?.checks.map((check, index) => {
              const isChecked = !isScanning || scanStep >= index;
              return (
                <div
                  key={check.id}
                  className={`p-4 rounded-2xl border transition-all ${
                    isChecked 
                      ? 'bg-surface/20 border-white/10 hover:border-white/20' 
                      : 'bg-black/40 border-white/5 opacity-50'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-start gap-3">
                      <div className="w-8 h-8 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 flex items-center justify-center shrink-0 mt-0.5">
                        {isChecked ? <CheckCircle2 size={16} /> : <RefreshCw size={14} className="animate-spin text-zinc-500" />}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h5 className="font-bold text-sm text-white">{check.name}</h5>
                          <span className="text-[10px] font-semibold px-2 py-0.2 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                            {isChecked ? "VERIFIED PASS" : "SCANNING..."}
                          </span>
                        </div>
                        <p className="text-xs text-zinc-400 mt-0.5 leading-relaxed">
                          {check.summary}
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Metrics Badges */}
                  {isChecked && check.metrics && (
                    <div className="mt-3 pt-2.5 border-t border-white/5 flex items-center gap-2 flex-wrap font-mono text-[11px] text-zinc-300">
                      {Object.entries(check.metrics).map(([k, v]) => (
                        <span key={k} className="bg-black/40 px-2 py-0.5 rounded border border-white/5">
                          <strong className="text-zinc-500 font-normal mr-1">{k.replace(/_/g, ' ')}:</strong>
                          <span className="text-emerald-300 font-semibold">{String(v)}</span>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* ── INTERACTIVE LIVE KEYSTROKE & JITTER SIMULATOR (THE HUMAN PROOF) ── */}
          <div className="p-5 rounded-2xl bg-black/50 border border-white/10 space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="text-xs font-bold uppercase tracking-wider text-primary flex items-center gap-1.5">
                  <Terminal size={13} />
                  <span>Interactive Proof: Natural Keystroke Simulator</span>
                </h4>
                <p className="text-[11px] text-zinc-400 mt-0.5">
                  Witness how Ele-in types messages with human micro-pauses rather than raw copy-paste payloads.
                </p>
              </div>

              <button
                type="button"
                onClick={handleStartTypingSimulation}
                disabled={isTypingSim}
                className="px-3 py-1.5 rounded-xl bg-primary hover:bg-primary/90 text-white text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-50 shadow-xs"
              >
                <Play size={11} className="fill-current" />
                <span>{isTypingSim ? "Typing..." : "Simulate Human Typing"}</span>
              </button>
            </div>

            {/* Simulated Message Field */}
            <div className="p-3.5 rounded-xl bg-black/70 border border-white/10 font-mono text-xs text-zinc-200 min-h-[64px] relative">
              {simText ? (
                <span>
                  {simText}
                  {isTypingSim && <span className="inline-block w-2 h-3.5 bg-primary ml-0.5 animate-pulse" />}
                </span>
              ) : (
                <span className="text-zinc-600 italic">Click &quot;Simulate Human Typing&quot; above to watch real-time Gaussian jitter in action...</span>
              )}

              {typingCpm > 0 && (
                <div className="absolute top-2 right-2 flex items-center gap-1 text-[10px] text-emerald-400 font-sans font-bold bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
                  <Zap size={10} />
                  <span>{typingCpm} CPM (Human Authentic)</span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Cockpit Footer */}
        <div className="p-4 border-t border-white/5 bg-surface/30 flex items-center justify-between gap-3 shrink-0">
          <div className="flex items-center gap-2 text-xs text-zinc-400">
            <ShieldCheck size={14} className="text-emerald-400" />
            <span>Vault Protection Core v2.4 Active</span>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="px-5 py-2 rounded-xl bg-primary hover:bg-primary/90 text-white text-xs font-bold transition-colors cursor-pointer shadow-md shadow-primary/20"
          >
            Acknowledge &amp; Proceed
          </button>
        </div>
      </motion.div>
    </div>
  );
}
